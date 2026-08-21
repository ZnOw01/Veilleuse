import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.shortcut_utils as shortcut_utils


def block_for(keys_spec, eol="\n"):
    return shortcut_utils._block_text(keys_spec, eol)


class ShortcutUtilsTestBase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.config_home = Path(self.tempdir.name) / "config"
        self.home = Path(self.tempdir.name) / "home"
        self.home.mkdir()
        self.environment = mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.config_home),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            clear=False,
        )
        self.environment.start()
        reload_patch = mock.patch.object(shortcut_utils, "_reload")
        self.reload_mock = reload_patch.start()
        self.reload_mock.return_value = {"ok": True, "error": None}
        self.addCleanup(reload_patch.stop)
        self.addCleanup(self.environment.stop)
        self.addCleanup(self.tempdir.cleanup)

    def bindings_file(self):
        return self.config_home / "hypr" / "bindings.lua"

    def write_bindings(self, text, mode=0o644):
        path = self.bindings_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        path.chmod(mode)
        return path

    def read_bindings(self):
        return self.bindings_file().read_text(encoding="utf-8")


class ParseKeysTest(unittest.TestCase):
    def test_valid_spec_returns_sorted_mods_and_upper_key(self):
        mods, key = shortcut_utils.parse_keys("ctrl alt, f5")
        self.assertEqual(mods, ("ALT", "CTRL"))
        self.assertEqual(key, "F5")

    def test_single_modifier_and_letter_is_valid(self):
        self.assertEqual(shortcut_utils.parse_keys("SUPER, V"), (("SUPER",), "V"))

    def test_named_keys_and_digits_are_accepted(self):
        for spec, key in (
            ("SUPER, PAGE_UP", "PAGE_UP"),
            ("MOD4, SPACE", "SPACE"),
            ("SHIFT, 5", "5"),
            ("CTRL, F24", "F24"),
        ):
            with self.subTest(spec=spec):
                self.assertEqual(shortcut_utils.parse_keys(spec)[1], key)

    def test_invalid_specs_raise_value_error(self):
        for spec in (
            "",
            "   ",
            None,
            42,
            "V",
            "SUPER",
            "SUPER, ",
            "SUPER, V, EXTRA",
            "HYPER, V",
            "SUPER SUPER, V",
            "SUPER, É",
            "SUPER, F25",
            "SUPER, F0",
            "SUPER, V\nevil()",
            "SUPER,\rV",
            ", V",
            "SUPER,",
        ):
            with self.subTest(spec=repr(spec)):
                with self.assertRaises(ValueError):
                    shortcut_utils.parse_keys(spec)

    def test_canonical_keys_formats_mods_plus_key(self):
        self.assertEqual(shortcut_utils.canonical_keys("alt ctrl, f5"), "ALT + CTRL + F5")
        self.assertEqual(shortcut_utils.canonical_keys("super, v"), "SUPER + V")


class XdgConfigHomeTest(ShortcutUtilsTestBase):
    def test_absolute_xdg_config_home_is_honored(self):
        self.assertEqual(shortcut_utils.xdg_config_home(), self.config_home)

    def test_relative_xdg_config_home_falls_back_to_home(self):
        os.environ["XDG_CONFIG_HOME"] = "relative/path"
        self.assertEqual(shortcut_utils.xdg_config_home(), self.home / ".config")

    def test_empty_xdg_config_home_falls_back_to_home(self):
        os.environ["XDG_CONFIG_HOME"] = ""
        self.assertEqual(shortcut_utils.xdg_config_home(), self.home / ".config")

    def test_bindings_path_lives_under_hypr(self):
        self.assertEqual(
            shortcut_utils.bindings_path(), self.config_home / "hypr" / "bindings.lua"
        )


class FindBlockTest(unittest.TestCase):
    def test_missing_block_returns_none(self):
        self.assertIsNone(shortcut_utils.find_block("local x = 1\n"))

    def test_block_span_covers_markers_and_trailing_newline(self):
        prefix = "local ok = true\n"
        text = prefix + block_for("SUPER, V")
        found = shortcut_utils.find_block(text)
        self.assertIsNotNone(found)
        start, end = found
        self.assertEqual(start, len(prefix))
        self.assertEqual(text[start:end], block_for("SUPER, V"))
        self.assertEqual(end, len(text))

    def test_unclosed_block_raises_value_error(self):
        with self.assertRaises(ValueError):
            shortcut_utils.find_block("-- >>> Veilleuse shortcut >>>\n")

    def test_non_string_text_raises_value_error(self):
        with self.assertRaises(ValueError):
            shortcut_utils.find_block(None)


