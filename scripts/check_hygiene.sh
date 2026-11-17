#!/bin/bash
# Package gate shared by local checks and CI: validate the manifest and helper
# permissions, then reject symlinks and bytecode outside excluded tool directories.
set -euo pipefail

TARGET=${1:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}
cd "$TARGET"

PYTHON="${PYTHON:-python3}"

if [[ ! -x scripts/veilleuse-control ]]; then
    echo "hygiene gate: scripts/veilleuse-control is not executable" >&2
    exit 1
fi

if [[ -f scripts/release.py && ! -x scripts/release.py ]]; then
    echo "hygiene gate: scripts/release.py is not executable" >&2
    exit 1
fi

"$PYTHON" - <<'PY'
import json
import re
from pathlib import Path

manifest = json.loads(Path("manifest.json").read_text(encoding="utf-8"))
assert manifest.get("schemaVersion") == 1, "manifest schemaVersion must be 1"
assert manifest.get("id") == "io.github.znow01.veilleuse", "manifest id mismatch"
assert manifest.get("name") == "Veilleuse", "manifest name mismatch"
assert manifest.get("entryPoints", {}).get("barWidget") == "BarWidget.qml", "manifest barWidget entryPoint mismatch"
version = manifest.get("version")
assert isinstance(version, str) and re.fullmatch(r"\d+\.\d+\.\d+", version), f"manifest version must be SemVer X.Y.Z, got {version!r}"
PY

PRUNE_DIRS=( -name .venv -o -name venv -o -name ENV -o -name node_modules -o -name dist -o -name build -o -name .pytest_cache -o -name .ruff_cache -o -name .mypy_cache )

if find . -path ./.git -prune -o -type d \( "${PRUNE_DIRS[@]}" \) -prune -o -type l -print -quit | grep -q .; then
    echo "hygiene gate: symlink found in $TARGET" >&2
    exit 1
fi

if find . -path ./.git -prune -o -type d \( "${PRUNE_DIRS[@]}" \) -prune -o \( -name __pycache__ -o -name '*.pyc' \) -print -quit | grep -q .; then
    echo "hygiene gate: bytecode cache found in $TARGET" >&2
    exit 1
fi
