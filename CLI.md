# CLI reference

Run the examples from the repository root, or from the installed plugin directory (`~/.config/omarchy/plugins/io.github.znow01.veilleuse` with the standard Omarchy installer). Replace `DP-1` with an enabled monitor name reported by `status`.

`scripts/veilleuse-control` is a synchronous helper. Handled operations return JSON on stdout; argument-parser errors print usage on stderr. Mutation failures normally exit non-zero, but `status` and `preflight` return zero even when their payload reports unavailable backends. Check `preflight.ok` and each status section's `available`/`error` fields rather than relying on the exit code alone. For standalone `preflight`, check its top-level `ok`. A `schedule set` response can also contain `state_persist_error` after the schedule file was saved; inspect it before treating the whole update as successful.

Most read and write commands accept `--monitor`, which defaults to `focused` and otherwise takes an enabled monitor name (`status`, `brightness`, `nightlight`, `snooze`, `reconcile`, and every `schedule` subcommand except `schedule get`).

[Diagnostics](#diagnostics) · [Brightness](#display-brightness) · [Night light](#night-light-and-gamma) · [Automation](#automation-and-snooze) · [Shortcuts](#global-shortcut-management) · [Shell IPC](#shell-ipc)

## Diagnostics

```bash
# Read combined system and plugin state as JSON
./scripts/veilleuse-control status
./scripts/veilleuse-control status --monitor DP-1

# Read-only availability check for the helper and its backends
./scripts/veilleuse-control preflight
```

## Display brightness

```bash
# Read current brightness on the focused monitor
./scripts/veilleuse-control brightness

# Set brightness (1-100%) on the focused or a named monitor
./scripts/veilleuse-control brightness 75
./scripts/veilleuse-control brightness 75 --monitor DP-1
```

## Night light and gamma

```bash
# Toggle night light on/off
./scripts/veilleuse-control nightlight toggle

# Restore daylight natural color (identity)
./scripts/veilleuse-control nightlight natural

# Set custom temperature and gamma
./scripts/veilleuse-control nightlight temperature 3500
./scripts/veilleuse-control nightlight gamma 85
```

See the [README feature ranges](README.md#features) for temperature and gamma limits. Night light and gamma use the global `hyprsunset` backend; `--monitor` selects brightness readback and automation brightness, not a per-monitor color temperature.

## Automation and snooze

```bash
# Snooze night light for a set duration
./scripts/veilleuse-control snooze set --minutes 30
./scripts/veilleuse-control snooze set --seconds 1800
./scripts/veilleuse-control snooze clear
./scripts/veilleuse-control snooze status

# Read or modify the schedule
./scripts/veilleuse-control schedule get
./scripts/veilleuse-control schedule status
./scripts/veilleuse-control schedule enable
./scripts/veilleuse-control schedule disable
./scripts/veilleuse-control schedule set \
  --day-time 06:00 --night-time 18:30 \
  --day-temp 6200 --night-temp 3500 \
  --day-brightness 80 --day-gamma 100 \
  --night-brightness 50 --night-gamma 80

# Reconcile snooze expiration and schedule boundaries
./scripts/veilleuse-control reconcile
```

Supply exactly one of `--minutes` or `--seconds`. Clearing snooze removes its timer; run `reconcile` to apply the active profile immediately.

`--minutes` accepts `1–1440`; `--seconds` accepts `10–86400`. Schedule times use 24-hour `HH:MM`; day temperatures accept `5900–6500 K` (at or above `6000 K` the day profile is written as natural color), night temperatures accept `2500–5000 K`, and the optional per-period `--*-brightness` (1–100) and `--*-gamma` (0–100) values are validated on save. Omitting optional display values leaves the corresponding period without scheduled brightness/gamma. After CLI schedule changes, run `reconcile` to apply the current profile; the panel queues reconciliation after its own successful schedule changes.

## Global shortcut management

See the [README shortcut guide](README.md#global-shortcut) for `shortcut status`, `shortcut install --keys`, and `shortcut remove`, including the managed Lua block and backup/reload guarantees.

The CLI accepts comma notation such as `"SUPER SHIFT, N"`; the panel converts its plus notation before calling the helper. Modifiers are `SUPER`, `CTRL`, `ALT`, `SHIFT`, and `MOD1`–`MOD5`. Keys include single letters/digits, `F1`–`F24`, and named keys such as `SPACE`, `RETURN`, and the arrow keys. The backend rejects unsupported syntax and collisions.

## Shell IPC

```bash
# Toggle night light directly through Omarchy Shell IPC
omarchy shell io.github.znow01.veilleuse toggleNightlight

# Toggle the popout panel UI
omarchy shell io.github.znow01.veilleuse toggle
```

The panel also exposes `open`, `close`, `show`, and `hide`. IPC requires a running Omarchy shell with the plugin loaded.

See the [README](README.md) for installation, configuration, and troubleshooting, and [PROJECT.md](PROJECT.md) for persistence and request ordering.
