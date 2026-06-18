"""Talk to the Starling MCP server over stdio using the official MCP client.

The dashboard is an MCP *host*: it launches the server (the same `command` your
agent uses in mcp.json) and calls its read-only tools. The server signs locally
and never exposes key material — we only read status + public addresses here.
"""

from __future__ import annotations

import json
import os
import shlex
import time
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession, StdioServerParameters

VENUES = ("polygon", "hyperliquid", "solana")


@dataclass
class Snapshot:
    network: str = "?"
    key_source: str = "?"
    unlock_mode: str = "?"
    venues: dict[str, dict[str, Any]] = field(default_factory=dict)
    addresses: dict[str, Any] = field(default_factory=dict)
    # auth_check.treasury: { sealed, withdrawsEnabled, byChain:{chain:{address,source,commitment}} }
    treasury: dict[str, Any] | None = None
    ping_ms: float | None = None
    error: str | None = None


def _text(result: Any) -> str:
    """Pull the text payload out of a CallToolResult."""
    for c in getattr(result, "content", []) or []:
        text = getattr(c, "text", None)
        if text is not None:
            return text
    return "{}"


def server_params(command: str, env_overrides: dict[str, str] | None = None) -> StdioServerParameters:
    """Build the stdio launch params. Inherits the current environment (so PATH,
    npx/node, and any STARLING_* the server needs are present) plus overrides."""
    parts = shlex.split(command, posix=(os.name != "nt"))
    if not parts:
        raise ValueError("empty MCP command")
    env = {**os.environ, **(env_overrides or {})}
    return StdioServerParameters(command=parts[0], args=parts[1:], env=env)


async def fetch_snapshot(session: ClientSession) -> Snapshot:
    """Call the server's read-only tools and assemble one frame of state."""
    snap = Snapshot()
    try:
        auth = json.loads(_text(await session.call_tool("auth_check", {})))
        snap.network = auth.get("network", "?")
        snap.key_source = auth.get("keySource", "?")
        snap.unlock_mode = auth.get("unlockMode", "?")
        snap.venues = auth.get("venues", {})
        snap.treasury = auth.get("treasury")

        snap.addresses = json.loads(_text(await session.call_tool("get_wallet_addresses", {})))

        t0 = time.perf_counter()
        await session.call_tool("ping", {})
        snap.ping_ms = (time.perf_counter() - t0) * 1000.0
    except Exception as exc:  # surface, don't crash the live view
        snap.error = f"{type(exc).__name__}: {exc}"
    return snap
