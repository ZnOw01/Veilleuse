import QtQuick
import "I18n.js" as I18n
import "Icons.js" as Icons
import qs.Commons
import qs.Ui

BarWidget {
    id: root

    readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false
    readonly property bool lightActive: panelLoader.item ? panelLoader.item.stateReady === true && panelLoader.item.state.enabled === true : false
    readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false
    readonly property var liveState: panelLoader.item ? panelLoader.item.state : ({})
    readonly property string barGlyph: root.glyphForState(root.liveState)
    readonly property string barTooltip: root.tooltipForState(root.liveState)

    function glyphForState(value) {
        return Icons.glyphForState(value);
    }

    function tooltipForState(value) {
        var state = value || {};
        var automation = state.automation || {};
        var origin = automation.origin ? String(automation.origin) : "unknown";
        var provenance = I18n.t("origin_" + origin, panelLoader.item ? panelLoader.item.locale : "en");
        if (automation.snoozed === true) {
            var until = Number(automation.snooze_until);
            var remaining = isFinite(until) && until > 0 ? Math.max(1, Math.ceil((until - Date.now() / 1000) / 60)) : 0;
            var minText = I18n.t("minutes_short", panelLoader.item ? panelLoader.item.locale : "en");
            var snoozeText = I18n.t("snooze_active", panelLoader.item ? panelLoader.item.locale : "en");
            return snoozeText + (remaining > 0 ? " (" + remaining + " " + minText + ")" : "") + " · " + provenance;
        }
        var title = I18n.t("night_light", panelLoader.item ? panelLoader.item.locale : "en");
        if (state.available !== true) return title;
        if (state.enabled === true && state.temperature) {
            return title + ": " + state.temperature + " K · " + provenance;
        }
        return title + " · " + provenance;
    }

    function injectPanel() {
        var panel = panelLoader.item;
        if (!panel)
            return ;

        if ("bar" in panel)
            panel.bar = root.bar;

        if ("settings" in panel)
            panel.settings = root.settings;

        if ("anchorItem" in panel)
            panel.anchorItem = button;

    }

    function open() {
        if (panelLoader.item)
            panelLoader.item.open();

    }

    function close() {
        if (panelLoader.item)
            panelLoader.item.close();

    }

    function toggle() {
        if (panelLoader.item)
            panelLoader.item.toggle();

    }

    function closeForPopoutSwitch() {
        if (panelLoader.item)
            panelLoader.item.closeForPopoutSwitch();

    }

    moduleName: "io.github.znow01.veilleuse"
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    onBarChanged: injectPanel()
    onSettingsChanged: injectPanel()

    Loader {
        id: panelLoader

        active: true
        source: Qt.resolvedUrl("Panel.qml")
        visible: false
        onLoaded: {
            root.injectPanel();
            Qt.callLater(root.injectPanel);
        }
    }

    BarIconButton {
        id: button

        anchors.fill: parent
        bar: root.bar
        text: root.barGlyph
        active: root.lightActive
        tooltipText: root.barTooltip
        onPressed: function(buttonCode) {
            if (buttonCode === Qt.RightButton) {
                if (panelLoader.item)
                    panelLoader.item.requestStatus();

                return ;
            }
            if (buttonCode === Qt.MiddleButton) {
                if (panelLoader.item)
                    panelLoader.item.close();

                return ;
            }
            root.toggle();
        }
    }

}
