#!/usr/bin/python3
import datetime
import importlib
import json
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))
veilleuse = importlib.import_module("veilleuse")


@dataclass(frozen=True)
class BrightnessState:
    available: bool
    percent: int | None
    monitor: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class NightLightState:
    available: bool
    enabled: bool | None
    temperature: int | None
    identity: bool | None
    gamma: int | None
    error: str | None = None


class FakeBrightness:
    def __init__(self, state):
        self.state = state
        self.calls = []

    def read_state(self):
        self.calls.append(("read_state",))
        return self.state

    def set_percent(self, target):
        self.calls.append(("set_percent", target))
        self.state = BrightnessState(True, target, "eDP-1")
        return self.state

    def step(self, direction):
        self.calls.append(("step", direction))
        return self.state


class FakeNightLight:
    def __init__(self, state):
        self.state = state
        self.calls = []

    def read_state(self):
        self.calls.append(("read_state",))
        return self.state

    def set_natural(self):
        self.calls.append(("set_natural",))
        self.state = NightLightState(True, False, None, True, 100)
        return self.state

    def set_temperature(self, kelvin):
        self.calls.append(("set_temperature", kelvin))
        self.state = NightLightState(True, True, kelvin, False, 100)
        return self.state

    def set_gamma(self, percent):
        self.calls.append(("set_gamma", percent))
        self.state = NightLightState(True, True, 3500, False, percent)
        return self.state


