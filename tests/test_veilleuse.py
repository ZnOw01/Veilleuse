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


if __name__ == "__main__":
    unittest.main(verbosity=2)
