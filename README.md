# Starling Agent Dashboard

**Watch and control your trading agent from your desktop.** A small, open example
that shows a *running* [Starling MCP](https://github.com/thedopetoad/Starling-MCP)
live — network, venues, open positions, P&L, trading state — and gives you
**admin buttons**: halt all trading, resume, close all positions, withdraw to your
pinned wallet.

It opens as a **click-to-open desktop window** (no terminal). There's also a
read-only terminal view for quick checks.

**It never holds keys or signs anything itself.** The window talks to the live MCP
through small files in `~/.starling/` (see [CONTROL_PROTOCOL.md](CONTROL_PROTOCOL.md)):
it *reads* the state the MCP publishes, and the buttons only *queue intent* — the
MCP runs the actual trade/withdraw behind its own guardrails. The kill-switch is the
one exception, and it's deliberately the simplest thing possible: a flag file the
MCP refuses to trade while it exists.

> **Prerequisite:** Python 3.10+. The window needs a Starling MCP that implements
> the control protocol (it publishes `~/.starling/status.json` and watches the
> control files). No MCP yet? Run the bundled **mock** to see everything work —
> see [Try it without a real MCP](#try-it-without-a-real-mcp).

## Quick start — just double-click

No terminal, no `pip`, no flags. Download or clone this repo, then:

- **Windows** — double-click **`run-dashboard.bat`**
- **macOS** — double-click **`run-dashboard.command`** (first time: right-click → Open)
- **Linux** — run **`./run-dashboard.sh`** (needs Tk: `sudo apt install python3-tk`)

The launcher sets up a private virtual environment the first time (~30s), then
opens the window — and just opens instantly after that. The only prerequisite is
**Python 3.10+**; if it's missing, the launcher points you at the download page.

## How it connects

The dashboard does **not** launch or share the trading MCP's process — an MCP over
stdio is a private pipe owned by whatever started your agent. Instead both sides
coordinate through files under `~/.starling/` (honoring `STARLING_DIR`):

```
~/.starling/
  status.json          MCP → dashboard   heartbeat: live state (network, venues, positions, tradingEnabled)
  trading.halt         dashboard → MCP   kill-switch FLAG — present == halted
  control/<id>.cmd.json  dashboard → MCP   an action (close_all / withdraw)
  control/<id>.ack.json  MCP → dashboard   that action's result
```

This works while the bot is mid-trade, needs no ports or auth, and survives
restarts. The full wire contract — and a checklist for the MCP side — is in
**[CONTROL_PROTOCOL.md](CONTROL_PROTOCOL.md)**.

## The buttons

| button | what it does |
|---|---|
| **Halt all trading** | drops the `trading.halt` flag. The MCP's policy gate must refuse to sign while it exists — an instant, fail-safe stop. |
| **Resume trading** | removes the flag (confirmation required). |
| **Close all positions** | queues `close_all`; the MCP market-closes every open position and acks the result. |
| **Withdraw to treasury** | queues `withdraw`; the MCP sweeps free balances to your **pinned** destination (below). Blocked until one is pinned. |
| **Set withdraw destination…** | pin the wallet funds sweep to (see next section). |

Destructive actions (close all, withdraw) show a confirmation first. The window
shows the result of each queued command as the MCP acks it.

## Try it without a real MCP

A bundled mock implements the MCP side of the protocol (no keys, no network, no
trades) so you can see the live view and buttons work end-to-end. In one terminal:

```bash
# point both at a scratch dir so it never touches your real ~/.starling
STARLING_DIR=./.scratch python tools/mock_mcp.py
```

…then launch the dashboard with the same `STARLING_DIR` (or just double-click the
launcher if you let it use the default dir). Halt/Resume flips the banner;
Close-all empties the fake book; Withdraw acks a mock sweep. `tools/mock_mcp.py` is
also a runnable reference for whoever implements the real MCP side.

## Set your withdraw destination

Pin the wallet your funds withdraw/sweep home to — once, by **pasting it here**, not
into chat or a hand-edited `.env`. In the window, click **“Set withdraw
destination…”**; from the terminal:

```bash
starling-dashboard set-treasury                 # prompts for chain + address
starling-dashboard set-treasury --chain polygon # skip the chain prompt
```

You paste the address, the tool validates it and shows a 4-byte **commitment**, you
confirm, and it's written to `~/.starling/treasury.json` (honoring `STARLING_DIR`)
— the same file the MCP reads for `withdraw`. The point is *transcription
integrity*: your exact bytes reach disk, and the agent never re-types the 40/44-char
string (where one flipped character would strand a sweep).

> Verify the commitment against your wallet / recovery sheet — **not** against
> anything an agent printed in chat. This is a transcription check, not a security
> control: a code-exec'd agent could still rewrite the file.

## Terminal version (read-only)

Prefer the terminal, or just want a quick read-only peek that launches its own
read-only MCP copy? Install the package and use the CLI:

```bash
git clone https://github.com/thedopetoad/Starling-Agent-Dashboard
cd Starling-Agent-Dashboard
pip install -e .

starling-dashboard gui                                                  # the desktop window
starling-dashboard --mcp "node /path/to/Starling-MCP/dist/bin/starling-mcp.js"   # live terminal view
starling-dashboard --once --mcp "node .../starling-mcp.js"              # one frame, for CI
```

The terminal view spawns its own read-only MCP instance (`auth_check` /
`get_wallet_addresses` / `ping`) and so needs that instance's key source in its
environment; the desktop window does not — it reads the running agent's published
`status.json` instead.

## How it fits

```
Agent-Wallet-Setup        Starling-MCP                  Starling-Agent-Dashboard
 (encrypt keys)  ───────▶  (sign locally,    ──files──▶  (watch live + admin buttons)
                            publish status)   ◀─files──   (halt / close / withdraw)
```

- Keys: [Agent-Wallet-Setup](https://github.com/thedopetoad/Agent-Wallet-Setup)
- Server: [Starling-MCP](https://github.com/thedopetoad/Starling-MCP)
- Protocol: [CONTROL_PROTOCOL.md](CONTROL_PROTOCOL.md)

The window is pure Python standard library + Tk. The terminal view additionally uses
the official [MCP Python SDK](https://pypi.org/project/mcp/) + [rich](https://pypi.org/project/rich/). License: MIT.
