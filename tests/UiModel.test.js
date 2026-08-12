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

test('clamps a horizontal field when vertical navigation enters a shorter section', () => {
  assert.deepEqual(Model.moveCursor({ section: 4, field: 3 }, 'k'), { section: 3, field: 1 });
});

test('normalizes unavailable helper data to a fail-closed state', () => {
  assert.deepEqual(Model.normalizeState({
    available: true,
    enabled: true,
    brightness: 150,
    temperature: 'not-a-number',
    gamma: -4,
    schedule: { start: '25:99', end: '15:30', temperature: 3000 }
  }), {
    available: false,
    enabled: false,
    brightness: null,
    temperature: null,
    gamma: null,
    schedule: { start: null, end: '15:30', temperature: 3000 },
    error: 'Estado no confirmado'
  });
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
    schedule: { available: true, day_time: '07:00', night_time: '21:00', night_temp: 3200, error: null }
  });
  assert.equal(state.available, true);
  assert.equal(state.brightness, 42);
  assert.equal(state.enabled, true);
  assert.equal(state.temperature, 3500);
  assert.equal(state.gamma, 90);
  assert.deepEqual(state.schedule, { start: '07:00', end: '21:00', temperature: 3200 });
});
