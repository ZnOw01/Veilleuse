#!/usr/bin/python3
from __future__ import annotations

import json
import re
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

try:
  from ui_accessibility import set_description, set_range, set_status
except ModuleNotFoundError as error:
  if error.name != "ui_accessibility":
    raise
  sys.path.insert(0, str(Path(__file__).resolve().parent))
  from ui_accessibility import set_description, set_range, set_status

try:
  from schedule_utils import (
    DAY_TEMP,
    DAY_TEMP_MAX,
    DAY_TEMP_MIN,
    DEFAULT_TEMP,
    HYPRSUNSET_CONFIG,
    NIGHT_TEMP_MAX,
    NIGHT_TEMP_MIN,
    SETTINGS_PATH,
    STATE_LOCK,
    atomic_write_text,
    day_profile_is_identity,
    default_schedule,
    exclusive_lock,
    iter_profile_blocks,
    normalize_clock,
    parse_schedule_text,
    profile_info,
    profile_kind,
    schedule_period,
    validate_schedule,
  )
except ModuleNotFoundError as error:
  if error.name != "schedule_utils":
    raise
  sys.path.insert(0, str(Path(__file__).resolve().parent))
  from schedule_utils import (
    DAY_TEMP,
    DAY_TEMP_MAX,
    DAY_TEMP_MIN,
    DEFAULT_TEMP,
    HYPRSUNSET_CONFIG,
    NIGHT_TEMP_MAX,
    NIGHT_TEMP_MIN,
    SETTINGS_PATH,
    STATE_LOCK,
    atomic_write_text,
    day_profile_is_identity,
    default_schedule,
    exclusive_lock,
    iter_profile_blocks,
    normalize_clock,
    parse_schedule_text,
    profile_info,
    profile_kind,
    schedule_period,
    validate_schedule,
  )

try:
  from hyprsunset_backend import (
    BackendState,
    DEFAULT_TEMPERATURE,
    read_state as read_backend_state,
    ensure_backend,
    load_temperature as backend_load_temperature,
    read_identity as backend_read_identity,
    read_service_state,
    read_state,
    read_temperature as backend_read_temperature,
    request as backend_request,
    run_command as backend_run_command,
    set_identity,
    set_temperature,
    set_gamma,
  )
except ModuleNotFoundError as error:
  if error.name != "hyprsunset_backend":
    raise
  sys.path.insert(0, str(Path(__file__).resolve().parent))
  from hyprsunset_backend import (
    BackendState,
    DEFAULT_TEMPERATURE,
    read_state as read_backend_state,
    ensure_backend,
    load_temperature as backend_load_temperature,
    read_identity as backend_read_identity,
    read_service_state,
    read_state,
    read_temperature as backend_read_temperature,
    request as backend_request,
    run_command as backend_run_command,
    set_identity,
    set_temperature,
    set_gamma,
  )


APP_ID = "com.snowflake.NightLight"
CONFIG_PATH = SETTINGS_PATH
GAMMA_SETTINGS_PATH = SETTINGS_PATH.with_name("gamma.json")
GAMMA_UI_MIN = 50
GAMMA_UI_MAX = 100
GAMMA_DEFAULT = 100
GAMMA_WARNING = "Puede reducir la precisión del color."
SERVICE_NAME = "hyprsunset.service"

# Compatibility names used by the command-line tools and older callers.  The
# implementation remains in hyprsunset_backend.py.
current_temperature = backend_read_temperature
current_identity = backend_read_identity


def backend_state():
  """Return the legacy ``(active, temperature)`` compatibility tuple."""
  state = read_backend_state()
  if not state.available or state.active is None:
    return None, None
  if state.identity is True:
    return False, DAY_TEMP
  if state.temperature is None:
    return None, None
  return state.active, state.temperature


request_hyprsunset = backend_request


CSS = """
/* ---------------------------------------------------------------------------
 * Design tokens — warm, temperature-aware accents on top of libadwaita.
 * Surfaces, borders and state colors come from the active system theme so
 * the app follows Omarchy light/dark themes; the amber ramp is semantic
 * (it represents color temperature) and works in both modes.
 * ------------------------------------------------------------------------ */
@define-color nl_warm        #f2a35e;
@define-color nl_warm_strong #e8893f;
@define-color nl_warm_soft   rgba(242, 163, 94, 0.16);
@define-color nl_warm_line   rgba(242, 163, 94, 0.30);
@define-color nl_warm_text   #ffc98f;
@define-color nl_knob        #fff7ec;

window {
  background: @window_bg_color;
}

.app-content {
  padding-bottom: 10px;
}

/* ---------------------------------- Hero -------------------------------- */

.hero-card {
  background: linear-gradient(140deg,
    rgba(242, 163, 94, 0.20),
    rgba(242, 163, 94, 0.09) 46%,
    rgba(143, 184, 216, 0.07));
  border: 1px solid @nl_warm_line;
  border-radius: 24px;
  padding: 24px;
  transition: background 400ms ease, border-color 400ms ease;
}

.hero-card.inactive {
  background: @card_bg_color;
  border-color: alpha(@borders, 0.70);
}

.hero-icon-wrap {
  background: @nl_warm_soft;
  border: 1px solid @nl_warm_line;
  border-radius: 999px;
  padding: 15px;
}

.hero-card.inactive .hero-icon-wrap {
  background: alpha(@theme_fg_color, 0.06);
  border-color: alpha(@borders, 0.60);
}

.hero-icon {
  color: @nl_warm_text;
}

.hero-card.inactive .hero-icon {
  color: alpha(@theme_fg_color, 0.72);
}

.eyebrow {
  color: alpha(@theme_fg_color, 0.58);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
}

.hero-title {
  font-size: 26px;
  font-weight: 800;
}

.hero-subtitle {
  color: alpha(@theme_fg_color, 0.74);
  font-size: 13.5px;
}

/* ------------------------------- Status line ---------------------------- */

.status-pill {
  background: alpha(@theme_fg_color, 0.07);
  border: 1px solid alpha(@theme_fg_color, 0.09);
  border-radius: 999px;
  padding: 6px 13px;
  font-size: 13px;
  font-weight: 700;
  color: alpha(@theme_fg_color, 0.86);
  transition: background 300ms ease, border-color 300ms ease, color 300ms ease;
}

.status-pill.active {
  background: @nl_warm_soft;
  border-color: @nl_warm_line;
  color: @nl_warm_text;
}

.status-pill.error {
  background: alpha(@error_color, 0.12);
  border-color: alpha(@error_color, 0.32);
  color: @error_color;
}

.metric-value {
  font-size: 34px;
  font-weight: 800;
}

.metric-unit {
  color: alpha(@theme_fg_color, 0.62);
  font-size: 14px;
}

.operation-status {
  color: alpha(@theme_fg_color, 0.60);
  font-size: 12px;
  font-weight: 600;
}

.operation-status.applying {
  color: @warning_color;
}

.operation-status.confirmed {
  color: @success_color;
}

.operation-status.error {
  color: @error_color;
}

/* ------------------------------- Section cards -------------------------- */

.section-card {
  background: @card_bg_color;
  border: 1px solid alpha(@borders, 0.65);
  border-radius: 18px;
  padding: 20px;
}

.section-heading {
  font-size: 17px;
  font-weight: 700;
}

.section-description {
  color: alpha(@theme_fg_color, 0.66);
  font-size: 13px;
}

.metric-panel {
  background: alpha(@theme_fg_color, 0.045);
  border: 1px solid alpha(@theme_fg_color, 0.055);
  border-radius: 14px;
  padding: 14px;
}

.metric-caption {
  color: alpha(@theme_fg_color, 0.55);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.07em;
}

.metric-panel-value {
  font-size: 26px;
  font-weight: 800;
}

/* ---------------------------- Temperature slider ------------------------ */
/* Blackbody-style ramp: deep amber at 2500 K to neutral daylight at 5000 K. */

.temperature-scale trough {
  min-height: 10px;
  border-radius: 999px;
  background: linear-gradient(90deg,
    #ff8a3d,
    #ffa95c 30%,
    #ffc785 55%,
    #ffe0b4 78%,
    #e9e6dc);
  outline: 1px solid alpha(@theme_fg_color, 0.06);
  outline-offset: -1px;
}

.temperature-scale highlight {
  background: transparent;
}

.temperature-scale slider {
  min-width: 22px;
  min-height: 22px;
  border-radius: 999px;
  background: @nl_knob;
  border: 1px solid rgba(60, 40, 20, 0.22);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.35);
  transition: box-shadow 200ms ease;
}

.temperature-scale slider:hover {
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.45), 0 0 0 6px rgba(242, 163, 94, 0.18);
}

.limit-label {
  color: alpha(@theme_fg_color, 0.55);
  font-size: 12px;
}

/* ------------------------------- Intensity ------------------------------ */

.intensity-value {
  color: @nl_warm_text;
  font-size: 20px;
  font-weight: 800;
}

.intensity-bar trough {
  min-height: 8px;
  border-radius: 999px;
  background: alpha(@theme_fg_color, 0.08);
}

.intensity-bar progress {
  min-height: 8px;
  border-radius: 999px;
  background: linear-gradient(90deg, #ffd9a3, @nl_warm);
}

/* -------------------------------- Timeline ------------------------------ */
/* Calm 24 h ramp: night indigo → daylight blue → dusk amber → night. */

.timeline {
  background: linear-gradient(90deg,
    alpha(#4b5878, 0.55),
    alpha(#8fb8d8, 0.60) 30%,
    alpha(#f2a35e, 0.66) 62%,
    alpha(#4b5878, 0.55));
  border: 1px solid alpha(@theme_fg_color, 0.08);
  border-radius: 999px;
  min-height: 14px;
}

.timeline-caption {
  color: alpha(@theme_fg_color, 0.70);
  font-size: 12px;
  font-weight: 600;
}

.timeline-now {
  color: @nl_warm_text;
  font-size: 12px;
  font-weight: 700;
}

/* ------------------------------ Form pieces ----------------------------- */

.inline-error {
  color: @error_color;
  font-size: 12px;
}

.time-entry {
  min-width: 82px;
  padding: 7px 10px;
}

.dim {
  color: alpha(@theme_fg_color, 0.66);
}

.pill {
  border-radius: 999px;
}
"""


