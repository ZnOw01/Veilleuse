const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const Model = require('../UiModel.js');
const I18n = require('../I18n.js');

const ROOT = path.join(__dirname, '..');

// Canonical inventory of every stable error code the Python helper can emit
// into a payload the panel parses.  Kept in lockstep with the sources by the
// coverage tests below: adding a new code requires extending this list, and
// removing one requires pruning it.
const EMITTED_ERROR_CODES = [
  'helper_unavailable',
  'monitor_unavailable',
  'invalid_argument',
  'invalid_transition',
  'invalid_brightness_step',
  'invalid_value',
  'invalid_preset',
  'invalid_json',
  'invalid_schema',
  'invalid_config',
  'invalid_state',
  'invalid_history',
  'brightness_readback_failed',
  'brightness_write_failed',
  'temperature_readback_failed',
  'gamma_readback_failed',
  'readback_mismatch',
  'schedule_unavailable',
  'schedule_failed',
  'state_unavailable',
  'state_failed',
  'state_update_failed',
  'unsafe_path',
  'io_error',
  'not_executable',
  'missing_command',
  'timeout',
  'backend_unavailable',
  'preset_failed',
  'preset_not_found',
  'shortcut_failed',
  'builtin_immutable',
  'default_conflict',
  'deadline_exceeded',
  'deadline',
  'cancelled',
  'snooze_failed',
  'transition_failed',
  'reconcile_failed',
  'apply_failed',
  'read_failed',
  'native_failure',
  'native_operation_missing',
  'nightlight_failure',
  'conflict',
  'missing_config',
  'malformed_config',
  'ambiguous_config',
  'rollback_failed',
  'malformed_state',
  'history_error',
  'history_failed'
];

// Error-code literal forms recognized in the production Python sources.  A
// scan with these terms must reproduce EMITTED_ERROR_CODES exactly, so an
// unmapped code can never slip in and a stale inventory entry can never linger.
const PRODUCTION_SOURCES = [
  'scripts/veilleuse-control',
  'scripts/automation_utils.py',
  'scripts/preset_utils.py',
  'scripts/state_utils.py',
  'scripts/schedule_toggle_utils.py'
];

