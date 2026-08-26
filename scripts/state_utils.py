"""Safe, versioned persistence for Veilleuse configuration and state.

This module deliberately has no provider, model, UI, or application-command
dependencies.  It owns only the three XDG documents used by the backend
slice: ``config.json``, ``state.json``, and ``history.jsonl``.
"""

from __future__ import annotations

import copy
import contextlib
from datetime import datetime
import fcntl
import json
import math
import os
import re
import stat
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path


SCHEMA_VERSION = 1
MAX_HISTORY = 50
CONFIG_FILENAME = "config.json"
STATE_FILENAME = "state.json"
HISTORY_FILENAME = "history.jsonl"
_NAME_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
_ISO_LIKE_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\Z"
)
_ORIGINS = {"automatic", "manual", "preset", "snooze", "unknown"}

# Presets were removed from the product. Documents written by preset-era
# releases still carry these keys; validation drops them on read so those
# installs keep loading instead of failing as invalid_config.
_LEGACY_CONFIG_KEYS = ("presets", "default_preset")

DEFAULT_CONFIG = {
    "schema": SCHEMA_VERSION,
}

DEFAULT_STATE = {
    "schema": SCHEMA_VERSION,
    "schedule_enabled": True,
    "snooze_until": None,
    "transition_seconds": 0,
    "origin": "unknown",
    "last_applied": None,
    "schedule_disabled": None,
    "manual_override": None,
    "schedule_display": None,
    "schedule_period_applied": None,
}

_SCHEDULE_PERIODS = ("day", "night")


class StateError(Exception):
    """A persistence failure with a stable machine-readable error code."""

    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code


def _home() -> Path:
    try:
        home = Path.home()
    except (RuntimeError, OSError):
        home = Path(os.environ.get("HOME", "."))
    if not home.is_absolute():
        home = Path(os.path.abspath(str(home)))
    return home


def _xdg_home(variable: str, fallback: str) -> Path:
    raw = os.environ.get(variable, "")
    if raw:
        try:
            candidate = Path(raw).expanduser()
        except (RuntimeError, OSError):
            candidate = None
        if candidate is not None and candidate.is_absolute():
            return candidate
    return _home() / fallback


def config_path() -> Path:
    return _xdg_home("XDG_CONFIG_HOME", ".config") / "veilleuse" / CONFIG_FILENAME


def state_path() -> Path:
    return _xdg_home("XDG_STATE_HOME", ".local/state") / "veilleuse" / STATE_FILENAME


def history_path() -> Path:
    return _xdg_home("XDG_STATE_HOME", ".local/state") / "veilleuse" / HISTORY_FILENAME


def _lock_path(document: Path) -> Path:
    return document.with_name(f".{document.name}.lock")


def _raise_path_error(message: str) -> None:
    raise StateError("unsafe_path", message)


def _check_path(path: Path) -> None:
    """Reject symlink path components and non-directory parents."""
    if not path.is_absolute():
        _raise_path_error("Persistence paths must be absolute")
    parts = path.parts
    current = Path(parts[0])
    for index, part in enumerate(parts[1:], start=1):
        current /= part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            continue
        except OSError as error:
            raise StateError("io_error", f"Unable to inspect {current}") from error
        if stat.S_ISLNK(mode):
            _raise_path_error(f"Symlink path component: {current}")
        if index < len(parts) - 1 and not stat.S_ISDIR(mode):
            _raise_path_error(f"Non-directory parent: {current}")


def _prepare_parent(path: Path) -> None:
    _check_path(path)
    missing = []
    current = path.parent
    while current != current.parent:
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            missing.append(current)
            current = current.parent
            continue
        except OSError as error:
            raise StateError("io_error", f"Unable to inspect {current}") from error
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            _raise_path_error(f"Unsafe parent: {current}")
        break
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
        except OSError as error:
            raise StateError("io_error", f"Unable to create {directory}") from error
        _check_path(directory)
        try:
            if not stat.S_ISDIR(os.lstat(directory).st_mode):
                _raise_path_error(f"Unsafe parent: {directory}")
            os.chmod(directory, 0o700)
        except OSError as error:
            raise StateError("io_error", f"Unable to inspect {directory}") from error
    _check_path(path)


def _document_exists(path: Path) -> bool:
    _check_path(path)
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return False
    except OSError as error:
        raise StateError("io_error", f"Unable to inspect {path}") from error
    if stat.S_ISLNK(mode):
        _raise_path_error(f"Symlink document: {path}")
    if not stat.S_ISREG(mode):
        raise StateError("io_error", f"Document is not a regular file: {path}")
    return True


