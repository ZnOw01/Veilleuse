import json
import os
import stat
import subprocess
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


class StateUtilsTest(unittest.TestCase):
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

    def tearDown(self):
        self.environment.stop()
        self.tempdir.cleanup()

    def config_file(self):
        return self.config_home / "veilleuse" / "config.json"

    def state_file(self):
        return self.state_home / "veilleuse" / "state.json"

    def history_file(self):
        return self.state_home / "veilleuse" / "history.jsonl"

    def test_paths_are_absolute_and_relative_xdg_values_fall_back_to_home(self):
        with mock.patch.dict(
            os.environ,
            {"XDG_CONFIG_HOME": "relative-config", "XDG_STATE_HOME": "relative-state"},
            clear=False,
        ):
            self.assertEqual(
                state_utils.config_path(), self.home / ".config" / "veilleuse" / "config.json"
            )
            self.assertEqual(
                state_utils.state_path(), self.home / ".local" / "state" / "veilleuse" / "state.json"
            )
        self.assertTrue(state_utils.config_path().is_absolute())
        self.assertTrue(state_utils.state_path().is_absolute())

    def test_absent_documents_return_defaults_without_writing(self):
        self.assertEqual(state_utils.read_config(), state_utils.DEFAULT_CONFIG)
        self.assertEqual(state_utils.read_state(), state_utils.DEFAULT_STATE)
        self.assertEqual(state_utils.list_history(), [])
        self.assertFalse(self.config_file().exists())
        self.assertFalse(self.state_file().exists())
        self.assertFalse(self.history_file().exists())

    def test_config_and_state_are_strictly_validated_and_written_mode_0600(self):
        config = {
            "schema": 1,
            "presets": {
                "desk": {"temperature": 4200, "gamma": 85, "brightness": 70}
            },
            "default_preset": "desk",
        }
        state = {
            "schema": 1,
            "schedule_enabled": False,
            "snooze_until": 1700000000,
            "transition_seconds": 45,
            "origin": "manual",
            "last_applied": {
                "at": "2026-08-13T10:00:00Z",
                "origin": "manual",
                "operation": "preset_apply",
                "preset": "reading",
                "values": {"temperature": 3500, "gamma": 90, "brightness": 60},
            },
            "schedule_disabled": None,
        }
        state_utils.write_config(config)
        state_utils.write_state(state)
        self.assertEqual(state_utils.read_config(), config)
        self.assertEqual(state_utils.read_state(), state)
        self.assertEqual(stat.S_IMODE(self.config_file().stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.state_file().stat().st_mode), 0o600)

        invalid_config = dict(config, unexpected=True)
        with self.assertRaises(state_utils.StateError) as error:
            state_utils.write_config(invalid_config)
        self.assertEqual(error.exception.error_code, "invalid_config")

        invalid_state = dict(state, transition_seconds=1801)
        with self.assertRaises(state_utils.StateError) as error:
            state_utils.write_state(invalid_state)
        self.assertEqual(error.exception.error_code, "invalid_state")

    def test_last_applied_requires_strict_provenance_object(self):
        valid = {
            "at": "2026-08-13T10:00:00Z",
            "origin": "manual",
            "operation": "preset_apply",
            "preset": "reading",
            "values": {"temperature": 3500, "gamma": 90, "brightness": 60},
        }
        self.assertEqual(
            state_utils.write_state(dict(state_utils.DEFAULT_STATE, last_applied=valid))["last_applied"],
            valid,
        )

        invalid_values = [
            dict(valid, at="not-an-iso-time"),
            dict(valid, at="2026-99-99T99:99:99Z"),
            dict(valid, origin="external"),
            dict(valid, operation="preset apply"),
            dict(valid, operation=""),
            dict(valid, preset="Not a valid preset"),
            dict(valid, values={"temperature": 7000, "gamma": 90}),
            dict(valid, values={"temperature": 3500, "gamma": True}),
            dict(valid, values={"unknown": 1}),
            dict(valid, unexpected=True),
        ]
        for last_applied in invalid_values:
            with self.subTest(last_applied=last_applied):
                with self.assertRaises(state_utils.StateError) as error:
                    state_utils.write_state(
                        dict(state_utils.DEFAULT_STATE, last_applied=last_applied)
                    )
                self.assertEqual(error.exception.error_code, "invalid_state")

    def test_corrupt_json_has_stable_error_and_is_never_overwritten(self):
        path = self.config_file()
        path.parent.mkdir(parents=True)
        path.write_text('{"schema": 1,', encoding="utf-8")
        original = path.read_bytes()
        with self.assertRaises(state_utils.StateError) as error:
            state_utils.read_config()
        self.assertEqual(error.exception.error_code, "invalid_json")
        with self.assertRaises(state_utils.StateError) as error:
            state_utils.write_config(state_utils.DEFAULT_CONFIG)
        self.assertEqual(error.exception.error_code, "invalid_json")
        self.assertEqual(path.read_bytes(), original)

    def test_schema_is_required_and_malformed_documents_are_never_overwritten(self):
        for path, reader, writer, default, error_code in (
            (
                self.config_file(),
                state_utils.read_config,
                state_utils.write_config,
                state_utils.DEFAULT_CONFIG,
                "invalid_schema",
            ),
            (
                self.state_file(),
                state_utils.read_state,
                state_utils.write_state,
                state_utils.DEFAULT_STATE,
                "invalid_schema",
            ),
        ):
            with self.subTest(path=path):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"{}")
                original = path.read_bytes()
                with self.assertRaises(state_utils.StateError) as error:
                    reader()
                self.assertEqual(error.exception.error_code, error_code)
                with self.assertRaises(state_utils.StateError) as error:
                    writer(default)
                self.assertEqual(error.exception.error_code, error_code)
                self.assertEqual(path.read_bytes(), original)

    def test_schema_zero_is_migrated_only_when_explicitly_written(self):
        config = {
            "schema": 0,
            "presets": {"desk": {"temperature": 4200, "gamma": 85}},
            "default_preset": "desk",
        }
        state = {
            "schema": 0,
            "schedule_enabled": True,
            "snooze_until": None,
            "transition_seconds": 0,
            "origin": "unknown",
            "last_applied": None,
            "schedule_disabled": None,
        }
        self.config_file().parent.mkdir(parents=True)
        self.state_file().parent.mkdir(parents=True)
        self.config_file().write_text(json.dumps(config), encoding="utf-8")
        self.state_file().write_text(json.dumps(state), encoding="utf-8")

        loaded_config = state_utils.read_config()
        loaded_state = state_utils.read_state()
        self.assertEqual(loaded_config["schema"], 1)
        self.assertEqual(loaded_state["schema"], 1)
        self.assertEqual(json.loads(self.config_file().read_text()), config)
        self.assertEqual(json.loads(self.state_file().read_text()), state)

        state_utils.write_config(loaded_config)
        state_utils.write_state(loaded_state)
        self.assertEqual(json.loads(self.config_file().read_text())["schema"], 1)
        self.assertEqual(json.loads(self.state_file().read_text())["schema"], 1)

    def test_symlink_file_and_parent_fail_closed(self):
        real = Path(self.tempdir.name) / "real"
        real.mkdir()
        self.config_home.symlink_to(real, target_is_directory=True)
        with self.assertRaises(state_utils.StateError) as error:
            state_utils.read_config()
        self.assertEqual(error.exception.error_code, "unsafe_path")

        self.config_home.unlink()
        self.config_file().parent.mkdir(parents=True)
        target = Path(self.tempdir.name) / "target.json"
        target.write_text(json.dumps(state_utils.DEFAULT_CONFIG), encoding="utf-8")
        self.config_file().symlink_to(target)
        with self.assertRaises(state_utils.StateError) as error:
            state_utils.read_config()
        self.assertEqual(error.exception.error_code, "unsafe_path")

    def test_symlink_lock_fails_closed(self):
        lock = self.state_file().with_name(".state.json.lock")
        lock.parent.mkdir(parents=True)
        target = Path(self.tempdir.name) / "lock-target"
        target.write_bytes(b"do not touch")
        lock.symlink_to(target)

        with self.assertRaises(state_utils.StateError) as error:
            state_utils.write_state(state_utils.DEFAULT_STATE)
        self.assertEqual(error.exception.error_code, "unsafe_path")
        self.assertEqual(target.read_bytes(), b"do not touch")

    def test_nonregular_lock_fails_closed_after_fstat(self):
        lock = self.state_file().with_name(".state.json.lock")
        lock.parent.mkdir(parents=True)
        os.mkfifo(lock, 0o600)

        with self.assertRaises(state_utils.StateError) as error:
            state_utils.write_state(state_utils.DEFAULT_STATE)
        self.assertEqual(error.exception.error_code, "unsafe_path")

    def test_destination_is_rechecked_after_pre_replace_race(self):
        path = self.state_file()
        outside = Path(self.tempdir.name) / "outside-state.json"
        outside.write_bytes(b"outside bytes")
        state_utils.write_state(state_utils.DEFAULT_STATE)
        original = path.read_bytes()

        def replace_with_symlink(destination):
            destination.unlink()
            destination.symlink_to(outside)

        with mock.patch.object(state_utils, "_before_replace", side_effect=replace_with_symlink):
            with self.assertRaises(state_utils.StateError) as error:
                state_utils.write_state(state_utils.DEFAULT_STATE)
        self.assertEqual(error.exception.error_code, "unsafe_path")
        self.assertTrue(path.is_symlink())
        self.assertEqual(outside.read_bytes(), b"outside bytes")
        self.assertEqual(path.read_bytes(), b"outside bytes")
        self.assertNotEqual(path, path.resolve())
        self.assertNotEqual(original, outside.read_bytes())

    def history_record(self, number):
        return {
            "time": f"2026-08-13T10:{number:02d}:00Z",
            "operation": "preset",
            "origin": "preset",
            "preset": "reading",
            "temperature": 3500,
            "gamma": 85,
            "brightness": 60,
            "monitor": "focused",
            "success": True,
        }

    def test_history_is_validated_bounded_and_clearable(self):
        for number in range(55):
            state_utils.append_history(self.history_record(number))
        records = state_utils.list_history()
        self.assertEqual(len(records), 50)
        self.assertEqual(records[0]["time"], "2026-08-13T10:05:00Z")
        self.assertEqual(records[-1]["time"], "2026-08-13T10:54:00Z")
        self.assertEqual(stat.S_IMODE(self.history_file().stat().st_mode), 0o600)

        with self.assertRaises(state_utils.StateError) as error:
            state_utils.append_history({"operation": "preset"})
        self.assertEqual(error.exception.error_code, "invalid_history")
        before = self.history_file().read_bytes()
        with self.assertRaises(state_utils.StateError) as error:
            state_utils.append_history(dict(self.history_record(99), unexpected=True))
        self.assertEqual(error.exception.error_code, "invalid_history")
        self.assertEqual(self.history_file().read_bytes(), before)

        self.assertEqual(state_utils.clear_history(), [])
        self.assertEqual(state_utils.list_history(), [])
        self.assertTrue(self.history_file().exists())

    def test_concurrent_history_appends_preserve_all_latest_records(self):
        worker = (
            "import sys; "
            "from scripts import state_utils; "
            "prefix, count = sys.argv[1], int(sys.argv[2]); "
            "[state_utils.append_history({'time': prefix + str(i), 'operation': 'manual', "
            "'origin': 'manual', 'success': True}) for i in range(count)]"
        )
        workers = []
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        for number in range(4):
            workers.append(
                subprocess.Popen(
                    [sys.executable, "-c", worker, f"worker-{number}-", "10"],
                    cwd=ROOT,
                    env=environment,
                )
            )
        self.assertTrue(all(process.wait(timeout=10) == 0 for process in workers))
        records = state_utils.list_history()
        self.assertEqual(len(records), 40)
        self.assertEqual(
            {record["time"] for record in records},
            {f"worker-{number}-{index}" for number in range(4) for index in range(10)},
        )

    def test_tests_do_not_create_python_bytecode(self):
        self.assertFalse(any(ROOT.rglob("__pycache__")))


if __name__ == "__main__":
    unittest.main()
