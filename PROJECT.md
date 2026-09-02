# Project: Veilleuse Modernization

## Architecture
Veilleuse is a native Omarchy Quattro shell plugin for brightness control, night light temperature adjustment, and automated hyprsunset schedule management.

### Component & Layer Structure
1. **Shell Entry Points**:
   - `BarWidget.qml`: Status bar icon, dynamic glyph state, provenance tooltip, and popout trigger.
   - `Panel.qml`: Top-level popout panel (`KeyboardPanel`), route container (`Home`, `Automation`, `Settings`), hybrid single-cursor navigation coordinator, and asynchronous `latest-wins` request bus.
2. **Design System & Presentation**:
   - Omarchy Quattro tokens: `/usr/share/omarchy/shell/Commons/` (`Style.qml`, `Color.qml`, `Border.qml`, `Util.qml`) and `qs.Ui` components (`BorderSurface`, `CursorSurface`, `PanelHero`, `PanelSlider`, `ToggleSwitch`, `Dropdown`, `NumberField`, `TextField`).
   - `NerdIcon.qml` & `Icons.js`: Material Design Icons codepoints and contextual glyph resolution.
3. **Frontend Logic & State Machine**:
   - `UiModel.js`: Pure JavaScript state machine, schedule validators, cursor navigation indices, monotonic request commit logic, and 38+ error code mappings.
   - `I18n.js`: Complete dual English/Spanish translation catalogs with 100% key parity and fallback resolution.
4. **Native Backend Subsystem**:
   - `scripts/veilleuse-control`: CLI entry point (stdlib-only, zero daemon) handling `status`, `brightness`, `nightlight`, `snooze`, `reconcile`, `schedule`, `shortcut`.
   - `scripts/state_utils.py`, `automation_utils.py`, `schedule_utils.py`, `schedule_toggle_utils.py`, `shortcut_utils.py`: Atomic mode `0600` state persistence, flock file locking, hyprsunset configuration parsing, and bindings.lua management.

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Design Token Alignment | Standardize all spacing, font sizing, padding, and surface alphas on `Style.spacing.*`, `Style.font.*`, and `Color.*` | M1 | survey/spec |
| 2 | Bar Widget & Tooltip Elevation | Modernize `BarWidget.qml`, active glyph transitions, status indicators, and rich provenance tooltips | M1 | survey/request |
| 3 | Panel Container & Hero Elevation | Polish `Panel.qml` header, `PanelHero` layout, hero icon opacity/color kinetics, and status subtitle pill | M1 | survey/request |
| 4 | Modern Home Sliders & Value Badges | Elevate brightness and temperature sliders with sleek dynamic pill badges, step snapping, and hover glow | M2 | survey/request |
| 5 | Quick Snooze Pills & Live Countdown | Interactive snooze presets (15m, 1h, 2h, 4h, until sunset), active snooze countdown badge, cancel button | M2 | survey/request |
| 6 | Fluid Route Cross-Fade Transitions | Smooth cross-fade and height transitions between `Home`, `Automation`, and `Settings` routes | M3 | survey/request |
| 7 | Automation Route & Schedule Grid | Harmonized schedule editor grid, consistent input heights, duration indicator, animated save/reset | M3 | survey/request |
| 8 | Settings Route & Shortcut Visuals | Per-monitor toggle cards, shortcut binding inspector/creator with visual keyboard chips | M3 | survey/request |
| 9 | Hybrid Navigation & Focus Traps | Preserve and elevate hybrid single-cursor navigation, `keyCatcherBlocked` focus trapping, and arrow key flow | M4 | survey/contract |
| 10 | Dual i18n & Error Toast Polish | 100% EN/ES localization parity, animated toast error banners with auto-dismiss and localized messages | M4 | survey/contract |
| 11 | Monotonic Request Bus Integrity | Preserve zero-race condition `latest-wins` bus, 90ms debounce, stale response merging, and drag intent tracking | M4 | survey/contract |
| 12 | E2E Test Suite & Adversarial Hardening | Comprehensive 4-tier E2E testing, coverage hardening (Tier 5), `qmllint`, `omarchy-plugin-validate` | M5 | survey/gates |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Foundation & Tokens | Design token standardization, `BarWidget.qml`, `NerdIcon.qml`, `PanelHero` and header polish | none | DONE |
| 2 | Home Route & Controls | Modernized sliders, value badges, snooze presets, live countdown badge, instant drag feedback | M1 | DONE |
| 3 | Transitions & View Routes | Animated route transitions, schedule editor grid harmonization, monitor cards, shortcut manager | M2 | DONE |
| 4 | Navigation & Micro-Interactions | Hybrid single-cursor navigation polish, focus isolation, toast notifications, dual i18n parity | M3 | DONE |
| 5 | E2E Validation & Hardening | Full 100% E2E test verification (Tiers 1-4), adversarial test hardening (Tier 5), hygiene & packaging gates | M4 | DONE |

---

## Interface Contracts

### QML Frontend ↔ JavaScript State Machine (`UiModel.js`)
- `normalizeState(rawState)`: Accepts raw JSON status from `veilleuse-control status` and returns normalized UI state with safe defaults.
- `validateScheduleFields(startStr, endStr, startTemp, endTemp)`: Validates 24h `HH:MM` time format and temperature bounds (1000K-10000K).
- `computeScheduleWindows(schedule)`: Calculates current window, active period, next transition time, and ramp progress.
- `formatSnoozeRemaining(seconds, locale)`: Returns localized human-readable time remaining string (e.g. `45m remaining` / `45m restantes`).
- `buildRequestArgs(action, params)`: Formats CLI arguments for `veilleuse-control` invocation.

### QML Frontend ↔ Backend Process (`scripts/veilleuse-control`)
- `runAsync(action, args)`: Spawns `scripts/veilleuse-control <action> <args>` via Quickshell `Process` with monotonic `requestId`.
- Monotonic Bus: `latestRequestId` increments per user interaction. `handleExit` processes only `latestRequestId` or performs `mergeStaleResponse` if newer write is pending.

### Layout Contract Preservation (`tests/layout.test.mjs`)
- Required IDs: `brightnessLabel`, `brightnessValue`, `nightlightLabel`, `nightlightValue`, `snoozeRow`, `saveScheduleButton`, `resetScheduleButton`, `startEditor`, `endEditor`.
- Signal signatures: `onMoved: function(v)` on sliders, `onClicked` on buttons.
- Navigation contract: `hasCursor` property on all interactive items, `keyCatcherBlocked` on text/number fields.

---

## Code Layout
- `BarWidget.qml`: Shell status bar icon, dynamic glyph, provenance tooltip.
- `Panel.qml`: Main panel, route switching, request bus, hybrid cursor manager, route views.
- `NerdIcon.qml`: Nerd font glyph renderer.
- `Icons.js`: Material Design icon codepoints and glyph selectors.
- `I18n.js`: English and Spanish translation catalogs.
- `UiModel.js`: Pure JavaScript state machine, validation, and navigation logic.
- `scripts/`: Backend CLI scripts and persistence utilities.
- `tests/`: Node and Python test suites.
- `.agents/`: Agent metadata and execution logs (no code or test files).
