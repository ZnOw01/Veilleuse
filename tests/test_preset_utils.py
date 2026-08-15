import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.state_utils as state_utils
from scripts import preset_utils
from scripts.preset_utils import PresetError, PresetManager


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class FakeOperations:
    def __init__(self):
        self.monitors = [
            {"name": "eDP-1", "enabled": True, "focused": True},
            {"name": "DP-1", "enabled": True, "focused": False},
            {"name": "HDMI-1", "enabled": False, "focused": False},
        ]
        self.brightness = {"eDP-1": 42, "DP-1": 50}
        self.nightlight_calls = []
        self.brightness_steps = []
        self.readback_values = {}
        self.fail_nightlight = False
        self.nightlight_result = None
        self.fail_step = False
        self.step_advances = 0.0
        self.clock = None

    def read_monitor_state(self):
        return {"monitors": [dict(monitor) for monitor in self.monitors]}

    def read_brightness(self, monitor):
        value = self.readback_values.get(monitor, self.brightness.get(monitor))
        if isinstance(value, list):
            value = value.pop(0)
        return value, None if value is not None else "missing brightness"

    def brightness_step(self, monitor, token):
        self.brightness_steps.append((monitor, token))
        if self.clock is not None:
            self.clock.advance(self.step_advances)
        if self.fail_step:
            return {"ok": False, "error_code": "native_failure"}
        if token == "+1%":
            self.brightness[monitor] += 1
        elif token == "1%-":
            self.brightness[monitor] -= 1
        return {"ok": True}

    def apply_nightlight(self, temperature, gamma):
        self.nightlight_calls.append((temperature, gamma))
        if self.nightlight_result is not None:
            return self.nightlight_result
        if self.fail_nightlight:
            return {"ok": False, "error_code": "nightlight_failure"}
        return {"ok": True}


class PresetUtilsTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.home = Path(self.tempdir.name) / "home"
        self.home.mkdir()
        self.config_home = Path(self.tempdir.name) / "config"
        self.state_home = Path(self.tempdir.name) / "state"
        self.environment = mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.config_home),
                "XDG_STATE_HOME": str(self.state_home),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            clear=False,
        )
        self.environment.start()
        self.clock = FakeClock()
        self.operations = FakeOperations()
        self.operations.clock = self.clock
        self.manager = PresetManager(self.operations, clock=self.clock)

    def tearDown(self):
        self.environment.stop()
        self.tempdir.cleanup()

    def save_custom(self, name="desk", brightness=None):
        return self.manager.save_preset(
            name,
            temperature=4200,
            gamma=80,
            brightness=brightness,
        )

    def test_resolves_focused_and_exact_enabled_monitors(self):
        self.assertEqual(self.manager.resolve_monitor("focused"), "eDP-1")
        self.assertEqual(self.manager.resolve_monitor("DP-1"), "DP-1")

    def test_rejects_unknown_and_disabled_monitors(self):
        for target in ("missing", "HDMI-1"):
            with self.subTest(target=target):
                with self.assertRaises(PresetError) as error:
                    self.manager.resolve_monitor(target)
                self.assertEqual(error.exception.error_code, "monitor_unavailable")

    def test_focused_monitor_disappearance_aborts_apply(self):
        self.save_custom(brightness=43)
        self.operations.monitors = [dict(self.operations.monitors[0])]
        self.operations.monitors[0]["focused"] = True
        original_step = self.operations.brightness_step

        def unplug_after_first_step(monitor, token):
            result = original_step(monitor, token)
            self.operations.monitors = []
            return result

        self.operations.brightness_step = unplug_after_first_step
        result = self.manager.apply_preset("desk", monitor="focused", timeout=10)
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "monitor_unavailable")
        self.assertEqual(len(self.operations.brightness_steps), 1)
        self.assertIsNone(state_utils.read_state()["last_applied"])
        self.assertEqual(len(state_utils.list_history()), 1)

    def test_builtin_presets_are_immutable(self):
        self.assertEqual(
            {preset["name"] for preset in self.manager.list_presets()},
            {"reading", "work", "cinema"},
        )
        for action in (
            lambda: self.manager.save_preset("reading", 4200, 80),
            lambda: self.manager.delete_preset("reading"),
        ):
            with self.assertRaises(PresetError) as error:
                action()
            self.assertEqual(error.exception.error_code, "builtin_immutable")

    def test_custom_names_values_and_default_delete_conflict_are_strict(self):
        invalid_saves = [
            ("Desk", 4200, 80, None),
            ("desk name", 4200, 80, None),
            ("desk", True, 80, None),
            ("desk", 4200, 101, None),
            ("desk", 4200, 80, 0),
        ]
        for args in invalid_saves:
            with self.subTest(args=args):
                with self.assertRaises(PresetError) as error:
                    self.manager.save_preset(args[0], args[1], args[2], args[3])
                self.assertEqual(error.exception.error_code, "invalid_preset")

        self.save_custom()
        with self.assertRaises(PresetError) as error:
            self.manager.set_default_preset("unknown")
        self.assertEqual(error.exception.error_code, "preset_not_found")
        self.manager.set_default_preset("desk")
        with self.assertRaises(PresetError) as error:
            self.manager.delete_preset("desk")
        self.assertEqual(error.exception.error_code, "default_conflict")

    def test_brightness_converges_with_only_one_point_native_steps(self):
        self.save_custom(brightness=45)
        result = self.manager.apply_preset("desk", monitor="eDP-1", timeout=10)
        self.assertTrue(result["success"])
        self.assertEqual(
            self.operations.brightness_steps,
            [("eDP-1", "+1%"), ("eDP-1", "+1%"), ("eDP-1", "+1%")],
        )
        self.assertEqual(self.operations.brightness["eDP-1"], 45)

    def test_deadline_is_shared_across_repeated_brightness_steps(self):
        self.save_custom(brightness=50)
        self.operations.step_advances = 1.0
        result = self.manager.apply_preset("desk", monitor="eDP-1", timeout=2)
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "deadline_exceeded")
        self.assertEqual(len(self.operations.brightness_steps), 2)
        self.assertIsNone(state_utils.read_state()["last_applied"])
        self.assertEqual(len(state_utils.list_history()), 1)

    def test_readback_mismatch_aborts_without_claiming_success(self):
        self.save_custom(brightness=43)
        self.operations.readback_values["eDP-1"] = [42, 99]
        result = self.manager.apply_preset("desk", monitor="eDP-1", timeout=10)
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "readback_mismatch")
        self.assertEqual(self.operations.brightness_steps, [("eDP-1", "+1%")])
        self.assertIsNone(state_utils.read_state()["last_applied"])
        self.assertEqual(len(state_utils.list_history()), 1)

    def test_temperature_and_gamma_use_one_combined_nightlight_call(self):
        self.save_custom()
        result = self.manager.apply_preset("desk", monitor="DP-1", timeout=10)
        self.assertTrue(result["success"])
        self.assertEqual(self.operations.nightlight_calls, [(4200, 80)])
        self.assertEqual(self.operations.brightness_steps, [])

    def test_partial_failure_writes_one_history_record_and_preserves_last_applied(self):
        state_utils.write_state(
            dict(
                state_utils.DEFAULT_STATE,
                last_applied={
                    "at": "2026-08-13T10:00:00Z",
                    "origin": "manual",
                    "operation": "manual_apply",
                    "values": {"temperature": 3500, "gamma": 90},
                },
            )
        )
        self.save_custom()
        self.operations.fail_nightlight = True
        result = self.manager.apply_preset("desk", monitor="eDP-1", timeout=10)
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "nightlight_failure")
        self.assertEqual(
            state_utils.read_state()["last_applied"]["operation"], "manual_apply"
        )
        history = state_utils.list_history()
        self.assertEqual(len(history), 1)
        self.assertFalse(history[0]["success"])
        self.assertEqual(history[0]["error_code"], "nightlight_failure")

    def test_operation_ok_reports_unavailable_native_results_as_failure(self):
        result = {
            "available": False,
            "error_code": "nightlight_apply_failed",
            "error": "no se pudo aplicar el nightlight",
        }
        self.assertEqual(
            preset_utils._operation_ok(result), (False, "nightlight_apply_failed")
        )
        self.assertEqual(
            preset_utils._operation_ok({"available": True, "error": "parcial"}),
            (False, "native_failure"),
        )

    def test_native_unavailable_nightlight_fails_the_apply(self):
        self.save_custom(brightness=43)
        self.operations.nightlight_result = {
            "available": False,
            "error_code": "nightlight_apply_failed",
            "error": "no se pudo aplicar el nightlight",
        }
        result = self.manager.apply_preset("desk", monitor="eDP-1", timeout=10)
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "nightlight_apply_failed")
        self.assertEqual(self.operations.brightness_steps, [])
        self.assertIsNone(state_utils.read_state()["last_applied"])
        history = state_utils.list_history()
        self.assertEqual(len(history), 1)
        self.assertFalse(history[0]["success"])
        self.assertEqual(history[0]["error_code"], "nightlight_apply_failed")

    def test_success_updates_last_applied_only_after_all_operations(self):
        self.save_custom(brightness=43)
        result = self.manager.apply_preset("desk", monitor="eDP-1", timeout=10)
        self.assertTrue(result["success"])
        state = state_utils.read_state()
        self.assertEqual(state["origin"], "preset")
        self.assertEqual(state["last_applied"]["preset"], "desk")
        self.assertEqual(
            state["last_applied"]["values"],
            {"temperature": 4200, "gamma": 80, "brightness": 43},
        )
        history = state_utils.list_history()
        self.assertEqual(len(history), 1)
        self.assertTrue(history[0]["success"])
        self.assertEqual(history[0]["monitor"], "eDP-1")

    def test_state_failure_after_physical_operations_preserves_state_without_success_history(self):
        previous = {
            "at": "2026-08-13T10:00:00Z",
            "origin": "manual",
            "operation": "manual_apply",
            "values": {"temperature": 3500, "gamma": 90},
        }
        state_utils.write_state(dict(state_utils.DEFAULT_STATE, last_applied=previous))
        self.save_custom(brightness=43)

        with mock.patch.object(
            state_utils,
            "update_state",
            side_effect=state_utils.StateError("io_error", "injected state failure"),
        ):
            result = self.manager.apply_preset("desk", monitor="eDP-1", timeout=10)

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "state_failed")
        self.assertEqual(state_utils.read_state()["last_applied"], previous)
        self.assertEqual(self.operations.nightlight_calls, [(4200, 80)])
        self.assertEqual(self.operations.brightness_steps, [("eDP-1", "+1%")])
        history = state_utils.list_history()
        self.assertEqual(len(history), 1)
        self.assertFalse(history[0]["success"])
        self.assertEqual(history[0]["error_code"], "state_failed")

    def test_history_failure_after_state_commit_keeps_success_without_repeating_operations(self):
        self.save_custom()

        with mock.patch.object(
            state_utils,
            "append_history",
            side_effect=state_utils.StateError("io_error", "injected history failure"),
        ):
            result = self.manager.apply_preset("desk", monitor="DP-1", timeout=10)

        self.assertTrue(result["success"])
        self.assertEqual(result["error_code"], "history_error")
        self.assertEqual(self.operations.nightlight_calls, [(4200, 80)])
        self.assertEqual(self.operations.brightness_steps, [])
        self.assertEqual(state_utils.read_state()["last_applied"]["preset"], "desk")
        self.assertEqual(state_utils.list_history(), [])


if __name__ == "__main__":
    unittest.main()
