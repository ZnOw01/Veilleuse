// Kept free of Qt globals so the state contract can be exercised with Node.

var ROUTES = ['home', 'automation', 'settings'];

// Each route owns its vertical list of cursor sections, so wrapping to a
// route always lands on a control that route actually renders. Sections that
// expose several sibling actions (snooze buttons, shortcut install/remove)
// navigate horizontally across their fields.
var ROUTE_SECTIONS = {
  home: ['nightLight', 'brightness', 'temperature', 'gamma'],
  automation: ['scheduleToggle', 'transition', 'snooze', 'schedule'],
  settings: ['locale', 'scope', 'preset', 'preflight', 'shortcut', 'shortcutActions']
};

var ROUTE_FIELD_COUNTS = {
  home: [1, 1, 1, 1],
  automation: [1, 1, 4, 1],
  settings: [1, 1, 1, 1, 1, 2]
};

var DRAG_SECTIONS = ['brightness', 'temperature', 'gamma'];

// Load I18n when running under Node (CommonJS module present). Quickshell has
// no `require`, so the bundled DEFAULT_COPY below keeps the panel fully
// functional in its native Spanish default until the locale wiring is added.
var I18n = null;
if (typeof module !== 'undefined' && module.exports) {
  I18n = require('./I18n.js');
}

