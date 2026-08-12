#!/usr/bin/python3
import importlib.util
import datetime
import stat
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

MODULE_PATH = Path(__file__).parents[1] / "src/night_light_control.py"
spec = importlib.util.spec_from_file_location("night_light_control", MODULE_PATH)
night_light = importlib.util.module_from_spec(spec)
spec.loader.exec_module(night_light)


class ClockValidationTests(unittest.TestCase):
    def test_normalizes_valid_clock(self):
        self.assertEqual(night_light.normalize_clock("7:05"), "07:05")
        self.assertEqual(night_light.normalize_clock("23:59"), "23:59")

    def test_rejects_invalid_clock(self):
        for value in ("24:00", "12:60", "noon", "", "7"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    night_light.normalize_clock(value)


class TemperatureCopyTests(unittest.TestCase):
    def test_gamma_copy_is_perceived_brightness_and_warns_about_color_accuracy(self):
        self.assertIn("percibido", night_light.gamma_description(75).lower())
        self.assertIn("precisión del color", night_light.GAMMA_WARNING)
        self.assertNotIn("luz azul", night_light.gamma_description(75).lower())

    def test_gamma_ui_is_separate_and_accessible(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("Brillo percibido", source)
        self.assertIn("Puede reducir la precisión del color.", source)
        self.assertIn("GAMMA_UI_MIN", source)
        self.assertIn("GAMMA_UI_MAX", source)
        self.assertIn("set_range(self.gamma_scale", source)

    def test_describes_each_temperature_range(self):
        self.assertIn("cálido", night_light.temperature_description(2800))
        self.assertIn("descansar", night_light.temperature_description(3500))
        self.assertIn("leer", night_light.temperature_description(4200))
        self.assertIn("natural", night_light.temperature_description(4800))

    def test_identity_is_authoritative_for_display_and_intensity(self):
        state = night_light.BackendState(True, False, True, 3500)

        self.assertEqual(night_light.state_temperature(state), night_light.DAY_TEMP)
        self.assertEqual(night_light.state_filter_intensity(state), 0)

    def test_natural_color_copy_does_not_expose_internal_identity_name(self):
        copy = night_light.temperature_description(3500, identity=True)
        self.assertNotIn("identity", copy.lower())
        self.assertIn("natural", copy.lower())

    def test_relative_intensity_is_labeled_scale_not_physical_measurement(self):
        self.assertEqual(night_light.relative_filter_intensity(2500), 100)
        self.assertEqual(night_light.relative_filter_intensity(3750), 50)
        self.assertEqual(night_light.relative_filter_intensity(5000), 0)
        self.assertEqual(night_light.relative_filter_intensity(2500, identity=True), 0)

    def test_selected_filter_display_uses_selected_temperature_metric(self):
        display = night_light.selected_filter_display(2500)
        self.assertEqual(display["temperature"], 2500)
        self.assertEqual(display["intensity"], 100)
        self.assertEqual(display["fraction"], 1.0)
        self.assertEqual(display["label"], "100%")

    def test_user_facing_copy_has_no_debug_or_preset_strings(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        ui_lines = tuple(
            line for line in source.splitlines()
            if any(token in line for token in (
                "label=", "title=", "subtitle=", "set_label(", "set_subtitle(",
            ))
        )
        forbidden = (
            "identity", "medición física", "no sustituye", "Tu luz, a tu ritmo",
            "Noche · 2700 K", "Ámbar · 3100 K", "Equilibrio · 3500 K",
            "Lectura · 4200 K", "Suave · 4800 K",
        )
        for text in forbidden:
            self.assertNotIn(text.lower(), "\n".join(ui_lines).lower())
        self.assertNotIn("Gtk.ToggleButton", source)
        self.assertNotIn("sync_presets", source)
        self.assertNotIn("on_preset", source)

    def test_visible_copy_avoids_implementation_details_and_dead_state(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        for text in (
            "Actualiza el archivo de forma atómica",
            "Horario guardado de forma atómica.",
            "No se pudo leer hyprsunset",
            "self.selected_intensity",
        ):
            self.assertNotIn(text, source)
        self.assertIn("Guarda los cambios y aplica el perfil si procede", source)
        self.assertIn("Horario guardado correctamente.", source)
        self.assertIn("No se pudo comprobar el servicio", source)


class UserFacingErrorTests(unittest.TestCase):
    SECRET = "/secret/module.py: command failed"

    def assert_safe_error(self, outcome):
        self.assertFalse(outcome.confirmed)
        self.assertNotIn(self.SECRET, outcome.message)
        self.assertNotIn("module.py", outcome.message)
        self.assertNotIn("command", outcome.message)

    def test_refresh_worker_hides_exception_details(self):
        window = SimpleNamespace()
        with patch.object(night_light, "read_state", side_effect=RuntimeError(self.SECRET)):
            self.assert_safe_error(night_light.NightLightWindow._refresh_worker(window))

    def test_bootstrap_worker_hides_exception_details(self):
        window = SimpleNamespace()
        with (
            patch.object(
                night_light, "load_schedule_config",
                return_value=(night_light.default_schedule(), False, ""),
            ),
            patch.object(night_light, "load_settings", side_effect=ValueError(self.SECRET)),
        ):
            self.assert_safe_error(night_light.NightLightWindow._bootstrap_worker(window))

    def test_settings_worker_hides_exception_details(self):
        window = SimpleNamespace(
            _settings_write_lock=threading.Lock(),
            _settings_generation=1,
        )
        with patch.object(night_light, "save_settings", side_effect=OSError(self.SECRET)):
            self.assert_safe_error(
                night_light.NightLightWindow._settings_worker(window, 3500, 1)
            )

    def test_schedule_save_worker_hides_exception_details(self):
        with patch.object(night_light, "write_schedule", side_effect=OSError(self.SECRET)):
            self.assert_safe_error(
                night_light._save_schedule_worker(night_light.default_schedule())
            )

    def test_start_worker_uses_fixed_error_copy(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn('message=f"Operación fallida: {error}"', source)
        self.assertIn("No se pudo completar la operación. Inténtalo de nuevo.", source)


class ScheduleFormValidationTests(unittest.TestCase):
    def test_validates_and_normalizes_form_values(self):
        self.assertEqual(
            night_light.validate_schedule_values("6:05", "23:10", 3300, 6200),
            {
                "night_time": "06:05",
                "night_temp": 3300,
                "day_time": "23:10",
                "day_temp": 6200,
            },
        )

    def test_rejects_equal_times_and_out_of_range_temperatures(self):
        with self.assertRaisesRegex(ValueError, "diferentes"):
            night_light.validate_schedule_values("06:00", "6:00", 3500, 6000)
        with self.assertRaises(ValueError):
            night_light.validate_schedule_values("06:00", "18:00", 2400, 6000)


class BackendOperationTests(unittest.TestCase):
    def test_legacy_backend_state_keeps_tuple_shape_for_callers(self):
        with patch.object(
            night_light, "read_backend_state",
            return_value=night_light.BackendState(True, False, True, 3500),
        ):
            self.assertEqual(night_light.backend_state(), (False, night_light.DAY_TEMP))

    def test_confirmed_result_requires_successful_readback_result(self):
        self.assertTrue(night_light.operation_confirmed(SimpleNamespace(returncode=0)))
        self.assertFalse(night_light.operation_confirmed(SimpleNamespace(returncode=1)))
        self.assertFalse(night_light.operation_confirmed(None))

    def test_day_identity_profile_never_requests_6000_kelvin(self):
        schedule = {
            "day_time": "06:00",
            "day_temp": 6000,
            "night_time": "15:30",
            "night_temp": 3500,
        }
        with (
            patch.object(night_light, "set_identity", return_value=SimpleNamespace(returncode=0)) as identity,
            patch.object(night_light, "set_temperature", return_value=SimpleNamespace(returncode=0)) as temperature,
        ):
            result = night_light.apply_scheduled_profile(schedule, True, datetime.time(9, 0))

        self.assertTrue(night_light.operation_confirmed(result))
        identity.assert_called_once_with()
        temperature.assert_not_called()

    def test_gamma_worker_uses_shared_lock_and_readback(self):
        state = night_light.BackendState(True, True, False, 3500, 75)
        with (
            patch.object(night_light, "exclusive_lock") as lock,
            patch.object(night_light, "ensure_backend", return_value=state),
            patch.object(night_light, "set_gamma", return_value=SimpleNamespace(returncode=0)) as setter,
        ):
            result = night_light._apply_gamma_worker(75)

        self.assertTrue(result.confirmed)
        setter.assert_called_once_with(75)
        lock.assert_called_once_with(night_light.STATE_LOCK)

    def test_temperature_worker_reports_confirmed_backend_operation_without_hardware(self):
        state = night_light.BackendState(True, True, False, 3500)
        with (
            patch.object(night_light, "exclusive_lock") as lock,
            patch.object(night_light, "ensure_backend", return_value=state),
            patch.object(night_light, "set_temperature", return_value=SimpleNamespace(returncode=0)) as setter,
        ):
            result = night_light._apply_temperature_worker(3500)

        self.assertTrue(result.confirmed)
        setter.assert_called_once_with(3500)
        lock.assert_called_once_with(night_light.STATE_LOCK)

    def test_schedule_worker_applies_identity_without_temperature_request(self):
        schedule = {
            "day_time": "06:00",
            "day_temp": 6000,
            "night_time": "15:30",
            "night_temp": 3500,
        }
        state = night_light.BackendState(True, False, True, 3500)
        with (
            patch.object(night_light, "exclusive_lock") as lock,
            patch.object(night_light, "ensure_backend", return_value=state),
            patch.object(night_light, "schedule_period", return_value="day"),
            patch.object(night_light, "set_identity", return_value=SimpleNamespace(returncode=0)) as identity,
            patch.object(night_light, "set_temperature", return_value=SimpleNamespace(returncode=0)) as temperature,
        ):
            result = night_light._apply_schedule_worker(schedule, True)

        self.assertTrue(result.confirmed)
        identity.assert_called_once_with()
        temperature.assert_not_called()
        lock.assert_called_once_with(night_light.STATE_LOCK)


class GammaSettingsTests(unittest.TestCase):
    def test_gamma_preference_is_separate_and_clamped_to_ui_range(self):
        with tempfile.TemporaryDirectory(prefix="night-light-gamma-test-") as td:
            path = Path(td) / "gamma.json"
            path.write_text('{"gamma": 25}', encoding="utf-8")
            self.assertEqual(night_light.load_gamma(path), night_light.GAMMA_UI_MIN)
            path.write_text('{"gamma": 150}', encoding="utf-8")
            self.assertEqual(night_light.load_gamma(path), night_light.GAMMA_UI_MAX)

    def test_gamma_preference_does_not_write_temperature_settings(self):
        with tempfile.TemporaryDirectory(prefix="night-light-gamma-test-") as td:
            path = Path(td) / "gamma.json"
            temperature_path = Path(td) / "settings.json"
            original_path = night_light.GAMMA_SETTINGS_PATH
            original_lock = night_light.STATE_LOCK
            try:
                night_light.GAMMA_SETTINGS_PATH = path
                night_light.STATE_LOCK = Path(td) / "state.lock"
                night_light.save_gamma(75)
            finally:
                night_light.GAMMA_SETTINGS_PATH = original_path
                night_light.STATE_LOCK = original_lock
            self.assertEqual(path.read_text(encoding="utf-8"), '{\n  "gamma": 75\n}\n')
            self.assertFalse(temperature_path.exists())


class ScheduleConfigTests(unittest.TestCase):
    def test_schedule_loader_reports_malformed_config_without_hiding_it(self):
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            path = Path(td) / "hyprsunset.conf"
            path.write_text("profile { time = 99:99 temperature = 3500 }", encoding="utf-8")
            schedule, identity, error = night_light.load_schedule_config(path)

        self.assertEqual(schedule, night_light.default_schedule())
        self.assertFalse(identity)
        self.assertIn("No se pudo validar", error)

    def test_invalid_schedule_repair_preserves_custom_content(self):
        existing = """# Keep this directive and comment
max-gamma = 150
profile {
    time = 99:99
    temperature = 6200
}
profile {
    time = 15:30
    temperature = 3500
}
profile {
    # custom profile must survive untouched
    time = 22:00
    temperature = 3200
}
"""
        schedule = {
            "day_time": "07:00", "day_temp": 6100,
            "night_time": "18:00", "night_temp": 3300,
        }
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            path = Path(td) / "hyprsunset.conf"
            path.write_text(existing, encoding="utf-8")
            with patch.object(night_light, "STATE_LOCK", Path(td) / "state.lock"):
                night_light.write_schedule(path, schedule, repair_invalid=True)
            written = path.read_text(encoding="utf-8")
            repaired, _identity, repaired_error = night_light.load_schedule_config(path)

        self.assertEqual(repaired, schedule)
        self.assertEqual(repaired_error, "")
        self.assertIn("# Keep this directive and comment", written)
        self.assertIn("max-gamma = 150", written)
        self.assertIn("# custom profile must survive untouched", written)
        self.assertIn("time = 22:00", written)
        self.assertIn("temperature = 3200", written)

    def test_unrepairable_schedule_is_not_overwritten(self):
        original = "max-gamma = 150\nprofile {\n    time = 06:00\n"
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            path = Path(td) / "hyprsunset.conf"
            path.write_text(original, encoding="utf-8")
            with patch.object(night_light, "STATE_LOCK", Path(td) / "state.lock"):
                with self.assertRaisesRegex(ValueError, "No se puede reparar"):
                    night_light.write_schedule(
                        path,
                        night_light.default_schedule(),
                        repair_invalid=True,
                    )
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertFalse(path.with_suffix(".conf.bak").exists())

    def test_read_schedule_falls_back_when_config_is_malformed(self):
        original_path = night_light.HYPRSUNSET_CONFIG
        try:
            with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
                path = Path(td) / "hyprsunset.conf"
                path.write_text("profile { time = 99:99 temperature = 3500 }\n")
                night_light.HYPRSUNSET_CONFIG = path
                self.assertEqual(night_light.read_schedule(), ("15:30", "06:00", 3500))
        finally:
            night_light.HYPRSUNSET_CONFIG = original_path

    def test_parses_day_and_night_profiles(self):
        text = """
profile {
    time = 06:15
    temperature = 6100
}
profile {
    time = 16:45
    temperature = 3200
}
"""
        schedule = night_light.parse_schedule_text(text)
        self.assertEqual(schedule, {
            "day_time": "06:15",
            "day_temp": 6100,
            "night_time": "16:45",
            "night_temp": 3200,
        })

    def test_ignores_comments_and_identity_false_profiles(self):
        text = """
# profile {
#     time = 01:00
#     temperature = 6400
# }
profile {
    time = 06:15
    identity = false
    temperature = 6100
}
profile {
    time = 16:45
    temperature = 3200
}
"""
        schedule = night_light.parse_schedule_text(text)
        self.assertEqual(schedule["day_time"], "06:15")
        self.assertEqual(schedule["night_time"], "16:45")

    def test_identity_profile_is_a_natural_day_profile(self):
        schedule = night_light.parse_schedule_text("""
profile {
    time = 06:00
    identity = true
}
profile {
    time = 15:30
    temperature = 3500
}
""")
        self.assertEqual(schedule["day_time"], "06:00")
        self.assertEqual(schedule["day_temp"], 6000)
        self.assertEqual(schedule["night_time"], "15:30")

    def test_updates_signed_temperatures_and_preserves_crlf_comments(self):
        existing = (
            "profile {\r\n"
            "    time = 06:00\r\n"
            "    temperature = +6200 # day\r\n"
            "}\r\n"
            "profile {\r\n"
            "    time = 15:30\r\n"
            "    temperature = -100 # night\r\n"
            "}\r\n"
        )
        updated = night_light.update_schedule_text(existing, {
            "day_time": "07:00", "day_temp": 6100,
            "night_time": "18:00", "night_temp": 3300,
        })

        self.assertIn("temperature = 6100 # day\r\n", updated)
        self.assertIn("temperature = 3300 # night\r\n", updated)
        self.assertNotIn("+6200", updated)
        self.assertNotIn("-100", updated)
        self.assertEqual(night_light.parse_schedule_text(updated), {
            "day_time": "07:00", "day_temp": 6100,
            "night_time": "18:00", "night_temp": 3300,
        })

    def test_updating_identity_profile_honors_requested_day_temperature(self):
        existing = """profile {
    time = 06:00
    identity = true # natural color
}
profile {
    time = 15:30
    temperature = 3500
}
"""
        updated = night_light.update_schedule_text(existing, {
            "day_time": "07:00", "day_temp": 6200,
            "night_time": "18:00", "night_temp": 3300,
        })
        self.assertNotIn("identity = true", updated)
        self.assertIn("temperature = 6200", updated)
        self.assertEqual(night_light.parse_schedule_text(updated)["day_time"], "07:00")

    def test_updating_profile_removes_identity_when_temperature_is_present(self):
        updated = night_light.update_schedule_text("""profile {
    time = 06:00
    identity = true
    temperature = 6000
}
profile {
    time = 15:30
    temperature = 3500
}
""", {
            "day_time": "07:00", "day_temp": 6200,
            "night_time": "18:00", "night_temp": 3300,
        })
        self.assertNotIn("identity", updated)
        self.assertIn("temperature = 6200", updated)

    def test_schedule_period_handles_midnight(self):
        schedule = {
            "day_time": "06:00", "day_temp": 6000,
            "night_time": "15:30", "night_temp": 3500,
        }
        self.assertEqual(
            night_light.schedule_period(schedule, datetime.time(23, 0)), "night"
        )
        self.assertEqual(
            night_light.schedule_period(schedule, datetime.time(9, 0)), "day"
        )

    def test_parsed_schedule_clamps_temperatures_to_ui_ranges(self):
        text = """
profile {
    time = 06:00
    temperature = 99999
}
profile {
    time = 15:30
    temperature = 100
}
"""
        schedule = night_light.parse_schedule_text(text)
        self.assertEqual(schedule["day_temp"], 6500)
        self.assertEqual(schedule["night_temp"], 2500)

    def test_renders_round_trip_schedule(self):
        expected = {
            "day_time": "07:00",
            "day_temp": 6000,
            "night_time": "18:30",
            "night_temp": 2900,
        }
        rendered = night_light.render_schedule(expected)
        self.assertEqual(night_light.parse_schedule_text(rendered), expected)
        self.assertIn("Generated by Night Light Control", rendered)

    def test_renders_identity_profile_without_day_temperature(self):
        schedule = {
            "day_time": "07:00",
            "day_temp": 6200,
            "night_time": "18:30",
            "night_temp": 2900,
        }
        rendered = night_light.render_schedule(schedule, True)
        day_profile = next(
            profile
            for _start, _end, profile in night_light.iter_profile_blocks(rendered)
            if night_light.profile_kind(night_light.profile_info(profile)) == "day"
        )

        self.assertIn("identity = true", day_profile)
        self.assertIsNone(night_light.profile_info(day_profile)["temperature"])
        self.assertEqual(night_light.parse_schedule_text(rendered)["day_time"], "07:00")

    def test_writes_identity_profile_without_editing_custom_profile(self):
        existing = """# Keep this comment
profile {
    time = 06:00
    temperature = 6000
}
profile {
    time = 15:30
    temperature = 3500
}
profile {
    # custom profile must survive untouched
    time = 22:00
    temperature = 3200
}
"""
        schedule = {
            "day_time": "07:00",
            "day_temp": 6200,
            "night_time": "18:30",
            "night_temp": 2900,
        }
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            path = Path(td) / "hyprsunset.conf"
            path.write_text(existing, encoding="utf-8")
            with patch.object(night_light, "STATE_LOCK", Path(td) / "state.lock"):
                night_light.write_schedule(path, schedule, True)
            written = path.read_text(encoding="utf-8")

        day_profile = next(
            profile
            for _start, _end, profile in night_light.iter_profile_blocks(written)
            if night_light.profile_kind(night_light.profile_info(profile)) == "day"
        )
        custom_profile = next(
            profile
            for _start, _end, profile in night_light.iter_profile_blocks(written)
            if "time = 22:00" in profile
        )
        self.assertEqual(night_light.profile_info(day_profile)["identity"], True)
        self.assertIsNone(night_light.profile_info(day_profile)["temperature"])
        self.assertIn("# custom profile must survive untouched", custom_profile)
        self.assertIn("temperature = 3200", custom_profile)

    def test_updates_schedule_without_deleting_custom_content(self):
        existing = """# Keep this comment
max-gamma = 150
profile {
    time = 06:00
    temperature = 6000
}
profile {
    time = 15:30
    temperature = 3500
}
profile {
    # custom profile must survive untouched
    time = 22:00
    temperature = 3200
}
"""
        updated = night_light.update_schedule_text(existing, {
            "day_time": "07:15", "day_temp": 6200,
            "night_time": "17:45", "night_temp": 3300,
        })
        self.assertIn("# Keep this comment", updated)
        self.assertIn("max-gamma = 150", updated)
        self.assertIn("# custom profile must survive untouched", updated)
        self.assertIn("time = 22:00", updated)
        self.assertIn("temperature = 3200", updated)
        self.assertIn("time = 07:15", updated)
        self.assertIn("temperature = 6200", updated)
        self.assertIn("time = 17:45", updated)
        self.assertIn("temperature = 3300", updated)
        parsed = night_light.parse_schedule_text(updated)
        self.assertEqual(parsed["day_time"], "07:15")
        self.assertEqual(parsed["night_time"], "17:45")

    def test_schedule_update_does_not_edit_commented_temperature(self):
        existing = """profile {
    time = 06:00
    # temperature = 9999
    temperature = 6000
}
profile {
    time = 15:30
    temperature = 3500
}
"""
        updated = night_light.update_schedule_text(existing, {
            "day_time": "07:00", "day_temp": 6200,
            "night_time": "18:00", "night_temp": 3300,
        })
        self.assertIn("# temperature = 9999", updated)
        self.assertIn("temperature = 6200", updated)
        self.assertNotIn("# temperature = 6200", updated)

    def test_each_write_backs_up_the_immediately_previous_version(self):
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            path = Path(td) / "hyprsunset.conf"
            path.write_text("# original\n" + night_light.render_schedule({
                "day_time": "06:00", "day_temp": 6000,
                "night_time": "15:30", "night_temp": 3500,
            }))
            first = {
                "day_time": "07:00", "day_temp": 6100,
                "night_time": "17:00", "night_temp": 3400,
            }
            second = {
                "day_time": "08:00", "day_temp": 6200,
                "night_time": "18:00", "night_temp": 3300,
            }
            with patch.object(night_light, "STATE_LOCK", Path(td) / "state.lock"):
                night_light.write_schedule(path, first)
                first_written = path.read_text()
                night_light.write_schedule(path, second)
            self.assertEqual(path.with_suffix(".conf.bak").read_text(), first_written)

    def test_atomic_schedule_write_keeps_backup(self):
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            path = Path(td) / "hyprsunset.conf"
            path.write_text("ORIGINAL\n", encoding="utf-8")
            schedule = {
                "day_time": "06:00",
                "day_temp": 6000,
                "night_time": "15:30",
                "night_temp": 3500,
            }
            with patch.object(night_light, "STATE_LOCK", Path(td) / "state.lock"):
                night_light.write_schedule(path, schedule)
            self.assertEqual(path.with_suffix(".conf.bak").read_text(), "ORIGINAL\n")
            self.assertEqual(night_light.parse_schedule_text(path.read_text()), schedule)
            self.assertFalse(path.with_suffix(".conf.tmp").exists())

    def test_schedule_write_preserves_private_file_mode(self):
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            path = Path(td) / "hyprsunset.conf"
            path.write_text(night_light.render_schedule({
                "day_time": "06:00", "day_temp": 6000,
                "night_time": "15:30", "night_temp": 3500,
            }))
            path.chmod(0o600)
            with patch.object(night_light, "STATE_LOCK", Path(td) / "state.lock"):
                night_light.write_schedule(path, {
                    "day_time": "07:00", "day_temp": 6100,
                    "night_time": "17:00", "night_temp": 3400,
                })
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_rejects_equal_day_and_night_times(self):
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            with patch.object(night_light, "STATE_LOCK", Path(td) / "state.lock"):
                with self.assertRaises(ValueError):
                    night_light.write_schedule(Path(td) / "hyprsunset.conf", {
                        "day_time": "06:00", "day_temp": 6000,
                        "night_time": "06:00", "night_temp": 3500,
                    })

    def test_settings_write_preserves_symlink(self):
        with tempfile.TemporaryDirectory(prefix="night-light-test-") as td:
            target = Path(td) / "settings-target.json"
            link = Path(td) / "settings.json"
            lock = Path(td) / "state.lock"
            target.write_text("{}\n")
            link.symlink_to(target)
            original_config = night_light.CONFIG_PATH
            try:
                night_light.CONFIG_PATH = link
                with patch.object(night_light, "STATE_LOCK", lock):
                    night_light.save_settings(4200)
            finally:
                night_light.CONFIG_PATH = original_config
            self.assertTrue(link.is_symlink())
            self.assertIn('4200', target.read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
