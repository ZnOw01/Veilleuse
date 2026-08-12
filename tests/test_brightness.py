#!/usr/bin/python3
import contextlib
import importlib.util
import os
import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import call, patch

import gi

ACCESSIBILITY_PATH = Path(__file__).parents[1] / "src/ui_accessibility.py"
accessibility_spec = importlib.util.spec_from_file_location("ui_accessibility", ACCESSIBILITY_PATH)
accessibility = importlib.util.module_from_spec(accessibility_spec)
accessibility_spec.loader.exec_module(accessibility)

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk

MODULE_PATH = Path(__file__).parents[1] / "src/brightness_control.py"
spec = importlib.util.spec_from_file_location("brightness_control", MODULE_PATH)
brightness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brightness)

HELPER_PATH = Path(__file__).parents[1] / "bin/brightness-step"
helper_loader = SourceFileLoader("brightness_step", str(HELPER_PATH))
helper_spec = importlib.util.spec_from_loader("brightness_step", helper_loader)
brightness_step = importlib.util.module_from_spec(helper_spec)
helper_spec.loader.exec_module(brightness_step)


class AccessibilityTests(unittest.TestCase):
    def test_range_accessibility_sets_label_and_current_value(self):
        calls = []

        class Widget:
            def update_property(self, properties, values):
                calls.append((properties, values))

        accessibility.set_range(Widget(), "Brillo de pantalla", 1, 100, 42, "42 %")
        self.assertEqual(calls[0][1], ["Brillo de pantalla", 1.0, 100.0, 42.0, "42 %"])

    def test_description_accessibility_sets_description_and_invalid_state(self):
        calls = []

        class Widget:
            def update_property(self, properties, values):
                calls.append(("property", properties, values))

            def update_state(self, states, values):
                calls.append(("state", states, values))

        accessibility.set_description(Widget(), "Hora inválida", invalid=True)
        self.assertEqual(calls[0][2], ["Hora inválida"])
        self.assertEqual(calls[1][2], [1])
        self.assertIs(type(calls[1][2][0]), int)
        self.assertEqual(calls[1][1], [accessibility.Gtk.AccessibleState.INVALID])

    def test_status_accessibility_sets_status_role_label_and_busy_state(self):
        calls = []

        class Widget:
            def set_accessible_role(self, role):
                calls.append(("role", role))

            def update_property(self, properties, values):
                calls.append(("property", properties, values))

            def update_state(self, states, values):
                calls.append(("state", states, values))

        accessibility.set_status(Widget(), "Buscando…", busy=True)
        self.assertEqual(calls[0], ("role", accessibility.Gtk.AccessibleRole.STATUS))
        self.assertEqual(calls[1][2], ["Buscando…"])
        self.assertEqual(calls[2][1], [accessibility.Gtk.AccessibleState.BUSY])
        self.assertEqual(calls[2][2], [True])
        self.assertIs(type(calls[2][2][0]), bool)


class BackendStatusAccessibilityTests(unittest.TestCase):
    def test_backend_status_uses_status_accessibility_and_preserves_css(self):
        calls = []

        class Label:
            def set_label(self, text):
                calls.append(("label", text))

            def remove_css_class(self, css_class):
                calls.append(("remove", css_class))

            def add_css_class(self, css_class):
                calls.append(("add", css_class))

        window = type("Window", (), {"backend_status": Label()})()
        with patch.object(brightness, "set_status") as set_status:
            brightness.BrightnessWindow._set_backend_status(window, "Buscando…", "warning")

        set_status.assert_called_once_with(window.backend_status, "Buscando…", busy=True)
        self.assertIn(("label", "Buscando…"), calls)
        self.assertIn(("add", "warning"), calls)
        self.assertIn(("remove", "success"), calls)
        self.assertIn(("remove", "error"), calls)
        self.assertIn(("remove", "warning"), calls)


