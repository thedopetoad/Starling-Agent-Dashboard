"""Starling Agent Dashboard — a click-to-open control panel for a *running* MCP.

Double-click ``run-dashboard.bat`` (Windows) / ``run-dashboard.command`` (macOS) to
open it — no terminal. It does NOT launch or share the trading MCP's process; it
talks to the live MCP through the file control plane in ``~/.starling/`` (see
CONTROL_PROTOCOL.md and ``controlplane.py``):

  • reads ``status.json`` the MCP publishes → live network / venues / positions /
    PnL / trading state, refreshed ~1s;
  • drives admin buttons → **Halt all trading** (kill-switch flag), **Resume**,
    **Close all positions**, **Withdraw to treasury**, **Set withdraw destination**.

No background threads, no asyncio, no ``mcp``/``rich`` import — just polling small
local files on a Tk timer. It never holds keys; the destructive buttons only *queue*
intent for the MCP, which runs them behind its own guardrails.
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

from . import __version__, controlplane as cp
from . import treasury as tre

# ── palette (Starling brand) ──────────────────────────────────────────────────
BG = "#0b1322"
PANEL = "#0f1a2e"
BORDER = "#22324a"
TEXT = "#e6edf6"
DIM = "#8aa0b8"
ACCENT = "#86c8ff"
GREEN = "#4ade80"
RED = "#f8717a"
YELLOW = "#fbbf24"
GREY = "#6b7a90"
HALT_BG = "#3a1620"
ACTIVE_BG = "#11331f"

if sys.platform == "win32":
    MONO = ("Consolas", 11)
    SANS = ("Segoe UI", 10)
    SANS_B = ("Segoe UI Semibold", 14)
    BANNER_F = ("Segoe UI Semibold", 17)
elif sys.platform == "darwin":
    MONO = ("Menlo", 12)
    SANS = ("Helvetica Neue", 12)
    SANS_B = ("Helvetica Neue", 16, "bold")
    BANNER_F = ("Helvetica Neue", 19, "bold")
else:
    MONO = ("DejaVu Sans Mono", 11)
    SANS = ("DejaVu Sans", 10)
    SANS_B = ("DejaVu Sans", 14, "bold")
    BANNER_F = ("DejaVu Sans", 18, "bold")

POLL_MS = 1000


def _short(addr) -> str:
    if not addr:
        return "—"
    addr = str(addr)
    return addr if len(addr) <= 20 else f"{addr[:8]}…{addr[-6:]}"


def _trunc(s, n=28) -> str:
    s = str(s or "")
    return s if len(s) <= n else s[: n - 1] + "…"


def _ago(age) -> str:
    if age is None:
        return "never"
    if age < 0:
        return "just now"
    if age < 90:
        return f"{age:.0f}s ago"
    return f"{age / 60:.0f}m ago"


def _log_path() -> Path:
    return tre.starling_dir() / "dashboard.log"


def _log(msg: str) -> None:
    try:
        p = _log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(msg.rstrip() + "\n")
    except OSError:
        pass


class Dashboard:
    def __init__(self, root):
        import tkinter as tk

        self.tk = tk
        self.root = root
        self._pending: dict[str, str] = {}      # cmd id -> action, awaiting ack
        self._flash_until = 0.0

        root.title("Starling — Agent Dashboard")
        root.configure(bg=BG)
        root.minsize(600, 640)
        try:
            root.geometry("640x700")
        except Exception:
            pass

        self._build()
        self.root.after(50, self._poll)

    # -- layout -----------------------------------------------------------------
    def _build(self):
        tk = self.tk
        # header
        head = tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=18, pady=(16, 6))
        tk.Label(head, text="◆ Starling", font=SANS_B, fg=ACCENT, bg=BG).pack(side="left")
        tk.Label(head, text="Agent Dashboard", font=SANS, fg=DIM, bg=BG).pack(side="left", padx=(8, 0), pady=(4, 0))
        tk.Label(head, text=f"v{__version__}", font=SANS, fg=GREY, bg=BG).pack(side="right", pady=(4, 0))

        # heartbeat line
        self.hb = tk.Label(self.root, text="", font=SANS, fg=DIM, bg=BG, anchor="w")
        self.hb.pack(fill="x", padx=18, pady=(0, 8))

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        # trading-state banner
        self.banner_outer = tk.Frame(body, bg=BORDER)
        self.banner_outer.pack(fill="x", pady=(0, 12))
        self.banner = tk.Label(self.banner_outer, text="…", font=BANNER_F, fg=DIM, bg=PANEL, pady=14)
        self.banner.pack(fill="both", padx=1, pady=1)
        self.banner_sub = None  # set in render via banner text only (kept simple)

        # meta
        meta_o, meta = self._card(body)
        meta_o.pack(fill="x", pady=(0, 10))
        row = tk.Frame(meta, bg=PANEL)
        row.pack(fill="x", padx=14, pady=12)
        self.lbl_network = self._kv(row, "network", "…", GREEN)
        self.lbl_keysrc = self._kv(row, "key source", "…", ACCENT)
        self.lbl_pnl = self._kv(row, "unrealized P&L", "…", DIM)

        # venues
        ven_o, ven = self._card(body, "Venues")
        ven_o.pack(fill="x", pady=(0, 10))
        grid = tk.Frame(ven, bg=PANEL)
        grid.pack(fill="x", padx=14, pady=(6, 12))
        grid.columnconfigure(2, weight=1)
        self.venue_rows = {}
        for i, v in enumerate(("polygon", "hyperliquid", "solana")):
            tk.Label(grid, text=v, font=SANS, fg=TEXT, bg=PANEL, anchor="w", width=12).grid(row=i, column=0, sticky="w", pady=3)
            signer = tk.Label(grid, text="○ …", font=SANS, fg=GREY, bg=PANEL, anchor="w", width=10)
            signer.grid(row=i, column=1, sticky="w", pady=3)
            addr = tk.Label(grid, text="—", font=MONO, fg=DIM, bg=PANEL, anchor="w", cursor="hand2")
            addr.grid(row=i, column=2, sticky="w", pady=3)
            addr.bind("<Button-1>", lambda _e, ch=v: self._copy_address(ch))
            self.venue_rows[v] = {"signer": signer, "addr": addr, "full": None}

        # positions
        pos_o, pos = self._card(body, "Open positions")
        pos_o.pack(fill="both", expand=True, pady=(0, 12))
        self.pos_body = tk.Frame(pos, bg=PANEL)
        self.pos_body.pack(fill="both", expand=True, padx=14, pady=(6, 12))

        # controls
        controls = tk.Frame(body, bg=BG)
        controls.pack(fill="x")
        top = tk.Frame(controls, bg=BG)
        top.pack(fill="x", pady=(0, 8))
        self.halt_btn = self._button(top, "■  Halt all trading", self._toggle_halt, kind="danger")
        self.halt_btn.pack(side="left")
        self.feedback = tk.Label(controls, text="", font=SANS, fg=DIM, bg=BG, anchor="w", justify="left")
        self.feedback.pack(fill="x", pady=(0, 8))

        bottom = tk.Frame(controls, bg=BG)
        bottom.pack(fill="x")
        self._button(bottom, "Close all positions", self._close_all, kind="warn").pack(side="left")
        self._button(bottom, "Withdraw to treasury", self._withdraw, kind="warn").pack(side="left", padx=(8, 0))
        self._button(bottom, "Set withdraw destination…", self._set_treasury, kind="ghost").pack(side="right")

    # -- widget helpers ---------------------------------------------------------
    def _card(self, parent, title=None):
        tk = self.tk
        outer = tk.Frame(parent, bg=BORDER)
        inner = tk.Frame(outer, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        if title:
            tk.Label(inner, text=title, font=SANS, fg=DIM, bg=PANEL, anchor="w").pack(fill="x", padx=14, pady=(10, 0))
        return outer, inner

    def _kv(self, parent, label, value, color):
        tk = self.tk
        cell = tk.Frame(parent, bg=PANEL)
        cell.pack(side="left", padx=(0, 26))
        tk.Label(cell, text=label, font=SANS, fg=DIM, bg=PANEL).pack(anchor="w")
        val = tk.Label(cell, text=value, font=MONO, fg=color, bg=PANEL)
        val.pack(anchor="w")
        return val

    def _button(self, parent, text, cmd, kind="primary"):
        tk = self.tk
        styles = {
            "primary": (BG, ACCENT, "#9fd2ff"),
            "danger": ("#ffffff", "#d6334a", "#e5566a"),
            "resume": (BG, GREEN, "#6ef0a0"),
            "warn": (TEXT, "#243349", BORDER),
            "ghost": (ACCENT, PANEL, BORDER),
        }
        fg, bg, active = styles.get(kind, styles["primary"])
        return tk.Button(parent, text=text, command=cmd, font=SANS, fg=fg, bg=bg,
                         activeforeground=fg, activebackground=active, relief="flat",
                         bd=0, padx=14, pady=8, cursor="hand2", highlightthickness=0)

    def _flash(self, msg, color=ACCENT, secs=6.0):
        self.feedback.config(text=msg, fg=color)
        self._flash_until = time.monotonic() + secs

    # -- poll + render ----------------------------------------------------------
    def _poll(self):
        try:
            st = cp.read_status()
            self._render(st)
            self._check_acks()
        except Exception:
            _log("poll error:\n" + traceback.format_exc())
        self.root.after(POLL_MS, self._poll)

    def _render(self, st: cp.Status):
        halted_flag = cp.is_halted()

        # heartbeat
        if not st.present:
            self.hb.config(text="✕  no heartbeat yet — waiting for the MCP to publish ~/.starling/status.json", fg=RED)
        elif st.error:
            self.hb.config(text=f"✕  status.json: {st.error}", fg=RED)
        elif st.live:
            pid = f" · pid {st.pid}" if st.pid else ""
            self.hb.config(text=f"●  live · updated {_ago(st.age)}{pid}", fg=GREEN)
        else:
            self.hb.config(text=f"○  stale · MCP last seen {_ago(st.age)} — is it still running?", fg=YELLOW)

        # banner (trading state)
        self._render_banner(st, halted_flag)

        # halt/resume button reflects intent
        if halted_flag:
            self.halt_btn.config(text="▶  Resume trading")
            self._restyle(self.halt_btn, "resume")
        else:
            self.halt_btn.config(text="■  Halt all trading")
            self._restyle(self.halt_btn, "danger")

        # meta
        self.lbl_network.config(text=st.network, fg=GREEN if st.network == "mainnet" else YELLOW)
        self.lbl_keysrc.config(text=st.key_source)
        unrl = st.pnl.get("unrealized")
        if unrl is None:
            self.lbl_pnl.config(text="—", fg=DIM)
        else:
            self.lbl_pnl.config(text=f"{unrl:+.2f}", fg=GREEN if unrl >= 0 else RED)

        # venues
        for v, row in self.venue_rows.items():
            info = st.venues.get(v, {}) if isinstance(st.venues.get(v), dict) else {}
            loaded = bool(info.get("signerLoaded"))
            row["signer"].config(text="● ready" if loaded else "○ none", fg=GREEN if loaded else GREY)
            full = info.get("address")
            row["full"] = full
            row["addr"].config(text=_short(full), fg=DIM if full else GREY)

        self._render_positions(st)

    def _render_banner(self, st: cp.Status, halted_flag: bool):
        if halted_flag:
            confirmed = st.live and not st.trading_enabled
            txt = "TRADING HALTED" if confirmed else "HALTING — kill-switch set…"
            self._set_banner(txt, RED, HALT_BG)
        elif not st.live:
            self._set_banner("MCP OFFLINE — no fresh heartbeat", GREY, PANEL)
        elif st.trading_enabled:
            self._set_banner("● TRADING ACTIVE", GREEN, ACTIVE_BG)
        else:
            reason = f" — {st.halt_reason}" if st.halt_reason else ""
            self._set_banner(f"TRADING DISABLED{reason}", YELLOW, PANEL)

    def _set_banner(self, text, fg, bg):
        self.banner.config(text=text, fg=fg, bg=bg)

    def _restyle(self, btn, kind):
        styles = {
            "danger": ("#ffffff", "#d6334a", "#e5566a"),
            "resume": (BG, GREEN, "#6ef0a0"),
        }
        fg, bg, active = styles[kind]
        btn.config(fg=fg, bg=bg, activeforeground=fg, activebackground=active)

    def _render_positions(self, st: cp.Status):
        tk = self.tk
        for c in self.pos_body.winfo_children():
            c.destroy()
        positions = st.positions
        if "positions" not in st.raw:
            tk.Label(self.pos_body, text="positions not reported by this MCP build", font=SANS, fg=GREY, bg=PANEL, anchor="w").pack(fill="x")
            return
        if not positions:
            tk.Label(self.pos_body, text="flat — no open positions", font=SANS, fg=GREY, bg=PANEL, anchor="w").pack(fill="x")
            return
        header = tk.Frame(self.pos_body, bg=PANEL)
        header.pack(fill="x")
        for txt, w, side in (("venue", 12, "left"), ("market", 30, "left"),
                             ("side", 6, "left"), ("size", 10, "left"), ("P&L", 8, "right")):
            tk.Label(header, text=txt, font=SANS, fg=GREY, bg=PANEL, width=w,
                     anchor=("e" if side == "right" else "w")).pack(side=side)
        for p in positions[:8]:
            r = tk.Frame(self.pos_body, bg=PANEL)
            r.pack(fill="x", pady=1)
            tk.Label(r, text=_trunc(p.get("venue"), 12), font=SANS, fg=TEXT, bg=PANEL, width=12, anchor="w").pack(side="left")
            tk.Label(r, text=_trunc(p.get("market"), 30), font=SANS, fg=DIM, bg=PANEL, width=30, anchor="w").pack(side="left")
            tk.Label(r, text=_trunc(p.get("side"), 6), font=SANS, fg=DIM, bg=PANEL, width=6, anchor="w").pack(side="left")
            tk.Label(r, text=_trunc(p.get("size"), 10), font=MONO, fg=DIM, bg=PANEL, width=10, anchor="w").pack(side="left")
            pnl = p.get("pnl")
            ptxt = f"{pnl:+.2f}" if isinstance(pnl, (int, float)) else "—"
            tk.Label(r, text=ptxt, font=MONO, fg=(GREEN if (pnl or 0) >= 0 else RED), bg=PANEL, width=8, anchor="e").pack(side="right")
        if len(positions) > 8:
            tk.Label(self.pos_body, text=f"+ {len(positions) - 8} more", font=SANS, fg=GREY, bg=PANEL, anchor="w").pack(fill="x", pady=(2, 0))

    def _check_acks(self):
        # let a flash decay
        if self._flash_until and time.monotonic() >= self._flash_until and not self._pending:
            self._flash_until = 0.0
            self.feedback.config(text="", fg=DIM)
        for cid in list(self._pending):
            ack = cp.read_ack(cid)
            if not ack:
                continue
            status = ack.get("status")
            if status == "in_progress":
                self._flash(f"{ack.get('action')}: {ack.get('message', 'working…')}", ACCENT, 30)
                continue
            action = self._pending.pop(cid)
            color = GREEN if status == "ok" else RED
            self._flash(f"{action} → {status}: {ack.get('message', '')}", color, 8)
            cp.clear_command(cid)
        if self._pending:
            n = len(self._pending)
            self.feedback.config(text=self.feedback.cget("text") + f"   ({n} command{'s' if n > 1 else ''} pending…)")

    # -- actions ----------------------------------------------------------------
    def _toggle_halt(self):
        from tkinter import messagebox

        if cp.is_halted():
            if not messagebox.askyesno("Resume trading",
                                       "Remove the kill-switch and let the agent trade again?",
                                       parent=self.root):
                return
            cp.clear_halt()
            self._flash("resuming — kill-switch cleared", GREEN, 5)
        else:
            cp.set_halt("manual")  # instant, no confirm — this is the emergency stop
            self._flash("HALT set — agent must stop signing. Confirming with MCP…", RED, 8)

    def _close_all(self):
        from tkinter import messagebox

        if not messagebox.askyesno(
            "Close all positions",
            "Market-close EVERY open position across all venues now?\n\n"
            "This tells the MCP to sell everything at market. It cannot be undone.",
            icon="warning", parent=self.root,
        ):
            return
        cid = cp.enqueue_command("close_all")
        self._pending[cid] = "close_all"
        self._flash("close_all queued — waiting for the MCP…", ACCENT, 30)

    def _withdraw(self):
        from tkinter import messagebox

        pinned = (tre.read_treasury() or {}).get("byChain") or {}
        if not pinned:
            messagebox.showwarning(
                "No destination pinned",
                "Set a withdraw destination first (Set withdraw destination…), so the MCP "
                "knows where to sweep funds.", parent=self.root)
            return
        dest = "\n".join(f"  {c}: {a}" for c, a in pinned.items())
        if not messagebox.askyesno(
            "Withdraw to treasury",
            "Tell the MCP to sweep free balances to your pinned destination?\n\n"
            f"{dest}\n\nVerify these against your wallet. Proceed?",
            icon="warning", parent=self.root,
        ):
            return
        cid = cp.enqueue_command("withdraw", {"chain": "all"})
        self._pending[cid] = "withdraw"
        self._flash("withdraw queued — waiting for the MCP…", ACCENT, 30)

    def _set_treasury(self):
        TreasuryDialog(self)

    def _copy_address(self, chain):
        full = self.venue_rows.get(chain, {}).get("full")
        if not full:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(str(full))
        self._flash(f"copied {chain} address", ACCENT, 2)


# ── set-treasury dialog (paste + commitment + confirm) ─────────────────────────
class TreasuryDialog:
    def __init__(self, app: Dashboard):
        tk = app.tk
        self.app = app
        win = tk.Toplevel(app.root, bg=BG)
        self.win = win
        win.title("Set withdraw destination")
        win.transient(app.root)
        win.resizable(False, False)

        tk.Label(win, text="Set withdraw destination", font=SANS_B, fg=ACCENT, bg=BG).pack(anchor="w", padx=16, pady=(16, 2))
        tk.Label(win, text=("Paste the wallet your funds sweep/withdraw to. Saved to a local file the MCP\n"
                            "reads — the agent never types it. Verify the commitment against your wallet."),
                 font=SANS, fg=DIM, bg=BG, justify="left").pack(anchor="w", padx=16, pady=(0, 12))

        row = tk.Frame(win, bg=BG)
        row.pack(fill="x", padx=16)
        tk.Label(row, text="chain", font=SANS, fg=DIM, bg=BG).pack(side="left")
        self.chain = tk.StringVar(value="polygon")
        opt = tk.OptionMenu(row, self.chain, *tre.CHAINS, command=lambda _=None: self._recompute())
        opt.config(font=SANS, bg=PANEL, fg=TEXT, activebackground=BORDER, activeforeground=TEXT,
                   relief="flat", highlightthickness=0, bd=0)
        opt["menu"].config(bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground=BG)
        opt.pack(side="left", padx=(8, 0))

        tk.Label(win, text="address", font=SANS, fg=DIM, bg=BG).pack(anchor="w", padx=16, pady=(12, 4))
        self.entry = tk.Entry(win, font=MONO, bg=PANEL, fg=TEXT, insertbackground=TEXT, width=52,
                              relief="flat", highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT)
        self.entry.pack(fill="x", padx=16, ipady=5)
        self.entry.bind("<KeyRelease>", lambda _e: self._recompute())

        self.note = tk.Label(win, text="", font=MONO, fg=DIM, bg=BG, anchor="w", justify="left")
        self.note.pack(fill="x", padx=16, pady=(10, 0))

        bar = tk.Frame(win, bg=BG)
        bar.pack(fill="x", padx=16, pady=16)
        app._button(bar, "Pin destination", self._save).pack(side="right")
        app._button(bar, "Cancel", win.destroy, kind="ghost").pack(side="right", padx=(0, 8))
        self._recompute()
        win.grab_set()
        self.entry.focus_set()

    def _recompute(self):
        chain = self.chain.get()
        norm = tre.normalize(chain, self.entry.get())
        if norm:
            self.note.config(text=f"commitment  {tre.commitment(chain, norm)}\n"
                                  "verify against your wallet / recovery sheet — not against chat", fg=GREEN)
        elif self.entry.get().strip():
            self.note.config(text=f"not a valid {chain} address yet", fg=RED)
        else:
            self.note.config(text="", fg=DIM)

    def _save(self):
        from tkinter import messagebox

        chain = self.chain.get()
        norm = tre.normalize(chain, self.entry.get())
        if not norm:
            messagebox.showwarning("Starling", f"That isn't a valid {chain} address.", parent=self.win)
            return
        if not messagebox.askyesno("Confirm withdraw destination",
                                   f"Pin this as the {chain} withdraw destination?\n\n{norm}\n\n"
                                   f"commitment {tre.commitment(chain, norm)}\n\n"
                                   "Verify the commitment against your wallet — not against anything an agent printed.",
                                   parent=self.win):
            return
        merged = dict((tre.read_treasury() or {}).get("byChain") or {})
        merged[chain] = norm
        path = tre.write_treasury(merged)
        self.win.destroy()
        self.app._flash(f"pinned {chain} → {_short(norm)}  ({path})", GREEN, 6)


# ── entry point ────────────────────────────────────────────────────────────────
def main() -> None:
    try:
        import tkinter as tk
    except Exception:
        print(
            "The desktop window needs Tkinter, which isn't available in this Python.\n"
            "  • macOS (Homebrew):  brew install python-tk\n"
            "  • or install Python from https://www.python.org (bundles Tk)\n",
            file=sys.stderr,
        )
        _log("tkinter unavailable:\n" + traceback.format_exc())
        sys.exit(1)

    try:
        root = tk.Tk()
    except Exception as exc:
        print(f"Couldn't open a window: {exc}", file=sys.stderr)
        _log("Tk() failed:\n" + traceback.format_exc())
        sys.exit(1)

    try:
        Dashboard(root)
        root.mainloop()
    except Exception:
        _log("GUI crashed:\n" + traceback.format_exc())
        try:
            from tkinter import messagebox
            messagebox.showerror("Starling Dashboard", "Something went wrong. See ~/.starling/dashboard.log")
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
