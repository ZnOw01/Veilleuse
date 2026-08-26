#!/bin/bash
# Package hygiene gate shared by scripts/check.sh and CI.
#
# Fails on a clone that is not release-safe: missing or wrong package entry
# points, symlinks, or any __pycache__ / *.pyc bytecode cache left behind by
# running the python helpers outside the gate.
set -euo pipefail

TARGET=${1:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}
cd "$TARGET"

PYTHON="${PYTHON:-python3}"

if [[ ! -x scripts/veilleuse-control ]]; then
    echo "hygiene gate: scripts/veilleuse-control is not executable" >&2
    exit 1
fi

"$PYTHON" - <<'PY'
import json
from pathlib import Path

manifest = json.loads(Path("manifest.json").read_text(encoding="utf-8"))
assert manifest.get("schemaVersion") == 1, "manifest schemaVersion must be 1"
assert manifest.get("id") == "io.github.znow01.veilleuse", "manifest id mismatch"
assert manifest.get("name") == "Veilleuse", "manifest name mismatch"
assert manifest.get("entryPoints", {}).get("barWidget") == "BarWidget.qml", "manifest barWidget entryPoint mismatch"
assert bool(manifest.get("version")), "manifest version must not be empty"
PY

if find . -path ./.git -prune -o -type d \( -name .venv -o -name dist -o -name build -o -name .pytest_cache -o -name .ruff_cache -o -name .mypy_cache \) -prune -o -type l -print -quit | grep -q .; then
    echo "hygiene gate: symlink found in $TARGET" >&2
    exit 1
fi

if find . -path ./.git -prune -o -type d \( -name .venv -o -name dist -o -name build -o -name .pytest_cache -o -name .ruff_cache -o -name .mypy_cache \) -prune -o \( -name __pycache__ -o -name '*.pyc' \) -print -quit | grep -q .; then
    echo "hygiene gate: bytecode cache found in $TARGET" >&2
    exit 1
fi
