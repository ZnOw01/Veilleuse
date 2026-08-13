#!/usr/bin/python3
"""Tests for the native Veilleuse plugin control helper."""

import datetime
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
HELPER = SCRIPTS / "veilleuse-control"

loader = importlib.machinery.SourceFileLoader("veilleuse_control", str(HELPER))
spec = importlib.util.spec_from_loader("veilleuse_control", loader)
vc = importlib.util.module_from_spec(spec)
sys.modules["veilleuse_control"] = vc
loader.exec_module(vc)

shortcut_loader = importlib.machinery.SourceFileLoader(
    "veilleuse_shortcut_utils", str(SCRIPTS / "shortcut_utils.py")
)
shortcut_spec = importlib.util.spec_from_loader("veilleuse_shortcut_utils", shortcut_loader)
sc = importlib.util.module_from_spec(shortcut_spec)
sys.modules["veilleuse_shortcut_utils"] = sc
shortcut_loader.exec_module(sc)


def cp(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(list(args), returncode, stdout, stderr)


def monitor_state_text(
    brightness="42",
    internal="eDP-1",
    external="DP-1",
    internal_active="eDP-1",
    mirror="",
    focused="eDP-1",
    scaling="1",
    monitors=None,
):
    monitors = monitors or [
        {"name": "eDP-1", "enabled": True, "focused": True, "width": 1920, "height": 1080},
        {"name": "DP-1", "enabled": True, "focused": False, "width": 2560, "height": 1440},
    ]
    lines = [brightness, internal, external, internal_active, mirror, focused, scaling]
    lines.append(json.dumps(monitors))
    return "\n".join(lines) + "\n"


class SimulatedCommands:
    """Deterministic stand-in for omarchy-monitor-state / brightness / hyprsunset."""

    def __init__(self):
        self.brightness_percent = 42
        self.focused = "eDP-1"
        self.temperature = 3500
        self.identity = False
        self.gamma = 100
        self.calls = []
        self.fail_monitor = False
        self.fail_brightness_read = False
        self.apply_brightness = True
        self.readback_count = 0
        self.failures_before_readback = 0
        self.monitor_state_text = None
        self.hyprsunset_available = True
        self.fail_identity_read = False
        self.fail_identity_write = False
        self.brightness_output = None

    def __call__(self, args, *, timeout=None):
        tokens = list(args)
        self.calls.append((tokens, timeout))
        if tokens == ["omarchy-monitor-state"]:
            if self.fail_monitor:
                return cp(tokens, 1, "", "no monitors")
            text = self.monitor_state_text or monitor_state_text(
                brightness=str(self.brightness_percent), focused=self.focused
            )
            return cp(tokens, 0, text, "")
        if tokens[:2] == ["omarchy-brightness-display", "--no-osd"]:
            # --no-osd --monitor NAME  → read
            if len(tokens) == 4 and tokens[2] == "--monitor":
                if self.fail_brightness_read:
                    return cp(tokens, 1, "", "driver busy")
                output = self.brightness_output
                if output is None:
                    output = f"{self.brightness_percent}\n"
                return cp(tokens, 0, output, "")
            # --no-osd --monitor NAME +1%|1%- → one-point write
            if len(tokens) == 5 and tokens[2] == "--monitor":
                if self.apply_brightness:
                    token = tokens[4]
                    if token == "+1%":
                        self.brightness_percent = min(100, self.brightness_percent + 1)
                    elif token == "1%-":
                        self.brightness_percent = max(1, self.brightness_percent - 1)
                return cp(tokens, 0, "", "")
            return cp(tokens, 1, "", "unexpected brightness command")
        if tokens[:2] == ["hyprctl", "hyprsunset"]:
            if not self.hyprsunset_available:
                return cp(tokens, 1, "", "hyprsunset not running")
            command = tokens[2]
            if command == "temperature" and len(tokens) == 3:
                return cp(tokens, 0, f"{self.temperature}\n", "")
            if command == "temperature" and len(tokens) == 4:
                target = int(tokens[3])
                if self.failures_before_readback > 0:
                    self.failures_before_readback -= 1
                else:
                    self.temperature = target
                    self.identity = False
                return cp(tokens, 0, "", "")
            if command == "identity" and len(tokens) == 4 and tokens[3] == "get":
                if self.fail_identity_read:
                    return cp(tokens, 1, "", "identity unavailable")
                return cp(tokens, 0, "true" if self.identity else "false\n", "")
            if command == "identity" and len(tokens) == 3:
                if self.fail_identity_write:
                    return cp(tokens, 1, "", "hyprsunset not running")
                self.identity = True
                return cp(tokens, 0, "", "")
            if command == "gamma" and len(tokens) == 3:
                return cp(tokens, 0, f"{self.gamma}\n", "")
            if command == "gamma" and len(tokens) == 4:
                self.gamma = int(tokens[3])
                return cp(tokens, 0, "", "")
            return cp(tokens, 1, "", "unexpected hyprsunset command")
        return cp(tokens, 127, "", "command not found")

    def brightness_writes(self):
        return [
            tokens
            for tokens, _ in self.calls
            if tokens[:2] == ["omarchy-brightness-display", "--no-osd"]
            and len(tokens) == 5
        ]

    def hyprsunset_sets(self):
        return [
            tokens
            for tokens, _ in self.calls
            if tokens[:2] == ["hyprctl", "hyprsunset"] and len(tokens) >= 4
        ]


class ShortcutReloadSim:
    """Deterministic stand-in for the best-effort ``hyprctl reload`` call.

    The shortcut module runs hyprctl reload after a successful install or
    removal only; the runner records every call so tests can pin both the
    invocation and its best-effort failure behavior.
    """

    def __init__(self, ok=True):
        self.ok = ok
        self.calls = []

    def __call__(self, args, *, timeout=None):
        tokens = list(args)
        self.calls.append((tokens, timeout))
        if self.ok:
            return cp(tokens, 0, "", "")
        return cp(tokens, 1, "", "hyprctl not running")


class HelperModuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.xdg = Path(self.tmp.name)
        self.env_patch = patch.dict(
            os.environ,
            {
                "XDG_CONFIG_HOME": str(self.xdg),
                "XDG_DATA_HOME": str(self.xdg / "data"),
                "XDG_STATE_HOME": str(self.xdg / "state"),
            },
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.addCleanup(self.tmp.cleanup)
        self.sim = SimulatedCommands()
        self.runner_patch = patch.object(vc, "run_command", side_effect=self.sim)
        self.runner_patch.start()
        self.addCleanup(self.runner_patch.stop)

    def run_cli(self, *args):
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = vc.main(list(args))
        return code, stream.getvalue()


class PluginRootTests(HelperModuleTests):
    def test_resolves_plugin_root_from_helper_location(self):
        root = vc.resolve_plugin_root()
        self.assertEqual(root, ROOT)
        self.assertTrue((root / "manifest.json").is_file())

    def test_installed_plugin_resolves_its_own_path(self):
        # A plugin installed at ~/.config/omarchy/plugins/<id> keeps the same
        # layout: manifest.json at root, helper under scripts/.  The helper
        # anchors itself to its own __file__ so the installed location wins.
        install = self.xdg / "omarchy" / "plugins" / "io.github.znow01.veilleuse"
        (install / "scripts").mkdir(parents=True)
        (install / "manifest.json").write_text("{}", encoding="utf-8")
        helper = install / "scripts" / "veilleuse-control"
        helper.write_text("", encoding="utf-8")
        original = vc.__file__
        vc.__file__ = str(helper)
        try:
            root = vc.resolve_plugin_root()
            self.assertEqual(root, install)
        finally:
            vc.__file__ = original


class StatusTests(HelperModuleTests):
    def test_status_combines_monitor_brightness_and_nightlight(self):
        code, output = self.run_cli("status")
        self.assertEqual(code, 0)
        status = json.loads(output)
        self.assertTrue(status["brightness"]["available"])
        self.assertEqual(status["brightness"]["percent"], 42)
        self.assertEqual(status["brightness"]["monitor"], "eDP-1")
        self.assertEqual(status["nightlight"]["temperature"], 3500)
        self.assertTrue(status["nightlight"]["enabled"])
        self.assertEqual(status["nightlight"]["gamma"], 100)
        self.assertEqual(status["schedule"]["night_time"], "15:30")
        self.assertEqual(status["plugin"]["id"], "io.github.znow01.veilleuse")

    def test_status_reports_nightlight_unavailable_when_hyprsunset_missing(self):
        self.sim.hyprsunset_available = False
        code, output = self.run_cli("status")
        self.assertEqual(code, 0)
        status = json.loads(output)
        self.assertFalse(status["nightlight"]["available"])
        self.assertIsNone(status["nightlight"]["temperature"])

    def test_status_brightness_unavailable_without_monitor(self):
        self.sim.fail_monitor = True
        code, output = self.run_cli("status")
        status = json.loads(output)
        self.assertFalse(status["brightness"]["available"])
        self.assertIsNone(status["brightness"]["percent"])

    def test_status_ignores_malformed_monitor_entries(self):
        self.sim.monitor_state_text = monitor_state_text(
            monitors=[
                {"name": None, "enabled": True, "focused": True},
                {"name": "DP-1", "enabled": "yes", "focused": False},
                {"name": "eDP-1", "enabled": True, "focused": True},
            ]
        )
        status = json.loads(self.run_cli("status")[1])
        self.assertEqual(status["monitors"], [{"name": "eDP-1", "enabled": True, "focused": True}])

    def test_status_includes_schedule_period(self):
        code, output = self.run_cli("status")
        status = json.loads(output)
        self.assertIn(status["schedule"]["period"], ("day", "night"))


class StateControlSliceBTests(HelperModuleTests):
    def state_module(self):
        module = vc._state_module()
        self.assertIsNotNone(module)
        return module

    def test_state_loader_is_bytecode_free_and_absent_documents_do_not_write(self):
        module = self.state_module()
        self.assertEqual(module.read_config(), module.DEFAULT_CONFIG)
        self.assertEqual(module.read_state(), module.DEFAULT_STATE)
        self.assertEqual(module.list_history(), [])
        self.assertFalse((self.xdg / "veilleuse" / "config.json").exists())
        self.assertFalse((self.xdg / "state" / "veilleuse" / "state.json").exists())
        self.assertFalse((self.xdg / "state" / "veilleuse" / "history.jsonl").exists())

    def test_status_adds_persistence_sections_without_dropping_live_fields(self):
        module = self.state_module()
        module.write_config(
            {
                "schema": 1,
                "presets": {"desk": {"temperature": 4200, "gamma": 85}},
                "default_preset": "desk",
            }
        )
        module.write_state(
            dict(
                module.DEFAULT_STATE,
                schedule_enabled=False,
                snooze_until=4102444800,
                transition_seconds=45,
                origin="preset",
            )
        )
        module.append_history({"time": "2026-08-13T10:00:00Z", "operation": "old", "origin": "manual"})
        module.append_history({"time": "2026-08-13T11:00:00Z", "operation": "new", "origin": "preset"})

        code, output = self.run_cli("status")
        self.assertEqual(code, 0)
        status = json.loads(output)
        self.assertEqual(status["plugin"]["id"], vc.PLUGIN_ID)
        self.assertEqual(status["brightness"]["percent"], 42)
        self.assertEqual(status["nightlight"]["temperature"], 3500)
        self.assertIn("preflight", status)
        self.assertEqual(status["automation"]["schedule_enabled"], False)
        self.assertEqual(status["automation"]["transition_seconds"], 45)
        self.assertEqual(status["automation"]["origin"], "preset")
        self.assertEqual(status["presets"]["default_preset"], "desk")
        self.assertEqual([item["name"] for item in status["presets"]["builtins"]], ["reading", "work", "cinema"])
        self.assertEqual(status["presets"]["user"][0]["name"], "desk")
        self.assertEqual([item["operation"] for item in status["history"]], ["new", "old"])

    def test_corrupt_state_only_fails_automation_section(self):
        module = self.state_module()
        path = module.state_path()
        path.parent.mkdir(parents=True)
        path.write_text("{\"schema\": 1,", encoding="utf-8")

        status = json.loads(self.run_cli("status")[1])
        self.assertEqual(status["brightness"]["percent"], 42)
        self.assertEqual(status["nightlight"]["temperature"], 3500)
        self.assertFalse(status["automation"]["available"])
        self.assertEqual(status["automation"]["error_code"], "invalid_json")
        self.assertEqual(status["presets"]["default_preset"], "reading")
        self.assertEqual(status["history"], [])

    def test_corrupt_config_and_history_fail_only_their_sections(self):
        module = self.state_module()
        config = module.config_path()
        config.parent.mkdir(parents=True)
        config.write_text("{\"schema\": 1,", encoding="utf-8")
        history = module.history_path()
        history.parent.mkdir(parents=True, exist_ok=True)
        history.write_text("not-json\n", encoding="utf-8")

        status = json.loads(self.run_cli("status")[1])
        self.assertEqual(status["brightness"]["percent"], 42)
        self.assertEqual(status["nightlight"]["temperature"], 3500)
        self.assertFalse(status["presets"]["available"])
        self.assertEqual(status["presets"]["error_code"], "invalid_json")
        self.assertEqual(status["history"], [])
        self.assertFalse(status["history_status"]["available"])
        self.assertEqual(status["history_status"]["error_code"], "invalid_json")

    def test_preflight_reports_bounded_read_only_checks_with_stable_errors(self):
        calls = []

        def runner(args, *, timeout=None):
            calls.append((list(args), timeout))
            return cp(args, 127, "", "command not found")

        with patch.object(vc, "run_command", side_effect=runner):
            result = vc.preflight()

        self.assertIn("helper", result)
        self.assertIn("commands", result)
        self.assertIn("backend", result)
        self.assertIn("checks", result)
        self.assertLessEqual(len(calls), 3)
        self.assertTrue(all(timeout is not None and timeout <= vc.COMMAND_TIMEOUT for _, timeout in calls))
        self.assertFalse(result["ok"])
        failed = [check for check in result["checks"] if not check["ok"]]
        self.assertTrue(failed)
        self.assertTrue(all(check["error_code"] for check in failed))
        self.assertTrue(all(check["error"] for check in failed))
        self.assertTrue(all(any(token in check["error"] for token in ("Comando", "Backend", "Tiempo")) for check in failed))

    def test_preflight_uses_one_monitor_probe_when_backend_is_healthy(self):
        calls = []

        def runner(args, *, timeout=None):
            tokens = list(args)
            calls.append((tokens, timeout))
            if tokens == list(vc.MONITOR_STATE_COMMAND):
                return cp(tokens, 0, monitor_state_text(), "")
            if tokens[:3] == ["omarchy-brightness-display", "--no-osd", "--monitor"]:
                return cp(tokens, 0, "42\n", "")
            if tokens == ["hyprctl", "hyprsunset", "identity", "get"]:
                return cp(tokens, 0, "false\n", "")
            return cp(tokens, 127, "", "command not found")

        with patch.object(vc, "run_command", side_effect=runner):
            result = vc.preflight()

        self.assertTrue(result["commands"]["omarchy-monitor-state"]["ok"])
        self.assertEqual(
            sum(tokens == list(vc.MONITOR_STATE_COMMAND) for tokens, _timeout in calls),
            1,
        )
        self.assertEqual(len(calls), 3)

    def test_preflight_reports_missing_brightness_command_without_a_monitor(self):
        def runner(args, *, timeout=None):
            tokens = list(args)
            if tokens == list(vc.MONITOR_STATE_COMMAND):
                return cp(tokens, 1, "", "no monitors")
            if tokens == ["hyprctl", "hyprsunset", "identity", "get"]:
                return cp(tokens, 127, "", "command not found")
            return cp(tokens, 127, "", "command not found")

        with patch.object(vc, "run_command", side_effect=runner):
            with patch("shutil.which", return_value=None):
                result = vc.preflight()

        brightness = result["commands"]["omarchy-brightness-display"]
        self.assertFalse(brightness["ok"])
        self.assertEqual(brightness["error_code"], "missing_command")
        self.assertIn("Comando ausente", brightness["error"])

    def test_history_cli_lists_newest_first_and_clear_is_explicit(self):
        module = self.state_module()
        module.append_history({"time": "2026-08-13T10:00:00Z", "operation": "old"})
        module.append_history({"time": "2026-08-13T11:00:00Z", "operation": "new"})

        code, output = self.run_cli("history", "list")
        self.assertEqual(code, 0)
        self.assertEqual([item["operation"] for item in json.loads(output)["history"]], ["new", "old"])

        code, output = self.run_cli("history", "clear")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["history"], [])
        self.assertTrue(module.history_path().exists())
        self.assertEqual(module.history_path().read_text(encoding="utf-8"), "")

    def test_settings_get_set_validates_presets_and_does_not_touch_schedule(self):
        module = self.state_module()
        module.write_config(
            {
                "schema": 1,
                "presets": {"desk": {"temperature": 4200, "gamma": 85}},
                "default_preset": "desk",
            }
        )
        schedule = self.xdg / "hypr" / "hyprsunset.conf"
        schedule.parent.mkdir(parents=True)
        schedule.write_text("# untouched\n", encoding="utf-8")

        code, output = self.run_cli("settings", "get")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["settings"]["default_preset"], "desk")

        code, output = self.run_cli("settings", "set", "--default-preset", "work")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["settings"]["default_preset"], "work")
        self.assertEqual(module.read_config()["default_preset"], "work")
        self.assertEqual(schedule.read_text(encoding="utf-8"), "# untouched\n")

        code, output = self.run_cli("settings", "set", "--default-preset", "missing")
        self.assertNotEqual(code, 0)
        self.assertEqual(json.loads(output)["error_code"], "invalid_config")
        self.assertEqual(module.read_config()["default_preset"], "work")


