#!/bin/bash
# ====================================================================
#  Starling Agent Dashboard - launcher (Linux)
#  Run:  ./run-dashboard.sh   (chmod +x once if needed)
#  First run creates a private virtualenv and installs the two deps
#  (mcp, rich); after that it just opens the window.
#  Needs Tk:  Debian/Ubuntu -> sudo apt install python3-tk
# ====================================================================
cd "$(dirname "$0")" || exit 1

VENV=".venv"
PY="$VENV/bin/python3"
READY="$VENV/.starling-deps"

if [ ! -x "$PY" ] || [ ! -f "$READY" ]; then
  echo "Setting up the Starling Dashboard (one time)..."
  BASEPY="$(command -v python3 || true)"
  if [ -z "$BASEPY" ]; then
    echo "Python 3.10+ was not found. Install it (and python3-tk) and run this again."
    exit 1
  fi
  if [ ! -x "$PY" ]; then
    "$BASEPY" -m venv "$VENV" || { echo "Could not create venv."; exit 1; }
  fi
  echo "Installing dependencies (mcp, rich)..."
  "$PY" -m pip install --upgrade pip >/dev/null 2>&1
  if ! "$PY" -m pip install "mcp>=1.0" "rich>=13.0"; then
    echo "Dependency install failed. Check your internet connection and try again."
    exit 1
  fi
  : > "$READY"
fi

PYTHONPATH="$(pwd)" exec "$PY" -m starling_dashboard.gui