def _read_text(path: Path) -> str | None:
    if not _document_exists(path):
        return None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = None
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            descriptor = None
            return stream.read()
    except (OSError, UnicodeError) as error:
        if descriptor is not None:
            os.close(descriptor)
        raise StateError("io_error", f"Unable to read {path}") from error


def _parse_json(text: str, path: Path) -> object:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError) as error:
        raise StateError("invalid_json", f"Invalid JSON in {path}") from error


def _integer(value: object, *, minimum: int, maximum: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StateError("invalid_value", f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise StateError("invalid_value", f"{field} is out of range")
    return value


def _name(value: object, field: str) -> str:
    if not isinstance(value, str) or _NAME_PATTERN.fullmatch(value) is None:
        raise StateError("invalid_value", f"{field} is invalid")
    return value


def _schema(raw: object, kind: str) -> tuple[dict, int]:
    if not isinstance(raw, dict):
        raise StateError(f"invalid_{kind}", f"{kind} must be a JSON object")
    if "schema" not in raw:
        raise StateError("invalid_schema", f"{kind} schema is missing")
    value = raw["schema"]
    if isinstance(value, bool) or not isinstance(value, int) or value not in (0, SCHEMA_VERSION):
        raise StateError("invalid_schema", f"Unsupported {kind} schema")
    return copy.deepcopy(raw), value


def _validate_config(raw: object) -> dict:
    data, version = _schema(raw, "config")
    if version == 0:
        data["schema"] = SCHEMA_VERSION
    for key in _LEGACY_CONFIG_KEYS:
        data.pop(key, None)
    if set(data) != {"schema"}:
        raise StateError("invalid_config", "Config fields are invalid")
    return {"schema": SCHEMA_VERSION}


def _validate_schedule_display_period(value: object, period: str) -> dict:
    """Per-period display values scheduled by the user.

    Each period may configure ``brightness`` (1-100) and ``gamma`` (0-100);
    a period entry must carry at least one of them, and periods without
    scheduled values are simply absent from the mapping.
    """
    if not isinstance(value, dict) or not value or set(value) - {"brightness", "gamma"}:
        raise StateError("invalid_state", f"schedule_display.{period} is invalid")
    normalized = {}
    for field, minimum, maximum in (("brightness", 1, 100), ("gamma", 0, 100)):
        if field in value:
            try:
                normalized[field] = _integer(
                    value[field], minimum=minimum, maximum=maximum, field=field
                )
            except StateError as error:
                raise StateError(
                    "invalid_state", f"schedule_display.{period} is invalid"
                ) from error
    if not normalized:
        raise StateError("invalid_state", f"schedule_display.{period} is invalid")
    return normalized


def _validate_schedule_display(value: object) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - set(_SCHEDULE_PERIODS):
        raise StateError("invalid_state", "schedule_display is invalid")
    return {
        period: _validate_schedule_display_period(value[period], period)
        for period in _SCHEDULE_PERIODS
        if period in value
    }


def _validate_schedule_disabled(value: object) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"original_hash", "disabled_hash", "original_text"}:
        raise StateError("invalid_state", "schedule_disabled is invalid")
    if not all(isinstance(value[field], str) and value[field] for field in value):
        raise StateError("invalid_state", "schedule_disabled fields are invalid")
    return copy.deepcopy(value)


def _validate_applied_values(value: object) -> dict:
    if not isinstance(value, dict) or not value or set(value) - {"temperature", "gamma", "brightness"}:
        raise StateError("invalid_state", "last_applied values are invalid")
    normalized = {}
    for field, minimum, maximum in (
        ("temperature", 2500, 6500), ("gamma", 0, 100), ("brightness", 1, 100)
    ):
        if field in value:
            try:
                normalized[field] = _integer(value[field], minimum=minimum, maximum=maximum, field=field)
            except StateError as error:
                raise StateError("invalid_state", "last_applied values are invalid") from error
    return normalized


def _validate_last_applied(value: object) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {"at", "origin", "operation", "preset", "values"}:
        raise StateError("invalid_state", "last_applied is invalid")
    if not {"at", "origin", "operation"} <= set(value):
        raise StateError("invalid_state", "last_applied is invalid")
    timestamp = value["at"]
    if not isinstance(timestamp, str) or not timestamp or _ISO_LIKE_PATTERN.fullmatch(timestamp) is None:
        raise StateError("invalid_state", "last_applied.at is invalid")
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise StateError("invalid_state", "last_applied.at is invalid") from error
    if not isinstance(value["origin"], str) or value["origin"] not in _ORIGINS:
        raise StateError("invalid_state", "last_applied.origin is invalid")
    try:
        operation = _name(value["operation"], "last_applied.operation")
    except StateError as error:
        raise StateError("invalid_state", "last_applied.operation is invalid") from error
    normalized = {
        "at": timestamp,
        "origin": value["origin"],
        "operation": operation,
    }
    if "preset" in value:
        try:
            normalized["preset"] = _name(value["preset"], "last_applied.preset")
        except StateError as error:
            raise StateError("invalid_state", "last_applied.preset is invalid") from error
    if "values" in value:
        normalized["values"] = _validate_applied_values(value["values"])
    return normalized


def _validate_manual_override(value: object) -> dict | None:
    """Validate the optional manual-intent override persisted with a manual apply.

    ``None`` means no manual intent is active.  Otherwise the record ties the
    manual operation to the schedule profile (``profile`` fingerprint) that
    was active when it happened, so reconcile can skip scheduled enforcement
    while that same period lasts and resume automatically at the next one.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise StateError("invalid_state", "manual_override is invalid")
    if set(value) - {"at", "until", "operation", "profile", "values"}:
        raise StateError("invalid_state", "manual_override is invalid")
    if not {"at", "operation", "profile"} <= set(value):
        raise StateError("invalid_state", "manual_override is invalid")
    timestamp = value["at"]
    if not isinstance(timestamp, str) or not timestamp or _ISO_LIKE_PATTERN.fullmatch(timestamp) is None:
        raise StateError("invalid_state", "manual_override.at is invalid")
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise StateError("invalid_state", "manual_override.at is invalid") from error
    if "until" in value:
        until = value["until"]
        if not isinstance(until, str) or not until or _ISO_LIKE_PATTERN.fullmatch(until) is None:
            raise StateError("invalid_state", "manual_override.until is invalid")
        try:
            datetime.fromisoformat(until.replace("Z", "+00:00"))
        except ValueError as error:
            raise StateError("invalid_state", "manual_override.until is invalid") from error
    try:
        operation = _name(value["operation"], "manual_override.operation")
    except StateError as error:
        raise StateError("invalid_state", "manual_override.operation is invalid") from error
    profile = value["profile"]
    if not isinstance(profile, dict) or set(profile) - {"kind", "temperature"}:
        raise StateError("invalid_state", "manual_override.profile is invalid")
    kind = profile.get("kind")
    if kind == "identity":
        if "temperature" in profile:
            raise StateError("invalid_state", "manual_override.profile is invalid")
        normalized_profile = {"kind": "identity"}
    elif kind == "temperature":
        try:
            temperature = _integer(
                profile.get("temperature"), minimum=2500, maximum=6500, field="temperature"
            )
        except StateError as error:
            raise StateError("invalid_state", "manual_override.profile is invalid") from error
        normalized_profile = {"kind": "temperature", "temperature": temperature}
    else:
        raise StateError("invalid_state", "manual_override.profile is invalid")
    normalized = {
        "at": timestamp,
        "operation": operation,
        "profile": normalized_profile,
    }
    if "until" in value:
        normalized["until"] = value["until"]
    if "values" in value:
        try:
            normalized["values"] = _validate_applied_values(value["values"])
        except StateError as error:
            raise StateError("invalid_state", "manual_override.values is invalid") from error
    return normalized


def _validate_state(raw: object) -> dict:
    data, version = _schema(raw, "state")
    if set(data) - set(DEFAULT_STATE):
        raise StateError("invalid_state", "State fields are invalid")
    data["schema"] = SCHEMA_VERSION
    for key, default in DEFAULT_STATE.items():
        data.setdefault(key, copy.deepcopy(default))
    if not isinstance(data["schedule_enabled"], bool):
        raise StateError("invalid_state", "schedule_enabled must be boolean")
    snooze = data["snooze_until"]
    if snooze is not None and (
        isinstance(snooze, bool)
        or not isinstance(snooze, (int, float))
        or not math.isfinite(snooze)
        or snooze < 0
    ):
        raise StateError("invalid_state", "snooze_until is invalid")
    try:
        transition = _integer(
            data["transition_seconds"], minimum=0, maximum=1800, field="transition_seconds"
        )
    except StateError as error:
        raise StateError("invalid_state", "transition_seconds is invalid") from error
    origin = data["origin"]
    if not isinstance(origin, str) or origin not in _ORIGINS:
        raise StateError("invalid_state", "origin is invalid")
    schedule_display = _validate_schedule_display(data["schedule_display"])
    schedule_period_applied = data["schedule_period_applied"]
    if schedule_period_applied is not None:
        if schedule_period_applied not in _SCHEDULE_PERIODS:
            raise StateError("invalid_state", "schedule_period_applied is invalid")
        if not (
            isinstance(schedule_display, dict)
            and schedule_period_applied in schedule_display
        ):
            raise StateError("invalid_state", "schedule_period_applied is invalid")
    return {
        "schema": SCHEMA_VERSION,
        "schedule_enabled": data["schedule_enabled"],
        "snooze_until": snooze,
        "transition_seconds": transition,
        "origin": origin,
        "last_applied": _validate_last_applied(data["last_applied"]),
        "schedule_disabled": _validate_schedule_disabled(data["schedule_disabled"]),
        "manual_override": _validate_manual_override(data["manual_override"]),
        "schedule_display": schedule_display,
        "schedule_period_applied": schedule_period_applied,
    }


def _read_document(path: Path, kind: str, validator: Callable[[object], dict], default: dict) -> dict:
    text = _read_text(path)
    if text is None:
        return copy.deepcopy(default)
    return validator(_parse_json(text, path))


def _atomic_write(path: Path, data: object) -> None:
    _prepare_parent(path)
    directory = path.parent
    descriptor = None
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=directory
        )
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = None
            json.dump(data, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        _before_replace(path)
        _check_destination(path)
        os.replace(temporary, path)
        temporary = None
        directory_descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except StateError:
        raise
    except (OSError, TypeError, ValueError) as error:
        raise StateError("io_error", f"Unable to write {path}") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            with contextlib.suppress(OSError):
                os.unlink(temporary)


@contextlib.contextmanager
def _locked(document: Path):
    lock = _lock_path(document)
    _prepare_parent(lock)
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor = None
    try:
        descriptor = os.open(lock, flags, 0o600)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise StateError("unsafe_path", "Lock is not a regular file")
        os.fchmod(descriptor, 0o600)
    except StateError:
        if descriptor is not None:
            with contextlib.suppress(OSError):
                os.close(descriptor)
        raise
    except OSError as error:
        if descriptor is not None:
            with contextlib.suppress(OSError):
                os.close(descriptor)
        raise StateError("unsafe_path" if error.errno in {40, 62} else "io_error", "Unable to lock document") from error
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    except StateError:
        raise
    except OSError as error:
        raise StateError("io_error", "Unable to lock document") from error
    finally:
        if descriptor is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            with contextlib.suppress(OSError):
                os.close(descriptor)

def read_config() -> dict:
    return _read_document(config_path(), "config", _validate_config, DEFAULT_CONFIG)


def write_config(value: Mapping) -> dict:
    normalized = _validate_config(value)
    path = config_path()
    with _locked(path):
        if _document_exists(path):
            _read_document(path, "config", _validate_config, DEFAULT_CONFIG)
        _atomic_write(path, normalized)
    return copy.deepcopy(normalized)


def update_config(mutator: Callable[[dict], Mapping]) -> dict:
    path = config_path()
    with _locked(path):
        current = _read_document(path, "config", _validate_config, DEFAULT_CONFIG)
        try:
            candidate = mutator(copy.deepcopy(current))
        except StateError:
            raise
        except Exception as error:
            raise StateError("invalid_config", "Config update failed") from error
        normalized = _validate_config(candidate)
        _atomic_write(path, normalized)
    return copy.deepcopy(normalized)


def read_state() -> dict:
    return _read_document(state_path(), "state", _validate_state, DEFAULT_STATE)


def write_state(value: Mapping) -> dict:
    normalized = _validate_state(value)
    path = state_path()
    with _locked(path):
        if _document_exists(path):
            _read_document(path, "state", _validate_state, DEFAULT_STATE)
        _atomic_write(path, normalized)
    return copy.deepcopy(normalized)


def update_state(mutator: Callable[[dict], Mapping | None]) -> dict:
    """Read-modify-write ``state.json`` under its lock (lost-update safe).

    ``mutator`` receives a deep copy of the current validated state and returns
    the complete new state, or ``None`` to leave the document untouched.  The
    read, the mutation and the write all happen inside one ``_locked`` span, so
    concurrent updaters (toggles, snoozes, preset applies) can never overwrite
    each other's keys the way a cold ``read_state()`` + ``write_state()`` pair
    would.  The document is written only when the mutated state actually
    differs from what was read.
    """
    path = state_path()
    with _locked(path):
        current = _read_document(path, "state", _validate_state, DEFAULT_STATE)
        try:
            candidate = mutator(copy.deepcopy(current))
        except StateError:
            raise
        except Exception as error:
            raise StateError("invalid_state", "State update failed") from error
        if candidate is None:
            return copy.deepcopy(current)
        normalized = _validate_state(candidate)
        if normalized != current:
            _atomic_write(path, normalized)
    return copy.deepcopy(normalized)


_HISTORY_FIELDS = {
    "time", "timestamp", "operation", "origin", "preset", "temperature", "gamma",
    "brightness", "monitor", "success", "error_code",
}


def validate_history_record(value: object) -> dict:
    if not isinstance(value, dict) or "operation" not in value:
        raise StateError("invalid_history", "History record is invalid")
    if set(value) - _HISTORY_FIELDS:
        raise StateError("invalid_history", "History fields are invalid")
    time_fields = {"time", "timestamp"} & set(value)
    if len(time_fields) != 1:
        raise StateError("invalid_history", "History record time is invalid")
    timestamp = value[next(iter(time_fields))]
    if isinstance(timestamp, bool) or not isinstance(timestamp, (str, int, float)):
        raise StateError("invalid_history", "timestamp is invalid")
    if isinstance(timestamp, str) and not timestamp:
        raise StateError("invalid_history", "timestamp is invalid")
    if not isinstance(value["operation"], str) or not value["operation"]:
        raise StateError("invalid_history", "operation is invalid")
    if "origin" in value and value["origin"] not in _ORIGINS:
        raise StateError("invalid_history", "origin is invalid")
    string_fields = {"preset", "monitor", "error_code"}
    for field in string_fields & set(value):
        if not isinstance(value[field], str) or not value[field]:
            raise StateError("invalid_history", f"{field} is invalid")
    for field, minimum, maximum in (
        ("temperature", 2500, 6500), ("gamma", 0, 100), ("brightness", 1, 100)
    ):
        if field in value:
            try:
                _integer(value[field], minimum=minimum, maximum=maximum, field=field)
            except StateError as error:
                raise StateError("invalid_history", f"{field} is invalid") from error
    if "success" in value and not isinstance(value["success"], bool):
        raise StateError("invalid_history", "success is invalid")
    return copy.deepcopy(value)


def _read_history(path: Path) -> list[dict]:
    text = _read_text(path)
    if text is None:
        return []
    records = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            raise StateError("invalid_history", f"Blank history line {line_number}")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise StateError("invalid_json", f"Invalid history JSON line {line_number}") from error
        try:
            records.append(validate_history_record(value))
        except StateError as error:
            if error.error_code == "invalid_history":
                raise
            raise StateError("invalid_history", f"Invalid history line {line_number}") from error
    return records


def append_history(record: Mapping) -> list[dict]:
    normalized = validate_history_record(record)
    path = history_path()
    with _locked(path):
        records = _read_history(path)
        records = (records + [normalized])[-MAX_HISTORY:]
        _atomic_write_lines(path, records)
    return copy.deepcopy(records)


def _atomic_write_lines(path: Path, records: list[dict]) -> None:
    _prepare_parent(path)
    descriptor = None
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = None
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
                stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        _before_replace(path)
        _check_destination(path)
        os.replace(temporary, path)
        temporary = None
        directory_descriptor = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except StateError:
        raise
    except OSError as error:
        raise StateError("io_error", f"Unable to write {path}") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            with contextlib.suppress(OSError):
                os.unlink(temporary)


def list_history() -> list[dict]:
    return _read_history(history_path())[-MAX_HISTORY:]


def clear_history() -> list[dict]:
    path = history_path()
    with _locked(path):
        # The existence decision belongs inside the lock: an append_history
        # racing between an unlocked check and the lock would otherwise
        # survive the clear.
        if not _document_exists(path):
            return []
        _read_history(path)
        _atomic_write_lines(path, [])
    return []


def _before_replace(path: Path) -> None:
    """Test seam immediately before the final destination safety check."""


def _check_destination(path: Path) -> None:
    _check_path(path)
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return
    except OSError as error:
        raise StateError("io_error", f"Unable to inspect {path}") from error
    if stat.S_ISLNK(mode):
        _raise_path_error(f"Symlink document: {path}")
    if not stat.S_ISREG(mode):
        _raise_path_error(f"Non-regular document: {path}")


# Explicit aliases keep the persistence API easy to discover for callers that
# use load/save terminology.
load_config = read_config
save_config = write_config
load_state = read_state
save_state = write_state


__all__ = [
    "DEFAULT_CONFIG", "DEFAULT_STATE", "MAX_HISTORY",
    "StateError", "append_history", "clear_history", "config_path",
    "history_path", "list_history", "read_config", "read_state", "save_config",
    "save_state", "state_path", "update_config", "update_state",
    "validate_history_record", "write_config", "write_state",
]
