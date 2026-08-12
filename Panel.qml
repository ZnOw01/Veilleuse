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
    property string editTemperature: "2500"
    property string lastError: ""
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
                 "--night-time", editEnd, "--day-temp", "6000",
                 "--night-temp", editTemperature, "--natural-day"], "schedule");
    }

    function scheduleFieldsValid() {
        return /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(editStart) && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(editEnd) && /^(?:2500|[2-4]\d{3}|5000)$/.test(editTemperature);
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
            lastError = "";
            if (queuedOperation === "schedule")
                scheduleExpanded = false;

            return ;
        }
        actionPending = false;
        if (queuedOperation === "status")
            state = Model.normalizeState({
        });

        lastError = processError !== "" ? processError : Model.copy.notConfirmed;
    }

    function moveCursor(dx, dy) {
        if (dx !== 0 && stateReady) {
            var section = Model.sectionOrder()[cursor.section];
            if (section === "brightness")
                queueMutation("brightness", state.brightness + dx);
            else if (section === "temperature")
                queueMutation("temperature", state.temperature + dx * 100);
            else if (section === "gamma")
                queueMutation("gamma", state.gamma + dx);
        }
        var key = dy > 0 ? "j" : (dy < 0 ? "k" : (dx > 0 ? "l" : "h"));
        cursor = Model.moveCursor(cursor, key);
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
                editTemperature = String(state.schedule.temperature || 2500);
                return ;
            }
            if (cursor.field === 0)
                startEditor.forceActiveFocus();
            else if (cursor.field === 1)
                endEditor.forceActiveFocus();
            else if (cursor.field === 2)
                scheduleTemperatureEditor.forceActiveFocus();
            else
                queueSchedule();
        }
    }

    function setScheduleEditorFocus(editor) {
        if (scheduleExpanded)
            editor.forceActiveFocus();

    }

    moduleName: "io.github.ZnOw01.veilleuse"
    ipcTarget: "io.github.ZnOw01.veilleuse"
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
            blocked: startEditor.activeFocus || endEditor.activeFocus || scheduleTemperatureEditor.activeFocus
            onMoveRequested: function(dx, dy) {
                root.moveCursor(dx, dy);
            }
            onActivateRequested: root.activateCursor()
            onCloseRequested: root.close()
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
                        meta: root.stateReady ? root.statusText : Model.copy.unavailable
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
                    visible: root.lastError !== ""
                    width: parent.width
                    text: root.lastError
                    color: Color.urgent
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.WordWrap
                }

                PanelSeparator {
                    foreground: root.foreground
                }

                Column {
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
                                text: root.stateReady ? root.state.brightness + "%" : "—"
                                color: root.foreground
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.body
                                width: Style.space(42)
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            PanelSlider {
                                width: parent.width - Style.space(42) - Style.spacing.controlGap
                                bar: root.bar
                                value: root.state.brightness === null ? 1 : root.state.brightness
                                minimum: 1
                                maximum: 100
                                step: 1
                                integer: true
                                enabled: root.stateReady
                                onMoved: root.queueMutation("brightness", value)
                            }

                        }

                    }

                }

                PanelSeparator {
                    foreground: root.foreground
                }

                Column {
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
                                width: Style.space(54)
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            PanelSlider {
                                width: parent.width - Style.space(54) - Style.spacing.controlGap
                                bar: root.bar
                                value: root.state.temperature === null ? 2500 : root.state.temperature
                                minimum: 2500
                                maximum: 5000
                                step: 100
                                integer: true
                                enabled: root.stateReady
                                onMoved: root.queueMutation("temperature", value)
                            }

                        }

                    }

                }

                PanelSeparator {
                    foreground: root.foreground
                }

                Column {
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
                                width: Style.space(42)
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            PanelSlider {
                                width: parent.width - Style.space(42) - Style.spacing.controlGap
                                bar: root.bar
                                value: root.state.gamma === null ? 0 : root.state.gamma
                                minimum: 0
                                maximum: 100
                                step: 1
                                integer: true
                                enabled: root.stateReady
                                onMoved: root.queueMutation("gamma", value)
                            }

                        }

                    }

                }

                PanelSeparator {
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
                                        root.editTemperature = String(root.state.schedule.temperature || 2500);
                                    }
                                }
                            }

                            Column {
                                visible: root.scheduleExpanded
                                width: parent.width
                                spacing: Style.spacing.controlGap

                                Row {
                                    width: parent.width
                                    spacing: Style.spacing.controlGap

                                    Text {
                                        text: Model.copy.start
                                        color: root.foreground
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                        width: Style.space(54)
                                        anchors.verticalCenter: parent.verticalCenter
                                    }

                                    CursorSurface {
                                        width: parent.width - Style.space(54) - Style.spacing.controlGap
                                        hasCursor: root.cursor.section === 4 && root.cursor.field === 0
                                        foreground: root.foreground
                                        implicitHeight: startEditor.implicitHeight + Style.spacing.controlPaddingY * 2

                                        TextInput {
                                            id: startEditor

                                            anchors.fill: parent
                                            anchors.leftMargin: Style.spacing.controlPaddingX
                                            anchors.rightMargin: Style.spacing.controlPaddingX
                                            text: root.editStart
                                            color: root.foreground
                                            selectionColor: Color.accent
                                            font.family: root.fontFamily
                                            font.pixelSize: Style.font.body
                                            inputMask: "99:99"
                                            onTextChanged: root.editStart = text
                                            onAccepted: endEditor.forceActiveFocus()
                                            Keys.onEscapePressed: {
                                                focus = false;
                                                keyCatcher.forceActiveFocus();
                                            }
                                        }

                                    }

                                }

                                Row {
                                    width: parent.width
                                    spacing: Style.spacing.controlGap

                                    Text {
                                        text: Model.copy.end
                                        color: root.foreground
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                        width: Style.space(54)
                                        anchors.verticalCenter: parent.verticalCenter
                                    }

                                    CursorSurface {
                                        width: parent.width - Style.space(54) - Style.spacing.controlGap
                                        hasCursor: root.cursor.section === 4 && root.cursor.field === 1
                                        foreground: root.foreground
                                        implicitHeight: endEditor.implicitHeight + Style.spacing.controlPaddingY * 2

                                        TextInput {
                                            id: endEditor

                                            anchors.fill: parent
                                            anchors.leftMargin: Style.spacing.controlPaddingX
                                            anchors.rightMargin: Style.spacing.controlPaddingX
                                            text: root.editEnd
                                            color: root.foreground
                                            selectionColor: Color.accent
                                            font.family: root.fontFamily
                                            font.pixelSize: Style.font.body
                                            inputMask: "99:99"
                                            onTextChanged: root.editEnd = text
                                            onAccepted: scheduleTemperatureEditor.forceActiveFocus()
                                            Keys.onEscapePressed: {
                                                focus = false;
                                                keyCatcher.forceActiveFocus();
                                            }
                                        }

                                    }

                                }

                                Row {
                                    width: parent.width
                                    spacing: Style.spacing.controlGap

                                    Text {
                                        text: Model.copy.scheduleTemperature
                                        color: root.foreground
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                        width: Style.space(54)
                                        anchors.verticalCenter: parent.verticalCenter
                                    }

                                    CursorSurface {
                                        width: parent.width - Style.space(54) - Style.spacing.controlGap
                                        hasCursor: root.cursor.section === 4 && root.cursor.field === 2
                                        foreground: root.foreground
                                        implicitHeight: scheduleTemperatureEditor.implicitHeight + Style.spacing.controlPaddingY * 2

                                        TextInput {
                                            id: scheduleTemperatureEditor

                                            anchors.fill: parent
                                            anchors.leftMargin: Style.spacing.controlPaddingX
                                            anchors.rightMargin: Style.spacing.controlPaddingX
                                            text: root.editTemperature
                                            color: root.foreground
                                            selectionColor: Color.accent
                                            font.family: root.fontFamily
                                            font.pixelSize: Style.font.body
                                            inputMethodHints: Qt.ImhDigitsOnly
                                            onTextChanged: root.editTemperature = text
                                            onAccepted: {
                                                focus = false;
                                                keyCatcher.forceActiveFocus();
                                            }
                                            Keys.onEscapePressed: {
                                                focus = false;
                                                keyCatcher.forceActiveFocus();
                                            }
                                        }

                                    }

                                }

                                Button {
                                    text: Model.copy.save
                                    focusable: true
                                    hasCursor: root.cursor.section === 4 && root.cursor.field === 3
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
