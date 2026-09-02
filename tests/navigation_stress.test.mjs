import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Model from '../UiModel.js';

const qml = fs.readFileSync(new URL('../Panel.qml', import.meta.url), 'utf8');

// ============================================================================
// Simulated Panel Navigation & Focus Harness
// ============================================================================

function createAdversarialPanelHarness(initialOverrides = {}) {
  const routeOptions = Model.routeOrder(); // ['home', 'automation', 'settings']
  
  let state = {
    route: 'home',
    transitionDirection: 1,
    dragTarget: Model.dragTargetEmpty(),
    cursor: Model.cursorStart(),
    routeOptions: routeOptions,
    flickContentY: 0,
    activeFocusItem: 'keyCatcher',
    panelOpened: true,
    closedCount: 0,
    stateReady: true,
    latestRequestId: 0,
    editStart: '06:00',
    editEnd: '18:00',
    editDayTemperature: '6000',
    editDayBrightness: '100',
    editDayGamma: '100',
    editNightTemperature: '3500',
    editNightBrightness: '100',
    editNightGamma: '100',
    snoozeAmount: 30,
    snoozeUnit: 'minutes',
    shortcutKeys: 'SUPER+SHIFT+N',
    selectedMonitor: 'focused',
    locale: 'en',
    // 12 focus trap items
    focusItems: {
      'startEditor': false,
      'endEditor': false,
      'dayTemperatureEditor.field': false,
      'dayBrightnessEditor.field': false,
      'dayGammaEditor.field': false,
      'nightTemperatureEditor.field': false,
      'nightBrightnessEditor.field': false,
      'nightGammaEditor.field': false,
      'snoozeEditor.field': false,
      'shortcutField': false,
      'monitorSelector.popupOpen': false,
      'localeSelector.popupOpen': false
    },
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
    requestsSent: [],
    ...initialOverrides
  };

  function isKeyCatcherBlocked() {
    return Object.values(state.focusItems).some(val => val === true);
  }

  function handleCloseRequested() {
    state.panelOpened = false;
    state.closedCount++;
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
      state.latestRequestId++;
      state.requestsSent.push({ action: 'schedule-status', reqId: state.latestRequestId });
    }
    state.flickContentY = 0;
    state.activeFocusItem = 'keyCatcher';
  }

  function switchRouteBy(direction) {
    navigateToRoute(Model.adjacentRoute(state.route, direction));
  }

  function sliderCurrentValue(section) {
    if (section === 'brightness') return state.state.brightness.percent;
    if (section === 'temperature') return state.state.temperature;
    if (section === 'gamma') return state.state.gamma;
    return null;
  }

  function adjustSliderBy(direction) {
    const names = Model.routeSections(state.route);
    const section = names[state.cursor.section];
    if (!Model.isSliderSection(section) || !state.stateReady)
      return false;
    const current = sliderCurrentValue(section);
    const next = Model.stepSliderValue(section, direction, current);
    if (next === null)
      return false;
    state.dragTarget = Model.dragTargetPush(state.dragTarget, section, next);
    state.latestRequestId++;
    state.requestsSent.push({ action: section, value: next, reqId: state.latestRequestId });
    return true;
  }

  function moveCursorVertically(direction) {
    const key = direction > 0 ? 'ArrowDown' : 'ArrowUp';
    state.cursor = Model.moveCursor(state.cursor, key, state.route);
  }

  function cursorToSection(index) {
    const names = Model.routeSections(state.route);
    if (index < 0 || index >= names.length) return;
    state.cursor = { section: index, field: 0 };
  }

  function refocusKeyCatcher() {
    state.activeFocusItem = 'keyCatcher';
    for (const key of Object.keys(state.focusItems)) {
      state.focusItems[key] = false;
    }
  }

  function handleKeyCatcherPress(key) {
    if (isKeyCatcherBlocked()) {
      return { handled: false, reason: 'blocked' };
    }
    if (key === 'Escape') {
      handleCloseRequested();
      return { handled: true, action: 'close' };
    }
    if (key === 'ArrowLeft') {
      if (!adjustSliderBy(-1)) {
        switchRouteBy(-1);
        return { handled: true, action: 'switchRoutePrev' };
      }
      return { handled: true, action: 'adjustSliderLeft' };
    }
    if (key === 'ArrowRight') {
      if (!adjustSliderBy(1)) {
        switchRouteBy(1);
        return { handled: true, action: 'switchRouteNext' };
      }
      return { handled: true, action: 'adjustSliderRight' };
    }
    if (key === 'ArrowUp') {
      moveCursorVertically(-1);
      return { handled: true, action: 'moveCursorUp' };
    }
    if (key === 'ArrowDown') {
      moveCursorVertically(1);
      return { handled: true, action: 'moveCursorDown' };
    }
    return { handled: false, reason: 'unrecognized' };
  }

  function focusTargetField(fieldKey) {
    if (state.focusItems.hasOwnProperty(fieldKey)) {
      for (const k of Object.keys(state.focusItems)) {
        state.focusItems[k] = false;
      }
      state.focusItems[fieldKey] = true;
      state.activeFocusItem = fieldKey;
    }
  }

  function releaseFocusFromField(fieldKey) {
    if (state.focusItems[fieldKey]) {
      state.focusItems[fieldKey] = false;
      state.activeFocusItem = 'keyCatcher';
    }
  }

  return {
    state,
    isKeyCatcherBlocked,
    handleCloseRequested,
    navigateToRoute,
    switchRouteBy,
    adjustSliderBy,
    moveCursorVertically,
    cursorToSection,
    refocusKeyCatcher,
    handleKeyCatcherPress,
    focusTargetField,
    releaseFocusFromField
  };
}

