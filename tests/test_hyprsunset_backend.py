#!/usr/bin/python3
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
import hyprsunset_backend as backend


STATUS_PATH = ROOT / "bin/night-light-status"
status_spec = importlib.util.spec_from_file_location(
    "night_light_status",
    STATUS_PATH,
    loader=SourceFileLoader("night_light_status", str(STATUS_PATH)),
)
status = importlib.util.module_from_spec(status_spec)
status_spec.loader.exec_module(status)


class StateTests(unittest.TestCase):
    def test_identity_is_authoritative_for_natural_color(self):
        state = backend.state_from_readings(True, 3500)

        self.assertEqual(
            state,
            backend.BackendState(
                available=True,
                active=False,
                identity=True,
                temperature=3500,
            ),
        )

    def test_enabled_threshold_matches_omarchy_identity_temperature(self):
        self.assertEqual(backend.IDENTITY_TEMPERATURE, 6000)
        self.assertFalse(backend.state_from_readings(False, 6000).active)
        self.assertTrue(backend.state_from_readings(False, 5999).active)

    def test_identity_stays_authoritative_below_the_threshold(self):
        state = backend.state_from_readings(True, 3500)
        self.assertFalse(state.active)
        self.assertIs(state.identity, True)

    def test_state_is_unavailable_when_both_reads_fail(self):
        self.assertEqual(
            backend.state_from_readings(None, None),
            backend.BackendState(False, None, None, None),
        )

    def test_gamma_is_an_optional_observed_state_field(self):
        state = backend.state_from_readings(False, 3500, 75)
        self.assertEqual(state.gamma, 75)
        self.assertEqual(
            backend.BackendState(True, True, False, 3500),
            backend.BackendState(True, True, False, 3500, None),
        )

    def test_read_state_keeps_availability_when_gamma_read_fails(self):
        results = [
            subprocess.CompletedProcess([], 0, "false\n", ""),
            subprocess.CompletedProcess([], 0, "3500\n", ""),
            subprocess.CompletedProcess([], 1, "", "unsupported"),
        ]
        with patch.object(backend, "run_command", side_effect=results):
            state = backend.read_state(timeout=1.0)
        self.assertTrue(state.available)
        self.assertIsNone(state.gamma)

    def test_read_state_uses_one_deadline_for_both_reads(self):
        results = [
            subprocess.CompletedProcess([], 0, "false\n", ""),
            subprocess.CompletedProcess([], 0, "3500\n", ""),
        ]
        with patch.object(backend, "run_command", side_effect=results) as run:
            state = backend.read_state(timeout=1.0)

        self.assertTrue(state.available)
        self.assertTrue(state.active)
        self.assertFalse(state.identity)
        self.assertEqual(state.temperature, 3500)
        self.assertEqual(
            run.call_args_list[0].kwargs["deadline"],
            run.call_args_list[1].kwargs["deadline"],
        )


class GammaCommandTests(unittest.TestCase):
    def test_reads_gamma_percentage(self):
        result = subprocess.CompletedProcess([], 0, "75\n", "")
        with patch.object(backend, "run_command", return_value=result) as run:
            self.assertEqual(backend.read_gamma(), 75)
        self.assertEqual(run.call_args.args[0][-1], "gamma")

    def test_read_gamma_rejects_malformed_and_out_of_range_output(self):
        for output in ("", "75%\n", "-1\n", "201\n", "75\nextra"):
            with self.subTest(output=output):
                result = subprocess.CompletedProcess([], 0, output, "")
                with patch.object(backend, "run_command", return_value=result):
                    self.assertIsNone(backend.read_gamma())

    def test_read_gamma_honors_deadline(self):
        result = subprocess.CompletedProcess([], 0, "75\n", "")
        with patch.object(backend, "run_command", return_value=result) as run:
            backend.read_gamma(timeout=0.2, deadline=12.5)
        self.assertEqual(run.call_args.kwargs, {"timeout": 0.2, "deadline": 12.5})

    def test_set_gamma_requires_matching_readback(self):
        command = subprocess.CompletedProcess([], 0, "", "")
        with (
            patch.object(backend, "run_command", return_value=command) as run,
            patch.object(backend, "read_gamma", return_value=75),
        ):
            result = backend.set_gamma(75)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(run.call_args.args[0][-2:], ["gamma", "75"])

    def test_set_gamma_rejects_out_of_range_without_ipc(self):
        with patch.object(backend, "run_command") as run:
            with self.assertRaises(ValueError):
                backend.set_gamma(201)
        run.assert_not_called()

    def test_set_gamma_does_not_report_success_without_readback(self):
        command = subprocess.CompletedProcess([], 0, "", "")
        with (
            patch.object(backend.time, "monotonic", side_effect=[0.0, 0.0, 2.0]),
            patch.object(backend, "run_command", return_value=command),
            patch.object(backend, "read_gamma", return_value=73),
        ):
            result = backend.set_gamma(75)
        self.assertEqual(result.returncode, backend.READBACK_EXIT_CODE)

    def test_reset_gamma_uses_official_request_and_confirms_default(self):
        command = subprocess.CompletedProcess([], 0, "", "")
        with (
            patch.object(backend, "run_command", return_value=command) as run,
            patch.object(backend, "read_gamma", return_value=100),
        ):
            result = backend.reset_gamma()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(run.call_args.args[0][-2:], ["reset", "gamma"])


