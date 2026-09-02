import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Model from '../UiModel.js';

const qml = fs.readFileSync(new URL('../Panel.qml', import.meta.url), 'utf8');

// --- Helper to extract Panel navigation state machine logic ---
function createPanelState() {
  const routeOptions = Model.routeOrder(); // ['home', 'automation', 'settings']
  let state = {
    route: 'home',
    transitionDirection: 1,
    dragTarget: Model.dragTargetEmpty(),
    cursor: Model.cursorStart(),
    routeOptions: routeOptions,
    flickContentY: 0,
    activeFocusItem: 'keyCatcher',
    stateReady: true,
    latestRequestId: 0,
    editStart: '06:00',
    editEnd: '18:00',
    editDayTemperature: '6000',
    editNightTemperature: '3500',
    state: {
      available: true,
      enabled: true,
      brightness: { percent: 50 },
      nightlight: { temperature: 3500, gamma: 100 },
      temperature: 3500,
      gamma: 100,
      schedule: {
        available: true,
        day_time: '07:00',
        night_time: '20:00',
        day_temp: 6200,
        night_temp: 3200
      }
    },
    requestsSent: []
  };

  function populateScheduleEditor() {
    if (state.state && state.state.schedule) {
      state.editStart = state.state.schedule.day_time || '06:00';
      state.editEnd = state.state.schedule.night_time || '18:00';
      state.editDayTemperature = String(state.state.schedule.day_temp || 6000);
      state.editNightTemperature = String(state.state.schedule.night_temp || 3500);
    }
  }

  function navigateToRoute(nextRoute) {
    if (state.routeOptions.indexOf(nextRoute) === -1) return;
    if (nextRoute !== state.route) {
      const curIdx = state.routeOptions.indexOf(state.route);
      const nextIdx = state.routeOptions.indexOf(nextRoute);
      if (curIdx === 2 && nextIdx === 0) {
        state.transitionDirection = 1;
      } else if (curIdx === 0 && nextIdx === 2) {
        state.transitionDirection = -1;
      } else {
        state.transitionDirection = nextIdx >= curIdx ? 1 : -1;
      }
      state.dragTarget = Model.dragTargetEmpty();
      state.cursor = Model.cursorStart();
    }
    state.route = nextRoute;
    if (nextRoute === 'home') {
      state.latestRequestId++;
      state.requestsSent.push({ action: 'status', reqId: state.latestRequestId });
    }
    if (nextRoute === 'automation') {
      populateScheduleEditor();
      state.latestRequestId++;
      state.requestsSent.push({ action: 'schedule-status', reqId: state.latestRequestId });
    }
    state.flickContentY = 0;
    state.activeFocusItem = 'keyCatcher';
  }

  function switchRouteBy(direction) {
    navigateToRoute(Model.adjacentRoute(state.route, direction));
  }

  function adjustSliderBy(direction) {
    const names = Model.routeSections(state.route);
    const section = names[state.cursor.section];
    if (!Model.isSliderSection(section) || !state.stateReady)
      return false;
    let current = null;
    if (section === 'brightness') current = state.state.brightness.percent;
    if (section === 'temperature') current = state.state.temperature;
    if (section === 'gamma') current = state.state.gamma;
    const next = Model.stepSliderValue(section, direction, current);
    if (next === null) return false;
    state.dragTarget = Model.dragTargetPush(state.dragTarget, section, next);
    state.latestRequestId++;
    state.requestsSent.push({ action: section, value: next, reqId: state.latestRequestId });
    return true;
  }

  function moveCursorVertically(delta) {
    const key = delta > 0 ? 'ArrowDown' : 'ArrowUp';
    state.cursor = Model.moveCursor(state.cursor, key, state.route);
  }

  function refocusKeyCatcher() {
    state.activeFocusItem = 'keyCatcher';
  }

  return {
    state,
    navigateToRoute,
    switchRouteBy,
    adjustSliderBy,
    moveCursorVertically,
    refocusKeyCatcher,
    populateScheduleEditor
  };
}

// ---------------------------------------------------------------------------
// Tier 1: Direction Tracking and Route Ring Invariants
// ---------------------------------------------------------------------------

