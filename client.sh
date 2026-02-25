#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_EXE_DOTVENV="$SCRIPT_DIR/.venv/bin/python"
PY_EXE_VENV="$SCRIPT_DIR/venv/bin/python"
CLIENT_MAIN="$SCRIPT_DIR/client/main.py"

run_client() {
  if [[ -x "$PY_EXE_DOTVENV" ]]; then
    "$PY_EXE_DOTVENV" "$CLIENT_MAIN"
  elif [[ -x "$PY_EXE_VENV" ]]; then
    "$PY_EXE_VENV" "$CLIENT_MAIN"
  else
    echo "[WARN] No local venv Python found in .venv or venv."
    echo "[INFO] Falling back to python3/python..."
    if command -v python3 >/dev/null 2>&1; then
      python3 "$CLIENT_MAIN"
    elif command -v python >/dev/null 2>&1; then
      python "$CLIENT_MAIN"
    else
      echo "[ERROR] No Python executable found in PATH."
      return 1
    fi
  fi
}

run_client
status=$?
if [[ $status -ne 0 ]]; then
  echo
  echo "[ERROR] Client exited with an error (code: $status)."
  read -r -p "Press Enter to close..." _
fi

exit $status
