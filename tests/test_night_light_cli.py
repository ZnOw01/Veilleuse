#!/usr/bin/python3
import importlib.util
import json
import subprocess
import sys
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

spec = importlib.util.spec_from_file_location(
    "night_light_cli", ROOT / "bin/night-light",
    loader=SourceFileLoader("night_light_cli", str(ROOT / "bin/night-light")),
)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
import hyprsunset_backend as backend


class CliTests(unittest.TestCase):
    def test_cli_temperature_uses_shared_backend(self):
        state = backend.BackendState(True, True, False, 3500, 100)
        result = subprocess.CompletedProcess([], 0, "", "")
        with (
            patch.object(cli, "ensure_backend", return_value=state),
            patch.object(cli, "set_temperature", return_value=result) as setter,
            patch.object(cli, "exclusive_lock"),
        ):
            self.assertEqual(cli.main(["--temperature", "2700"]), 0)
        setter.assert_called_once_with(2700)

    def test_invalid_combination_returns_two_without_ipc(self):
        with patch.object(cli, "set_temperature") as setter:
            self.assertEqual(cli.main(["--temperature", "2700", "--natural"]), 2)
        setter.assert_not_called()

    def test_cli_cycle_uses_observed_state_to_choose_next_mode(self):
        state = backend.BackendState(True, True, False, 2700, 100)
        result = subprocess.CompletedProcess([], 0, "", "")
        with (
            patch.object(cli, "ensure_backend", return_value=state),
            patch.object(cli, "set_temperature", return_value=result) as setter,
            patch.object(cli, "exclusive_lock"),
        ):
            self.assertEqual(cli.main(["--cycle"]), 0)
        setter.assert_called_once_with(3500)

    def test_status_is_json_and_reuses_the_held_lock(self):
        payload = {"text": "2700 K", "class": "active"}
        with patch.object(cli, "build_status_payload", return_value=payload) as build, \
             patch.object(cli, "exclusive_lock"), \
             patch("sys.stdout") as stdout:
            self.assertEqual(cli.main(["--status"]), 0)
            output = stdout.write.call_args_list
        build.assert_called_once_with(acquire_lock=False)
        self.assertTrue(any("2700 K" in call.args[0] for call in output))


if __name__ == "__main__":
    unittest.main(verbosity=2)
