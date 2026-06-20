#!/bin/bash
# ====================================================================
#  Starling Agent Dashboard - double-click launcher (macOS)
#  Double-click in Finder. First run creates a private virtualenv and
#  installs the two deps (mcp, rich); after that it just opens the window.
#  If Finder won't run it, right-click -> Open the first time, or run:
#      chmod +x run-dashboard.command
# ====================================================================
cd "$(dirname "$0")" || exit 1

VENV=".venv"
PY="$VENV/bin/python3"
READY="$VENV/.starling-deps"

if [ ! -x "$PY" ] || [ ! -f "$READY" ]; then
  echo "Setting up the Starling Dashboard (one time, ~30s)..."
  BASEPY="$(command -v python3 || true)"
  if [ -z "$BASEPY" ]; then
    echo "Python 3.10+ was not found."
    echo "Install it from https://www.python.org/downloads/macos/ and run this again."
    open "https://www.python.org/downloads/macos/" 2>/dev/null || true
    read -r -p "Press Return to close."
    exit 1
  fi
  if [ ! -x "$PY" ]; then
    "$BASEPY" -m venv "$VENV" || { echo "Could not create venv."; read -r -p "Press Return."; exit 1; }
  fi
  echo "Installing dependencies (mcp, rich)..."
  "$PY" -m pip install --upgrade pip >/dev/null 2>&1
  if ! "$PY" -m pip install "mcp>=1.0" "rich>=13.0"; then
    echo "Dependency install failed. Check your internet connection and try again."
    read -r -p "Press Return to close."
    exit 1
  fi
  : > "$READY"
fi

# Tk windows on macOS run fine from a Terminal-launched process.
PYTHONPATH="$(pwd)" exec "$PY" -m starling_dashboard.gui
