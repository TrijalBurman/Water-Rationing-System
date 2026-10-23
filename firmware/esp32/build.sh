#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p .cache/tmp
export PLATFORMIO_CORE_DIR="$PWD/.platformio"
export PIP_CACHE_DIR="$PWD/.cache/pip"
export XDG_CACHE_HOME="$PWD/.cache"
export TMPDIR="$PWD/.cache/tmp"
export PYTHONDONTWRITEBYTECODE=1
if [[ -x .venv/bin/python ]]; then
  .venv/bin/python -m platformio run "$@"
else
  pio run "$@"
fi
