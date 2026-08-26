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
    property string locale: "en"
    property string selectedMonitor: "focused"
    property string shortcutKeys: "SUPER+SHIFT+N"
    property int snoozeAmount: 30
    property string snoozeUnit: "minutes"
    property string lastError: ""
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
            root.dragTarget = Model.dragTargetEmpty();
            root.cursor = Model.cursorStart();
        }
        root.route = nextRoute;
        // Returning home re-reads the physical baseline the sliders show.
        if (nextRoute === "home") root.requestStatus();
        if (nextRoute === "automation") {
            root.populateScheduleEditor();
            root.request(["schedule", "status"], "schedule-status");
        }
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
        var choices = [{ value: "focused", label: text("focused_monitor") }];
        for (var i = 0; i < monitors.length; i++) {
            if (monitors[i] && monitors[i].enabled !== false)
                choices.push({ value: String(monitors[i].name), label: String(monitors[i].name) });
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
                Text {
                    visible: root.errorText !== ""
                    width: parent.width
                    leftPadding: Style.spacing.rowPaddingX
                    rightPadding: Style.spacing.rowPaddingX
                    text: root.errorText
                    color: Color.urgent
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.WordWrap
                }

                CursorSurface {
                    id: heroSurface

                    visible: root.route === "home"
                    width: parent.width
                    hasCursor: root.cursor.section === 0
                    foreground: root.foreground
                    implicitHeight: hero.implicitHeight + Style.spacing.rowPaddingX

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
                    width: parent.width
                    spacing: Style.spacing.panelGap

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
                                    iconColor: root.foreground
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                Text {
                                    id: brightnessLabel

                                    text: root.text("brightness")
                                    color: root.foreground
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.body
                                    elide: Text.ElideRight
                                    width: Math.max(0, parent.width - brightnessValue.implicitWidth - brightnessIcon.width - 2 * Style.spacing.controlGap)
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                Text {
                                    id: brightnessValue

                                    text: root.stateReady ? root.displayValue("brightness", root.state.brightness.percent) + "%" : "—"
                                    color: root.foreground
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.body
                                    font.bold: true
                                    anchors.verticalCenter: parent.verticalCenter
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
                                    iconColor: root.foreground
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                Text {
                                    id: temperatureLabel

                                    text: root.text("temperature")
                                    color: root.foreground
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.body
                                    elide: Text.ElideRight
                                    width: Math.max(0, parent.width - temperatureValue.implicitWidth - temperatureIcon.width - 2 * Style.spacing.controlGap)
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                Text {
                                    id: temperatureValue

                                    text: root.stateReady ? root.displayValue("temperature", root.state.temperature) + " K" : "—"
                                    color: root.foreground
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.body
                                    font.bold: true
                                    anchors.verticalCenter: parent.verticalCenter
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
                                    iconColor: root.foreground
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                Text {
                                    id: gammaLabel

                                    text: root.text("gamma_short")
                                    color: root.foreground
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.body
                                    elide: Text.ElideRight
                                    width: Math.max(0, parent.width - gammaValue.implicitWidth - gammaIcon.width - 2 * Style.spacing.controlGap)
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                Text {
                                    id: gammaValue

                                    text: root.stateReady ? root.displayValue("gamma", root.state.gamma) + "%" : "—"
                                    color: root.foreground
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.body
                                    font.bold: true
                                    anchors.verticalCenter: parent.verticalCenter
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
                    width: parent.width
                    spacing: Style.spacing.panelGap

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

                            PanelSectionHeader {
                                width: parent.width
                                text: root.text("day_period")
                                foreground: root.foreground
                                fontFamily: root.fontFamily
                                elide: Text.ElideRight
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

                            PanelSectionHeader {
                                width: parent.width
                                text: root.text("night_period")
                                foreground: root.foreground
                                fontFamily: root.fontFamily
                                elide: Text.ElideRight
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
                            Text {
                                visible: root.scheduleValidationError !== ""
                                width: parent.width
                                text: root.scheduleValidationError
                                color: Color.urgent
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.bodySmall
                                wrapMode: Text.WordWrap
                            }

                            Button {
                                id: saveScheduleButton

                                text: root.text("save")
                                width: parent.width
                                leftAlign: false
                                bordered: true
                                focusable: true
                                foreground: root.foreground
                                Accessible.name: root.text("save")
                                Accessible.role: Accessible.Button
                                enabled: root.stateReady && !root.actionPending
                                onClicked: {
                                    root.queueSchedule();
                                    root.refocusKeyCatcher();
                                }
                            }

                            Text {
                                visible: root.feedbackText !== ""
                                width: parent.width
                                text: root.feedbackText
                                color: root.foreground
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.bodySmall
                                wrapMode: Text.WordWrap
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
                            Text {
                                visible: root.snoozeActive
                                width: parent.width
                                text: root.text("snooze_active") + " · " + root.snoozeRemainingMinutes + " " + root.text("minutes_short")
                                color: Color.urgent
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.bodySmall
                                elide: Text.ElideRight
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
                    width: parent.width
                    spacing: Style.spacing.panelGap

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
