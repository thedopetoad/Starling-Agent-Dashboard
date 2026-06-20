"""A fake Starling MCP that speaks the file control protocol — for trying the
dashboard's live view + control buttons WITHOUT a real MCP (and as an executable
reference of CONTROL_PROTOCOL.md for whoever implements the real MCP side).

It does NOT trade, hold keys, or touch the network. It just:
  - heartbeats ~/.starling/status.json every second with made-up state,
  - honors ~/.starling/trading.halt (flips tradingEnabled off),
  - drains ~/.starling/control/*.cmd.json (close_all empties the fake book;
    withdraw pretends to sweep) and writes *.ack.json.

Run it next to the dashboard:
    python tools/mock_mcp.py
Point both at a scratch dir to avoid your real ~/.starling:
    STARLING_DIR=./.scratch python tools/mock_mcp.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


def starling_dir() -> Path:
    d = os.environ.get("STARLING_DIR")
    return Path(os.path.abspath(d)) if d else Path.home() / ".starling"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp"
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# A tiny fake book the buttons can act on.
POSITIONS = [
    {"venue": "polymarket", "market": "Will it rain in NYC?", "side": "YES",
     "size": 100.0, "entry": 0.62, "value": 64.0, "pnl": 2.0},
    {"venue": "hyperliquid", "market": "BTC-PERP", "side": "LONG",
     "size": 0.05, "entry": 64000.0, "value": 3250.0, "pnl": 50.0},
    {"venue": "polymarket", "market": "Election outcome", "side": "NO",
     "size": 40.0, "entry": 0.31, "value": 12.8, "pnl": -0.6},
]


def main() -> None:
    d = starling_dir()
    control = d / "control"
    halt = d / "trading.halt"
    status = d / "status.json"
    print(f"mock MCP: writing {status}  (Ctrl-C to stop)", file=sys.stderr)

    positions = [dict(p) for p in POSITIONS]
    while True:
        # 1) drain the command queue
        if control.is_dir():
            for cmd_file in sorted(control.glob("*.cmd.json")):
                cid = cmd_file.name[: -len(".cmd.json")]
                ack_file = control / f"{cid}.ack.json"
                if ack_file.exists():
                    continue  # idempotent: already handled
                try:
                    cmd = json.loads(cmd_file.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                action = cmd.get("action")
                if action == "close_all":
                    n = len(positions)
                    positions.clear()
                    ack = {"id": cid, "action": action, "status": "ok",
                           "message": f"closed {n} of {n} positions",
                           "detail": {"closed": n, "failed": 0, "errors": []}, "ts": now_iso()}
                elif action == "withdraw":
                    chain = (cmd.get("args") or {}).get("chain", "all")
                    ack = {"id": cid, "action": action, "status": "ok",
                           "message": f"swept {chain} to pinned treasury (mock)",
                           "detail": {"chain": chain, "amount": 123.45,
                                      "txids": ["0xmocktx"]}, "ts": now_iso()}
                else:
                    ack = {"id": cid, "action": action, "status": "error",
                           "message": f"mock does not implement {action!r}", "ts": now_iso()}
                atomic_write(ack_file, ack)
                print(f"  acked {cid}: {action} -> {ack['status']}", file=sys.stderr)

        # 2) publish a heartbeat (honoring the halt flag)
        halted = halt.exists()
        reason = None
        if halted:
            try:
                reason = json.loads(halt.read_text(encoding="utf-8")).get("reason", "manual")
            except (OSError, ValueError):
                reason = "manual"
        atomic_write(status, {
            "version": 1,
            "ts": now_iso(),
            "pid": os.getpid(),
            "network": "testnet",
            "keySource": "keystore",
            "tradingEnabled": (not halted),
            "haltReason": reason,
            "venues": {
                "polygon": {"signerLoaded": True, "address": "0x1440B1aa00bb00cc00dd00ee00ff0011374bB1"},
                "hyperliquid": {"signerLoaded": True, "address": "0x4f072daa00bb00cc00dd00ee00ff00112266056"},
                "solana": {"signerLoaded": True, "address": "FdY9B9JnaabbccddeeffgghhiijjkkllmmnnCMRVPw"},
            },
            "positions": positions,
            "pnl": {"realized": 11.4, "unrealized": round(sum(p["pnl"] for p in positions), 2)},
        })
        time.sleep(1.0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
