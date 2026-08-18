const test = require('node:test');
const assert = require('node:assert/strict');

const Model = require('../UiModel.js');
const I18n = require('../I18n.js');

test('declares per-route control sections in visual order', () => {
  assert.deepEqual(Model.routeSections('home'), ['nightLight', 'brightness', 'temperature', 'gamma', 'monitor']);
  assert.deepEqual(Model.routeSections('automation'), ['scheduleToggle', 'schedule', 'snooze']);
  assert.deepEqual(Model.routeSections('settings'), ['locale', 'shortcut', 'shortcutActions']);
});

test('ArrowUp and ArrowDown move the cursor across the route sections', () => {
  let cursor = Model.cursorStart();
  cursor = Model.moveCursor(cursor, 'ArrowDown', 'home');
  assert.deepEqual(cursor, { section: 1, field: 0 });
  cursor = Model.moveCursor(cursor, 'ArrowDown', 'home');
  cursor = Model.moveCursor(cursor, 'ArrowDown', 'home');
  assert.deepEqual(cursor, { section: 3, field: 0 });
  cursor = Model.moveCursor(cursor, 'ArrowUp', 'home');
  assert.deepEqual(cursor, { section: 2, field: 0 });
});

test('vertical movement clamps at the route boundaries without wrapping', () => {
  const top = Model.moveCursor({ section: 0, field: 0 }, 'ArrowUp', 'home');
  assert.deepEqual(top, { section: 0, field: 0 });
  const bottom = Model.moveCursor({ section: 4, field: 0 }, 'ArrowDown', 'home');
  assert.deepEqual(bottom, { section: 4, field: 0 });
});

test('adjacentRoute rings through the views for the Left/Right arrows', () => {
  assert.equal(Model.adjacentRoute('home', 1), 'automation');
  assert.equal(Model.adjacentRoute('settings', 1), 'home');
  assert.equal(Model.adjacentRoute('home', -1), 'settings');
});

test('isSliderSection owns exactly the three drag sections', () => {
  for (const section of ['brightness', 'temperature', 'gamma'])
    assert.equal(Model.isSliderSection(section), true, section);
  for (const section of ['nightLight', 'monitor', 'scheduleToggle', 'schedule', 'snooze', 'locale', 'shortcut'])
    assert.equal(Model.isSliderSection(section), false, section);
});

test('stepSliderValue moves within the section range by the keyboard step', () => {
  assert.equal(Model.stepSliderValue('brightness', 1, 41), 42);
  assert.equal(Model.stepSliderValue('brightness', -1, 1), 1);
  assert.equal(Model.stepSliderValue('brightness', 1, 100), 100);
  assert.equal(Model.stepSliderValue('temperature', 1, 3000), 3050);
  assert.equal(Model.stepSliderValue('temperature', -1, 2500), 2500);
  assert.equal(Model.stepSliderValue('temperature', 1, 6500), 6500);
  assert.equal(Model.stepSliderValue('gamma', 1, 50), 51);
  assert.equal(Model.stepSliderValue('gamma', -1, 0), 0);
  assert.equal(Model.stepSliderValue('monitor', 1, 50), null);
  assert.equal(Model.stepSliderValue('brightness', 1, null), 2);
});

test('normalizes unavailable helper data to a fail-closed state', () => {
  const state = Model.normalizeState({
    available: true,
    enabled: true,
    brightness: 150,
    temperature: 'not-a-number',
    gamma: -4,
    schedule: { start: '25:99', end: '15:30', temperature: 3000 }
  });
  assert.equal(state.available, false);
  assert.equal(state.enabled, false);
  assert.deepEqual(state.brightness, { available: false, percent: null, monitor: null, error: null });
  assert.equal(state.temperature, null);
  assert.equal(state.gamma, null);
  assert.equal(state.schedule.start, null);
  assert.equal(state.schedule.end, '15:30');
  assert.equal(state.schedule.temperature, 3000);
  assert.equal(state.error, 'State not confirmed');
});

