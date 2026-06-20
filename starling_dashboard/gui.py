"""`starling-dashboard` as a click-to-open desktop window (Tkinter).

Same read-only view as the terminal dashboard — network / key source / per-venue
signer + address / withdraw destination / ping — but in a real window you open by
double-clicking ``run-dashboard.bat`` (Windows) or ``run-dashboard.command`` (macOS),
no terminal required.

Architecture: Tk owns the main thread; a background thread runs an asyncio loop that
launches the MCP over stdio and polls its read-only tools, handing each frame to the
UI through a thread-safe queue. It never signs or moves funds — the one thing it can
write is *your* withdraw destination, via the same paste-and-confirm flow as the CLI.
"""

from __future__ import annotations

import asyncio
import os
import queue
import sys
import threading
import time
import traceback
from pathlib import Path

from . import __version__, config as cfg
from . import treasury as tre
from .client import VENUES, Snapshot, fetch_snapshot, server_params_parts

# ── palette (mirrors the rich TUI / Starling brand) ──────────────────────────
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

if sys.platform == "win32":
    MONO = ("Consolas", 11)
    SANS = ("Segoe UI", 10)
    SANS_B = ("Segoe UI Semibold", 14)
elif sys.platform == "darwin":
    MONO = ("Menlo", 12)
    SANS = ("Helvetica Neue", 12)
    SANS_B = ("Helvetica Neue", 16, "bold")
else:
    MONO = ("DejaVu Sans Mono", 11)
    SANS = ("DejaVu Sans", 10)
    SANS_B = ("DejaVu Sans", 14, "bold")


def _short(addr: str | None) -> str:
    if not addr:
        return "—"
    return addr if len(addr) <= 20 else f"{addr[:8]}…{addr[-6:]}"


def _log_path() -> Path:
    return tre.starling_dir() / "dashboard.log"


def _log(msg: str) -> None:
    """Best-effort crash log — under pythonw there's no console to print to."""
    try:
        p = _log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(msg.rstrip() + "\n")
    except OSError:
        pass


# ── background MCP poller ────────────────────────────────────────────────────
class MCPWorker(threading.Thread):
    """Owns an asyncio loop on its own thread: launch the MCP, poll it, push each
    Snapshot to ``out`` (a queue the Tk side drains). Reconnects on failure until
    asked to stop."""

    def __init__(self, args: list[str], key: str | None, interval: float, out: "queue.Queue[Snapshot]"):
        super().__init__(daemon=True)
        self.args = list(args)
        self.key = key
        self.interval = max(0.5, float(interval))
        self.out = out
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            asyncio.run(self._main())
        except Exception as exc:  # never let the thread die silently
            _log("worker crashed:\n" + traceback.format_exc())
            self.out.put(Snapshot(error=f"{type(exc).__name__}: {exc}"))

    async def _main(self) -> None:
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        overrides = {"STARLING_KEY": self.key} if self.key else {}
        try:
            params = server_params_parts(self.args, overrides)
        except Exception as exc:
            self.out.put(Snapshot(error=f"bad MCP command: {exc}"))
            return

        while not self._stop.is_set():
            try:
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        while not self._stop.is_set():
                            self.out.put(await fetch_snapshot(session))
                            await self._sleep(self.interval)
            except Exception as exc:
                self.out.put(Snapshot(error=f"{type(exc).__name__}: {exc}"))
                await self._sleep(min(self.interval, 3.0))  # back off, then reconnect

    async def _sleep(self, secs: float) -> None:
        waited = 0.0
        while waited < secs and not self._stop.is_set():
            await asyncio.sleep(0.1)
            waited += 0.1


