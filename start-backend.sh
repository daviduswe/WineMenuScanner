#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR/backend"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

PY="./.venv/bin/python"
PIP="./.venv/bin/pip"

"$PY" -m pip install --upgrade pip
"$PIP" install -r requirements.txt

exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
