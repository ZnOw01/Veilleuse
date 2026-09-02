# Original User Request

## 2026-09-01T18:47:05Z

Modernize and elevate the entire frontend design, visual polish, layout typography, animations, and micro-interactions of the Veilleuse Omarchy Quattro plugin.

Working directory: `/home/snowflake/Projects/Veilleuse`
Integrity mode: `development`

## Requirements

### R1. Visual Polish & Omarchy Quattro Design Token Alignment
- Modernize the visual hierarchy, padding, spacing tokens (`Style.spacing`), typography, and border treatments across all three views (`Home`, `Automation`, `Settings`).
- Refine interactive elements (sliders, toggle switches, action buttons, dropdown pickers) with sleek visual micro-interactions while strictly using native Omarchy Quattro tokens (`qs.Commons`, `Style`, `Color`, `BorderSurface`, `CursorSurface`, `PanelHero`).

### R2. Fluid View Transitions & Real-time Dynamic Feedback
- Implement fluid, responsive view transitions between routes (`Home` ↔ `Automation` ↔ `Settings`) that preserve high frame rates and avoid visual stutter.
- Enhance real-time state feedback: improve active snooze timer display, schedule period badges, dynamic bar status icons, and localized hover tooltips in `BarWidget.qml` and `Panel.qml`.

### R3. Accessibility & Hybrid Navigation Preservation
- Ensure flawless interaction integrity for both mouse hover and keyboard navigation (arrow keys `← → ↑ ↓`, `Enter`, `Esc`).
- Retain the non-blocking latest-wins asynchronous request bus for instant slider responsiveness without UI stutter.

### R4. Verification & Quality Gate Compliance
- All modifications must strictly conform to zero external Python packages and zero daemon invariants.
- Must achieve 100% pass rate across the full test suite (`./scripts/check.sh` and `./scripts/check_hygiene.sh`).
- Zero syntax or binding errors under `qmllint` and `omarchy-plugin-validate .`.

## Acceptance Criteria

### UI / UX Modernization
- [ ] Panel header, route navigation, sliders, and form controls exhibit consistent, polished margins, spacing, and typography.
- [ ] Smooth transitions between `Home`, `Automation`, and `Settings` routes without flickering.
- [ ] Bar widget displays clear, dynamic glyphs and descriptive tooltips reflecting active/snoozed/scheduled states.

### Quality & Regression Gate
- [ ] `./scripts/check.sh` passes 100% (all Python unit tests and Node contract tests green).
- [ ] `./scripts/check_hygiene.sh` passes 100% (clean repository, no bytecode or extraneous files).
- [ ] `qmllint` and `omarchy-plugin-validate .` succeed without errors.
- [ ] Conventional Commits applied and active shell reloaded via `omarchy-restart-shell`.

## 2026-09-02T13:38:08Z

Finalize the frontend and UI modernization for Veilleuse, verify all 158+ contract and unit tests, ensure 0 qmllint/hygiene errors, commit with Conventional Commits, push to git, and reload the active Omarchy shell.

Working directory: `/home/snowflake/Projects/Veilleuse`
Integrity mode: `development`

## Requirements

### R1. Frontend Refinement & Polish
- Ensure smooth route transitions (`Home` ↔ `Automation` ↔ `Settings`) in `Panel.qml`.
- Ensure all quick snooze pills, shortcut chips, and duration badges render crisply with native Omarchy Quattro tokens.
- Maintain full key parity in `I18n.js` for `en` and `es` locales.

### R2. Verification & Hygiene Gates
- Pass all 158+ tests via `./scripts/check.sh` and `./scripts/check_hygiene.sh`.
- Confirm 0 syntax and binding errors with `qmllint` and `omarchy-plugin-validate .`.

### R3. Commit, Push & Shell Reload
- Stage and commit all improvements using Conventional Commits (`feat(ui): ...`, `perf(ui): ...`, `style(ui): ...`).
- Push all commits to `origin main`.
- Reload the running desktop shell via `omarchy-restart-shell`.

## Acceptance Criteria

### Verification
- [ ] `./scripts/check.sh` passes 100% (158+ unit/contract tests).
- [ ] `./scripts/check_hygiene.sh` passes 100%.
- [ ] `qmllint` and `omarchy-plugin-validate .` pass without errors.
- [ ] Git working tree clean and pushed to `origin main`.
- [ ] Shell reloaded via `omarchy-restart-shell`.

