#!/usr/bin/python3
"""Injected, testable command adapters for the Omarchy 4 native backends.

Brightness reads and writes converge on one Omarchy surface: the focused
Hyprland monitor is selected with ``omarchy-hyprland-monitor-focused`` and
every operation goes through ``omarchy-brightness-display --no-osd --monitor``
for both reads (no step argument) and one-percent writes (``+1%`` / ``1%-``).
That single entry point routes internal backlights, DDC/CI monitors and Apple
displays exactly like Omarchy itself.  State is refreshed from hardware after
every write and a non-numeric readback fails closed.
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Sequence

import hyprsunset_backend


COMMAND_TIMEOUT = 1.0
BRIGHTNESS_MAX_STEPS = 100
DEADLINE_EXIT_CODE = 124

PERCENT_MIN = 1
PERCENT_MAX = 100
READBACK_RETRIES = 2
READBACK_POLL = 0.05

# One Omarchy entry point for focused-monitor selection, reads and writes.
MONITOR_COMMAND = ("omarchy-hyprland-monitor-focused",)
BRIGHTNESS_COMMAND = ("omarchy-brightness-display", "--no-osd", "--monitor")
SHELL_REFRESH_COMMAND = ("omarchy-shell", "-q", "nightlight", "refresh")

# Omarchy accepted adjustment tokens: `[+N%|N%-|N%|off|on]`.
STEP_UP = "+1%"
STEP_DOWN = "1%-"

_PERCENT_PATTERN = re.compile(r"\s*([0-9]{1,3})\s*")


@dataclass(frozen=True)
class BrightnessState:
    available: bool
    percent: int | None
    monitor: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class NightLightState:
    available: bool
    enabled: bool | None
    temperature: int | None
    identity: bool | None
    gamma: int | None
    error: str | None = None


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _remaining(deadline: float | None) -> float | None:
    return None if deadline is None else deadline - time.monotonic()


def run_command(
    args: Sequence[str],
    *,
    timeout: float = COMMAND_TIMEOUT,
    deadline: float | None = None,
) -> subprocess.CompletedProcess:
    """Run one command array under a per-command timeout and a total deadline."""
    remaining = _remaining(deadline)
    if remaining is not None:
        if remaining <= 0:
            return subprocess.CompletedProcess(
                list(args),
                DEADLINE_EXIT_CODE,
                "",
                "Se agoto el plazo de la operacion",
            )
        timeout = min(float(timeout), remaining)
    else:
        timeout = float(timeout)
    if timeout <= 0:
        return subprocess.CompletedProcess(
            list(args),
            DEADLINE_EXIT_CODE,
            "",
            "Se agoto el plazo de la operacion",
        )

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


def refresh_nightlight(
    *,
    runner: Callable = run_command,
    timeout: float = COMMAND_TIMEOUT,
    command: Sequence[str] = SHELL_REFRESH_COMMAND,
) -> None:
    """Best-effort shell refresh that never raises on failure."""
    try:
        runner(command, timeout=timeout)
    except Exception:
        pass


def _stderr(stderr, fallback):
    message = _text(stderr).strip()
    return message or fallback


def _parse_percent(output) -> int | None:
    """Parse a plain integer percentage; anything else fails closed."""
    match = _PERCENT_PATTERN.fullmatch(_text(output))
    if match is None:
        return None
    return max(PERCENT_MIN, min(PERCENT_MAX, int(match.group(1))))


class OmarchyBrightnessBackend:
    def __init__(
        self,
        *,
        runner: Callable | None = None,
        timeout: float = COMMAND_TIMEOUT,
        max_steps: int = BRIGHTNESS_MAX_STEPS,
    ):
        self._runner = runner if runner is not None else run_command
        self._timeout = float(timeout)
        self._max_steps = int(max_steps)

    def _operation_deadline(self, deadline: float | None) -> float:
        if deadline is not None:
            return max(0.0, float(deadline))
        return time.monotonic() + max(0.0, self._timeout * 4.0)

    def _monitor(self, deadline: float) -> str | None:
        result = self._runner(MONITOR_COMMAND, timeout=self._timeout, deadline=deadline)
        if result.returncode != 0:
            return None
        name = _text(result.stdout).strip()
        return name or None

    def _read(self, deadline: float) -> BrightnessState:
        monitor = self._monitor(deadline)
        if monitor is None:
            return BrightnessState(
                False, None, None, "No se pudo seleccionar un monitor enfocado"
            )
        result = self._runner(
            [*BRIGHTNESS_COMMAND, monitor],
            timeout=self._timeout,
            deadline=deadline,
        )
        if result.returncode != 0:
            return BrightnessState(
                False, None, monitor, _stderr(result.stderr, "No se pudo leer el brillo")
            )
        percent = _parse_percent(result.stdout)
        if percent is None:
            return BrightnessState(False, None, monitor, "Salida de brillo no reconocida")
        return BrightnessState(True, percent, monitor)

    def read_state(self, *, deadline: float | None = None) -> BrightnessState:
        return self._read(self._operation_deadline(deadline))

    @staticmethod
    def _safe_delta(before: int, after: int, direction: int) -> bool:
        delta = after - before
        if direction > 0:
            return 0 <= delta <= 1
        if direction < 0:
            return -1 <= delta <= 0
        return delta == 0

    def _readback(self, before: int, direction: int, deadline: float) -> BrightnessState:
        """Confirm a write, retrying only transient non-numeric races."""
        after = None
        for attempt in range(READBACK_RETRIES + 1):
            after = self._read(deadline)
            if after.available and after.percent is not None:
                if not self._safe_delta(before, after.percent, direction):
                    return BrightnessState(
                        False,
                        after.percent,
                        after.monitor,
                        "El dispositivo superó un paso de 1 %",
                    )
                return after
            remaining = _remaining(deadline)
            if attempt >= READBACK_RETRIES or (remaining is not None and remaining <= 0):
                break
            time.sleep(READBACK_POLL if remaining is None else min(READBACK_POLL, remaining))
        return after

    def step(self, direction: int, *, deadline: float | None = None) -> BrightnessState:
        operation_deadline = self._operation_deadline(deadline)
        direction = 1 if direction > 0 else -1 if direction < 0 else 0
        before = self._read(operation_deadline)
        if not before.available or before.percent is None:
            return before
        if direction == 0:
            return before
        token = STEP_UP if direction > 0 else STEP_DOWN
        monitor = before.monitor
        result = self._runner(
            [*BRIGHTNESS_COMMAND, monitor, token],
            timeout=self._timeout,
            deadline=operation_deadline,
        )
        if result.returncode != 0:
            return BrightnessState(
                False,
                before.percent,
                monitor,
                _stderr(result.stderr, "No se pudo cambiar el brillo"),
            )
        return self._readback(before.percent, direction, operation_deadline)

    def set_percent(
        self,
        target: int,
        *,
        should_stop: Callable[[], bool] | None = None,
        deadline: float | None = None,
    ) -> BrightnessState:
        operation_deadline = self._operation_deadline(deadline)
        target = max(PERCENT_MIN, min(PERCENT_MAX, int(target)))
        state = self._read(operation_deadline)
        if not state.available or state.percent is None:
            return state
        for _ in range(self._max_steps):
            if should_stop is not None and should_stop():
                return BrightnessState(
                    state.available, state.percent, state.monitor, "Operación cancelada"
                )
            if state.percent == target:
                return state
            direction = 1 if target > state.percent else -1
            state = self.step(direction, deadline=operation_deadline)
            if not state.available or state.percent is None:
                return state
        if state.percent != target:
            return BrightnessState(
                state.available,
                state.percent,
                state.monitor,
                "No se pudo alcanzar el nivel solicitado",
            )
        return state


class OmarchyNightLightBackend:
    def __init__(
        self,
        *,
        read_state: Callable | None = None,
        set_temperature: Callable | None = None,
        set_identity: Callable | None = None,
        set_gamma: Callable | None = None,
        reset_gamma: Callable | None = None,
        runner: Callable | None = None,
        timeout: float = COMMAND_TIMEOUT,
    ):
        self._read_state = read_state or hyprsunset_backend.read_state
        self._set_temperature = set_temperature or hyprsunset_backend.set_temperature
        self._set_identity = set_identity or hyprsunset_backend.set_identity
        self._set_gamma = set_gamma or hyprsunset_backend.set_gamma
        self._reset_gamma = reset_gamma or hyprsunset_backend.reset_gamma
        self._runner = runner if runner is not None else run_command
        self._timeout = float(timeout)

    @staticmethod
    def _confirmed(result) -> bool:
        return getattr(result, "returncode", 1) == 0

    def _to_state(self, backend_state, error=None) -> NightLightState:
        if backend_state is None or not getattr(backend_state, "available", False):
            return NightLightState(
                False, None, None, None, None, error or "Backend no disponible"
            )
        return NightLightState(
            available=True,
            enabled=backend_state.active,
            temperature=backend_state.temperature,
            identity=backend_state.identity,
            gamma=backend_state.gamma,
            error=error,
        )

    def _refresh_state(self, error=None) -> NightLightState:
        try:
            return self._to_state(self._read_state(), error=error)
        except Exception as caught:
            return NightLightState(False, None, None, None, None, str(caught))

    def read_state(self) -> NightLightState:
        try:
            return self._to_state(self._read_state())
        except Exception as caught:
            return NightLightState(False, None, None, None, None, str(caught))

    def _apply(self, operation: Callable, failure_message: str) -> NightLightState:
        try:
            result = operation()
        except Exception as caught:
            return NightLightState(False, None, None, None, None, str(caught))
        if not self._confirmed(result):
            return self._refresh_state(failure_message)
        refresh_nightlight(runner=self._runner, timeout=self._timeout)
        return self._refresh_state()

    def set_temperature(self, kelvin: int) -> NightLightState:
        return self._apply(
            lambda: self._set_temperature(kelvin),
            "No se pudo confirmar la temperatura aplicada",
        )

    def set_natural(self) -> NightLightState:
        return self._apply(
            self._set_identity,
            "No se pudo confirmar el color natural",
        )

    def set_gamma(self, percent: int) -> NightLightState:
        return self._apply(
            lambda: self._set_gamma(percent),
            "No se pudo confirmar el brillo percibido",
        )

    def reset_gamma(self) -> NightLightState:
        return self._apply(
            self._reset_gamma,
            "No se pudo restablecer el brillo percibido",
        )
