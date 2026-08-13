"""Preset storage and fail-closed application orchestration.

The native display operations are injected so this module can enforce the
ordering and safety rules without owning subprocesses or QML state.  An
operations object supplies ``read_monitor_state``, ``apply_nightlight``,
``read_brightness`` and ``brightness_step``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import copy
import re
import time

from . import state_utils


_NAME_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
_TEMPERATURE_MIN = 2500
_TEMPERATURE_MAX = 6500
_GAMMA_MIN = 0
_GAMMA_MAX = 100
_BRIGHTNESS_MIN = 1
_BRIGHTNESS_MAX = 100
_BUILTIN_ORDER = ("reading", "work", "cinema")
_BUILTIN_VALUES = {
    name: copy.deepcopy(state_utils.BUILTIN_PRESETS[name]) for name in _BUILTIN_ORDER
}


class PresetError(Exception):
    """A preset operation failure with a stable machine-readable code."""

    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code


def _validate_name(value, field="preset name"):
    if not isinstance(value, str) or _NAME_PATTERN.fullmatch(value) is None:
        raise PresetError("invalid_preset", f"Invalid {field}")
    return value


def _validate_integer(value, minimum, maximum, field):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise PresetError("invalid_preset", f"Invalid {field}")
    return value


def _validate_values(temperature, gamma, brightness):
    values = {
        "temperature": _validate_integer(
            temperature, _TEMPERATURE_MIN, _TEMPERATURE_MAX, "temperature"
        ),
        "gamma": _validate_integer(gamma, _GAMMA_MIN, _GAMMA_MAX, "gamma"),
    }
    if brightness is not None:
        values["brightness"] = _validate_integer(
            brightness, _BRIGHTNESS_MIN, _BRIGHTNESS_MAX, "brightness"
        )
    return values


def _operation_method(operations, name):
    if isinstance(operations, Mapping):
        method = operations.get(name)
    else:
        method = getattr(operations, name, None)
    if not callable(method):
        raise PresetError("native_operation_missing", f"Missing native operation: {name}")
    return method


def _operation_ok(result):
    if result is None or result is True:
        return True, None
    if result is False:
        return False, "native_failure"
    if isinstance(result, Mapping):
        if result.get("ok", result.get("success", True)) is False:
            return False, str(result.get("error_code") or "native_failure")
        return True, None
    return bool(result), None if result else "native_failure"


def _timestamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class PresetManager:
    """Manage validated presets and apply them through injected operations."""

    def __init__(self, operations, *, state=state_utils, clock=time.monotonic, timestamp=None):
        self.operations = operations
        self.state = state
        self.clock = clock
        self.timestamp = timestamp or _timestamp

    def list_presets(self):
        config = self.state.read_config()
        result = []
        builtins = self._builtins()
        for name in _BUILTIN_ORDER:
            result.append({"name": name, **copy.deepcopy(builtins[name]), "builtin": True})
        for name in sorted(config["presets"]):
            result.append({"name": name, **copy.deepcopy(config["presets"][name]), "builtin": False})
        return result

    def _builtins(self):
        return copy.deepcopy(_BUILTIN_VALUES)

    def _read_preset(self, name):
        name = _validate_name(name)
        builtins = self._builtins()
        if name in builtins:
            return copy.deepcopy(builtins[name])
        config = self.state.read_config()
        if name not in config["presets"]:
            raise PresetError("preset_not_found", "Preset not found")
        return copy.deepcopy(config["presets"][name])

    def save_preset(self, name, temperature, gamma, brightness=None):
        name = _validate_name(name)
        if name in self._builtins():
            raise PresetError("builtin_immutable", "Built-in presets are immutable")
        values = _validate_values(temperature, gamma, brightness)

        def update(config):
            config["presets"][name] = copy.deepcopy(values)
            return config

        self.state.update_config(update)
        return {"name": name, **copy.deepcopy(values), "builtin": False}

    def set_default_preset(self, name):
        name = _validate_name(name)
        config = self.state.read_config()
        if name not in self._builtins() and name not in config["presets"]:
            raise PresetError("preset_not_found", "Preset not found")

        def update(config):
            config["default_preset"] = name
            return config

        try:
            self.state.update_config(update)
        except PresetError:
            raise
        except state_utils.StateError as error:
            raise PresetError(error.error_code, str(error)) from error
        return name

    def delete_preset(self, name):
        name = _validate_name(name)
        if name in self._builtins():
            raise PresetError("builtin_immutable", "Built-in presets are immutable")
        config = self.state.read_config()
        if name not in config["presets"]:
            raise PresetError("preset_not_found", "Preset not found")
        if config["default_preset"] == name:
            raise PresetError("default_conflict", "The default preset cannot be deleted")

        def update(config):
            del config["presets"][name]
            return config

        try:
            self.state.update_config(update)
        except PresetError:
            raise
        except state_utils.StateError as error:
            raise PresetError(error.error_code, str(error)) from error
        return {"name": name, "deleted": True}

    def _monitor_entries(self, payload):
        if isinstance(payload, Mapping):
            entries = payload.get("monitors", [])
        else:
            entries = payload
        if not isinstance(entries, list):
            return []
        return [entry for entry in entries if isinstance(entry, Mapping)]

    @staticmethod
    def _enabled(entry):
        return entry.get("enabled") is True and entry.get("disabled", False) is not True

    def _resolve_from_payload(self, payload, target, selected=None):
        entries = self._monitor_entries(payload)
        if target == "focused":
            candidates = [
                entry.get("name")
                for entry in entries
                if self._enabled(entry) and entry.get("focused") is True
            ]
            if len(candidates) != 1 or not isinstance(candidates[0], str) or not candidates[0]:
                raise PresetError("monitor_unavailable", "Focused monitor is unavailable")
            if selected is not None and candidates[0] != selected:
                raise PresetError("monitor_unavailable", "Focused monitor changed")
            return candidates[0]
        matches = [
            entry for entry in entries
            if entry.get("name") == target and self._enabled(entry)
        ]
        if len(matches) != 1:
            raise PresetError("monitor_unavailable", "Selected monitor is unavailable")
        return target

    def resolve_monitor(self, target):
        if not isinstance(target, str) or not target:
            raise PresetError("monitor_unavailable", "Selected monitor is unavailable")
        try:
            payload = _operation_method(self.operations, "read_monitor_state")()
            return self._resolve_from_payload(payload, target)
        except PresetError:
            raise
        except Exception as error:
            raise PresetError("monitor_unavailable", "Selected monitor is unavailable") from error

    def _deadline(self, deadline, timeout):
        now = self.clock()
        if deadline is not None:
            if not isinstance(deadline, (int, float)) or isinstance(deadline, bool):
                raise PresetError("deadline_exceeded", "Invalid deadline")
            return float(deadline)
        if timeout is None:
            timeout = 30.0
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout < 0:
            raise PresetError("deadline_exceeded", "Invalid timeout")
        return now + float(timeout)

    def _check_deadline(self, deadline):
        if self.clock() >= deadline:
            raise PresetError("deadline_exceeded", "Preset application deadline exceeded")

    def _read_brightness(self, monitor):
        result = _operation_method(self.operations, "read_brightness")(monitor)
        if isinstance(result, tuple) and len(result) == 2:
            value, error = result
        elif isinstance(result, Mapping):
            value, error = result.get("percent"), result.get("error")
        else:
            value, error = result, None
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not _BRIGHTNESS_MIN <= value <= _BRIGHTNESS_MAX
        ):
            raise PresetError("readback_mismatch", str(error or "Brightness readback unavailable"))
        return value

    def _history_record(self, *, timestamp, name, values, monitor, success, error_code=None):
        record = {
            "timestamp": timestamp,
            "operation": "preset_apply",
            "origin": "preset",
            "preset": name,
            "temperature": values["temperature"],
            "gamma": values["gamma"],
            "success": success,
        }
        if "brightness" in values:
            record["brightness"] = values["brightness"]
        if monitor is not None:
            record["monitor"] = monitor
        if error_code is not None:
            record["error_code"] = error_code
        self.state.append_history(record)

    def _failure(self, *, timestamp, name, values, monitor, error_code):
        try:
            self._history_record(
                timestamp=timestamp,
                name=name,
                values=values,
                monitor=monitor,
                success=False,
                error_code=error_code,
            )
        except Exception:
            pass
        return {
            "success": False,
            "ok": False,
            "error_code": error_code,
            "preset": name,
            "monitor": monitor,
            "values": copy.deepcopy(values),
        }

    def apply_preset(self, name, *, monitor="focused", deadline=None, timeout=None):
        timestamp = self.timestamp()
        name = _validate_name(name)
        values = self._read_preset(name)
        selected = None
        try:
            end = self._deadline(deadline, timeout)
            self._check_deadline(end)
            selected = self.resolve_monitor(monitor)
            self._check_deadline(end)

            nightlight = _operation_method(self.operations, "apply_nightlight")
            nightlight_result = nightlight(values["temperature"], values["gamma"])
            ok, operation_error = _operation_ok(nightlight_result)
            if not ok:
                raise PresetError(operation_error or "nightlight_failure", "Nightlight operation failed")
            self._check_deadline(end)

            if "brightness" in values:
                target = values["brightness"]
                current = self._read_brightness(selected)
                while current != target:
                    self._check_deadline(end)
                    payload = _operation_method(self.operations, "read_monitor_state")()
                    self._resolve_from_payload(payload, monitor, selected=selected)
                    step = "+1%" if target > current else "1%-"
                    expected = current + 1 if step == "+1%" else current - 1
                    result = _operation_method(self.operations, "brightness_step")(selected, step)
                    ok, operation_error = _operation_ok(result)
                    if not ok:
                        raise PresetError(operation_error or "native_failure", "Brightness operation failed")
                    self._check_deadline(end)
                    payload = _operation_method(self.operations, "read_monitor_state")()
                    self._resolve_from_payload(payload, monitor, selected=selected)
                    actual = self._read_brightness(selected)
                    if actual != expected:
                        raise PresetError("readback_mismatch", "Brightness changed by more than one point")
                    current = actual

            self._check_deadline(end)
            def update(state):
                state["origin"] = "preset"
                state["last_applied"] = {
                    "at": timestamp,
                    "origin": "preset",
                    "operation": "preset_apply",
                    "preset": name,
                    "values": copy.deepcopy(values),
                }
                return state

            try:
                self.state.update_state(update)
            except Exception:
                return self._failure(
                    timestamp=timestamp,
                    name=name,
                    values=values,
                    monitor=selected,
                    error_code="state_failed",
                )

            try:
                self._history_record(
                    timestamp=timestamp,
                    name=name,
                    values=values,
                    monitor=selected,
                    success=True,
                )
            except Exception:
                history_error = "history_error"
            else:
                history_error = None
            return {
                "success": True,
                "ok": True,
                "error_code": history_error,
                "preset": name,
                "monitor": selected,
                "values": copy.deepcopy(values),
            }
        except PresetError as error:
            return self._failure(
                timestamp=timestamp,
                name=name,
                values=values,
                monitor=selected,
                error_code=error.error_code,
            )


PresetStore = PresetManager


__all__ = ["PresetError", "PresetManager", "PresetStore"]
