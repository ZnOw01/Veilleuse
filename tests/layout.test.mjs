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
  assert.match(toggle, /Keys\.onReturnPressed:\s*if \(!busy\) root\.editNaturalDay\s*=\s*!root\.editNaturalDay/);
  assert.match(toggle, /Keys\.onEnterPressed:\s*if \(!busy\) root\.editNaturalDay\s*=\s*!root\.editNaturalDay/);
  assert.match(toggle, /Keys\.onSpacePressed:\s*if \(!busy\) root\.editNaturalDay\s*=\s*!root\.editNaturalDay/);
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
  const end = qml.indexOf('id: scheduleRoute', start);
  const err = qml.slice(start, end);

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

test('closed panel reconciles periodically so snooze expiry and schedule boundaries physically apply', () => {
  assert.match(qml, /id:\s*backgroundStatusTimer[\s\S]*?interval:\s*30000[\s\S]*?repeat:\s*true/);
  assert.match(qml, /running:\s*!root\.opened/);
  assert.match(qml, /onTriggered:\s*if\s*\(!root\.actionPending\)\s*root\.reconcile\(\)/);
  assert.doesNotMatch(qml, /onTriggered:\s*if\s*\(!root\.actionPending\)\s*root\.requestStatus\(\)/);
  assert.match(qml, /function reconcile\(\)\s*\{\s*root\.request\(\["reconcile"\],\s*"reconcile"\)\s*;/);
});

test('panel reconciles once after load, retrying until idle so an expired snooze applies even after a shell restart', () => {
  assert.match(qml, /id:\s*initialReconcileTimer[\s\S]*?interval:\s*1000[\s\S]*?repeat:\s*false/);
  assert.match(qml, /onTriggered:\s*\{[\s\S]*?if\s*\(root\.actionPending\)\s*\{[\s\S]*?initialReconcileTimer\.restart\(\);[\s\S]*?return\s*;[\s\S]*?root\.reconcile\(\)/);
});

test('global IPC toggleNightlight queues through the latest-wins request bus instead of silently dropping while busy or unavailable', () => {
  const toggle = qml.slice(qml.indexOf('function toggleNightlight()'), qml.indexOf('function normalizeCombined'));
  assert.match(qml, /function toggleNightlight\(\)\s*\{\s*root\.request\(\["nightlight",\s*"toggle"\],\s*"toggle"\)\s*;\s*\}/);
  assert.doesNotMatch(toggle, /stateReady|actionPending|return/);
  assert.equal((toggle.match(/request\(\["nightlight"/g) || []).length, 1);
});

test('schedule summary stays a full-width left-aligned button like the reference', () => {
  const start = qml.indexOf('id: scheduleColumn');
  const summary = qml.slice(start, qml.indexOf('Column {', start));

  assert.match(summary, /Button\s*\{\s*visible:\s*!root\.scheduleExpanded/);
  assert.match(summary, /width:\s*parent\.width/);
  assert.match(summary, /leftAlign:\s*true/);
});

test('expanded schedule keeps vertical cursor movement in the schedule section', () => {
  assert.match(qml, /cursor\s*=\s*Model\.moveCursor\(cursor, key, root\.route, root\.scheduleExpanded\)/);
});

test('vertical boundary presses wrap to a visible landing section of the neighboring route', () => {
  const moveCursorBlock = qml.slice(qml.indexOf('function moveCursor(dx, dy) {'), qml.indexOf('function handleCloseRequested()'));
  assert.match(moveCursorBlock, /Model\.navigateCursorRoute\(root\.route,\s*cursor,\s*key,\s*root\.scheduleExpanded\)/);
  assert.match(moveCursorBlock, /routeJump\.route\s*!==\s*root\.route/);
  assert.match(moveCursorBlock, /root\.navigateToRoute\(routeJump\.route\)/);
  assert.match(moveCursorBlock, /cursor\s*=\s*\{\s*"section":\s*routeJump\.section,\s*"field":\s*0\s*\}/);
});

test('the schedule editor opens in place on the automation route without cross-route navigation', () => {
  const activate = qml.slice(qml.indexOf('function activateCursor()'), qml.indexOf('function setScheduleEditorFocus'));
  assert.doesNotMatch(activate, /navigateToRoute\("automation"\)/);
  assert.match(activate, /if\s*\(section\s*===\s*"schedule"\)[\s\S]*?if\s*\(!scheduleExpanded\)\s*\{\s*scheduleExpanded\s*=\s*true;/);
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
  assert.match(qml, /\["transition-config",\s*"--seconds"/);
  assert.doesNotMatch(qml, /\["transition",\s*"--temperature"/);
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
  assert.match(qml, /blocked:[^\n]*shortcutField\.activeFocus/);
  assert.match(qml, /\["install",\s*"--keys",\s*shortcutField\.text\]/);
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
  assert.match(qml, /manageIpc:\s*false/);
  assert.match(qml, /function toggleNightlight\(\)/);
  assert.match(qml, /request\(\["nightlight",\s*"toggle"\],\s*"toggle"\)/);
  assert.match(qml, /IpcHandler\s*\{[\s\S]*target:\s*root\.ipcTarget[\s\S]*function toggleNightlight\(\)/);
  for (const method of ['open', 'close', 'show', 'hide', 'toggle']) {
    assert.match(qml, new RegExp(`function ${method}\\(\\)`));
  }
});

test('structured v2 status consumes nested automation provenance and preset lists', () => {
  assert.match(qml, /data\.automation\s*&&\s*data\.automation\.last_applied/);
  assert.match(qml, /root\.formatLastApplied\(data\.automation\.last_applied\)/);
  assert.match(qml, /root\.presetItems\s*=\s*Array\.isArray\(data\.presets\.list\)\s*\?\s*data\.presets\.list\s*:\s*\[\]/);
});

test('final integration passes the selected monitor and exposes custom preset controls', () => {
  assert.match(qml, /request\(\["brightness",\s*String\(Math\.round\(value\)\),\s*"--monitor",\s*root\.selectedMonitor\],\s*name\)/);
  assert.match(qml, /id:\s*customPresetName/);
  assert.match(qml, /preset.*save|save.*preset/s);
  assert.match(qml, /preset.*delete|delete.*preset/s);
  assert.match(qml, /customPresetName\.activeFocus/);
});

test('ToggleSwitch controls maintain stable geometry and never bind interactive to actionPending', () => {
  const switchCount = (qml.match(/\bToggleSwitch\s*\{/g) || []).length;
  assert.equal(switchCount, 3, 'expected exactly 3 ToggleSwitch instances in Panel.qml');

  assert.doesNotMatch(qml, /ToggleSwitch\s*\{[^}]*interactive:\s*[^;\n]*actionPending/);
  assert.doesNotMatch(qml, /ToggleSwitch\s*\{[^}]*interactive:\s*[^;\n]*stateReady/);

  const heroSwitch = qml.slice(qml.indexOf('trailingControl: Component {'), qml.indexOf('id: homeRoute'));
  assert.match(heroSwitch, /busy:\s*!root\.stateReady\s*\|\|\s*root\.actionPending/);
  assert.match(heroSwitch, /Accessible\.name:\s*root\.text\("night_light"\)/);

  const schedSwitch = qml.slice(qml.indexOf('id: scheduleToggle'), qml.indexOf('id: transitionEditor'));
  assert.match(schedSwitch, /busy:\s*!root\.automationReady\s*\|\|\s*root\.actionPending/);
  assert.match(schedSwitch, /Accessible\.name:\s*root\.text\("schedule"\)/);

  const natStart = qml.indexOf('id: naturalDayEditor');
  const natEnd = qml.indexOf('Column {', natStart);
  const natSwitch = qml.slice(natStart, natEnd);
  assert.match(natSwitch, /busy:\s*!root\.stateReady\s*\|\|\s*root\.actionPending/);
  assert.match(natSwitch, /Accessible\.name:\s*root\.text\("natural_day"\)/);
  assert.doesNotMatch(natSwitch, /width:\s*parent\.width/, 'natural-day switch must not stretch width over parent');
});

test('schedule enabled state semantics stay honest before automation payload is available', () => {
  const schedSwitch = qml.slice(qml.indexOf('id: scheduleToggle'), qml.indexOf('id: transitionEditor'));
  assert.doesNotMatch(qml, /scheduleEnabled:\s*!\(root\.state\.automation\s*&&\s*root\.state\.automation\.schedule_enabled === false\)/);
  assert.match(qml, /readonly\s+property\s+bool\s+automationReady:\s*Boolean\(root\.state\.automation\s*&&\s*root\.state\.automation\.available\s*===\s*true\)/);
  assert.match(qml, /readonly\s+property\s+bool\s+scheduleEnabled:\s*Boolean\(root\.automationReady\s*&&\s*root\.state\.automation\.schedule_enabled\s*!==\s*false\)/);
  assert.match(schedSwitch, /busy:\s*!root\.automationReady\s*\|\|\s*root\.actionPending/);
});

test('natural-day keyboard activation respects the same busy gate as pointer input', () => {
  for (const key of ['Return', 'Enter', 'Space'])
    assert.match(qml, new RegExp(`Keys\\.on${key}Pressed:\\s*if \\(!busy\\)`));
});

test('keyCatcher isolates open dropdown popups to prevent key leakage', () => {
  assert.match(qml, /blocked:[^\n]*monitorSelector\.popupOpen/);
  assert.match(qml, /blocked:[^\n]*localeSelector\.popupOpen/);
  assert.match(qml, /blocked:[^\n]*scopeSelector\.popupOpen/);
  assert.match(qml, /blocked:[^\n]*presetSelector\.popupOpen/);
});

test('slider mutations from keyboard cursor only occur on home route when schedule is collapsed', () => {
  const moveCursorBlock = qml.slice(qml.indexOf('function moveCursor(dx, dy) {'), qml.indexOf('function handleCloseRequested()'));
  assert.match(moveCursorBlock, /if\s*\(\s*dx\s*!==\s*0\s*&&\s*stateReady\s*&&\s*root\.route\s*===\s*"home"\s*&&\s*!root\.scheduleExpanded\s*\)/);
});

test('hero does not add MouseArea and custom preset deletion waits for confirmation', () => {
  const heroSurface = qml.slice(qml.indexOf('id: heroSurface'), qml.indexOf('id: homeRoute'));
  assert.doesNotMatch(heroSurface, /\bMouseArea\s*\{/);

  const deleteFunc = qml.slice(qml.indexOf('function deleteSelectedCustomPreset()'), qml.indexOf('function toggleSchedule('));
  assert.doesNotMatch(deleteFunc, /preferredPreset\s*=/);
});

test('transition config sets seconds only', () => {
  assert.match(qml, /\["transition-config"\s*,\s*"--seconds"/);
  assert.match(qml, /setTransition\(root\.transitionSeconds\)/);
});

test('ids are never accessed through the root object', () => {
  // `root.<id>` is undefined for plain QML ids: a freshly started engine
  // throws on the access and every helper call dies with it.
  assert.doesNotMatch(qml, /root\.(helperProcess|debounce|feedbackTimer|keyCatcher)\b/);
  assert.match(qml, /if \(helperProcess\.running \|\| root\.stoppingForLatest \|\| debounce\.running\) \{/);
});

test('slider value labels track the drag target like the knob does', () => {
  // The knob shows displayValue() while a chase is in flight; the numeric
  // label must too, or the number lags the pointer and then snaps.
  const labels = qml.match(/root\.displayValue\("(brightness|temperature|gamma)"/g) || [];
  assert.equal(labels.length, 6, 'each slider binds knob and label through displayValue');
  assert.match(qml, /id:\s*temperatureRow[\s\S]*?step:\s*50/);
});

test('transition seconds field bounds', () => {
  assert.match(qml, /id:\s*transitionEditor[\s\S]*?from:\s*0/);
  assert.match(qml, /id:\s*transitionEditor[\s\S]*?to:\s*1800/);
});

test('home status box is the single now/last-applied source and history is one affordance', () => {
  // The former standalone "Last applied" row was merged into the home
  // summary box, and history is one button with the latest entries bound to it.
  assert.doesNotMatch(qml, /id:\s*lastAppliedLabel/);
  assert.match(qml, /id:\s*homeSummary/);
  assert.match(qml, /root\.text\("view_history"\)/);
  assert.match(qml, /root\.historyItems\.slice\(0,\s*3\)/);
  assert.match(qml, /formatHistoryEntry\(modelData\)/);
  assert.doesNotMatch(qml, /root\.text\("open_automation"\)/);
  assert.match(qml, /root\.text\("live_controls"\)/);
  // Working feedback, active snooze with remaining minutes and keyboard
  // hints keep the panel's state and model discoverable.
  assert.match(qml, /root\.text\("working"\)/);
  assert.match(qml, /snoozeRemainingMinutes/);
  assert.match(qml, /root\.text\("keyboard_hints"\)/);
});

test('keyboard slider steps accumulate pending offsets instead of recomputing from stale confirmed state', () => {
  const moveCursorBlock = qml.slice(qml.indexOf('function moveCursor(dx, dy) {'), qml.indexOf('function handleCloseRequested()'));
  assert.match(moveCursorBlock, /Model\.keyboardStep\(section,\s*dx,\s*confirmed,\s*root\.pendingSteps\[section\]\)/);
  assert.match(moveCursorBlock, /root\.pendingSteps\[section\]\s*=\s*step\.pending/);
  assert.match(moveCursorBlock, /function reconcilePending\(previous\)/);
});

test('confirmed readbacks reconcile pending steps and drain the remaining distance', () => {
  assert.match(qml, /function reconcilePending\(previous\)[\s\S]*?Model\.reconcilePendingSteps\(previous,\s*root\.state,\s*root\.pendingSteps,\s*root\.queuedOperation\)/);
  assert.match(qml, /root\.pendingSteps\s*=\s*result\.pending/);
  assert.match(qml, /root\.queueMutation\(result\.requests\[i\]\.section,\s*result\.requests\[i\]\.value\)/);
  assert.match(qml, /var\s+previousState\s*=\s*state;[\s\S]*?root\.reconcilePending\(previousState\)/);
});

test('pointer slider drags record the latest-wins drag target through the request bus', () => {
  const brightness = qml.slice(qml.indexOf('id: brightnessRow'), qml.indexOf('id: temperatureRow'));
  assert.match(brightness, /onMoved:\s*function\(v\)\s*\{\s*root\.queueDragMutation\("brightness",\s*v\)\s*\}/);
  const temperature = qml.slice(qml.indexOf('id: temperatureRow'), qml.indexOf('id: gammaRow'));
  assert.match(temperature, /onMoved:\s*function\(v\)\s*\{\s*root\.queueDragMutation\("temperature",\s*v\)\s*\}/);
  const gamma = qml.slice(qml.indexOf('id: gammaRow'));
  assert.match(gamma, /onMoved:\s*function\(v\)\s*\{\s*root\.queueDragMutation\("gamma",\s*v\)\s*\}/);
  assert.match(qml, /function queueDragMutation\(section,\s*value\)[\s\S]*?Model\.dragTargetPush\(root\.dragTarget,\s*section,\s*value\)[\s\S]*?root\.queueMutation\(section,\s*value\)/);
});

test('slider value shows the pending drag target so drags never revert to stale state', () => {
  assert.match(qml, /function displayValue\(section,\s*fallback\)/);
  assert.match(qml, /value:\s*root\.displayValue\("brightness"/);
  assert.match(qml, /value:\s*root\.displayValue\("temperature"/);
  assert.match(qml, /value:\s*root\.displayValue\("gamma"/);
});

test('confirmed readbacks advance the drag chase one helper request at a time', () => {
  assert.match(qml, /function reconcilePending\(previous\)[\s\S]*?Model\.reconcileDragTargets\(previous,\s*root\.state,\s*root\.dragTarget,\s*root\.queuedOperation\)/);
  assert.match(qml, /root\.dragTarget\s*=\s*drag\.target/);
  assert.match(qml, /root\.queueMutation\(drag\.requests\[j\]\.section,\s*drag\.requests\[j\]\.value\)/);
});

test('keyboard slider steps and failed requests clear the pending drag target', () => {
  const moveCursorBlock = qml.slice(qml.indexOf('function moveCursor(dx, dy) {'), qml.indexOf('function handleCloseRequested()'));
  assert.match(moveCursorBlock, /root\.dragTarget\s*=\s*Model\.dragTargetPush\(root\.dragTarget,\s*section,\s*null\)/);
  const exitBlock = qml.slice(qml.indexOf('function handleExit(exitCode) {'), qml.indexOf('function moveCursor(dx, dy) {'));
  assert.match(exitBlock, /actionPending\s*=\s*false;[\s\S]*?root\.dragTarget\s*=\s*Model\.dragTargetEmpty\(\);/);
});

test('automation route exposes keyboard-reachable schedule, transition, snooze and schedule sections', () => {
  assert.match(qml, /id:\s*scheduleToggle[\s\S]*?hasCursor:\s*root\.cursor\.section\s*===\s*0/);
  assert.match(qml, /id:\s*transitionEditor[\s\S]*?hasCursor:\s*root\.cursor\.section\s*===\s*1/);
  assert.match(qml, /id:\s*scheduleSurface[\s\S]*?hasCursor:\s*root\.cursor\.section\s*===\s*3/);
});

test('snooze actions are reachable through the four cursor fields', () => {
  for (let field = 0; field < 4; field++) {
    const name = ['snooze_30', 'snooze_120', 'until_tomorrow', 'clear_snooze'][field];
    assert.match(qml, new RegExp(`text: root\\.text\\("${name}"\\)[\\s\\S]*?hasCursor: root\\.cursor\\.section === 2 && root\\.cursor\\.field === ${field}`));
  }
});

test('settings route exposes keyboard-reachable dropdowns, preflight, shortcut field and actions', () => {
  assert.match(qml, /id:\s*localeSelector[\s\S]*?hasCursor:\s*root\.cursor\.section\s*===\s*0/);
  assert.match(qml, /id:\s*scopeSelector[\s\S]*?hasCursor:\s*root\.cursor\.section\s*===\s*1/);
  assert.match(qml, /id:\s*presetSelector[\s\S]*?hasCursor:\s*root\.cursor\.section\s*===\s*2/);
  assert.match(qml, /text:\s*root\.text\("run_preflight"\)[\s\S]*?hasCursor:\s*root\.cursor\.section\s*===\s*3/);
  assert.match(qml, /id:\s*shortcutField[\s\S]*?hasCursor:\s*root\.cursor\.section\s*===\s*4/);
  assert.match(qml, /install_shortcut"\)[\s\S]*?hasCursor:\s*root\.cursor\.section\s*===\s*5\s*&&\s*root\.cursor\.field\s*===\s*0/);
  assert.match(qml, /remove_shortcut"\)[\s\S]*?hasCursor:\s*root\.cursor\.section\s*===\s*5\s*&&\s*root\.cursor\.field\s*===\s*1/);
});

test('keyboard activation opens dropdowns, edits the shortcut field, and runs actions', () => {
  const activate = qml.slice(qml.indexOf('function activateCursor()'), qml.indexOf('function setScheduleEditorFocus'));
  assert.match(activate, /section\s*===\s*"locale"\)\s*\{\s*localeSelector\.open\(\);/);
  assert.match(activate, /section\s*===\s*"scope"\)\s*\{\s*scopeSelector\.open\(\);/);
  assert.match(activate, /section\s*===\s*"preset"\)\s*\{\s*presetSelector\.open\(\);/);
  assert.match(activate, /section\s*===\s*"shortcut"\)\s*\{\s*shortcutField\.forceActiveFocus\(\);/);
  assert.match(activate, /section\s*===\s*"shortcutActions"\)\s*\{[\s\S]*?install",\s*"--keys",\s*shortcutField\.text/);
  assert.match(activate, /section\s*===\s*"transition"\)\s*\{\s*transitionEditor\.field\.forceActiveFocus\(\);/);
  assert.match(activate, /section\s*===\s*"snooze"\)\s*\{[\s\S]*?root\.setSnooze\(30\)/);
});

test('dropdown, shortcut and preset editors return focus before Escape can close the panel', () => {
  assert.match(qml, /onPopupOpenChanged:\s*if\s*\(!localeSelector\.popupOpen\)\s*Qt\.callLater\(function\(\)\s*\{\s*keyCatcher\.forceActiveFocus\(\);\s*\}\)/);
  assert.match(qml, /onPopupOpenChanged:\s*if\s*\(!scopeSelector\.popupOpen\)\s*Qt\.callLater\(function\(\)\s*\{\s*keyCatcher\.forceActiveFocus\(\);\s*\}\)/);
  assert.match(qml, /onPopupOpenChanged:\s*if\s*\(!presetSelector\.popupOpen\)\s*Qt\.callLater\(function\(\)\s*\{\s*keyCatcher\.forceActiveFocus\(\);\s*\}\)/);
  assert.match(qml, /onPopupOpenChanged:\s*if\s*\(!monitorSelector\.popupOpen\)\s*Qt\.callLater\(function\(\)\s*\{\s*keyCatcher\.forceActiveFocus\(\);\s*\}\)/);
  assert.match(qml, /id:\s*shortcutField[\s\S]*?Keys\.onEscapePressed:\s*keyCatcher\.forceActiveFocus\(\)/);
  assert.match(qml, /id:\s*customPresetName[\s\S]*?Keys\.onEscapePressed:\s*keyCatcher\.forceActiveFocus\(\)/);
  assert.match(qml, /id:\s*transitionEditor[\s\S]*?field\.Keys\.onPressed:[\s\S]*?Qt\.Key_Escape[\s\S]*?keyCatcher\.forceActiveFocus\(\);[\s\S]*?Qt\.Key_Return[\s\S]*?root\.setTransition\(root\.transitionSeconds\)/);
});

test('requests launch immediately when idle and only debounce bursts to preserve latest-wins', () => {
  const requestBlock = qml.slice(qml.indexOf('function request(command, operation) {'), qml.indexOf('function queueMutation(name, value) {'));
  assert.match(requestBlock, /if\s*\(\s*helperProcess\.running\s*\|\|\s*root\.stoppingForLatest\s*\|\|\s*debounce\.running\s*\)/);
  assert.match(requestBlock, /debounce\.restart\(\)/);
  assert.match(requestBlock, /debounce\.stop\(\)/);
  assert.match(requestBlock, /root\.launchLatest\(\)/);
});

test('keyCatcher yields to the transition editor so arrows edit the field instead of moving the cursor', () => {
  assert.match(qml, /blocked:[^\n]*transitionEditor\.field\.activeFocus/);
});

test('a superseded helper exit cancels the stale burst debounce before relaunching the latest', () => {
  assert.match(qml, /if\s*\(\s*requestId\s*!==\s*latestRequestId\)\s*\{\s*debounce\.stop\(\);\s*Qt\.callLater\(root\.launchLatest\);/);
});

test('a superseded helper exit still adopts the state of the write that physically applied', () => {
  assert.match(qml, /function mergeStaleResponse\(exitCode\)/);
  assert.match(qml, /if\s*\(\s*requestId\s*!==\s*latestRequestId\)\s*\{[\s\S]*?Qt\.callLater\(root\.launchLatest\);\s*root\.mergeStaleResponse\(exitCode\);\s*return ;\s*\}/);
  const merge = qml.slice(qml.indexOf('function mergeStaleResponse(exitCode)'), qml.indexOf('function handleExit(exitCode)'));
  assert.match(merge, /if\s*\(exitCode\s*!==\s*0\)\s*return ;/);
  assert.match(merge, /JSON\.parse\(processOutput\)/);
  assert.match(merge, /Model\.mergeStatePatch\(before,\s*patch\)/);
});

test('returning to the home route refreshes the physical state the sliders must show', () => {
  const nav = qml.slice(qml.indexOf('function navigateToRoute('), qml.indexOf('function monitorChoices()'));
  assert.match(nav, /if\s*\(nextRoute\s*===\s*"home"\)\s*root\.requestStatus\(\);/);
});

test('route changes reset the cursor so activation targets the new route, not the previous one', () => {
  const nav = qml.slice(qml.indexOf('function navigateToRoute('), qml.indexOf('function refocusKeyCatcher()'));
  assert.match(nav, /if\s*\(nextRoute\s*!==\s*root\.route\)\s*\{[\s\S]*?root\.cursor\s*=\s*Model\.cursorStart\(\);/);
});

test('focusable action buttons return focus to the key catcher after their click', () => {
  assert.match(qml, /function refocusKeyCatcher\(\)\s*\{\s*Qt\.callLater\(function\(\)\s*\{\s*if\s*\(keyCatcher\)\s*keyCatcher\.forceActiveFocus\(\);\s*\}\s*\);\s*\}/);
  const actions = [
    'root.applyPreset("day")',
    'root.applyPreset("evening")',
    'root.applyPreset("night")',
    'root.settingsCommand("preset", ["list"])',
    'root.saveCustomPreset()',
    'root.settingsCommand("history", ["list"])',
    'root.setTransition(root.transitionSeconds)',
    'root.setSnooze(30)',
    'root.setSnooze(120)',
    'root.settingsCommand("snooze", ["until-tomorrow"])',
    'root.settingsCommand("snooze", ["clear"])',
    'root.settingsCommand("preflight", [])',
    'root.settingsCommand("shortcut", ["remove"])',
    'root.queueSchedule()'
  ];
  for (const action of actions) {
    assert.match(
      qml,
      new RegExp(`onClicked:\\s*\\{\\s*${action.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*;\\s*root\\.refocusKeyCatcher\\(\\);\\s*\\}`)
    );
  }
  // Deleting a preset is a two-click confirm: the first click arms it (with
  // the target name and an expiry timer), the second one actually deletes.
  assert.match(qml, /property bool presetDeleteArmed: false/);
  assert.match(qml, /id:\s*presetDeleteArmTimer/);
  assert.match(
    qml,
    /root\.presetDeleteArmed\s*=\s*true;\s*root\.presetDeleteArmedName\s*=\s*String\(root\.preferredPreset\);\s*presetDeleteArmTimer\.restart\(\);[\s\S]*?root\.deleteSelectedCustomPreset\(\);\s*\}\s*root\.refocusKeyCatcher\(\);/
  );
});

test('schedule edit and shortcut install buttons also restore key catcher focus', () => {
  const editSchedule = qml.slice(qml.indexOf('root.text("edit_schedule")'), qml.indexOf('id: settingsRoute'));
  assert.match(editSchedule, /root\.editNightTemperature\s*=\s*String\(root\.state\.schedule\.night_temp\s*\|\|\s*3500\);\s*\}\s*root\.refocusKeyCatcher\(\);/);
  const install = qml.slice(qml.indexOf('id: shortcutField'), qml.indexOf('Text {\n                    visible: root.errorText'));
  assert.match(install, /root\.settingsCommand\("shortcut",\s*\["install",\s*"--keys",\s*shortcutField\.text\]\);\s*root\.refocusKeyCatcher\(\);/);
});

test('text fields return focus to the key catcher on accept', () => {
  assert.match(qml, /onAccepted:\s*\{\s*root\.saveCustomPreset\(\);\s*keyCatcher\.forceActiveFocus\(\);\s*\}/);
  assert.match(qml, /onAccepted:\s*\{\s*root\.setInlineSetting\("shortcutKeys",\s*text\);\s*keyCatcher\.forceActiveFocus\(\);\s*\}/);
});

test('a failed preset apply reverts the optimistic selection to the previous preset', () => {
  const apply = qml.slice(qml.indexOf('function applyPreset(name)'), qml.indexOf('function saveCustomPreset()'));
  assert.match(apply, /root\.queuedPresetPrevious\s*=\s*root\.preferredPreset;/);
  assert.match(apply, /root\.preferredPreset\s*=\s*String\(name\);/);
  assert.match(apply, /root\.queuedPresetRequestId\s*=\s*root\.issue\(/);
  const exitBlock = qml.slice(qml.indexOf('function handleExit(exitCode) {'), qml.indexOf('function moveCursor(dx, dy) {'));
  assert.match(exitBlock, /if\s*\(queuedOperation\s*===\s*"preset"\s*&&\s*root\.queuedPresetRequestId\s*===\s*requestId\)\s*root\.preferredPreset\s*=\s*root\.queuedPresetPrevious;/);
});
