#!/usr/bin/python3
import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))
spec = importlib.util.spec_from_file_location(
    "veilleuse_cli", ROOT / "bin/veilleuse",
    loader=SourceFileLoader("veilleuse_cli", str(ROOT / "bin/veilleuse")),
)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
import veilleuse


@dataclass(frozen=True)
class BState:
    available: bool
    percent: int | None
    monitor: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class NState:
    available: bool
    enabled: bool | None
    temperature: int | None
    identity: bool | None
    gamma: int | None
    error: str | None = None


class Brightness:
    def __init__(self):
        self.state = BState(True, 40, "eDP-1")
        self.calls = []

    def read_state(self):
        return self.state

    def set_percent(self, value):
        self.calls.append(("set_percent", value))
        self.state = BState(True, value, "eDP-1")
        return self.state


class NightLight:
    def __init__(self):
        self.state = NState(True, True, 3500, False, 100)
        self.calls = []

    def read_state(self):
        return self.state

    def set_natural(self):
        self.calls.append(("natural",))
        return NState(True, False, None, True, 100)

    def set_temperature(self, value):
        self.calls.append(("temperature", value))
        return NState(True, True, value, False, 100)

    def set_gamma(self, value):
        self.calls.append(("gamma", value))
        return NState(True, True, 3500, False, value)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.backends = veilleuse.BackendBundle(Brightness(), NightLight())

    def test_parser_has_one_operation_and_gui_default(self):
        self.assertEqual(cli.build_parser().parse_args(["--natural"]).natural, True)
        with self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["--natural", "--gamma", "80"])
        self.assertEqual(cli.main(["--natural", "--gamma", "80"], backends=self.backends), 2)

    def test_status_prints_json_from_shared_service(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = cli.main(["--status"], backends=self.backends)

        self.assertEqual(result, 0)
        self.assertEqual(json.loads(stdout.getvalue())["brightness"]["percent"], 40)

    def test_each_mutating_option_uses_the_injected_backend(self):
        cases = (
            (["--toggle"], [("natural",)]),
            (["--natural"], [("natural",)]),
            (["--temperature", "2700"], [("temperature", 2700)]),
            (["--gamma", "80"], [("gamma", 80)]),
            (["--brightness", "72"], [("set_percent", 72)]),
        )
        for argv, expected in cases:
            with self.subTest(argv=argv):
                self.backends = veilleuse.BackendBundle(Brightness(), NightLight())
                self.assertEqual(cli.main(argv, backends=self.backends), 0)
                calls = self.backends.night_light.calls + self.backends.brightness.calls
                self.assertEqual(calls, expected)

    def test_mutating_options_do_not_print_status_json(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = cli.main(["--gamma", "80"], backends=self.backends)

        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue(), "")

    def test_backend_failure_is_actionable_and_returns_one(self):
        self.backends.night_light.state = NState(False, None, None, None, None)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = cli.main(["--toggle"], backends=self.backends)

        self.assertEqual(result, 1)
        self.assertIn("disponible", stderr.getvalue())

    def test_no_operation_launches_gui(self):
        with patch.object(cli, "run_gui", return_value=7) as launch:
            self.assertEqual(cli.main([], backends=self.backends), 7)
        launch.assert_called_once_with()

    def test_desktop_template_names_the_unified_app(self):
        desktop = (ROOT / "data/io.github.ZnOw01.Veilleuse.desktop.in").read_text()
        self.assertIn("Name=Veilleuse", desktop)
        self.assertIn("Icon=io.github.ZnOw01.Veilleuse", desktop)
        self.assertIn("StartupWMClass=io.github.ZnOw01.Veilleuse", desktop)


if __name__ == "__main__":
    unittest.main(verbosity=2)