// ============================================================================
// Test Suite 1: Cursor Movement & Clamping Across All Routes
// ============================================================================

test('Cursor movement on route "home" traverses 0..4 and clamps at boundaries', () => {
  const harness = createAdversarialPanelHarness();
  harness.navigateToRoute('home');
  assert.equal(harness.state.route, 'home');
  assert.deepEqual(harness.state.cursor, { section: 0, field: 0 });

  // Up at section 0 clamps at 0
  harness.moveCursorVertically(-1);
  assert.deepEqual(harness.state.cursor, { section: 0, field: 0 }, 'Should clamp at top (0)');

  // Down 1 -> brightness (1)
  harness.moveCursorVertically(1);
  assert.deepEqual(harness.state.cursor, { section: 1, field: 0 });

  // Down 2 -> temperature (2)
  harness.moveCursorVertically(1);
  assert.deepEqual(harness.state.cursor, { section: 2, field: 0 });

  // Down 3 -> gamma (3)
  harness.moveCursorVertically(1);
  assert.deepEqual(harness.state.cursor, { section: 3, field: 0 });

  // Down 4 -> monitor (4)
  harness.moveCursorVertically(1);
  assert.deepEqual(harness.state.cursor, { section: 4, field: 0 });

  // Down at section 4 clamps at 4
  harness.moveCursorVertically(1);
  assert.deepEqual(harness.state.cursor, { section: 4, field: 0 }, 'Should clamp at bottom (4)');

  // 1000 consecutive Down presses still clamped at 4
  for (let i = 0; i < 1000; i++) {
    harness.moveCursorVertically(1);
  }
  assert.deepEqual(harness.state.cursor, { section: 4, field: 0 });

  // 1000 consecutive Up presses clamp at 0
  for (let i = 0; i < 1000; i++) {
    harness.moveCursorVertically(-1);
  }
  assert.deepEqual(harness.state.cursor, { section: 0, field: 0 });
});

