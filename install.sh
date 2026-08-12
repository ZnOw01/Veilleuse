#!/usr/bin/env bash
set -euo pipefail
# Native Veilleuse installer (Omarchy 4). See docs/ARCHITECTURE.md.
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec /usr/bin/python3 "$ROOT/scripts/install.py"
