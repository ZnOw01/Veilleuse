#!/usr/bin/python3
"""Deterministic tests for the automation orchestration module.

All tests use injected fake clocks, sleepers, cancellation tokens,
applicators and (optionally) the real ``state_utils`` persistence backed by a
temporary XDG home.  No live shell commands or real time are ever used.
"""

import calendar
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


class FakeDST(datetime.tzinfo):
    """Pinned local timezone: CEST offsets in [2026-03-29 02:00, 2026-10-25 02:00)."""

    START = datetime.datetime(2026, 3, 29, 2, 0, 0)
    END = datetime.datetime(2026, 10, 25, 2, 0, 0)

    def _naive(self, dt):
        return dt.replace(tzinfo=None)

    def utcoffset(self, dt):
        naive = self._naive(dt)
        if naive is not None and self.START <= naive < self.END:
            return datetime.timedelta(hours=2)
        return datetime.timedelta(hours=1)

    def dst(self, dt):
        naive = self._naive(dt)
        if naive is not None and self.START <= naive < self.END:
            return datetime.timedelta(hours=1)
        return datetime.timedelta(0)

    def tzname(self, dt):
        return "CEST" if self.dst(dt) else "CET"


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
        self.profile = {"available": True, "kind": "temperature", "temperature": 3500}
        self.local_now = datetime.datetime(2026, 3, 28, 23, 30, tzinfo=FakeDST())

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
            "local_now": lambda: self.local_now,
            "monotonic": self.clock.monotonic,
            "sleep": self.clock.sleep,
            "read_state": state_utils.read_state,
            "update_state": state_utils.update_state,
            "append_history": state_utils.append_history,
            "read_nightlight": self.nightlight.read,
            "apply_values": self.nightlight.apply_values,
            "apply_natural": self.nightlight.apply_natural,
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

    def test_until_tomorrow_across_midnight(self):
        local_now = datetime.datetime(2026, 3, 28, 23, 30, tzinfo=FakeDST())
        target = automation.until_tomorrow_epoch(local_now)
        expected = calendar.timegm(datetime.datetime(2026, 3, 29).timetuple()) - 3600
        self.assertEqual(target, float(expected))
        self.assertEqual(
            target - local_now.timestamp(),
            30 * 60,
        )

    def test_until_tomorrow_after_midnight_is_full_next_day(self):
        local_now = datetime.datetime(2026, 3, 28, 0, 30, tzinfo=FakeDST())
        target = automation.until_tomorrow_epoch(local_now)
        expected = calendar.timegm(datetime.datetime(2026, 3, 29).timetuple()) - 3600
        self.assertEqual(target, float(expected))
        self.assertEqual(target - local_now.timestamp(), 23 * 3600 + 30 * 60)

    def test_until_tomorrow_across_dst_spring_forward(self):
        local_now = datetime.datetime(2026, 3, 29, 1, 30, tzinfo=FakeDST())
        target = automation.until_tomorrow_epoch(local_now)
        expected = calendar.timegm(datetime.datetime(2026, 3, 30).timetuple()) - 7200
        self.assertEqual(target, float(expected))
        # 21.5 real hours: the next local midnight is one hour further away.
        self.assertEqual(target - local_now.timestamp(), 21.5 * 3600)

    def test_until_tomorrow_across_dst_fall_back(self):
        local_now = datetime.datetime(2026, 10, 24, 23, 30, tzinfo=FakeDST())
        target = automation.until_tomorrow_epoch(local_now)
        expected = calendar.timegm(datetime.datetime(2026, 10, 25).timetuple()) - 7200
        self.assertEqual(target, float(expected))
        self.assertEqual(target - local_now.timestamp(), 30 * 60)

    def test_snooze_until_tomorrow_orchestration(self):
        result = automation.snooze_until_tomorrow(env=self.env())
        self.assertTrue(result["success"], result)
        expected = automation.until_tomorrow_epoch(self.local_now)
        self.assertEqual(result["snooze_until"], expected)
        state = self.read_state()
        self.assertEqual(state["snooze_until"], expected)
        self.assertEqual(state["last_applied"]["operation"], "snooze_until_tomorrow")
        self.assertEqual(self.nightlight.naturals, 1)

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
        self.assertFalse(records[0].get("temperature"))

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

    # ------------------------------------------------------------------ \
    # transition

    def test_transition_immediate_mode_zero_seconds_applies_exact_once(self):
        result = automation.transition(4000, 80, 0, env=self.env())
        self.assertTrue(result["success"], result)
        self.assertTrue(result["applied"])
        self.assertEqual(result["temperature"], 4000)
        self.assertEqual(result["gamma"], 80)
        self.assertEqual(self.nightlight.applications, [(4000, 80)])
        self.assertEqual(self.clock.sleeps, [])
        self.assertEqual(self.nightlight.naturals, 0)

    def test_transition_validates_ranges(self):
        for target in (
            (2499, 80, 10),
            (6501, 80, 10),
            (4000, -1, 10),
            (4000, 101, 10),
            (4000, 80, -1),
            (4000, 80, 1801),
            (4000, 80, 1.5),
            (True, 80, 10),
        ):
            result = automation.transition(*target, env=self.env())
            self.assertFalse(result["success"], target)
            self.assertEqual(result["error_code"], "invalid_argument", target)
        self.assertEqual(self.nightlight.applications, [])

    def test_transition_ramp_is_monotonic_bounded_and_ends_exact(self):
        result = automation.transition(4000, 80, 60, env=self.env())
        self.assertTrue(result["success"], result)
        applications = self.nightlight.applications
        self.assertEqual(len(applications), 60)
        temperatures = [values[0] for values in applications]
        gammas = [values[1] for values in applications]
        # Monotonic toward the targets, never overshooting.
        self.assertEqual(temperatures, sorted(temperatures))
        self.assertEqual(gammas, sorted(gammas, reverse=True))
        for value in temperatures:
            self.assertTrue(3500 <= value <= 4000, value)
        for value in gammas:
            self.assertTrue(80 <= value <= 90, value)
        # Per-step deltas are bounded by the ramp geometry (+1 rounding).
        for previous, current in zip(temperatures, temperatures[1:]):
            self.assertLessEqual(current - previous, 9)
        # Final step is exactly the requested target.
        self.assertEqual(applications[-1], (4000, 80))
        # One bounded sleep per intermediate step; deadline never exceeded.
        self.assertEqual(len(self.clock.sleeps), 59)
        self.assertLessEqual(self.clock.monotonic(), 60)
        self.assertEqual(result["steps"], 60)
        self.assertEqual(result["temperature"], 4000)
        self.assertEqual(result["gamma"], 80)

    def test_transition_ramp_consolidates_steps_without_value_change(self):
        result = automation.transition(3500, 90, 30, env=self.env())
        self.assertTrue(result["success"], result)
        self.assertEqual(self.nightlight.applications, [(3500, 90)])
        # Timing is still bounded and honored even without redundant IPC.
        self.assertEqual(len(self.clock.sleeps), 29)
        self.assertLessEqual(self.clock.monotonic(), 30)

    def test_transition_ramp_starting_from_natural_uses_identity_temperature(self):
        self.nightlight = FakeNightlight(temperature=3500, gamma=90, identity=True)
        result = automation.transition(6500, 100, 10, env=self.env())
        self.assertTrue(result["success"], result)
        applications = self.nightlight.applications
        self.assertEqual(applications[0], (6050, 91))
        self.assertEqual(applications[-1], (6500, 100))
        temperatures = [values[0] for values in applications]
        self.assertEqual(temperatures, sorted(temperatures))
        self.assertEqual(result["temperature"], 6500)

    def test_transition_cancellation_stops_with_honest_partial(self):
        token = FakeToken(clock=self.clock, trip_monotonic=5.0)
        result = automation.transition(
            4000, 80, 60, env=self.env(token=lambda: token)
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "cancelled")
        self.assertEqual(len(self.nightlight.applications), 5)
        applied = result["applied_steps"]
        self.assertEqual(applied, self.nightlight.applications)
        temperatures = [values[0] for values in applied]
        self.assertEqual(temperatures, sorted(temperatures))
        self.assertEqual(result["temperature"], applied[-1][0])
        self.assertEqual(result["gamma"], applied[-1][1])
        # Nothing was applied once the token was set.
        self.assertGreaterEqual(self.clock.monotonic(), 5.0)

    def test_transition_deadline_exceeded_stops_honest_partial(self):
        def lying_sleep(_seconds):
            self.clock.advance(4.0)

        result = automation.transition(
            4000, 80, 60, env=self.env(sleep=lying_sleep)
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "deadline")
        applied = result["applied_steps"]
        self.assertEqual(len(applied), 15)
        self.assertEqual(applied, self.nightlight.applications)
        self.assertEqual(result["temperature"], applied[-1][0])
        self.assertLessEqual(self.clock.monotonic(), 60)

    def test_transition_read_failure_fails_closed(self):
        self.nightlight.read_error = True
        result = automation.transition(4000, 80, 10, env=self.env())
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "read_failed")
        self.assertEqual(self.nightlight.applications, [])

    def test_transition_apply_failure_mid_ramp_is_honest(self):
        self.nightlight.fail_at = 2
        result = automation.transition(4000, 80, 60, env=self.env())
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "apply_failed")
        self.assertEqual(len(self.nightlight.applications), 1)
        self.assertEqual(result["applied_steps"], [(3508, 90)])

    def test_transition_commits_provenance_and_history_on_success(self):
        automation.transition(4000, 80, 0, env=self.env())
        state = self.read_state()
        last = state["last_applied"]
        self.assertEqual(last["origin"], "manual")
        self.assertEqual(last["operation"], "transition")
        self.assertEqual(last["at"], ISO)
        self.assertEqual(last["values"], {"temperature": 4000, "gamma": 80})
        records = self.read_history()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["operation"], "transition")
        self.assertEqual(records[0]["origin"], "manual")
        self.assertTrue(records[0]["success"])
        self.assertEqual(records[0]["temperature"], 4000)
        self.assertEqual(records[0]["gamma"], 80)

    def test_transition_failure_does_not_touch_provenance(self):
        self.nightlight.fail_at = 2
        automation.transition(4000, 80, 60, env=self.env())
        self.assertIsNone(self.read_state()["last_applied"])

    # ------------------------------------------------------------------ \
    # reconcile

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

    def test_transition_records_manual_override_for_identity_period(self):
        self.profile = {"available": True, "kind": "identity"}
        result = automation.transition(4500, 90, 0, env=self.env())
        self.assertTrue(result["success"], result)
        state = self.read_state()
        self.assertEqual(state["manual_override"]["profile"], {"kind": "identity"})
        self.assertEqual(state["manual_override"]["operation"], "transition")
        self.assertEqual(
            state["manual_override"]["values"], {"temperature": 4500, "gamma": 90}
        )
        self.assertIn("at", state["manual_override"])

    def test_transition_records_manual_override_for_temperature_period(self):
        self.profile = {"available": True, "kind": "temperature", "temperature": 3500}
        result = automation.transition(4000, 80, 0, env=self.env())
        self.assertTrue(result["success"], result)
        state = self.read_state()
        self.assertEqual(
            state["manual_override"]["profile"],
            {"kind": "temperature", "temperature": 3500},
        )

    def test_transition_with_unavailable_profile_records_no_override(self):
        self.profile = {"available": False, "error": "no schedule"}
        result = automation.transition(4000, 80, 0, env=self.env())
        self.assertTrue(result["success"], result)
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

    # ------------------------------------------------------------------ \
    # fail-closed defaults

    def test_defaults_fail_closed_without_live_commands(self):
        result = automation.snooze_set(30)
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "helper_unavailable")
        self.assertFalse(self.state_file().exists())

        transition = automation.transition(4000, 80, 10)
        self.assertFalse(transition["success"])
        self.assertEqual(transition["error_code"], "helper_unavailable")

        reconcile = automation.reconcile()
        self.assertFalse(reconcile["success"])
        self.assertEqual(reconcile["error_code"], "helper_unavailable")

    def test_tests_do_not_create_python_bytecode(self):
        self.assertFalse(any(ROOT.rglob("__pycache__")))


if __name__ == "__main__":
    unittest.main()
