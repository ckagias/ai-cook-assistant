#!/usr/bin/env bash
# One-command setup: creates/repairs the venv, installs deps, prepares .env,
# runs the test suite, and prints next steps. Safe to re-run repeatedly.
set -uo pipefail

RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/backend" || exit 1

# --- 1. find a usable Python (3.10+), verified via sys.version_info, not --version string parsing ---
find_python() {
  for candidate in python3 python py; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
        echo "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

PYTHON="$(find_python)"
if [ -z "$PYTHON" ]; then
  echo -e "${RED}ERROR: no Python 3.10+ found (tried python3, python, py).${NC}" >&2
  exit 1
fi
echo "Using Python: $($PYTHON -c 'import sys; print(sys.executable, sys.version.split()[0])')"

# --- 2/3. Windows venv layout (Scripts/+python.exe) vs POSIX (bin/+python) ---
if [ -d ".venv/Scripts" ] || [ "${OS:-}" = "Windows_NT" ]; then
  VENV_PYTHON=".venv/Scripts/python.exe"
else
  VENV_PYTHON=".venv/bin/python"
fi

# --- 4. stale-venv detection: a venv baked with an absolute path that later
# moves silently falls through to the system Python with no error ---
if [ -f ".venv/pyvenv.cfg" ]; then
  CMD_LINE="$(grep '^command = ' ".venv/pyvenv.cfg" || true)"
  if [ -n "$CMD_LINE" ]; then
    # Not a naive last-token split - a Windows path with spaces would look truncated.
    RECORDED_DIR="$(echo "$CMD_LINE" | sed 's/.*-m venv //')"
    if [ -n "$RECORDED_DIR" ] && [ ! -d "$RECORDED_DIR" ]; then
      echo -e "${RED}WARNING: .venv looks stale - it was created at '$RECORDED_DIR', which no longer exists (the project was likely moved or copied). Recreating .venv...${NC}" >&2
      rm -rf .venv
    fi
  fi
fi

# --- 5. create .venv if missing, install deps ---
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  "$PYTHON" -m venv .venv || exit 1
fi

echo "Installing dependencies..."
"$VENV_PYTHON" -m pip install --upgrade pip -q
"$VENV_PYTHON" -m pip install -r requirements.txt -q

# --- 6. .env from .env.example, plus loud warnings for common footguns ---
if [ ! -f ".env" ]; then
  cp ".env.example" ".env"
  echo "Created .env from .env.example"
fi

if grep -qE '^[A-Za-z_]*_API_KEY=.+' ".env.example"; then
  echo -e "${RED}WARNING: .env.example contains a non-empty *_API_KEY= line. .env.example is git-tracked and looks identical to .env in an editor - move any real key into .env instead, never .env.example.${NC}" >&2
fi

if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a

  case "${VISION_PROVIDER:-}" in
    anthropic) KEY_VAR="ANTHROPIC_API_KEY"; KEY_VALUE="${ANTHROPIC_API_KEY:-}" ;;
    openai) KEY_VAR="OPENAI_API_KEY"; KEY_VALUE="${OPENAI_API_KEY:-}" ;;
    gemini) KEY_VAR="GEMINI_API_KEY or GOOGLE_API_KEY"; KEY_VALUE="${GEMINI_API_KEY:-}${GOOGLE_API_KEY:-}" ;;
    *) KEY_VAR=""; KEY_VALUE="" ;;
  esac
  if [ -n "$KEY_VAR" ] && [ -z "$KEY_VALUE" ]; then
    echo -e "${RED}WARNING: VISION_PROVIDER=${VISION_PROVIDER:-} but $KEY_VAR is empty in .env${NC}" >&2
  fi
fi

# --- 7. run the test suite; PIPESTATUS[0], not tail's own exit code, decides pass/fail ---
echo "Running tests..."
"$VENV_PYTHON" -m pytest tests -q -p no:warnings | tail -3
TEST_EXIT_CODE=${PIPESTATUS[0]}
if [ "$TEST_EXIT_CODE" -ne 0 ]; then
  echo -e "${RED}Tests failed (exit code $TEST_EXIT_CODE) - see above.${NC}" >&2
else
  echo "Tests passed."
fi

# --- 8. next steps ---
echo ""
echo "Setup complete. Next steps:"
echo "  1. Edit backend/.env and add your provider API key(s)."
echo "  2. Verify providers: $VENV_PYTHON scripts/check_providers.py"
echo "  3. Start the server: $VENV_PYTHON -m uvicorn app.main:app --host \${BACKEND_HOST:-0.0.0.0} --port \${BACKEND_PORT:-8000}"
echo "     (or re-run this script with --run to do that automatically)"
echo "  4. Reach it from an Android tablet over USB: adb reverse tcp:8000 tcp:8000"
echo "  5. Open http://localhost:8000/probe.html on the tablet to check capabilities."

# --- 9. --run: exec uvicorn in the foreground afterward ---
if [ "${1:-}" = "--run" ]; then
  echo ""
  echo "Starting server..."
  exec "$VENV_PYTHON" -m uvicorn app.main:app --host "${BACKEND_HOST:-0.0.0.0}" --port "${BACKEND_PORT:-8000}"
fi
