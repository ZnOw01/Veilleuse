<div align="center">

# Veilleuse

**Native brightness, night light temperature, and day/night automation for Omarchy Quattro.**

[![CI](https://img.shields.io/github/actions/workflow/status/ZnOw01/Veilleuse/checks.yml?branch=main&style=for-the-badge&logo=githubactions&logoColor=white&label=CI)](https://github.com/ZnOw01/Veilleuse/actions/workflows/checks.yml)
[![Version](https://img.shields.io/badge/version-3.3.0-7C3AED?style=for-the-badge&logo=semver&logoColor=white)](https://github.com/ZnOw01/Veilleuse/releases)
[![Platform](https://img.shields.io/badge/Platform-Omarchy_Quattro_4.0%2B-008080?style=for-the-badge&logo=linux&logoColor=white)](https://github.com/ZnOw01/Veilleuse)
[![Hyprland](https://img.shields.io/badge/Hyprland-hyprsunset-00AAFF?style=for-the-badge&logo=wayland&logoColor=white)](https://hyprland.org/)
[![Python](https://img.shields.io/badge/Python-3.12%2B_stdlib-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-3DA639?style=for-the-badge&logo=opensourceinitiative&logoColor=white)](LICENSE)

[Features](#features) ·
[Architecture](#architecture--system-design) ·
[Quick Start](#quick-start) ·
[Screenshots](#screenshots) ·
[Panel & Navigation](#panel--navigation) ·
[CLI Reference](#cli-reference) ·
[Storage & Security](#storage--security-invariants) ·
[Dual Localization](#dual-localization-en--es) ·
[Troubleshooting](#troubleshooting) ·
[Development](#development) ·
[License](#license)

</div>

---

## Screenshots

<div align="center">

| Home | Automation | Settings |
| :---: | :---: | :---: |
| ![Home view](preview.png) | ![Automation view](assets/automation.png) | ![Settings view](assets/settings.png) |
| Night-light toggle, live brightness, temperature and gamma sliders, monitor picker | Day/night schedule editor with per-period display values and timed snooze | Language selector and conflict-checked global shortcut binding |

</div>

---

## Features

| Feature | Description |
| :--- | :--- |
| **Display Brightness** | 1–100% brightness control for focused and named external monitors via `omarchy-brightness-display`. |
| **Night Light & Gamma** | Temperature adjustment (`2500–6500 K`) and gamma correction (`0–100%`) via `hyprsunset`. |
| **Day/Night Automation** | Circadian transitions with per-period brightness, temperature, and gamma profiles. |
| **Timed Snooze** | Temporary night light suspension (1m–24h) with automatic state reconciliation. |
| **Hybrid Navigation** | Arrow-key navigation (`← → ↑ ↓`) with real-time mouse-hover cursor tracking. |
| **Safe Hyprland Shortcuts** | Conflict-checked, reversible shortcut management in `~/.config/hypr/bindings.lua` with `.bak` backups. |
| **Zero External Deps** | Python 3.12+ standard library only; zero pip dependencies and zero persistent daemons. |
| **Dual Localization** | English (`en`) and Spanish (`es`) dictionaries with 100% key parity across all 37 backend error codes. |
| **Atomic Persistence** | Mode `0600` XDG storage protected by `fcntl` file locks and atomic file replacement. |

---

## Architecture & System Design

```mermaid
graph TD
    subgraph UI ["Frontend (QML / QtQuick 6)"]
        BW["BarWidget.qml<br/>(Omarchy Bar Entry)"] --> P["Panel.qml<br/>(Popup & Navigation)"]
        P --> UM["UiModel.js<br/>(State & Drag Chase)"]
        P --> I18N["I18n.js<br/>(en / es Dictionaries)"]
        P --> IC["Icons.js<br/>(Nerd Fonts Mappings)"]
    end

    subgraph IPC ["Monotonic Request Bus"]
        P -->|"Latest-Wins CLI Execution"| VC["scripts/veilleuse-control"]
    end

    subgraph Backend ["Backend Python Subsystem (Python 3.12+ stdlib)"]
        VC --> SU["schedule_utils.py<br/>(hyprsunset.conf Parser)"]
        VC --> STU["schedule_toggle_utils.py<br/>(Transactional Toggle)"]
        VC --> SCU["shortcut_utils.py<br/>(Lua AST Bindings)"]
        VC --> AU["automation_utils.py<br/>(Snooze & Reconcile Engine)"]
        VC --> ST["state_utils.py<br/>(Atomic XDG Storage 0600)"]
    end

    subgraph System ["System Surfaces"]
        VC --> HS["hyprctl hyprsunset"]
        VC --> MS["omarchy-monitor-state"]
        VC --> BD["omarchy-brightness-display"]
        ST --> XDG["~/.config/veilleuse/<br/>~/.local/state/veilleuse/"]
        SU --> HCONF["~/.config/hypr/hyprsunset.conf"]
        SCU --> LUA["~/.config/hypr/bindings.lua"]
    end
```

### Backend Modules Overview

| Module | Responsibility |
| :--- | :--- |
| `scripts/veilleuse-control` | Main CLI entry point, preflight diagnostics, subprocess bounds, and latest-wins IPC gateway. |
| `scripts/schedule_utils.py` | Comment-preserving parser for `hyprsunset.conf` with circular modulo-1440 time math. |
| `scripts/schedule_toggle_utils.py` | Transactional profile stripper and restorer for schedule enable/disable with SHA-256 state locking. |
| `scripts/shortcut_utils.py` | AST/lexical-safe Lua manipulator for `bindings.lua` with collision analysis and marker block isolation. |
| `scripts/automation_utils.py` | Dependency-injected orchestration engine for snooze countdowns, transition ramps, and drift reconciliation. |
| `scripts/state_utils.py` | Atomic XDG JSON persistence layer for `config.json`, `state.json`, and `history.jsonl` (mode `0600`, `fcntl` locks). |

---

## Quick Start

### Requirements

- **Omarchy Quattro** (Omarchy 4.0+)
- **Hyprland** with `hyprsunset` installed
- **Python 3.12+** (`python3`, standard library only)

### Installation & Lifecycle

```bash
# Install and enable plugin
omarchy plugin add https://github.com/ZnOw01/Veilleuse.git --enable --yes

# Update plugin and reload shell UI components
omarchy plugin update io.github.znow01.veilleuse --yes
omarchy restart shell

# Remove plugin (preserves hyprsunset.conf schedule and backups)
omarchy plugin remove io.github.znow01.veilleuse --yes
```

---

## Panel & Navigation

The popout panel provides three views:
- **Home (`home`)** — Master night-light toggle, live brightness, temperature and gamma sliders, and monitor selector.
- **Automation (`automation`)** — Schedule toggle, start/end transition editors with per-period display presets, and timed snooze.
- **Settings (`settings`)** — Active language selector (`English` / `Español`) and optional Hyprland global shortcut binding.

### Keyboard & Mouse Controls

| Input | Scope | Action |
| :--- | :--- | :--- |
| `↑` / `↓` | Everywhere | Move focus cursor vertically between rows |
| `←` / `→` | On Sliders | Step value (`brightness` ±1%, `temperature` ±50 K, `gamma` ±1%) |
| `←` / `→` | On Navigation / Rows | Switch between routes (`Home` ↔ `Automation` ↔ `Settings`) |
| `Enter` / `Space` | On Controls | Activate button, toggle switch, or open dropdown picker |
| `Esc` | Everywhere | Unfocus editor / close dropdown, or dismiss the panel |
| **Mouse Hover** | Any row | Moves keyboard cursor to the hovered row for instant `←` / `→` adjustment |

---

## CLI Reference

The helper `scripts/veilleuse-control` provides direct CLI and script access:

### Status & Display Brightness
```bash
# Read unified system and plugin state JSON
./scripts/veilleuse-control status

# Set brightness (1–100%) on focused or named monitor
./scripts/veilleuse-control brightness 75
./scripts/veilleuse-control brightness 75 --monitor focused
./scripts/veilleuse-control brightness 75 --monitor DP-1
```

### Night Light & Gamma
```bash
# Toggle night light on/off
./scripts/veilleuse-control nightlight toggle

# Restore daylight natural color (identity)
./scripts/veilleuse-control nightlight natural

# Set custom temperature and gamma
./scripts/veilleuse-control nightlight temperature 3500
./scripts/veilleuse-control nightlight gamma 85
```

Temperature range: `2500–6500 K`
Gamma range: `0–100%`

### Automation & Snooze
```bash
# Snooze night light for a set duration
./scripts/veilleuse-control snooze set --minutes 30
./scripts/veilleuse-control snooze set --seconds 1800
./scripts/veilleuse-control snooze clear
./scripts/veilleuse-control snooze status

# Read or modify schedule
./scripts/veilleuse-control schedule get
./scripts/veilleuse-control schedule status
./scripts/veilleuse-control schedule enable
./scripts/veilleuse-control schedule disable
./scripts/veilleuse-control schedule set \
  --day-time 06:00 --night-time 18:30 \
  --day-temp 6000 --night-temp 3500 \
  --day-brightness 80 --day-gamma 100 \
  --night-brightness 50 --night-gamma 80

# Reconcile snooze expiration and schedule boundaries
./scripts/veilleuse-control reconcile
```

### Global Shortcut Management

Veilleuse does not install a shortcut automatically.

```bash
# Install, inspect, or remove Hyprland shortcut binding
./scripts/veilleuse-control shortcut status
./scripts/veilleuse-control shortcut install --keys "SUPER, V"
./scripts/veilleuse-control shortcut remove
```

Installation validates keys against an allowlist, checks for collisions, and manages only the Veilleuse marker block in `~/.config/hypr/bindings.lua`:

```lua
-- >>> Veilleuse shortcut >>>
o.bind("SUPER + V", "Veilleuse", "omarchy-shell -q io.github.znow01.veilleuse toggleNightlight")
-- <<< Veilleuse shortcut <<<
```

A `bindings.lua.bak` backup is created before modification.

### Shell IPC
```bash
# Toggle night light directly through Omarchy Shell IPC
omarchy shell io.github.znow01.veilleuse toggleNightlight

# Toggle the popout panel UI
omarchy shell io.github.znow01.veilleuse toggle
```

---

## Storage & Security Invariants

| File Path | Purpose | Permissions | Safety Mechanism |
| :--- | :--- | :--- | :--- |
| `~/.config/hypr/hyprsunset.conf` | Night light temperature & schedule | `0644` | Atomic temp write, `.lock` protection, `.bak` backup |
| `~/.config/hypr/bindings.lua` | Optional Hyprland shortcut | `0644` | Bound marker blocks (`-- >>> Veilleuse shortcut >>>`), `.bak` backup |
| `~/.config/veilleuse/config.json` | Plugin settings & language preference | `0600` | Atomic replace, versioned schema, stripped legacy keys |
| `~/.local/state/veilleuse/state.json` | Runtime state, snooze tokens, display values | `0600` | Mode `0600`, atomic write, bounded validation |
| `~/.local/state/veilleuse/history.jsonl` | Audit history of operations | `0600` | Ring buffer strictly capped at the last 50 entries |

### Core Architectural Invariants

1. **Non-destructive Parsing**: Custom profiles, comments, and unmanaged blocks in `hyprsunset.conf` are preserved during schedule updates.
2. **Latest-Wins Request Bus**: Rapid slider drags use monotonic request IDs so stale responses never overwrite pending user intent.
3. **Fail-Closed Normalization**: Backend command failures or timeouts gracefully fall back to an explicit safe state with translated error messages.
4. **Zero Daemon Policy**: Periodic reconciliation and snooze checks run synchronously on state changes and shell lifecycle events without spawning daemons.

---

## Dual Localization (en / es)

Localization is decoupled from the UI framework in pure JavaScript (`I18n.js`):

- **Strict Key Parity**: 100% key parity between English and Spanish dictionaries enforced by continuous automated tests.
- **37 Mapped Error Codes**: Every backend error code (`invalid_json`, `helper_unavailable`, `timeout`, `conflict`, etc.) maps to a distinct localized string in both languages.
- **Fail-Safe Fallbacks**: Unknown locales fall back to English (`en`), missing keys fall back to Spanish (`es`), and unrecognized diagnostics pass through untouched.

---

## Troubleshooting

### Arrow keys switch views instead of moving the slider

The `←` / `→` keys adjust the slider that currently holds cursor focus:
- Hover the mouse pointer over the slider row to focus it immediately, or press `↑` / `↓` until the row is highlighted.

### Updates do not appear after running `omarchy plugin update`

Reload the shell to unload cached QML components from memory:

```bash
omarchy restart shell
```

### Panel values display `—` or helper unavailable

Verify that `hyprsunset` is running and your focused display is detected:

```bash
./scripts/veilleuse-control status
```

### Global shortcut does not trigger

Inspect the shortcut status and check for conflicting key bindings:

```bash
./scripts/veilleuse-control shortcut status
```

---

## Development

Veilleuse uses vertical Test-Driven Development (TDD) across Python unit tests and Node.js test runners (450+ tests).

### Run Verification Suite

```bash
# Execute complete verification pipeline (Python tests, Node tests, linters, hygiene)
./scripts/check.sh

# Run package hygiene check (manifest validation, bytecode & symlink blockers)
./scripts/check_hygiene.sh
```

### Individual Test Runners

```bash
# Python backend unit tests
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'

# Node.js UI model, layout, and localization tests
node --test tests/UiModel.test.js tests/layout.test.mjs tests/i18n.test.js tests/errorCodes.test.js tests/icons.test.mjs
```

---

## License

MIT © 2026 [ZnOw01](https://github.com/ZnOw01). Released under the [MIT License](LICENSE).
