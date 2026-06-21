#!/bin/bash
# ====================================================================
#  Starling Agent Dashboard - web UI launcher (Linux)
#  Run:  ./run-dashboard.sh   (chmod +x once if needed)
#  Stdlib only: no virtualenv, no pip install. Needs Python 3.10+.
#  Opens the dashboard in your browser; Ctrl-C here to stop it.
# ====================================================================
cd "$(dirname "$0")" || exit 1

BASEPY="$(command -v python3 || true)"
if [ -z "$BASEPY" ]; then
  echo "Python 3.10+ was not found. Install it and run this again."
  exit 1
fi

echo "Starting the Starling dashboard - a browser tab will open shortly."
echo "Press Ctrl-C to stop."
PYTHONPATH="$(pwd)" exec "$BASEPY" -m starling_dashboard web
