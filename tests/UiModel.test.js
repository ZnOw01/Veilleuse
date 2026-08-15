const test = require('node:test');
const assert = require('node:assert/strict');

const Model = require('../UiModel.js');
const I18n = require('../I18n.js');

test('declares per-route control sections in visual order', () => {
  assert.deepEqual(Model.routeSections('home'), ['nightLight', 'brightness', 'temperature', 'gamma']);
  assert.deepEqual(Model.routeSections('automation'), ['scheduleToggle', 'transition', 'snooze', 'schedule']);
  assert.deepEqual(Model.routeSections('settings'), ['locale', 'scope', 'preset', 'preflight', 'shortcut', 'shortcutActions']);
});

test('moves the home cursor with bounded section and field navigation', () => {
  const first = Model.cursorStart();
  assert.deepEqual(Model.moveCursor(first, 'j', 'home'), { section: 1, field: 0 });
  assert.deepEqual(Model.moveCursor({ section: 3, field: 0 }, 'j', 'home'), { section: 3, field: 0 });
  assert.deepEqual(Model.moveCursor({ section: 0, field: 0 }, 'k', 'home'), { section: 0, field: 0 });
  assert.deepEqual(Model.moveCursor({ section: 1, field: 0 }, 'h', 'home'), { section: 1, field: 0 });
});

test('schedule editor expands to six keyboard fields on the automation route', () => {
  assert.equal(Model.sectionFieldCount('automation', 3, false), 1);
  assert.equal(Model.sectionFieldCount('automation', 3, true), 6);
  assert.deepEqual(Model.moveCursor({ section: 3, field: 4 }, 'j', 'automation', true), { section: 3, field: 5 });
  assert.deepEqual(Model.moveCursor({ section: 3, field: 5 }, 'j', 'automation', true), { section: 3, field: 5 });
});

test('snooze and shortcut action sections move horizontally across their actions', () => {
  assert.deepEqual(Model.moveCursor({ section: 2, field: 0 }, 'l', 'automation'), { section: 2, field: 1 });
  assert.deepEqual(Model.moveCursor({ section: 2, field: 3 }, 'l', 'automation'), { section: 2, field: 3 });
  assert.deepEqual(Model.moveCursor({ section: 5, field: 1 }, 'h', 'settings'), { section: 5, field: 0 });
});

test('clamps a horizontal field when vertical navigation enters a shorter section', () => {
  assert.deepEqual(Model.moveCursor({ section: 3, field: 5 }, 'k', 'automation'), { section: 2, field: 3 });
  assert.deepEqual(Model.moveCursor({ section: 5, field: 1 }, 'k', 'settings'), { section: 4, field: 0 });
});

