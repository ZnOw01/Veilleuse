import QtQuick
import Quickshell.Io
import "UiModel.js" as Model
import "I18n.js" as I18n
import qs.Commons
import qs.Ui

Panel {
    id: root

    property Item anchorItem: null
    property var state: root.normalizeCombined({})
    property string route: "home"
    property string locale: "es"
    property string applyScope: "session"
    property string selectedMonitor: "focused"
    property string preferredPreset: "reading"
    property string customPresetName: ""
    property string shortcutKeys: "SUPER+SHIFT+N"
    property int transitionSeconds: 8
    property bool scheduleEditorOpen: false
    property bool presetsLoaded: false
    property bool historyLoaded: false
    property bool preflightLoaded: false
    property var presetItems: []
    property var historyItems: []
    property var preflightState: ({})
    property string lastAppliedText: ""
    property string operationOrigin: "unknown"
    property var cursor: Model.cursorStart()
    property bool scheduleExpanded: false
    property string editStart: "06:00"
    property string editEnd: "15:30"
    property bool editNaturalDay: true
    property string editDayTemperature: "6000"
    property string editNightTemperature: "3500"
    property string lastError: ""
    property string feedbackText: ""
    property bool actionPending: false
    property int latestRequestId: 0
    property int queuedRequestId: 0
    property int processRequestId: 0
    property var pendingSteps: { "brightness": 0, "temperature": 0, "gamma": 0 }
    property string queuedOperation: ""
    property var queuedCommand: []
    property bool stoppingForLatest: false
    property string processOutput: ""
    property string processError: ""
    readonly property color foreground: bar ? bar.foreground : Color.foreground
    readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
    readonly property string helperPath: root.normalizedPath(root.setting("helperPath", ""))
    readonly property bool stateReady: state.available === true
    readonly property string statusText: !stateReady ? root.text("unavailable") : (state.enabled ? root.text("enabled") : root.text("disabled"))
    readonly property string scheduleValidationError: Model.validateScheduleFields(editStart, editEnd, editNaturalDay, editDayTemperature, editNightTemperature, root.locale).error
    readonly property string errorText: root.lastError !== "" ? root.lastError : (root.scheduleExpanded && root.scheduleValidationError !== "" ? root.scheduleValidationError : root.localizeErrorString(root.state.error || ""))
    readonly property string periodText: root.stateReady && root.state.schedule.period === "day" ? root.text("period_day") : (root.stateReady && root.state.schedule.period === "night" ? root.text("period_night") : root.statusText)
    readonly property string manualOverrideText: root.text("manual_override")
    readonly property string heroMeta: root.periodText + (Model.isManualOverride(root.state) ? " · " + root.manualOverrideText : "")
    readonly property real valueColumnWidth: Style.space(54)
    readonly property var routeOptions: ["home", "automation", "settings"]
    readonly property var monitorOptions: root.monitorChoices()
    readonly property var presetOptions: root.presetChoices()
    readonly property string automationOrigin: root.state.automation && root.state.automation.origin ? String(root.state.automation.origin) : root.operationOrigin
    readonly property bool automationReady: Boolean(root.state.automation && root.state.automation.available === true)
    readonly property bool scheduleEnabled: Boolean(root.automationReady && root.state.automation.schedule_enabled !== false)
    readonly property string provenanceText: I18n.t("origin_" + root.automationOrigin, root.locale)
    readonly property string heroGlyph: root.glyphForState(root.state)
    readonly property string scopeText: I18n.t(root.applyScope === "persistent" ? "persistent" : "session", root.locale)

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
    // Spanish "not confirmed" fallback maps to the active locale, and every
    // other literal passes through verbatim.
    function localizeErrorString(value) {
        return Model.localizeStateError(value, root.locale);
    }

    function toggleNightlight() {
        root.request(["nightlight", "toggle"], "toggle");
    }

    function normalizeCombined(raw) {
        var input = raw && typeof raw === "object" ? raw : {};
        var normalized = Model.normalizeState(input);
        normalized.automation = input.automation && typeof input.automation === "object" ? input.automation : {
            schedule_enabled: input.schedule_enabled !== false,
            snooze_until: null,
            snoozed: false,
            transition_seconds: root.transitionSeconds,
            origin: "unknown",
            last_applied: null
        };
        normalized.presets = input.presets && typeof input.presets === "object" ? input.presets : { builtins: [], user: [] };
        normalized.history = Array.isArray(input.history) ? input.history : [];
        normalized.monitors = Array.isArray(input.monitors) ? input.monitors : [];
        normalized.preflight = input.preflight && typeof input.preflight === "object" ? input.preflight : {};
        return normalized;
    }

    function mergeCombined(base, raw) {
        var next = normalizeCombined(base);
        var input = raw && typeof raw === "object" ? raw : {};
        if (input.automation && typeof input.automation === "object") next.automation = input.automation;
        if (input.presets && typeof input.presets === "object") next.presets = input.presets;
        if (Array.isArray(input.history)) next.history = input.history;
        if (Array.isArray(input.monitors)) next.monitors = input.monitors;
        if (input.preflight && typeof input.preflight === "object") next.preflight = input.preflight;
        if (input.origin) root.operationOrigin = String(input.origin);
        if (input.last_applied) root.lastAppliedText = root.formatLastApplied(input.last_applied);
        if (input.automation && input.automation.last_applied)
            root.lastAppliedText = root.formatLastApplied(input.automation.last_applied);
        return next;
    }

    function navigateToRoute(nextRoute) {
        if (root.routeOptions.indexOf(nextRoute) === -1) return;
        if (nextRoute !== root.route)
            root.pendingSteps = { "brightness": 0, "temperature": 0, "gamma": 0 };
        root.route = nextRoute;
        if (nextRoute === "automation" && !root.scheduleEditorOpen) root.request(["schedule", "status"], "schedule-status");
        if (nextRoute === "settings" && !root.preflightLoaded) root.request(["preflight"], "preflight");
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

    function presetChoices() {
        var builtins = [
            { value: "reading", label: text("preset_reading") },
            { value: "work", label: text("preset_work") },
            { value: "cinema", label: text("preset_cinema") }
        ];
        var user = root.state && root.state.presets && Array.isArray(root.state.presets.user) ? root.state.presets.user : [];
        for (var i = 0; i < user.length; i++) {
            var name = user[i] && user[i].name ? String(user[i].name) : "";
            if (name) builtins.push({ value: name, label: name });
        }
        return builtins;
    }

    function glyphForState(value) {
        var input = value || {};
        var automation = input.automation || {};
        if (automation.snoozed === true) return "󰒲";
        if (input.available !== true) return "󰌙";
        if (input.enabled === true) return automation.origin === "preset" ? "󰏘" : "󰖙";
        return automation.schedule_enabled === false ? "󰅙" : "󰖔";
    }

    function formatLastApplied(value) {
        if (!value || typeof value !== "object") return "";
        var preset = value.preset ? String(value.preset) : "";
        var origin = value.origin ? I18n.t("origin_" + String(value.origin), root.locale) : "";
        var stamp = value.at ? String(value.at) : "";
        return [preset, origin, stamp].filter(function(part) { return part !== ""; }).join(" · ");
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
        if (name === "applyScope") root.applyScope = String(value);
        if (name === "monitor") root.selectedMonitor = String(value);
        if (name === "preferredPreset") root.preferredPreset = String(value);
        if (name === "transitionSeconds") root.transitionSeconds = Number(value);
        if (name === "shortcutKeys") root.shortcutKeys = String(value);
        var values = {};
        values[name] = value;
        root.persistInline(values);
    }

    function issue(command, operation) {
        root.request(command, operation);
    }

    function applyPreset(name) {
        root.preferredPreset = String(name);
        root.issue(["preset", "apply", String(name), "--monitor", root.selectedMonitor, "--transition-seconds", String(root.transitionSeconds)], "preset");
    }

    function saveCustomPreset() {
        var name = String(root.customPresetName || "").trim();
        if (name === "" || !root.stateReady || root.actionPending)
            return ;
        root.request(["preset", "save", name,
                      "--temperature", String(root.state.temperature),
                      "--gamma", String(root.state.gamma),
                      "--brightness", String(root.state.brightness.percent)], "preset-save");
    }

    function deleteSelectedCustomPreset() {
        var name = String(root.preferredPreset || "");
        if (["reading", "work", "cinema"].indexOf(name) !== -1 || name === "" || root.actionPending)
            return ;
        root.request(["preset", "delete", name], "preset-delete");
    }

    function toggleSchedule(enabled) {
        root.issue(["schedule", enabled ? "enable" : "disable"], "schedule-toggle");
    }

    function setSnooze(minutes) {
        root.issue(["snooze", "set", "--minutes", String(minutes)], "snooze");
    }

    function setTransition(seconds) {
        root.transitionSeconds = Math.max(0, Math.min(1800, Number(seconds)));
        root.persistInline({ transitionSeconds: root.transitionSeconds });
        root.issue(["transition-config", "--seconds", String(root.transitionSeconds)], "transition-config");
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
        if (root.helperProcess.running || root.stoppingForLatest || debounce.running) {
            debounce.restart();
        } else {
            debounce.stop();
            root.launchLatest();
        }
    }

    function queueMutation(name, value) {
        if (!stateReady)
            return ;

        if (name === "brightness")
            request(["brightness", String(Math.round(value)), "--monitor", root.selectedMonitor], name);
        else
            request(["nightlight", name, String(Math.round(value))], name);
    }

    function queueSchedule() {
        if (!stateReady || actionPending || !scheduleFieldsValid())
            return ;

        request(["schedule", "set", "--day-time", editStart,
                 "--night-time", editEnd, "--day-temp", editDayTemperature,
                 "--night-temp", editNightTemperature,
                 editNaturalDay ? "--natural-day" : "--no-natural-day"], "schedule");
    }

    function scheduleFieldsValid() {
        return Model.validateScheduleFields(editStart, editEnd, editNaturalDay, editDayTemperature, editNightTemperature).valid;
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

    function consumeStructuredPayload(payload) {
        var data = payload && typeof payload === "object" ? payload : {};
        var changed = false;
        if (data.preflight && typeof data.preflight === "object") {
            root.preflightState = data.preflight;
            root.preflightLoaded = true;
            changed = true;
        }
        if (data.presets && typeof data.presets === "object") {
            root.state = root.mergeCombined(root.state, data);
            root.presetItems = Array.isArray(data.presets.list) ? data.presets.list : [];
            root.presetsLoaded = true;
            changed = true;
        }
        if (Array.isArray(data.history)) {
            root.historyItems = data.history;
            root.state = root.mergeCombined(root.state, data);
            root.historyLoaded = true;
            changed = true;
        }
        if (data.automation && data.automation.last_applied) {
            root.lastAppliedText = root.formatLastApplied(data.automation.last_applied);
            changed = true;
        } else if (data.last_applied) {
            root.lastAppliedText = root.formatLastApplied(data.last_applied);
            changed = true;
        }
        return changed;
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
            return ;
        }
        var payload = null;
        try {
            payload = processOutput === "" ? null : JSON.parse(processOutput);
        } catch (error) {
            payload = null;
        }
        var structured = root.consumeStructuredPayload(payload);
        var responseState = payload && payload.state ? payload.state : payload;
        var result = Model.commitResponse(root.state, {
            "requestId": requestId,
            "latestRequestId": latestRequestId,
            "ok": exitCode === 0 && payload !== null && payload.ok !== false,
            "state": responseState
        });
        if (result.accepted) {
            var previousState = state;
            state = root.mergeCombined(result.state, responseState);
            root.historyItems = Array.isArray(state.history) ? state.history : root.historyItems;
            actionPending = false;
            lastError = root.localizeErrorString(result.state.error);
            if (responseState && responseState.manual_persist_error) {
                lastError = root.text("manualPersistError");
            }
            root.reconcilePending(previousState);
            if (queuedOperation === "schedule") {
                feedbackText = root.text("saved");
                feedbackTimer.restart();
                scheduleExpanded = false;
                scheduleEditorOpen = false;
            }

            return ;
        }
        if (structured && exitCode === 0 && payload && payload.ok !== false) {
            actionPending = false;
            lastError = "";
            return ;
        }
        actionPending = false;
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

    function moveCursor(dx, dy) {
        if (dx !== 0 && stateReady && root.route === "home" && !root.scheduleExpanded) {
            var section = Model.sectionOrder()[cursor.section];
            var confirmed = null;
            if (section === "brightness")
                confirmed = state.brightness.percent;
            else if (section === "temperature")
                confirmed = state.temperature;
            else if (section === "gamma")
                confirmed = state.gamma;
            if (typeof confirmed === "number") {
                var step = Model.keyboardStep(section, dx, confirmed, root.pendingSteps[section]);
                root.pendingSteps[section] = step.pending;
                queueMutation(section, step.value);
            }
        }
        var key = dy > 0 ? "j" : (dy < 0 ? "k" : (dx > 0 ? "l" : "h"));
        var routeJump = Model.navigateCursorRoute(root.route, cursor, key, root.scheduleExpanded);
        if (routeJump && routeJump.route !== root.route) {
            root.navigateToRoute(routeJump.route);
            cursor = Model.cursorStart();
            return ;
        }
        cursor = Model.moveCursor(cursor, key, root.scheduleExpanded);
    }

    function reconcilePending(previous) {
        if (root.route !== "home" || root.scheduleExpanded) {
            root.pendingSteps = { "brightness": 0, "temperature": 0, "gamma": 0 };
            return ;
        }
        var result = Model.reconcilePendingSteps(previous, root.state, root.pendingSteps, root.queuedOperation);
        root.pendingSteps = result.pending;
        for (var i = 0; i < result.requests.length; i++)
            root.queueMutation(result.requests[i].section, result.requests[i].value);
    }

    function handleCloseRequested() {
        if (scheduleExpanded) {
            scheduleExpanded = false;
            scheduleEditorOpen = false;
            keyCatcher.forceActiveFocus();
            return ;
        }
        root.close();
    }

    function leaveScheduleEditor(editor, cursorField) {
        editor.focus = false;
        if (cursorField !== undefined)
            cursor = { "section": 4, "field": cursorField };
        keyCatcher.forceActiveFocus();
    }

    function activateCursor() {
        var section = Model.sectionOrder()[cursor.section];
        if (section === "nightLight") {
            if (stateReady && !actionPending)
                request(["nightlight", "toggle"], "toggle");

            return ;
        }
        if (section === "schedule") {
            if (!scheduleExpanded) {
                if (root.route !== "automation")
                    root.navigateToRoute("automation");
                scheduleExpanded = true;
                scheduleEditorOpen = true;
                editStart = state.schedule.start || "06:00";
                editEnd = state.schedule.end || "15:30";
                editNaturalDay = state.schedule.day_identity === true;
                editDayTemperature = String(state.schedule.day_temp || 6000);
                editNightTemperature = String(state.schedule.night_temp || 3500);
                return ;
            }
            if (cursor.field === 0)
                startEditor.forceActiveFocus();
            else if (cursor.field === 1)
                endEditor.forceActiveFocus();
            else if (cursor.field === 2)
                naturalDayEditor.forceActiveFocus();
            else if (cursor.field === 3)
                dayTemperatureEditor.field.forceActiveFocus();
            else if (cursor.field === 4)
                scheduleTemperatureEditor.field.forceActiveFocus();
            else
                queueSchedule();
        }
    }

    function setScheduleEditorFocus(editor) {
        if (scheduleExpanded)
            editor.forceActiveFocus();

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
            root.toggleNightlight();
        }
    }

    onOpenedChanged: {
        if (opened)
            requestStatus();

    }
    Component.onCompleted: {
        root.locale = String(root.setting("locale", "es"));
        root.applyScope = String(root.setting("applyScope", "session"));
        root.selectedMonitor = String(root.setting("monitor", "focused"));
        root.preferredPreset = String(root.setting("preferredPreset", "reading"));
        root.transitionSeconds = Number(root.setting("transitionSeconds", 8));
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
        contentWidth: keyboardPanel.fittedContentWidth(Style.space(380))
        contentHeight: keyboardPanel.fittedContentHeight(contentColumn.implicitHeight, Style.space(560))

        PanelKeyCatcher {
            id: keyCatcher

            anchors.fill: parent
            blocked: startEditor.activeFocus || endEditor.activeFocus || naturalDayEditor.activeFocus || dayTemperatureEditor.field.activeFocus || scheduleTemperatureEditor.field.activeFocus || transitionEditor.field.activeFocus || shortcutField.activeFocus || customPresetName.activeFocus || monitorSelector.popupOpen || localeSelector.popupOpen || scopeSelector.popupOpen || presetSelector.popupOpen
            onMoveRequested: function(dx, dy) {
                root.moveCursor(dx, dy);
            }
            onActivateRequested: root.activateCursor()
            onCloseRequested: root.handleCloseRequested()
            onTabRequested: function(direction) {
                root.switchPanel(direction);
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

                Row {
                    id: routeNav

                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.leftMargin: Style.spacing.rowPaddingX
                    anchors.rightMargin: Style.spacing.rowPaddingX
                    spacing: Style.spacing.controlGap

                    Button {
                        text: root.text("home")
                        selected: root.route === "home"
                        focusable: true
                        foreground: root.foreground
                        onClicked: root.navigateToRoute("home")
                    }

                    Button {
                        text: root.text("automation")
                        selected: root.route === "automation"
                        focusable: true
                        foreground: root.foreground
                        onClicked: root.navigateToRoute("automation")
                    }

                    Button {
                        text: root.text("settings")
                        selected: root.route === "settings"
                        focusable: true
                        foreground: root.foreground
                        onClicked: root.navigateToRoute("settings")
                    }
                }

                CursorSurface {
                    id: heroSurface

                    visible: root.route === "home" && !root.scheduleExpanded
                    width: parent.width
                    hasCursor: root.cursor.section === 0
                    foreground: root.foreground
                    implicitHeight: hero.implicitHeight + Style.spacing.rowPaddingX

                    PanelHero {
                        id: hero

                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: Style.spacing.rowPaddingX
                        anchors.rightMargin: Style.spacing.rowPaddingX
                        title: root.text("night_light")
                        meta: root.stateReady ? root.heroMeta : root.text("unavailable")
                        foreground: root.foreground
                        fontFamily: root.fontFamily
                        iconOpacity: root.stateReady ? 1 : 0.45

                        iconComponent: Component {
                            Text {
                                id: heroGlyph
                                text: root.heroGlyph
                                color: root.foreground
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
                                foreground: root.foreground
                                Accessible.name: root.text("night_light")
                                onToggled: root.request(["nightlight", "toggle"], "toggle")
                            }

                        }

                    }

                }

                Column {
                    id: homeRoute

                    visible: root.route === "home" && !root.scheduleExpanded
                    width: parent.width
                    spacing: Style.spacing.panelGap

                    BorderSurface {
                        width: parent.width
                        implicitHeight: homeSummary.implicitHeight + Style.spacing.rowPaddingX * 2
                        color: Style.normalFill
                        borderSpec: Border.controlSpec("normal", root.foreground, Color.accent)
                        radius: Style.cornerRadius

                        Column {
                            id: homeSummary
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: Style.spacing.rowPaddingX
                            anchors.rightMargin: Style.spacing.rowPaddingX
                            spacing: Style.spacing.labelGap

                            Text {
                                text: root.text("live_now") + "  ·  " + root.provenanceText
                                color: root.foreground
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                                font.bold: true
                            }

                            Text {
                                text: root.lastAppliedText === "" ? root.text("unknown") : root.lastAppliedText
                                color: Qt.darker(root.foreground, 1.35)
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.bodySmall
                                elide: Text.ElideRight
                            }
                        }
                    }

                    PanelSectionHeader {
                        text: root.text("presets")
                        foreground: root.foreground
                        fontFamily: root.fontFamily
                    }

                    Row {
                        width: parent.width
                        spacing: Style.spacing.controlGap

                        Button {
                            text: root.text("preset_reading")
                            selected: root.preferredPreset === "reading"
                            focusable: true
                            bordered: true
                            foreground: root.foreground
                            enabled: root.stateReady && !root.actionPending
                            onClicked: root.applyPreset("reading")
                        }

                        Button {
                            text: root.text("preset_work")
                            selected: root.preferredPreset === "work"
                            focusable: true
                            bordered: true
                            foreground: root.foreground
                            enabled: root.stateReady && !root.actionPending
                            onClicked: root.applyPreset("work")
                        }

                        Button {
                            text: root.text("preset_cinema")
                            selected: root.preferredPreset === "cinema"
                            focusable: true
                            bordered: true
                            foreground: root.foreground
                            enabled: root.stateReady && !root.actionPending
                            onClicked: root.applyPreset("cinema")
                        }

                        PanelActionButton {
                            iconText: "󰑓"
                            tooltipText: root.text("presets")
                            foreground: root.foreground
                            focusable: true
                            onClicked: root.settingsCommand("preset", ["list"])
                        }
                    }

                    Row {
                        width: parent.width
                        spacing: Style.spacing.controlGap

                        TextField {
                            id: customPresetName
                            width: parent.width - saveCustomPresetButton.implicitWidth - deleteCustomPresetButton.implicitWidth - Style.spacing.controlGap * 2
                            text: root.customPresetName
                            placeholderText: root.text("preset_name")
                            foreground: root.foreground
                            font.family: root.fontFamily
                            onTextChanged: root.customPresetName = text
                            onAccepted: root.saveCustomPreset()
                        }

                        Button {
                            id: saveCustomPresetButton
                            text: root.text("save_current_preset")
                            focusable: true
                            bordered: true
                            foreground: root.foreground
                            enabled: root.stateReady && !root.actionPending && customPresetName.text.trim() !== ""
                            onClicked: root.saveCustomPreset()
                        }

                        Button {
                            id: deleteCustomPresetButton
                            text: root.text("delete_custom_preset")
                            focusable: true
                            bordered: true
                            foreground: root.foreground
                            enabled: root.stateReady && !root.actionPending && ["reading", "work", "cinema"].indexOf(root.preferredPreset) === -1 && root.preferredPreset !== ""
                            onClicked: root.deleteSelectedCustomPreset()
                        }
                    }

                    SearchableDropdown {
                        id: monitorSelector
                        width: parent.width
                        label: root.text("monitor")
                        value: root.selectedMonitor
                        options: root.monitorOptions
                        foreground: root.foreground
                        accent: Color.accent
                        showLabel: true
                        onChanged: function(value) { root.setInlineSetting("monitor", value) }
                    }

                    Button {
                        text: root.text("open_automation")
                        width: parent.width
                        leftAlign: true
                        bordered: true
                        focusable: true
                        foreground: root.foreground
                        onClicked: root.navigateToRoute("automation")
                    }

                    Row {
                        width: parent.width
                        spacing: Style.spacing.controlGap

                        Text {
                            id: lastAppliedLabel
                            text: root.text("last_applied")
                            color: Qt.darker(root.foreground, 1.35)
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.caption
                        }

                        Text {
                            width: parent.width - lastAppliedLabel.implicitWidth - parent.spacing
                            text: root.lastAppliedText === "" ? root.text("unknown") : root.lastAppliedText
                            color: root.foreground
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                            elide: Text.ElideRight
                        }
                    }

                    PanelSectionHeader {
                        text: root.text("history")
                        foreground: root.foreground
                        fontFamily: root.fontFamily
                    }

                    Text {
                        width: parent.width
                        text: root.historyItems.length > 0 ? String(root.historyItems[0].at || root.historyItems[0].origin || root.text("unknown")) : root.text("unknown")
                        color: Qt.darker(root.foreground, 1.35)
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.bodySmall
                        elide: Text.ElideRight
                    }

                    Button {
                        text: root.text("history")
                        width: parent.width
                        leftAlign: true
                        focusable: true
                        bordered: true
                        foreground: root.foreground
                        onClicked: root.settingsCommand("history", ["list"])
                    }
                }

                Column {
                    id: automationRoute

                    visible: root.route === "automation"
                    width: parent.width
                    spacing: Style.spacing.panelGap

                    BorderSurface {
                        width: parent.width
                        implicitHeight: automationHeader.implicitHeight + Style.spacing.rowPaddingX * 2
                        color: Style.normalFill
                        borderSpec: Border.controlSpec("normal", root.foreground, Color.accent)
                        radius: Style.cornerRadius

                        Row {
                            id: automationHeader
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: Style.spacing.rowPaddingX
                            anchors.rightMargin: Style.spacing.rowPaddingX
                            spacing: Style.spacing.controlGap

                            Column {
                                width: parent.width - scheduleToggle.width - Style.spacing.controlGap
                                spacing: Style.spacing.labelGap

                                Text {
                                    text: root.text("schedule")
                                    color: root.foreground
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.title
                                    font.bold: true
                                }

                                Text {
                                    text: root.scheduleEnabled ? root.text("schedule_enabled") : root.text("schedule_disabled")
                                    color: Qt.darker(root.foreground, 1.35)
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.bodySmall
                                }
                            }

                            ToggleSwitch {
                                id: scheduleToggle
                                checked: root.scheduleEnabled
                                busy: !root.automationReady || root.actionPending
                                foreground: root.foreground
                                Accessible.name: root.text("schedule")
                                onToggled: root.toggleSchedule(!root.scheduleEnabled)
                            }
                        }
                    }

                    Text {
                        width: parent.width
                        text: root.text("midnight_explanation")
                        color: Qt.darker(root.foreground, 1.35)
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.bodySmall
                        wrapMode: Text.WordWrap
                    }

                    PanelSectionHeader {
                        text: root.text("transition")
                        foreground: root.foreground
                        fontFamily: root.fontFamily
                    }

                    Row {
                        width: parent.width
                        spacing: Style.spacing.controlGap

                        NumberField {
                            id: transitionEditor
                            width: parent.width - transitionApply.implicitWidth - Style.spacing.controlGap
                            fieldWidth: width
                            value: root.transitionSeconds
                            from: 0
                            to: 1800
                            stepSize: 1
                            foreground: root.foreground
                            fontFamily: root.fontFamily
                            onModified: function(value) { root.transitionSeconds = Number(value) }
                        }

                        Button {
                            id: transitionApply
                            text: root.text("seconds")
                            focusable: true
                            bordered: true
                            foreground: root.foreground
                            enabled: root.stateReady && !root.actionPending
                            onClicked: root.setTransition(root.transitionSeconds)
                        }
                    }

                    PanelSectionHeader {
                        text: root.text("snooze")
                        foreground: root.foreground
                        fontFamily: root.fontFamily
                    }

                    Row {
                        width: parent.width
                        spacing: Style.spacing.controlGap

                        Button {
                            text: root.text("snooze_30")
                            focusable: true
                            bordered: true
                            foreground: root.foreground
                            onClicked: root.setSnooze(30)
                        }

                        Button {
                            text: root.text("snooze_120")
                            focusable: true
                            bordered: true
                            foreground: root.foreground
                            onClicked: root.setSnooze(120)
                        }

                        Button {
                            text: root.text("until_tomorrow")
                            focusable: true
                            bordered: true
                            foreground: root.foreground
                            onClicked: root.settingsCommand("snooze", ["until-tomorrow"])
                        }

                        Button {
                            text: root.text("clear_snooze")
                            focusable: true
                            bordered: true
                            foreground: root.foreground
                            onClicked: root.settingsCommand("snooze", ["clear"])
                        }
                    }

                    Button {
                        text: root.scheduleExpanded ? root.text("cancel") : root.text("edit_schedule")
                        width: parent.width
                        leftAlign: true
                        bordered: true
                        focusable: true
                        foreground: root.foreground
                        enabled: !root.actionPending
                        onClicked: {
                            if (root.scheduleExpanded) {
                                root.scheduleExpanded = false;
                                root.scheduleEditorOpen = false;
                            } else {
                                root.scheduleExpanded = true;
                                root.scheduleEditorOpen = true;
                                root.editStart = root.state.schedule.start || "06:00";
                                root.editEnd = root.state.schedule.end || "15:30";
                                root.editNaturalDay = root.state.schedule.day_identity === true;
                                root.editDayTemperature = String(root.state.schedule.day_temp || 6000);
                                root.editNightTemperature = String(root.state.schedule.night_temp || 3500);
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
                        text: root.text("settings")
                        foreground: root.foreground
                        fontFamily: root.fontFamily
                    }

                    Dropdown {
                        id: localeSelector
                        width: parent.width
                        label: root.text("language")
                        value: root.locale
                        options: [
                            { value: "es", label: root.text("spanish") },
                            { value: "en", label: root.text("english") }
                        ]
                        foreground: root.foreground
                        onChanged: function(value) { root.setInlineSetting("locale", value) }
                    }

                    Dropdown {
                        id: scopeSelector
                        width: parent.width
                        label: root.text("apply_scope")
                        value: root.applyScope
                        options: [
                            { value: "session", label: root.text("session") },
                            { value: "persistent", label: root.text("persistent") }
                        ]
                        foreground: root.foreground
                        onChanged: function(value) { root.setInlineSetting("applyScope", value) }
                    }

                    Dropdown {
                        id: presetSelector
                        width: parent.width
                        label: root.text("default_preset")
                        value: root.preferredPreset
                        options: root.presetOptions
                        foreground: root.foreground
                        onChanged: function(value) {
                            root.preferredPreset = value;
                            root.setInlineSetting("preferredPreset", value);
                            root.settingsCommand("settings", ["set", "--default-preset", value]);
                        }
                    }

                    PanelSectionHeader {
                        text: root.text("preflight")
                        foreground: root.foreground
                        fontFamily: root.fontFamily
                    }

                    Button {
                        text: root.text("run_preflight")
                        width: parent.width
                        leftAlign: true
                        bordered: true
                        focusable: true
                        foreground: root.foreground
                        enabled: !root.actionPending
                        onClicked: root.settingsCommand("preflight", [])
                    }

                    Text {
                        visible: root.preflightLoaded
                        width: parent.width
                        text: root.preflightState.ok === true ? root.text("enabled") : root.text("unavailable")
                        color: root.preflightState.ok === true ? root.foreground : Color.urgent
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.bodySmall
                    }

                    PanelSectionHeader {
                        text: root.text("shortcut")
                        foreground: root.foreground
                        fontFamily: root.fontFamily
                    }

                    TextField {
                        id: shortcutField
                        width: parent.width
                        text: root.shortcutKeys
                        placeholderText: root.text("shortcut_keys")
                        foreground: root.foreground
                        font.family: root.fontFamily
                        onAccepted: root.setInlineSetting("shortcutKeys", text)
                    }

                    Row {
                        width: parent.width
                        spacing: Style.spacing.controlGap

                        Button {
                            text: root.text("install_shortcut")
                            focusable: true
                            bordered: true
                            foreground: root.foreground
                            enabled: !root.actionPending
                            onClicked: {
                                root.setInlineSetting("shortcutKeys", shortcutField.text);
                                root.settingsCommand("shortcut", ["install", "--keys", shortcutField.text]);
                            }
                        }

                        Button {
                            text: root.text("remove_shortcut")
                            focusable: true
                            bordered: true
                            foreground: root.foreground
                            enabled: !root.actionPending
                            onClicked: root.settingsCommand("shortcut", ["remove"])
                        }
                    }
                }

                Text {
                    visible: root.errorText !== ""
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.leftMargin: Style.spacing.rowPaddingX
                    anchors.rightMargin: Style.spacing.rowPaddingX
                    text: root.errorText
                    color: Color.urgent
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.WordWrap
                }

                Text {
                    visible: root.feedbackText !== ""
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.leftMargin: Style.spacing.rowPaddingX
                    anchors.rightMargin: Style.spacing.rowPaddingX
                    text: root.feedbackText
                    color: root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.WordWrap
                }

                PanelSeparator {
                    visible: root.route === "home" && !root.scheduleExpanded
                    foreground: root.foreground
                }

                Column {
                    visible: root.route === "home" && !root.scheduleExpanded
                    width: parent.width
                    spacing: Style.spacing.labelGap

                    PanelSectionHeader {
                        text: root.text("brightness")
                        foreground: root.foreground
                        fontFamily: root.fontFamily
                    }

                    CursorSurface {
                        width: parent.width
                        hasCursor: root.cursor.section === 1
                        foreground: root.foreground
                        implicitHeight: brightnessRow.implicitHeight + Style.spacing.rowPaddingX

                        Row {
                            id: brightnessRow

                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: Style.spacing.rowPaddingX
                            anchors.rightMargin: Style.spacing.rowPaddingX
                            spacing: Style.spacing.controlGap

                            Text {
                                text: root.stateReady ? root.state.brightness.percent + "%" : "—"
                                color: root.foreground
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.body
                                width: root.valueColumnWidth
                                horizontalAlignment: Text.AlignRight
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            PanelSlider {
                                width: parent.width - root.valueColumnWidth - Style.spacing.controlGap
                                bar: root.bar
                                value: root.state.brightness.percent === null ? 1 : root.state.brightness.percent
                                minimum: 1
                                maximum: 100
                                step: 1
                                integer: true
                                enabled: root.stateReady
                                onMoved: function(v) { root.pendingSteps["brightness"] = 0; root.queueMutation("brightness", v) }
                            }

                        }

                    }

                }

                PanelSeparator {
                    visible: root.route === "home" && !root.scheduleExpanded
                    foreground: root.foreground
                }

                Column {
                    visible: root.route === "home" && !root.scheduleExpanded
                    width: parent.width
                    spacing: Style.spacing.labelGap

                    PanelSectionHeader {
                        text: root.text("temperature")
                        foreground: root.foreground
                        fontFamily: root.fontFamily
                    }

                    CursorSurface {
                        width: parent.width
                        hasCursor: root.cursor.section === 2
                        foreground: root.foreground
                        implicitHeight: temperatureRow.implicitHeight + Style.spacing.rowPaddingX

                        Row {
                            id: temperatureRow

                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: Style.spacing.rowPaddingX
                            anchors.rightMargin: Style.spacing.rowPaddingX
                            spacing: Style.spacing.controlGap

                            Text {
                                text: root.stateReady ? root.state.temperature + " K" : "—"
                                color: root.foreground
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.body
                                width: root.valueColumnWidth
                                horizontalAlignment: Text.AlignRight
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            PanelSlider {
                                width: parent.width - root.valueColumnWidth - Style.spacing.controlGap
                                bar: root.bar
                                value: root.state.temperature === null ? 2500 : root.state.temperature
                                minimum: 2500
                                maximum: 6500
                                step: 100
                                integer: true
                                enabled: root.stateReady
                                onMoved: function(v) { root.pendingSteps["temperature"] = 0; root.queueMutation("temperature", v) }
                            }

                        }

                    }

                }

                PanelSeparator {
                    visible: root.route === "home" && !root.scheduleExpanded
                    foreground: root.foreground
                }

                Column {
                    visible: root.route === "home" && !root.scheduleExpanded
                    width: parent.width
                    spacing: Style.spacing.labelGap

                    PanelSectionHeader {
                        text: root.text("gamma")
                        foreground: root.foreground
                        fontFamily: root.fontFamily
                    }

                    CursorSurface {
                        width: parent.width
                        hasCursor: root.cursor.section === 3
                        foreground: root.foreground
                        implicitHeight: gammaRow.implicitHeight + Style.spacing.rowPaddingX

                        Row {
                            id: gammaRow

                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: Style.spacing.rowPaddingX
                            anchors.rightMargin: Style.spacing.rowPaddingX
                            spacing: Style.spacing.controlGap

                            Text {
                                text: root.stateReady ? root.state.gamma + "%" : "—"
                                color: root.foreground
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.body
                                width: root.valueColumnWidth
                                horizontalAlignment: Text.AlignRight
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            PanelSlider {
                                width: parent.width - root.valueColumnWidth - Style.spacing.controlGap
                                bar: root.bar
                                value: root.state.gamma === null ? 0 : root.state.gamma
                                minimum: 0
                                maximum: 100
                                step: 1
                                integer: true
                                enabled: root.stateReady
                                onMoved: function(v) { root.pendingSteps["gamma"] = 0; root.queueMutation("gamma", v) }
                            }

                        }

                    }

                }

                PanelSeparator {
                    visible: root.route === "home" && !root.scheduleExpanded
                    foreground: root.foreground
                }

                Column {
                    id: scheduleRoute
                    visible: root.route === "automation"
                    width: parent.width
                    spacing: Style.spacing.labelGap

                    PanelSectionHeader {
                        text: root.text("schedule")
                        foreground: root.foreground
                        fontFamily: root.fontFamily
                    }

                    CursorSurface {
                        id: scheduleSurface

                        width: parent.width
                        hasCursor: root.cursor.section === 4
                        foreground: root.foreground
                        implicitHeight: scheduleColumn.implicitHeight + Style.spacing.rowPaddingX

                        Column {
                            id: scheduleColumn

                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: Style.spacing.rowPaddingX
                            anchors.rightMargin: Style.spacing.rowPaddingX
                            spacing: Style.spacing.controlGap

                            Button {
                                visible: !root.scheduleExpanded
                                width: parent.width
                                text: root.stateReady ? ((root.state.schedule.start || "06:00") + "  →  " + (root.state.schedule.end || "15:30") + "  ·  " + (root.state.schedule.temperature || 2500) + " K") : root.text("unavailable")
                                leftAlign: true
                                focusable: true
                                hasCursor: root.cursor.section === 4 && !root.scheduleExpanded
                                foreground: root.foreground
                                enabled: !root.actionPending
                                onClicked: {
                                    root.scheduleExpanded = !root.scheduleExpanded;
                                    if (root.scheduleExpanded) {
                                        root.scheduleEditorOpen = true;
                                        root.editStart = root.state.schedule.start || "06:00";
                                        root.editEnd = root.state.schedule.end || "15:30";
                                        root.editNaturalDay = root.state.schedule.day_identity === true;
                                        root.editDayTemperature = String(root.state.schedule.day_temp || 6000);
                                        root.editNightTemperature = String(root.state.schedule.night_temp || 3500);
                                    } else {
                                        root.scheduleEditorOpen = false;
                                    }
                                }
                            }

                            Column {
                                visible: root.scheduleExpanded
                                width: parent.width
                                spacing: Style.spacing.rowGap

                                Column {
                                    width: parent.width
                                    spacing: Style.spacing.labelGap

                                    Text {
                                        text: root.text("start")
                                        color: root.foreground
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                        width: parent.width
                                    }

                                    TextField {
                                        id: startEditor

                                        width: parent.width
                                        hasCursor: root.cursor.section === 4 && root.cursor.field === 0
                                        foreground: root.foreground
                                        font.family: root.fontFamily
                                        text: root.editStart
                                        inputMask: "99:99"
                                        onTextChanged: root.editStart = text
                                        onAccepted: endEditor.forceActiveFocus()
                                        Keys.onEscapePressed: {
                                            root.leaveScheduleEditor(startEditor);
                                        }
                                    }

                                }

                                Column {
                                    width: parent.width
                                    spacing: Style.spacing.labelGap

                                    Text {
                                        text: root.text("end")
                                        color: root.foreground
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                        width: parent.width
                                    }

                                    TextField {
                                        id: endEditor

                                        width: parent.width
                                        hasCursor: root.cursor.section === 4 && root.cursor.field === 1
                                        foreground: root.foreground
                                        font.family: root.fontFamily
                                        text: root.editEnd
                                        inputMask: "99:99"
                                        onTextChanged: root.editEnd = text
                                        onAccepted: naturalDayEditor.forceActiveFocus()
                                        Keys.onEscapePressed: {
                                            root.leaveScheduleEditor(endEditor);
                                        }
                                    }

                                }

                                Column {
                                    width: parent.width
                                    spacing: Style.spacing.labelGap

                                    Text {
                                        text: root.text("natural_day")
                                        color: root.foreground
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                        width: parent.width
                                    }

                                    ToggleSwitch {
                                        id: naturalDayEditor

                                        checked: root.editNaturalDay
                                        busy: !root.stateReady || root.actionPending
                                        hasCursor: root.cursor.section === 4 && root.cursor.field === 2
                                        foreground: root.foreground
                                        Accessible.name: root.text("natural_day")
                                        onToggled: root.editNaturalDay = !root.editNaturalDay
                                        Keys.onEscapePressed: root.leaveScheduleEditor(naturalDayEditor, 2)
                                        Keys.onReturnPressed: if (!busy) root.editNaturalDay = !root.editNaturalDay
                                        Keys.onEnterPressed: if (!busy) root.editNaturalDay = !root.editNaturalDay
                                        Keys.onSpacePressed: if (!busy) root.editNaturalDay = !root.editNaturalDay
                                    }

                                }

                                Column {
                                    width: parent.width
                                    spacing: Style.spacing.labelGap

                                    Text {
                                        text: root.text("day_temperature")
                                        color: root.foreground
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                        width: parent.width
                                    }

                                    NumberField {
                                        id: dayTemperatureEditor

                                        width: parent.width
                                        fieldWidth: parent.width
                                        hasCursor: root.cursor.section === 4 && root.cursor.field === 3
                                        foreground: root.foreground
                                        fontFamily: root.fontFamily
                                        value: Number(root.editDayTemperature || 6000)
                                        from: 5900
                                        to: 6500
                                        stepSize: 100
                                        onModified: value => root.editDayTemperature = String(value)
                                        field.Keys.priority: Keys.BeforeItem
                                        field.Keys.onPressed: function(event) {
                                            if (event.key === Qt.Key_Escape) {
                                                root.leaveScheduleEditor(dayTemperatureEditor.field, 3);
                                                event.accepted = true;
                                            } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                                root.leaveScheduleEditor(dayTemperatureEditor.field, 4);
                                                event.accepted = true;
                                            }
                                        }
                                    }

                                }

                                Column {
                                    width: parent.width
                                    spacing: Style.spacing.labelGap

                                    Text {
                                        text: root.text("night_temperature")
                                        color: root.foreground
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                        width: parent.width
                                    }

                                    NumberField {
                                        id: scheduleTemperatureEditor

                                        width: parent.width
                                        fieldWidth: parent.width
                                        hasCursor: root.cursor.section === 4 && root.cursor.field === 4
                                        foreground: root.foreground
                                        fontFamily: root.fontFamily
                                        value: Number(root.editNightTemperature || 3500)
                                        from: 2500
                                        to: 5000
                                        stepSize: 100
                                        onModified: value => root.editNightTemperature = String(value)
                                        field.Keys.priority: Keys.BeforeItem
                                        field.Keys.onPressed: function(event) {
                                            if (event.key === Qt.Key_Escape) {
                                                root.leaveScheduleEditor(scheduleTemperatureEditor.field, 4);
                                                event.accepted = true;
                                            } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                                root.leaveScheduleEditor(scheduleTemperatureEditor.field, 5);
                                                event.accepted = true;
                                            }
                                        }
                                    }

                                }

                                Button {
                                    text: root.text("save")
                                    width: parent.width
                                    leftAlign: false
                                    bordered: true
                                    focusable: true
                                    hasCursor: root.cursor.section === 4 && root.cursor.field === 5
                                    foreground: root.foreground
                                    enabled: root.stateReady && !root.actionPending && root.scheduleFieldsValid()
                                    onClicked: root.queueSchedule()
                                }

                            }

                        }

                        MouseArea {
                            anchors.fill: parent
                            enabled: !root.scheduleExpanded
                            onClicked: root.activateCursor()
                        }

                    }

                }

            }

        }

    }

}
