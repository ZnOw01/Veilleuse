#!/usr/bin/python3
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).parents[1] / "scripts/uninstall.py"
spec = importlib.util.spec_from_file_location("uninstall", MODULE_PATH)
uninstall = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uninstall)

INSTALL_PATH = Path(__file__).parents[1] / "scripts/install.py"
install_spec = importlib.util.spec_from_file_location("install", INSTALL_PATH)
install = importlib.util.module_from_spec(install_spec)
install_spec.loader.exec_module(install)


class WaybarCleanupTests(unittest.TestCase):
    def test_brightness_launcher_is_restored_to_safe_native_osd(self):
        config = '''{
  "backlight": {
    "on-click": "~/.local/bin/brightness-control",
    "on-scroll-up": "omarchy-brightness-display +1%"
  }
}
// cambio posterior del usuario
'''
        cleaned = uninstall.clean_waybar_config(config)
        self.assertNotIn("brightness-control", cleaned)
        self.assertIn("omarchy-swayosd-brightness", cleaned)
        self.assertIn("// cambio posterior del usuario", cleaned)

    def test_brightness_cleanup_does_not_modify_other_waybar_modules(self):
        config = r'''{
  "custom/other": {
    "on-click": "~/.local/bin/brightness-control",
    "tooltip-format": "Ajeno\nClic: abrir control seguro"
  },
  "backlight": {
    "states": { "warning": 15, "critical": 5 },
    "on-click": "~/.local/bin/brightness-control",
    "tooltip-format": "Brillo\nClic: abrir control seguro"
  }
}
'''
        cleaned = uninstall.clean_waybar_config(config)
        self.assertEqual(cleaned.count("~/.local/bin/brightness-control"), 1)
        self.assertIn('"custom/other": {\n    "on-click": "~/.local/bin/brightness-control"', cleaned)
        self.assertIn('"tooltip-format": "Ajeno\\nClic: abrir control seguro"', cleaned)
        self.assertIn("omarchy-swayosd-brightness", cleaned)
        self.assertIn('"tooltip-format": "Brillo\\nClic: abrir control seguro"', cleaned)

    def test_brightness_cleanup_ignores_fake_keys_in_comments_and_strings(self):
        config = r'''{
  // "backlight": { "on-click": "~/.local/bin/brightness-control" },
  "note": "fake key: \"backlight\": { untouched",
  "backlight": {
    "on-click": "~/.local/bin/brightness-control"
  }
}
'''
        cleaned = uninstall.clean_waybar_config(config)
        self.assertIn('// "backlight": { "on-click": "~/.local/bin/brightness-control" }', cleaned)
        self.assertIn('"note": "fake key: \\"backlight\\": { untouched"', cleaned)
        self.assertEqual(cleaned.count("omarchy-swayosd-brightness"), 1)
        self.assertEqual(cleaned.count("~/.local/bin/brightness-control"), 1)

    def test_brightness_cleanup_ignores_nested_backlight_key(self):
        config = '''{
  "custom/other": {
    "backlight": { "on-click": "~/.local/bin/brightness-control" }
  },
  "backlight": {
    "on-click": "~/.local/bin/brightness-control"
  }
}
'''
        cleaned = uninstall.clean_waybar_config(config)
        self.assertIn(
            '"backlight": { "on-click": "~/.local/bin/brightness-control" }',
            cleaned,
        )
        self.assertEqual(cleaned.count("omarchy-swayosd-brightness"), 1)
        self.assertEqual(cleaned.count("~/.local/bin/brightness-control"), 1)

    def test_brightness_cleanup_only_changes_direct_backlight_properties(self):
        config = r'''{
  "backlight": {
    // "on-click": "~/.local/bin/brightness-control",
    "nested": {
      "on-click": "~/.local/bin/brightness-control",
      "tooltip-format": "Nested\nClic: abrir control seguro"
    },
    "on-click": "~/.local/bin/brightness-control",
    "tooltip-format": "Brillo\nClic: abrir control seguro"
  }
}
'''
        cleaned = uninstall.clean_waybar_config(config)
        self.assertIn('// "on-click": "~/.local/bin/brightness-control"', cleaned)
        self.assertIn('"nested": {\n      "on-click": "~/.local/bin/brightness-control"', cleaned)
        self.assertIn('"tooltip-format": "Nested\\nClic: abrir control seguro"', cleaned)
        self.assertEqual(cleaned.count("omarchy-swayosd-brightness"), 1)
        self.assertIn('"tooltip-format": "Brillo\\nClic: abrir control seguro"', cleaned)

    def test_brightness_cleanup_leaves_globally_unbalanced_jsonc_unchanged(self):
        for config in (
            '{ "backlight": { "on-click": "~/.local/bin/brightness-control" } }}',
            '{ "backlight": { "on-click": "~/.local/bin/brightness-control" }',
        ):
            with self.subTest(config=config):
                self.assertEqual(uninstall.clean_waybar_config(config), config)

    def test_brightness_cleanup_accepts_comments_between_jsonc_tokens(self):
        config = '''{
  "backlight" /* module key */ : // module value follows
  {
    "on-click" /* action key */ : /* action value */
      "~/.local/bin/brightness-control",
    "tooltip-format" /* tooltip key */ :
      /* tooltip value */ "Brillo\\nClic: abrir control seguro"
  }
}
'''
        cleaned = uninstall.clean_waybar_config(config)
        self.assertIn("omarchy-swayosd-brightness", cleaned)
        self.assertNotIn("~/.local/bin/brightness-control", cleaned)
        self.assertIn('"Brillo\\nClic: abrir control seguro"', cleaned)
        self.assertIn("/* module key */", cleaned)
        self.assertIn("/* action value */", cleaned)

    def test_size_upgrade_is_restored_without_losing_later_changes(self):
        config = '''# BEGIN NIGHT LIGHT CONTROL SIZE UPGRADE
windowrule = size 620 650, match:class com.snowflake.NightLight
# END NIGHT LIGHT CONTROL SIZE UPGRADE
# regla personalizada posterior
'''
        cleaned = uninstall.clean_hyprland_rules(config)
        self.assertIn(
            "windowrule = size 500 610, match:class com.snowflake.NightLight",
            cleaned,
        )
        self.assertNotIn("size 620 650", cleaned)
        self.assertIn("# regla personalizada posterior", cleaned)