def gamma_description(gamma):
  """Describe perceived brightness without conflating it with color filtering."""
  return f"Brillo percibido al {int(gamma)}%"


def temperature_description(temperature, identity=False):
  """Describe a selected filter or the natural-color mode in human language."""
  if identity is True:
    return "Color natural, sin filtro añadido"
  if temperature is None:
    return "No hay una lectura de temperatura disponible"
  if temperature <= 2900:
    return "Tono muy cálido para la noche tardía"
  if temperature <= 3600:
    return "Cálida y equilibrada para descansar"
  if temperature <= 4400:
    return "Cómoda para leer o trabajar"
  return "Clara, cercana al color natural"


def relative_filter_intensity(temperature, identity=False):
  """Return a comparative 0-100 scale for the selected warm-color range.

  This is intentionally a UI-relative estimate, not a physical blue-light
  measurement.  ``identity`` is authoritative and always means no filter.
  """
  if identity is True:
    return 0
  if temperature is None:
    return None
  if isinstance(temperature, bool):
    raise ValueError("La temperatura debe ser numerica")
  try:
    value = int(temperature)
  except (TypeError, ValueError, OverflowError) as error:
    raise ValueError("La temperatura debe ser numerica") from error
  value = max(NIGHT_TEMP_MIN, min(NIGHT_TEMP_MAX, value))
  return round((NIGHT_TEMP_MAX - value) * 100 / (NIGHT_TEMP_MAX - NIGHT_TEMP_MIN))


def selected_filter_display(temperature):
  """Return the complete display model for the selected manual filter."""
  intensity = relative_filter_intensity(temperature)
  return {
    "temperature": temperature,
    "intensity": intensity,
    "fraction": None if intensity is None else intensity / 100,
    "label": "—" if intensity is None else f"{intensity}%",
  }


# Short aliases make the pure metric easy to discover for callers and tests.
temperature_intensity = relative_filter_intensity
filter_intensity = relative_filter_intensity


def state_temperature(state):
  """Return the temperature represented in the UI by an authoritative state."""
  if state is None or not state.available or state.active is None:
    return None
  # hyprsunset may return a stale temperature while identity is active.  The
  # natural-color mode is displayed as its nominal daylight value instead.
  return DAY_TEMP if state.identity is True else state.temperature


def state_filter_intensity(state):
  if state is None or not state.available or state.active is None:
    return None
  return relative_filter_intensity(state_temperature(state), state.identity is True)


def operation_confirmed(result):
  """Whether a backend operation completed and passed its readback."""
  if hasattr(result, "confirmed"):
    return bool(result.confirmed)
  return result is not None and getattr(result, "returncode", 1) == 0


def validate_schedule_values(night_time, day_time, night_temp, day_temp):
  """Validate the values entered by the schedule form without I/O."""
  return validate_schedule({
    "night_time": night_time,
    "night_temp": night_temp,
    "day_time": day_time,
    "day_temp": day_temp,
  })


class WorkerResult:
  __slots__ = ("confirmed", "message", "value")

  def __init__(self, confirmed, value=None, message=""):
    self.confirmed = bool(confirmed)
    self.value = value
    self.message = message


def _backend_failure(message):
  return WorkerResult(False, message=message)


def _backend_result(result, confirmed_message, error_message):
  if operation_confirmed(result):
    return WorkerResult(True, value=result, message=confirmed_message)
  return WorkerResult(False, value=result, message=error_message)


def apply_scheduled_profile(schedule, schedule_identity=False, now=None):
  """Apply the scheduled profile through the shared backend.

  A day profile represented by ``identity = true`` must use ``set_identity``;
  it must never be converted into a ``temperature = 6000`` request.
  """
  if schedule_period(schedule, now) == "night":
    return set_temperature(schedule["night_temp"])
  if schedule_identity:
    return set_identity()
  return set_temperature(schedule["day_temp"])


def _apply_temperature_worker(temperature):
  with exclusive_lock(STATE_LOCK):
    state = ensure_backend()
    if state.active is None:
      return _backend_failure("No se pudo conectar con el servicio")
    return _backend_result(
      set_temperature(temperature),
      f"Filtro confirmado a {temperature} K",
      "No se pudo confirmar la temperatura aplicada",
    )


def _apply_identity_worker():
  with exclusive_lock(STATE_LOCK):
    state = ensure_backend()
    if state.active is None:
      return _backend_failure("No se pudo conectar con el servicio")
    return _backend_result(
      set_identity(),
      "Color natural confirmado",
      "No se pudo confirmar el color natural",
    )


def _apply_gamma_worker(gamma):
  with exclusive_lock(STATE_LOCK):
    state = ensure_backend()
    if state.active is None:
      return _backend_failure("No se pudo conectar con el servicio")
    return _backend_result(
      set_gamma(gamma),
      f"Brillo percibido confirmado al {int(gamma)}%",
      "No se pudo confirmar el brillo percibido",
    )


def _apply_schedule_worker(schedule, schedule_identity=False):
  with exclusive_lock(STATE_LOCK):
    state = ensure_backend()
    if state.active is None:
      return _backend_failure("No se pudo conectar con el servicio")
    return _backend_result(
      apply_scheduled_profile(schedule, schedule_identity),
      "Perfil del horario confirmado",
      "No se pudo confirmar el perfil del horario",
    )


def _service_command(arguments):
  return backend_run_command(["systemctl", "--user", *arguments])


def _toggle_backend_worker(active, temperature):
  if active:
    return _apply_temperature_worker(temperature)
  return _apply_identity_worker()


def _toggle_schedule_worker(enabled, schedule, schedule_identity):
  with exclusive_lock(STATE_LOCK):
    if enabled:
      enabled_result = _service_command(["enable", "--now", SERVICE_NAME])
      if not operation_confirmed(enabled_result):
        return _backend_failure("No se pudo activar el horario automático")
      state = ensure_backend()
      if state.active is None:
        return _backend_failure("Servicio activado, pero el servicio no responde")
      return _backend_result(
        apply_scheduled_profile(schedule, schedule_identity),
        "Horario automático activado y confirmado",
        "Servicio activado, pero no se pudo confirmar el horario",
      )

    state = ensure_backend()
    normal_result = set_identity() if state.active is not None else None
    disabled_result = _service_command(["disable", "--now", SERVICE_NAME])
    if operation_confirmed(normal_result) and operation_confirmed(disabled_result):
      return WorkerResult(True, message="Horario automático desactivado")
    return _backend_failure("No se pudo desactivar completamente el horario")


def _save_schedule_worker(schedule, schedule_identity=False, repair_invalid=False):
  try:
    write_schedule(
      HYPRSUNSET_CONFIG,
      schedule,
      schedule_identity,
      repair_invalid=repair_invalid,
    )
  except (OSError, ValueError) as error:
    return WorkerResult(
      False,
      message="No se pudo guardar el horario. Revisa los datos e inténtalo de nuevo.",
    )

  service = read_service_state()
  if service.enabled is not True:
    return WorkerResult(
      True,
      value={"schedule": schedule, "applied": False},
      message="Horario guardado; actívalo cuando quieras",
    )

  with exclusive_lock(STATE_LOCK):
    restarted = _service_command(["restart", SERVICE_NAME])
    if not operation_confirmed(restarted):
      return WorkerResult(
        True,
        value={"schedule": schedule, "applied": False},
        message="Horario guardado, pero no se pudo reiniciar el servicio",
      )
    state = ensure_backend()
    if state.active is None:
      return WorkerResult(
        True,
        value={"schedule": schedule, "applied": False},
        message="Horario guardado, pero el servicio no responde",
      )
    applied = apply_scheduled_profile(schedule, schedule_identity)
    if not operation_confirmed(applied):
      return WorkerResult(
        True,
        value={"schedule": schedule, "applied": False},
        message="Horario guardado, pero no se pudo aplicar ahora",
      )
  return WorkerResult(
    True,
    value={"schedule": schedule, "applied": True},
    message="Horario personalizado guardado y aplicado",
  )