// Bundled Spanish default used only as a Quickshell fallback; it mirrors the
// exact I18n.es dictionary key-for-key (enforced by the parity test) so the
// panel never shows a raw key before the locale library is wired in.
var DEFAULT_COPY = {
  heroTitle: 'Luz nocturna',
  brightness: 'Brillo',
  temperature: 'Temperatura',
  gamma: 'Gamma (brillo percibido)',
  schedule: 'Horario',
  save: 'Guardar cambios',
  saved: 'Cambios guardados',
  unavailable: 'No disponible',
  notConfirmed: 'Estado no confirmado',
  enabled: 'Activada',
  disabled: 'Color natural',
  periodDay: 'Horario: día',
  periodNight: 'Horario: noche',
  manualOverride: 'Anulación manual',
  start: 'Inicio',
  end: 'Fin',
  naturalDay: 'Día natural',
  scheduleDayTemperature: 'Temperatura diurna',
  scheduleTemperature: 'Temperatura nocturna',
  routeHome: 'Inicio',
  routeAutomation: 'Automatización',
  routeSettings: 'Ajustes',
  provenanceAutomatic: 'Automática',
  provenanceManual: 'Manual',
  provenancePreset: 'Perfil',
  provenanceSnooze: 'Posposición',
  provenanceUnknown: 'Desconocido',
  appliedPresetLabel: 'Aplicado ahora',
  midnightExplanation: 'La posposición “hasta mañana” se mantiene hasta el inicio del periodo diurno del día siguiente (medianoche), cuando el horario retoma el perfil programado.',
  preflightTitle: 'Comprobación del asistente',
  preflightStatusOk: 'Todo listo',
  preflightStatusWarn: 'Atención',
  preflightStatusFail: 'Falla',
  errHelperMissing: 'No se pudo iniciar el asistente de control.',
  errBrightnessUnavailable: 'El brillo no está disponible en este momento.',
  errNightlightUnavailable: 'La luz nocturna no está disponible.',
  errMonitorUnavailable: 'El monitor seleccionado no está disponible.',
  errScheduleInvalid: 'El horario configurado no es válido.',
  errSnoozeInvalid: 'La posposición solicitada no es válida.',
  errPresetNotFound: 'No se encontró el perfil solicitado.',
  errPresetInvalid: 'El perfil no es válido.',
  errHistoryUnreadable: 'No se pudo leer el historial.',
  errSettingsWrite: 'No se pudieron guardar los ajustes.',
  errShortcutWrite: 'No se pudo actualizar el acceso directo.',
  errUnknown: 'Se produjo un error desconocido.',
  errInvalidValue: 'El valor solicitado no es válido.',
  errInvalidJson: 'Los datos guardados no tienen un formato válido.',
  errInvalidConfig: 'La configuración guardada no es válida.',
  errInvalidState: 'El estado guardado no es válido.',
  errInvalidHistory: 'El historial guardado no es válido.',
  errReadbackFailed: 'No se pudo confirmar el cambio.',
  errBrightnessWrite: 'No se pudo escribir el brillo del monitor.',
  errScheduleUnavailable: 'El horario configurado no está disponible.',
  errScheduleFailed: 'No se pudo actualizar el horario.',
  errStateFailed: 'No se pudo guardar el estado.',
  errUnsafePath: 'La ruta de datos guardados no es segura.',
  errIoError: 'No se pudieron leer o escribir los datos guardados.',
  errNotExecutable: 'El asistente de control no es ejecutable.',
  errMissingCommand: 'Falta un comando necesario del sistema.',
  errTimeout: 'Se agotó el tiempo de espera del comando.',
  errBackendUnavailable: 'El backend de control no está disponible.',
  errPresetFailed: 'No se pudo aplicar el perfil.',
  errDeadline: 'Se superó el plazo de la operación.',
  errCancelled: 'La operación fue cancelada.',
  errSnoozeFailed: 'No se pudo aplicar la posposición.',
  errTransitionFailed: 'No se pudo completar la transición.',
  errReconcileFailed: 'No se pudo reconciliar el horario.',
  errApplyFailed: 'No se pudo aplicar la luz nocturna.',
  errReadFailed: 'No se pudo leer el estado actual.',
  errNativeFailure: 'La operación nativa no se pudo completar.',
  errScheduleConflict: 'El archivo de horario cambió durante la operación.',
  manualPersistError: 'El ajuste manual se aplicó, pero no se pudo guardar la preferencia; el horario podría revertirlo al próximo ciclo.',
  scheduleDayTimeFormat: 'La hora diurna debe usar el formato HH:MM',
  scheduleNightTimeFormat: 'La hora nocturna debe usar el formato HH:MM',
  scheduleDayNightEqual: 'Las horas de día y noche deben ser diferentes',
  scheduleDayTemperatureRange: 'La temperatura diurna debe estar entre 5900 y 6500 K',
  scheduleNightTemperatureRange: 'La temperatura nocturna debe estar entre 2500 y 5000 K',
  presetTitle: 'Perfiles',
  presetApply: 'Aplicar',
  presetDelete: 'Eliminar',
  presetSave: 'Guardar perfil',
  presetAll: 'Todos los perfiles',
  presetBuiltIn: 'Integrado',
  presetName: 'Nombre del perfil',
  saveCurrentPreset: 'Guardar actual',
  deleteCustomPreset: 'Eliminar perfil',
  deletePresetConfirm: '¿Eliminar?',
  newPresetName: 'Nombre del nuevo perfil',
  reloadPresets: 'Recargar perfiles',
  presetReading: 'Lectura',
  presetWork: 'Trabajo',
  presetCinema: 'Cine',
  focusedMonitor: 'Monitor enfocado',
  monitor: 'Monitor',
  lastApplied: 'Última aplicación',
  openAutomation: 'Editar automatización',
  scheduleEnabled: 'Horario activo',
  scheduleDisabled: 'Horario pausado',
  transitionTitle: 'Transición',
  seconds: 'segundos',
  snooze30: '30 minutos',
  snooze120: '2 horas',
  editSchedule: 'Editar horario',
  cancel: 'Cancelar',
  spanish: 'Español',
  english: 'English',
  runPreflight: 'Comprobar disponibilidad',
  shortcutKeys: 'Teclas',
  liveNow: 'Ahora',
  liveControls: 'Ajustes en vivo',
  working: 'Aplicando…',
  keyboardHints: 'j/k moverse · h/l cambiar vista · Enter activar · Esc cerrar',
  minutesShort: 'min',
  viewHistory: 'Ver historial',
  latestEvent: 'Último',
  scheduleRuns: 'Activo',
  snoozeTitle: 'Posposición',
  snoozeSet: 'Posponer',
  snoozeUntilTomorrow: 'Hasta mañana',
  snoozeClear: 'Cancelar posposición',
  snoozeStatusActive: 'Pospuesta',
  snoozeStatusOff: 'Sin posposición',
  settingsTitle: 'Ajustes',
  applyScope: 'Alcance de aplicación',
  applyScopeSession: 'Sesión',
  applyScopePersistent: 'Persistente',
  scopeHelp: 'Sesión: aplica hasta cerrar la sesión. Persistente: sobrevive a los reinicios.',
  preflightOk: 'Correcto',
  preflightFailed: 'Falla',
  defaultPreset: 'Perfil predeterminado',
  language: 'Idioma',
  shortcut: 'Acceso directo',
  shortcutInstall: 'Instalar',
  shortcutRemove: 'Quitar',
  transitionSeconds: 'Transición (s)',
  historyTitle: 'Historial',
  historyClear: 'Limpiar historial',
  historyEmpty: 'Sin registros'
};

var copy = (I18n && I18n.es) ? I18n.es : DEFAULT_COPY;

// Wire the real locale library at runtime. Quickshell has no `module` or
// `require`, so the Node bootstrap above cannot run there; the panel calls
// this from Component.onCompleted with its imported I18n.js namespace to give
// t() the locale-aware dictionaries instead of the bundled Spanish fallback.
// Passing null unwires the library and falls back to DEFAULT_COPY again.
function setI18n(lib) {
  I18n = lib || null;
  copy = I18n && I18n.es ? I18n.es : DEFAULT_COPY;
}


function routeSections(route) {
  return (ROUTE_SECTIONS[route] || ROUTE_SECTIONS.home).slice();
}