class InstallerIntegrationTests(unittest.TestCase):
    def test_uninstall_manifest_includes_accessibility_helper(self):
        destination = uninstall.BIN / "ui_accessibility.py"
        self.assertEqual(
            uninstall.expected_payload(destination),
            uninstall.ROOT / "src/ui_accessibility.py",
        )

    def test_uninstall_manifest_includes_hyprsunset_backend(self):
        destination = uninstall.BIN / "hyprsunset_backend.py"
        self.assertEqual(
            uninstall.expected_payload(destination),
            uninstall.ROOT / "src/hyprsunset_backend.py",
        )

    def test_install_files_copies_all_runtime_modules(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            root = Path(td)
            paths = {
                "BIN": root / "bin",
                "APPS": root / "applications",
                "ICONS": root / "icons",
                "HYPR": root / "hypr",
            }
            with (
                patch.object(install, "BIN", paths["BIN"]),
                patch.object(install, "APPS", paths["APPS"]),
                patch.object(install, "ICONS", paths["ICONS"]),
                patch.object(install, "HYPR", paths["HYPR"]),
            ):
                install.install_files()
            for name in (
                "night-light-control",
                "brightness-control",
                "brightness_utils.py",
                "ui_accessibility.py",
                "schedule_utils.py",
                "hyprsunset_backend.py",
                "night-light-toggle",
                "night-light-status",
                "night-light",
                "brightness-step",
            ):
                self.assertTrue((paths["BIN"] / name).exists(), name)
            self.assertIn(
                'Exec="' + str(paths["BIN"] / "night-light-control") + '"',
                (paths["APPS"] / "night-light-control.desktop").read_text(),
            )

    def waybar_config(self, scroll_up, scroll_down, modules='"group/tray-expander",'):
        return f'''{{
  "modules-right": [{modules}],
  "backlight": {{
    "on-click": "omarchy-swayosd-brightness $(brightnessctl -d panel -m | cut -d, -f4 | tr -d '%')",
    "on-scroll-up": "{scroll_up}",
    "on-scroll-down": "{scroll_down}"
  }},
  "bluetooth": {{}}
}}
'''

    def test_waybar_preserves_custom_scroll_commands(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            root = Path(td)
            config_dir = root / "waybar"
            config_dir.mkdir()
            config = config_dir / "config.jsonc"
            config.write_text(self.waybar_config("custom-up", "custom-down"))
            original = install.WAYBAR
            try:
                install.WAYBAR = config_dir
                install.integrate_waybar()
            finally:
                install.WAYBAR = original
            updated = config.read_text()
            self.assertIn('"on-scroll-up": "custom-up"', updated)
            self.assertIn('"on-scroll-down": "custom-down"', updated)

    def test_compact_waybar_module_gets_middle_click_without_corrupting_jsonc(self):
        config = '{"custom/nightlight":{"exec":"~/.local/bin/night-light-status","on-click":"~/.local/bin/night-light-control"}}'
        updated = install.ensure_jsonc_string_property(
            config,
            "custom/nightlight",
            "on-click-middle",
            "~/.local/bin/night-light-control",
        )
        self.assertIsNotNone(uninstall.scan_jsonc(updated))
        self.assertEqual(updated.count('"custom/nightlight"'), 1)
        self.assertIn('"on-click-middle": "~/.local/bin/night-light-control"', updated)
        self.assertEqual(
            install.ensure_jsonc_string_property(
                updated,
                "custom/nightlight",
                "on-click-middle",
                "~/.local/bin/night-light-control",
            ),
            updated,
        )

    def test_waybar_migration_preserves_custom_module_click(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            config_dir = Path(td) / "waybar"
            config_dir.mkdir()
            config = config_dir / "config.jsonc"
            config.write_text('''{
  "custom/nightlight": {
    "exec": "~/.local/bin/night-light-status",
    "on-click": "user-action"
  }
}
''')
            original = install.WAYBAR
            try:
                install.WAYBAR = config_dir
                install.integrate_waybar()
            finally:
                install.WAYBAR = original
            updated = config.read_text()
            self.assertIn('"on-click": "user-action"', updated)
            self.assertNotIn("night-light --cycle", updated)

    def test_uninstall_preserves_custom_nightlight_actions(self):
        config = '''{
  "custom/nightlight": {
    "on-click": "user-action",
    "on-click-middle": "user-middle"
  }
}
'''
        cleaned = uninstall.clean_waybar_config(config)
        self.assertIn('"on-click": "user-action"', cleaned)
        self.assertIn('"on-click-middle": "user-middle"', cleaned)

    def test_waybar_migrates_managed_clicks_idempotently(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            config_dir = Path(td) / "waybar"
            config_dir.mkdir()
            config = config_dir / "config.jsonc"
            config.write_text('''{
  "custom/nightlight": {
    "exec": "~/.local/bin/night-light-status",
    "on-click": "~/.local/bin/night-light-control",
    "on-click-right": "~/.local/bin/night-light-toggle"
  },
  "custom/other": { "on-click": "user-action" }
}
''')
            original = install.WAYBAR
            try:
                install.WAYBAR = config_dir
                install.integrate_waybar()
                first = config.read_text()
                install.integrate_waybar()
            finally:
                install.WAYBAR = original
            self.assertEqual(config.read_text(), first)
            self.assertIn('"on-click": "~/.local/bin/night-light --cycle"', first)
            self.assertIn('"on-click-middle": "~/.local/bin/night-light-control"', first)
            self.assertIn('"on-click": "user-action"', first)

    def test_uninstall_restores_managed_waybar_clicks(self):
        config = '''{
  "custom/nightlight": {
    "on-click": "~/.local/bin/night-light --cycle",
    "on-click-middle": "~/.local/bin/night-light-control",
    "on-click-right": "~/.local/bin/night-light-toggle"
  }
}
'''
        cleaned = uninstall.clean_waybar_config(config)
        self.assertIn('"on-click": "~/.local/bin/night-light-control"', cleaned)
        self.assertNotIn("on-click-middle", cleaned)
        self.assertTrue(uninstall.scan_jsonc(cleaned) is not None)

    def test_waybar_replaces_only_known_scroll_commands(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            root = Path(td)
            config_dir = root / "waybar"
            config_dir.mkdir()
            config = config_dir / "config.jsonc"
            config.write_text(self.waybar_config(
                "omarchy-brightness-display +1%",
                "omarchy-brightness-display 1%-",
            ))
            original = install.WAYBAR
            try:
                install.WAYBAR = config_dir
                install.integrate_waybar()
            finally:
                install.WAYBAR = original
            updated = config.read_text()
            self.assertIn('"on-scroll-up": "~/.local/bin/brightness-step +"', updated)
            self.assertIn('"on-scroll-down": "~/.local/bin/brightness-step -"', updated)

    def test_hyprland_bindl_conflict_is_not_overwritten(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            hypr = Path(td)
            bindings = hypr / "bindings.conf"
            bindings.write_text("bindl = SUPER CTRL, N, exec, custom-command\n")
            original = install.HYPR
            try:
                install.HYPR = hypr
                install.integrate_hyprland()
            finally:
                install.HYPR = original
            self.assertNotIn("night-light-toggle", bindings.read_text())


class SnapshotSafetyTests(unittest.TestCase):
    def test_service_state_restores_enabled_and_active_independently(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            state = Path(td) / "install-state.json"
            state.write_text(json.dumps({"enabled": True, "active": False}))
            with (
                patch.object(uninstall, "SERVICE_STATE", state),
                patch.object(uninstall, "run_optional", return_value=True) as run,
            ):
                self.assertTrue(uninstall.restore_service_state())
            self.assertEqual(
                [call.args for call in run.call_args_list],
                [
                    ("systemctl", "--user", "enable", "hyprsunset.service"),
                    ("systemctl", "--user", "stop", "hyprsunset.service"),
                ],
            )
            self.assertFalse(state.exists())

    def test_reinstall_updates_owned_payload_and_restores_original(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            source = Path(td) / "source"
            destination = Path(td) / "destination"
            source.write_bytes(b"version one\n")
            destination.write_bytes(b"original\n")
            install.copy_managed_file(source, destination, 0o644)
            source.write_bytes(b"version two\n")
            install.copy_managed_file(source, destination, 0o644)
            uninstall.remove_or_restore(destination, source.read_bytes())
            self.assertEqual(destination.read_bytes(), b"original\n")

    def test_reinstall_does_not_overwrite_modified_payload(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            source = Path(td) / "source"
            destination = Path(td) / "destination"
            source.write_bytes(b"version one\n")
            destination.write_bytes(b"original\n")
            install.copy_managed_file(source, destination, 0o644)
            destination.write_bytes(b"user edit\n")
            source.write_bytes(b"version two\n")
            install.copy_managed_file(source, destination, 0o644)
            self.assertEqual(destination.read_bytes(), b"user edit\n")

    def test_identical_preexisting_file_is_restored_instead_of_deleted(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            source = Path(td) / "source"
            destination = Path(td) / "destination"
            source.write_bytes(b"same payload\n")
            destination.write_bytes(b"same payload\n")
            install.copy_managed_file(source, destination, 0o644)
            uninstall.remove_or_restore(destination, source.read_bytes())
            self.assertEqual(destination.read_bytes(), b"same payload\n")
            self.assertFalse(destination.with_name(
                destination.name + ".night-light-control.installed"
            ).exists())

    def test_modified_managed_file_survives_uninstall(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            source = Path(td) / "source"
            destination = Path(td) / "destination"
            source.write_bytes(b"installed\n")
            destination.write_bytes(b"original\n")
            install.copy_managed_file(source, destination, 0o644)
            destination.write_bytes(b"user edit\n")
            uninstall.remove_or_restore(destination, source.read_bytes())
            self.assertEqual(destination.read_bytes(), b"user edit\n")

    def test_legacy_marked_integration_is_cleaned_without_snapshot(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            path = Path(td) / "hyprland.conf"
            path.write_text(
                "before\n# BEGIN NIGHT LIGHT CONTROL\nowned\n"
                "# END NIGHT LIGHT CONTROL\nafter\n"
            )
            uninstall.remove_owned_integration(
                path,
                lambda text: uninstall.remove_marked_block(
                    text, "# BEGIN NIGHT LIGHT CONTROL", "# END NIGHT LIGHT CONTROL"
                ),
            )
            self.assertEqual(path.read_text(), "before\nafter\n")

    def test_reinstall_does_not_overwrite_first_installed_snapshot(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            path = Path(td) / "config"
            path.write_text("first installed state\n")
            install.save_installed_snapshot(path)
            path.write_text("user change plus reinstall\n")
            install.save_installed_snapshot(path)
            snapshot = path.with_name(path.name + ".night-light-control.installed")
            self.assertEqual(snapshot.read_text(), "first installed state\n")

    def test_user_change_survives_two_complete_install_uninstall_cycles(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            path = Path(td) / "config"
            path.write_text("base\n")

            install.backup_once(path)
            path.write_text("installed\n")
            install.save_installed_snapshot(path)
            path.write_text("installed\nuser-change\n")
            uninstall.remove_owned_integration(
                path, lambda text: text.replace("installed\n", "base\n")
            )
            self.assertEqual(path.read_text(), "base\nuser-change\n")

            install.backup_once(path)
            path.write_text("installed\nuser-change\n")
            install.save_installed_snapshot(path)
            uninstall.remove_owned_integration(
                path, lambda text: text.replace("installed\n", "base\n")
            )
            self.assertEqual(path.read_text(), "base\nuser-change\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