def render_schedule(schedule, schedule_identity=False):
  day_time = normalize_clock(schedule["day_time"])
  night_time = normalize_clock(schedule["night_time"])
  if day_time == night_time:
    raise ValueError("Las horas de día y noche deben ser diferentes")
  day_temp = max(DAY_TEMP_MIN, min(DAY_TEMP_MAX, int(schedule["day_temp"])))
  night_temp = max(NIGHT_TEMP_MIN, min(NIGHT_TEMP_MAX, int(schedule["night_temp"])))
  day_profile = (
    f"""profile {{
    time = {day_time}
    identity = true
}}"""
    if schedule_identity else f"""profile {{
    time = {day_time}
    temperature = {day_temp}
}}"""
  )
  return f"""# Generated by Night Light Control.
# Times use the system timezone.
{day_profile}

profile {{
    time = {night_time}
    temperature = {night_temp}
}}
"""


def _updated_profile(profile, time_value, temperature, schedule_identity=False):
  """Update one profile block without disturbing its formatting or comments."""
  info = profile_info(profile)
  profile = re.sub(
    r"(?mi)^([ \t]*time\s*=\s*)[0-9]{1,2}:[0-9]{2}"
    r"([ \t]*(?:#.*)?)(\r?)$",
    lambda match: (
      match.group(1) + time_value + match.group(2) + match.group(3)
    ),
    profile,
    count=1,
  )

  temperature_pattern = (
    r"(?mi)^([ \t]*)temperature\s*=\s*[^ \t\r\n{}#]+"
    r"([ \t]*(?:#.*)?)(\r?)$"
  )
  identity_pattern = (
    r"(?mi)^([ \t]*)identity(?:[ \t]*=[ \t]*(?:true|false))?"
    r"([ \t]*(?:#.*)?)(\r?)$"
  )

  if schedule_identity:
    profile = re.sub(
      temperature_pattern,
      lambda match: (
        match.group(1) + match.group(2) + match.group(3)
        if "#" in match.group(2) else match.group(3)
      ),
      profile,
    )
    if info["identity"] is not None:
      profile = re.sub(
        identity_pattern,
        lambda match: (
          match.group(1) + "identity = true"
          + match.group(2) + match.group(3)
        ),
        profile,
        count=1,
      )
    else:
      line_ending = "\r\n" if "\r\n" in profile else "\n"
      profile = re.sub(
        r"\}\s*$",
        f"    identity = true{line_ending}}}",
        profile,
        count=1,
      )
  elif info["temperature"] is not None:
    profile = re.sub(
      r"(?mi)^([ \t]*temperature\s*=\s*)[+-]?\d+"
      r"([ \t]*(?:#.*)?)(\r?)$",
      lambda match: (
        match.group(1) + str(temperature) + match.group(2) + match.group(3)
      ),
      profile,
      count=1,
    )
    profile = re.sub(
      identity_pattern,
      lambda match: (
        match.group(1) + match.group(2) + match.group(3)
        if "#" in match.group(2) else match.group(3)
      ),
      profile,
      count=1,
    )
  elif info["identity"] is not None:
    profile = re.sub(
      identity_pattern,
      lambda match: (
        match.group(1) + f"temperature = {temperature}"
        + match.group(2) + match.group(3)
      ),
      profile,
      count=1,
    )
  else:
    line_ending = "\r\n" if "\r\n" in profile else "\n"
    profile = re.sub(
      r"\}\s*$",
      f"    temperature = {temperature}{line_ending}}}",
      profile,
      count=1,
    )
  return profile


def update_schedule_text(existing, schedule, schedule_identity=False):
  """Update primary day/night profiles while preserving other content."""
  day_time = normalize_clock(schedule["day_time"])
  night_time = normalize_clock(schedule["night_time"])
  if day_time == night_time:
    raise ValueError("Las horas de día y noche deben ser diferentes")
  day_temp = max(DAY_TEMP_MIN, min(DAY_TEMP_MAX, int(schedule["day_temp"])))
  night_temp = max(NIGHT_TEMP_MIN, min(NIGHT_TEMP_MAX, int(schedule["night_temp"])))

  replacements = []
  found_day = False
  found_night = False
  for start, end, profile in iter_profile_blocks(existing):
    info = profile_info(profile)
    if info["time"] is None:
      continue
    kind = profile_kind(info)
    if kind == "day" and not found_day:
      replacements.append((
        start,
        end,
        _updated_profile(profile, day_time, day_temp, schedule_identity),
      ))
      found_day = True
    elif kind == "night" and not found_night:
      replacements.append((start, end, _updated_profile(profile, night_time, night_temp)))
      found_night = True

  updated = existing
  for start, end, replacement in reversed(replacements):
    updated = updated[:start] + replacement + updated[end:]

  missing = []
  if not found_day:
    missing.append(
      f"profile {{\n    time = {day_time}\n"
      + ("    identity = true\n" if schedule_identity else f"    temperature = {day_temp}\n")
      + "}"
    )
  if not found_night:
    missing.append(f"profile {{\n    time = {night_time}\n    temperature = {night_temp}\n}}")
  if missing:
    separator = "" if not updated or updated.endswith("\n\n") else ("\n" if updated.endswith("\n") else "\n\n")
    updated += separator + "\n\n".join(missing) + "\n"
  return updated


def _managed_profile_text(schedule, kind, schedule_identity=False):
  """Render one managed profile for use only after repair classification."""
  if kind == "day":
    time_value = normalize_clock(schedule["day_time"])
    body = (
      "    identity = true\n"
      if schedule_identity else
      f"    temperature = {max(DAY_TEMP_MIN, min(DAY_TEMP_MAX, int(schedule['day_temp'])))}\n"
    )
  else:
    time_value = normalize_clock(schedule["night_time"])
    body = (
      f"    temperature = {max(NIGHT_TEMP_MIN, min(NIGHT_TEMP_MAX, int(schedule['night_temp'])))}\n"
    )
  return f"profile {{\n    time = {time_value}\n{body}}}"


def _repair_schedule_text(existing, schedule, schedule_identity=False):
  """Repair recognized managed profiles without dropping recoverable text."""
  try:
    blocks = list(iter_profile_blocks(existing))
  except ValueError as error:
    raise ValueError(f"No se puede reparar el horario de forma segura: {error}") from error
  if existing.strip() and not blocks:
    raise ValueError(
      "No se puede reparar el horario de forma segura: no contiene perfiles"
    )

  replacements = []
  found = {"day": False, "night": False}
  for start, end, profile in blocks:
    info = profile_info(profile)
    kind = profile_kind(info)
    if kind not in found:
      raise ValueError(
        "No se puede reparar el horario de forma segura: "
        "hay un perfil sin temperatura o identidad reconocible"
      )
    if found[kind]:
      continue
    time_value = schedule["day_time"] if kind == "day" else schedule["night_time"]
    temperature = schedule["day_temp"] if kind == "day" else schedule["night_temp"]
    replacement = _updated_profile(
      profile,
      normalize_clock(time_value),
      temperature,
      schedule_identity if kind == "day" else False,
    )
    replacement_info = profile_info(replacement)
    if replacement_info["time"] is None or profile_kind(replacement_info) != kind:
      replacement = _managed_profile_text(schedule, kind, schedule_identity if kind == "day" else False)
    replacements.append((start, end, replacement))
    found[kind] = True

  repaired = existing
  for start, end, replacement in reversed(replacements):
    repaired = repaired[:start] + replacement + repaired[end:]

  missing = []
  if not found["day"]:
    missing.append(_managed_profile_text(schedule, "day", schedule_identity))
  if not found["night"]:
    missing.append(_managed_profile_text(schedule, "night"))
  if missing:
    if repaired and not repaired.endswith(("\n", "\r")):
      repaired += "\r\n" if "\r\n" in repaired else "\n"
    separator = "\r\n" if "\r\n" in repaired else "\n"
    repaired += separator.join(missing) + separator

  try:
    parse_schedule_text(repaired)
  except ValueError as error:
    raise ValueError(
      f"No se puede reparar el horario de forma segura: {error}"
    ) from error
  return repaired


def write_schedule(path, schedule, schedule_identity=False, repair_invalid=False):
  path = Path(path)
  if path.is_symlink():
    path = path.resolve(strict=True)
  day_time = normalize_clock(schedule["day_time"])
  night_time = normalize_clock(schedule["night_time"])
  if day_time == night_time:
    raise ValueError("Las horas de día y noche deben ser diferentes")
  path.parent.mkdir(parents=True, exist_ok=True)
  backup = path.with_suffix(path.suffix + ".bak")
  with exclusive_lock(STATE_LOCK):
    original_mode = path.stat().st_mode & 0o7777 if path.exists() else None
    if path.exists():
      with path.open("r", encoding="utf-8", newline="") as stream:
        existing = stream.read()
    else:
      existing = ""
    if repair_invalid:
      updated = _repair_schedule_text(existing, schedule, schedule_identity)
    elif not existing:
      updated = render_schedule(schedule, schedule_identity)
    else:
      updated = update_schedule_text(existing, schedule, schedule_identity)
    if path.exists():
      atomic_write_text(backup, existing, original_mode)
    atomic_write_text(path, updated, original_mode)


def load_schedule_config(path):
  """Load a user schedule while preserving malformed-config feedback."""
  path = Path(path)
  try:
    text = path.read_text(encoding="utf-8")
    schedule = parse_schedule_text(text)
    return schedule, day_profile_is_identity(text), ""
  except (OSError, ValueError) as error:
    return (
      default_schedule(),
      False,
      "No se pudo validar el horario. Revisa los valores y pulsa Guardar.",
    )