class BrightnessTests(HelperModuleTests):
    def test_brightness_read_uses_focused_monitor(self):
        code, output = self.run_cli("brightness")
        self.assertEqual(code, 0)
        result = json.loads(output)
        self.assertEqual(result["percent"], 42)
        self.assertEqual(result["monitor"], "eDP-1")

    def test_brightness_set_delegates_one_relative_step_to_same_monitor(self):
        code, output = self.run_cli("brightness", "60")
        self.assertEqual(code, 0)
        result = json.loads(output)
        self.assertEqual(result["brightness"]["percent"], 43)
        writes = self.sim.brightness_writes()
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0], ["omarchy-brightness-display", "--no-osd", "--monitor", "eDP-1", "+1%"])

    def test_brightness_set_clamps_intent_but_never_moves_more_than_one_point(self):
        code, output = self.run_cli("brightness", "0")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["brightness"]["percent"], 41)
        code, output = self.run_cli("brightness", "150")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["brightness"]["percent"], 42)
        writes = self.sim.brightness_writes()
        self.assertEqual(writes[0][4], "1%-")
        self.assertEqual(writes[1][4], "+1%")

    def test_brightness_equal_target_issues_no_write(self):
        code, output = self.run_cli("brightness", "42")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["brightness"]["percent"], 42)
        self.assertEqual(self.sim.brightness_writes(), [])

    def test_brightness_set_rejects_non_numeric(self):
        code, output = self.run_cli("brightness", "abc")
        self.assertNotEqual(code, 0)
        self.assertIn("error", output.lower())

    def test_brightness_read_rejects_out_of_range_native_output(self):
        self.sim.brightness_output = "101\n"
        percent, error = vc.read_brightness("eDP-1")
        self.assertIsNone(percent)
        self.assertEqual(error, "Salida de brillo no reconocida")


