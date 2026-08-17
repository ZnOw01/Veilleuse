# Veilleuse

An **Omarchy Quattro** bar plugin for brightness, night light, and day/night scheduling.

![Veilleuse](previewv3.png)

## Panel

Three views, switchable with `‹ ›` or `← →`:

* **Home** — night light toggle, brightness, temperature, gamma, and monitor selection.
* **Automation** — day/night schedule, display values for each period, and snooze controls.
* **Settings** — language and optional keyboard shortcut.

Scheduled brightness, temperature, and gamma are applied when the active period changes or after saving.

## Keyboard

| Key     | Action                |
| ------- | --------------------- |
| `← →`   | Switch view           |
| `↑ ↓`   | Move between controls |
| `Enter` | Activate              |
| `Esc`   | Close                 |

Mouse input is also supported.

## CLI

`scripts/veilleuse-control` exposes the same controls:

```bash
./scripts/veilleuse-control status
./scripts/veilleuse-control brightness 70

./scripts/veilleuse-control nightlight toggle
./scripts/veilleuse-control nightlight temperature 3500
./scripts/veilleuse-control nightlight gamma 80

./scripts/veilleuse-control snooze set --minutes 30
./scripts/veilleuse-control snooze clear

./scripts/veilleuse-control schedule get
./scripts/veilleuse-control schedule set \
  --day-time 06:00 --night-time 15:30 \
  --day-temp 6000 --night-temp 3500 \
  --day-brightness 80 --day-gamma 100 \
  --night-brightness 55 --night-gamma 85
./scripts/veilleuse-control schedule enable
./scripts/veilleuse-control schedule disable

./scripts/veilleuse-control reconcile
```

Temperature range: `2500–6500 K`
Gamma range: `0–100%`

Schedule configuration is stored in `~/.config/hypr/hyprsunset.conf`. Updates are atomic and keep a `.bak` backup.

## Requirements

* `hyprsunset`
* `/usr/bin/python3`

## Install

> Omarchy Shell plugins run unsandboxed. Review the code before enabling them.

```bash
omarchy plugin add https://github.com/ZnOw01/veilleuse.git --enable --yes
```

Update:

```bash
omarchy plugin update io.github.znow01.veilleuse --yes
```

Disable:

```bash
omarchy plugin disable io.github.znow01.veilleuse
```

Remove:

```bash
omarchy plugin remove io.github.znow01.veilleuse --yes
```

Removing Veilleuse preserves the `hyprsunset` configuration and backup.

## Keyboard shortcut

Veilleuse does not install a shortcut automatically.

```bash
./scripts/veilleuse-control shortcut install --keys "SUPER, V"
./scripts/veilleuse-control shortcut status
./scripts/veilleuse-control shortcut remove
```

Installation validates the key combination, checks for binding conflicts, and manages only the Veilleuse block in `~/.config/hypr/bindings.lua`:

```lua
-- >>> Veilleuse shortcut >>>
o.bind("SUPER + V", "Veilleuse", "omarchy-shell -q io.github.znow01.veilleuse toggleNightlight")
-- <<< Veilleuse shortcut <<<
```

The command itself is fixed. A `bindings.lua.bak` backup is created before modification.

## Files

| Path                                     | Purpose                                |
| ---------------------------------------- | -------------------------------------- |
| `~/.config/hypr/hyprsunset.conf`         | Schedule and night-light configuration |
| `~/.config/veilleuse/config.json`        | Plugin configuration                   |
| `~/.local/state/veilleuse/state.json`    | Snooze and display state               |
| `~/.local/state/veilleuse/history.jsonl` | Last 50 operations                     |

Writes are atomic and use mode `0600`.

## Development

```bash
git clone https://github.com/ZnOw01/veilleuse.git
cd veilleuse

omarchy plugin validate .
./scripts/check.sh
```

## License

MIT © 2026 ZnOw01
