#!/usr/bin/python3
"""Safe per-user uninstaller for the native Veilleuse app (Omarchy 4).

Restores same-named pre-existing destinations byte-for-byte and mode-for-mode
(they are preserved as *.veilleuse.bak during install), removes only the files
the installer owns, and never touches a user-modified managed file. Waybar,
bindings.conf/bindings.lua, hyprland.conf/hyprland.lua, hyprsunset.service and
the user's ~/.config/hypr/hyprsunset.conf schedule are left alone.

Supports --dry-run to preview the actions without modifying anything.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from schedule_utils import xdg_config_home, xdg_data_home  # noqa: E402

HOME = Path.home()
CONFIG_HOME = xdg_config_home()
DATA_HOME = xdg_data_home()

MARKER = "veilleuse"
DRY_RUN = False


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
    return path.with_name(path.name + f".{MARKER}.{kind}")


def _runtime_sources(root: Path | None = None) -> list[Path]:
    base = root or ROOT / "src"
    names = (
        "veilleuse.py",
        "native_backends.py",
        "hyprsunset_backend.py",
        "schedule_utils.py",
        "ui_accessibility.py",
    )
    return [base / name for name in names]


def runtime_destinations(paths: SimpleNamespace) -> list[Path]:
    base = ROOT / "src"
    return [paths.LIB_DIR / source.relative_to(base) for source in _runtime_sources()]


def desktop_argument(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace('"', '\\"')


def desktop_payload(paths: SimpleNamespace) -> bytes:
    template = (ROOT / "data" / "io.github.ZnOw01.Veilleuse.desktop.in").read_text(encoding="utf-8")
    return template.replace("@VEILLEUSE_EXEC@", desktop_argument(paths.BIN / "veilleuse")).encode(
        "utf-8"
    )


def _expected_payload(path: Path, paths: SimpleNamespace) -> bytes | None:
    """Exact bytes our installer would have written, if we recognize the path."""
    if path == paths.BIN / "veilleuse":
        return (ROOT / "bin" / "veilleuse").read_bytes()
    if path == paths.ICON:
        return (ROOT / "data" / "io.github.ZnOw01.Veilleuse.svg").read_bytes()
    if path == paths.DESKTOP:
        return desktop_payload(paths)
    base = ROOT / "src"
    for source in _runtime_sources():
        if path == paths.LIB_DIR / source.relative_to(base):
            return source.read_bytes()
    return None


def _is_owned(path: Path, snapshot: Path) -> bool:
    """A destination is still ours when bytes *and* mode match the snapshot."""
    try:
        return (
            path.read_bytes() == snapshot.read_bytes()
            and (path.stat().st_mode & 0o7777) == (snapshot.stat().st_mode & 0o7777)
        )
    except OSError:
        return False


def remove_or_restore(
    path: Path, paths: SimpleNamespace | None = None, expected: bytes | None = None
) -> None:
    """Remove only files we still own; restore the original pre-install file.

    Ownership is established by the *.veilleuse.installed snapshot (first
    installed bytes). If the snapshot is missing but the file still matches our
    known payload, it is also treated as ours. A user-modified file (bytes *or*
    mode differ) is never deleted: it becomes the new user-owned baseline. Its
    ambiguous pre-install backup is dropped (so no orphan *.bak is left), while
    the snapshot is kept so a later reinstall never overwrites that ownership.
    """
    if DRY_RUN:
        print(f"  --dry-run: se desinstalaría {path}")
        return
    if path.is_symlink():
        marker(path, "installed").unlink(missing_ok=True)
        return
    snapshot = marker(path, "installed")
    backup = marker(path, "bak")
    if snapshot.exists():
        if path.exists() and _is_owned(path, snapshot):
            path.unlink(missing_ok=True)
            if backup.exists():
                # Restore the pre-existing original byte-for-byte and mode-for-mode.
                backup.replace(path)
            snapshot.unlink(missing_ok=True)
        elif path.exists():
            # User modified the managed file: keep their bytes and mode, drop the
            # now-ambiguous backup, and retain the snapshot for durable ownership.
            backup.unlink(missing_ok=True)
        else:
            # File already gone: just forget ownership.
            snapshot.unlink(missing_ok=True)
        return
    if expected is None and paths is not None:
        expected = _expected_payload(path, paths)
    if expected is not None and path.exists() and path.read_bytes() == expected:
        path.unlink(missing_ok=True)
        if backup.exists():
            backup.replace(path)


def clean_metadata(paths: SimpleNamespace) -> None:
    """Remove app-owned metadata, leaving any user file in ~/.config/veilleuse."""
    if DRY_RUN:
        print(f"  --dry-run: se limpiaría la metadata en {paths.CONFIG_DIR}")
        return
    # install-state.json is handled like any artifact by uninstall_all; here we
    # only remove our own transient residue (.tmp writes and sidecar markers),
    # never a user file living inside the app config dir.
    if paths.CONFIG_DIR.exists():
        for leftover in list(paths.CONFIG_DIR.rglob("*")):
            if leftover.is_file() and (
                leftover.name.endswith(".tmp") or f".{MARKER}." in leftover.name
            ):
                leftover.unlink(missing_ok=True)
        try:
            paths.CONFIG_DIR.rmdir()
        except OSError:
            # A user file lives in the app config dir: keep the directory.
            pass


def _collapse_empty_dirs(paths: SimpleNamespace) -> None:
    if DRY_RUN:
        return
    if paths.LIB_DIR.exists():
        for junk in list(paths.LIB_DIR.rglob("__pycache__")):
            shutil.rmtree(junk, ignore_errors=True)
    try:
        paths.LIB_DIR.rmdir()
    except OSError:
        pass


def uninstall_all(paths: SimpleNamespace | None = None) -> None:
    paths = paths or _default_paths()
    artifacts = [
        paths.BIN / "veilleuse",
        *runtime_destinations(paths),
        paths.ICON,
        paths.DESKTOP,
        paths.STATE_FILE,
    ]
    for artifact in artifacts:
        remove_or_restore(artifact, paths)
    _collapse_empty_dirs(paths)
    clean_metadata(paths)


def run_optional(*args: str) -> bool:
    import subprocess

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
    parser = argparse.ArgumentParser(
        prog="uninstall.py", description="Desinstala la aplicación Veilleuse"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="mostrar qué se haría sin modificar ningún archivo",
    )
    args = parser.parse_args(argv)
    global DRY_RUN
    DRY_RUN = args.dry_run
    if DRY_RUN:
        print("Modo seco: no se modificará ningún archivo.")

    try:
        uninstall_all()
    except OSError as error:
        print(f"Error: no se pudo completar la desinstalación: {error}")
        return 1

    if not DRY_RUN:
        if not run_optional("update-desktop-database", str(_default_paths().APPS)):
            print("  Aviso: no se pudo actualizar la base de lanzadores.")
    print("✓ Veilleuse desinstalado.")
    print("  Tu horario personal de ~/.config/hypr/hyprsunset.conf se conservó por seguridad.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())