# Changelog

Release versions correspond to `manifest.json`. See the [README](README.md) for current installation and usage.

## v3.5.2 (2026-10-17)

- Render all panel text explicitly as plain text, including helper errors, schedule validation, and feedback; markup in diagnostics is never interpreted as rich text.
- Add a real, headless Qt 6 regression test for diagnostic rendering and run it in local checks and CI.

## v3.5.1 (2026-10-17)

- Preserve non-default schedule values when disabling removes every profile from the config.
- Reject schedule edits while disabled after recovering any interrupted toggle; preserve the backup and saved recovery transaction, and explain the required action in English and Spanish.
- Recognize whitespace before Lua `unbind` parentheses so removed shortcuts do not cause false collisions.
- Reject malformed structured numeric readings and snooze durations instead of coercing JSON arrays to numbers.
- Disable only the affected control when a partial readback contains a malformed section array, rather than retaining its stale available state.

## v3.5.0 (2026-10-01)

- Brightness, night light, and schedule controls remain available when an unrelated reading fails.
- Monitor selection refreshes its brightness reading, while keyboard navigation follows the hovered control and grouped actions.
- Schedule saving validates its fields; snooze actions respect pending work and refresh when the timer expires.
- Automation adds a localized 24-hour day/night schedule track and keeps keyboard navigation visible while scrolling.
- Updated control labels and feedback in English and Spanish.
