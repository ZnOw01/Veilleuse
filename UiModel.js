// Kept free of Qt globals so the state contract can be exercised with Node.

var ROUTES = ['home', 'automation', 'settings'];

// Up/Down move between sections; Left/Right adjust sliders or switch routes.
// Focused editors handle their own keys.
var ROUTE_SECTIONS = {
  home: ['nightLight', 'brightness', 'temperature', 'gamma', 'monitor'],
  automation: ['scheduleToggle', 'schedule', 'snooze'],
  settings: ['locale', 'shortcut', 'shortcutActions']
};

var CONTROL_FIELD_LIMITS = {
  home: [0, 0, 0, 0, 0],
  automation: [0, 10, 9],
  settings: [0, 0, 2]
};

var DRAG_SECTIONS = ['brightness', 'temperature', 'gamma'];

// Keyboard steps for the Left/Right arrows on a slider section: temperature
// moves by the same 50 K grain as the schedule editor, brightness and gamma
// by one point per press.
var KEYBOARD_STEPS = {
  brightness: 1,
  temperature: 50,
  gamma: 1
};

// Node loads I18n through CommonJS; QML injects it from Component.onCompleted.
// The English fallback keeps lookups valid before that injection.
var I18n = null;
if (typeof module !== 'undefined' && module.exports) {
  I18n = require('./I18n.js');
}

var DEFAULT_COPY = {
  notConfirmed: 'State not confirmed',
  errUnknown: 'An unknown error occurred.'
};

var copy = (I18n && I18n.en) ? I18n.en : DEFAULT_COPY;

function setI18n(lib) {
  I18n = lib || null;
  copy = I18n && I18n.en ? I18n.en : DEFAULT_COPY;
}


