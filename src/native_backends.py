#!/usr/bin/python3
"""Injected, testable command adapters for the Omarchy 4 native backends."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Callable, Sequence

import hyprsunset_backend
from brightness_utils import parse_brightness_info


COMMAND_TIMEOUT = 1.0
BRIGHTNESS_MAX_STEPS = 100
DEADLINE_EXIT_CODE = 124

PERCENT_MIN = 1
PERCENT_MAX = 100

DISPLAY_COMMAND = ("omarchy-hw-display",)
READ_COMMAND_PREFIX = ("brightnessctl", "-d")
WRITE_COMMAND = ("omarchy-brightness-display", "--no-osd")
SHELL_REFRESH_COMMAND = ("omarchy-shell", "-q", "nightlight", "refresh")

STEP_UP = "1%+"
STEP_DOWN = "1%-"


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


def run_command(
    args: Sequence[str], *, timeout: float = COMMAND_TIMEOUT
) -> subprocess.CompletedProcess:
    """Run one command array with a bounded timeout and never a shell."""
    try:
        return subprocess.run(
            args,
            text=True,
            capture_output=True,
            check=False,
            timeout=float(timeout),
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

    def _device(self) -> str | None:
        result = self._runner(DISPLAY_COMMAND, timeout=self._timeout)
        if result.returncode != 0:
            return None
        name = _text(result.stdout).strip()
        return name or None

    def _read(self) -> BrightnessState:
        monitor = self._device()
        if monitor is None:
            return BrightnessState(
                False, None, None, "No se pudo seleccionar un dispositivo de pantalla"
            )
        result = self._runner(
            [*READ_COMMAND_PREFIX, monitor, "-m"], timeout=self._timeout
        )
        if result.returncode != 0:
            return BrightnessState(
                False, None, monitor, _stderr(result.stderr, "No se pudo leer el brillo")
            )
        try:
            percent = parse_brightness_info(_text(result.stdout))["percent"]
        except (TypeError, ValueError):
            return BrightnessState(False, None, monitor, "Salida de brillo no reconocida")
        return BrightnessState(True, percent, monitor)

    def read_state(self) -> BrightnessState:
        return self._read()

    @staticmethod
    def _safe_delta(before: int, after: int, direction: int) -> bool:
        delta = after - before
        if direction > 0:
            return 0 <= delta <= 1
        if direction < 0:
            return -1 <= delta <= 0
        return delta == 0

    def step(self, direction: int) -> BrightnessState:
        direction = 1 if direction > 0 else -1 if direction < 0 else 0
        before = self._read()
        if not before.available or before.percent is None:
            return before
        if direction == 0:
            return before
        token = STEP_UP if direction > 0 else STEP_DOWN
        result = self._runner([*WRITE_COMMAND, token], timeout=self._timeout)
        if result.returncode != 0:
            return BrightnessState(
                False,
                before.percent,
                before.monitor,
                _stderr(result.stderr, "No se pudo cambiar el brillo"),
            )
        after = self._read()
        if not after.available or after.percent is None:
            return after
        if not self._safe_delta(before.percent, after.percent, direction):
            return BrightnessState(
                False,
                after.percent,
                after.monitor,
                "El dispositivo superó un paso de 1 %",
            )
        return after

    def set_percent(
        self, target: int, *, should_stop: Callable[[], bool] | None = None
    ) -> BrightnessState:
        target = max(PERCENT_MIN, min(PERCENT_MAX, int(target)))
        state = self._read()
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
            state = self.step(direction)
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