# ── the window ───────────────────────────────────────────────────────────────
class Dashboard:
    def __init__(self, root, key: str | None):
        import tkinter as tk

        self.tk = tk
        self.root = root
        self.key = key
        self.queue: "queue.Queue[Snapshot]" = queue.Queue()
        self.worker: MCPWorker | None = None
        self._connecting = False
        self._status_reset_at = 0.0

        root.title("Starling — Agent Dashboard")
        root.configure(bg=BG)
        root.minsize(560, 520)
        try:
            root.geometry("600x560")
        except Exception:
            pass
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_header()
        # The body swaps between the live dashboard and the first-run setup card.
        self.body = tk.Frame(root, bg=BG)
        self.body.pack(fill="both", expand=True, padx=18, pady=(0, 14))
        self._dash_frame = None
        self._setup_frame = None

        # Decide how to connect: saved config → env → auto-detect (then remember).
        args, source = cfg.resolve_mcp_args()
        if args:
            self._show_dashboard()
            self._start_worker(args)
            if source == "detected":
                self._flash(f"found your MCP next door — remembered it · {_short_cmd(args)}")
        else:
            self._show_setup()

        self.root.after(150, self._drain)
        self.root.after(500, self._tick_status)

    # -- chrome -----------------------------------------------------------------
    def _build_header(self):
        tk = self.tk
        head = tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=18, pady=(16, 8))
        tk.Label(head, text="◆ Starling", font=SANS_B, fg=ACCENT, bg=BG).pack(side="left")
        tk.Label(head, text="Agent Dashboard", font=SANS, fg=DIM, bg=BG).pack(side="left", padx=(8, 0), pady=(4, 0))
        tk.Label(head, text=f"v{__version__}", font=SANS, fg=GREY, bg=BG).pack(side="right", pady=(4, 0))

        self.status_dot = tk.Label(self.root, text="", font=SANS, bg=BG)
        self.status_dot.pack(anchor="w", padx=18)
        self.status_text = tk.Label(self.root, text="", font=SANS, fg=DIM, bg=BG, anchor="w", justify="left")
        self.status_text.pack(fill="x", padx=18, pady=(0, 4))

    def _set_status(self, dot: str, dot_color: str, text: str):
        self.status_dot.config(text=dot, fg=dot_color)
        self.status_text.config(text=text)

    def _flash(self, msg: str, secs: float = 4.0):
        """Show a transient note in the status line, then let the live state return."""
        self.status_text.config(text=msg, fg=ACCENT)
        self._status_reset_at = time.monotonic() + secs

    # -- views ------------------------------------------------------------------
    def _clear_body(self):
        for child in self.body.winfo_children():
            child.destroy()
        self._dash_frame = None
        self._setup_frame = None

    def _card(self, parent, title: str | None = None):
        tk = self.tk
        outer = tk.Frame(parent, bg=BORDER)
        inner = tk.Frame(outer, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        if title:
            tk.Label(inner, text=title, font=SANS, fg=DIM, bg=PANEL, anchor="w").pack(fill="x", padx=14, pady=(10, 0))
        return outer, inner

    def _show_dashboard(self):
        tk = self.tk
        self._clear_body()
        self._connecting = True

        # meta row
        meta_outer, meta = self._card(self.body)
        meta_outer.pack(fill="x", pady=(6, 10))
        row = tk.Frame(meta, bg=PANEL)
        row.pack(fill="x", padx=14, pady=12)
        self.lbl_network = self._kv(row, "network", "…", GREEN)
        self.lbl_keysrc = self._kv(row, "key source", "…", ACCENT)
        self.lbl_unlock = self._kv(row, "unlock", "", TEXT)

        # venues
        ven_outer, ven = self._card(self.body, "Venues")
        ven_outer.pack(fill="x", pady=(0, 10))
        grid = tk.Frame(ven, bg=PANEL)
        grid.pack(fill="x", padx=14, pady=(6, 12))
        grid.columnconfigure(2, weight=1)
        self.venue_rows = {}
        for i, v in enumerate(VENUES):
            name = tk.Label(grid, text=v, font=SANS, fg=TEXT, bg=PANEL, anchor="w", width=12)
            name.grid(row=i, column=0, sticky="w", pady=3)
            signer = tk.Label(grid, text="○ …", font=SANS, fg=GREY, bg=PANEL, anchor="w", width=10)
            signer.grid(row=i, column=1, sticky="w", pady=3)
            addr = tk.Label(grid, text="—", font=MONO, fg=DIM, bg=PANEL, anchor="w", cursor="hand2")
            addr.grid(row=i, column=2, sticky="w", pady=3)
            addr.bind("<Button-1>", lambda _e, ch=v: self._copy_address(ch))
            self.venue_rows[v] = {"signer": signer, "addr": addr, "full": None}

        # withdraw destination
        tre_outer, tre_inner = self._card(self.body, "Withdraw destination")
        tre_outer.pack(fill="x", pady=(0, 10))
        self.tre_body = tk.Frame(tre_inner, bg=PANEL)
        self.tre_body.pack(fill="x", padx=14, pady=(6, 12))

        # buttons
        btns = tk.Frame(self.body, bg=BG)
        btns.pack(fill="x", pady=(2, 0))
        self._button(btns, "Set withdraw destination…", self._open_set_treasury).pack(side="left")
        self._button(btns, "Reconnect", self._reconnect, primary=False).pack(side="right")
        self._button(btns, "Settings…", self._open_settings, primary=False).pack(side="right", padx=(0, 8))

        self._dash_frame = self.body
        self._set_status("○", GREY, "connecting to the Starling MCP…")

    def _show_setup(self):
        tk = self.tk
        self._clear_body()
        self._set_status("○", GREY, "not connected")

        outer, card = self._card(self.body, None)
        outer.pack(fill="both", expand=True, pady=(8, 0))
        tk.Label(card, text="Point me at your Starling MCP", font=SANS_B, fg=TEXT, bg=PANEL).pack(
            anchor="w", padx=16, pady=(16, 4)
        )
        tk.Label(
            card,
            text=("Couldn't auto-find a local Starling-MCP build next door.\n"
                  "Clone Starling-MCP, run `npm install` (builds dist/), then pick its built\n"
                  "entry point below — I'll remember it for next time."),
            font=SANS, fg=DIM, bg=PANEL, justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 12))

        ent_row = tk.Frame(card, bg=PANEL)
        ent_row.pack(fill="x", padx=16)
        self.setup_entry = tk.Entry(ent_row, font=MONO, bg=BG, fg=TEXT, insertbackground=TEXT,
                                    relief="flat", highlightthickness=1, highlightbackground=BORDER,
                                    highlightcolor=ACCENT)
        self.setup_entry.insert(0, "node /path/to/Starling-MCP/dist/bin/starling-mcp.js")
        self.setup_entry.pack(side="left", fill="x", expand=True, ipady=5)
        self._button(ent_row, "Browse…", self._browse_mcp, primary=False).pack(side="left", padx=(8, 0))

        self._button(card, "Save & Connect", self._save_setup).pack(anchor="e", padx=16, pady=14)
        self._setup_frame = self.body

    # -- small widget helpers ---------------------------------------------------
    def _kv(self, parent, label, value, value_color):
        tk = self.tk
        cell = tk.Frame(parent, bg=PANEL)
        cell.pack(side="left", padx=(0, 26))
        tk.Label(cell, text=label, font=SANS, fg=DIM, bg=PANEL).pack(anchor="w")
        val = tk.Label(cell, text=value, font=MONO, fg=value_color, bg=PANEL)
        val.pack(anchor="w")
        return val

    def _button(self, parent, text, cmd, primary=True):
        tk = self.tk
        fg = BG if primary else ACCENT
        bg = ACCENT if primary else PANEL
        active = "#9fd2ff" if primary else BORDER
        b = tk.Button(parent, text=text, command=cmd, font=SANS, fg=fg, bg=bg,
                      activeforeground=fg, activebackground=active, relief="flat",
                      bd=0, padx=14, pady=7, cursor="hand2", highlightthickness=0)
        return b

    # -- worker management ------------------------------------------------------
    def _start_worker(self, args: list[str]):
        self._stop_worker()
        self._connecting = True
        self.worker = MCPWorker(args, self.key, cfg.get_interval(), self.queue)
        self.worker.start()

    def _stop_worker(self):
        if self.worker is not None:
            self.worker.stop()
            self.worker = None

    def _reconnect(self):
        args, _ = cfg.resolve_mcp_args()
        if not args:
            self._show_setup()
            return
        if self._dash_frame is None:
            self._show_dashboard()
        self._start_worker(args)
        self._flash("reconnecting…", 2.0)

    # -- queue drain + render ---------------------------------------------------
    def _drain(self):
        latest = None
        try:
            while True:
                latest = self.queue.get_nowait()
        except queue.Empty:
            pass
        if latest is not None and self._dash_frame is not None:
            self._connecting = False
            self._render(latest)
        self.root.after(200, self._drain)

    def _tick_status(self):
        # let a transient flash decay back to the live status text
        if self._status_reset_at and time.monotonic() >= self._status_reset_at:
            self._status_reset_at = 0.0
            self.status_text.config(fg=DIM)
        self.root.after(500, self._tick_status)

    def _render(self, snap: Snapshot):
        tk = self.tk
        if snap.error:
            first = snap.error.splitlines()[0] if snap.error else "error"
            self._set_status("✕", RED, f"{first}\nCheck the MCP path in Settings, or click Reconnect.")
            return

        ping = f"{snap.ping_ms:.0f} ms" if snap.ping_ms is not None else "—"
        if not self._status_reset_at:
            self._set_status("●", GREEN, f"connected · ping {ping} · updated {time.strftime('%H:%M:%S')}")

        self.lbl_network.config(text=snap.network,
                                fg=GREEN if snap.network == "mainnet" else YELLOW)
        self.lbl_keysrc.config(text=snap.key_source)
        if snap.key_source == "keystore":
            self.lbl_unlock.master.pack(side="left", padx=(0, 26))
            self.lbl_unlock.config(text=snap.unlock_mode)
        else:
            self.lbl_unlock.master.pack_forget()

        for v in VENUES:
            row = self.venue_rows[v]
            loaded = bool(snap.venues.get(v, {}).get("signerLoaded"))
            row["signer"].config(text="● ready" if loaded else "○ none",
                                 fg=GREEN if loaded else GREY)
            full = snap.addresses.get(v)
            row["full"] = full
            row["addr"].config(text=_short(full), fg=DIM if full else GREY)

        self._render_treasury(snap)

    def _render_treasury(self, snap: Snapshot):
        tk = self.tk
        for child in self.tre_body.winfo_children():
            child.destroy()
        by = (snap.treasury or {}).get("byChain") or {}
        if not by:
            tk.Label(self.tre_body, text="none set — click “Set withdraw destination…” to pin one",
                     font=SANS, fg=GREY, bg=PANEL, anchor="w").pack(fill="x")
            return
        for chain, info in by.items():
            r = tk.Frame(self.tre_body, bg=PANEL)
            r.pack(fill="x", pady=2)
            tk.Label(r, text=chain, font=SANS, fg=TEXT, bg=PANEL, width=12, anchor="w").pack(side="left")
            src = info.get("source", "?")
            color = {"keystore": GREEN, "dashboard": ACCENT, "conflict": RED}.get(src, GREY)
            tk.Label(r, text=("CONFLICT" if src == "conflict" else src),
                     font=SANS, fg=color, bg=PANEL, width=10, anchor="w").pack(side="left")
            tk.Label(r, text=_short(info.get("address")), font=MONO, fg=DIM, bg=PANEL, anchor="w").pack(side="left")
            tk.Label(r, text=info.get("commitment") or "—", font=MONO, fg=GREY, bg=PANEL).pack(side="right")

    # -- actions ----------------------------------------------------------------
    def _copy_address(self, chain: str):
        full = self.venue_rows.get(chain, {}).get("full")
        if not full:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(full)
        self._flash(f"copied {chain} address to clipboard", 2.0)

    def _browse_mcp(self):
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            title="Select your built starling-mcp.js (or its launcher)",
            filetypes=[("MCP entry point", "*.js"), ("All files", "*.*")],
        )
        if path:
            self.setup_entry.delete(0, "end")
            # Store as a clean argv via the entry; _save_setup parses it. Quote for display.
            self.setup_entry.insert(0, f'node "{path}"' if " " in path else f"node {path}")

    def _save_setup(self):
        from tkinter import messagebox

        text = self.setup_entry.get().strip()
        args = cfg.parse_command(text)
        if not args:
            messagebox.showwarning("Starling", "Please enter a command to launch your MCP.")
            return
        cfg.remember_mcp_args(args)
        self._show_dashboard()
        self._start_worker(args)

    def _open_settings(self):
        SettingsDialog(self)

    def _open_set_treasury(self):
        TreasuryDialog(self)

    def _on_close(self):
        self._stop_worker()
        try:
            self.root.destroy()
        except Exception:
            pass