test('Cursor movement on route "automation" traverses 0..2 and clamps at boundaries', () => {
  const harness = createAdversarialPanelHarness();
  harness.navigateToRoute('automation');
  assert.equal(harness.state.route, 'automation');
  assert.deepEqual(harness.state.cursor, { section: 0, field: 0 });

  // Up clamps at 0
  harness.moveCursorVertically(-1);
  assert.deepEqual(harness.state.cursor, { section: 0, field: 0 });

  // Down 1 -> schedule editor (1)
  harness.moveCursorVertically(1);
  assert.deepEqual(harness.state.cursor, { section: 1, field: 0 });

  // Down 2 -> snooze (2)
  harness.moveCursorVertically(1);
  assert.deepEqual(harness.state.cursor, { section: 2, field: 0 });

  // Down at section 2 clamps at 2
  harness.moveCursorVertically(1);
  assert.deepEqual(harness.state.cursor, { section: 2, field: 0 });

  for (let i = 0; i < 500; i++) {
    harness.moveCursorVertically(1);
  }
  assert.deepEqual(harness.state.cursor, { section: 2, field: 0 });
});

test('Cursor movement on route "settings" traverses 0..2 and clamps at boundaries', () => {
  const harness = createAdversarialPanelHarness();
  harness.navigateToRoute('settings');
  assert.equal(harness.state.route, 'settings');
  assert.deepEqual(harness.state.cursor, { section: 0, field: 0 });

  // Up clamps at 0
  harness.moveCursorVertically(-1);
  assert.deepEqual(harness.state.cursor, { section: 0, field: 0 });

  // Down 1 -> shortcut (1)
  harness.moveCursorVertically(1);
  assert.deepEqual(harness.state.cursor, { section: 1, field: 0 });

  // Down 2 -> shortcutActions (2)
  harness.moveCursorVertically(1);
  assert.deepEqual(harness.state.cursor, { section: 2, field: 0 });

  // Down at section 2 clamps at 2
  harness.moveCursorVertically(1);
  assert.deepEqual(harness.state.cursor, { section: 2, field: 0 });

  for (let i = 0; i < 500; i++) {
    harness.moveCursorVertically(1);
  }
  assert.deepEqual(harness.state.cursor, { section: 2, field: 0 });
});

test('Cursor resets to { section: 0, field: 0 } on every route transition', () => {
  const harness = createAdversarialPanelHarness();

  // Move to section 4 on home
  harness.navigateToRoute('home');
  harness.cursorToSection(4);
  assert.equal(harness.state.cursor.section, 4);

  // Switch to automation -> must reset to 0 (since 4 is invalid for automation)
  harness.navigateToRoute('automation');
  assert.deepEqual(harness.state.cursor, { section: 0, field: 0 });

  // Move to section 2 on automation
  harness.cursorToSection(2);
  assert.equal(harness.state.cursor.section, 2);

  // Switch to settings -> must reset to 0
  harness.navigateToRoute('settings');
  assert.deepEqual(harness.state.cursor, { section: 0, field: 0 });

  // Move to section 2 on settings
  harness.cursorToSection(2);
  assert.equal(harness.state.cursor.section, 2);

  // Switch to home -> must reset to 0
  harness.navigateToRoute('home');
  assert.deepEqual(harness.state.cursor, { section: 0, field: 0 });
});

test('Model.moveCursor handles malformed cursor states and invalid keys robustly', () => {
  const routes = ['home', 'automation', 'settings'];

  for (const route of routes) {
    const sections = Model.routeSections(route);
    const maxIdx = sections.length - 1;

    // Null/undefined cursor
    assert.deepEqual(Model.moveCursor(null, 'ArrowDown', route), { section: 1, field: 0 });
    assert.deepEqual(Model.moveCursor(undefined, 'ArrowUp', route), { section: 0, field: 0 });
    assert.deepEqual(Model.moveCursor({}, 'ArrowDown', route), { section: 1, field: 0 });

    // Negative cursor index clamps to 0
    assert.deepEqual(Model.moveCursor({ section: -10 }, 'ArrowUp', route), { section: 0, field: 0 });
    assert.deepEqual(Model.moveCursor({ section: -10 }, 'ArrowDown', route), { section: 1, field: 0 });

    // Out-of-bounds large cursor index clamps to maxIdx
    assert.deepEqual(Model.moveCursor({ section: 9999 }, 'ArrowDown', route), { section: maxIdx, field: 0 });
    assert.deepEqual(Model.moveCursor({ section: 9999 }, 'ArrowUp', route), { section: maxIdx - 1, field: 0 });

    // Non-numeric cursor index defaults to 0
    assert.deepEqual(Model.moveCursor({ section: 'invalid' }, 'ArrowDown', route), { section: 1, field: 0 });
    assert.deepEqual(Model.moveCursor({ section: NaN }, 'ArrowUp', route), { section: 0, field: 0 });

    // Non-arrow keys leave bounded section intact
    assert.deepEqual(Model.moveCursor({ section: 1 }, 'KeyA', route), { section: 1, field: 0 });
    assert.deepEqual(Model.moveCursor({ section: 1 }, 'Escape', route), { section: 1, field: 0 });
    assert.deepEqual(Model.moveCursor({ section: 1 }, null, route), { section: 1, field: 0 });
  }
});

