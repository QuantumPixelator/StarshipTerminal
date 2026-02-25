#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_EXE_DOTVENV="$SCRIPT_DIR/.venv/bin/python"
PY_EXE_VENV="$SCRIPT_DIR/venv/bin/python"
SERVER_MAIN="$SCRIPT_DIR/server/game_server_auth.py"

if [[ -x "$PY_EXE_DOTVENV" ]]; then
  "$PY_EXE_DOTVENV" "$SERVER_MAIN"
elif [[ -x "$PY_EXE_VENV" ]]; then
  "$PY_EXE_VENV" "$SERVER_MAIN"
else
  echo "[WARN] No local venv Python found in .venv or venv."
  echo "[INFO] Falling back to python3/python..."
  if command -v python3 >/dev/null 2>&1; then
    python3 "$SERVER_MAIN"
  elif command -v python >/dev/null 2>&1; then
    python "$SERVER_MAIN"
  else
    echo "[ERROR] No Python executable found in PATH."
    exit 1
  fi
fi
