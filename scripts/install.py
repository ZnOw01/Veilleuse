#!/usr/bin/python3
"""Per-user installer for Night Light Control on Omarchy/Hyprland."""
from __future__ import annotations

import os
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home()
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from schedule_utils import CONFIG_DIR, atomic_write_text, xdg_config_home, xdg_data_home
from uninstall import replace_jsonc_string_property, scan_jsonc, skip_jsonc_trivia


BIN = HOME / ".local/bin"
XDG_CONFIG = xdg_config_home()
XDG_DATA = xdg_data_home()
APPS = XDG_DATA / "applications"
ICONS = XDG_DATA / "icons/hicolor/scalable/apps"
HYPR = XDG_CONFIG / "hypr"
WAYBAR = XDG_CONFIG / "waybar"
SERVICE_STATE = CONFIG_DIR / "install-state.json"
OWN_NIGHTLIGHT_CLICKS = frozenset(
    {
        "~/.local/bin/night-light-control",
        "~/.local/bin/night-light --cycle",
    }
)


def backup_once(path: Path) -> None:
    """Keep one pre-install copy before changing an existing config file."""
    backup = path.with_name(path.name + ".night-light-control.bak")
    if path.exists() and not backup.exists():
        shutil.copy2(path, backup)


def save_installed_snapshot(path: Path) -> None:
    """Keep the first post-install bytes so reinstalls cannot erase user changes."""
    snapshot = path.with_name(path.name + ".night-light-control.installed")
    if not snapshot.exists():
        shutil.copy2(path, snapshot)


def refresh_installed_snapshot(path: Path) -> None:
    snapshot = path.with_name(path.name + ".night-light-control.installed")
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{snapshot.name}.", suffix=".tmp", dir=snapshot.parent
        )
        os.close(descriptor)
        shutil.copy2(path, temporary)
        os.replace(temporary, snapshot)
        temporary = None
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def managed_file_was_changed(path: Path) -> bool:
    snapshot = path.with_name(path.name + ".night-light-control.installed")
    return snapshot.exists() and path.exists() and path.read_bytes() != snapshot.read_bytes()


def backup_managed_file(destination: Path, new_content: bytes) -> None:
    """Preserve a pre-existing same-named user file before replacing it."""
    backup = destination.with_name(destination.name + ".night-light-control.bak")
    if destination.is_symlink():
        raise OSError(f"No se puede gestionar un enlace simbólico: {destination}")
    if destination.exists() and not backup.exists():
        shutil.copy2(destination, backup)


