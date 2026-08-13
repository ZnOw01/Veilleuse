#!/bin/bash
# Package hygiene gate shared by scripts/check.sh and CI.
#
# Fails on a clone that is not release-safe: missing or wrong package entry
# points, symlinks, or any __pycache__ / *.pyc bytecode cache left behind by
# running the python helpers outside the gate.
set -euo pipefail

TARGET=${1:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}
cd "$TARGET"

[[ -x scripts/veilleuse-control ]]
[[ $(jq -r '.id' manifest.json) == io.github.znow01.veilleuse ]]
[[ $(jq -r '.entryPoints.barWidget' manifest.json) == BarWidget.qml ]]

if find . -path ./.git -prune -o -type d \( -name .venv -o -name dist -o -name build -o -name .pytest_cache \) -prune -o -type l -print -quit | grep -q .; then
    echo "hygiene gate: symlink found in $TARGET" >&2
    exit 1
fi

if find . -path ./.git -prune -o -type d \( -name .venv -o -name dist -o -name build -o -name .pytest_cache \) -prune -o \( -name __pycache__ -o -name '*.pyc' \) -print -quit | grep -q .; then
    echo "hygiene gate: bytecode cache found in $TARGET" >&2
    exit 1
fi
