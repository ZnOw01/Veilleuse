# Test Coverage and Limits

The repository has deterministic Python unit tests plus Node.js tests for the JavaScript model and source-level UI contracts. These suites verify backend behavior, state transitions, request ordering, localization, and selected QML structure.

## What the Tests Exercise

- Python tests cover the helper CLI, automation, schedule parsing/toggling, shortcut handling, and state persistence.
- `UiModel.test.js` exercises normalization, validation, navigation-model behavior, request commits, and modeled scenarios.
- `layout.test.mjs` checks QML contracts by inspecting source text.
- `transitions.test.mjs` checks route and request-bus behavior through JavaScript test logic.
- `navigation_stress.test.mjs` uses a JavaScript harness to stress navigation and focus rules; it does not send input to a running panel.
- `i18n.test.js`, `errorCodes.test.js`, and `icons.test.mjs` check translation and glyph contracts.

No current test launches Quickshell, exercises real Qt focus/accessibility, or performs a GUI end-to-end workflow. Visual and real-device behavior still requires manual verification in Omarchy. The results below are a verification baseline, not a release certification or a GUI end-to-end result.

## Commands

The canonical local gate is `./scripts/check.sh`. It runs the Python and Node suites, validates the manifest JSON, checks package hygiene, and runs available host validators. Run `./scripts/check_hygiene.sh` directly for the packaging hygiene gate.

The test runners can be invoked independently:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
node --test tests/UiModel.test.js tests/layout.test.mjs tests/i18n.test.js tests/errorCodes.test.js tests/icons.test.mjs tests/transitions.test.mjs tests/navigation_stress.test.mjs
```

## Baseline

- Python: 382 unit tests pass across the five suites invoked by `scripts/check.sh` (`test_veilleuse_control`, `test_shortcut_utils`, `test_automation_utils`, `test_schedule_toggle_utils`, `test_state_utils`).
- Node.js: the built-in runner executes seven test files and reports 210 test cases. Those counts are test cases, not individual assertions.
- `scripts/check.sh` also runs manifest JSON parsing, package hygiene, and `git diff --check`.
- `omarchy-plugin-validate` and `qmllint` are host-dependent. The gate prints `SKIP` when unavailable; a skipped validator is not a pass.

Each run prints its own counts, so re-run the gate to confirm them after changing tests.

## Host-Dependent Validation

`check.sh` runs `omarchy-plugin-validate` only when installed. It runs `qmllint` only when the command and `/usr/share/omarchy/shell` are both available; that invocation checks `BarWidget.qml`, `Panel.qml`, and `NerdIcon.qml`. The script prints `SKIP` when a validator cannot run. A generic Ubuntu CI runner without Omarchy does not establish that those checks passed. Use an Omarchy environment to verify the plugin manifest and QML imports before release.
