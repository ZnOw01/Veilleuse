import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const iconsJs = fs.readFileSync(new URL('../Icons.js', import.meta.url), 'utf8');
const nerdIconQml = fs.readFileSync(new URL('../NerdIcon.qml', import.meta.url), 'utf8');
const { ICONS, glyph, glyphForState } = await import('../Icons.js');

test('Icons.js exports all canonical Material Design Icons (nf-md-*)', () => {
  assert.ok(ICONS && typeof ICONS === 'object');
  const expectedKeys = [
    'weatherSunny', 'weatherSunset', 'weatherNight', 'themeLightDark',
    'brightness', 'temperature', 'gamma', 'contrast',
    'monitor', 'keyboard', 'schedule', 'clock', 'timer', 'snooze',
    'settings', 'language', 'chevronLeft', 'chevronRight',
    'save', 'check', 'close', 'disabled', 'unavailable', 'alert', 'palette'
  ];
  for (const key of expectedKeys) {
    assert.ok(key in ICONS, `ICONS must include ${key}`);
    const char = ICONS[key];
    assert.equal(typeof char, 'string');
    assert.equal([...char].length, 1, `${key} must be a single unicode character`);
    assert.ok(char.codePointAt(0) >= 0xf0000, `${key} must be in the Nerd Fonts Private Use Area (>= 0xF0000)`);
  }
});

test('glyph helper returns the requested icon or empty string', () => {
  assert.equal(glyph('weatherSunny'), ICONS.weatherSunny);
  assert.equal(glyph('nonExistentIcon'), '');
});

test('glyphForState returns the correct glyph per system state', () => {
  assert.equal(glyphForState({ automation: { snoozed: true } }), ICONS.snooze);
  assert.equal(glyphForState({ available: false }), ICONS.unavailable);
  assert.equal(glyphForState({ available: true, enabled: true, automation: { origin: 'preset' } }), ICONS.palette);
  assert.equal(glyphForState({ available: true, enabled: true, automation: { origin: 'schedule' } }), ICONS.weatherSunny);
  // Off reads as a dimmable night glyph, never as the close-circle error
  // icon: an off light is a state, not a fault.
  assert.equal(glyphForState({ available: true, enabled: false, automation: { schedule_enabled: false } }), ICONS.weatherNight);
  assert.equal(glyphForState({ available: true, enabled: false, automation: { schedule_enabled: true } }), ICONS.weatherNight);
});

test('NerdIcon.qml conforms to Omarchy Quattro tokenized icon contract', () => {
  assert.match(nerdIconQml, /property string glyph:\s*""/);
  assert.match(nerdIconQml, /property color iconColor:\s*Color\.foreground/);
  assert.match(nerdIconQml, /property real iconSize:\s*Style\.font\.icon/);
  assert.match(nerdIconQml, /font\.family:\s*fontFamily/);
  assert.match(nerdIconQml, /font\.pixelSize:\s*iconSize/);
});
