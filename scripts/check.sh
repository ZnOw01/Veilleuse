#!/bin/bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 - <<'PY'
from pathlib import Path
for path in (Path('scripts/veilleuse-control'), Path('scripts/schedule_utils.py')):
    compile(path.read_text(encoding='utf-8'), str(path), 'exec')
PY
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest discover -s tests -p 'test_veilleuse_control.py'
node --test tests/UiModel.test.js tests/model.test.mjs tests/layout.test.mjs
/usr/bin/python3 -m json.tool manifest.json >/dev/null

if command -v omarchy-plugin-validate >/dev/null 2>&1; then
  PACKAGE_TMP=$(mktemp -d)
  trap 'rm -rf "$PACKAGE_TMP"' EXIT
  git ls-files -z | tar --null -T - -cf - | tar -xf - -C "$PACKAGE_TMP"
  omarchy-plugin-validate "$PACKAGE_TMP"
fi
if command -v qmllint >/dev/null 2>&1 && [[ -d /usr/share/omarchy/shell ]]; then
  qmllint -I /usr/share/omarchy/shell BarWidget.qml Panel.qml
fi

[[ -x scripts/veilleuse-control ]]
[[ $(jq -r '.id' manifest.json) == io.github.ZnOw01.veilleuse ]]
[[ $(jq -r '.entryPoints.barWidget' manifest.json) == BarWidget.qml ]]
! find . -path ./.git -prune -o -type d \( -name .venv -o -name dist -o -name build -o -name .pytest_cache \) -prune -o -type l -print -quit | grep -q .
! find . -path ./.git -prune -o -type d \( -name .venv -o -name dist -o -name build -o -name .pytest_cache \) -prune -o \( -name __pycache__ -o -name '*.pyc' \) -print -quit | grep -q .

git diff --check
printf 'Veilleuse plugin checks passed.\n'