function sectionFieldCount(route, section, scheduleExpanded) {
  var names = routeSections(route);
  var index = boundedInteger(section, 0, names.length - 1);
  if (index === null) index = 0;
  if (route === 'automation' && names[index] === 'schedule')
    return scheduleExpanded === true ? 6 : 1;
  var counts = ROUTE_FIELD_COUNTS[route] || ROUTE_FIELD_COUNTS.home;
  return counts[index] !== undefined ? counts[index] : 1;
}

function cursorStart() {
  return { section: 0, field: 0 };
}

function clamp(value, minimum, maximum) {
  var number = Number(value);
  if (!isFinite(number)) return null;
  return Math.max(minimum, Math.min(maximum, number));
}

function boundedInteger(value, minimum, maximum) {
  var number = clamp(value, minimum, maximum);
  return number === null ? null : Math.round(number);
}

function moveCursor(cursor, key, route, scheduleExpanded) {
  var names = routeSections(route);
  var section = boundedInteger(cursor && cursor.section, 0, names.length - 1);
  if (section === null) section = 0;
  // Preserve the incoming field across vertical moves so the cursor keeps its
  // relative position; the destination section clamps it at the end.
  var field = boundedInteger(cursor && cursor.field, 0, 6);
  if (field === null) field = 0;

  if (scheduleExpanded === true && route === 'automation' && names[section] === 'schedule'
      && (key === 'j' || key === 'ArrowDown' || key === 'k' || key === 'ArrowUp')) {
    if (key === 'j' || key === 'ArrowDown') field = Math.min(5, field + 1);
    if (key === 'k' || key === 'ArrowUp') field = Math.max(0, field - 1);
    return { section: section, field: field };
  }

  if (key === 'j' || key === 'ArrowDown') section = Math.min(names.length - 1, section + 1);
  if (key === 'k' || key === 'ArrowUp') section = Math.max(0, section - 1);
  if (key === 'l' || key === 'ArrowRight') field = Math.min(sectionFieldCount(route, section, scheduleExpanded) - 1, field + 1);
  if (key === 'h' || key === 'ArrowLeft') field = Math.max(0, field - 1);
  field = Math.min(sectionFieldCount(route, section, scheduleExpanded) - 1, field);

  return { section: section, field: field };
}

// Per-section keyboard step magnitudes and ranges. The panel mutates sliders
// from ArrowRight/ArrowLeft; each press counts as one step so the slider
// moves by SECTION_STEP. Temperature steps 50 K so the numeric line walks
// without skipping; the pointer drag itself stays free-form per kelvin.
var SECTION_STEP = {
  brightness: 1,
  temperature: 50,
  gamma: 1
};

var SECTION_RANGES = {
  brightness: { min: 1, max: 100 },
  temperature: { min: 2500, max: 6500 },
  gamma: { min: 0, max: 100 }
};

function sectionStep(section) {
  return SECTION_STEP[section] || 0;
}

// Absolute value to request for a section when `pending` steps still sit ahead
// of the last confirmed `confirmed` readback. Clamped to the section range so
// requests never aim beyond a reachable physical value.
function stepTargetValue(section, confirmed, pending) {
  var range = SECTION_RANGES[section];
  if (!range || typeof confirmed !== 'number' || !isFinite(confirmed)) return confirmed;
  var magnitude = SECTION_STEP[section] || 0;
  var steps = typeof pending === 'number' && isFinite(pending) ? pending : 0;
  return Math.max(range.min, Math.min(range.max, confirmed + steps * magnitude));
}

// One rapid keyboard step. `delta` is +1 (ArrowRight) or -1 (ArrowLeft) and
// `pending` is the number of steps already requested ahead of the last
// confirmed readback. Accumulating `pending` across presses lets N rapid Arrow
// presses request N steps without waiting for N sequential helper readbacks;
// a step that is clamped away at a range boundary is not accumulated.
function keyboardStep(section, delta, confirmed, pending) {
  var steps = typeof pending === 'number' && isFinite(pending) ? pending : 0;
  if (delta > 0) steps += 1;
  else if (delta < 0) steps -= 1;
  var value = stepTargetValue(section, confirmed, steps);
  if (value === confirmed && steps !== 0) steps = 0;
  return { value: value, pending: steps };
}

