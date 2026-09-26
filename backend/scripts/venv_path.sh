# Sourced (from backend/) by setup.sh and start.sh: which virtual environment this OS uses.
# Sets PLATFORM, LAYOUT, PYEXE, VENV_DIR, VENV_PYTHON; prints why when it isn't plain .venv.
#
# One venv per OS, side by side - a Windows venv is useless from WSL/Linux and vice versa, and an
# existing environment is never deleted.
# WSL with the project on the Windows drive (/mnt/c/...): the Linux venv lives in the Linux home
# instead. Writing torch's thousands of small files through /mnt/c takes so long that installs
# never finished; the Linux filesystem does it in a minute. COOK_VENV=<dir> overrides all of this.

case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) PLATFORM=windows; LAYOUT=Scripts; PYEXE=python.exe ;;
  Darwin) PLATFORM=macos; LAYOUT=bin; PYEXE=python ;;
  *) PLATFORM=linux; LAYOUT=bin; PYEXE=python ;;
esac

VENV_DIR=".venv"
if [ -n "${COOK_VENV:-}" ]; then
  VENV_DIR="$COOK_VENV"
elif [ "$PLATFORM" = "linux" ] && grep -qi microsoft /proc/version 2>/dev/null && [[ "$(pwd)" == /mnt/* ]]; then
  VENV_DIR="$HOME/.local/share/ai-cook-assistant/venv-$(pwd | md5sum | cut -c1-8)"
  [ "${VENV_QUIET:-0}" = "1" ] || echo "WSL, project on the Windows drive: the Linux environment lives at $VENV_DIR (fast); Windows keeps backend/.venv."
elif [ -d ".venv" ] && [ ! -d ".venv/$LAYOUT" ]; then
  VENV_DIR=".venv-$PLATFORM"  # .venv was made by another OS (e.g. Windows, seen from WSL): leave it alone
  [ "${VENV_QUIET:-0}" = "1" ] || echo "backend/.venv belongs to another operating system - using backend/$VENV_DIR for $PLATFORM."
fi
VENV_PYTHON="$VENV_DIR/$LAYOUT/$PYEXE"
