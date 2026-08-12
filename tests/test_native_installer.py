#!/usr/bin/python3
"""Contract tests for the native Veilleuse installer (Omarchy 4)."""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
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

    def test_ui_accessibility_is_not_part_of_the_runtime(self):
        """The unified app never imports ui_accessibility: do not install it."""
        with tempfile.TemporaryDirectory(prefix="veilleuse-runtime-") as td:
            paths = make_paths(td)
            install.install_files(paths)

            self.assertFalse((paths.LIB_DIR / "ui_accessibility.py").exists())
            installed = {
                p.name for p in paths.LIB_DIR.iterdir() if p.is_file() and p.suffix == ".py"
            }
            expected = {s.name for s in install.runtime_sources()}
            self.assertEqual(installed, expected)

    def test_isolated_runtime_runs_native_status_without_module_error(self):
        """An installed runtime (only LIB_DIR on path) imports native_backends
        and runs a fake status without any ModuleNotFoundError.

        This guards the runtime manifest: every module that native_backends
        imports at module level (hyprsunset_backend and brightness_utils) must
        actually be installed, or an isolated install cannot even load the
        backend for ``veilleuse --status``.
        """
        with tempfile.TemporaryDirectory(prefix="veilleuse-runtime-") as td:
            paths = make_paths(td)
            install.install_files(paths)

            lib = str(paths.LIB_DIR)
            probe = (
                "import importlib.util, subprocess; "
                "import native_backends as nb; "
                "print(importlib.util.find_spec('native_backends').origin); "
                "fake = lambda args, **kw: subprocess.CompletedProcess("
                "list(args), 1, '', 'no display'); "
                "bs = nb.OmarchyBrightnessBackend(runner=fake).read_state(); "
                "ns = nb.OmarchyNightLightBackend(read_state=lambda: None).read_state(); "
                "assert bs.available is False and ns.available is False"
            )
            result = subprocess.run(
                [sys.executable, "-c", probe],
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONPATH": lib},
                cwd=td,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            # Proves the backend was loaded from the isolated installed runtime
            # (only LIB_DIR on the path) and not from the repo's src/.
            self.assertEqual(
                result.stdout.strip(), str(paths.LIB_DIR / "native_backends.py")
            )

    def test_desktop_argument_escapes_percent(self):
        """A literal %% in Exec must be escaped as %%%% per the desktop spec."""
        self.assertEqual(
            install.desktop_argument(Path("/tmp/a%b/c")), "/tmp/a%%b/c"
        )
        self.assertEqual(
            install.desktop_argument(Path('/tmp/a"b%c\\d')),
            '/tmp/a\\"b%%c\\\\d',
        )
        # uninstall must byte-swap identically so it recognizes the desktop file.
        self.assertEqual(
            uninstall.desktop_argument(Path("/tmp/a%b/c")), "/tmp/a%%b/c"
        )


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

    def test_hypr_config_dir_not_created_when_schedule_exists(self):
        """~/.config/hypr is never (re)created when hyprsunset.conf exists."""
        with tempfile.TemporaryDirectory(prefix="veilleuse-hypr-") as td:
            paths = make_paths(td)
            paths.HYPR.mkdir(parents=True)
            paths.HYPRSUNSET.write_bytes(b"user schedule\n")

            created: list[Path] = []
            real_mkdir = install.Path.mkdir

            def spy_mkdir(self, *args, **kwargs):
                created.append(self)
                return real_mkdir(self, *args, **kwargs)

            with patch.object(install.Path, "mkdir", spy_mkdir):
                install.install_files(paths)

            self.assertNotIn(paths.HYPR, created)
            self.assertEqual(paths.HYPRSUNSET.read_bytes(), b"user schedule\n")

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

class StateFileOwnershipTests(unittest.TestCase):
    def test_preexisting_state_file_is_backed_up_and_restored(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-state-") as td:
            paths = make_paths(td)
            original = b'{"legacy": true}\n'
            paths.CONFIG_DIR.mkdir(parents=True)
            paths.STATE_FILE.write_bytes(original)
            paths.STATE_FILE.chmod(0o640)

            install.install_files(paths)

            # Now managed: replaced by our state JSON with the install mode.
            self.assertNotEqual(paths.STATE_FILE.read_bytes(), original)
            self.assertEqual(paths.STATE_FILE.stat().st_mode & 0o7777, 0o600)
            # Written through the managed mechanism (pre-install backup preserved).
            self.assertTrue(install.marker(paths.STATE_FILE, "bak").exists())

            uninstall.uninstall_all(paths)

            # Original restored byte-for-byte and mode-for-mode.
            self.assertEqual(paths.STATE_FILE.read_bytes(), original)
            self.assertEqual(paths.STATE_FILE.stat().st_mode & 0o7777, 0o640)


class ModeOwnershipTests(unittest.TestCase):
    def test_mode_only_change_survives_reinstall(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-mode-") as td:
            source = Path(td) / "source"
            destination = Path(td) / "destination"
            source.write_bytes(b"payload\n")
            install.copy_managed_file(source, destination, 0o644)
            destination.chmod(0o600)
            install.copy_managed_file(source, destination, 0o644)
            self.assertEqual(destination.stat().st_mode & 0o7777, 0o600)

    def test_mode_only_change_survives_uninstall(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-mode-") as td:
            source = Path(td) / "source"
            destination = Path(td) / "destination"
            source.write_bytes(b"payload\n")
            install.copy_managed_file(source, destination, 0o644)
            destination.chmod(0o600)
            uninstall.remove_or_restore(destination)
            self.assertEqual(destination.read_bytes(), b"payload\n")
            self.assertEqual(destination.stat().st_mode & 0o7777, 0o600)


class BackupOrphanTests(unittest.TestCase):
    def test_uninstall_preserves_edit_and_removes_orphan_backup(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-orphan-") as td:
            source = Path(td) / "source"
            destination = Path(td) / "destination"
            source.write_bytes(b"payload\n")
            destination.write_bytes(b"original\n")
            install.copy_managed_file(source, destination, 0o644)
            backup = install.marker(destination, "bak")
            self.assertTrue(backup.exists())
            destination.write_bytes(b"user edit\n")
            uninstall.remove_or_restore(destination)
            self.assertEqual(destination.read_bytes(), b"user edit\n")
            self.assertFalse(backup.exists())

class DurableOwnershipTests(unittest.TestCase):
    def test_reinstall_after_uninstall_does_not_overwrite_edit(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-durable-") as td:
            source = Path(td) / "source"
            destination = Path(td) / "destination"
            source.write_bytes(b"version one\n")
            destination.write_bytes(b"original\n")
            install.copy_managed_file(source, destination, 0o644)
            destination.write_bytes(b"user edit\n")
            uninstall.remove_or_restore(destination)
            self.assertEqual(destination.read_bytes(), b"user edit\n")
            install.copy_managed_file(source, destination, 0o644)
            self.assertEqual(destination.read_bytes(), b"user edit\n")

    def test_install_edit_uninstall_reinstall_never_overwrites_edit(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-durable-") as td:
            paths = make_paths(td)
            install.install_files(paths)
            binary = paths.BIN / "veilleuse"
            binary.write_bytes(b"my custom binary edit\n")
            uninstall.uninstall_all(paths)
            self.assertEqual(binary.read_bytes(), b"my custom binary edit\n")
            install.install_files(paths)
            self.assertEqual(binary.read_bytes(), b"my custom binary edit\n")


class TransactionalInstallTests(unittest.TestCase):
    def test_install_rolls_back_when_payload_missing(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-tx-") as td:
            paths = make_paths(td)
            fake_root = Path(td) / "broken-root"
            (fake_root / "bin").mkdir(parents=True)
            (fake_root / "src").mkdir()
            (fake_root / "data").mkdir()
            shutil.copy2(ROOT / "bin" / "veilleuse", fake_root / "bin" / "veilleuse")
            for entry in (ROOT / "src").iterdir():
                if entry.is_file() and entry.name.endswith(".py"):
                    shutil.copy2(entry, fake_root / "src" / entry.name)
            # Simulate one runtime payload missing from the deploy tree so the
            # install aborts before writing anything.
            (fake_root / "src" / "schedule_utils.py").unlink()
            for name in (
                "io.github.ZnOw01.Veilleuse.desktop.in",
                "io.github.ZnOw01.Veilleuse.svg",
                "hyprsunset.conf",
            ):
                shutil.copy2(ROOT / "data" / name, fake_root / "data" / name)

            with patch.object(install, "ROOT", fake_root):
                with self.assertRaises(OSError):
                    install.install_files(paths)

            # No partial artifacts left behind.
            self.assertFalse((paths.BIN / "veilleuse").exists())
            self.assertFalse((paths.LIB_DIR / "veilleuse.py").exists())

    def test_install_rolls_back_restores_original_on_write_failure(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-tx-") as td:
            paths = make_paths(td)
            original = b"pre-existing binary\n"
            paths.BIN.mkdir(parents=True)
            (paths.BIN / "veilleuse").write_bytes(original)
            real = install.copy_managed_file

            def flaky(src, dst, mode):
                if dst.suffix == ".py":
                    raise OSError("simulated write failure")
                return real(src, dst, mode)

            with patch.object(install, "copy_managed_file", flaky):
                with self.assertRaises(OSError):
                    install.install_files(paths)

            # The pre-existing destination was rolled back, nothing partial remains.
            self.assertEqual((paths.BIN / "veilleuse").read_bytes(), original)
            self.assertEqual(list(paths.LIB_DIR.rglob("*.py")), [])


class UninstallResidueTests(unittest.TestCase):
    def test_uninstall_removes_only_app_temp_residue_not_user_files(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-residue-") as td:
            paths = make_paths(td)
            install.install_files(paths)
            user_cfg = paths.CONFIG_DIR / "user-settings.conf"
            user_cfg.write_text("user data\n")
            residue = paths.CONFIG_DIR / "install-state.json.tmp"
            residue.write_text("junk\n")
            uninstall.uninstall_all(paths)
            self.assertTrue(user_cfg.exists())
            self.assertFalse(residue.exists())
            self.assertTrue(paths.CONFIG_DIR.exists())


class LegacyRuntimeMigrationTests(unittest.TestCase):
    """ui_accessibility.py was installed by earlier Veilleuse releases but is
    no longer part of the runtime. It is retired only when ownership (an
    installed snapshot or our exact published payload) is proven; a
    user-modified or foreign same-named file is always preserved."""

    def test_snapshot_owned_unmodified_ui_accessibility_is_retired(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-legacy-") as td:
            paths = make_paths(td)
            install.install_files(paths)
            legacy = paths.LIB_DIR / "ui_accessibility.py"
            payload = (ROOT / "src" / "ui_accessibility.py").read_bytes()
            legacy.write_bytes(payload)
            snapshot = install.marker(legacy, "installed")
            snapshot.write_bytes(payload)

            install.install_files(paths)

            self.assertFalse(legacy.exists())
            self.assertFalse(snapshot.exists())

    def test_byte_owned_without_snapshot_is_retired(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-legacy-") as td:
            paths = make_paths(td)
            install.install_files(paths)
            legacy = paths.LIB_DIR / "ui_accessibility.py"
            legacy.write_bytes((ROOT / "src" / "ui_accessibility.py").read_bytes())

            install.install_files(paths)

            self.assertFalse(legacy.exists())

    def test_user_modified_ui_accessibility_is_preserved(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-legacy-") as td:
            paths = make_paths(td)
            install.install_files(paths)
            legacy = paths.LIB_DIR / "ui_accessibility.py"
            payload = (ROOT / "src" / "ui_accessibility.py").read_bytes()
            legacy.write_bytes(payload)
            snapshot = install.marker(legacy, "installed")
            snapshot.write_bytes(payload)
            legacy.write_bytes(payload + b"\n# user tweak\n")

            install.install_files(paths)

            self.assertTrue(legacy.exists())
            self.assertNotEqual(legacy.read_bytes(), payload)
            self.assertTrue(snapshot.exists())

    def test_foreign_file_is_preserved(self):
        with tempfile.TemporaryDirectory(prefix="veilleuse-legacy-") as td:
            paths = make_paths(td)
            install.install_files(paths)
            legacy = paths.LIB_DIR / "ui_accessibility.py"
            foreign = b"foreign content that is not veilleuse\n"
            legacy.write_bytes(foreign)

            install.install_files(paths)

            self.assertTrue(legacy.exists())
            self.assertEqual(legacy.read_bytes(), foreign)
            self.assertFalse(install.marker(legacy, "installed").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)