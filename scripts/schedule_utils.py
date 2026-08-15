#!/usr/bin/python3
"""Shared parsing and filesystem helpers for the Night Light tools."""

from __future__ import annotations

import contextlib
import datetime
import fcntl
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path

DEFAULT_TEMP = 3500
DAY_TEMP = 6000
NIGHT_TEMP_MIN = 2500
NIGHT_TEMP_MAX = 5000
DAY_TEMP_MIN = 5900
DAY_TEMP_MAX = 6500


def xdg_config_home() -> Path:
    value = os.environ.get("XDG_CONFIG_HOME", "")
    candidate = Path(value).expanduser() if value else Path.home() / ".config"
    return candidate if candidate.is_absolute() else Path.home() / ".config"


HYPRSUNSET_CONFIG = xdg_config_home() / "hypr" / "hyprsunset.conf"


def normalize_clock(value):
    if not isinstance(value, str):
        raise ValueError("La hora debe ser texto con formato HH:MM")
    match = re.fullmatch(r"\s*([0-9]{1,2}):([0-9]{2})\s*", value)
    if not match:
        raise ValueError("La hora debe usar el formato HH:MM")
    hour, minute = map(int, match.groups())
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("La hora está fuera de rango")
    return f"{hour:02d}:{minute:02d}"


def _coerce_integer(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} debe ser un entero")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"[+-]?[0-9]+", value.strip()):
        return int(value)
    raise ValueError(f"{field} debe ser un entero")


def _validate_temperature(temperature, minimum, maximum, field):
    value = _coerce_integer(temperature, field)
    if not minimum <= value <= maximum:
        raise ValueError(f"{field} fuera de rango ({minimum}-{maximum} K)")
    return value


def clamp_day_temperature(temperature):
    value = _coerce_integer(temperature, "La temperatura diurna")
    return max(DAY_TEMP_MIN, min(DAY_TEMP_MAX, value))


def clamp_night_temperature(temperature):
    value = _coerce_integer(temperature, "La temperatura nocturna")
    return max(NIGHT_TEMP_MIN, min(NIGHT_TEMP_MAX, value))


def default_schedule():
    return {
        "day_time": "06:00",
        "day_temp": DAY_TEMP,
        "night_time": "15:30",
        "night_temp": DEFAULT_TEMP,
    }


def _mask_comments(text):
    """Replace comments with spaces while preserving offsets and newlines."""
    if not isinstance(text, str):
        raise ValueError("La configuración debe ser texto")
    chars = list(text)
    in_quote = False
    escaped = False
    in_comment = False
    for index, char in enumerate(chars):
        if in_comment:
            if char == "\n":
                in_comment = False
            else:
                chars[index] = " "
            continue
        if in_quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_quote = False
            if char != "\n":
                chars[index] = " "
            continue
        if char == '"':
            in_quote = True
            chars[index] = " "
        elif char == "#":
            chars[index] = " "
            in_comment = True
    if in_quote:
        raise ValueError("La configuración contiene una cadena sin cerrar")
    return "".join(chars)


def iter_profile_blocks(text):
    """Yield ``(start, end, original_block)`` for real profile blocks only."""
    masked = _mask_comments(text)
    for match in re.finditer(r"(?mi)^[ \t]*profile\s*\{", masked):
        opening = masked.find("{", match.start(), match.end())
        depth = 0
        closing = None
        for index in range(opening, len(masked)):
            if masked[index] == "{":
                depth += 1
            elif masked[index] == "}":
                depth -= 1
                if depth == 0:
                    closing = index
                    break
        if closing is None:
            raise ValueError("El perfil no tiene una llave de cierre")
        yield match.start(), closing + 1, text[match.start():closing + 1]


def _assignment_values(masked, name):
    pattern = re.compile(
        rf"(?mi)(?<![A-Za-z0-9_]){name}[ \t]*=", re.IGNORECASE
    )
    values = []
    for match in pattern.finditer(masked):
        value_match = re.match(r"\s*([^\s{{}}]+)", masked[match.end():])
        values.append(value_match.group(1) if value_match else None)
    return values