// Reconcile accumulated keyboard steps against a confirmed readback.
//
// `previous` is the state before the readback, `current` the state after it,
// `pending` the per-section keyboard-step offsets and `lastOperation` the
// operation tag of the request that produced the readback. Pointer slider
// drags and foreign operations (preset apply, reconcile, another section's
// request) move a section's value without keyboard intent, so draining must
// be gated: only a same-section request drains; anything else clears the
// stale pending offset instead of re-queueing a revert.
function reconcilePendingSteps(previous, current, pending, lastOperation) {
  var out = {
    brightness: pending && typeof pending.brightness === 'number' ? pending.brightness : 0,
    temperature: pending && typeof pending.temperature === 'number' ? pending.temperature : 0,
    gamma: pending && typeof pending.gamma === 'number' ? pending.gamma : 0
  };
  var requests = [];
  var sections = ['brightness', 'temperature', 'gamma'];
  for (var i = 0; i < sections.length; i++) {
    var section = sections[i];
    if (out[section] === 0)
      continue;
    var before = section === 'brightness' ? previous.brightness.percent : (section === 'temperature' ? previous.nightlight.temperature : previous.nightlight.gamma);
    var after = section === 'brightness' ? current.brightness.percent : (section === 'temperature' ? current.nightlight.temperature : current.nightlight.gamma);
    if (typeof before !== 'number' || typeof after !== 'number')
      continue;
    var magnitude = sectionStep(section);
    if (magnitude <= 0)
      continue;
    var realized = Math.round((after - before) / magnitude);
    if (lastOperation !== section) {
      out[section] = 0;
      continue;
    }
    if (realized === 0)
      continue;
    var remaining = out[section] - realized;
    if (remaining === 0) {
      out[section] = 0;
      continue;
    }
    // A same-section concurrent change that overshoots the pending intent
    // flips the sign of `remaining`. Re-queueing that would counter-adjust
    // back past the confirmed value; drain instead, never negative-correct.
    if (remaining < 0 !== out[section] < 0) {
      out[section] = 0;
      continue;
    }
    var target = stepTargetValue(section, after, remaining);
    if (target === after) {
      out[section] = 0;
      continue;
    }
    out[section] = remaining;
    requests.push({ section: section, value: target });
  }
  return { pending: out, requests: requests };
}

// Vertical route wrapping for the panel cursor: pressing Up on a route's
// first section moves to the previous route (landing on its last visible
// section), pressing Down on the last section moves to the next route
// (landing on its first visible section). Interior navigation and expanded
// editors return null so the cursor model keeps its existing behavior.
function navigateCursorRoute(route, cursor, key, scheduleExpanded) {
  if (scheduleExpanded === true)
    return null;
  var names = routeSections(route);
  var section = boundedInteger(cursor && cursor.section, 0, names.length - 1);
  if (section === null)
    return null;
  var index = ROUTES.indexOf(route);
  if (index === -1)
    index = 0;
  if ((key === 'k' || key === 'ArrowUp') && section === 0) {
    var previous = ROUTES[(index - 1 + ROUTES.length) % ROUTES.length];
    return { route: previous, section: routeSections(previous).length - 1 };
  }
  if ((key === 'j' || key === 'ArrowDown') && section === names.length - 1) {
    var next = ROUTES[(index + 1) % ROUTES.length];
    return { route: next, section: 0 };
  }
  return null;
}

// Absolute pointer drag intent. The helper enforces one physical point per
// brightness write, so a drag to 70 has to be re-requested against each
// confirmed readback; dragTargetPush stores the newest absolute target so a
// fast drag always converges on the finger's last position (latest wins) and
// the UI never shows a value the physical monitor has not reached.
function dragTargetEmpty() {
  return { brightness: null, temperature: null, gamma: null };
}

function dragTargetPush(target, section, value) {
  var out = dragTargetEmpty();
  var src = target && typeof target === 'object' ? target : {};
  for (var i = 0; i < DRAG_SECTIONS.length; i++) {
    var name = DRAG_SECTIONS[i];
    if (src[name] === null || src[name] === undefined) out[name] = null;
    else out[name] = src[name];
  }
  var range = SECTION_RANGES[section];
  var number = Number(value);
  if (value === null || value === undefined || value === '' || !range || !isFinite(number))
    out[section] = null;
  else
    out[section] = Math.max(range.min, Math.min(range.max, Math.round(number)));
  return out;
}

function confirmedValue(state, section) {
  if (!state || typeof state !== 'object') return null;
  if (section === 'brightness')
    return state.brightness && typeof state.brightness.percent === 'number' ? state.brightness.percent : null;
  if (section === 'temperature')
    return state.nightlight && typeof state.nightlight.temperature === 'number' ? state.nightlight.temperature : null;
  if (section === 'gamma')
    return state.nightlight && typeof state.nightlight.gamma === 'number' ? state.nightlight.gamma : null;
  return null;
}

// Advance a pending drag target against a confirmed readback. A same-section
// readback that moved toward the goal re-queues the absolute target so the
// helper can apply its next one-point step; a readback that reached the goal,
// moved away from it, made no progress, or belongs to a foreign operation
// clears the intent instead of looping or reverting the physical state.
function reconcileDragTargets(previous, current, target, lastOperation) {
  var out = dragTargetEmpty();
  var src = target && typeof target === 'object' ? target : {};
  var requests = [];
  for (var i = 0; i < DRAG_SECTIONS.length; i++) {
    var section = DRAG_SECTIONS[i];
    var goal = src[section];
    if (typeof goal !== 'number' || !isFinite(goal)) continue;
    if (lastOperation !== section) continue;
    var before = confirmedValue(previous, section);
    var after = confirmedValue(current, section);
    if (typeof before !== 'number' || typeof after !== 'number') continue;
    if (after === goal) continue;
    var progressed = goal > after ? after > before : after < before;
    if (!progressed) continue;
    out[section] = goal;
    requests.push({ section: section, value: goal });
  }
  return { target: out, requests: requests };
}

