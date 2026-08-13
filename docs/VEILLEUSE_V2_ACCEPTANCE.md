# Veilleuse 2.0 acceptance matrix

Each row requires production path + deterministic test + integrated runtime verification where applicable.

- [ ] P1 Hero opens Automation directly and explains current period/origin.
- [ ] P2 Day temperature is editable and persisted.
- [ ] P3 Natural-day is editable by pointer and keyboard.
- [ ] P4 Live temperature range and documentation agree (2500..6500 K).
- [ ] P5 Errors stay visible in every route/editor.
- [ ] P6 Error codes distinguish helper missing, permission/OS error, backend missing, timeout, malformed response and readback failure.
- [ ] P7 Helper preflight is visible before mutation.
- [ ] P8 Dynamic bar/hero glyph and state cover warm, natural, pending, unavailable, snoozed.
- [ ] P9 Bar state follows actual/reconciled backend while panel is closed.
- [ ] P10 Live Controls and Automation have visibly distinct hierarchy.
- [ ] P11 Provenance states automatic/manual/preset/snooze/unknown and last-applied timestamp.
- [ ] P12 Settings route includes monitor, locale, scope/defaults, transition, preflight and shortcut.
- [ ] P13 Explicit enabled monitor selector controls brightness target with fail-closed readback.
- [ ] P14 Schedule can be disabled/enabled without losing exact selected profiles/comments/mode; conflicts fail closed.
- [ ] P15 Successful saves/actions show localized feedback.
- [ ] P16 Complete ES/EN dictionaries, runtime switch, key parity and no opposite-locale leakage.
- [ ] P17 Midnight-crossing schedules work and show localized next-day explanation; equal boundaries fail.
- [ ] P18 Helper path resolution handles encoded file URLs and preflight failure safely.
- [ ] P19 Latest-wins operations prevent stale UI and cancel obsolete ramps.
- [ ] F1 Built-in and custom presets apply temp/gamma and optional brightness with partial-failure reporting.
- [ ] F2 Snooze supports duration/until tomorrow/clear, survives shell restart and expires via reconcile.
- [ ] F3 Gradual transition is bounded, cancelable, defaults off and uses existing hyprsunset IPC only.
- [ ] F4 Selected monitor `focused|NAME` is persisted inline and validated each physical brightness step.
- [ ] F5 Shortcut status/install/remove is opt-in, collision-safe, marker-owned, reversible and never auto-installed.
- [ ] F6 History is bounded, validated, clearable and displays last 10 operations.
- [ ] F7 Session vs persistent scope is explicit; persistent default never silently rewrites schedule.
- [ ] F8 Schedule editor remains in Automation context, supports cancel/reset/dirty state and does not hide origin/status.
- [ ] F9 Temperature and gamma remain independent controls with preset grouping rather than semantic fusion.
- [ ] F10 Plugin config/state/history use versioned atomic XDG files mode 0600 and migrate safely.
- [ ] Q1 No service lifecycle management, no second hyprsunset daemon, no Omarchy-default edits.
- [ ] Q2 One physical percentage point max per brightness command; convergence has deadline/cancellation.
- [ ] Q3 1.1 CLI/status contract remains compatible.
- [ ] Q4 Checkout, clean clone, git archive, installed plugin and updater all pass gates without bytecode/symlinks.
- [ ] Q5 Real local install preserves protected schedule and display state after no-touch checks.
