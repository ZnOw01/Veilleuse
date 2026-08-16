import contextlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
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

    def test_config_is_preset_free_and_defaults_to_schema_only(self):
        # Presets are gone from the product: the config document carries
        # nothing but its schema, and no preset surface exists in the module.
        self.assertEqual(state_utils.DEFAULT_CONFIG, {"schema": 1})
        self.assertFalse(hasattr(state_utils, "BUILTIN_PRESETS"))
        state_utils.write_config({"schema": 1})
        self.assertEqual(state_utils.read_config(), {"schema": 1})

    def test_legacy_preset_documents_migrate_on_read(self):
        # A config written by a preset-era release must keep loading instead
        # of failing validation and bricking the plugin: the legacy preset
        # keys are dropped and the document normalizes to schema-only.
        legacy = {
            "schema": 1,
            "presets": {"desk": {"temperature": 4200, "gamma": 85}},
            "default_preset": "desk",
        }
        self.config_file().parent.mkdir(parents=True, exist_ok=True)
        self.config_file().write_text(json.dumps(legacy), encoding="utf-8")
        self.assertEqual(state_utils.read_config(), {"schema": 1})

        legacy_zero = {
            "schema": 0,
            "presets": {"desk": {"temperature": 4200, "gamma": 85}},
            "default_preset": "desk",
        }
        self.config_file().write_text(json.dumps(legacy_zero), encoding="utf-8")
        self.assertEqual(state_utils.read_config(), {"schema": 1})

    def test_schedule_display_and_applied_period_are_validated(self):
        display = {
            "day": {"brightness": 80, "gamma": 100},
            "night": {"brightness": 60, "gamma": 90},
        }
        normalized = state_utils.write_state(
            dict(
                state_utils.DEFAULT_STATE,
                schedule_display=display,
                schedule_period_applied="night",
            )
        )
        self.assertEqual(normalized["schedule_display"], display)
        self.assertEqual(normalized["schedule_period_applied"], "night")
        self.assertIsNone(state_utils.DEFAULT_STATE["schedule_display"])
        self.assertIsNone(state_utils.DEFAULT_STATE["schedule_period_applied"])

        invalid_states = [
            dict(state_utils.DEFAULT_STATE, schedule_display={"day": {}}),
            dict(state_utils.DEFAULT_STATE, schedule_display={"day": {"brightness": 0}}),
            dict(state_utils.DEFAULT_STATE, schedule_display={"day": {"brightness": 101}}),
            dict(state_utils.DEFAULT_STATE, schedule_display={"day": {"gamma": 101}}),
            dict(state_utils.DEFAULT_STATE, schedule_display={"dawn": {"brightness": 80}}),
            dict(state_utils.DEFAULT_STATE, schedule_display={"day": {"brightness": 80}, "night": None}),
            dict(state_utils.DEFAULT_STATE, schedule_display={"day": {"brightness": True}}),
            dict(state_utils.DEFAULT_STATE, schedule_display={"day": {"contrast": 5}}),
            dict(state_utils.DEFAULT_STATE, schedule_display="night"),
            dict(state_utils.DEFAULT_STATE, schedule_period_applied="dawn"),
            # The applied-period marker only makes sense while the matching
            # period carries display values; anything else is stale data.
            dict(state_utils.DEFAULT_STATE, schedule_period_applied="day"),
            dict(
                state_utils.DEFAULT_STATE,
                schedule_display={"night": {"brightness": 60}},
                schedule_period_applied="day",
            ),
        ]
        for candidate in invalid_states:
            with self.subTest(candidate=candidate):
                with self.assertRaises(state_utils.StateError) as error:
                    state_utils.write_state(candidate)
                self.assertEqual(error.exception.error_code, "invalid_state")

        # Applied period matching a period that does carry display values is
        # the one valid combination.
        partial = state_utils.write_state(
            dict(
                state_utils.DEFAULT_STATE,
                schedule_display={"night": {"brightness": 60}},
                schedule_period_applied="night",
            )
        )
        self.assertEqual(partial["schedule_period_applied"], "night")

    def test_config_and_state_are_strictly_validated_and_written_mode_0600(self):
        config = {"schema": 1}
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
            "manual_override": None,
            "schedule_display": {
                "day": {"brightness": 80, "gamma": 100},
                "night": {"brightness": 55, "gamma": 85},
            },
            "schedule_period_applied": "day",
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

    def test_manual_override_is_validated_and_defaults_to_none(self):
        valid = {
            "at": "2026-08-13T10:00:00Z",
            "operation": "nightlight_toggle",
            "profile": {"kind": "identity"},
            "values": {"temperature": 4500, "gamma": 90},
        }
        self.assertEqual(
            state_utils.write_state(
                dict(state_utils.DEFAULT_STATE, manual_override=valid)
            )["manual_override"],
            valid,
        )

        temp_valid = dict(valid, profile={"kind": "temperature", "temperature": 3500})
        self.assertEqual(
            state_utils.write_state(
                dict(state_utils.DEFAULT_STATE, manual_override=temp_valid)
            )["manual_override"],
            temp_valid,
        )

        minimal = {"at": "2026-08-13T10:00:00Z", "operation": "transition", "profile": {"kind": "identity"}}
        self.assertEqual(
            state_utils.write_state(
                dict(state_utils.DEFAULT_STATE, manual_override=minimal)
            )["manual_override"],
            minimal,
        )

        with_boundary = dict(
            minimal,
            until="2026-08-14T10:00:00Z",
        )
        self.assertEqual(
            state_utils.write_state(
                dict(state_utils.DEFAULT_STATE, manual_override=with_boundary)
            )["manual_override"],
            with_boundary,
        )

        invalid_values = [
            dict(valid, at="not-an-iso-time"),
            dict(valid, at="2026-99-99T99:99:99Z"),
            dict(valid, until="not-an-iso-time"),
            dict(valid, until="2026-99-99T99:99:99Z"),
            dict(valid, operation="nightlight toggle"),
            dict(valid, operation=""),
            dict(valid, profile={"kind": "identity", "temperature": 4000}),
            dict(valid, profile={"kind": "temperature", "temperature": 7000}),
            dict(valid, profile={"kind": "temperature"}),
            dict(valid, profile="identity"),
            dict(valid, values={"temperature": 7000, "gamma": 90}),
            dict(valid, unexpected=True),
        ]
        for manual_override in invalid_values:
            with self.subTest(manual_override=manual_override):
                with self.assertRaises(state_utils.StateError) as error:
                    state_utils.write_state(
                        dict(state_utils.DEFAULT_STATE, manual_override=manual_override)
                    )
                self.assertEqual(error.exception.error_code, "invalid_state")

    def test_schema_one_state_without_manual_override_loads_with_default(self):
        state = {
            "schema": 1,
            "schedule_enabled": True,
            "snooze_until": None,
            "transition_seconds": 45,
            "origin": "manual",
            "last_applied": None,
            "schedule_disabled": None,
        }
        self.state_file().parent.mkdir(parents=True)
        self.state_file().write_text(json.dumps(state), encoding="utf-8")
        loaded = state_utils.read_state()
        self.assertEqual(loaded["manual_override"], None)
        self.assertEqual(loaded["transition_seconds"], 45)
        self.assertEqual(loaded["origin"], "manual")
        # Reading does not rewrite the on-disk schema-1 document.
        self.assertEqual(json.loads(self.state_file().read_text()), state)
        # Once a write happens the optional field is materialized.
        written = state_utils.write_state(loaded)
        self.assertIn("manual_override", written)
        self.assertIn("manual_override", json.loads(self.state_file().read_text()))

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

    def test_update_state_writes_only_when_the_mutated_state_changes(self):
        self.assertEqual(
            state_utils.update_state(lambda state: None), state_utils.DEFAULT_STATE
        )
        self.assertFalse(self.state_file().exists())

        state_utils.write_state(dict(state_utils.DEFAULT_STATE, transition_seconds=30))
        before = self.state_file().read_bytes()
        for mutator in (
            lambda state: None,
            lambda state: {**state, "transition_seconds": state["transition_seconds"]},
        ):
            self.assertEqual(
                state_utils.update_state(mutator)["transition_seconds"], 30
            )
        self.assertEqual(self.state_file().read_bytes(), before)

    def test_update_state_never_loses_concurrent_mutator_keys(self):
        state_utils.update_state(lambda state: {**state, "transition_seconds": 0})
        barrier = threading.Barrier(8)

        def bump():
            barrier.wait()
            for _ in range(5):
                state_utils.update_state(
                    lambda state: {
                        **state,
                        "transition_seconds": state["transition_seconds"] + 1,
                    }
                )

        threads = [threading.Thread(target=bump) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(state_utils.read_state()["transition_seconds"], 40)

    def test_clear_history_decides_existence_only_under_the_lock(self):
        real_locked = state_utils._locked
        real_exists = state_utils._document_exists
        held = []
        decisions = []

        @contextlib.contextmanager
        def traced_locked(document):
            held.append(True)
            try:
                with real_locked(document):
                    yield
            finally:
                held.pop()

        def traced_exists(path):
            if path == self.history_file():
                decisions.append(bool(held))
            return real_exists(path)

        for history_present in (False, True):
            with self.subTest(history_present=history_present):
                decisions.clear()
                if history_present:
                    state_utils.append_history(self.history_record(0))
                with mock.patch.object(
                    state_utils, "_locked", traced_locked
                ), mock.patch.object(state_utils, "_document_exists", traced_exists):
                    self.assertEqual(state_utils.clear_history(), [])
                self.assertTrue(
                    decisions, "clear_history must decide the document's existence"
                )
                self.assertTrue(
                    all(decisions),
                    "a concurrent append between check and lock would survive the clear",
                )
                self.assertEqual(state_utils.list_history(), [])

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
