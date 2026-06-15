"""`starling-dashboard` — a live terminal view of your Starling agent.

Launches the Starling MCP server (the same command from your mcp.json), then
polls its read-only tools and renders them. Read-only: it never moves funds.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from mcp import ClientSession
from mcp.client.stdio import stdio_client
from rich.console import Console
from rich.live import Live

from . import __version__
from .client import fetch_snapshot, server_params
from .ui import render

DEFAULT_MCP = "npx -y @starling/execution-mcp"


async def _run(args: argparse.Namespace) -> int:
    overrides = {"STARLING_KEY": args.key} if args.key else {}
    params = server_params(args.mcp, overrides)
    console = Console()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # One-shot or piped output: render a single frame deterministically.
            if args.once or not console.is_terminal:
                snap = await fetch_snapshot(session)
                console.print(render(snap))
                return 0 if snap.error is None else 1
            # Interactive terminal: live-refresh.
            with Live(render(None), console=console, refresh_per_second=4, screen=False) as live:
                while True:
                    snap = await fetch_snapshot(session)
                    live.update(render(snap))
                    await asyncio.sleep(args.interval)


def main() -> None:
    # On Windows a redirected/piped stdout defaults to cp1252, which can't encode
    # the dashboard's glyphs (◆ ● …). Force UTF-8 so piping / --once never crashes.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

    p = argparse.ArgumentParser(
        prog="starling-dashboard",
        description="Watch your Starling trading agent live on your desktop.",
    )
    p.add_argument(
        "--mcp",
        default=os.environ.get("STARLING_MCP_CMD", DEFAULT_MCP),
        help=f'command that launches the Starling MCP server (default: "{DEFAULT_MCP}")',
    )
    p.add_argument("--interval", type=float, default=5.0, help="refresh seconds (default 5)")
    p.add_argument("--once", action="store_true", help="render a single frame and exit")
    p.add_argument("--key", default=os.environ.get("STARLING_KEY"), help="analytics MCP key (sk_live_…)")
    p.add_argument("--version", action="version", version=f"starling-dashboard {__version__}")
    args = p.parse_args()
    try:
        sys.exit(asyncio.run(_run(args)))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