class FinalIntegrationCliTests(HelperModuleTests):
    def test_final_cli_grammar_matches_panel_commands(self):
        parser = vc.build_parser()
        commands = (
            ("brightness", "60", "--monitor", "DP-1"),
            ("preset", "list"),
            ("preset", "save", "desk", "--temperature", "4200", "--gamma", "85"),
            ("preset", "delete", "desk"),
            ("preset", "apply", "reading", "--monitor", "focused", "--transition-seconds", "0"),
            ("snooze", "status"),
            ("snooze", "set", "--minutes", "30"),
            ("snooze", "until-tomorrow"),
            ("snooze", "clear"),
            ("transition", "--temperature", "4200", "--gamma", "85", "--seconds", "0"),
            ("schedule", "status"),
            ("schedule", "get"),
            ("schedule", "set", "--day-time", "06:00", "--night-time", "15:30", "--day-temp", "6000", "--night-temp", "3500"),
            ("schedule", "enable"),
            ("schedule", "disable"),
            ("reconcile",),
        )
        for command in commands:
            with self.subTest(command=command):
                args = parser.parse_args(command)
                self.assertTrue(callable(args.handler))

    def test_brightness_explicit_monitor_is_validated_and_wired_to_native_step(self):
        code, output = self.run_cli("brightness", "60", "--monitor", "DP-1")
        self.assertEqual(code, 0, output)
        result = json.loads(output)
        self.assertEqual(result["brightness"]["monitor"], "DP-1")
        writes = self.sim.brightness_writes()
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][3], "DP-1")
        self.assertEqual(writes[0][4], "+1%")

    def test_custom_preset_commands_return_status_compatible_payloads(self):
        code, output = self.run_cli(
            "preset", "save", "desk", "--temperature", "4200", "--gamma", "85", "--brightness", "45"
        )
        self.assertEqual(code, 0, output)
        saved = json.loads(output)
        self.assertTrue(saved["presets"]["available"])
        self.assertEqual(saved["presets"]["user"][0]["name"], "desk")

        code, output = self.run_cli("preset", "apply", "desk", "--monitor", "focused", "--transition-seconds", "0")
        self.assertEqual(code, 0, output)
        applied = json.loads(output)
        self.assertEqual(applied["automation"]["origin"], "preset")
        self.assertEqual(applied["automation"]["last_applied"]["preset"], "desk")
        self.assertTrue(all(call[4] in ("+1%", "1%-") for call in self.sim.brightness_writes()))

        code, output = self.run_cli("preset", "delete", "desk")
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(output)["presets"]["user"], [])

    def test_snooze_transition_reconcile_and_schedule_toggle_are_structured(self):
        schedule = vc.config_path()
        schedule.parent.mkdir(parents=True, exist_ok=True)
        schedule.write_text(
            "profile {\n    time = 06:00\n    identity = true\n}\n\n"
            "profile {\n    time = 15:30\n    temperature = 3500\n}\n",
            encoding="utf-8",
        )

        for command in (
            ("snooze", "status"),
            ("snooze", "set", "--minutes", "30"),
            ("snooze", "clear"),
            ("snooze", "until-tomorrow"),
            ("transition", "--temperature", "4200", "--gamma", "85", "--seconds", "0"),
            ("reconcile",),
        ):
            with self.subTest(command=command):
                code, output = self.run_cli(*command)
                self.assertEqual(code, 0, output)
                payload = json.loads(output)
                self.assertIn("automation", payload)
                self.assertIn("nightlight", payload)

        code, output = self.run_cli("schedule", "disable")
        self.assertEqual(code, 0, output)
        self.assertFalse(json.loads(output)["automation"]["schedule_enabled"])
        code, output = self.run_cli("schedule", "enable")
        self.assertEqual(code, 0, output)
        self.assertTrue(json.loads(output)["automation"]["schedule_enabled"])

    def test_new_command_errors_have_stable_json_codes(self):
        code, output = self.run_cli(
            "preset", "save", "NotValid", "--temperature", "4200", "--gamma", "85"
        )
        self.assertNotEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload["error_code"], "invalid_preset")
        self.assertTrue(payload["error"])


class NightlightTests(HelperModuleTests):
    def test_temperature_set_applies_and_reads_back(self):
        code, output = self.run_cli("nightlight", "temperature", "4000")
        self.assertEqual(code, 0)
        result = json.loads(output)
        self.assertEqual(result["nightlight"]["temperature"], 4000)
        self.assertIn(["hyprctl", "hyprsunset", "temperature", "4000"], self.sim.hyprsunset_sets())

    def test_temperature_set_rejects_out_of_range(self):
        code, output = self.run_cli("nightlight", "temperature", "1000")
        self.assertNotEqual(code, 0)

    def test_natural_applies_identity_and_reads_back(self):
        code, output = self.run_cli("nightlight", "natural")
        self.assertEqual(code, 0)
        result = json.loads(output)
        self.assertTrue(result["nightlight"]["identity"])
        self.assertFalse(result["nightlight"]["enabled"])

    def test_gamma_set_applies_and_reads_back(self):
        code, output = self.run_cli("nightlight", "gamma", "75")
        self.assertEqual(code, 0)
        result = json.loads(output)
        self.assertEqual(result["nightlight"]["gamma"], 75)

    def test_toggle_warm_to_natural(self):
        code, output = self.run_cli("nightlight", "toggle")
        self.assertEqual(code, 0)
        result = json.loads(output)
        self.assertEqual(result["nightlight"]["identity"], True)
        self.assertEqual(result["nightlight"]["enabled"], False)

    def test_toggle_natural_to_warm(self):
        self.sim.identity = True
        self.sim.temperature = 6500
        code, output = self.run_cli("nightlight", "toggle")
        self.assertEqual(code, 0)
        result = json.loads(output)
        self.assertFalse(result["nightlight"]["identity"])
        self.assertTrue(result["nightlight"]["enabled"])

    def test_nightlight_unavailable_fails_cleanly(self):
        self.sim.hyprsunset_available = False
        code, output = self.run_cli("nightlight", "natural")
        self.assertNotEqual(code, 0)
        self.assertIn("error", output.lower())

    def test_failed_nightlight_operation_preserves_error_in_nested_state(self):
        self.sim.fail_identity_write = True
        code, output = self.run_cli("nightlight", "natural")
        self.assertNotEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload["error"], "hyprsunset not running")
        self.assertEqual(payload["state"]["nightlight"]["error"], payload["error"])

    def test_readback_deadline_is_shared_across_nightlight_queries(self):
        calls = []
        now = iter([10.0, 10.6, 11.2])

        def slow_runner(args, *, timeout=None):
            calls.append((list(args), timeout))
            return cp(args, 0, "false\n", "")

        with patch.object(vc, "run_command", side_effect=slow_runner):
            with patch.object(vc.time, "monotonic", side_effect=lambda: next(now)):
                state = vc.read_nightlight(deadline=11.0)

        self.assertFalse(state["available"])
        self.assertIn("Tiempo de espera agotado", state["error"])
        self.assertEqual([call[0][2:] for call in calls], [["identity", "get"], ["temperature"]])
        self.assertAlmostEqual(calls[0][1], 1.0)
        self.assertAlmostEqual(calls[1][1], 0.4)

    def test_nightlight_fails_closed_when_identity_read_is_missing(self):
        self.sim.fail_identity_read = True
        state = vc.read_nightlight()
        self.assertFalse(state["available"])
        self.assertIsNone(state["identity"])
        self.assertIsNone(state["temperature"])

    def test_nightlight_rejects_out_of_range_temperature_readback(self):
        self.sim.temperature = 1000
        state = vc.read_nightlight()
        self.assertFalse(state["available"])
        self.assertIsNone(state["temperature"])


