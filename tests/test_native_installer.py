#!/usr/bin/python3
"""Contract tests for the native Veilleuse installer (Omarchy 4)."""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# Keep real user HOME/XDG out of the tests: point them to a throwaway tree
# before the installer modules compute their destination constants.
_THOME = Path(tempfile.mkdtemp(prefix="veilleuse-home-"))
os.environ["HOME"] = str(_THOME)
os.environ.setdefault("XDG_CONFIG_HOME", str(_THOME / ".config"))
os.environ.setdefault("XDG_DATA_HOME", str(_THOME / ".local/share"))

ROOT = Path(__file__).parents[1]

INSTALL_PATH = ROOT / "scripts/install.py"
install_spec = importlib.util.spec_from_file_location("install", INSTALL_PATH)
install = importlib.util.module_from_spec(install_spec)
install_spec.loader.exec_module(install)

UNINSTALL_PATH = ROOT / "scripts/uninstall.py"
uninstall_spec = importlib.util.spec_from_file_location("uninstall", UNINSTALL_PATH)
uninstall = importlib.util.module_from_spec(uninstall_spec)
uninstall_spec.loader.exec_module(uninstall)


def make_paths(td: str) -> SimpleNamespace:
    root = Path(td)
    return SimpleNamespace(
        BIN=root / "bin",
        LIB_DIR=root / "lib" / "veilleuse",
        APPS=root / "applications",
        ICONS=root / "icons",
        ICON=root / "icons" / "io.github.ZnOw01.Veilleuse.svg",
        DESKTOP=root / "applications" / "io.github.ZnOw01.Veilleuse.desktop",
        CONFIG_DIR=root / "config" / "veilleuse",
        HYPR=root / "hypr",
        HYPRSUNSET=root / "hypr" / "hyprsunset.conf",
        STATE_FILE=root / "config" / "veilleuse" / "install-state.json",
    )


