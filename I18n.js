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
  errPresetFailed: 'No se pudo aplicar el perfil.',
  errDeadline: 'Se superó el plazo de la operación.',
  errCancelled: 'La operación fue cancelada.',
  errSnoozeFailed: 'No se pudo aplicar la posposición.',
  errTransitionFailed: 'No se pudo completar la transición.',
  errReconcileFailed: 'No se pudo reconciliar el horario.',
  errApplyFailed: 'No se pudo aplicar la luz nocturna.',
  errReadFailed: 'No se pudo leer el estado actual.',
  errNativeFailure: 'La operación nativa no se pudo completar.',
  errScheduleConflict: 'El archivo de horario cambió durante la operación.',
  scheduleDayTimeFormat: 'La hora diurna debe usar el formato HH:MM',
  scheduleNightTimeFormat: 'La hora nocturna debe usar el formato HH:MM',
  scheduleDayNightEqual: 'Las horas de día y noche deben ser diferentes',
  scheduleDayTemperatureRange: 'La temperatura diurna debe estar entre 5900 y 6500 K',
  scheduleNightTemperatureRange: 'La temperatura nocturna debe estar entre 2500 y 5000 K',
  // Presets.
  presetTitle: 'Perfiles',
  presetApply: 'Aplicar',
  presetDelete: 'Eliminar',
  presetSave: 'Guardar perfil',
  presetAll: 'Todos los perfiles',
  presetBuiltIn: 'Integrado',
  presetName: 'Nombre del perfil',
  saveCurrentPreset: 'Guardar actual',
  deleteCustomPreset: 'Eliminar perfil',
  presetReading: 'Lectura',
  presetWork: 'Trabajo',
  presetCinema: 'Cine',
  focusedMonitor: 'Monitor enfocado',
  monitor: 'Monitor',
  lastApplied: 'Última aplicación',
  openAutomation: 'Editar automatización',
  scheduleEnabled: 'Horario activo',
  scheduleDisabled: 'Horario pausado',
  transitionTitle: 'Transición',
  seconds: 'segundos',
  snooze30: '30 minutos',
  snooze120: '2 horas',
  editSchedule: 'Editar horario',
  cancel: 'Cancelar',
  spanish: 'Español',
  english: 'English',
  runPreflight: 'Comprobar disponibilidad',
  shortcutKeys: 'Teclas',
  liveNow: 'Ahora',
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
  errPresetFailed: 'The preset could not be applied.',
  errDeadline: 'The operation deadline was exceeded.',
  errCancelled: 'The operation was cancelled.',
  errSnoozeFailed: 'The snooze could not be applied.',
  errTransitionFailed: 'The transition could not be completed.',
  errReconcileFailed: 'The schedule could not be reconciled.',
  errApplyFailed: 'The night light could not be applied.',
  errReadFailed: 'The current state could not be read.',
  errNativeFailure: 'The native operation could not be completed.',
  errScheduleConflict: 'The schedule file changed during the operation.',
  scheduleDayTimeFormat: 'Day time must use the HH:MM format',
  scheduleNightTimeFormat: 'Night time must use the HH:MM format',
  scheduleDayNightEqual: 'Day and night times must be different',
  scheduleDayTemperatureRange: 'Day temperature must be between 5900 and 6500 K',
  scheduleNightTemperatureRange: 'Night temperature must be between 2500 and 5000 K',
  presetTitle: 'Presets',
  presetApply: 'Apply',
  presetDelete: 'Delete',
  presetSave: 'Save preset',
  presetAll: 'All presets',
  presetBuiltIn: 'Built-in',
  presetName: 'Preset name',
  saveCurrentPreset: 'Save current',
  deleteCustomPreset: 'Delete preset',
  presetReading: 'Reading',
  presetWork: 'Work',
  presetCinema: 'Cinema',
  focusedMonitor: 'Focused monitor',
  monitor: 'Monitor',
  lastApplied: 'Last applied',
  openAutomation: 'Edit automation',
  scheduleEnabled: 'Schedule on',
  scheduleDisabled: 'Schedule paused',
  transitionTitle: 'Transition',
  seconds: 'seconds',
  snooze30: '30 minutes',
  snooze120: '2 hours',
  editSchedule: 'Edit schedule',
  cancel: 'Cancel',
  spanish: 'Español',
  english: 'English',
  runPreflight: 'Check availability',
  shortcutKeys: 'Keys',
  liveNow: 'Now',
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

// QML-facing semantic aliases. Dictionaries keep the established camelCase
// contract while the panel uses stable snake_case action keys.
var ALIASES = {
  home: 'routeHome', automation: 'routeAutomation', settings: 'routeSettings',
  night_light: 'heroTitle', period_day: 'periodDay', period_night: 'periodNight',
  manual_override: 'manualOverride', presets: 'presetTitle',
  preset_reading: 'presetReading', preset_work: 'presetWork', preset_cinema: 'presetCinema',
  preset_name: 'presetName', save_current_preset: 'saveCurrentPreset', delete_custom_preset: 'deleteCustomPreset',
  focused_monitor: 'focusedMonitor', monitor: 'monitor', last_applied: 'lastApplied',
  history: 'historyTitle', open_automation: 'openAutomation',
  schedule_enabled: 'scheduleEnabled', schedule_disabled: 'scheduleDisabled',
  transition: 'transitionTitle', seconds: 'seconds', snooze: 'snoozeTitle',
  snooze_30: 'snooze30', snooze_120: 'snooze120', until_tomorrow: 'snoozeUntilTomorrow',
  clear_snooze: 'snoozeClear', midnight_explanation: 'midnightExplanation',
  edit_schedule: 'editSchedule', natural_day: 'naturalDay',
  day_temperature: 'scheduleDayTemperature', night_temperature: 'scheduleTemperature',
  cancel: 'cancel', language: 'language', spanish: 'spanish', english: 'english',
  apply_scope: 'applyScope', session: 'applyScopeSession', persistent: 'applyScopePersistent',
  default_preset: 'defaultPreset', preflight: 'preflightTitle', run_preflight: 'runPreflight',
  shortcut: 'shortcut', shortcut_keys: 'shortcutKeys', install_shortcut: 'shortcutInstall',
  remove_shortcut: 'shortcutRemove', live_now: 'liveNow', unknown: 'provenanceUnknown',
  origin_automatic: 'provenanceAutomatic', origin_manual: 'provenanceManual',
  origin_preset: 'provenancePreset', origin_snooze: 'provenanceSnooze',
  origin_unknown: 'provenanceUnknown', not_confirmed: 'notConfirmed'
};

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

function resolveKey(key) {
  return ALIASES[key] || key;
}

// Locale-aware lookup with a strict fallback chain: requested dictionary, then
// en, then es, then the raw key itself. Unknown locales resolve to `es`.
function t(key, locale) {
  key = resolveKey(key);
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
    resolveKey: resolveKey,
    t: t
  };
}