def _short_cmd(args: list[str]) -> str:
    last = args[-1] if args else ""
    base = os.path.basename(last) or last
    return base if base else " ".join(args)


# ── dialogs ───────────────────────────────────────────────────────────────────
class SettingsDialog:
    def __init__(self, app: Dashboard):
        tk = app.tk
        self.app = app
        win = tk.Toplevel(app.root, bg=BG)
        self.win = win
        win.title("Settings")
        win.configure(bg=BG)
        win.transient(app.root)
        win.resizable(False, False)

        cur = cfg.load_config()
        cur_args = cur.get("mcpArgs") or []
        shown = " ".join(f'"{a}"' if " " in a else a for a in cur_args)

        tk.Label(win, text="MCP launch command", font=SANS, fg=DIM, bg=BG).pack(anchor="w", padx=16, pady=(16, 4))
        row = tk.Frame(win, bg=BG)
        row.pack(fill="x", padx=16)
        self.entry = tk.Entry(row, font=MONO, bg=PANEL, fg=TEXT, insertbackground=TEXT, width=52,
                              relief="flat", highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT)
        self.entry.insert(0, shown or "node /path/to/Starling-MCP/dist/bin/starling-mcp.js")
        self.entry.pack(side="left", fill="x", expand=True, ipady=5)
        app._button(row, "Browse…", self._browse, primary=False).pack(side="left", padx=(8, 0))

        tk.Label(win, text="Refresh interval (seconds)", font=SANS, fg=DIM, bg=BG).pack(anchor="w", padx=16, pady=(14, 4))
        self.interval = tk.Spinbox(win, from_=1, to=60, increment=1, width=6, font=MONO, bg=PANEL, fg=TEXT,
                                   relief="flat", highlightthickness=1, highlightbackground=BORDER, insertbackground=TEXT,
                                   buttonbackground=PANEL)
        self.interval.delete(0, "end")
        self.interval.insert(0, str(int(cfg.get_interval())))
        self.interval.pack(anchor="w", padx=16)

        bar = tk.Frame(win, bg=BG)
        bar.pack(fill="x", padx=16, pady=16)
        app._button(bar, "Save", self._save).pack(side="right")
        app._button(bar, "Cancel", win.destroy, primary=False).pack(side="right", padx=(0, 8))
        win.grab_set()

    def _browse(self):
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            title="Select your built starling-mcp.js (or its launcher)",
            filetypes=[("MCP entry point", "*.js"), ("All files", "*.*")],
        )
        if path:
            self.entry.delete(0, "end")
            self.entry.insert(0, f'node "{path}"' if " " in path else f"node {path}")

    def _save(self):
        from tkinter import messagebox

        args = cfg.parse_command(self.entry.get())
        if not args:
            messagebox.showwarning("Starling", "Please enter a command to launch your MCP.")
            return
        try:
            secs = max(1.0, float(self.interval.get()))
        except ValueError:
            secs = cfg.DEFAULT_INTERVAL
        cfg.remember_mcp_args(args)
        cfg.set_interval(secs)
        self.win.destroy()
        self.app._reconnect()


