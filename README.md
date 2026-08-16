# Veilleuse

An **Omarchy Quattro** bar plugin for display control: brightness, night
light and a day/night schedule, in one compact panel.

![Veilleuse](preview.png)

## The panel

Three views, switched with the on-screen arrows `‹ ›` or the `← →` keys.

- **Home** — a switch for the night light and three live sliders: brightness,
  temperature and gamma. Each slider shows its label and live value on one
  row and moves one unit at a time. Below them, the monitor picker.
- **Automation** — the schedule: an on/off switch with its time window, and
  one block per period (**Day** and **Night**) where you set the time plus
  the same three options as Home (temperature, brightness, gamma) as
  numbers. Scheduled brightness and gamma are applied when the schedule
  enters each period — or right after you save. Below, snooze: a number, an
  hours/minutes/seconds unit, and one button.
- **Settings** — language (English by default, Spanish available) and the
  optional keyboard shortcut.

## Keyboard

| Key | Action |
| --- | ------ |
| `← →` | switch view |
| `↑ ↓` | move within a view |
| `Enter` | activate the highlighted control |
| `Esc` | close |

Everything else works with the mouse.

## Control from the terminal

`scripts/veilleuse-control` does everything the panel does:

```bash
./scripts/veilleuse-control status                       # combined JSON status
./scripts/veilleuse-control brightness 70                # absolute % write, readback-confirmed
./scripts/veilleuse-control nightlight toggle
./scripts/veilleuse-control nightlight temperature 3500
./scripts/veilleuse-control nightlight gamma 80
./scripts/veilleuse-control snooze set --minutes 30      # or --seconds 90
./scripts/veilleuse-control snooze clear
./scripts/veilleuse-control schedule get
./scripts/veilleuse-control schedule set \
  --day-time 06:00 --night-time 15:30 \
  --day-temp 6000 --night-temp 3500 \
  --day-brightness 80 --day-gamma 100 \
  --night-brightness 55 --night-gamma 85
./scripts/veilleuse-control schedule enable|disable
./scripts/veilleuse-control reconcile                    # enforce snooze/schedule now
```

Night light from 2500 to 6500 K and gamma from 0 to 100 %, matching the
panel sliders. Schedule times, temperatures and comments live in
`~/.config/hypr/hyprsunset.conf`, updated atomically with a `.bak` copy.

## Requirements

- `hyprsunset` configured by Omarchy.
- `/usr/bin/python3`.

## Install

> Plugins run unsandboxed inside Omarchy Shell. Review the code before
> enabling them.

```bash
omarchy plugin add https://github.com/ZnOw01/veilleuse.git --enable --yes
```

Update and remove:

```bash
omarchy plugin update io.github.znow01.veilleuse --yes
omarchy plugin disable io.github.znow01.veilleuse
omarchy plugin remove io.github.znow01.veilleuse --yes
```

Removal preserves `~/.config/hypr/hyprsunset.conf` and its backup copy.

## Optional keyboard shortcut

Veilleuse **never installs shortcuts automatically**. `~/.config/hypr/bindings.lua`
is only touched by an explicit command:

```bash
./scripts/veilleuse-control shortcut install --keys "SUPER, V"
./scripts/veilleuse-control shortcut status
./scripts/veilleuse-control shortcut remove
```

Installation validates the keys, detects collisions with other bindings and
edits only a marked `-- >>> Veilleuse shortcut >>>` block:

```lua
-- >>> Veilleuse shortcut >>>
o.bind("SUPER + V", "Veilleuse", "omarchy-shell -q io.github.znow01.veilleuse toggleNightlight")
-- <<< Veilleuse shortcut <<<
```

The command is fixed and cannot be customized. Installation saves a single
`bindings.lua.bak` and preserves the file mode; removal reverts the file to its previous content
and deletes it if it ends up empty.

## Where data lives

- `~/.config/hypr/hyprsunset.conf` — schedule times and temperatures.
- `~/.config/veilleuse/config.json` — plugin config (schema only).
- `~/.local/state/veilleuse/state.json` — snooze, provenance and scheduled
  display values.
- `~/.local/state/veilleuse/history.jsonl` — internal audit log (last 50
  operations).

All writes are atomic, mode 0600, and versioned with safe migrations.

## Development

```bash
git clone https://github.com/ZnOw01/veilleuse.git
cd veilleuse
omarchy plugin validate .
./scripts/check.sh
```

## License

MIT © 2026 ZnOw01.
