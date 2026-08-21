// Icons.js — Centralized Nerd Fonts (Material Design Icons nf-md-*) codepoints
// for the Veilleuse plugin (Omarchy Quattro / Quickshell).
//
// Uses current Nerd Fonts v3 Material Design Icons (nf-md-*) codepoints.

var ICONS = {
  // Weather / Sun / Moon (Night Light)
  weatherSunny: '󰖙',      // nf-md-weather_sunny (U+F0599)
  weatherSunset: '󰖘',     // nf-md-weather_sunset (U+F0598)
  weatherNight: '󰖔',      // nf-md-weather_night (U+F0594)
  themeLightDark: '󰔔',    // nf-md-theme_light_dark (U+F0514)

  // Controls & Adjustments
  brightness: '󰃟',        // nf-md-brightness_6 (U+F00DF)
  temperature: '󰔏',       // nf-md-thermometer (U+F050F)
  gamma: '󰆃',             // nf-md-contrast_box (U+F0183)
  contrast: '󰆂',          // nf-md-contrast (U+F0182)

  // Devices & Hardware
  monitor: '󰍹',           // nf-md-monitor (U+F0379)
  keyboard: '󰹴',          // nf-md-keyboard_outline (U+F0E74)

  // Automation & Time
  schedule: '󰃰',          // nf-md-calendar_clock (U+F00F0)
  clock: '󰅐',             // nf-md-clock_outline (U+F0150)
  timer: '󰔛',             // nf-md-timer_outline (U+F051B)
  snooze: '󰒲',            // nf-md-sleep (U+F04B2)

  // Settings & Internationalization
  settings: '󰒓',          // nf-md-cog (U+F0493)
  language: '󰗊',          // nf-md-translate (U+F05CA)

  // Navigation
  chevronLeft: '󰅁',       // nf-md-chevron_left (U+F0141)
  chevronRight: '󰅂',      // nf-md-chevron_right (U+F0142)

  // Actions & States
  save: '󰆓',              // nf-md-content_save (U+F0193)
  check: '󰄬',             // nf-md-check (U+F012C)
  close: '󰅖',             // nf-md-close (U+F0156)
  disabled: '󰅙',          // nf-md-close_circle_outline (U+F0159)
  unavailable: '󰌙',       // nf-md-link_variant_off (U+F0319)
  alert: '󰗖',             // nf-md-alert_circle_outline (U+F05D6)
  palette: '󰏘'            // nf-md-palette (U+F03D8)
};

function glyph(name) {
  return ICONS[name] || '';
}

function glyphForState(value) {
  var input = value || {};
  var automation = input.automation || {};
  if (automation.snoozed === true) return ICONS.snooze;
  if (input.available !== true) return ICONS.unavailable;
  if (input.enabled === true) return automation.origin === 'preset' ? ICONS.palette : ICONS.weatherSunny;
  // Off is a state, not a fault: the moon reads as "night light idle".
  // The close-circle glyph stays reserved for genuinely broken states.
  return ICONS.weatherNight;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    ICONS: ICONS,
    glyph: glyph,
    glyphForState: glyphForState
  };
}
