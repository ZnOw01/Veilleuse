#!/usr/bin/python3
"""Deterministic tests for the automation orchestration module.

All tests use injected fake clocks, sleepers, cancellation tokens,
applicators and (optionally) the real ``state_utils`` persistence backed by a
temporary XDG home.  No live shell commands or real time are ever used.
"""

import copy
import datetime
import json
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
import scripts.automation_utils as automation


ISO = "1970-01-01T00:16:40Z"


class FakeClock:
    """Deterministic wall clock, monotonic clock and sleeper in one object."""

    def __init__(self, now=1000.0, monotonic=0.0):
        self.now_value = now
        self.monotonic_value = monotonic
        self.sleeps = []

    def now(self):
        return self.now_value

    def monotonic(self):
        return self.monotonic_value

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now_value += seconds
        self.monotonic_value += seconds

    def advance(self, seconds):
        self.sleeps.append(seconds)
        self.now_value += seconds
        self.monotonic_value += seconds


class FakeToken:
    """Cancellation token that can trip itself when fake time passes a point."""

    def __init__(self, clock=None, trip_monotonic=None):
        self.clock = clock
        self.trip_monotonic = trip_monotonic
        self.cancelled = False

    def is_set(self):
        if self.clock is not None and self.trip_monotonic is not None:
            if self.clock.monotonic() >= self.trip_monotonic:
                self.cancelled = True
        return self.cancelled

    def cancel(self):
        self.cancelled = True


class FakeNightlight:
    """Injected applicator and reader with scriptable failures."""

    def __init__(self, temperature=3500, gamma=90, identity=False):
        self.temperature = temperature
        self.gamma = gamma
        self.identity = identity
        self.applications = []  # (temperature, gamma) successful apply_values
        self.naturals = 0
        self.read_error = False
        self.fail_first = 0  # number of initial applies that fail
        self.fail_at = None  # 1-based attempt index that fails (None = never)
        self.apply_attempts = 0

    def read(self):
        if self.read_error:
            return {
                "available": False,
                "identity": None,
                "temperature": None,
                "gamma": None,
                "error": "backend down",
            }
        return {
            "available": True,
            "identity": self.identity,
            "temperature": 6000 if self.identity else self.temperature,
            "gamma": self.gamma,
            "error": None,
        }

    def apply_values(self, temperature, gamma):
        self.apply_attempts += 1
        if self.fail_first > 0:
            self.fail_first -= 1
            return self._rejected()
        if self.fail_at is not None and self.apply_attempts == self.fail_at:
            return self._rejected()
        self.temperature = temperature
        self.gamma = gamma
        self.identity = False
        self.applications.append((temperature, gamma))
        return {
            "available": True,
            "identity": False,
            "temperature": temperature,
            "gamma": gamma,
            "error": None,
        }

    def apply_natural(self):
        self.apply_attempts += 1
        if self.fail_first > 0:
            self.fail_first -= 1
            return self._rejected()
        if self.fail_at is not None and self.apply_attempts == self.fail_at:
            return self._rejected()
        self.identity = True
        self.temperature = 6000
        self.naturals += 1
        return {
            "available": True,
            "identity": True,
            "temperature": 6000,
            "gamma": self.gamma,
            "error": None,
        }

    def _rejected(self):
        return {
            "available": False,
            "identity": None,
            "temperature": None,
            "gamma": None,
            "error": "apply rejected",
        }


class FakeDisplay:
    """Injected scheduled-display applicator (brightness / gamma)."""

    def __init__(self, brightness=50):
        self.brightness = brightness
        self.gamma = None
        self.brightness_writes = []
        self.gamma_writes = []
        self.fail_brightness = False
        self.fail_gamma = False

    def apply_brightness(self, percent):
        if self.fail_brightness:
            return {"available": False, "percent": None, "error": "ddc busy"}
        self.brightness = int(percent)
        self.brightness_writes.append(int(percent))
        return {"available": True, "percent": int(percent), "error": None}

    def apply_gamma(self, percent):
        if self.fail_gamma:
            return {"available": False, "identity": None, "temperature": None,
                    "gamma": None, "error": "gamma rejected"}
        self.gamma = int(percent)
        self.gamma_writes.append(int(percent))
        return {"available": True, "identity": False, "temperature": None,
                "gamma": int(percent), "error": None}