class BrightnessValueTests(unittest.TestCase):
    def test_clamps_percentage_to_safe_panel_range(self):
        self.assertEqual(brightness.clamp_percent(-20), 1)
        self.assertEqual(brightness.clamp_percent(37), 37)
        self.assertEqual(brightness.clamp_percent(140), 100)

    def test_parses_brightnessctl_machine_output(self):
        info = brightness.parse_brightness_info(
            "nvidia_wmi_ec_backlight,backlight,16,2%,800\n"
        )
        self.assertEqual(info["device"], "nvidia_wmi_ec_backlight")
        self.assertEqual(info["current"], 16)
        self.assertEqual(info["maximum"], 800)
        self.assertEqual(info["percent"], 2)

    def test_selects_best_backlight_from_multiline_output(self):
        info = brightness.parse_brightness_info(
            "acpi_video0,backlight,10,10%,100\n"
            "intel_backlight,backlight,200,20%,1000\n"
        )
        self.assertEqual(info["device"], "intel_backlight")
        self.assertEqual(info["percent"], 20)

    def test_preferred_backlight_device_wins(self):
        with patch.dict(os.environ, {"NIGHT_LIGHT_BACKLIGHT_DEVICE": "acpi_video0"}):
            info = brightness.parse_brightness_info(
                "intel_backlight,backlight,200,20%,1000\n"
                "acpi_video0,backlight,10,10%,100\n"
            )
        self.assertEqual(info["device"], "acpi_video0")

    def test_rejects_malformed_brightness_output(self):
        with self.assertRaises(ValueError):
            brightness.parse_brightness_info("unavailable")

    def test_limits_every_requested_change_to_one_percent(self):
        self.assertEqual(brightness.limit_change(1, 100), 2)
        self.assertEqual(brightness.limit_change(80, 1), 79)
        self.assertEqual(brightness.limit_change(40, 41), 41)

    def test_plans_one_physical_step_from_real_brightness(self):
        info = {"device": "intel_backlight", "percent": 2}
        self.assertEqual(brightness.plan_brightness_change(info, 1), (3, "1%+"))
        self.assertEqual(brightness.plan_brightness_change(info, -1), (1, "1%-"))
        self.assertEqual(brightness.plan_brightness_change(info, 0), (2, None))

    def test_verification_accepts_only_the_requested_direction_and_one_percent(self):
        before = {"device": "intel_backlight", "percent": 50}
        self.assertTrue(brightness.is_safe_brightness_change(
            before, {"device": "intel_backlight", "percent": 51}, 1
        ))
        self.assertTrue(brightness.is_safe_brightness_change(
            before, {"device": "intel_backlight", "percent": 50}, 1
        ))
        self.assertFalse(brightness.is_safe_brightness_change(
            before, {"device": "intel_backlight", "percent": 52}, 1
        ))
        self.assertFalse(brightness.is_safe_brightness_change(
            before, {"device": "intel_backlight", "percent": 49}, 1
        ))

    def test_transaction_keeps_lock_around_read_step_and_verification(self):
        events = []
        readings = iter([
            {"device": "intel_backlight", "percent": 80},
            {"device": "intel_backlight", "percent": 81},
        ])

        @contextlib.contextmanager
        def fake_lock(path):
            events.append(("lock-enter", path))
            yield
            events.append(("lock-exit", path))

        def read(device=None):
            events.append(("read", device))
            return next(readings)

        def apply(device, adjustment):
            events.append(("apply", device, adjustment))
            return subprocess.CompletedProcess([], 0, "", "")

        with (
            patch.object(brightness, "exclusive_lock", side_effect=fake_lock),
            patch.object(brightness, "get_brightness_info", side_effect=read),
            patch.object(brightness, "set_brightness_step", side_effect=apply),
        ):
            result = brightness.perform_brightness_step("intel_backlight", 1)

        self.assertEqual(result, {
            "device": "intel_backlight", "percent": 81, "changed": True,
        })
        self.assertEqual(events, [
            ("lock-enter", brightness.STATE_LOCK),
            ("read", "intel_backlight"),
            ("apply", "intel_backlight", "1%+"),
            ("read", "intel_backlight"),
            ("lock-exit", brightness.STATE_LOCK),
        ])

    def test_read_retries_then_redetects_a_missing_device(self):
        info = {"device": "new_backlight", "percent": 40}
        with (
            patch.object(
                brightness,
                "get_brightness_info",
                side_effect=[RuntimeError("missing"), RuntimeError("missing"), info],
            ) as get_info,
            patch.object(brightness.time, "sleep"),
        ):
            self.assertEqual(
                brightness.read_brightness_with_retry("old_backlight"), info
            )
        self.assertEqual(get_info.call_args_list, [
            call("old_backlight"), call("old_backlight"), call(None),
        ])

    def test_discovers_default_backlight_device(self):
        result = subprocess.CompletedProcess(
            ["brightnessctl", "-c", "backlight", "-m"], 0,
            "intel_backlight,backlight,200,20%,1000\n", "",
        )
        with patch.object(brightness, "command", return_value=result) as mocked:
            info = brightness.get_brightness_info()
        mocked.assert_called_once_with(["brightnessctl", "-c", "backlight", "-m"])
        self.assertEqual(info["device"], "intel_backlight")

    def test_uses_relative_step_on_discovered_device(self):
        result = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(brightness, "command", return_value=result) as mocked:
            brightness.set_brightness_step("intel_backlight", "1%+")
        mocked.assert_called_once_with([
            "brightnessctl", "-c", "backlight", "-d", "intel_backlight", "set", "1%+",
        ])

    def test_debounced_apply_reads_real_device_and_syncs_one_step(self):
        class WindowDouble:
            device = "intel_backlight"
            apply_timeout = 123

            def __init__(self):
                self.synced = []
                self.toasts = []

            def sync_value(self, percent):
                self.synced.append(percent)

            def toast(self, message):
                self.toasts.append(message)

        window = WindowDouble()
        readings = [
            {"device": "intel_backlight", "percent": 80},
            {"device": "intel_backlight", "percent": 81},
        ]
        success = subprocess.CompletedProcess([], 0, "", "")
        with (
            tempfile.TemporaryDirectory(prefix="brightness-test-") as td,
            patch.object(brightness, "STATE_LOCK", Path(td) / "state.lock"),
            patch.object(brightness, "get_brightness_info", side_effect=readings) as get_info,
            patch.object(brightness, "set_brightness_step", return_value=success) as set_step,
        ):
            result = brightness.BrightnessWindow.apply_value(window, 1)

        self.assertEqual(get_info.call_count, 2)
        set_step.assert_called_once_with("intel_backlight", "1%+")
        self.assertEqual(window.synced, [81])
        self.assertEqual(window.toasts, [])
        self.assertIsNone(window.apply_timeout)
        self.assertEqual(result, brightness.GLib.SOURCE_REMOVE)

    def test_worker_posts_result_to_the_gtk_thread(self):
        class WorkerDouble:
            def __init__(self):
                self.scheduled = []

            def _finish_apply(self, result, error):
                self.scheduled.append((result, error))

        window = WorkerDouble()
        result = {"device": "intel_backlight", "percent": 61, "changed": True}
        scheduled = []
        with (
            patch.object(brightness, "perform_brightness_step", return_value=result),
            patch.object(
                brightness.GLib,
                "idle_add",
                side_effect=lambda callback, *args: scheduled.append((callback, args)),
            ),
        ):
            brightness.BrightnessWindow._apply_worker(window, "intel_backlight", 1)

        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0][0].__name__, "_finish_apply")
        self.assertEqual(scheduled[0][1], (result, None))

    @unittest.skipUnless(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"),
        "requires a graphical session",
    )
    def test_action_row_is_attached_to_a_list_box_parent(self):
        if Gdk.Display.get_default() is None:
            self.skipTest("graphical display is unavailable")
        with patch.object(brightness.GLib, "idle_add", return_value=0):
            window = brightness.BrightnessWindow(None)
        try:
            self.assertIsInstance(window.device_row.get_parent(), brightness.Gtk.ListBox)
        finally:
            window.stop_timers()
            window.close()

    def test_closed_window_discards_worker_result_before_touching_widgets(self):
        class ClosedWindow:
            closed = True

        result = {"device": "intel_backlight", "percent": 61, "changed": True}
        window = ClosedWindow()
        self.assertEqual(
            brightness.BrightnessWindow._finish_apply(window, result, None),
            brightness.GLib.SOURCE_REMOVE,
        )


