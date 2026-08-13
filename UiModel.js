// Kept free of Qt globals so the state contract can be exercised with Node.

var SECTION_ORDER = ['nightLight', 'brightness', 'temperature', 'gamma', 'schedule'];
var FIELD_COUNTS = [2, 2, 2, 2, 6];

var copy = {
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
  scheduleTemperature: 'Temperatura nocturna'
};

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

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    copy: copy,
    FIELD_COUNTS: FIELD_COUNTS,
    sectionOrder: sectionOrder,
    cursorStart: cursorStart,
    moveCursor: moveCursor,
    normalizeState: normalizeState,
    validateScheduleFields: validateScheduleFields,
    isManualOverride: isManualOverride,
    commitResponse: commitResponse
  };
}
