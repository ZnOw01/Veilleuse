#! /usr/bin/python3
"""Reversible Hyprland shortcut management for the Veilleuse plugin.

Only the user bindings file at ``$XDG_CONFIG_HOME/hypr/bindings.lua`` is ever
touched, and only inside one unique Veilleuse marker block.  Omarchy 4
executes bindings.lua as Lua and exposes the ``o`` helpers table, so the
block is written in its documented ``o.bind`` form::

    -- >>> Veilleuse shortcut >>>
    o.bind("SUPER + V", "Veilleuse", "omarchy-shell -q io.github.znow01.veilleuse toggleNightlight")
    -- <<< Veilleuse shortcut <<<

``install_shortcut`` validates the requested keys against a conservative
allowlist, refuses keys already bound outside the marker block, appends or
replaces the block, keeps a single ``bindings.lua.bak`` copy of the original on
the first write, and preserves the file mode.  ``remove_shortcut`` drops exactly
the marker block so the file returns to its exact pre-install bytes (user
edits elsewhere are preserved).  ``shortcut_status`` only reads.

Nothing in this module — or anywhere else in the plugin helper — installs a
shortcut automatically.  Every write is the result of an explicit ``shortcut
install`` or ``shortcut remove`` invocation.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

PLUGIN_ID = "io.github.znow01.veilleuse"
FIXED_COMMAND = "omarchy-shell -q io.github.znow01.veilleuse toggleNightlight"
MARKER_OPEN = "-- >>> Veilleuse shortcut >>>"
MARKER_CLOSE = "-- <<< Veilleuse shortcut <<<"
SHORTCUT_DESCRIPTION = "Veilleuse"
BACKUP_SUFFIX = ".bak"
NEW_FILE_MODE = 0o644
RELOAD_TIMEOUT = 1.0
RELOAD_EXIT_CODE = 124

_MODIFIERS = frozenset(
    {"SUPER", "CTRL", "ALT", "SHIFT", "MOD1", "MOD2", "MOD3", "MOD4", "MOD5"}
)
_NAMED_KEYS = frozenset(
    {
        "SPACE", "RETURN", "ESCAPE", "TAB", "BACKSPACE", "DELETE", "INSERT",
        "HOME", "END", "PAGE_UP", "PAGE_DOWN", "PRINT", "PAUSE", "CAPS_LOCK",
        "NUM_LOCK", "SCROLL_LOCK", "MENU", "LEFT", "RIGHT", "UP", "DOWN",
    }
)
_FUNCTION_KEY = re.compile(r"^F(?:[1-9]|1[0-9]|2[0-4])$")
_SINGLE_KEY = re.compile(r"^[A-Z0-9]$")
# Omarchy 4 bindings.lua: o.bind/hl.bind install, hl.unbind removes.
_BIND_CALL = re.compile(r"(?m)\b(?:o|hl)\.(?:bind|unbind)\s*\(")


# --------------------------------------------------------------------------- \
# paths

def xdg_config_home() -> Path:
    """XDG config home honoring $XDG_CONFIG_HOME when absolute."""
    value = os.environ.get("XDG_CONFIG_HOME", "")
    candidate = Path(value).expanduser() if value else Path.home() / ".config"
    return candidate if candidate.is_absolute() else Path.home() / ".config"


def bindings_path() -> Path:
    """Path of the user Hyprland bindings file."""
    return xdg_config_home() / "hypr" / "bindings.lua"


# --------------------------------------------------------------------------- \
# bounded subprocess (best-effort hyprctl reload only)

def run_command(args, *, timeout=RELOAD_TIMEOUT):
    """Run one command array without a shell under a bounded timeout."""
    try:
        return subprocess.run(
            list(args),
            text=True,
            capture_output=True,
            check=False,
            timeout=float(timeout),
        )
    except subprocess.TimeoutExpired as error:
        result = subprocess.CompletedProcess(
            list(args), RELOAD_EXIT_CODE, "", str(error.stderr or error)
        )
        return result
    except FileNotFoundError as error:
        return subprocess.CompletedProcess(list(args), 127, "", str(error))
    except OSError as error:
        return subprocess.CompletedProcess(list(args), 127, "", str(error))


def _reload():
    """Best-effort hyprctl reload; never fails the underlying operation."""
    result = run_command(("hyprctl", "reload"))
    if result.returncode == 0:
        return {"ok": True, "error": None}
    detail = (result.stderr or "").strip()
    return {
        "ok": False,
        "error": detail or "hyprctl reload no está disponible",
    }


def _atomic_write_text(path, text, mode):
    """Write text atomically (temp file + os.replace) preserving mode."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        temporary = None
        try:
            directory_fd = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def _detect_eol(text):
    return "\r\n" if "\r\n" in text else "\n"