class VeilleuseServiceTests(unittest.TestCase):
    def bundle(self, brightness=55, night=None):
        return veilleuse.BackendBundle(
            FakeBrightness(BrightnessState(True, brightness, "eDP-1")),
            FakeNightLight(night or NightLightState(True, True, 3500, False, 100)),
        )

    def test_app_id_is_the_unified_desktop_identity(self):
        self.assertEqual(veilleuse.APP_ID, "io.github.ZnOw01.Veilleuse")

    def test_status_snapshot_reads_both_native_adapters_and_is_json_safe(self):
        backends = self.bundle()
        snapshot = veilleuse.status_snapshot(backends)

        self.assertEqual(snapshot["brightness"]["percent"], 55)
        self.assertEqual(snapshot["brightness"]["monitor"], "eDP-1")
        self.assertEqual(snapshot["night_light"]["temperature"], 3500)
        json.dumps(snapshot)
        self.assertEqual(backends.brightness.calls, [("read_state",)])
        self.assertEqual(backends.night_light.calls, [("read_state",)])

    def test_toggle_uses_observed_state_and_confirms_the_write(self):
        backends = self.bundle(night=NightLightState(True, True, 3500, False, 100))

        result = veilleuse.toggle_night_light(backends)

        self.assertEqual(backends.night_light.calls,
                         [("read_state",), ("set_natural",)])
        self.assertTrue(result["identity"])

    def test_toggle_uses_observed_temperature_when_leaving_natural_mode(self):
        backends = self.bundle(night=NightLightState(True, False, 4200, True, 100))

        veilleuse.toggle_night_light(backends, fallback_temperature=3500)

        self.assertEqual(backends.night_light.calls,
                         [("read_state",), ("set_temperature", 4200)])

    def test_toggle_treats_identity_as_authoritative_over_enabled(self):
        backends = self.bundle(night=NightLightState(True, True, 4200, True, 100))

        veilleuse.toggle_night_light(backends, fallback_temperature=3500)

        self.assertEqual(backends.night_light.calls,
                         [("read_state",), ("set_temperature", 4200)])

    def test_unavailable_backend_raises_user_facing_operation_error(self):
        backends = self.bundle(
            night=NightLightState(False, None, None, None, None, "missing")
        )

        with self.assertRaisesRegex(veilleuse.OperationError, "disponible"):
            veilleuse.toggle_night_light(backends)

    def test_backend_error_state_is_not_treated_as_confirmed_success(self):
        state = BrightnessState(True, 42, "eDP-1", "Operación cancelada")

        with self.assertRaisesRegex(veilleuse.OperationError, "cancelada"):
            veilleuse._confirmed_state(state, lambda: state, "La pantalla")

    def test_confirmation_readback_receives_compatible_deadline(self):
        received = []

        def reader(*, deadline=None):
            received.append(deadline)
            return BrightnessState(True, 42, "eDP-1")

        veilleuse._confirmed_state(None, reader, "La pantalla", deadline=12.5)

        self.assertEqual(received, [12.5])

    def test_schedule_update_preserves_comments_custom_content_and_unmanaged_profiles(self):
        original = """# personal header
profile {
    time = 06:00
    identity
    # keep this note
}
profile {
    time = 15:30
    temperature = 3500
    custom_option = true
}
profile {
    time = 23:00
    temperature = 3200
}
"""

        updated = veilleuse.update_schedule_text(original, {
            "day_time": "07:15",
            "day_temp": 6100,
            "night_time": "22:45",
            "night_temp": 3000,
        })

        self.assertIn("# keep this note", updated)
        self.assertIn("custom_option = true", updated)
        self.assertIn("time = 23:00", updated)
        self.assertEqual(veilleuse.parse_schedule_text(updated), {
            "day_time": "07:15",
            "day_temp": 6000,
            "night_time": "22:45",
            "night_temp": 3000,
        })

    def test_malformed_schedule_is_not_replaced_by_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hyprsunset.conf"
            original = "profile { time = 06:00 }\n"
            path.write_text(original, encoding="utf-8")

            with patch.object(veilleuse, "STATE_LOCK", Path(directory) / "state.lock"):
                with self.assertRaises(ValueError):
                    veilleuse.write_schedule(path, veilleuse.default_schedule())

            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_load_schedule_reads_valid_existing_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hyprsunset.conf"
            path.write_text(
                "profile { time = 07:00 identity }\n"
                "profile { time = 22:00 temperature = 3000 }\n",
                encoding="utf-8",
            )

            self.assertEqual(veilleuse.load_schedule(path), {
                "day_time": "07:00",
                "day_temp": 6000,
                "night_time": "22:00",
                "night_temp": 3000,
            })

    def test_schedule_write_is_atomic_and_preserves_existing_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hyprsunset.conf"
            path.write_text(
                "profile { time = 06:00 identity }\n"
                "profile { time = 15:30 temperature = 3500 }\n",
                encoding="utf-8",
            )
            path.chmod(0o640)

            with patch.object(veilleuse, "STATE_LOCK", Path(directory) / "state.lock"):
                veilleuse.write_schedule(path, {
                    "day_time": "06:30",
                    "day_temp": 6000,
                    "night_time": "21:00",
                    "night_temp": 3200,
                })

            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            self.assertEqual(veilleuse.parse_schedule_text(path.read_text()), {
                "day_time": "06:30",
                "day_temp": 6000,
                "night_time": "21:00",
                "night_temp": 3200,
            })

    def test_schedule_update_does_not_duplicate_an_unchanged_temperature(self):
        original = (
            "profile { time = 06:00 identity }\n"
            "profile { time = 15:30 temperature = 3500 }\n"
        )

        updated = veilleuse.update_schedule_text(original, {
            "day_time": "06:00",
            "day_temp": 6000,
            "night_time": "15:30",
            "night_temp": 3500,
        })

        self.assertEqual(updated, original)

    def test_worker_runs_work_off_the_caller_thread_and_dispatches_result(self):
        started = threading.Event()
        finished = threading.Event()
        calls = []
        caller = threading.get_ident()

        def work():
            started.set()
            return threading.get_ident()

        def dispatch(callback):
            callback()

        veilleuse.run_worker(work, calls.append, calls.append, dispatch=dispatch)
        self.assertTrue(started.wait(1))
        for _ in range(100):
            if len(calls) >= 1:
                break
            time.sleep(0.01)

        self.assertEqual(len(calls), 1)
        self.assertNotEqual(calls[0], caller)


