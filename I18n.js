// I18n.js — pure localized dictionaries for the Veilleuse panel.
//
// Kept free of Qt globals so the dictionaries and the fallback/parity contract
// can be exercised with Node (the module.exports guard below lets Quickshell
// import it with `import "I18n.js" as I18n`).
//
// The default locale is `en`: the plugin ships in English and Spanish stays a
// first-class choice in settings. `es` mirrors every key.

var DEFAULT_LOCALE = 'en';
var LOCALES = ['en', 'es'];

var en = {
  // Core panel copy (backward-compatible with UiModel.copy / Panel.qml).
  heroTitle: 'Night light',
  brightness: 'Brightness',
  temperature: 'Temperature',
  gamma: 'Gamma (perceived brightness)',
  gammaShort: 'Gamma',
  schedule: 'Schedule',
  save: 'Save changes',
  saved: 'Changes saved',
  unavailable: 'Unavailable',
  notConfirmed: 'State not confirmed',
  enabled: 'Enabled',
  disabled: 'Natural color',
  manualOverride: 'Manual override',
  start: 'Start',
  end: 'End',
  cancel: 'Cancel',
  // Routes.
  routeHome: 'Home',
  routeAutomation: 'Automation',
  routeSettings: 'Settings',
  // Provenance labels ("preset" only survives in persisted history).
  provenanceAutomatic: 'Automatic',
  provenanceManual: 'Manual',
  provenancePreset: 'Preset',
  provenanceSnooze: 'Snoozed',
  provenanceUnknown: 'Unknown',
  // Schedule editor.
  dayPeriod: 'Day',
  nightPeriod: 'Night',
  scheduleDayTimeFormat: 'Day time must use the HH:MM format',
  scheduleNightTimeFormat: 'Night time must use the HH:MM format',
  scheduleDayNightEqual: 'Day and night times must be different',
  scheduleDayTemperatureRange: 'Day temperature must be between 5900 and 6500 K',
  scheduleNightTemperatureRange: 'Night temperature must be between 2500 and 5000 K',
  scheduleBrightnessRange: 'Brightness must be between 1 and 100%',
  scheduleGammaRange: 'Gamma must be between 0 and 100%',
  // Snooze.
  snoozeTitle: 'Snooze',
  snoozeSet: 'Snooze',
  snoozeClear: 'Cancel snooze',
  snoozeStatusActive: 'Snoozed',
  unitHours: 'Hours',
  unitMinutes: 'Minutes',
  unitSeconds: 'Seconds',
  sunset: 'Sunset',
  quickSnooze: 'Quick snooze',
  // Settings.
  settingsTitle: 'Settings',
  language: 'Language',
  shortcut: 'Keyboard shortcut',
  shortcutKeys: 'Keys',
  shortcutInstall: 'Install',
  shortcutRemove: 'Remove',
  spanish: 'Español',
  english: 'English',
  // Stable error codes.
  errHelperMissing: 'The control helper could not be started.',
  errBrightnessUnavailable: 'Brightness is currently unavailable.',
  errNightlightUnavailable: 'Night light is unavailable.',
  errMonitorUnavailable: 'The selected monitor is unavailable.',
  errScheduleInvalid: 'The configured schedule is not valid.',
  errSnoozeInvalid: 'The requested snooze is not valid.',
  errHistoryUnreadable: 'The history could not be read.',
  errSettingsWrite: 'The settings could not be saved.',
  errShortcutWrite: 'The keyboard shortcut could not be updated.',
  errUnknown: 'An unknown error occurred.',
  errInvalidValue: 'The requested value is not valid.',
  errInvalidJson: 'The saved data is not in a valid format.',
  errInvalidConfig: 'The saved configuration is not valid.',
  errInvalidState: 'The saved state is not valid.',
  errInvalidHistory: 'The saved history is not valid.',
  errReadbackFailed: 'The change could not be confirmed.',
  errBrightnessWrite: 'The monitor brightness could not be written.',
  errScheduleUnavailable: 'The configured schedule is unavailable.',
  errScheduleFailed: 'The schedule could not be updated.',
  errStateFailed: 'The state could not be saved.',
  errUnsafePath: 'The saved data path is not safe.',
  errIoError: 'The saved data could not be read or written.',
  errNotExecutable: 'The control helper is not executable.',
  errMissingCommand: 'A required system command is missing.',
  errTimeout: 'The command timed out.',
  errBackendUnavailable: 'The control backend is unavailable.',
  errDeadline: 'The operation deadline was exceeded.',
  errCancelled: 'The operation was cancelled.',
  errSnoozeFailed: 'The snooze could not be applied.',
  errReconcileFailed: 'The schedule could not be reconciled.',
  errApplyFailed: 'The night light could not be applied.',
  errReadFailed: 'The current state could not be read.',
  errNativeFailure: 'The native operation could not be completed.',
  errScheduleConflict: 'The schedule file changed during the operation.',
  manualPersistError: 'The manual setting was applied, but the preference could not be saved; the schedule may revert it on its next cycle.',
  // Misc.
  monitor: 'Monitor',
  focusedMonitor: 'Focused monitor',
  working: 'Applying…',
  minutesShort: 'min',
  keyboardHints: '← →\u00A0adjust / switch\u00A0view · ↑ ↓\u00A0move · Enter\u00A0activate · Esc\u00A0close'
};

