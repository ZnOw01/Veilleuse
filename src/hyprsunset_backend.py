#!/usr/bin/python3
"""Small, bounded and testable interface to the hyprsunset IPC commands."""

from __future__ import annotations

import inspect
import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


DEFAULT_TEMPERATURE = 3500
NIGHT_TEMP_MIN = 2500
NIGHT_TEMP_MAX = 5000
# Matches the Omarchy nightlight identity point (shell/NightlightModel.js and
# bin/omarchy-toggle-nightlight): temperatures strictly below this count as
# night light.  Identity remains authoritative in state_from_readings().
IDENTITY_TEMPERATURE = 6000
TEMPERATURE_RANGE = (NIGHT_TEMP_MIN, 6500)

COMMAND_TIMEOUT = 1.0
READ_TIMEOUT = 1.5
REQUEST_TIMEOUT = 1.0
START_TIMEOUT = 1.5
SERVICE_TIMEOUT = 0.5
POLL_INTERVAL = 0.05
TEMPERATURE_TOLERANCE = 50
GAMMA_MIN = 0
GAMMA_MAX = 200
GAMMA_DEFAULT = 100
GAMMA_TOLERANCE = 1
DEADLINE_EXIT_CODE = 124
READBACK_EXIT_CODE = 1

_HYPRSUNSET = ("hyprctl", "hyprsunset")


@dataclass(frozen=True, slots=True)
class BackendState:
    """The observed backend state, including partial-read information."""

    available: bool
    active: bool | None
    identity: bool | None
    temperature: int | None
    # Optional so positional four-argument callers remain compatible.
    gamma: int | None = None


@dataclass(frozen=True, slots=True)
class ServiceState:
    """Best-effort state of the user service, independent of IPC availability."""

    enabled: bool | None
    active: bool | None


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _completed(args: Sequence[str], returncode: int, stderr: str = ""):
    return subprocess.CompletedProcess(list(args), returncode, "", stderr)


def _remaining(deadline: float | None) -> float | None:
    return None if deadline is None else deadline - time.monotonic()