// ============================================================================
// Test Suite 2: Slider Stepping vs View Switching on Left/Right Keys
// ============================================================================

test('Slider stepping on brightness, temperature, and gamma operates precisely with boundary clamping', () => {
  const harness = createAdversarialPanelHarness();
  harness.navigateToRoute('home');

  // 1. Brightness slider (section 1: range 1..100, step 1)
  harness.cursorToSection(1);
  harness.state.state.brightness.percent = 50;

  // Step right
  let res = harness.handleKeyCatcherPress('ArrowRight');
  assert.equal(res.action, 'adjustSliderRight');
  assert.equal(harness.state.dragTarget.brightness, 51);
  assert.equal(harness.state.route, 'home');

  // Step left
  res = harness.handleKeyCatcherPress('ArrowLeft');
  assert.equal(res.action, 'adjustSliderLeft');
  assert.equal(harness.state.dragTarget.brightness, 49);
  assert.equal(harness.state.route, 'home');

  // Test lower boundary clamp (1%)
  harness.state.state.brightness.percent = 1;
  res = harness.handleKeyCatcherPress('ArrowLeft');
  assert.equal(res.action, 'adjustSliderLeft', 'Must adjust slider and NOT switch route at min boundary');
  assert.equal(harness.state.dragTarget.brightness, 1, 'Clamped at min 1');
  assert.equal(harness.state.route, 'home', 'Route must remain home');

  // Test upper boundary clamp (100%)
  harness.state.state.brightness.percent = 100;
  res = harness.handleKeyCatcherPress('ArrowRight');
  assert.equal(res.action, 'adjustSliderRight', 'Must adjust slider and NOT switch route at max boundary');
  assert.equal(harness.state.dragTarget.brightness, 100, 'Clamped at max 100');
  assert.equal(harness.state.route, 'home');

  // 2. Temperature slider (section 2: range 2500..6500, step 50)
  harness.cursorToSection(2);
  harness.state.state.temperature = 4000;

  res = harness.handleKeyCatcherPress('ArrowRight');
  assert.equal(res.action, 'adjustSliderRight');
  assert.equal(harness.state.dragTarget.temperature, 4050);

  res = harness.handleKeyCatcherPress('ArrowLeft');
  assert.equal(res.action, 'adjustSliderLeft');
  assert.equal(harness.state.dragTarget.temperature, 3950);

  // Test lower boundary clamp (2500 K)
  harness.state.state.temperature = 2500;
  res = harness.handleKeyCatcherPress('ArrowLeft');
  assert.equal(res.action, 'adjustSliderLeft');
  assert.equal(harness.state.dragTarget.temperature, 2500);
  assert.equal(harness.state.route, 'home');

  // Test upper boundary clamp (6500 K)
  harness.state.state.temperature = 6500;
  res = harness.handleKeyCatcherPress('ArrowRight');
  assert.equal(res.action, 'adjustSliderRight');
  assert.equal(harness.state.dragTarget.temperature, 6500);
  assert.equal(harness.state.route, 'home');

  // 3. Gamma slider (section 3: range 0..100, step 1)
  harness.cursorToSection(3);
  harness.state.state.gamma = 50;

  res = harness.handleKeyCatcherPress('ArrowRight');
  assert.equal(res.action, 'adjustSliderRight');
  assert.equal(harness.state.dragTarget.gamma, 51);

  // Test lower boundary clamp (0%)
  harness.state.state.gamma = 0;
  res = harness.handleKeyCatcherPress('ArrowLeft');
  assert.equal(res.action, 'adjustSliderLeft');
  assert.equal(harness.state.dragTarget.gamma, 0);
  assert.equal(harness.state.route, 'home');

  // Test upper boundary clamp (100%)
  harness.state.state.gamma = 100;
  res = harness.handleKeyCatcherPress('ArrowRight');
  assert.equal(res.action, 'adjustSliderRight');
  assert.equal(harness.state.dragTarget.gamma, 100);
  assert.equal(harness.state.route, 'home');
});

