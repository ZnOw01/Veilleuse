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

test('superseding respects active slider writes while preserving slider latest-wins', () => {
  for (const operation of ['schedule', 'schedule-toggle', 'shortcut', 'snooze', 'toggle']) {
    assert.equal(Model.maySupersedeOperation(operation, 'brightness'), false, operation);
  }
  for (const operation of ['status', 'schedule-status', 'reconcile', 'schedule-reconcile']) {
    assert.equal(Model.maySupersedeOperation(operation, 'status'), true, operation);
  }
  for (const slider of ['brightness', 'temperature', 'gamma']) {
    assert.equal(Model.maySupersedeOperation(slider, 'status'), false, `${slider} -> status`);
    for (const nextSlider of ['brightness', 'temperature', 'gamma'])
      assert.equal(Model.maySupersedeOperation(slider, nextSlider), true, `${slider} -> ${nextSlider}`);
  }
  assert.equal(Model.maySupersedeOperation('future-mutation', 'status'), false);
});

test('a superseded schedule reconcile retries after reads but yields to manual actions', () => {
  for (const operation of ['status', 'schedule-status', 'reconcile']) {
    assert.equal(Model.shouldRetryScheduleReconcile(operation), true, operation);
  }
  for (const operation of ['brightness', 'temperature', 'gamma', 'schedule', 'shortcut', 'future-mutation']) {
    assert.equal(Model.shouldRetryScheduleReconcile(operation), false, operation);
  }
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

test('rejects structured numeric readings instead of coercing JSON arrays', () => {
  for (const value of [[50], [], {}, [null]]) {
    const state = Model.normalizeState({
      brightness: { available: true, percent: value },
      nightlight: { available: true, temperature: [3500], gamma: value }
    });
    assert.equal(state.brightness.available, false);
    assert.equal(state.brightness.percent, null);
    assert.equal(state.nightlight.available, false);
    assert.equal(state.temperature, null);
    assert.equal(state.gamma, null);
    assert.deepEqual(Model.scheduleDisplayValues({ schedule_display: { day: { brightness: value, gamma: value } } }), {});
  }
});

test('malformed section arrays invalidate only the affected control on readback', () => {
  const previous = Model.normalizeState({
    brightness: { available: true, percent: 50 },
    nightlight: { available: true, enabled: true, temperature: 3500, gamma: 100 }
  });
  for (const section of ['brightness', 'nightlight']) {
    const result = Model.commitResponse(previous, {
      requestId: 1, latestRequestId: 1, ok: true, state: { [section]: [] }
    });
    assert.equal(result.state[section].available, false);
    const unaffected = section === 'brightness' ? 'nightlight' : 'brightness';
    assert.equal(result.state[unaffected].available, true);
  }
});

test('snooze duration rejects structured values but accepts numeric text from editors', () => {
  for (const value of [[30], [], {}, [null]])
    assert.equal(Model.snoozeDurationSeconds(value, 'minutes'), null);
  assert.equal(Model.snoozeDurationSeconds('30', 'minutes'), 1800);
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

test('normalizes stable error codes for each status section', () => {
  const state = Model.normalizeState({
    brightness: { available: false, error: 'driver busy', error_code: 'brightness_readback_failed' },
    nightlight: { available: false, error: 'hyprsunset not running', error_code: 'backend_unavailable' },
    schedule: { available: false, error: 'malformed profile', error_code: 'schedule_invalid' }
  });
  assert.equal(state.brightness.error_code, 'brightness_readback_failed');
  assert.equal(state.nightlight.error_code, 'backend_unavailable');
  assert.equal(state.schedule.error_code, 'schedule_invalid');
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
  assert.equal(Model.t('heroTitle', 'en'), 'Night light');
  assert.equal(Model.t('brightness', 'en'), 'Brightness');
  assert.equal(Model.t('temperature', 'en'), 'Temperature');
  assert.equal(Model.t('gamma', 'en'), 'Gamma (perceived brightness)');
  assert.equal(Model.t('schedule', 'en'), 'Schedule');
  assert.equal(Model.t('save', 'en'), 'Save changes');
  assert.equal(Model.t('unavailable', 'en'), 'Unavailable');
  assert.equal(Model.t('disabled', 'en'), 'Natural color');
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

test('keeps each control ready when an unrelated backend section is unavailable', () => {
  const state = Model.normalizeState({
    brightness: { available: false, percent: null, monitor: 'DP-1', error: 'monitor unavailable' },
    nightlight: { available: true, enabled: true, identity: false, temperature: 3500, gamma: 90 },
    schedule: { available: true, day_time: '06:00', day_temp: 6000, night_time: '18:00', night_temp: 3500 }
  });
  assert.equal(state.available, false);
  assert.equal(state.brightness.available, false);
  assert.equal(state.nightlight.available, true);
  assert.equal(state.enabled, true);
  assert.equal(state.temperature, 3500);
  assert.equal(state.gamma, 90);
  assert.equal(state.schedule.available, true);
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
  const current = physicalState({ brightness: 50 });
  const result = Model.reconcileDragTargets(
    current,
    Model.dragTargetPush(Model.dragTargetEmpty(), 'brightness', 70),
    'brightness'
  );
  assert.deepEqual(result.target, { brightness: 70, temperature: null, gamma: null });
  assert.deepEqual(result.requests, [{ section: 'brightness', value: 70 }]);
});

test('reconcileDragTargets clears a target the readback reached within tolerance', () => {
  const current = physicalState({ brightness: 69 });
  const result = Model.reconcileDragTargets(
    current,
    Model.dragTargetPush(Model.dragTargetEmpty(), 'brightness', 70),
    'brightness'
  );
  assert.deepEqual(result.target, Model.dragTargetEmpty());
  assert.deepEqual(result.requests, []);
});

test('reconcileDragTargets drops drag intent on a foreign readback', () => {
  const current = physicalState({ brightness: 50 });
  const result = Model.reconcileDragTargets(
    current,
    Model.dragTargetPush(Model.dragTargetEmpty(), 'brightness', 70),
    'status'
  );
  assert.deepEqual(result.target, Model.dragTargetEmpty());
  assert.deepEqual(result.requests, []);
});

test('reconcileDragTargets keeps a temperature target inside the 50 K tolerance window', () => {
  const current = physicalState({ temperature: 3540 });
  const result = Model.reconcileDragTargets(
    current,
    Model.dragTargetPush(Model.dragTargetEmpty(), 'temperature', 3550),
    'temperature'
  );
  assert.deepEqual(result.target, Model.dragTargetEmpty());
  const far = Model.reconcileDragTargets(
    physicalState({ temperature: 3540 }),
    Model.dragTargetPush(Model.dragTargetEmpty(), 'temperature', 4000),
    'temperature'
  );
  assert.deepEqual(far.target, { brightness: null, temperature: 4000, gamma: null });
});

test('every mapped error-code key exists in I18n dictionaries', () => {
  const codeKeys = Object.values(Model.ERROR_CODE_KEYS);
  assert.ok(codeKeys.length >= 30, `expected >= 30 mapped codes, got ${codeKeys.length}`);
  for (const key of new Set(codeKeys)) {
    assert.ok(typeof I18n.en[key] === 'string' && I18n.en[key] !== '', `en missing ${key}`);
    assert.ok(typeof I18n.es[key] === 'string' && I18n.es[key] !== '', `es missing ${key}`);
  }
  Model.setI18n(null);
  try {
    assert.equal(Model.t('notConfirmed'), 'State not confirmed');
    assert.equal(Model.errorCodeMessage('unknown_code'), 'An unknown error occurred.');
  } finally {
    Model.setI18n(I18n);
  }
  assert.equal(Model.t('save', 'es'), 'Guardar cambios');
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
  const testCodes = ['helper_unavailable', 'monitor_unavailable', 'invalid_state', 'timeout', 'conflict'];
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

test('cursorAtControl preserves the hovered control field and clamps by route section', () => {
  assert.deepEqual(Model.cursorAtControl(Model.cursorStart(), 1, 10, 'automation'), { section: 1, field: 10 });
  assert.deepEqual(Model.cursorAtControl(Model.cursorStart(), 2, 99, 'automation'), { section: 2, field: 9 });
  assert.deepEqual(Model.cursorAtControl(Model.cursorStart(), 2, 2, 'settings'), { section: 2, field: 2 });
  assert.deepEqual(Model.cursorAtControl(Model.cursorStart(), 0, 4, 'home'), { section: 0, field: 0 });
});

test('reconcileDragTargets respects tolerance windows', () => {
  const current = Model.normalizeState({
    available: true,
    brightness: { available: true, percent: 50, monitor: 'eDP-1' },
    nightlight: { available: true, enabled: true, temperature: 3500, gamma: 90 }
  });

  const exactBright = Model.reconcileDragTargets(current, { brightness: 51, temperature: null, gamma: null }, 'brightness');
  assert.equal(exactBright.target.brightness, null);
  assert.equal(exactBright.requests.length, 0);

  const exactTemp = Model.reconcileDragTargets(current, { brightness: null, temperature: 3540, gamma: null }, 'temperature');
  assert.equal(exactTemp.target.temperature, null);
  assert.equal(exactTemp.requests.length, 0);

  const farBright = Model.reconcileDragTargets(current, { brightness: 75, temperature: null, gamma: null }, 'brightness');
  assert.equal(farBright.target.brightness, 75);
  assert.deepEqual(farBright.requests, [{ section: 'brightness', value: 75 }]);

  const farTemp = Model.reconcileDragTargets(current, { brightness: null, temperature: 4200, gamma: null }, 'temperature');
  assert.equal(farTemp.target.temperature, 4200);
  assert.deepEqual(farTemp.requests, [{ section: 'temperature', value: 4200 }]);
});

test('formatSnoozeRemaining formats minutes and hours locally', () => {
  assert.equal(Model.formatSnoozeRemaining(0, 'en'), '');
  assert.equal(Model.formatSnoozeRemaining(90, 'en'), '2 min');
  assert.equal(Model.formatSnoozeRemaining(5400, 'es'), '1h 30m');
});

test('Prototype pollution and deep property corruption safety in normalizeState', () => {
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

test('scheduleTrackSegments maps daytime and midnight-wrapping windows onto a 24-hour track', () => {
  assert.deepEqual(Model.scheduleTrackSegments('06:00', '18:00'), [{ from: 0.25, to: 0.75 }]);
  assert.deepEqual(Model.scheduleTrackSegments('22:00', '06:00'), [
    { from: 0, to: 0.25 },
    { from: 22 / 24, to: 1 }
  ]);
  assert.deepEqual(Model.scheduleTrackSegments('06:00', '06:00'), []);
  assert.deepEqual(Model.scheduleTrackSegments('25:00', '06:00'), []);
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

test('schedule readiness rejects incomplete advertised schedules', () => {
  for (const patch of [{ day_time: null }, { night_time: '25:00' }, { day_temp: null }, { night_temp: false }]) {
    const state = Model.normalizeState({ schedule: {
      available: true, day_time: '06:00', night_time: '18:00', day_temp: 6000, night_temp: 3500, ...patch
    } });
    assert.equal(state.schedule.available, false, JSON.stringify(patch));
  }
});

test('UI shortcut notation converts to the CLI format without sanitizing invalid input', () => {
  assert.equal(Model.shortcutCommandKeys('SUPER+SHIFT+N'), 'SUPER SHIFT, N');
  assert.equal(Model.shortcutCommandKeys(' CTRL + F8 '), 'CTRL, F8');
  assert.equal(Model.shortcutCommandKeys('SUPER, V'), 'SUPER, V');
  for (const value of ['SUPER++N', 'SUPER+N\nevil()', 'SUPER+SHIFT, N'])
    assert.equal(Model.shortcutCommandKeys(value), value);
});
