var ICONS = {
  weatherSunny: '󰖙',      // nf-md-weather_sunny (U+F0599)
  weatherNight: '󰖔',      // nf-md-weather_night (U+F0594)
  brightness: '󰃟',        // nf-md-brightness_6 (U+F00DF)
  temperature: '󰔏',       // nf-md-thermometer (U+F050F)
  gamma: '󰆃',             // nf-md-contrast_box (U+F0183)
  schedule: '󰃰',          // nf-md-calendar_clock (U+F00F0)
  snooze: '󰒲',            // nf-md-sleep (U+F04B2)
  chevronLeft: '󰅁',       // nf-md-chevron_left (U+F0141)
  chevronRight: '󰅂',      // nf-md-chevron_right (U+F0142)
  chevronUp: '󰅃',         // nf-md-chevron_up (U+F0143)
  chevronDown: '󰅀',       // nf-md-chevron_down (U+F0140)
  check: '󰄬',             // nf-md-check (U+F012C)
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
  var available = input.nightlight && typeof input.nightlight === 'object'
    ? input.nightlight.available === true
    : input.available === true;
  if (!available) return ICONS.unavailable;
  if (input.enabled === true) return automation.origin === 'preset' ? ICONS.palette : ICONS.weatherSunny;
  // An idle night light uses the moon; availability failures use their own glyph.
  return ICONS.weatherNight;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    ICONS: ICONS,
    glyph: glyph,
    glyphForState: glyphForState
  };
}
