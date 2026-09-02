import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const qml = fs.readFileSync(new URL('../Panel.qml', import.meta.url), 'utf8');
const barQml = fs.readFileSync(new URL('../BarWidget.qml', import.meta.url), 'utf8');
const i18n = fs.readFileSync(new URL('../I18n.js', import.meta.url), 'utf8');
const helper = fs.readFileSync(new URL('../scripts/veilleuse-control', import.meta.url), 'utf8');
const workflow = fs.readFileSync(new URL('../.github/workflows/checks.yml', import.meta.url), 'utf8');
const hygiene = fs.readFileSync(new URL('../scripts/check_hygiene.sh', import.meta.url), 'utf8');
const manifest = JSON.parse(fs.readFileSync(new URL('../manifest.json', import.meta.url), 'utf8'));

test('community plugin id is lowercase and consistent across entry points', () => {
  assert.equal(manifest.id, manifest.id.toLowerCase());
  assert.ok(qml.includes(`moduleName: "${manifest.id}"`));
  assert.ok(qml.includes(`ipcTarget: "${manifest.id}"`));
  assert.ok(barQml.includes(`moduleName: "${manifest.id}"`));
  assert.ok(helper.includes(`PLUGIN_ID = "${manifest.id}"`));
  // CI delegates to the local gate, and the hygiene gate is what pins the id.
  assert.ok(workflow.includes('./scripts/check.sh'));
  assert.ok(hygiene.includes(`manifest.get("id") == "${manifest.id}"`));
});