class TreasuryDialog:
    """Paste-and-confirm the withdraw destination — the same transcription-integrity
    flow as the CLI's `set-treasury`, but in a window. Writes ~/.starling/treasury.json
    (a public address), never key material, never a transaction."""

    def __init__(self, app: Dashboard):
        tk = app.tk
        self.app = app
        win = tk.Toplevel(app.root, bg=BG)
        self.win = win
        win.title("Set withdraw destination")
        win.configure(bg=BG)
        win.transient(app.root)
        win.resizable(False, False)

        tk.Label(win, text="Set withdraw destination", font=SANS_B, fg=ACCENT, bg=BG).pack(
            anchor="w", padx=16, pady=(16, 2)
        )
        tk.Label(
            win,
            text=("Paste the wallet your funds sweep/withdraw to. Saved to a local file the MCP\n"
                  "reads — the agent never types it. Verify the commitment against your wallet."),
            font=SANS, fg=DIM, bg=BG, justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 12))

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
        self.save_btn = app._button(bar, "Pin destination", self._save)
        self.save_btn.pack(side="right")
        app._button(bar, "Cancel", win.destroy, primary=False).pack(side="right", padx=(0, 8))
        self._recompute()
        win.grab_set()
        self.entry.focus_set()

    def _recompute(self):
        chain = self.chain.get()
        norm = tre.normalize(chain, self.entry.get())
        if norm:
            self.note.config(text=f"commitment  {tre.commitment(chain, norm)}\n"
                                  f"verify against your wallet / recovery sheet — not against chat", fg=GREEN)
        elif self.entry.get().strip():
            self.note.config(text=f"not a valid {chain} address yet", fg=RED)
        else:
            self.note.config(text="", fg=DIM)

    def _save(self):
        from tkinter import messagebox

        chain = self.chain.get()
        norm = tre.normalize(chain, self.entry.get())
        if not norm:
            messagebox.showwarning("Starling", f"That isn't a valid {chain} address.")
            return
        if not messagebox.askyesno(
            "Confirm withdraw destination",
            f"Pin this as the {chain} withdraw destination?\n\n{norm}\n\n"
            f"commitment {tre.commitment(chain, norm)}\n\n"
            "Verify the commitment against your wallet — not against anything an agent printed.",
        ):
            return
        current = (tre.read_treasury() or {}).get("byChain") or {}
        merged = dict(current)
        merged[chain] = norm
        path = tre.write_treasury(merged)
        self.win.destroy()
        self.app._flash(f"pinned {chain} → {_short(norm)}  ({path})", 5.0)


# ── entry point ────────────────────────────────────────────────────────────────
def main() -> None:
    try:
        import tkinter as tk
    except Exception:
        msg = (
            "The desktop window needs Tkinter, which isn't available in this Python.\n\n"
            "  • macOS (Homebrew):  brew install python-tk\n"
            "  • or install Python from https://www.python.org (bundles Tk)\n\n"
            "You can still use the terminal dashboard: `starling-dashboard --mcp ...`."
        )
        print(msg, file=sys.stderr)
        _log("tkinter unavailable:\n" + traceback.format_exc())
        sys.exit(1)

    key = os.environ.get("STARLING_KEY")
    try:
        root = tk.Tk()
    except Exception as exc:
        print(f"Couldn't open a window: {exc}", file=sys.stderr)
        _log("Tk() failed:\n" + traceback.format_exc())
        sys.exit(1)

    try:
        Dashboard(root, key)
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
