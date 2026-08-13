import QtQuick
import Quickshell.Io
import "UiModel.js" as Model
import qs.Commons
import qs.Ui

Panel {
    id: root

    property Item anchorItem: null
    property var state: Model.normalizeState({
    })
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
    property string queuedOperation: ""
    property var queuedCommand: []
    property bool stoppingForLatest: false
    property string processOutput: ""
    property string processError: ""
    readonly property color foreground: bar ? bar.foreground : Color.foreground
    readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
    readonly property string helperPath: root.normalizedPath(root.setting("helperPath", ""))
    readonly property bool stateReady: state.available === true
    readonly property string statusText: !stateReady ? Model.copy.unavailable : (state.enabled ? Model.copy.enabled : Model.copy.disabled)
    readonly property string scheduleValidationError: Model.validateScheduleFields(editStart, editEnd, editNaturalDay, editDayTemperature, editNightTemperature).error
    readonly property string errorText: root.lastError !== "" ? root.lastError : (root.scheduleExpanded && root.scheduleValidationError !== "" ? root.scheduleValidationError : String(root.state.error || ""))
    readonly property string periodText: root.stateReady && root.state.schedule.period === "day" ? Model.copy.periodDay : (root.stateReady && root.state.schedule.period === "night" ? Model.copy.periodNight : root.statusText)
    readonly property string heroMeta: root.periodText + (Model.isManualOverride(root.state) ? " · " + Model.copy.manualOverride : "")
    readonly property real valueColumnWidth: Style.space(54)

    function normalizedPath(value) {
        var candidate = String(value || "");
        if (candidate === "")
            candidate = String(Qt.resolvedUrl("scripts/veilleuse-control"));

        if (candidate.indexOf("file://") === 0)
            candidate = decodeURIComponent(candidate.replace(/^file:\/\/\//, "/"));

        return candidate;
    }

    function requestStatus() {
        request(["status"], "status");
    }

    function request(command, operation) {
        latestRequestId += 1;
        queuedRequestId = latestRequestId;
        queuedCommand = [root.helperPath].concat(command);
        queuedOperation = operation;
        actionPending = true;
        lastError = "";
        feedbackText = "";
        debounce.restart();
    }

    function queueMutation(name, value) {
        if (!stateReady)
            return ;

        if (name === "brightness")
            request(["brightness", String(Math.round(value))], name);
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

    function handleExit(exitCode) {
        var requestId = processRequestId;
        if (stoppingForLatest) {
            stoppingForLatest = false;
            Qt.callLater(root.launchLatest);
            return ;
        }
        if (requestId !== latestRequestId) {
            Qt.callLater(root.launchLatest);
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
            state = result.state;
            actionPending = false;
            lastError = result.state.error || "";
            if (queuedOperation === "schedule") {
                feedbackText = Model.copy.saved;
                feedbackTimer.restart();
                scheduleExpanded = false;
            }

            return ;
        }
        actionPending = false;
        if (queuedOperation === "status")
            state = Model.normalizeState({
        });

        var payloadError = payload && payload.error ? String(payload.error) : "";
        var failedState = responseState && typeof responseState === "object" ? Model.normalizeState(responseState) : null;
        lastError = payloadError || (failedState && failedState.error ? failedState.error : "") || processError || Model.copy.notConfirmed;
    }

    function moveCursor(dx, dy) {
        if (dx !== 0 && stateReady) {
            var section = Model.sectionOrder()[cursor.section];
            if (section === "brightness")
                queueMutation("brightness", state.brightness.percent + dx);
            else if (section === "temperature")
                queueMutation("temperature", state.temperature + dx * 100);
            else if (section === "gamma")
                queueMutation("gamma", state.gamma + dx);
        }
        var key = dy > 0 ? "j" : (dy < 0 ? "k" : (dx > 0 ? "l" : "h"));
        cursor = Model.moveCursor(cursor, key, root.scheduleExpanded);
    }

    function handleCloseRequested() {
        if (scheduleExpanded) {
            scheduleExpanded = false;
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
                scheduleExpanded = true;
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
    onOpenedChanged: {
        if (opened)
            requestStatus();

    }
    Component.onCompleted: requestStatus()

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
        id: backgroundStatusTimer

        interval: 30000
        repeat: true
        running: !root.opened
        onTriggered: if (!root.actionPending) root.requestStatus()
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
            blocked: startEditor.activeFocus || endEditor.activeFocus || naturalDayEditor.activeFocus || dayTemperatureEditor.field.activeFocus || scheduleTemperatureEditor.field.activeFocus
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

                CursorSurface {
                    id: heroSurface

                    visible: !root.scheduleExpanded
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
                        title: Model.copy.heroTitle
                        meta: root.stateReady ? root.heroMeta : Model.copy.unavailable
                        foreground: root.foreground
                        fontFamily: root.fontFamily
                        iconOpacity: root.stateReady ? 1 : 0.45

                        iconComponent: Component {
                            Text {
                                text: "☾"
                                color: root.foreground
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.display
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }

                        }

                        trailingControl: Component {
                            ToggleSwitch {
                                checked: root.stateReady && root.state.enabled
                                busy: root.actionPending
                                interactive: root.stateReady && !root.actionPending
                                foreground: root.foreground
                                onToggled: root.request(["nightlight", "toggle"], "toggle")
                            }

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
                    visible: !root.scheduleExpanded
                    foreground: root.foreground
                }

                Column {
                    visible: !root.scheduleExpanded
                    width: parent.width
                    spacing: Style.spacing.labelGap

                    PanelSectionHeader {
                        text: Model.copy.brightness
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
                                onMoved: function(v) { root.queueMutation("brightness", v) }
                            }

                        }

                    }

                }

                PanelSeparator {
                    visible: !root.scheduleExpanded
                    foreground: root.foreground
                }

                Column {
                    visible: !root.scheduleExpanded
                    width: parent.width
                    spacing: Style.spacing.labelGap

                    PanelSectionHeader {
                        text: Model.copy.temperature
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
                                onMoved: function(v) { root.queueMutation("temperature", v) }
                            }

                        }

                    }

                }

                PanelSeparator {
                    visible: !root.scheduleExpanded
                    foreground: root.foreground
                }

                Column {
                    visible: !root.scheduleExpanded
                    width: parent.width
                    spacing: Style.spacing.labelGap

                    PanelSectionHeader {
                        text: Model.copy.gamma
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
                                onMoved: function(v) { root.queueMutation("gamma", v) }
                            }

                        }

                    }

                }

                PanelSeparator {
                    visible: !root.scheduleExpanded
                    foreground: root.foreground
                }

                Column {
                    width: parent.width
                    spacing: Style.spacing.labelGap

                    PanelSectionHeader {
                        text: Model.copy.schedule
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
                                text: root.stateReady ? ((root.state.schedule.start || "06:00") + "  →  " + (root.state.schedule.end || "15:30") + "  ·  " + (root.state.schedule.temperature || 2500) + " K") : Model.copy.unavailable
                                leftAlign: true
                                focusable: true
                                hasCursor: root.cursor.section === 4 && !root.scheduleExpanded
                                foreground: root.foreground
                                enabled: !root.actionPending
                                onClicked: {
                                    root.scheduleExpanded = !root.scheduleExpanded;
                                    if (root.scheduleExpanded) {
                                        root.editStart = root.state.schedule.start || "06:00";
                                        root.editEnd = root.state.schedule.end || "15:30";
                                        root.editNaturalDay = root.state.schedule.day_identity === true;
                                        root.editDayTemperature = String(root.state.schedule.day_temp || 6000);
                                        root.editNightTemperature = String(root.state.schedule.night_temp || 3500);
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
                                        text: Model.copy.start
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
                                        text: Model.copy.end
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
                                        text: Model.copy.naturalDay
                                        color: root.foreground
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                        width: parent.width
                                    }

                                    ToggleSwitch {
                                        id: naturalDayEditor

                                        width: parent.width
                                        checked: root.editNaturalDay
                                        hasCursor: root.cursor.section === 4 && root.cursor.field === 2
                                        foreground: root.foreground
                                        interactive: root.stateReady && !root.actionPending
                                        onToggled: root.editNaturalDay = !root.editNaturalDay
                                        Keys.onEscapePressed: root.leaveScheduleEditor(naturalDayEditor, 2)
                                        Keys.onReturnPressed: root.editNaturalDay = !root.editNaturalDay
                                        Keys.onEnterPressed: root.editNaturalDay = !root.editNaturalDay
                                        Keys.onSpacePressed: root.editNaturalDay = !root.editNaturalDay
                                    }

                                }

                                Column {
                                    width: parent.width
                                    spacing: Style.spacing.labelGap

                                    Text {
                                        text: Model.copy.scheduleDayTemperature
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
                                        text: Model.copy.scheduleTemperature
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
                                    text: Model.copy.save
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