test('slider handlers declare signal parameters explicitly and step one by one', () => {
  assert.equal((qml.match(/onMoved:\s*function\(v\)\s*\{/g) || []).length, 3);
  assert.doesNotMatch(qml, /onMoved:\s*root\./);
  // One unit at a time while the pointer moves: no 50 K snapping anywhere.
  const steps = [...qml.matchAll(/step:\s*([0-9]+)/g)].map(match => match[1]);
  assert.equal(steps.length, 3);
  for (const step of steps) assert.equal(step, '1');
});

test('each slider renders a label row with its live value above the track', () => {
  const home = qml.slice(qml.indexOf('id: homeRoute'), qml.indexOf('id: automationRoute'));
  for (const [labelId, valueId, textKey, valueKey] of [
    ['brightnessLabel', 'brightnessValue', 'brightness', 'brightness'],
    ['temperatureLabel', 'temperatureValue', 'temperature', 'temperature'],
    // Gamma shows the short label so the live value never collides with it.
    ['gammaLabel', 'gammaValue', 'gamma_short', 'gamma']
  ]) {
    assert.match(home, new RegExp(`id:\\s*${labelId}[\\s\\S]*?text:\\s*root\\.text\\("${textKey}"\\)`));
    assert.match(home, new RegExp(`id:\\s*${valueId}[\\s\\S]*?root\\.displayValue\\("${valueKey}"`));
  }
});

test('sliders span the full panel width under their label rows', () => {
  const home = qml.slice(qml.indexOf('id: homeRoute'), qml.indexOf('id: automationRoute'));
  const sliders = home.match(/PanelSlider\s*\{[\s\S]*?\n\s{28}\}/g) || [];
  for (const slider of sliders) assert.match(slider, /width:\s*parent\.width/);
});

test('slider value labels track the drag target like the knob does', () => {
  const labels = qml.match(/root\.displayValue\("(brightness|temperature|gamma)"/g) || [];
  assert.equal(labels.length, 6, 'each slider binds knob and label through displayValue');
});

test('mouse hover moves the panel cursor onto the hovered row', () => {
  // The Omarchy cursor contract: every navigable section binds hasCursor to
  // a cursor.section index and a HoverHandler points the cursor at that same
  // index, so hover + arrows drive one single cursor.
  assert.match(qml, /function cursorToSection\(index\)/);
  const sections = [...qml.matchAll(/hasCursor:\s*root\.cursor\.section === (\d+)/g)].map(m => m[1]);
  assert.ok(sections.length >= 9, `expected all routes to be hover-navigable, got ${sections.length}`);
  for (const index of [...new Set(sections)]) {
    const cursorTargets = qml.match(new RegExp(`root\\.cursorToSection\\(${index}\\)`, 'g')) || [];
    // Action buttons that share one row (shortcut install/remove) bind
    // hasCursor individually but share the row's single HoverHandler.
    const buttonBindings = [...qml.matchAll(
      new RegExp(`Button\\s*\\{[^{}]*?hasCursor:\\s*root\\.cursor\\.section === ${index}`, 'g')
    )].length;
    const surfaceCount = sections.filter(s => s === index).length - buttonBindings;
    assert.ok(cursorTargets.length >= surfaceCount,
      `section ${index} must hover-set the cursor it claims (${cursorTargets.length} hover(s) for ${surfaceCount} hasCursor binding(s))`);
  }
});

test('the keyboard is arrows-only and owned by an inline key catcher', () => {
  assert.doesNotMatch(qml, /PanelKeyCatcher/);
  assert.match(qml, /Keys\.priority:\s*Keys\.BeforeItem/);
  // Left/Right adjust the slider the cursor owns and only fall back to view
  // switching outside the drag sections.
  assert.match(qml, /Qt\.Key_Left[\s\S]*?root\.adjustSliderBy\(-1\)[\s\S]*?root\.switchRouteBy\(-1\)/);
  assert.match(qml, /Qt\.Key_Right[\s\S]*?root\.adjustSliderBy\(1\)[\s\S]*?root\.switchRouteBy\(1\)/);
  assert.match(qml, /Qt\.Key_Up[\s\S]*?root\.moveCursorVertically\(-1\)/);
  assert.match(qml, /Qt\.Key_Down[\s\S]*?root\.moveCursorVertically\(1\)/);
  assert.match(qml, /Qt\.Key_Return[\s\S]*?root\.activateCursor\(\)/);
  assert.match(qml, /Qt\.Key_Escape[\s\S]*?root\.handleCloseRequested\(\)/);
  // The vim-era letter keys are gone from the model and the panel.
  assert.doesNotMatch(qml, /'j'|'k'|'h'|'l'/);
  // Key/action pairs use non-breaking spaces so a wrapped line never splits
  // a pair across lines (matched against the literal \u00A0 escapes).
  assert.match(i18n, /keyboardHints:\s*'← →\\u00A0adjust \/ switch\\u00A0view · ↑ ↓\\u00A0move · Enter\\u00A0activate · Esc\\u00A0close'/);
});

test('view switching is the two chevrons plus the current view name', () => {
  const nav = qml.slice(qml.indexOf('// View switching'), qml.indexOf('id: heroSurface'));
  assert.equal((nav.match(/PanelActionButton\s*\{/g) || []).length, 2);
  assert.match(nav, /text:\s*root\.routeTitle/);
  assert.match(nav, /horizontalAlignment:\s*Text\.AlignHCenter/);
  assert.match(nav, /verticalAlignment:\s*Text\.AlignVCenter/);
  assert.match(nav, /elide:\s*Text\.ElideRight/);
  assert.match(qml, /function switchRouteBy\(direction\)\s*\{\s*root\.navigateToRoute\(Model\.adjacentRoute\(root\.route,\s*direction\)\);\s*\}/);
});

test('the hero shows the title and switch only, with no schedule meta line', () => {
  const hero = qml.slice(qml.indexOf('id: heroSurface'), qml.indexOf('id: homeRoute'));
  assert.match(hero, /title:\s*root\.text\("night_light"\)/);
  assert.match(hero, /onToggled:\s*root\.request\(\["nightlight",\s*"toggle"\],\s*"toggle"\)/);
  assert.doesNotMatch(hero, /meta:/);
  assert.doesNotMatch(hero, /periodText|period_day|period_night|manual_override/);
});

test('the home summary box, presets, and history affordances are gone', () => {
  assert.doesNotMatch(qml, /id:\s*homeSummary/);
  assert.doesNotMatch(qml, /live_controls|live_now|view_history|last_applied|latest_event/);
  assert.doesNotMatch(qml, /text\("preset|presetItems|customPresetName|preferredPreset|applyPreset|saveCustomPreset|deleteSelectedCustomPreset/);
  assert.doesNotMatch(qml, /historyItems|formatHistoryEntry|\["history"/);
  // The glyph still renders the persisted "preset" provenance of old states.
  assert.doesNotMatch(qml, /presetSelector|preset_utils|BUILTIN_PRESETS/);
});

test('home route keeps the monitor picker as its only saved setting', () => {
  const home = qml.slice(qml.indexOf('id: homeRoute'), qml.indexOf('id: automationRoute'));
  assert.match(home, /SearchableDropdown\s*\{\s*id:\s*monitorSelector/);
  assert.match(home, /label:\s*root\.text\("monitor"\)/);
  assert.match(qml, /onChanged:\s*function\(value\)\s*\{\s*root\.setInlineSetting\("monitor",\s*value\)\s*\}/);
});

test('automation header carries the window only while the schedule runs', () => {
  const header = qml.slice(qml.indexOf('id: automationHeader'), qml.indexOf('// The schedule itself'));
  assert.match(header, /text:\s*root\.text\("schedule"\)/);
  assert.match(header, /visible:\s*root\.scheduleEnabled\s*&&\s*root\.stateReady/);
  assert.match(header, /elide:\s*Text\.ElideRight/);
  assert.match(header, /id:\s*scheduleLabelsColumn/);
  // The off switch already says paused: no redundant "paused" caption.
  assert.doesNotMatch(header, /schedule_disabled|schedule_paused/);
  assert.match(qml, /\["schedule",\s*enabled \? "enable" : "disable"\]/);
});

test('the schedule editor is always visible and configures both periods', () => {
  const editor = qml.slice(qml.indexOf('id: scheduleEditorColumn'), qml.indexOf('// Snooze:'));
  assert.equal((editor.match(/\bTextField\s*\{/g) || []).length, 2);
  assert.equal((editor.match(/\bNumberField\s*\{/g) || []).length, 6);
  assert.match(editor, /text:\s*root\.text\("day_period"\)/);
  assert.match(editor, /text:\s*root\.text\("night_period"\)/);
  assert.match(editor, /id:\s*dayTemperatureEditor[\s\S]*?fieldWidth:\s*width[\s\S]*?from:\s*5900[\s\S]*?to:\s*6500/);
  assert.match(editor, /id:\s*nightTemperatureEditor[\s\S]*?fieldWidth:\s*width[\s\S]*?from:\s*2500[\s\S]*?to:\s*5000/);
  // No collapse state: the editor lives on the automation route for good.
  assert.doesNotMatch(qml, /scheduleExpanded|scheduleEditorOpen/);
});

test('saving a schedule sends the times, temperatures and per-period display values', () => {
  assert.match(qml, /--day-time/);
  assert.match(qml, /--night-time/);
  assert.match(qml, /--day-temp/);
  assert.match(qml, /--night-temp/);
  assert.match(qml, /"\--" \+ periods\[i\]\[0\] \+ "\-" \+ periods\[i\]\[1\]/);
  for (const entry of ['"day", "brightness"', '"day", "gamma"', '"night", "brightness"', '"night", "gamma"'])
    assert.ok(qml.includes(`[${entry},`), `periods table must include ${entry}`);
  // Natural day is derived from the day temperature now, not a toggle.
  assert.doesNotMatch(qml, /--natural-day|--no-natural-day|natural_day/);
});

test('the transition section and its config command are gone', () => {
  assert.doesNotMatch(qml, /transition-config|transitionSeconds|transitionEditor|setTransition/);
  assert.doesNotMatch(qml, /transitionTitle|transition_seconds/);
});

test('snooze composes a number, a unit and one apply action', () => {
  const snooze = qml.slice(qml.indexOf('id: snoozeColumn'), qml.indexOf('id: settingsRoute'));
  assert.match(snooze, /id:\s*snoozeEditor/);
  for (const unit of ['unit_hours', 'unit_minutes', 'unit_seconds'])
    assert.match(snooze, new RegExp(`text:\\s*root\\.text\\("${unit}"\\)`));
  assert.match(snooze, /text:\s*root\.text\("snooze_set"\)/);
  assert.match(snooze, /enabled:\s*root\.snoozeSeconds !== null\s*&&\s*!root\.actionPending/);
  assert.match(qml, /\["snooze",\s*"set",\s*"--seconds",\s*String\(root\.snoozeSeconds\)\]/);
  // The active snooze shows its remaining time and a cancel; nothing else.
  assert.match(snooze, /visible:\s*root\.snoozeActive/);
  assert.match(snooze, /snoozeRemainingMinutes/);
  assert.match(snooze, /text:\s*root\.text\("clear_snooze"\)/);
  // The preset durations and "until tomorrow" are gone.
  assert.doesNotMatch(qml, /snooze_30|snooze_120|until-tomorrow|until_tomorrow|setSnooze\(30\)|setSnooze\(120\)/);
});

test('settings route is language and the shortcut only', () => {
  const settings = qml.slice(qml.indexOf('id: settingsRoute'), qml.indexOf('root.text("keyboard_hints")'));
  assert.match(settings, /id:\s*localeSelector/);
  assert.match(settings, /\{\s*value:\s*"en",\s*label:\s*root\.text\("english"\)\s*\}/);
  assert.match(settings, /\{\s*value:\s*"es",\s*label:\s*root\.text\("spanish"\)\s*\}/);
  assert.match(settings, /id:\s*shortcutField/);
  assert.match(settings, /settingsCommand\("shortcut",\s*\["install",\s*"--keys",\s*shortcutField\.text\]\)/);
  assert.match(settings, /settingsCommand\("shortcut",\s*\["remove"\]\)/);
  assert.doesNotMatch(settings, /applyScope|scopeSelector|preflight|default-preset|default_preset/);
});

test('errors, feedback and schedule validation stay visible with equal padding', () => {
  // The global error sits under the view header so it stays on screen no
  // matter how far the panel content scrolls.
  const errorStart = qml.indexOf('visible: root.errorText !== ""');
  const heroStart = qml.indexOf('id: heroSurface');
  assert.ok(errorStart > -1 && errorStart < heroStart, 'global error must precede the hero surface');

  // Field validation sits right above Save and the saved confirmation right
  // below it, both inside the schedule editor column.
  const editor = qml.slice(qml.indexOf('id: scheduleEditorColumn'), qml.indexOf('// Snooze: enter a duration'));
  const validateAt = editor.indexOf('visible: root.scheduleValidationError !== ""');
  const saveAt = editor.indexOf('id: saveScheduleButton');
  const feedbackAt = editor.indexOf('visible: root.feedbackText !== ""');
  assert.ok(validateAt > -1 && validateAt < saveAt, 'validation message must precede the save button');
  assert.ok(feedbackAt > saveAt, 'save feedback must follow the save button');

  // Every message keeps the shared horizontal padding: the global one
  // carries it directly, the editor messages inherit it from the editor
  // column margins.
  const errorAt = qml.indexOf('visible: root.errorText !== ""');
  const errorSlice = qml.slice(errorAt, qml.indexOf('}', errorAt));
  assert.match(errorSlice, /leftPadding:\s*Style\.spacing\.rowPaddingX/);
  assert.match(errorSlice, /rightPadding:\s*Style\.spacing\.rowPaddingX/);
  assert.match(editor, /anchors\.leftMargin:\s*Style\.spacing\.rowPaddingX/);
  assert.match(editor, /anchors\.rightMargin:\s*Style\.spacing\.rowPaddingX/);
});

test('successful schedule saves render short-lived feedback and refresh the drafts', () => {
  assert.match(qml, /property string feedbackText/);
  assert.match(qml, /id:\s*feedbackTimer/);
  assert.match(qml, /feedbackTimer\.restart\(\)/);
  assert.match(qml, /queuedOperation === "schedule"[\s\S]*?root\.populateScheduleEditor\(\)/);
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
  assert.match(qml, /function reconcile\(\)\s*\{\s*root\.request\(\["reconcile"\],\s*"reconcile"\)\s*;/);
});

test('panel reconciles once after load, retrying until idle so an expired snooze applies even after a shell restart', () => {
  assert.match(qml, /id:\s*initialReconcileTimer[\s\S]*?interval:\s*1000[\s\S]*?repeat:\s*false/);
  assert.match(qml, /onTriggered:\s*\{[\s\S]*?if\s*\(root\.actionPending\)\s*\{[\s\S]*?initialReconcileTimer\.restart\(\);[\s\S]*?return\s*;[\s\S]*?root\.reconcile\(\)/);
});

test('global IPC toggleNightlight queues through the latest-wins request bus instead of silently dropping while busy or unavailable', () => {
  assert.match(qml, /function toggleNightlight\(\)\s*\{\s*root\.request\(\["nightlight",\s*"toggle"\],\s*"toggle"\)\s*;\s*\}/);
});

test('v2 panel exposes three native routes and route navigation preserves context', () => {
  assert.match(qml, /property string route:\s*"home"/);
  assert.match(qml, /routeOptions|routeOrder/);
  assert.match(i18n, /routeHome:\s*'Home'/);
  assert.match(i18n, /routeAutomation:\s*'Automation'/);
  assert.match(i18n, /routeSettings:\s*'Settings'/);
  assert.match(qml, /function navigateToRoute\(/);
});

test('entering the automation route refreshes both status and the editor drafts', () => {
  const nav = qml.slice(qml.indexOf('function navigateToRoute('), qml.indexOf('function refocusKeyCatcher()'));
  assert.match(nav, /if\s*\(nextRoute\s*===\s*"home"\)\s*root\.requestStatus\(\);/);
  assert.match(nav, /if\s*\(nextRoute\s*===\s*"automation"\)\s*\{\s*root\.populateScheduleEditor\(\);/);
  assert.match(nav, /root\.cursor\s*=\s*Model\.cursorStart\(\);/);
});

test('route sections match the three compact views', () => {
  assert.match(qml, /Model\.routeSections\(root\.route\)\[cursor\.section\]/);
});

test('keyboard activation opens the pickers, focuses editors and runs actions', () => {
  const activate = qml.slice(qml.indexOf('function activateCursor()'), qml.indexOf('moduleName:'));
  assert.match(activate, /section\s*===\s*"nightLight"[\s\S]*?\["nightlight",\s*"toggle"\]/);
  assert.match(activate, /section\s*===\s*"monitor"\)\s*\{\s*monitorSelector\.open\(\);/);
  assert.match(activate, /section\s*===\s*"scheduleToggle"[\s\S]*?root\.toggleSchedule\(!root\.scheduleEnabled\)/);
  assert.match(activate, /section\s*===\s*"schedule"\)\s*\{\s*startEditor\.forceActiveFocus\(\);/);
  assert.match(activate, /section\s*===\s*"snooze"\)\s*\{\s*root\.applySnooze\(\);/);
  assert.match(activate, /section\s*===\s*"locale"\)\s*\{\s*localeSelector\.open\(\);/);
  assert.match(activate, /section\s*===\s*"shortcut"\)\s*\{\s*shortcutField\.forceActiveFocus\(\);/);
  assert.match(activate, /section\s*===\s*"shortcutActions"[\s\S]*?install",\s*"--keys",\s*shortcutField\.text/);
});

test('the blocked gate covers every editor and popup that must own its keys', () => {
  assert.match(qml, /readonly property bool keyCatcherBlocked:/);
  for (const owner of [
    'startEditor.activeFocus', 'endEditor.activeFocus',
    'dayTemperatureEditor.field.activeFocus', 'dayBrightnessEditor.field.activeFocus',
    'dayGammaEditor.field.activeFocus', 'nightTemperatureEditor.field.activeFocus',
    'nightBrightnessEditor.field.activeFocus', 'nightGammaEditor.field.activeFocus',
    'snoozeEditor.field.activeFocus', 'shortcutField.activeFocus',
    'monitorSelector.popupOpen', 'localeSelector.popupOpen'
  ]) {
    assert.ok(qml.includes(owner), `keyCatcherBlocked must include ${owner}`);
  }
});

test('editors and popups return focus before Escape can close the panel', () => {
  assert.match(qml, /onPopupOpenChanged:\s*if\s*\(!monitorSelector\.popupOpen\)\s*Qt\.callLater\(function\(\)\s*\{\s*keyCatcher\.forceActiveFocus\(\);\s*\}\)/);
  assert.match(qml, /onPopupOpenChanged:\s*if\s*\(!localeSelector\.popupOpen\)\s*Qt\.callLater\(function\(\)\s*\{\s*keyCatcher\.forceActiveFocus\(\);\s*\}\)/);
  assert.match(qml, /id:\s*shortcutField[\s\S]*?Keys\.onEscapePressed:\s*keyCatcher\.forceActiveFocus\(\)/);
  assert.match(qml, /id:\s*startEditor[\s\S]*?Keys\.onEscapePressed:\s*keyCatcher\.forceActiveFocus\(\)/);
});

test('requests launch immediately when idle and only debounce bursts to preserve latest-wins', () => {
  const requestBlock = qml.slice(qml.indexOf('function request(command, operation) {'), qml.indexOf('function queueMutation('));
  assert.match(requestBlock, /if\s*\(\s*helperProcess\.running\s*\|\|\s*root\.stoppingForLatest\s*\|\|\s*debounce\.running\s*\)/);
  assert.match(requestBlock, /debounce\.restart\(\)/);
  assert.match(requestBlock, /debounce\.stop\(\)/);
  assert.match(requestBlock, /root\.launchLatest\(\)/);
});

test('a superseded helper exit cancels the stale burst debounce before relaunching the latest', () => {
  assert.match(qml, /if\s*\(\s*requestId\s*!==\s*latestRequestId\s*\)\s*\{\s*debounce\.stop\(\);\s*Qt\.callLater\(root\.launchLatest\);/);
});

test('a superseded helper exit still adopts the state of the write that physically applied', () => {
  assert.match(qml, /function mergeStaleResponse\(exitCode\)/);
  assert.match(qml, /if\s*\(\s*requestId\s*!==\s*latestRequestId\s*\)\s*\{[\s\S]*?Qt\.callLater\(root\.launchLatest\);\s*root\.mergeStaleResponse\(exitCode\);\s*return ;\s*\}/);
  const merge = qml.slice(qml.indexOf('function mergeStaleResponse(exitCode)'), qml.indexOf('function handleExit(exitCode)'));
  assert.match(merge, /if\s*\(exitCode\s*!==\s*0\)\s*return ;/);
  assert.match(merge, /JSON\.parse\(processOutput\)/);
  assert.match(merge, /Model\.mergeStatePatch\(state,\s*patch\)/);
});

test('brightness writes pass the selected monitor and nightlight writes do not', () => {
  assert.match(qml, /request\(\["brightness",\s*String\(Math\.round\(value\)\),\s*"--monitor",\s*root\.selectedMonitor\],\s*section\)/);
  assert.match(qml, /request\(\["nightlight",\s*section,\s*String\(Math\.round\(value\)\)\],\s*section\)/);
});

test('pointer drags record the latest drag target through the request bus', () => {
  assert.match(qml, /function queueDragMutation\(section,\s*value\)[\s\S]*?Model\.dragTargetPush\(root\.dragTarget,\s*section,\s*value\)[\s\S]*?root\.queueMutation\(section,\s*value\)/);
  for (const section of ['brightness', 'temperature', 'gamma'])
    assert.match(qml, new RegExp(`onMoved:\\s*function\\(v\\)\\s*\\{\\s*root\\.queueDragMutation\\("${section}",\\s*v\\)\\s*\\}`));
});

test('confirmed readbacks advance the drag chase with the helper tolerances', () => {
  assert.match(qml, /function reconcilePending\(\)[\s\S]*?Model\.reconcileDragTargets\(state,\s*root\.state,\s*root\.dragTarget,\s*root\.queuedOperation\)/);
  assert.match(qml, /root\.dragTarget\s*=\s*drag\.target/);
  assert.match(qml, /root\.queueMutation\(drag\.requests\[j\]\.section,\s*drag\.requests\[j\]\.value\)/);
});

test('failed requests clear the pending drag target', () => {
  const exitBlock = qml.slice(qml.indexOf('function handleExit(exitCode) {'), qml.indexOf('function moveCursorVertically'));
  assert.match(exitBlock, /actionPending\s*=\s*false;[\s\S]*?root\.dragTarget\s*=\s*Model\.dragTargetEmpty\(\);/);
});

test('ToggleSwitch count is the two real toggles and neither binds interactive to pending state', () => {
  const switchCount = (qml.match(/\bToggleSwitch\s*\{/g) || []).length;
  assert.equal(switchCount, 2, 'expected exactly 2 ToggleSwitch instances in Panel.qml');
  assert.doesNotMatch(qml, /ToggleSwitch\s*\{[^}]*interactive:\s*[^;\n]*actionPending/);

  const heroSwitch = qml.slice(qml.indexOf('trailingControl: Component {'), qml.indexOf('id: homeRoute'));
  assert.match(heroSwitch, /busy:\s*!root\.stateReady\s*\|\|\s*root\.actionPending/);
  assert.match(heroSwitch, /Accessible\.name:\s*root\.text\("night_light"\)/);

  const schedSwitch = qml.slice(qml.indexOf('id: scheduleToggle'), qml.indexOf('id: scheduleEditorColumn'));
  assert.match(schedSwitch, /busy:\s*!root\.automationReady\s*\|\|\s*root\.actionPending/);
  assert.match(schedSwitch, /Accessible\.name:\s*root\.text\("schedule"\)/);
});

test('schedule enabled semantics stay honest before the automation payload is available', () => {
  assert.match(qml, /readonly\s+property\s+bool\s+automationReady:\s*Boolean\(root\.state\.automation\s*&&\s*root\.state\.automation\.available\s*===\s*true\)/);
  assert.match(qml, /readonly\s+property\s+bool\s+scheduleEnabled:\s*Boolean\(root\.automationReady\s*&&\s*root\.state\.automation\.schedule_enabled\s*!==\s*false\)/);
});

test('ids are never accessed through the root object', () => {
  assert.doesNotMatch(qml, /root\.(helperProcess|debounce|feedbackTimer|keyCatcher)\b/);
  assert.match(qml, /if \(helperProcess\.running \|\| root\.stoppingForLatest \|\| debounce\.running\) \{/);
});

test('focusable action buttons return focus to the key catcher after their click', () => {
  assert.match(qml, /function refocusKeyCatcher\(\)\s*\{\s*Qt\.callLater\(function\(\)\s*\{\s*if\s*\(keyCatcher\)\s*keyCatcher\.forceActiveFocus\(\);\s*\}\s*\);\s*\}/);
  const actions = [
    'root.switchRouteBy(-1)',
    'root.switchRouteBy(1)',
    'root.queueSchedule()',
    'root.applySnooze()',
    'root.settingsCommand("snooze", ["clear"])',
    'root.settingsCommand("shortcut", ["remove"])'
  ];
  for (const action of actions) {
    assert.ok(qml.includes(`${action};`), `action must exist: ${action}`);
  }
  assert.match(qml, /root\.settingsCommand\("shortcut",\s*\["install",\s*"--keys",\s*shortcutField\.text\]\);\s*root\.refocusKeyCatcher\(\);/);
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

test('bar glyph and tooltip are dynamic and expose live provenance', () => {
  assert.match(barQml, /readonly property string barGlyph/);
  assert.match(barQml, /readonly property string barTooltip/);
  assert.match(barQml, /state\.automation|state\.origin/);
  assert.match(barQml, /text:\s*root\.barGlyph/);
  assert.match(barQml, /tooltipText:\s*root\.barTooltip/);
});

// ============================================================================
// TIER 1: FEATURE COVERAGE (Design Tokens, Components, and UI Layout Contracts)
// ============================================================================

test('Tier 1 - F1 Design Tokens: Panel.qml and BarWidget.qml import qs.Commons and qs.Ui', () => {
  assert.match(qml, /import qs\.Commons/);
  assert.match(qml, /import qs\.Ui/);
  assert.match(barQml, /import qs\.Commons/);
  assert.match(barQml, /import qs\.Ui/);
});

test('Tier 1 - F1 Design Tokens: Named panel geometry and spacing use Style.space tokens', () => {
  assert.match(qml, /readonly property int panelWidth:\s*Style\.space\(330\)/);
  assert.match(qml, /readonly property int panelMaxHeight:\s*Style\.space\(560\)/);
  assert.match(qml, /readonly property int controlIconSlot:\s*Style\.space\(20\)/);
  assert.match(qml, /readonly property int sectionPad:\s*Style\.space\(6\)/);
  assert.match(qml, /readonly property int headerPad:\s*Style\.space\(16\)/);
});

test('Tier 1 - F2 Bar Widget: Mouse button handlers support Right click, Middle click, and Toggle', () => {
  assert.match(barQml, /if\s*\(buttonCode\s*===\s*Qt\.RightButton\)[\s\S]*?requestStatus\(\)/);
  assert.match(barQml, /if\s*\(buttonCode\s*===\s*Qt\.MiddleButton\)[\s\S]*?close\(\)/);
  assert.match(barQml, /root\.toggle\(\)/);
});

test('Tier 1 - F3 Panel Hero: Hero surface embeds toggle switch with busy and accessible name bindings', () => {
  assert.match(qml, /id:\s*heroSurface/);
  assert.match(qml, /trailingControl:\s*Component\s*\{[\s\S]*?ToggleSwitch/);
  assert.match(qml, /title:\s*root\.text\("night_light"\)/);
});

test('Tier 1 - F5 Quick Snooze: Snooze row binds number field, unit picker, and apply action', () => {
  assert.match(qml, /id:\s*snoozeColumn/);
  assert.match(qml, /id:\s*snoozeEditor/);
  assert.match(qml, /root\.applySnooze\(\)/);
  assert.match(qml, /root\.snoozeActive/);
});

test('Tier 1 - F8 Settings Route: Shortcut visual field and action buttons are properly configured', () => {
  assert.match(qml, /id:\s*shortcutField/);
  assert.match(qml, /root\.settingsCommand\("shortcut",\s*\["install",\s*"--keys",\s*shortcutField\.text\]\)/);
  assert.match(qml, /root\.settingsCommand\("shortcut",\s*\["remove"\]\)/);
  assert.match(qml, /id:\s*localeSelector/);
});

test('Tier 1 - F9 Hybrid Navigation: keyCatcher intercepts arrow keys, return, and escape', () => {
  assert.match(qml, /id:\s*keyCatcher/);
  assert.match(qml, /Keys\.onPressed:\s*function\(event\)/);
  assert.match(qml, /event\.key\s*===\s*Qt\.Key_Left/);
  assert.match(qml, /event\.key\s*===\s*Qt\.Key_Right/);
  assert.match(qml, /event\.key\s*===\s*Qt\.Key_Up/);
  assert.match(qml, /event\.key\s*===\s*Qt\.Key_Down/);
  assert.match(qml, /event\.key\s*===\s*Qt\.Key_Return/);
  assert.match(qml, /event\.key\s*===\s*Qt\.Key_Escape/);
});


// ============================================================================
// TIER 2: BOUNDARY & CORNER CASES (Focus isolation, signals, and popups)
// ============================================================================

test('Tier 2 - F9 Focus Isolation: keyCatcherBlocked isolates all 12 input and popup surfaces', () => {
  const blockedProps = [
    'startEditor.activeFocus',
    'endEditor.activeFocus',
    'dayTemperatureEditor.field.activeFocus',
    'dayBrightnessEditor.field.activeFocus',
    'dayGammaEditor.field.activeFocus',
    'nightTemperatureEditor.field.activeFocus',
    'nightBrightnessEditor.field.activeFocus',
    'nightGammaEditor.field.activeFocus',
    'snoozeEditor.field.activeFocus',
    'shortcutField.activeFocus',
    'monitorSelector.popupOpen',
    'localeSelector.popupOpen'
  ];
  for (const prop of blockedProps) {
    assert.ok(qml.includes(prop), `keyCatcherBlocked must guard: ${prop}`);
  }
});

test('Tier 2 - F8 Dropdown Popups: Escape key and popup close restore keyCatcher focus safely', () => {
  assert.match(qml, /if\s*\(!monitorSelector\.popupOpen\)\s*Qt\.callLater/);
  assert.match(qml, /if\s*\(!localeSelector\.popupOpen\)\s*Qt\.callLater/);
  assert.match(qml, /shortcutField[\s\S]*?Keys\.onEscapePressed:\s*keyCatcher\.forceActiveFocus\(\)/);
  assert.match(qml, /startEditor[\s\S]*?Keys\.onEscapePressed:\s*keyCatcher\.forceActiveFocus\(\)/);
});

test('Tier 2 - F11 Monotonic Bus: Process cancellation and burst debouncing prevent race conditions', () => {
  assert.match(qml, /function launchLatest\(\)/);
  assert.match(qml, /if\s*\(helperProcess\.running\)\s*\{[\s\S]*?stoppingForLatest\s*=\s*true;[\s\S]*?helperProcess\.running\s*=\s*false;/);
  assert.match(qml, /id:\s*debounce[\s\S]*?interval:\s*90/);
});

test('Tier 1 - F6 Route Transitions: Panel.qml defines animated cross-fade, directional slide, and container height morphing', () => {
  assert.match(qml, /property int transitionDirection:\s*1/);
  assert.match(qml, /KeyboardPanel\s*\{[\s\S]*?Behavior on contentHeight\s*\{\s*NumberAnimation\s*\{[\s\S]*?duration:\s*180[\s\S]*?easing\.type:\s*Easing\.OutCubic/);
  assert.match(qml, /if\s*\(panelFlick\)\s*panelFlick\.contentY\s*=\s*0;/);

  for (const containerId of ['heroSurface', 'homeRoute', 'automationRoute', 'settingsRoute']) {
    const block = qml.slice(qml.indexOf(`id: ${containerId}`), qml.indexOf(`id: ${containerId}`) + 1200);
    assert.match(block, /opacity:\s*root\.route\s*===\s*"\w+"\s*\?\s*1\.0\s*:\s*0\.0/);
    assert.match(block, /Behavior on opacity\s*\{\s*NumberAnimation\s*\{[\s\S]*?duration:\s*180/);
    assert.match(block, /transform:\s*Translate\s*\{[\s\S]*?Behavior on x\s*\{\s*NumberAnimation\s*\{[\s\S]*?duration:\s*180/);
  }
});

test('Tier 1 - F7 Schedule Grid: Aligned inputs, duration badges, and resetScheduleButton satisfy contracts', () => {
  const editor = qml.slice(qml.indexOf('id: scheduleEditorColumn'), qml.indexOf('// Snooze:'));
  assert.match(editor, /id:\s*startEditor[\s\S]*?horizontalAlignment:\s*Qt\.AlignHCenter/);
  assert.match(editor, /id:\s*endEditor[\s\S]*?horizontalAlignment:\s*Qt\.AlignHCenter/);
  assert.match(editor, /id:\s*dayDurationBadge/);
  assert.match(editor, /id:\s*nightDurationBadge/);
  assert.match(editor, /id:\s*resetScheduleButton/);
  assert.match(editor, /id:\s*saveScheduleButton/);
  assert.match(editor, /root\.populateScheduleEditor\(\)/);
  assert.match(editor, /root\.queueSchedule\(\)/);
  assert.match(editor, /id:\s*feedbackBanner[\s\S]*?Behavior on opacity/);
});

test('Tier 1 - F8 Settings Visuals: Shortcut badge chips row and enriched monitor descriptions render properly', () => {
  const settings = qml.slice(qml.indexOf('id: settingsRoute'), qml.indexOf('root.text("keyboard_hints")'));
  assert.match(settings, /id:\s*shortcutBadgeRow/);
  assert.match(settings, /id:\s*shortcutChipsRepeater/);
  assert.match(settings, /Model\.parseShortcutTokens\(shortcutField\.text\)/);

  assert.match(qml, /function monitorChoices\(\)/);
  assert.match(qml, /focusedName\s*\?\s*\("\("\s*\+\s*focusedName\s*\+\s*"\)"\)\s*:\s*""/);
});

test('Tier 1 - F10 Error and Feedback Banners: Styled BorderSurface containers with icons and animations', () => {
  // Global error banner
  assert.match(qml, /id:\s*globalErrorBanner[\s\S]*?Behavior on opacity[\s\S]*?Icons\.glyph\("alert"\)/);

  // Schedule validation banner
  const editor = qml.slice(qml.indexOf('id: scheduleEditorColumn'), qml.indexOf('// Snooze:'));
  assert.match(editor, /id:\s*scheduleValidationBanner[\s\S]*?Behavior on opacity[\s\S]*?Icons\.glyph\("alert"\)/);

  // Settings feedback banner
  const settings = qml.slice(qml.indexOf('id: settingsRoute'), qml.indexOf('root.text("keyboard_hints")'));
  assert.match(settings, /id:\s*settingsFeedbackBanner[\s\S]*?Behavior on opacity[\s\S]*?Icons\.glyph\("check"\)/);

  // Shortcut positive feedback trigger
  assert.match(qml, /queuedOperation === "shortcut"[\s\S]*?feedbackText = root\.text\("saved"\)[\s\S]*?feedbackTimer\.restart\(\)/);
});
