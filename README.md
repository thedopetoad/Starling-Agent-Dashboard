# Starling Agent Dashboard

**Watch your trading agent live on your desktop.** A small, open example that
connects to the [Starling MCP](https://github.com/thedopetoad/Starling-MCP)
over stdio and renders its live state — as a click-to-open **desktop window**, or
in your terminal. Fork it, embed it, or extend it as the MCP grows new analytics
tools.

It's **read-only with respect to funds and keys** — it reads status and public
addresses from the MCP and never signs, moves funds, or touches key material. The
one thing it writes is *your* human-confirmed **withdraw destination** (a public
address, to `~/.starling/treasury.json`) when you run `set-treasury` — never a
transaction, never key material.

> **Prerequisite:** Python 3.10+. The live view also needs your local Starling
> MCP build reachable by the launch command — clone
> [Starling-MCP](https://github.com/thedopetoad/Starling-MCP), run `npm install`
> (its prepare script builds `dist/`), then point `--mcp` at the built bin.
> Note: `set-treasury` writes a local file and does **not** need the MCP — only
> the live view launches it.

## Quick start — just double-click (desktop window)

No terminal, no `pip`, no flags. Download or clone this repo, then:

- **Windows** — double-click **`run-dashboard.bat`**
- **macOS** — double-click **`run-dashboard.command`** (first time: right-click → Open)
- **Linux** — run **`./run-dashboard.sh`** (needs Tk: `sudo apt install python3-tk`)

The launcher sets up a private virtual environment and installs the two
dependencies the first time (~30s), then opens the window. After that it just
opens instantly. The only prerequisite is **Python 3.10+** — if it's missing, the
launcher points you at the download page.

**Finding your MCP is automatic.** On first launch the window looks for a sibling
`Starling-MCP` build (e.g. `../Starling-MCP/dist/bin/starling-mcp.js`) and, if it
finds one, remembers it so future launches are zero-config. If it can't find one,
the window asks you to pick the built `starling-mcp.js` once (Browse…) and saves
your choice to `~/.starling/dashboard.json`. You can change it any time under
**Settings…**. (Clone [Starling-MCP](https://github.com/thedopetoad/Starling-MCP)
and run `npm install` first — its prepare script builds `dist/`.)

## Terminal version

Prefer the terminal? Install it as a package and run the CLI:

```bash
git clone https://github.com/thedopetoad/Starling-Agent-Dashboard
cd Starling-Agent-Dashboard
pip install -e .                      # editable: your edits take effect immediately
```

```bash
# the desktop window, from the CLI:
starling-dashboard gui

# the live terminal view — point at your local MCP build:
starling-dashboard --mcp "node /path/to/Starling-MCP/dist/bin/starling-mcp.js"

# …or set it once and just run `starling-dashboard`:
export STARLING_MCP_CMD="node /path/to/Starling-MCP/dist/bin/starling-mcp.js"
starling-dashboard

# one frame and exit (handy for a quick check / CI):
starling-dashboard --once --mcp "node /path/to/Starling-MCP/dist/bin/starling-mcp.js"
```

## Set your withdraw destination

Pin the wallet your funds withdraw/sweep home to — once, by **pasting it here**, not
into chat or a hand-edited `.env`. In the desktop window, click **“Set withdraw
destination…”**; from the terminal:

```bash
starling-dashboard set-treasury                 # prompts for chain + address
starling-dashboard set-treasury --chain polygon # skip the chain prompt
```

You paste the address, the tool validates it and shows a 4-byte **commitment**, you
confirm, and it's written to `~/.starling/treasury.json` (honoring `STARLING_DIR`)
— the same file the MCP reads. The point is *transcription integrity*: your exact
bytes reach disk, and the trading agent never re-types the 40/44-char string into a
config (where one flipped character would strand a sweep). This is the **preferred**
way to set the destination. (If you have no dashboard, a file-capable agent can write
that file for you as a fallback, from an address you give it — then read it back so
you confirm the commitment. The MCP itself exposes no address-setting tool.)

> Verify the commitment against your wallet / recovery sheet — **not** against
> anything the agent printed in chat. This is a transcription check, not a security
> control: a code-exec'd agent could still rewrite the file (the same honest ceiling
> as the MCP's keystore-sealed treasury). The live view shows the current
> destination, its source (`keystore` / `dashboard` / red `CONFLICT`), and commitment.

It launches the MCP exactly the way your agent does, then polls `auth_check`,
`get_wallet_addresses`, and `ping`, showing:

- **network** (testnet / mainnet) and **key source** (keystore / env / file)
- per-venue **signer status** and **public address**
- your **withdraw destination** per chain (address, source, commitment)
- round-trip **ping**

```
╭───── ◆ Starling — Agent Dashboard ──────────────────────────────╮
│  network  testnet     key source  keystore     unlock  env       │
│                                                                   │
│  Venue        Signer     Address                                  │
│  polygon      ● ready    0x1440B1…374bB1                          │
│  hyperliquid  ● ready    0x4f072d…266056                          │
│  solana       ● ready    FdY9B9Jn…CMRVPw                          │
│                                                                   │
│  ping 12 ms    ·    Ctrl-C to quit                                │
╰───────────────────────────────────────────────────────────────────╯
```

## Options

| flag | default | meaning |
|---|---|---|
| `--mcp "<cmd>"` | *required* (or `STARLING_MCP_CMD`) | command that launches your local Starling MCP build, e.g. `node /path/to/Starling-MCP/dist/bin/starling-mcp.js`. Not needed by `set-treasury`. |
| `--interval <s>` | `5` | refresh interval |
| `--once` | off | render one frame and exit |
| `--key sk_live_…` | `$STARLING_KEY` | analytics MCP key (forwarded to the MCP) |

Any `STARLING_*` environment variables (key source, unlock mode, network) are
passed through to the spawned MCP, so configure the server once and the
dashboard inherits it.

## How it fits

```
Agent-Wallet-Setup        Starling-MCP                 Starling-Agent-Dashboard
 (encrypt keys)  ───────▶  (sign locally)  ◀──stdio──  (watch it live, read-only)
```

- Keys: [Agent-Wallet-Setup](https://github.com/thedopetoad/Agent-Wallet-Setup)
- Server: [Starling-MCP](https://github.com/thedopetoad/Starling-MCP)

Built on the official [MCP Python SDK](https://pypi.org/project/mcp/) + [rich](https://pypi.org/project/rich/). License: MIT.