class InstallRemoveBlockTest(unittest.TestCase):
    def test_install_into_empty_text_produces_only_the_block(self):
        self.assertEqual(shortcut_utils.install_block("", "SUPER, V"), block_for("SUPER, V"))

    def test_remove_after_install_restores_exact_bytes_without_trailing_newline(self):
        original = 'o.bind("SUPER + Q", "App", "app")'
        installed = shortcut_utils.install_block(original, "SUPER, V")
        rest, found, keys = shortcut_utils.remove_block(installed)
        self.assertTrue(found)
        self.assertEqual(rest, original)
        self.assertEqual(keys, "SUPER + V")

    def test_remove_after_install_restores_exact_bytes_with_trailing_newline(self):
        original = 'o.bind("SUPER + Q", "App", "app")\n'
        installed = shortcut_utils.install_block(original, "SUPER, V")
        rest, found, _ = shortcut_utils.remove_block(installed)
        self.assertTrue(found)
        self.assertEqual(rest, original)

    def test_install_replaces_existing_block_in_place(self):
        first = shortcut_utils.install_block("local a = 1\n", "SUPER, V")
        second = shortcut_utils.install_block(first, "CTRL ALT, F5")
        self.assertIn('o.bind("ALT + CTRL + F5"', second)
        self.assertNotIn("SUPER + V", second)
        self.assertTrue(second.startswith("local a = 1\n"))

    def test_crlf_files_keep_crlf_endings(self):
        installed = shortcut_utils.install_block("line one\r\nline two\r\n", "SUPER, V")
        self.assertIn("\r\n", installed)
        rest, found, _ = shortcut_utils.remove_block(installed)
        self.assertTrue(found)
        self.assertEqual(rest, "line one\r\nline two\r\n")

    def test_remove_without_block_is_a_noop(self):
        text = "local a = 1\n"
        rest, found, keys = shortcut_utils.remove_block(text)
        self.assertFalse(found)
        self.assertIsNone(keys)
        self.assertEqual(rest, text)


class CollisionTest(unittest.TestCase):
    def test_no_external_binding_means_free_even_with_own_block(self):
        text = block_for("SUPER, V") + "local extra = true\n"
        self.assertIsNone(shortcut_utils.collision(text, "SUPER, V"))

    def test_external_bind_on_same_keys_collides(self):
        line = 'o.bind("SUPER + V", "Other", "other")'
        text = line + "\n" + block_for("SUPER, V")
        self.assertEqual(shortcut_utils.collision(text, "SUPER, V"), line)

    def test_bind_then_unbind_leaves_keys_free(self):
        text = (
            'o.bind("SUPER + V", "A", "a")\n'
            'hl.unbind("SUPER + V")\n'
        )
        self.assertIsNone(shortcut_utils.collision(text, "SUPER, V"))

    def test_unbind_then_bind_collides_with_last_active_bind(self):
        line = 'hl.bind("SUPER + V", "B", "b")'
        text = 'hl.unbind("SUPER + V")\n' + line + "\n"
        self.assertEqual(shortcut_utils.collision(text, "SUPER, V"), line)

    def test_different_keys_do_not_collide(self):
        text = 'o.bind("SUPER + B", "Other", "other")\n'
        self.assertIsNone(shortcut_utils.collision(text, "SUPER, V"))

    def test_commented_out_bind_is_ignored(self):
        text = '-- o.bind("SUPER + V", "Ghost", "ghost")\n'
        self.assertIsNone(shortcut_utils.collision(text, "SUPER, V"))

    def test_long_commented_bind_is_ignored(self):
        text = "--[[\no.bind(\"SUPER + V\", \"Ghost\", \"ghost\")\n]]\n"
        self.assertIsNone(shortcut_utils.collision(text, "SUPER, V"))

    def test_bind_inside_string_literal_is_ignored(self):
        text = 'local hint = "o.bind(\\"SUPER + V\\", \\"x\\", \\"y\\")"\n'
        self.assertIsNone(shortcut_utils.collision(text, "SUPER, V"))

    def test_dynamic_keys_fail_closed(self):
        text = 'local k = "SUPER + V"\no.bind(k, "Dyn", "dyn")\n'
        with self.assertRaises(shortcut_utils.UnparseableBindingError):
            shortcut_utils.collision(text, "SUPER, W")

    def test_concatenated_keys_fail_closed(self):
        text = 'o.bind("SUPER + " .. k, "Dyn", "dyn")\n'
        with self.assertRaises(shortcut_utils.UnparseableBindingError):
            shortcut_utils.collision(text, "SUPER, W")

    def test_call_without_keys_argument_fails_closed(self):
        text = "o.bind()\n"
        with self.assertRaises(shortcut_utils.UnparseableBindingError):
            shortcut_utils.collision(text, "SUPER, W")


