#!/usr/bin/env bash
# Open the Cooking Assistant in seconds - Linux, macOS, WSL/Ubuntu. (On Windows: start.cmd.)
#
#   - Runs ./setup.sh only the first time, or after a requirement or detector setting changed.
#   - One server, two addresses: http://localhost:8000 for this computer (any browser, no
#     certificate warning) and https://<LAN IP>:8443 for phones on the same Wi-Fi.
#   - Opens the app in its own Chrome/Edge window, camera and microphone already allowed.
#   - Object/hand detection is on whenever it's installed. Ctrl+C stops the server.
#
# Flags: --no-window (serve only)  --local-only (no LAN address)  --no-detection
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/backend" || exit 1
RUN_DIR="$SCRIPT_DIR/.run"
mkdir -p "$RUN_DIR"
STARTED=$(date +%s.%N 2>/dev/null || date +%s)

OPEN_WINDOW=1
LOCAL_ONLY=0
DETECTION=auto
SETUP_ARGS=(--skip-tests --no-summary)
for arg in "$@"; do
  case "$arg" in
    --no-window) OPEN_WINDOW=0 ;;
    --local-only) LOCAL_ONLY=1 ;;
    --no-detection) DETECTION=off; SETUP_ARGS+=(--no-detection) ;;
  esac
done

# --- 1. setup, only when something changed since the last successful one ---
VENV_QUIET=1
# shellcheck disable=SC1091
. scripts/venv_path.sh
if ! "$VENV_PYTHON" scripts/setup_stamp.py check >/dev/null 2>&1; then
  echo "First start, or something changed - running setup once (later starts skip it)..."
  bash "$SCRIPT_DIR/setup.sh" "${SETUP_ARGS[@]}" || exit 1
fi

PORT="${BACKEND_PORT:-8000}"
LAN_PORT="${BACKEND_HTTPS_PORT:-8443}"
health() {
  if command -v curl >/dev/null 2>&1; then
    curl -s -o /dev/null "http://127.0.0.1:$PORT/health"
  else
    "$VENV_PYTHON" -c "import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=2)" \
      "http://127.0.0.1:$PORT/health" >/dev/null 2>&1
  fi
}

# --- 2. pairing token, and this machine's LAN address + certificate (one call) ---
IFS='|' read -r TOKEN TOKEN_STATE LAN_IP CERT KEY _SPKI < <("$VENV_PYTHON" scripts/lan.py all)
if [ -z "${TOKEN:-}" ]; then echo "ERROR: scripts/lan.py failed." >&2; exit 1; fi
[ "$TOKEN_STATE" = "generated" ] && echo "Generated a pairing token in backend/.env (links below carry it)."
if grep -qi microsoft /proc/version 2>/dev/null && [ "$(wslinfo --networking-mode 2>/dev/null)" != "mirrored" ]; then
  # WSL's own address sits behind Windows' NAT - phones can't reach it.
  [ "$LOCAL_ONLY" = "1" ] || echo "WSL: phones can't reach this server - use start.cmd on Windows for phones (or WSL mirrored networking)."
  LOCAL_ONLY=1
fi
[ "$LOCAL_ONLY" = "1" ] && LAN_IP=""

LOCAL_URL="http://localhost:$PORT/?token=$TOKEN&detect=1"
PROFILE="$RUN_DIR/app-profile"

if health; then
  echo "Already running - opening the app window."
  "$VENV_PYTHON" scripts/app_window.py open --url "$LOCAL_URL" --profile "$PROFILE"
  exit 0
fi

# --- 3. the server: both addresses, one process ---
SERVER_ARGS=(scripts/serve.py --port "$PORT" --detection "$DETECTION")
[ -n "$LAN_IP" ] && SERVER_ARGS+=(--lan-port "$LAN_PORT" --cert "$CERT" --key "$KEY")
BACKEND_PAIRING_TOKEN="$TOKEN" "$VENV_PYTHON" "${SERVER_ARGS[@]}" >"$RUN_DIR/server.log" 2>"$RUN_DIR/server.err.log" &
SERVER=$!
trap 'kill "$SERVER" 2>/dev/null; wait "$SERVER" 2>/dev/null; echo "Server stopped."' EXIT
trap 'exit 0' INT TERM

for _ in $(seq 1 240); do
  health && break
  kill -0 "$SERVER" 2>/dev/null || break
  sleep 0.25
done
if ! health; then
  echo "ERROR: the server did not start (is port $PORT or $LAN_PORT already in use?):" >&2
  tail -20 "$RUN_DIR/server.err.log" >&2
  exit 1
fi
SECS=$(awk "BEGIN { printf \"%.1f\", $(date +%s.%N 2>/dev/null || date +%s) - $STARTED }")

echo ""
echo "Cooking Assistant is running (${SECS} s)."
echo "  This computer, any browser:  $LOCAL_URL"
if [ -n "$LAN_IP" ]; then
  PHONE_URL="https://$LAN_IP:$LAN_PORT/?token=$TOKEN&detect=1"
  echo "  Phone/tablet on this Wi-Fi:  $PHONE_URL"
  echo "      (first time on a phone: open https://$LAN_IP:$LAN_PORT/ca.crt, install it, then no warning)"
  "$VENV_PYTHON" scripts/pairing_qr.py --url "$PHONE_URL" --png "$RUN_DIR/pairing.png" || \
    echo "      (QR skipped - qrcode not installed; re-run setup.sh)"
fi
echo "  Press the big Start button and allow the camera. Detection starts by itself (first frames: 'loading model')."
echo "  Server log: .run/server.err.log"
echo ""

# --- 4. the app window: own profile, camera + microphone allowed for localhost ---
if [ "$OPEN_WINDOW" = "1" ]; then
  "$VENV_PYTHON" scripts/app_window.py open --url "$LOCAL_URL" --profile "$PROFILE" ||
    echo "No Chrome/Edge for an app window - open the link above in any browser."
fi
echo "Ctrl+C stops the server."
wait "$SERVER"
