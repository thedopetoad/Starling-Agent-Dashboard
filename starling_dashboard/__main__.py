"""``starling-dashboard`` — a local web UI for a *running* Starling MCP.

Default action launches the web dashboard: a tiny local server (127.0.0.1) that
serves a single-page app and talks to the live MCP over the file control plane in
``~/.starling/`` (see CONTROL_PROTOCOL.md). It never holds keys or signs — admin
actions only queue intent for the MCP.

Commands:
  starling-dashboard                 open the web dashboard (default)
  starling-dashboard web             same, with --port / --no-open
  starling-dashboard set-treasury    pin a withdraw destination from the terminal

Stdlib only — no third-party dependencies.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__, treasury as tre


def _run_set_treasury(args: argparse.Namespace) -> int:
    """Pin a withdraw destination from the terminal: paste the address, see the
    4-byte commitment, confirm, write ``~/.starling/treasury.json``. Stdlib only —
    the web UI's Wallet States tab does the same thing graphically."""
    print("◆ Starling — set withdraw destination")
    print(
        "Paste the wallet your funds withdraw/sweep to. Saved to a local file the MCP\n"
        f"reads ({tre.treasury_path()}) — the agent never re-types it.\n"
    )
    current = (tre.read_treasury() or {}).get("byChain") or {}
    if current:
        print("Currently pinned:")
        for c, a in current.items():
            print(f"  {c}  {a}  (commitment {tre.commitment(c, a)})")
        print()

    chains = [args.chain] if args.chain else list(tre.CHAINS)
    by_chain = dict(current)
    changed = False
    for chain in chains:
        raw = args.address if (args.address and args.chain) else input(f"{chain} withdraw address (blank to skip): ")
        if not raw.strip():
            continue
        norm = tre.normalize(chain, raw)
        if not norm:
            print(f"  ✗ not a valid {chain} address — skipped")
            continue
        print(f"  address    {norm}")
        print(f"  commitment {tre.commitment(chain, norm)}  (verify against your wallet — not chat)")
        ans = input(f"Pin this as the {chain} withdraw destination? [y/N] ").strip().lower()
        if ans == "y":
            by_chain[chain] = norm
            changed = True
        else:
            print("  skipped")

    if not changed:
        print("\nNothing changed.")
        return 1
    path = tre.write_treasury(by_chain)
    print(f"\n✓ Saved {path}")
    return 0


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

    p = argparse.ArgumentParser(
        prog="starling-dashboard",
        description="Local web dashboard for a running Starling MCP.",
    )
    p.add_argument("--version", action="version", version=f"starling-dashboard {__version__}")
    sub = p.add_subparsers(dest="command")

    web = sub.add_parser("web", help="open the web dashboard (default)")
    web.add_argument("--port", type=int, default=8787, help="local port (default 8787)")
    web.add_argument("--host", default="127.0.0.1", help="bind host (default 127.0.0.1 — keep it local)")
    web.add_argument("--no-open", action="store_true", help="don't auto-open the browser")

    st = sub.add_parser("set-treasury", help="pin a withdraw destination from the terminal")
    st.add_argument("--chain", choices=list(tre.CHAINS), help="chain to set (prompted if omitted)")
    st.add_argument("--address", help="non-interactive: the address (requires --chain)")

    args = p.parse_args()

    if args.command == "set-treasury":
        sys.exit(_run_set_treasury(args))

    # default + `web`: launch the server.
    from .web import serve

    port = getattr(args, "port", 8787)
    host = getattr(args, "host", "127.0.0.1")
    no_open = getattr(args, "no_open", False)
    try:
        serve(host=host, port=port, open_browser=not no_open)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
