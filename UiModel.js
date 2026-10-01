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
  automation: [0, 10, 11],
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

// Keep the fallback in sync with I18n.en; parity tests enforce its keys.
var DEFAULT_COPY = {
  heroTitle: 'Night light',
  brightness: 'Brightness',
  temperature: 'Temperature',
  gamma: 'Gamma (perceived brightness)',
  gammaShort: 'Gamma',
  schedule: 'Schedule',
  save: 'Save changes',
  saved: 'Changes saved',
  unavailable: 'Unavailable',
  notConfirmed: 'State not confirmed',
  enabled: 'Enabled',
  disabled: 'Natural color',
  manualOverride: 'Manual override',
  start: 'Start',
  end: 'End',
  cancel: 'Cancel',
  routeHome: 'Home',
  routeAutomation: 'Automation',
  routeSettings: 'Settings',
  provenanceAutomatic: 'Automatic',
  provenanceManual: 'Manual',
  provenancePreset: 'Preset',
  provenanceSnooze: 'Snoozed',
  provenanceUnknown: 'Unknown',
  dayPeriod: 'Day',
  nightPeriod: 'Night',
  scheduleTrack: 'Daylight window · 24 hours',
  scheduleDayTimeFormat: 'Day time must use the HH:MM format',
  scheduleNightTimeFormat: 'Night time must use the HH:MM format',
  scheduleDayNightEqual: 'Day and night times must be different',
  scheduleDayTemperatureRange: 'Day temperature must be between 5900 and 6500 K',
  scheduleNightTemperatureRange: 'Night temperature must be between 2500 and 5000 K',
  scheduleBrightnessRange: 'Brightness must be between 1 and 100%',
  scheduleGammaRange: 'Gamma must be between 0 and 100%',
  snoozeTitle: 'Snooze',
  snoozeSet: 'Snooze',
  snoozeClear: 'Cancel snooze',
  snoozeStatusActive: 'Snoozed',
  unitHours: 'Hours',
  unitMinutes: 'Minutes',
  unitSeconds: 'Seconds',
  sunset: 'Sunset',
  nightStart: 'Night start',
  quickSnooze: 'Quick snooze',
  settingsTitle: 'Settings',
  language: 'Language',
  shortcut: 'Keyboard shortcut',
  shortcutKeys: 'Keys',
  shortcutInstall: 'Install',
  shortcutRemove: 'Remove',
  spanish: 'Español',
  english: 'English',
  errHelperMissing: 'The control helper could not be started.',
  errBrightnessUnavailable: 'Brightness is currently unavailable.',
  errNightlightUnavailable: 'Night light is unavailable.',
  errMonitorUnavailable: 'The selected monitor is unavailable.',
  errScheduleInvalid: 'The configured schedule is not valid.',
  errSnoozeInvalid: 'The requested snooze is not valid.',
  errHistoryUnreadable: 'The history could not be read.',
  errSettingsWrite: 'The settings could not be saved.',
  errShortcutWrite: 'The keyboard shortcut could not be updated.',
  errUnknown: 'An unknown error occurred.',
  errInvalidValue: 'The requested value is not valid.',
  errInvalidJson: 'The saved data is not in a valid format.',
  errInvalidConfig: 'The saved configuration is not valid.',
  errInvalidState: 'The saved state is not valid.',
  errInvalidHistory: 'The saved history is not valid.',
  errReadbackFailed: 'The change could not be confirmed.',
  errBrightnessWrite: 'The monitor brightness could not be written.',
  errScheduleUnavailable: 'The configured schedule is unavailable.',
  errAutomationUnavailable: 'Automation is unavailable.',
  errScheduleFailed: 'The schedule could not be updated.',
  errStateFailed: 'The state could not be saved.',
  errUnsafePath: 'The saved data path is not safe.',
  errIoError: 'The saved data could not be read or written.',
  errNotExecutable: 'The control helper is not executable.',
  errMissingCommand: 'A required system command is missing.',
  errTimeout: 'The command timed out.',
  errBackendUnavailable: 'The control backend is unavailable.',
  errDeadline: 'The operation deadline was exceeded.',
  errCancelled: 'The operation was cancelled.',
  errSnoozeFailed: 'The snooze could not be applied.',
  errReconcileFailed: 'The schedule could not be reconciled.',
  errApplyFailed: 'The night light could not be applied.',
  errReadFailed: 'The current state could not be read.',
  errNativeFailure: 'The native operation could not be completed.',
  errScheduleConflict: 'The schedule file changed during the operation.',
  manualPersistError: 'The manual setting was applied, but the preference could not be saved; the schedule may revert it on its next cycle.',
  scheduleDisplayPersistError: 'The schedule was saved, but its brightness and gamma values could not be saved.',
  optional: 'Optional',
  monitor: 'Monitor',
  focusedMonitor: 'Focused monitor',
  working: 'Applying…',
  minutesShort: 'min',
  keyboardHints: '← →\u00A0adjust / switch\u00A0view · ↑ ↓\u00A0move · Enter\u00A0activate · Esc\u00A0close'
};

