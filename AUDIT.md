# Technical audit — 2026-10-01

## Scope and architecture

The review covered the QML frontend, JavaScript model/localization/icons,
Python CLI and all five utility modules, test infrastructure, scripts,
manifest, documentation, packaging rules and GitHub Actions.

The frontend uses QtQuick 6, Quickshell and Omarchy's native components.
Its three local views share a request queue and communicate with a synchronous
Python helper through argument-array subprocesses. Python uses only the standard
library. Native integrations are `hyprctl hyprsunset`, `omarchy-monitor-state`,
`omarchy-brightness-display` and the optional Hyprland shortcut reload.

There is no database, HTTP API, authentication, web routing, web bundle,
dependency lockfile or package installation stage. Persistent storage consists
of XDG JSON state/config/history and Hyprland configuration files. Module caches
live only for the helper process. Configuration includes XDG paths, HOME,
inline shell settings and the check script's PYTHON override. CI runs the same
quality gate on Python 3.12 and Node 24; deployment uses Omarchy plugin tooling.

## Findings implemented

| Priority | Finding | Correction |
| --- | --- | --- |
| Functional | Scheduled gamma used an unavailable default applicator for natural profiles and display-only updates. | Wire the actual gamma applicator into the CLI automation environment. |
| Functional | Scheduled brightness targeted the focused monitor regardless of the selected monitor. | Resolve and validate the selected monitor, retaining its snapshot for the write. |
| Functional | Display settings configured for only one period never re-applied after the first cycle. | Re-arm the marker when the opposite period is observed, including periods without display settings. |
| Functional | Periodic automation stopped while the panel was open. | Keep the existing timer active and defer reconciliation while a request is pending. |
| Functional | The displayed default shortcut notation was rejected by the CLI. | Convert plus notation at the UI boundary; keep backend allowlist validation. |
| Functional | Shortcut results were interpreted as display-state patches and reload failures still announced success. | Handle successful shortcut mutations separately, preserve state, localize reload failures and reject malformed results. |
| Functional | Schedule status refreshed state but left editor drafts stale. | Populate from the confirmed response only if the user has not edited the pending draft. |
| Security | Schedule reads followed symlinks and could attempt to read non-regular files. | Reuse the safe regular-file reader with ancestor checks and O_NOFOLLOW. |
| Resilience | Malformed subprocess bytes could raise UnicodeDecodeError. | Decode UTF-8 with replacement; numeric readback validation still rejects invalid output. |
| Resilience | Oversized native integer output could throw during parsing. | Bound the accepted numeric token length. |
| Data integrity | Invalid history origins raised TypeError, and non-finite timestamps produced nonstandard JSON. | Validate types and finite floating-point timestamps before writing. |
| Latency | Brightness readback could start a full timeout after its shared deadline was nearly exhausted. | Bound each read to the remaining deadline and start no read after expiry. |

Automation brightness resolution also removes a redundant monitor-state
subprocess. No libraries, daemons, format migrations or new public CLI commands
were introduced. Private writes retain mode 0600 and existing transaction locks.
Request identity and latest-wins behavior remain in place.

## Verification and limits

Initial verification: 382 Python tests and 210 JavaScript tests passed.
After the changes: 395 Python tests and 220 JavaScript tests passed.
Regression cases reproduced the corrected failures before implementation.

The completed checks are `scripts/check.sh`, `scripts/check_hygiene.sh`,
`git diff --check`, `qmllint -I /usr/share/omarchy/shell BarWidget.qml Panel.qml NerdIcon.qml`
and `omarchy-plugin-validate .`. Both host validators ran successfully.
Local runtimes were Python 3.14.7 and Node 26.10.0; GitHub CI covers the supported
Python 3.12 / Node 24 combination.

The current-source credential-pattern scan found no obvious credentials;
this is not a certification of all Git history. Subprocesses use arrays rather
than shell strings. GUI focus, accessibility announcements, theme contrast,
rendering performance and physical multi-monitor behavior still need a live
Quickshell/device session. Tests do not claim to verify those surfaces.

## Changes deferred

- Splitting the large panel into components: no demonstrated functional benefit
  justifies changing its tightly shared focus and request scopes in this pass.
- Full GUI automation and rendering benchmarks: require an isolated desktop
  fixture and real Omarchy components; source contracts alone cannot supply them.
- A common deadline for file locks and whole operations: requires coordinated
  cancellation/recovery semantics across transactional writers and legacy ramps.
- Applying automation while the shell is stopped, or detecting entire schedule
  cycles missed during suspension: requires additional lifecycle semantics;
  the no-daemon invariant remains unchanged.
