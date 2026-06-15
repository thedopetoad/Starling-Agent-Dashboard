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
pip install starling-dashboard      # or: pip install mcp rich, then run from a clone

# point it at your MCP server (same command as your mcp.json) and watch:
starling-dashboard

# during local development, launch the MCP from a build:
starling-dashboard --mcp "node /path/to/Starling-MCP/dist/bin/starling-mcp.js"

# one frame and exit (handy for CI / a quick check):
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
| `--mcp "<cmd>"` | `npx -y @starling/execution-mcp` | command that launches the MCP server (or set `STARLING_MCP_CMD`) |
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
