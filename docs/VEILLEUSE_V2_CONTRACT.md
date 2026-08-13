# Veilleuse 2.0 — integration contract

Base: e6f1e5793101e941368530b808d8c6ffff064738. Preserve all 1.1 CLI/status fields.

## Ownership
- Omarchy inline widget settings (`shell.json`, via updateEntryInline): locale, selected monitor (`focused` or explicit name), apply scope (`session`/`persistent`), transition seconds, preferred preset, shortcut key display.
- Plugin config: `$XDG_CONFIG_HOME/veilleuse/config.json`, schema 1. Custom presets and persistent default only. Atomic write, mode 0600.
- Plugin state: `$XDG_STATE_HOME/veilleuse/state.json`, schema 1. Snooze expiry, schedule-disabled transaction metadata, latest provenance/operation. Atomic write, mode 0600.
- History: `$XDG_STATE_HOME/veilleuse/history.jsonl`, bounded to 50 validated records, mode 0600.
- Never manage/restart services or edit Omarchy-owned defaults.

## Combined status additions
`preflight`, `automation`, `presets`, `history`, while preserving plugin/brightness/nightlight/schedule/monitors.
- preflight: helper/backend command availability and specific errors.
- automation: schedule_enabled, snooze_until, snoozed, transition_seconds, origin (`automatic|manual|preset|snooze|unknown`), last_applied.
- monitor entries retain name/enabled/focused; brightness command accepts `--monitor focused|NAME` and validates enabled target/readback.

## CLI additions
- `preflight`
- `settings get`; `settings set --default-preset NAME`; no provider/model data.
- `preset list|save NAME --temperature K --gamma N [--brightness N]|delete NAME|apply NAME --monitor TARGET [--transition-seconds 0..1800]`
- `snooze status|set --minutes N|until-tomorrow|clear`; set applies natural immediately; reconcile enforces natural while active and active schedule profile when expired.
- `transition --temperature K --gamma N --seconds 0..1800`: cancelable helper process, bounded IPC calls, no second daemon.
- `schedule enable|disable|status`: disable removes only selected managed day/night profile blocks, stores exact original/disabled hashes and text transactionally; enable restores only if current disabled hash matches, otherwise fails closed. Preserve unrelated profiles/comments/mode.
- `history list|clear`
- `shortcut status|install --keys SAFE_KEYS|remove`: edit only a marker block in the user `~/.config/hypr/bindings.lua` using Omarchy 4 Lua `o.bind("MODS + KEY", "Veilleuse", CMD)` syntax, validate keys, honor ordered bind/unbind state, fail closed on dynamic bindings, backup once, preserve mode, use the fixed command `omarchy-shell -q io.github.znow01.veilleuse toggleNightlight`, and reload best-effort with `hyprctl reload`. Never install automatically.
- `reconcile`: used by loaded bar widget timer; enforces snooze or applies current schedule profile with configured transition. Idempotent.

## Presets
Built-ins: reading, work, cinema. User presets validated. Applying brightness converges using only native +1%/1%- steps, with a global deadline and cancellation by process replacement; never one physical jump.

## UI
Three compact routes within one native panel: Home, Automation, Settings; route switch preserves live context. Home: dynamic hero/bar glyph and provenance, presets, live sliders, monitor selector, last-applied/history. Automation: enabled toggle, schedule editor, transition, snooze and midnight explanation. Settings: ES/EN, apply scope, default preset, helper preflight, shortcut install/remove/key field. All actions backed by helper or native inline settings—no fake controls.

## i18n
`I18n.js` with complete `es` and `en` dictionaries and key parity. No user-facing literals in QML/helper response codes; helper includes stable `error_code` plus Spanish fallback message. UI localizes codes.

## TDD / safety
Strict vertical RED→GREEN. Preserve 1.1 tests. Add deterministic fixtures for XDG config/state, corruption/migration, concurrent writes, schedule disable/enable conflict, midnight, snooze expiry, ramp cancellation/deadline, monitor disappearance, preset partial failures, shortcut install/remove/collision, history bound, locale parity and no opposite-locale leakage. No pycache/symlinks. No external config touched by tests.