class AutomationUtilsTest(unittest.TestCase):
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
        self.token = None
        self.nightlight = FakeNightlight()
        self.display = FakeDisplay()
        self.profile = {
            "available": True,
            "kind": "temperature",
            "temperature": 3500,
            "period": "night",
        }

    def tearDown(self):
        self.environment.stop()
        self.tempdir.cleanup()

    def state_file(self):
        return self.state_home / "veilleuse" / "state.json"

    def history_file(self):
        return self.state_home / "veilleuse" / "history.jsonl"

    def initial_state(self, **changes):
        state = copy.deepcopy(state_utils.DEFAULT_STATE)
        state.update(changes)
        state_utils.write_state(state)
        return state

    def env(self, **overrides):
        env = {
            "now": self.clock.now,
            "monotonic": self.clock.monotonic,
            "sleep": self.clock.sleep,
            "read_state": state_utils.read_state,
            "update_state": state_utils.update_state,
            "append_history": state_utils.append_history,
            "read_nightlight": self.nightlight.read,
            "apply_values": self.nightlight.apply_values,
            "apply_natural": self.nightlight.apply_natural,
            "apply_brightness": self.display.apply_brightness,
            "apply_gamma": self.display.apply_gamma,
            "current_profile": lambda: self.profile,
            "token": lambda: self.token,
        }
        env.update(overrides)
        return env

    def read_state(self):
        return state_utils.read_state()

    def read_history(self):
        return state_utils.list_history()

    # ------------------------------------------------------------------ \
    # snooze status

    def test_snooze_status_pure_active_expired_and_none(self):
        state = {"snooze_until": 1000.0}
        active = automation.snooze_status(state, 500.0)
        self.assertTrue(active["snoozed"])
        self.assertEqual(active["snooze_until"], 1000.0)
        self.assertEqual(active["expires_in_seconds"], 500.0)
        self.assertEqual(active["expires_in_minutes"], 8)

        expired = automation.snooze_status(state, 1000.0)
        self.assertFalse(expired["snoozed"])
        self.assertEqual(expired["expires_in_seconds"], 0)

        none = automation.snooze_status({"snooze_until": None}, 500.0)
        self.assertFalse(none["snoozed"])
        self.assertIsNone(none["snooze_until"])

    def test_snooze_set_applies_natural_and_persists_expiry_provenance_history(self):
        result = automation.snooze_set(30, env=self.env())
        self.assertTrue(result["success"], result)
        self.assertTrue(result["applied"])
        self.assertTrue(result["snoozed"])
        self.assertEqual(result["snooze_until"], 1000.0 + 30 * 60)
        self.assertEqual(result["expires_in_seconds"], 1800.0)

        self.assertEqual(self.nightlight.naturals, 1)
        state = self.read_state()
        self.assertEqual(state["snooze_until"], 1000.0 + 30 * 60)
        last = state["last_applied"]
        self.assertEqual(last["origin"], "snooze")
        self.assertEqual(last["operation"], "snooze_set")
        self.assertEqual(last["at"], ISO)
        self.assertEqual(last["values"], {"temperature": 6000, "gamma": 90})

        records = self.read_history()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["operation"], "snooze_set")
        self.assertEqual(records[0]["origin"], "snooze")
        self.assertTrue(records[0]["success"])

    def test_snooze_set_status_survives_separate_process_style_reread(self):
        automation.snooze_set(30, env=self.env())
        later_clock = FakeClock(now=1100.0)
        fresh_env = self.env(now=later_clock.now, token=None)
        status = automation.snooze_status_current(env=fresh_env)
        self.assertTrue(status["snoozed"])
        self.assertEqual(status["snooze_until"], 2800.0)

        expired_clock = FakeClock(now=3000.0)
        status = automation.snooze_status_current(
            env=self.env(now=expired_clock.now, token=None)
        )
        self.assertFalse(status["snoozed"])

    def test_snooze_set_bounds_minutes(self):
        for minutes in (0, -5, 1441, 3.5, True, "45"):
            result = automation.snooze_set(minutes, env=self.env())
            self.assertFalse(result["success"], minutes)
            self.assertEqual(result["error_code"], "invalid_argument", minutes)
        self.assertEqual(self.nightlight.naturals, 0)
        self.assertFalse(self.state_file().exists())

    def test_snooze_set_seconds_applies_and_persists_expiry(self):
        # The panel composes number + unit; seconds is the base unit, so a
        # 90-second snooze keeps working exactly as requested.
        result = automation.snooze_set_seconds(90, env=self.env())
        self.assertTrue(result["success"])
        self.assertTrue(result["snoozed"])
        self.assertEqual(result["snooze_until"], 1000.0 + 90)
        state = self.read_state()
        self.assertEqual(state["snooze_until"], 1090.0)
        self.assertEqual(state["last_applied"]["operation"], "snooze_set")

    def test_snooze_set_seconds_bounds(self):
        for seconds in (9, -1, 86401, 12.5, True, "60"):
            result = automation.snooze_set_seconds(seconds, env=self.env())
            self.assertFalse(result["success"], seconds)
            self.assertEqual(result["error_code"], "invalid_argument", seconds)
        self.assertEqual(self.nightlight.naturals, 0)
        self.assertFalse(self.state_file().exists())

    def test_snooze_set_apply_failure_persists_nothing(self):
        self.nightlight.fail_first = 1
        result = automation.snooze_set(30, env=self.env())
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "apply_failed")
        self.assertFalse(self.state_file().exists())
        self.assertEqual(self.read_history(), [])

    def test_snooze_set_state_failure_after_apply_is_honest(self):
        def failing_update(mutator):
            raise state_utils.StateError("io_error", "disk full")

        result = automation.snooze_set(
            30, env=self.env(update_state=failing_update)
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "state_failed")
        # Natural was applied but the expiry was never persisted.
        self.assertEqual(self.nightlight.naturals, 1)
        self.assertFalse(self.state_file().exists())
        records = self.read_history()
        self.assertEqual(len(records), 1)
        self.assertFalse(records[0]["success"])
        self.assertEqual(records[0]["error_code"], "state_failed")

    def test_snooze_set_history_failure_is_reported_but_core_succeeds(self):
        def failing_history(record):
            raise state_utils.StateError("io_error", "history full")

        result = automation.snooze_set(30, env=self.env(append_history=failing_history))
        self.assertTrue(result["success"], result)
        self.assertEqual(result["history_error"], "io_error")
        state = self.read_state()
        self.assertEqual(state["snooze_until"], 2800.0)
        self.assertEqual(state["last_applied"]["origin"], "snooze")

    def test_snooze_clear_persists_and_records_history(self):
        self.initial_state(snooze_until=2800.0, origin="snooze")
        result = automation.snooze_clear(env=self.env())
        self.assertTrue(result["success"])
        self.assertTrue(result["cleared"])
        self.assertFalse(result["snoozed"])
        self.assertEqual(self.read_state()["snooze_until"], None)
        records = self.read_history()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["operation"], "snooze_clear")
        self.assertNotIn("temperature", records[0])

    def test_snooze_clear_noop_when_not_snoozed(self):
        result = automation.snooze_clear(env=self.env())
        self.assertTrue(result["success"])
        self.assertFalse(result["cleared"])
        self.assertEqual(self.read_state(), state_utils.DEFAULT_STATE)
        self.assertEqual(self.read_history(), [])
        self.assertEqual(self.nightlight.naturals, 0)

    def test_snooze_clear_state_failure_is_honest(self):
        self.initial_state(snooze_until=2800.0)

        def failing_update(mutator):
            raise state_utils.StateError("io_error", "disk full")

        result = automation.snooze_clear(env=self.env(update_state=failing_update))
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "state_failed")
        self.assertEqual(self.read_state()["snooze_until"], 2800.0)

    def test_snooze_clear_clears_manual_override(self):
        self.initial_state(
            snooze_until=2800.0,
            manual_override=self.manual_override(),
        )
        result = automation.snooze_clear(env=self.env())
        self.assertTrue(result["success"], result)
        state = self.read_state()
        self.assertIsNone(state["snooze_until"])
        self.assertIsNone(state["manual_override"])

    def test_snooze_clear_clears_override_in_single_atomic_write(self):
        self.initial_state(
            snooze_until=2800.0,
            manual_override=self.manual_override(),
        )
        calls = []

        def tracking_update(mutator):
            calls.append(mutator)
            return state_utils.update_state(mutator)

        result = automation.snooze_clear(env=self.env(update_state=tracking_update))
        self.assertTrue(result["success"], result)
        self.assertEqual(len(calls), 1)
        mutated = calls[0](self.read_state())
        self.assertIsNone(mutated["snooze_until"])
        self.assertIsNone(mutated["manual_override"])

    def test_snooze_clear_failure_preserves_both_snooze_and_override(self):
        self.initial_state(
            snooze_until=2800.0,
            manual_override=self.manual_override(),
        )

        def failing_update(mutator):
            raise state_utils.StateError("io_error", "disk full")

        result = automation.snooze_clear(env=self.env(update_state=failing_update))
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "state_failed")
        state = self.read_state()
        self.assertEqual(state["snooze_until"], 2800.0)
        self.assertEqual(state["manual_override"], self.manual_override())

    # ------------------------------------------------------------------ \
    # transition

    def test_reconcile_noop_when_no_drift_and_idempotent(self):
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"])
        self.assertFalse(result["applied"])
        again = automation.reconcile(env=self.env())
        self.assertTrue(again["success"])
        self.assertFalse(again["applied"])
        self.assertEqual(self.nightlight.applications, [])
        self.assertEqual(self.nightlight.naturals, 0)
        self.assertEqual(self.read_history(), [])
        self.assertEqual(self.read_state(), state_utils.DEFAULT_STATE)

    def test_reconcile_enforces_natural_while_snoozed_then_idempotent(self):
        self.initial_state(snooze_until=2800.0)
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertTrue(result["applied"])
        self.assertTrue(result["snoozed"])
        self.assertEqual(self.nightlight.naturals, 1)
        state = self.read_state()
        self.assertEqual(state["snooze_until"], 2800.0)
        self.assertEqual(state["last_applied"]["origin"], "snooze")
        self.assertEqual(state["last_applied"]["operation"], "reconcile_snooze")
        records = self.read_history()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["operation"], "reconcile_snooze")
        self.assertEqual(records[0]["origin"], "snooze")

        # Already natural: enforcement is a no-op.
        again = automation.reconcile(env=self.env())
        self.assertTrue(again["success"])
        self.assertFalse(again["applied"])
        self.assertEqual(self.nightlight.naturals, 1)
        self.assertEqual(self.read_history(), records)

    def test_reconcile_snoozed_apply_failure_keeps_snooze_honestly(self):
        self.initial_state(snooze_until=2800.0)
        self.nightlight.fail_first = 1
        result = automation.reconcile(env=self.env())
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "apply_failed")
        self.assertEqual(self.read_state()["snooze_until"], 2800.0)
        # Periodic reconcile never spams history.
        self.assertEqual(self.read_history(), [])

    def test_reconcile_snoozed_ignores_schedule_disabled(self):
        self.initial_state(snooze_until=2800.0, schedule_enabled=False)
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"])
        self.assertTrue(result["applied"])
        self.assertEqual(self.nightlight.naturals, 1)

    def test_reconcile_expired_clears_snooze_and_applies_profile_once(self):
        self.initial_state(
            snooze_until=900.0, last_applied=None, transition_seconds=30
        )
        self.profile = {"available": True, "kind": "temperature", "temperature": 4000}
        first = automation.reconcile(env=self.env())
        self.assertTrue(first["success"], first)
        self.assertTrue(first["applied"])
        self.assertFalse(first["snoozed"])
        # Snooze was cleared and stored.
        state = self.read_state()
        self.assertIsNone(state["snooze_until"])
        self.assertEqual(state["last_applied"]["origin"], "automatic")
        self.assertEqual(state["last_applied"]["operation"], "reconcile_schedule")
        self.assertEqual(
            state["last_applied"]["values"], {"temperature": 4000, "gamma": 90}
        )
        # Configured transition performed exactly one full ramp.
        self.assertEqual(len(self.nightlight.applications), 30)
        self.assertEqual(self.nightlight.applications[-1], (4000, 90))

        second = automation.reconcile(env=self.env())
        self.assertTrue(second["success"])
        self.assertFalse(second["applied"])
        self.assertEqual(len(self.nightlight.applications), 30)
        self.assertEqual(len(self.read_history()), 1)

    def test_reconcile_expired_applies_profile_once_even_without_drift(self):
        self.initial_state(snooze_until=900.0)
        self.profile = {"available": True, "kind": "temperature", "temperature": 3500}
        first = automation.reconcile(env=self.env())
        self.assertTrue(first["success"], first)
        self.assertTrue(first["applied"])
        self.assertEqual(self.nightlight.applications, [(3500, 90)])
        self.assertIsNone(self.read_state()["snooze_until"])
        second = automation.reconcile(env=self.env())
        self.assertFalse(second["applied"])
        self.assertEqual(len(self.nightlight.applications), 1)

    def test_reconcile_expired_schedule_disabled_clears_without_apply(self):
        self.initial_state(snooze_until=900.0, schedule_enabled=False)
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertFalse(result["applied"])
        self.assertIsNone(self.read_state()["snooze_until"])
        self.assertEqual(self.read_history(), [])

    def test_reconcile_expired_profile_unavailable_is_honest(self):
        self.initial_state(snooze_until=900.0)
        self.profile = {"available": False, "error": "no schedule"}
        result = automation.reconcile(env=self.env())
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "schedule_unavailable")
        self.assertIsNone(self.read_state()["snooze_until"])
        self.assertEqual(self.read_history(), [])

    def test_reconcile_period_drift_ramps_with_configured_transition(self):
        self.initial_state(transition_seconds=40)
        self.profile = {"available": True, "kind": "temperature", "temperature": 4000}
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertTrue(result["applied"])
        applications = self.nightlight.applications
        self.assertEqual(len(applications), 40)
        self.assertEqual(applications[-1], (4000, 90))
        temperatures = [values[0] for values in applications]
        self.assertEqual(temperatures, sorted(temperatures))
        state = self.read_state()
        self.assertEqual(state["last_applied"]["origin"], "automatic")
        self.assertEqual(state["last_applied"]["operation"], "reconcile_schedule")
        self.assertEqual(len(self.read_history()), 1)

        again = automation.reconcile(env=self.env())
        self.assertFalse(again["applied"])
        self.assertEqual(len(self.nightlight.applications), 40)

    def test_reconcile_period_identity_drift_applies_natural(self):
        self.profile = {"available": True, "kind": "identity"}
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertTrue(result["applied"])
        self.assertEqual(self.nightlight.naturals, 1)
        state = self.read_state()
        self.assertEqual(state["last_applied"]["origin"], "automatic")
        self.assertEqual(state["last_applied"]["operation"], "reconcile_schedule")

    def test_reconcile_period_identity_already_active_is_noop(self):
        self.nightlight = FakeNightlight(temperature=6000, gamma=90, identity=True)
        self.profile = {"available": True, "kind": "identity"}
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"])
        self.assertFalse(result["applied"])
        self.assertEqual(self.nightlight.naturals, 0)
        self.assertEqual(self.read_history(), [])

    def test_reconcile_period_temp_drift_when_natural_identity_active(self):
        self.nightlight = FakeNightlight(temperature=6000, gamma=90, identity=True)
        self.profile = {"available": True, "kind": "temperature", "temperature": 4000}
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertTrue(result["applied"])
        self.assertEqual(self.nightlight.applications, [(4000, 90)])
        self.assertFalse(self.nightlight.identity)

    def test_reconcile_period_temperature_within_tolerance_is_noop(self):
        self.nightlight = FakeNightlight(temperature=4030, gamma=90)
        self.profile = {"available": True, "kind": "temperature", "temperature": 4000}
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"])
        self.assertFalse(result["applied"])
        self.assertEqual(self.nightlight.applications, [])

    def test_reconcile_period_schedule_disabled_is_noop(self):
        self.initial_state(schedule_enabled=False)
        self.profile = {"available": True, "kind": "temperature", "temperature": 5000}
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"])
        self.assertFalse(result["applied"])
        self.assertEqual(self.nightlight.applications, [])
        self.assertEqual(self.read_history(), [])

    def test_reconcile_period_profile_unavailable_is_honest(self):
        self.profile = {"available": False, "error": "no schedule"}
        result = automation.reconcile(env=self.env())
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "schedule_unavailable")
        self.assertFalse(result["applied"])

    def test_reconcile_period_read_failure_is_honest(self):
        self.nightlight.read_error = True
        self.profile = {"available": True, "kind": "temperature", "temperature": 5000}
        result = automation.reconcile(env=self.env())
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "read_failed")
        self.assertEqual(self.nightlight.applications, [])

    def test_reconcile_provenance_failure_after_apply_is_honest(self):
        self.initial_state(transition_seconds=0)
        self.profile = {"available": True, "kind": "temperature", "temperature": 4000}

        def flaky_update(mutator):
            raise state_utils.StateError("io_error", "disk full")

        result = automation.reconcile(env=self.env(update_state=flaky_update))
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "state_failed")
        # Physical values were applied; the failure is reported honestly.
        self.assertEqual(self.nightlight.applications, [(4000, 90)])
        self.assertIsNone(self.read_state()["last_applied"])
        self.assertEqual(self.read_history(), [])

    def test_reconcile_state_failure_is_honest(self):
        self.initial_state(snooze_until=900.0)

        def failing_read():
            raise state_utils.StateError("io_error", "disk full")

        result = automation.reconcile(env=self.env(read_state=failing_read))
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "state_failed")

    # ------------------------------------------------------------------ \
    # manual override / manual intent

    def manual_override(self, **changes):
        record = {
            "at": ISO,
            "operation": "nightlight_toggle",
            "profile": {"kind": "identity"},
            "values": {"temperature": 4500, "gamma": 90},
        }
        record.update(changes)
        return record

    def test_commit_manual_apply_preserves_override_when_profile_unavailable(self):
        existing = self.manual_override()
        self.initial_state(manual_override=existing)
        self.profile = {"available": False, "error": "no schedule"}
        result = automation.commit_manual_apply(
            self.env(), "nightlight_temperature", {"temperature": 4000}
        )
        self.assertEqual(result["manual_override"], existing)
        self.assertEqual(self.read_state()["manual_override"], existing)
        self.assertEqual(self.read_state()["origin"], "manual")
        self.assertEqual(self.read_state()["last_applied"]["operation"], "nightlight_temperature")

    def test_identity_override_gets_deterministic_finite_boundary(self):
        self.profile = {"available": True, "kind": "identity"}
        automation.commit_manual_apply(
            self.env(), "nightlight_temperature", {"temperature": 4500, "gamma": 90}
        )
        override = self.read_state()["manual_override"]
        self.assertIn("until", override)
        expected = datetime.datetime.fromtimestamp(
            1000.0 + 24 * 60 * 60, tz=datetime.timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertEqual(override["until"], expected)

    def test_temperature_override_has_no_time_boundary(self):
        self.profile = {"available": True, "kind": "temperature", "temperature": 3500}
        automation.commit_manual_apply(
            self.env(), "nightlight_temperature", {"temperature": 4000, "gamma": 80}
        )
        override = self.read_state()["manual_override"]
        self.assertEqual(override["profile"], {"kind": "temperature", "temperature": 3500})
        self.assertNotIn("until", override)

    def test_reconcile_identity_override_honored_within_boundary(self):
        self.profile = {"available": True, "kind": "identity"}
        self.initial_state(
            manual_override=self.manual_override(until="1970-01-01T00:20:00Z")
        )
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertFalse(result["applied"])
        self.assertTrue(result["manual_override"])
        self.assertEqual(self.nightlight.naturals, 0)
        self.assertEqual(self.read_state()["manual_override"]["until"], "1970-01-01T00:20:00Z")

    def test_reconcile_identity_override_expired_at_boundary_resumes_schedule(self):
        self.profile = {"available": True, "kind": "identity"}
        self.nightlight = FakeNightlight(temperature=4500, gamma=90)
        self.initial_state(
            manual_override=self.manual_override(until="1970-01-01T00:00:00Z")
        )
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertTrue(result["applied"])
        self.assertEqual(self.nightlight.naturals, 1)
        self.assertIsNone(self.read_state()["manual_override"])
        self.assertEqual(self.read_state()["last_applied"]["origin"], "automatic")

    def test_reconcile_identity_expired_override_cleared_without_drift(self):
        self.profile = {"available": True, "kind": "identity"}
        self.nightlight = FakeNightlight(temperature=6000, gamma=90, identity=True)
        self.initial_state(
            manual_override=self.manual_override(until="1970-01-01T00:00:00Z")
        )
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertFalse(result["applied"])
        self.assertEqual(self.nightlight.naturals, 0)
        self.assertIsNone(self.read_state()["manual_override"])

    def test_legacy_identity_override_without_boundary_stays_active_while_fresh(self):
        self.profile = {"available": True, "kind": "identity"}
        self.initial_state(manual_override=self.manual_override())
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertFalse(result["applied"])
        self.assertTrue(result["manual_override"])
        self.assertEqual(self.read_state()["manual_override"], self.manual_override())

    def test_legacy_identity_override_older_than_fallback_boundary_expires(self):
        self.profile = {"available": True, "kind": "identity"}
        self.nightlight = FakeNightlight(temperature=4500, gamma=90)
        self.initial_state(
            manual_override=self.manual_override(at="1969-12-31T00:00:00Z")
        )
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertTrue(result["applied"])
        self.assertEqual(self.nightlight.naturals, 1)
        self.assertIsNone(self.read_state()["manual_override"])

    def test_reconcile_preserves_manual_override_within_same_period(self):
        self.profile = {"available": True, "kind": "identity"}
        self.initial_state(manual_override=self.manual_override())
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertFalse(result["applied"])
        self.assertTrue(result["manual_override"])
        self.assertEqual(self.nightlight.naturals, 0)
        self.assertEqual(self.nightlight.applications, [])
        self.assertEqual(self.read_history(), [])
        self.assertEqual(self.read_state()["manual_override"], self.manual_override())
        # Idempotent: a second reconcile in the same period still preserves it.
        again = automation.reconcile(env=self.env())
        self.assertTrue(again["success"], again)
        self.assertFalse(again["applied"])
        self.assertEqual(self.nightlight.naturals, 0)

    def test_reconcile_preserves_manual_override_within_temperature_period(self):
        self.profile = {"available": True, "kind": "temperature", "temperature": 3500}
        self.nightlight = FakeNightlight(temperature=4500, gamma=90)
        self.initial_state(
            manual_override=self.manual_override(
                profile={"kind": "temperature", "temperature": 3500}
            )
        )
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertFalse(result["applied"])
        self.assertEqual(self.nightlight.applications, [])
        self.assertEqual(self.read_history(), [])

    def test_reconcile_resumes_schedule_when_period_changes(self):
        self.nightlight = FakeNightlight(temperature=4500, gamma=90)
        self.initial_state(manual_override=self.manual_override(), transition_seconds=0)
        self.profile = {"available": True, "kind": "temperature", "temperature": 3500}
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertTrue(result["applied"])
        self.assertEqual(self.nightlight.applications, [(3500, 90)])
        state = self.read_state()
        self.assertIsNone(state["manual_override"])
        self.assertEqual(state["last_applied"]["origin"], "automatic")
        self.assertEqual(state["last_applied"]["operation"], "reconcile_schedule")
        # Once resumed, later reconciles enforce drift normally.
        again = automation.reconcile(env=self.env())
        self.assertTrue(again["success"], again)
        self.assertFalse(again["applied"])

    def test_reconcile_clears_stale_override_when_period_changed_without_drift(self):
        self.initial_state(manual_override=self.manual_override())
        self.nightlight = FakeNightlight(temperature=3500, gamma=90)
        self.profile = {"available": True, "kind": "temperature", "temperature": 3500}
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertFalse(result["applied"])
        self.assertIsNone(self.read_state()["manual_override"])
        self.assertEqual(self.read_history(), [])

    def test_reconcile_schedule_disabled_clears_stale_override(self):
        self.initial_state(
            schedule_enabled=False,
            manual_override=self.manual_override(
                profile={"kind": "temperature", "temperature": 3500}
            ),
        )
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertFalse(result["applied"])
        self.assertIsNone(self.read_state()["manual_override"])
        self.assertEqual(self.read_history(), [])

    def test_reconcile_schedule_disabled_state_failure_is_honest(self):
        self.initial_state(
            schedule_enabled=False,
            manual_override=self.manual_override(),
        )

        def failing_update(mutator):
            raise state_utils.StateError("io_error", "disk full")

        result = automation.reconcile(env=self.env(update_state=failing_update))
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "state_failed")

    def test_reconcile_reenable_after_disabled_clears_does_not_suppress_enforcement(self):
        self.nightlight = FakeNightlight(temperature=4500, gamma=90)
        self.profile = {"available": True, "kind": "temperature", "temperature": 3500}
        self.initial_state(
            schedule_enabled=False,
            manual_override=self.manual_override(
                profile={"kind": "temperature", "temperature": 3500}
            ),
            transition_seconds=0,
        )
        cleared = automation.reconcile(env=self.env())
        self.assertTrue(cleared["success"], cleared)
        self.assertIsNone(self.read_state()["manual_override"])
        state_utils.update_state(lambda current: {**current, "schedule_enabled": True})
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertTrue(result["applied"])
        self.assertEqual(self.nightlight.applications, [(3500, 90)])

    def test_snooze_set_clears_manual_override(self):
        self.initial_state(manual_override=self.manual_override())
        result = automation.snooze_set(30, env=self.env())
        self.assertTrue(result["success"], result)
        self.assertIsNone(self.read_state()["manual_override"])

    def test_reconcile_snoozed_clears_manual_override(self):
        self.initial_state(
            snooze_until=2800.0,
            manual_override=self.manual_override(),
        )
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertTrue(result["applied"])
        self.assertTrue(result["snoozed"])
        self.assertIsNone(self.read_state()["manual_override"])

    def test_reconcile_expiry_applies_profile_and_clears_override(self):
        self.initial_state(
            snooze_until=900.0,
            manual_override=self.manual_override(),
            transition_seconds=0,
        )
        self.profile = {"available": True, "kind": "temperature", "temperature": 4000}
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertTrue(result["applied"])
        self.assertIsNone(self.read_state()["manual_override"])

    def test_reconcile_snoozed_already_natural_clears_stale_override(self):
        self.nightlight = FakeNightlight(temperature=6000, gamma=90, identity=True)
        self.initial_state(
            snooze_until=2800.0,
            manual_override=self.manual_override(
                profile={"kind": "temperature", "temperature": 3500}
            ),
        )
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertFalse(result["applied"])
        self.assertTrue(result["snoozed"])
        self.assertEqual(self.nightlight.naturals, 0)
        self.assertIsNone(self.read_state()["manual_override"])

    def test_reconcile_expiry_schedule_disabled_clears_stale_override(self):
        self.initial_state(
            snooze_until=900.0,
            schedule_enabled=False,
            manual_override=self.manual_override(
                profile={"kind": "temperature", "temperature": 3500}
            ),
        )
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertFalse(result["applied"])
        self.assertIsNone(self.read_state()["snooze_until"])
        self.assertIsNone(self.read_state()["manual_override"])
        self.assertEqual(self.read_history(), [])

    def test_reconcile_expiry_cleared_override_does_not_suppress_later_enable(self):
        self.nightlight = FakeNightlight(temperature=4000, gamma=90)
        self.initial_state(
            snooze_until=900.0,
            schedule_enabled=False,
            manual_override=self.manual_override(
                profile={"kind": "temperature", "temperature": 3500}
            ),
        )
        first = automation.reconcile(env=self.env())
        self.assertTrue(first["success"], first)
        self.assertFalse(first["applied"])
        self.assertIsNone(self.read_state()["manual_override"])
        state_utils.update_state(lambda current: {**current, "schedule_enabled": True})
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertTrue(result["applied"])
        self.assertEqual(self.nightlight.applications, [(3500, 90)])

    # ------------------------------------------------------------------ \
    # fail-closed defaults

    def test_reconcile_period_drift_applies_scheduled_display_once(self):
        # Entering a period with scheduled display values applies brightness
        # and gamma alongside the profile temperature, records the period so
        # the next reconcile is a no-op, and reports both values.
        self.initial_state(
            schedule_display={"night": {"brightness": 60, "gamma": 80}},
            schedule_period_applied="night",
        )
        # A marker matching the period means the display values were already
        # applied: force a fresh entry the way saving the schedule does.
        state_utils.update_state(lambda current: dict(current, schedule_period_applied=None))
        self.nightlight.temperature = 5000
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertTrue(result["applied"])
        self.assertEqual(self.display.brightness_writes, [60])
        self.assertEqual(self.display.gamma_writes, [])
        self.assertEqual(self.nightlight.applications, [(3500, 80)])
        state = self.read_state()
        self.assertEqual(state["schedule_period_applied"], "night")
        self.assertEqual(
            state["last_applied"]["values"],
            {"temperature": 3500, "gamma": 80, "brightness": 60},
        )

        second = automation.reconcile(env=self.env())
        self.assertTrue(second["success"])
        self.assertFalse(second["applied"])
        self.assertEqual(self.display.brightness_writes, [60])
        self.assertEqual(self.display.gamma_writes, [])
        self.assertEqual(self.nightlight.applications, [(3500, 80)])

    def test_reconcile_display_only_when_temperature_already_matches(self):
        # A freshly saved schedule with unchanged temperatures must still
        # apply its display values: reconcile treats the cleared marker as a
        # pending period entry even without drift.
        self.nightlight.temperature = 3500
        self.initial_state(
            schedule_display={"night": {"brightness": 40, "gamma": 75}},
            schedule_period_applied=None,
        )
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertTrue(result["applied"])
        self.assertEqual(self.nightlight.applications, [])
        self.assertEqual(self.display.brightness_writes, [40])
        self.assertEqual(self.display.gamma_writes, [75])
        self.assertEqual(self.read_state()["schedule_period_applied"], "night")

    def test_reconcile_ignores_display_for_other_period(self):
        self.nightlight.temperature = 5000
        self.initial_state(
            schedule_display={"day": {"brightness": 70}},
            schedule_period_applied="day",
        )
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertTrue(result["applied"])  # temperature drift still applies
        self.assertEqual(self.display.brightness_writes, [])
        # No scheduled values exist for the night period, so the day marker
        # survives untouched.
        self.assertEqual(self.read_state()["schedule_period_applied"], "day")

    def test_reconcile_display_failure_is_honest_and_retried(self):
        self.initial_state(
            schedule_display={"night": {"brightness": 60}},
            schedule_period_applied=None,
        )
        self.display.fail_brightness = True
        result = automation.reconcile(env=self.env())
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "brightness_write_failed")
        self.assertIsNone(self.read_state()["schedule_period_applied"])

        self.display.fail_brightness = False
        retried = automation.reconcile(env=self.env())
        self.assertTrue(retried["success"], retried)
        self.assertEqual(self.display.brightness_writes, [60])
        self.assertEqual(self.read_state()["schedule_period_applied"], "night")

    def test_reconcile_identity_period_applies_scheduled_display(self):
        self.profile = {
            "available": True,
            "kind": "identity",
            "period": "day",
        }
        self.initial_state(
            schedule_display={"day": {"brightness": 90, "gamma": 95}},
            schedule_period_applied=None,
        )
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertTrue(result["applied"])
        self.assertEqual(self.nightlight.naturals, 1)
        self.assertEqual(self.display.brightness_writes, [90])
        self.assertEqual(self.display.gamma_writes, [95])
        self.assertEqual(self.read_state()["schedule_period_applied"], "day")

    def test_reconcile_expired_snooze_applies_scheduled_display(self):
        self.initial_state(
            snooze_until=self.clock.now() - 1,
            schedule_display={"night": {"brightness": 55, "gamma": 85}},
            schedule_period_applied=None,
        )
        result = automation.reconcile(env=self.env())
        self.assertTrue(result["success"], result)
        self.assertTrue(result["applied"])
        self.assertEqual(self.display.brightness_writes, [55])
        self.assertEqual(self.display.gamma_writes, [])
        self.assertEqual(self.nightlight.applications, [(3500, 85)])
        self.assertEqual(self.read_state()["schedule_period_applied"], "night")

    def test_defaults_fail_closed_without_live_commands(self):
        result = automation.snooze_set(30)
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "helper_unavailable")
        self.assertFalse(self.state_file().exists())

        reconcile = automation.reconcile()
        self.assertFalse(reconcile["success"])
        self.assertEqual(reconcile["error_code"], "helper_unavailable")

    def test_tests_do_not_create_python_bytecode(self):
        self.assertFalse(any(ROOT.rglob("__pycache__")))


    # ------------------------------------------------------------------ \
    # ramp robustness: latest-wins cancellation, deadline, dedup

    def test_reconcile_ramp_cancelled_midway_reports_cancelled_with_honest_prefix(self):
        self.initial_state(transition_seconds=4)
        self.nightlight.temperature = 5000
        self.token = FakeToken(self.clock, trip_monotonic=1.5)

        result = automation.reconcile(env=self.env())

        self.assertEqual(result["error_code"], "cancelled")
        self.assertFalse(result["applied"])
        applied_steps = result["applied_steps"]
        self.assertEqual(len(applied_steps), 2)
        self.assertEqual(self.nightlight.applications, applied_steps)
        self.assertEqual(result["temperature"], applied_steps[-1][0])
        self.assertEqual(result["gamma"], applied_steps[-1][1])
        # A cancelled ramp never reports the requested target as reached.
        self.assertNotEqual(result["temperature"], 3500)

    def test_reconcile_ramp_deadline_expiry_midway_reports_deadline_and_last_values(self):
        self.initial_state(transition_seconds=3)
        self.nightlight.temperature = 5000

        def jumping_sleep(seconds):
            self.clock.monotonic_value += 10.0

        result = automation.reconcile(env=self.env(sleep=jumping_sleep))

        self.assertEqual(result["error_code"], "deadline")
        self.assertFalse(result["applied"])
        self.assertEqual(len(result["applied_steps"]), 1)
        self.assertEqual(self.nightlight.applications, result["applied_steps"])

    def test_run_ramp_final_step_within_grace_still_delivers_exact_target(self):
        env = self.env()
        ok, detail = automation._run_ramp(
            env, {"temperature": 5000, "gamma": 90}, 4000, 80,
            2.0, None,
        )
        self.assertTrue(ok)
        self.assertEqual(detail[-1], (4000, 80))
        self.assertEqual(self.nightlight.applications[-1], (4000, 80))

    def test_run_ramp_final_step_beyond_grace_reports_deadline(self):
        def slow_sleep(seconds):
            self.clock.monotonic_value += 8.0

        env = self.env(sleep=slow_sleep)
        ok, detail = automation._run_ramp(
            env, {"temperature": 5000, "gamma": 90}, 4000, 80,
            2.0, None,
        )
        self.assertFalse(ok)
        self.assertEqual(detail["error_code"], "deadline")
        self.assertTrue(detail["applied_steps"])

    def test_run_ramp_skips_steps_whose_values_equal_previous(self):
        env = self.env()
        ok, detail = automation._run_ramp(
            env, {"temperature": 4000, "gamma": 80}, 4000, 80,
            3.0, None,
        )
        self.assertTrue(ok)
        self.assertEqual(detail, [(4000, 80)])
        self.assertEqual(self.nightlight.applications, [(4000, 80)])

    def test_reconcile_midramp_apply_failure_is_honest_with_last_good_values(self):
        self.initial_state(transition_seconds=3)
        self.nightlight.temperature = 5000
        self.nightlight.fail_at = 2

        result = automation.reconcile(env=self.env())

        self.assertEqual(result["error_code"], "apply_failed")
        self.assertFalse(result["applied"])
        self.assertEqual(len(result["applied_steps"]), 1)
        self.assertEqual(self.nightlight.applications, result["applied_steps"])
        self.assertEqual(result["temperature"], result["applied_steps"][-1][0])

    def test_snooze_bounds_inclusive_edges_are_accepted(self):
        for unit, value in (("seconds", 10), ("seconds", 86400), ("minutes", 1), ("minutes", 1440)):
            with self.subTest(unit=unit, value=value):
                setter = (
                    automation.snooze_set_seconds
                    if unit == "seconds"
                    else automation.snooze_set
                )
                result = setter(value, env=self.env())
                self.assertTrue(result["success"], result)
                self.assertTrue(result["snoozed"])

    def test_ramp_schedule_clamps_steps_and_lands_exactly_on_target(self):
        self.assertEqual(
            automation.ramp_schedule(5000, 90, 3000, 10, 0), [(3000, 10)]
        )
        flat = automation.ramp_schedule(4000, 80, 4000, 80, 3)
        self.assertEqual(flat, [(4000, 80)] * 3)
        descending = automation.ramp_schedule(6500, 100, 2500, 0, 7)
        temperatures = [pair[0] for pair in descending]
        gammas = [pair[1] for pair in descending]
        self.assertEqual(temperatures, sorted(temperatures, reverse=True))
        self.assertEqual(gammas, sorted(gammas, reverse=True))
        self.assertEqual(descending[-1], (2500, 0))


if __name__ == "__main__":
    unittest.main()
