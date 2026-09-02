import QtQuick
import qs.Commons

Text {
    id: root

    property string glyph: ""
    property color iconColor: Color.foreground
    property real iconSize: Style.font.icon
    property string fontFamily: Style.font.family

    text: glyph

    font.family: fontFamily
    font.pixelSize: iconSize

    color: iconColor

    width: Math.max(implicitWidth, iconSize)
    height: Math.max(implicitHeight, iconSize)

    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
    renderType: Text.NativeRendering

    Behavior on color {
        ColorAnimation {
            duration: 160
            easing.type: Easing.OutCubic
        }
    }
}
