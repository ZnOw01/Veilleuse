// Kept free of Qt globals so the state contract can be exercised with Node.

var SECTION_ORDER = ['nightLight', 'brightness', 'temperature', 'gamma', 'schedule'];
var FIELD_COUNTS = [2, 2, 2, 2, 4];

var copy = {
  heroTitle: 'Luz nocturna',
  brightness: 'Brillo',
  temperature: 'Temperatura',
  gamma: 'Brillo percibido',
  schedule: 'Horario',
  save: 'Guardar cambios',
  unavailable: 'No disponible',
  notConfirmed: 'Estado no confirmado',
  enabled: 'Activada',
  disabled: 'Color natural',
  start: 'Inicio',
  end: 'Fin',
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

function moveCursor(cursor, key) {
  var section = boundedInteger(cursor && cursor.section, 0, SECTION_ORDER.length - 1);
  var field = boundedInteger(cursor && cursor.field, 0, FIELD_COUNTS[section === null ? 0 : section] - 1);
  if (section === null) section = 0;
  if (field === null) field = 0;

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

function normalizeSchedule(schedule) {
  var source = schedule || {};
  var start = validTime(source.start);
  var end = validTime(source.end);
  if (start !== null && start === end) {
    start = null;
    end = null;
  }
  return {
    start: start,
    end: end,
    temperature: validNumber(source.temperature, 2500, 5000)
  };
}

function normalizeState(raw) {
  var source = raw || {};
  var brightnessSource = source.brightness && typeof source.brightness === 'object' ? source.brightness : {};
  var nightSource = source.nightlight && typeof source.nightlight === 'object' ? source.nightlight : {};
  var scheduleSource = source.schedule && typeof source.schedule === 'object' ? source.schedule : {};
  var brightness = validNumber(brightnessSource.percent !== undefined ? brightnessSource.percent : source.brightness, 1, 100);
  var temperature = validNumber(nightSource.temperature !== undefined ? nightSource.temperature : source.temperature, 2500, 6500);
  var gamma = validNumber(nightSource.gamma !== undefined ? nightSource.gamma : source.gamma, 0, 100);
  var available = (brightnessSource.available !== undefined ? brightnessSource.available === true : source.available === true)
    && (nightSource.available !== undefined ? nightSource.available === true : source.available === true)
    && brightness !== null && temperature !== null && gamma !== null;
  return {
    available: available,
    enabled: available && (nightSource.enabled !== undefined ? nightSource.enabled === true : source.enabled === true),
    brightness: available ? brightness : null,
    temperature: available ? temperature : null,
    gamma: available ? gamma : null,
    schedule: normalizeSchedule({
      start: scheduleSource.day_time !== undefined ? scheduleSource.day_time : scheduleSource.start,
      end: scheduleSource.night_time !== undefined ? scheduleSource.night_time : scheduleSource.end,
      temperature: scheduleSource.night_temp !== undefined ? scheduleSource.night_temp : scheduleSource.temperature
    }),
    error: available ? String(source.error || brightnessSource.error || nightSource.error || '') : copy.notConfirmed
  };
}

function commitResponse(previousState, response) {
  var current = normalizeState(previousState);
  var requestId = response && response.requestId;
  var latestRequestId = response && response.latestRequestId;
  var validRequestId = typeof requestId === 'number' && isFinite(requestId) && Math.floor(requestId) === requestId && requestId >= 0;
  var validLatestRequestId = typeof latestRequestId === 'number' && isFinite(latestRequestId) && Math.floor(latestRequestId) === latestRequestId && latestRequestId >= 0;
  var patch = response && response.state;
  var validPatch = patch !== null && typeof patch === 'object' && !Array.isArray(patch);
  var stateKeys = ['available', 'enabled', 'brightness', 'temperature', 'gamma', 'schedule', 'error'];
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
  for (var patchKey in patch) next[patchKey] = patch[patchKey];
  return { accepted: true, state: normalizeState(next) };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    copy: copy,
    sectionOrder: sectionOrder,
    cursorStart: cursorStart,
    moveCursor: moveCursor,
    normalizeState: normalizeState,
    commitResponse: commitResponse
  };
}