test('keeps expanded schedule vertical navigation inside fields 0 through 5', () => {
  assert.deepEqual(Model.moveCursor({ section: 3, field: 0 }, 'j', 'automation', true), { section: 3, field: 1 });
  assert.deepEqual(Model.moveCursor({ section: 3, field: 1 }, 'ArrowDown', 'automation', true), { section: 3, field: 2 });
  assert.deepEqual(Model.moveCursor({ section: 3, field: 2 }, 'j', 'automation', true), { section: 3, field: 3 });
  assert.deepEqual(Model.moveCursor({ section: 3, field: 3 }, 'ArrowDown', 'automation', true), { section: 3, field: 4 });
  assert.deepEqual(Model.moveCursor({ section: 3, field: 4 }, 'k', 'automation', true), { section: 3, field: 3 });
  assert.deepEqual(Model.moveCursor({ section: 3, field: 0 }, 'ArrowUp', 'automation', true), { section: 3, field: 0 });
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
  assert.equal(state.error, 'Estado no confirmado');
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
  assert.equal(Model.copy.heroTitle, 'Luz nocturna');
  assert.equal(Model.copy.brightness, 'Brillo');
  assert.equal(Model.copy.temperature, 'Temperatura');
  assert.equal(Model.copy.gamma, 'Gamma (brillo percibido)');
  assert.equal(Model.copy.schedule, 'Horario');
  assert.equal(Model.copy.save, 'Guardar cambios');
  assert.equal(Model.copy.unavailable, 'No disponible');
  assert.equal(Model.copy.disabled, 'Color natural');
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
  assert.deepEqual(Model.validateScheduleFields('06:00', '06:00', true, 6000, 3500), {
    valid: false,
    error: 'Las horas de día y noche deben ser diferentes'
  });
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

test('three rapid Arrow presses accumulate three steps without waiting for three readbacks', () => {
  const state = Model.normalizeState({
    available: true,
    enabled: false,
    brightness: { available: true, percent: 50, monitor: 'eDP-2', error: null },
    nightlight: { available: true, enabled: false, identity: true, temperature: 6000, gamma: 100, error: null },
    schedule: { available: false }
  });
  let pending = 0;
  const requested = [];
  for (let i = 0; i < 3; i++) {
    const step = Model.keyboardStep('brightness', 1, state.brightness.percent, pending);
    pending = step.pending;
    requested.push(step.value);
  }
  assert.deepEqual(requested, [51, 52, 53]);
  assert.equal(pending, 3);
});

test('temperature and gamma keyboard steps scale by their own magnitudes', () => {
  const temp = Model.keyboardStep('temperature', 1, 3500, 0);
  assert.equal(temp.value, 3600);
  assert.equal(Model.keyboardStep('temperature', 1, 3500, temp.pending).value, 3700);
  assert.equal(Model.keyboardStep('gamma', -1, 40, 0).value, 39);
});

test('keyboard steps clamp at the section boundary and stop accumulating', () => {
  assert.equal(Model.keyboardStep('brightness', 1, 100, 0).value, 100);
  assert.equal(Model.keyboardStep('brightness', 1, 100, 0).pending, 0);
  assert.equal(Model.keyboardStep('brightness', -1, 1, 0).value, 1);
  assert.equal(Model.keyboardStep('brightness', -1, 1, 0).pending, 0);
  assert.equal(Model.stepTargetValue('gamma', 95, 10), 100);
  assert.equal(Model.stepTargetValue('brightness', 2, -5), 1);
});

test('pending steps are drained toward the confirmed value by the realized delta', () => {
  const first = Model.keyboardStep('brightness', 1, 50, 0);
  const second = Model.keyboardStep('brightness', 1, 50, first.pending);
  const third = Model.keyboardStep('brightness', 1, 50, second.pending);
  const realized = 1;
  const remaining = third.pending - realized;
  const drainTarget = Model.stepTargetValue('brightness', 51, remaining);
  assert.equal(remaining, 2);
  assert.equal(drainTarget, 53);
});

function stepState(sections) {
  return Model.normalizeState({
    available: true,
    enabled: false,
    brightness: sections.brightness !== undefined
      ? { available: true, percent: sections.brightness, monitor: 'eDP-2', error: null }
      : { available: false, percent: null, monitor: null, error: null },
    nightlight: {
      available: true,
      enabled: false,
      identity: true,
      temperature: sections.temperature !== undefined ? sections.temperature : 6000,
      gamma: sections.gamma !== undefined ? sections.gamma : 100,
      error: null
    },
    schedule: { available: false }
  });
}

const zeroPending = { brightness: 0, temperature: 0, gamma: 0 };

test('reconcilePendingSteps never re-queues a section with no keyboard steps pending', () => {
  const result = Model.reconcilePendingSteps(stepState({ brightness: 50 }), stepState({ brightness: 80 }), zeroPending, 'brightness');
  assert.deepEqual(result.requests, []);
  assert.deepEqual(result.pending, zeroPending);
});

test('a readback from a different operation clears stale keyboard pending instead of draining', () => {
  const result = Model.reconcilePendingSteps(
    stepState({ brightness: 50 }),
    stepState({ brightness: 80 }),
    { brightness: 3, temperature: 0, gamma: 0 },
    'preset'
  );
  assert.deepEqual(result.requests, []);
  assert.deepEqual(result.pending, { brightness: 0, temperature: 0, gamma: 0 });
});

test('a same-section confirmed readback drains keyboard pending fully', () => {
  const result = Model.reconcilePendingSteps(
    stepState({ brightness: 50 }),
    stepState({ brightness: 53 }),
    { brightness: 3, temperature: 0, gamma: 0 },
    'brightness'
  );
  assert.deepEqual(result.requests, []);
  assert.deepEqual(result.pending, zeroPending);
});

test('a same-section partial readback re-queues only the remaining distance', () => {
  const result = Model.reconcilePendingSteps(
    stepState({ brightness: 50 }),
    stepState({ brightness: 51 }),
    { brightness: 3, temperature: 0, gamma: 0 },
    'brightness'
  );
  assert.deepEqual(result.requests, [{ section: 'brightness', value: 53 }]);
  assert.deepEqual(result.pending, { brightness: 2, temperature: 0, gamma: 0 });
});

test('negative realized delta from a foreign change clears pending without a revert', () => {
  const result = Model.reconcilePendingSteps(
    stepState({ brightness: 80 }),
    stepState({ brightness: 50 }),
    { brightness: 3, temperature: 0, gamma: 0 },
    'reconcile'
  );
  assert.deepEqual(result.requests, []);
  assert.deepEqual(result.pending, zeroPending);
});

test('superseded keyboard steps in another section clear instead of over-shooting later', () => {
  const result = Model.reconcilePendingSteps(
    stepState({ brightness: 50, temperature: 3500 }),
    stepState({ brightness: 50, temperature: 3600 }),
    { brightness: 3, temperature: 1, gamma: 0 },
    'temperature'
  );
  assert.deepEqual(result.requests, []);
  assert.deepEqual(result.pending, { brightness: 0, temperature: 0, gamma: 0 });
});

test('temperature pending drains with its own 100 K magnitude', () => {
  const result = Model.reconcilePendingSteps(
    stepState({ temperature: 3500 }),
    stepState({ temperature: 3800 }),
    { brightness: 0, temperature: 4, gamma: 0 },
    'temperature'
  );
  assert.deepEqual(result.requests, [{ section: 'temperature', value: 3900 }]);
  assert.deepEqual(result.pending, { brightness: 0, temperature: 1, gamma: 0 });
});

test('navigateCursorRoute wraps routes onto a visible landing section at vertical boundaries', () => {
  assert.deepEqual(Model.navigateCursorRoute('home', { section: 0, field: 0 }, 'k', false), { route: 'settings', section: 5 });
  assert.deepEqual(Model.navigateCursorRoute('home', { section: 3, field: 0 }, 'j', false), { route: 'automation', section: 0 });
  assert.deepEqual(Model.navigateCursorRoute('automation', { section: 0, field: 0 }, 'k', false), { route: 'home', section: 3 });
  assert.deepEqual(Model.navigateCursorRoute('settings', { section: 5, field: 0 }, 'j', false), { route: 'home', section: 0 });
  assert.deepEqual(Model.navigateCursorRoute('automation', { section: 3, field: 0 }, 'j', false), { route: 'settings', section: 0 });
  assert.deepEqual(Model.navigateCursorRoute('settings', { section: 0, field: 0 }, 'k', false), { route: 'automation', section: 3 });
});

test('a same-section concurrent change that overshoots pending intent drains without counter-adjusting', () => {
  const result = Model.reconcilePendingSteps(
    stepState({ brightness: 50 }),
    stepState({ brightness: 55 }),
    { brightness: 3, temperature: 0, gamma: 0 },
    'brightness'
  );
  assert.deepEqual(result.requests, []);
  assert.deepEqual(result.pending, zeroPending);
});

test('a same-section concurrent negative overshoot drains without a positive counter-correction', () => {
  const result = Model.reconcilePendingSteps(
    stepState({ brightness: 60 }),
    stepState({ brightness: 52 }),
    { brightness: -2, temperature: 0, gamma: 0 },
    'brightness'
  );
  assert.deepEqual(result.requests, []);
  assert.deepEqual(result.pending, zeroPending);
});

test('navigateCursorRoute leaves interior navigation and expanded editors alone', () => {
  assert.equal(Model.navigateCursorRoute('home', { section: 1, field: 0 }, 'k', false), null);
  assert.equal(Model.navigateCursorRoute('home', { section: 2, field: 0 }, 'j', false), null);
  assert.equal(Model.navigateCursorRoute('home', { section: 0, field: 0 }, 'k', true), null);
  assert.equal(Model.navigateCursorRoute('home', { section: 0, field: 0 }, 'j', false), null);
  assert.equal(Model.navigateCursorRoute('automation', { section: 3, field: 0 }, 'k', false), null);
});

test('dragTargetEmpty starts every drag section without an absolute target', () => {
  assert.deepEqual(Model.dragTargetEmpty(), { brightness: null, temperature: null, gamma: null });
});

test('dragTargetPush clamps the newest absolute target per section', () => {
  let bus = Model.dragTargetEmpty();
  bus = Model.dragTargetPush(bus, 'brightness', 150);
  assert.equal(bus.brightness, 100);
  bus = Model.dragTargetPush(bus, 'brightness', 0);
  assert.equal(bus.brightness, 1);
  bus = Model.dragTargetPush(bus, 'brightness', 70);
  assert.equal(bus.brightness, 70);
  assert.equal(bus.temperature, null);
  bus = Model.dragTargetPush(bus, 'temperature', 6200);
  assert.equal(bus.temperature, 6200);
  assert.equal(bus.brightness, 70);
});

test('dragTargetPush clears a section when the intent is removed', () => {
  let bus = Model.dragTargetPush(Model.dragTargetEmpty(), 'brightness', 70);
  bus = Model.dragTargetPush(bus, 'brightness', null);
  assert.equal(bus.brightness, null);
});

test('reconcileDragTargets keeps chasing a same-section target one request at a time', () => {
  const result = Model.reconcileDragTargets(
    stepState({ brightness: 50 }),
    stepState({ brightness: 51 }),
    { brightness: 70, temperature: null, gamma: null },
    'brightness'
  );
  assert.deepEqual(result.requests, [{ section: 'brightness', value: 70 }]);
  assert.deepEqual(result.target, { brightness: 70, temperature: null, gamma: null });
});

test('reconcileDragTargets clears a target the readback reached', () => {
  const result = Model.reconcileDragTargets(
    stepState({ brightness: 69 }),
    stepState({ brightness: 70 }),
    { brightness: 70, temperature: null, gamma: null },
    'brightness'
  );
  assert.deepEqual(result.requests, []);
  assert.deepEqual(result.target, Model.dragTargetEmpty());
});

test('reconcileDragTargets drops drag intent on a foreign readback', () => {
  const result = Model.reconcileDragTargets(
    stepState({ brightness: 50 }),
    stepState({ brightness: 51 }),
    { brightness: 70, temperature: null, gamma: null },
    'preset'
  );
  assert.deepEqual(result.requests, []);
  assert.deepEqual(result.target, Model.dragTargetEmpty());
});

test('reconcileDragTargets stops chasing when a readback makes no progress', () => {
  const result = Model.reconcileDragTargets(
    stepState({ brightness: 51 }),
    stepState({ brightness: 51 }),
    { brightness: 70, temperature: null, gamma: null },
    'brightness'
  );
  assert.deepEqual(result.requests, []);
  assert.deepEqual(result.target, Model.dragTargetEmpty());
});

test('reconcileDragTargets stops when the value moved away from the target', () => {
  const result = Model.reconcileDragTargets(
    stepState({ brightness: 80 }),
    stepState({ brightness: 50 }),
    { brightness: 70, temperature: null, gamma: null },
    'brightness'
  );
  assert.deepEqual(result.requests, []);
  assert.deepEqual(result.target, Model.dragTargetEmpty());
});

test('bundled fallback copy keeps exact key parity with the I18n Spanish dictionary', () => {
  const fallback = Model.DEFAULT_COPY;
  assert.ok(fallback && typeof fallback === 'object', 'DEFAULT_COPY must be exported for parity checks');
  assert.deepEqual(Object.keys(fallback).sort(), Object.keys(I18n.es).sort());
  for (const key of Object.keys(I18n.es))
    assert.equal(fallback[key], I18n.es[key], `fallback ${key} must copy the I18n.es value`);
});

test('every stable error-code key resolves to a real message without the I18n library wired', () => {
  const codeKeys = Object.values(Model.ERROR_CODE_KEYS);
  assert.ok(codeKeys.length >= 50, `expected >= 50 mapped codes, got ${codeKeys.length}`);
  Model.setI18n(null);
  try {
    for (const key of new Set(codeKeys)) {
      assert.ok(typeof Model.DEFAULT_COPY[key] === 'string' && Model.DEFAULT_COPY[key] !== '', `fallback copy missing ${key}`);
      assert.notEqual(Model.t(key), key, `${key} must not degrade to the raw key in the fallback`);
    }
    assert.equal(Model.errorCodeMessage('invalid_json'), 'Los datos guardados no tienen un formato válido.');
    assert.equal(Model.errorCodeMessage('timeout'), 'Se agotó el tiempo de espera del comando.');
    assert.equal(Model.validateScheduleFields('25:00', '18:00', true, 6000, 3500).error, 'La hora diurna debe usar el formato HH:MM');
    assert.equal(Model.validateScheduleFields('06:00', '18:00', true, 7000, 3500).error, 'La temperatura diurna debe estar entre 5900 y 6500 K');
    assert.equal(Model.t('manualPersistError'), Model.DEFAULT_COPY.manualPersistError);
  } finally {
    Model.setI18n(I18n);
  }
});

test('setI18n swaps the runtime locale library and restores the active copy', () => {
  assert.equal(typeof Model.setI18n, 'function');
  Model.setI18n(null);
  try {
    assert.equal(Model.t('save', 'en'), 'Guardar cambios');
    assert.equal(Model.copyFor('en'), Model.DEFAULT_COPY);
  } finally {
    Model.setI18n(I18n);
  }
  assert.equal(Model.t('save', 'en'), 'Save changes');
  assert.equal(Model.copyFor('fr'), I18n.es);
  assert.equal(Model.copy, I18n.es);
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

  const toggled = Model.mergeStatePatch(physicalState(), { enabled: true });
  assert.equal(toggled.enabled, true);
  assert.equal(toggled.nightlight.enabled, true);

  const viaNightlight = Model.mergeStatePatch(physicalState(), {
    nightlight: { enabled: true }
  });
  assert.equal(viaNightlight.enabled, true);
});

test('mergeStatePatch ignores non-object patches and re-normalizes garbage values', () => {
  assert.equal(typeof Model.mergeStatePatch, 'function');
  if (typeof Model.mergeStatePatch !== 'function') return;
  const base = physicalState();
  assert.equal(Model.mergeStatePatch(base, null).brightness.percent, 50);
  assert.equal(Model.mergeStatePatch(base, 'corrupt').brightness.percent, 50);
  const garbage = Model.mergeStatePatch(base, { brightness: { available: true, percent: true } });
  assert.equal(garbage.brightness.percent, null, 'a boolean percent fails closed instead of rendering');
});
