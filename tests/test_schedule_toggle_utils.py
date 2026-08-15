"""Strict vertical tests for transactional schedule toggling."""

from __future__ import annotations

import hashlib
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "scripts"))

import schedule_toggle_utils as toggle  # noqa: E402
import state_utils  # noqa: E402


REALISTIC_CONFIG = (
    "# Hyprsunset schedule; comments and spacing are user-owned.\n"
    "brightness = 92\n"
    "\n"
    "profile {\n"
    "    # sunrise / natural daylight\n"
    "    time = 18:45  # local time\n"
    "    identity = true\n"
    "}\n"
    "\n"
    "# keep this unrelated setting and its whitespace\n"
    "temperature = 4100\n"
    "\n"
    "profile {\n"
    "  time = 06:15\n"
    "  temperature = 3200  # warm\n"
    "}\n"
    "\n"
)


def default_state():
    return dict(state_utils.DEFAULT_STATE)


class ScheduleToggleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / "hypr" / "hyprsunset.conf"
        self.config.parent.mkdir(parents=True)
        self.config.write_bytes(REALISTIC_CONFIG.encode("utf-8"))
        self.env = mock.patch.dict(
            os.environ,
            {
                "XDG_CONFIG_HOME": str(self.root),
                "XDG_STATE_HOME": str(self.root / "state"),
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.temp.cleanup)
        self.path_patch = mock.patch.object(toggle, "HYPRSUNSET_CONFIG", self.config)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

    def read_state(self):
        return state_utils.read_state()

    def test_disable_removes_only_unique_profiles_and_persists_exact_transaction(self):
        original = self.config.read_bytes()
        original_mode = stat.S_IMODE(self.config.stat().st_mode)

        result = toggle.disable_schedule()

        disabled = self.config.read_bytes()
        self.assertFalse(result["schedule_enabled"])
        self.assertIsNotNone(result["schedule_disabled"])
        self.assertEqual(result["schedule_disabled"]["original_text"], original.decode())
        self.assertEqual(
            result["schedule_disabled"]["original_hash"],
            hashlib.sha256(original).hexdigest(),
        )
        self.assertEqual(
            result["schedule_disabled"]["disabled_hash"],
            hashlib.sha256(disabled).hexdigest(),
        )
        self.assertNotIn(b"profile {", disabled)
        self.assertIn(b"# keep this unrelated setting", disabled)
        self.assertIn(b"temperature = 4100", disabled)
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), original_mode)
        self.assertEqual(self.read_state(), result)

    def test_cross_midnight_profiles_are_selected_without_reordering(self):
        original = (
            b"# cross midnight\n"
            b"profile {\n time = 20:00\n identity = true\n}\n"
            b"\nprofile {\n time = 05:00\n temperature = 3000\n}\n"
        )
        self.config.write_bytes(original)

        toggle.disable_schedule()
        self.assertEqual(self.config.read_bytes(), b"# cross midnight\n\n\n\n")
        toggle.enable_schedule()
        self.assertEqual(self.config.read_bytes(), original)

    def test_explicit_veilleuse_markers_select_managed_profiles_among_others(self):
        original = (
            b"# >>> Veilleuse managed day profile >>>\n"
            b"profile {\n time = 18:00\n identity = true\n}\n"
            b"# unrelated profile\n"
            b"profile {\n time = 12:00\n temperature = 4500\n}\n"
            b"# >>> Veilleuse managed night profile >>>\n"
            b"profile {\n time = 06:00\n temperature = 3200\n}\n"
        )
        self.config.write_bytes(original)

        toggle.disable_schedule()

        disabled = self.config.read_bytes()
        self.assertIn(b"# >>> Veilleuse managed day profile >>>", disabled)
        self.assertIn(b"# unrelated profile\nprofile {", disabled)
        self.assertIn(b"# >>> Veilleuse managed night profile >>>", disabled)
        self.assertNotIn(b"time = 18:00", disabled)
        self.assertNotIn(b"time = 06:00", disabled)

    def test_repeated_disable_and_enable_are_idempotent(self):
        first = toggle.disable_schedule()
        disabled = self.config.read_bytes()
        second = toggle.disable_schedule()
        self.assertEqual(second, first)
        self.assertEqual(self.config.read_bytes(), disabled)

        first_enabled = toggle.enable_schedule()
        restored = self.config.read_bytes()
        second_enabled = toggle.enable_schedule()
        self.assertEqual(first_enabled, second_enabled)
        self.assertTrue(second_enabled["schedule_enabled"])
        self.assertEqual(restored, REALISTIC_CONFIG.encode())

    def manual_override(self):
        return {
            "at": "2026-08-13T10:00:00Z",
            "operation": "nightlight_temperature",
            "profile": {"kind": "temperature", "temperature": 3500},
            "values": {"temperature": 4000},
        }

    def test_disable_clears_stale_manual_override(self):
        state_utils.write_state(
            dict(state_utils.DEFAULT_STATE, manual_override=self.manual_override())
        )
        result = toggle.disable_schedule()
        self.assertFalse(result["schedule_enabled"])
        self.assertIsNone(result["manual_override"])
        self.assertIsNone(self.read_state()["manual_override"])

    def test_disable_then_enable_cannot_suppress_schedule_enforcement(self):
        state_utils.write_state(
            dict(state_utils.DEFAULT_STATE, manual_override=self.manual_override())
        )
        disabled = toggle.disable_schedule()
        self.assertIsNone(disabled["manual_override"])
        enabled = toggle.enable_schedule()
        self.assertTrue(enabled["schedule_enabled"])
        self.assertIsNone(self.read_state()["manual_override"])

    def test_repeated_disable_clears_override_added_while_disabled(self):
        state_utils.write_state(
            dict(state_utils.DEFAULT_STATE, manual_override=self.manual_override())
        )
        toggle.disable_schedule()
        state_utils.write_state(
            dict(self.read_state(), manual_override=self.manual_override())
        )
        again = toggle.disable_schedule()
        self.assertIsNone(again["manual_override"])
        self.assertIsNone(self.read_state()["manual_override"])

    def test_enable_restores_exact_original_bytes_and_mode(self):
        self.config.chmod(0o640)
        original = self.config.read_bytes()
        original_mode = stat.S_IMODE(self.config.stat().st_mode)
        toggle.disable_schedule()
        self.config.chmod(0o600)

        toggle.enable_schedule()

        self.assertEqual(self.config.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o600)
        self.assertEqual(original_mode, 0o640)

    def test_enable_conflict_leaves_file_and_state_untouched(self):
        toggle.disable_schedule()
        before_state = self.read_state()
        self.config.write_bytes(self.config.read_bytes() + b"# external edit\n")
        conflicted = self.config.read_bytes()

        with self.assertRaises(toggle.ScheduleToggleError) as error:
            toggle.enable_schedule()

        self.assertEqual(error.exception.error_code, "conflict")
        self.assertEqual(self.config.read_bytes(), conflicted)
        self.assertEqual(self.read_state(), before_state)

    def test_missing_malformed_and_ambiguous_configs_fail_closed(self):
        cases = [
            ("missing", None),
            ("malformed", b"profile {\n time = 06:00\n"),
            (
                "ambiguous",
                REALISTIC_CONFIG.encode()
                + b"profile {\n time = 07:00\n temperature = 4000\n}\n",
            ),
        ]
        for name, content in cases:
            with self.subTest(name=name):
                if content is None:
                    self.config.unlink()
                else:
                    self.config.write_bytes(content)
                before = self.config.read_bytes() if self.config.exists() else None
                with self.assertRaises(toggle.ScheduleToggleError):
                    toggle.disable_schedule()
                self.assertEqual(
                    self.config.read_bytes() if self.config.exists() else None,
                    before,
                )
                self.assertEqual(self.read_state(), default_state())

    def test_symlink_config_fails_closed_without_touching_target(self):
        target = self.root / "real.conf"
        target.write_bytes(self.config.read_bytes())
        self.config.unlink()
        self.config.symlink_to(target)
        before = target.read_bytes()

        with self.assertRaises(toggle.ScheduleToggleError) as error:
            toggle.disable_schedule()

        self.assertEqual(error.exception.error_code, "unsafe_path")
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(self.read_state(), default_state())

    def test_file_write_failure_rolls_back_file_and_state(self):
        original = self.config.read_bytes()
        real_write = toggle._atomic_write_bytes
        calls = 0

        def crash_once(*args, **kwargs):
            nonlocal calls
            calls += 1
            real_write(*args, **kwargs)
            if calls == 1:
                raise RuntimeError("injected crash after replace")

        with mock.patch.object(toggle, "_atomic_write_bytes", side_effect=crash_once):
            with self.assertRaises(RuntimeError):
                toggle.disable_schedule()

        self.assertEqual(self.config.read_bytes(), original)
        self.assertEqual(self.read_state(), default_state())

    def test_state_write_failure_rolls_back_file_and_state(self):
        original = self.config.read_bytes()
        with mock.patch.object(
            toggle.state_utils,
            "write_state",
            side_effect=state_utils.StateError("io_error", "injected state failure"),
        ):
            with self.assertRaises(state_utils.StateError):
                toggle.disable_schedule()

        self.assertEqual(self.config.read_bytes(), original)
        self.assertEqual(self.read_state(), default_state())

    def test_enable_state_failure_rolls_back_restoration(self):
        toggle.disable_schedule()
        disabled = self.config.read_bytes()
        with mock.patch.object(
            toggle.state_utils,
            "write_state",
            side_effect=state_utils.StateError("io_error", "injected state failure"),
        ):
            with self.assertRaises(state_utils.StateError):
                toggle.enable_schedule()

        self.assertEqual(self.config.read_bytes(), disabled)
        self.assertFalse(self.read_state()["schedule_enabled"])

    def test_test_imports_leave_no_bytecode_in_installed_scripts(self):
        self.assertFalse(any((ROOT / "scripts").rglob("__pycache__")))
        self.assertFalse(any((ROOT / "scripts").rglob("*.pyc")))


if __name__ == "__main__":
    unittest.main()