class ShortcutStatusTest(ShortcutUtilsTestBase):
    def test_status_when_bindings_file_is_missing(self):
        status = shortcut_utils.shortcut_status()
        self.assertTrue(status["available"])
        self.assertFalse(status["exists"])
        self.assertFalse(status["installed"])
        self.assertIsNone(status["keys"])
        self.assertFalse(status["backup_exists"])
        self.assertIsNone(status["error"])

    def test_status_reports_installed_keys(self):
        self.write_bindings(block_for("CTRL ALT, F5"))
        status = shortcut_utils.shortcut_status()
        self.assertTrue(status["installed"])
        self.assertEqual(status["keys"], "ALT + CTRL + F5")
        self.assertEqual(status["command"], shortcut_utils.FIXED_COMMAND)
        self.assertIsNone(status["error"])

    def test_status_without_block_reports_not_installed(self):
        self.write_bindings("local mine = true\n")
        status = shortcut_utils.shortcut_status()
        self.assertTrue(status["exists"])
        self.assertFalse(status["installed"])
        self.assertIsNone(status["keys"])

    def test_status_fails_closed_on_unclosed_marker_block(self):
        self.write_bindings("-- >>> Veilleuse shortcut >>>\n")
        status = shortcut_utils.shortcut_status()
        self.assertFalse(status["installed"])
        self.assertIsNotNone(status["error"])

    def test_status_reports_unreadable_file_as_error(self):
        path = self.write_bindings(block_for("SUPER, V"))
        path.chmod(0o000)
        try:
            status = shortcut_utils.shortcut_status()
        finally:
            path.chmod(0o644)
        self.assertFalse(status["installed"])
        self.assertIsNotNone(status["error"])


class InstallShortcutTest(ShortcutUtilsTestBase):
    def test_fresh_install_creates_file_with_block_and_default_mode(self):
        result = shortcut_utils.install_shortcut("SUPER, V")
        self.assertTrue(result["available"])
        self.assertEqual(result["action"], "install")
        self.assertEqual(result["keys"], "SUPER + V")
        self.assertFalse(result["backup_created"])
        text = self.read_bindings()
        self.assertIn(shortcut_utils.MARKER_OPEN, text)
        self.assertIn(f'"{shortcut_utils.FIXED_COMMAND}"', text)
        mode = stat.S_IMODE(self.bindings_file().stat().st_mode)
        self.assertEqual(mode, 0o644)

    def test_second_install_creates_single_backup_third_does_not(self):
        shortcut_utils.install_shortcut("SUPER, V")
        second = shortcut_utils.install_shortcut("CTRL, K")
        self.assertTrue(second["backup_created"])
        backup = self.bindings_file().with_suffix(".lua.bak")
        self.assertTrue(backup.is_file())
        third = shortcut_utils.install_shortcut("SUPER, B")
        self.assertFalse(third["backup_created"])
        replaced = self.read_bindings()
        self.assertIn("SUPER + B", replaced)
        self.assertNotIn("CTRL + K", replaced)

    def test_install_preserves_user_content_mode_and_backs_up_original(self):
        original = 'o.bind("SUPER + Q", "App", "app")\nlocal keep = true\n'
        path = self.write_bindings(original, mode=0o600)
        result = shortcut_utils.install_shortcut("SUPER, V")
        self.assertTrue(result["available"])
        self.assertTrue(result["backup_created"])
        backup = path.with_suffix(".lua.bak")
        self.assertEqual(backup.read_text(encoding="utf-8"), original)
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)
        after = self.read_bindings()
        self.assertIn('o.bind("SUPER + Q", "App", "app")', after)
        self.assertIn("local keep = true", after)
        self.assertIn("SUPER + V", after)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_install_refuses_collision_and_leaves_file_untouched(self):
        original = 'o.bind("SUPER + V", "Music", "music")\n'
        path = self.write_bindings(original)
        result = shortcut_utils.install_shortcut("SUPER, V")
        self.assertFalse(result["available"])
        self.assertIn("SUPER + V", result["error"])
        self.assertEqual(self.read_bindings(), original)
        self.assertFalse(path.with_suffix(".lua.bak").exists())

    def test_install_with_invalid_keys_raises_before_touching_the_file(self):
        original = "local mine = true\n"
        path = self.write_bindings(original)
        with self.assertRaises(ValueError):
            shortcut_utils.install_shortcut("SUPER, V\nDROP TABLE")
        self.assertEqual(self.read_bindings(), original)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)

    def test_install_fails_closed_on_corrupt_marker_block(self):
        original = "-- >>> Veilleuse shortcut >>>\n"
        self.write_bindings(original)
        result = shortcut_utils.install_shortcut("SUPER, V")
        self.assertFalse(result["available"])
        self.assertIsNotNone(result["error"])
        self.assertEqual(self.read_bindings(), original)

    def test_install_reports_reload_result(self):
        self.reload_mock.return_value = {"ok": False, "error": "hyprctl no va"}
        result = shortcut_utils.install_shortcut("SUPER, V")
        self.assertTrue(result["available"])
        self.assertEqual(result["reload"], {"ok": False, "error": "hyprctl no va"})


