const test = require('node:test');
const assert = require('node:assert/strict');

const UiModel = require('../UiModel.js');
const I18n = require('../I18n.js');

test('copy is the native English default and is sourced from I18n.en', () => {
  assert.equal(UiModel.copy, I18n.en);
  assert.equal(UiModel.copy.heroTitle, 'Night light');
});

test('bundled fallback copy keeps exact key parity with the I18n English dictionary', () => {
  assert.deepEqual(
    Object.keys(UiModel.DEFAULT_COPY).sort(),
    Object.keys(I18n.en).sort()
  );
  for (const key of Object.keys(UiModel.DEFAULT_COPY)) {
    assert.equal(UiModel.DEFAULT_COPY[key], I18n.en[key], `DEFAULT_COPY.${key}`);
  }
});

test('normalizeState and validateScheduleFields stay backward compatible in English', () => {
  const state = UiModel.normalizeState({
    available: true,
    enabled: true,
    brightness: { available: true, percent: 55 },
    nightlight: { available: true, enabled: true, temperature: 3500, gamma: 90 }
  });
  assert.equal(state.available, true);
  assert.equal(state.brightnessPercent, 55);
  assert.equal(state.temperature, 3500);
  assert.equal(state.gamma, 90);

  const result = UiModel.validateScheduleFields('06:00', '15:30', '6000', '', '', '3500', '', '', 'en');
  assert.deepEqual(result, { valid: true, error: '' });
});

test('copyFor() returns the locale dictionary with English as the default', () => {
  assert.equal(UiModel.copyFor('es'), I18n.es);
  assert.equal(UiModel.copyFor('en'), I18n.en);
  assert.equal(UiModel.copyFor('fr'), I18n.en);
});

test('t() delegates to the locale-aware lookup and stays pure', () => {
  assert.equal(UiModel.t('routeSettings', 'es'), 'Ajustes');
  assert.equal(UiModel.t('routeSettings', 'en'), 'Settings');
  assert.equal(UiModel.t('unknown_key', 'en'), 'unknown_key');
});

test('error codes localize to the requested locale with a safe unknown fallback', () => {
  assert.equal(UiModel.errorCodeMessage('monitor_unavailable', 'es'), I18n.es.errMonitorUnavailable);
  assert.equal(UiModel.errorCodeMessage('monitor_unavailable', 'en'), I18n.en.errMonitorUnavailable);
  assert.equal(UiModel.errorCodeMessage('no_such_code', 'en'), I18n.en.errUnknown);
});

test('localizeError maps known codes and leaves existing literals untouched', () => {
  assert.equal(UiModel.localizeError('timeout', 'en'), I18n.en.errTimeout);
  const literal = 'El monitor seleccionado no está habilitado';
  assert.equal(UiModel.localizeError(literal, 'en'), literal);
  assert.equal(UiModel.localizeError(null, 'en'), '');
});

test('routes expose the three compact views in order', () => {
  assert.deepEqual(UiModel.routeOrder(), ['home', 'automation', 'settings']);
  assert.deepEqual(UiModel.routeSections('home'), ['nightLight', 'brightness', 'temperature', 'gamma', 'monitor']);
  assert.deepEqual(UiModel.routeSections('automation'), ['scheduleToggle', 'schedule', 'snooze']);
  assert.deepEqual(UiModel.routeSections('settings'), ['locale', 'shortcut', 'shortcutActions']);
});

test('adjacentRoute rings through the views for the left/right arrows', () => {
  assert.equal(UiModel.adjacentRoute('home', 1), 'automation');
  assert.equal(UiModel.adjacentRoute('automation', 1), 'settings');
  assert.equal(UiModel.adjacentRoute('settings', 1), 'home');
  assert.equal(UiModel.adjacentRoute('home', -1), 'settings');
  assert.equal(UiModel.adjacentRoute('automation', -1), 'home');
});

test('provenance labels localize each automation origin', () => {
  assert.equal(UiModel.provenanceLabel('automatic', 'es'), 'Automática');
  assert.equal(UiModel.provenanceLabel('manual', 'en'), 'Manual');
  // "preset" only survives in persisted history; it still renders sanely.
  assert.equal(UiModel.provenanceLabel('preset', 'en'), 'Preset');
  assert.equal(UiModel.provenanceLabel('anything', 'en'), I18n.en.provenanceUnknown);
});

test('schedule display values normalize per period and drop junk fields', () => {
  assert.deepEqual(
    UiModel.scheduleDisplayValues({
      schedule_display: {
        day: { brightness: 80, gamma: 100 },
        night: { brightness: 55, gamma: 85 }
      }
    }),
    { day: { brightness: 80, gamma: 100 }, night: { brightness: 55, gamma: 85 } }
  );
  assert.deepEqual(
    UiModel.scheduleDisplayValues({ schedule_display: { day: { brightness: 70 } } }),
    { day: { brightness: 70 } }
  );
  assert.deepEqual(UiModel.scheduleDisplayValues({}), {});
  assert.deepEqual(UiModel.scheduleDisplayValues({ schedule_display: { dawn: { brightness: 5 } } }), {});
  assert.deepEqual(
    UiModel.scheduleDisplayValues({ schedule_display: { night: { brightness: 101, gamma: 85 } } }),
    { night: { gamma: 85 } }
  );
});

test('snoozeDurationSeconds composes number plus unit inside the helper window', () => {
  assert.equal(UiModel.snoozeDurationSeconds(90, 'seconds'), 90);
  assert.equal(UiModel.snoozeDurationSeconds(30, 'minutes'), 1800);
  assert.equal(UiModel.snoozeDurationSeconds(2, 'hours'), 7200);
  assert.equal(UiModel.snoozeDurationSeconds(24, 'hours'), 86400);
  // Below the 10 s floor, above the 24 h ceiling, or plain invalid.
  assert.equal(UiModel.snoozeDurationSeconds(5, 'seconds'), null);
  assert.equal(UiModel.snoozeDurationSeconds(25, 'hours'), null);
  assert.equal(UiModel.snoozeDurationSeconds(0, 'minutes'), null);
  assert.equal(UiModel.snoozeDurationSeconds(-3, 'minutes'), null);
  assert.equal(UiModel.snoozeDurationSeconds(10, 'days'), null);
  assert.equal(UiModel.snoozeDurationSeconds('abc', 'minutes'), null);
  assert.equal(UiModel.snoozeDurationSeconds(null, 'minutes'), null);
});
