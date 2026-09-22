# Contributing

## Before opening a pull request

1. Make the change in the smallest relevant layer and preserve the existing CLI/UI contract.
2. Run `./scripts/check.sh` and `./scripts/check_hygiene.sh` from the repository root.
3. Review the full diff, including generated or untracked files, and confirm that only intended files changed.
4. For QML, shell integration, or package-entry changes, run the host validations in an Omarchy environment and exercise the changed control manually.
5. In the pull request, state the commands run and whether each optional validator ran or was skipped. Do not describe the source-contract/model suites as GUI end-to-end tests.

## Environment and verification

The automated gate needs Python 3.12+, Node.js 24, and the standard library only for Python runtime code. `scripts/check.sh` reports a `SKIP` when `omarchy-plugin-validate` is missing or when `qmllint`/Omarchy QML imports are unavailable. A pass with a skip does not verify the skipped integration.

To exercise those integration checks, use Omarchy with the plugin validator and `qmllint` available, then run:

```bash
./scripts/check.sh
qmllint -I /usr/share/omarchy/shell BarWidget.qml Panel.qml NerdIcon.qml
omarchy-plugin-validate .
```

The last two commands are explicit for review evidence; they may duplicate checks already run by `check.sh`.

## Safety and review expectations

- Keep Python runtime code dependency-free and avoid persistent background services.
- Preserve mode `0600` for private Veilleuse configuration/state and the locking/atomic-write behavior used for state updates.
- Keep subprocess calls bounded and pass argument arrays; do not introduce shell-string execution.
- Preserve monotonic request IDs and fail-closed behavior when backend state is unavailable.
- Keep user-facing errors localized in English and Spanish when adding backend error codes.
- Use focused Conventional Commit titles when creating commits: `feat(scope):`, `fix(scope):`, `docs(scope):`, or `chore(scope):`.

The current suites do not launch Quickshell or test real keyboard, screen-reader, or rendering behavior. When a change affects those surfaces, include manual Omarchy verification steps and results in the pull request.