test('Non-slider sections and non-ready state fall back cleanly to view switching', () => {
  const harness = createAdversarialPanelHarness();

  // Route Home, Section 0: Night Light hero switch
  harness.navigateToRoute('home');
  harness.cursorToSection(0);
  let res = harness.handleKeyCatcherPress('ArrowRight');
  assert.equal(res.action, 'switchRouteNext');
  assert.equal(harness.state.route, 'automation');

  res = harness.handleKeyCatcherPress('ArrowLeft');
  assert.equal(res.action, 'switchRoutePrev');
  assert.equal(harness.state.route, 'home');

  // Route Home, Section 4: Monitor dropdown
  harness.cursorToSection(4);
  res = harness.handleKeyCatcherPress('ArrowRight');
  assert.equal(res.action, 'switchRouteNext');
  assert.equal(harness.state.route, 'automation');

  // Route Automation: all sections fall back to route switching
  harness.cursorToSection(0); // scheduleToggle
  res = harness.handleKeyCatcherPress('ArrowRight');
  assert.equal(res.action, 'switchRouteNext');
  assert.equal(harness.state.route, 'settings');

  harness.navigateToRoute('automation');
  harness.cursorToSection(1); // schedule
  res = harness.handleKeyCatcherPress('ArrowLeft');
  assert.equal(res.action, 'switchRoutePrev');
  assert.equal(harness.state.route, 'home');

  harness.navigateToRoute('automation');
  harness.cursorToSection(2); // snooze
  res = harness.handleKeyCatcherPress('ArrowRight');
  assert.equal(res.action, 'switchRouteNext');
  assert.equal(harness.state.route, 'settings');

  // Route Settings: all sections fall back to route switching
  harness.cursorToSection(0); // locale
  res = harness.handleKeyCatcherPress('ArrowLeft');
  assert.equal(res.action, 'switchRoutePrev');
  assert.equal(harness.state.route, 'automation');

  harness.navigateToRoute('settings');
  harness.cursorToSection(1); // shortcut
  res = harness.handleKeyCatcherPress('ArrowRight');
  assert.equal(res.action, 'switchRouteNext');
  assert.equal(harness.state.route, 'home');

  harness.navigateToRoute('settings');
  harness.cursorToSection(2); // shortcutActions
  res = harness.handleKeyCatcherPress('ArrowRight');
  assert.equal(res.action, 'switchRouteNext');
  assert.equal(harness.state.route, 'home');

  // Fallback when stateReady is false
  harness.navigateToRoute('home');
  harness.cursorToSection(1); // brightness
  harness.state.stateReady = false;
  res = harness.handleKeyCatcherPress('ArrowRight');
  assert.equal(res.action, 'switchRouteNext', 'Unready state must fall back to route switching');
  assert.equal(harness.state.route, 'automation');
});

// ============================================================================
// Test Suite 3: Escape Key Focus Release & 12-Surface Focus Traps
// ============================================================================

