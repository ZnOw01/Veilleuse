#!/usr/bin/python3
"""Safe per-user uninstaller for Night Light Control."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from schedule_utils import CONFIG_DIR, xdg_config_home, xdg_data_home

HOME = Path.home()
XDG_CONFIG = xdg_config_home()
XDG_DATA = xdg_data_home()
BIN = HOME / ".local/bin"
APPS = XDG_DATA / "applications"
ICON = XDG_DATA / "icons/hicolor/scalable/apps/night-light-control.svg"
BRIGHTNESS_ICON = XDG_DATA / "icons/hicolor/scalable/apps/brightness-control.svg"
HYPR = XDG_CONFIG / "hypr"
WAYBAR = XDG_CONFIG / "waybar"
SERVICE_STATE = CONFIG_DIR / "install-state.json"
OWN_NIGHTLIGHT_CLICK = "~/.local/bin/night-light --cycle"
OWN_NIGHTLIGHT_MIDDLE_CLICK = "~/.local/bin/night-light-control"


def remove_or_restore(path: Path, expected: bytes | Path | None = None) -> None:
    """Remove only files that still match an install snapshot or known payload."""
    if isinstance(expected, Path):
        expected = expected.read_bytes()
    if path.is_symlink():
        path.with_name(path.name + ".night-light-control.installed").unlink(missing_ok=True)
        return
    backup = path.with_name(path.name + ".night-light-control.bak")
    snapshot = path.with_name(path.name + ".night-light-control.installed")
    if snapshot.exists():
        owned = path.exists() and path.read_bytes() == snapshot.read_bytes()
        if owned:
            path.unlink(missing_ok=True)
            if backup.exists():
                backup.replace(path)
        snapshot.unlink(missing_ok=True)
        return
    if expected is not None and path.exists() and path.read_bytes() == expected:
        path.unlink(missing_ok=True)
        if backup.exists():
            backup.replace(path)


def rewrite(path: Path, transform) -> None:
    if not path.exists():
        return
    original = path.read_text(encoding="utf-8")
    updated = transform(original)
    if updated != original:
        path.write_text(updated, encoding="utf-8")


def remove_owned_integration(path: Path, transform) -> None:
    """Restore exact pre-install bytes, or remove only our marked blocks."""
    if path.is_symlink():
        path.with_name(path.name + ".night-light-control.installed").unlink(missing_ok=True)
        return
    snapshot = path.with_name(path.name + ".night-light-control.installed")
    backup = path.with_name(path.name + ".night-light-control.bak")
    if not snapshot.exists():
        if path.exists() and any(
            marker in path.read_text(encoding="utf-8")
            for marker in (
                "BEGIN NIGHT LIGHT CONTROL",
                "BEGIN BRIGHTNESS CONTROL",
            )
        ):
            rewrite(path, transform)
        return
    if path.exists() and path.read_bytes() == snapshot.read_bytes():
        if backup.exists():
            path.unlink()
            backup.replace(path)
        else:
            path.unlink()
        snapshot.unlink(missing_ok=True)
        return
    rewrite(path, transform)
    if path.exists():
        # The transformed file is now the new user-owned baseline. Keeping the
        # old backup would discard later user changes on a future install cycle.
        backup.unlink(missing_ok=True)
    snapshot.unlink(missing_ok=True)


def remove_hypr_integration() -> None:
    def clean_bindings(text: str) -> str:
        return remove_marked_block(text, "# BEGIN NIGHT LIGHT CONTROL", "# END NIGHT LIGHT CONTROL")

    remove_owned_integration(HYPR / "bindings.conf", clean_bindings)
    remove_owned_integration(HYPR / "hyprland.conf", clean_hyprland_rules)


def clean_hyprland_rules(text: str) -> str:
    old_size = "windowrule = size 500 610, match:class com.snowflake.NightLight"
    text = replace_marked_block(
        text,
        "# BEGIN NIGHT LIGHT CONTROL SIZE UPGRADE",
        "# END NIGHT LIGHT CONTROL SIZE UPGRADE",
        "\n" + old_size + "\n",
    )
    text = remove_marked_block(text, "# BEGIN NIGHT LIGHT CONTROL", "# END NIGHT LIGHT CONTROL")
    return remove_marked_block(text, "# BEGIN BRIGHTNESS CONTROL", "# END BRIGHTNESS CONTROL")


def replace_marked_block(text: str, begin: str, end: str, replacement: str) -> str:
    pattern = rf"(?ms)^[ \t]*{re.escape(begin)}[ \t]*\r?\n.*?^[ \t]*{re.escape(end)}[ \t]*(?:\r?\n|$)"
    return re.sub(pattern, replacement, text)


def remove_marked_block(text: str, begin: str, end: str) -> str:
    return replace_marked_block(text, begin, end, "")


def scan_jsonc(text: str):
    tokens = []
    pairs = {}
    stack = []
    index = 0
    while index < len(text):
        if text.startswith("//", index):
            newline = text.find("\n", index + 2)
            index = len(text) if newline < 0 else newline + 1
            continue
        if text.startswith("/*", index):
            closing = text.find("*/", index + 2)
            if closing < 0:
                return None
            index = closing + 2
            continue
        char = text[index]
        if char == '"':
            start = index
            index += 1
            escaped = False
            while index < len(text):
                char = text[index]
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    break
                index += 1
            if index >= len(text):
                return None
            tokens.append((start, index + 1, text[start + 1:index], tuple(item[0] for item in stack)))
        elif char in "{[":
            stack.append((char, index))
        elif char in "}]":
            expected = "{" if char == "}" else "["
            if not stack or stack[-1][0] != expected:
                return None
            _, opening = stack.pop()
            pairs[opening] = index + 1
        index += 1
    if stack:
        return None
    return tokens, pairs


def skip_jsonc_trivia(text: str, index: int, limit: int) -> int:
    while index < limit:
        if text[index].isspace():
            index += 1
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index + 2, limit)
            if newline < 0:
                return limit
            index = newline + 1
            continue
        if text.startswith("/*", index):
            closing = text.find("*/", index + 2, limit)
            if closing < 0:
                return limit
            index = closing + 2
            continue
        break
    return index


def replace_jsonc_string_property(text: str, object_key: str, property_key: str, transform) -> str:
    parsed = scan_jsonc(text)
    if parsed is None:
        return text
    tokens, pairs = parsed
    token_by_start = {start: (end, value, containers) for start, end, value, containers in tokens}
    object_start = None
    object_end = None
    for _, token_end, value, containers in tokens:
        if value != object_key or containers != ("{",):
            continue
        following = skip_jsonc_trivia(text, token_end, len(text))
        if following >= len(text) or text[following] != ":":
            continue
        following = skip_jsonc_trivia(text, following + 1, len(text))
        if following < len(text) and text[following] == "{" and following in pairs:
            object_start = following
            object_end = pairs[following]
            break
    if object_start is None or object_end is None:
        return text

    for token_start, token_end, value, containers in tokens:
        if (
            value != property_key
            or containers != ("{", "{")
            or token_start <= object_start
            or token_end > object_end
        ):
            continue
        following = skip_jsonc_trivia(text, token_end, object_end)
        if following >= object_end or text[following] != ":":
            continue
        following = skip_jsonc_trivia(text, following + 1, object_end)
        value_token = token_by_start.get(following)
        if value_token is None:
            continue
        value_end, current, _ = value_token
        replacement = transform(current)
        if replacement == current:
            return text
        return text[:following + 1] + replacement + text[value_end - 1:]
    return text


def remove_jsonc_string_property(
    text: str, object_key: str, property_key: str, expected_value: str | None = None
) -> str:
    parsed = scan_jsonc(text)
    if parsed is None:
        return text
    tokens, pairs = parsed
    object_start = object_end = None
    for token_start, token_end, value, containers in tokens:
        if value != object_key or containers != ("{",):
            continue
        following = skip_jsonc_trivia(text, token_end, len(text))
        following = skip_jsonc_trivia(text, following + 1, len(text)) if following < len(text) and text[following] == ":" else len(text)
        if following < len(text) and text[following] == "{" and following in pairs:
            object_start, object_end = following, pairs[following]
            break
    if object_start is None or object_end is None:
        return text
    for token_start, token_end, value, containers in tokens:
        if value != property_key or containers != ("{", "{") or not object_start < token_start < object_end:
            continue
        following = skip_jsonc_trivia(text, token_end, object_end)
        if following >= object_end or text[following] != ":":
            continue
        following = skip_jsonc_trivia(text, following + 1, object_end)
        value_token = next(
            (item for item in tokens if item[0] == following), None
        )
        if value_token is None:
            return text
        value_end = value_token[1]
        current = value_token[2]
        if expected_value is not None and current != expected_value:
            continue
        after = skip_jsonc_trivia(text, value_end, object_end)
        previous_comma = None
        if after < object_end and text[after] == ",":
            value_end = after + 1
        else:
            previous = token_start - 1
            while previous >= object_start and text[previous].isspace():
                previous -= 1
            if previous >= object_start and text[previous] == ",":
                previous_comma = previous
        line_start = text.rfind("\n", 0, token_start) + 1
        line_end = text.find("\n", value_end, object_end)
        if line_end < 0:
            line_end = value_end
        else:
            line_end += 1
        if not text[line_start:token_start].strip():
            result = text[:line_start] + text[line_end:]
        else:
            result = text[:token_start] + text[value_end:]
        if previous_comma is not None:
            result = result[:previous_comma] + result[previous_comma + 1:]
        return result
    return text


def clean_waybar_config(text: str) -> str:
    if scan_jsonc(text) is None:
        return text
    old_click = "~/.local/bin/brightness-control"
    native_click = (
        "omarchy-swayosd-brightness $(brightnessctl -c backlight -m "
        "| cut -d, -f4 | tr -d '%')"
    )
    text = replace_jsonc_string_property(
        text,
        "backlight",
        "on-click",
        lambda value: native_click if value == old_click else value,
    )
    text = replace_jsonc_string_property(
        text,
        "backlight",
        "on-scroll-up",
        lambda value: "omarchy-brightness-display +1%"
        if value == "~/.local/bin/brightness-step +" else value,
    )
    text = replace_jsonc_string_property(
        text,
        "backlight",
        "on-scroll-down",
        lambda value: "omarchy-brightness-display 1%-"
        if value == "~/.local/bin/brightness-step -" else value,
    )
    text = replace_jsonc_string_property(
        text,
        "custom/nightlight",
        "on-click",
        lambda value: "~/.local/bin/night-light-control"
        if value == OWN_NIGHTLIGHT_CLICK else value,
    )
    text = remove_jsonc_string_property(
        text,
        "custom/nightlight",
        "on-click-middle",
        OWN_NIGHTLIGHT_MIDDLE_CLICK,
    )
    text = remove_marked_block(
        text, "// BEGIN NIGHT LIGHT CONTROL ITEM", "// END NIGHT LIGHT CONTROL ITEM"
    )
    return remove_marked_block(
        text, "// BEGIN NIGHT LIGHT CONTROL MODULE", "// END NIGHT LIGHT CONTROL MODULE"
    )


def remove_waybar_integration() -> None:
    def clean_style(text: str) -> str:
        return remove_marked_block(
            text, "/* BEGIN NIGHT LIGHT CONTROL */", "/* END NIGHT LIGHT CONTROL */"
        )

    config = next((candidate for candidate in (WAYBAR / "config.jsonc", WAYBAR / "config") if candidate.exists()), None)
    if config is not None:
        remove_owned_integration(config, clean_waybar_config)
    remove_owned_integration(WAYBAR / "style.css", clean_style)


def desktop_argument(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace('"', '\\"')


def expected_payload(path: Path):
    payloads = {
        BIN / "night-light-control": ROOT / "src/night_light_control.py",
        BIN / "brightness-control": ROOT / "src/brightness_control.py",
        BIN / "ui_accessibility.py": ROOT / "src/ui_accessibility.py",
        BIN / "hyprsunset_backend.py": ROOT / "src/hyprsunset_backend.py",
        BIN / "brightness_utils.py": ROOT / "src/brightness_utils.py",
        BIN / "schedule_utils.py": ROOT / "src/schedule_utils.py",
        BIN / "night-light-toggle": ROOT / "bin/night-light-toggle",
        BIN / "night-light-status": ROOT / "bin/night-light-status",
        BIN / "night-light": ROOT / "bin/night-light",
        BIN / "brightness-step": ROOT / "bin/brightness-step",
        ICON: ROOT / "data/night-light-control.svg",
        BRIGHTNESS_ICON: ROOT / "data/brightness-control.svg",
    }
    source = payloads.get(path)
    if source is not None:
        return source
    if path == APPS / "night-light-control.desktop":
        text = (ROOT / "data/night-light-control.desktop.in").read_text(encoding="utf-8")
        return text.replace("@APP_EXEC@", desktop_argument(BIN / "night-light-control")).encode()
    if path == APPS / "brightness-control.desktop":
        text = (ROOT / "data/brightness-control.desktop.in").read_text(encoding="utf-8")
        return text.replace(
            "@BRIGHTNESS_EXEC@", desktop_argument(BIN / "brightness-control")
        ).encode()
    return None


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


def restore_service_state() -> bool:
    state = None
    if SERVICE_STATE.exists():
        try:
            import json

            state = json.loads(SERVICE_STATE.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            state = None
    if not state:
        return True
    enabled = bool(state.get("enabled"))
    active = bool(state.get("active"))
    results = [
        run_optional(
            "systemctl", "--user", "enable" if enabled else "disable", "hyprsunset.service"
        ),
        run_optional(
            "systemctl", "--user", "start" if active else "stop", "hyprsunset.service"
        ),
    ]
    if all(results):
        SERVICE_STATE.unlink(missing_ok=True)
        return True
    return False


def main() -> int:
    try:
        for path in (
            BIN / "night-light-control",
            BIN / "brightness-control",
            BIN / "ui_accessibility.py",
            BIN / "hyprsunset_backend.py",
            BIN / "brightness_utils.py",
            BIN / "schedule_utils.py",
            BIN / "night-light-toggle",
            BIN / "night-light-status",
            BIN / "night-light",
            BIN / "brightness-step",
            APPS / "night-light-control.desktop",
            APPS / "brightness-control.desktop",
            ICON,
            BRIGHTNESS_ICON,
        ):
            remove_or_restore(path, expected_payload(path))

        remove_hypr_integration()
        remove_waybar_integration()
    except OSError as error:
        print(f"Error: no se pudo completar la desinstalación: {error}")
        return 1

    warnings = []
    if not restore_service_state():
        warnings.append("restaurar el estado de hyprsunset.service")
    if not run_optional("update-desktop-database", str(APPS)):
        warnings.append("actualizar la base de lanzadores")
    if not run_optional("hyprctl", "reload"):
        warnings.append("recargar Hyprland")
    if not run_optional("omarchy", "restart", "waybar"):
        warnings.append("reiniciar Waybar")
    print("✓ Aplicación e integraciones desinstaladas.")
    print("  Tu horario personal de hyprsunset se conservó por seguridad.")
    for warning in warnings:
        print(f"  Aviso: no se pudo {warning}.")
    return 1 if warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())
