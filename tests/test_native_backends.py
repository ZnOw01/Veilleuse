#!/usr/bin/python3
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import brightness_utils
import hyprsunset_backend as hb
import native_backends as nb


def cp(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(list(args), returncode, stdout, stderr)


def backlight_output(device, percent, current=None, maximum=1000):
    current = percent * 10 if current is None else current
    return f"{device},backlight,{current},{percent}%,{maximum}\n"


class SimulatedBrightness:
    """Deterministic fake omarchy-hw-display / brightnessctl / omarchy write."""

    def __init__(
        self,
        device="intel_backlight",
        percent=20,
        step=1,
        fail_display=False,
        read_returncode=0,
        read_stderr="",
        read_text_override=None,
        write_returncode=0,
        apply_write=True,
    ):
        self.device = device
        self.percent = percent
        self.step = step
        self.fail_display = fail_display
        self.read_returncode = read_returncode
        self.read_stderr = read_stderr
        self.read_text_override = read_text_override
        self.write_returncode = write_returncode
        self.apply_write = apply_write
        self.calls = []

    def __call__(self, args, *, timeout=None):
        tokens = list(args)
        self.calls.append((tokens, timeout))
        if tokens == list(nb.DISPLAY_COMMAND):
            if self.fail_display:
                return cp(tokens, 1, "", "no display")
            return cp(tokens, 0, self.device + "\n", "")
        if tokens[:2] == list(nb.READ_COMMAND_PREFIX) and tokens[-1] == "-m":
            if self.read_text_override is not None:
                return cp(tokens, self.read_returncode, self.read_text_override, self.read_stderr)
            if self.read_returncode != 0:
                return cp(tokens, self.read_returncode, "", self.read_stderr)
            return cp(tokens, 0, backlight_output(self.device, self.percent), "")
        if tokens[:2] == list(nb.WRITE_COMMAND):
            token = tokens[-1]
            if self.apply_write:
                if token == nb.STEP_UP:
                    self.percent = min(100, self.percent + self.step)
                elif token == nb.STEP_DOWN:
                    self.percent = max(1, self.percent - self.step)
            return cp(tokens, self.write_returncode, "", "" if self.write_returncode == 0 else "write denied")
        return cp(tokens, 1, "", "unexpected command")

    def write_calls(self):
        return [tokens for tokens, _timeout in self.calls if tokens[:2] == list(nb.WRITE_COMMAND)]

    def read_timeouts(self):
        return [
            timeout
            for tokens, timeout in self.calls
            if tokens[:2] == list(nb.READ_COMMAND_PREFIX)
        ]


class BrightnessReadTests(unittest.TestCase):
    def test_read_state_uses_omarchy_display_then_brightnessctl(self):
        sim = SimulatedBrightness(device="intel_backlight", percent=20)
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.read_state()

        self.assertTrue(state.available)
        self.assertEqual(state.percent, 20)
        self.assertEqual(state.monitor, "intel_backlight")
        read_call = next(
            tokens
            for tokens, _timeout in sim.calls
            if tokens[:2] == list(nb.READ_COMMAND_PREFIX)
        )
        self.assertEqual(read_call, ["brightnessctl", "-d", "intel_backlight", "-m"])

    def test_read_state_reports_missing_display_device(self):
        sim = SimulatedBrightness(fail_display=True)
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.read_state()

        self.assertFalse(state.available)
        self.assertIsNone(state.percent)
        self.assertTrue(state.error)

    def test_read_state_reports_brightnessctl_failure(self):
        sim = SimulatedBrightness(read_returncode=1, read_stderr="no such device")
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.read_state()

        self.assertFalse(state.available)
        self.assertEqual(state.monitor, "intel_backlight")
        self.assertIn("no such device", state.error)

    def test_read_state_rejects_unrecognized_output(self):
        sim = SimulatedBrightness(read_text_override="not a brightnessctl line")
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.read_state()

        self.assertFalse(state.available)
        self.assertIsNone(state.percent)
        self.assertTrue(state.error)

    def test_run_command_is_array_based_and_timeout_bounded(self):
        completed = cp(["a", "b"], 0, "", "")
        with patch.object(nb.subprocess, "run", return_value=completed) as run:
            result = nb.run_command(["a", "b"], timeout=0.5)

        args, kwargs = run.call_args
        self.assertEqual(args[0], ["a", "b"])
        self.assertNotIn("shell", kwargs)
        self.assertLessEqual(kwargs["timeout"], 0.5)
        self.assertEqual(result.returncode, 0)

    def test_brightness_reads_use_bounded_timeouts(self):
        sim = SimulatedBrightness(percent=35)
        backend = nb.OmarchyBrightnessBackend(runner=sim, timeout=0.25)

        backend.read_state()

        self.assertTrue(sim.read_timeouts())
        for timeout in sim.read_timeouts():
            self.assertLessEqual(timeout, 0.25)


class BrightnessStepTests(unittest.TestCase):
    def test_step_up_uses_one_percent_omarchy_write_and_readback(self):
        sim = SimulatedBrightness(percent=20)
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.step(1)

        self.assertTrue(state.available)
        self.assertEqual(state.percent, 21)
        writes = sim.write_calls()
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0], ["omarchy-brightness-display", "--no-osd", "1%+"])

    def test_step_down_uses_one_percent_omarchy_write_and_readback(self):
        sim = SimulatedBrightness(percent=20)
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.step(-1)

        self.assertEqual(state.percent, 19)
        self.assertEqual(sim.write_calls()[0], ["omarchy-brightness-display", "--no-osd", "1%-"])

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

    def test_step_rejects_jump_over_one_percent(self):
        sim = SimulatedBrightness(percent=20, step=5)
        backend = nb.OmarchyBrightnessBackend(runner=sim)

        state = backend.step(1)

        self.assertFalse(state.available)
        self.assertEqual(state.percent, 25)
        self.assertIn("1 %", state.error)


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
            self.assertEqual(int(tokens[-1][0]), 1)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)