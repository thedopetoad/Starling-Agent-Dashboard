# Starling Control Protocol v1

How the **dashboard** and a **running Starling MCP** talk to each other while the
MCP is live and trading. This is the contract both sides must implement; the
dashboard side is `starling_dashboard/controlplane.py`, and `tools/mock_mcp.py` is
a runnable reference implementation of the MCP side.

## Why files, not a socket

The dashboard cannot share the trading MCP's **stdio** pipe — that pipe is owned by
whatever launched the MCP (your agent / bot). Rather than make the MCP open a TCP
port (new attack surface, auth, lifecycle), both sides coordinate through small
files under the existing **`~/.starling/`** directory (honoring `STARLING_DIR`) —
the same shared-file pattern the repo already uses for `treasury.json`. It works
while the bot is mid-trade, needs no network, and survives restarts.

All writes are **atomic** (temp file + `os.replace`/`rename`) so a reader never sees
a half-written file. All paths resolve under `starlingDir()` — identical to the
MCP's `src/keystore/store.ts`.

```
~/.starling/
  status.json          MCP → dashboard   (heartbeat; the MCP publishes its state)
  trading.halt         dashboard → MCP   (kill-switch FLAG; presence == halt)
  control/
    <id>.cmd.json      dashboard → MCP   (an action to run)
    <id>.ack.json      MCP → dashboard   (the result of that action)
```

---

## 1. `status.json` — the heartbeat (MCP writes)

The MCP **rewrites this atomically on a heartbeat (≈1–2s)** with its current state.
The dashboard polls it (~1s) and treats it as **stale** if `ts` is older than
**6 seconds** (`DEFAULT_STALE_AFTER`). Keep the heartbeat well under that.

```jsonc
{
  "version": 1,
  "ts": "2026-06-20T19:00:03Z",      // UTC ISO-8601; how the dashboard judges liveness
  "pid": 48213,                       // MCP process id (optional, shown for liveness)
  "network": "mainnet",               // or "testnet"
  "keySource": "keystore",            // keystore | env | file
  "tradingEnabled": true,             // MUST be false whenever trading.halt exists
  "haltReason": null,                 // string when halted (e.g. "manual", "daily-loss-cap")
  "venues": {
    "polygon":     { "signerLoaded": true,  "address": "0x1440…374bB1" },
    "hyperliquid": { "signerLoaded": true,  "address": "0x4f07…266056" },
    "solana":      { "signerLoaded": false, "address": null }
  },
  "positions": [                      // open positions; [] when flat. Keep it small.
    { "venue": "polymarket", "market": "Will X win?", "side": "YES",
      "size": 100.0, "entry": 0.62, "value": 64.0, "pnl": 2.0 }
  ],
  "pnl": { "realized": 12.30, "unrealized": -4.50 }   // optional summary
}
```

Only `version`, `ts`, and `tradingEnabled` are strictly required; everything else is
rendered when present and degrades gracefully when absent.

**Required MCP behavior:** `tradingEnabled` must be `false` whenever `trading.halt`
exists, and `haltReason` should echo that flag's `reason`.

---

## 2. `trading.halt` — the kill switch (dashboard writes, MCP obeys)

A **flag file**. Its *presence* means "halt." The dashboard creates it (Halt button)
and deletes it (Resume button). Content is informational:

```jsonc
{ "version": 1, "reason": "manual", "source": "dashboard", "ts": "2026-06-20T19:00:00Z" }
```

**Required MCP behavior — this is the safety-critical part:** the policy gate must
check `exists(~/.starling/trading.halt)` **before every signed action** (order, swap,
bridge, withdraw) and **refuse** while it exists. Wire it into the existing
kill-switch in `src/policy/limits.ts`. Because it's a re-checked state (not a queued
message), trading stops even mid-loop and even if the command queue below is never
drained. Resume = the dashboard deletes the file; the next gate check passes.

---

## 3. `control/<id>.cmd.json` — actions (dashboard writes, MCP runs, then acks)

One-shot actions that aren't a state. The dashboard writes a command file; the MCP
**watches `control/`**, executes each command **at most once** (the `id` is the
idempotency key), and writes a sibling `.ack.json`.

```jsonc
// dashboard writes  control/cmd_a1b2c3d4e5f6.cmd.json
{
  "version": 1,
  "id": "cmd_a1b2c3d4e5f6",
  "action": "close_all",        // close_all | withdraw  (halt/resume use the flag)
  "args": { },                  // withdraw: { "chain": "polygon" | "all" }
  "source": "dashboard",
  "ts": "2026-06-20T19:00:10Z"
}
```

```jsonc
// MCP writes      control/cmd_a1b2c3d4e5f6.ack.json   when done (or progressing)
{
  "id": "cmd_a1b2c3d4e5f6",
  "action": "close_all",
  "status": "ok",              // ok | error | in_progress
  "message": "closed 3 of 3 positions",
  "detail": { "closed": 3, "failed": 0, "errors": [] },
  "ts": "2026-06-20T19:00:12Z"
}
```

### Actions

| action | args | MCP does | ack `detail` |
|---|---|---|---|
| `close_all` | — | market-close every open position across venues | `{ closed, failed, errors[] }` |
| `withdraw` | `{ "chain": "polygon"\|"hyperliquid"\|"solana"\|"all" }` | sweep free balance to the **pinned `treasury.json`** destination | `{ chain, amount, txids[] }` |

**Required MCP behavior:**
- Idempotent by `id` — if an ack already exists for an id, do nothing.
- `withdraw` sweeps **only** to the address in `treasury.json` (set via the
  dashboard's "Set withdraw destination…"). If none is pinned, ack with
  `status: "error"`, `message: "no withdraw destination pinned"`.
- Write `in_progress` first for long actions if you like; the dashboard shows it and
  keeps waiting for the terminal `ok`/`error`.
- The dashboard cleans up the `.cmd.json`/`.ack.json` pair after it reads a terminal
  ack, so don't rely on them persisting.

---

## MCP implementation checklist

- [ ] On a 1–2s timer, atomically write `status.json` (schema §1), with
      `tradingEnabled = internalEnabled && !exists(trading.halt)`.
- [ ] In the policy gate, refuse to sign while `trading.halt` exists (§2).
- [ ] Watch `control/`; for each `*.cmd.json` with no matching `*.ack.json`, run the
      action once and write `*.ack.json` (§3).
- [ ] `withdraw` resolves its destination from `treasury.json` only.
- [ ] Use `starlingDir()` for every path; write atomically (temp + rename).

Version this protocol via the top-level `version` field; bump it on a breaking
change so both sides can detect a mismatch.