function routeSections(route) {
  return (ROUTE_SECTIONS[route] || ROUTE_SECTIONS.home).slice();
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

function moveCursor(cursor, key, route) {
  var names = routeSections(route);
  var section = boundedInteger(cursor && cursor.section, 0, names.length - 1);
  if (section === null) section = 0;
  if (key === 'ArrowDown') section = Math.min(names.length - 1, section + 1);
  if (key === 'ArrowUp') section = Math.max(0, section - 1);
  return { section: section, field: 0 };
}

function cursorAtControl(cursor, section, field, route) {
  var names = routeSections(route);
  var sectionIndex = boundedInteger(section, 0, names.length - 1);
  var fieldLimit = CONTROL_FIELD_LIMITS[route] && CONTROL_FIELD_LIMITS[route][sectionIndex] !== undefined
    ? CONTROL_FIELD_LIMITS[route][sectionIndex]
    : 0;
  var fieldIndex = boundedInteger(field, 0, fieldLimit);
  if (sectionIndex === null || fieldIndex === null) return cursorStart();
  return { section: sectionIndex, field: fieldIndex };
}

function moveCursorHorizontally(cursor, direction, route, options) {
  var names = routeSections(route);
  var section = boundedInteger(cursor && cursor.section, 0, names.length - 1);
  if (section === null) return null;
  var limits = CONTROL_FIELD_LIMITS[route];
  var maxField = limits && limits[section] !== undefined ? limits[section] : 0;
  if (route === 'automation' && section === 2 && !(options && options.snoozeActive === true))
    maxField = Math.min(maxField, 8);
  if (maxField <= 0) return null;
  var step = direction < 0 ? -1 : 1;
  var currentField = boundedInteger(cursor && cursor.field, 0, maxField);
  if (currentField === null) currentField = 0;
  if (route === 'settings' && section === 2 && currentField === 0) currentField = 1;
  if (currentField === 0) {
    return step > 0 ? { section: section, field: 1 } : null;
  }
  var nextField = currentField + step;
  if (nextField < 1 || nextField > maxField) return null;
  return { section: section, field: nextField };
}

// Wrap at the ends so either arrow can reach every route.
function adjacentRoute(route, direction) {
  var index = ROUTES.indexOf(route);
  if (index === -1) index = 0;
  var next = (index + (direction < 0 ? -1 : 1) + ROUTES.length) % ROUTES.length;
  return ROUTES[next];
}

function isSliderSection(section) {
  return DRAG_SECTIONS.indexOf(section) !== -1;
}

// Keep transactional writes intact while allowing same-section slider values
// and read/reconcile work to yield to the newest request.
function maySupersedeOperation(operation, nextOperation) {
  if (isSliderSection(operation))
    return operation === nextOperation;
  return ['status', 'schedule-status', 'reconcile', 'schedule-reconcile'].indexOf(operation) !== -1;
}

function shouldRetryScheduleReconcile(operation) {
  return ['status', 'schedule-status', 'reconcile'].indexOf(operation) !== -1;
}

// Next value for a keyboard step on a slider section, clamped to the
// section range. Returns null when the section is not a slider.
function stepSliderValue(section, direction, current) {
  var range = SECTION_RANGES[section];
  var step = KEYBOARD_STEPS[section];
  if (!range || !step) return null;
  var number = Number(current);
  if (current === null || current === undefined || current === "" || !isFinite(number))
    number = range.min;
  return boundedInteger(number + (direction < 0 ? -step : step), range.min, range.max);
}

var SECTION_RANGES = {
  brightness: { min: 1, max: 100 },
  temperature: { min: 2500, max: 6500 },
  gamma: { min: 0, max: 100 }
};

// Readback tolerances mirroring the helper's confirmation windows: a target
// the physical register reached within tolerance is done, not chased.
var SECTION_TOLERANCE = {
  brightness: 1,
  temperature: 50,
  gamma: 1
};

// Keep the latest pointer target visible until the hardware confirms it.
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

// Retry unsettled slider targets while slider mutations are active.
// A non-slider operation clears drag intent instead of replaying it.
function reconcileDragTargets(current, target, lastOperation) {
  var out = dragTargetEmpty();
  var src = target && typeof target === 'object' ? target : {};
  var requests = [];
  if (!isSliderSection(lastOperation))
    return { target: out, requests: requests };
  for (var i = 0; i < DRAG_SECTIONS.length; i++) {
    var section = DRAG_SECTIONS[i];
    var goal = src[section];
    if (typeof goal !== 'number' || !isFinite(goal)) continue;
    var after = confirmedValue(current, section);
    if (typeof after !== 'number') {
      if (lastOperation !== section) {
        out[section] = goal;
        requests.push({ section: section, value: goal });
      }
      continue;
    }
    if (Math.abs(after - goal) <= SECTION_TOLERANCE[section]) continue;
    out[section] = goal;
    requests.push({ section: section, value: goal });
  }
  return { target: out, requests: requests };
}

function validTime(value) {
  return typeof value === 'string' && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value) ? value : null;
}

function validNumber(value, minimum, maximum) {
  if ((typeof value !== 'number' && typeof value !== 'string') || (typeof value === 'string' && value.trim() === '')) return null;
  var number = Number(value);
  return isFinite(number) && number >= minimum && number <= maximum ? Math.round(number) : null;
}

function normalizeBrightness(source, root) {
  var raw = source && typeof source === 'object' ? source : {};
  var percentValue = raw.percent !== undefined ? raw.percent : (typeof source === 'number' ? source : root.brightness);
  var percent = validNumber(percentValue, 1, 100);
  var advertised = raw.available !== undefined ? raw.available === true : root.available === true;
  var result = {
    available: advertised && percent !== null,
    percent: advertised && percent !== null ? percent : null,
    monitor: raw.monitor ? String(raw.monitor) : null,
    error: raw.error ? String(raw.error) : null
  };
  if (typeof raw.error_code === 'string' && raw.error_code !== '') result.error_code = raw.error_code;
  return result;
}

