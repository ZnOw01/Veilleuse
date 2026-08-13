// I18n.js — pure localized dictionaries for the Veilleuse panel.
//
// Kept free of Qt globals so the dictionaries and the fallback/parity contract
// can be exercised with Node (the module.exports guard below lets Quickshell
// import it with `import "I18n.js" as I18n`).
//
// The default locale is `es` to preserve the plugin's native Spanish first
// impression and the existing UiModel.copy surface. `en` mirrors every key.

var DEFAULT_LOCALE = 'es';
var LOCALES = ['es', 'en'];

var es = {
  // Core panel copy (backward-compatible with UiModel.copy / Panel.qml).
  heroTitle: 'Luz nocturna',
  brightness: 'Brillo',
  temperature: 'Temperatura',
  gamma: 'Brillo percibido',
  schedule: 'Horario',
  save: 'Guardar cambios',
  saved: 'Cambios guardados',
  unavailable: 'No disponible',
  notConfirmed: 'Estado no confirmado',
  enabled: 'Activada',
  disabled: 'Color natural',
  periodDay: 'Periodo diurno',
  periodNight: 'Periodo nocturno',
  manualOverride: 'Anulación manual',
  start: 'Inicio',
  end: 'Fin',
  naturalDay: 'Día natural',
  scheduleDayTemperature: 'Temperatura diurna',
  scheduleTemperature: 'Temperatura nocturna',
  // Routes.
  routeHome: 'Inicio',
  routeAutomation: 'Automatización',
  routeSettings: 'Ajustes',
  // Provenance labels.
  provenanceAutomatic: 'Automática',
  provenanceManual: 'Manual',
  provenancePreset: 'Perfil',
  provenanceSnooze: 'Posposición',
  provenanceUnknown: 'Desconocido',
  // Midnight / snooze-until-tomorrow explanation.
  midnightExplanation: 'La posposición “hasta mañana” se mantiene hasta el inicio del periodo diurno del día siguiente (medianoche), cuando el horario retoma el perfil programado.',
  // Preflight.
  preflightTitle: 'Comprobación del asistente',
  preflightStatusOk: 'Todo listo',
  preflightStatusWarn: 'Atención',
  preflightStatusFail: 'Falla',
  // Stable error codes.
  errHelperMissing: 'No se pudo iniciar el asistente de control.',
  errBrightnessUnavailable: 'El brillo no está disponible en este momento.',
  errNightlightUnavailable: 'La luz nocturna no está disponible.',
  errMonitorUnavailable: 'El monitor seleccionado no está disponible.',
  errScheduleInvalid: 'El horario configurado no es válido.',
  errSnoozeInvalid: 'La posposición solicitada no es válida.',
  errPresetNotFound: 'No se encontró el perfil solicitado.',
  errPresetInvalid: 'El perfil no es válido.',
  errHistoryUnreadable: 'No se pudo leer el historial.',
  errSettingsWrite: 'No se pudieron guardar los ajustes.',
  errShortcutWrite: 'No se pudo actualizar el acceso directo.',
  errUnknown: 'Se produjo un error desconocido.',
  // Presets.
  presetTitle: 'Perfiles',
  presetApply: 'Aplicar',
  presetDelete: 'Eliminar',
  presetSave: 'Guardar perfil',
  presetAll: 'Todos los perfiles',
  presetBuiltIn: 'Integrado',
  // Snooze.
  snoozeTitle: 'Posposición',
  snoozeSet: 'Posponer',
  snoozeUntilTomorrow: 'Hasta mañana',
  snoozeClear: 'Cancelar posposición',
  snoozeStatusActive: 'Pospuesta',
  snoozeStatusOff: 'Sin posposición',
  // Settings.
  settingsTitle: 'Ajustes',
  applyScope: 'Alcance de aplicación',
  applyScopeSession: 'Sesión',
  applyScopePersistent: 'Persistente',
  defaultPreset: 'Perfil predeterminado',
  language: 'Idioma',
  shortcut: 'Acceso directo',
  shortcutInstall: 'Instalar',
  shortcutRemove: 'Quitar',
  transitionSeconds: 'Transición (s)',
  // History.
  historyTitle: 'Historial',
  historyClear: 'Limpiar historial',
  historyEmpty: 'Sin registros'
};


