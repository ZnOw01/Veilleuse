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


def _file_mode(path: Path) -> int:
    return path.stat().st_mode & 0o7777


def save_installed_snapshot(path: Path, mode: int | None = None) -> None:
    """Record the post-install bytes and mode as the owned state."""
    snapshot = marker(path, "installed")
    if not snapshot.exists():
        _atomic_replace_bytes(
            path.read_bytes(), snapshot, _file_mode(path) if mode is None else mode
        )


def refresh_installed_snapshot(path: Path, mode: int | None = None) -> None:
    """Bring the owned-state snapshot up to date with the current bytes/mode."""
    _atomic_replace_bytes(
        path.read_bytes(),
        marker(path, "installed"),
        _file_mode(path) if mode is None else mode,
    )


def managed_file_was_changed(path: Path) -> bool:
    """A managed file counts as user-edited if bytes *or* mode diverged.

    A mode-only change is still an edit: it must survive reinstall and
    uninstall instead of being treated as still-owned.
    """
    snapshot = marker(path, "installed")
    if not (snapshot.exists() and path.exists()):
        return False
    if path.read_bytes() != snapshot.read_bytes():
        return True
    return _file_mode(path) != (snapshot.stat().st_mode & 0o7777)


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


def copy_managed_file(source: Path, destination: Path, mode: int) -> bool:
    """Install one file, honoring backups, snapshots and user edits.

    Returns True when the file was actually written, False when a user edit
    was preserved instead.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise OSError(f"No se puede gestionar un enlace simbólico: {destination}")
    if managed_file_was_changed(destination):
        print(f"  Aviso: se conserva el archivo modificado por el usuario: {destination}")
        return False
    backup_managed_file(destination)
    _atomic_replace_bytes(source.read_bytes(), destination, mode)
    _record_ownership(destination, mode)
    return True


def write_managed_file(content, destination: Path, mode: int) -> bool:
    """Install a generated file, honoring backups, snapshots and user edits.

    Returns True when the file was actually written, False when a user edit
    was preserved instead.
    """
    data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise OSError(f"No se puede gestionar un enlace simbólico: {destination}")
    if managed_file_was_changed(destination):
        print(f"  Aviso: se conserva el archivo modificado por el usuario: {destination}")
        return False
    backup_managed_file(destination)
    _atomic_replace_bytes(data, destination, mode)
    _record_ownership(destination, mode)
    return True


def _record_ownership(path: Path, mode: int) -> None:
    snapshot = marker(path, "installed")
    if snapshot.exists():
        refresh_installed_snapshot(path, mode)
    else:
        save_installed_snapshot(path, mode)


def desktop_argument(path: Path) -> str:
    return (
        str(path)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("%", "%%")
    )


def build_desktop(executable: Path) -> str:
    template = (ROOT / "data" / "io.github.ZnOw01.Veilleuse.desktop.in").read_text(encoding="utf-8")
    return template.replace("@VEILLEUSE_EXEC@", desktop_argument(executable))


def runtime_sources(root: Path | None = None) -> list[Path]:
    base = root or ROOT / "src"
    names = (
        "veilleuse.py",
        "brightness_utils.py",
        "native_backends.py",
        "hyprsunset_backend.py",
        "schedule_utils.py",
    )
    return [base / name for name in names]


def _app_version() -> str:
    return "1.0.0"


def _state_content(paths: SimpleNamespace) -> bytes:
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
    return (json.dumps(state, indent=2) + "\n").encode("utf-8")


def write_state(paths: SimpleNamespace) -> None:
    """Write install-state.json through the managed mechanism.

    A pre-existing install-state.json is backed up byte-for-byte and
    mode-for-mode like any other artifact, and restored on uninstall. It is
    never written outside ``write_managed_file``.
    """
    paths.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    write_managed_file(_state_content(paths), paths.STATE_FILE, 0o600)


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


# Legacy runtime file that earlier Veilleuse releases installed but that the
# unified runtime no longer ships. It is retired only on proven ownership.
_LEGACY_RUNTIME_FILES = ("ui_accessibility.py",)


def migrate_legacy_runtime(paths: SimpleNamespace) -> None:
    """Retire legacy runtime files that Veilleuse no longer ships.

    ``ui_accessibility.py`` was part of the runtime manifest until the unified
    application replaced it. A leftover copy in the installed runtime directory
    is removed only when Veilleuse ownership is proven: either the adjacent
    ``*.veilleuse.installed`` snapshot still matches the live bytes, or (with no
    snapshot) the bytes exactly match our published ``src/ui_accessibility.py``
    payload. A user-modified or foreign same-named file is always preserved
    untouched. This never infers ownership from the file name alone.
    """
    for relative in _LEGACY_RUNTIME_FILES:
        destination = paths.LIB_DIR / relative
        snapshot = marker(destination, "installed")
        backup = marker(destination, "bak")
        if not destination.exists() and not snapshot.exists():
            continue
        owned_by_snapshot = (
            snapshot.exists()
            and destination.exists()
            and destination.read_bytes() == snapshot.read_bytes()
        )
        owned_by_payload = destination.exists() and (
            ROOT / "src" / relative
        ).read_bytes() == destination.read_bytes()
        if not (owned_by_snapshot or owned_by_payload):
            # User-modified (diverged from the snapshot) or foreign (no proof of
            # Veilleuse ownership): preserve it and its ownership markers.
            continue
        destination.unlink(missing_ok=True)
        if backup.exists():
            # A genuine pre-Veilleuse original: restore it byte-for-byte and
            # mode-for-mode instead of discarding the user's content.
            backup.replace(destination)
        snapshot.unlink(missing_ok=True)
        backup.unlink(missing_ok=True)


def _required_payloads(root: Path) -> list[Path]:
    base = root / "src"
    payloads = [
        root / "bin" / "veilleuse",
        root / "data" / "io.github.ZnOw01.Veilleuse.svg",
        root / "data" / "io.github.ZnOw01.Veilleuse.desktop.in",
        root / "data" / "hyprsunset.conf",
    ]
    payloads.extend(runtime_sources(base))
    return payloads


def _check_payloads_available(root: Path) -> None:
    missing = [p for p in _required_payloads(root) if not p.exists() or p.is_symlink()]
    if missing:
        raise OSError(
            "Falta un payload requerido: " + ", ".join(str(p) for p in missing)
        )


def _rollback_install(written: list[Path]) -> None:
    """Undo a failed install: restore pre-install origins or remove new files."""
    for destination in reversed(written):
        backup = marker(destination, "bak")
        if backup.exists():
            try:
                backup.replace(destination)
            except OSError:
                pass
        else:
            destination.unlink(missing_ok=True)
        marker(destination, "installed").unlink(missing_ok=True)


def install_files(paths: SimpleNamespace | None = None) -> None:
    """Install every owned artifact transactionally.

    Missing payloads fail up front, and a write failure rolls the already
    written destinations back to their pre-install byte-for-byte origins.
    """
    paths = paths or _default_paths()
    base = ROOT / "src"
    _check_payloads_available(ROOT)

    for directory in (
        paths.BIN,
        paths.LIB_DIR,
        paths.APPS,
        paths.ICONS,
        paths.CONFIG_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    # One-time cleanup: retire the legacy ui_accessibility.py only when we own
    # it (snapshot/bytes prove Veilleuse created it), preserving user edits.
    migrate_legacy_runtime(paths)

    jobs: list[tuple[str, object, Path, int]] = [
        ("copy", ROOT / "bin" / "veilleuse", paths.BIN / "veilleuse", 0o755),
        (
            "copy",
            ROOT / "data" / "io.github.ZnOw01.Veilleuse.svg",
            paths.ICON,
            0o644,
        ),
        ("write", build_desktop(paths.BIN / "veilleuse"), paths.DESKTOP, 0o644),
        ("write", _state_content(paths), paths.STATE_FILE, 0o600),
    ]
    for source in runtime_sources():
        jobs.append(("copy", source, paths.LIB_DIR / source.relative_to(base), 0o644))

    written: list[Path] = []
    try:
        for kind, payload, destination, mode in jobs:
            if kind == "copy":
                wrote = copy_managed_file(payload, destination, mode)  # type: ignore[arg-type]
            else:
                wrote = write_managed_file(payload, destination, mode)
            if wrote:
                written.append(destination)
        seed_hyprsunset(paths)
    except OSError:
        _rollback_install(written)
        raise


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