# --------------------------------------------------------------------------- \
# key validation

def parse_keys(spec):
    """Validate ``MODS, KEY`` and return ``(mods, key)``.

    Modifiers come from a fixed set, may be repeated neither within the slot
    nor with the key, and the key must be an allowed letter/digit, ``F1``-``F24``
    or a named key.  Anything that could smuggle a second binding, a comment or
    a newline into the generated ``o.bind`` call is rejected.
    """
    if not isinstance(spec, str):
        raise ValueError("Las teclas deben ser un texto")
    spec = spec.strip()
    if not spec:
        raise ValueError("Las teclas no pueden estar vacías")
    if "\n" in spec or "\r" in spec:
        raise ValueError("Las teclas no pueden contener saltos de línea")
    parts = [part.strip() for part in spec.split(",")]
    if len(parts) != 2 or not parts[1]:
        raise ValueError('El atajo debe usar el formato "MOD, TECLA" (p. ej. "SUPER, V")')
    mods = []
    for token in parts[0].split():
        token = token.upper()
        if token not in _MODIFIERS:
            raise ValueError(f"Modificador no permitido: {token}")
        if token in mods:
            raise ValueError(f"Modificador repetido: {token}")
        mods.append(token)
    key = parts[1].upper()
    if not (
        _SINGLE_KEY.fullmatch(key)
        or _FUNCTION_KEY.fullmatch(key)
        or key in _NAMED_KEYS
    ):
        raise ValueError(f"Tecla no permitida: {parts[1]}")
    return tuple(sorted(mods)), key


def _format_keys(mods, key):
    """Spell ``MODS + KEY`` the way Omarchy 4 bindings.lua does."""
    return " + ".join((*sorted(mods), key))


def canonical_keys(spec):
    """Return the canonical ``MODS + KEY`` spelling for a validated spec."""
    mods, key = parse_keys(spec)
    return _format_keys(mods, key)


# --------------------------------------------------------------------------- \
# marker block editing (pure text operations)

def _block_text(keys_spec, eol):
    keys = canonical_keys(keys_spec)
    call = f'o.bind("{keys}", "{SHORTCUT_DESCRIPTION}", "{FIXED_COMMAND}")'
    return f"{MARKER_OPEN}{eol}{call}{eol}{MARKER_CLOSE}{eol}"


def find_block(text):
    """Return ``(start, end)`` of the marker block, or ``None``.

    ``end`` covers the closing marker and its trailing line ending.  An open
    marker without a closing one is a corrupt state and fails closed.
    """
    if not isinstance(text, str):
        raise ValueError("El contenido de bindings.lua debe ser texto")
    open_index = text.find(MARKER_OPEN)
    if open_index < 0:
        return None
    close_index = text.find(MARKER_CLOSE, open_index + len(MARKER_OPEN))
    if close_index < 0:
        raise ValueError("El bloque de atajo de Veilleuse no está cerrado")
    end = close_index + len(MARKER_CLOSE)
    for eol in ("\r\n", "\n"):
        if text.startswith(eol, end):
            end += len(eol)
            break
    return open_index, end


def install_block(text, keys_spec):
    """Insert or replace the Veilleuse marker block in ``text``.

    When appending to a non-empty file, exactly one line ending is always
    inserted before the block.  ``remove_block`` consumes exactly that one
    separator, so ``remove_block(install_block(text, keys)) == text`` holds
    for every input, including text that already ends (or not) with a newline.
    """
    eol = _detect_eol(text) if text else "\n"
    new_block = _block_text(keys_spec, eol)
    block = find_block(text)
    if block is not None:
        start, end = block
        return text[:start] + new_block + text[end:]
    if not text:
        return new_block
    return text + eol + new_block


def _block_keys(text):
    """Extract the canonical ``MODS + KEY`` of the marker block's o.bind call."""
    masked = _mask_lua(text)
    for match in _BIND_CALL.finditer(masked):
        keys_string = _first_string_arg(text, match.end())
        parsed = _parse_keys_string(keys_string) if keys_string is not None else None
        if parsed is None:
            continue
        mods, key = parsed
        return _format_keys(mods, key)
    return None


