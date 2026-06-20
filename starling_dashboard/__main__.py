"""`starling-dashboard` — a live terminal view of your Starling agent.

Launches the Starling MCP (the same command from your mcp.json), then polls its
read-only tools and renders them. Read-only: it never moves funds.
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

# Example local-build launch command — clone Starling-MCP, run `npm install`
# (its prepare script builds to dist/), then point --mcp at the built bin.
EXAMPLE_MCP = 'node /path/to/Starling-MCP/dist/bin/starling-mcp.js'

NO_MCP_HELP = (
    'No MCP command. Point me at your local Starling MCP build:\n'
    f'  --mcp "{EXAMPLE_MCP}"\n'
    "(or set STARLING_MCP_CMD). Clone Starling-MCP, run `npm install` to build "
    "dist/, then pass the path to the built bin."
)


async def _run(args: argparse.Namespace) -> int:
    console = Console()
    if not args.mcp:
        console.print(f"[yellow]{NO_MCP_HELP}[/]")
        return 2
    overrides = {"STARLING_KEY": args.key} if args.key else {}
    params = server_params(args.mcp, overrides)
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


def _prompt_chains(console) -> list[str]:
    from rich.prompt import Prompt

    choice = Prompt.ask(
        "Which chain?", choices=["polygon", "solana", "hyperliquid", "all"], default="polygon", console=console
    )
    return ["polygon", "solana", "hyperliquid"] if choice == "all" else [choice]


def _run_set_treasury(args: argparse.Namespace) -> int:
    """Interactive: the human pastes their withdraw address; we validate it, show
    the 4-byte commitment, confirm, and write ~/.starling/treasury.json. Runs
    ENTIRELY here — it never goes through the MCP, so the agent never sees or
    re-types the address (the whole point: no transcription errors)."""
    from rich.console import Console
    from rich.prompt import Confirm, Prompt

    from . import treasury as tre

    console = Console()
    console.print("[bold #86c8ff]◆ Starling — set withdraw destination[/]")
    console.print(
        "Paste the wallet address your funds should withdraw/sweep to. It's saved to a local\n"
        f"text file ([dim]{tre.treasury_path()}[/]) the MCP reads — the agent never types it.\n"
    )

    current = tre.read_treasury() or {}
    cur_by = current.get("byChain") or {}
    if cur_by:
        console.print("[dim]Currently pinned:[/]")
        for c, a in cur_by.items():
            console.print(f"  [white]{c}[/]  {a}  [dim]commitment {tre.commitment(c, a)}[/]")
        console.print()

    chains = [args.chain] if args.chain else _prompt_chains(console)
    by_chain = dict(cur_by)
    changed = False
    for chain in chains:
        if chain == "hyperliquid":
            console.print(
                "[dim]note: Hyperliquid's native withdraw always lands at your own address; a pin here\n"
                "only affects cross-chain bridge-outs to HL.[/]"
            )
        raw = args.address if (args.address and args.chain) else Prompt.ask(f"[white]{chain}[/] withdraw address", console=console)
        norm = tre.normalize(chain, raw)
        if not norm:
            console.print(f"[red]✗ not a valid {chain} address — skipped[/]")
            continue
        console.print(f"  address    [white]{norm}[/]")
        console.print(
            f"  commitment [bold]{tre.commitment(chain, norm)}[/]  "
            "[dim](verify against your wallet / recovery sheet — not against chat)[/]"
        )
        if Confirm.ask(f"Pin this as the [bold]{chain}[/] withdraw destination?", default=False, console=console):
            by_chain[chain] = norm
            changed = True
        else:
            console.print("[yellow]skipped[/]")

    if not changed:
        console.print("\n[yellow]Nothing changed.[/]")
        return 1

    path = tre.write_treasury(by_chain)
    console.print(f"\n[green]✓ Saved[/] {path}")
    console.print("[dim]The agent reads it via auth_check / request_withdraw_address. Re-run your withdraw.[/]")
    return 0


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
        default=os.environ.get("STARLING_MCP_CMD"),
        help=f'command that launches your local Starling MCP build, e.g. "{EXAMPLE_MCP}" '
        "(or set STARLING_MCP_CMD). Required for the live view; not needed by set-treasury.",
    )
    p.add_argument("--interval", type=float, default=5.0, help="refresh seconds (default 5)")
    p.add_argument("--once", action="store_true", help="render a single frame and exit")
    p.add_argument("--key", default=os.environ.get("STARLING_KEY"), help="analytics MCP key (sk_live_…)")
    p.add_argument("--version", action="version", version=f"starling-dashboard {__version__}")

    sub = p.add_subparsers(dest="command")
    st = sub.add_parser(
        "set-treasury",
        help="pin your withdraw destination — paste an address into a local file the MCP reads",
    )
    st.add_argument("--chain", choices=["polygon", "solana", "hyperliquid"], help="chain to set (prompted if omitted)")
    st.add_argument("--address", help="non-interactive: the address (requires --chain; normally you paste interactively)")

    sub.add_parser(
        "gui",
        help="open the desktop window instead of the terminal view (same as the run-dashboard launchers)",
    )

    args = p.parse_args()

    if getattr(args, "command", None) == "set-treasury":
        sys.exit(_run_set_treasury(args))

    if getattr(args, "command", None) == "gui":
        from .gui import main as gui_main

        gui_main()
        return

    try:
        sys.exit(asyncio.run(_run(args)))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
