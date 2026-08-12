#!/usr/bin/python3
import datetime
import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "src/schedule_utils.py"
spec = importlib.util.spec_from_file_location("schedule_utils_under_test", MODULE_PATH)
schedule = importlib.util.module_from_spec(spec)
spec.loader.exec_module(schedule)


class ScheduleParsingTests(unittest.TestCase):
    def test_parses_profiles_and_preserves_legacy_clamping(self):
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
        self.assertEqual(
            schedule.parse_schedule_text(text),
            {
                "day_time": "06:00",
                "day_temp": 6500,
                "night_time": "15:30",
                "night_temp": 2500,
            },
        )

    def test_strict_parsing_rejects_out_of_range_temperatures(self):
        text = """
profile { time = 06:00 temperature = 6501 }
profile { time = 15:30 temperature = 3500 }
"""
        with self.assertRaisesRegex(ValueError, "fuera de rango"):
            schedule.parse_schedule_text(text, strict=True)

    def test_identity_is_natural_and_not_a_temperature_profile(self):
        text = """
profile {
    time = 06:00
    identity = true
    temperature = 3500
}
profile {
    time = 15:30
    temperature = 3500
}
"""
        parsed = schedule.parse_schedule_text(text)
        self.assertEqual(parsed["day_temp"], schedule.DAY_TEMP)
        self.assertTrue(schedule.day_profile_is_identity(text))
        self.assertEqual(
            schedule.profile_kind(schedule.profile_info(
                "profile { time = 06:00 identity = true }"
            )),
            "day",
        )

    def test_identity_false_with_a_temperature_is_not_natural(self):
        text = """
profile { time = 06:00 identity = false temperature = 6100 }
profile { time = 15:30 temperature = 3500 }
"""
        self.assertFalse(schedule.day_profile_is_identity(text))
        self.assertEqual(schedule.parse_schedule_text(text)["day_temp"], 6100)

    def test_comments_and_bare_identity_are_parsed_without_fake_profiles(self):
        text = r'''
# profile { time = 01:00 temperature = 2500 }
description = "profile { time = 02:00 temperature = 2500 } # literal"
profile {
    time = 06:00 # natural daylight
    identity
}
profile {
    time = 15:30 # warm profile
    temperature = 3500
}
'''
        self.assertEqual(schedule.parse_schedule_text(text)["day_time"], "06:00")
        self.assertTrue(schedule.day_profile_is_identity(text))

    def test_incomplete_or_malformed_profiles_raise_instead_of_using_defaults(self):
        invalid_configs = (
            "profile { time = 06:00 }\nprofile { time = 15:30 temperature = 3500 }",
            "profile { identity = true }\nprofile { time = 15:30 temperature = 3500 }",
            "profile { time = 99:99 temperature = 6000 }\nprofile { time = 15:30 temperature = 3500 }",
            "profile { time = 06:00 temperature = 6000 ",
        )
        for text in invalid_configs:
            with self.subTest(text=text), self.assertRaises(ValueError):
                schedule.parse_schedule_text(text)

    def test_empty_text_remains_the_legacy_fallback_sentinel(self):
        self.assertEqual(schedule.parse_schedule_text(""), schedule.default_schedule())
        with self.assertRaises(ValueError):
            schedule.parse_schedule_text("", strict=True)

    def test_equal_profile_times_are_rejected(self):
        text = """
profile { time = 06:00 temperature = 6000 }
profile { time = 06:00 temperature = 3500 }
"""
        with self.assertRaisesRegex(ValueError, "diferentes"):
            schedule.parse_schedule_text(text)

    def test_profile_blocks_keep_custom_content_and_offsets(self):
        custom = """profile {
    # custom profile must survive
    time = 22:00
    temperature = 3200
}"""
        text = (
            "# managed profiles\n"
            "profile { time = 06:00 temperature = 6000 }\n"
            "profile { time = 15:30 temperature = 3500 }\n"
            + custom
            + "\n"
        )
        blocks = list(schedule.iter_profile_blocks(text))
        self.assertEqual(len(blocks), 3)
        self.assertEqual(blocks[2][2], custom)
        self.assertEqual(text[blocks[2][0]:blocks[2][1]], custom)


class ScheduleValidationTests(unittest.TestCase):
    def valid_schedule(self):
        return {
            "day_time": "6:00",
            "day_temp": 6000,
            "night_time": "15:30",
            "night_temp": 3500,
        }

    def test_validate_schedule_normalizes_and_rejects_equal_times(self):
        normalized = schedule.validate_schedule(self.valid_schedule())
        self.assertEqual(normalized["day_time"], "06:00")
        with self.assertRaises(ValueError):
            schedule.validate_schedule({
                **self.valid_schedule(),
                "night_time": "06:00",
            })

    def test_validate_schedule_handles_invalid_types_without_attribute_errors(self):
        invalid_values = (
            None,
            [],
            {"day_time": None},
            {**self.valid_schedule(), "day_temp": []},
            {**self.valid_schedule(), "night_temp": {"value": 3500}},
            {**self.valid_schedule(), "day_temp": True},
        )
        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                schedule.validate_schedule(value)

    def test_clamped_validation_is_explicit(self):
        clamped = schedule.validate_schedule({
            **self.valid_schedule(),
            "day_temp": 1,
            "night_temp": 99999,
        }, clamp=True)
        self.assertEqual(clamped["day_temp"], schedule.DAY_TEMP_MIN)
        self.assertEqual(clamped["night_temp"], schedule.NIGHT_TEMP_MAX)
        with self.assertRaises(ValueError):
            schedule.validate_schedule({
                **self.valid_schedule(),
                "day_temp": 1,
            })

    def test_runtime_period_rejects_invalid_schedule_and_clock_types(self):
        valid = schedule.default_schedule()
        self.assertEqual(
            schedule.schedule_period(valid, datetime.time(9, 0)), "day"
        )
        with self.assertRaises(ValueError):
            schedule.schedule_period({**valid, "night_time": "06:00"})
        with self.assertRaises(ValueError):
            schedule.schedule_period(valid, "09:00")

    def test_public_parsers_reject_non_text_input_with_value_error(self):
        for parser in (schedule.parse_schedule_text, schedule.iter_profile_blocks):
            with self.subTest(parser=parser), self.assertRaises(ValueError):
                if parser is schedule.iter_profile_blocks:
                    list(parser(None))
                else:
                    parser(None)
        with self.assertRaises(ValueError):
            schedule.profile_info(None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