function normalizeNightlight(source, root) {
  var raw = source && typeof source === 'object' ? source : {};
  var temperatureValue = raw.temperature !== undefined ? raw.temperature : root.temperature;
  var gammaValue = raw.gamma !== undefined ? raw.gamma : root.gamma;
  var temperature = validNumber(temperatureValue, 2500, 6500);
  var gamma = validNumber(gammaValue, 0, 100);
  var advertised = raw.available !== undefined ? raw.available === true : root.available === true;
  var enabled = raw.enabled !== undefined ? raw.enabled === true : root.enabled === true;
  var result = {
    available: advertised && temperature !== null && gamma !== null,
    enabled: advertised && temperature !== null && gamma !== null && enabled,
    identity: raw.identity === true || raw.identity === false ? raw.identity : null,
    temperature: advertised && temperature !== null ? temperature : null,
    gamma: advertised && gamma !== null ? gamma : null,
    error: raw.error ? String(raw.error) : null
  };
  if (typeof raw.error_code === 'string' && raw.error_code !== '') result.error_code = raw.error_code;
  return result;
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
  available = available && dayTime !== null && nightTime !== null
    && nightTemperature !== null && (dayTemperature !== null || raw.day_identity === true);
  if (dayTime !== null && dayTime === nightTime) {
    dayTime = null;
    nightTime = null;
    available = false;
  }
  var period = raw.period === 'day' || raw.period === 'night' ? raw.period : null;
  var result = {
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
  if (typeof raw.error_code === 'string' && raw.error_code !== '') result.error_code = raw.error_code;
  return result;
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
    enabled: nightlight.available && nightlight.enabled,
    brightness: brightness,
    brightnessPercent: brightness.percent,
    temperature: nightlight.temperature,
    gamma: nightlight.gamma,
    nightlight: nightlight,
    schedule: schedule,
    error: String(source.error || brightness.error || nightlight.error || (available ? '' : copy.notConfirmed))
  };
}

// Scheduled display values per period, as persisted by veilleuse-control.
// Periods without scheduled values are simply absent.
function scheduleDisplayValues(automation) {
  var display = automation && typeof automation === 'object' && automation.schedule_display
    ? automation.schedule_display : {};
  var out = {};
  var periods = ['day', 'night'];
  for (var i = 0; i < periods.length; i++) {
    var period = periods[i];
    var values = display[period] && typeof display[period] === 'object' ? display[period] : null;
    if (!values) continue;
    var entry = {};
    if (validNumber(values.brightness, 1, 100) !== null) entry.brightness = validNumber(values.brightness, 1, 100);
    if (validNumber(values.gamma, 0, 100) !== null) entry.gamma = validNumber(values.gamma, 0, 100);
    if (Object.keys(entry).length > 0) out[period] = entry;
  }
  return out;
}

function validateScheduleFields(start, end, dayTemperature, dayBrightness, dayGamma,
                                nightTemperature, nightBrightness, nightGamma, locale) {
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
  // Empty display fields omit that setting from the saved schedule.
  if (dayBrightness !== null && dayBrightness !== '' && validNumber(dayBrightness, 1, 100) === null)
    return { valid: false, error: t('scheduleBrightnessRange', locale) };
  if (dayGamma !== null && dayGamma !== '' && validNumber(dayGamma, 0, 100) === null)
    return { valid: false, error: t('scheduleGammaRange', locale) };
  if (nightBrightness !== null && nightBrightness !== '' && validNumber(nightBrightness, 1, 100) === null)
    return { valid: false, error: t('scheduleBrightnessRange', locale) };
  if (nightGamma !== null && nightGamma !== '' && validNumber(nightGamma, 0, 100) === null)
    return { valid: false, error: t('scheduleGammaRange', locale) };
  return { valid: true, error: '' };
}

// Compose the snooze duration the panel sends: a number plus one of the
// hour/minute/second units, converted to whole seconds inside the helper's
// 10 s .. 24 h window. Returns null when the input cannot compose.
function snoozeDurationSeconds(value, unit) {
  if (typeof value !== 'number' && typeof value !== 'string') return null;
  var number = Number(value);
  if (!isFinite(number) || number <= 0) return null;
  var factor = unit === 'hours' ? 3600 : (unit === 'minutes' ? 60 : (unit === 'seconds' ? 1 : null));
  if (factor === null) return null;
  var seconds = Math.round(number * factor);
  if (seconds < 10 || seconds > 86400) return null;
  return seconds;
}

function formatSnoozeRemaining(seconds, locale) {
  if (seconds === null || seconds === undefined || !isFinite(seconds) || seconds <= 0)
    return '';
  var mins = Math.max(1, Math.ceil(seconds / 60));
  var minUnit = t('minutesShort', locale);
  if (mins < 60)
    return mins + ' ' + minUnit;
  var hours = Math.floor(mins / 60);
  var remMins = mins % 60;
  return hours + 'h' + (remMins > 0 ? ' ' + remMins + 'm' : '');
}

