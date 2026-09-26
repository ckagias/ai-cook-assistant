#!/usr/bin/env bash
# One-command setup: creates/repairs the venv, installs everything (base + object/hand
# detection + models), prepares .env, runs the test suite, and prints next steps.
#
# Safe to re-run: packages already installed at the required version are not downloaded
# again; a package whose required version changed gets the new version, and the old one's
# wheel is kept in .wheelhouse/ (never deleted). Models are only ever added to backend/models/.
#
# Flags, in any order:
#   --no-detection   skip the ~1 GB detection stack (torch, ultralytics, mediapipe) and models
#   --skip-tests     don't run the test suite at the end
#   --run            start uvicorn in the foreground afterwards (see also ./setup-window.sh)
#   --no-summary     skip the closing "what it does / how to use it" summary
set -uo pipefail

RED='\033[0;31m'
NC='\033[0m'
export PIP_DISABLE_PIP_VERSION_CHECK=1  # pip's "new release available" notice is noise here

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/backend" || exit 1

WITH_DETECTION=1
RUN_SERVER=0
RUN_TESTS=1
SHOW_SUMMARY=1
for arg in "$@"; do
  case "$arg" in
    --no-detection) WITH_DETECTION=0 ;;
    --with-detection) WITH_DETECTION=1 ;;  # the default now; kept so old commands still work
    --skip-tests) RUN_TESTS=0 ;;
    --run) RUN_SERVER=1 ;;
    --no-summary) SHOW_SUMMARY=0 ;;  # setup-window prints its own links instead
  esac
done

# --- 1. find a usable Python. Detection needs 3.11/3.12 (mediapipe has no 3.13+ wheels yet),
#        so prefer those; anything 3.10+ still runs the base app. ---
python_ok() {  # $@ = command; exit 0 if it runs Python 3.10 or newer
  "$@" -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] else 1)" >/dev/null 2>&1
}
find_python() {
  for candidate in "py -3.12" "python3.12" "py -3.11" "python3.11" "python3" "python" "py"; do
    # shellcheck disable=SC2086
    if command -v ${candidate%% *} >/dev/null 2>&1 && python_ok $candidate; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

PYTHON="$(find_python)"
if [ -z "$PYTHON" ]; then
  echo -e "${RED}ERROR: no Python 3.10+ found (tried 3.12, 3.11, python3, python, py).${NC}" >&2
  exit 1
fi
# shellcheck disable=SC2086
echo "Using Python: $($PYTHON -c 'import sys; print(sys.executable, sys.version.split()[0])')"

# --- 2. which venv: one per OS, side by side. A Windows venv is useless from WSL/Linux and vice
#        versa - and an existing environment is never deleted, only ever set aside. ---
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) PLATFORM=windows; LAYOUT=Scripts; PYEXE=python.exe ;;
  Darwin) PLATFORM=macos; LAYOUT=bin; PYEXE=python ;;
  *) PLATFORM=linux; LAYOUT=bin; PYEXE=python ;;
esac
VENV_DIR=".venv"
if [ -d ".venv" ] && [ ! -d ".venv/$LAYOUT" ]; then
  VENV_DIR=".venv-$PLATFORM"  # .venv was made by another OS (e.g. Windows, seen from WSL): leave it alone
  echo "backend/.venv belongs to another operating system - using backend/$VENV_DIR for $PLATFORM."
fi
VENV_PYTHON="$VENV_DIR/$LAYOUT/$PYEXE"

set_aside() {  # $1 = reason. Renames, never deletes: the old environment stays on disk.
  local aside
  aside="$VENV_DIR.$1-$(date +%Y%m%d-%H%M%S)"
  mv "$VENV_DIR" "$aside" && echo -e "${RED}Moved the old environment to backend/$aside (delete it yourself once the new one works).${NC}" >&2
}

# --- 3. a venv whose project moved (its recorded path no longer exists) or whose Python no
#        longer starts is set aside and rebuilt - from .wheelhouse/, so without re-downloading ---
if [ -f "$VENV_DIR/pyvenv.cfg" ]; then
  # tr -d '\r': a pyvenv.cfg written on Windows has CRLF line endings.
  RECORDED_DIR="$(grep '^command = ' "$VENV_DIR/pyvenv.cfg" | tr -d '\r' | sed 's/.*-m venv //' || true)"
  if [ -n "$RECORDED_DIR" ] && [ ! -d "$RECORDED_DIR" ]; then
    echo -e "${RED}WARNING: $VENV_DIR was created at '$RECORDED_DIR', which no longer exists (the project was moved or copied).${NC}" >&2
    set_aside moved
  elif ! "$VENV_PYTHON" -c "import sys" >/dev/null 2>&1; then
    echo -e "${RED}WARNING: $VENV_DIR's Python no longer starts.${NC}" >&2
    set_aside broken
  fi
