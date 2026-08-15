# Veilleuse

An **Omarchy Quattro** plugin to control brightness, night light and schedules
from the bar.

![Veilleuse](preview.png)

## Features

- Redesigned panel with Home, Automation and Settings views, direct
  navigation and status glyphs.
- Brightness for the focused or a selected monitor, limited to one physical
  step per operation and confirmed by readback.
- Night light from 2500 to 6500 K and gamma from 0 to 100 %.
- Built-in and custom presets with temperature, gamma and optional brightness.
- Snooze for a fixed time or until tomorrow, cancelable gradual transitions
  and schedule reconciliation.
- Day/night schedule with atomic updates to `~/.config/hypr/hyprsunset.conf`;
  comments, permissions, foreign profiles and a `.bak` copy are preserved.
- Transactional schedule enable/disable with conflict detection.
- Visible preflight, bounded history, operation provenance and a complete
  Spanish/English interface.
- Optional, reversible keyboard shortcut in `bindings.lua` (manual install,
  never automatic).
- Mouse, arrow-key and `j/k/h/l` navigation.

## Requirements

- `hyprsunset` configured by Omarchy.
- `/usr/bin/python3`.

## Install

> Plugins run unsandboxed inside Omarchy Shell. Review the code before
> enabling them.

```bash
omarchy plugin add https://github.com/ZnOw01/veilleuse.git --enable --yes
```

## Maintenance

```bash
omarchy plugin update io.github.znow01.veilleuse --yes
omarchy plugin disable io.github.znow01.veilleuse
omarchy plugin remove io.github.znow01.veilleuse --yes
```

Removal preserves `~/.config/hypr/hyprsunset.conf` and its backup copy.

## Keyboard shortcut (optional)

Veilleuse **never installs shortcuts automatically**. `~/.config/hypr/bindings.lua`
is only touched by an explicit command:

```bash
./scripts/veilleuse-control shortcut install --keys "SUPER, V"
./scripts/veilleuse-control shortcut status
./scripts/veilleuse-control shortcut remove
```

Installation validates the keys, detects collisions with other bindings and
edits only a marked `-- >>> Veilleuse shortcut >>>` block. Because
`bindings.lua` runs as Lua in Omarchy 4, the block uses the shell's `o.bind`
syntax:

```lua
-- >>> Veilleuse shortcut >>>
o.bind("SUPER + V", "Veilleuse", "omarchy-shell -q io.github.znow01.veilleuse toggleNightlight")
-- <<< Veilleuse shortcut <<<
```

The command is fixed and cannot be customized.
Installation saves a single `bindings.lua.bak` and preserves the file mode.
Removal reverts the file to its previous content and deletes it if it ends
up empty. Both try a `hyprctl` reload when available.

## Development

```bash
git clone https://github.com/ZnOw01/veilleuse.git
cd veilleuse
omarchy plugin validate .
./scripts/check.sh
```

## License

MIT © 2026 ZnOw01.