const CODE_PATTERNS = [
  /error_code\s*=\s*"([a-z][a-z0-9_]*)"/g,
  /"error_code"\s*:\s*"([a-z][a-z0-9_]*)"/g,
  /"error_code"\s*:\s*None if [a-z]+ else\s*"([a-z][a-z0-9_]*)"/g,
  /_failure\(\s*"([a-z][a-z0-9_]*)"/g,
  /(?:StateError|PresetError|AutomationError|_error)\(\s*"([a-z][a-z0-9_]*)"/g,
  /getattr\([^)]*"error_code",\s*"([a-z][a-z0-9_]*)"/g,
  /\.get\("error_code",\s*"([a-z][a-z0-9_]*)"/g,
  /_preflight_check\([^,]*,[^,]*,\s*"([a-z][a-z0-9_]*)"/g,
  /\["error_code"\]\s*=\s*"([a-z][a-z0-9_]*)"/g,
  /_failure_code\([^,]*,\s*"([a-z][a-z0-9_]*)"/g,
  /or\s*"([a-z][a-z0-9_]*)"[,)]/g,
  /history_error\s*=\s*"([a-z][a-z0-9_]*)"/g,
  /(?:^|\s)return\s+"([a-z][a-z0-9_]*)",/g
];

function scanEmittedCodes() {
  const found = new Set();
  for (const file of PRODUCTION_SOURCES) {
    const text = fs.readFileSync(path.join(ROOT, file), 'utf8');
    for (const pattern of CODE_PATTERNS) {
      pattern.lastIndex = 0;
      let match;
      while ((match = pattern.exec(text)) !== null) found.add(match[1]);
    }
  }
  return found;
}

test('emitted-code inventory matches the production sources exactly', () => {
  const found = scanEmittedCodes();
  assert.deepEqual(
    [...found].sort(),
    [...EMITTED_ERROR_CODES].sort(),
    'error-code inventory must cover every code the helper can emit'
  );
});

test('every emitted error code maps to a non-empty message in both locales', () => {
  for (const code of EMITTED_ERROR_CODES) {
    const es = Model.errorCodeMessage(code, 'es');
    const en = Model.errorCodeMessage(code, 'en');
    assert.ok(typeof es === 'string' && es !== '', `${code} es message must be non-empty`);
    assert.ok(typeof en === 'string' && en !== '', `${code} en message must be non-empty`);
    assert.notEqual(es, I18n.es.errUnknown, `${code} es must not degrade to errUnknown`);
    assert.notEqual(en, I18n.en.errUnknown, `${code} en must not degrade to errUnknown`);
  }
});

test('no opposite-locale leakage for any emitted error code', () => {
  for (const code of EMITTED_ERROR_CODES) {
    const es = Model.errorCodeMessage(code, 'es');
    const en = Model.errorCodeMessage(code, 'en');
    assert.notEqual(es, en, `${code} must not produce the same string in both locales`);
  }
});

test('error dictionaries are disjoint across locales (no shared literal)', () => {
  const esErrorValues = new Set();
  const enErrorValues = new Set();
  for (const key of I18n.keys()) {
    if (key.indexOf('err') === 0 || key.indexOf('schedule') === 0) {
      if (typeof I18n.es[key] === 'string') esErrorValues.add(I18n.es[key]);
      if (typeof I18n.en[key] === 'string') enErrorValues.add(I18n.en[key]);
    }
  }
  for (const esValue of esErrorValues) {
    assert.ok(
      !enErrorValues.has(esValue),
      `Spanish error value leaks into English: ${JSON.stringify(esValue)}`
    );
  }
});

test('every emitted code resolves through the shared es/en dictionary', () => {
  assert.deepEqual(Object.keys(I18n.es), Object.keys(I18n.en));
  const esValues = new Set(Object.keys(I18n.es).map((key) => I18n.es[key]));
  const enValues = new Set(Object.keys(I18n.en).map((key) => I18n.en[key]));
  for (const code of EMITTED_ERROR_CODES) {
    const es = Model.errorCodeMessage(code, 'es');
    const en = Model.errorCodeMessage(code, 'en');
    assert.ok(esValues.has(es), `${code} es message must come from the es dictionary`);
    assert.ok(enValues.has(en), `${code} en message must come from the en dictionary`);
  }
});

test('localizeError maps known codes and leaves literal diagnostics untouched', () => {
  for (const code of EMITTED_ERROR_CODES) {
    assert.equal(Model.localizeError(code, 'es'), Model.errorCodeMessage(code, 'es'));
    assert.equal(Model.localizeError(code, 'en'), Model.errorCodeMessage(code, 'en'));
  }
  const literal = 'El monitor seleccionado no está habilitado';
  assert.equal(Model.localizeError(literal, 'en'), literal);
  assert.equal(Model.localizeError('', 'en'), '');
  assert.equal(Model.localizeError(null, 'en'), '');
});

test('localizeStateError maps the not-confirmed fallback and passes literals through', () => {
  assert.equal(Model.localizeStateError('Estado no confirmado', 'es'), I18n.es.notConfirmed);
  assert.equal(Model.localizeStateError('Estado no confirmado', 'en'), I18n.en.notConfirmed);
  assert.equal(Model.localizeStateError('monitor_unavailable', 'en'), I18n.en.errMonitorUnavailable);
  const literal = 'No se pudo resolver un monitor enfocado';
  assert.equal(Model.localizeStateError(literal, 'en'), literal);
  assert.equal(Model.localizeStateError('', 'en'), '');
  assert.equal(Model.localizeStateError(null, 'en'), '');
});

test('schedule validation errors localize in English without breaking Spanish defaults', () => {
  assert.deepEqual(Model.validateScheduleFields('06:00', '06:00', true, 6000, 3500, 'es'), {
    valid: false,
    error: I18n.es.scheduleDayNightEqual
  });
  assert.deepEqual(Model.validateScheduleFields('06:00', '06:00', true, 6000, 3500, 'en'), {
    valid: false,
    error: I18n.en.scheduleDayNightEqual
  });
  assert.deepEqual(Model.validateScheduleFields('25:00', '18:00', true, 6000, 3500, 'en'), {
    valid: false,
    error: I18n.en.scheduleDayTimeFormat
  });
  assert.deepEqual(Model.validateScheduleFields('06:00', '25:00', true, 6000, 3500, 'en'), {
    valid: false,
    error: I18n.en.scheduleNightTimeFormat
  });
  assert.deepEqual(Model.validateScheduleFields('06:00', '18:00', true, 7000, 3500, 'en'), {
    valid: false,
    error: I18n.en.scheduleDayTemperatureRange
  });
  assert.deepEqual(Model.validateScheduleFields('06:00', '18:00', true, 6000, 7000, 'en'), {
    valid: false,
    error: I18n.en.scheduleNightTemperatureRange
  });
  assert.deepEqual(Model.validateScheduleFields('06:00', '18:00', true, 6000, 3500, 'en'), {
    valid: true,
    error: ''
  });
});

test('Panel localizes structured errors through the error-code mapping', () => {
  const panel = fs.readFileSync(path.join(ROOT, 'Panel.qml'), 'utf8');
  assert.match(panel, /payload\.error_code/);
  assert.match(panel, /errorCodeMessage/);
  assert.match(panel, /validateScheduleFields\([^)]*root\.locale/);
});