test('Focusing any of the 12 input surfaces blocks keyCatcher and Escape releases focus before close', () => {
  const harness = createAdversarialPanelHarness();
  
  const all12FocusTargets = [
    'startEditor',
    'endEditor',
    'dayTemperatureEditor.field',
    'dayBrightnessEditor.field',
    'dayGammaEditor.field',
    'nightTemperatureEditor.field',
    'nightBrightnessEditor.field',
    'nightGammaEditor.field',
    'snoozeEditor.field',
    'shortcutField',
    'monitorSelector.popupOpen',
    'localeSelector.popupOpen'
  ];

  for (const target of all12FocusTargets) {
    // 1. Focus the target
    harness.focusTargetField(target);
    assert.equal(harness.isKeyCatcherBlocked(), true, `${target} must block keyCatcher`);
    assert.equal(harness.state.activeFocusItem, target);

    // 2. While focused, keyCatcher ignores key presses (including Escape)
    const blockedRes = harness.handleKeyCatcherPress('Escape');
    assert.equal(blockedRes.handled, false);
    assert.equal(blockedRes.reason, 'blocked');
    assert.equal(harness.state.panelOpened, true, 'Panel must NOT close while focused in field');
    assert.equal(harness.state.closedCount, 0);

    // 3. User hits Escape in the target field -> focus returns to keyCatcher
    harness.releaseFocusFromField(target);
    assert.equal(harness.isKeyCatcherBlocked(), false, `Focus release from ${target} unblocks keyCatcher`);
    assert.equal(harness.state.activeFocusItem, 'keyCatcher');
    assert.equal(harness.state.panelOpened, true, 'Panel remains open after releasing focus');

    // 4. Second Escape press on keyCatcher closes the panel
    const closeRes = harness.handleKeyCatcherPress('Escape');
    assert.equal(closeRes.handled, true);
    assert.equal(closeRes.action, 'close');
    assert.equal(harness.state.panelOpened, false, 'Panel closes on second Escape');

    // Reset panel opened state for next loop
    harness.state.panelOpened = true;
    harness.state.closedCount = 0;
  }
});

test('refocusKeyCatcher restores active focus after button clicks across all routes', () => {
  const harness = createAdversarialPanelHarness();

  // Simulate button click stealing focus
  harness.state.activeFocusItem = 'someButton';
  harness.refocusKeyCatcher();
  assert.equal(harness.state.activeFocusItem, 'keyCatcher');
  assert.equal(harness.isKeyCatcherBlocked(), false);
});

// ============================================================================
// Test Suite 4: Adversarial Fuzzing (100,000 Random Navigation Interactions)
// ============================================================================

test('Adversarial fuzzing (100,000 steps) verifies cursor boundedness, route stability, and memory safety', () => {
  const harness = createAdversarialPanelHarness();
  const keys = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Escape', 'Enter', 'Space', 'Tab', 'KeyA', null, undefined];
  const routes = ['home', 'automation', 'settings'];

  const startMem = process.memoryUsage().heapUsed;

  for (let i = 0; i < 100000; i++) {
    const actionType = i % 5;
    if (actionType === 0) {
      // Random key press
      const key = keys[Math.floor(Math.random() * keys.length)];
      harness.handleKeyCatcherPress(key);
    } else if (actionType === 1) {
      // Direct route navigation
      const r = routes[Math.floor(Math.random() * routes.length)];
      harness.navigateToRoute(r);
    } else if (actionType === 2) {
      // Random hover setting cursor
      const maxSec = Model.routeSections(harness.state.route).length - 1;
      const sec = Math.floor(Math.random() * (maxSec + 4)) - 2; // includes invalid indices -2..maxSec+1
      harness.cursorToSection(sec);
    } else if (actionType === 3) {
      // Focus / unfocus a random field
      const targets = Object.keys(harness.state.focusItems);
      const target = targets[Math.floor(Math.random() * targets.length)];
      if (Math.random() > 0.5) {
        harness.focusTargetField(target);
      } else {
        harness.releaseFocusFromField(target);
      }
    } else {
      // Slider value modification
      harness.adjustSliderBy(Math.random() > 0.5 ? 1 : -1);
    }

    // Invariant assertions
    assert.ok(routes.includes(harness.state.route), `Invalid route ${harness.state.route}`);
    const validSections = Model.routeSections(harness.state.route);
    assert.ok(
      harness.state.cursor.section >= 0 && harness.state.cursor.section < validSections.length,
      `Cursor section ${harness.state.cursor.section} out of bounds for route ${harness.state.route} (0..${validSections.length - 1})`
    );
  }

  const endMem = process.memoryUsage().heapUsed;
  const memDiffMB = (endMem - startMem) / (1024 * 1024);
  assert.ok(memDiffMB < 30, `Memory growth should be bounded, got ${memDiffMB.toFixed(2)} MB`);
});