test('Direction tracking follows ring navigation in both directions', () => {
  const { state, navigateToRoute } = createPanelState();

  // Forward ring traversal: home (0) -> automation (1) -> settings (2) -> home (0)
  navigateToRoute('automation');
  assert.equal(state.route, 'automation');
  assert.equal(state.transitionDirection, 1, 'home -> automation must be +1');

  navigateToRoute('settings');
  assert.equal(state.route, 'settings');
  assert.equal(state.transitionDirection, 1, 'automation -> settings must be +1');

  navigateToRoute('home');
  assert.equal(state.route, 'home');
  assert.equal(state.transitionDirection, 1, 'settings -> home (forward wrap) must be +1');

  // Reverse ring traversal: home (0) -> settings (2) -> automation (1) -> home (0)
  navigateToRoute('settings');
  assert.equal(state.route, 'settings');
  assert.equal(state.transitionDirection, -1, 'home -> settings (reverse wrap) must be -1');

  navigateToRoute('automation');
  assert.equal(state.route, 'automation');
  assert.equal(state.transitionDirection, -1, 'settings -> automation must be -1');

  navigateToRoute('home');
  assert.equal(state.route, 'home');
  assert.equal(state.transitionDirection, -1, 'automation -> home must be -1');
});

test('Direction tracking ignores invalid routes and idempotent transitions', () => {
  const { state, navigateToRoute } = createPanelState();

  state.transitionDirection = 1;
  navigateToRoute('home'); // same route
  assert.equal(state.route, 'home');
  assert.equal(state.transitionDirection, 1);

  navigateToRoute('invalid_route');
  assert.equal(state.route, 'home');
  assert.equal(state.transitionDirection, 1);

  navigateToRoute(null);
  assert.equal(state.route, 'home');

  navigateToRoute(undefined);
  assert.equal(state.route, 'home');
});

// ---------------------------------------------------------------------------
// Tier 2: Rapid Route Switching Stress & Invariant Verification
// ---------------------------------------------------------------------------

test('Rapid route switching stress test (100,000 transitions) maintains integrity', () => {
  const { state, navigateToRoute, switchRouteBy } = createPanelState();
  const routes = ['home', 'automation', 'settings'];

  const initialMemory = process.memoryUsage().heapUsed;

  for (let i = 0; i < 100000; i++) {
    // Alternate between forward, backward, random, and duplicate switches
    const mode = i % 4;
    if (mode === 0) {
      switchRouteBy(1);
    } else if (mode === 1) {
      switchRouteBy(-1);
    } else if (mode === 2) {
      const target = routes[Math.floor(Math.random() * routes.length)];
      navigateToRoute(target);
    } else {
      navigateToRoute(state.route); // duplicate
    }

    assert.ok(routes.includes(state.route), `Route must be valid, got ${state.route}`);
    assert.ok(state.transitionDirection === 1 || state.transitionDirection === -1, 'Direction must be +1 or -1');
    assert.deepEqual(state.cursor, { section: 0, field: 0 }, 'Cursor must be reset');
    assert.deepEqual(state.dragTarget, { brightness: null, temperature: null, gamma: null }, 'Drag target must be reset');
    assert.equal(state.flickContentY, 0, 'Scroll position must be reset to 0');
    assert.equal(state.activeFocusItem, 'keyCatcher', 'Focus must target keyCatcher');
  }

  const finalMemory = process.memoryUsage().heapUsed;
  const memoryDeltaMB = (finalMemory - initialMemory) / (1024 * 1024);
  assert.ok(memoryDeltaMB < 25, `Memory delta should be bounded, got ${memoryDeltaMB.toFixed(2)} MB`);
});

// ---------------------------------------------------------------------------
// Tier 3: Hybrid Keyboard Navigation vs Slider Interception
// ---------------------------------------------------------------------------

test('Left/Right arrows adjust sliders on slider sections and switch routes elsewhere', () => {
  const panel = createPanelState();

  // Section 0 on home: nightLight (toggle) -> Left/Right switches view
  assert.equal(panel.state.cursor.section, 0);
  let handled = panel.adjustSliderBy(1);
  assert.equal(handled, false, 'nightLight is not a slider');
  panel.switchRouteBy(1);
  assert.equal(panel.state.route, 'automation');

  panel.navigateToRoute('home');

  // Move cursor to section 1: brightness
  panel.moveCursorVertically(1);
  assert.equal(panel.state.cursor.section, 1);
  assert.equal(panel.state.state.brightness.percent, 50);

  handled = panel.adjustSliderBy(1);
  assert.equal(handled, true, 'brightness slider handled step');
  assert.equal(panel.state.dragTarget.brightness, 51);
  assert.equal(panel.state.route, 'home', 'route must NOT change while adjusting slider');

  handled = panel.adjustSliderBy(-1);
  assert.equal(handled, true);
  assert.equal(panel.state.dragTarget.brightness, 49);

  // Move cursor to section 2: temperature
  panel.moveCursorVertically(1);
  assert.equal(panel.state.cursor.section, 2);
  handled = panel.adjustSliderBy(1);
  assert.equal(handled, true);
  assert.equal(panel.state.dragTarget.temperature, 3550);
  assert.equal(panel.state.route, 'home');

  // Move cursor to section 3: gamma
  panel.moveCursorVertically(1);
  assert.equal(panel.state.cursor.section, 3);
  handled = panel.adjustSliderBy(-1);
  assert.equal(handled, true);
  assert.equal(panel.state.dragTarget.gamma, 99);
  assert.equal(panel.state.route, 'home');

  // Move cursor to section 4: monitor dropdown -> Left/Right switches view
  panel.moveCursorVertically(1);
  assert.equal(panel.state.cursor.section, 4);
  handled = panel.adjustSliderBy(1);
  assert.equal(handled, false, 'monitor dropdown is not a slider');
  panel.switchRouteBy(1);
  assert.equal(panel.state.route, 'automation');
});

