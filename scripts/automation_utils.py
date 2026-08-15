#!/usr/bin/python3
"""Automation orchestration for the Veilleuse night light plugin.

Pure and dependency-injected snooze, gradual transition and reconcile logic
built on top of the safe XDG persistence in ``state_utils``.

Design rules
------------
* No provider, model, UI or application-command dependency and **no daemon**:
  every orchestration is a synchronous in-process call.
* Every side effect (clock, sleeper, cancellability, night light reads,
  applies, schedule profile resolution and persistence) is injectable, so
  tests are fully deterministic and never touch the real system.
* The default wiring of the *night light* injectables (``read_nightlight``,
  ``apply_values``, ``apply_natural``, ``current_profile``) fails closed with
  ``helper_unavailable``: the CLI helper (``veilleuse-control``) injects its
  bounded IPC implementations when it wires this library.
* Provenance (``last_applied``) and history are updated only after the
  operation fully succeeded; partial failures are reported honestly with a
  stable machine-readable ``error_code``.
"""

from __future__ import annotations

import datetime
import threading
import time
from collections.abc import Mapping

# ---------------------------------------------------------------------------
# Bounds and tolerances (mirrors state_utils / veilleuse-control contracts).

SNOOZE_MINUTES_MIN = 1
SNOOZE_MINUTES_MAX = 1440
TEMPERATURE_MIN = 2500
TEMPERATURE_MAX = 6500
GAMMA_MIN = 0
GAMMA_MAX = 100
TRANSITION_SECONDS_MIN = 0
TRANSITION_SECONDS_MAX = 1800
STEP_INTERVAL_SECONDS = 1.0
IDENTITY_TEMPERATURE = 6000
DRIFT_TOLERANCE_TEMPERATURE = 50
# Deterministic cap for a manual override tied to the time-invariant identity
# profile: the longest possible identity period is under 24 hours, so a
# 24-hour boundary preserves the same-period semantics while guaranteeing the
# override can never persist forever.  Legacy identity overrides without an
# explicit ``until`` use the same duration from their ``at`` timestamp.
IDENTITY_OVERRIDE_DURATION_SECONDS = 24 * 60 * 60


class AutomationError(Exception):
    """Input/argument error with a stable machine-readable code."""

    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code


