# Verification baseline

The Python count below is the measured baseline at commit `e1c16e4`. The Node gate now includes the previously omitted navigation stress file, so its current inventory is seven files. This is not a release certification or a GUI end-to-end result.

## Baseline evidence

- Python: 357 unit tests pass across the five suites invoked by `scripts/check.sh`.
- Node.js: the built-in runner executes seven test files. Its summary reports test cases, not individual assertion counts.
- Package hygiene, manifest JSON parsing, and `git diff --check` run in `scripts/check.sh`.
- `omarchy-plugin-validate` and `qmllint` are host-dependent. The gate prints `SKIP` when unavailable; a skipped validator is not a pass.
- There is no automated test that starts Quickshell or validates real Qt interaction, accessibility, or rendering.

## Reproduce

```bash
./scripts/check.sh
./scripts/check_hygiene.sh
```

Run the full gate in an Omarchy environment to include plugin validation and QML linting. For exact suite coverage and standalone commands, see [TEST_INFRA.md](TEST_INFRA.md).