class InstallArticlesTests(unittest.TestCase):
    def test_only_contract_artifacts_are_installed(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-install-") as td:
            paths = make_paths(td)
            install.install_files(paths)

            # Binary in ~/.local/bin
            self.assertEqual(
                (paths.BIN / "veilleuse").read_bytes(),
                (ROOT / "bin" / "veilleuse").read_bytes(),
            )
            self.assertEqual(
                (paths.BIN / "veilleuse").stat().st_mode & 0o7777, 0o755
            )
            # Runtime Python modules under ~/.local/lib/veilleuse
            self.assertEqual(
                (paths.LIB_DIR / "veilleuse.py").read_bytes(),
                (ROOT / "src" / "veilleuse.py").read_bytes(),
            )
            self.assertEqual(
                (paths.LIB_DIR / "native_backends.py").read_bytes(),
                (ROOT / "src" / "native_backends.py").read_bytes(),
            )
            # Desktop entry
            desktop = (paths.DESKTOP).read_text(encoding="utf-8")
            self.assertIn("Name=Veilleuse", desktop)
            self.assertIn("Icon=io.github.ZnOw01.Veilleuse", desktop)
            self.assertIn("Exec=\"" + str(paths.BIN / "veilleuse") + "\"", desktop)
            # Icon
            self.assertEqual(
                paths.ICON.read_bytes(), (ROOT / "data" / "io.github.ZnOw01.Veilleuse.svg").read_bytes()
            )
            # Own metadata
            self.assertTrue(paths.STATE_FILE.exists())

    def test_install_never_touches_waybar_bindings_or_hyprland(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-install-") as td:
            paths = make_paths(td)
            (paths.HYPR / "bindings.conf").parent.mkdir(parents=True)
            (paths.HYPR / "bindings.conf").write_text("bindd = SUPER, N, exec, factorie\n")
            (paths.HYPR / "hyprland.conf").write_text("source = ./hyprland.conf\n")
            (paths.HYPR / "hyprland.lua").write_text("return { }\n")
            (paths.HYPR / "bindings.lua").write_text("return { }\n")
            waybar = Path(td) / "waybar" / "config.jsonc"
            waybar.parent.mkdir(parents=True, exist_ok=True)
            waybar.write_text("{ }\n")

            install.install_files(paths)

            self.assertEqual(
                (paths.HYPR / "bindings.conf").read_text(encoding="utf-8"),
                "bindd = SUPER, N, exec, factorie\n",
            )
            self.assertEqual(
                (paths.HYPR / "hyprland.conf").read_text(encoding="utf-8"),
                "source = ./hyprland.conf\n",
            )
            self.assertEqual((paths.HYPR / "hyprland.lua").read_text(encoding="utf-8"), "return { }\n")
            self.assertEqual((paths.HYPR / "bindings.lua").read_text(encoding="utf-8"), "return { }\n")
            self.assertEqual(waybar.read_text(encoding="utf-8"), "{ }\n")

    def test_double_install_is_idempotent(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-install-") as td:
            paths = make_paths(td)
            install.install_files(paths)
            install.install_files(paths)

            binary = paths.BIN / "veilleuse"
            self.assertEqual(
                binary.read_bytes(), (ROOT / "bin" / "veilleuse").read_bytes()
            )
            snapshots = [
                p
                for p in binary.parent.iterdir()
                if p.name.endswith(".veilleuse.installed")
            ]
            self.assertEqual(len(snapshots), 1)


class PreexistingDestinationTests(unittest.TestCase):
    def test_preexisting_file_is_backed_up_and_restored(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-pre-") as td:
            paths = make_paths(td)
            binary = paths.BIN / "veilleuse"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"user original veilleuse\n")
            binary.chmod(0o754)

            install.install_files(paths)

            # Now ours: content replaced, install mode applied.
            self.assertEqual(
                binary.read_bytes(), (ROOT / "bin" / "veilleuse").read_bytes()
            )
            self.assertEqual(binary.stat().st_mode & 0o7777, 0o755)

            uninstall.uninstall_all(paths)

            # Original restored byte-for-byte and mode-for-mode.
            self.assertEqual(binary.read_bytes(), b"user original veilleuse\n")
            self.assertEqual(binary.stat().st_mode & 0o7777, 0o754)


class SeedScheduleTests(unittest.TestCase):
    def test_hyprsunset_is_seeded_only_when_absent(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-seed-") as td:
            paths = make_paths(td)
            install.install_files(paths)
            self.assertEqual(
                paths.HYPRSUNSET.read_bytes(),
                (ROOT / "data" / "hyprsunset.conf").read_bytes(),
            )
            template = paths.HYPRSUNSET.read_bytes()
            install.install_files(paths)
            self.assertEqual(paths.HYPRSUNSET.read_bytes(), template)

    def test_existing_hyprsunset_is_never_overwritten(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-seed-") as td:
            paths = make_paths(td)
            paths.HYPR.mkdir(parents=True)
            paths.HYPRSUNSET.write_bytes(b"not the template\n")
            install.install_files(paths)
            self.assertEqual(paths.HYPRSUNSET.read_bytes(), b"not the template\n")

    def test_foreign_schedule_survives_install_and_uninstall(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-seed-") as td:
            paths = make_paths(td)
            paths.HYPR.mkdir(parents=True)
            foreign = b"schedule owned by the user\n"
            paths.HYPRSUNSET.write_bytes(foreign)
            install.install_files(paths)
            uninstall.uninstall_all(paths)
            self.assertEqual(paths.HYPRSUNSET.read_bytes(), foreign)

    def test_uninstall_preserves_a_seeded_hyprsunset_schedule(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-seed-") as td:
            paths = make_paths(td)
            install.install_files(paths)
            seeded = paths.HYPRSUNSET.read_bytes()
            uninstall.uninstall_all(paths)
            self.assertEqual(paths.HYPRSUNSET.read_bytes(), seeded)


class UninstallContractTests(unittest.TestCase):
    def test_uninstall_removes_all_owned_artifacts(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-uninstall-") as td:
            paths = make_paths(td)
            install.install_files(paths)
            uninstall.uninstall_all(paths)

            self.assertFalse((paths.BIN / "veilleuse").exists())
            self.assertFalse(paths.LIB_DIR.exists())
            self.assertFalse(paths.ICON.exists())
            self.assertFalse(paths.DESKTOP.exists())

    def test_modified_managed_file_survives_uninstall(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-mod-") as td:
            paths = make_paths(td)
            install.install_files(paths)
            binary = paths.BIN / "veilleuse"
            binary.write_bytes(b"user edit\n")
            uninstall.uninstall_all(paths)
            self.assertEqual(binary.read_bytes(), b"user edit\n")

    def test_dry_run_performs_no_changes(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-dry-") as td:
            paths = make_paths(td)
            install.install_files(paths)
            binary = paths.BIN / "veilleuse"
            self.assertTrue(binary.exists())
            with patch.object(uninstall, "_default_paths", return_value=paths):
                try:
                    rc = uninstall.main(["--dry-run"])
                finally:
                    uninstall.DRY_RUN = False
            self.assertEqual(rc, 0)
            self.assertTrue(binary.exists())
            self.assertTrue(paths.DESKTOP.exists())
            self.assertEqual(
                binary.read_bytes(), (ROOT / "bin" / "veilleuse").read_bytes()
            )


class SnapshotSafetyTests(unittest.TestCase):
    def test_copy_managed_file_idempotent_for_clean_target(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-snap-") as td:
            source = Path(td) / "source"
            destination = Path(td) / "destination"
            source.write_bytes(b"payload\n")
            install.copy_managed_file(source, destination, 0o644)
            install.copy_managed_file(source, destination, 0o644)
            self.assertEqual(destination.read_bytes(), b"payload\n")
            markers = [
                p for p in Path(td).iterdir() if p.name.endswith(".veilleuse.installed")
            ]
            self.assertEqual(len(markers), 1)

    def test_modified_managed_file_survives_uninstall(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-snap-") as td:
            source = Path(td) / "source"
            destination = Path(td) / "destination"
            source.write_bytes(b"installed\n")
            destination.write_bytes(b"original\n")
            install.copy_managed_file(source, destination, 0o644)
            destination.write_bytes(b"user edit\n")
            uninstall.remove_or_restore(destination)
            self.assertEqual(destination.read_bytes(), b"user edit\n")

    def test_reinstall_updates_owned_payload_and_restores_original(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-snap-") as td:
            source = Path(td) / "source"
            destination = Path(td) / "destination"
            source.write_bytes(b"version one\n")
            destination.write_bytes(b"original\n")
            install.copy_managed_file(source, destination, 0o644)
            source.write_bytes(b"version two\n")
            install.copy_managed_file(source, destination, 0o644)
            uninstall.remove_or_restore(destination)
            self.assertEqual(destination.read_bytes(), b"original\n")

    def test_reinstall_does_not_overwrite_modified_payload(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-snap-") as td:
            source = Path(td) / "source"
            destination = Path(td) / "destination"
            source.write_bytes(b"version one\n")
            destination.write_bytes(b"original\n")
            install.copy_managed_file(source, destination, 0o644)
            destination.write_bytes(b"user edit\n")
            source.write_bytes(b"version two\n")
            install.copy_managed_file(source, destination, 0o644)
            self.assertEqual(destination.read_bytes(), b"user edit\n")

    def test_save_installed_snapshot_not_overwritten(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-snap-") as td:
            path = Path(td) / "config"
            path.write_text("first installed state\n")
            install.save_installed_snapshot(path)
            path.write_text("user change plus reinstall\n")
            install.save_installed_snapshot(path)
            snapshot = path.with_name(path.name + ".veilleuse.installed")
            self.assertEqual(snapshot.read_text(), "first installed state\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)