var en = {
  heroTitle: 'Night light',
  brightness: 'Brightness',
  temperature: 'Temperature',
  gamma: 'Perceived brightness',
  schedule: 'Schedule',
  save: 'Save changes',
  saved: 'Changes saved',
  unavailable: 'Unavailable',
  notConfirmed: 'State not confirmed',
  enabled: 'Enabled',
  disabled: 'Natural color',
  periodDay: 'Day period',
  periodNight: 'Night period',
  manualOverride: 'Manual override',
  start: 'Start',
  end: 'End',
  naturalDay: 'Natural day',
  scheduleDayTemperature: 'Day temperature',
  scheduleTemperature: 'Night temperature',
  routeHome: 'Home',
  routeAutomation: 'Automation',
  routeSettings: 'Settings',
  provenanceAutomatic: 'Automatic',
  provenanceManual: 'Manual',
  provenancePreset: 'Preset',
  provenanceSnooze: 'Snoozed',
  provenanceUnknown: 'Unknown',
  midnightExplanation: 'The “snooze until tomorrow” option is held until the start of the next day period (midnight), when the schedule resumes the configured profile.',
  preflightTitle: 'Helper check',
  preflightStatusOk: 'All set',
  preflightStatusWarn: 'Attention',
  preflightStatusFail: 'Failed',
  errHelperMissing: 'The control helper could not be started.',
  errBrightnessUnavailable: 'Brightness is currently unavailable.',
  errNightlightUnavailable: 'Night light is unavailable.',
  errMonitorUnavailable: 'The selected monitor is unavailable.',
  errScheduleInvalid: 'The configured schedule is not valid.',
  errSnoozeInvalid: 'The requested snooze is not valid.',
  errPresetNotFound: 'The requested preset was not found.',
  errPresetInvalid: 'The preset is not valid.',
  errHistoryUnreadable: 'The history could not be read.',
  errSettingsWrite: 'The settings could not be saved.',
  errShortcutWrite: 'The keyboard shortcut could not be updated.',
  errUnknown: 'An unknown error occurred.',
  presetTitle: 'Presets',
  presetApply: 'Apply',
  presetDelete: 'Delete',
  presetSave: 'Save preset',
  presetAll: 'All presets',
  presetBuiltIn: 'Built-in',
  snoozeTitle: 'Snooze',
  snoozeSet: 'Snooze',
  snoozeUntilTomorrow: 'Until tomorrow',
  snoozeClear: 'Cancel snooze',
  snoozeStatusActive: 'Snoozed',
  snoozeStatusOff: 'No snooze',
  settingsTitle: 'Settings',
  applyScope: 'Apply scope',
  applyScopeSession: 'Session',
  applyScopePersistent: 'Persistent',
  defaultPreset: 'Default preset',
  language: 'Language',
  shortcut: 'Shortcut',
  shortcutInstall: 'Install',
  shortcutRemove: 'Remove',
  transitionSeconds: 'Transition (s)',
  historyTitle: 'History',
  historyClear: 'Clear history',
  historyEmpty: 'No records'
};

var KEYS = (function () {
  var combined = {};
  var key;
  for (key in es) combined[key] = true;
  for (key in en) combined[key] = true;
  return Object.keys(combined);
})();

function locales() {
  return LOCALES.slice();
}

function defaultLocale() {
  return DEFAULT_LOCALE;
}

function hasLocale(locale) {
  return locale === 'es' || locale === 'en';
}

function resolveLocale(locale) {
  return hasLocale(locale) ? locale : DEFAULT_LOCALE;
}

function dictionary(locale) {
  return resolveLocale(locale) === 'en' ? en : es;
}

function keys() {
  return KEYS.slice();
}

function missingKeys(locale) {
  var dict = dictionary(locale);
  var missing = [];
  for (var i = 0; i < KEYS.length; i++) {
    if (!Object.prototype.hasOwnProperty.call(dict, KEYS[i])) missing.push(KEYS[i]);
  }
  return missing;
}

function keyParity() {
  var esMissing = missingKeys('es');
  var enMissing = missingKeys('en');
  if (esMissing.length > 0 || enMissing.length > 0) return false;
  var esKeys = Object.keys(es);
  var enKeys = Object.keys(en);
  return esKeys.length === enKeys.length;
}

function hasOwn(object, key) {
  return Object.prototype.hasOwnProperty.call(object, key);
}

// Locale-aware lookup with a strict fallback chain: requested dictionary, then
// en, then es, then the raw key itself. Unknown locales resolve to `es`.
function t(key, locale) {
  var resolved = resolveLocale(locale);
  var primary = resolved === 'en' ? en : es;
  if (hasOwn(primary, key)) return primary[key];
  if (resolved !== 'en' && hasOwn(en, key)) return en[key];
  if (resolved !== 'es' && hasOwn(es, key)) return es[key];
  return key;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    LOCALES: LOCALES,
    DEFAULT_LOCALE: DEFAULT_LOCALE,
    es: es,
    en: en,
    locales: locales,
    defaultLocale: defaultLocale,
    hasLocale: hasLocale,
    resolveLocale: resolveLocale,
    dictionary: dictionary,
    keys: keys,
    missingKeys: missingKeys,
    keyParity: keyParity,
    t: t
  };
}
