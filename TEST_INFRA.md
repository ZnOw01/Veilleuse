# E2E Test Infra: Veilleuse Modernization

## Test Philosophy
- **Opaque-box, requirement-driven**: Tests derive directly from `ORIGINAL_REQUEST.md`, `AGENTS.md`, and Omarchy Quattro design guidelines, validating user-facing behavior, layout structure, state stability, and visual contracts without relying on transient implementation internals.
- **Multi-Tier Methodology**:
  - **Tier 1 — Feature Coverage (>=5 per feature)**: Isolated happy-path verification of every visual, behavioral, and functional capability.
  - **Tier 2 — Boundary & Corner Cases (>=5 per feature)**: Extreme values, rapid dragging, empty inputs, midnight wrap-arounds, locale switching, and error recovery.
  - **Tier 3 — Cross-Feature Combinations (pairwise)**: Interactions between sliders, snooze timers, schedule toggles, route switches, keyboard/mouse transitions, and rapid bus requests.
  - **Tier 4 — Real-World Application Scenarios**: Multi-monitor setups, daily schedule routines, sleep mode transitions, and theme change responsiveness.
  - **Tier 5 — Adversarial Coverage Hardening**: White-box path analysis, contract regression stress testing, and edge condition fuzzing.

---

## Feature Inventory
| # | Feature | Source | Tier 1 | Tier 2 | Tier 3 |
|---|---------|--------|:------:|:------:|:------:|
| 1 | Design Token Alignment | ORIGINAL_REQUEST §1, AGENTS.md | 5 | 5 | ✓ |
| 2 | Bar Widget & Tooltip Elevation | ORIGINAL_REQUEST §1, §2 | 5 | 5 | ✓ |
| 3 | Panel Container & Hero Polish | ORIGINAL_REQUEST §1, §2 | 5 | 5 | ✓ |
| 4 | Modern Home Sliders & Badges | ORIGINAL_REQUEST §1, §2 | 5 | 5 | ✓ |
| 5 | Quick Snooze Pills & Live Countdown | ORIGINAL_REQUEST §2 | 5 | 5 | ✓ |
| 6 | Fluid Route Cross-Fade Transitions | ORIGINAL_REQUEST §2 | 5 | 5 | ✓ |
| 7 | Automation Route & Schedule Grid | ORIGINAL_REQUEST §1, §2 | 5 | 5 | ✓ |
| 8 | Settings Route & Shortcut Visuals | ORIGINAL_REQUEST §1, §3 | 5 | 5 | ✓ |
| 9 | Hybrid Navigation & Focus Traps | ORIGINAL_REQUEST §3 | 5 | 5 | ✓ |
| 10 | Dual i18n & Error Toast Polish | ORIGINAL_REQUEST §4, AGENTS.md | 5 | 5 | ✓ |
| 11 | Monotonic Request Bus Integrity | AGENTS.md | 5 | 5 | ✓ |
| 12 | Quality Gate & Packaging Validation | AGENTS.md | 5 | 5 | ✓ |

---

## Test Architecture
- **Test Runner Commands**:
  - Full automated test suite: `./scripts/check.sh`
  - Repository hygiene validation: `./scripts/check_hygiene.sh`
  - Plugin packaging validation: `omarchy-plugin-validate .`
  - QML static analysis & linting: `qmllint -I /usr/share/omarchy/shell BarWidget.qml Panel.qml NerdIcon.qml`
  - Node contract tests: `node --test tests/*.test.*`
  - Python test discovery: `python3 -m unittest discover -s tests -p "test_*.py"`
- **Pass / Fail Semantics**:
  - Zero test failures, zero warnings/errors from linters, 0 non-zero exit codes.
  - Strict layout contract compliance in `tests/layout.test.mjs`.
  - 100% i18n key parity between English and Spanish.

---

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Evening Sunset Ramp & Night Light Auto-Engagement | F1, F4, F7, F11 | High |
| 2 | Quick Snooze during Nighttime Task & Resumption | F4, F5, F2, F10 | Medium |
| 3 | Rapid Multi-Monitor Brightness & Temperature Adjustment | F4, F8, F11 | High |
| 4 | Full Hybrid Keyboard Walkthrough across All 3 Routes | F3, F6, F7, F8, F9 | High |
| 5 | Dual-Locale Switching & Error Toast Handling | F9, F10, F12 | Medium |

---

## Coverage Thresholds
- **Tier 1**: ≥60 test assertions across 12 features (≥5 per feature).
- **Tier 2**: ≥60 boundary test assertions (≥5 per feature).
- **Tier 3**: ≥12 cross-feature interaction test cases.
- **Tier 4**: ≥5 realistic end-to-end user workflows.
- **Tier 5**: Comprehensive adversarial stress testing and contract gap closure.
- **Total Suite Minimum**: ≥137 test cases / contract assertions.
