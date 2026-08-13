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


class HelperModuleTests(unittest.TestCase):
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
    """Shallow-copy the tracked package files like the release staging does.

    Mirrors the ``git ls-files | tar`` staging used by check.sh and CI: only
    tracked files, preserving the executable bit, with no VCS metadata.
    """
    destination = Path(destination)
    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")
    for relative in tracked:
        if not relative:
            continue
        source = ROOT / relative
        target = destination / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
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

    def test_helper_status_without_gate_leaves_artifacts_that_hygiene_rejects(self):
        result = self.run_helper(bytecode_gate=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        gate = self.run_gate()
        self.assertNotEqual(
            gate.returncode,
            0,
            "helper bytecode artifacts must make the hygiene gate fail",
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


if __name__ == "__main__":
    unittest.main()
