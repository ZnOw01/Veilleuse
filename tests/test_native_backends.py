#!/usr/bin/python3
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import hyprsunset_backend as hb
import native_backends as nb


def cp(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(list(args), returncode, stdout, stderr)


def percent_output(percent):
    return f"{percent}\n"


class SimulatedBrightness:
    """Deterministic fake monitor selection / omarchy-brightness-display pair."""

    def __init__(
        self,
        device="intel_backlight",
        percent=20,
        step=1,
        fail_monitor=False,
        read_returncode=0,
        read_stderr="",
        read_text_override=None,
        write_returncode=0,
        apply_write=True,
        readback_failures=0,
    ):
        self.device = device
        self.percent = percent
        self.step = step
        self.fail_monitor = fail_monitor
        self.read_returncode = read_returncode
        self.read_stderr = read_stderr
        self.read_text_override = read_text_override
        self.write_returncode = write_returncode
        self.apply_write = apply_write
        self.remaining_read_failures = int(readback_failures)
        self.writes_done = 0
        self.calls = []

    def __call__(self, args, *, timeout=None, deadline=None):
        tokens = list(args)
        self.calls.append((tokens, timeout, deadline))
        if tokens == list(nb.MONITOR_COMMAND):
            if self.fail_monitor:
                return cp(tokens, 1, "", "no focused monitor")
            return cp(tokens, 0, self.device + "\n", "")
        if tokens[:3] == list(nb.BRIGHTNESS_COMMAND) and len(tokens) == 4:
            # Read path: `omarchy-brightness-display --no-osd --monitor NAME`.
            if self.writes_done and self.remaining_read_failures > 0:
                self.remaining_read_failures -= 1
                return cp(tokens, 1, "", "driver busy")
            if self.read_text_override is not None:
                return cp(tokens, self.read_returncode, self.read_text_override, self.read_stderr)
            if self.read_returncode != 0:
                return cp(tokens, self.read_returncode, "", self.read_stderr)
            return cp(tokens, 0, percent_output(self.percent), "")
        if tokens[:3] == list(nb.BRIGHTNESS_COMMAND) and len(tokens) == 5:
            # Write path: same command with a one-percent token appended.
            token = tokens[4]
            if self.apply_write:
                if token == nb.STEP_UP:
                    self.percent = min(100, self.percent + self.step)
                elif token == nb.STEP_DOWN:
                    self.percent = max(1, self.percent - self.step)
            self.writes_done += 1
            return cp(tokens, self.write_returncode, "", "" if self.write_returncode == 0 else "write denied")
        return cp(tokens, 1, "", "unexpected command")

    def write_calls(self):
        return [
            tokens
            for tokens, _timeout, _deadline in self.calls
            if tokens[:3] == list(nb.BRIGHTNESS_COMMAND) and len(tokens) == 5
        ]

    def read_calls(self):
        return [
            tokens
            for tokens, _timeout, _deadline in self.calls
            if tokens[:3] == list(nb.BRIGHTNESS_COMMAND) and len(tokens) == 4
        ]

    def read_timeouts(self):
        return [
            timeout
            for tokens, timeout, _deadline in self.calls
            if tokens[:3] == list(nb.BRIGHTNESS_COMMAND) and len(tokens) == 4
        ]


class CommandContractTests(unittest.TestCase):
    def test_command_contract_matches_omarchy_cli(self):
        self.assertEqual(nb.MONITOR_COMMAND, ("omarchy-hyprland-monitor-focused",))
        self.assertEqual(
            nb.BRIGHTNESS_COMMAND,
            ("omarchy-brightness-display", "--no-osd", "--monitor"),
        )
        self.assertEqual(nb.STEP_UP, "+1%")
        self.assertEqual(nb.STEP_DOWN, "1%-")
        self.assertEqual(nb.PERCENT_MIN, 1)

    def test_run_command_is_array_based_and_timeout_bounded(self):
        completed = cp(["a", "b"], 0, "", "")
        with patch.object(nb.subprocess, "run", return_value=completed) as run:
            result = nb.run_command(["a", "b"], timeout=0.5)

        args, kwargs = run.call_args
        self.assertEqual(args[0], ["a", "b"])
        self.assertNotIn("shell", kwargs)
        self.assertLessEqual(kwargs["timeout"], 0.5)
        self.assertEqual(result.returncode, 0)

    def test_run_command_uses_global_absolute_deadline(self):
        completed = cp(["a"], 0, "", "")
        with (
            patch.object(nb.time, "monotonic", return_value=100.0),
            patch.object(nb.subprocess, "run", return_value=completed) as run,
        ):
            nb.run_command(["a"], timeout=2.0, deadline=100.5)

        self.assertAlmostEqual(run.call_args.kwargs["timeout"], 0.5)

    def test_run_command_expired_deadline_fails_without_subprocess(self):
        with (
            patch.object(nb.time, "monotonic", return_value=101.0),
            patch.object(nb.subprocess, "run") as run,
        ):
            result = nb.run_command(["a"], timeout=2.0, deadline=100.5)

        self.assertEqual(result.returncode, nb.DEADLINE_EXIT_CODE)
        run.assert_not_called()

    def test_subprocess_timeout_becomes_deadline_failure(self):
        timeout = subprocess.TimeoutExpired(["hyprctl"], 0.2, output="partial")
        with patch.object(nb.subprocess, "run", side_effect=timeout) as run:
            result = nb.run_command(["hyprctl"], timeout=0.2)

        self.assertEqual(result.returncode, nb.DEADLINE_EXIT_CODE)
        self.assertEqual(result.stdout, "partial")
        self.assertLessEqual(run.call_args.kwargs["timeout"], 0.2)


class BrightnessReadTests(unittest.TestCase):
    def test_read_state_uses_focused_monitor_and_omarchy_read(self):
        sim = SimulatedBrightness(device="eDP-1", percent=20)
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.read_state()

        self.assertTrue(state.available)
        self.assertEqual(state.percent, 20)
        self.assertEqual(state.monitor, "eDP-1")
        self.assertEqual(
            sim.read_calls(),
            [["omarchy-brightness-display", "--no-osd", "--monitor", "eDP-1"]],
        )
        self.assertEqual(sim.calls[0][0], ["omarchy-hyprland-monitor-focused"])

    def test_read_state_reports_missing_focused_monitor(self):
        sim = SimulatedBrightness(fail_monitor=True)
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.read_state()

        self.assertFalse(state.available)
        self.assertIsNone(state.percent)
        self.assertTrue(state.error)

    def test_read_state_reports_omarchy_read_failure(self):
        sim = SimulatedBrightness(read_returncode=1, read_stderr="no such monitor")
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.read_state()

        self.assertFalse(state.available)
        self.assertEqual(state.monitor, "intel_backlight")
        self.assertIn("no such monitor", state.error)

    def test_read_state_fails_closed_on_non_numeric_readback(self):
        sim = SimulatedBrightness(read_text_override="not a number")
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.read_state()

        self.assertFalse(state.available)
        self.assertIsNone(state.percent)
        self.assertTrue(state.error)

    def test_read_state_fails_closed_on_empty_readback(self):
        sim = SimulatedBrightness(read_text_override="")
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.read_state()

        self.assertFalse(state.available)
        self.assertIsNone(state.percent)
        self.assertTrue(state.error)

    def test_read_state_clamps_to_minimum_one_percent(self):
        sim = SimulatedBrightness(read_text_override="0\n")
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.read_state()

        self.assertTrue(state.available)
        self.assertEqual(state.percent, 1)

    def test_brightness_reads_use_bounded_timeouts(self):
        sim = SimulatedBrightness(percent=35)
        backend = nb.OmarchyBrightnessBackend(runner=sim, timeout=0.25)

        backend.read_state()

        self.assertTrue(sim.read_timeouts())
        for timeout in sim.read_timeouts():
            self.assertLessEqual(timeout, 0.25)

    def test_read_state_uses_one_deadline_for_monitor_and_read(self):
        sim = SimulatedBrightness(percent=35)
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        backend.read_state()

        deadlines = [deadline for _tokens, _timeout, deadline in sim.calls]
        self.assertEqual(len(deadlines), 2)
        self.assertEqual(deadlines[0], deadlines[1])


class BrightnessStepTests(unittest.TestCase):
    def test_step_up_writes_plus_one_percent_with_monitor_and_reads_back(self):
        sim = SimulatedBrightness(percent=20)
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.step(1)

        self.assertTrue(state.available)
        self.assertEqual(state.percent, 21)
        self.assertEqual(
            sim.write_calls(),
            [["omarchy-brightness-display", "--no-osd", "--monitor", "intel_backlight", "+1%"]],
        )

    def test_step_down_writes_one_percent_minus_with_monitor_and_reads_back(self):
        sim = SimulatedBrightness(percent=20)
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.step(-1)

        self.assertEqual(state.percent, 19)
        self.assertEqual(
            sim.write_calls()[0],
            ["omarchy-brightness-display", "--no-osd", "--monitor", "intel_backlight", "1%-"],
        )

    def test_step_zero_does_not_write(self):
        sim = SimulatedBrightness(percent=40)
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.step(0)

        self.assertTrue(state.available)
        self.assertEqual(state.percent, 40)
        self.assertEqual(sim.write_calls(), [])

    def test_step_reports_write_failure(self):
        sim = SimulatedBrightness(percent=20, write_returncode=1, apply_write=False)
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.step(1)

        self.assertFalse(state.available)
        self.assertEqual(state.percent, 20)
        self.assertIn("write denied", state.error)

    def test_step_retries_transient_readback_race_without_extra_writes(self):
        sim = SimulatedBrightness(percent=20, readback_failures=1)
        backend = nb.OmarchyBrightnessBackend(runner=sim)
        with patch.object(nb.time, "sleep"):
            state = backend.step(1)

        self.assertTrue(state.available)
        self.assertEqual(state.percent, 21)
        self.assertEqual(len(sim.write_calls()), 1)
        # pre-write read + failed readback + successful readback
        self.assertEqual(len(sim.read_calls()), 3)

    def test_step_fails_closed_after_bounded_readback_retries(self):
        sim = SimulatedBrightness(percent=20, readback_failures=99)
        backend = nb.OmarchyBrightnessBackend(runner=sim)
        with patch.object(nb.time, "sleep"):
            state = backend.step(1)

        self.assertFalse(state.available)
        self.assertIsNone(state.percent)
        self.assertEqual(len(sim.write_calls()), 1)
        self.assertEqual(len(sim.read_calls()), 1 + nb.READBACK_RETRIES + 1)

    def test_step_rejects_readback_jump_over_one_percent_without_retrying(self):
        sim = SimulatedBrightness(percent=20, step=5)
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.step(1)

        self.assertFalse(state.available)
        self.assertEqual(state.percent, 25)
        self.assertIn("1 %", state.error)
        # A numeric but out-of-range readback must fail closed immediately.
        self.assertEqual(len(sim.read_calls()), 2)
        self.assertEqual(len(sim.write_calls()), 1)

    def test_step_down_at_one_percent_stays_at_one(self):
        sim = SimulatedBrightness(percent=1)
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.step(-1)

        self.assertTrue(state.available)
        self.assertEqual(state.percent, 1)
        self.assertEqual(
            sim.write_calls()[0],
            ["omarchy-brightness-display", "--no-osd", "--monitor", "intel_backlight", "1%-"],
        )


class BrightnessSetPercentTests(unittest.TestCase):
    def test_set_percent_converges_only_through_one_percent_steps(self):
        sim = SimulatedBrightness(percent=65)
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.set_percent(70)

        self.assertTrue(state.available)
        self.assertEqual(state.percent, 70)
        self.assertIsNone(state.error)
        writes = sim.write_calls()
        self.assertEqual(len(writes), 5)
        for tokens in writes:
            self.assertIn(tokens[-1], (nb.STEP_UP, nb.STEP_DOWN))

    def test_set_percent_noops_when_already_at_target(self):
        sim = SimulatedBrightness(percent=40)
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.set_percent(40)

        self.assertTrue(state.available)
        self.assertEqual(state.percent, 40)
        self.assertEqual(sim.write_calls(), [])

    def test_set_percent_is_bounded(self):
        sim = SimulatedBrightness(percent=65)
        backend = nb.OmarchyBrightnessBackend(runner=sim, max_steps=3)

        state = backend.set_percent(90)

        self.assertTrue(state.available)
        self.assertEqual(state.percent, 68)
        self.assertEqual(len(sim.write_calls()), 3)
        self.assertIn("No se pudo alcanzar", state.error)

    def test_set_percent_is_cancellable(self):
        sim = SimulatedBrightness(percent=65)
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        def should_stop():
            return len(sim.write_calls()) >= 2

        state = backend.set_percent(90, should_stop=should_stop)

        self.assertTrue(state.available)
        self.assertEqual(state.percent, 67)
        self.assertEqual(len(sim.write_calls()), 2)
        self.assertIn("cancelad", state.error)

    def test_set_percent_clamps_out_of_range_target(self):
        sim = SimulatedBrightness(percent=99)
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.set_percent(500)

        self.assertTrue(state.available)
        self.assertEqual(state.percent, 100)
        self.assertEqual(len(sim.write_calls()), 1)

    def test_set_percent_clamps_target_to_minimum_one_percent(self):
        sim = SimulatedBrightness(percent=5)
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.set_percent(0)

        self.assertTrue(state.available)
        self.assertEqual(state.percent, 1)
        writes = sim.write_calls()
        self.assertTrue(writes)
        for tokens in writes:
            self.assertEqual(tokens[-1], nb.STEP_DOWN)
            self.assertNotEqual(tokens[-1], "0%-")

    def test_set_percent_shares_one_deadline_across_steps(self):
        sim = SimulatedBrightness(percent=65)
        backend = nb.OmarchyBrightnessBackend(runner=sim, timeout=0.5)

        backend.set_percent(70)

        deadlines = {deadline for _tokens, _timeout, deadline in sim.calls}
        self.assertEqual(len(deadlines), 1)
        (shared,) = deadlines
        self.assertIsNotNone(shared)


class NightLightReadTests(unittest.TestCase):
    def test_read_state_maps_backend_readings(self):
        backend = nb.OmarchyNightLightBackend(
            read_state=lambda: hb.BackendState(True, True, False, 3500, 100)
        )

        state = backend.read_state()

        self.assertEqual(
            state,
            nb.NightLightState(
                available=True, enabled=True, temperature=3500, identity=False, gamma=100
            ),
        )

    def test_read_state_reports_unavailable_backend(self):
        backend = nb.OmarchyNightLightBackend(
            read_state=lambda: hb.BackendState(False, None, None, None, None)
        )

        state = backend.read_state()

        self.assertFalse(state.available)
        self.assertIsNone(state.enabled)
        self.assertIsNotNone(state.error)


class NightLightWriteTests(unittest.TestCase):
    def _recorder(self):
        calls = []

        def runner(args, *, timeout=None):
            calls.append(list(args))
            return cp(args, 0, "", "")

        return calls, runner

    def test_set_temperature_confirms_refreshes_and_reads_back(self):
        calls, runner = self._recorder()
        backend = nb.OmarchyNightLightBackend(
            set_temperature=lambda k: cp([], 0, "", ""),
            read_state=lambda: hb.BackendState(True, True, False, 3500, 100),
            runner=runner,
        )

        state = backend.set_temperature(3500)

        self.assertTrue(state.available)
        self.assertEqual(state.temperature, 3500)
        self.assertIsNone(state.error)
        self.assertEqual(calls, [list(nb.SHELL_REFRESH_COMMAND)])

    def test_shell_refresh_failure_does_not_invalidate_confirmed_write(self):
        def failing_runner(args, *, timeout=None):
            return cp(args, 1, "", "shell unreachable")

        backend = nb.OmarchyNightLightBackend(
            set_temperature=lambda k: cp([], 0, "", ""),
            read_state=lambda: hb.BackendState(True, True, False, 3500, 100),
            runner=failing_runner,
        )

        state = backend.set_temperature(3500)

        self.assertTrue(state.available)
        self.assertIsNone(state.error)

    def test_failed_temperature_write_reports_error_without_refresh(self):
        calls, runner = self._recorder()
        backend = nb.OmarchyNightLightBackend(
            set_temperature=lambda k: cp([], 1, "", "rejected"),
            read_state=lambda: hb.BackendState(True, True, False, 3500, 100),
            runner=runner,
        )

        state = backend.set_temperature(4000)

        self.assertTrue(state.available)
        self.assertIsNotNone(state.error)
        self.assertEqual(calls, [])

    def test_set_natural_uses_identity_readback_and_refreshes(self):
        calls, runner = self._recorder()
        backend = nb.OmarchyNightLightBackend(
            set_identity=lambda: cp([], 0, "", ""),
            read_state=lambda: hb.BackendState(True, False, True, 6000, 100),
            runner=runner,
        )

        state = backend.set_natural()

        self.assertTrue(state.available)
        self.assertIs(state.identity, True)
        self.assertIsNone(state.error)
        self.assertEqual(calls, [list(nb.SHELL_REFRESH_COMMAND)])

    def test_set_natural_failure_reports_error_without_refresh(self):
        calls, runner = self._recorder()
        backend = nb.OmarchyNightLightBackend(
            set_identity=lambda: cp([], 1, "", "rejected"),
            read_state=lambda: hb.BackendState(True, False, False, 6000, 100),
            runner=runner,
        )

        state = backend.set_natural()

        self.assertIsNotNone(state.error)
        self.assertEqual(calls, [])

    def test_set_gamma_refreshes_after_confirmed_write(self):
        calls, runner = self._recorder()
        backend = nb.OmarchyNightLightBackend(
            set_gamma=lambda p: cp([], 0, "", ""),
            read_state=lambda: hb.BackendState(True, True, False, 3500, 75),
            runner=runner,
        )

        state = backend.set_gamma(75)

        self.assertEqual(state.gamma, 75)
        self.assertIsNone(state.error)
        self.assertEqual(calls, [list(nb.SHELL_REFRESH_COMMAND)])

    def test_reset_gamma_refreshes_after_confirmed_write(self):
        calls, runner = self._recorder()
        backend = nb.OmarchyNightLightBackend(
            reset_gamma=lambda: cp([], 0, "", ""),
            read_state=lambda: hb.BackendState(True, False, False, 6000, 100),
            runner=runner,
        )

        state = backend.reset_gamma()

        self.assertTrue(state.available)
        self.assertEqual(state.gamma, 100)
        self.assertIsNone(state.error)
        self.assertEqual(calls, [list(nb.SHELL_REFRESH_COMMAND)])

    def test_writes_delegate_to_existing_hyprsunset_backend(self):
        calls, runner = self._recorder()
        with (
            patch.object(hb, "set_temperature", return_value=cp([], 0, "", "")) as set_temp,
            patch.object(hb, "read_state", return_value=hb.BackendState(True, True, False, 3500, 100)),
        ):
            backend = nb.OmarchyNightLightBackend(runner=runner)
            state = backend.set_temperature(3500)

        set_temp.assert_called_once_with(3500)
        self.assertTrue(state.available)
        self.assertIsNone(state.error)
        self.assertEqual(calls, [list(nb.SHELL_REFRESH_COMMAND)])

    def test_write_timeouts_are_bounded(self):
        recorded = []

        def recording_runner(args, *, timeout=None):
            recorded.append(timeout)
            return cp(args, 0, "", "")

        backend = nb.OmarchyNightLightBackend(
            set_temperature=lambda k: cp([], 0, "", ""),
            read_state=lambda: hb.BackendState(True, True, False, 3500, 100),
            runner=recording_runner,
            timeout=0.3,
        )

        backend.set_temperature(3500)

        self.assertEqual(recorded, [0.3])


class ServiceOwnershipTests(unittest.TestCase):
    def test_brightness_backend_never_manages_services(self):
        sim = SimulatedBrightness(percent=20)
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        backend.set_percent(22)

        for tokens, _timeout, _deadline in sim.calls:
            self.assertNotEqual(tokens[0], "systemctl")
            self.assertNotIn("systemctl", tokens)

    def test_nightlight_backend_only_refreshes_the_shell(self):
        calls, runner = self._recorder()
        backend = nb.OmarchyNightLightBackend(
            set_identity=lambda: cp([], 0, "", ""),
            set_gamma=lambda p: cp([], 0, "", ""),
            read_state=lambda: hb.BackendState(True, False, True, 6000, 100),
            runner=runner,
        )

        backend.set_natural()
        backend.set_gamma(75)
        backend.read_state()

        self.assertEqual(
            calls,
            [
                list(nb.SHELL_REFRESH_COMMAND),
                list(nb.SHELL_REFRESH_COMMAND),
            ],
        )
        for tokens in calls:
            self.assertNotEqual(tokens[0], "systemctl")

    def _recorder(self):
        calls = []

        def runner(args, *, timeout=None):
            calls.append(list(args))
            return cp(args, 0, "", "")

        return calls, runner


if __name__ == "__main__":
    unittest.main(verbosity=2)
