const test = require('node:test');
const assert = require('node:assert/strict');

const I18n = require('../I18n.js');

test('exposes en and es as the only supported locales, English first', () => {
  assert.deepEqual(I18n.locales(), ['en', 'es']);
  assert.equal(I18n.defaultLocale(), 'en');
  assert.equal(I18n.hasLocale('en'), true);
  assert.equal(I18n.hasLocale('es'), true);
  assert.equal(I18n.hasLocale('fr'), false);
});

test('resolves unknown locales to the English default without throwing', () => {
  assert.equal(I18n.resolveLocale('fr'), 'en');
  assert.equal(I18n.resolveLocale(null), 'en');
  assert.equal(I18n.resolveLocale('es'), 'es');
  assert.equal(I18n.resolveLocale('en'), 'en');
});

test('complete en and es dictionaries share identical key sets', () => {
  const esKeys = Object.keys(I18n.es);
  const enKeys = Object.keys(I18n.en);
  assert.ok(esKeys.length >= 50, `expected >= 50 keys, got ${esKeys.length}`);
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
  assert.equal(I18n.t('save', 'fr'), I18n.en.save);
  assert.equal(I18n.t('save', null), I18n.en.save);
});

test('t() falls back to es, then to the key itself when a key is missing', () => {
  const enSave = I18n.en.save;
  const esSave = I18n.es.save;
  // Deleted only from en: an English lookup falls back to the Spanish value.
  delete I18n.en.save;
  try {
    assert.equal(I18n.t('save', 'en'), esSave);
  } finally {
    I18n.en.save = enSave;
  }
  // Deleted from both: the fallback chain ends at the raw key itself.
  delete I18n.en.save;
  delete I18n.es.save;
  try {
    assert.equal(I18n.t('save', 'en'), 'save');
  } finally {
    I18n.en.save = enSave;
    I18n.es.save = esSave;
  }
});

test('dictionary() returns the localized map for a supported locale only', () => {
  assert.equal(I18n.dictionary('es'), I18n.es);
  assert.equal(I18n.dictionary('en'), I18n.en);
  assert.equal(I18n.dictionary('fr'), I18n.en);
});

test('the preset-era UI keys are gone and the schedule keys survive', () => {
  for (const key of [
    'presetTitle', 'presetApply', 'presetSave', 'presetName', 'defaultPreset',
    'runPreflight', 'preflightTitle', 'applyScope', 'scopeHelp',
    'midnightExplanation', 'editSchedule', 'snoozeUntilTomorrow',
    'transitionTitle', 'viewHistory', 'liveControls', 'historyTitle'
  ]) {
    assert.ok(!Object.prototype.hasOwnProperty.call(I18n.en, key), `en.${key} must be gone`);
    assert.ok(!Object.prototype.hasOwnProperty.call(I18n.es, key), `es.${key} must be gone`);
  }
  for (const key of [
    'routeHome', 'routeAutomation', 'routeSettings',
    'provenanceAutomatic', 'provenanceManual', 'provenancePreset',
    'provenanceSnooze', 'provenanceUnknown',
    'dayPeriod', 'nightPeriod',
    'scheduleDayTemperatureRange', 'scheduleNightTemperatureRange',
    'scheduleBrightnessRange', 'scheduleGammaRange',
    'snoozeTitle', 'snoozeSet', 'snoozeClear', 'snoozeStatusActive',
    'unitHours', 'unitMinutes', 'unitSeconds',
    'settingsTitle', 'language', 'shortcut', 'shortcutInstall', 'shortcutRemove',
    'keyboardHints', 'monitor', 'focusedMonitor',
    'errHelperMissing', 'errUnknown', 'manualPersistError'
  ]) {
    assert.ok(typeof I18n.es[key] === 'string' && I18n.es[key] !== '', `es.${key}`);
    assert.ok(typeof I18n.en[key] === 'string' && I18n.en[key] !== '', `en.${key}`);
  }
});

test('keyboard hints describe the arrows-only model in both locales', () => {
  // Key/action pairs use non-breaking spaces so line wraps never split a
  // pair across lines in the panel's hint footer.
  assert.equal(I18n.en.keyboardHints, '← →\u00A0adjust / switch\u00A0view · ↑ ↓\u00A0move · Enter\u00A0activate · Esc\u00A0close');
  assert.equal(I18n.es.keyboardHints, '← →\u00A0ajustar / cambiar\u00A0vista · ↑ ↓\u00A0moverse · Enter\u00A0activar · Esc\u00A0cerrar');
});

// ============================================================================
// TIER 1 & TIER 2: I18N CONTRACTS & BOUNDARIES
// ============================================================================

test('Tier 1 - F10 i18n: All route names resolve cleanly in both English and Spanish', () => {
  assert.equal(I18n.t('routeHome', 'en'), 'Home');
  assert.equal(I18n.t('routeHome', 'es'), 'Inicio');
  assert.equal(I18n.t('routeAutomation', 'en'), 'Automation');
  assert.equal(I18n.t('routeAutomation', 'es'), 'Automatización');
  assert.equal(I18n.t('routeSettings', 'en'), 'Settings');
  assert.equal(I18n.t('routeSettings', 'es'), 'Ajustes');
});

test('Tier 1 - F10 i18n: All provenance strings resolve cleanly in both locales', () => {
  const provenances = ['provenanceAutomatic', 'provenancePreset', 'provenanceSnooze', 'provenanceUnknown'];
  for (const p of provenances) {
    const en = I18n.t(p, 'en');
    const es = I18n.t(p, 'es');
    assert.ok(en.length > 0);
    assert.ok(es.length > 0);
    assert.notEqual(en, es);
  }
  // provenanceManual is "Manual" in both Spanish and English
  assert.equal(I18n.t('provenanceManual', 'en'), 'Manual');
  assert.equal(I18n.t('provenanceManual', 'es'), 'Manual');
});

test('Tier 2 - F10 i18n Boundaries: resolveKey converts defined semantic aliases correctly', () => {
  assert.equal(I18n.resolveKey('night_light'), 'heroTitle');
  assert.equal(I18n.resolveKey('home'), 'routeHome');
  assert.equal(I18n.resolveKey('automation'), 'routeAutomation');
  assert.equal(I18n.resolveKey('settings'), 'routeSettings');
  assert.equal(I18n.resolveKey('snooze_set'), 'snoozeSet');
  assert.equal(I18n.resolveKey('clear_snooze'), 'snoozeClear');
  assert.equal(I18n.resolveKey('day_period'), 'dayPeriod');
  assert.equal(I18n.resolveKey('night_period'), 'nightPeriod');
  assert.equal(I18n.resolveKey('heroTitle'), 'heroTitle');
});

test('Tier 2 - F10 i18n Boundaries: Handling null, undefined, empty, and non-existent keys safely', () => {
  assert.equal(I18n.t('', 'en'), '');
  assert.equal(I18n.t(null, 'en'), null);
  assert.equal(I18n.t(undefined, 'en'), undefined);
  assert.equal(I18n.t('nonExistentKey123', 'en'), 'nonExistentKey123');
  assert.equal(I18n.t('nonExistentKey123', 'es'), 'nonExistentKey123');
});
