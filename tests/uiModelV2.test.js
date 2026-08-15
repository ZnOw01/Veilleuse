const test = require('node:test');
const assert = require('node:assert/strict');

const Model = require('../UiModel.js');
const I18n = require('../I18n.js');

test('copy remains the native Spanish default and is sourced from I18n.es', () => {
  assert.equal(Model.copy, I18n.es);
  assert.equal(Model.copy.heroTitle, 'Luz nocturna');
  assert.equal(Model.copy.brightness, 'Brillo');
  assert.equal(Model.copy.unavailable, 'No disponible');
  assert.equal(Model.copy.disabled, 'Color natural');
});

test('normalizeState and validateScheduleFields stay backward compatible in Spanish', () => {
  const state = Model.normalizeState({ available: true, enabled: true, brightness: 50, temperature: 3500, gamma: 100 });
  assert.equal(state.error, '');
  const unavailable = Model.normalizeState({});
  assert.equal(unavailable.error, 'Estado no confirmado');
  assert.deepEqual(Model.validateScheduleFields('06:00', '06:00', true, 6000, 3500), {
    valid: false,
    error: 'Las horas de día y noche deben ser diferentes'
  });
});

test('copyFor() returns the locale dictionary with Spanish as the default', () => {
  assert.equal(Model.copyFor('es'), I18n.es);
  assert.equal(Model.copyFor('en'), I18n.en);
  assert.equal(Model.copyFor('fr'), I18n.es);
});

test('t() delegates to the locale-aware lookup and stays pure', () => {
  assert.equal(Model.t('save', 'en'), 'Save changes');
  assert.equal(Model.t('save', 'es'), Model.copy.save);
  assert.equal(Model.t('save'), Model.copy.save);
});

test('error codes localize to the requested locale with a safe unknown fallback', () => {
  assert.equal(Model.errorCodeMessage('settingsWrite', 'es'), I18n.es.errSettingsWrite);
  assert.equal(Model.errorCodeMessage('settingsWrite', 'en'), I18n.en.errSettingsWrite);
  assert.equal(Model.errorCodeMessage('monitorUnavailable', 'en'), 'The selected monitor is unavailable.');
  assert.equal(Model.errorCodeMessage('totally-unknown-code', 'en'), I18n.en.errUnknown);
  assert.equal(Model.errorCodeMessage('totally-unknown-code', 'es'), I18n.es.errUnknown);
});

test('localizeError maps known codes and leaves existing literals untouched', () => {
  assert.equal(Model.localizeError('scheduleInvalid', 'en'), I18n.en.errScheduleInvalid);
  assert.equal(Model.localizeError('scheduleInvalid', 'es'), I18n.es.errScheduleInvalid);
  assert.equal(Model.localizeError('Estado no confirmado', 'en'), 'Estado no confirmado');
  assert.equal(Model.localizeError('', 'en'), '');
  assert.equal(Model.localizeError('', 'es'), '');
});

test('routes expose the three compact views in order', () => {
  assert.deepEqual(Model.routeOrder(), ['home', 'automation', 'settings']);
  assert.equal(Model.routeStart, undefined, 'routeStart was superseded by per-route cursor sections');
  assert.equal(Model.moveRoute, undefined, 'moveRoute was superseded by navigateCursorRoute');
  assert.equal(Model.routeLabel, undefined, 'routeLabel was superseded by t("routeHome") style lookups');
});

test('provenance labels localize each automation origin', () => {
  assert.equal(Model.provenanceLabel('automatic', 'es'), 'Automática');
  assert.equal(Model.provenanceLabel('automatic', 'en'), 'Automatic');
  assert.equal(Model.provenanceLabel('manual', 'en'), 'Manual');
  assert.equal(Model.provenanceLabel('preset', 'en'), 'Preset');
  assert.equal(Model.provenanceLabel('snooze', 'en'), 'Snoozed');
  assert.equal(Model.provenanceLabel('mystery', 'en'), 'Unknown');
  assert.equal(Model.provenanceLabel(null, 'en'), 'Unknown');
});

