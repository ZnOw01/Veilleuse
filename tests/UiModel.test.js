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

test('schedule parsing errors stay scoped to schedule without leaking into global state error', () => {
  const state = Model.normalizeState({
    available: true,
    enabled: true,
    brightness: { available: true, percent: 80, monitor: 'eDP-2', error: null },
    nightlight: { available: true, enabled: true, temperature: 4000, gamma: 100, error: null },
    schedule: { available: false, error: 'La configuración no contiene perfiles' }
  });
  assert.equal(state.available, true);
  assert.equal(state.enabled, true);
  assert.equal(state.error, '');
  assert.equal(state.schedule.available, false);
  assert.equal(state.schedule.error, 'La configuración no contiene perfiles');
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

test('validateScheduleFields returns localized error messages when requested', () => {
  const enResult = Model.validateScheduleFields('25:00', '18:00', '6000', '', '', '3500', '', '', 'en');
  assert.equal(enResult.valid, false);
  assert.equal(enResult.error, 'Day time must use the HH:MM format');

  const esResult = Model.validateScheduleFields('25:00', '18:00', '6000', '', '', '3500', '', '', 'es');
  assert.equal(esResult.valid, false);
  assert.equal(esResult.error, 'La hora diurna debe usar el formato HH:MM');
});
test('commitResponse rejects mismatched request IDs and handles error responses fail-closed', () => {
  const base = Model.normalizeState({ available: true, enabled: true });
  const rejected = Model.commitResponse(base, { requestId: 1, latestRequestId: 2, ok: true, state: { available: true } });
  assert.equal(rejected.accepted, false);

  const errCommit = Model.commitResponse(base, { requestId: 2, latestRequestId: 2, ok: false, error_code: 'service_unavailable' });
  assert.equal(errCommit.accepted, false);
  assert.deepEqual(errCommit.state, base);
});

// ============================================================================
// TIER 1: FEATURE COVERAGE (Isolated happy-path & core feature capabilities)
// ============================================================================

test('Tier 1 - F4 Modern Sliders: stepSliderValue adjusts all slider sections within range', () => {
  // Brightness: step 1, range 1..100
  assert.equal(Model.stepSliderValue('brightness', 1, 50), 51);
  assert.equal(Model.stepSliderValue('brightness', -1, 50), 49);
  // Temperature: step 50, range 2500..6500
  assert.equal(Model.stepSliderValue('temperature', 1, 4000), 4050);
  assert.equal(Model.stepSliderValue('temperature', -1, 4000), 3950);
  // Gamma: step 1, range 0..100
  assert.equal(Model.stepSliderValue('gamma', 1, 80), 81);
  assert.equal(Model.stepSliderValue('gamma', -1, 80), 79);
  // Non-slider sections return null
  assert.equal(Model.stepSliderValue('schedule', 1, 50), null);
  assert.equal(Model.stepSliderValue('nightLight', 1, 50), null);
});

test('Tier 1 - F5 Quick Snooze: snoozeDurationSeconds computes exact whole seconds for all units', () => {
  assert.equal(Model.snoozeDurationSeconds(15, 'minutes'), 900);
  assert.equal(Model.snoozeDurationSeconds(1, 'hours'), 3600);
  assert.equal(Model.snoozeDurationSeconds(4, 'hours'), 14400);
  assert.equal(Model.snoozeDurationSeconds(45, 'seconds'), 45);
  assert.equal(Model.snoozeDurationSeconds(120, 'seconds'), 120);
});

test('Tier 1 - F7 Schedule Grid: validateScheduleFields validates complete day and night schedule', () => {
  const result = Model.validateScheduleFields('07:00', '20:00', '6200', '90', '100', '3200', '60', '80', 'en');
  assert.equal(result.valid, true);
  assert.equal(result.error, '');

  const minimalResult = Model.validateScheduleFields('06:30', '18:45', '6000', '', '', '3500', '', '', 'en');
  assert.equal(minimalResult.valid, true);
  assert.equal(minimalResult.error, '');
});

test('Tier 1 - F9 Hybrid Navigation: cursorStart and moveCursor navigate through all route sections', () => {
  assert.deepEqual(Model.cursorStart(), { section: 0, field: 0 });
  const homeSections = Model.routeSections('home');
  assert.equal(homeSections.length, 5);

  let c = Model.cursorStart();
  for (let i = 1; i < homeSections.length; i++) {
    c = Model.moveCursor(c, 'ArrowDown', 'home');
    assert.equal(c.section, i);
  }
  // Up moves backward
  c = Model.moveCursor(c, 'ArrowUp', 'home');
  assert.equal(c.section, homeSections.length - 2);
});

test('Tier 1 - F10 Dual i18n & Error Resolution: errorCodeMessage resolves all major failure codes', () => {
  const testCodes = ['helper_unavailable', 'monitor_unavailable', 'invalid_config', 'timeout', 'conflict'];
  for (const code of testCodes) {
    const enMsg = Model.errorCodeMessage(code, 'en');
    const esMsg = Model.errorCodeMessage(code, 'es');
    assert.ok(typeof enMsg === 'string' && enMsg.length > 0);
    assert.ok(typeof esMsg === 'string' && esMsg.length > 0);
    assert.notEqual(enMsg, esMsg);
  }
});

test('Tier 1 - F11 Monotonic Request Bus: commitResponse accepts latest in-order response', () => {
  const prev = Model.normalizeState({
    available: true,
    enabled: false,
    brightness: { available: true, percent: 50, monitor: 'eDP-1', error: null },
    nightlight: { available: true, enabled: false, temperature: 4000, gamma: 100, error: null }
  });
  const res = Model.commitResponse(prev, {
    requestId: 10,
    latestRequestId: 10,
    ok: true,
    state: {
      enabled: true,
      nightlight: { available: true, enabled: true, temperature: 3200, gamma: 90, error: null }
    }
  });
  assert.equal(res.accepted, true);
  assert.equal(res.state.enabled, true);
  assert.equal(res.state.temperature, 3200);
  assert.equal(res.state.gamma, 90);
  assert.equal(res.state.brightnessPercent, 50); // Unchanged field preserved
});

// ============================================================================
// TIER 2: BOUNDARY & CORNER CASES (Extreme values, empty inputs, edge limits)
// ============================================================================

test('Tier 2 - F4 Sliders Boundary: stepSliderValue clamps strictly at min and max limits', () => {
  // Brightness limits [1, 100]
  assert.equal(Model.stepSliderValue('brightness', -1, 1), 1);
  assert.equal(Model.stepSliderValue('brightness', -1, 0), 1);
  assert.equal(Model.stepSliderValue('brightness', 1, 100), 100);
  assert.equal(Model.stepSliderValue('brightness', 1, 105), 100);
  // Temperature limits [2500, 6500]
  assert.equal(Model.stepSliderValue('temperature', -1, 2500), 2500);
  assert.equal(Model.stepSliderValue('temperature', -1, 2400), 2500);
  assert.equal(Model.stepSliderValue('temperature', 1, 6500), 6500);
  assert.equal(Model.stepSliderValue('temperature', 1, 6600), 6500);
  // Gamma limits [0, 100]
  assert.equal(Model.stepSliderValue('gamma', -1, 0), 0);
  assert.equal(Model.stepSliderValue('gamma', -1, -5), 0);
  assert.equal(Model.stepSliderValue('gamma', 1, 100), 100);
  assert.equal(Model.stepSliderValue('gamma', 1, 150), 100);
});

test('Tier 2 - F4 Sliders Drag Target: dragTargetPush clamps and filters corrupted values', () => {
  let target = Model.dragTargetEmpty();
  target = Model.dragTargetPush(target, 'brightness', 150);
  assert.equal(target.brightness, 100);

  target = Model.dragTargetPush(target, 'brightness', -20);
  assert.equal(target.brightness, 1);

  target = Model.dragTargetPush(target, 'temperature', 9000);
  assert.equal(target.temperature, 6500);

  target = Model.dragTargetPush(target, 'temperature', 1000);
  assert.equal(target.temperature, 2500);

  target = Model.dragTargetPush(target, 'gamma', 'invalid');
  assert.equal(target.gamma, null);

  target = Model.dragTargetPush(target, 'brightness', null);
  assert.equal(target.brightness, null);
});

test('Tier 2 - F5 Snooze Boundaries: snoozeDurationSeconds enforces [10, 86400] second window', () => {
  // Exactly at boundary
  assert.equal(Model.snoozeDurationSeconds(10, 'seconds'), 10);
  assert.equal(Model.snoozeDurationSeconds(86400, 'seconds'), 86400);
  assert.equal(Model.snoozeDurationSeconds(24, 'hours'), 86400);

  // Outside boundary
  assert.equal(Model.snoozeDurationSeconds(9, 'seconds'), null);
  assert.equal(Model.snoozeDurationSeconds(86401, 'seconds'), null);
  assert.equal(Model.snoozeDurationSeconds(24.1, 'hours'), null);
  assert.equal(Model.snoozeDurationSeconds(0, 'minutes'), null);
  assert.equal(Model.snoozeDurationSeconds(-10, 'seconds'), null);
  assert.equal(Model.snoozeDurationSeconds(Infinity, 'hours'), null);
  assert.equal(Model.snoozeDurationSeconds(NaN, 'minutes'), null);
  assert.equal(Model.snoozeDurationSeconds(true, 'seconds'), null);
});

test('Tier 2 - F7 Schedule Midnight & Time Boundaries: validateScheduleFields handles edge time formats', () => {
  // Midnight wrap-around and boundary times
  assert.equal(Model.validateScheduleFields('00:00', '23:59', '6000', '', '', '3500', '', '', 'en').valid, true);
  assert.equal(Model.validateScheduleFields('23:59', '00:00', '6000', '', '', '3500', '', '', 'en').valid, true);
  assert.equal(Model.validateScheduleFields('00:01', '23:58', '6000', '', '', '3500', '', '', 'en').valid, true);

  // Invalid hour / minute formats
  assert.equal(Model.validateScheduleFields('24:00', '12:00', '6000', '', '', '3500', '', '', 'en').valid, false);
  assert.equal(Model.validateScheduleFields('12:60', '18:00', '6000', '', '', '3500', '', '', 'en').valid, false);
  assert.equal(Model.validateScheduleFields('-01:00', '18:00', '6000', '', '', '3500', '', '', 'en').valid, false);
  assert.equal(Model.validateScheduleFields('7:00', '18:00', '6000', '', '', '3500', '', '', 'en').valid, false);
  assert.equal(Model.validateScheduleFields('', '18:00', '6000', '', '', '3500', '', '', 'en').valid, false);
  assert.equal(Model.validateScheduleFields(null, '18:00', '6000', '', '', '3500', '', '', 'en').valid, false);
});

test('Tier 2 - F7 Schedule Temperature Bounds: validateScheduleFields tests exact Kelvin limits', () => {
  // Day temp limits [5900, 6500]
  assert.equal(Model.validateScheduleFields('06:00', '18:00', '5900', '', '', '3500', '', '', 'en').valid, true);
  assert.equal(Model.validateScheduleFields('06:00', '18:00', '6500', '', '', '3500', '', '', 'en').valid, true);
  assert.equal(Model.validateScheduleFields('06:00', '18:00', '5899', '', '', '3500', '', '', 'en').valid, false);
  assert.equal(Model.validateScheduleFields('06:00', '18:00', '6501', '', '', '3500', '', '', 'en').valid, false);

  // Night temp limits [2500, 5000]
  assert.equal(Model.validateScheduleFields('06:00', '18:00', '6000', '', '', '2500', '', '', 'en').valid, true);
  assert.equal(Model.validateScheduleFields('06:00', '18:00', '6000', '', '', '5000', '', '', 'en').valid, true);
  assert.equal(Model.validateScheduleFields('06:00', '18:00', '6000', '', '', '2499', '', '', 'en').valid, false);
  assert.equal(Model.validateScheduleFields('06:00', '18:00', '6000', '', '', '5001', '', '', 'en').valid, false);
});

test('Tier 2 - F9 Navigation Boundary: moveCursor clamps at limits without wrap-around across all routes', () => {
  for (const route of ['home', 'automation', 'settings']) {
    const sections = Model.routeSections(route);
    const top = Model.moveCursor({ section: 0, field: 0 }, 'ArrowUp', route);
    assert.equal(top.section, 0);

    const bottom = Model.moveCursor({ section: sections.length - 1, field: 0 }, 'ArrowDown', route);
    assert.equal(bottom.section, sections.length - 1);

    // Invalid cursor index recovers safely to clamped range
    const overflow = Model.moveCursor({ section: 99, field: 0 }, 'ArrowUp', route);
    assert.equal(overflow.section, sections.length - 2);

    const underflow = Model.moveCursor({ section: -5, field: 0 }, 'ArrowDown', route);
    assert.equal(underflow.section, 1);
  }
});

test('Tier 2 - F11 Drag Reconciliation: reconcileDragTargets respects tolerance windows', () => {
  const current = Model.normalizeState({
    available: true,
    brightness: { available: true, percent: 50, monitor: 'eDP-1' },
    nightlight: { available: true, enabled: true, temperature: 3500, gamma: 90 }
  });

  // Goal within tolerance is cleared (brightness tol: 1, temp tol: 50, gamma tol: 1)
  const exactBright = Model.reconcileDragTargets(null, current, { brightness: 51, temperature: null, gamma: null }, 'brightness');
  assert.equal(exactBright.target.brightness, null);
  assert.equal(exactBright.requests.length, 0);

  const exactTemp = Model.reconcileDragTargets(null, current, { brightness: null, temperature: 3540, gamma: null }, 'temperature');
  assert.equal(exactTemp.target.temperature, null);
  assert.equal(exactTemp.requests.length, 0);

  // Goal outside tolerance survives and generates chase request
  const farBright = Model.reconcileDragTargets(null, current, { brightness: 75, temperature: null, gamma: null }, 'brightness');
  assert.equal(farBright.target.brightness, 75);
  assert.deepEqual(farBright.requests, [{ section: 'brightness', value: 75 }]);

  const farTemp = Model.reconcileDragTargets(null, current, { brightness: null, temperature: 4200, gamma: null }, 'temperature');
  assert.equal(farTemp.target.temperature, 4200);
  assert.deepEqual(farTemp.requests, [{ section: 'temperature', value: 4200 }]);
});

// ============================================================================
// TIER 3: CROSS-FEATURE COMBINATIONS (Pairwise Interaction Stability)
// ============================================================================

test('Tier 3 - Pairwise 1: Slider Drag (F4) + Monotonic Request Bus (F11) - Debounce & Stale Merge', () => {
  const initial = Model.normalizeState({
    available: true,
    brightness: { available: true, percent: 30, monitor: 'eDP-1' },
    nightlight: { available: true, enabled: true, temperature: 3500, gamma: 100 }
  });

  // User drags brightness to 70 (req 1) then to 85 (req 2)
  let drag = Model.dragTargetPush(Model.dragTargetEmpty(), 'brightness', 70);
  drag = Model.dragTargetPush(drag, 'brightness', 85);
  assert.equal(drag.brightness, 85);

  // Readback for req 1 arrives late (requestId: 1, latestRequestId: 2) with brightness: 70
  const staleResponse = {
    requestId: 1,
    latestRequestId: 2,
    ok: true,
    state: { brightness: { available: true, percent: 70, monitor: 'eDP-1' } }
  };
  const commit = Model.commitResponse(initial, staleResponse);
  assert.equal(commit.accepted, false); // Stale commit rejected

  // Panel adopts physical progress via mergeStatePatch
  const merged = Model.mergeStatePatch(initial, staleResponse.state);
  assert.equal(merged.brightnessPercent, 70);

  // Reconcile against newest drag target (85) still produces chase request
  const reconciled = Model.reconcileDragTargets(initial, merged, drag, 'brightness');
  assert.equal(reconciled.target.brightness, 85);
  assert.deepEqual(reconciled.requests, [{ section: 'brightness', value: 85 }]);
});

test('Tier 3 - Pairwise 2: Quick Snooze (F5) + Bar Widget Tooltip & Provenance (F2)', () => {
  const activeSnoozeState = Model.normalizeState({
    available: true,
    enabled: false,
    nightlight: { available: true, enabled: false, temperature: 6500, gamma: 100 }
  });
  activeSnoozeState.automation = {
    snoozed: true,
    snooze_until: Date.now() / 1000 + 1800,
    origin: 'snooze'
  };

  assert.equal(Model.provenanceLabel(activeSnoozeState.automation.origin, 'en'), 'Snoozed');
  assert.equal(Model.provenanceLabel(activeSnoozeState.automation.origin, 'es'), 'Posposición');
});

test('Tier 3 - Pairwise 3: Schedule Grid (F7) + Hero Switch & Sunset Auto-Engagement (F3)', () => {
  const dayState = Model.normalizeState({
    available: true,
    enabled: false,
    brightness: { available: true, percent: 80, monitor: 'eDP-1', error: null },
    nightlight: { available: true, enabled: false, identity: true, temperature: 6500, gamma: 100, error: null },
    schedule: { available: true, day_time: '07:00', day_temp: 6500, night_time: '19:00', night_temp: 3200, day_identity: true, period: 'day', error: null }
  });
  assert.equal(Model.isManualOverride(dayState), false);

  // Night transition occurs
  const nightState = Model.mergeStatePatch(dayState, {
    enabled: true,
    nightlight: { available: true, enabled: true, identity: false, temperature: 3200, gamma: 100, error: null },
    schedule: { available: true, day_time: '07:00', day_temp: 6500, night_time: '19:00', night_temp: 3200, day_identity: true, period: 'night', error: null }
  });
  assert.equal(nightState.enabled, true);
  assert.equal(nightState.temperature, 3200);
  assert.equal(Model.isManualOverride(nightState), false);
});

test('Tier 3 - Pairwise 4: Locale Switch (F8, F10) + Schedule Field Validation Messages (F7)', () => {
  const invalidDayTime = '99:99';
  const enRes = Model.validateScheduleFields(invalidDayTime, '19:00', '6000', '', '', '3500', '', '', 'en');
  const esRes = Model.validateScheduleFields(invalidDayTime, '19:00', '6000', '', '', '3500', '', '', 'es');

  assert.equal(enRes.valid, false);
  assert.equal(esRes.valid, false);
  assert.equal(enRes.error, I18n.en.scheduleDayTimeFormat);
  assert.equal(esRes.error, I18n.es.scheduleDayTimeFormat);
  assert.notEqual(enRes.error, esRes.error);
});

test('Tier 3 - Pairwise 5: Route Cross-Fade Transitions (F6) + Cursor Navigation State (F9)', () => {
  let route = 'home';
  let cursor = Model.cursorStart();
  cursor = Model.moveCursor(cursor, 'ArrowDown', route);
  cursor = Model.moveCursor(cursor, 'ArrowDown', route);
  assert.equal(cursor.section, 2);

  // Transition to automation
  route = Model.adjacentRoute(route, 1);
  assert.equal(route, 'automation');
  cursor = Model.cursorStart(); // Reset cursor on route change
  assert.deepEqual(cursor, { section: 0, field: 0 });

  // Transition to settings
  route = Model.adjacentRoute(route, 1);
  assert.equal(route, 'settings');
  cursor = Model.cursorStart();
  assert.deepEqual(cursor, { section: 0, field: 0 });
});

test('Tier 3 - Pairwise 6: Multi-Monitor Selection (F8) + Brightness Slider Mutation (F4, F11)', () => {
  const rawState = {
    brightness: { available: true, percent: 60, monitor: 'DP-2', error: null },
    nightlight: { available: true, enabled: true, temperature: 4000, gamma: 100, error: null }
  };
  const normalized = Model.normalizeState(rawState);
  assert.equal(normalized.brightness.monitor, 'DP-2');
  assert.equal(normalized.brightness.percent, 60);

  // Patching brightness for specific monitor preserves nightlight state
  const updated = Model.mergeStatePatch(normalized, {
    brightness: { available: true, percent: 80, monitor: 'DP-2', error: null }
  });
  assert.equal(updated.brightness.percent, 80);
  assert.equal(updated.brightness.monitor, 'DP-2');
  assert.equal(updated.temperature, 4000);
});

test('Tier 3 - Pairwise 7: Active Snooze (F5) + Manual Hero Toggle (F3, F11)', () => {
  const snoozed = Model.normalizeState({
    available: true,
    enabled: false,
    brightness: { available: true, percent: 50, monitor: 'eDP-1', error: null },
    nightlight: { available: true, enabled: false, temperature: 6500, gamma: 100, error: null }
  });
  snoozed.automation = { snoozed: true, snooze_until: Date.now() / 1000 + 3600, origin: 'snooze', manual_override: null };

  // User manually toggles night light ON during snooze
  const toggled = Model.mergeStatePatch(snoozed, {
    enabled: true,
    nightlight: { available: true, enabled: true, temperature: 3500, gamma: 100 }
  });
  toggled.automation = { snoozed: false, snooze_until: null, origin: 'manual', manual_override: true };
  assert.equal(toggled.enabled, true);
  assert.equal(toggled.automation.snoozed, false);
  assert.equal(toggled.automation.manual_override, true);
  assert.equal(Model.isManualOverride(toggled), true);
});


test('Tier 3 - Pairwise 8: Keyboard Stepping (F9) + Drag Target Reconcile (F4, F11)', () => {
  const base = Model.normalizeState({
    available: true,
    brightness: { available: true, percent: 50, monitor: 'eDP-1' },
    nightlight: { available: true, enabled: true, temperature: 3500, gamma: 100 }
  });

  const nextVal = Model.stepSliderValue('temperature', 1, base.temperature);
  assert.equal(nextVal, 3550);

  const drag = Model.dragTargetPush(Model.dragTargetEmpty(), 'temperature', nextVal);
  assert.equal(drag.temperature, 3550);

  const res = Model.reconcileDragTargets(base, base, drag, 'temperature');
  // Tolerance is 50 K; diff is exactly 50 K so it is within tolerance and considered settled
  assert.equal(res.target.temperature, null);

  // Stepping by 200 K
  const farDrag = Model.dragTargetPush(Model.dragTargetEmpty(), 'temperature', 3800);
  const farRes = Model.reconcileDragTargets(base, base, farDrag, 'temperature');
  assert.equal(farRes.target.temperature, 3800);
  assert.deepEqual(farRes.requests, [{ section: 'temperature', value: 3800 }]);
});

test('Tier 3 - Pairwise 9: Schedule Toggle (F7) + Provenance Labeling (F2, F10)', () => {
  assert.equal(Model.provenanceLabel('automatic', 'en'), 'Automatic');
  assert.equal(Model.provenanceLabel('manual', 'en'), 'Manual');
  assert.equal(Model.provenanceLabel('snooze', 'es'), 'Posposición');
  assert.equal(Model.provenanceLabel('unknown', 'es'), 'Desconocido');
});

test('Tier 3 - Pairwise 10: Error Code Dispatch (F10) + State Error Recovery (F11)', () => {
  const prev = Model.normalizeState({ available: true, enabled: true });
  const failedResponse = {
    requestId: 5,
    latestRequestId: 5,
    ok: false,
    error: 'state_failed',
    state: null
  };
  const committed = Model.commitResponse(prev, failedResponse);
  assert.equal(committed.accepted, false);
  assert.deepEqual(committed.state, prev);

  const localizedEn = Model.localizeError('state_failed', 'en');
  const localizedEs = Model.localizeError('state_failed', 'es');
  assert.equal(localizedEn, I18n.en.errStateFailed);
  assert.equal(localizedEs, I18n.es.errStateFailed);
});

test('Tier 3 - Pairwise 11: Stale Response Merge (F11) + Multi-Slider Value Coherence (F4)', () => {
  const state = Model.normalizeState({
    available: true,
    brightness: { available: true, percent: 40, monitor: 'eDP-1' },
    nightlight: { available: true, enabled: true, temperature: 3000, gamma: 90 }
  });

  // Stale patch updating temperature only
  const patched = Model.mergeStatePatch(state, {
    nightlight: { available: true, enabled: true, temperature: 3400, gamma: 90 }
  });
  assert.equal(patched.temperature, 3400);
  assert.equal(patched.brightnessPercent, 40); // Brightness untouched
  assert.equal(patched.gamma, 90); // Gamma untouched
});

test('Tier 3 - Pairwise 12: Snooze Duration Composition (F5) + Keyboard Return Activation (F9)', () => {
  // Composed valid duration produces valid integer
  const validSecs = Model.snoozeDurationSeconds(45, 'minutes');
  assert.equal(validSecs, 2700);

  // Invalid composed duration returns null, preventing invalid command generation
  const invalidSecs = Model.snoozeDurationSeconds(-5, 'minutes');
  assert.equal(invalidSecs, null);
});

// ============================================================================
// TIER 4: REAL-WORLD APPLICATION SCENARIOS
// ============================================================================

test('Tier 4 - Scenario 1: Evening Sunset Ramp & Night Light Auto-Engagement', () => {
  // 1. Initial daytime state (14:00)
  let appState = Model.normalizeState({
    available: true,
    enabled: false,
    brightness: { available: true, percent: 100, monitor: 'eDP-1', error: null },
    nightlight: { available: true, enabled: false, identity: true, temperature: 6500, gamma: 100, error: null },
    schedule: {
      available: true,
      day_time: '07:00',
      day_temp: 6500,
      night_time: '19:30',
      night_temp: 3200,
      day_identity: true,
      period: 'day',
      error: null
    }
  });
  appState.automation = { schedule_enabled: true, origin: 'automatic', snoozed: false };
  assert.equal(appState.enabled, false);
  assert.equal(appState.schedule.period, 'day');
  assert.equal(Model.isManualOverride(appState), false);

  // 2. Sunset reconciliation event triggers at 19:30
  const sunsetPatch = {
    enabled: true,
    nightlight: { available: true, enabled: true, identity: false, temperature: 3200, gamma: 100, error: null },
    schedule: {
      available: true,
      day_time: '07:00',
      day_temp: 6500,
      night_time: '19:30',
      night_temp: 3200,
      day_identity: true,
      period: 'night',
      error: null
    },
    automation: { schedule_enabled: true, origin: 'automatic', snoozed: false }
  };
  const commit = Model.commitResponse(appState, { requestId: 1, latestRequestId: 1, ok: true, state: sunsetPatch });
  assert.equal(commit.accepted, true);
  appState = commit.state;

  // 3. Verify night light is active at 3200K without manual override
  assert.equal(appState.enabled, true);
  assert.equal(appState.temperature, 3200);
  assert.equal(appState.schedule.period, 'night');
  assert.equal(Model.isManualOverride(appState), false);
});

test('Tier 4 - Scenario 2: Quick Snooze during Nighttime Task & Resumption', () => {
  // 1. Active night state (3200K)
  let appState = Model.normalizeState({
    available: true,
    enabled: true,
    brightness: { available: true, percent: 100, monitor: 'eDP-1', error: null },
    nightlight: { available: true, enabled: true, identity: false, temperature: 3200, gamma: 100, error: null },
    schedule: { available: true, day_time: '07:00', day_temp: 6500, night_time: '19:30', night_temp: 3200, period: 'night' }
  });
  appState.automation = { schedule_enabled: true, origin: 'automatic', snoozed: false };

  // 2. User sets 30 min snooze
  const snoozeSecs = Model.snoozeDurationSeconds(30, 'minutes');
  assert.equal(snoozeSecs, 1800);

  const snoozePatch = {
    enabled: false,
    nightlight: { available: true, enabled: false, identity: true, temperature: 6500, gamma: 100, error: null }
  };
  const snoozeCommit = Model.commitResponse(appState, { requestId: 2, latestRequestId: 2, ok: true, state: snoozePatch });
  assert.equal(snoozeCommit.accepted, true);
  appState = snoozeCommit.state;
  appState.automation = { schedule_enabled: true, snoozed: true, snooze_until: Date.now() / 1000 + 1800, origin: 'snooze' };

  // 3. Verify natural color identity and snooze provenance
  assert.equal(appState.enabled, false);
  assert.equal(appState.automation.snoozed, true);
  assert.equal(Model.provenanceLabel(appState.automation.origin, 'en'), 'Snoozed');

  // 4. User clears snooze early
  const clearPatch = {
    enabled: true,
    nightlight: { available: true, enabled: true, identity: false, temperature: 3200, gamma: 100, error: null }
  };
  const clearCommit = Model.commitResponse(appState, { requestId: 3, latestRequestId: 3, ok: true, state: clearPatch });
  assert.equal(clearCommit.accepted, true);
  appState = clearCommit.state;
  appState.automation = { schedule_enabled: true, snoozed: false, snooze_until: null, origin: 'automatic' };

  // 5. Scheduled night temperature restored
  assert.equal(appState.enabled, true);
  assert.equal(appState.temperature, 3200);
  assert.equal(appState.automation.snoozed, false);
});


test('Tier 4 - Scenario 3: Rapid Multi-Monitor Brightness & Temperature Adjustment', () => {
  let state = Model.normalizeState({
    available: true,
    brightness: { available: true, percent: 50, monitor: 'DP-1', error: null },
    nightlight: { available: true, enabled: true, temperature: 4000, gamma: 100, error: null }
  });

  // User drags brightness rapidly: 50 -> 60 -> 75 -> 80
  let reqId = 10;
  for (const targetBrightness of [60, 75, 80]) {
    reqId++;
    const dragTarget = Model.dragTargetPush(Model.dragTargetEmpty(), 'brightness', targetBrightness);
    assert.equal(dragTarget.brightness, targetBrightness);
  }

  // Response for 80 arrives with latestRequestId = 13
  const finalResponse = {
    requestId: 13,
    latestRequestId: 13,
    ok: true,
    state: { brightness: { available: true, percent: 80, monitor: 'DP-1', error: null } }
  };
  const commit = Model.commitResponse(state, finalResponse);
  assert.equal(commit.accepted, true);
  assert.equal(commit.state.brightnessPercent, 80);
});

test('Tier 4 - Scenario 4: Full Hybrid Keyboard Walkthrough across All 3 Routes', () => {
  let route = 'home';
  let cursor = Model.cursorStart();

  // Walk Home route sections
  const homeSections = Model.routeSections(route);
  for (let i = 0; i < homeSections.length - 1; i++) {
    cursor = Model.moveCursor(cursor, 'ArrowDown', route);
  }
  assert.equal(cursor.section, homeSections.length - 1);

  // Switch to Automation
  route = Model.adjacentRoute(route, 1);
  assert.equal(route, 'automation');
  cursor = Model.cursorStart();

  // Validate schedule inputs on Automation route
  const schedValid = Model.validateScheduleFields('06:30', '21:00', '6000', '100', '100', '3000', '50', '80', 'en');
  assert.equal(schedValid.valid, true);

  // Switch to Settings
  route = Model.adjacentRoute(route, 1);
  assert.equal(route, 'settings');
  cursor = Model.cursorStart();
  assert.deepEqual(cursor, { section: 0, field: 0 });

  // Switch back to Home (ring complete)
  route = Model.adjacentRoute(route, 1);
  assert.equal(route, 'home');
});

test('Tier 4 - Scenario 5: Dual-Locale Switching & Error Toast Handling', () => {
  const errorKey = 'errMonitorUnavailable';

  // In English
  const enToast = I18n.t(errorKey, 'en');
  assert.equal(enToast, 'The selected monitor is unavailable.');

  // Live switch to Spanish
  const esToast = I18n.t(errorKey, 'es');
  assert.equal(esToast, 'El monitor seleccionado no está disponible.');

  // Error cleared
  assert.equal(Model.localizeError('', 'en'), '');
  assert.equal(Model.localizeError('', 'es'), '');
});

// ============================================================================
// TIER 5: ADVERSARIAL COVERAGE HARDENING (Fuzzing, Malformed Payloads, Safety)
// ============================================================================

test('Tier 5 - Adversarial: Prototype pollution and deep property corruption safety in normalizeState', () => {
  const malicious = JSON.parse('{"__proto__": {"polluted": true}, "brightness": {"percent": "__proto__"}, "nightlight": null}');
  const normalized = Model.normalizeState(malicious);
  assert.equal(normalized.available, false);
  assert.equal(Object.prototype.polluted, undefined);
});

test('Tier 5 - Adversarial: Fuzzing validateScheduleFields with arbitrary inputs', () => {
  const fuzzInputs = [
    [undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined],
    [{}, [], () => {}, true, false, Symbol('test'), 123, null],
    ['00:00:00', '24:00', '99999999999999', '', '', '-500', '', ''],
    ['\u0000', '\n\r', 'NaN', 'Infinity', '-Infinity', '0x10', 'null', 'undefined']
  ];
  for (const input of fuzzInputs) {
    const res = Model.validateScheduleFields(...input, 'en');
    assert.equal(typeof res.valid, 'boolean');
    assert.equal(typeof res.error, 'string');
  }
});

test('Tier 5 - Adversarial: Monotonic Request Bus randomized arrival fuzzing', () => {
  const base = Model.normalizeState({ available: true, enabled: false });
  const responses = [
    { requestId: 1, latestRequestId: 5, ok: true, state: { enabled: true } },
    { requestId: 3, latestRequestId: 5, ok: true, state: { enabled: true } },
    { requestId: 5, latestRequestId: 5, ok: true, state: { enabled: true } },
    { requestId: 4, latestRequestId: 5, ok: true, state: { enabled: true } },
    { requestId: 2, latestRequestId: 5, ok: true, state: { enabled: true } }
  ];

  let acceptedCount = 0;
  for (const res of responses) {
    const result = Model.commitResponse(base, res);
    if (result.accepted) acceptedCount++;
  }
  // Only the exactly matching request ID (5) must be accepted
  assert.equal(acceptedCount, 1);
});

test('Tier 1 - F7 Schedule Duration Calculation: calculateScheduleDuration accurately computes daylight and night windows', () => {
  // Standard daytime window: 06:00 to 18:00 (12h day, 12h night)
  const standard = Model.calculateScheduleDuration('06:00', '18:00');
  assert.equal(standard.valid, true);
  assert.equal(standard.dayMinutes, 720);
  assert.equal(standard.nightMinutes, 720);
  assert.equal(standard.dayFormatted, '12h');
  assert.equal(standard.nightFormatted, '12h');

  // Unequal window: 07:30 to 19:45 (12h 15m day, 11h 45m night)
  const unequal = Model.calculateScheduleDuration('07:30', '19:45');
  assert.equal(unequal.valid, true);
  assert.equal(unequal.dayMinutes, 735);
  assert.equal(unequal.nightMinutes, 705);
  assert.equal(unequal.dayFormatted, '12h 15m');
  assert.equal(unequal.nightFormatted, '11h 45m');

  // Midnight wrap: 22:00 to 06:00 (8h day, 16h night)
  const wrap = Model.calculateScheduleDuration('22:00', '06:00');
  assert.equal(wrap.valid, true);
  assert.equal(wrap.dayMinutes, 480);
  assert.equal(wrap.nightMinutes, 960);
  assert.equal(wrap.dayFormatted, '8h');
  assert.equal(wrap.nightFormatted, '16h');

  // Short minute-only duration: 06:00 to 06:45 (45m day, 23h 15m night)
  const shortDur = Model.calculateScheduleDuration('06:00', '06:45');
  assert.equal(shortDur.valid, true);
  assert.equal(shortDur.dayFormatted, '45m');
  assert.equal(shortDur.nightFormatted, '23h 15m');
});

test('Tier 2 - F7 Schedule Duration Boundaries: calculateScheduleDuration handles equal or invalid times safely', () => {
  // Equal times are invalid (zero duration)
  const equalTimes = Model.calculateScheduleDuration('06:00', '06:00');
  assert.equal(equalTimes.valid, false);
  assert.equal(equalTimes.dayMinutes, 0);
  assert.equal(equalTimes.nightMinutes, 0);
  assert.equal(equalTimes.dayFormatted, '');
  assert.equal(equalTimes.nightFormatted, '');

  // Invalid formats return invalid object
  assert.equal(Model.calculateScheduleDuration('25:00', '18:00').valid, false);
  assert.equal(Model.calculateScheduleDuration('06:00', '18:60').valid, false);
  assert.equal(Model.calculateScheduleDuration(null, '18:00').valid, false);
  assert.equal(Model.calculateScheduleDuration('06:00', '').valid, false);
  assert.equal(Model.calculateScheduleDuration(undefined, undefined).valid, false);
});

test('Tier 1 - F8 Shortcut Tokenizer: parseShortcutTokens splits keys into uppercase tokens', () => {
  assert.deepEqual(Model.parseShortcutTokens('SUPER+SHIFT+N'), ['SUPER', 'SHIFT', 'N']);
  assert.deepEqual(Model.parseShortcutTokens('ctrl + alt + f5'), ['CTRL', 'ALT', 'F5']);
  assert.deepEqual(Model.parseShortcutTokens('Mod4,Mod1,Return'), ['MOD4', 'MOD1', 'RETURN']);
  assert.deepEqual(Model.parseShortcutTokens('XF86MonBrightnessUp'), ['XF86MONBRIGHTNESSUP']);
});

test('Tier 2 - F8 Shortcut Tokenizer Boundaries: parseShortcutTokens handles whitespace, empty, or special inputs', () => {
  assert.deepEqual(Model.parseShortcutTokens(''), []);
  assert.deepEqual(Model.parseShortcutTokens('   '), []);
  assert.deepEqual(Model.parseShortcutTokens(null), []);
  assert.deepEqual(Model.parseShortcutTokens(undefined), []);
  assert.deepEqual(Model.parseShortcutTokens('++  + ,'), []);
});