def copy_managed_file(source: Path, destination: Path, mode: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise OSError(f"No se puede gestionar un enlace simbólico: {destination}")
    if managed_file_was_changed(destination):
        print(f"  Aviso: se conserva el archivo modificado por el usuario: {destination}")
        return
    backup_managed_file(destination, source.read_bytes())
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        os.close(descriptor)
        shutil.copy2(source, temporary)
        Path(temporary).chmod(mode)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
    if destination.with_name(destination.name + ".night-light-control.installed").exists():
        refresh_installed_snapshot(destination)
    else:
        save_installed_snapshot(destination)


def write_managed_file(content: str, destination: Path, mode: int) -> None:
    encoded = content.encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise OSError(f"No se puede gestionar un enlace simbólico: {destination}")
    if managed_file_was_changed(destination):
        print(f"  Aviso: se conserva el archivo modificado por el usuario: {destination}")
        return
    backup_managed_file(destination, encoded)
    atomic_write_text(destination, content, mode)
    if destination.with_name(destination.name + ".night-light-control.installed").exists():
        refresh_installed_snapshot(destination)
    else:
        save_installed_snapshot(destination)


def write_config(path: Path, content: str) -> None:
    if path.is_symlink():
        path.write_text(content, encoding="utf-8")
        return
    mode = path.stat().st_mode & 0o7777 if path.exists() else None
    atomic_write_text(path, content, mode)


def append_once(path: Path, marker: str, block: str) -> bool:
    if not path.exists() or marker in path.read_text(encoding="utf-8"):
        return False
    backup_once(path)
    updated = path.read_text(encoding="utf-8") + "\n" + block.strip() + "\n"
    write_config(path, updated)
    save_installed_snapshot(path)
    return True


def install_files() -> None:
    for directory in (BIN, APPS, ICONS):
        directory.mkdir(parents=True, exist_ok=True)

    copy_managed_file(ROOT / "src/night_light_control.py", BIN / "night-light-control", 0o755)
    copy_managed_file(ROOT / "src/brightness_control.py", BIN / "brightness-control", 0o755)
    copy_managed_file(ROOT / "src/ui_accessibility.py", BIN / "ui_accessibility.py", 0o644)
    copy_managed_file(ROOT / "src/hyprsunset_backend.py", BIN / "hyprsunset_backend.py", 0o644)
    copy_managed_file(ROOT / "src/brightness_utils.py", BIN / "brightness_utils.py", 0o644)
    copy_managed_file(ROOT / "src/schedule_utils.py", BIN / "schedule_utils.py", 0o644)
    copy_managed_file(ROOT / "bin/night-light-toggle", BIN / "night-light-toggle", 0o755)
    copy_managed_file(ROOT / "bin/night-light-status", BIN / "night-light-status", 0o755)
    copy_managed_file(ROOT / "bin/night-light", BIN / "night-light", 0o755)
    copy_managed_file(ROOT / "bin/brightness-step", BIN / "brightness-step", 0o755)
    copy_managed_file(ROOT / "data/night-light-control.svg", ICONS / "night-light-control.svg", 0o644)
    copy_managed_file(ROOT / "data/brightness-control.svg", ICONS / "brightness-control.svg", 0o644)

    desktop = (ROOT / "data/night-light-control.desktop.in").read_text(encoding="utf-8")
    desktop = desktop.replace("@APP_EXEC@", desktop_argument(BIN / "night-light-control"))
    write_managed_file(desktop, APPS / "night-light-control.desktop", 0o644)

    brightness_desktop = (ROOT / "data/brightness-control.desktop.in").read_text(encoding="utf-8")
    brightness_desktop = brightness_desktop.replace(
        "@BRIGHTNESS_EXEC@", desktop_argument(BIN / "brightness-control")
    )
    write_managed_file(brightness_desktop, APPS / "brightness-control.desktop", 0o644)

    schedule = HYPR / "hyprsunset.conf"
    # Keep an existing personal file or symlink untouched; only seed a missing path.
    if not schedule.exists() and not schedule.is_symlink():
        template = (ROOT / "data/hyprsunset.conf").read_text(encoding="utf-8")
        atomic_write_text(schedule, template, 0o644)


def desktop_argument(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace('"', '\\"')


def remember_service_state() -> None:
    if SERVICE_STATE.exists():
        return
    try:
        enabled_result = subprocess.run(
            ("systemctl", "--user", "is-enabled", "hyprsunset.service"),
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
        enabled = enabled_result.returncode == 0 and enabled_result.stdout.strip() in {
            "enabled",
            "enabled-runtime",
        }
    except (OSError, subprocess.TimeoutExpired):
        enabled = False
    state = {
        "active": run_optional("systemctl", "--user", "is-active", "hyprsunset.service"),
        "enabled": enabled,
    }
    atomic_write_text(SERVICE_STATE, json.dumps(state, indent=2) + "\n", 0o600)


def integrate_hyprland() -> None:
    bindings = HYPR / "bindings.conf"
    bindings_text = bindings.read_text(encoding="utf-8") if bindings.exists() else ""
    has_super_ctrl_n = bool(
        re.search(
            r"(?mi)^\s*bind[a-z]*\s*=\s*SUPER\s+CTRL\s*,\s*N\b",
            bindings_text,
        )
    )
    if bindings.exists() and "night-light-toggle" not in bindings_text and not has_super_ctrl_n:
        append_once(
            bindings,
            "BEGIN NIGHT LIGHT CONTROL",
            """# BEGIN NIGHT LIGHT CONTROL
unbind = SUPER CTRL, N
bindd = SUPER CTRL, N, Toggle Night Light, exec, ~/.local/bin/night-light-toggle
# END NIGHT LIGHT CONTROL""",
        )
    elif has_super_ctrl_n and "night-light-toggle" not in bindings_text:
        print("  Aviso: no se añadió Super+Ctrl+N porque ya existe otra combinación.")

    hyprland = HYPR / "hyprland.conf"
    if hyprland.exists():
        text = hyprland.read_text(encoding="utf-8")
        old_size = "windowrule = size 500 610, match:class com.snowflake.NightLight"
        new_size = "windowrule = size 620 650, match:class com.snowflake.NightLight"
        upgrade_marker = "BEGIN NIGHT LIGHT CONTROL SIZE UPGRADE"
        backup = hyprland.with_name(hyprland.name + ".night-light-control.bak")
        backup_had_old_size = (
            backup.exists() and old_size in backup.read_text(encoding="utf-8")
        )
        size_to_wrap = old_size if old_size in text else new_size
        if upgrade_marker not in text and (
            old_size in text or (new_size in text and backup_had_old_size)
        ):
            backup_once(hyprland)
            upgrade_block = f"""# BEGIN NIGHT LIGHT CONTROL SIZE UPGRADE
{new_size}
# END NIGHT LIGHT CONTROL SIZE UPGRADE"""
            write_config(hyprland, text.replace(size_to_wrap, upgrade_block, 1))
            save_installed_snapshot(hyprland)
        if "com.snowflake.NightLight" not in hyprland.read_text(encoding="utf-8"):
            append_once(
                hyprland,
                "BEGIN NIGHT LIGHT CONTROL",
                """# BEGIN NIGHT LIGHT CONTROL
windowrule = float on, match:class com.snowflake.NightLight
windowrule = center on, match:class com.snowflake.NightLight
windowrule = size 620 650, match:class com.snowflake.NightLight
# END NIGHT LIGHT CONTROL""",
            )
        if "com.snowflake.Brightness" not in hyprland.read_text(encoding="utf-8"):
            append_once(
                hyprland,
                "BEGIN BRIGHTNESS CONTROL",
                """# BEGIN BRIGHTNESS CONTROL
windowrule = float on, match:class com.snowflake.Brightness
windowrule = center on, match:class com.snowflake.Brightness
windowrule = size 540 455, match:class com.snowflake.Brightness
# END BRIGHTNESS CONTROL""",
            )


def ensure_jsonc_string_property(text: str, object_key: str, property_key: str, value: str) -> str:
    """Add one direct property to a named top-level JSONC object if absent."""
    parsed = scan_jsonc(text)
    if parsed is None:
        return text
    tokens, pairs = parsed
    object_start = object_end = None
    for token_start, token_end, current, containers in tokens:
        if current != object_key or containers != ("{",):
            continue
        following = skip_jsonc_trivia(text, token_end, len(text))
        if following >= len(text) or text[following] != ":":
            continue
        following = skip_jsonc_trivia(text, following + 1, len(text))
        if following < len(text) and text[following] == "{" and following in pairs:
            object_start, object_end = following, pairs[following]
            break
    if object_start is None or object_end is None:
        return text

    for token_start, token_end, current, containers in tokens:
        if current != property_key or containers != ("{", "{"):
            continue
        if object_start < token_start < object_end:
            return text

    closing = object_end - 1
    interior_start = object_start + 1
    interior = text[interior_start:closing]
    trailing = interior[len(interior.rstrip()):]
    content = interior[:-len(trailing)] if trailing else interior
    last = len(content.rstrip()) - 1
    separator = "," if last >= 0 and content[last] not in "{," else ""

    # Insert relative to the object boundary, not the whole document.  The
    # latter happens to work for pretty-printed objects but duplicates the
    # surrounding prefix when the module is compact and on one line.
    if "\n" not in interior and "\r" not in interior:
        insertion = f'{separator} "{property_key}": "{value}"'
    else:
        closing_indent = trailing[trailing.rfind("\n") + 1:] if trailing else ""
        property_indent = closing_indent + "  "
        insertion = (
            separator + f'\n{property_indent}"{property_key}": "{value}"'
        )
    return text[:interior_start] + content + insertion + trailing + text[closing:]


def integrate_waybar() -> None:
    config = next((candidate for candidate in (WAYBAR / "config.jsonc", WAYBAR / "config") if candidate.exists()), None)
    if config is not None:
        text = config.read_text(encoding="utf-8")
        if scan_jsonc(text) is None:
            print(f"  Aviso: no se modificó Waybar porque {config} no es JSONC válido.")
            return
        changed = False
        updated = replace_jsonc_string_property(
            text,
            "backlight",
            "on-click",
            lambda value: (
                "~/.local/bin/brightness-control"
                if value.startswith("omarchy-swayosd-brightness ")
                else value
            ),
        )
        updated = replace_jsonc_string_property(
            updated,
            "backlight",
            "on-scroll-up",
            lambda value: "~/.local/bin/brightness-step +"
            if value in {"omarchy-brightness-display +1%", "~/.local/bin/brightness-step +"}
            else value,
        )
        updated = replace_jsonc_string_property(
            updated,
            "backlight",
            "on-scroll-down",
            lambda value: "~/.local/bin/brightness-step -"
            if value in {"omarchy-brightness-display 1%-", "~/.local/bin/brightness-step -"}
            else value,
        )
        if updated != text:
            text = updated
            changed = True

        migrated = replace_jsonc_string_property(
            text,
            "custom/nightlight",
            "on-click",
            lambda value: (
                "~/.local/bin/night-light --cycle"
                if value in OWN_NIGHTLIGHT_CLICKS
                else value
            ),
        )
        migrated = ensure_jsonc_string_property(
            migrated,
            "custom/nightlight",
            "on-click-middle",
            "~/.local/bin/night-light-control",
        )
        if migrated != text:
            text = migrated
            changed = True

        tokens = scan_jsonc(text)[0]
        has_module = any(
            value == "custom/nightlight" and containers == ("{",)
            for _start, _end, value, containers in tokens
        )
        has_item = any(
            value == "custom/nightlight" and "[" in containers
            for _start, _end, value, containers in tokens
        )
        if not has_item:
            anchor = '"group/tray-expander",'
            module_anchor = '  "bluetooth": {'
            if anchor in text and module_anchor in text:
                text = text.replace(
                    anchor,
                    anchor + '\n    // BEGIN NIGHT LIGHT CONTROL ITEM\n'
                    '    "custom/nightlight",\n'
                    '    // END NIGHT LIGHT CONTROL ITEM',
                    1,
                )
                changed = True
            elif anchor not in text or module_anchor not in text:
                print("  Aviso: no se añadió Luz nocturna a Waybar; faltan anchors seguros.")
        if not has_module and 'night-light-status' not in text:
            anchor = '  "bluetooth": {'
            module = '''  // BEGIN NIGHT LIGHT CONTROL MODULE
  "custom/nightlight": {
    "exec": "~/.local/bin/night-light-status",
    "return-type": "json",
    "format": "{}",
    "interval": 2,
    "tooltip": true,
    "on-click": "~/.local/bin/night-light --cycle",
    "on-click-middle": "~/.local/bin/night-light-control",
    "on-click-right": "~/.local/bin/night-light-toggle"
  },
  // END NIGHT LIGHT CONTROL MODULE
'''
            if anchor in text:
                text = text.replace(anchor, module + anchor, 1)
                changed = True
        if changed:
            backup_once(config)
            write_config(config, text)
            save_installed_snapshot(config)

    style = WAYBAR / "style.css"
    if style.exists():
        style_text = style.read_text(encoding="utf-8")
        if "#custom-nightlight" not in style_text:
            append_once(
                style,
                "#custom-nightlight",
                """/* BEGIN NIGHT LIGHT CONTROL */
#custom-nightlight { min-width: 12px; margin: 0 7.5px; font-size: 14px; }
#custom-nightlight.active { color: #e69875; }
#custom-nightlight.inactive { opacity: 0.72; }
#custom-nightlight.unavailable { opacity: 0.45; }
/* END NIGHT LIGHT CONTROL */""",
            )
        elif "#custom-nightlight.unavailable" not in style_text:
            append_once(
                style,
                "#custom-nightlight.unavailable",
                "#custom-nightlight.unavailable { opacity: 0.45; }",
            )


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


def main() -> int:
    try:
        install_files()
        integrate_hyprland()
        integrate_waybar()
    except OSError as error:
        print(f"Error: no se pudo completar la instalación: {error}")
        return 1
    optional = (
        ("actualizar la base de lanzadores", ("update-desktop-database", str(APPS))),
        ("recargar Hyprland", ("hyprctl", "reload")),
        ("reiniciar Waybar", ("omarchy", "restart", "waybar")),
    )
    warnings = [label for label, args in optional if not run_optional(*args)]
    try:
        remember_service_state()
    except OSError as error:
        print(f"  Aviso: no se pudo guardar el estado previo del servicio: {error}")
    service_ok = run_optional(
        "systemctl", "--user", "enable", "--now", "hyprsunset.service"
    )
    print("✓ Luz nocturna y Brillo instalados para", os.environ.get("USER", HOME.name))
    print("  Abre 'Luz nocturna' o 'Brillo' desde el menú.")
    for warning in warnings:
        print(f"  Aviso: no se pudo {warning}; vuelve a iniciar la sesión si es necesario.")
    if not service_ok:
        print("  Error: no se pudo habilitar hyprsunset.service.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