test('rejects boolean numeric fields from malformed JSON', () => {
  const state = Model.normalizeState({
    brightness: { available: true, percent: true },
    nightlight: { available: true, temperature: 3500, gamma: true }
  });
  assert.equal(state.available, false);
  assert.deepEqual(state.brightness, { available: false, percent: null, monitor: null, error: null });
  assert.equal(state.gamma, null);
});

test('accepts only the latest successful helper response', () => {
  const state = Model.normalizeState({ available: true, enabled: false, brightness: 50, temperature: 3500, gamma: 100 });
  const stale = Model.commitResponse(state, { requestId: 3, latestRequestId: 4, ok: true, state: { enabled: true } });
  assert.equal(stale.accepted, false);
  assert.equal(stale.state.enabled, false);

  const current = Model.commitResponse(state, { requestId: 4, latestRequestId: 4, ok: true, state: { enabled: true } });
  assert.equal(current.accepted, true);
  assert.equal(current.state.enabled, true);
});

test('promotes the initial fail-closed state with a real full status payload', () => {
  const initial = Model.normalizeState({});
  const result = Model.commitResponse(initial, {
    requestId: 1,
    latestRequestId: 1,
    ok: true,
    state: {
      brightness: { available: true, percent: 42, monitor: 'eDP-2', error: null },
      nightlight: { available: true, enabled: true, identity: false, temperature: 3500, gamma: 100, error: null },
      schedule: { available: true, day_time: '06:00', day_temp: 6000, night_time: '18:00', night_temp: 3500, day_identity: true, period: 'day', error: null }
    }
  });
  assert.equal(result.accepted, true);
  assert.equal(result.state.available, true);
  assert.equal(result.state.enabled, true);
  assert.equal(result.state.error, '');
});

test('rejects helper responses without a request identity', () => {
  const state = Model.normalizeState({ available: true, enabled: false, brightness: 50, temperature: 3500, gamma: 100 });
  const result = Model.commitResponse(state, { ok: true, state: { enabled: true } });
  assert.equal(result.accepted, false);
  assert.equal(result.state.enabled, false);
});

test('rejects successful helper responses whose state is not an object', () => {
  const state = Model.normalizeState({ available: true, enabled: false, brightness: 50, temperature: 3500, gamma: 100 });
  const result = Model.commitResponse(state, { requestId: 4, latestRequestId: 4, ok: true, state: 'corrupt' });
  assert.equal(result.accepted, false);
  assert.equal(result.state.enabled, false);
});

test('rejects successful helper responses with no state fields', () => {
  const state = Model.normalizeState({ available: true, enabled: false, brightness: 50, temperature: 3500, gamma: 100 });
  const result = Model.commitResponse(state, { requestId: 4, latestRequestId: 4, ok: true, state: { ok: true } });
  assert.equal(result.accepted, false);
  assert.equal(result.state.enabled, false);
});

test('keeps native copy explicit and action-oriented', () => {
  assert.equal(Model.copy.heroTitle, 'Night light');
  assert.equal(Model.copy.brightness, 'Brightness');
  assert.equal(Model.copy.temperature, 'Temperature');
  assert.equal(Model.copy.gamma, 'Gamma (perceived brightness)');
  assert.equal(Model.copy.schedule, 'Schedule');
  assert.equal(Model.copy.save, 'Save changes');
  assert.equal(Model.copy.unavailable, 'Unavailable');
  assert.equal(Model.copy.disabled, 'Natural color');
});

test('normalizes the combined JSON emitted by veilleuse-control', () => {
  const state = Model.normalizeState({
    brightness: { available: true, percent: 42, monitor: 'eDP-2', error: null },
    nightlight: { available: true, enabled: true, identity: false, temperature: 3500, gamma: 90, error: null },
    schedule: { available: true, day_time: '07:00', day_temp: 6200, night_time: '21:00', night_temp: 3200, day_identity: false, period: 'day', error: null }
  });
  assert.equal(state.available, true);
  assert.deepEqual(state.brightness, { available: true, percent: 42, monitor: 'eDP-2', error: null });
  assert.equal(state.enabled, true);
  assert.equal(state.temperature, 3500);
  assert.equal(state.gamma, 90);
  assert.deepEqual(state.schedule, {
    available: true,
    day_time: '07:00',
    day_temp: 6200,
    night_time: '21:00',
    night_temp: 3200,
    day_identity: false,
    period: 'day',
    start: '07:00',
    end: '21:00',
    temperature: 3200,
    error: null
  });
});