fi

# --- 4. CPU-only torch on Linux without an NVIDIA GPU: PyPI's default Linux torch bundles CUDA
#        (~2.5 GB); the CPU build is ~200 MB and just as fast on a CPU. ---
if [ "$PLATFORM" = "linux" ] && ! command -v nvidia-smi >/dev/null 2>&1; then
  export PIP_EXTRA_INDEX_URL="https://download.pytorch.org/whl/cpu"
fi

# --- 5. create the venv if missing, install what's missing or at the wrong version ---
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment ($VENV_DIR)..."
  # shellcheck disable=SC2086
  $PYTHON -m venv "$VENV_DIR" || exit 1
fi

if [ "$WITH_DETECTION" = "1" ] && ! "$VENV_PYTHON" -c "import sys; sys.exit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) else 1)"; then
  echo -e "${RED}WARNING: $VENV_DIR uses Python $("$VENV_PYTHON" -c 'import sys; print(sys.version.split()[0])') - detection needs 3.11 or 3.12 (mediapipe). Installing the base app only; install Python 3.12 and rename backend/$VENV_DIR to get detection.${NC}" >&2
  WITH_DETECTION=0
fi

# pip >= 23 for `install --dry-run --report`, which is how already-installed packages are skipped.
"$VENV_PYTHON" -m pip install -q "pip>=23"

REQUIREMENTS=(requirements.txt)
[ "$WITH_DETECTION" = "1" ] && REQUIREMENTS+=(requirements-detect.txt)
echo "Checking dependencies (${REQUIREMENTS[*]})..."
"$VENV_PYTHON" scripts/sync_deps.py "${REQUIREMENTS[@]}" || { echo -e "${RED}Dependency install failed - see above.${NC}" >&2; exit 1; }

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

# --- 7. models for the configured detector (download/export once; nothing is ever deleted) ---
if [ "$WITH_DETECTION" = "1" ]; then
  echo "Checking detection models..."
  "$VENV_PYTHON" scripts/fetch_models.py || echo -e "${RED}WARNING: model download/export failed - /detect will retry on first use.${NC}" >&2
fi

# --- 8. local recipe database (created + seeded from data/recipes.json on first run) ---
"$VENV_PYTHON" scripts/db_init.py || echo -e "${RED}WARNING: database setup failed - see above.${NC}" >&2

# --- 9. run the test suite; PIPESTATUS[0], not tail's own exit code, decides pass/fail ---
if [ "$RUN_TESTS" = "1" ]; then
  echo "Running tests..."
  "$VENV_PYTHON" -m pytest tests -q -p no:warnings -p no:cacheprovider | tail -3
  TEST_EXIT_CODE=${PIPESTATUS[0]}
  if [ "$TEST_EXIT_CODE" -ne 0 ]; then
    echo -e "${RED}Tests failed (exit code $TEST_EXIT_CODE) - see above.${NC}" >&2
  else
    echo "Tests passed."
  fi
fi

# --- 10. what the system does, where to open it, how to use it, and this install's status ---
if [ "$SHOW_SUMMARY" = "1" ]; then
  PYTHONIOENCODING=utf-8 "$VENV_PYTHON" scripts/usage.py --shell sh --python "backend/$VENV_PYTHON"
fi

# --- 11. --run: exec uvicorn in the foreground afterward ---
if [ "$RUN_SERVER" = "1" ]; then
  URL="http://localhost:${BACKEND_PORT:-8000}/"
  [ -n "${BACKEND_PAIRING_TOKEN:-}" ] && URL="${URL}?token=${BACKEND_PAIRING_TOKEN}"
  echo "Starting the server - open $URL  (Ctrl+C stops it)"
  exec "$VENV_PYTHON" -m uvicorn app.main:app --host "${BACKEND_HOST:-0.0.0.0}" --port "${BACKEND_PORT:-8000}"
fi
