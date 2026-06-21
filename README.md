# Starling Agent Dashboard

**Watch and control your trading agent from your browser.** A small, open local
web app for a *running* [Starling MCP](https://github.com/thedopetoad/Starling-MCP).
It runs on `127.0.0.1`, opens in your browser, and gives you three pages:

- **Control** — halt/resume trading, close all or selected positions, withdraw a
  single chain, or consolidate everything to one chain.
- **Analytics** — total value, unrealized P&L, per-wallet balances, open positions.
- **Wallet States** — each MCP wallet's address + value, and the **editable
  withdraw destinations** you paste in (with a transcription commitment to verify).

**It never holds keys or signs anything.** The page talks to the live MCP through
small files in `~/.starling/` (see [CONTROL_PROTOCOL.md](CONTROL_PROTOCOL.md)): it
*reads* the state the MCP publishes, and the buttons only *queue intent* — the MCP
runs the actual trade/withdraw behind its own guardrails. The kill-switch is the
one exception: a flag file the MCP refuses to trade while it exists.

> **Zero dependencies.** Pure Python standard library — no `pip install`, no
> virtualenv. The only prerequisite is **Python 3.10+**.

## Quick start — just double-click

- **Windows** — double-click **`run-dashboard.bat`**
- **macOS** — double-click **`run-dashboard.command`** (first time: right-click → Open)
- **Linux** — run **`./run-dashboard.sh`**

It starts a local server and opens `http://127.0.0.1:8787` in your browser. Keep
the launcher window open while you use it; close it to stop the server.

Or from a terminal:

```bash
python -m starling_dashboard            # opens the web dashboard (default)
python -m starling_dashboard web --port 9000 --no-open
```

> No MCP running yet? The dashboard shows **"MCP OFFLINE"** until one publishes
> `~/.starling/status.json`. Spin up the bundled **mock** to see it work — see
> [Try it without a real MCP](#try-it-without-a-real-mcp).

## Security model

The dashboard can halt trading and queue withdrawals, so the local server is
locked down:

- It binds to **`127.0.0.1` only** — never a routable interface.
- Every `/api/*` request must carry a **per-session token** minted at startup and
  embedded in the served page. A web page on another origin can't read that page,
  so it can't learn the token — this blocks drive-by requests from other browser
  tabs. Requests without it get `403`.
- It still **never holds keys or signs**: admin actions only queue intent for the
  MCP, which enforces its own guardrails.

## How it connects

The dashboard does **not** launch or share the trading MCP's process — an MCP over
stdio is a private pipe owned by whatever started your agent. Both sides coordinate
through files under `~/.starling/` (honoring `STARLING_DIR`):

```
~/.starling/
  status.json            MCP → dashboard   heartbeat: network, venues, portfolio, withdraw destinations, tradingEnabled
  trading.halt           dashboard → MCP   kill-switch FLAG — present == halted
  treasury.json          dashboard → MCP   the editable withdraw destinations you pin
  control/<id>.cmd.json  dashboard → MCP   an action (close_all / withdraw)
  control/<id>.ack.json  MCP → dashboard   that action's result
```

This works while the bot is mid-trade, needs no shared ports with the MCP, and
survives restarts. The full wire contract is in
**[CONTROL_PROTOCOL.md](CONTROL_PROTOCOL.md)**.

## Try it without a real MCP

A bundled mock implements the MCP side of the protocol (no keys, no network, no
trades) so you can see the live view and buttons end-to-end:

```bash
# point both at a scratch dir so it never touches your real ~/.starling
STARLING_DIR=./.scratch python tools/mock_mcp.py        # in one terminal
STARLING_DIR=./.scratch python -m starling_dashboard    # in another
```

Halt/Resume flips the banner; Close-all empties the fake book; Withdraw acks a mock
sweep. `tools/mock_mcp.py` is also a runnable reference for the MCP side.

## Set your withdraw destination

Pin the wallet your funds withdraw/sweep to on the **Wallet States** page: paste
the address, the field shows a 4-byte **commitment**, you Save, and it's written to
`~/.starling/treasury.json` — the same file the MCP reads for `withdraw`. The point
is *transcription integrity*: your exact bytes reach disk and the agent never
re-types the 40/44-char string.

There's also a terminal equivalent:

```bash
python -m starling_dashboard set-treasury                 # prompts for chain + address
python -m starling_dashboard set-treasury --chain polygon
```

> Verify the commitment against your wallet / recovery sheet — **not** against
> anything an agent printed in chat. This is a transcription check, not a security
> control: a code-exec'd agent could still rewrite the file.

## How it fits

```
Agent-Wallet-Setup        Starling-MCP                  Starling-Agent-Dashboard
 (encrypt keys)  ───────▶  (sign locally,    ──files──▶  (web UI: watch + control)
                            publish status)   ◀─files──   (halt / close / withdraw / pin treasury)
```

- Keys: [Agent-Wallet-Setup](https://github.com/thedopetoad/Agent-Wallet-Setup)
- Server: [Starling-MCP](https://github.com/thedopetoad/Starling-MCP)
- Protocol: [CONTROL_PROTOCOL.md](CONTROL_PROTOCOL.md)

Pure Python standard library, no third-party dependencies. License: MIT.