class ScheduleTests(HelperModuleTests):
    def write_config(self, text):
        path = vc.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_schedule_get_returns_parsed_values(self):
        self.write_config(
            "# comment\n"
            "profile {\n"
            "    time = 06:00\n"
            "    identity = true\n"
            "}\n"
            "\n"
            "profile {\n"
            "    time = 15:30\n"
            "    temperature = 3500\n"
            "}\n"
        )
        code, output = self.run_cli("schedule", "get")
        self.assertEqual(code, 0)
        schedule = json.loads(output)
        self.assertEqual(schedule["day_time"], "06:00")
        self.assertEqual(schedule["day_temp"], 6000)
        self.assertTrue(schedule["day_identity"])
        self.assertEqual(schedule["night_time"], "15:30")
        self.assertEqual(schedule["night_temp"], 3500)

    def test_schedule_set_is_atomic_and_preserves_comments(self):
        path = self.write_config(
            "# keep me\n"
            "profile {\n"
            "    time = 06:00\n"
            "    identity = true\n"
            "}\n"
            "\n"
            "profile {\n"
            "    time = 15:30\n"
            "    temperature = 3500\n"
            "}\n"
        )
        original_mode = path.stat().st_mode & 0o7777
        code, output = self.run_cli(
            "schedule", "set",
            "--night-time", "21:00",
            "--day-time", "07:00",
            "--night-temp", "4000",
            "--day-temp", "5900",
            "--no-natural-day",
        )
        self.assertEqual(code, 0)
        result = json.loads(output)
        self.assertEqual(result["schedule"]["night_time"], "21:00")
        self.assertEqual(result["schedule"]["day_time"], "07:00")
        text = path.read_text(encoding="utf-8")
        self.assertIn("# keep me", text)
        self.assertIn("21:00", text)
        self.assertIn("temperature = 4000", text)
        self.assertEqual(path.stat().st_mode & 0o7777, original_mode)

    def test_schedule_set_preserves_unrelated_profiles(self):
        path = self.write_config(
            "profile {\n"
            "    time = 06:00\n"
            "    identity = true\n"
            "}\n"
            "\n"
            "profile {\n"
            "    time = 15:30\n"
            "    temperature = 3500\n"
            "}\n"
            "# unrelated section\n"
            "some_other_setting = 1\n"
        )
        code, _ = self.run_cli(
            "schedule", "set",
            "--night-time", "22:00",
            "--day-time", "06:00",
            "--night-temp", "3800",
            "--day-temp", "6000",
            "--natural-day",
        )
        self.assertEqual(code, 0)
        text = path.read_text(encoding="utf-8")
        self.assertIn("# unrelated section", text)
        self.assertIn("some_other_setting = 1", text)
        self.assertIn("identity = true", text)

    def test_schedule_set_rejects_invalid_unrelated_profile_without_writing(self):
        original = (
            "profile {\n"
            "    time = 06:00\n"
            "    identity = true\n"
            "}\n\n"
            "profile {\n"
            "    time = 15:30\n"
            "    temperature = 3500\n"
            "}\n\n"
            "profile {\n"
            "    time = 12:00\n"
            "    temperature = 7000\n"
            "}\n"
        )
        path = self.write_config(original)
        code, output = self.run_cli(
            "schedule", "set",
            "--night-time", "21:00",
            "--day-time", "07:00",
            "--night-temp", "4000",
            "--day-temp", "6000",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("fuera de rango", output)
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_schedule_set_rejects_invalid_time(self):
        self.write_config(
            "profile {\n    time = 06:00\n    identity = true\n}\n"
            "profile {\n    time = 15:30\n    temperature = 3500\n}\n"
        )
        code, output = self.run_cli(
            "schedule", "set",
            "--night-time", "25:00",
            "--day-time", "06:00",
            "--night-temp", "3500",
            "--day-temp", "6000",
        )
        self.assertNotEqual(code, 0)
        self.assertIn("error", output.lower())

    def test_schedule_get_fails_closed_on_unreadable_config(self):
        with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
            state = vc.schedule_get()
        self.assertFalse(state["available"])
        self.assertIn("denied", state["error"])

    def test_schedule_get_rejects_out_of_range_profile_temperature(self):
        self.write_config(
            "profile {\n    time = 06:00\n    temperature = 7000\n}\n"
            "profile {\n    time = 15:30\n    temperature = 3500\n}\n"
        )
        state = vc.schedule_get()
        self.assertFalse(state["available"])
        self.assertIn("fuera de rango", state["error"])

    def test_schedule_set_writes_bak_copy_of_previous_config(self):
        # README promises a preserved `.bak` copy; pin the actual behavior.
        original = (
            "profile {\n    time = 06:00\n    identity = true\n}\n\n"
            "profile {\n    time = 15:30\n    temperature = 3500\n}\n"
        )
        path = self.write_config(original)
        code, _ = self.run_cli(
            "schedule", "set",
            "--night-time", "21:00",
            "--day-time", "07:00",
            "--night-temp", "4000",
            "--day-temp", "6000",
        )
        self.assertEqual(code, 0)
        bak = path.with_suffix(path.suffix + ".bak")
        self.assertTrue(bak.is_file())
        self.assertEqual(bak.read_text(encoding="utf-8"), original)

    def test_schedule_set_snapshots_file_mode_after_acquiring_lock(self):
        self.write_config(
            "profile {\n    time = 06:00\n    identity = true\n}\n"
            "profile {\n    time = 15:30\n    temperature = 3500\n}\n"
        )
        module = vc._schedule_module()
        config = vc.config_path()
        events = []

        class FakeLock:
            def __enter__(self):
                events.append("lock")

            def __exit__(self, *_args):
                return False

        original_stat = Path.stat

        def tracked_stat(path, *args, **kwargs):
            if path == config:
                events.append("config-stat")
            return original_stat(path, *args, **kwargs)

        with patch.object(module, "exclusive_lock", return_value=FakeLock()):
            with patch.object(Path, "stat", new=tracked_stat):
                state = vc.schedule_set(
                    {
                        "day_time": "07:00",
                        "day_temp": 6000,
                        "night_time": "21:00",
                        "night_temp": 3500,
                        "natural_day": True,
                    }
                )
        self.assertIsNone(state["error"])
        self.assertLess(events.index("lock"), events.index("config-stat"))


def clone_tracked_files(destination):
    """Copy the releasable package tree with or without VCS metadata.

    In a checkout, mirror the ``git ls-files | tar`` staging used by CI. In a
    ``git archive`` export, copy the already-filtered package tree directly so
    the release artifact can run its own verification suite.
    """
    destination = Path(destination)
    listed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        capture_output=True,
        text=True,
    )
    if listed.returncode == 0:
        relatives = [Path(relative) for relative in listed.stdout.split("\0") if relative]
    else:
        relatives = [
            source.relative_to(ROOT)
            for source in ROOT.rglob("*")
            if source.is_file()
            and ".git" not in source.relative_to(ROOT).parts
            and "__pycache__" not in source.relative_to(ROOT).parts
            and source.suffix != ".pyc"
        ]

    for relative in relatives:
        source = ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        shutil.copymode(source, target)


class HygieneGateTests(unittest.TestCase):
    """Deterministic checks for the package hygiene release gate."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fixture = Path(self.tmp.name) / "clone"
        self.fixture.mkdir()
        clone_tracked_files(self.fixture)

    def run_gate(self, target=None):
        return subprocess.run(
            [str(ROOT / "scripts" / "check_hygiene.sh"), str(target or self.fixture)],
            capture_output=True,
            text=True,
        )

    def test_clean_clone_passes_hygiene_gate(self):
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_clone_with_bytecode_cache_fails_hygiene_gate(self):
        cache = self.fixture / "scripts" / "__pycache__"
        cache.mkdir(parents=True)
        (cache / "schedule_utils.cpython-313.pyc").write_bytes(b"cached")
        result = self.run_gate()
        self.assertNotEqual(result.returncode, 0, "bytecode caches must fail the gate")

    def test_clone_with_symlink_fails_hygiene_gate(self):
        (self.fixture / "link-escape").symlink_to(self.fixture / "manifest.json")
        result = self.run_gate()
        self.assertNotEqual(result.returncode, 0, "symlinks must fail the gate")

    def test_clone_with_tampered_manifest_id_fails_hygiene_gate(self):
        manifest = self.fixture / "manifest.json"
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace(
                "io.github.znow01.veilleuse", "evil.example.not-the-plugin"
            ),
            encoding="utf-8",
        )
        result = self.run_gate()
        self.assertNotEqual(
            result.returncode, 0, "a tampered plugin id must fail the gate"
        )


class HelperArtifactTests(unittest.TestCase):
    """Running the helper must never leave bytecode caches in the clone."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fixture = Path(self.tmp.name) / "clone"
        self.runtime = Path(self.tmp.name) / "runtime"
        self.fixture.mkdir()
        self.runtime.mkdir()
        clone_tracked_files(self.fixture)

    def run_helper(self, *, bytecode_gate=True):
        environment = dict(os.environ)
        environment["XDG_CONFIG_HOME"] = str(self.runtime)
        environment["XDG_DATA_HOME"] = str(self.runtime / "data")
        if bytecode_gate:
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
        else:
            environment.pop("PYTHONDONTWRITEBYTECODE", None)
        return subprocess.run(
            [sys.executable, str(self.fixture / "scripts" / "veilleuse-control"), "status"],
            capture_output=True,
            text=True,
            env=environment,
        )

    def run_gate(self):
        return subprocess.run(
            [str(ROOT / "scripts" / "check_hygiene.sh"), str(self.fixture)],
            capture_output=True,
            text=True,
        )

    def test_helper_status_generates_no_pycache_with_bytecode_gate(self):
        result = self.run_helper(bytecode_gate=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(self.fixture.rglob("__pycache__")), [])
        self.assertEqual(list(self.fixture.rglob("*.pyc")), [])
        self.assertEqual(self.run_gate().returncode, 0, "clone must stay release-clean")

    def test_helper_status_without_environment_gate_stays_release_clean(self):
        result = self.run_helper(bytecode_gate=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(self.fixture.rglob("__pycache__")), [])
        self.assertEqual(list(self.fixture.rglob("*.pyc")), [])
        self.assertEqual(
            self.run_gate().returncode,
            0,
            "the helper must keep an installed clone release-clean by itself",
        )


