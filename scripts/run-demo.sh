#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
if [[ ! -x .venv/bin/python ]]; then
  echo 'First run ./scripts/setup.sh to create the local Python environment.' >&2
  exit 1
fi
export TMPDIR="$PWD/.runtime"
export XDG_CACHE_HOME="$PWD/.cache"
export APP_MODE=demo DEMO_AUTOSTART=true MQTT_HOST= INFLUX_URL=
# Explicit empty key for the local-only demo; deployment uses its generated key.
export API_KEY=
exec .venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port "${PORT:-8000}"
