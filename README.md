# Starling Agent Dashboard

**Watch your trading agent live on your desktop.** A small, open example that
connects to the [Starling MCP server](https://github.com/thedopetoad/Starling-MCP)
over stdio and renders its live state in your terminal. Fork it, embed it, or
extend it as the MCP grows new analytics tools.

It's **read-only with respect to funds and keys** — it reads status and public
addresses from the MCP and never signs, moves funds, or touches key material. The
one thing it writes is *your* human-confirmed **withdraw destination** (a public
address, to `~/.starling/treasury.json`) when you run `set-treasury` — never a
transaction, never key material.

> **Prerequisite:** Python 3.10+ and the Starling MCP server reachable by the
> launch command (default `npx -y @starling/execution-mcp`, which needs Node).

## Quick start

```bash
# install straight from GitHub (no clone needed):
pip install git+https://github.com/thedopetoad/Starling-Agent-Dashboard

# …or from a clone:
#   git clone https://github.com/thedopetoad/Starling-Agent-Dashboard
#   cd Starling-Agent-Dashboard && pip install -e .

# watch your agent — by default it launches the MCP straight from GitHub:
starling-dashboard

# point at a local MCP build instead:
starling-dashboard --mcp "node /path/to/Starling-MCP/dist/bin/starling-mcp.js"

# one frame and exit (handy for a quick check / CI):
starling-dashboard --once
```

## Set your withdraw destination

Pin the wallet your funds withdraw/sweep home to — once, by **pasting it here**, not
into chat or a hand-edited `.env`:

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
| `--mcp "<cmd>"` | `npx -y github:thedopetoad/Starling-MCP` | command that launches the MCP server (or set `STARLING_MCP_CMD`) |
| `--interval <s>` | `5` | refresh interval |
| `--once` | off | render one frame and exit |
| `--key sk_live_…` | `$STARLING_KEY` | analytics MCP key (forwarded to the server) |

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