test('fails closed when schedule boundaries are equal', () => {
  const state = Model.normalizeState({
    available: true,
    brightness: 50,
    temperature: 3500,
    gamma: 90,
    schedule: { start: '06:00', end: '06:00', temperature: 3200 }
  });
  assert.equal(state.schedule.start, null);
  assert.equal(state.schedule.end, null);
  assert.equal(state.schedule.temperature, 3200);
  assert.equal(state.schedule.available, false);
});

test('keeps a numeric day profile and its 5900..6500 temperature', () => {
  const state = Model.normalizeState({
    brightness: { available: true, percent: 50, monitor: 'DP-1' },
    nightlight: { available: true, enabled: false, identity: true, temperature: 6000, gamma: 100 },
    schedule: { available: true, day_time: '06:00', day_temp: 5900, night_time: '18:00', night_temp: 5000, day_identity: false, period: 'night' }
  });
  assert.equal(state.schedule.day_temp, 5900);
  assert.equal(state.schedule.night_temp, 5000);
  assert.equal(state.schedule.day_identity, false);
  assert.equal(state.schedule.period, 'night');
});

test('reports a specific local error when schedule times are equal', () => {
  assert.equal(typeof Model.validateScheduleFields, 'function');
  if (typeof Model.validateScheduleFields !== 'function') return;
  assert.deepEqual(Model.validateScheduleFields('06:00', '06:00', '6000', '', '', '3500', '', '', 'es'), {
    valid: false,
    error: 'Las horas de día y noche deben ser diferentes'
  });
});

test('schedule display drafts are optional and validated when present', () => {
  assert.deepEqual(Model.validateScheduleFields('06:00', '15:30', '6000', '', '', '3500', '', '', 'en'), {
    valid: true,
    error: ''
  });
  assert.deepEqual(Model.validateScheduleFields('06:00', '15:30', '6000', '80', '100', '3500', '55', '85', 'en'), {
    valid: true,
    error: ''
  });
  assert.equal(
    Model.validateScheduleFields('06:00', '15:30', '6000', '101', '', '3500', '', '', 'en').error,
    I18n.en.scheduleBrightnessRange
  );
  assert.equal(
    Model.validateScheduleFields('06:00', '15:30', '6000', '', '101', '3500', '', '', 'en').error,
    I18n.en.scheduleGammaRange
  );
  assert.equal(
    Model.validateScheduleFields('06:00', '15:30', '6000', '', '', '3500', '0', '', 'en').error,
    I18n.en.scheduleBrightnessRange
  );
});

test('detects a manual override only when real light state contradicts schedule period', () => {
  assert.equal(typeof Model.isManualOverride, 'function');
  if (typeof Model.isManualOverride !== 'function') return;
  const scheduledDay = Model.normalizeState({
    brightness: { available: true, percent: 50, monitor: 'DP-1' },
    nightlight: { available: true, enabled: true, identity: false, temperature: 3500, gamma: 100 },
    schedule: { available: true, day_time: '06:00', day_temp: 6000, night_time: '18:00', night_temp: 3500, day_identity: true, period: 'day' }
  });
  const scheduledNight = Model.commitResponse(scheduledDay, {
    requestId: 1,
    latestRequestId: 1,
    ok: true,
    state: { enabled: false, schedule: { period: 'night' } }
  }).state;
  assert.equal(Model.isManualOverride(scheduledDay), true);
  assert.equal(Model.isManualOverride(scheduledNight), true);
  assert.equal(Model.isManualOverride(Model.commitResponse(scheduledDay, {
    requestId: 2,
    latestRequestId: 2,
    ok: true,
    state: { enabled: false, schedule: { period: 'day' } }
  }).state), false);

  const numericDay = Model.normalizeState({
    brightness: { available: true, percent: 50, monitor: 'DP-1' },
    nightlight: { available: true, enabled: true, identity: false, temperature: 5900, gamma: 100 },
    schedule: { available: true, day_time: '06:00', day_temp: 5900, night_time: '18:00', night_temp: 3500, day_identity: false, period: 'day' }
  });
  assert.equal(Model.isManualOverride(numericDay), false);
  assert.equal(Model.isManualOverride(Model.commitResponse(numericDay, {
    requestId: 3,
    latestRequestId: 3,
    ok: true,
    state: { enabled: false }
  }).state), true);
});

