import QtQuick
import qs.Commons

Text {
    id: root

    property string glyph: ""
    property color iconColor: Color.foreground
    property real iconSize: Style.font.icon
    property string fontFamily: "monospace"

    text: glyph

    font.family: fontFamily
    font.pixelSize: iconSize

    color: iconColor

    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
    renderType: Text.NativeRendering
}