var es = {
  heroTitle: 'Luz nocturna',
  brightness: 'Brillo',
  temperature: 'Temperatura',
  gamma: 'Gamma (brillo percibido)',
  gammaShort: 'Gamma',
  schedule: 'Horario',
  save: 'Guardar cambios',
  saved: 'Cambios guardados',
  unavailable: 'No disponible',
  notConfirmed: 'Estado no confirmado',
  enabled: 'Activada',
  disabled: 'Color natural',
  manualOverride: 'Anulación manual',
  start: 'Inicio',
  end: 'Fin',
  cancel: 'Cancelar',
  routeHome: 'Inicio',
  routeAutomation: 'Automatización',
  routeSettings: 'Ajustes',
  provenanceAutomatic: 'Automática',
  provenanceManual: 'Manual',
  provenancePreset: 'Perfil',
  provenanceSnooze: 'Posposición',
  provenanceUnknown: 'Desconocido',
  dayPeriod: 'Día',
  nightPeriod: 'Noche',
  scheduleDayTimeFormat: 'La hora diurna debe usar el formato HH:MM',
  scheduleNightTimeFormat: 'La hora nocturna debe usar el formato HH:MM',
  scheduleDayNightEqual: 'Las horas de día y noche deben ser diferentes',
  scheduleDayTemperatureRange: 'La temperatura diurna debe estar entre 5900 y 6500 K',
  scheduleNightTemperatureRange: 'La temperatura nocturna debe estar entre 2500 y 5000 K',
  scheduleBrightnessRange: 'El brillo debe estar entre 1 y 100 %',
  scheduleGammaRange: 'La gamma debe estar entre 0 y 100 %',
  snoozeTitle: 'Posposición',
  snoozeSet: 'Posponer',
  snoozeClear: 'Cancelar posposición',
  snoozeStatusActive: 'Pospuesta',
  unitHours: 'Horas',
  unitMinutes: 'Minutos',
  unitSeconds: 'Segundos',
  sunset: 'Atardecer',
  quickSnooze: 'Posposición rápida',
  settingsTitle: 'Ajustes',
  language: 'Idioma',
  shortcut: 'Acceso directo',
  shortcutKeys: 'Teclas',
  shortcutInstall: 'Instalar',
  shortcutRemove: 'Quitar',
  spanish: 'Español',
  english: 'English',
  errHelperMissing: 'No se pudo iniciar el asistente de control.',
  errBrightnessUnavailable: 'El brillo no está disponible en este momento.',
  errNightlightUnavailable: 'La luz nocturna no está disponible.',
  errMonitorUnavailable: 'El monitor seleccionado no está disponible.',
  errScheduleInvalid: 'El horario configurado no es válido.',
  errSnoozeInvalid: 'La posposición solicitada no es válida.',
  errHistoryUnreadable: 'No se pudo leer el historial.',
  errSettingsWrite: 'No se pudieron guardar los ajustes.',
  errShortcutWrite: 'No se pudo actualizar el acceso directo.',
  errUnknown: 'Se produjo un error desconocido.',
  errInvalidValue: 'El valor solicitado no es válido.',
  errInvalidJson: 'Los datos guardados no tienen un formato válido.',
  errInvalidConfig: 'La configuración guardada no es válida.',
  errInvalidState: 'El estado guardado no es válido.',
  errInvalidHistory: 'El historial guardado no es válido.',
  errReadbackFailed: 'No se pudo confirmar el cambio.',
  errBrightnessWrite: 'No se pudo escribir el brillo del monitor.',
  errScheduleUnavailable: 'El horario configurado no está disponible.',
  errScheduleFailed: 'No se pudo actualizar el horario.',
  errStateFailed: 'No se pudo guardar el estado.',
  errUnsafePath: 'La ruta de datos guardados no es segura.',
  errIoError: 'No se pudieron leer o escribir los datos guardados.',
  errNotExecutable: 'El asistente de control no es ejecutable.',
  errMissingCommand: 'Falta un comando necesario del sistema.',
  errTimeout: 'Se agotó el tiempo de espera del comando.',
  errBackendUnavailable: 'El backend de control no está disponible.',
  errDeadline: 'Se superó el plazo de la operación.',
  errCancelled: 'La operación fue cancelada.',
  errSnoozeFailed: 'No se pudo aplicar la posposición.',
  errReconcileFailed: 'No se pudo reconciliar el horario.',
  errApplyFailed: 'No se pudo aplicar la luz nocturna.',
  errReadFailed: 'No se pudo leer el estado actual.',
  errNativeFailure: 'La operación nativa no se pudo completar.',
  errScheduleConflict: 'El archivo de horario cambió durante la operación.',
  manualPersistError: 'El ajuste manual se aplicó, pero no se pudo guardar la preferencia; el horario podría revertirlo al próximo ciclo.',
  monitor: 'Monitor',
  focusedMonitor: 'Monitor enfocado',
  working: 'Aplicando…',
  minutesShort: 'min',
  keyboardHints: '← →\u00A0ajustar / cambiar\u00A0vista · ↑ ↓\u00A0moverse · Enter\u00A0activar · Esc\u00A0cerrar'
};