def remove_block(text):
    """Remove exactly the marker block; return ``(rest, found, keys)``.

    The single separator line ending introduced by ``install_block`` is
    consumed too, so ``remove_block(install_block(text, keys)) == text`` for
    every input.  User edits between the original content and the block keep
    the separator, so they stay untouched either way.
    """
    block = find_block(text)
    if block is None:
        return text, False, None
    start, end = block
    keys = _block_keys(text[start:end])
    prefix = start
    eol = _detect_eol(text) if text else "\n"
    if start > 0 and text[:start].endswith(eol + eol):
        prefix = start - len(eol)
    elif start > 0 and text[:start].endswith(eol):
        prefix = start - len(eol)
    return text[:prefix] + text[end:], True, keys


# --------------------------------------------------------------------------- \
# collision detection

def _mask_lua(text):
    """Mask comments and string literals with spaces, preserving offsets."""
    if not isinstance(text, str):
        raise ValueError("El contenido de bindings.lua debe ser texto")
    chars = list(text)
    length = len(chars)
    index = 0
    quote = None
    while index < length:
        char = chars[index]
        if quote is not None:
            if char == "\\":
                chars[index] = " "
                index += 1
            elif char == quote:
                quote = None
                chars[index] = " "
            elif char == "\n":
                chars[index] = "\n"
            else:
                chars[index] = " "
            index += 1
            continue
        if char == '"' or char == "'":
            quote = char
            chars[index] = " "
            index += 1
            continue
        if char == "-" and index + 1 < length and chars[index + 1] == "-":
            if index + 2 < length and chars[index + 2] == "[":
                equals = 0
                probe = index + 3
                while probe < length and chars[probe] == "=":
                    equals += 1
                    probe += 1
                if probe < length and chars[probe] == "[":
                    closer = f"]{'=' * equals}]"
                    tail = text.find(closer, probe + 1)
                    if tail < 0:
                        for pos in range(index + 2, length):
                            chars[pos] = " " if chars[pos] != "\n" else "\n"
                        index = length
                        continue
                    for pos in range(index + 2, tail + len(closer)):
                        chars[pos] = " " if chars[pos] != "\n" else "\n"
                    index = tail + len(closer)
                    continue
            for pos in range(index, length):
                if text[pos] == "\n":
                    index = pos
                    break
                chars[pos] = " "
            else:
                index = length
            continue
        if char == "[":
            equals = 0
            probe = index + 1
            while probe < length and chars[probe] == "=":
                equals += 1
                probe += 1
            if probe < length and chars[probe] == "[":
                closer = f"]{'=' * equals}]"
                tail = text.find(closer, probe + 1)
                if tail < 0:
                    for pos in range(index, length):
                        chars[pos] = " " if chars[pos] != "\n" else "\n"
                    index = length
                    continue
                for pos in range(index, tail + len(closer)):
                    chars[pos] = " " if chars[pos] != "\n" else "\n"
                index = tail + len(closer)
                continue
        index += 1
    return "".join(chars)


def _first_string_arg(text, position):
    """Return the first Lua string literal at/after ``position``, or ``None``."""
    probe = position
    length = len(text)
    while probe < length and text[probe] not in ('"', "'"):
        probe += 1
    if probe >= length:
        return None
    quote = text[probe]
    content = []
    current = probe + 1
    while current < length:
        char = text[current]
        if char == "\\":
            if current + 1 < length:
                content.append(text[current + 1])
            current += 2
            continue
        if char == quote:
            return "".join(content)
        content.append(char)
        current += 1
    return None


def _parse_keys_string(keys_string):
    """Parse an Omarchy key string like ``SUPER + V`` into ``(mods, key)``."""
    parts = [part.strip() for part in keys_string.split("+")]
    parts = [part for part in parts if part]
    if not parts:
        return None
    key = parts[-1].upper()
    if not re.fullmatch(r"[A-Z0-9_]+", key):
        return None
    mods = frozenset(part.upper() for part in parts[:-1])
    return mods, key


def _external_bindelines(text, block):
    """Yield ``(mods, key, original_line)`` for active binds outside the block.

    Only calls that survive the comment/string mask count: a masked match means
    the call name sits outside comments and string literals.  The key string is
    then read from the original text so masking never destroys it.
    """
    masked = _mask_lua(text)
    for match in _BIND_CALL.finditer(masked):
        if block is not None and match.start() >= block[0] and match.start() < block[1]:
            continue
        keys_string = _first_string_arg(text, match.end())
        parsed = _parse_keys_string(keys_string) if keys_string is not None else None
        if parsed is None:
            continue
        mods, key = parsed
        line_start = masked.rfind("\n", 0, match.start()) + 1
        line_end = masked.find("\n", match.end())
        if line_end < 0:
            line_end = len(masked)
        original_line = text[line_start:line_end].strip()
        yield mods, key, original_line