def read_schedule():
  schedule, _identity, _error = load_schedule_config(HYPRSUNSET_CONFIG)
  return schedule["night_time"], schedule["day_time"], schedule["night_temp"]


def load_settings(schedule_temp):
  return backend_load_temperature(CONFIG_PATH, default=schedule_temp)


def save_settings(temp):
  path = CONFIG_PATH.resolve(strict=False) if CONFIG_PATH.is_symlink() else CONFIG_PATH
  with exclusive_lock(STATE_LOCK):
    mode = path.stat().st_mode & 0o7777 if path.exists() else 0o600
    atomic_write_text(
      path,
      json.dumps({"temperature": int(temp)}, indent=2) + "\n",
      mode,
    )


def load_gamma(path=GAMMA_SETTINGS_PATH, *, default=GAMMA_DEFAULT):
  try:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
  except (OSError, TypeError, ValueError, json.JSONDecodeError):
    return int(default)
  if not isinstance(data, dict) or isinstance(data.get("gamma"), bool):
    return int(default)
  try:
    value = int(data.get("gamma", default))
  except (TypeError, ValueError, OverflowError):
    return int(default)
  return max(GAMMA_UI_MIN, min(GAMMA_UI_MAX, value))


def save_gamma(gamma):
  path = GAMMA_SETTINGS_PATH.resolve(strict=False) if GAMMA_SETTINGS_PATH.is_symlink() else GAMMA_SETTINGS_PATH
  with exclusive_lock(STATE_LOCK):
    mode = path.stat().st_mode & 0o7777 if path.exists() else 0o600
    atomic_write_text(path, json.dumps({"gamma": int(gamma)}, indent=2) + "\n", mode)


