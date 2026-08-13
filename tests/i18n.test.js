const test = require('node:test');
const assert = require('node:assert/strict');

const I18n = require('../I18n.js');

test('exposes es and en as the only supported locales', () => {
  assert.deepEqual(I18n.locales(), ['es', 'en']);
  assert.equal(I18n.defaultLocale(), 'es');
  assert.equal(I18n.hasLocale('es'), true);
  assert.equal(I18n.hasLocale('en'), true);
  assert.equal(I18n.hasLocale('fr'), false);
});

test('resolves unknown locales to the default without throwing', () => {
  assert.equal(I18n.resolveLocale('fr'), 'es');
  assert.equal(I18n.resolveLocale(null), 'es');
  assert.equal(I18n.resolveLocale('es'), 'es');
  assert.equal(I18n.resolveLocale('en'), 'en');
});

test('complete es and en dictionaries share identical key sets', () => {
  const esKeys = Object.keys(I18n.es);
  const enKeys = Object.keys(I18n.en);
  assert.ok(esKeys.length >= 60, `expected >= 60 keys, got ${esKeys.length}`);
  assert.deepEqual(new Set(esKeys), new Set(enKeys));
  assert.equal(I18n.keyParity(), true);
  assert.deepEqual(I18n.missingKeys('es'), []);
  assert.deepEqual(I18n.missingKeys('en'), []);
});

test('every canonical key resolves to a non-empty localized value in both locales', () => {
  for (const key of I18n.keys()) {
    assert.notEqual(I18n.es[key], '', `es.${key} must not be empty`);
    assert.notEqual(I18n.en[key], '', `en.${key} must not be empty`);
  }
});

test('no opposite-locale leakage: es values are Spanish and en values are English', () => {
  // Core strings that prove neither dictionary bleeds into the other.
  assert.notEqual(I18n.es.heroTitle, 'Night light');
  assert.notEqual(I18n.en.heroTitle, 'Luz nocturna');
  assert.equal(I18n.es.unavailable, 'No disponible');
  assert.equal(I18n.en.unavailable, 'Unavailable');
});

test('t() returns the requested locale translation', () => {
  assert.equal(I18n.t('save', 'es'), 'Guardar cambios');
  assert.equal(I18n.t('save', 'en'), 'Save changes');
  assert.equal(I18n.t('enabled', 'en'), 'Enabled');
});

test('t() falls back to the default locale for an unknown requested locale', () => {
  assert.equal(I18n.t('save', 'fr'), I18n.es.save);
  assert.equal(I18n.t('save', null), I18n.es.save);
});

test('t() falls back to en, then to the key itself when a key is missing', () => {
  const esSave = I18n.es.save;
  const enSave = I18n.en.save;
  // Deleted only from es: a Spanish lookup falls back to the English value.
  delete I18n.es.save;
  try {
    assert.equal(I18n.t('save', 'es'), enSave);
  } finally {
    I18n.es.save = esSave;
  }
  // Deleted from both: the fallback chain ends at the raw key itself.
  delete I18n.es.save;
  delete I18n.en.save;
  try {
    assert.equal(I18n.t('save', 'es'), 'save');
  } finally {
    I18n.es.save = esSave;
    I18n.en.save = enSave;
  }
});

test('dictionary() returns the localized map for a supported locale only', () => {
  assert.equal(I18n.dictionary('es'), I18n.es);
  assert.equal(I18n.dictionary('en'), I18n.en);
  assert.equal(I18n.dictionary('fr'), I18n.es);
});

test('midnight explanation and v2 UI keys are present in both locales', () => {
  for (const key of [
    'routeHome', 'routeAutomation', 'routeSettings',
    'provenanceAutomatic', 'provenanceManual', 'provenancePreset',
    'provenanceSnooze', 'provenanceUnknown',
    'midnightExplanation',
    'preflightTitle', 'preflightStatusOk', 'preflightStatusFail',
    'errHelperMissing', 'errSettingsWrite', 'errUnknown',
    'presetTitle', 'presetApply', 'presetDelete', 'presetSave', 'presetBuiltIn',
    'snoozeTitle', 'snoozeSet', 'snoozeUntilTomorrow', 'snoozeClear',
    'snoozeStatusActive', 'snoozeStatusOff',
    'settingsTitle', 'applyScope', 'applyScopeSession', 'applyScopePersistent',
    'defaultPreset', 'language', 'shortcut', 'shortcutInstall', 'shortcutRemove',
    'transitionSeconds',
    'historyTitle', 'historyClear', 'historyEmpty'
  ]) {
    assert.ok(typeof I18n.es[key] === 'string' && I18n.es[key] !== '', `es.${key}`);
    assert.ok(typeof I18n.en[key] === 'string' && I18n.en[key] !== '', `en.${key}`);
  }
});
