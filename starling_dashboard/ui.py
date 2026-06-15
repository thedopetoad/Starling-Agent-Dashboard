"""Render a Snapshot as a live rich panel."""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .client import VENUES, Snapshot

ACCENT = "#86c8ff"


def _short(addr: str | None) -> str:
    if not addr:
        return "—"
    return addr if len(addr) <= 20 else f"{addr[:8]}…{addr[-6:]}"


def render(snap: Snapshot | None) -> Panel:
    title = Text("◆ Starling — Agent Dashboard", style=f"bold {ACCENT}")

    if snap is None:
        return Panel("Connecting to the Starling MCP…", title=title, border_style=ACCENT, padding=(1, 2))
    if snap.error:
        body = Text(snap.error, style="red")
        hint = Text(
            "\nIs the MCP command right? Try: starling-dashboard --mcp \"node path/to/dist/bin/starling-mcp.js\"",
            style="dim",
        )
        return Panel(Text.assemble(body, hint), title=title, border_style="red", padding=(1, 2))

    net_style = "green" if snap.network == "mainnet" else "yellow"
    header = Table.grid(expand=True, padding=(0, 2))
    header.add_column()
    header.add_column()
    header.add_column()
    # unlock mode is only meaningful for the encrypted-keystore source
    third = (
        Text.assemble(("unlock  ", "dim"), (snap.unlock_mode, "white"))
        if snap.key_source == "keystore"
        else Text()
    )
    header.add_row(
        Text.assemble(("network  ", "dim"), (snap.network, net_style)),
        Text.assemble(("key source  ", "dim"), (snap.key_source, ACCENT)),
        third,
    )

    table = Table(expand=True, border_style="grey37", header_style=f"bold {ACCENT}")
    table.add_column("Venue", style="white", no_wrap=True)
    table.add_column("Signer")
    table.add_column("Address", style="dim")
    for v in VENUES:
        loaded = bool(snap.venues.get(v, {}).get("signerLoaded"))
        signer = Text("● ready", style="green") if loaded else Text("○ none", style="grey50")
        table.add_row(v, signer, _short(snap.addresses.get(v)))

    ping = f"{snap.ping_ms:.0f} ms" if snap.ping_ms is not None else "—"
    footer = Text.assemble(
        ("ping ", "dim"), (ping, "white"), ("    ·    Ctrl-C to quit", "dim")
    )

    grid = Table.grid(expand=True)
    grid.add_column()
    grid.add_row(header)
    grid.add_row(Text())
    grid.add_row(table)
    grid.add_row(footer)
    return Panel(grid, title=title, border_style=ACCENT, padding=(1, 2))
