import QtQuick
import qs.Commons
import qs.Ui

BarWidget {
    id: root

    readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false
    readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false

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
        text: "☾"
        active: root.opened
        tooltipText: "Luz nocturna"
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
