#!/usr/bin/python3
"""Per-user installer for the native Veilleuse app (Omarchy 4).

Owns exactly the artifacts defined in docs/ARCHITECTURE.md:

- ~/.local/bin/veilleuse
- the Veilleuse Python runtime under ~/.local/lib/veilleuse/
- the desktop entry in ~/.local/share/applications/
- the icon in ~/.local/share/icons/hicolor/scalable/apps/
- app metadata under ~/.config/veilleuse/

It never edits Waybar, bindings.conf/bindings.lua, hyprland.conf/hyprland.lua
or any service state, and only seeds ~/.config/hypr/hyprsunset.conf when that
file does not exist. Install is idempotent and transactional at the file level:
pre-existing same-named destinations are kept byte-for-byte and mode-for-mode
(in a *.veilleuse.bak backup) and later restored by the uninstaller, and a
user-modified managed file is never overwritten.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from schedule_utils import xdg_config_home, xdg_data_home  # noqa: E402

HOME = Path.home()
CONFIG_HOME = xdg_config_home()
DATA_HOME = xdg_data_home()

MARKER = "veilleuse"


def _default_paths() -> SimpleNamespace:
    home = HOME
    return SimpleNamespace(
        BIN=home / ".local" / "bin",
        LIB_DIR=home / ".local" / "lib" / "veilleuse",
        APPS=DATA_HOME / "applications",
        ICONS=DATA_HOME / "icons" / "hicolor" / "scalable" / "apps",
        ICON=DATA_HOME
        / "icons"
        / "hicolor"
        / "scalable"
        / "apps"
        / "io.github.ZnOw01.Veilleuse.svg",
        DESKTOP=DATA_HOME / "applications" / "io.github.ZnOw01.Veilleuse.desktop",
        CONFIG_DIR=CONFIG_HOME / "veilleuse",
        HYPR=CONFIG_HOME / "hypr",
        HYPRSUNSET=CONFIG_HOME / "hypr" / "hyprsunset.conf",
        STATE_FILE=CONFIG_HOME / "veilleuse" / "install-state.json",
    )


def marker(path: Path, kind: str) -> Path:
    """Adjacent marker used to track installed snapshots and backups."""
    return path.with_name(path.name + f".{MARKER}.{kind}")


def save_installed_snapshot(path: Path) -> None:
    """Keep the first post-install bytes so a reinstall never erases user edits."""
    snapshot = marker(path, "installed")
    if not snapshot.exists():
        shutil.copy2(path, snapshot)


def refresh_installed_snapshot(path: Path) -> None:
    """Bring the installed snapshot up to date with the current managed bytes."""
    snapshot = marker(path, "installed")
    _atomic_replace_bytes(path.read_bytes(), snapshot, path.stat().st_mode & 0o7777)


def managed_file_was_changed(path: Path) -> bool:
    snapshot = marker(path, "installed")
    return snapshot.exists() and path.exists() and path.read_bytes() != snapshot.read_bytes()


def backup_once(path: Path) -> None:
    """Keep one pre-install copy of an existing path before changing it."""
    backup = marker(path, "bak")
    if path.exists() and not backup.exists():
        shutil.copy2(path, backup)


def backup_managed_file(path: Path) -> None:
    """Preserve an unmanaged pre-existing file (byte-for-byte and mode-for-mode).

    A backup is only created the first time we take over a destination (i.e.
    before any installed snapshot exists), so idempotent reinstalls of our own
    files do not accumulate spurious backups.
    """
    if path.is_symlink():
        raise OSError(f"No se puede gestionar un enlace simbólico: {path}")
    snapshot = marker(path, "installed")
    backup = marker(path, "bak")
    if not snapshot.exists() and path.exists() and not backup.exists():
        shutil.copy2(path, backup)


def _atomic_replace_bytes(content_bytes: bytes, destination: Path, mode: int) -> None:
    """Atomically write raw bytes to a destination with the requested mode."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        os.close(descriptor)
        Path(temporary).write_bytes(content_bytes)
        Path(temporary).chmod(mode)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def copy_managed_file(source: Path, destination: Path, mode: int) -> None:
    """Install one file, honoring backups, snapshots and user edits."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise OSError(f"No se puede gestionar un enlace simbólico: {destination}")
    if managed_file_was_changed(destination):
        print(f"  Aviso: se conserva el archivo modificado por el usuario: {destination}")
        return
    backup_managed_file(destination)
    _atomic_replace_bytes(source.read_bytes(), destination, mode)
    if marker(destination, "installed").exists():
        refresh_installed_snapshot(destination)
    else:
        save_installed_snapshot(destination)


def write_managed_file(content, destination: Path, mode: int) -> None:
    """Install a generated file, honoring backups, snapshots and user edits."""
    data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise OSError(f"No se puede gestionar un enlace simbólico: {destination}")
    if managed_file_was_changed(destination):
        print(f"  Aviso: se conserva el archivo modificado por el usuario: {destination}")
        return
    backup_managed_file(destination)
    _atomic_replace_bytes(data, destination, mode)
    if marker(destination, "installed").exists():
        refresh_installed_snapshot(destination)
    else:
        save_installed_snapshot(destination)


def desktop_argument(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace('"', '\\"')


def build_desktop(executable: Path) -> str:
    template = (ROOT / "data" / "io.github.ZnOw01.Veilleuse.desktop.in").read_text(encoding="utf-8")
    return template.replace("@VEILLEUSE_EXEC@", desktop_argument(executable))


def runtime_sources(root: Path | None = None) -> list[Path]:
    base = root or ROOT / "src"
    names = (
        "veilleuse.py",
        "native_backends.py",
        "hyprsunset_backend.py",
        "schedule_utils.py",
        "ui_accessibility.py",
    )
    return [base / name for name in names]


def _app_version() -> str:
    return "1.0.0"


def write_state(paths: SimpleNamespace) -> None:
    state = {
        "app": "veilleuse",
        "app_id": "io.github.ZnOw01.Veilleuse",
        "version": _app_version(),
        "artifacts": [
            str(paths.BIN / "veilleuse"),
            str(paths.LIB_DIR),
            str(paths.ICON),
            str(paths.DESKTOP),
        ],
    }
    paths.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_replace_bytes(
        (json.dumps(state, indent=2) + "\n").encode("utf-8"),
        paths.STATE_FILE,
        0o600,
    )


def seed_hyprsunset(paths: SimpleNamespace) -> None:
    """Seed the default schedule only when ~/.config/hypr/hyprsunset.conf is absent.

    Once present (whether pre-existing or seeded), it is user-owned and never
    overwritten or removed.
    """
    if paths.HYPRSUNSET.exists() or paths.HYPRSUNSET.is_symlink():
        return
    paths.HYPR.mkdir(parents=True, exist_ok=True)
    _atomic_replace_bytes(
        (ROOT / "data" / "hyprsunset.conf").read_bytes(), paths.HYPRSUNSET, 0o644
    )


def install_files(paths: SimpleNamespace | None = None) -> None:
    paths = paths or _default_paths()
    base = ROOT / "src"
    for directory in (
        paths.BIN,
        paths.LIB_DIR,
        paths.APPS,
        paths.ICONS,
        paths.CONFIG_DIR,
        paths.HYPR,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    copy_managed_file(ROOT / "bin" / "veilleuse", paths.BIN / "veilleuse", 0o755)
    for source in runtime_sources():
        relative = source.relative_to(base)
        copy_managed_file(source, paths.LIB_DIR / relative, 0o644)
    copy_managed_file(ROOT / "data" / "io.github.ZnOw01.Veilleuse.svg", paths.ICON, 0o644)
    write_managed_file(build_desktop(paths.BIN / "veilleuse"), paths.DESKTOP, 0o644)
    write_state(paths)
    seed_hyprsunset(paths)


def run_optional(*args: str) -> bool:
    try:
        result = subprocess.run(
            args,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def main(argv=None) -> int:
    try:
        install_files()
    except OSError as error:
        print(f"Error: no se pudo completar la instalación: {error}")
        return 1
    if not run_optional("update-desktop-database", str(_default_paths().APPS)):
        print("  Aviso: no se pudo actualizar la base de lanzadores; reinicia la sesión si el lanzador no aparece.")
    print("✓ Veilleuse instalado.")
    print("  Abre 'Veilleuse' desde el lanzador, o usa ~/.local/bin/veilleuse --status")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())