test('Automation and Settings routes always allow Left/Right view switching', () => {
  const panel = createPanelState();

  // Automation route
  panel.navigateToRoute('automation');
  const autoSections = Model.routeSections('automation');
  for (let s = 0; s < autoSections.length; s++) {
    panel.state.cursor.section = s;
    assert.equal(panel.adjustSliderBy(1), false, `Automation section ${autoSections[s]} must not intercept`);
    assert.equal(panel.adjustSliderBy(-1), false, `Automation section ${autoSections[s]} must not intercept`);
  }

  // Settings route
  panel.navigateToRoute('settings');
  const settingsSections = Model.routeSections('settings');
  for (let s = 0; s < settingsSections.length; s++) {
    panel.state.cursor.section = s;
    assert.equal(panel.adjustSliderBy(1), false, `Settings section ${settingsSections[s]} must not intercept`);
    assert.equal(panel.adjustSliderBy(-1), false, `Settings section ${settingsSections[s]} must not intercept`);
  }
});

// ---------------------------------------------------------------------------
// Tier 4: Async Request Bus & Stale Response Interleaving during Route Switch
// ---------------------------------------------------------------------------

test('In-flight slider drag request arriving after route transition is safely superseded', () => {
  const panel = createPanelState();

  // Cursor on brightness slider
  panel.moveCursorVertically(1);
  assert.equal(panel.state.cursor.section, 1);

  // User steps brightness -> Request #1 launched
  panel.adjustSliderBy(1);
  assert.equal(panel.state.latestRequestId, 1);
  assert.equal(panel.state.dragTarget.brightness, 51);

  // User immediately switches to automation route before Request #1 finishes
  panel.navigateToRoute('automation');
  assert.equal(panel.state.route, 'automation');
  assert.equal(panel.state.latestRequestId, 2); // schedule-status launched
  assert.deepEqual(panel.state.dragTarget, { brightness: null, temperature: null, gamma: null });

  // Stale response #1 arrives from backend helper
  const staleCommit = Model.commitResponse(panel.state.state, {
    requestId: 1,
    latestRequestId: panel.state.latestRequestId, // 2
    ok: true,
    state: { brightness: { available: true, percent: 51 } }
  });

  // Since requestId (1) < latestRequestId (2), commit is rejected as stale
  assert.equal(staleCommit.accepted, false);
  // Drag target on panel remains clean
  assert.deepEqual(panel.state.dragTarget, { brightness: null, temperature: null, gamma: null });

  // Switching back to home re-queries status
  panel.navigateToRoute('home');
  assert.equal(panel.state.route, 'home');
  assert.equal(panel.state.latestRequestId, 3);
});

test('Schedule draft state resets cleanly on route switch and reset button click', () => {
  const panel = createPanelState();

  // Switch to automation route
  panel.navigateToRoute('automation');
  assert.equal(panel.state.editStart, '07:00');
  assert.equal(panel.state.editEnd, '20:00');

  // User edits drafts
  panel.state.editStart = '05:00';
  panel.state.editEnd = '22:00';
  assert.equal(panel.state.editStart, '05:00');

  // User clicks resetScheduleButton
  panel.populateScheduleEditor();
  assert.equal(panel.state.editStart, '07:00');
  assert.equal(panel.state.editEnd, '20:00');
});

// ---------------------------------------------------------------------------
// Tier 5: QML Kinetic Transitions, Height Morphing, and Focus Contracts
// ---------------------------------------------------------------------------