function validTime(value) {
  return typeof value === 'string' && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value) ? value : null;
}

function validNumber(value, minimum, maximum) {
  if (value === null || value === undefined || typeof value === 'boolean' || (typeof value === 'string' && value.trim() === '')) return null;
  var number = Number(value);
  return isFinite(number) && number >= minimum && number <= maximum ? Math.round(number) : null;
}

function normalizeBrightness(source, root) {
  var raw = source && typeof source === 'object' ? source : {};
  var percentValue = raw.percent !== undefined ? raw.percent : (typeof source === 'number' ? source : root.brightness);
  var percent = validNumber(percentValue, 1, 100);
  var advertised = raw.available !== undefined ? raw.available === true : root.available === true;
  return {
    available: advertised && percent !== null,
    percent: advertised && percent !== null ? percent : null,
    monitor: raw.monitor ? String(raw.monitor) : null,
    error: raw.error ? String(raw.error) : null
  };
}

function normalizeNightlight(source, root) {
  var raw = source && typeof source === 'object' ? source : {};
  var temperatureValue = raw.temperature !== undefined ? raw.temperature : root.temperature;
  var gammaValue = raw.gamma !== undefined ? raw.gamma : root.gamma;
  var temperature = validNumber(temperatureValue, 2500, 6500);
  var gamma = validNumber(gammaValue, 0, 100);
  var advertised = raw.available !== undefined ? raw.available === true : root.available === true;
  var enabled = raw.enabled !== undefined ? raw.enabled === true : root.enabled === true;
  return {
    available: advertised && temperature !== null && gamma !== null,
    enabled: advertised && temperature !== null && gamma !== null && enabled,
    identity: raw.identity === true || raw.identity === false ? raw.identity : null,
    temperature: advertised && temperature !== null ? temperature : null,
    gamma: advertised && gamma !== null ? gamma : null,
    error: raw.error ? String(raw.error) : null
  };
}

function normalizeSchedule(source) {
  var raw = source && typeof source === 'object' ? source : {};
  var dayTime = validTime(raw.day_time !== undefined ? raw.day_time : raw.start);
  var nightTime = validTime(raw.night_time !== undefined ? raw.night_time : raw.end);
  var dayTemperature = validNumber(raw.day_temp, 5900, 6500);
  var nightTemperature = validNumber(raw.night_temp !== undefined ? raw.night_temp : raw.temperature, 2500, 5000);
  var available = raw.available === true;
  if (raw.available === undefined)
    available = dayTime !== null && nightTime !== null && nightTemperature !== null;
  if (dayTime !== null && dayTime === nightTime) {
    dayTime = null;
    nightTime = null;
    available = false;
  }
  var period = raw.period === 'day' || raw.period === 'night' ? raw.period : null;
  return {
    available: available,
    day_time: dayTime,
    day_temp: dayTemperature,
    night_time: nightTime,
    night_temp: nightTemperature,
    day_identity: raw.day_identity === true,
    period: period,
    start: dayTime,
    end: nightTime,
    temperature: nightTemperature,
    error: raw.error ? String(raw.error) : null
  };
}

function normalizeState(raw) {
  var source = raw || {};
  var brightness = normalizeBrightness(source.brightness, source);
  var nightlight = normalizeNightlight(source.nightlight, source);
  var schedule = normalizeSchedule(source.schedule);
  var available = brightness.available && nightlight.available;
  if (source.available !== undefined)
    available = available && source.available === true;
  return {
    available: available,
    enabled: available && nightlight.enabled,
    brightness: brightness,
    brightnessPercent: brightness.percent,
    temperature: available ? nightlight.temperature : null,
    gamma: available ? nightlight.gamma : null,
    nightlight: nightlight,
    schedule: schedule,
    error: String(source.error || brightness.error || nightlight.error || schedule.error || (available ? '' : copy.notConfirmed))
  };
}

function validateScheduleFields(start, end, naturalDay, dayTemperature, nightTemperature, locale) {
  if (validTime(start) === null)
    return { valid: false, error: t('scheduleDayTimeFormat', locale) };
  if (validTime(end) === null)
    return { valid: false, error: t('scheduleNightTimeFormat', locale) };
  if (start === end)
    return { valid: false, error: t('scheduleDayNightEqual', locale) };
  if (validNumber(dayTemperature, 5900, 6500) === null)
    return { valid: false, error: t('scheduleDayTemperatureRange', locale) };
  if (validNumber(nightTemperature, 2500, 5000) === null)
    return { valid: false, error: t('scheduleNightTemperatureRange', locale) };
  return { valid: true, error: '' };
}