test('isManualOverride trusts a persisted automation manual_override when present', () => {
  const scheduledDay = Model.normalizeState({
    brightness: { available: true, percent: 50, monitor: 'DP-1' },
    nightlight: { available: true, enabled: true, identity: false, temperature: 5900, gamma: 100 },
    schedule: { available: true, day_time: '06:00', day_temp: 5900, night_time: '18:00', night_temp: 3500, day_identity: false, period: 'day' }
  });
  assert.equal(Model.isManualOverride(scheduledDay), false);
  scheduledDay.automation = { manual_override: { profile: { kind: 'identity' } } };
  assert.equal(Model.isManualOverride(scheduledDay), true);

  const persistedClear = Model.normalizeState({
    available: true,
    enabled: true,
    brightness: { available: true, percent: 50, monitor: 'DP-1' },
    nightlight: { available: true, enabled: true, identity: false, temperature: 3500, gamma: 100 },
    schedule: { available: true, day_time: '06:00', day_temp: 6000, night_time: '18:00', night_temp: 3500, day_identity: true, period: 'day' }
  });
  assert.equal(Model.isManualOverride(persistedClear), true);
  persistedClear.automation = { manual_override: null };
  assert.equal(Model.isManualOverride(persistedClear), false);
});

test('dragTargetEmpty starts every drag section without an absolute target', () => {
  assert.deepEqual(Model.dragTargetEmpty(), { brightness: null, temperature: null, gamma: null });
});

test('dragTargetPush clamps the newest absolute target per section', () => {
  const first = Model.dragTargetPush(Model.dragTargetEmpty(), 'brightness', 70);
  assert.deepEqual(first, { brightness: 70, temperature: null, gamma: null });
  const second = Model.dragTargetPush(first, 'temperature', 9000);
  assert.deepEqual(second, { brightness: 70, temperature: 6500, gamma: null });
  const third = Model.dragTargetPush(second, 'brightness', 0);
  assert.deepEqual(third, { brightness: 1, temperature: 6500, gamma: null });
});

test('dragTargetPush clears a section when the intent is removed', () => {
  const target = Model.dragTargetPush(Model.dragTargetEmpty(), 'gamma', 80);
  const cleared = Model.dragTargetPush(target, 'gamma', null);
  assert.deepEqual(cleared, { brightness: null, temperature: null, gamma: null });
});

test('reconcileDragTargets keeps a same-section target until the readback tolerates it', () => {
  const previous = physicalState({ brightness: 50 });
  const current = physicalState({ brightness: 50 });
  const result = Model.reconcileDragTargets(
    previous, current,
    Model.dragTargetPush(Model.dragTargetEmpty(), 'brightness', 70),
    'brightness'
  );
  assert.deepEqual(result.target, { brightness: 70, temperature: null, gamma: null });
  assert.deepEqual(result.requests, [{ section: 'brightness', value: 70 }]);
});

test('reconcileDragTargets clears a target the readback reached within tolerance', () => {
  const previous = physicalState({ brightness: 50 });
  // One point of DDC quantization is within the helper's tolerance.
  const current = physicalState({ brightness: 69 });
  const result = Model.reconcileDragTargets(
    previous, current,
    Model.dragTargetPush(Model.dragTargetEmpty(), 'brightness', 70),
    'brightness'
  );
  assert.deepEqual(result.target, Model.dragTargetEmpty());
  assert.deepEqual(result.requests, []);
});

test('reconcileDragTargets drops drag intent on a foreign readback', () => {
  const previous = physicalState({ brightness: 50 });
  const current = physicalState({ brightness: 50 });
  const result = Model.reconcileDragTargets(
    previous, current,
    Model.dragTargetPush(Model.dragTargetEmpty(), 'brightness', 70),
    'status'
  );
  assert.deepEqual(result.target, Model.dragTargetEmpty());
  assert.deepEqual(result.requests, []);
});