test('Panel.qml defines 180ms Easing.OutCubic animations for height, opacity, and translate', () => {
  // Container height morphing
  assert.match(
    qml,
    /KeyboardPanel\s*\{[\s\S]*?Behavior on contentHeight\s*\{\s*NumberAnimation\s*\{\s*duration:\s*180[\s\S]*?easing\.type:\s*Easing\.OutCubic/
  );

  // Cross-fade and translate on all route views
  const viewContainers = ['heroSurface', 'homeRoute', 'automationRoute', 'settingsRoute'];
  for (const cid of viewContainers) {
    const idx = qml.indexOf(`id: ${cid}`);
    assert.ok(idx !== -1, `Container ${cid} must exist`);
    const slice = qml.slice(idx, idx + 1000);

    assert.match(slice, /Behavior on opacity\s*\{\s*NumberAnimation\s*\{\s*duration:\s*180[\s\S]*?easing\.type:\s*Easing\.OutCubic/, `${cid} must animate opacity with 180ms OutCubic`);
    assert.match(slice, /transform:\s*Translate\s*\{[\s\S]*?Behavior on x\s*\{\s*NumberAnimation\s*\{\s*duration:\s*180[\s\S]*?easing\.type:\s*Easing\.OutCubic/, `${cid} must animate translate x with 180ms OutCubic`);
  }
});

test('Panel.qml resets scroll position and refocuses key catcher on every navigation', () => {
  const navFunc = qml.slice(qml.indexOf('function navigateToRoute'), qml.indexOf('function refocusKeyCatcher'));
  assert.match(navFunc, /if\s*\(panelFlick\)\s*panelFlick\.contentY\s*=\s*0;/);
  assert.match(navFunc, /Qt\.callLater\(function\(\)\s*\{\s*if\s*\(keyCatcher\)\s*keyCatcher\.forceActiveFocus\(\);\s*\}\);/);
});

test('All interactive buttons in Panel.qml call refocusKeyCatcher to prevent dead focus traps', () => {
  // Navigation chevrons
  const prevBtn = qml.slice(qml.indexOf('id: prevRouteButton'), qml.indexOf('id: routeTitleText'));
  const nextBtn = qml.slice(qml.indexOf('id: nextRouteButton'), qml.indexOf('// Global helper errors'));
  assert.match(prevBtn, /root\.refocusKeyCatcher\(\)/);
  assert.match(nextBtn, /root\.refocusKeyCatcher\(\)/);

  // Automation schedule action buttons
  const resetBtn = qml.slice(qml.indexOf('id: resetScheduleButton'), qml.indexOf('id: saveScheduleButton'));
  const saveBtn = qml.slice(qml.indexOf('id: saveScheduleButton'), qml.indexOf('id: scheduleFeedbackRow'));
  assert.match(resetBtn, /root\.refocusKeyCatcher\(\)/);
  assert.match(saveBtn, /root\.refocusKeyCatcher\(\)/);

  // Settings shortcut buttons
  const settingsBlock = qml.slice(qml.indexOf('id: settingsRoute'), qml.indexOf('root.text("keyboard_hints")'));
  assert.match(settingsBlock, /text:\s*root\.text\("install_shortcut"\)[\s\S]*?root\.refocusKeyCatcher\(\)/);
  assert.match(settingsBlock, /text:\s*root\.text\("remove_shortcut"\)[\s\S]*?root\.refocusKeyCatcher\(\)/);

  // Quick snooze apply helper refocuses key catcher
  assert.match(qml, /function applyQuickSnooze[\s\S]*?root\.refocusKeyCatcher\(\)/);

  // Unit and manual snooze buttons refocus key catcher
  const snoozeBlock = qml.slice(qml.indexOf('id: snoozeEditor'), qml.indexOf('id: settingsRoute'));
  const snoozeRefocusMatches = snoozeBlock.match(/root\.refocusKeyCatcher\(\)/g) || [];
  assert.equal(snoozeRefocusMatches.length, 5, 'Unit and manual snooze buttons must call refocusKeyCatcher');
});

test('keyCatcherBlocked comprehensively guards all 12 input, editor, and popup focus surfaces', () => {
  const blockedDecl = qml.slice(qml.indexOf('readonly property bool keyCatcherBlocked:'), qml.indexOf('function normalizedPath'));
  const expectedGuards = [
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

  for (const guard of expectedGuards) {
    assert.ok(blockedDecl.includes(guard), `keyCatcherBlocked must guard ${guard}`);
  }
});

test('Escape keys on all text fields release active focus back to keyCatcher', () => {
  assert.match(qml, /startEditor[\s\S]*?Keys\.onEscapePressed:\s*keyCatcher\.forceActiveFocus\(\)/);
  assert.match(qml, /endEditor[\s\S]*?Keys\.onEscapePressed:\s*keyCatcher\.forceActiveFocus\(\)/);
  assert.match(qml, /shortcutField[\s\S]*?Keys\.onEscapePressed:\s*keyCatcher\.forceActiveFocus\(\)/);
});