def run_command(
    args: Sequence[str], *, timeout: float = COMMAND_TIMEOUT, deadline: float | None = None
):
    """Run one command with a per-command timeout and an optional total deadline."""
    remaining = _remaining(deadline)
    if remaining is not None:
        if remaining <= 0:
            return _completed(args, DEADLINE_EXIT_CODE, "Se agoto el plazo de la operacion")
        timeout = min(float(timeout), remaining)
    else:
        timeout = float(timeout)
    if timeout <= 0:
        return _completed(args, DEADLINE_EXIT_CODE, "Se agoto el plazo de la operacion")

    try:
        return subprocess.run(
            args,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        return subprocess.CompletedProcess(
            list(args),
            DEADLINE_EXIT_CODE,
            _text(error.stdout),
            _text(error.stderr) or str(error),
        )
    except OSError as error:
        return subprocess.CompletedProcess(list(args), 127, "", str(error))


def read_temperature(*, timeout: float = COMMAND_TIMEOUT, deadline: float | None = None):
    result = run_command(
        [*_HYPRSUNSET, "temperature"], timeout=timeout, deadline=deadline
    )
    if result.returncode != 0:
        return None
    match = re.fullmatch(r"\s*(\d+)\s*", _text(result.stdout))
    return int(match.group(1)) if match else None


def read_identity(*, timeout: float = COMMAND_TIMEOUT, deadline: float | None = None):
    result = run_command(
        [*_HYPRSUNSET, "identity", "get"], timeout=timeout, deadline=deadline
    )
    if result.returncode != 0:
        return None
    value = _text(result.stdout).strip().casefold()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def read_gamma(
    *, timeout: float = COMMAND_TIMEOUT, deadline: float | None = None
) -> int | None:
    """Read the observed hyprsunset gamma percentage, when supported."""
    result = run_command(
        [*_HYPRSUNSET, "gamma"], timeout=timeout, deadline=deadline
    )
    if result.returncode != 0:
        return None
    match = re.fullmatch(r"\s*(\d+)\s*", _text(result.stdout))
    if not match:
        return None
    value = int(match.group(1))
    return value if GAMMA_MIN <= value <= GAMMA_MAX else None


def state_from_readings(
    identity: bool | None, temperature: int | None, gamma: int | None = None
) -> BackendState:
    """Resolve a state without allowing a stale temperature to beat identity."""
    available = identity is not None or temperature is not None or gamma is not None
    if not available:
        return BackendState(False, None, None, None, gamma)
    if identity is True:
        return BackendState(True, False, identity, temperature, gamma)
    if temperature is None:
        return BackendState(True, None, identity, None, gamma)
    return BackendState(True, temperature < IDENTITY_TEMPERATURE, identity, temperature, gamma)


def read_state(*, timeout: float = READ_TIMEOUT, deadline: float | None = None) -> BackendState:
    """Read identity and temperature under one deadline."""
    operation_deadline = (
        deadline if deadline is not None else time.monotonic() + float(timeout)
    )
    identity = read_identity(deadline=operation_deadline)
    temperature = read_temperature(deadline=operation_deadline)
    # Gamma was added after the original backend contract.  A backend that
    # lacks this IPC read must still provide the temperature/identity state.
    try:
        gamma = read_gamma(deadline=operation_deadline)
    except Exception:
        gamma = None
    return state_from_readings(identity, temperature, gamma)


def _invoke_readback(predicate: Callable, deadline: float) -> bool:
    """Support both deadline-aware predicates and the old zero-argument shape."""
    try:
        signature = inspect.signature(predicate)
    except (TypeError, ValueError):
        return bool(predicate(deadline))
    try:
        signature.bind(deadline)
    except TypeError:
        return bool(predicate())
    return bool(predicate(deadline))


def _readback_failure(result, message: str):
    return subprocess.CompletedProcess(
        result.args,
        READBACK_EXIT_CODE,
        _text(result.stdout),
        message,
    )


def request(
    arguments: Sequence[str],
    predicate: Callable | None = None,
    *,
    timeout: float = REQUEST_TIMEOUT,
):
    """Send an IPC request until it succeeds and its optional readback agrees."""
    command_args = [*_HYPRSUNSET, *arguments]
    deadline = time.monotonic() + max(0.0, float(timeout))
    result = _completed(command_args, DEADLINE_EXIT_CODE)

    while True:
        if time.monotonic() >= deadline:
            return result
        result = run_command(command_args, deadline=deadline)
        if result.returncode == 0:
            if predicate is None:
                return result
            acknowledged = result
            while True:
                if _invoke_readback(predicate, deadline):
                    return acknowledged
                result = _readback_failure(
                    acknowledged, "El estado observado no coincide con la solicitud"
                )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return result
                time.sleep(min(POLL_INTERVAL, remaining))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return result
        time.sleep(min(POLL_INTERVAL, remaining))


def _safe_temperature(value) -> int:
    if isinstance(value, bool):
        raise ValueError("La temperatura debe ser numerica")
    try:
        temperature = int(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("La temperatura debe ser numerica") from error
    if not TEMPERATURE_RANGE[0] <= temperature <= TEMPERATURE_RANGE[1]:
        raise ValueError("La temperatura esta fuera de rango")
    return temperature


def _safe_gamma(value) -> int:
    if isinstance(value, bool):
        raise ValueError("El gamma debe ser numerico")
    try:
        gamma = int(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("El gamma debe ser numerico") from error
    if not GAMMA_MIN <= gamma <= GAMMA_MAX:
        raise ValueError("El gamma esta fuera de rango")
    return gamma


def clamp_temperature(value: int) -> int:
    return max(NIGHT_TEMP_MIN, min(NIGHT_TEMP_MAX, int(value)))


def temperature_applied(temperature: int, *, deadline: float | None = None) -> bool:
    target = _safe_temperature(temperature)
    state = read_state(deadline=deadline)
    return (
        state.available
        and state.identity is False
        and state.temperature is not None
        and abs(state.temperature - target) <= TEMPERATURE_TOLERANCE
    )


def identity_applied(deadline: float | None = None) -> bool:
    return read_identity(deadline=deadline) is True


def set_temperature(temperature: int, *, timeout: float = REQUEST_TIMEOUT):
    target = _safe_temperature(temperature)
    return request(
        ["temperature", str(target)],
        lambda deadline: temperature_applied(target, deadline=deadline),
        timeout=timeout,
    )


def set_identity(*, timeout: float = REQUEST_TIMEOUT):
    return request(["identity"], identity_applied, timeout=timeout)


def gamma_applied(gamma, *, deadline: float | None = None) -> bool:
    target = _safe_gamma(gamma)
    observed = read_gamma(deadline=deadline)
    return observed is not None and abs(observed - target) <= GAMMA_TOLERANCE


def set_gamma(
    gamma: int, *, timeout: float = REQUEST_TIMEOUT
) -> subprocess.CompletedProcess:
    target = _safe_gamma(gamma)
    return request(
        ["gamma", str(target)],
        lambda deadline: gamma_applied(target, deadline=deadline),
        timeout=timeout,
    )


def reset_gamma(*, timeout: float = REQUEST_TIMEOUT) -> subprocess.CompletedProcess:
    """Reset gamma and require the documented default readback of 100%."""
    return request(
        ["reset", "gamma"],
        lambda deadline: gamma_applied(GAMMA_DEFAULT, deadline=deadline),
        timeout=timeout,
    )


def wait_for_state(
    timeout: float = START_TIMEOUT, *, deadline: float | None = None
) -> BackendState:
    operation_deadline = (
        deadline if deadline is not None else time.monotonic() + float(timeout)
    )
    state = read_state(deadline=operation_deadline)
    while state.active is None:
        remaining = operation_deadline - time.monotonic()
        if remaining <= 0:
            return state
        time.sleep(min(POLL_INTERVAL, remaining))
        state = read_state(deadline=operation_deadline)
    return state


def ensure_backend(timeout: float = START_TIMEOUT) -> BackendState:
    """Start the user service when needed, keeping startup under one deadline."""
    deadline = time.monotonic() + float(timeout)
    state = read_state(deadline=deadline)
    if state.active is not None:
        return state
    started = run_command(
        ["systemctl", "--user", "start", "hyprsunset.service"],
        deadline=deadline,
    )
    if started.returncode != 0:
        return state
    return wait_for_state(deadline=deadline)


def _service_flag(result, expected: str) -> bool | None:
    if result.returncode == 0:
        return _text(result.stdout).strip() == expected
    if result.returncode in {DEADLINE_EXIT_CODE, 127}:
        return None
    return False


def read_service_state(*, timeout: float = SERVICE_TIMEOUT) -> ServiceState:
    deadline = time.monotonic() + float(timeout)
    enabled = run_command(
        ["systemctl", "--user", "is-enabled", "hyprsunset.service"],
        deadline=deadline,
    )
    active = run_command(
        ["systemctl", "--user", "is-active", "hyprsunset.service"],
        deadline=deadline,
    )
    enabled_value = _service_flag(enabled, "enabled")
    if enabled.returncode == 0 and _text(enabled.stdout).strip() == "enabled-runtime":
        enabled_value = True
    return ServiceState(
        enabled_value,
        _service_flag(active, "active"),
    )


def load_temperature(
    path: Path, *, default: int = DEFAULT_TEMPERATURE
) -> int:
    safe_default = clamp_temperature(default)
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return safe_default
    if not isinstance(data, dict):
        return safe_default
    value = data.get("temperature", safe_default)
    if isinstance(value, bool):
        return safe_default
    try:
        value = int(value)
    except (TypeError, ValueError, OverflowError):
        return safe_default
    return clamp_temperature(value)


# Names kept as simple aliases for callers that used the old script helpers.
current_temperature = read_temperature
current_identity = read_identity
backend_state = read_state
request_hyprsunset = request