test('reconcileDragTargets keeps a temperature target inside the 50 K tolerance window', () => {
  const previous = physicalState({ temperature: 3500 });
  const current = physicalState({ temperature: 3540 });
  const result = Model.reconcileDragTargets(
    previous, current,
    Model.dragTargetPush(Model.dragTargetEmpty(), 'temperature', 3550),
    'temperature'
  );
  assert.deepEqual(result.target, Model.dragTargetEmpty());
  const far = Model.reconcileDragTargets(
    current, physicalState({ temperature: 3540 }),
    Model.dragTargetPush(Model.dragTargetEmpty(), 'temperature', 4000),
    'temperature'
  );
  assert.deepEqual(far.target, { brightness: null, temperature: 4000, gamma: null });
});

test('bundled fallback copy keeps exact key parity with the I18n English dictionary', () => {
  const fallback = Model.DEFAULT_COPY;
  assert.ok(fallback && typeof fallback === 'object', 'DEFAULT_COPY must be exported for parity checks');
  assert.deepEqual(Object.keys(fallback).sort(), Object.keys(I18n.en).sort());
  for (const key of Object.keys(I18n.en))
    assert.equal(fallback[key], I18n.en[key], `fallback ${key} must copy the I18n.en value`);
});

test('every stable error-code key resolves to a real message without the I18n library wired', () => {
  const codeKeys = Object.values(Model.ERROR_CODE_KEYS);
  assert.ok(codeKeys.length >= 30, `expected >= 30 mapped codes, got ${codeKeys.length}`);
  Model.setI18n(null);
  try {
    for (const key of new Set(codeKeys)) {
      assert.ok(typeof Model.DEFAULT_COPY[key] === 'string' && Model.DEFAULT_COPY[key] !== '', `fallback copy missing ${key}`);
      assert.notEqual(Model.t(key), key, `${key} must not degrade to the raw key in the fallback`);
    }
    assert.equal(Model.errorCodeMessage('invalid_json'), 'The saved data is not in a valid format.');
    assert.equal(Model.errorCodeMessage('timeout'), 'The command timed out.');
    assert.equal(Model.validateScheduleFields('25:00', '18:00', '6000', '', '', '3500', '', '').error, 'Day time must use the HH:MM format');
    assert.equal(Model.validateScheduleFields('06:00', '18:00', '7000', '', '', '3500', '', '').error, 'Day temperature must be between 5900 and 6500 K');
    assert.equal(Model.t('manualPersistError'), Model.DEFAULT_COPY.manualPersistError);
  } finally {
    Model.setI18n(I18n);
  }
});

test('setI18n swaps the runtime locale library and restores the active copy', () => {
  assert.equal(typeof Model.setI18n, 'function');
  Model.setI18n(null);
  try {
    assert.equal(Model.t('save', 'es'), 'Save changes');
    assert.equal(Model.copyFor('es'), Model.DEFAULT_COPY);
  } finally {
    Model.setI18n(I18n);
  }
  assert.equal(Model.t('save', 'es'), 'Guardar cambios');
  assert.equal(Model.copyFor('fr'), I18n.en);
  assert.equal(Model.copy, I18n.en);
});

function physicalState(overrides) {
  const options = overrides || {};
  return Model.normalizeState({
    available: true,
    enabled: false,
    brightness: { available: true, percent: options.brightness || 50, monitor: 'eDP-2', error: null },
    nightlight: {
      available: true,
      enabled: false,
      identity: options.identity === undefined ? false : options.identity,
      temperature: options.temperature || 3500,
      gamma: options.gamma === undefined ? 100 : options.gamma,
      error: null
    },
    schedule: {
      available: true,
      day_time: '06:00',
      day_temp: 6000,
      night_time: '18:00',
      night_temp: 3500,
      day_identity: true,
      period: 'day',
      error: null
    }
  });
}

