#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
mkdir -p .runtime .cache data
export TMPDIR="$PWD/.runtime" PIP_CACHE_DIR="$PWD/.cache/pip" XDG_CACHE_HOME="$PWD/.cache"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv --without-pip .venv
fi
if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  if ! .venv/bin/python -m ensurepip --upgrade >/dev/null 2>&1; then
    echo 'Installing pip into the project environment from bootstrap.pypa.io...'
    curl -fsSL https://bootstrap.pypa.io/get-pip.py -o .runtime/get-pip.py
    .venv/bin/python .runtime/get-pip.py
  fi
fi
.venv/bin/python -m pip install -c requirements.lock -e '.[dev]'
echo 'Ready. Run ./scripts/run-demo.sh and open http://127.0.0.1:8000.'