def collision(text, keys_spec):
    """Return the conflicting external bind line, or ``None``.

    Every binding outside the Veilleuse marker block is compared against the
    requested keys; bindings inside the block are the plugin's own and are
    skipped.
    """
    mods, key = parse_keys(keys_spec)
    needle = (frozenset(mods), key)
    block = find_block(text)
    for external_mods, external_key, original_line in _external_bindelines(text, block):
        if (external_mods, external_key) == needle:
            return original_line
    return None


# --------------------------------------------------------------------------- \
# status / install / remove

def shortcut_status():
    """Read-only snapshot of the shortcut and its single backup."""
    path = bindings_path()
    backup = path.with_suffix(path.suffix + BACKUP_SUFFIX)
    state = {
        "available": True,
        "file": str(path),
        "exists": path.is_file(),
        "installed": False,
        "keys": None,
        "command": FIXED_COMMAND,
        "backup": str(backup),
        "backup_exists": backup.is_file(),
        "error": None,
    }
    if not path.is_file():
        return state
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as caught:
        state["error"] = str(caught)
        return state
    try:
        block = find_block(text)
    except ValueError as caught:
        state["error"] = str(caught)
        return state
    if block is None:
        return state
    state["installed"] = True
    state["keys"] = _block_keys(text[block[0]:block[1]])
    return state


def _backup_once(path, original_text):
    """Copy the original file to ``.bak`` exactly once (one backup)."""
    backup = path.with_suffix(path.suffix + BACKUP_SUFFIX)
    if not path.exists() or backup.exists():
        return False
    mode = path.stat().st_mode & 0o7777
    _atomic_write_text(backup, original_text, mode)
    return True


def install_shortcut(keys_spec):
    """Install (or refresh) the marker block; check collisions first.

    Invalid key specs raise ``ValueError`` before any state changes; file-level
    failures (collisions, unreadable or corrupt files) are reported as an
    unavailable result and leave the file untouched.
    """
    canonical = canonical_keys(keys_spec)
    path = bindings_path()
    try:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            conflict = collision(text, keys_spec)
            if conflict is not None:
                return {
                    "available": False,
                    "error": (
                        f"El atajo {canonical} ya está asignado en bindings.lua: {conflict}"
                    ),
                }
            candidate = install_block(text, keys_spec)
        else:
            text = ""
            candidate = install_block("", keys_spec)
        backup_created = _backup_once(path, text)
        mode = path.stat().st_mode & 0o7777 if path.exists() else NEW_FILE_MODE
        _atomic_write_text(path, candidate, mode)
    except OSError as caught:
        return {"available": False, "error": str(caught)}
    except ValueError as caught:
        return {"available": False, "error": str(caught)}
    return {
        "available": True,
        "action": "install",
        "keys": canonical,
        "exists": path.is_file(),
        "backup_created": backup_created,
        "reload": _reload(),
        "error": None,
    }


def remove_shortcut():
    """Remove exactly the marker block, restoring the pre-install file.

    A file that holds nothing but the block is deleted again (a backup, if any,
    preserves the original for manual restore).  A missing or already-clean
    file is a successful no-op.
    """
    path = bindings_path()
    if not path.is_file():
        return {
            "available": True,
            "action": "remove",
            "restored": False,
            "exists": False,
            "keys": None,
            "reload": None,
            "error": None,
        }
    try:
        text = path.read_text(encoding="utf-8")
        new_text, found, keys = remove_block(text)
    except (OSError, ValueError) as caught:
        return {"available": False, "error": str(caught)}
    if not found:
        return {
            "available": True,
            "action": "remove",
            "restored": False,
            "exists": True,
            "keys": None,
            "reload": None,
            "error": None,
        }
    mode = path.stat().st_mode & 0o7777
    if not new_text:
        path.unlink(missing_ok=True)
    else:
        _atomic_write_text(path, new_text, mode)
    return {
        "available": True,
        "action": "remove",
        "restored": True,
        "exists": path.exists(),
        "keys": keys,
        "reload": _reload(),
        "error": None,
    }