class CancellationToken:
    """Dismissable in-process cancellation flag.

    A running transition checks ``is_set()`` before every step; the caller
    cancels the previous token when a newer operation replaces it
    (latest-wins / process replacement).
    """

    def __init__(self):
        self._event = threading.Event()

    def is_set(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()


# ---------------------------------------------------------------------------
# state_utils access (works both as scripts.automation_utils and as a bare
# module exec'd by the CLI helper).

_STATE_UTILS = None


def _state_utils():
    global _STATE_UTILS
    if _STATE_UTILS is None:
        try:
            from scripts import state_utils as candidate
        except ImportError:  # bare-module context (helper exec)
            import state_utils as candidate
        _STATE_UTILS = candidate
    return _STATE_UTILS


# ---------------------------------------------------------------------------
# Helpers.

def _integer(value, label, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int):
        raise AutomationError(
            "invalid_argument", f"{label} debe ser un número entero"
        )
    if not minimum <= value <= maximum:
        raise AutomationError(
            "invalid_argument", f"{label} debe estar entre {minimum} y {maximum}"
        )
    return value


def _iso_timestamp(epoch) -> str:
    return datetime.datetime.fromtimestamp(
        float(epoch), tz=datetime.timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_epoch(value) -> float | None:
    """UTC epoch for an ISO-like timestamp, or ``None`` when malformed."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.datetime.fromisoformat(
            value.replace("Z", "+00:00")
        ).timestamp()
    except ValueError:
        return None


def _default_local_now() -> datetime.datetime:
    return datetime.datetime.now().astimezone()


def until_tomorrow_epoch(now_local: datetime.datetime) -> float:
    """Epoch of the next local midnight, computed in the local timezone.

    Correct across midnight and DST: the wall-clock ``tomorrow 00:00`` is
    built inside ``now_local``'s timezone, then converted with that zone's
    UTC offset for the resulting date (spring forward shortens the real
    interval, fall back lengthens it).
    """
    if not isinstance(now_local, datetime.datetime) or now_local.tzinfo is None:
        raise AutomationError(
            "invalid_argument", "La hora local debe incluir zona horaria"
        )
    naive = now_local.replace(tzinfo=None)
    midnight = (naive + datetime.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return midnight.replace(tzinfo=now_local.tzinfo).timestamp()


def snooze_status(state: Mapping, now: float) -> dict:
    """Pure snooze projection: active, expired or absent.

    An expiry at exactly ``now`` counts as expired, matching the reconcile
    boundary used by the persistence schema.
    """
    until = state.get("snooze_until")
    remaining = 0.0
    if until is not None and now < until:
        remaining = float(until) - float(now)
    return {
        "snoozed": remaining > 0,
        "snooze_until": until,
        "expires_in_seconds": remaining,
        "expires_in_minutes": int(remaining // 60),
    }


def ramp_schedule(
    current_temperature: int,
    current_gamma: int,
    target_temperature: int,
    target_gamma: int,
    steps: int,
):
    """Interpolated application schedule for one ramp.

    Returns ``steps`` ``(temperature, gamma)`` pairs covering the ramp; each
    value is monotonic toward its target, inside the [current, target] range,
    and the final pair is exactly the requested target.  ``round`` of a
    monotone interpolation is monotone, so values never overshoot.
    """
    if steps < 1:
        steps = 1
    schedule = []
    for index in range(1, steps + 1):
        fraction = index / steps
        schedule.append(
            (
                round(current_temperature + (target_temperature - current_temperature) * fraction),
                round(current_gamma + (target_gamma - current_gamma) * fraction),
            )
        )
    schedule[-1] = (target_temperature, target_gamma)
    return schedule


def _failure(error_code, message, **fields):
    result = {
        "success": False,
        "error_code": error_code,
        "error": message,
        "history_error": None,
    }
    result.update(fields)
    return result


def _success(**fields):
    result = {
        "success": True,
        "error_code": None,
        "error": None,
        "history_error": None,
    }
    result.update(fields)
    return result


def _failure_code(state: Mapping, fallback: str) -> str:
    code = state.get("error_code") if isinstance(state, Mapping) else None
    return code if isinstance(code, str) and code else fallback


def _natural_values(state: Mapping) -> dict:
    values = {}
    temperature = state.get("temperature")
    if temperature is not None:
        values["temperature"] = int(temperature)
    if state.get("identity") is True and "temperature" not in values:
        values["temperature"] = IDENTITY_TEMPERATURE
    gamma = state.get("gamma")
    if gamma is not None:
        values["gamma"] = int(gamma)
    if not values:
        values["temperature"] = IDENTITY_TEMPERATURE
    return values


def _profile_fingerprint(profile) -> dict | None:
    """Normalize a schedule profile to the stable period fingerprint.

    The fingerprint is constant for the whole day (identity or a single day
    temperature) and for the whole night (a single night temperature), so
    equality between the fingerprint captured at a manual action and the
    current profile tells reconcile whether the manual intent belongs to the
    same schedule period or a stale one.
    """
    if not isinstance(profile, Mapping) or profile.get("available") is not True:
        return None
    if profile.get("kind") == "identity":
        return {"kind": "identity"}
    if profile.get("kind") == "temperature":
        temperature = profile.get("temperature")
        if (
            isinstance(temperature, int)
            and not isinstance(temperature, bool)
            and TEMPERATURE_MIN <= temperature <= TEMPERATURE_MAX
        ):
            return {"kind": "temperature", "temperature": temperature}
    return None


def build_manual_override(profile, now, operation, values=None) -> dict | None:
    """Best-effort manual-intent record tied to the current schedule period.

    Returns ``None`` when no schedule profile is available (reconcile would
    fail closed on ``schedule_unavailable`` anyway, so no override is needed).
    Identity profiles are time-invariant, so their override carries a
    deterministic ``until`` boundary (see
    :data:`IDENTITY_OVERRIDE_DURATION_SECONDS`) instead of persisting forever.
    """
    fingerprint = _profile_fingerprint(profile)
    if fingerprint is None:
        return None
    record = {
        "at": _iso_timestamp(now),
        "operation": operation,
        "profile": fingerprint,
    }
    if fingerprint.get("kind") == "identity":
        record["until"] = _iso_timestamp(now + IDENTITY_OVERRIDE_DURATION_SECONDS)
    if values:
        normalized = {}
        for field in ("temperature", "gamma"):
            if values.get(field) is not None:
                normalized[field] = int(values[field])
        if normalized:
            record["values"] = normalized
    return record


def _identity_override_active(override: Mapping, now: float) -> bool:
    """True while an identity override is inside its deterministic boundary.

    Records written without an ``until`` (schema-1 migration) derive the
    boundary from their ``at`` timestamp plus the fixed duration, so a stale
    legacy identity override can never survive indefinitely.
    """
    until = override.get("until")
    if until is None:
        at = override.get("at")
        if at is None:
            return False
        until_epoch = _iso_epoch(at)
        if until_epoch is None:
            return False
        until_epoch += IDENTITY_OVERRIDE_DURATION_SECONDS
    else:
        until_epoch = _iso_epoch(until)
        if until_epoch is None:
            return False
    return float(now) < until_epoch


def _manual_override_active(override, profile, now) -> bool:
    """True while the manual override belongs to the current schedule period.

    Identity overrides additionally expire at their deterministic boundary;
    temperature overrides keep the period-bound semantics (active as long as
    the period fingerprint matches).
    """
    fingerprint = _profile_fingerprint(profile)
    if override is None or fingerprint is None:
        return False
    if not isinstance(override, Mapping):
        return False
    if override.get("profile") != fingerprint:
        return False
    if fingerprint.get("kind") == "identity" and not _identity_override_active(override, now):
        return False
    return True


def commit_manual_apply(env, operation, values=None) -> dict:
    """Persist provenance and manual intent for a successful manual apply.

    The provenance entry and the ``manual_override`` (tied to the schedule
    period active at apply time) are written atomically in the same state
    update so reconcile can preserve the manual filter within the period.
    """
    env = _resolve_env(env)
    now = env["now"]()
    try:
        profile = env["current_profile"]()
    except Exception:
        profile = None
    override = build_manual_override(profile, now, operation, values)
    entry = {
        "at": _iso_timestamp(now),
        "origin": "manual",
        "operation": operation,
    }
    if values:
        entry["values"] = dict(values)

    def _commit(current):
        next_state = {
            **current,
            "origin": "manual",
            "last_applied": entry,
        }
        if override is not None:
            next_state["manual_override"] = override
        elif current.get("manual_override") is not None:
            # The current schedule profile is temporarily unavailable, so a
            # fresh period fingerprint cannot be captured. Keep the existing
            # manual intent instead of clobbering it with None: reconcile is
            # the authority on whether that override is still current.
            next_state["manual_override"] = current["manual_override"]
        else:
            next_state["manual_override"] = None
        return next_state

    return env["update_state"](_commit)


def _append_history(env, record) -> str | None:
    """Append one history record, returning a history error code or None."""
    try:
        env["append_history"](record)
    except Exception as error:  # persistence must never mask core success
        return str(getattr(error, "error_code", "history_failed"))
    return None


def _history_record(operation, origin, now, *, values=None, success=True, error_code=None):
    record = {
        "time": _iso_timestamp(now),
        "operation": operation,
        "origin": origin,
        "success": success,
    }
    if values:
        for field in ("temperature", "gamma"):
            if field in values and values[field] is not None:
                record[field] = int(values[field])
    if error_code is not None:
        record["error_code"] = error_code
    return record


# ---------------------------------------------------------------------------
# Dependency resolution.

def default_env() -> dict:
    """Default injectables: real persistence and wall clock, fail-closed IO."""
    return {
        "now": time.time,
        "local_now": _default_local_now,
        "monotonic": time.monotonic,
        "sleep": time.sleep,
        "read_state": _state_utils().read_state,
        "update_state": _state_utils().update_state,
        "append_history": _state_utils().append_history,
        "read_nightlight": _default_read_nightlight,
        "apply_values": _default_apply_values,
        "apply_natural": _default_apply_natural,
        "current_profile": _default_current_profile,
        "token": lambda: None,
    }


def _resolve_env(env) -> dict:
    resolved = default_env()
    if env is None:
        return resolved
    if not isinstance(env, Mapping):
        raise ValueError("env must be a mapping")
    resolved.update(env)
    return resolved


def _token(env) -> object | None:
    provider = env["token"]
    if provider is None:
        return None
    if callable(provider):
        return provider()
    return provider


def _default_read_nightlight() -> dict:
    return {
        "available": False,
        "identity": None,
        "temperature": None,
        "gamma": None,
        "error_code": "helper_unavailable",
        "error": "El aplicador de luz nocturna no está configurado",
    }


def _default_apply_values(_temperature, _gamma) -> dict:
    return _default_read_nightlight()


def _default_apply_natural() -> dict:
    return _default_read_nightlight()


def _default_current_profile() -> dict:
    return {
        "available": False,
        "error_code": "helper_unavailable",
        "error": "El perfil de horario no está configurado",
    }


# ---------------------------------------------------------------------------
# Snooze.

def snooze_status_current(env=None) -> dict:
    """Read persisted state and project the snooze status at this moment."""
    env = _resolve_env(env)
    try:
        state = env["read_state"]()
    except Exception as error:
        return _failure(
            "state_failed",
            str(error) if str(error) else "No se pudo leer el estado",
            operation="snooze_status", applied=False,
            snoozed=False, snooze_until=None,
            expires_in_seconds=0.0, expires_in_minutes=0,
        )
    return snooze_status(state, env["now"]())


def _snooze_set_expiry(target_epoch: float, operation: str, env: dict, minutes=None) -> dict:
    now = env["now"]()
    natural = env["apply_natural"]()
    if not natural.get("available") or natural.get("error"):
        return _failure(
            _failure_code(natural, "apply_failed"),
            natural.get("error") or "No se pudo aplicar el color natural",
            operation=operation,
            applied=False,
            snoozed=False,
            snooze_until=None,
        )

    values = _natural_values(natural)
    at = _iso_timestamp(now)
    try:
        updated = env["update_state"](
            lambda current: {
                **current,
                "snooze_until": float(target_epoch),
                "manual_override": None,
                "last_applied": {
                    "at": at,
                    "origin": "snooze",
                    "operation": operation,
                    "values": values,
                },
            }
        )
    except Exception as error:
        code = "state_failed"
        history_error = _append_history(
            env,
            _history_record(
                operation, "snooze", now, values=values,
                success=False, error_code=code,
            ),
        )
        return _failure(
            code,
            str(error) if str(error) else "No se pudo guardar la posposición",
            operation=operation,
            applied=False,
            snoozed=False,
            snooze_until=None,
            history_error=history_error,
        )

    history_error = _append_history(
        env,
        _history_record(
            operation, "snooze", now, values=values, success=True
        ),
    )
    remaining = float(target_epoch) - now
    return _success(
        operation=operation,
        applied=True,
        snoozed=True,
        snooze_until=float(target_epoch),
        expires_in_seconds=remaining,
        expires_in_minutes=int(remaining // 60),
        temperature=values.get("temperature"),
        gamma=values.get("gamma"),
        history_error=history_error,
    )


def snooze_set(minutes, env=None) -> dict:
    """Snooze for ``minutes`` (1..1440): apply natural, then persist expiry.

    The expiry is persisted only after the natural application succeeded; the
    provenance entry and history record are written transactionally with the
    expiry in the same atomic state write.
    """
    env = _resolve_env(env)
    try:
        _integer(minutes, "La duración de la posposición", SNOOZE_MINUTES_MIN, SNOOZE_MINUTES_MAX)
    except AutomationError as error:
        return _failure(
            error.error_code, str(error),
            operation="snooze_set", applied=False,
            snoozed=False, snooze_until=None,
        )
    target = env["now"]() + int(minutes) * 60
    return _snooze_set_expiry(target, "snooze_set", env, minutes=minutes)


def snooze_until_tomorrow(env=None) -> dict:
    """Snooze until the next local midnight (accurate across midnight/DST)."""
    env = _resolve_env(env)
    try:
        target = until_tomorrow_epoch(env["local_now"]())
    except AutomationError as error:
        return _failure(
            error.error_code, str(error),
            operation="snooze_until_tomorrow", applied=False,
            snoozed=False, snooze_until=None,
        )
    return _snooze_set_expiry(target, "snooze_until_tomorrow", env)


def snooze_clear(env=None) -> dict:
    """Cancel an active snooze; already-clear is a successful no-op."""
    env = _resolve_env(env)
    try:
        state = env["read_state"]()
    except Exception as error:
        return _failure(
            "state_failed",
            str(error) if str(error) else "No se pudo leer el estado",
            operation="snooze_clear", applied=False, cleared=False,
            snoozed=False, snooze_until=None,
        )
    if state.get("snooze_until") is None:
        return _success(
            operation="snooze_clear", applied=False, cleared=False,
            snoozed=False, snooze_until=None,
        )
    now = env["now"]()
    try:
        env["update_state"](
            lambda current: {
                **current,
                "snooze_until": None,
                "manual_override": None,
            }
        )
    except Exception as error:
        code = "state_failed"
        history_error = _append_history(
            env,
            _history_record("snooze_clear", "snooze", now, success=False, error_code=code),
        )
        return _failure(
            code,
            str(error) if str(error) else "No se pudo cancelar la posposición",
            operation="snooze_clear", applied=False, cleared=False,
            snoozed=False, snooze_until=state.get("snooze_until"),
            history_error=history_error,
        )
    history_error = _append_history(
        env,
        _history_record("snooze_clear", "snooze", now, success=True),
    )
    return _success(
        operation="snooze_clear", applied=False, cleared=True,
        snoozed=False, snooze_until=None, history_error=history_error,
    )


# ---------------------------------------------------------------------------
# Transition ramp.

def _ramp_start(env: dict, target_temperature: int, target_gamma: int) -> tuple[dict, object]:
    """Read the current night light state and derive the ramp start values."""
    current = env["read_nightlight"]()
    if not current.get("available"):
        return None, _failure(
            _failure_code(current, "read_failed"),
            current.get("error") or "No se pudo leer el estado de la luz nocturna",
            operation="transition", applied=False,
            temperature=None, gamma=None, applied_steps=[],
        )
    if current.get("identity") is True:
        start_temperature = IDENTITY_TEMPERATURE
    else:
        start_temperature = current.get("temperature")
        if start_temperature is None:
            return None, _failure(
                "read_failed", "La temperatura actual no está disponible",
                operation="transition", applied=False,
                temperature=None, gamma=None, applied_steps=[],
            )
    start_gamma = current.get("gamma")
    if start_gamma is None:
        return None, _failure(
            "read_failed", "La gamma actual no está disponible",
            operation="transition", applied=False,
            temperature=None, gamma=None, applied_steps=[],
        )
    return {"temperature": int(start_temperature), "gamma": int(start_gamma)}, None


def _run_ramp(
    env: dict,
    start: Mapping,
    target_temperature: int,
    target_gamma: int,
    seconds: float,
    token: object,
    *,
    operation: str = "transition",
) -> tuple[bool, object]:
    """Drive one gradual ramp: monotonic bounded steps, shared deadline.

    Returns ``(success, detail)`` where ``detail`` is the list of applied
    steps on success or the honest partial-failure dict otherwise.  No step
    is applied after the shared deadline or once the token is set.
    """
    deadline = env["monotonic"]() + seconds
    steps = max(1, int(seconds / STEP_INTERVAL_SECONDS))
    schedule = ramp_schedule(
        start["temperature"], start["gamma"],
        target_temperature, target_gamma, steps,
    )
    applied = []
    last_values = None
    for index, values in enumerate(schedule):
        remaining = deadline - env["monotonic"]()
        if remaining <= 0:
            return False, _failure(
                "deadline", "El plazo de la transición ha expirado",
                operation=operation, applied=False,
                temperature=applied[-1][0] if applied else None,
                gamma=applied[-1][1] if applied else None,
                applied_steps=list(applied), seconds=seconds,
            )
        if token is not None and token.is_set():
            return False, _failure(
                "cancelled", "La transición fue cancelada",
                operation=operation, applied=False,
                temperature=applied[-1][0] if applied else None,
                gamma=applied[-1][1] if applied else None,
                applied_steps=list(applied), seconds=seconds,
            )
        if values != last_values:
            state = env["apply_values"](*values)
            if not state.get("available") or state.get("error"):
                return False, _failure(
                    _failure_code(state, "apply_failed"),
                    state.get("error") or "No se pudo aplicar un paso de la transición",
                    operation=operation, applied=False,
                    temperature=applied[-1][0] if applied else None,
                    gamma=applied[-1][1] if applied else None,
                    applied_steps=list(applied), seconds=seconds,
                )
            applied.append(values)
            last_values = values
        if index < len(schedule) - 1:
            env["sleep"](min(STEP_INTERVAL_SECONDS, remaining))
    return True, applied


def transition(target_temperature, target_gamma, seconds, env=None) -> dict:
    """Ramp temperature and gamma coherently over ``seconds`` (0..1800).

    ``seconds == 0`` applies the exact target once (immediate mode).  Longer
    ramps share one deadline, use monotonic bounded steps, honor the
    cancellation token and never spawn a daemon.  Provenance and history are
    committed only after the whole ramp succeeded.
    """
    env = _resolve_env(env)
    try:
        temperature = _integer(target_temperature, "La temperatura", TEMPERATURE_MIN, TEMPERATURE_MAX)
        gamma = _integer(target_gamma, "La gamma", GAMMA_MIN, GAMMA_MAX)
        seconds_value = _integer(
            seconds, "La duración de la transición",
            TRANSITION_SECONDS_MIN, TRANSITION_SECONDS_MAX,
        )
    except AutomationError as error:
        return _failure(
            error.error_code, str(error),
            operation="transition", applied=False,
            temperature=None, gamma=None, applied_steps=[],
        )

    token = _token(env)
    if seconds_value == 0:
        state = env["apply_values"](temperature, gamma)
        if not state.get("available") or state.get("error"):
            return _failure(
                _failure_code(state, "apply_failed"),
                state.get("error") or "No se pudo aplicar la transición",
                operation="transition", applied=False,
                temperature=None, gamma=None, applied_steps=[],
            )
        applied = [(temperature, gamma)]
    else:
        start, error = _ramp_start(env, temperature, gamma)
        if start is None:
            return error
        ok, detail = _run_ramp(env, start, temperature, gamma, float(seconds_value), token)
        if not ok:
            return detail
        applied = detail

    now = env["now"]()
    values = {"temperature": temperature, "gamma": gamma}
    try:
        profile = env["current_profile"]()
    except Exception:
        profile = None
    override = build_manual_override(profile, now, "transition", values)
    try:
        env["update_state"](
            lambda current: {
                **current,
                "origin": "manual",
                "last_applied": {
                    "at": _iso_timestamp(now),
                    "origin": "manual",
                    "operation": "transition",
                    "values": values,
                },
                "manual_override": override,
            }
        )
    except Exception as error:
        code = "state_failed"
        history_error = _append_history(
            env,
            _history_record(
                "transition", "manual", now, values=values,
                success=False, error_code=code,
            ),
        )
        return _failure(
            code,
            str(error) if str(error) else "No se pudo guardar la transición",
            operation="transition", applied=False,
            temperature=None, gamma=None, applied_steps=list(applied),
            history_error=history_error,
        )
    history_error = _append_history(
        env,
        _history_record("transition", "manual", now, values=values, success=True),
    )
    return _success(
        operation="transition", applied=True,
        temperature=temperature, gamma=gamma,
        seconds=seconds_value, steps=len(applied),
        applied_steps=list(applied), history_error=history_error,
    )


# ---------------------------------------------------------------------------
# Reconcile.

def _profile_drift(profile: Mapping, current: Mapping) -> bool:
    if profile.get("kind") == "identity":
        return current.get("identity") is not True
    target = profile.get("temperature")
    if current.get("identity") is True:
        return True
    current_temperature = current.get("temperature")
    if current_temperature is None or target is None:
        return True
    return abs(int(current_temperature) - int(target)) > DRIFT_TOLERANCE_TEMPERATURE


def _apply_profile(
    env: dict, profile: Mapping, current: Mapping,
    transition_seconds: int, token: object,
) -> tuple[dict, list | None]:
    """Apply the schedule profile; returns ``(result, applied_values_or_None)``."""
    if profile.get("kind") == "identity":
        state = env["apply_natural"]()
        if not state.get("available") or state.get("error"):
            return _failure(
                _failure_code(state, "apply_failed"),
                state.get("error") or "No se pudo aplicar el color natural",
                operation="reconcile", applied=False, snoozed=False,
            ), None
        return _success(operation="reconcile", applied=True, snoozed=False), _natural_values(state)

    target_temperature = profile.get("temperature")
    if target_temperature is None:
        return _failure(
            "schedule_unavailable", "El perfil de horario no define temperatura",
            operation="reconcile", applied=False, snoozed=False,
        ), None
    start = {"temperature": current.get("temperature"), "gamma": current.get("gamma")}
    if start["temperature"] is None or start["gamma"] is None:
        return _failure(
            "read_failed", "El estado de la luz nocturna está incompleto",
            operation="reconcile", applied=False, snoozed=False,
        ), None
    start_temperature = (
        IDENTITY_TEMPERATURE if current.get("identity") is True else int(start["temperature"])
    )
    start_gamma = int(start["gamma"])
    if transition_seconds == 0:
        state = env["apply_values"](target_temperature, start_gamma)
        if not state.get("available") or state.get("error"):
            return _failure(
                _failure_code(state, "apply_failed"),
                state.get("error") or "No se pudo aplicar el perfil",
                operation="reconcile", applied=False, snoozed=False,
            ), None
        applied = [(target_temperature, start_gamma)]
    else:
        ok, detail = _run_ramp(
            env,
            {"temperature": start_temperature, "gamma": start_gamma},
            target_temperature, start_gamma,
            float(transition_seconds), token,
            operation="reconcile",
        )
        if not ok:
            return detail, None
        applied = detail
    values = {"temperature": target_temperature, "gamma": start_gamma}
    return _success(operation="reconcile", applied=True, snoozed=False), values


def _commit_reconcile(env: dict, values: dict) -> tuple[bool, str | None]:
    """Persist provenance and history for one reconcile apply.

    Returns ``(ok, history_error)``: ``ok`` is False only when the atomic
    provenance write failed (the caller must report an honest failure).
    """
    now = env["now"]()
    try:
        env["update_state"](
            lambda current: {
                **current,
                "last_applied": {
                    "at": _iso_timestamp(now),
                    "origin": "automatic",
                    "operation": "reconcile_schedule",
                    "values": values,
                },
                "manual_override": None,
            }
        )
    except Exception:
        return False, None
    return True, _append_history(
        env,
        _history_record(
            "reconcile_schedule", "automatic", now, values=values, success=True
        ),
    )


def reconcile(env=None) -> dict:
    """Idempotent enforcement of snooze and schedule.

    * While snoozed: enforce natural identity (no-op once natural).
    * On expiry: clear the snooze first, then apply the current schedule
      profile once (even without drift) using the configured transition.
    * Otherwise: apply the current period only when drift exists.
    """
    env = _resolve_env(env)
    try:
        state = env["read_state"]()
    except Exception as error:
        return _failure(
            "state_failed",
            str(error) if str(error) else "No se pudo leer el estado",
            operation="reconcile", applied=False, snoozed=False,
        )
    now = env["now"]()
    snooze_until = state.get("snooze_until")
    snoozed = snooze_until is not None and now < snooze_until
    token = _token(env)

    if snoozed:
        current = env["read_nightlight"]()
        if not current.get("available"):
            return _failure(
                _failure_code(current, "read_failed"),
                current.get("error") or "No se pudo leer el estado de la luz nocturna",
                operation="reconcile", applied=False, snoozed=True,
            )
        if current.get("identity") is True:
            if state.get("manual_override") is not None:
                try:
                    env["update_state"](
                        lambda current_state: {
                            **current_state,
                            "manual_override": None,
                        }
                    )
                except Exception:
                    return _failure(
                        "state_failed",
                        "No se pudo limpiar el modo manual durante la posposición",
                        operation="reconcile", applied=False, snoozed=True,
                    )
            return _success(operation="reconcile", applied=False, snoozed=True)
        natural = env["apply_natural"]()
        if not natural.get("available") or natural.get("error"):
            return _failure(
                _failure_code(natural, "apply_failed"),
                natural.get("error") or "No se pudo aplicar el color natural",
                operation="reconcile", applied=False, snoozed=True,
            )
        values = _natural_values(natural)
        now = env["now"]()
        try:
            env["update_state"](
                lambda current_state: {
                    **current_state,
                    "manual_override": None,
                    "last_applied": {
                        "at": _iso_timestamp(now),
                        "origin": "snooze",
                        "operation": "reconcile_snooze",
                        "values": values,
                    },
                }
            )
        except Exception as error:
            return _failure(
                "state_failed",
                str(error) if str(error) else "No se pudo guardar el estado",
                operation="reconcile", applied=False, snoozed=True,
            )
        history_error = _append_history(
            env,
            _history_record(
                "reconcile_snooze", "snooze", now, values=values, success=True
            ),
        )
        return _success(
            operation="reconcile", applied=True, snoozed=True,
            history_error=history_error,
        )

    if snooze_until is not None and now >= snooze_until:
        # Expiry: clear the snooze (one-shot) and any manual intent recorded
        # during the snooze (snooze_set always clears it, so an override here
        # cannot predate the snooze), then apply the profile once.
        try:
            env["update_state"](
                lambda current: {
                    **current,
                    "snooze_until": None,
                    "manual_override": None,
                }
            )
        except Exception as error:
            return _failure(
                "state_failed",
                str(error) if str(error) else "No se pudo limpiar la posposición",
                operation="reconcile", applied=False, snoozed=False,
            )
        if state.get("schedule_enabled") is not True:
            return _success(operation="reconcile", applied=False, snoozed=False)

        profile = env["current_profile"]()
        if not profile.get("available"):
            return _failure(
                _failure_code(profile, "schedule_unavailable"),
                profile.get("error") or "El perfil de horario no está disponible",
                operation="reconcile", applied=False, snoozed=False,
            )
        current = env["read_nightlight"]()
        if not current.get("available"):
            return _failure(
                _failure_code(current, "read_failed"),
                current.get("error") or "No se pudo leer el estado de la luz nocturna",
                operation="reconcile", applied=False, snoozed=False,
            )
        result, values = _apply_profile(
            env, profile, current, state.get("transition_seconds", 0), token
        )
        if not result.get("success"):
            return result
        committed, history_error = _commit_reconcile(env, values)
        if not committed:
            return _failure(
                "state_failed", "No se pudo guardar el perfil aplicado",
                operation="reconcile", applied=False, snoozed=False,
                temperature=values.get("temperature"),
                gamma=values.get("gamma"),
            )
        return _success(
            operation="reconcile", applied=True, snoozed=False,
            temperature=values.get("temperature"),
            gamma=values.get("gamma"),
            history_error=history_error,
        )

    # Otherwise: apply the current period only when drift exists, honoring a
    # manual intent recorded in the same schedule period.
    if state.get("schedule_enabled") is not True:
        if state.get("manual_override") is not None:
            try:
                env["update_state"](
                    lambda current_state: {
                        **current_state,
                        "manual_override": None,
                    }
                )
            except Exception as error:
                return _failure(
                    "state_failed",
                    str(error) if str(error) else "No se pudo limpiar el modo manual con el horario desactivado",
                    operation="reconcile", applied=False, snoozed=False,
                )
        return _success(operation="reconcile", applied=False, snoozed=False)

    profile = env["current_profile"]()
    if not profile.get("available"):
        return _failure(
            _failure_code(profile, "schedule_unavailable"),
            profile.get("error") or "El perfil de horario no está disponible",
            operation="reconcile", applied=False, snoozed=False,
        )
    override = state.get("manual_override")
    if _manual_override_active(override, profile, env["now"]()):
        return _success(
            operation="reconcile", applied=False, snoozed=False,
            manual_override=True,
        )
    current = env["read_nightlight"]()
    if not current.get("available"):
        return _failure(
            _failure_code(current, "read_failed"),
            current.get("error") or "No se pudo leer el estado de la luz nocturna",
            operation="reconcile", applied=False, snoozed=False,
        )
    if not _profile_drift(profile, current):
        if override is not None:
            try:
                env["update_state"](
                    lambda current_state: {**current_state, "manual_override": None}
                )
            except Exception:
                return _failure(
                    "state_failed",
                    "No se pudo limpiar el modo manual del período anterior",
                    operation="reconcile", applied=False, snoozed=False,
                )
        return _success(operation="reconcile", applied=False, snoozed=False)

    result, values = _apply_profile(
        env, profile, current, state.get("transition_seconds", 0), token
    )
    if not result.get("success"):
        return result
    committed, history_error = _commit_reconcile(env, values)
    if not committed:
        return _failure(
            "state_failed", "No se pudo guardar el perfil aplicado",
            operation="reconcile", applied=False, snoozed=False,
            temperature=values.get("temperature"),
            gamma=values.get("gamma"),
        )
    return _success(
        operation="reconcile", applied=True, snoozed=False,
        temperature=values.get("temperature"),
        gamma=values.get("gamma"),
        history_error=history_error,
    )


__all__ = [
    "AutomationError", "CancellationToken",
    "SNOOZE_MINUTES_MIN", "SNOOZE_MINUTES_MAX",
    "TEMPERATURE_MIN", "TEMPERATURE_MAX", "GAMMA_MIN", "GAMMA_MAX",
    "TRANSITION_SECONDS_MIN", "TRANSITION_SECONDS_MAX",
    "STEP_INTERVAL_SECONDS", "IDENTITY_TEMPERATURE",
    "DRIFT_TOLERANCE_TEMPERATURE", "IDENTITY_OVERRIDE_DURATION_SECONDS",
    "build_manual_override", "commit_manual_apply",
    "default_env", "ramp_schedule", "snooze_status",
    "snooze_status_current", "snooze_set", "snooze_until_tomorrow",
    "snooze_clear", "transition", "reconcile", "until_tomorrow_epoch",
]
