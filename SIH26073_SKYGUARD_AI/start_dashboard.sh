#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
VENV_DIR=.venv
if [ ! -x "$VENV_DIR/bin/python" ] && [ -x ../.venv/bin/python ]; then VENV_DIR=../.venv; fi
if [ ! -x "$VENV_DIR/bin/python" ]; then python3 -m venv .venv; VENV_DIR=.venv; fi
if [ ! -e "$VENV_DIR/.sih26073_requirements_v5" ]; then
  "$VENV_DIR/bin/python" -m pip install -r backend/requirements.txt
  touch "$VENV_DIR/.sih26073_requirements_v5"
fi
echo "Open http://127.0.0.1:8000 and keep this terminal open."
"$VENV_DIR/bin/python" -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