var KEYS = (function () {
  var combined = {};
  var key;
  for (key in en) combined[key] = true;
  for (key in es) combined[key] = true;
  return Object.keys(combined);
})();

// QML-facing semantic aliases. Dictionaries keep the established camelCase
// contract while the panel uses stable snake_case action keys.
var ALIASES = {
  home: 'routeHome', automation: 'routeAutomation', settings: 'routeSettings',
  night_light: 'heroTitle', manual_override: 'manualOverride',
  focused_monitor: 'focusedMonitor', monitor: 'monitor',
  day_period: 'dayPeriod', night_period: 'nightPeriod',
  snooze: 'snoozeTitle', snooze_set: 'snoozeSet', clear_snooze: 'snoozeClear',
  snooze_active: 'snoozeStatusActive', minutes_short: 'minutesShort',
  unit_hours: 'unitHours', unit_minutes: 'unitMinutes', unit_seconds: 'unitSeconds',
  sunset: 'sunset', quick_snooze: 'quickSnooze',
  cancel: 'cancel', language: 'language', spanish: 'spanish', english: 'english',
  shortcut: 'shortcut', shortcut_keys: 'shortcutKeys', install_shortcut: 'shortcutInstall',
  remove_shortcut: 'shortcutRemove', working: 'working',
  gamma_short: 'gammaShort',
  keyboard_hints: 'keyboardHints', unknown: 'provenanceUnknown',
  origin_automatic: 'provenanceAutomatic', origin_manual: 'provenanceManual',
  origin_preset: 'provenancePreset', origin_snooze: 'provenanceSnooze',
  origin_unknown: 'provenanceUnknown', not_confirmed: 'notConfirmed'
};

// Canonical keys the panel addresses without an alias.
var CANONICAL_PASSTHROUGH = [
  'brightness', 'temperature', 'gamma', 'schedule', 'save', 'saved',
  'unavailable', 'start', 'end', 'sunset'
];

function locales() {
  return LOCALES.slice();
}

function defaultLocale() {
  return DEFAULT_LOCALE;
}

function hasLocale(locale) {
  return locale === 'en' || locale === 'es';
}

function resolveLocale(locale) {
  return hasLocale(locale) ? locale : DEFAULT_LOCALE;
}

function dictionary(locale) {
  return resolveLocale(locale) === 'es' ? es : en;
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

function resolveKey(key) {
  if (hasOwn(ALIASES, key)) return ALIASES[key];
  if (hasOwn(en, key) || hasOwn(es, key)) return key;
  return key;
}

// Locale-aware lookup with a strict fallback chain: requested dictionary, then
// the default (en), then es, then the raw key itself. Unknown locales resolve
// to `en`.
function t(key, locale) {
  key = resolveKey(key);
  var resolved = resolveLocale(locale);
  var primary = resolved === 'es' ? es : en;
  if (hasOwn(primary, key)) return primary[key];
  if (resolved !== 'es' && hasOwn(es, key)) return es[key];
  if (resolved !== 'en' && hasOwn(en, key)) return en[key];
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
    resolveKey: resolveKey,
    t: t
  };
}
