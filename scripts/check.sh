#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

printf '%s\n' '→ Python syntax'
/usr/bin/python3 -m py_compile src/night_light_control.py src/brightness_control.py src/brightness_utils.py src/schedule_utils.py src/hyprsunset_backend.py bin/night-light-toggle bin/night-light-status bin/night-light bin/brightness-step scripts/install.py scripts/uninstall.py

printf '%s\n' '→ Unit tests'
/usr/bin/python3 -m unittest discover -s tests -p 'test_*.py' -v

printf '%s\n' '→ Shell syntax'
bash -n install.sh uninstall.sh scripts/check.sh

printf '%s\n' '→ Desktop entry'
tmp="$(mktemp --suffix=.desktop)"
brightness_tmp="$(mktemp --suffix=.desktop)"
trap 'rm -f "$tmp" "$brightness_tmp"' EXIT
sed "s|@APP_EXEC@|$HOME/.local/bin/night-light-control|" data/night-light-control.desktop.in > "$tmp"
sed "s|@BRIGHTNESS_EXEC@|$HOME/.local/bin/brightness-control|" data/brightness-control.desktop.in > "$brightness_tmp"
desktop-file-validate "$tmp" "$brightness_tmp"

printf '%s\n' '→ Safety and portability'
if grep -R --line-number --exclude-dir='__pycache__' --exclude='*.pyc' \
  -E '/home/[^/]+|shell[[:space:]]*=[[:space:]]*True|os\.system\(|eval\(|exec\(' \
  src bin scripts/install.py scripts/uninstall.py install.sh uninstall.sh data/night-light-control.desktop.in; then
  printf '%s\n' 'Unsafe or non-portable pattern detected.' >&2
  exit 1
fi

printf '%s\n' '→ Schedule template'
/usr/bin/python3 - <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, "src")
from schedule_utils import day_profile_is_identity, iter_profile_blocks, parse_schedule_text, profile_info, profile_kind

text = Path("data/hyprsunset.conf").read_text(encoding="utf-8")
schedule = parse_schedule_text(text, strict=True)
if schedule != {
    "day_time": "06:00",
    "day_temp": 6000,
    "night_time": "15:30",
    "night_temp": 3500,
}:
    raise SystemExit("Unexpected schedule template values")
if not day_profile_is_identity(text):
    raise SystemExit("The daylight profile must use identity = true")
for _start, _end, profile in iter_profile_blocks(text):
    info = profile_info(profile)
    if profile_kind(info) == "day" and info["identity"] is True and info["temperature"] is not None:
        raise SystemExit("The identity daylight profile must not apply a temperature filter")
PY

printf '%s\n' '→ Runtime status JSON'
if systemctl --user is-active --quiet hyprsunset.service; then
  bin/night-light-status | /usr/bin/python3 -m json.tool >/dev/null
fi

printf '%s\n' '✓ All checks passed.'