function isManualOverride(state) {
  if (!state || state.available !== true)
    return false;
  // The persisted automation record is reconcile's ground truth: when the
  // status exposes it, agree with reconcile instead of re-deriving intent
  // from a live-state heuristic that can disagree with it.
  var automation = state.automation;
  if (automation && typeof automation === 'object'
      && Object.prototype.hasOwnProperty.call(automation, 'manual_override')) {
    return automation.manual_override !== null && automation.manual_override !== undefined;
  }
  var schedule = state.schedule;
  if (!schedule || schedule.available !== true)
    return false;
  if (schedule.period === 'day') {
    var expectedDayEnabled = schedule.day_identity !== true
      && schedule.day_temp !== null
      && schedule.day_temp < 6000;
    return state.enabled !== expectedDayEnabled;
  }
  if (schedule.period === 'night') return state.enabled !== true;
  return false;
}

// Superficial state merge: nested brightness/nightlight/schedule objects merge
// key-by-key, every other patch key overwrites, a full status patch (brightness
// plus nightlight) re-derives availability, `enabled` and nightlight.enabled
// stay in sync, and the result re-normalizes so no unvalidated value renders.
// Shared by commitResponse and by the panel when it adopts the state of a
// superseded write that still physically applied.
function mergeStatePatch(previous, patch) {
  var current = normalizeState(previous);
  var validPatch = patch !== null && typeof patch === 'object' && !Array.isArray(patch) ? patch : {};
  var next = {};
  for (var key in current) next[key] = current[key];
  var fullStatus = Object.prototype.hasOwnProperty.call(validPatch, 'brightness')
    && Object.prototype.hasOwnProperty.call(validPatch, 'nightlight');
  if (fullStatus) {
    delete next.available;
    delete next.error;
  }
  for (var patchKey in validPatch) {
    if ((patchKey === 'brightness' || patchKey === 'nightlight' || patchKey === 'schedule')
        && validPatch[patchKey] && typeof validPatch[patchKey] === 'object'
        && current[patchKey] && typeof current[patchKey] === 'object') {
      next[patchKey] = {};
      for (var currentNestedKey in current[patchKey]) next[patchKey][currentNestedKey] = current[patchKey][currentNestedKey];
      for (var patchNestedKey in validPatch[patchKey]) next[patchKey][patchNestedKey] = validPatch[patchKey][patchNestedKey];
    } else {
      next[patchKey] = validPatch[patchKey];
    }
  }
  if (validPatch.enabled !== undefined && validPatch.nightlight === undefined) {
    next.nightlight = {};
    for (var nightlightKey in current.nightlight) next.nightlight[nightlightKey] = current.nightlight[nightlightKey];
    next.nightlight.enabled = validPatch.enabled === true;
  } else if (validPatch.nightlight && validPatch.enabled === undefined && validPatch.nightlight.enabled !== undefined) {
    next.enabled = validPatch.nightlight.enabled === true;
  }
  return normalizeState(next);
}

function commitResponse(previousState, response) {
  var current = normalizeState(previousState);
  var requestId = response && response.requestId;
  var latestRequestId = response && response.latestRequestId;
  var validRequestId = typeof requestId === 'number' && isFinite(requestId) && Math.floor(requestId) === requestId && requestId >= 0;
  var validLatestRequestId = typeof latestRequestId === 'number' && isFinite(latestRequestId) && Math.floor(latestRequestId) === latestRequestId && latestRequestId >= 0;
  var patch = response && response.state;
  var validPatch = patch !== null && typeof patch === 'object' && !Array.isArray(patch);
  var stateKeys = ['available', 'enabled', 'brightness', 'brightnessPercent', 'temperature', 'gamma', 'nightlight', 'schedule', 'error'];
  var hasStateField = false;
  if (validPatch) {
    for (var stateKeyIndex = 0; stateKeyIndex < stateKeys.length; stateKeyIndex++) {
      if (Object.prototype.hasOwnProperty.call(patch, stateKeys[stateKeyIndex])) {
        hasStateField = true;
        break;
      }
    }
  }
  if (!response || !validRequestId || !validLatestRequestId || requestId !== latestRequestId || response.ok !== true || !validPatch || !hasStateField) {
    return { accepted: false, state: current };
  }
  return { accepted: true, state: mergeStatePatch(current, patch) };
}

function t(key, locale) {
  if (I18n) return I18n.t(key, locale);
  return Object.prototype.hasOwnProperty.call(copy, key) ? copy[key] : key;
}

function copyFor(locale) {
  if (I18n) return I18n.dictionary(locale);
  return copy;
}

