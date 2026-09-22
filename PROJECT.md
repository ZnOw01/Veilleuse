# Veilleuse architecture

Veilleuse is an Omarchy Quattro shell plugin for display brightness, hyprsunset night light, and schedule automation. The QML panel talks to a synchronous, standard-library-only Python helper through bounded subprocess calls.

## Components

| Area | Files | Responsibility |
| --- | --- | --- |
| Shell UI | `BarWidget.qml`, `Panel.qml`, `NerdIcon.qml` | Status widget, popout routes, controls, keyboard and pointer navigation |
| UI logic | `UiModel.js`, `I18n.js`, `Icons.js` | State normalization, schedule validation, request ordering, translations, glyphs |
| Backend | `scripts/veilleuse-control` | CLI and shell IPC boundary; calls Omarchy brightness and hyprsunset commands |
| Automation and persistence | `scripts/automation_utils.py`, `scripts/state_utils.py` | Snooze, transitions, reconciliation, private XDG settings/state/history |
| User configuration | `scripts/schedule_utils.py`, `scripts/schedule_toggle_utils.py`, `scripts/shortcut_utils.py` | Schedule parsing and transactions; optional Hyprland binding management |

## Contracts

- Python has no third-party runtime dependencies and starts no persistent daemon.
- Private Veilleuse config and state files use mode `0600`; state updates use file locking and atomic replacement.
- The UI request bus uses monotonic request IDs. Only a response matching the latest request is committed; stale physical readback is merged without replacing a newer drag target.
- Schedule input uses 24-hour `HH:MM` values, day temperatures from 5900–6500 K, and night temperatures from 2500–5000 K. Optional per-period brightness and gamma values are supported.
- The UI dictionaries provide English and Spanish translations. Backend errors use machine-readable codes mapped by the UI.

## Verification scope

`tests/` contains Python unit tests and Node.js model/contract tests. Layout tests inspect QML source and navigation stress tests run a JavaScript harness; neither suite launches the real Quickshell UI. See [TEST_INFRA.md](TEST_INFRA.md) for coverage limits and [CONTRIBUTING.md](CONTRIBUTING.md) for local verification steps.
