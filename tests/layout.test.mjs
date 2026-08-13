import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const qml = fs.readFileSync(new URL('../Panel.qml', import.meta.url), 'utf8');
const barQml = fs.readFileSync(new URL('../BarWidget.qml', import.meta.url), 'utf8');
const i18n = fs.readFileSync(new URL('../I18n.js', import.meta.url), 'utf8');
const helper = fs.readFileSync(new URL('../scripts/veilleuse-control', import.meta.url), 'utf8');
const workflow = fs.readFileSync(new URL('../.github/workflows/checks.yml', import.meta.url), 'utf8');
const manifest = JSON.parse(fs.readFileSync(new URL('../manifest.json', import.meta.url), 'utf8'));
const schedule = qml.slice(qml.indexOf('id: scheduleColumn'));

test('community plugin id is lowercase and consistent across entry points', () => {
  assert.equal(manifest.id, manifest.id.toLowerCase());
  assert.ok(qml.includes(`moduleName: "${manifest.id}"`));
  assert.ok(qml.includes(`ipcTarget: "${manifest.id}"`));
  assert.ok(barQml.includes(`moduleName: "${manifest.id}"`));
  assert.ok(helper.includes(`PLUGIN_ID = "${manifest.id}"`));
  assert.ok(workflow.includes(`manifest["id"] == "${manifest.id}"`));
});