var ERROR_CODE_KEYS = {
  // camelCase aliases (backward-compatible with the original contract).
  helperMissing: 'errHelperMissing',
  brightnessUnavailable: 'errBrightnessUnavailable',
  nightlightUnavailable: 'errNightlightUnavailable',
  monitorUnavailable: 'errMonitorUnavailable',
  scheduleInvalid: 'errScheduleInvalid',
  snoozeInvalid: 'errSnoozeInvalid',
  presetNotFound: 'errPresetNotFound',
  presetInvalid: 'errPresetInvalid',
  historyUnreadable: 'errHistoryUnreadable',
  settingsWrite: 'errSettingsWrite',
  shortcutWrite: 'errShortcutWrite',
  // snake_case codes actually emitted by the Python helper, mapped to the
  // same localized dictionaries so no emitted code degrades to errUnknown.
  helper_unavailable: 'errHelperMissing',
  monitor_unavailable: 'errMonitorUnavailable',
  invalid_argument: 'errInvalidValue',
  invalid_transition: 'errInvalidValue',
  invalid_brightness_step: 'errInvalidValue',
  invalid_value: 'errInvalidValue',
  invalid_preset: 'errPresetInvalid',
  builtin_immutable: 'errPresetInvalid',
  default_conflict: 'errPresetInvalid',
  invalid_json: 'errInvalidJson',
  invalid_schema: 'errInvalidConfig',
  invalid_config: 'errInvalidConfig',
  invalid_state: 'errInvalidState',
  invalid_history: 'errInvalidHistory',
  brightness_readback_failed: 'errReadbackFailed',
  temperature_readback_failed: 'errReadbackFailed',
  gamma_readback_failed: 'errReadbackFailed',
  readback_mismatch: 'errReadbackFailed',
  brightness_write_failed: 'errBrightnessWrite',
  schedule_unavailable: 'errScheduleUnavailable',
  schedule_failed: 'errScheduleFailed',
  state_unavailable: 'errStateFailed',
  state_failed: 'errStateFailed',
  state_update_failed: 'errStateFailed',
  unsafe_path: 'errUnsafePath',
  io_error: 'errIoError',
  not_executable: 'errNotExecutable',
  missing_command: 'errMissingCommand',
  timeout: 'errTimeout',
  backend_unavailable: 'errBackendUnavailable',
  preset_failed: 'errPresetFailed',
  preset_not_found: 'errPresetNotFound',
  shortcut_failed: 'errShortcutWrite',
  deadline_exceeded: 'errDeadline',
  deadline: 'errDeadline',
  cancelled: 'errCancelled',
  snooze_failed: 'errSnoozeFailed',
  transition_failed: 'errTransitionFailed',
  reconcile_failed: 'errReconcileFailed',
  apply_failed: 'errApplyFailed',
  nightlight_failure: 'errApplyFailed',
  read_failed: 'errReadFailed',
  native_failure: 'errNativeFailure',
  native_operation_missing: 'errNativeFailure',
  conflict: 'errScheduleConflict',
  missing_config: 'errScheduleConflict',
  malformed_config: 'errScheduleConflict',
  ambiguous_config: 'errScheduleConflict',
  rollback_failed: 'errScheduleConflict',
  malformed_state: 'errScheduleConflict',
  history_error: 'errInvalidHistory',
  history_failed: 'errInvalidHistory'
};

function errorCodeMessage(code, locale) {
  var key = Object.prototype.hasOwnProperty.call(ERROR_CODE_KEYS, code) ? ERROR_CODE_KEYS[code] : 'errUnknown';
  return t(key, locale);
}

function localizeError(error, locale) {
  if (!error) return '';
  if (typeof error === 'string' && Object.prototype.hasOwnProperty.call(ERROR_CODE_KEYS, error)) {
    return errorCodeMessage(error, locale);
  }
  return error;
}

// Localize a state error diagnostic: known codes map through the dictionaries,
// the model's Spanish "not confirmed" fallback maps to the active locale, and
// every other literal passes through verbatim.
function localizeStateError(error, locale) {
  var text = error ? String(error) : '';
  if (text === copy.notConfirmed) return t('notConfirmed', locale);
  return localizeError(text, locale);
}

function routeOrder() {
  return ROUTES.slice();
}
var PROVENANCE_KEYS = {
  automatic: 'provenanceAutomatic',
  manual: 'provenanceManual',
  preset: 'provenancePreset',
  snooze: 'provenanceSnooze',
  unknown: 'provenanceUnknown'
};

function provenanceLabel(origin, locale) {
  var key = Object.prototype.hasOwnProperty.call(PROVENANCE_KEYS, origin) ? PROVENANCE_KEYS[origin] : 'provenanceUnknown';
  return t(key, locale);
}

function midnightExplanation(locale) {
  return t('midnightExplanation', locale);
}

