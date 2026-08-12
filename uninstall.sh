#!/usr/bin/env bash
set -euo pipefail
# Native Veilleuse uninstaller (Omarchy 4). Supports --dry-run.
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec /usr/bin/python3 "$ROOT/scripts/uninstall.py" "$@"
