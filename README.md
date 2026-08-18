# Veilleuse

An **Omarchy Quattro** bar plugin for brightness, night light, and day/night scheduling.

![Veilleuse](preview.png)

## Panel

The panel opens from the bar icon (or the bound keyboard shortcut). It has three views:

* **Home** — night light toggle, brightness, temperature, gamma, and monitor selection.
* **Automation** — day/night schedule, display values for each period, and snooze controls.
* **Settings** — language and optional keyboard shortcut.

Switch views with the `‹ ›` chevrons or the `← →` keys. Scheduled brightness, temperature, and gamma are applied when the active period changes or after saving.

## Keyboard

| Key     | Action                                                                  |
| ------- | ----------------------------------------------------------------------- |
| `← →`   | Adjust the focused slider (`brightness` +1, `temperature` +50 K, `gamma` +1); switch view elsewhere |
| `↑ ↓`   | Move between controls                                                   |
| `Enter` | Activate                                                                |
| `Esc`   | Close                                                                   |

Mouse hover moves the focus to the row under the pointer, so `← →` adjust the slider you are hovering and `Enter` activates the row beneath it. Dragging a slider with the mouse works as usual.

## Install

> Omarchy Shell plugins run unsandboxed. Review the code before enabling them.

```bash
omarchy plugin add https://github.com/ZnOw01/veilleuse.git --enable --yes
```

## Update

```bash
omarchy plugin update io.github.znow01.veilleuse --yes
omarchy-shell shell rescanPlugins
```

`omarchy plugin update` only fetches and fast-forwards the checkout and validates the manifest — it does **not** notify the running shell, so the widget keeps executing the previously loaded QML. `rescanPlugins` unloads and recreates the plugin components from disk (the same behavior `plugin add`, `enable`, and `disable` use). If the widget still looks stale after `rescanPlugins`, restart the shell:

```bash
omarchy restart shell
```

A full shell restart always applies the new code with no further action.

## Usage

### CLI

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

### Keyboard shortcut

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

## Troubleshooting

### ←/→ change views instead of adjusting the slider

The arrows adjust the slider that has the panel focus. Position the focus first:

* **Mouse**: hover the slider — the cursor follows the pointer.
* **Keyboard**: press `↑` / `↓` until the row is highlighted.

If hover does not move the cursor or the arrows still switch views after an update, the shell is running the old QML — see "Updates do not appear" below.

### Updates do not appear (widget still shows the old version)

`omarchy plugin update` touches only the checkout on disk. The running shell keeps the previously loaded code until told otherwise:

```bash
omarchy-shell shell rescanPlugins    # unload and reload plugin components
omarchy restart shell                # if the widget still looks stale, full restart
```

Verify the version actually on disk when in doubt:

```bash
grep '"version"' ~/.config/omarchy/plugins/io.github.znow01.veilleuse/manifest.json
```

It must be `3.1.1` (or newer) for the hover/arrow behavior described above.

### The panel shows `—` for every value

The helper could not read the state. Check it directly:

```bash
./scripts/veilleuse-control status
```

The usual causes are a missing `hyprsunset` (see [Requirements](#requirements)) or a monitor selection you can fix in the **Home** view under *Monitor*.

### The keyboard shortcut does nothing

Check whether the shortcut is installed and what it is bound to:

```bash
./scripts/veilleuse-control shortcut status
```

If it is installed but Hyprland does not fire it, look for conflicting bindings in `~/.config/hypr/bindings.lua` and remove the shortcut first:

```bash
./scripts/veilleuse-control shortcut remove
```

### The bar icon shows an unavailable state (dimmed glyph)

The glyph dims when the helper state is unavailable. Start with `./scripts/veilleuse-control status` and check the requirements below. If the panel opens but no write changes anything, run the same command from a terminal to see the exact error.

## Requirements

* `hyprsunset`
* `/usr/bin/python3`

## Manage the plugin

Disable:

```bash
omarchy plugin disable io.github.znow01.veilleuse
```

Remove:

```bash
omarchy plugin remove io.github.znow01.veilleuse --yes
```

Removing Veilleuse preserves the `hyprsunset` configuration and backup.

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