function preflightStatus(preflight, locale) {
  var checks = preflight && Array.isArray(preflight.checks) ? preflight.checks : [];
  var failed = 0;
  var warnings = 0;
  for (var i = 0; i < checks.length; i++) {
    var check = checks[i] || {};
    if (check.ok !== true) failed += 1;
    else if (check.warn === true) warnings += 1;
  }
  var statusKey = failed > 0 || checks.length === 0 ? 'preflightStatusFail' : (warnings > 0 ? 'preflightStatusWarn' : 'preflightStatusOk');
  var mapped = [];
  for (var j = 0; j < checks.length; j++) {
    var c = checks[j] || {};
    mapped.push({
      name: c.name ? String(c.name) : '',
      ok: c.ok === true,
      warn: c.warn === true,
      error: c.error ? (typeof c.error === 'string' ? localizeError(c.error, locale) : c.error) : ''
    });
  }
  return {
    ok: checks.length > 0 && failed === 0 && warnings === 0,
    status: t(statusKey, locale),
    failed: failed,
    warnings: warnings,
    checks: mapped
  };
}

function presetViewModel(presets, selected, locale) {
  var list = Array.isArray(presets) ? presets : [];
  var applyLabel = t('presetApply', locale);
  var builtinLabel = t('presetBuiltIn', locale);
  var mapped = [];
  for (var i = 0; i < list.length; i++) {
    var preset = list[i] || {};
    var name = preset.name ? String(preset.name) : '';
    mapped.push({
      name: name,
      builtin: preset.builtin === true,
      selected: name !== '' && name === String(selected == null ? '' : selected),
      applyLabel: applyLabel,
      builtinLabel: builtinLabel
    });
  }
  return mapped;
}

function snoozeViewModel(automation, locale) {
  var a = automation && typeof automation === 'object' ? automation : {};
  return {
    snoozed: a.snoozed === true,
    scheduleEnabled: a.schedule_enabled === true,
    transitionSeconds: a.transition_seconds,
    statusLabel: t(a.snoozed === true ? 'snoozeStatusActive' : 'snoozeStatusOff', locale),
    snoozeSetLabel: t('snoozeSet', locale),
    snoozeUntilTomorrowLabel: t('snoozeUntilTomorrow', locale),
    snoozeClearLabel: t('snoozeClear', locale)
  };
}

function settingsViewModel(settings, locale) {
  var s = settings && typeof settings === 'object' ? settings : {};
  return {
    language: s.locale ? String(s.locale) : 'es',
    applyScope: s.apply_scope === 'persistent' ? 'persistent' : 'session',
    defaultPreset: s.default_preset ? String(s.default_preset) : '',
    shortcutKeys: s.shortcut_keys ? String(s.shortcut_keys) : '',
    languageLabel: t('language', locale),
    applyScopeLabel: t('applyScope', locale),
    sessionLabel: t('applyScopeSession', locale),
    persistentLabel: t('applyScopePersistent', locale),
    defaultPresetLabel: t('defaultPreset', locale),
    shortcutLabel: t('shortcut', locale),
    shortcutInstallLabel: t('shortcutInstall', locale),
    shortcutRemoveLabel: t('shortcutRemove', locale),
    transitionLabel: t('transitionSeconds', locale)
  };
}

function historyViewModel(records, locale) {
  var list = Array.isArray(records) ? records : [];
  var bounded = list.slice(0, 50);
  var mapped = [];
  for (var i = 0; i < bounded.length; i++) {
    var record = bounded[i] || {};
    mapped.push({
      time: record.time ? String(record.time) : '',
      operation: record.operation ? String(record.operation) : '',
      origin: record.origin ? String(record.origin) : ''
    });
  }
  return {
    records: mapped,
    empty: mapped.length === 0,
    emptyLabel: t('historyEmpty', locale),
    clearLabel: t('historyClear', locale)
  };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    copy: copy,
    DEFAULT_COPY: DEFAULT_COPY,
    ERROR_CODE_KEYS: ERROR_CODE_KEYS,
    setI18n: setI18n,
    routeSections: routeSections,
    sectionFieldCount: sectionFieldCount,
    cursorStart: cursorStart,
    moveCursor: moveCursor,
    sectionStep: sectionStep,
    stepTargetValue: stepTargetValue,
    keyboardStep: keyboardStep,
    reconcilePendingSteps: reconcilePendingSteps,
    dragTargetEmpty: dragTargetEmpty,
    dragTargetPush: dragTargetPush,
    reconcileDragTargets: reconcileDragTargets,
    navigateCursorRoute: navigateCursorRoute,
    normalizeState: normalizeState,
    validateScheduleFields: validateScheduleFields,
    isManualOverride: isManualOverride,
    mergeStatePatch: mergeStatePatch,
    commitResponse: commitResponse,
    t: t,
    copyFor: copyFor,
    errorCodeMessage: errorCodeMessage,
    localizeError: localizeError,
    localizeStateError: localizeStateError,
    routeOrder: routeOrder,
    provenanceLabel: provenanceLabel,
    midnightExplanation: midnightExplanation,
    preflightStatus: preflightStatus,
    presetViewModel: presetViewModel,
    snoozeViewModel: snoozeViewModel,
    settingsViewModel: settingsViewModel,
    historyViewModel: historyViewModel
  };
}
