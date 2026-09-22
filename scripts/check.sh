#!/bin/bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

PYTHON="${PYTHON:-python3}"

PYTHONDONTWRITEBYTECODE=1 "$PYTHON" - <<'PY'
from pathlib import Path
for path in (
    Path('scripts/veilleuse-control'),
    Path('scripts/schedule_utils.py'),
    Path('scripts/schedule_toggle_utils.py'),
    Path('scripts/shortcut_utils.py'),
    Path('scripts/automation_utils.py'),
    Path('scripts/state_utils.py'),
):
    compile(path.read_text(encoding='utf-8'), str(path), 'exec')
PY
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m unittest discover -s tests -p 'test_veilleuse_control.py'
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m unittest discover -s tests -p test_automation_utils.py
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m unittest discover -s tests -p test_state_utils.py
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m unittest discover -s tests -p 'test_schedule_toggle_utils.py'
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m unittest discover -s tests -p 'test_shortcut_utils.py'
node --test tests/UiModel.test.js tests/layout.test.mjs tests/i18n.test.js tests/errorCodes.test.js tests/icons.test.mjs tests/transitions.test.mjs tests/navigation_stress.test.mjs
"$PYTHON" -m json.tool manifest.json >/dev/null

if command -v omarchy-plugin-validate >/dev/null 2>&1; then
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    PACKAGE_TMP=$(mktemp -d)
    trap 'rm -rf "$PACKAGE_TMP"' EXIT
    git ls-files -z | tar --null -T - -cf - | tar -xf - -C "$PACKAGE_TMP"
    omarchy-plugin-validate "$PACKAGE_TMP"
  else
    omarchy-plugin-validate "$ROOT"
  fi
else
  printf 'SKIP: omarchy-plugin-validate is not installed; package manifest validation did not run.\n' >&2
fi
if ! command -v qmllint >/dev/null 2>&1; then
  printf 'SKIP: qmllint is not installed; QML static analysis did not run.\n' >&2
elif [[ ! -d /usr/share/omarchy/shell ]]; then
  printf 'SKIP: /usr/share/omarchy/shell is unavailable; Omarchy QML imports were not linted.\n' >&2
else
  qmllint -I /usr/share/omarchy/shell BarWidget.qml Panel.qml NerdIcon.qml
fi

./scripts/check_hygiene.sh

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git diff --check
fi
printf 'Veilleuse plugin checks passed.\n'
