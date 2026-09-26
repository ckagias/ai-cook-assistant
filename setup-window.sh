#!/usr/bin/env bash
# Set everything up, then run the whole app on this machine's network address and open it in
# its own app window (Edge/Chrome app mode: no address bar, own taskbar icon).
#
#   ./setup-window.sh                  # setup (no tests) + HTTPS server on the LAN + app window
#   ./setup-window.sh --no-detection   # same, without the object/hand detection stack
#
# On Windows, PowerShell users can run .\setup-window.ps1 (or double-click setup-window.cmd)
# instead - same behavior. From WSL this script hands over to that Windows launcher, because the
# camera, the browser window and the network card phones can reach all belong to Windows.
#
# - Serves https://<this machine's LAN IP>:8443 (BACKEND_HTTPS_PORT to change): phones and
#   tablets on the same Wi-Fi can open the printed link. HTTPS is required - browsers only
#   allow the camera on a non-localhost address over HTTPS.
# - Uses a self-signed certificate made for this LAN IP (backend/certs/, kept per IP). The app
#   window trusts exactly that certificate; a phone shows a warning once - accept it.
# - Reachable from the network means it's protected: a pairing token is generated into
#   backend/.env if none is set, and the printed links carry it.
# - Closing the app window stops the server.
set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- 0. WSL: run the Windows launcher instead ---
if grep -qi microsoft /proc/version 2>/dev/null; then
  PS_ARGS=()
  for arg in "$@"; do [ "$arg" = "--no-detection" ] && PS_ARGS+=(-NoDetection); done
  if command -v powershell.exe >/dev/null 2>&1 && [[ "$SCRIPT_DIR" == /mnt/* ]]; then
    echo "WSL detected - the camera, browser window and network are Windows', so starting setup-window.ps1 on Windows..."
    exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$SCRIPT_DIR/setup-window.ps1")" "${PS_ARGS[@]}"
  fi
  echo -e "${RED}ERROR: from WSL the app window must run on Windows. Open PowerShell in the project folder and run: .\\setup-window.ps1${NC}" >&2
  exit 1
fi

RUN_DIR="$SCRIPT_DIR/.run"
mkdir -p "$RUN_DIR"

# --- 1. setup: install/verify everything (seconds when nothing changed) ---
SETUP_ARGS=(--skip-tests)
WITH_DETECTION=1
for arg in "$@"; do
  [ "$arg" = "--no-detection" ] && { SETUP_ARGS+=(--no-detection); WITH_DETECTION=0; }
done
"$SCRIPT_DIR/setup.sh" "${SETUP_ARGS[@]}" || exit 1

cd "$SCRIPT_DIR/backend" || exit 1
# Same venv choice as setup.sh: .venv, or .venv-<os> when .venv belongs to another OS.
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) PLATFORM=windows; LAYOUT=Scripts; PYEXE=python.exe ;;
  Darwin) PLATFORM=macos; LAYOUT=bin; PYEXE=python ;;
  *) PLATFORM=linux; LAYOUT=bin; PYEXE=python ;;
esac
VENV_DIR=".venv"
[ -d ".venv" ] && [ ! -d ".venv/$LAYOUT" ] && VENV_DIR=".venv-$PLATFORM"
VENV_PYTHON="$VENV_DIR/$LAYOUT/$PYEXE"

# --- 2. LAN address, certificate for it, pairing token (scripts/lan.py - shared with the .ps1) ---
LAN_IP="$("$VENV_PYTHON" scripts/lan.py ip)" || {
  echo -e "${RED}ERROR: no network connection found - connect to Wi-Fi/Ethernet first (or use ./setup.sh --run for localhost).${NC}" >&2
  exit 1
}
PORT="${BACKEND_HTTPS_PORT:-8443}"
IFS='|' read -r CERT KEY SPKI <<< "$("$VENV_PYTHON" scripts/lan.py cert "$LAN_IP")"
[ -n "$SPKI" ] || { echo -e "${RED}ERROR: certificate generation failed.${NC}" >&2; exit 1; }
IFS='|' read -r TOKEN TOKEN_STATE <<< "$("$VENV_PYTHON" scripts/lan.py token)"
[ "$TOKEN_STATE" = "generated" ] && echo "Generated a pairing token and saved it in backend/.env (devices need it once, via the link below)."
export BACKEND_PAIRING_TOKEN="$TOKEN"

# --- 3. start the server on all interfaces, HTTPS ---
stop_server() {
  [ -z "${SERVER_PID:-}" ] && return
  if [ -r "/proc/$SERVER_PID/winpid" ]; then
    # Git Bash: the venv python.exe is a launcher with a child interpreter - end the whole tree.
    taskkill //F //T //PID "$(cat "/proc/$SERVER_PID/winpid")" >/dev/null 2>&1
  else
    kill "$SERVER_PID" 2>/dev/null
  fi
  SERVER_PID=""
  echo "Server stopped."
}
trap stop_server EXIT INT TERM

if curl -sk "https://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
  echo -e "${RED}ERROR: something is already listening on port $PORT - close it or set BACKEND_HTTPS_PORT.${NC}" >&2
  exit 1
fi
if [ "$WITH_DETECTION" = "1" ] && "$VENV_PYTHON" -c "import importlib.util as u, sys; sys.exit(0 if u.find_spec('ultralytics') and u.find_spec('mediapipe') else 1)"; then
  export DETECTION_ENABLED=true
fi
LOG="$RUN_DIR/server.log"
echo "Starting the server on https://$LAN_IP:$PORT (log: .run/server.log)..."
"$VENV_PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" \
  --ssl-certfile "$CERT" --ssl-keyfile "$KEY" > "$LOG" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 60); do
  curl -sk "https://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo -e "${RED}ERROR: the server exited during startup:${NC}" >&2; tail -20 "$LOG" >&2; exit 1
  fi
  sleep 1
done

APP_URL="https://$LAN_IP:$PORT/?token=$TOKEN"
[ "${DETECTION_ENABLED:-false}" = "true" ] && APP_URL="$APP_URL&detect=1"
echo ""
echo -e "${GREEN}Running.${NC} On a phone/tablet on the same network, open (accept the certificate warning once):"
echo "    $APP_URL"
echo "  (Windows may ask to allow Python through the firewall - allow it on private networks.)"
echo ""

# --- 4. the app window: Edge/Chrome in app mode, own profile ---
find_browser() {
  local candidates=(
    "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
    "/c/Program Files/Microsoft/Edge/Application/msedge.exe"
    "/c/Program Files/Google/Chrome/Application/chrome.exe"
    "${LOCALAPPDATA:-}/Google/Chrome/Application/chrome.exe"
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
    "/Applications/Chromium.app/Contents/MacOS/Chromium"
  )
  for c in "${candidates[@]}"; do [ -n "$c" ] && [ -x "$c" ] && { echo "$c"; return 0; }; done
  for c in google-chrome google-chrome-stable chromium chromium-browser microsoft-edge; do
    command -v "$c" >/dev/null 2>&1 && { command -v "$c"; return 0; }
  done
  return 1
}

BROWSER="$(find_browser || true)"
if [ -z "$BROWSER" ]; then
  echo "No Chrome/Edge found for an app window - open the link above in any browser."
  read -r -p "Press Enter to stop the server... " _
  exit 0
fi

PROFILE="$RUN_DIR/app-profile"
if command -v cygpath >/dev/null 2>&1; then PROFILE="$(cygpath -w "$PROFILE")"; fi
echo "Opening the app window - close it to stop the server."
STARTED=$(date +%s)
"$BROWSER" --app="$APP_URL" --user-data-dir="$PROFILE" --ignore-certificate-errors-spki-list="$SPKI" \
  --no-first-run --no-default-browser-check --window-size=1280,860 >/dev/null 2>&1
# If the profile was already open, the launcher hands off to that window and returns at once.
if [ $(( $(date +%s) - STARTED )) -lt 5 ]; then
  read -r -p "The app window is open. Press Enter here to stop the server... " _
fi