class BrightnessHelperTests(unittest.TestCase):
    def test_helper_verifies_the_relative_step_under_the_shared_lock(self):
        output_before = "intel_backlight,backlight,800,80%,1000\n"
        output_after = "intel_backlight,backlight,810,81%,1000\n"
        success = subprocess.CompletedProcess([], 0, "", "")
        calls = []

        @contextlib.contextmanager
        def fake_lock(path):
            calls.append(("lock-enter", path))
            yield
            calls.append(("lock-exit", path))

        with (
            patch.object(brightness_step, "sys") as fake_sys,
            patch.object(brightness_step, "exclusive_lock", side_effect=fake_lock),
            patch.object(
                brightness_step,
                "run",
                side_effect=[
                    subprocess.CompletedProcess([], 0, output_before, ""),
                    success,
                    subprocess.CompletedProcess([], 0, output_after, ""),
                ],
            ) as run,
        ):
            fake_sys.argv = ["brightness-step", "+"]
            result = brightness_step.main()

        self.assertEqual(result, 0)
        self.assertEqual(calls, [
            ("lock-enter", brightness_step.STATE_LOCK),
            ("lock-exit", brightness_step.STATE_LOCK),
        ])
        self.assertEqual(run.call_args_list[1].args[0][-1], "1%+")
        self.assertEqual(len(run.call_args_list), 3)

    def test_helper_rejects_a_verified_jump_over_one_percent(self):
        output_before = "intel_backlight,backlight,800,80%,1000\n"
        output_after = "intel_backlight,backlight,830,83%,1000\n"
        success = subprocess.CompletedProcess([], 0, "", "")
        with (
            patch.object(brightness_step, "sys") as fake_sys,
            patch.object(brightness_step, "exclusive_lock", return_value=contextlib.nullcontext()),
            patch.object(
                brightness_step,
                "run",
                side_effect=[
                    subprocess.CompletedProcess([], 0, output_before, ""),
                    success,
                    subprocess.CompletedProcess([], 0, output_after, ""),
                ],
            ),
        ):
            fake_sys.argv = ["brightness-step", "+"]
            self.assertEqual(brightness_step.main(), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
