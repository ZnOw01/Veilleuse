"""Transactional enable/disable for Veilleuse-owned hyprsunset profiles.

The schedule parser is deliberately shared with :mod:`schedule_utils`.  A
toggle is allowed only when the complete file contains one valid day profile
and one valid night profile.  This makes ownership unambiguous without
guessing about similarly-shaped profiles belonging to another tool.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import stat
import tempfile
from pathlib import Path

import schedule_utils
import state_utils


HYPRSUNSET_CONFIG = schedule_utils.HYPRSUNSET_CONFIG
LOCK_NAME = schedule_utils.SCHEDULE_LOCK_NAME


class ScheduleToggleError(RuntimeError):
    """A fail-closed schedule transaction error."""

    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code


def _error(code: str, message: str, cause: BaseException | None = None):
    error = ScheduleToggleError(code, message)
    if cause is not None:
        error.__cause__ = cause
    return error


def _path(value: str | os.PathLike[str] | None) -> Path:
    return Path(HYPRSUNSET_CONFIG if value is None else value)


def _check_parent(path: Path) -> None:
    if not path.is_absolute():
        raise _error("unsafe_path", "Schedule path must be absolute")
    current = Path(path.parts[0])
    for part in path.parts[1:-1]:
        current /= part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            current.mkdir()
            mode = os.lstat(current).st_mode
        except OSError as caught:
            raise _error("io_error", f"Unable to inspect {current}", caught)
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise _error("unsafe_path", f"Unsafe schedule parent: {current}")


def _read_bytes(path: Path) -> tuple[bytes, int, os.stat_result]:
    _check_parent(path)
    try:
        before = os.lstat(path)
    except FileNotFoundError as caught:
        raise _error("missing_config", f"Schedule file does not exist: {path}", caught)
    except OSError as caught:
        raise _error("io_error", f"Unable to inspect {path}", caught)
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise _error("unsafe_path", f"Schedule file is not a regular file: {path}")
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        after = os.fstat(descriptor)
        if not stat.S_ISREG(after.st_mode):
            raise _error("unsafe_path", f"Schedule file is not regular: {path}")
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks), stat.S_IMODE(after.st_mode), after
    except ScheduleToggleError:
        raise
    except (OSError, UnicodeError) as caught:
        raise _error("io_error", f"Unable to read {path}", caught)
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _assert_same_file(path: Path, expected: bytes) -> tuple[int, os.stat_result]:
    current, mode, metadata = _read_bytes(path)
    if current != expected:
        raise _error("conflict", "Schedule changed during the transaction")
    return mode, metadata


def _atomic_write_bytes(
    path: Path,
    data: bytes,
    mode: int,
    *,
    expected: bytes | None = None,
) -> None:
    """Replace a regular file atomically, retaining its exact permission mode."""
    _check_parent(path)
    current, _current_mode, _metadata = _read_bytes(path)
    if expected is not None and current != expected:
        raise _error("conflict", "Schedule changed before it could be written")
    descriptor = None
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # Re-check immediately before replace.  The lock protects Veilleuse
        # callers, while this check also fails closed for unrelated writers.
        _assert_same_file(path, current)
        os.replace(temporary, path)
        temporary = None
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        replaced_mode = stat.S_IMODE(os.lstat(path).st_mode)
        if replaced_mode != mode:
            raise _error("io_error", "Schedule file mode was not preserved")
    except ScheduleToggleError:
        raise
    except (OSError, ValueError) as caught:
        raise _error("io_error", f"Unable to write {path}", caught)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            with contextlib.suppress(OSError):
                os.unlink(temporary)


@contextlib.contextmanager
def _locked(path: Path):
    _check_parent(path)
    lock_path = path.parent / LOCK_NAME
    descriptor = None
    try:
        descriptor = os.open(
            lock_path,
            os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise _error("unsafe_path", "Schedule lock is not a regular file")
        os.fchmod(descriptor, 0o600)
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    except ScheduleToggleError:
        raise
    except OSError as caught:
        code = "unsafe_path" if getattr(caught, "errno", None) in {40, 62} else "io_error"
        raise _error(code, "Unable to lock schedule", caught)
    finally:
        if descriptor is not None:
            with contextlib.suppress(OSError):
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _managed_ranges(text: str) -> list[tuple[int, int]]:
    try:
        blocks = list(schedule_utils.iter_profile_blocks(text))
        records = schedule_utils._profile_records(text, strict_temperatures=True)
    except (AttributeError, ValueError) as caught:
        raise _error("malformed_config", "Schedule contains malformed profiles", caught)
    if len(blocks) != len(records):
        raise _error("malformed_config", "Schedule profile records are inconsistent")
    ranges = [(start, end) for start, end, _profile in blocks]
    if len(records) == 2:
        kinds = [kind for _info, kind in records]
        if sorted(kinds) == ["day", "night"]:
            return ranges

    # A user config may contain additional valid profiles.  In that case only
    # an explicit Veilleuse day/night comment directly associated with a block
    # establishes ownership; ordinary comments are never treated as markers.
    marker_pattern = re.compile(
        r"(?im)^[ \t]*#[^\n]*\bveilleuse\b[^\n]*\b(day|night)\b[^\n]*$"
    )
    marked = []
    previous_end = 0
    for (start, end, _profile), (_info, _kind) in zip(blocks, records):
        context = text[max(previous_end, start - 256):end]
        kinds = [match.group(1).casefold() for match in marker_pattern.finditer(context)]
        if len(kinds) == 1:
            marked.append((kinds[0], (start, end)))
        elif kinds:
            raise _error("ambiguous_config", "A managed profile has multiple markers")
        previous_end = end
    if sorted(kind for kind, _range in marked) == ["day", "night"]:
        return [profile_range for _kind, profile_range in marked]
    raise _error("ambiguous_config", "Schedule day/night profiles are ambiguous")


def _remove_ranges(text: str, ranges: list[tuple[int, int]]) -> str:
    updated = text
    for start, end in reversed(ranges):
        updated = updated[:start] + updated[end:]
    return updated


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as caught:
        raise _error("malformed_config", "Schedule is not valid UTF-8", caught)


def _state_with_schedule(state: dict, *, enabled: bool, disabled: dict | None) -> dict:
    updated = dict(state)
    updated["schedule_enabled"] = enabled
    updated["schedule_disabled"] = disabled
    return updated


def _clear_stale_override(old_state: dict) -> dict:
    """Drop a manual-intent override while the schedule stays disabled.

    A stale override recorded before or during the disabled window must never
    survive re-enable and suppress schedule enforcement, so the disabled
    state is written without it.  The clear is a read-modify-write under the
    state lock so concurrent writers (snooze, reconcile) are not lost.
    """
    if old_state.get("manual_override") is None:
        return old_state
    return state_utils.update_state(
        lambda current: {**current, "manual_override": None}
    )


def _rollback_file(path: Path, data: bytes, mode: int, expected: bytes) -> None:
    try:
        _atomic_write_bytes(path, data, mode, expected=expected)
    except BaseException as caught:
        raise _error("rollback_failed", "Unable to roll back schedule file", caught)


def _rollback_after_file_write(
    path: Path,
    old_file: bytes,
    old_mode: int,
    new_file: bytes,
    cause: BaseException,
) -> None:
    """Undo a write only when the destination contains our new bytes."""
    current, _mode, _metadata = _read_bytes(path)
    if current == old_file:
        raise cause
    if current != new_file:
        # The write failed before replacement, or another writer intervened.
        # In either case, do not overwrite bytes we cannot identify.
        raise cause
    _rollback_file(path, old_file, old_mode, expected=new_file)
    raise cause


def _write_state_or_rollback(
    path: Path,
    old_file: bytes,
    old_mode: int,
    new_file: bytes,
    old_state: dict,
    commit,
) -> dict:
    state_path = state_utils.state_path()
    state_before = None
    if state_path.exists():
        state_before = state_path.read_bytes()
    try:
        new_state = state_utils.update_state(commit)
    except BaseException as cause:
        _rollback_file(path, old_file, old_mode, expected=new_file)
        # A state writer may fail after replacing its destination.  Restore
        # through state_utils as well; if that cannot be done, do not claim a
        # successful transaction.
        state_after = state_path.read_bytes() if state_path.exists() else None
        if state_after != state_before:
            try:
                state_utils.write_state(old_state)
            except BaseException as caught:
                raise _error("rollback_failed", "Unable to roll back schedule state", caught)
        raise cause
    return new_state


def _disable_locked(path: Path) -> dict:
    old_state = state_utils.read_state()
    data, mode, _metadata = _read_bytes(path)
    current_hash = _hash(data)
    recorded = old_state["schedule_disabled"]
    if recorded is not None:
        if not old_state["schedule_enabled"] and current_hash == recorded["disabled_hash"]:
            return _clear_stale_override(old_state)
        raise _error("conflict", "Schedule state and file disagree")
    if not old_state["schedule_enabled"]:
        raise _error("conflict", "Schedule state is disabled without a transaction")
    text = _decode(data)
    ranges = _managed_ranges(text)
    disabled = _remove_ranges(text, ranges).encode("utf-8")
    if disabled == data:
        raise _error("malformed_config", "Managed profiles could not be removed")
    transaction = {
        "original_hash": current_hash,
        "disabled_hash": _hash(disabled),
        "original_text": text,
    }

    def _commit(current):
        # Apply the schedule keys to the freshest state: concurrent writers
        # (snooze, reconcile, transitions) that committed while this toggle
        # held the schedule file lock must not be overwritten.
        next_state = _state_with_schedule(
            current, enabled=False, disabled=transaction
        )
        if current.get("manual_override") is not None:
            next_state["manual_override"] = None
        return next_state

    try:
        _atomic_write_bytes(path, disabled, mode, expected=data)
    except BaseException as caught:
        _rollback_after_file_write(path, data, mode, disabled, caught)
    return _write_state_or_rollback(
        path, data, mode, disabled, old_state, _commit
    )


def _enable_locked(path: Path) -> dict:
    old_state = state_utils.read_state()
    data, mode, _metadata = _read_bytes(path)
    recorded = old_state["schedule_disabled"]
    if recorded is None:
        if old_state["schedule_enabled"]:
            return old_state
        raise _error("conflict", "Schedule state is disabled without a transaction")
    if old_state["schedule_enabled"]:
        raise _error("conflict", "Schedule state and file disagree")
    if _hash(data) != recorded["disabled_hash"]:
        raise _error("conflict", "Schedule was changed while disabled")
    try:
        original = recorded["original_text"].encode("utf-8")
    except UnicodeEncodeError as caught:
        raise _error("malformed_state", "Stored schedule text is invalid", caught)
    if _hash(original) != recorded["original_hash"]:
        raise _error("conflict", "Stored schedule transaction is invalid")

    def _commit(current):
        # Apply the schedule keys to the freshest state: concurrent writers
        # (snooze, reconcile, transitions) that committed while this toggle
        # held the schedule file lock must not be overwritten.
        return _state_with_schedule(current, enabled=True, disabled=None)

    try:
        _atomic_write_bytes(path, original, mode, expected=data)
    except BaseException as caught:
        _rollback_after_file_write(path, data, mode, original, caught)
    return _write_state_or_rollback(
        path, data, mode, original, old_state, _commit
    )


def disable_schedule(path: str | os.PathLike[str] | None = None) -> dict:
    """Disable the uniquely identified Veilleuse day/night profiles."""
    target = _path(path)
    with _locked(target):
        return _disable_locked(target)


def enable_schedule(path: str | os.PathLike[str] | None = None) -> dict:
    """Restore the exact saved bytes when the disabled file is unchanged."""
    target = _path(path)
    with _locked(target):
        return _enable_locked(target)


def schedule_status(path: str | os.PathLike[str] | None = None) -> dict:
    """Read schedule state without changing either persistence document."""
    target = _path(path)
    with _locked(target):
        state = state_utils.read_state()
        data, _mode, _metadata = _read_bytes(target)
        recorded = state["schedule_disabled"]
        if recorded is not None and _hash(data) != recorded["disabled_hash"]:
            raise _error("conflict", "Schedule state and file disagree")
        if recorded is None and not state["schedule_enabled"]:
            raise _error("conflict", "Schedule state is disabled without a transaction")
        return state


# Short aliases make the small module convenient for command/helper callers.
disable = disable_schedule
enable = enable_schedule
status = schedule_status


__all__ = [
    "HYPRSUNSET_CONFIG",
    "ScheduleToggleError",
    "disable",
    "disable_schedule",
    "enable",
    "enable_schedule",
    "schedule_status",
    "status",
]
