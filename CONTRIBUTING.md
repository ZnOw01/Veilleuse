# Contributing

Use the [README](README.md) for installation and panel usage, [PROJECT.md](PROJECT.md) for architecture and safety contracts, and [CLI.md](CLI.md) for the helper interface.

## Development environment

Clone the repository and work from its root:

```bash
git clone https://github.com/ZnOw01/Veilleuse.git
cd Veilleuse
```

Python 3.12+ and Node.js are required for the automated suites; CI uses Python 3.12 and Node 24. Python runtime code uses only the standard library, and Node tests use the built-in test runner. There is no package installation or build step.

For live UI verification, use Omarchy Quattro with Hyprland, Quickshell, its native QML components, and the display backends listed in the [README requirements](README.md#requirements). Install/enable the plugin through Omarchy tooling; executing `Panel.qml` alone does not provide the shell context.

## Verification

Run both required gates:

```bash
./scripts/check.sh
./scripts/check_hygiene.sh
```

To select a Python interpreter for both scripts:

```bash
PYTHON=python3.12 ./scripts/check.sh
PYTHON=python3.12 ./scripts/check_hygiene.sh
```

Use an interpreter installed on your system. The gate reports `SKIP` when `omarchy-plugin-validate` is missing or when `qmllint`/Omarchy QML imports are unavailable. A pass with a skip does not verify the skipped integration.

On an Omarchy host, you can run those validators directly:

```bash
qmllint -I /usr/share/omarchy/shell BarWidget.qml Panel.qml NerdIcon.qml
omarchy-plugin-validate .
```

The package validator rejects symlinks in the package. In a Git checkout, `check.sh` validates a temporary copy of tracked files, excluding ignored local tools; a direct validation of `.` may also inspect local files. See [TEST_INFRA.md](TEST_INFRA.md) for individual runners and coverage limits.

## Changes and pull requests

1. Make the change in the smallest relevant layer and preserve the CLI/UI contract.
2. Run both gates and review the full diff, including generated or untracked files.
3. For QML, shell integration, or package-entry changes, run host validations in Omarchy and exercise the changed controls manually.
4. In the pull request, describe the resulting behavior and the checks run, including optional validators that were skipped.

Use Conventional Commit titles, for example `fix(control): ...`, `feat(panel): ...`, `style(panel): ...`, `docs: ...`, or `chore(repo): ...`. Keep documentation accurate when changing commands, settings, or behavior. Preserve dated release and audit records rather than replacing historical results with current test counts.

## Safety contracts

- Keep Python runtime code dependency-free and avoid persistent background services.
- Preserve mode `0600` for private Veilleuse files and the locking/atomic-write behavior used for updates.
- Keep subprocess calls bounded and pass argument arrays; do not introduce shell-string execution.
- Preserve monotonic request IDs, mutation ordering, and fail-closed availability handling.
- Keep user-facing errors localized in English and Spanish when adding backend error codes.
- Preserve unmanaged configuration, backups, and interrupted schedule transaction recovery.

The current suites do not launch Quickshell or test real keyboard, accessibility, or rendering behavior. Include manual Omarchy verification results when a change affects those surfaces.
