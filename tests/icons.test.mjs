import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const panelQml = fs.readFileSync(new URL('../Panel.qml', import.meta.url), 'utf8');
const iconsJs = fs.readFileSync(new URL('../Icons.js', import.meta.url), 'utf8');
const nerdIconQml = fs.readFileSync(new URL('../NerdIcon.qml', import.meta.url), 'utf8');
const { ICONS, glyph, glyphForState } = await import('../Icons.js');

test('Icons.js exports only active Nerd Fonts glyphs with valid PUA codepoints', () => {
  assert.ok(ICONS && typeof ICONS === 'object');
  const expectedKeys = [
    'weatherSunny', 'weatherNight', 'brightness', 'temperature', 'gamma',
    'schedule', 'snooze', 'chevronLeft', 'chevronRight', 'chevronUp', 'chevronDown', 'check',
    'unavailable', 'alert', 'palette'
  ];
  assert.deepEqual(Object.keys(ICONS).sort(), expectedKeys.slice().sort());
  for (const key of expectedKeys) {
    const char = ICONS[key];
    assert.equal(typeof char, 'string');
    assert.equal([...char].length, 1, `${key} must be a single unicode character`);
    assert.ok(char.codePointAt(0) >= 0xf0000, `${key} must be in the Nerd Fonts Private Use Area (>= 0xF0000)`);
    const usedInPanel = panelQml.includes(`Icons.glyph("${key}")`);
    const usedInHelper = iconsJs.includes(`ICONS.${key}`);
    assert.ok(usedInPanel || usedInHelper, `${key} must be referenced in UI or Icons module`);
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
  assert.equal(glyphForState({ available: true, enabled: false, automation: { schedule_enabled: false } }), ICONS.weatherNight);
  assert.equal(glyphForState({ available: true, enabled: false, automation: { schedule_enabled: true } }), ICONS.weatherNight);
  assert.equal(glyphForState(null), ICONS.unavailable);
  assert.equal(glyphForState({}), ICONS.unavailable);
  assert.equal(glyphForState({ available: false, automation: { snoozed: true } }), ICONS.snooze);
  assert.equal(
    glyphForState({ available: false, enabled: true, brightness: { available: false }, nightlight: { available: true } }),
    ICONS.weatherSunny
  );
  assert.equal(
    glyphForState({ available: false, enabled: true, nightlight: { available: false } }),
    ICONS.unavailable
  );
});

test('NerdIcon.qml conforms to Omarchy Quattro tokenized icon contract', () => {
  assert.match(nerdIconQml, /property string glyph:\s*""/);
  assert.match(nerdIconQml, /property color iconColor:\s*Color\.foreground/);
  assert.match(nerdIconQml, /property real iconSize:\s*Style\.font\.icon/);
  assert.match(nerdIconQml, /font\.family:\s*fontFamily/);
  assert.match(nerdIconQml, /font\.pixelSize:\s*iconSize/);
  assert.match(nerdIconQml, /duration:\s*Style\.duration\(160\)/);
});