def _bare_identity_values(masked):
    matches = re.finditer(
        r"(?mi)(?<![A-Za-z0-9_])identity(?![A-Za-z0-9_])(?!(?:[ \t\r\n])*=)",
        masked,
    )
    return [None for _match in matches]


def _parse_profile_info(profile, strict):
    if not isinstance(profile, str):
        raise ValueError("El perfil debe ser texto")
    masked = _mask_comments(profile)
    errors = []

    time_values = _assignment_values(masked, "time")
    if len(time_values) > 1:
        errors.append("El perfil contiene varias horas")
    time_value = None
    if time_values:
        raw_time = time_values[0]
        if raw_time is None:
            errors.append("time requiere un valor")
        else:
            try:
                time_value = normalize_clock(raw_time)
            except ValueError as error:
                errors.append(str(error))

    temperature_values = _assignment_values(masked, "temperature")
    if len(temperature_values) > 1:
        errors.append("El perfil contiene varias temperaturas")
    temperature = None
    if temperature_values:
        raw_temperature = temperature_values[0]
        if raw_temperature is None:
            errors.append("temperature requiere un valor")
        else:
            try:
                temperature = _coerce_integer(raw_temperature, "La temperatura")
            except ValueError as error:
                errors.append(str(error))

    identity_assignments = _assignment_values(masked, "identity")
    identity_values = identity_assignments + _bare_identity_values(masked)
    if len(identity_values) > 1:
        errors.append("El perfil contiene varias declaraciones identity")
    identity = None
    if identity_values:
        raw_identity = identity_values[0]
        if raw_identity is None:
            if identity_assignments:
                errors.append("identity requiere true o false")
            else:
                identity = True
        elif raw_identity.lower() in {"true", "false"}:
            identity = raw_identity.lower() == "true"
        else:
            errors.append("identity debe ser true o false")

    if strict and errors:
        raise ValueError(f"Perfil inválido: {errors[0]}")
    return {
        "time": time_value,
        "temperature": temperature,
        "identity": identity,
    }


def profile_info(profile):
    """Return the recognizable fields of a profile while ignoring comments."""
    return _parse_profile_info(profile, strict=False)


def profile_kind(info):
    if not isinstance(info, Mapping):
        return None
    identity = info.get("identity")
    if identity is True:
        return "day"
    if identity is not None and not isinstance(identity, bool):
        return None
    temperature = info.get("temperature")
    if temperature is None:
        return None
    try:
        temperature = _coerce_integer(temperature, "La temperatura")
    except ValueError:
        return None
    return "day" if temperature >= DAY_TEMP_MIN else "night"


def _profile_records(text, strict_temperatures=False):
    if not isinstance(text, str):
        raise ValueError("La configuración debe ser texto")
    blocks = list(iter_profile_blocks(text))
    if not blocks:
        raise ValueError("La configuración no contiene perfiles")

    records = []
    for number, (_start, _end, profile) in enumerate(blocks, 1):
        info = _parse_profile_info(profile, strict=True)
        if info["time"] is None:
            raise ValueError(f"El perfil {number} está incompleto: falta time")
        kind = profile_kind(info)
        if kind is None:
            raise ValueError(
                f"El perfil {number} está incompleto: falta temperature o identity"
            )
        if strict_temperatures and info["identity"] is not True:
            if kind == "day":
                _validate_temperature(
                    info["temperature"], DAY_TEMP_MIN, DAY_TEMP_MAX,
                    "La temperatura diurna",
                )
            else:
                _validate_temperature(
                    info["temperature"], NIGHT_TEMP_MIN, NIGHT_TEMP_MAX,
                    "La temperatura nocturna",
                )
        records.append((info, kind))
    return records