var copy = (I18n && I18n.en) ? I18n.en : DEFAULT_COPY;

// QML supplies its imported I18n namespace here; null restores the fallback.
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

// Keep transactional writes intact while allowing absolute slider values and
// read/reconcile work to yield to the newest request.
function maySupersedeOperation(operation, nextOperation) {
  var sliders = ['brightness', 'temperature', 'gamma'];
  if (sliders.indexOf(operation) !== -1)
    return sliders.indexOf(nextOperation) !== -1;
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

// Retry only an unsettled target for the operation just confirmed.
// A foreign operation clears drag intent instead of replaying it.
function reconcileDragTargets(previous, current, target, lastOperation) {
  var out = dragTargetEmpty();
  var src = target && typeof target === 'object' ? target : {};
  var requests = [];
  for (var i = 0; i < DRAG_SECTIONS.length; i++) {
    var section = DRAG_SECTIONS[i];
    var goal = src[section];
    if (typeof goal !== 'number' || !isFinite(goal)) continue;
    if (lastOperation !== section) continue;
    var after = confirmedValue(current, section);
    if (typeof after !== 'number') continue;
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
  if (value === null || value === undefined || typeof value === 'boolean' || (typeof value === 'string' && value.trim() === '')) return null;
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
  if (value === null || value === undefined || typeof value === 'boolean') return null;
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

// Preserve unrelated sections when a partial readback arrives. Full status
// refreshes recompute availability; normalization validates the merged values.
// Superseded writes may still report physical progress through this path.
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
  historyUnreadable: 'errHistoryUnreadable',
  settingsWrite: 'errSettingsWrite',
  shortcutWrite: 'errShortcutWrite',
  nativeFailure: 'errNativeFailure',
  // snake_case codes actually emitted by the Python helper, mapped to the
  // same localized dictionaries so no emitted code degrades to errUnknown.
  helper_unavailable: 'errHelperMissing',
  monitor_unavailable: 'errMonitorUnavailable',
  invalid_argument: 'errInvalidValue',
  invalid_value: 'errInvalidValue',
  invalid_json: 'errInvalidJson',
  invalid_schema: 'errInvalidConfig',
  invalid_config: 'errInvalidConfig',
  invalid_state: 'errInvalidState',
  invalid_history: 'errInvalidHistory',
  brightness_readback_failed: 'errReadbackFailed',
  temperature_readback_failed: 'errReadbackFailed',
  gamma_readback_failed: 'errReadbackFailed',
  brightness_write_failed: 'errBrightnessWrite',
  schedule_unavailable: 'errScheduleUnavailable',
  schedule_invalid: 'errScheduleInvalid',
  schedule_failed: 'errScheduleFailed',
  state_unavailable: 'errStateFailed',
  state_failed: 'errStateFailed',
  unsafe_path: 'errUnsafePath',
  io_error: 'errIoError',
  not_executable: 'errNotExecutable',
  missing_command: 'errMissingCommand',
  timeout: 'errTimeout',
  backend_unavailable: 'errBackendUnavailable',
  shortcut_failed: 'errShortcutWrite',
  deadline: 'errDeadline',
  cancelled: 'errCancelled',
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

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    copy: copy,
    DEFAULT_COPY: DEFAULT_COPY,
    ERROR_CODE_KEYS: ERROR_CODE_KEYS,
    setI18n: setI18n,
    routeSections: routeSections,
    cursorStart: cursorStart,
    cursorAtControl: cursorAtControl,
    moveCursor: moveCursor,
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
    calculateScheduleDuration: calculateScheduleDuration,
    scheduleTrackSegments: scheduleTrackSegments,
    parseShortcutTokens: parseShortcutTokens,
    shortcutCommandKeys: shortcutCommandKeys
  };
}
