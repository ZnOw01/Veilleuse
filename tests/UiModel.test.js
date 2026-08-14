const test = require('node:test');
const assert = require('node:assert/strict');

const Model = require('../UiModel.js');

test('declares the compact control sections in visual order', () => {
  assert.deepEqual(Model.sectionOrder(), [
    'nightLight',
    'brightness',
    'temperature',
    'gamma',
    'schedule'
  ]);
});

test('moves the panel cursor with bounded section and field navigation', () => {
  const first = Model.cursorStart();
  assert.deepEqual(Model.moveCursor(first, 'j'), { section: 1, field: 0 });
  assert.deepEqual(Model.moveCursor({ section: 4, field: 0 }, 'j'), { section: 4, field: 0 });
  assert.deepEqual(Model.moveCursor({ section: 0, field: 0 }, 'k'), { section: 0, field: 0 });
  assert.deepEqual(Model.moveCursor({ section: 1, field: 0 }, 'l'), { section: 1, field: 1 });
  assert.deepEqual(Model.moveCursor({ section: 1, field: 0 }, 'h'), { section: 1, field: 0 });
  assert.deepEqual(Model.moveCursor({ section: 2, field: 1 }, 'h'), { section: 2, field: 0 });
});

test('exposes six keyboard fields when the schedule editor is expanded', () => {
  assert.equal(Model.FIELD_COUNTS && Model.FIELD_COUNTS[4], 6);
  assert.deepEqual(Model.moveCursor({ section: 4, field: 4 }, 'j', true), { section: 4, field: 5 });
  assert.deepEqual(Model.moveCursor({ section: 4, field: 5 }, 'j', true), { section: 4, field: 5 });
});

test('clamps a horizontal field when vertical navigation enters a shorter section', () => {
  assert.deepEqual(Model.moveCursor({ section: 4, field: 3 }, 'k'), { section: 3, field: 1 });
});

test('keeps expanded schedule vertical navigation inside fields 0 through 5', () => {
  assert.deepEqual(Model.moveCursor({ section: 4, field: 0 }, 'j', true), { section: 4, field: 1 });
  assert.deepEqual(Model.moveCursor({ section: 4, field: 1 }, 'ArrowDown', true), { section: 4, field: 2 });
  assert.deepEqual(Model.moveCursor({ section: 4, field: 2 }, 'j', true), { section: 4, field: 3 });
  assert.deepEqual(Model.moveCursor({ section: 4, field: 3 }, 'ArrowDown', true), { section: 4, field: 4 });
  assert.deepEqual(Model.moveCursor({ section: 4, field: 4 }, 'k', true), { section: 4, field: 3 });
  assert.deepEqual(Model.moveCursor({ section: 4, field: 0 }, 'ArrowUp', true), { section: 4, field: 0 });
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
  assert.equal(Model.copy.gamma, 'Brillo percibido');
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
