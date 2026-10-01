# Test coverage and limits

The repository has deterministic Python unit tests plus Node.js tests for the JavaScript model and source-level UI contracts. These suites verify backend behavior, state transitions, request ordering, localization, and selected QML structure.

## Coverage

- Python tests cover the helper CLI, automation, schedule parsing/toggling, shortcut handling, and state persistence.
- `UiModel.test.js` exercises normalization, validation, navigation-model behavior, request commits, and modeled scenarios.
- `layout.test.mjs` checks QML contracts by inspecting source text and executes selected panel JavaScript handlers in Node's VM for response, refresh, and timer regressions. It does not instantiate Qt objects.
- `transitions.test.mjs` checks route and request-bus behavior through JavaScript test logic.
- `navigation_stress.test.mjs` uses a JavaScript harness to stress navigation and focus rules; it does not send input to a running panel.
- `i18n.test.js`, `errorCodes.test.js`, and `icons.test.mjs` check translation and glyph contracts.

No current test launches Quickshell, exercises real Qt focus/accessibility, or performs a GUI end-to-end workflow. Visual and real-device behavior still requires manual verification in Omarchy. Each run prints current test counts. Historical verification results are recorded in [AUDIT.md](AUDIT.md#verification-and-limits).

## Commands

Run the required gates from the repository root:

```bash
./scripts/check.sh
./scripts/check_hygiene.sh
```

`check.sh` compiles all six Python source files without writing bytecode, runs the Python and Node suites, parses the manifest JSON, runs available host validators, checks package hygiene, and runs `git diff --check`. The hygiene gate checks the helper's executable bit and manifest fields and rejects symlinks and Python bytecode outside excluded tool directories. It also accepts an optional package-directory argument.

The test runners can be invoked independently:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
node --test tests/UiModel.test.js tests/layout.test.mjs tests/i18n.test.js tests/errorCodes.test.js tests/icons.test.mjs tests/transitions.test.mjs tests/navigation_stress.test.mjs
```

## Host-dependent validation

`check.sh` runs `omarchy-plugin-validate` only when installed. It runs `qmllint` only when the command and `/usr/share/omarchy/shell` are both available; that invocation checks `BarWidget.qml`, `Panel.qml`, and `NerdIcon.qml`. The script prints `SKIP` when a validator cannot run. A generic Ubuntu CI runner without Omarchy does not establish that those checks passed. Use an Omarchy environment to verify the plugin manifest and QML imports before release.

## Manual verification

For changes to the panel, verify opening/closing, all three views, pointer/keyboard focus, dropdowns, and both languages in a running Omarchy session. For display and automation changes, check readback on the intended monitor, schedule transitions, snooze expiration, and shortcut installation/removal as applicable. Record the conditions and results; source-level tests cannot establish physical display behavior.

See [CONTRIBUTING.md](CONTRIBUTING.md) for environment setup and review expectations.