class NightLightWindow(Adw.ApplicationWindow):
  def __init__(self, app):
    super().__init__(application=app, title="Luz nocturna")
    self.set_default_size(720, 900)
    self.set_size_request(300, 640)

    self.schedule = default_schedule()
    self.schedule_identity = False
    self.night_time = self.schedule["night_time"]
    self.day_time = self.schedule["day_time"]
    self.selected_temp = DEFAULT_TEMPERATURE
    self.selected_gamma = GAMMA_DEFAULT
    self.last_backend_state = BackendState(False, None, None, None)
    self.last_service_state = None

    self.updating = False
    self.closed = False
    self.ready = False
    self.schedule_dirty = False
    self.schedule_config_error = ""
    self.apply_timeout = None
    self.gamma_apply_timeout = None
    self.settings_timeout = None
    self.gamma_settings_timeout = None
    self.refresh_timeout = None
    self.refresh_in_flight = False
    self._tokens = {}
    self._mutation_channels = set()
    self._operation_serial = 0
    self._latest_operation_generation = 0
    self._settings_generation = 0
    self._settings_dirty = False
    self._gamma_settings_generation = 0
    self._gamma_settings_dirty = False
    self._settings_write_lock = threading.Lock()
    self._gamma_settings_write_lock = threading.Lock()

    provider = Gtk.CssProvider()
    provider.load_from_string(CSS)
    display = self.get_display()
    if display is not None:
      Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
      )

    self._build_ui()
    self._set_controls_sensitive(False)
    self._set_operation_status("applying", "Comprobando el servicio…")
    self._start_worker("bootstrap", self._bootstrap_worker, self._finish_bootstrap)

  def _build_ui(self):
    toolbar = Adw.ToolbarView()
    header = Adw.HeaderBar()
    header.set_title_widget(Adw.WindowTitle(
      title="Luz nocturna",
      subtitle="Pantalla y descanso visual",
    ))
    toolbar.add_top_bar(header)

    self.toast_overlay = Adw.ToastOverlay()
    scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
    clamp = Adw.Clamp(maximum_size=760, tightening_threshold=580)
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, css_classes=["app-content"])
    content.set_margin_top(20)
    content.set_margin_bottom(28)
    content.set_margin_start(20)
    content.set_margin_end(20)
    clamp.set_child(content)
    scroller.set_child(clamp)
    self.toast_overlay.set_child(scroller)
    toolbar.set_content(self.toast_overlay)
    self.set_content(toolbar)

    self._build_hero(content)
    self._build_temperature_card(content)
    self._build_gamma_card(content)
    self._build_timeline_card(content)
    self._build_schedule_card(content)

  def _build_hero(self, content):
    self.hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, css_classes=["hero-card"])
    top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
    icon_wrap = Gtk.Box(css_classes=["hero-icon-wrap"], valign=Gtk.Align.CENTER)
    self.hero_icon = Gtk.Image.new_from_icon_name("weather-clear-night-symbolic")
    self.hero_icon.set_pixel_size(38)
    self.hero_icon.add_css_class("hero-icon")
    icon_wrap.append(self.hero_icon)
    top.append(icon_wrap)

    titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, valign=Gtk.Align.CENTER, hexpand=True)
    titles.append(Gtk.Label(label="CONTROL DE AMBIENTE", xalign=0, css_classes=["eyebrow"]))
    titles.append(Gtk.Label(label="Filtro de luz azul", xalign=0, css_classes=["hero-title"]))
    titles.append(Gtk.Label(
      label="Control manual de 2500–5000 K con horario automático opcional",
      xalign=0,
      wrap=True,
      css_classes=["hero-subtitle"],
    ))
    top.append(titles)

    self.hero.append(top)

    metric = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0,
                     valign=Gtk.Align.CENTER, halign=Gtk.Align.END)
    current_metric = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4,
                             halign=Gtk.Align.END)
    self.current_temp_label = Gtk.Label(label="—", css_classes=["metric-value"])
    current_metric.append(self.current_temp_label)
    current_metric.append(Gtk.Label(label="K", css_classes=["metric-unit"], valign=Gtk.Align.END))
    metric.append(current_metric)
    self.current_mode_label = Gtk.Label(label="Comprobando…", xalign=1, css_classes=["metric-unit"])
    metric.append(self.current_mode_label)
    self.hero.append(metric)

    status_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    self.status_label = Gtk.Label(label="Comprobando…", css_classes=["status-pill"], xalign=0)
    set_status(self.status_label, "Comprobando…", busy=True)
    status_line.append(self.status_label)
    self.operation_spinner = Gtk.Spinner(visible=False, valign=Gtk.Align.CENTER)
    status_line.append(self.operation_spinner)
    self.operation_label = Gtk.Label(label="", css_classes=["operation-status"], xalign=1)
    set_status(self.operation_label, "", busy=False)
    status_line.append(self.operation_label)
    self.hero.append(status_line)
    content.append(self.hero)

    control_group = Adw.PreferencesGroup()
    self.main_switch = Adw.SwitchRow(
      title="Activar filtro ahora",
      subtitle="No cambia el horario automático",
      icon_name="weather-clear-night-symbolic",
    )
    self.main_switch.connect("notify::active", self.on_main_toggle)
    control_group.add(self.main_switch)
    content.append(control_group)

  def _build_temperature_card(self, content):
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=13, css_classes=["section-card"])
    heading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
    heading.append(Gtk.Label(label="Filtro manual · 2500–5000 K", xalign=0, css_classes=["section-heading"]))
    heading.append(Gtk.Label(
      label="La temperatura seleccionada se aplica solo cuando el filtro está activo.",
      xalign=0,
      wrap=True,
      css_classes=["section-description"],
    ))
    card.append(heading)

    metrics = Gtk.Grid(column_spacing=10, row_spacing=10, column_homogeneous=True)
    current_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, css_classes=["metric-panel"])
    current_panel.append(Gtk.Label(label="AHORA", xalign=0, css_classes=["metric-caption"]))
    current_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
    self.current_card_temp_label = Gtk.Label(label="—", xalign=0, css_classes=["metric-panel-value"])
    current_line.append(self.current_card_temp_label)
    current_line.append(Gtk.Label(label="K", css_classes=["metric-unit"], valign=Gtk.Align.END))
    current_panel.append(current_line)
    self.current_card_note = Gtk.Label(label="Esperando lectura", xalign=0, wrap=True, css_classes=["dim"])
    current_panel.append(self.current_card_note)
    metrics.attach(current_panel, 0, 0, 1, 1)

    selected_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, css_classes=["metric-panel"])
    selected_panel.append(Gtk.Label(label="SELECCIONADA", xalign=0, css_classes=["metric-caption"]))
    selected_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
    self.temp_label = Gtk.Label(label=str(self.selected_temp), xalign=0, css_classes=["metric-panel-value"])
    selected_line.append(self.temp_label)
    selected_line.append(Gtk.Label(label="K", css_classes=["metric-unit"], valign=Gtk.Align.END))
    selected_panel.append(selected_line)
    self.temp_description = Gtk.Label(
      label=temperature_description(self.selected_temp),
      xalign=0,
      wrap=True,
      css_classes=["dim"],
    )
    selected_panel.append(self.temp_description)
    metrics.attach(selected_panel, 1, 0, 1, 1)
    card.append(metrics)

    self.scale = Gtk.Scale.new_with_range(
      Gtk.Orientation.HORIZONTAL, NIGHT_TEMP_MIN, NIGHT_TEMP_MAX, 100
    )
    self.scale.set_value(self.selected_temp)
    self.scale.set_draw_value(False)
    self.scale.set_hexpand(True)
    self.scale.add_css_class("temperature-scale")
    self.scale.set_tooltip_text("Selecciona una temperatura entre 2500 K y 5000 K")
    set_range(self.scale, "Temperatura del filtro de luz azul", NIGHT_TEMP_MIN,
              NIGHT_TEMP_MAX, self.selected_temp, f"{self.selected_temp} K")
    self.scale.connect("value-changed", self.on_scale_changed)
    card.append(self.scale)

    limits = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    limits.append(Gtk.Label(label="2500 K · más ámbar", xalign=0, hexpand=True, css_classes=["limit-label"]))
    limits.append(Gtk.Label(label="5000 K · más natural", xalign=1, css_classes=["limit-label"]))
    card.append(limits)

    intensity_head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    intensity_head.append(Gtk.Label(label="Intensidad del filtro seleccionado", xalign=0, hexpand=True, css_classes=["metric-caption"]))
    self.intensity_value_label = Gtk.Label(label="—", css_classes=["intensity-value"])
    intensity_head.append(self.intensity_value_label)
    card.append(intensity_head)
    self.intensity_bar = Gtk.ProgressBar(show_text=False)
    self.intensity_bar.add_css_class("intensity-bar")
    card.append(self.intensity_bar)
    self.intensity_note = Gtk.Label(
      label="2500 K = más cálido · 5000 K = más natural",
      xalign=0,
      wrap=True,
      css_classes=["section-description"],
    )
    card.append(self.intensity_note)

    content.append(card)
    self._update_selected_temperature()

  def _build_gamma_card(self, content):
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=13, css_classes=["section-card"])
    card.append(Gtk.Label(label="Brillo percibido · 50–100%", xalign=0, css_classes=["section-heading"]))
    card.append(Gtk.Label(
      label="Ajusta cómo percibes el brillo de la pantalla, separado del color cálido.",
      xalign=0,
      wrap=True,
      css_classes=["section-description"],
    ))

    metrics = Gtk.Grid(column_spacing=10, row_spacing=10, column_homogeneous=True)
    current_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, css_classes=["metric-panel"])
    current_panel.append(Gtk.Label(label="AHORA", xalign=0, css_classes=["metric-caption"]))
    self.current_gamma_label = Gtk.Label(label="—", xalign=0, css_classes=["metric-panel-value"])
    current_panel.append(self.current_gamma_label)
    self.current_gamma_note = Gtk.Label(label="Esperando lectura", xalign=0, wrap=True, css_classes=["dim"])
    current_panel.append(self.current_gamma_note)
    metrics.attach(current_panel, 0, 0, 1, 1)

    selected_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, css_classes=["metric-panel"])
    selected_panel.append(Gtk.Label(label="SELECCIONADO", xalign=0, css_classes=["metric-caption"]))
    self.gamma_label = Gtk.Label(label=f"{self.selected_gamma}%", xalign=0, css_classes=["metric-panel-value"])
    selected_panel.append(self.gamma_label)
    self.gamma_description_label = Gtk.Label(
      label=gamma_description(self.selected_gamma), xalign=0, wrap=True, css_classes=["dim"]
    )
    selected_panel.append(self.gamma_description_label)
    metrics.attach(selected_panel, 1, 0, 1, 1)
    card.append(metrics)

    self.gamma_scale = Gtk.Scale.new_with_range(
      Gtk.Orientation.HORIZONTAL, GAMMA_UI_MIN, GAMMA_UI_MAX, 1
    )
    self.gamma_scale.set_value(self.selected_gamma)
    self.gamma_scale.set_draw_value(False)
    self.gamma_scale.set_hexpand(True)
    self.gamma_scale.add_css_class("gamma-scale")
    self.gamma_scale.set_tooltip_text("Selecciona un brillo percibido entre 50% y 100%")
    set_range(self.gamma_scale, "Brillo percibido", GAMMA_UI_MIN, GAMMA_UI_MAX,
              self.selected_gamma, f"{self.selected_gamma}%")
    self.gamma_scale.connect("value-changed", self.on_gamma_changed)
    card.append(self.gamma_scale)

    limits = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    limits.append(Gtk.Label(label="50% · más tenue", xalign=0, hexpand=True, css_classes=["limit-label"]))
    limits.append(Gtk.Label(label="100% · normal", xalign=1, css_classes=["limit-label"]))
    card.append(limits)
    warning = Gtk.Label(label=GAMMA_WARNING, xalign=0, wrap=True, css_classes=["section-description"])
    set_description(self.gamma_scale, GAMMA_WARNING, invalid=False)
    card.append(warning)
    content.append(card)
    self._update_selected_gamma()

  def _build_timeline_card(self, content):
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["section-card"])
    card.append(Gtk.Label(label="Tu día, en una línea", xalign=0, css_classes=["section-heading"]))
    card.append(Gtk.Label(
      label="El horario usa la zona horaria local del sistema.",
      xalign=0,
      css_classes=["section-description"],
    ))
    card.append(Gtk.Box(css_classes=["timeline"]))
    labels = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    self.night_timeline_label = Gtk.Label(label="☾  15:30 · 3500 K", xalign=0, hexpand=True, css_classes=["timeline-caption"])
    self.day_timeline_label = Gtk.Label(label="☀  06:00 · 6000 K", xalign=1, css_classes=["timeline-caption"])
    labels.append(self.night_timeline_label)
    labels.append(self.day_timeline_label)
    card.append(labels)
    self.timeline_now_label = Gtk.Label(label="Comprobando el tramo actual…", xalign=0, css_classes=["timeline-now"])
    card.append(self.timeline_now_label)
    content.append(card)

  def _build_schedule_card(self, content):
    group = Adw.PreferencesGroup(
      title="Automatización personalizada",
      description="Configura cuándo empieza y termina la luz cálida.",
    )
    self.schedule_switch = Adw.SwitchRow(
      title="Seguir este horario",
      subtitle="Todos los días · 15:30 → 06:00",
      icon_name="preferences-system-time-symbolic",
    )
    self.schedule_switch.connect("notify::active", self.on_schedule_toggle)
    group.add(self.schedule_switch)

    night_row = Adw.ActionRow(
      title="Comienza la noche",
      subtitle="Hora local, formato de 24 horas",
      icon_name="weather-clear-night-symbolic",
    )
    self.night_time_entry = self._make_time_entry(self.night_time)
    night_row.add_suffix(self.night_time_entry)
    group.add(night_row)
    self.night_time_error = self._make_error_label()
    group.add(self.night_time_error)

    day_row = Adw.ActionRow(
      title="Termina la noche",
      subtitle="Regresa al color natural",
      icon_name="weather-clear-symbolic",
    )
    self.day_time_entry = self._make_time_entry(self.day_time)
    day_row.add_suffix(self.day_time_entry)
    group.add(day_row)
    self.day_time_error = self._make_error_label()
    group.add(self.day_time_error)

    self.day_identity_switch = Adw.SwitchRow(
      title="Usar color natural",
      subtitle="Sin filtro añadido durante el día",
      icon_name="weather-clear-symbolic",
    )
    self.day_identity_switch.connect("notify::active", self.on_day_identity_changed)
    group.add(self.day_identity_switch)

    self.night_temp_row = Adw.SpinRow.new_with_range(NIGHT_TEMP_MIN, NIGHT_TEMP_MAX, 100)
    self.night_temp_row.set_title("Temperatura nocturna")
    self.night_temp_row.set_subtitle("Más baja significa un tono más ámbar")
    self.night_temp_row.add_prefix(Gtk.Image.new_from_icon_name("night-light-symbolic"))
    self.night_temp_row.set_value(self.schedule["night_temp"])
    self.night_temp_row.connect("notify::value", self.on_schedule_value_changed)
    group.add(self.night_temp_row)

    self.day_temp_row = Adw.SpinRow.new_with_range(DAY_TEMP_MIN, DAY_TEMP_MAX, 100)
    self.day_temp_row.set_title("Referencia diurna · 5900–6500 K")
    self.day_temp_row.set_subtitle("Se usa solo si desactivas el color natural")
    self.day_temp_row.add_prefix(Gtk.Image.new_from_icon_name("display-brightness-symbolic"))
    self.day_temp_row.set_value(self.schedule["day_temp"])
    self.day_temp_row.connect("notify::value", self.on_schedule_value_changed)
    group.add(self.day_temp_row)

    self.schedule_feedback = Gtk.Label(
      label="Los cambios del horario se guardan al pulsar Guardar.",
      xalign=0,
      wrap=True,
      css_classes=["section-description"],
    )
    set_status(self.schedule_feedback, self.schedule_feedback.get_label(), busy=False)
    group.add(self.schedule_feedback)

    save_row = Adw.ActionRow(
      title="Guardar personalización",
      subtitle="Guarda los cambios y aplica el perfil si procede",
      icon_name="document-save-symbolic",
    )
    self.save_schedule_button = Gtk.Button(
      label="Guardar",
      valign=Gtk.Align.CENTER,
      css_classes=["suggested-action", "pill"],
    )
    self.save_schedule_button.connect("clicked", self.on_save_schedule)
    save_row.add_suffix(self.save_schedule_button)
    save_row.set_activatable_widget(self.save_schedule_button)
    group.add(save_row)

    reset_row = Adw.ActionRow(
      title="Aplicar el perfil de ahora",
      subtitle="Descarta la previsualización manual actual",
      icon_name="view-refresh-symbolic",
    )
    self.reset_button = Gtk.Button(label="Restaurar", valign=Gtk.Align.CENTER, css_classes=["pill"])
    self.reset_button.connect("clicked", self.on_reset)
    reset_row.add_suffix(self.reset_button)
    reset_row.set_activatable_widget(self.reset_button)
    group.add(reset_row)
    content.append(group)

  def _make_time_entry(self, value):
    entry = Gtk.Entry(
      text=value,
      width_chars=5,
      max_length=5,
      valign=Gtk.Align.CENTER,
      css_classes=["time-entry"],
    )
    entry.set_placeholder_text("HH:MM")
    entry.set_tooltip_text("Hora local en formato de 24 horas, por ejemplo 06:30")
    set_description(entry, "Hora local en formato de 24 horas, por ejemplo 06:30", invalid=False)
    try:
      entry.set_input_purpose(Gtk.InputPurpose.TIME)
    except AttributeError:
      pass
    entry.connect("changed", self.on_schedule_entry_changed)
    return entry

  def _make_error_label(self):
    label = Gtk.Label(label="", xalign=0, wrap=True, css_classes=["inline-error"])
    label.set_margin_start(56)
    label.set_margin_end(18)
    label.set_visible(False)
    set_status(label, "", busy=False)
    return label

  def toast(self, text):
    if not self.closed:
      self.toast_overlay.add_toast(Adw.Toast.new(text))

  def _set_operation_status(self, state, text):
    self.operation_label.remove_css_class("applying")
    self.operation_label.remove_css_class("confirmed")
    self.operation_label.remove_css_class("error")
    self.operation_label.add_css_class(state)
    self.operation_label.set_label(text)
    set_status(self.operation_label, text, busy=state == "applying")
    if state == "applying":
      self.operation_spinner.set_visible(True)
      self.operation_spinner.start()
    else:
      self.operation_spinner.stop()
      self.operation_spinner.set_visible(False)

  def _set_controls_sensitive(self, sensitive):
    for widget in (
      self.main_switch,
      self.schedule_switch,
      self.scale,
      self.gamma_scale,
      self.night_time_entry,
      self.day_time_entry,
      self.day_identity_switch,
      self.night_temp_row,
      self.day_temp_row,
      self.reset_button,
    ):
      widget.set_sensitive(sensitive)
    self._update_day_identity_ui()
    self.save_schedule_button.set_sensitive(sensitive and not self.schedule_dirty)
    if sensitive:
      self._update_save_button()

  def _update_day_identity_ui(self):
    identity = self.day_identity_switch.get_active()
    self.day_temp_row.set_sensitive(self.ready and not identity)
    self.day_temp_row.set_subtitle(
      "Solo referencia; no se aplica con color natural"
      if identity else "Se usa solo si desactivas el color natural"
    )
    self._update_schedule_labels()

  def _update_save_button(self):
    if not self.ready:
      self.save_schedule_button.set_sensitive(False)
      return
    self.save_schedule_button.set_sensitive(
      not self.schedule_dirty or self._schedule_form_values() is not None
    )

  def _set_entry_error(self, entry, label, message):
    if message:
      entry.add_css_class("error")
      label.set_label(message)
      label.set_visible(True)
      set_description(entry, message, invalid=True)
      set_status(label, message, busy=False)
    else:
      entry.remove_css_class("error")
      label.set_label("")
      label.set_visible(False)
      set_description(entry, "Hora local en formato de 24 horas, por ejemplo 06:30", invalid=False)
      set_status(label, "", busy=False)

  def _schedule_form_values(self):
    night_text = self.night_time_entry.get_text()
    day_text = self.day_time_entry.get_text()
    errors = {"night_time": "", "day_time": ""}
    try:
      night_time = normalize_clock(night_text)
    except ValueError:
      night_time = None
      errors["night_time"] = "Usa una hora válida en formato HH:MM (24 horas)."
    try:
      day_time = normalize_clock(day_text)
    except ValueError:
      day_time = None
      errors["day_time"] = "Usa una hora válida en formato HH:MM (24 horas)."
    if night_time is not None and day_time is not None and night_time == day_time:
      errors["night_time"] = "Debe ser diferente de la hora de fin."
      errors["day_time"] = "Debe ser diferente de la hora de inicio."

    self._set_entry_error(self.night_time_entry, self.night_time_error, errors["night_time"])
    self._set_entry_error(self.day_time_entry, self.day_time_error, errors["day_time"])
    if errors["night_time"] or errors["day_time"]:
      self._update_save_button_for_form(False)
      return None

    try:
      schedule = validate_schedule_values(
        night_time,
        day_time,
        int(self.night_temp_row.get_value()),
        int(self.day_temp_row.get_value()),
      )
    except ValueError:
      self._update_save_button_for_form(False)
      return None
    self._update_save_button_for_form(True)
    return schedule

  def _update_save_button_for_form(self, valid):
    self.save_schedule_button.set_sensitive(
      self.ready and valid and "schedule" not in self._mutation_channels
    )

  def _on_schedule_changed(self):
    if not self.ready or self.updating:
      return
    self.schedule_dirty = True
    feedback = "Hay cambios sin guardar. Revisa las horas y pulsa Guardar."
    self.schedule_feedback.set_label(feedback)
    set_status(self.schedule_feedback, feedback, busy=False)
    self._schedule_form_values()

  def on_schedule_entry_changed(self, _entry):
    self._on_schedule_changed()

  def on_schedule_value_changed(self, _row, _param):
    self._on_schedule_changed()

  def on_day_identity_changed(self, _row, _param):
    if self.updating or not self.ready:
      self._update_day_identity_ui()
      return
    self._update_day_identity_ui()
    self._on_schedule_changed()

  def _set_schedule_widgets(self):
    self.updating = True
    self.night_time_entry.set_text(self.night_time)
    self.day_time_entry.set_text(self.day_time)
    self.day_identity_switch.set_active(self.schedule_identity)
    self.night_temp_row.set_value(self.schedule["night_temp"])
    self.day_temp_row.set_value(self.schedule["day_temp"])
    self.schedule_switch.set_subtitle(
      f"Todos los días · {self.night_time} → {self.day_time}"
    )
    self.updating = False
    self._update_day_identity_ui()
    self._set_entry_error(self.night_time_entry, self.night_time_error, "")
    self._set_entry_error(self.day_time_entry, self.day_time_error, "")
    self._update_schedule_labels()

  def _update_schedule_labels(self):
    identity = self.day_identity_switch.get_active()
    day_caption = "Color natural" if identity else f"{self.schedule['day_temp']} K"
    self.night_timeline_label.set_label(
      f"☾  {self.night_time} · {self.schedule['night_temp']} K"
    )
    self.day_timeline_label.set_label(f"☀  {self.day_time} · {day_caption}")
    period = schedule_period(self.schedule)
    if period == "night":
      self.timeline_now_label.set_label(
        f"Ahora: tramo nocturno · {self.schedule['night_temp']} K"
      )
    elif identity:
      self.timeline_now_label.set_label("Ahora: tramo diurno · Color natural")
    else:
      self.timeline_now_label.set_label(
        f"Ahora: tramo diurno · {self.schedule['day_temp']} K"
      )

  def _update_selected_temperature(self):
    self.temp_label.set_label(str(self.selected_temp))
    self.temp_description.set_label(temperature_description(self.selected_temp))
    set_range(self.scale, "Temperatura del filtro de luz azul", NIGHT_TEMP_MIN,
              NIGHT_TEMP_MAX, self.selected_temp, f"{self.selected_temp} K")
    display = selected_filter_display(self.selected_temp)
    self.intensity_value_label.set_label(display["label"])
    self.intensity_bar.set_fraction(display["fraction"] or 0)

  def _update_selected_gamma(self):
    self.gamma_label.set_label(f"{self.selected_gamma}%")
    self.gamma_description_label.set_label(gamma_description(self.selected_gamma))
    set_range(self.gamma_scale, "Brillo percibido", GAMMA_UI_MIN, GAMMA_UI_MAX,
              self.selected_gamma, f"{self.selected_gamma}%")

  def _apply_backend_state(self, state, service=None):
    self.last_backend_state = state
    if service is not None:
      self.last_service_state = service

    if state.gamma is None:
      self.current_gamma_label.set_label("—")
      self.current_gamma_note.set_label("No hay una lectura disponible")
    else:
      self.current_gamma_label.set_label(f"{state.gamma}%")
      self.current_gamma_note.set_label(gamma_description(state.gamma))

    available = state.available and state.active is not None
    if not available:
      self.status_label.set_label("Backend no disponible")
      self.status_label.add_css_class("error")
      self.status_label.remove_css_class("active")
      self.current_temp_label.set_label("—")
      self.current_card_temp_label.set_label("—")
      self.current_mode_label.set_label("Sin lectura")
      self.current_card_note.set_label("No se pudo comprobar el servicio")
      self.hero.add_css_class("inactive")
      self.hero_icon.set_from_icon_name("weather-clear-symbolic")
    else:
      self.status_label.remove_css_class("error")
      display_temperature = state_temperature(state)
      self.current_temp_label.set_label(str(display_temperature))
      self.current_card_temp_label.set_label(str(display_temperature))
      if state.identity is True:
        self.status_label.set_label("Color natural")
        self.current_mode_label.set_label("Color natural")
        self.current_card_note.set_label("Sin filtro añadido")
      elif state.active:
        self.status_label.set_label(f"Filtro activo · {state.temperature} K")
        self.current_mode_label.set_label("filtro cálido activo")
        self.current_card_note.set_label(temperature_description(state.temperature))
        self.intensity_note.set_label("2500 K = más cálido · 5000 K = más natural")
      else:
        self.status_label.set_label("Filtro desactivado")
        self.current_mode_label.set_label("sin filtro confirmado")
        self.current_card_note.set_label("Sin filtro añadido")
        self.intensity_note.set_label("2500 K = más cálido · 5000 K = más natural")
      self.status_label.remove_css_class("active")
      if state.active:
        self.status_label.add_css_class("active")
        self.hero.remove_css_class("inactive")
        self.hero_icon.set_from_icon_name("weather-clear-night-symbolic")
      else:
        self.hero.add_css_class("inactive")
        self.hero_icon.set_from_icon_name("weather-clear-symbolic")

    set_status(self.status_label, self.status_label.get_label(), busy=False)
    set_status(self.current_mode_label, self.current_mode_label.get_label(), busy=False)
    self.updating = True
    self.main_switch.set_active(bool(state.active) if state.active is not None else False)
    if service is not None and service.enabled is not None:
      self.schedule_switch.set_active(service.enabled is True)
    self.updating = False
    self._update_schedule_labels()

  def set_status(self, active, temp, available=True, identity=None):
    """Compatibility wrapper for callers that used the old UI helper."""
    state = BackendState(
      available=available,
      active=active if available else None,
      identity=identity,
      temperature=temp,
    )
    self._apply_backend_state(state)

  def refresh(self):
    if self.closed or not self.ready or self.refresh_in_flight or self._mutation_channels:
      return GLib.SOURCE_CONTINUE
    self.refresh_in_flight = True
    token = self._next_token("refresh")
    self._start_worker("refresh", self._refresh_worker, self._finish_refresh, token=token)
    return GLib.SOURCE_CONTINUE

  def _refresh_worker(self):
    try:
      return WorkerResult(True, value=(read_state(), read_service_state()))
    except Exception as error:
      return WorkerResult(False, message="No se pudo comprobar el servicio. Inténtalo de nuevo.")

  def _finish_refresh(self, outcome, _generation):
    self.refresh_in_flight = False
    if not outcome.confirmed:
      self._apply_backend_state(BackendState(False, None, None, None))
      return
    state, service = outcome.value
    self._apply_backend_state(state, service)

  def _bootstrap_worker(self):
    schedule, schedule_identity, config_error = load_schedule_config(HYPRSUNSET_CONFIG)
    try:
      selected = load_settings(schedule["night_temp"])
      selected_gamma = load_gamma()
      state = read_state()
      service = read_service_state()
    except Exception as error:
      return WorkerResult(
        False,
        message="No se pudo preparar la aplicación. Comprueba el servicio e inténtalo de nuevo.",
      )
    return WorkerResult(True, value=(schedule, schedule_identity, config_error, selected, selected_gamma, state, service))

  def _finish_bootstrap(self, outcome, _generation):
    config_error = ""
    if outcome.confirmed:
      (
        self.schedule, self.schedule_identity, config_error, self.selected_temp,
        self.selected_gamma, state, service,
      ) = outcome.value
      self.schedule_config_error = config_error
    else:
      self.schedule = default_schedule()
      self.schedule_identity = False
      self.schedule_config_error = ""
      self.selected_temp = DEFAULT_TEMPERATURE
      self.selected_gamma = GAMMA_DEFAULT
      state = BackendState(False, None, None, None)
      service = None
    self.night_time = self.schedule["night_time"]
    self.day_time = self.schedule["day_time"]
    self._set_schedule_widgets()
    self.scale.set_value(self.selected_temp)
    self.gamma_scale.set_value(self.selected_gamma)
    self._update_selected_temperature()
    self._update_selected_gamma()
    self.ready = True
    self._set_controls_sensitive(True)
    self._apply_backend_state(state, service)
    if config_error:
      feedback = "No se pudo validar el horario. Corrige los valores y pulsa Guardar."
      self.schedule_feedback.set_label(feedback)
      self.schedule_feedback.add_css_class("error")
      set_status(self.schedule_feedback, self.schedule_feedback.get_label(), busy=False)
    if outcome.confirmed and not config_error:
      self._set_operation_status("confirmed", "Listo")
    elif outcome.confirmed:
      self._set_operation_status("error", "Horario no validado")
    else:
      self._set_operation_status("error", "Revisa la conexión")
      self.toast(outcome.message)
    self.refresh_timeout = GLib.timeout_add_seconds(4, self.refresh)

  def _next_token(self, channel):
    token = self._tokens.get(channel, 0) + 1
    self._tokens[channel] = token
    return token

  def _start_worker(self, channel, work, callback, token=None, generation=0):
    token = self._next_token(channel) if token is None else token

    def runner():
      try:
        outcome = work()
        if not isinstance(outcome, WorkerResult):
          outcome = WorkerResult(True, value=outcome)
      except Exception as error:
        outcome = WorkerResult(
          False,
          message="No se pudo completar la operación. Inténtalo de nuevo.",
        )
      try:
        GLib.idle_add(self._deliver_worker, channel, token, generation, callback, outcome)
      except Exception:
        # The application may already be shutting down; no GTK object is used here.
        pass

    threading.Thread(
      target=runner,
      name=f"night-light-{channel}",
      daemon=True,
    ).start()
    return token

  def _deliver_worker(self, channel, token, generation, callback, outcome):
    if self.closed or self._tokens.get(channel) != token:
      return GLib.SOURCE_REMOVE
    if channel in self._mutation_channels:
      self._mutation_channels.discard(channel)
    callback(outcome, generation)
    return GLib.SOURCE_REMOVE

  def _cancel_operation(self, channel):
    self._next_token(channel)
    self._mutation_channels.discard(channel)

  def _begin_operation(self, channel, message):
    self._next_token("refresh")
    self.refresh_in_flight = False
    token = self._next_token(channel)
    self._mutation_channels.add(channel)
    self._operation_serial += 1
    generation = self._operation_serial
    self._latest_operation_generation = generation
    self._set_operation_status("applying", message)
    return token, generation

  def _launch_operation(self, channel, message, work, callback):
    token, generation = self._begin_operation(channel, message)
    self._start_worker(channel, work, callback, token=token, generation=generation)
    return token, generation

  def _complete_operation(self, channel, generation, outcome, notify=True):
    latest = generation == self._latest_operation_generation
    if outcome.confirmed:
      if latest:
        self._set_operation_status("confirmed", outcome.message or "Cambio confirmado")
      if latest and notify and outcome.message:
        self.toast(outcome.message)
    else:
      message = outcome.message or "No se pudo confirmar el cambio"
      if latest:
        self._set_operation_status("error", message)
      if latest and notify:
        self.toast(message)
    if not self._mutation_channels:
      self.refresh()

  def _finish_toggle(self, target, outcome, generation):
    if not outcome.confirmed:
      self.updating = True
      self.main_switch.set_active(not target)
      self.updating = False
    self.main_switch.set_sensitive(self.ready)
    self._complete_operation("toggle", generation, outcome)

  def on_main_toggle(self, row, _param):
    if self.updating or not self.ready:
      return
    target = row.get_active()
    if not target:
      self.cancel_apply_timer()
      self._cancel_operation("temperature")
    message = "Activando el filtro…" if target else "Restaurando el color natural…"
    self.main_switch.set_sensitive(False)
    self._launch_operation(
      "toggle",
      message,
      lambda: _toggle_backend_worker(target, self.selected_temp),
      lambda outcome, generation: self._finish_toggle(target, outcome, generation),
    )

  def on_scale_changed(self, scale):
    self.selected_temp = int(round(scale.get_value() / 100) * 100)
    self._update_selected_temperature()
    if not self.ready or self.updating:
      return
    self._settings_generation += 1
    revision = self._settings_generation
    self._settings_dirty = True
    if self.settings_timeout:
      GLib.source_remove(self.settings_timeout)
    self.settings_timeout = GLib.timeout_add(
      250, self.persist_selected_temp, revision, self.selected_temp
    )
    if self.main_switch.get_active():
      self.cancel_apply_timer()
      self.apply_timeout = GLib.timeout_add(140, self.apply_selected_temp)

  def on_gamma_changed(self, scale):
    self.selected_gamma = int(round(scale.get_value()))
    self._update_selected_gamma()
    if not self.ready or self.updating:
      return
    self._gamma_settings_generation += 1
    revision = self._gamma_settings_generation
    self._gamma_settings_dirty = True
    if self.gamma_settings_timeout:
      GLib.source_remove(self.gamma_settings_timeout)
    self.gamma_settings_timeout = GLib.timeout_add(
      250, self.persist_selected_gamma, revision, self.selected_gamma
    )
    self.cancel_gamma_apply_timer()
    self.gamma_apply_timeout = GLib.timeout_add(140, self.apply_selected_gamma)

  def _settings_worker(self, temperature, revision):
    with self._settings_write_lock:
      if revision != self._settings_generation:
        return WorkerResult(True, value="stale")
      try:
        save_settings(temperature)
      except (OSError, ValueError) as error:
        return WorkerResult(
          False,
          message="No se pudo guardar la preferencia. Inténtalo de nuevo.",
        )
    return WorkerResult(True, value="saved", message="Temperatura guardada")

  def persist_selected_temp(self, revision=None, temperature=None):
    self.settings_timeout = None
    if self.closed:
      return GLib.SOURCE_REMOVE
    revision = self._settings_generation if revision is None else revision
    temperature = self.selected_temp if temperature is None else temperature
    if revision != self._settings_generation:
      return GLib.SOURCE_REMOVE
    self._launch_operation(
      "settings",
      "Guardando preferencia…",
      lambda: self._settings_worker(temperature, revision),
      lambda outcome, generation: self._finish_settings(revision, outcome, generation),
    )
    return GLib.SOURCE_REMOVE

  def _finish_settings(self, revision, outcome, generation):
    if outcome.value == "stale":
      if not self._mutation_channels:
        self.refresh()
      return
    if outcome.confirmed and revision == self._settings_generation:
      self._settings_dirty = False
    self._complete_operation("settings", generation, outcome, notify=False)

  def apply_selected_temp(self):
    self.apply_timeout = None
    if self.closed or not self.ready or not self.main_switch.get_active():
      return GLib.SOURCE_REMOVE
    temperature = self.selected_temp
    self._launch_operation(
      "temperature",
      f"Aplicando {temperature} K…",
      lambda: _apply_temperature_worker(temperature),
      lambda outcome, generation: self._finish_temperature(temperature, outcome, generation),
    )
    return GLib.SOURCE_REMOVE

  def _gamma_settings_worker(self, gamma, revision):
    with self._gamma_settings_write_lock:
      if revision != self._gamma_settings_generation:
        return WorkerResult(True, value="stale")
      try:
        save_gamma(gamma)
      except (OSError, ValueError):
        return WorkerResult(
          False,
          message="No se pudo guardar la preferencia. Inténtalo de nuevo.",
        )
    return WorkerResult(True, value="saved", message="Brillo percibido guardado")

  def persist_selected_gamma(self, revision=None, gamma=None):
    self.gamma_settings_timeout = None
    if self.closed:
      return GLib.SOURCE_REMOVE
    revision = self._gamma_settings_generation if revision is None else revision
    gamma = self.selected_gamma if gamma is None else gamma
    if revision != self._gamma_settings_generation:
      return GLib.SOURCE_REMOVE
    self._launch_operation(
      "gamma-settings",
      "Guardando preferencia…",
      lambda: self._gamma_settings_worker(gamma, revision),
      lambda outcome, generation: self._finish_gamma_settings(revision, outcome, generation),
    )
    return GLib.SOURCE_REMOVE

  def _finish_gamma_settings(self, revision, outcome, generation):
    if outcome.value == "stale":
      return
    if outcome.confirmed and revision == self._gamma_settings_generation:
      self._gamma_settings_dirty = False
    self._complete_operation("gamma-settings", generation, outcome, notify=False)

  def apply_selected_gamma(self):
    self.gamma_apply_timeout = None
    if self.closed or not self.ready:
      return GLib.SOURCE_REMOVE
    gamma = self.selected_gamma
    self._launch_operation(
      "gamma",
      f"Aplicando brillo percibido al {gamma}%…",
      lambda: _apply_gamma_worker(gamma),
      lambda outcome, generation: self._finish_gamma(gamma, outcome, generation),
    )
    return GLib.SOURCE_REMOVE

  def _finish_gamma(self, gamma, outcome, generation):
    self._complete_operation("gamma", generation, outcome)

  def cancel_gamma_apply_timer(self):
    if self.gamma_apply_timeout:
      GLib.source_remove(self.gamma_apply_timeout)
      self.gamma_apply_timeout = None

  def _finish_temperature(self, temperature, outcome, generation):
    self._complete_operation("temperature", generation, outcome)

  def cancel_apply_timer(self):
    if self.apply_timeout:
      GLib.source_remove(self.apply_timeout)
      self.apply_timeout = None

  def on_save_schedule(self, _button):
    schedule = self._schedule_form_values()
    if schedule is None:
      feedback = "Revisa los campos marcados antes de guardar."
      self.schedule_feedback.set_label(feedback)
      set_status(self.schedule_feedback, feedback, busy=False)
      self._set_operation_status("error", "Horario inválido")
      self.toast("Revisa las horas: usa HH:MM y valores diferentes")
      return
    schedule_identity = self.day_identity_switch.get_active()
    self.save_schedule_button.set_sensitive(False)
    self._launch_operation(
      "schedule",
      "Guardando horario…",
      lambda: _save_schedule_worker(
        schedule,
        schedule_identity,
        repair_invalid=bool(self.schedule_config_error),
      ),
      lambda outcome, generation: self._finish_schedule_save(
        schedule, schedule_identity, outcome, generation
      ),
    )

  def _finish_schedule_save(self, schedule, schedule_identity, outcome, generation):
    if outcome.confirmed:
      self.schedule = schedule
      self.schedule_identity = schedule_identity
      self.night_time = schedule["night_time"]
      self.day_time = schedule["day_time"]
      self.schedule_dirty = False
      self.schedule_config_error = ""
      self._set_schedule_widgets()
      feedback = "Horario guardado correctamente."
      self.schedule_feedback.set_label(feedback)
      self.schedule_feedback.remove_css_class("error")
      set_status(self.schedule_feedback, feedback, busy=False)
    self._update_save_button()
    self._complete_operation("schedule", generation, outcome)

  def on_schedule_toggle(self, row, _param):
    if self.updating or not self.ready:
      return
    target = row.get_active()
    schedule = dict(self.schedule)
    identity = self.schedule_identity
    self.schedule_switch.set_sensitive(False)
    self._launch_operation(
      "schedule-toggle",
      "Activando horario…" if target else "Desactivando horario…",
      lambda: _toggle_schedule_worker(target, schedule, identity),
      lambda outcome, generation: self._finish_schedule_toggle(target, outcome, generation),
    )

  def _finish_schedule_toggle(self, target, outcome, generation):
    if not outcome.confirmed:
      self.updating = True
      self.schedule_switch.set_active(not target)
      self.updating = False
    self.schedule_switch.set_sensitive(self.ready)
    self._complete_operation("schedule-toggle", generation, outcome)

  def on_reset(self, _button):
    schedule = dict(self.schedule)
    identity = self.schedule_identity
    self.reset_button.set_sensitive(False)
    self._launch_operation(
      "reset",
      "Aplicando el perfil del horario…",
      lambda: _apply_schedule_worker(schedule, identity),
      lambda outcome, generation: self._finish_reset(outcome, generation),
    )

  def _finish_reset(self, outcome, generation):
    self.reset_button.set_sensitive(self.ready)
    self._complete_operation("reset", generation, outcome)

  def _start_detached_gamma_save(self, gamma, revision):
    def runner():
      with self._gamma_settings_write_lock:
        if revision != self._gamma_settings_generation:
          return
        try:
          save_gamma(gamma)
        except (OSError, ValueError):
          pass

    threading.Thread(
      target=runner,
      name="night-light-gamma-settings-final",
      daemon=False,
    ).start()

  def _start_detached_settings_save(self, temperature, revision):
    def runner():
      with self._settings_write_lock:
        if revision != self._settings_generation:
          return
        try:
          save_settings(temperature)
        except (OSError, ValueError):
          pass

    threading.Thread(
      target=runner,
      name="night-light-settings-final",
      # The final atomic write must finish even while the GTK application exits.
      daemon=False,
    ).start()

  def stop_timers(self):
    self.closed = True
    self.ready = False
    self.cancel_apply_timer()
    self.cancel_gamma_apply_timer()
    if self.settings_timeout:
      GLib.source_remove(self.settings_timeout)
      self.settings_timeout = None
    if self._settings_dirty:
      self._start_detached_settings_save(self.selected_temp, self._settings_generation)
      self._settings_dirty = False
    if self.gamma_settings_timeout:
      GLib.source_remove(self.gamma_settings_timeout)
      self.gamma_settings_timeout = None
    if self._gamma_settings_dirty:
      self._start_detached_gamma_save(self.selected_gamma, self._gamma_settings_generation)
      self._gamma_settings_dirty = False
    if self.refresh_timeout:
      GLib.source_remove(self.refresh_timeout)
      self.refresh_timeout = None
    for channel in tuple(self._tokens):
      self._next_token(channel)
    self._mutation_channels.clear()


class NightLightApp(Adw.Application):
  def __init__(self):
    super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

  def do_activate(self):
    if not hasattr(self, "window"):
      self.hold()
      self.window = NightLightWindow(self)
      self.window.connect("close-request", self.on_window_close)
    self.window.present()

  def on_window_close(self, _window):
    self.window.stop_timers()
    del self.window
    self.release()
    return False


if __name__ == "__main__":
  app = NightLightApp()
  raise SystemExit(app.run())
