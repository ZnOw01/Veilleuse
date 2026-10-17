import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
QML_RUNNER = shutil.which("qmltestrunner6")
if QML_RUNNER is None and Path("/usr/lib/qt6/bin/qmltestrunner").is_file():
    QML_RUNNER = "/usr/lib/qt6/bin/qmltestrunner"


@unittest.skipUnless(QML_RUNNER, "Qt 6 qmltestrunner is not installed")
class DiagnosticTextSafetyTests(unittest.TestCase):
    def test_diagnostics_render_markup_literally_in_qt(self):
        panel = (ROOT / "Panel.qml").read_text(encoding="utf-8")
        blocks = re.findall(r"(?m)^([ \t]*)Text\s*\{([\s\S]*?)^\1\}", panel)
        fields = ("errorText", "scheduleValidationError", "feedbackText")
        sinks = []
        for field in fields:
            matches = [body for _, body in blocks if re.search(rf"\btext:\s*root\.{field}\s*$", body, re.M)]
            self.assertTrue(matches, f"No diagnostic text found for {field}")
            for body in matches:
                bindings = re.findall(r"^\s*(?:text|textFormat|wrapMode):[^\n]*", body, re.M)
                sinks.append("\n".join(bindings))

        items = "\n".join(
            f"Text {{ id: sink{index}; width: 10000; font.pixelSize: 14; {bindings}\n}}"
            for index, bindings in enumerate(sinks)
        )
        names = ", ".join(f"sink{index}" for index in range(len(sinks)))
        qml = f'''import QtQuick
import QtTest

Item {{
    id: root
    width: 640
    height: 100
    property string errorText: ""
    property string scheduleValidationError: ""
    property string feedbackText: ""
    property var diagnostics: [{names}]
    {items}
    Text {{
        id: literal
        width: 10000
        font.pixelSize: 14
        textFormat: Text.PlainText
        text: root.errorText
    }}
    TestCase {{
        name: "DiagnosticTextSafety"
        when: windowShown
        function test_literal_data() {{
            return [
                {{ tag: "bold", value: "<b>backend failure</b>" }},
                {{ tag: "entities", value: "&lt;literal&gt; &amp; details" }},
                {{ tag: "link", value: '<a href="file:///not-a-real-target">details</a>' }},
                {{ tag: "image", value: '<img src="file:///not-a-real-image.png"> failure' }},
                {{ tag: "spanish", value: "No se pudo leer <i>el estado</i>." }}
            ];
        }}
        function test_literal(data) {{
            root.errorText = data.value;
            root.scheduleValidationError = data.value;
            root.feedbackText = data.value;
            for (const diagnostic of root.diagnostics) {{
                compare(diagnostic.text, data.value);
                compare(diagnostic.textFormat, Text.PlainText);
                tryCompare(diagnostic, "contentWidth", literal.contentWidth);
            }}
        }}
    }}
}}
'''
        with tempfile.TemporaryDirectory(prefix="veilleuse-qml-text-") as directory:
            path = Path(directory) / "tst_diagnostics.qml"
            path.write_text(qml, encoding="utf-8")
            environment = {
                **os.environ,
                "QT_QPA_PLATFORM": "offscreen",
                "QT_QUICK_BACKEND": "software",
                "QSG_RHI_BACKEND": "software",
                "QT_LOGGING_TO_CONSOLE": "1",
                "QT_FORCE_STDERR_LOGGING": "1",
            }
            result = subprocess.run(
                [QML_RUNNER, "-input", str(path), "-o", "-,txt"],
                capture_output=True,
                text=True,
                env=environment,
                timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