class RemoveShortcutTest(ShortcutUtilsTestBase):
    def test_remove_without_file_is_successful_noop(self):
        result = shortcut_utils.remove_shortcut()
        self.assertTrue(result["available"])
        self.assertFalse(result["restored"])
        self.assertFalse(result["exists"])
        self.assertIsNone(result["reload"])

    def test_remove_on_clean_file_keeps_file_untouched(self):
        original = "local mine = true\n"
        self.write_bindings(original)
        result = shortcut_utils.remove_shortcut()
        self.assertTrue(result["available"])
        self.assertFalse(result["restored"])
        self.assertTrue(result["exists"])
        self.assertEqual(self.read_bindings(), original)

    def test_remove_deletes_file_that_held_only_the_block(self):
        self.write_bindings(block_for("SUPER, V"))
        result = shortcut_utils.remove_shortcut()
        self.assertTrue(result["available"])
        self.assertTrue(result["restored"])
        self.assertFalse(result["exists"])
        self.assertEqual(result["keys"], "SUPER + V")
        self.assertFalse(self.bindings_file().exists())

    def test_remove_restores_exact_pre_install_bytes(self):
        original = 'o.bind("SUPER + Q", "App", "app")\nlocal keep = true\n'
        self.write_bindings(original)
        shortcut_utils.install_shortcut("SUPER, V")
        result = shortcut_utils.remove_shortcut()
        self.assertTrue(result["restored"])
        self.assertEqual(self.read_bindings(), original)

    def test_remove_fails_closed_on_unclosed_marker_block(self):
        corrupt = "-- >>> Veilleuse shortcut >>>\n"
        self.write_bindings(corrupt)
        result = shortcut_utils.remove_shortcut()
        self.assertFalse(result["available"])
        self.assertIsNotNone(result["error"])
        self.assertEqual(self.read_bindings(), corrupt)

    def test_remove_reports_installed_keys_and_reloads(self):
        self.write_bindings(block_for("CTRL ALT, F5"))
        result = shortcut_utils.remove_shortcut()
        self.assertEqual(result["keys"], "ALT + CTRL + F5")
        self.reload_mock.assert_called_once()

    def test_remove_on_unreadable_file_fails_closed(self):
        path = self.write_bindings(block_for("SUPER, V"))
        path.chmod(0o000)
        try:
            result = shortcut_utils.remove_shortcut()
        finally:
            path.chmod(0o644)
        self.assertFalse(result["available"])
        self.assertIsNotNone(result["error"])
        self.assertTrue(path.is_file())


class RunCommandTest(unittest.TestCase):
    def test_successful_command_returns_zero_exit_code(self):
        result = shortcut_utils.run_command(("true",))
        self.assertEqual(result.returncode, 0)

    def test_missing_binary_returns_127(self):
        result = shortcut_utils.run_command(("veilleuse-missing-binary-xyz",))
        self.assertEqual(result.returncode, 127)

    def test_timeout_returns_124(self):
        result = shortcut_utils.run_command(("sleep", "2"), timeout=0.1)
        self.assertEqual(result.returncode, 124)


class ReloadContractTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.config_home = Path(self.tempdir.name) / "config"
        self.home = Path(self.tempdir.name) / "home"
        self.home.mkdir()
        environment = mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.config_home),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            clear=False,
        )
        environment.start()
        self.addCleanup(environment.stop)
        self.addCleanup(self.tempdir.cleanup)

    def test_reload_uses_bounded_hyprctl_call(self):
        import inspect
        import subprocess

        completed = subprocess.CompletedProcess(("hyprctl", "reload"), 0, "", "")
        with mock.patch.object(shortcut_utils, "run_command") as spy:
            spy.return_value = completed
            result = shortcut_utils.install_shortcut("SUPER, V")
        spy.assert_called_once_with(("hyprctl", "reload"))
        default_timeout = inspect.signature(
            shortcut_utils.run_command
        ).parameters["timeout"].default
        self.assertEqual(default_timeout, shortcut_utils.RELOAD_TIMEOUT)
        self.assertTrue(result["reload"]["ok"])


class MaskLuaEdgeCaseTest(unittest.TestCase):
    def test_unterminated_long_comment_masks_rest_of_file(self):
        text = "--[[ o.bind(\"SUPER + V\", \"Ghost\", \"ghost\")\nlocal x = 1\n"
        self.assertIsNone(shortcut_utils.collision(text, "SUPER, V"))

    def test_unterminated_long_string_masks_rest_of_file(self):
        text = 'local s = [==[ o.bind("SUPER + V")\n'
        self.assertIsNone(shortcut_utils.collision(text, "SUPER, V"))


if __name__ == "__main__":
    unittest.main()