test('mergeStatePatch adopts a superseded write without dropping unrelated state', () => {
  assert.equal(typeof Model.mergeStatePatch, 'function');
  if (typeof Model.mergeStatePatch !== 'function') return;
  const merged = Model.mergeStatePatch(physicalState(), {
    brightness: { available: true, percent: 70, monitor: 'eDP-2', error: null }
  });
  assert.equal(merged.brightness.percent, 70);
  assert.equal(merged.nightlight.temperature, 3500);
  assert.equal(merged.nightlight.gamma, 100);
  assert.equal(merged.schedule.day_time, '06:00');
  assert.equal(merged.schedule.day_temp, 6000);
});

test('mergeStatePatch merges nested sections key-by-key and syncs enabled like commitResponse', () => {
  assert.equal(typeof Model.mergeStatePatch, 'function');
  if (typeof Model.mergeStatePatch !== 'function') return;
  const partial = Model.mergeStatePatch(physicalState(), {
    nightlight: { temperature: 4000 }
  });
  assert.equal(partial.nightlight.temperature, 4000);
  assert.equal(partial.nightlight.gamma, 100, 'unset nested keys keep their confirmed value');
});

test('mergeStatePatch ignores non-object patches and re-normalizes garbage values', () => {
  assert.equal(typeof Model.mergeStatePatch, 'function');
  if (typeof Model.mergeStatePatch !== 'function') return;
  const untouched = Model.mergeStatePatch(physicalState(), 'corrupt');
  assert.equal(untouched.brightness.percent, 50);
  const garbage = Model.mergeStatePatch(physicalState(), {
    brightness: { available: true, percent: 400, monitor: 'eDP-2', error: null }
  });
  assert.equal(garbage.available, false);
});

test('provenance labels localize each automation origin', () => {
  assert.equal(Model.provenanceLabel('automatic', 'es'), 'Automática');
  assert.equal(Model.provenanceLabel('manual', 'en'), 'Manual');
  // "preset" only survives in persisted history; it still renders sanely.
  assert.equal(Model.provenanceLabel('preset', 'en'), 'Preset');
  assert.equal(Model.provenanceLabel('anything', 'en'), I18n.en.provenanceUnknown);
});

test('schedule display values normalize per period and drop junk fields', () => {
  assert.deepEqual(
    Model.scheduleDisplayValues({
      schedule_display: {
        day: { brightness: 80, gamma: 100 },
        night: { brightness: 55, gamma: 85 }
      }
    }),
    { day: { brightness: 80, gamma: 100 }, night: { brightness: 55, gamma: 85 } }
  );
  assert.deepEqual(
    Model.scheduleDisplayValues({ schedule_display: { day: { brightness: 70 } } }),
    { day: { brightness: 70 } }
  );
  assert.deepEqual(Model.scheduleDisplayValues({}), {});
  assert.deepEqual(Model.scheduleDisplayValues({ schedule_display: { dawn: { brightness: 5 } } }), {});
  assert.deepEqual(
    Model.scheduleDisplayValues({ schedule_display: { night: { brightness: 101, gamma: 85 } } }),
    { night: { gamma: 85 } }
  );
});

test('snoozeDurationSeconds composes number plus unit inside the helper window', () => {
  assert.equal(Model.snoozeDurationSeconds(90, 'seconds'), 90);
  assert.equal(Model.snoozeDurationSeconds(30, 'minutes'), 1800);
  assert.equal(Model.snoozeDurationSeconds(2, 'hours'), 7200);
  assert.equal(Model.snoozeDurationSeconds(24, 'hours'), 86400);
  // Below the 10 s floor, above the 24 h ceiling, or plain invalid.
  assert.equal(Model.snoozeDurationSeconds(5, 'seconds'), null);
  assert.equal(Model.snoozeDurationSeconds(25, 'hours'), null);
  assert.equal(Model.snoozeDurationSeconds(0, 'minutes'), null);
  assert.equal(Model.snoozeDurationSeconds(-3, 'minutes'), null);
  assert.equal(Model.snoozeDurationSeconds(10, 'days'), null);
  assert.equal(Model.snoozeDurationSeconds('abc', 'minutes'), null);
  assert.equal(Model.snoozeDurationSeconds(null, 'minutes'), null);
});
