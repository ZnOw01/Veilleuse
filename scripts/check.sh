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

./scripts/check_hygiene.sh

git diff --check
printf 'Veilleuse plugin checks passed.\n'
