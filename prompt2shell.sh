#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
REQ_FILE="$SCRIPT_DIR/requirements.txt"
PYTHON_BIN="${PYTHON_BIN:-python3}"
ENV_FILE="$SCRIPT_DIR/.env"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

INSTALL_DEPS=0
CREATED_VENV=0
NEED_DEPS=0
RUN_TESTS=0
UPDATE_REQUIREMENTS=0
SHOW_HELP=0
ADD_ALIAS=0
END_OF_OPTIONS=0
FORWARDED_ARGS=()

for arg in "$@"; do
  if [ "$END_OF_OPTIONS" -eq 1 ]; then
    FORWARDED_ARGS+=("$arg")
    continue
  fi

  case "$arg" in
    --)
      END_OF_OPTIONS=1
      ;;
    --install)
      INSTALL_DEPS=1
      ;;
    --tests)
      RUN_TESTS=1
      ;;
    --update-requirements)
      UPDATE_REQUIREMENTS=1
      ;;
    --add-alias)
      ADD_ALIAS=1
      ;;
    -h|--help)
      SHOW_HELP=1
      ;;
    -m5)
      FORWARDED_ARGS+=("--model=gpt-5-mini")
      ;;
    *)
      FORWARDED_ARGS+=("$arg")
      ;;
  esac
done

detect_shell_profile() {
  local shell_name="${1:-$(basename "${SHELL:-}")}"
  case "$shell_name" in
    zsh)
      printf '%s\n' "$HOME/.zshrc"
      ;;
    fish)
      printf '%s\n' "$HOME/.config/fish/config.fish"
      ;;
    *)
      printf '%s\n' "$HOME/.bashrc"
      ;;
  esac
}

render_alias_line() {
  local shell_name="$1"
  local alias_target="$SCRIPT_DIR/prompt2shell.sh"
  case "$shell_name" in
    fish)
      printf "alias p2s '%s'\n" "$alias_target"
      ;;
    *)
      printf "alias p2s=%q\n" "$alias_target"
      ;;
  esac
}

add_p2s_alias() {
  local shell_name="${PROMPT2SHELL_ALIAS_SHELL:-$(basename "${SHELL:-bash}")}"
  local profile_file
  local alias_line
  local tmp_file

  profile_file="$(detect_shell_profile "$shell_name")"
  alias_line="$(render_alias_line "$shell_name")"

  mkdir -p "$(dirname "$profile_file")"
  if [ ! -f "$profile_file" ]; then
    touch "$profile_file"
  fi

  if grep -Fqx "$alias_line" "$profile_file"; then
    echo "[prompt2shell] Alias p2s already configured in $profile_file"
    return 0
  fi

  tmp_file="$(mktemp)"
  awk -v alias_line="$alias_line" '
    BEGIN { replaced = 0 }
    /^[[:space:]]*alias[[:space:]]+p2s[ =]/ {
      if (replaced == 0) {
        print alias_line
        replaced = 1
      }
      next
    }
    { print }
    END {
      if (replaced == 0) {
        print alias_line
      }
    }
  ' "$profile_file" > "$tmp_file"
  mv "$tmp_file" "$profile_file"

  echo "[prompt2shell] Configured alias p2s in $profile_file for shell $shell_name"
}

if [ "$SHOW_HELP" -eq 1 ]; then
  cat <<'EOF'
Usage: ./prompt2shell.sh [maintenance-options] [runtime-options] [--] [prompt...]

Maintenance options:
  --install               Create venv (if needed) and install deps from requirements.txt
  --tests                 Run unit tests (python -m unittest discover -s tests -v)
  --update-requirements   Upgrade required packages in .venv and rewrite requirements.txt
  --add-alias             Add/update alias p2s in the active shell profile
  --help                  Show this help message

Runtime options:
  -o, --once              Exit after processing the initial prompt
  --model=NAME            Override OpenAI model for this run
  --tokens=NUMBER         Override max output tokens for this run
  --config=PATH           Use a specific TOML config file
  --dry-run               Preview commands without executing them
  --explain-only          Show explanation and proposed commands without execution
  --report[=PATH]         Write a Markdown session report
  -m5                     Shortcut for --model=gpt-5-mini

Examples:
  ./prompt2shell.sh "find 3 largest files"
  ./prompt2shell.sh --dry-run "inspect recent logs"
  ./prompt2shell.sh --report ./logs/reports/run.md "summarize git status"
  ls | ./prompt2shell.sh
  ./prompt2shell.sh -- "prompt that starts with -"
EOF
  exit 0
fi

if [ "$ADD_ALIAS" -eq 1 ]; then
  add_p2s_alias
fi

if [ "$ADD_ALIAS" -eq 1 ] && [ "$INSTALL_DEPS" -eq 0 ] && [ "$RUN_TESTS" -eq 0 ] && [ "$UPDATE_REQUIREMENTS" -eq 0 ] && [ "${#FORWARDED_ARGS[@]}" -eq 0 ]; then
  exit 0
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "[prompt2shell] Creating virtualenv in $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  CREATED_VENV=1
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

if ! python - <<'PY'
import importlib.util

required_modules = ("openai", "termcolor", "distro", "prompt_toolkit")
missing = [name for name in required_modules if importlib.util.find_spec(name) is None]
if missing:
    print("[prompt2shell] Missing Python modules: " + ", ".join(missing))
    raise SystemExit(1)
PY
then
  NEED_DEPS=1
fi

if [ "$INSTALL_DEPS" -eq 1 ] || [ "$CREATED_VENV" -eq 1 ] || [ "$NEED_DEPS" -eq 1 ]; then
  if [ -f "$REQ_FILE" ]; then
    echo "[prompt2shell] Installing dependencies from requirements.txt"
    python -m pip install -r "$REQ_FILE"
  else
    echo "[prompt2shell] Missing $REQ_FILE - cannot install dependencies" >&2
    exit 1
  fi
fi

if [ "$UPDATE_REQUIREMENTS" -eq 1 ]; then
  echo "[prompt2shell] Upgrading core packages in virtualenv"
  python -m pip install --upgrade openai termcolor distro prompt_toolkit tomli
  echo "[prompt2shell] Writing pinned versions to requirements.txt"
  P2S_REQ_FILE="$REQ_FILE" python - <<'PY'
import os
from importlib.metadata import version

packages = ("openai", "termcolor", "distro", "prompt_toolkit", "tomli")
req_file = os.environ["P2S_REQ_FILE"]
lines = [f"{name}=={version(name)}" for name in packages]
with open(req_file, "w", encoding="utf-8") as handle:
    handle.write("\n".join(lines) + "\n")
print("[prompt2shell] Updated:", ", ".join(lines))
PY
fi

if [ "$RUN_TESTS" -eq 1 ]; then
  echo "[prompt2shell] Running tests"
  python -m unittest discover -s "$SCRIPT_DIR/tests" -v
fi

if [ "$RUN_TESTS" -eq 1 ] || [ "$UPDATE_REQUIREMENTS" -eq 1 ]; then
  if [ "${#FORWARDED_ARGS[@]}" -eq 0 ]; then
    exit 0
  fi
fi

if [ "${#FORWARDED_ARGS[@]}" -eq 0 ]; then
  exec python "$SCRIPT_DIR/prompt2shell.py"
fi

exec python "$SCRIPT_DIR/prompt2shell.py" "${FORWARDED_ARGS[@]}"
