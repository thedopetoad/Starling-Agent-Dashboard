"""The file-based control plane between the dashboard and a *running* Starling MCP.

The dashboard can't share the trading MCP's stdio pipe (that belongs to the agent
that launched it), so the two coordinate through small files under ``~/.starling/``
— the same directory, and the same shared-file idea, as ``treasury.json``.

  MCP  → dashboard :  status.json     (heartbeat: state the MCP publishes)
  dash → MCP       :  trading.halt    (kill-switch FLAG — presence == halt)
  dash → MCP       :  control/<id>.cmd.json   (an action to run: close_all / withdraw)
  MCP  → dashboard :  control/<id>.ack.json   (the result of that action)

Why a flag file for halt but a queue for the rest: a kill-switch must be a *state*
the MCP re-checks before every signed action, not a message that could sit
unprocessed. Closing positions / withdrawing are one-shot *actions*, so they're
queued and acknowledged.

Stdlib only (no ``mcp`` / ``rich`` / ``tkinter``) so it stays trivially testable and
importable. See CONTROL_PROTOCOL.md for the wire contract the MCP must match.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .treasury import starling_dir  # the one true ~/.starling resolver

STATUS_NAME = "status.json"
HALT_NAME = "trading.halt"
CONTROL_DIRNAME = "control"

# Actions the dashboard can request. halt/resume are handled by the flag file, not
# the queue, but we keep them in the vocabulary for acks/auditing if the MCP wants.
ACTIONS = ("close_all", "withdraw", "halt", "resume")

# The MCP is expected to heartbeat well under this; older than this == not live.
DEFAULT_STALE_AFTER = 6.0
PROTOCOL_VERSION = 1


# ── status.json (MCP → dashboard) ─────────────────────────────────────────────
@dataclass
class Status:
    present: bool = False          # does status.json exist?
    live: bool = False             # exists AND heartbeat is fresh
    age: float | None = None       # seconds since the MCP's ts (None if unparsable)
    raw: dict[str, Any] = field(default_factory=dict)
    error: str | None = None       # set if the file exists but couldn't be read/parsed

    # convenience accessors over the raw payload --------------------------------
    @property
    def network(self) -> str:
        return self.raw.get("network", "?")

    @property
    def key_source(self) -> str:
        return self.raw.get("keySource", "?")

    @property
    def pid(self) -> Any:
        return self.raw.get("pid")

    @property
    def trading_enabled(self) -> bool:
        # The MCP is the authority, but absence defaults to "unknown" → treat as off.
        return bool(self.raw.get("tradingEnabled", False))

    @property
    def halt_reason(self) -> str | None:
        return self.raw.get("haltReason")

    @property
    def venues(self) -> dict[str, Any]:
        return self.raw.get("venues", {}) or {}

    @property
    def positions(self) -> list[dict[str, Any]]:
        p = self.raw.get("positions")
        return p if isinstance(p, list) else []

    @property
    def pnl(self) -> dict[str, Any]:
        return self.raw.get("pnl", {}) or {}


def status_path() -> Path:
    return starling_dir() / STATUS_NAME


def _parse_ts(s: Any) -> datetime | None:
    if not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _age_seconds(ts: Any) -> float | None:
    dt = _parse_ts(ts)
    if dt is None:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds()


def read_status(stale_after: float = DEFAULT_STALE_AFTER) -> Status:
    """Read the MCP's published state. Never raises — surfaces problems on .error."""
    p = status_path()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Status(present=False)
    except (OSError, ValueError) as exc:
        return Status(present=True, error=f"{type(exc).__name__}: {exc}")
    if not isinstance(raw, dict):
        return Status(present=True, error="status.json is not an object")
    age = _age_seconds(raw.get("ts"))
    live = age is not None and 0 <= age <= stale_after
    return Status(present=True, raw=raw, age=age, live=live)


# ── trading.halt (dashboard → MCP, the kill switch) ────────────────────────────
def halt_path() -> Path:
    return starling_dir() / HALT_NAME


def is_halted() -> bool:
    return halt_path().exists()


def set_halt(reason: str = "manual") -> Path:
    """Create the kill-switch flag. The MCP's policy gate must refuse to sign while
    this file exists. Instant + local — does not depend on the MCP draining a queue."""
    d = starling_dir()
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": PROTOCOL_VERSION,
        "reason": reason,
        "source": "dashboard",
        "ts": _now_iso(),
    }
    return _atomic_write_json(halt_path(), payload)


def clear_halt() -> None:
    """Remove the kill-switch flag (resume). Safe if it's already gone."""
    try:
        halt_path().unlink()
    except FileNotFoundError:
        pass


def read_halt() -> dict | None:
    try:
        return json.loads(halt_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ── control/ command queue (dashboard → MCP → dashboard) ───────────────────────
def control_dir() -> Path:
    return starling_dir() / CONTROL_DIRNAME


def enqueue_command(action: str, args: dict | None = None) -> str:
    """Drop a one-shot command for the MCP to execute. Returns the command id, which
    is also the idempotency key — the MCP must run each id at most once."""
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    cid = f"cmd_{uuid.uuid4().hex[:12]}"
    payload = {
        "version": PROTOCOL_VERSION,
        "id": cid,
        "action": action,
        "args": args or {},
        "source": "dashboard",
        "ts": _now_iso(),
    }
    d = control_dir()
    d.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(d / f"{cid}.cmd.json", payload)
    return cid


def read_ack(cid: str) -> dict | None:
    """The MCP's result for a command, or None if it hasn't acked yet."""
    try:
        return json.loads((control_dir() / f"{cid}.ack.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def pending_commands() -> list[str]:
    """Command ids written but not yet acked by the MCP."""
    d = control_dir()
    if not d.is_dir():
        return []
    cmds = {p.name[: -len(".cmd.json")] for p in d.glob("*.cmd.json")}
    acks = {p.name[: -len(".ack.json")] for p in d.glob("*.ack.json")}
    return sorted(cmds - acks)


def clear_command(cid: str) -> None:
    """Best-effort cleanup of a finished command + its ack."""
    for suffix in (".cmd.json", ".ack.json"):
        try:
            (control_dir() / f"{cid}{suffix}").unlink()
        except FileNotFoundError:
            pass


# ── helpers ────────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _atomic_write_json(dest: Path, payload: dict) -> Path:
    """Write JSON via a temp file + rename so a reader never sees a partial file."""
    d = dest.parent
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".{dest.name}.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp"
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, dest)  # atomic on the same filesystem
    return dest
