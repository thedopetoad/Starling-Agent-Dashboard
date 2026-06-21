"""Starling Agent Dashboard — a local web UI for a running Starling MCP.

A tiny stdlib-only local server (127.0.0.1) serves a single-page app that watches
and controls a live Starling MCP (https://github.com/thedopetoad/Starling-MCP)
through the file control plane in ``~/.starling/`` — it never holds keys or signs.
Run it with ``python -m starling_dashboard`` (or the ``run-dashboard`` launchers).
"""

__version__ = "0.2.0"