test('slider handlers declare signal parameters explicitly', () => {
  assert.equal((qml.match(/onMoved:\s*function\(v\)\s*\{/g) || []).length, 3);
  assert.doesNotMatch(qml, /onMoved:\s*root\./);
});

test('schedule editor uses native vertically centered fields', () => {
  assert.equal((schedule.match(/\bTextField\s*\{/g) || []).length, 2);
  assert.equal((schedule.match(/\bNumberField\s*\{/g) || []).length, 2);
  assert.match(schedule, /text:\s*root\.text\("natural_day"\)/);
  assert.match(schedule, /id:\s*naturalDayEditor/);
  assert.equal((schedule.match(/\bTextInput\s*\{/g) || []).length, 0);
});

test('natural-day switch owns its value and is keyboard operable', () => {
  const start = schedule.indexOf('id: naturalDayEditor');
  const end = schedule.indexOf('\n                                Column {', start);
  const toggle = schedule.slice(start, end);
  assert.doesNotMatch(toggle, /\bfocusable\s*:/);
  assert.match(toggle, /onToggled:\s*root\.editNaturalDay\s*=\s*!root\.editNaturalDay/);
  assert.match(toggle, /Keys\.onReturnPressed:\s*root\.editNaturalDay\s*=\s*!root\.editNaturalDay/);
  assert.match(toggle, /Keys\.onSpacePressed:\s*root\.editNaturalDay\s*=\s*!root\.editNaturalDay/);
});

test('schedule editor exposes the day and night temperature bounds and both identity flags', () => {
  assert.match(schedule, /id:\s*dayTemperatureEditor[\s\S]*?from:\s*5900[\s\S]*?to:\s*6500/);
  assert.match(schedule, /id:\s*scheduleTemperatureEditor[\s\S]*?from:\s*2500[\s\S]*?to:\s*5000/);
  assert.match(qml, /--day-temp/, 'queueSchedule sends the edited day temperature');
  assert.match(qml, /--natural-day/);
  assert.match(qml, /--no-natural-day/);
});

test('schedule controls share full width and the save label is centered', () => {
  assert.match(schedule, /id:\s*startEditor[\s\S]*?width:\s*parent\.width/);
  assert.match(schedule, /id:\s*endEditor[\s\S]*?width:\s*parent\.width/);
  assert.match(schedule, /id:\s*scheduleTemperatureEditor[\s\S]*?fieldWidth:\s*parent\.width/);
  assert.match(schedule, /text:\s*root\.text\("save"\)[\s\S]*?width:\s*parent\.width[\s\S]*?leftAlign:\s*false/);
});

test('value column width is a single Style.space(54) token', () => {
  assert.match(qml, /readonly\s+property\s+real\s+valueColumnWidth:\s*Style\.space\(54\)/);
});

test('value texts share valueColumnWidth and align right', () => {
  const brightness = qml.slice(qml.indexOf('id: brightnessRow'), qml.indexOf('id: temperatureRow'));
  const temperature = qml.slice(qml.indexOf('id: temperatureRow'), qml.indexOf('id: gammaRow'));
  const gamma = qml.slice(qml.indexOf('id: gammaRow'), qml.indexOf('id: scheduleSurface'));

  for (const section of [brightness, temperature, gamma]) {
    assert.match(section, /width:\s*root\.valueColumnWidth/);
    assert.match(section, /horizontalAlignment:\s*Text\.AlignRight/);
    assert.match(section, /PanelSlider\s*\{[\s\S]*?width:\s*parent\.width\s*-\s*root\.valueColumnWidth\s*-\s*Style\.spacing\.controlGap/);
  }
});

test('value column width has a single source of truth', () => {
  assert.equal((qml.match(/Style\.space\(42\)/g) || []).length, 0);
  assert.equal((qml.match(/Style\.space\(54\)/g) || []).length, 1);
  const occurrences = qml.match(/valueColumnWidth/g);
  assert.equal(occurrences ? occurrences.length : 0, 7);
});

test('lastError text gets the same horizontal padding as the rows', () => {
  const start = qml.indexOf('visible: root.errorText !== ""');
  const end = qml.indexOf('PanelSeparator {', start);
  const err = qml.slice(start, end + 'PanelSeparator {'.length);

  assert.match(err, /anchors\.leftMargin:\s*Style\.spacing\.rowPaddingX/);
  assert.match(err, /anchors\.rightMargin:\s*Style\.spacing\.rowPaddingX/);
  assert.doesNotMatch(err, /visible:\s*root\.lastError !== ""\s*&&\s*!root\.scheduleExpanded/);
});

test('payload and state errors remain visible while the editor is expanded', () => {
  assert.match(qml, /payload\.error/);
  assert.match(qml, /state\.error/);
  assert.match(qml, /visible:\s*root\.errorText !== ""/);
  assert.doesNotMatch(qml, /visible:\s*root\.errorText !== ""\s*&&\s*!root\.scheduleExpanded/);
});

test('successful schedule saves render short-lived feedback', () => {
  assert.match(qml, /property string feedbackText/);
  assert.match(qml, /Timer\s*\{[\s\S]*?id:\s*feedbackTimer/);
  assert.match(qml, /feedbackTimer\.restart\(\)/);
  assert.match(qml, /text:\s*root\.feedbackText/);
});

test('hero shows the scheduled period and only conditional manual override', () => {
  assert.match(qml, /state\.schedule\.period/);
  assert.match(qml, /Model\.isManualOverride\(root\.state\)/);
  assert.match(qml, /root\.text\("manual_override"\)/);
});

test('temperature slider is live across the full 2500..6500 range', () => {
  const temperature = qml.slice(qml.indexOf('id: temperatureRow'), qml.indexOf('id: gammaRow'));
  assert.match(temperature, /minimum:\s*2500/);
  assert.match(temperature, /maximum:\s*6500/);
  assert.match(temperature, /onMoved:\s*function\(v\)/);
});

test('bar activity follows actual night-light state without depending on panel visibility', () => {
  assert.match(barQml, /readonly property bool lightActive/);
  assert.match(barQml, /state\.enabled/);
  assert.match(barQml, /active:\s*root\.lightActive/);
  assert.doesNotMatch(barQml, /active:\s*root\.opened/);
});

test('closed panel refreshes status so scheduled bar activity cannot stay stale', () => {
  assert.match(qml, /id:\s*backgroundStatusTimer[\s\S]*?interval:\s*30000[\s\S]*?repeat:\s*true/);
  assert.match(qml, /running:\s*!root\.opened/);
  assert.match(qml, /onTriggered:\s*if\s*\(!root\.actionPending\)\s*root\.requestStatus\(\)/);
});

test('schedule summary stays a full-width left-aligned button like the reference', () => {
  const start = qml.indexOf('id: scheduleColumn');
  const summary = qml.slice(start, qml.indexOf('Column {', start));

  assert.match(summary, /Button\s*\{\s*visible:\s*!root\.scheduleExpanded/);
  assert.match(summary, /width:\s*parent\.width/);
  assert.match(summary, /leftAlign:\s*true/);
});

test('expanded schedule keeps vertical cursor movement in the schedule section', () => {
  assert.match(qml, /cursor\s*=\s*Model\.moveCursor\(cursor, key, root\.scheduleExpanded\)/);
});

test('schedule editors return focus before Escape can close the panel', () => {
  assert.match(qml, /function handleCloseRequested\(\)\s*\{[\s\S]*?if \(scheduleExpanded\)[\s\S]*?scheduleExpanded\s*=\s*false;[\s\S]*?keyCatcher\.forceActiveFocus\(\);[\s\S]*?return ;[\s\S]*?root\.close\(\);/);

  const editor = schedule.slice(schedule.indexOf('id: scheduleTemperatureEditor'));
  assert.match(editor, /field\.Keys\.onPressed:\s*function\(event\)\s*\{[\s\S]*?Qt\.Key_Escape[\s\S]*?root\.leaveScheduleEditor\(scheduleTemperatureEditor\.field,\s*4\)[\s\S]*?Qt\.Key_Return[\s\S]*?root\.leaveScheduleEditor\(scheduleTemperatureEditor\.field,\s*5\)/);
});

test('v2 panel exposes three native routes and route navigation preserves context', () => {
  assert.match(qml, /property string route:\s*"home"/);
  assert.match(qml, /routeOptions|routeOrder/);
  assert.match(i18n, /routeHome:\s*'Home'/);
  assert.match(i18n, /routeAutomation:\s*'Automation'/);
  assert.match(i18n, /routeSettings:\s*'Settings'/);
  assert.match(qml, /function navigateToRoute\(/);
  assert.doesNotMatch(qml, /state\s*=\s*Model\.normalizeState\(\{\s*\}\)\s*;\s*route/);
});

test('home route has live controls, presets, monitor selection, provenance, history, and direct automation navigation', () => {
  assert.match(qml, /id:\s*homeRoute/);
  assert.match(qml, /id:\s*heroGlyph/);
  assert.match(qml, /automationOrigin|last_applied/);
  assert.match(qml, /preset list|presetList|presets/);
  assert.match(qml, /SearchableDropdown|Dropdown/);
  assert.match(qml, /history.*list|\["history",\s*"list"\]/s);
  assert.match(qml, /navigateToRoute\("automation"\)/);
  assert.match(barQml, /heroGlyph|provenance|origin/);
});

test('automation route exposes schedule toggle, context-preserving editor, midnight explanation, transition, and snooze commands', () => {
  assert.match(qml, /id:\s*automationRoute/);
  assert.match(qml, /schedule_enabled/);
  assert.match(qml, /\["schedule",\s*enabled \? "enable" : "disable"\]/);
  assert.match(qml, /midnight|midnightExplanation|crossesMidnight/);
  assert.match(qml, /\["transition",\s*"--temperature"/);
  assert.match(qml, /snooze set|until-tomorrow|snooze clear/);
  assert.match(qml, /scheduleEditorOpen|scheduleExpanded/);
});

test('settings route persists only native inline settings and exposes preflight and explicit shortcut actions', () => {
  assert.match(qml, /id:\s*settingsRoute/);
  assert.match(qml, /updateEntryInline/);
  assert.match(qml, /locale/);
  assert.match(qml, /applyScope|session.*persistent|persistent.*session/);
  assert.match(qml, /default-preset/);
  assert.match(qml, /preflight/);
  assert.match(qml, /settingsCommand\("shortcut",\s*\["install"/);
  assert.match(qml, /settingsCommand\("shortcut",\s*\["remove"/);
  assert.match(qml, /shortcutKeys|SAFE_KEYS/);
});

test('v2 actions use helper commands, native scrolling, and keyboard-visible native controls', () => {
  assert.match(qml, /function issue\(/);
  assert.match(qml, /new Process|Process\s*\{/);
  assert.match(qml, /Flickable\s*\{/);
  assert.match(qml, /PanelKeyCatcher\s*\{/);
  assert.match(qml, /ToggleSwitch\s*\{/);
  assert.match(qml, /Button\s*\{/);
  assert.match(qml, /PanelSlider\s*\{/);
  assert.match(qml, /Dropdown|SearchableDropdown/);
  assert.doesNotMatch(qml, /onClicked:\s*\{\s*\/\/\s*(TODO|fake|placeholder)/i);
});

test('bar glyph and tooltip are dynamic and expose live provenance', () => {
  assert.match(barQml, /readonly property string barGlyph/);
  assert.match(barQml, /readonly property string barTooltip/);
  assert.match(barQml, /state\.automation|state\.schedule|state\.origin/);
  assert.match(barQml, /text:\s*root\.barGlyph/);
  assert.match(barQml, /tooltipText:\s*root\.barTooltip/);
});

test('i18n module has complete Spanish and English key parity', () => {
  const es = [...i18n.matchAll(/var es = \{([\s\S]*?)\n\};/g)][0][1];
  const en = [...i18n.matchAll(/var en = \{([\s\S]*?)\n\};/g)][0][1];
  const keys = source => [...source.matchAll(/^\s*([A-Za-z0-9_]+):/gm)].map(match => match[1]).sort();
  assert.deepEqual(keys(es), keys(en));
  assert.match(i18n, /function t\(key, locale\)/);
});

test('every translated QML key resolves in Spanish and English', async () => {
  const I18n = await import('../I18n.js');
  const used = [...qml.matchAll(/(?:root\.)?text\("([^"]+)"\)/g)].map(match => match[1]);
  for (const key of new Set(used)) {
    const resolved = I18n.resolveKey(key);
    assert.ok(Object.hasOwn(I18n.es, resolved), `missing es key: ${key}`);
    assert.ok(Object.hasOwn(I18n.en, resolved), `missing en key: ${key}`);
    assert.ok(I18n.t(key, 'es').length > 0);
    assert.ok(I18n.t(key, 'en').length > 0);
  }
  assert.doesNotMatch(qml, /Model\.copy\./, 'QML must not bypass the active locale');
  assert.doesNotMatch(qml + barQml, /I18n\.t\(root\.locale,/, 'I18n uses t(key, locale)');
});

test('global shortcut IPC endpoint performs a real helper toggle', () => {
  assert.match(qml, /function toggleNightlight\(\)/);
  assert.match(qml, /request\(\["nightlight",\s*"toggle"\],\s*"toggle"\)/);
  assert.match(qml, /IpcHandler\s*\{[\s\S]*target:\s*root\.ipcTarget[\s\S]*function toggleNightlight\(\)/);
});