class LatestValueQueueTests(unittest.TestCase):
    def test_cancellable_queue_keeps_only_latest_value_and_stops_active_work(self):
        started = []
        completions = {}
        results = []

        def start(value, cancel_event, complete):
            started.append((value, cancel_event))
            completions[value] = complete

        queue = veilleuse.LatestValueQueue(
            start, lambda value, result, obsolete: results.append((value, result, obsolete)),
            cancel_active=True,
        )

        queue.submit(20)
        queue.submit(40)
        queue.submit(60)

        self.assertEqual([value for value, _event in started], [20])
        self.assertTrue(started[0][1].is_set())

        completions[20]("cancelled")
        self.assertEqual([value for value, _event in started], [20, 60])
        self.assertEqual(results, [(20, "cancelled", True)])

        completions[60]("confirmed")
        self.assertEqual(results, [(20, "cancelled", True), (60, "confirmed", False)])

    def test_non_cancellable_queue_starts_latest_value_after_active_result(self):
        started = []
        completions = {}

        def start(value, cancel_event, complete):
            started.append((value, cancel_event))
            completions[value] = complete

        queue = veilleuse.LatestValueQueue(start, lambda *_: None)
        queue.submit(20)
        queue.submit(40)
        queue.submit(60)

        self.assertFalse(started[0][1].is_set())
        completions[20]("confirmed")
        self.assertEqual([value for value, _event in started], [20, 60])

    def test_backend_adapter_supports_future_optional_deadline_and_cancel_event(self):
        received = []
        deadline = 123.5

        def future_backend(value, *, deadline=None, cancel_event=None):
            received.append((value, deadline, cancel_event))
            return "ok"

        cancel_event = threading.Event()
        self.assertEqual(
            veilleuse._call_backend(
                future_backend, 72, deadline=deadline, should_stop=cancel_event.is_set
            ),
            "ok",
        )
        self.assertEqual(received, [(72, deadline, cancel_event)])

    def test_backend_adapter_keeps_legacy_backend_signature_compatible(self):
        received = []

        def legacy_backend(value):
            received.append(value)
            return "ok"

        self.assertEqual(
            veilleuse._call_backend(
                legacy_backend, 72, deadline=123.5, should_stop=lambda: False
            ),
            "ok",
        )
        self.assertEqual(received, [72])


class VeilleuseAccessibilityTests(unittest.TestCase):
    def test_brightness_minimum_matches_native_backend_contract(self):
        self.assertEqual(veilleuse.BRIGHTNESS_MIN, 1)

    def test_accessible_label_is_explicit_in_addition_to_tooltip(self):
        calls = []

        class Widget:
            def update_property(self, properties, values):
                calls.append((properties, values))

        class Gtk:
            class AccessibleProperty:
                LABEL = "label"

        with patch.object(veilleuse, "_gtk_modules", return_value=(None, None, None, Gtk)):
            veilleuse._accessible_label(Widget(), "Reducir brillo")

        self.assertEqual(calls, [(["label"], ["Reducir brillo"])])



class DisplayControlStateTests(unittest.TestCase):
    def test_confirmed_value_resynchronizes_widget_without_reentering_user_handler(self):
        controls = veilleuse.DisplayControlState()
        observed = []

        confirmed = controls.confirm(
            "brightness",
            BrightnessState(True, 62, "eDP-1"),
            apply=lambda value: observed.append((value, controls.accepts_user_input)),
        )

        self.assertEqual(confirmed, 62)
        self.assertEqual(observed, [(62, False)])
        self.assertEqual(controls.confirmed("brightness"), 62)
        self.assertTrue(controls.accepts_user_input)

    def test_each_confirmed_display_control_resynchronizes_its_widget(self):
        controls = veilleuse.DisplayControlState()
        observed = []

        controls.confirm(
            "temperature",
            NightLightState(True, True, 2900, False, 100),
            apply=lambda value: observed.append(
                ("temperature", value, controls.accepts_user_input)
            ),
        )
        controls.confirm(
            "gamma",
            NightLightState(True, True, 2900, False, 73),
            apply=lambda value: observed.append(
                ("gamma", value, controls.accepts_user_input)
            ),
        )

        self.assertEqual(observed, [
            ("temperature", 2900, False),
            ("gamma", 73, False),
        ])
        self.assertEqual(controls.confirmed("temperature"), 2900)
        self.assertEqual(controls.confirmed("gamma"), 73)

    def test_brightness_steps_advance_from_latest_requested_confirmed_value(self):
        controls = veilleuse.DisplayControlState()
        controls.apply_snapshot({"brightness": {"percent": 40}}, {"brightness"})

        self.assertEqual(controls.step_brightness(1), 41)
        self.assertEqual(controls.step_brightness(1), 42)
        self.assertEqual(controls.step_brightness(-1), 41)

        controls.apply_snapshot({"brightness": {"percent": 70}}, {"brightness"})
        self.assertEqual(controls.step_brightness(1), 71)

    def test_external_refresh_is_deferred_until_all_control_queues_are_idle(self):
        controls = veilleuse.DisplayControlState()

        self.assertFalse(controls.request_refresh(controls_idle=False))
        self.assertFalse(controls.take_deferred_refresh(controls_idle=False))
        self.assertTrue(controls.take_deferred_refresh(controls_idle=True))
        self.assertFalse(controls.take_deferred_refresh(controls_idle=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
