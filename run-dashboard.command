#!/bin/bash
# ====================================================================
#  Starling Agent Dashboard - web UI launcher (macOS)
#  Double-click in Finder (first time: right-click -> Open).
#  Stdlib only: no virtualenv, no pip install. Needs Python 3.10+.
#  Opens the dashboard in your browser; close this window to stop it.
# ====================================================================
cd "$(dirname "$0")" || exit 1

BASEPY="$(command -v python3 || true)"
if [ -z "$BASEPY" ]; then
  echo "Python 3.10+ was not found."
  echo "Install it from https://www.python.org/downloads/macos/ and run this again."
  open "https://www.python.org/downloads/macos/" 2>/dev/null || true
  read -r -p "Press Return to close."
  exit 1
fi

echo "Starting the Starling dashboard - a browser tab will open shortly."
echo "Keep this window open while you use it; close it (or Ctrl-C) to stop."
PYTHONPATH="$(pwd)" exec "$BASEPY" -m starling_dashboard web
