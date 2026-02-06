#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
REQ_FILE="$SCRIPT_DIR/requirements.txt"
PYTHON_BIN="${PYTHON_BIN:-python3}"
INSTALL_DEPS=0
FORWARDED_ARGS=()

for arg in "$@"; do
  if [ "$arg" = "install" ] || [ "$arg" = "--install" ]; then
    INSTALL_DEPS=1
    continue
  fi
  FORWARDED_ARGS+=("$arg")
done

if [ ! -d "$VENV_DIR" ]; then
  echo "[prompt2shell-agent] Tworze virtualenv w $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

if [ "$INSTALL_DEPS" -eq 1 ]; then
  if [ -f "$REQ_FILE" ]; then
    echo "[prompt2shell-agent] Instaluje zaleznosci z requirements.txt"
    pip install -r "$REQ_FILE"
  else
    echo "[prompt2shell-agent] Brak $REQ_FILE - pomijam instalacje zaleznosci" >&2
  fi
fi

exec python "$SCRIPT_DIR/prompt2shell-agent.py" "${FORWARDED_ARGS[@]}"
