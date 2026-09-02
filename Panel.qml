import QtQuick
import QtQuick.Layouts
import Quickshell.Io
import "UiModel.js" as Model
import "I18n.js" as I18n
import "Icons.js" as Icons
import qs.Commons
import qs.Ui

Panel {
    id: root

    property Item anchorItem: null
    property var state: root.normalizeCombined({})
    property string route: "home"
    property int transitionDirection: 1
    property string locale: "en"
    property string selectedMonitor: "focused"
    property string shortcutKeys: "SUPER+SHIFT+N"
    property int snoozeAmount: 30
    property string snoozeUnit: "minutes"
    property string lastError: ""
    onLastErrorChanged: if (lastError !== "") errorTimer.restart()
    onSettingsChanged: {
        var s = root.settings;
        if (!s || typeof s !== "object") return;
        if (s.locale && typeof s.locale === "string") root.locale = s.locale;
        if (s.monitor && typeof s.monitor === "string") root.selectedMonitor = s.monitor;
        if (s.shortcutKeys && typeof s.shortcutKeys === "string") root.shortcutKeys = s.shortcutKeys;
    }
    property string feedbackText: ""
    property bool actionPending: false
    // Touched by snoozeTickTimer so the countdown binding re-evaluates
    // between helper refreshes.
    property int snoozeTick: 0
    property int latestRequestId: 0
    property int queuedRequestId: 0
    property int processRequestId: 0
    property var dragTarget: Model.dragTargetEmpty()
    property string queuedOperation: ""
    property var queuedCommand: []
    property bool stoppingForLatest: false
    property string processOutput: ""
    property string processError: ""
    // Schedule editor drafts: times, temperatures and the optional display
    // values (brightness/gamma) each period schedules. Empty display drafts
    // mean "leave the period without scheduled display values".
    property var cursor: Model.cursorStart()
    property string editStart: "06:00"
    property string editEnd: "15:30"
    property string editDayTemperature: "6000"
    property string editDayBrightness: ""
    property string editDayGamma: ""
    property string editNightTemperature: "3500"
    property string editNightBrightness: ""
    property string editNightGamma: ""
    readonly property color foreground: bar ? bar.foreground : Color.foreground
    readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
    // Named geometry: icon slot in slider rows and the panel's fixed outer
    // dimensions, kept as properties so the magic numbers live in one place.
    readonly property int controlIconSlot: Style.space(20)
    readonly property int panelWidth: Style.space(330)
    readonly property int panelMaxHeight: Style.space(560)
    // Uniform vertical breathing room: every cursor row pads with sectionPad,
    // the taller automation header with headerPad.
    readonly property int sectionPad: Style.space(6)
    readonly property int headerPad: Style.space(16)
    readonly property string helperPath: root.normalizedPath(root.setting("helperPath", ""))
    readonly property bool stateReady: state.available === true
    readonly property string errorText: root.lastError !== "" ? root.lastError : root.localizeErrorString(root.state.error || "")
    readonly property var routeOptions: Model.routeOrder()
    readonly property var monitorOptions: root.monitorChoices()
    readonly property string routeTitle: root.text(root.route)
    readonly property string previousRoute: Model.adjacentRoute(root.route, -1)
    readonly property string nextRoute: Model.adjacentRoute(root.route, 1)
    readonly property string automationOrigin: root.state.automation && root.state.automation.origin ? String(root.state.automation.origin) : "unknown"
    readonly property bool automationReady: Boolean(root.state.automation && root.state.automation.available === true)
    readonly property bool scheduleEnabled: Boolean(root.automationReady && root.state.automation.schedule_enabled !== false)
    readonly property string provenanceText: I18n.t("origin_" + root.automationOrigin, root.locale)
    readonly property string heroGlyph: root.glyphForState(root.state)
    readonly property bool snoozeActive: Boolean(root.state.automation && root.state.automation.snoozed)
    readonly property string heroStatusDetail: {
        if (!root.stateReady)
            return root.text("unavailable");
        if (root.snoozeActive)
            return root.text("snooze_active");
        if (root.state.enabled === true)
            return root.provenanceText;
        return root.text("disabled");
    }
    // Minutes left on the active snooze, recomputed whenever the helper
    // refreshes the combined status (open, actions, reconcile).
    readonly property int snoozeRemainingMinutes: {
        // snoozeTick is read only so this binding re-evaluates every 30 s
        // while a snooze is active; its value never changes the math.
        var tick = root.snoozeTick;
        var until = root.state.automation ? Number(root.state.automation.snooze_until) : 0;
        if (!isFinite(until) || until <= 0)
            return 0;
        return Math.max(0, Math.ceil((until - Date.now() / 1000) / 60));
    }
    readonly property var snoozeSeconds: Model.snoozeDurationSeconds(root.snoozeAmount, root.snoozeUnit)
    readonly property string scheduleValidationError: Model.validateScheduleFields(editStart, editEnd, editDayTemperature, editDayBrightness, editDayGamma, editNightTemperature, editNightBrightness, editNightGamma, root.locale).error
    readonly property var scheduleDurationInfo: Model.calculateScheduleDuration(root.editStart, root.editEnd)
    // Focus-owned controls suspend the arrow keyboard so editors and popup
    // lists receive their keys normally.
    readonly property bool keyCatcherBlocked: startEditor.activeFocus || endEditor.activeFocus
        || dayTemperatureEditor.field.activeFocus || dayBrightnessEditor.field.activeFocus || dayGammaEditor.field.activeFocus
        || nightTemperatureEditor.field.activeFocus || nightBrightnessEditor.field.activeFocus || nightGammaEditor.field.activeFocus
        || snoozeEditor.field.activeFocus || shortcutField.activeFocus
        || monitorSelector.popupOpen || localeSelector.popupOpen

    function normalizedPath(value) {
        var candidate = String(value || "");
        if (candidate === "")
            candidate = String(Qt.resolvedUrl("scripts/veilleuse-control"));

        if (candidate.indexOf("file://") === 0)
            candidate = decodeURIComponent(candidate.replace(/^file:\/\/\//, "/"));

        return candidate;
    }

    function text(key) {
        return I18n.t(key, root.locale);
    }

    // Localize a structured diagnostic without mangling an already-localized
    // literal: known error codes map through the dictionaries, the model's
    // English "not confirmed" fallback maps to the active locale, and every
    // other literal passes through verbatim.
    function localizeErrorString(value) {
        return Model.localizeStateError(value, root.locale);
    }

    function normalizeCombined(raw) {
        var input = raw && typeof raw === "object" ? raw : {};
        var normalized = Model.normalizeState(input);
        normalized.automation = input.automation && typeof input.automation === "object" ? input.automation : {
            schedule_enabled: input.schedule_enabled !== false,
            snooze_until: null,
            snoozed: false,
            origin: "unknown",
            schedule_display: null,
            schedule_period_applied: null
        };
        normalized.monitors = Array.isArray(input.monitors) ? input.monitors : [];
        return normalized;
    }

    function mergeCombined(base, raw) {
        var next = normalizeCombined(base);
        var input = raw && typeof raw === "object" ? raw : {};
        if (input.automation && typeof input.automation === "object") {
            if (!next.automation || typeof next.automation !== "object") next.automation = {};
            for (var key in input.automation) next.automation[key] = input.automation[key];
        }
        if (Array.isArray(input.monitors)) next.monitors = input.monitors;
        return next;
    }
    function navigateToRoute(nextRoute) {
        if (root.routeOptions.indexOf(nextRoute) === -1) return;
        if (nextRoute !== root.route) {
            var curIdx = root.routeOptions.indexOf(root.route);
            var nextIdx = root.routeOptions.indexOf(nextRoute);
            if (curIdx === 2 && nextIdx === 0) {
                root.transitionDirection = 1;
            } else if (curIdx === 0 && nextIdx === 2) {
                root.transitionDirection = -1;
            } else {
                root.transitionDirection = nextIdx >= curIdx ? 1 : -1;
            }
            root.dragTarget = Model.dragTargetEmpty();
            root.cursor = Model.cursorStart();
            root.lastError = "";
            root.feedbackText = "";
        }
        root.route = nextRoute;
        // Returning home re-reads the physical baseline the sliders show.
        if (nextRoute === "home") root.requestStatus();
        if (nextRoute === "automation") {
            root.populateScheduleEditor();
            root.request(["schedule", "status"], "schedule-status");
        }
        if (panelFlick) panelFlick.contentY = 0;
        Qt.callLater(function() { if (keyCatcher) keyCatcher.forceActiveFocus(); });
    }

    // Focusable buttons steal the active focus on click, which would leave the
    // arrow keys dead. Deferred through Qt.callLater so the button's own focus
    // grab settles first and the key catcher wins the frame after.
    function refocusKeyCatcher() {
        Qt.callLater(function() { if (keyCatcher) keyCatcher.forceActiveFocus(); });
    }

    function monitorChoices() {
        var monitors = root.state && Array.isArray(root.state.monitors) ? root.state.monitors : [];
        var focusedName = "";
        for (var f = 0; f < monitors.length; f++) {
            if (monitors[f] && monitors[f].focused) focusedName = String(monitors[f].name);
        }
        var choices = [{
            value: "focused",
            label: text("focused_monitor"),
            description: focusedName ? ("(" + focusedName + ")") : ""
        }];
        for (var i = 0; i < monitors.length; i++) {
            if (monitors[i] && monitors[i].enabled !== false) {
                var name = String(monitors[i].name);
                var isFocused = Boolean(monitors[i].focused);
                choices.push({
                    value: name,
                    label: name,
                    description: isFocused ? text("focused_monitor") : ""
                });
            }
        }
        return choices;
    }

    function glyphForState(value) {
        return Icons.glyphForState(value);
    }

    function persistInline(values) {
        var entry = { id: root.moduleName };
        var existing = root.settings || {};
        for (var key in existing) if (key !== "id") entry[key] = existing[key];
        for (var nextKey in values) entry[nextKey] = values[nextKey];
        root.settings = entry;
        if (root.bar && root.bar.shell && typeof root.bar.shell.updateEntryInline === "function")
            root.bar.shell.updateEntryInline(root.moduleName, entry);
    }

    function setInlineSetting(name, value) {
        if (name === "locale") root.locale = String(value);
        if (name === "monitor") root.selectedMonitor = String(value);
        if (name === "shortcutKeys") root.shortcutKeys = String(value);
        var values = {};
        values[name] = value;
        root.persistInline(values);
    }

    function issue(command, operation) {
        return root.request(command, operation);
    }

    function toggleSchedule(enabled) {
        root.issue(["schedule", enabled ? "enable" : "disable"], "schedule-toggle");
    }

    function applySnooze() {
        if (root.snoozeSeconds === null || root.actionPending)
            return ;
        root.issue(["snooze", "set", "--seconds", String(root.snoozeSeconds)], "snooze");
    }

    function minutesUntilSunset() {
        var nightTime = (root.state && root.state.schedule && root.state.schedule.night_time)
            ? root.state.schedule.night_time : "19:30";
        var parts = nightTime.split(":");
        var targetH = parseInt(parts[0], 10);
        var targetM = parseInt(parts[1] || "0", 10);
        if (isNaN(targetH)) targetH = 19;
        if (isNaN(targetM)) targetM = 30;
        var now = new Date();
        var sunset = new Date(now.getFullYear(), now.getMonth(), now.getDate(), targetH, targetM, 0, 0);
        var diffMs = sunset.getTime() - now.getTime();
        if (diffMs <= 0) {
            sunset.setDate(sunset.getDate() + 1);
            diffMs = sunset.getTime() - now.getTime();
        }
        var mins = Math.round(diffMs / 60000);
        return Math.max(1, Math.min(1440, mins));
    }

    function applyQuickSnooze(amount, unit) {
        root.snoozeAmount = amount;
        root.snoozeUnit = unit;
        root.applySnooze();
        root.refocusKeyCatcher();
    }

    function settingsCommand(name, args) {
        var command = [name].concat(args || []);
        root.issue(command, name);
    }

    function requestStatus() {
        request(["status"], "status");
    }

    function reconcile() {
        root.request(["reconcile"], "reconcile");
    }

    function request(command, operation) {
        latestRequestId += 1;
        queuedRequestId = latestRequestId;
        queuedCommand = [root.helperPath].concat(command);
        queuedOperation = operation;
        actionPending = true;
        lastError = "";
        feedbackText = "";
        // Ids resolve through the component scope, never through the root
        // object: qualifying an id with the root would read undefined and
        // abort every helper call on a freshly started engine.
        if (helperProcess.running || root.stoppingForLatest || debounce.running) {
            debounce.restart();
        } else {
            debounce.stop();
            root.launchLatest();
        }
        return latestRequestId;
    }

    function queueMutation(section, value) {
        if (!stateReady)
            return ;

        if (section === "brightness")
            request(["brightness", String(Math.round(value)), "--monitor", root.selectedMonitor], section);
        else
            request(["nightlight", section, String(Math.round(value))], section);
    }

    // Pointer drag intent for a slider: the helper writes absolute values in
    // one shot, so the newest target is recorded for the label while the
    // readback is in flight and cleared once the confirmed state reaches it.
    function queueDragMutation(section, value) {
        root.dragTarget = Model.dragTargetPush(root.dragTarget, section, value);
        root.queueMutation(section, value);
    }

    // A slider shows its pending drag target while the write is in flight so
    // the value the finger last aimed at stays on screen; once the readback
    // reaches it the target clears and the confirmed state takes over.
    function displayValue(section, fallback) {
        var target = root.dragTarget && typeof root.dragTarget === "object" ? root.dragTarget[section] : null;
        return typeof target === "number" && isFinite(target) ? target : fallback;
    }

    function scheduleDisplayDraft(period, field) {
        if (period === "day" && field === "brightness") return editDayBrightness;
        if (period === "day" && field === "gamma") return editDayGamma;
        if (period === "night" && field === "brightness") return editNightBrightness;
        if (period === "night" && field === "gamma") return editNightGamma;
        return "";
    }

    function queueSchedule() {
        if (!stateReady || actionPending || !scheduleFieldsValid())
            return ;

        var command = ["schedule", "set", "--day-time", editStart,
                       "--night-time", editEnd, "--day-temp", editDayTemperature,
                       "--night-temp", editNightTemperature];
        var periods = [["day", "brightness", "dayBrightness"],
                       ["day", "gamma", "dayGamma"],
                       ["night", "brightness", "nightBrightness"],
                       ["night", "gamma", "nightGamma"]];
        for (var i = 0; i < periods.length; i++) {
            var draft = scheduleDisplayDraft(periods[i][0], periods[i][1]);
            if (draft !== "")
                command = command.concat(["--" + periods[i][0] + "-" + periods[i][1], draft]);
        }
        request(command, "schedule");
    }

    function scheduleFieldsValid() {
        return Model.validateScheduleFields(editStart, editEnd, editDayTemperature, editDayBrightness, editDayGamma, editNightTemperature, editNightBrightness, editNightGamma, root.locale).valid;
    }

    function launchLatest() {
        if (helperProcess.running) {
            stoppingForLatest = true;
            helperProcess.running = false;
            return ;
        }
        processRequestId = queuedRequestId;
        processOutput = "";
        processError = "";
        helperProcess.command = queuedCommand;
        helperProcess.running = true;
    }

    // A superseded exit still describes a write that physically applied: the
    // latest-wins bus cancelled the readback chase, not the write itself. Adopt
    // the stale payload's state patch superficially so the knob never reverts
    // to a value the monitor has already left behind; the combined sections of
    // the previous state survive and the newest request relaunches against the
    // merged baseline.
    function mergeStaleResponse(exitCode) {
        if (exitCode !== 0)
            return ;

        var payload = null;
        try {
            payload = processOutput === "" ? null : JSON.parse(processOutput);
        } catch (error) {
            payload = null;
        }
        var patch = payload && payload.state && typeof payload.state === "object" && !Array.isArray(payload.state) ? payload.state : null;
        if (!patch)
            return ;

        state = root.mergeCombined(Model.mergeStatePatch(state, patch), patch);
    }

    function handleExit(exitCode) {
        var requestId = processRequestId;
        if (stoppingForLatest) {
            stoppingForLatest = false;
            Qt.callLater(root.launchLatest);
            return ;
        }
        if (requestId !== latestRequestId) {
            debounce.stop();
            Qt.callLater(root.launchLatest);
            root.mergeStaleResponse(exitCode);
            return ;
        }
        var payload = null;
        try {
            payload = processOutput === "" ? null : JSON.parse(processOutput);
        } catch (error) {
            payload = null;
        }
        var responseState = payload && payload.state ? payload.state : payload;
        var result = Model.commitResponse(root.state, {
            "requestId": requestId,
            "latestRequestId": latestRequestId,
            "ok": exitCode === 0 && payload !== null && payload.ok !== false,
            "state": responseState
        });
        if (result.accepted) {
            state = root.mergeCombined(result.state, responseState);
            actionPending = false;
            lastError = root.localizeErrorString(result.state.error);
            if (responseState && responseState.manual_persist_error) {
                lastError = root.text("manualPersistError");
            }
            root.reconcilePending();
            if (queuedOperation === "schedule") {
                feedbackText = root.text("saved");
                feedbackTimer.restart();
                root.populateScheduleEditor();
            } else if (queuedOperation === "shortcut") {
                feedbackText = root.text("saved");
                feedbackTimer.restart();
            }

            return ;
        }
        actionPending = false;
        root.dragTarget = Model.dragTargetEmpty();
        if (queuedOperation === "status")
            state = root.normalizeCombined({});

        var payloadError = payload && payload.error ? String(payload.error) : "";
        var payloadCode = payload && payload.error_code ? String(payload.error_code) : "";
        var failedState = responseState && typeof responseState === "object" ? Model.normalizeState(responseState) : null;
        if (payloadCode !== "")
            lastError = Model.errorCodeMessage(payloadCode, root.locale);
        else
            lastError = root.localizeErrorString(payloadError || (failedState && failedState.error ? failedState.error : "")) || processError || root.text("not_confirmed");
    }

    function moveCursorVertically(direction) {
        var key = direction > 0 ? "ArrowDown" : "ArrowUp";
        cursor = Model.moveCursor(cursor, key, root.route);
    }

    // Mouse hover targets the same single cursor the arrows walk: the row
    // under the pointer becomes the navigable section so Enter activates it
    // and Left/Right adjust it. This is the Omarchy cursor contract.
    function cursorToSection(index) {
        var names = Model.routeSections(root.route);
        if (index < 0 || index >= names.length)
            return;
        root.cursor = { section: index, field: 0 };
    }

    function switchRouteBy(direction) {
        root.navigateToRoute(Model.adjacentRoute(root.route, direction));
    }

    // The cursor owns a slider section: Left/Right step the live value with
    // the section keyboard step instead of switching routes. Returns false
    // when the arrows must fall back to view switching.
    function adjustSliderBy(direction) {
        var names = Model.routeSections(root.route);
        var section = names[root.cursor.section];
        if (!Model.isSliderSection(section) || !root.stateReady)
            return false;
        var current = root.sliderCurrentValue(section);
        var next = Model.stepSliderValue(section, direction, current);
        if (next === null)
            return false;
        root.queueDragMutation(section, next);
        return true;
    }

    function sliderCurrentValue(section) {
        if (section === "brightness") return root.displayValue(section, root.state.brightness.percent);
        if (section === "temperature") return root.displayValue(section, root.state.temperature);
        if (section === "gamma") return root.displayValue(section, root.state.gamma);
        return null;
    }

    function reconcilePending() {
        if (root.route !== "home") {
            root.dragTarget = Model.dragTargetEmpty();
            return ;
        }
        var drag = Model.reconcileDragTargets(state, root.state, root.dragTarget, root.queuedOperation);
        root.dragTarget = drag.target;
        for (var j = 0; j < drag.requests.length; j++)
            root.queueMutation(drag.requests[j].section, drag.requests[j].value);
    }

    function handleCloseRequested() {
        root.close();
    }

    function populateScheduleEditor() {
        var schedule = root.state.schedule || {};
        root.editStart = schedule.day_time || "06:00";
        root.editEnd = schedule.night_time || "15:30";
        root.editDayTemperature = String(schedule.day_temp || 6000);
        root.editNightTemperature = String(schedule.night_temp || 3500);
        var display = root.state.automation && root.state.automation.schedule_display
            ? root.state.automation.schedule_display : {};
        root.editDayBrightness = display.day && display.day.brightness !== undefined ? String(display.day.brightness) : "";
        root.editDayGamma = display.day && display.day.gamma !== undefined ? String(display.day.gamma) : "";
        root.editNightBrightness = display.night && display.night.brightness !== undefined ? String(display.night.brightness) : "";
        root.editNightGamma = display.night && display.night.gamma !== undefined ? String(display.night.gamma) : "";
    }

    function activateCursor() {
        var section = Model.routeSections(root.route)[cursor.section];
        if (section === "nightLight") {
            if (stateReady && !actionPending)
                request(["nightlight", "toggle"], "toggle");

            return ;
        }
        if (section === "monitor") {
            monitorSelector.open();
            return ;
        }
        if (section === "scheduleToggle") {
            if (automationReady && !actionPending)
                root.toggleSchedule(!root.scheduleEnabled);

            return ;
        }
        if (section === "schedule") {
            startEditor.forceActiveFocus();
            return ;
        }
        if (section === "snooze") {
            root.applySnooze();
            return ;
        }
        if (section === "locale") {
            localeSelector.open();
            return ;
        }
        if (section === "shortcut") {
            shortcutField.forceActiveFocus();
            return ;
        }
        if (section === "shortcutActions")
            root.settingsCommand("shortcut", ["install", "--keys", shortcutField.text]);
    }

    moduleName: "io.github.znow01.veilleuse"
    ipcTarget: "io.github.znow01.veilleuse"
    manageIpc: false

    IpcHandler {
        target: root.ipcTarget

        function open() { root.open(); }
        function close() { root.close(); }
        function show() { root.open(); }
        function hide() { root.close(); }
        function toggle() { root.toggle(); }

        function toggleNightlight() {
            root.request(["nightlight", "toggle"], "toggle");
        }
    }

    onOpenedChanged: {
        if (opened)
            requestStatus();

    }
    Component.onCompleted: {
        // Quickshell has no `module`/`require`, so UiModel.js boots without the
        // locale library; hand it the imported I18n namespace so t() honors the
        // persisted locale instead of the bundled English fallback.
        Model.setI18n(I18n);
        root.locale = String(root.setting("locale", "en"));
        root.selectedMonitor = String(root.setting("monitor", "focused"));
        root.shortcutKeys = String(root.setting("shortcutKeys", "SUPER+SHIFT+N"));
        requestStatus();
    }

    Timer {
        id: debounce

        interval: 90
        repeat: false
        onTriggered: root.launchLatest()
    }

    Timer {
        id: feedbackTimer

        interval: 2200
        repeat: false
        onTriggered: root.feedbackText = ""
    }

    Timer {
        id: errorTimer

        interval: 4500
        repeat: false
        onTriggered: root.lastError = ""
    }

    // Keeps the visible snooze countdown ticking between helper refreshes.
    Timer {
        id: snoozeTickTimer

        interval: 30000
        repeat: true
        running: root.opened && root.snoozeActive
        onTriggered: root.snoozeTick += 1
    }

    Timer {
        id: initialReconcileTimer

        interval: 1000
        repeat: false
        running: true
        onTriggered: {
            if (root.actionPending) {
                initialReconcileTimer.restart();
                return ;
            }
            root.reconcile();
        }
    }

    Timer {
        id: backgroundStatusTimer

        interval: 30000
        repeat: true
        running: !root.opened
        onTriggered: if (!root.actionPending) root.reconcile()
    }

    Process {
        id: helperProcess

        onExited: function(exitCode) {
            root.handleExit(exitCode);
        }

        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: root.processOutput = String(text || "").trim()
        }

        stderr: StdioCollector {
            waitForEnd: true
            onStreamFinished: root.processError = String(text || "").trim()
        }

    }

    KeyboardPanel {
        id: keyboardPanel

        anchorItem: root.anchorItem
        owner: root
        bar: root.bar
        open: root.opened
        focusTarget: keyCatcher
        contentWidth: keyboardPanel.fittedContentWidth(root.panelWidth)
        contentHeight: keyboardPanel.fittedContentHeight(contentColumn.implicitHeight, root.panelMaxHeight)

        Behavior on contentHeight {
            NumberAnimation {
                duration: 180
                easing.type: Easing.OutCubic
            }
        }

        // Arrows-only keyboard: Left/Right switch views, Up/Down move the
        // cursor, Enter/Space activate, Esc closes. Editors and popup lists
        // own their keys through the blocked gate.
        Item {
            id: keyCatcher

            anchors.fill: parent
            focus: true

            Keys.priority: Keys.BeforeItem
            Keys.onPressed: function(event) {
                if (root.keyCatcherBlocked)
                    return ;
                if (event.key === Qt.Key_Escape) {
                    root.handleCloseRequested();
                    event.accepted = true;
                    return ;
                }
                if (event.key === Qt.Key_Left) {
                    if (!root.adjustSliderBy(-1))
                        root.switchRouteBy(-1);
                    event.accepted = true;
                    return ;
                }
                if (event.key === Qt.Key_Right) {
                    if (!root.adjustSliderBy(1))
                        root.switchRouteBy(1);
                    event.accepted = true;
                    return ;
                }
                if (event.key === Qt.Key_Up) {
                    root.moveCursorVertically(-1);
                    event.accepted = true;
                    return ;
                }
                if (event.key === Qt.Key_Down) {
                    root.moveCursorVertically(1);
                    event.accepted = true;
                    return ;
                }
                if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
                    root.activateCursor();
                    event.accepted = true;
                    return ;
                }
            }
        }

        Flickable {
            id: panelFlick

            anchors.fill: parent
            contentWidth: width
            contentHeight: contentColumn.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            flickableDirection: Flickable.VerticalFlick
            interactive: contentHeight > height

            Column {
                id: contentColumn

                width: panelFlick.width
                spacing: Style.spacing.panelGap

                // View switching: just the arrows, plus the name of the view
                // you are on.
                Item {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.leftMargin: Style.spacing.rowPaddingX
                    anchors.rightMargin: Style.spacing.rowPaddingX
                    implicitHeight: Math.max(prevRouteButton.implicitHeight, routeTitleText.implicitHeight, nextRouteButton.implicitHeight)

                    PanelActionButton {
                        id: prevRouteButton

                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        iconText: Icons.glyph("chevronLeft")
                        tooltipText: root.text(root.previousRoute)
                        foreground: root.foreground
                        hoverColor: Color.accent
                        focusable: true
                        Accessible.name: root.text(root.previousRoute)
                        Accessible.role: Accessible.Button
                        onClicked: {
                            root.switchRouteBy(-1);
                            root.refocusKeyCatcher();
                        }
                    }

                    Text {
                        id: routeTitleText

                        anchors.left: prevRouteButton.right
                        anchors.right: nextRouteButton.left
                        anchors.leftMargin: Style.spacing.controlGap
                        anchors.rightMargin: Style.spacing.controlGap
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.routeTitle
                        color: root.foreground
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.title
                        font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }

                    PanelActionButton {
                        id: nextRouteButton

                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        iconText: Icons.glyph("chevronRight")
                        tooltipText: root.text(root.nextRoute)
                        foreground: root.foreground
                        hoverColor: Color.accent
                        focusable: true
                        Accessible.name: root.text(root.nextRoute)
                        Accessible.role: Accessible.Button
                        onClicked: {
                            root.switchRouteBy(1);
                            root.refocusKeyCatcher();
                        }
                    }
                }

                // Global helper errors sit directly under the view header,
                // near the top of the content, instead of at the very end of
                // the scrollable column where they could fall off-screen.
                BorderSurface {
                    id: globalErrorBanner

                    visible: root.errorText !== ""
                    leftPadding: Style.spacing.rowPaddingX
                    rightPadding: Style.spacing.rowPaddingX
                    opacity: root.errorText !== "" ? 1.0 : 0.0
                    width: parent.width
                    color: Style.hoverFillFor(root.foreground, Color.urgent)
                    borderSpec: Border.flat(Util.alpha(Color.urgent, Style.hoverBorderAlpha), Style.spacing.hairline)
                    radius: Style.cornerRadius
                    implicitHeight: errorRow.implicitHeight + Style.spacing.controlPaddingY * 2

                    Behavior on opacity {
                        NumberAnimation {
                            duration: 160
                            easing.type: Easing.OutCubic
                        }
                    }

                    Row {
                        id: errorRow

                        anchors.centerIn: parent
                        width: parent.width - Style.spacing.rowPaddingX * 2
                        spacing: Style.spacing.sm

                        NerdIcon {
                            glyph: Icons.glyph("alert")
                            iconSize: Style.font.bodySmall
                            iconColor: Color.urgent
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        Text {
                            width: parent.width - (Style.font.bodySmall + Style.spacing.sm)
                            text: root.errorText
                            color: Color.urgent
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                            wrapMode: Text.WordWrap
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }

                CursorSurface {
                    id: heroSurface

                    visible: root.route === "home"
                    opacity: root.route === "home" ? 1.0 : 0.0
                    width: parent.width
                    hasCursor: root.cursor.section === 0
                    foreground: root.foreground
                    implicitHeight: hero.implicitHeight + Style.spacing.rowPaddingX
                    transform: Translate {
                        x: root.route === "home" ? 0 : (root.transitionDirection > 0 ? 12 : -12)
                        Behavior on x {
                            NumberAnimation {
                                duration: 180
                                easing.type: Easing.OutCubic
                            }
                        }
                    }

                    Behavior on opacity {
                        NumberAnimation {
                            duration: 180
                            easing.type: Easing.OutCubic
                        }
                    }

                    HoverHandler {
                        onHoveredChanged: if (hovered) root.cursorToSection(0)
                    }

                    PanelHero {
                        id: hero

                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: Style.spacing.rowPaddingX
                        anchors.rightMargin: Style.spacing.rowPaddingX
                        title: root.text("night_light")
                        detail: root.heroStatusDetail
                        foreground: root.foreground
                        fontFamily: root.fontFamily
                        iconOpacity: root.stateReady ? 1 : 0.45

                        iconComponent: Component {
                            Text {
                                text: root.heroGlyph
                                color: root.foreground
                                // Off is a state, not a fault: the moon glyph
                                // dims instead of reading as an error.
                                opacity: root.stateReady && root.state.enabled === false ? 0.4 : 1
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.display
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                Accessible.name: root.provenanceText

                                Behavior on opacity {
                                    NumberAnimation {
                                        duration: 160
                                        easing.type: Easing.OutCubic
                                    }
                                }

                                Behavior on color {
                                    ColorAnimation {
                                        duration: 160
                                        easing.type: Easing.OutCubic
                                    }
                                }
                            }

                        }

                        trailingControl: Component {
                            ToggleSwitch {
                                checked: root.stateReady && root.state.enabled
                                busy: !root.stateReady || root.actionPending
                                trackHeight: Math.max(22, Style.space(24))
                                foreground: root.foreground
                                Accessible.name: root.text("night_light")
                                onToggled: root.request(["nightlight", "toggle"], "toggle")
                            }

                        }

                    }

                }

                Column {
                    id: homeRoute

                    visible: root.route === "home"
                    opacity: root.route === "home" ? 1.0 : 0.0
                    width: parent.width
                    spacing: Style.spacing.panelGap
                    transform: Translate {
                        x: root.route === "home" ? 0 : (root.transitionDirection > 0 ? 12 : -12)
                        Behavior on x {
                            NumberAnimation {
                                duration: 180
                                easing.type: Easing.OutCubic
                            }
                        }
                    }

                    Behavior on opacity {
                        NumberAnimation {
                            duration: 180
                            easing.type: Easing.OutCubic
                        }
                    }

                    // Live controls: what acts on the screen right now. One
                    // row of label + live value per slider, slider below.
                    CursorSurface {
                        width: parent.width
                        hasCursor: root.cursor.section === 1
                        foreground: root.foreground
                        implicitHeight: brightnessColumn.implicitHeight + root.sectionPad

                        HoverHandler {
                            onHoveredChanged: if (hovered) root.cursorToSection(1)
                        }

                        Column {
                            id: brightnessColumn

                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: Style.spacing.rowPaddingX
                            anchors.rightMargin: Style.spacing.rowPaddingX
                            spacing: Style.spacing.labelGap

                            Row {
                                width: parent.width
                                spacing: Style.spacing.controlGap

                                NerdIcon {
                                    id: brightnessIcon

                                    glyph: Icons.glyph("brightness")
                                    iconSize: Style.font.icon
                                    width: root.controlIconSlot
                                    height: Math.max(implicitHeight, iconSize)
                                    iconColor: root.cursor.section === 1 ? Color.accent : root.foreground
                                    anchors.verticalCenter: parent.verticalCenter

                                    Behavior on iconColor {
                                        ColorAnimation { duration: 120 }
                                    }
                                }

                                Text {
                                    id: brightnessLabel

                                    text: root.text("brightness")
                                    color: root.foreground
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.body
                                    elide: Text.ElideRight
                                    width: Math.max(0, parent.width - brightnessBadge.implicitWidth - brightnessIcon.width - 2 * Style.spacing.controlGap)
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                BorderSurface {
                                    id: brightnessBadge

                                    implicitWidth: brightnessValue.implicitWidth + Style.space(12)
                                    implicitHeight: brightnessValue.implicitHeight + Style.space(4)
                                    anchors.verticalCenter: parent.verticalCenter
                                    radius: Style.cornerRadius
                                    color: root.cursor.section === 1
                                        ? Style.selectedFillFor(root.foreground, Color.accent)
                                        : Style.normalFillFor(root.foreground, Color.accent)
                                    borderSpec: Border.flat(
                                        root.cursor.section === 1
                                            ? Util.alpha(Color.accent, Style.hoverBorderAlpha)
                                            : Util.alpha(root.foreground, Style.normalBorderAlpha),
                                        Style.spacing.hairline
                                    )

                                    Behavior on color {
                                        ColorAnimation { duration: 120 }
                                    }

                                    Text {
                                        id: brightnessValue

                                        anchors.centerIn: parent
                                        text: root.stateReady ? root.displayValue("brightness", root.state.brightness.percent) + "%" : "—"
                                        color: root.cursor.section === 1 ? Color.accent : root.foreground
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                        font.bold: true

                                        Behavior on color {
                                            ColorAnimation { duration: 120 }
                                        }
                                    }
                                }
                            }

                            PanelSlider {
                                width: parent.width
                                bar: root.bar
                                knobSize: Math.max(16, Style.space(16))
                                value: root.displayValue("brightness", root.state.brightness.percent === null ? 1 : root.state.brightness.percent)
                                minimum: 1
                                maximum: 100
                                step: 1
                                integer: true
                                enabled: root.stateReady
                                Accessible.name: root.text("brightness")
                                onMoved: function(v) { root.queueDragMutation("brightness", v) }
                            }
                        }

                    }

                    CursorSurface {
                        width: parent.width
                        hasCursor: root.cursor.section === 2
                        foreground: root.foreground
                        implicitHeight: temperatureColumn.implicitHeight + root.sectionPad

                        HoverHandler {
                            onHoveredChanged: if (hovered) root.cursorToSection(2)
                        }

                        Column {
                            id: temperatureColumn

                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: Style.spacing.rowPaddingX
                            anchors.rightMargin: Style.spacing.rowPaddingX
                            spacing: Style.spacing.labelGap

                            Row {
                                width: parent.width
                                spacing: Style.spacing.controlGap

                                NerdIcon {
                                    id: temperatureIcon

                                    glyph: Icons.glyph("temperature")
                                    iconSize: Style.font.icon
                                    width: root.controlIconSlot
                                    height: Math.max(implicitHeight, iconSize)
                                    iconColor: root.cursor.section === 2 ? Color.accent : root.foreground
                                    anchors.verticalCenter: parent.verticalCenter

                                    Behavior on iconColor {
                                        ColorAnimation { duration: 120 }
                                    }
                                }

                                Text {
                                    id: temperatureLabel

                                    text: root.text("temperature")
                                    color: root.foreground
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.body
                                    elide: Text.ElideRight
                                    width: Math.max(0, parent.width - temperatureBadge.implicitWidth - temperatureIcon.width - 2 * Style.spacing.controlGap)
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                BorderSurface {
                                    id: temperatureBadge

                                    implicitWidth: temperatureValue.implicitWidth + Style.space(12)
                                    implicitHeight: temperatureValue.implicitHeight + Style.space(4)
                                    anchors.verticalCenter: parent.verticalCenter
                                    radius: Style.cornerRadius
                                    color: root.cursor.section === 2
                                        ? Style.selectedFillFor(root.foreground, Color.accent)
                                        : Style.normalFillFor(root.foreground, Color.accent)
                                    borderSpec: Border.flat(
                                        root.cursor.section === 2
                                            ? Util.alpha(Color.accent, Style.hoverBorderAlpha)
                                            : Util.alpha(root.foreground, Style.normalBorderAlpha),
                                        Style.spacing.hairline
                                    )

                                    Behavior on color {
                                        ColorAnimation { duration: 120 }
                                    }

                                    Text {
                                        id: temperatureValue

                                        anchors.centerIn: parent
                                        text: root.stateReady ? root.displayValue("temperature", root.state.temperature) + " K" : "—"
                                        color: root.cursor.section === 2 ? Color.accent : root.foreground
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                        font.bold: true

                                        Behavior on color {
                                            ColorAnimation { duration: 120 }
                                        }
                                    }
                                }
                            }

                            PanelSlider {
                                width: parent.width
                                bar: root.bar
                                knobSize: Math.max(16, Style.space(16))
                                value: root.displayValue("temperature", root.state.temperature === null ? 2500 : root.state.temperature)
                                minimum: 2500
                                maximum: 6500
                                step: 1
                                integer: true
                                enabled: root.stateReady
                                Accessible.name: root.text("temperature")
                                onMoved: function(v) { root.queueDragMutation("temperature", v) }
                            }
                        }

                    }

                    CursorSurface {
                        width: parent.width
                        hasCursor: root.cursor.section === 3
                        foreground: root.foreground
                        implicitHeight: gammaColumn.implicitHeight + root.sectionPad

                        HoverHandler {
                            onHoveredChanged: if (hovered) root.cursorToSection(3)
                        }

                        Column {
                            id: gammaColumn

                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: Style.spacing.rowPaddingX
                            anchors.rightMargin: Style.spacing.rowPaddingX
                            spacing: Style.spacing.labelGap

                            Row {
                                width: parent.width
                                spacing: Style.spacing.controlGap

                                NerdIcon {
                                    id: gammaIcon

                                    glyph: Icons.glyph("gamma")
                                    iconSize: Style.font.icon
                                    width: root.controlIconSlot
                                    height: Math.max(implicitHeight, iconSize)
                                    iconColor: root.cursor.section === 3 ? Color.accent : root.foreground
                                    anchors.verticalCenter: parent.verticalCenter

                                    Behavior on iconColor {
                                        ColorAnimation { duration: 120 }
                                    }
                                }

                                Text {
                                    id: gammaLabel

                                    text: root.text("gamma_short")
                                    color: root.foreground
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.body
                                    elide: Text.ElideRight
                                    width: Math.max(0, parent.width - gammaBadge.implicitWidth - gammaIcon.width - 2 * Style.spacing.controlGap)
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                BorderSurface {
                                    id: gammaBadge

                                    implicitWidth: gammaValue.implicitWidth + Style.space(12)
                                    implicitHeight: gammaValue.implicitHeight + Style.space(4)
                                    anchors.verticalCenter: parent.verticalCenter
                                    radius: Style.cornerRadius
                                    color: root.cursor.section === 3
                                        ? Style.selectedFillFor(root.foreground, Color.accent)
                                        : Style.normalFillFor(root.foreground, Color.accent)
                                    borderSpec: Border.flat(
                                        root.cursor.section === 3
                                            ? Util.alpha(Color.accent, Style.hoverBorderAlpha)
                                            : Util.alpha(root.foreground, Style.normalBorderAlpha),
                                        Style.spacing.hairline
                                    )

                                    Behavior on color {
                                        ColorAnimation { duration: 120 }
                                    }

                                    Text {
                                        id: gammaValue

                                        anchors.centerIn: parent
                                        text: root.stateReady ? root.displayValue("gamma", root.state.gamma) + "%" : "—"
                                        color: root.cursor.section === 3 ? Color.accent : root.foreground
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                        font.bold: true

                                        Behavior on color {
                                            ColorAnimation { duration: 120 }
                                        }
                                    }
                                }
                            }

                            PanelSlider {
                                width: parent.width
                                bar: root.bar
                                knobSize: Math.max(16, Style.space(16))
                                value: root.displayValue("gamma", root.state.gamma === null ? 0 : root.state.gamma)
                                minimum: 0
                                maximum: 100
                                step: 1
                                integer: true
                                enabled: root.stateReady
                                Accessible.name: root.text("gamma")
                                onMoved: function(v) { root.queueDragMutation("gamma", v) }
                            }
                        }

                    }

                    PanelSeparator {
                        foreground: root.foreground
                    }

                    CursorSurface {
                        width: parent.width
                        hasCursor: root.cursor.section === 4
                        foreground: root.foreground
                        implicitHeight: monitorSelector.implicitHeight + root.sectionPad

                        HoverHandler {
                            onHoveredChanged: if (hovered) root.cursorToSection(4)
                        }

                        SearchableDropdown {
                            id: monitorSelector

                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: Style.spacing.rowPaddingX
                            anchors.rightMargin: Style.spacing.rowPaddingX
                            label: root.text("monitor")
                            value: root.selectedMonitor
                            options: root.monitorOptions
                            foreground: root.foreground
                            accent: Color.accent
                            showLabel: true
                            onPopupOpenChanged: if (!monitorSelector.popupOpen) Qt.callLater(function() { keyCatcher.forceActiveFocus(); })
                            onChanged: function(value) { root.setInlineSetting("monitor", value) }
                        }

                    }
                }

                Column {
                    id: automationRoute

                    visible: root.route === "automation"
                    opacity: root.route === "automation" ? 1.0 : 0.0
                    width: parent.width
                    spacing: Style.spacing.panelGap
                    transform: Translate {
                        x: root.route === "automation" ? 0 : (root.transitionDirection > 0 ? 12 : -12)
                        Behavior on x {
                            NumberAnimation {
                                duration: 180
                                easing.type: Easing.OutCubic
                            }
                        }
                    }

                    Behavior on opacity {
                        NumberAnimation {
                            duration: 180
                            easing.type: Easing.OutCubic
                        }
                    }

                    CursorSurface {
                        width: parent.width
                        hasCursor: root.cursor.section === 0
                        foreground: root.foreground
                        implicitHeight: automationHeader.implicitHeight + root.headerPad

                        HoverHandler {
                            onHoveredChanged: if (hovered) root.cursorToSection(0)
                        }

                        Item {
                            id: automationHeader

                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: Style.spacing.rowPaddingX
                            anchors.rightMargin: Style.spacing.rowPaddingX
                            height: Math.max(scheduleLabelsRow.implicitHeight, scheduleToggle.implicitHeight)
                            implicitHeight: height

                            Row {
                                id: scheduleLabelsRow

                                anchors.left: parent.left
                                anchors.right: scheduleToggle.left
                                anchors.rightMargin: Style.spacing.controlGap
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: Style.spacing.xxl

                                NerdIcon {
                                    id: scheduleIcon

                                    glyph: Icons.glyph("schedule")
                                    iconSize: Style.font.display
                                    width: Style.font.display
                                    height: Style.font.display
                                    iconColor: root.foreground
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                Column {
                                    id: scheduleLabelsColumn

                                    width: parent.width - scheduleIcon.width - parent.spacing
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: Style.spacing.xxs

                                    Text {
                                        width: parent.width
                                        text: root.text("schedule")
                                        color: root.foreground
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.title
                                        font.bold: true
                                        elide: Text.ElideRight
                                    }

                                    // The switch already says whether the schedule
                                    // runs: the text carries the programmed window
                                    // only while it is enabled.
                                    Text {
                                        visible: root.scheduleEnabled && root.stateReady
                                        width: parent.width
                                        text: (root.state.schedule.day_time || "06:00") + "  →  " + (root.state.schedule.night_time || "15:30")
                                        color: Qt.darker(root.foreground, 1.35)
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                        elide: Text.ElideRight
                                    }
                                }
                            }

                            ToggleSwitch {
                                id: scheduleToggle

                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                checked: root.scheduleEnabled
                                busy: !root.automationReady || root.actionPending
                                foreground: root.foreground
                                Accessible.name: root.text("schedule")
                                onToggled: root.toggleSchedule(!root.scheduleEnabled)
                            }
                        }
                    }

                    // The schedule itself: each period sets its time and the
                    // same three options the Home sliders drive, entered as
                    // numbers.
                    CursorSurface {
                        width: parent.width
                        hasCursor: root.cursor.section === 1
                        foreground: root.foreground
                        implicitHeight: scheduleEditorColumn.implicitHeight + root.sectionPad

                        HoverHandler {
                            onHoveredChanged: if (hovered) root.cursorToSection(1)
                        }

                        Column {
                            id: scheduleEditorColumn

                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: Style.spacing.rowPaddingX
                            anchors.rightMargin: Style.spacing.rowPaddingX
                            spacing: Style.spacing.rowGap

                            Item {
                                width: parent.width
                                implicitHeight: Math.max(dayHeaderRow.implicitHeight, dayDurationBadge.implicitHeight)

                                Row {
                                    id: dayHeaderRow
                                    anchors.left: parent.left
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: Style.spacing.sm

                                    NerdIcon {
                                        glyph: Icons.glyph("weatherSunny")
                                        iconSize: Style.font.body
                                        iconColor: Color.accent
                                        anchors.verticalCenter: parent.verticalCenter
                                    }

                                    Text {
                                        text: root.text("day_period")
                                        color: root.foreground
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.body
                                        font.bold: true
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                }

                                BorderSurface {
                                    id: dayDurationBadge
                                    visible: Boolean(root.scheduleDurationInfo && root.scheduleDurationInfo.valid && root.scheduleDurationInfo.dayFormatted)
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: Style.hoverFillFor(root.foreground, Color.accent)
                                    borderSpec: Border.flat(Util.alpha(Color.accent, 0.3), Style.spacing.hairline)
                                    radius: Style.cornerRadius
                                    implicitHeight: dayDurationText.implicitHeight + Style.spacing.xxs * 2
                                    implicitWidth: dayDurationText.implicitWidth + Style.spacing.sm * 2

                                    Text {
                                        id: dayDurationText
                                        anchors.centerIn: parent
                                        text: root.scheduleDurationInfo && root.scheduleDurationInfo.dayFormatted ? root.scheduleDurationInfo.dayFormatted : ""
                                        color: Color.accent
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.caption
                                        font.bold: true
                                    }
                                }
                            }

                            Row {
                                width: parent.width
                                spacing: Style.spacing.controlGap

                                Column {
                                    width: (parent.width - Style.spacing.controlGap) / 2
                                    spacing: Style.spacing.md

                                    Text {
                                        width: parent.width
                                        text: root.text("start")
                                        color: Qt.darker(root.foreground, 1.4)
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                        elide: Text.ElideRight
                                    }

                                    TextField {
                                        id: startEditor

                                        width: parent.width
                                        implicitHeight: Math.max(Style.spacing.controlHeight, font.pixelSize + Style.spacing.controlPaddingY * 2)
                                        horizontalAlignment: Qt.AlignHCenter
                                        foreground: root.foreground
                                        font.family: root.fontFamily
                                        text: root.editStart
                                        inputMask: "99:99"
                                        Accessible.name: root.text("day_period") + " " + root.text("start")
                                        Accessible.role: Accessible.EditableText
                                        onTextChanged: root.editStart = text
                                        onAccepted: dayTemperatureEditor.field.forceActiveFocus()
                                        Keys.onEscapePressed: keyCatcher.forceActiveFocus()
                                    }
                                }

                                NumberField {
                                    id: dayTemperatureEditor

                                    width: (parent.width - Style.spacing.controlGap) / 2
                                    fieldWidth: width
                                    label: root.text("temperature") + " (K)"
                                    // Matches the helper's DAY_TEMP_MIN/DAY_TEMP_MAX
                                    // (5900–6500): the day period is the high-light
                                    // window, so its temperature range is narrower
                                    // than the Home slider's.
                                    value: Number(root.editDayTemperature || 6000)
                                    from: 5900
                                    to: 6500
                                    stepSize: 50
                                    foreground: root.foreground
                                    fontFamily: root.fontFamily
                                    Accessible.name: root.text("day_period") + " " + root.text("temperature")
                                    onModified: value => root.editDayTemperature = String(value)
                                    field.Keys.priority: Keys.BeforeItem
                                    field.Keys.onPressed: function(event) {
                                        if (event.key === Qt.Key_Escape) {
                                            keyCatcher.forceActiveFocus();
                                            event.accepted = true;
                                        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                            dayBrightnessEditor.field.forceActiveFocus();
                                            event.accepted = true;
                                        }
                                    }
                                }
                            }

                            Row {
                                width: parent.width
                                spacing: Style.spacing.controlGap

                                NumberField {
                                    id: dayBrightnessEditor

                                    width: (parent.width - Style.spacing.controlGap) / 2
                                    fieldWidth: width
                                    label: root.text("brightness") + " (%)"
                                    value: Number(root.editDayBrightness || 100)
                                    from: 1
                                    to: 100
                                    stepSize: 5
                                    foreground: root.foreground
                                    fontFamily: root.fontFamily
                                    Accessible.name: root.text("day_period") + " " + root.text("brightness")
                                    onModified: value => root.editDayBrightness = String(value)
                                    field.Keys.priority: Keys.BeforeItem
                                    field.Keys.onPressed: function(event) {
                                        if (event.key === Qt.Key_Escape) {
                                            keyCatcher.forceActiveFocus();
                                            event.accepted = true;
                                        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                            dayGammaEditor.field.forceActiveFocus();
                                            event.accepted = true;
                                        }
                                    }
                                }

                                NumberField {
                                    id: dayGammaEditor

                                    width: (parent.width - Style.spacing.controlGap) / 2
                                    fieldWidth: width
                                    label: root.text("gamma_short") + " (%)"
                                    value: Number(root.editDayGamma || 100)
                                    from: 0
                                    to: 100
                                    stepSize: 5
                                    foreground: root.foreground
                                    fontFamily: root.fontFamily
                                    Accessible.name: root.text("day_period") + " " + root.text("gamma")
                                    onModified: value => root.editDayGamma = String(value)
                                    field.Keys.priority: Keys.BeforeItem
                                    field.Keys.onPressed: function(event) {
                                        if (event.key === Qt.Key_Escape) {
                                            keyCatcher.forceActiveFocus();
                                            event.accepted = true;
                                        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                            endEditor.forceActiveFocus();
                                            event.accepted = true;
                                        }
                                    }
                                }
                            }

                            Item {
                                width: parent.width
                                implicitHeight: Math.max(nightHeaderRow.implicitHeight, nightDurationBadge.implicitHeight)

                                Row {
                                    id: nightHeaderRow
                                    anchors.left: parent.left
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: Style.spacing.sm

                                    NerdIcon {
                                        glyph: Icons.glyph("weatherNight")
                                        iconSize: Style.font.body
                                        iconColor: Qt.darker(root.foreground, 1.2)
                                        anchors.verticalCenter: parent.verticalCenter
                                    }

                                    Text {
                                        text: root.text("night_period")
                                        color: root.foreground
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.body
                                        font.bold: true
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                }

                                BorderSurface {
                                    id: nightDurationBadge
                                    visible: Boolean(root.scheduleDurationInfo && root.scheduleDurationInfo.valid && root.scheduleDurationInfo.nightFormatted)
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: Style.hoverFillFor(root.foreground, Color.accent)
                                    borderSpec: Border.flat(Util.alpha(Color.accent, 0.3), Style.spacing.hairline)
                                    radius: Style.cornerRadius
                                    implicitHeight: nightDurationText.implicitHeight + Style.spacing.xxs * 2
                                    implicitWidth: nightDurationText.implicitWidth + Style.spacing.sm * 2

                                    Text {
                                        id: nightDurationText
                                        anchors.centerIn: parent
                                        text: root.scheduleDurationInfo && root.scheduleDurationInfo.nightFormatted ? root.scheduleDurationInfo.nightFormatted : ""
                                        color: Color.accent
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.caption
                                        font.bold: true
                                    }
                                }
                            }

                            Row {
                                width: parent.width
                                spacing: Style.spacing.controlGap

                                Column {
                                    width: (parent.width - Style.spacing.controlGap) / 2
                                    spacing: Style.spacing.md

                                    Text {
                                        width: parent.width
                                        text: root.text("end")
                                        color: Qt.darker(root.foreground, 1.4)
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                        elide: Text.ElideRight
                                    }

                                    TextField {
                                        id: endEditor

                                        width: parent.width
                                        implicitHeight: Math.max(Style.spacing.controlHeight, font.pixelSize + Style.spacing.controlPaddingY * 2)
                                        horizontalAlignment: Qt.AlignHCenter
                                        foreground: root.foreground
                                        font.family: root.fontFamily
                                        text: root.editEnd
                                        inputMask: "99:99"
                                        Accessible.name: root.text("night_period") + " " + root.text("end")
                                        Accessible.role: Accessible.EditableText
                                        onTextChanged: root.editEnd = text
                                        onAccepted: nightTemperatureEditor.field.forceActiveFocus()
                                        Keys.onEscapePressed: keyCatcher.forceActiveFocus()
                                    }
                                }

                                NumberField {
                                    id: nightTemperatureEditor

                                    width: (parent.width - Style.spacing.controlGap) / 2
                                    fieldWidth: width
                                    label: root.text("temperature") + " (K)"
                                    value: Number(root.editNightTemperature || 3500)
                                    from: 2500
                                    to: 5000
                                    stepSize: 50
                                    foreground: root.foreground
                                    fontFamily: root.fontFamily
                                    Accessible.name: root.text("night_period") + " " + root.text("temperature")
                                    onModified: value => root.editNightTemperature = String(value)
                                    field.Keys.priority: Keys.BeforeItem
                                    field.Keys.onPressed: function(event) {
                                        if (event.key === Qt.Key_Escape) {
                                            keyCatcher.forceActiveFocus();
                                            event.accepted = true;
                                        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                            nightBrightnessEditor.field.forceActiveFocus();
                                            event.accepted = true;
                                        }
                                    }
                                }
                            }

                            Row {
                                width: parent.width
                                spacing: Style.spacing.controlGap

                                NumberField {
                                    id: nightBrightnessEditor

                                    width: (parent.width - Style.spacing.controlGap) / 2
                                    fieldWidth: width
                                    label: root.text("brightness") + " (%)"
                                    value: Number(root.editNightBrightness || 100)
                                    from: 1
                                    to: 100
                                    stepSize: 5
                                    foreground: root.foreground
                                    fontFamily: root.fontFamily
                                    Accessible.name: root.text("night_period") + " " + root.text("brightness")
                                    onModified: value => root.editNightBrightness = String(value)
                                    field.Keys.priority: Keys.BeforeItem
                                    field.Keys.onPressed: function(event) {
                                        if (event.key === Qt.Key_Escape) {
                                            keyCatcher.forceActiveFocus();
                                            event.accepted = true;
                                        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                            nightGammaEditor.field.forceActiveFocus();
                                            event.accepted = true;
                                        }
                                    }
                                }

                                NumberField {
                                    id: nightGammaEditor

                                    width: (parent.width - Style.spacing.controlGap) / 2
                                    fieldWidth: width
                                    label: root.text("gamma_short") + " (%)"
                                    value: Number(root.editNightGamma || 100)
                                    from: 0
                                    to: 100
                                    stepSize: 5
                                    foreground: root.foreground
                                    fontFamily: root.fontFamily
                                    Accessible.name: root.text("night_period") + " " + root.text("gamma")
                                    onModified: value => root.editNightGamma = String(value)
                                    field.Keys.priority: Keys.BeforeItem
                                    field.Keys.onPressed: function(event) {
                                        if (event.key === Qt.Key_Escape) {
                                            keyCatcher.forceActiveFocus();
                                            event.accepted = true;
                                        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                            saveScheduleButton.forceActiveFocus();
                                            event.accepted = true;
                                        }
                                    }
                                }
                            }

                            // Field errors live right above the action that
                            // fails, so an inactive Save is never unexplained.
                            BorderSurface {
                                id: scheduleValidationBanner

                                visible: root.scheduleValidationError !== ""
                                opacity: root.scheduleValidationError !== "" ? 1.0 : 0.0
                                width: parent.width
                                color: Style.hoverFillFor(root.foreground, Color.urgent)
                                borderSpec: Border.flat(Util.alpha(Color.urgent, Style.hoverBorderAlpha), Style.spacing.hairline)
                                radius: Style.cornerRadius
                                implicitHeight: scheduleValidationRow.implicitHeight + Style.spacing.controlPaddingY * 2

                                Behavior on opacity {
                                    NumberAnimation {
                                        duration: 160
                                        easing.type: Easing.OutCubic
                                    }
                                }

                                Row {
                                    id: scheduleValidationRow

                                    anchors.centerIn: parent
                                    width: parent.width - Style.spacing.controlPaddingX * 2
                                    spacing: Style.spacing.sm

                                    NerdIcon {
                                        glyph: Icons.glyph("alert")
                                        iconSize: Style.font.bodySmall
                                        iconColor: Color.urgent
                                        anchors.verticalCenter: parent.verticalCenter
                                    }

                                    Text {
                                        width: parent.width - (Style.font.bodySmall + Style.spacing.sm)
                                        text: root.scheduleValidationError
                                        color: Color.urgent
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                        wrapMode: Text.WordWrap
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                }
                            }

                            Row {
                                width: parent.width
                                spacing: Style.spacing.controlGap

                                Button {
                                    id: resetScheduleButton

                                    text: root.text("cancel")
                                    width: (parent.width - Style.spacing.controlGap) / 2
                                    leftAlign: false
                                    bordered: true
                                    focusable: true
                                    foreground: root.foreground
                                    Accessible.name: root.text("cancel")
                                    Accessible.role: Accessible.Button
                                    enabled: root.stateReady && !root.actionPending
                                    onClicked: {
                                        root.populateScheduleEditor();
                                        root.refocusKeyCatcher();
                                    }
                                }

                                Button {
                                    id: saveScheduleButton

                                    text: root.text("save")
                                    width: (parent.width - Style.spacing.controlGap) / 2
                                    leftAlign: false
                                    bordered: true
                                    focusable: true
                                    foreground: root.foreground
                                    accent: Color.accent
                                    Accessible.name: root.text("save")
                                    Accessible.role: Accessible.Button
                                    enabled: root.stateReady && !root.actionPending
                                    onClicked: {
                                        root.queueSchedule();
                                        root.refocusKeyCatcher();
                                    }
                                }
                            }

                            BorderSurface {
                                id: feedbackBanner

                                width: parent.width
                                visible: root.feedbackText !== ""
                                opacity: root.feedbackText !== "" ? 1.0 : 0.0
                                color: Style.hoverFillFor(root.foreground, Color.accent)
                                borderSpec: Border.flat(Util.alpha(Color.accent, Style.hoverBorderAlpha), Style.spacing.hairline)
                                radius: Style.cornerRadius
                                implicitHeight: feedbackRow.implicitHeight + Style.spacing.controlPaddingY * 2

                                Behavior on opacity {
                                    NumberAnimation {
                                        duration: 160
                                        easing.type: Easing.OutCubic
                                    }
                                }

                                Row {
                                    id: feedbackRow

                                    anchors.centerIn: parent
                                    spacing: Style.spacing.sm

                                    NerdIcon {
                                        glyph: Icons.glyph("check")
                                        iconSize: Style.font.bodySmall
                                        iconColor: Color.accent
                                        anchors.verticalCenter: parent.verticalCenter
                                    }

                                    Text {
                                        text: root.feedbackText
                                        color: root.foreground
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                        font.bold: true
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                }
                            }
                        }

                    }

                    // Snooze: enter a duration, pick its unit, apply.
                    CursorSurface {
                        width: parent.width
                        hasCursor: root.cursor.section === 2
                        foreground: root.foreground
                        implicitHeight: snoozeColumn.implicitHeight + root.sectionPad

                        HoverHandler {
                            onHoveredChanged: if (hovered) root.cursorToSection(2)
                        }

                        Column {
                            id: snoozeColumn

                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: Style.spacing.rowPaddingX
                            anchors.rightMargin: Style.spacing.rowPaddingX
                            spacing: Style.spacing.controlGap

                            PanelSectionHeader {
                                width: parent.width
                                text: root.text("snooze")
                                foreground: root.foreground
                                fontFamily: root.fontFamily
                                elide: Text.ElideRight
                            }

                            // The active snooze is a fact the user set and must
                            // be able to verify at a glance.
                            BorderSurface {
                                visible: root.snoozeActive
                                width: parent.width
                                radius: Style.cornerRadius
                                color: Style.hoverFillFor(root.foreground, Color.accent)
                                borderSpec: Border.controlSpec("normal", Color.urgent, Color.urgent)
                                implicitHeight: activeSnoozeColumn.implicitHeight + Style.spacing.md * 2

                                Column {
                                    id: activeSnoozeColumn
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.leftMargin: Style.spacing.controlPaddingX
                                    anchors.rightMargin: Style.spacing.controlPaddingX
                                    spacing: Style.spacing.xs

                                    Row {
                                        width: parent.width
                                        spacing: Style.spacing.xs

                                        NerdIcon {
                                            glyph: Icons.glyph("snooze")
                                            iconColor: Color.urgent
                                            iconSize: Style.font.body
                                            width: iconSize
                                            height: iconSize
                                            anchors.verticalCenter: parent.verticalCenter
                                        }

                                        Text {
                                            width: parent.width - Style.font.body - Style.spacing.xs
                                            text: root.text("snooze_active") + " · " + root.snoozeRemainingMinutes + " " + root.text("minutes_short")
                                            color: Color.urgent
                                            font.family: root.fontFamily
                                            font.pixelSize: Style.font.bodySmall
                                            font.bold: true
                                            elide: Text.ElideRight
                                            anchors.verticalCenter: parent.verticalCenter
                                        }
                                    }

                                    // Progress bar indicator
                                    Rectangle {
                                        width: parent.width
                                        height: Style.space(3)
                                        radius: Style.space(1.5)
                                        color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.15)

                                        Rectangle {
                                            height: parent.height
                                            radius: parent.radius
                                            color: Color.urgent
                                            width: {
                                                var until = root.state.automation ? Number(root.state.automation.snooze_until) : 0;
                                                var remSecs = isFinite(until) && until > 0 ? Math.max(0, until - Date.now() / 1000) : 0;
                                                var totalSecs = root.snoozeSeconds ? root.snoozeSeconds : 1800;
                                                var ratio = Math.min(1.0, remSecs / Math.max(remSecs, totalSecs));
                                                return parent.width * ratio;
                                            }
                                            Behavior on width { NumberAnimation { duration: 250 } }
                                        }
                                    }
                                }
                            }

                            // Quick preset pills row
                            Row {
                                width: parent.width
                                spacing: Style.spacing.xs

                                Button {
                                    width: (parent.width - 4 * Style.spacing.xs) / 5
                                    text: "15m"
                                    fontSize: Style.font.bodySmall
                                    selected: root.snoozeAmount === 15 && root.snoozeUnit === "minutes"
                                    focusable: true
                                    bordered: true
                                    leftAlign: false
                                    foreground: root.foreground
                                    onClicked: root.applyQuickSnooze(15, "minutes")
                                }

                                Button {
                                    width: (parent.width - 4 * Style.spacing.xs) / 5
                                    text: "1h"
                                    fontSize: Style.font.bodySmall
                                    selected: root.snoozeAmount === 1 && root.snoozeUnit === "hours"
                                    focusable: true
                                    bordered: true
                                    leftAlign: false
                                    foreground: root.foreground
                                    onClicked: root.applyQuickSnooze(1, "hours")
                                }

                                Button {
                                    width: (parent.width - 4 * Style.spacing.xs) / 5
                                    text: "2h"
                                    fontSize: Style.font.bodySmall
                                    selected: root.snoozeAmount === 2 && root.snoozeUnit === "hours"
                                    focusable: true
                                    bordered: true
                                    leftAlign: false
                                    foreground: root.foreground
                                    onClicked: root.applyQuickSnooze(2, "hours")
                                }

                                Button {
                                    width: (parent.width - 4 * Style.spacing.xs) / 5
                                    text: "4h"
                                    fontSize: Style.font.bodySmall
                                    selected: root.snoozeAmount === 4 && root.snoozeUnit === "hours"
                                    focusable: true
                                    bordered: true
                                    leftAlign: false
                                    foreground: root.foreground
                                    onClicked: root.applyQuickSnooze(4, "hours")
                                }

                                Button {
                                    width: (parent.width - 4 * Style.spacing.xs) / 5
                                    text: root.text("sunset")
                                    fontSize: Style.font.bodySmall
                                    focusable: true
                                    bordered: true
                                    leftAlign: false
                                    foreground: root.foreground
                                    onClicked: {
                                        var mins = root.minutesUntilSunset();
                                        root.applyQuickSnooze(mins, "minutes");
                                    }
                                }
                            }

                            NumberField {
                                id: snoozeEditor

                                width: parent.width
                                fieldWidth: width
                                value: root.snoozeAmount
                                from: 1
                                to: 86400
                                stepSize: 1
                                foreground: root.foreground
                                fontFamily: root.fontFamily
                                Accessible.name: root.text("snooze")
                                onModified: value => root.snoozeAmount = value
                                field.Keys.priority: Keys.BeforeItem
                                field.Keys.onPressed: function(event) {
                                    if (event.key === Qt.Key_Escape) {
                                        keyCatcher.forceActiveFocus();
                                        event.accepted = true;
                                    } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                        root.applySnooze();
                                        keyCatcher.forceActiveFocus();
                                        event.accepted = true;
                                    }
                                }
                            }

                            Row {
                                width: parent.width
                                spacing: Style.spacing.controlGap

                                Button {
                                    width: (parent.width - 2 * Style.spacing.controlGap) / 3
                                    text: root.text("unit_hours")
                                    selected: root.snoozeUnit === "hours"
                                    focusable: true
                                    bordered: true
                                    leftAlign: false
                                    foreground: root.foreground
                                    onClicked: {
                                        root.snoozeUnit = "hours";
                                        root.refocusKeyCatcher();
                                    }
                                }

                                Button {
                                    width: (parent.width - 2 * Style.spacing.controlGap) / 3
                                    text: root.text("unit_minutes")
                                    selected: root.snoozeUnit === "minutes"
                                    focusable: true
                                    bordered: true
                                    leftAlign: false
                                    foreground: root.foreground
                                    onClicked: {
                                        root.snoozeUnit = "minutes";
                                        root.refocusKeyCatcher();
                                    }
                                }

                                Button {
                                    width: (parent.width - 2 * Style.spacing.controlGap) / 3
                                    text: root.text("unit_seconds")
                                    selected: root.snoozeUnit === "seconds"
                                    focusable: true
                                    bordered: true
                                    leftAlign: false
                                    foreground: root.foreground
                                    onClicked: {
                                        root.snoozeUnit = "seconds";
                                        root.refocusKeyCatcher();
                                    }
                                }
                            }

                            Row {
                                width: parent.width
                                spacing: Style.spacing.controlGap

                                Button {
                                    width: root.snoozeActive ? (parent.width - Style.spacing.controlGap) / 2 : parent.width
                                    text: root.text("snooze_set")
                                    focusable: true
                                    bordered: true
                                    leftAlign: false
                                    foreground: root.foreground
                                    enabled: root.snoozeSeconds !== null && !root.actionPending
                                    onClicked: {
                                        root.applySnooze();
                                        root.refocusKeyCatcher();
                                    }
                                }

                                Button {
                                    visible: root.snoozeActive
                                    width: (parent.width - Style.spacing.controlGap) / 2
                                    text: root.text("clear_snooze")
                                    focusable: true
                                    bordered: true
                                    leftAlign: false
                                    foreground: root.snoozeActive ? Color.urgent : root.foreground
                                    enabled: !root.actionPending
                                    onClicked: {
                                        root.settingsCommand("snooze", ["clear"]);
                                        root.refocusKeyCatcher();
                                    }
                                }
                            }
                        }

                    }
                }

                Column {
                    id: settingsRoute

                    visible: root.route === "settings"
                    opacity: root.route === "settings" ? 1.0 : 0.0
                    width: parent.width
                    spacing: Style.spacing.panelGap
                    transform: Translate {
                        x: root.route === "settings" ? 0 : (root.transitionDirection > 0 ? 12 : -12)
                        Behavior on x {
                            NumberAnimation {
                                duration: 180
                                easing.type: Easing.OutCubic
                            }
                        }
                    }

                    Behavior on opacity {
                        NumberAnimation {
                            duration: 180
                            easing.type: Easing.OutCubic
                        }
                    }

                    PanelSectionHeader {
                        width: parent.width
                        text: root.text("settings")
                        foreground: root.foreground
                        fontFamily: root.fontFamily
                        elide: Text.ElideRight
                    }

                    CursorSurface {
                        width: parent.width
                        hasCursor: root.cursor.section === 0
                        foreground: root.foreground
                        implicitHeight: localeSelector.implicitHeight + root.sectionPad

                        HoverHandler {
                            onHoveredChanged: if (hovered) root.cursorToSection(0)
                        }

                        Dropdown {
                            id: localeSelector

                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: Style.spacing.rowPaddingX
                            anchors.rightMargin: Style.spacing.rowPaddingX
                            label: root.text("language")
                            value: root.locale
                            options: [
                                { value: "en", label: root.text("english") },
                                { value: "es", label: root.text("spanish") }
                            ]
                            foreground: root.foreground
                            onPopupOpenChanged: if (!localeSelector.popupOpen) Qt.callLater(function() { keyCatcher.forceActiveFocus(); })
                            onChanged: function(value) { root.setInlineSetting("locale", value) }
                        }

                    }

                    PanelSectionHeader {
                        width: parent.width
                        text: root.text("shortcut")
                        foreground: root.foreground
                        fontFamily: root.fontFamily
                        elide: Text.ElideRight
                    }

                    CursorSurface {
                        width: parent.width
                        hasCursor: root.cursor.section === 1
                        foreground: root.foreground
                        implicitHeight: shortcutColumn.implicitHeight + root.sectionPad

                        HoverHandler {
                            onHoveredChanged: if (hovered) root.cursorToSection(1)
                        }

                        Column {
                            id: shortcutColumn

                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: Style.spacing.rowPaddingX
                            anchors.rightMargin: Style.spacing.rowPaddingX
                            spacing: Style.spacing.controlGap

                            Row {
                                id: shortcutBadgeRow
                                anchors.horizontalCenter: parent.horizontalCenter
                                spacing: Style.spacing.xs
                                visible: shortcutChipsRepeater.count > 0

                                Repeater {
                                    id: shortcutChipsRepeater
                                    model: Model.parseShortcutTokens(shortcutField.text)

                                    Row {
                                        spacing: Style.spacing.xs

                                        BorderSurface {
                                            color: Style.hoverFillFor(root.foreground, Color.accent)
                                            borderSpec: Border.flat(Util.alpha(Color.accent, 0.4), Style.spacing.hairline)
                                            radius: Style.cornerRadius
                                            implicitHeight: chipText.implicitHeight + Style.spacing.xxs * 2
                                            implicitWidth: chipText.implicitWidth + Style.spacing.sm * 2
                                            anchors.verticalCenter: parent.verticalCenter

                                            Text {
                                                id: chipText
                                                anchors.centerIn: parent
                                                text: modelData
                                                color: (modelData === "SUPER" || modelData === "SHIFT" || modelData === "CTRL" || modelData === "ALT" || modelData === "MOD4" || modelData === "MOD1") ? Color.accent : root.foreground
                                                font.family: root.fontFamily
                                                font.pixelSize: Style.font.caption
                                                font.bold: true
                                            }
                                        }

                                        Text {
                                            visible: index < shortcutChipsRepeater.count - 1
                                            text: "+"
                                            color: Qt.darker(root.foreground, 1.4)
                                            font.family: root.fontFamily
                                            font.pixelSize: Style.font.caption
                                            font.bold: true
                                            anchors.verticalCenter: parent.verticalCenter
                                        }
                                    }
                                }
                            }

                            TextField {
                                id: shortcutField

                                width: parent.width
                                text: root.shortcutKeys
                                placeholderText: root.text("shortcut_keys")
                                foreground: root.foreground
                                font.family: root.fontFamily
                                Accessible.name: root.text("shortcut_keys")
                                Accessible.role: Accessible.EditableText
                                onAccepted: {
                                    root.setInlineSetting("shortcutKeys", text);
                                    keyCatcher.forceActiveFocus();
                                }
                                Keys.onEscapePressed: keyCatcher.forceActiveFocus()
                            }

                            Row {
                                width: parent.width
                                spacing: Style.spacing.controlGap

                                HoverHandler {
                                    onHoveredChanged: if (hovered) root.cursorToSection(2)
                                }

                                Button {
                                    text: root.text("install_shortcut")
                                    width: (parent.width - Style.spacing.controlGap) / 2
                                    focusable: true
                                    bordered: true
                                    leftAlign: false
                                    foreground: root.foreground
                                    hasCursor: root.cursor.section === 2
                                    enabled: !root.actionPending && shortcutField.text.trim() !== ""
                                    onClicked: {
                                        root.setInlineSetting("shortcutKeys", shortcutField.text);
                                        root.settingsCommand("shortcut", ["install", "--keys", shortcutField.text]);
                                        root.refocusKeyCatcher();
                                    }
                                }

                                Button {
                                    text: root.text("remove_shortcut")
                                    width: (parent.width - Style.spacing.controlGap) / 2
                                    focusable: true
                                    bordered: true
                                    leftAlign: false
                                    foreground: root.foreground
                                    hasCursor: root.cursor.section === 2
                                    enabled: !root.actionPending
                                    onClicked: {
                                        root.settingsCommand("shortcut", ["remove"]);
                                        root.refocusKeyCatcher();
                                    }
                                }
                            }

                            BorderSurface {
                                id: settingsFeedbackBanner

                                width: parent.width
                                visible: root.feedbackText !== ""
                                opacity: root.feedbackText !== "" ? 1.0 : 0.0
                                color: Style.hoverFillFor(root.foreground, Color.accent)
                                borderSpec: Border.flat(Util.alpha(Color.accent, Style.hoverBorderAlpha), Style.spacing.hairline)
                                radius: Style.cornerRadius
                                implicitHeight: settingsFeedbackRow.implicitHeight + Style.spacing.controlPaddingY * 2

                                Behavior on opacity {
                                    NumberAnimation {
                                        duration: 160
                                        easing.type: Easing.OutCubic
                                    }
                                }

                                Row {
                                    id: settingsFeedbackRow

                                    anchors.centerIn: parent
                                    spacing: Style.spacing.sm

                                    NerdIcon {
                                        glyph: Icons.glyph("check")
                                        iconSize: Style.font.bodySmall
                                        iconColor: Color.accent
                                        anchors.verticalCenter: parent.verticalCenter
                                    }

                                    Text {
                                        text: root.feedbackText
                                        color: root.foreground
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                        font.bold: true
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                }
                            }
                        }

                    }
                }

                // One quiet line keeps the arrow model discoverable without a
                // tutorial.
                Text {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.leftMargin: Style.spacing.rowPaddingX
                    anchors.rightMargin: Style.spacing.rowPaddingX
                    horizontalAlignment: Text.AlignHCenter
                    text: root.text("keyboard_hints")
                    color: Qt.darker(root.foreground, 1.4)
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    wrapMode: Text.WordWrap
                }

            }

        }

    }

}