test('midnight explanation is a localized, non-empty sentence', () => {
  assert.ok(Model.midnightExplanation('es').length > 40);
  assert.ok(Model.midnightExplanation('en').length > 40);
  assert.notEqual(Model.midnightExplanation('es'), Model.midnightExplanation('en'));
});

test('preflight view model localizes status and per-check errors', () => {
  const result = Model.preflightStatus({
    checks: [
      { name: 'helper', ok: true, warn: false, error: null },
      { name: 'brightness', ok: false, warn: false, error: 'settingsWrite' }
    ]
  }, 'en');
  assert.equal(result.ok, false);
  assert.equal(result.failed, 1);
  assert.equal(result.status, I18n.en.preflightStatusFail);
  assert.equal(result.checks.length, 2);
  assert.equal(result.checks[1].error, I18n.en.errSettingsWrite);

  const allGood = Model.preflightStatus({ checks: [{ name: 'helper', ok: true }] }, 'es');
  assert.equal(allGood.ok, true);
  assert.equal(allGood.status, I18n.es.preflightStatusOk);

  const warning = Model.preflightStatus({ checks: [{ name: 'hyprctl', ok: true, warn: true }] }, 'en');
  assert.equal(warning.ok, false);
  assert.equal(warning.status, I18n.en.preflightStatusWarn);

  // Missing checks fail closed to a safe unknown-state view.
  const empty = Model.preflightStatus({}, 'en');
  assert.equal(empty.ok, false);
});

test('preset view model surfaces options with builtin flags and labels', () => {
  const vm = Model.presetViewModel([
    { name: 'day', builtin: true },
    { name: 'custom' }
  ], 'day', 'en');
  assert.equal(vm.length, 2);
  assert.equal(vm[0].name, 'day');
  assert.equal(vm[0].builtin, true);
  assert.equal(vm[0].selected, true);
  assert.equal(vm[1].selected, false);
  assert.equal(vm[0].applyLabel, I18n.en.presetApply);
  assert.equal(vm[0].builtinLabel, I18n.en.presetBuiltIn);
  assert.equal(vm[0].applyLabel, vm[1].applyLabel);
});

test('snooze view model reports active status and action labels', () => {
  const active = Model.snoozeViewModel({
    snoozed: true,
    schedule_enabled: true,
    transition_seconds: '5'
  }, 'en');
  assert.equal(active.snoozed, true);
  assert.equal(active.scheduleEnabled, true);
  assert.equal(active.statusLabel, I18n.en.snoozeStatusActive);
  assert.equal(active.snoozeClearLabel, I18n.en.snoozeClear);
  assert.equal(active.snoozeSetLabel, I18n.en.snoozeSet);

  const off = Model.snoozeViewModel({ snoozed: false }, 'es');
  assert.equal(off.snoozed, false);
  assert.equal(off.statusLabel, I18n.es.snoozeStatusOff);
});

test('settings view model localizes scope, language and shortcut fields', () => {
  const vm = Model.settingsViewModel({
    locale: 'en',
    apply_scope: 'persistent',
    default_preset: 'day',
    shortcut_keys: 'SUPER, L'
  }, 'en');
  assert.equal(vm.language, 'en');
  assert.equal(vm.applyScope, 'persistent');
  assert.equal(vm.defaultPreset, 'day');
  assert.equal(vm.shortcutKeys, 'SUPER, L');
  assert.equal(vm.languageLabel, I18n.en.language);
  assert.equal(vm.applyScopeLabel, I18n.en.applyScope);
  assert.equal(vm.sessionLabel, I18n.en.applyScopeSession);
  assert.equal(vm.persistentLabel, I18n.en.applyScopePersistent);
});

test('history view model bounds to 50 records and localizes labels', () => {
  const records = Array.from({ length: 60 }, (_, i) => ({ time: `t${i}`, operation: 'op', origin: 'manual' }));
  const vm = Model.historyViewModel(records, 'en');
  assert.equal(vm.records.length, 50);
  assert.equal(vm.empty, false);
  assert.equal(vm.emptyLabel, I18n.en.historyEmpty);
  assert.equal(vm.clearLabel, I18n.en.historyClear);

  const none = Model.historyViewModel([], 'es');
  assert.equal(none.empty, true);
  assert.equal(none.records.length, 0);
});
