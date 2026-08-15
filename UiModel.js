// Kept free of Qt globals so the state contract can be exercised with Node.

var SECTION_ORDER = ['nightLight', 'brightness', 'temperature', 'gamma', 'schedule'];
var FIELD_COUNTS = [2, 2, 2, 2, 6];
var ROUTES = ['home', 'automation', 'settings'];

// Load I18n when running under Node (CommonJS module present). Quickshell has
// no `require`, so the bundled DEFAULT_COPY below keeps the panel fully
// functional in its native Spanish default until the locale wiring is added.
var I18n = null;
if (typeof module !== 'undefined' && module.exports) {
  I18n = require('./I18n.js');
}

// Bundled Spanish default used only as a Quickshell fallback; in Node the
// `copy` surface is the exact I18n.es dictionary so both stay in parity.
var DEFAULT_COPY = {
  heroTitle: 'Luz nocturna',
  brightness: 'Brillo',
  temperature: 'Temperatura',
  gamma: 'Brillo percibido',
  schedule: 'Horario',
  save: 'Guardar cambios',
  saved: 'Cambios guardados',
  unavailable: 'No disponible',
  notConfirmed: 'Estado no confirmado',
  enabled: 'Activada',
  disabled: 'Color natural',
  periodDay: 'Periodo diurno',
  periodNight: 'Periodo nocturno',
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
  presetTitle: 'Perfiles',
  presetApply: 'Aplicar',
  presetDelete: 'Eliminar',
  presetSave: 'Guardar perfil',
  presetAll: 'Todos los perfiles',
  presetBuiltIn: 'Integrado',
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


function sectionOrder() {
  return SECTION_ORDER.slice();
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

function moveCursor(cursor, key, scheduleExpanded) {
  var section = boundedInteger(cursor && cursor.section, 0, SECTION_ORDER.length - 1);
  var field = boundedInteger(cursor && cursor.field, 0, FIELD_COUNTS[section === null ? 0 : section] - 1);
  if (section === null) section = 0;
  if (field === null) field = 0;

  if (scheduleExpanded === true && section === 4 && (key === 'j' || key === 'ArrowDown' || key === 'k' || key === 'ArrowUp')) {
    if (key === 'j' || key === 'ArrowDown') field = Math.min(FIELD_COUNTS[section] - 1, field + 1);
    if (key === 'k' || key === 'ArrowUp') field = Math.max(0, field - 1);
    return { section: section, field: field };
  }

  if (key === 'j' || key === 'ArrowDown') section = Math.min(SECTION_ORDER.length - 1, section + 1);
  if (key === 'k' || key === 'ArrowUp') section = Math.max(0, section - 1);
  if (key === 'l' || key === 'ArrowRight') field = Math.min(FIELD_COUNTS[section] - 1, field + 1);
  if (key === 'h' || key === 'ArrowLeft') field = Math.max(0, field - 1);
  field = Math.min(FIELD_COUNTS[section] - 1, field);

  return { section: section, field: field };
}

// Per-section keyboard step magnitudes and ranges. The panel mutates sliders
// from ArrowRight/ArrowLeft; each press counts as one step so the slider
// moves by SECTION_STEP (temperature scales each step by 100 K).
var SECTION_STEP = {
  brightness: 1,
  temperature: 100,
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

// Vertical route wrapping for the panel cursor: pressing Up on the first
// section moves to the previous route, pressing Down on the last section
// moves to the next route, both wrapping around the route list. Interior
// navigation and expanded editors return null so the cursor model keeps its
// existing behavior.
function navigateCursorRoute(route, cursor, key, scheduleExpanded) {
  if (scheduleExpanded === true)
    return null;
  var section = boundedInteger(cursor && cursor.section, 0, SECTION_ORDER.length - 1);
  if (section === null)
    return null;
  var index = ROUTES.indexOf(route);
  if (index === -1)
    index = 0;
  if ((key === 'k' || key === 'ArrowUp') && section === 0)
    return { route: ROUTES[(index - 1 + ROUTES.length) % ROUTES.length] };
  if ((key === 'j' || key === 'ArrowDown') && section === SECTION_ORDER.length - 1)
    return { route: ROUTES[(index + 1) % ROUTES.length] };
  return null;
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

function validateScheduleFields(start, end, naturalDay, dayTemperature, nightTemperature) {
  if (validTime(start) === null)
    return { valid: false, error: 'La hora diurna debe usar el formato HH:MM' };
  if (validTime(end) === null)
    return { valid: false, error: 'La hora nocturna debe usar el formato HH:MM' };
  if (start === end)
    return { valid: false, error: 'Las horas de día y noche deben ser diferentes' };
  if (validNumber(dayTemperature, 5900, 6500) === null)
    return { valid: false, error: 'La temperatura diurna debe estar entre 5900 y 6500 K' };
  if (validNumber(nightTemperature, 2500, 5000) === null)
    return { valid: false, error: 'La temperatura nocturna debe estar entre 2500 y 5000 K' };
  return { valid: true, error: '' };
}

function isManualOverride(state) {
  var schedule = state && state.schedule;
  if (!state || state.available !== true || !schedule || schedule.available !== true)
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
  var next = {};
  for (var key in current) next[key] = current[key];
  var fullStatus = Object.prototype.hasOwnProperty.call(patch, 'brightness')
    && Object.prototype.hasOwnProperty.call(patch, 'nightlight');
  if (fullStatus) {
    delete next.available;
    delete next.error;
  }
  for (var patchKey in patch) {
    if ((patchKey === 'brightness' || patchKey === 'nightlight' || patchKey === 'schedule')
        && patch[patchKey] && typeof patch[patchKey] === 'object'
        && current[patchKey] && typeof current[patchKey] === 'object') {
      next[patchKey] = {};
      for (var currentNestedKey in current[patchKey]) next[patchKey][currentNestedKey] = current[patchKey][currentNestedKey];
      for (var patchNestedKey in patch[patchKey]) next[patchKey][patchNestedKey] = patch[patchKey][patchNestedKey];
    } else {
      next[patchKey] = patch[patchKey];
    }
  }
  if (patch.enabled !== undefined && patch.nightlight === undefined) {
    next.nightlight = {};
    for (var nightlightKey in current.nightlight) next.nightlight[nightlightKey] = current.nightlight[nightlightKey];
    next.nightlight.enabled = patch.enabled === true;
  } else if (patch.nightlight && patch.enabled === undefined && patch.nightlight.enabled !== undefined) {
    next.enabled = patch.nightlight.enabled === true;
  }
  return { accepted: true, state: normalizeState(next) };
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
  shortcutWrite: 'errShortcutWrite'
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

function routeOrder() {
  return ROUTES.slice();
}

function routeStart() {
  return ROUTES[0];
}

function moveRoute(route, key) {
  var index = ROUTES.indexOf(route);
  if (index === -1) index = 0;
  if (key === 'l' || key === 'ArrowRight') index = Math.min(ROUTES.length - 1, index + 1);
  if (key === 'h' || key === 'ArrowLeft') index = Math.max(0, index - 1);
  return ROUTES[index];
}

function routeLabel(route, locale) {
  var name = String(route || '');
  var key = name === '' ? 'routeHome' : 'route' + name.charAt(0).toUpperCase() + name.slice(1);
  return t(key, locale);
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
    FIELD_COUNTS: FIELD_COUNTS,
    sectionOrder: sectionOrder,
    cursorStart: cursorStart,
    moveCursor: moveCursor,
    sectionStep: sectionStep,
    stepTargetValue: stepTargetValue,
    keyboardStep: keyboardStep,
    reconcilePendingSteps: reconcilePendingSteps,
    navigateCursorRoute: navigateCursorRoute,
    normalizeState: normalizeState,
    validateScheduleFields: validateScheduleFields,
    isManualOverride: isManualOverride,
    commitResponse: commitResponse,
    t: t,
    copyFor: copyFor,
    errorCodeMessage: errorCodeMessage,
    localizeError: localizeError,
    routeOrder: routeOrder,
    routeStart: routeStart,
    moveRoute: moveRoute,
    routeLabel: routeLabel,
    provenanceLabel: provenanceLabel,
    midnightExplanation: midnightExplanation,
    preflightStatus: preflightStatus,
    presetViewModel: presetViewModel,
    snoozeViewModel: snoozeViewModel,
    settingsViewModel: settingsViewModel,
    historyViewModel: historyViewModel
  };
}
