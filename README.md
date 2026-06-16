# Starling Agent Dashboard

**Watch your trading agent live on your desktop.** A small, open example that
connects to the [Starling MCP server](https://github.com/thedopetoad/Starling-MCP)
over stdio and renders its live state in your terminal. Fork it, embed it, or
extend it as the MCP grows new analytics tools.

It's **read-only** — it reads status and public addresses from the MCP and never
moves funds or touches key material.

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

It launches the MCP exactly the way your agent does, then polls `auth_check`,
`get_wallet_addresses`, and `ping`, showing:

- **network** (testnet / mainnet) and **key source** (keystore / env / file)
- per-venue **signer status** and **public address**
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