// ============================================================================
// Test Suite 5: QML Contract Verification for 12 Focus Targets & Escape Handlers
// ============================================================================

test('QML structure declares all 12 focus targets and binds Escape to keyCatcher', () => {
  const expectedTargets = [
    'startEditor',
    'endEditor',
    'dayTemperatureEditor',
    'dayBrightnessEditor',
    'dayGammaEditor',
    'nightTemperatureEditor',
    'nightBrightnessEditor',
    'nightGammaEditor',
    'snoozeEditor',
    'shortcutField',
    'monitorSelector',
    'localeSelector'
  ];

  for (const targetId of expectedTargets) {
    const idRegex = new RegExp(`id:\\s*${targetId}\\b`);
    assert.match(qml, idRegex, `Panel.qml must declare component with id: ${targetId}`);
  }

  // Verify text fields have Keys.onEscapePressed
  assert.match(qml, /id:\s*startEditor[\s\S]*?Keys\.onEscapePressed:\s*keyCatcher\.forceActiveFocus\(\)/);
  assert.match(qml, /id:\s*endEditor[\s\S]*?Keys\.onEscapePressed:\s*keyCatcher\.forceActiveFocus\(\)/);
  assert.match(qml, /id:\s*shortcutField[\s\S]*?Keys\.onEscapePressed:\s*keyCatcher\.forceActiveFocus\(\)/);

  // Verify number fields have field.Keys.onPressed with Qt.Key_Escape
  const numberFieldIds = [
    'dayTemperatureEditor',
    'dayBrightnessEditor',
    'dayGammaEditor',
    'nightTemperatureEditor',
    'nightBrightnessEditor',
    'nightGammaEditor',
    'snoozeEditor'
  ];

  for (const nfid of numberFieldIds) {
    const startIdx = qml.indexOf(`id: ${nfid}`);
    assert.ok(startIdx !== -1);
    const slice = qml.slice(startIdx, startIdx + 3000);
    assert.match(slice, /field\.Keys\.onPressed:\s*function\(event\)\s*\{[\s\S]*?Qt\.Key_Escape[\s\S]*?keyCatcher\.forceActiveFocus\(\)/,
      `${nfid} must intercept Key_Escape and force focus to keyCatcher`);
  }

  // Verify dropdown selectors restore focus on popup close
  assert.match(qml, /id:\s*monitorSelector[\s\S]*?onPopupOpenChanged:\s*if\s*\(!monitorSelector\.popupOpen\)\s*Qt\.callLater\(function\(\)\s*\{\s*keyCatcher\.forceActiveFocus\(\);\s*\}\)/);
  assert.match(qml, /id:\s*localeSelector[\s\S]*?onPopupOpenChanged:\s*if\s*\(!localeSelector\.popupOpen\)\s*Qt\.callLater\(function\(\)\s*\{\s*keyCatcher\.forceActiveFocus\(\);\s*\}\)/);
});

// ============================================================================
// Test Suite 6: Schedule Editor Enter/Tab Navigation Chain Contract
// ============================================================================

test('Schedule editor fields form a continuous forward focus progression via Enter/Return', () => {
  // startEditor -> dayTemperatureEditor
  assert.match(qml, /id:\s*startEditor[\s\S]*?onAccepted:\s*dayTemperatureEditor\.field\.forceActiveFocus\(\)/);

  // dayTemperatureEditor -> dayBrightnessEditor
  assert.match(qml, /id:\s*dayTemperatureEditor[\s\S]*?Qt\.Key_Return[\s\S]*?dayBrightnessEditor\.field\.forceActiveFocus\(\)/);

  // dayBrightnessEditor -> dayGammaEditor
  assert.match(qml, /id:\s*dayBrightnessEditor[\s\S]*?Qt\.Key_Return[\s\S]*?dayGammaEditor\.field\.forceActiveFocus\(\)/);

  // dayGammaEditor -> endEditor
  assert.match(qml, /id:\s*dayGammaEditor[\s\S]*?Qt\.Key_Return[\s\S]*?endEditor\.forceActiveFocus\(\)/);

  // endEditor -> nightTemperatureEditor
  assert.match(qml, /id:\s*endEditor[\s\S]*?onAccepted:\s*nightTemperatureEditor\.field\.forceActiveFocus\(\)/);

  // nightTemperatureEditor -> nightBrightnessEditor
  assert.match(qml, /id:\s*nightTemperatureEditor[\s\S]*?Qt\.Key_Return[\s\S]*?nightBrightnessEditor\.field\.forceActiveFocus\(\)/);

  // nightBrightnessEditor -> nightGammaEditor
  assert.match(qml, /id:\s*nightBrightnessEditor[\s\S]*?Qt\.Key_Return[\s\S]*?nightGammaEditor\.field\.forceActiveFocus\(\)/);

  // nightGammaEditor -> saveScheduleButton
  assert.match(qml, /id:\s*nightGammaEditor[\s\S]*?Qt\.Key_Return[\s\S]*?saveScheduleButton\.forceActiveFocus\(\)/);
});

// ============================================================================
// Test Suite 7: Monotonic Request Bus & Drag Mutation Interleaving
// ============================================================================

test('Monotonic request bus rejects interleaved stale responses across route jumps', () => {
  let currentState = Model.normalizeState({
    available: true,
    enabled: true,
    brightness: { percent: 50 },
    nightlight: { temperature: 3500, gamma: 100 }
  });

  let latestRequestId = 0;

  // Step 1: User issues brightness mutation (reqId = 1)
  latestRequestId++;
  const req1Id = latestRequestId;

  // Step 2: User issues temperature mutation before req1 finishes (reqId = 2)
  latestRequestId++;
  const req2Id = latestRequestId;

  // Step 3: User jumps to automation route (reqId = 3)
  latestRequestId++;
  const req3Id = latestRequestId;

  // Response for Req #1 arrives late (reqId = 1, latest = 3)
  const commit1 = Model.commitResponse(currentState, {
    requestId: req1Id,
    latestRequestId: latestRequestId,
    ok: true,
    state: { brightness: { available: true, percent: 60 } }
  });
  assert.equal(commit1.accepted, false, 'Req 1 response must be rejected as stale');
  assert.equal(commit1.state.brightness.percent, 50, 'State must remain unmutated');

  // Response for Req #2 arrives late (reqId = 2, latest = 3)
  const commit2 = Model.commitResponse(currentState, {
    requestId: req2Id,
    latestRequestId: latestRequestId,
    ok: true,
    state: { nightlight: { available: true, temperature: 4500, gamma: 100 } }
  });
  assert.equal(commit2.accepted, false, 'Req 2 response must be rejected as stale');
  assert.equal(commit2.state.nightlight.temperature, 3500);

  // Response for Req #3 (schedule-status) arrives (reqId = 3, latest = 3)
  const commit3 = Model.commitResponse(currentState, {
    requestId: req3Id,
    latestRequestId: latestRequestId,
    ok: true,
    state: {
      schedule: {
        available: true,
        day_time: '08:00',
        night_time: '21:00',
        day_temp: 6100,
        night_temp: 3100
      }
    }
  });
  assert.equal(commit3.accepted, true, 'Req 3 response must be accepted');
  assert.equal(commit3.state.schedule.day_time, '08:00');
  assert.equal(commit3.state.schedule.night_time, '21:00');
});