class ReadmeLimitsTests(unittest.TestCase):
    """README numeric claims must equal the control ranges the panel exposes."""

    @staticmethod
    def panel_slider_range(label_start, label_end):
        qml = (ROOT / "Panel.qml").read_text(encoding="utf-8")
        start = qml.index(label_start)
        end = qml.index(label_end, start)
        section = qml[start:end]
        match = re.search(
            r"PanelSlider\s*\{[\s\S]*?minimum:\s*(\d+)[\s\S]*?maximum:\s*(\d+)",
            section,
        )
        if match is None:
            raise AssertionError(f"no PanelSlider bounds found between {label_start!r} and {label_end!r}")
        return int(match.group(1)), int(match.group(2))

    def test_readme_temperature_range_matches_the_panel_slider(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        claim = re.search(r"Luz nocturna de (\d+) a (\d+) K", readme)
        self.assertIsNotNone(claim, "README must state the night-light temperature range")
        slider = self.panel_slider_range("id: temperatureRow", "id: gammaRow")
        self.assertEqual((int(claim.group(1)), int(claim.group(2))), slider)

    def test_readme_gamma_range_matches_the_panel_slider(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        claim = re.search(r"gamma de (\d+) a (\d+)\s*%", readme)
        self.assertIsNotNone(claim, "README must state the gamma range")
        slider = self.panel_slider_range("id: gammaRow", "id: scheduleSurface")
        self.assertEqual((int(claim.group(1)), int(claim.group(2))), slider)

    def test_readme_does_not_state_a_brightness_range_the_panel_does_not_share(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"Brillo del monitor enfocado[^\n]*\d+\s*%", readme))


class SchedulePeriodTests(unittest.TestCase):
    """The circular schedule period used by the status backend."""

    def setUp(self):
        self.module = vc._schedule_module()
        self.assertIsNotNone(self.module, "schedule_utils must ship with the plugin")

    def schedule(self, day="06:00", night="22:00"):
        return {
            "day_time": day,
            "day_temp": 6000,
            "night_time": night,
            "night_temp": 3500,
        }

    def test_period_day_and_night_windows(self):
        schedule = self.schedule(day="06:00", night="18:00")
        self.assertEqual(self.module.schedule_period(schedule, datetime.time(9, 0)), "day")
        self.assertEqual(self.module.schedule_period(schedule, datetime.time(22, 0)), "night")
        self.assertEqual(self.module.schedule_period(schedule, datetime.time(3, 0)), "night")

    def test_period_night_window_crosses_midnight(self):
        # night 22:00 -> day 06:00 spans midnight: 23:30 and 04:00 are night.
        schedule = self.schedule(day="06:00", night="22:00")
        self.assertEqual(self.module.schedule_period(schedule, datetime.time(23, 30)), "night")
        self.assertEqual(self.module.schedule_period(schedule, datetime.time(4, 0)), "night")
        self.assertEqual(self.module.schedule_period(schedule, datetime.time(12, 0)), "day")

    def test_period_rejects_equal_boundaries(self):
        with self.assertRaises(ValueError):
            self.module.schedule_period(
                self.schedule(day="06:00", night="06:00"), datetime.time(12, 0)
            )

    def test_period_rejects_non_time_now(self):
        with self.assertRaises(ValueError):
            self.module.schedule_period(self.schedule(), now="12:00")


class ManifestCompatibilityTests(unittest.TestCase):
    """The manifest must keep the marketplace contract of the release gate."""

    def setUp(self):
        self.manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))

    def test_schema_version_is_one(self):
        self.assertEqual(self.manifest["schemaVersion"], 1)

    def test_id_is_lowercase_reverse_dns(self):
        self.assertEqual(self.manifest["id"], "io.github.znow01.veilleuse")
        self.assertRegex(self.manifest["id"], r"^[a-z0-9]+(?:\.[a-z0-9]+)+$")

    def test_kind_is_bar_widget(self):
        self.assertEqual(self.manifest["kinds"], ["bar-widget"])

    def test_entry_point_is_bar_widget_qml(self):
        self.assertEqual(self.manifest["entryPoints"], {"barWidget": "BarWidget.qml"})
        self.assertTrue((ROOT / "BarWidget.qml").is_file())

    def test_referenced_release_files_exist(self):
        for relative in (
            "Panel.qml",
            "Model.js",
            "UiModel.js",
            "scripts/veilleuse-control",
            "scripts/schedule_utils.py",
            "scripts/shortcut_utils.py",
            "scripts/check.sh",
        ):
            self.assertTrue((ROOT / relative).is_file(), f"missing {relative}")

    def test_version_is_semver(self):
        self.assertRegex(self.manifest["version"], r"^\d+\.\d+\.\d+$")

    def test_package_metadata_is_present(self):
        for field in ("name", "author", "license", "description"):
            value = self.manifest.get(field)
            self.assertIsInstance(value, str)
            self.assertTrue(value.strip(), f"{field} must not be empty")


