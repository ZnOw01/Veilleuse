# Changelog

Release versions correspond to `manifest.json`. See the [README](README.md) for current installation and usage.

## Unreleased

- Hide the hero status pill in the natural color state; the bar tooltip still reports it.

## v3.6.1 (2026-11-02)

- Replace the panel screenshots with clean captures of the full Home, Automation, and Settings views.
- Compact the Automation snooze controls into one row so the full panel fits without clipping.

## v3.6.0 (2026-11-02)

- The manual night-light switch now applies the schedule's Night temperature, brightness, and gamma. Warm-light values live in one place.
- `nightlight toggle` accepts `--temperature`, `--brightness`, and `--gamma` for scripts.
- Reject non-warm toggle temperatures and toggle-only flags on other night-light operations.
- Propagate the underlying error code instead of flattening every failure to `apply_failed`.
- Persist the values that were confirmed when a later step fails.
- Hide the `Manual` and `Automatic` pill while the light is on. Snoozed, unavailable, and natural-color states still show.
- Use the theme-native `PanelSlider` and plain hero text. The custom gradients, halo, and colored hairline are gone.
- Align the value badges, consolidate the quick-snooze buttons, add a current-time marker to the schedule track, and respect reduced motion.
- Shorten the quick-snooze night-start label to Night/Noche so it no longer elides.
- Clean up `BarWidget.qml` and remove the repeated locale expression.
- Remove backend duplication in the module loader, atomic writer, timestamp validation, reconcile, and schedule dispatch.
- Fix `veilleuse-control nightlight --help` to exit 0 instead of 2.

## v3.5.3 (2026-10-19)

- Rewrite the README around the shipped behavior: verified Omarchy command flags, per-view usage, the 6000 K natural-color threshold, and the diagnostics exit-code caveat.
- Replace the August screenshots with Home, Automation, and Settings captures from the current panel.

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