class CommandTests(unittest.TestCase):
    def test_subprocess_timeout_becomes_failure(self):
        timeout = subprocess.TimeoutExpired(["hyprctl"], 0.2, output="partial")
        with patch.object(backend.subprocess, "run", side_effect=timeout) as run:
            result = backend.run_command(["hyprctl"], timeout=0.2)

        self.assertEqual(result.returncode, backend.DEADLINE_EXIT_CODE)
        self.assertEqual(result.stdout, "partial")
        self.assertLessEqual(run.call_args.kwargs["timeout"], 0.2)

    def test_deadline_caps_child_timeout(self):
        completed = subprocess.CompletedProcess([], 0, "", "")
        with (
            patch.object(backend.time, "monotonic", return_value=10.0),
            patch.object(backend.subprocess, "run", return_value=completed) as run,
        ):
            backend.run_command(["hyprctl"], timeout=2.0, deadline=10.2)

        self.assertAlmostEqual(run.call_args.kwargs["timeout"], 0.2)

    def test_scheduled_day_temperature_is_accepted_and_confirmed(self):
        command = subprocess.CompletedProcess([], 0, "", "")
        matching = backend.BackendState(True, False, False, 6200)
        with (
            patch.object(backend, "run_command", return_value=command) as run,
            patch.object(backend, "read_state", return_value=matching),
        ):
            result = backend.set_temperature(6200)

        self.assertEqual(result.returncode, 0)
        run.assert_called_once()

    def test_temperature_does_not_report_success_without_matching_readback(self):
        command = subprocess.CompletedProcess([], 0, "", "")
        mismatch = backend.BackendState(True, True, False, 3500)
        with (
            patch.object(backend.time, "monotonic", side_effect=[0.0, 0.0, 2.0]),
            patch.object(backend, "run_command", return_value=command) as run,
            patch.object(backend, "read_state", return_value=mismatch),
        ):
            result = backend.set_temperature(4000)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.returncode, backend.READBACK_EXIT_CODE)
        run.assert_called_once()

    def test_acknowledged_request_polls_delayed_readback_without_resending(self):
        command = subprocess.CompletedProcess([], 0, "", "")
        readbacks = iter((False, False, True))

        def predicate(deadline):
            return next(readbacks)

        with (
            patch.object(backend.time, "monotonic", return_value=0.0),
            patch.object(backend.time, "sleep") as sleep,
            patch.object(backend, "run_command", return_value=command) as run,
        ):
            result = backend.request(["temperature", "4000"], predicate)

        self.assertIs(result, command)
        self.assertEqual(result.returncode, 0)
        run.assert_called_once()
        self.assertEqual(sleep.call_count, 2)

    def test_acknowledged_request_rejects_false_readback_at_deadline(self):
        command = subprocess.CompletedProcess([], 0, "", "")
        with (
            patch.object(backend.time, "monotonic", side_effect=[0.0, 0.0, 0.2, 0.4, 1.1]),
            patch.object(backend.time, "sleep") as sleep,
            patch.object(backend, "run_command", return_value=command) as run,
            patch.object(backend, "read_state", return_value=backend.BackendState(True, True, False, 3500)) as read_state,
        ):
            result = backend.set_temperature(4000)

        self.assertEqual(result.returncode, backend.READBACK_EXIT_CODE)
        self.assertIn("no coincide", result.stderr)
        run.assert_called_once()
        self.assertEqual(read_state.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_identity_does_not_report_success_without_true_readback(self):
        command = subprocess.CompletedProcess([], 0, "", "")
        with (
            patch.object(backend.time, "monotonic", side_effect=[0.0, 0.0, 2.0]),
            patch.object(backend, "run_command", return_value=command),
            patch.object(backend, "read_identity", return_value=False),
        ):
            result = backend.set_identity()

        self.assertNotEqual(result.returncode, 0)

    def test_matching_identity_readback_reports_success(self):
        command = subprocess.CompletedProcess([], 0, "", "")
        with (
            patch.object(backend.time, "monotonic", side_effect=[0.0, 0.0]),
            patch.object(backend, "run_command", return_value=command),
            patch.object(backend, "read_identity", return_value=True),
        ):
            result = backend.set_identity()

        self.assertEqual(result.returncode, 0)


class SettingsTests(unittest.TestCase):
    def test_settings_requires_a_json_object_and_safe_temperature_range(self):
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as directory:
            path = Path(directory) / "settings.json"
            for content, expected in (
                ("[]", backend.DEFAULT_TEMPERATURE),
                ("null", backend.DEFAULT_TEMPERATURE),
                ("not json", backend.DEFAULT_TEMPERATURE),
                ('{"temperature": "invalid"}', backend.DEFAULT_TEMPERATURE),
                ('{"temperature": 100}', backend.NIGHT_TEMP_MIN),
                ('{"temperature": 9999}', backend.NIGHT_TEMP_MAX),
            ):
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    self.assertEqual(backend.load_temperature(path), expected)


class ServiceTests(unittest.TestCase):
    def test_reads_enabled_runtime_and_active_service_state(self):
        results = [
            subprocess.CompletedProcess([], 0, "enabled-runtime\n", ""),
            subprocess.CompletedProcess([], 0, "active\n", ""),
        ]
        with patch.object(backend, "run_command", side_effect=results) as run:
            service = backend.read_service_state()

        self.assertEqual(service, backend.ServiceState(enabled=True, active=True))
        self.assertEqual(run.call_args_list[0].args[0][-2:], ["is-enabled", "hyprsunset.service"])
        self.assertEqual(run.call_args_list[1].args[0][-2:], ["is-active", "hyprsunset.service"])

    def test_missing_systemd_is_optional(self):
        missing = subprocess.CompletedProcess([], 127, "", "not found")
        with patch.object(backend, "run_command", return_value=missing):
            service = backend.read_service_state()

        self.assertEqual(service, backend.ServiceState(enabled=None, active=None))


class WaybarPayloadTests(unittest.TestCase):
    def setUp(self):
        self.service = backend.ServiceState(enabled=True, active=True)

    def test_waybar_text_describes_temperature_natural_off_and_unavailable(self):
        cases = (
            (backend.BackendState(True, True, False, 2700, 100), "2700 K"),
            (backend.BackendState(True, False, True, 6000, 100), "Natural"),
            (backend.BackendState(True, False, False, 6000, 100), "Off"),
            (backend.BackendState(False, None, None, None, None), "No disponible"),
        )
        for state, expected in cases:
            with self.subTest(expected=expected):
                payload = status.build_payload(state, self.service, "15:30", "06:00")
                self.assertEqual(payload["text"], expected)

    def test_status_payload_serializes_state_read_under_lock(self):
        state = backend.BackendState(True, True, False, 3500, 100)
        with (
            patch.object(status, "exclusive_lock") as lock,
            patch.object(status, "read_state", return_value=state),
            patch.object(status, "read_service_state", return_value=self.service),
            patch.object(status, "read_schedule", return_value=("15:30", "06:00")),
        ):
            payload = status.build_status_payload()
        lock.assert_called_once_with(status.STATE_LOCK)
        self.assertEqual(payload["text"], "3500 K")

    def test_waybar_distinguishes_active_inactive_and_unavailable(self):
        cases = (
            (backend.BackendState(True, True, False, 3500), "active"),
            (backend.BackendState(True, False, True, 6000), "inactive"),
            (backend.BackendState(False, None, None, None), "unavailable"),
        )
        for state, expected in cases:
            with self.subTest(expected=expected):
                payload = status.build_payload(state, self.service, "15:30", "06:00")
                self.assertEqual(payload["class"], expected)
                self.assertEqual(payload["alt"], expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