def validate_schedule(schedule, clamp=False):
    """Validate and normalize a schedule mapping used by runtime callers.

    The default is strict for temperatures.  ``clamp=True`` is available for
    the legacy UI contract that displays out-of-range configuration safely.
    """
    if not isinstance(schedule, Mapping):
        raise ValueError("El horario debe ser un objeto tipo diccionario")
    required = ("day_time", "day_temp", "night_time", "night_temp")
    missing = [key for key in required if key not in schedule]
    if missing:
        raise ValueError(f"Faltan campos del horario: {', '.join(missing)}")

    day_time = normalize_clock(schedule["day_time"])
    night_time = normalize_clock(schedule["night_time"])
    if day_time == night_time:
        raise ValueError("Las horas de día y noche deben ser diferentes")
    if clamp:
        day_temp = clamp_day_temperature(schedule["day_temp"])
        night_temp = clamp_night_temperature(schedule["night_temp"])
    else:
        day_temp = _validate_temperature(
            schedule["day_temp"], DAY_TEMP_MIN, DAY_TEMP_MAX,
            "La temperatura diurna",
        )
        night_temp = _validate_temperature(
            schedule["night_temp"], NIGHT_TEMP_MIN, NIGHT_TEMP_MAX,
            "La temperatura nocturna",
        )
    return {
        "day_time": day_time,
        "day_temp": day_temp,
        "night_time": night_time,
        "night_temp": night_temp,
    }


def parse_schedule_text(text, strict=False):
    """Parse profiles while retaining the GUI's dict and clamping contract.

    Structural errors never become a default schedule.  The empty string is
    retained as the historical fallback sentinel used by the status helper.
    With the default ``strict=False``, numeric temperatures are clamped as
    before; ``strict=True`` rejects values outside the corresponding UI range.
    """
    if not isinstance(text, str):
        raise ValueError("La configuración debe ser texto")
    if not text.strip():
        if strict:
            raise ValueError("La configuración no contiene perfiles")
        return default_schedule()

    records = _profile_records(text, strict_temperatures=strict)
    schedule = {}
    found_day = False
    found_night = False
    for info, kind in records:
        if kind == "day" and not found_day:
            temperature = DAY_TEMP if info["identity"] is True else info["temperature"]
            day_temp = (
                DAY_TEMP
                if info["identity"] is True
                else clamp_day_temperature(temperature)
            )
            schedule.update(day_time=info["time"], day_temp=day_temp)
            found_day = True
        elif kind == "night" and not found_night:
            schedule.update(
                night_time=info["time"],
                night_temp=clamp_night_temperature(info["temperature"]),
            )
            found_night = True
    if not found_day or not found_night:
        missing = "day" if not found_day else "night"
        raise ValueError(f"La configuración no contiene un perfil {missing} válido")
    return validate_schedule(schedule)


def day_profile_is_identity(text):
    for info, kind in _profile_records(text):
        if kind == "day":
            return info["identity"] is True
    raise ValueError("La configuración no contiene un perfil day válido")


def schedule_period(schedule, now=None):
    """Return the profile active at local time using a circular 24-hour clock."""
    schedule = validate_schedule(schedule)
    now = datetime.datetime.now().time() if now is None else now
    if not isinstance(now, datetime.time):
        raise ValueError("La hora actual debe ser datetime.time")
    current = now.hour * 60 + now.minute
    night = sum(
        int(part) * factor
        for part, factor in zip(schedule["night_time"].split(":"), (60, 1))
    )
    day = sum(
        int(part) * factor
        for part, factor in zip(schedule["day_time"].split(":"), (60, 1))
    )
    return "night" if (current - night) % 1440 < (current - day) % 1440 else "day"


@contextlib.contextmanager
def exclusive_lock(path):
    """Serialize related GUI and command-line operations on Linux."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a+", encoding="utf-8") as stream:
        if new:
            path.chmod(0o600)
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def atomic_write_text(path, text, mode=None):
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
        if mode is not None:
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