class ShortcutKeyValidationTests(unittest.TestCase):
    """CLI key specs are validated against a conservative allowlist."""

    def test_accepts_simple_modifier_and_key(self):
        self.assertEqual(sc.canonical_keys("SUPER, V"), "SUPER + V")

    def test_accepts_multiple_modifiers_and_function_key(self):
        self.assertEqual(sc.canonical_keys("CTRL SHIFT, F8"), "CTRL + SHIFT + F8")

    def test_accepts_key_without_modifiers(self):
        self.assertEqual(sc.canonical_keys(", F9"), "F9")

    def test_normalizes_case_whitespace_and_named_keys(self):
        self.assertEqual(sc.canonical_keys("  super , v "), "SUPER + V")
        self.assertEqual(sc.canonical_keys("super, space"), "SUPER + SPACE")
        self.assertEqual(sc.canonical_keys("ALT, F24"), "ALT + F24")

    def test_rejects_unknown_modifier(self):
        for bad in ("SUPER2, V", "HYPER, V", "MOD9, V"):
            with self.assertRaises(ValueError, msg=bad):
                sc.canonical_keys(bad)

    def test_rejects_duplicate_modifiers(self):
        with self.assertRaises(ValueError):
            sc.canonical_keys("SUPER SUPER, V")

    def test_rejects_malformed_specs(self):
        for bad in ("", "SUPER", "SUPER,", ",", "SUPER,,V", "SUPER, V, C", "SUPER\n, V"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                sc.canonical_keys(bad)

    def test_rejects_unsafe_key_names(self):
        for bad in (
            "SUPER, X11",
            "SUPER, F25",
            "SUPER, V#",
            "SUPER, 'V'",
            "SUPER, V do",
            "SUPER, ]then",
        ):
            with self.assertRaises(ValueError, msg=repr(bad)):
                sc.canonical_keys(bad)

    def test_rejects_embedded_command_tokens(self):
        for bad in ("SUPER, V, exec, rm -rf /", "SUPER, V; shutdown", "SUPER, V --force"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                sc.canonical_keys(bad)


class ShortcutLuaBlockTests(unittest.TestCase):
    """The generated marker block is executable Lua (Omarchy 4 ``o.bind``).

    Omarchy 4 ``~/.config/hypr/bindings.lua`` is executed as Lua and exposes
    the ``o`` helpers table.  A Veilleuse block must run under only that stub
    and hand ``o.bind`` the exact canonical key string, the ``Veilleuse``
    description and the fixed IPC command.
    """

    LUA = Path("/usr/bin/lua")

    @classmethod
    def setUpClass(cls):
        cls.has_lua = cls.LUA.is_file() and os.access(cls.LUA, os.X_OK)

    def run_lua(self, path):
        return subprocess.run(
            [str(self.LUA), str(path)],
            text=True,
            capture_output=True,
            timeout=10,
        )

    def test_generated_block_runs_under_the_o_stub_and_passes_exact_arguments(self):
        if not self.has_lua:
            self.skipTest("/usr/bin/lua not available")
        with tempfile.TemporaryDirectory() as tmp:
            block_path = Path(tmp) / "bindings.lua"
            block_path.write_text(sc._block_text("SUPER, V", "\n"), encoding="utf-8")
            self.assertNotIn("]]", str(block_path), "long bracket path collision")
            bootstrap = Path(tmp) / "bootstrap.lua"
            bootstrap.write_text(
                "o = { bind = function(keys, desc, cmd)\n"
                "  captured = { keys = keys, desc = desc, cmd = cmd }\n"
                "end }\n"
                "local chunk = assert(loadfile([[" + str(block_path) + "]]))\n"
                "chunk()\n"
                "assert(captured, 'o.bind was not called')\n"
                "print(captured.keys)\n"
                "print(captured.desc)\n"
                "print(captured.cmd)\n",
                encoding="utf-8",
            )
            result = self.run_lua(bootstrap)
        self.assertEqual(
            result.returncode,
            0,
            "block must be valid Lua: " + result.stderr.strip(),
        )
        keys, desc, cmd = result.stdout.splitlines()
        self.assertEqual(keys, sc.canonical_keys("SUPER, V"))
        self.assertEqual(keys, "SUPER + V")
        self.assertEqual(desc, "Veilleuse")
        self.assertEqual(cmd, sc.FIXED_COMMAND)


class ShortcutBlockTextTests(unittest.TestCase):
    """The marker block editor only touches the unique Veilleuse block."""

    def test_block_contains_markers_and_fixed_command(self):
        block = sc._block_text("SUPER, V", "\n")
        self.assertEqual(
            block,
            "-- >>> Veilleuse shortcut >>>\n"
            'o.bind("SUPER + V", "Veilleuse",'
            ' "omarchy-shell -q io.github.znow01.veilleuse toggleNightlight")\n'
            "-- <<< Veilleuse shortcut <<<\n",
        )

    def test_install_appends_block_after_existing_content(self):
        new = sc.install_block("# keep me\n", "SUPER, V")
        self.assertTrue(new.startswith("# keep me\n"))
        self.assertEqual(new.count(sc.MARKER_OPEN), 1)
        self.assertEqual(new.count(sc.MARKER_CLOSE), 1)
        self.assertIn(sc.FIXED_COMMAND, new)

    def test_install_into_empty_text_returns_only_the_block(self):
        self.assertEqual(sc.install_block("", "SUPER, V"), sc._block_text("SUPER, V", "\n"))

    def test_install_insulates_a_file_without_trailing_newline(self):
        new = sc.install_block("# last line", "SUPER, V")
        self.assertTrue(new.startswith("# last line\n"))

    def test_remove_roundtrip_is_byte_exact(self):
        originals = (
            "",
            "abc",
            "abc\n",
            "abc\n\n",
            "a\r\nb\r\n",
            '# comment\no.bind("CTRL + F1", "x", "x")\n',
            'o.bind("SUPER + K", "y", "y")',
        )
        for original in originals:
            installed = sc.install_block(original, "SUPER, V")
            restored, found, keys = sc.remove_block(installed)
            self.assertEqual(restored, original, f"roundtrip failed for {original!r}")
            self.assertTrue(found)
            self.assertEqual(keys, "SUPER + V")

    def test_remove_without_block_is_a_noop(self):
        text = 'o.bind("CTRL + F1", "x", "x")\n'
        restored, found, keys = sc.remove_block(text)
        self.assertEqual(restored, text)
        self.assertFalse(found)
        self.assertIsNone(keys)

    def test_reinstall_replaces_the_only_block_in_place(self):
        once = sc.install_block("-- keep\n", "SUPER, V")
        twice = sc.install_block(once, "CTRL, F8")
        self.assertEqual(twice.count(sc.MARKER_OPEN), 1)
        self.assertEqual(twice.count(sc.MARKER_CLOSE), 1)
        self.assertIn("CTRL + F8", twice)
        self.assertNotIn("SUPER + V", twice)
        self.assertIn("-- keep", twice)

    def test_crlf_files_keep_crlf_through_install(self):
        new = sc.install_block("a\r\n", "SUPER, V")
        self.assertIn("\r\n", new)
        restored, found, _keys = sc.remove_block(new)
        self.assertEqual(restored, "a\r\n")
        self.assertTrue(found)

    def test_find_block_fails_closed_on_unclosed_marker(self):
        with self.assertRaises(ValueError):
            sc.find_block("-- >>> Veilleuse shortcut >>>\n")


class ShortcutCollisionTests(unittest.TestCase):
    """Install refuses keys already bound outside the Veilleuse block."""

    def test_detects_existing_binding_with_same_keys(self):
        text = 'o.bind("SUPER + V", "Kitty", "kitty")\n'
        self.assertEqual(
            sc.collision(text, "SUPER, V"), 'o.bind("SUPER + V", "Kitty", "kitty")'
        )

    def test_detects_case_insensitive_key_collision(self):
        self.assertEqual(sc.collision('o.bind("SUPER + v", "x", "x")\n', "SUPER, V"),
                         'o.bind("SUPER + v", "x", "x")')

    def test_lone_unbind_frees_the_keys(self):
        self.assertIsNone(sc.collision('hl.unbind("SUPER + V")\n', "SUPER, V"))

    def test_bind_then_unbind_frees_the_keys(self):
        text = 'o.bind("SUPER + V", "kitty", "kitty")\nhl.unbind("SUPER + V")\n'
        self.assertIsNone(sc.collision(text, "SUPER, V"))

    def test_unbind_then_bind_collides_with_the_later_bind(self):
        text = 'hl.unbind("SUPER + V")\no.bind("SUPER + V", "kitty", "kitty")\n'
        self.assertEqual(
            sc.collision(text, "SUPER, V"), 'o.bind("SUPER + V", "kitty", "kitty")'
        )

    def test_bind_then_bind_collides_with_the_active_bind(self):
        text = (
            'o.bind("SUPER + V", "one", "one-cmd")\n'
            'o.bind("SUPER + V", "two", "two-cmd")\n'
        )
        self.assertEqual(
            sc.collision(text, "SUPER, V"), 'o.bind("SUPER + V", "two", "two-cmd")'
        )

    def test_other_keys_do_not_affect_the_requested_key_order(self):
        text = (
            'o.bind("SUPER + V", "kitty", "kitty")\n'
            'o.bind("CTRL + F1", "x", "x")\n'
            'hl.unbind("SUPER + V")\n'
        )
        self.assertIsNone(sc.collision(text, "SUPER, V"))
        self.assertEqual(
            sc.collision(text, "CTRL, F1"), 'o.bind("CTRL + F1", "x", "x")'
        )

    def test_different_keys_do_not_collide(self):
        self.assertIsNone(sc.collision('o.bind("SUPER + K", "x", "x")\n', "SUPER, V"))

    def test_ignores_commented_bind_lines(self):
        text = "-- o.bind('SUPER + V', 'x', 'x')\no.bind(\"SUPER + K\", \"y\", \"y\")\n"
        self.assertIsNone(sc.collision(text, "SUPER, V"))
        self.assertEqual(sc.collision(text, "SUPER, K"), 'o.bind("SUPER + K", "y", "y")')

    def test_ignores_bindings_inside_block_comments(self):
        text = "--[[\no.bind(\"SUPER + V\", \"x\", \"x\")\n]]\n"
        self.assertIsNone(sc.collision(text, "SUPER, V"))

    def test_ignores_strings_that_contain_bind_text(self):
        self.assertIsNone(sc.collision('x = "o.bind(\'SUPER + V\', \'x\', \'x\')"\n', "SUPER, V"))

    def test_ignores_bindings_inside_long_strings(self):
        self.assertIsNone(
            sc.collision('x = [=[o.bind("SUPER + V", "x", "x")]=]\n', "SUPER, V")
        )

    def test_recognizes_hl_bind_outside_the_block(self):
        text = 'hl.bind("SUPER + V", exec_cmd("kitty"))\n'
        self.assertEqual(
            sc.collision(text, "SUPER, V"), 'hl.bind("SUPER + V", exec_cmd("kitty"))'
        )

    def test_ignores_our_own_block_for_collision_detection(self):
        installed = sc.install_block('o.bind("CTRL + F1", "x", "x")\n', "SUPER, V")
        self.assertIsNone(sc.collision(installed, "SUPER, V"))
        self.assertEqual(
            sc.collision(installed, "CTRL, F1"), 'o.bind("CTRL + F1", "x", "x")'
        )

    def test_marker_block_calls_do_not_participate_in_the_order(self):
        text = 'hl.unbind("SUPER + V")\n' + sc.install_block("", "SUPER, V")
        self.assertIsNone(sc.collision(text, "SUPER, V"))

    def test_concatenated_keys_argument_fails_closed(self):
        text = 'o.bind("SUPER + " .. k, "x", "x")\n'
        with self.assertRaises(sc.UnparseableBindingError):
            sc.collision(text, "SUPER, V")

    def test_non_string_first_argument_fails_closed(self):
        text = 'hl.bind(keys_var, "x", "x")\n'
        with self.assertRaises(sc.UnparseableBindingError):
            sc.collision(text, "SUPER, V")

    def test_malformed_keys_string_fails_closed(self):
        text = 'o.bind("SUPER + ;;;", "x", "x")\n'
        with self.assertRaises(sc.UnparseableBindingError):
            sc.collision(text, "SUPER, V")

    def test_dynamic_calls_inside_comments_are_still_ignored(self):
        text = (
            '-- o.bind("SUPER + " .. k, "x", "x")\n'
            'o.bind("SUPER + K", "y", "y")\n'
        )
        self.assertIsNone(sc.collision(text, "SUPER, V"))
        self.assertEqual(
            sc.collision(text, "SUPER, K"), 'o.bind("SUPER + K", "y", "y")'
        )

    def test_dynamic_calls_inside_long_strings_are_still_ignored(self):
        text = 'x = [=[o.bind("SUPER + " .. k, "x", "x")]=]\n'
        self.assertIsNone(sc.collision(text, "SUPER, V"))


class ShortcutFilesystemTests(unittest.TestCase):
    """Install and removal semantics against a deterministic isolated XDG."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.xdg = Path(self.tmp.name)
        self.env_patch = patch.dict(
            os.environ,
            {"XDG_CONFIG_HOME": str(self.xdg), "XDG_DATA_HOME": str(self.xdg / "data")},
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.addCleanup(self.tmp.cleanup)
        self.reload = ShortcutReloadSim()
        self.reload_patch = patch.object(sc, "run_command", side_effect=self.reload)
        self.reload_patch.start()
        self.addCleanup(self.reload_patch.stop)

    def bindings(self):
        return sc.bindings_path()

    def write_bindings(self, text, mode=0o644):
        path = self.bindings()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        path.chmod(mode)
        return path

    def test_status_reports_absent_without_creating_the_file(self):
        status = sc.shortcut_status()
        self.assertTrue(status["available"])
        self.assertFalse(status["exists"])
        self.assertFalse(status["installed"])
        self.assertIsNone(status["keys"])
        self.assertIsNone(status["error"])
        self.assertFalse(self.bindings().exists())

    def test_install_on_missing_file_creates_only_the_block(self):
        result = sc.install_shortcut("SUPER, V")
        self.assertTrue(result["available"], result)
        self.assertIsNone(result["error"])
        self.assertEqual(result["keys"], "SUPER + V")
        self.assertFalse(result["backup_created"])
        self.assertFalse(self.bindings().with_suffix(".lua.bak").exists())
        self.assertEqual(self.bindings().stat().st_mode & 0o7777, 0o644)
        self.assertEqual(
            self.bindings().read_text(encoding="utf-8"),
            sc._block_text("SUPER, V", "\n"),
        )
        self.assertEqual(
            [call for call, _timeout in self.reload.calls], [["hyprctl", "reload"]]
        )

    def test_install_preserves_user_content_and_mode_with_single_backup(self):
        original = '-- keep me\no.bind("CTRL + F1", "kitty", "kitty")\n'
        path = self.write_bindings(original, mode=0o604)
        result = sc.install_shortcut("SUPER, V")
        self.assertTrue(result["available"], result)
        self.assertTrue(result["backup_created"])
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(original))
        self.assertIn(sc.MARKER_OPEN, text)
        self.assertIn(sc.FIXED_COMMAND, text)
        self.assertEqual(path.stat().st_mode & 0o7777, 0o604)
        backup = path.with_suffix(".lua.bak")
        self.assertEqual(backup.read_text(encoding="utf-8"), original)
        self.assertEqual(backup.stat().st_mode & 0o7777, 0o604)

    def test_backup_is_created_exactly_once(self):
        original = '-- keep me\no.bind("CTRL + F1", "kitty", "kitty")\n'
        path = self.write_bindings(original)
        sc.install_shortcut("SUPER, V")
        self.assertEqual(path.with_suffix(".lua.bak").read_text(encoding="utf-8"), original)
        result = sc.install_shortcut("CTRL, F8")
        self.assertTrue(result["available"], result)
        self.assertFalse(result["backup_created"])
        self.assertEqual(path.with_suffix(".lua.bak").read_text(encoding="utf-8"), original)
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count(sc.MARKER_OPEN), 1)
        self.assertIn("CTRL + F8", text)
        self.assertNotIn("SUPER + V", text)
        self.assertIn("-- keep me", text)

    def test_install_rejects_collision_without_writing_anything(self):
        original = 'o.bind("SUPER + V", "kitty", "kitty")\n'
        path = self.write_bindings(original)
        result = sc.install_shortcut("SUPER, V")
        self.assertFalse(result["available"])
        self.assertIn("ya está asignado", result["error"])
        self.assertIn("SUPER + V", result["error"])
        self.assertEqual(path.read_text(encoding="utf-8"), original)
        self.assertFalse(path.with_suffix(".lua.bak").exists())
        self.assertEqual(self.reload.calls, [])

    def test_install_rejects_keys_already_bound_by_an_external_line(self):
        path = self.write_bindings('o.bind("CTRL + F1", "kitty", "kitty")\n')
        result = sc.install_shortcut("CTRL, F1")
        self.assertFalse(result["available"])
        self.assertEqual(
            path.read_text(encoding="utf-8"), 'o.bind("CTRL + F1", "kitty", "kitty")\n'
        )

    def test_install_succeeds_after_external_unbind_frees_the_keys(self):
        original = 'o.bind("SUPER + V", "kitty", "kitty")\nhl.unbind("SUPER + V")\n'
        path = self.write_bindings(original)
        result = sc.install_shortcut("SUPER, V")
        self.assertTrue(result["available"], result)
        self.assertIn("SUPER + V", path.read_text(encoding="utf-8"))

    def test_install_rejects_keys_rebound_after_an_unbind(self):
        original = 'hl.unbind("SUPER + V")\no.bind("SUPER + V", "kitty", "kitty")\n'
        path = self.write_bindings(original)
        result = sc.install_shortcut("SUPER, V")
        self.assertFalse(result["available"])
        self.assertIn("ya está asignado", result["error"])
        self.assertIn('o.bind("SUPER + V", "kitty", "kitty")', result["error"])
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_install_fails_closed_on_unparseable_external_binding(self):
        original = 'o.bind("SUPER + " .. k, "kitty", "kitty")\n'
        path = self.write_bindings(original)
        result = sc.install_shortcut("SUPER, V")
        self.assertFalse(result["available"])
        self.assertIn("No se pudo analizar", result["error"])
        self.assertEqual(path.read_text(encoding="utf-8"), original)
        self.assertFalse(path.with_suffix(".lua.bak").exists())
        self.assertEqual(self.reload.calls, [])

    def test_install_invalid_keys_raise_and_write_nothing(self):
        original = "# x\n"
        path = self.write_bindings(original)
        with self.assertRaises(ValueError):
            sc.install_shortcut("SUPER, V; rm -rf")
        self.assertEqual(path.read_text(encoding="utf-8"), original)
        self.assertFalse(path.with_suffix(".lua.bak").exists())

    def test_install_own_block_does_not_reintroduce_collision(self):
        self.write_bindings('o.bind("CTRL + F1", "kitty", "kitty")\n')
        self.assertTrue(sc.install_shortcut("SUPER, V")["available"])
        second = sc.install_shortcut("SUPER, V")
        self.assertTrue(second["available"], second)
        self.assertFalse(second["backup_created"])

    def test_install_fails_closed_on_unclosed_marker(self):
        path = self.write_bindings("-- >>> Veilleuse shortcut >>>\n")
        result = sc.install_shortcut("SUPER, V")
        self.assertFalse(result["available"])
        self.assertIn("no está cerrado", result["error"])
        self.assertEqual(path.read_text(encoding="utf-8"), "-- >>> Veilleuse shortcut >>>\n")

    def test_remove_restores_the_original_file_exactly(self):
        original = '-- keep me\no.bind("CTRL + F1", "kitty", "kitty")\n'
        path = self.write_bindings(original, mode=0o604)
        sc.install_shortcut("SUPER, V")
        result = sc.remove_shortcut()
        self.assertTrue(result["available"], result)
        self.assertTrue(result["restored"])
        self.assertTrue(result["exists"])
        self.assertEqual(result["keys"], "SUPER + V")
        self.assertEqual(path.read_text(encoding="utf-8"), original)
        self.assertEqual(path.stat().st_mode & 0o7777, 0o604)
        self.assertTrue(path.with_suffix(".lua.bak").exists())
        self.assertEqual(
            [call for call, _timeout in self.reload.calls],
            [["hyprctl", "reload"], ["hyprctl", "reload"]],
        )

    def test_remove_deletes_the_file_created_by_install(self):
        result = sc.install_shortcut("SUPER, V")
        self.assertTrue(result["available"], result)
        removed = sc.remove_shortcut()
        self.assertTrue(removed["available"], removed)
        self.assertTrue(removed["restored"])
        self.assertFalse(removed["exists"])
        self.assertFalse(self.bindings().exists())

    def test_remove_without_block_is_a_successful_noop(self):
        path = self.write_bindings("# x\n")
        result = sc.remove_shortcut()
        self.assertTrue(result["available"], result)
        self.assertFalse(result["restored"])
        self.assertEqual(path.read_text(encoding="utf-8"), "# x\n")
        self.assertEqual(self.reload.calls, [])

    def test_status_after_install_reports_keys_and_backup(self):
        self.write_bindings('-- keep me\no.bind("CTRL + F1", "kitty", "kitty")\n')
        sc.install_shortcut("SUPER, V")
        status = sc.shortcut_status()
        self.assertTrue(status["installed"])
        self.assertEqual(status["keys"], "SUPER + V")
        self.assertEqual(status["command"], sc.FIXED_COMMAND)
        self.assertTrue(status["backup_exists"])

    def test_unreadable_bindings_reports_error_without_writing(self):
        path = self.write_bindings("# x\n")
        with patch("veilleuse_shortcut_utils.Path.read_text", side_effect=PermissionError("denied")):
            status = sc.shortcut_status()
            result = sc.install_shortcut("SUPER, V")
        self.assertIn("denied", status["error"])
        self.assertFalse(result["available"])
        self.assertIn("denied", result["error"])
        self.assertEqual(path.read_text(encoding="utf-8"), "# x\n")

    def test_reload_failure_is_best_effort(self):
        self.reload.ok = False
        result = sc.install_shortcut("SUPER, V")
        self.assertTrue(result["available"], result)
        self.assertFalse(result["reload"]["ok"])
        self.assertEqual(self.reload.calls[0][0], ["hyprctl", "reload"])


class ShortcutCliTests(HelperModuleTests):
    """The shortcut subcommand surface of veilleuse-control."""

    def setUp(self):
        super().setUp()
        self.reload = ShortcutReloadSim()
        module = vc._shortcut_module()
        self.assertIsNotNone(module, "shortcut_utils must ship with the plugin")
        self.sc_module = module
        self.sc_patch = patch.object(self.sc_module, "run_command", side_effect=self.reload)
        self.sc_patch.start()
        self.addCleanup(self.sc_patch.stop)

    def test_cli_shortcut_status_when_absent(self):
        code, output = self.run_cli("shortcut", "status")
        self.assertEqual(code, 0)
        status = json.loads(output)
        self.assertFalse(status["installed"])
        self.assertFalse(sc.bindings_path().exists())

    def test_cli_install_status_remove_roundtrip(self):
        code, output = self.run_cli("shortcut", "install", "--keys", "SUPER, V")
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(output)["keys"], "SUPER + V")
        code, output = self.run_cli("shortcut", "status")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output)["installed"])
        self.assertEqual(json.loads(output)["keys"], "SUPER + V")
        code, output = self.run_cli("shortcut", "remove")
        self.assertEqual(code, 0, output)
        self.assertTrue(json.loads(output)["restored"])
        code, output = self.run_cli("shortcut", "status")
        self.assertEqual(code, 0)
        status = json.loads(output)
        self.assertFalse(status["installed"])
        self.assertFalse(sc.bindings_path().exists())

    def test_cli_install_preserves_existing_file_through_remove(self):
        original = '-- keep me\no.bind("CTRL + F1", "kitty", "kitty")\n'
        path = sc.bindings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(original, encoding="utf-8")
        code, output = self.run_cli("shortcut", "install", "--keys", "SUPER, V")
        self.assertEqual(code, 0, output)
        code, output = self.run_cli("shortcut", "remove")
        self.assertEqual(code, 0, output)
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_cli_install_requires_keys_argument(self):
        code, output = self.run_cli("shortcut", "install")
        self.assertEqual(code, 2)

    def test_cli_install_rejects_invalid_keys(self):
        code, output = self.run_cli("shortcut", "install", "--keys", "SUPER, V; rm")
        self.assertEqual(code, 1)
        self.assertIn("error", json.loads(output))

    def test_cli_rejects_unknown_shortcut_action(self):
        code, _output = self.run_cli("shortcut", "explode")
        self.assertEqual(code, 2)

    def test_status_commands_never_install_a_shortcut(self):
        code, _output = self.run_cli("status")
        self.assertEqual(code, 0)
        code, _output = self.run_cli("shortcut", "status")
        self.assertEqual(code, 0)
        code, _output = self.run_cli("shortcut", "remove")
        self.assertEqual(code, 0)
        self.assertFalse(sc.bindings_path().exists())

    def test_cli_collision_fails_with_state(self):
        path = sc.bindings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('o.bind("SUPER + V", "kitty", "kitty")\n', encoding="utf-8")
        code, output = self.run_cli("shortcut", "install", "--keys", "SUPER, V")
        self.assertEqual(code, 1)
        payload = json.loads(output)
        self.assertIn("ya está asignado", payload["error"])
        self.assertFalse(payload["state"]["installed"])
        self.assertEqual(
            path.read_text(encoding="utf-8"), 'o.bind("SUPER + V", "kitty", "kitty")\n'
        )

    def test_cli_reload_uses_the_plugin_module_runner(self):
        code, output = self.run_cli("shortcut", "install", "--keys", "SUPER, V")
        self.assertEqual(code, 0, output)
        self.assertEqual([call for call, _timeout in self.reload.calls], [["hyprctl", "reload"]])


class V2ReleaseTests(unittest.TestCase):
    """Release archives and installed clones stay release-safe with v2 files."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def build_archive(self):
        """Stage the package the same way CI does: git ls-files | tar."""
        destination = self.base / "archive"
        destination.mkdir(parents=True)
        listed = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True
        )
        if listed.returncode != 0:
            clone_tracked_files(destination)
            return destination
        pack = subprocess.Popen(
            ["tar", "--null", "-T", "-", "-cf", "-"],
            cwd=str(ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        stdout, _error = pack.communicate(input=listed.stdout)
        if pack.returncode != 0:
            clone_tracked_files(destination)
            return destination
        extract = subprocess.run(
            ["tar", "-xf", "-", "-C", str(destination)],
            input=stdout,
            capture_output=True,
        )
        if extract.returncode != 0:
            clone_tracked_files(destination)
        return destination

    def stub_hyprctl_environment(self):
        log = self.base / "reload.log"
        stub_dir = self.base / "bin"
        stub_dir.mkdir(exist_ok=True)
        stub = stub_dir / "hyprctl"
        stub.write_text(
            "#!/bin/sh\nprintf 'reload\\n' >> \"$VEILLEUSE_HYPRCTL_LOG\"\nexit 0\n",
            encoding="utf-8",
        )
        stub.chmod(0o755)
        environment = dict(os.environ)
        environment.pop("PYTHONDONTWRITEBYTECODE", None)
        environment["PATH"] = f"{stub_dir}:{environment.get('PATH', '')}"
        environment["VEILLEUSE_HYPRCTL_LOG"] = str(log)
        environment["XDG_CONFIG_HOME"] = str(self.base / "xdg")
        environment["XDG_DATA_HOME"] = str(self.base / "xdg" / "data")
        return environment, log

    def run_helper(self, fixture, *args):
        environment, _log = self.stub_hyprctl_environment()
        return subprocess.run(
            [sys.executable, str(fixture / "scripts" / "veilleuse-control"), *args],
            capture_output=True,
            text=True,
            env=environment,
        )

    def test_archive_contains_the_v2_owned_files(self):
        archive = self.build_archive()
        for relative in (
            "manifest.json",
            "README.md",
            "BarWidget.qml",
            "scripts/veilleuse-control",
            "scripts/schedule_utils.py",
            "scripts/shortcut_utils.py",
            "scripts/check.sh",
            "docs/VEILLEUSE_V2_CONTRACT.md",
        ):
            self.assertTrue((archive / relative).is_file(), f"archive missing {relative}")

    def test_archive_has_no_symlinks_or_bytecode_caches(self):
        archive = self.build_archive()
        self.assertEqual(list(archive.rglob("__pycache__")), [])
        self.assertEqual(list(archive.rglob("*.pyc")), [])
        self.assertEqual([path for path in archive.rglob("*") if path.is_symlink()], [])
        gate = subprocess.run(
            [str(ROOT / "scripts" / "check_hygiene.sh"), str(archive)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(gate.returncode, 0, gate.stderr)

    def test_installed_clone_runs_shortcut_commands_with_isolated_home(self):
        archive = self.build_archive()
        status = self.run_helper(archive, "shortcut", "status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertFalse(json.loads(status.stdout)["installed"])
        install = self.run_helper(archive, "shortcut", "install", "--keys", "SUPER, F8")
        self.assertEqual(install.returncode, 0, install.stderr)
        self.assertEqual(json.loads(install.stdout)["keys"], "SUPER + F8")
        status = self.run_helper(archive, "shortcut", "status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertTrue(json.loads(status.stdout)["installed"])
        remove = self.run_helper(archive, "shortcut", "remove")
        self.assertEqual(remove.returncode, 0, remove.stderr)
        self.assertTrue(json.loads(remove.stdout)["restored"])
        status = self.run_helper(archive, "shortcut", "status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertFalse(json.loads(status.stdout)["installed"])
        self.assertFalse((self.base / "xdg" / "hypr" / "bindings.lua").exists())

    def test_installed_clone_reload_is_best_effort_and_recorded(self):
        archive = self.build_archive()
        install = self.run_helper(archive, "shortcut", "install", "--keys", "SUPER, F8")
        self.assertEqual(install.returncode, 0, install.stderr)
        environment, log = self.stub_hyprctl_environment()
        self.assertEqual(log.read_text(encoding="utf-8"), "reload\n")
        self.assertIn("reload", json.loads(install.stdout))

    def test_installed_clone_stays_free_of_bytecode_caches(self):
        archive = self.build_archive()
        for _step in ("status", "install"):
            self.run_helper(archive, "shortcut", "status")
        self.assertEqual(list(archive.rglob("__pycache__")), [])
        self.assertEqual(list(archive.rglob("*.pyc")), [])
        gate = subprocess.run(
            [str(ROOT / "scripts" / "check_hygiene.sh"), str(archive)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(gate.returncode, 0, gate.stderr)

    def test_installed_clone_writes_nothing_outside_isolated_home(self):
        archive = self.build_archive()
        install = self.run_helper(archive, "shortcut", "install", "--keys", "SUPER, F8")
        self.assertEqual(install.returncode, 0, install.stderr)
        bindings = [str(path) for path in archive.rglob("bindings.lua")]
        self.assertEqual(bindings, [])
        self.assertTrue((self.base / "xdg" / "hypr" / "bindings.lua").is_file())


class ReadmeShortcutTests(unittest.TestCase):
    """README documents the opt-in shortcut workflow and its guarantees."""

    def setUp(self):
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_readme_documents_the_shortcut_commands(self):
        for needle in ("shortcut install", "shortcut status", "shortcut remove", "--keys"):
            self.assertIn(needle, self.readme, f"README must mention {needle!r}")

    def test_readme_states_installation_is_never_automatic(self):
        self.assertIn("nunca instala atajos automáticamente", self.readme)

    def test_readme_documents_fixed_command_and_marker_block(self):
        self.assertIn("omarchy-shell -q io.github.znow01.veilleuse toggleNightlight", self.readme)
        self.assertIn("-- >>> Veilleuse shortcut >>>", self.readme)

    def test_readme_documents_single_backup_and_exact_removal(self):
        self.assertIn("bindings.lua.bak", self.readme)
        self.assertIn("revierte el archivo a su contenido previo", self.readme)


if __name__ == "__main__":
    unittest.main()