function mergeStatePatch(previous, patch) {
  var current = normalizeState(previous);
  var validPatch = patch !== null && typeof patch === 'object' && !Array.isArray(patch) ? patch : {};
  var brightnessSkipped = validPatch.brightness && typeof validPatch.brightness === 'object'
    && !Array.isArray(validPatch.brightness) && validPatch.brightness.skipped === true;
  var next = {};
  for (var key in current) next[key] = current[key];
  var fullStatus = !brightnessSkipped
    && Object.prototype.hasOwnProperty.call(validPatch, 'brightness')
    && Object.prototype.hasOwnProperty.call(validPatch, 'nightlight');
  if (fullStatus) {
    delete next.available;
    delete next.error;
  }
  for (var patchKey in validPatch) {
    if (patchKey === 'brightness' && brightnessSkipped) {
      continue;
    } else if ((patchKey === 'brightness' || patchKey === 'nightlight' || patchKey === 'schedule')
        && Array.isArray(validPatch[patchKey])) {
      next[patchKey] = { available: false };
    } else if ((patchKey === 'brightness' || patchKey === 'nightlight' || patchKey === 'schedule')
        && validPatch[patchKey] && typeof validPatch[patchKey] === 'object'
        && current[patchKey] && typeof current[patchKey] === 'object') {
      next[patchKey] = {};
      for (var currentNestedKey in current[patchKey]) next[patchKey][currentNestedKey] = current[patchKey][currentNestedKey];
      for (var patchNestedKey in validPatch[patchKey]) next[patchKey][patchNestedKey] = validPatch[patchKey][patchNestedKey];
    } else {
      next[patchKey] = validPatch[patchKey];
    }
  }
  if (brightnessSkipped) {
    delete next.available;
    if (next.error === copy.notConfirmed) delete next.error;
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

var STATE_KEYS = ['available', 'enabled', 'brightness', 'brightnessPercent', 'temperature', 'gamma', 'nightlight', 'schedule', 'error'];

function commitResponse(previousState, response) {
  var current = normalizeState(previousState);
  var requestId = response && response.requestId;
  var latestRequestId = response && response.latestRequestId;
  var validRequestId = typeof requestId === 'number' && isFinite(requestId) && Math.floor(requestId) === requestId && requestId >= 0;
  var validLatestRequestId = typeof latestRequestId === 'number' && isFinite(latestRequestId) && Math.floor(latestRequestId) === latestRequestId && latestRequestId >= 0;
  var patch = response && response.state;
  var validPatch = patch !== null && typeof patch === 'object' && !Array.isArray(patch);
  var hasStateField = false;
  if (validPatch) {
    for (var stateKeyIndex = 0; stateKeyIndex < STATE_KEYS.length; stateKeyIndex++) {
      if (Object.prototype.hasOwnProperty.call(patch, STATE_KEYS[stateKeyIndex])) {
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

var ERROR_CODE_KEYS = {
  helperMissing: 'errHelperMissing',
  brightnessUnavailable: 'errBrightnessUnavailable',
  nightlightUnavailable: 'errNightlightUnavailable',
  monitorUnavailable: 'errMonitorUnavailable',
  scheduleInvalid: 'errScheduleInvalid',
  snoozeInvalid: 'errSnoozeInvalid',
  shortcutWrite: 'errShortcutWrite',
  nativeFailure: 'errNativeFailure',
  helper_unavailable: 'errHelperMissing',
  monitor_unavailable: 'errMonitorUnavailable',
  invalid_argument: 'errInvalidValue',
  invalid_value: 'errInvalidValue',
  invalid_json: 'errInvalidJson',
  invalid_schema: 'errInvalidConfig',
  invalid_state: 'errInvalidState',
  invalid_history: 'errInvalidHistory',
  brightness_readback_failed: 'errReadbackFailed',
  temperature_readback_failed: 'errReadbackFailed',
  gamma_readback_failed: 'errReadbackFailed',
  brightness_write_failed: 'errBrightnessWrite',
  schedule_unavailable: 'errScheduleUnavailable',
  schedule_invalid: 'errScheduleInvalid',
  schedule_failed: 'errScheduleFailed',
  schedule_disabled: 'errScheduleDisabled',
  state_unavailable: 'errStateFailed',
  state_failed: 'errStateFailed',
  unsafe_path: 'errUnsafePath',
  io_error: 'errIoError',
  not_executable: 'errNotExecutable',
  missing_command: 'errMissingCommand',
  timeout: 'errTimeout',
  backend_unavailable: 'errBackendUnavailable',
  shortcut_failed: 'errShortcutWrite',
  snooze_failed: 'errSnoozeFailed',
  reconcile_failed: 'errReconcileFailed',
  apply_failed: 'errApplyFailed',
  read_failed: 'errReadFailed',
  conflict: 'errScheduleConflict',
  missing_config: 'errScheduleConflict',
  malformed_config: 'errScheduleConflict',
  ambiguous_config: 'errScheduleConflict',
  rollback_failed: 'errScheduleConflict',
  malformed_state: 'errScheduleConflict',
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
// the model's English "not confirmed" fallback maps to the active locale, and
// every other literal passes through verbatim.
function localizeStateError(error, locale) {
  var text = error ? String(error) : '';
  if (text === copy.notConfirmed) return t('notConfirmed', locale);
  return localizeError(text, locale);
}

function routeOrder() {
  return ROUTES.slice();
}

function calculateScheduleDuration(startTime, endTime) {
  var start = validTime(startTime);
  var end = validTime(endTime);
  if (!start || !end || start === end) {
    return {
      valid: false,
      dayMinutes: 0,
      nightMinutes: 0,
      dayDuration: '',
      nightDuration: '',
      dayFormatted: '',
      nightFormatted: ''
    };
  }

  var sParts = start.split(':');
  var eParts = end.split(':');
  var sMin = parseInt(sParts[0], 10) * 60 + parseInt(sParts[1], 10);
  var eMin = parseInt(eParts[0], 10) * 60 + parseInt(eParts[1], 10);

  var dayMin = (eMin >= sMin) ? (eMin - sMin) : (1440 - sMin + eMin);
  var nightMin = 1440 - dayMin;

  function fmt(mins) {
    var h = Math.floor(mins / 60);
    var m = mins % 60;
    if (h > 0 && m > 0) return h + 'h ' + m + 'm';
    if (h > 0) return h + 'h';
    return m + 'm';
  }

  var dFmt = fmt(dayMin);
  var nFmt = fmt(nightMin);

  return {
    valid: true,
    dayMinutes: dayMin,
    nightMinutes: nightMin,
    dayDuration: dFmt,
    nightDuration: nFmt,
    dayFormatted: dFmt,
    nightFormatted: nFmt
  };
}

// Return daylight intervals as fractions of a normalized 24-hour track.
// An overnight day window wraps midnight and therefore uses two segments.
function scheduleTrackSegments(startTime, endTime) {
  var start = validTime(startTime);
  var end = validTime(endTime);
  if (!start || !end || start === end) return [];
  var startParts = start.split(':');
  var endParts = end.split(':');
  var from = (parseInt(startParts[0], 10) * 60 + parseInt(startParts[1], 10)) / 1440;
  var to = (parseInt(endParts[0], 10) * 60 + parseInt(endParts[1], 10)) / 1440;
  if (to > from) return [{ from: from, to: to }];
  return [{ from: 0, to: to }, { from: from, to: 1 }];
}

function parseShortcutTokens(shortcutStr) {
  var s = String(shortcutStr || '').trim();
  if (!s) return [];
  var parts = s.split(/[\s+,]+/).filter(function(p) { return p.length > 0; });
  return parts.map(function(p) { return p.toUpperCase(); });
}

// The panel displays MOD+KEY chips; the CLI owns validation of MODS, KEY.
function shortcutCommandKeys(value) {
  var spec = String(value || '');
  if (spec.indexOf(',') !== -1 || /[\r\n]/.test(spec) || spec.indexOf('+') === -1)
    return spec;
  var parts = spec.split('+').map(function(part) { return part.trim(); });
  if (parts.some(function(part) { return part === ''; })) return spec;
  var key = parts.pop();
  return parts.join(' ') + ', ' + key;
}

// Editing for PlainField. The panel draws its own fields instead of using a
// Qt text input, so nothing in the plugin ever reads the clipboard. `pattern`
// is the source of a one-character ASCII class such as "[0-9]".
function fieldFilter(raw, pattern, room) {
  var allowed = new RegExp('^' + pattern + '$');
  var source = String(raw === null || raw === undefined ? '' : raw);
  var limit = Math.max(0, Math.floor(Number(room) || 0));
  var clean = '';
  for (var i = 0; i < source.length && clean.length < limit; i++) {
    var code = source.charCodeAt(i);
    if (code >= 0x20 && code <= 0x7e && allowed.test(source[i])) clean += source[i];
  }
  return clean;
}

function fieldCursor(text, cursor) {
  var length = String(text || '').length;
  var position = Math.floor(Number(cursor));
  if (!isFinite(position)) position = length;
  return Math.max(0, Math.min(length, position));
}

function fieldInsert(text, cursor, raw, pattern, maximumLength) {
  var current = String(text || '');
  var at = fieldCursor(current, cursor);
  var clean = fieldFilter(raw, pattern, maximumLength - current.length);
  return { text: current.substring(0, at) + clean + current.substring(at), cursor: at + clean.length };
}

function fieldDelete(text, cursor, backward) {
  var current = String(text || '');
  var at = fieldCursor(current, cursor);
  if (backward) {
    if (at === 0) return { text: current, cursor: 0 };
    return { text: current.substring(0, at - 1) + current.substring(at), cursor: at - 1 };
  }
  return { text: current.substring(0, at) + current.substring(at + 1), cursor: at };
}

// A typed number counts only when it is a whole number inside the range.
function fieldNumber(text, minimum, maximum) {
  var source = String(text || '');
  if (!/^[0-9]+$/.test(source)) return null;
  var value = parseInt(source, 10);
  return value >= minimum && value <= maximum ? value : null;
}

// Arrow and Up/Down stepping: an unreadable draft restarts at the minimum.
function fieldStep(text, direction, minimum, maximum, step) {
  var current = /^[0-9]+$/.test(String(text || '')) ? parseInt(text, 10) : NaN;
  if (isNaN(current)) return String(minimum);
  return String(clamp(current + (direction > 0 ? step : -step), minimum, maximum));
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    ERROR_CODE_KEYS: ERROR_CODE_KEYS,
    setI18n: setI18n,
    routeSections: routeSections,
    cursorStart: cursorStart,
    cursorAtControl: cursorAtControl,
    moveCursor: moveCursor,
    moveCursorHorizontally: moveCursorHorizontally,
    adjacentRoute: adjacentRoute,
    isSliderSection: isSliderSection,
    maySupersedeOperation: maySupersedeOperation,
    shouldRetryScheduleReconcile: shouldRetryScheduleReconcile,
    stepSliderValue: stepSliderValue,
    dragTargetEmpty: dragTargetEmpty,
    dragTargetPush: dragTargetPush,
    reconcileDragTargets: reconcileDragTargets,
    normalizeState: normalizeState,
    scheduleDisplayValues: scheduleDisplayValues,
    validateScheduleFields: validateScheduleFields,
    snoozeDurationSeconds: snoozeDurationSeconds,
    formatSnoozeRemaining: formatSnoozeRemaining,
    mergeStatePatch: mergeStatePatch,
    commitResponse: commitResponse,
    t: t,
    errorCodeMessage: errorCodeMessage,
    localizeError: localizeError,
    localizeStateError: localizeStateError,
    routeOrder: routeOrder,
    calculateScheduleDuration: calculateScheduleDuration,
    scheduleTrackSegments: scheduleTrackSegments,
    parseShortcutTokens: parseShortcutTokens,
    shortcutCommandKeys: shortcutCommandKeys,
    fieldFilter: fieldFilter,
    fieldCursor: fieldCursor,
    fieldInsert: fieldInsert,
    fieldDelete: fieldDelete,
    fieldNumber: fieldNumber,
    fieldStep: fieldStep
  };
}
