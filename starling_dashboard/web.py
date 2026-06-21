"""Local web UI for a *running* Starling MCP — a modern replacement for the Tk
window, same engine underneath.

It serves a single-page app on ``127.0.0.1`` and exposes a tiny JSON API over the
SAME file control plane the Tk GUI used (``controlplane.py`` + ``treasury.py``):
reads ``status.json``, toggles the halt flag, queues close/withdraw commands, and
reads/writes the editable withdraw destinations. Stdlib only — no Flask/FastAPI.

Security (this server can halt trading and queue withdrawals, so it matters):
  • Binds to 127.0.0.1 ONLY — never a routable interface.
  • Every ``/api/*`` call must carry the per-session ``X-Starling-Token`` minted at
    startup and embedded in the served page. A web page on another origin can't
    read our HTML, so it can't learn the token — this blocks drive-by CSRF from
    other browser tabs hitting localhost. Requests without the token get 403.
  • It still never holds keys or signs: destructive actions only QUEUE intent for
    the MCP, which runs them behind its own guardrails (same as the Tk GUI).
"""

from __future__ import annotations

import json
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from . import __version__, controlplane as cp
from . import treasury as tre

_STATIC = Path(__file__).parent / "static"
TOKEN = secrets.token_urlsafe(18)


def _state() -> dict:
    """Everything the SPA needs to render one frame."""
    st = cp.read_status()
    treasury = (tre.read_treasury() or {}).get("byChain") or {}
    return {
        "present": st.present,
        "live": st.live,
        "age": st.age,
        "error": st.error,
        "halted": cp.is_halted(),
        "status": st.raw,
        "treasury": treasury,
        "version": __version__,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "StarlingDashboard"

    # quieter logs (one line per request is noisy for a 1s poller)
    def log_message(self, *_a):  # noqa: D401
        return

    # -- helpers ---------------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # Lock down: no caching of API, no embedding, no referrer leakage.
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def _authed(self) -> bool:
        return self.headers.get("X-Starling-Token") == TOKEN

    def _body(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return {}

    # -- routing ---------------------------------------------------------------
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            html = (_STATIC / "index.html").read_text(encoding="utf-8").replace("__STARLING_TOKEN__", TOKEN)
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path.startswith("/api/"):
            if not self._authed():
                self._json(403, {"error": "bad or missing token"})
                return
            self._api_get(path)
            return
        self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            self._send(404, b"not found", "text/plain")
            return
        if not self._authed():
            self._json(403, {"error": "bad or missing token"})
            return
        self._api_post(path, self._body())

    # -- API: reads ------------------------------------------------------------
    def _api_get(self, path: str) -> None:
        qs = parse_qs(urlparse(self.path).query)
        if path == "/api/state":
            self._json(200, _state())
        elif path == "/api/ack":
            cid = (qs.get("id") or [""])[0]
            ack = cp.read_ack(cid)
            self._json(200, ack or {"pending": True})
        elif path == "/api/validate":
            chain = (qs.get("chain") or [""])[0]
            addr = (qs.get("address") or [""])[0]
            norm = tre.normalize(chain, addr)
            self._json(200, {"valid": bool(norm), "normalized": norm,
                             "commitment": tre.commitment(chain, norm) if norm else None})
        else:
            self._json(404, {"error": "unknown endpoint"})

    # -- API: actions ----------------------------------------------------------
    def _api_post(self, path: str, body: dict) -> None:
        if path == "/api/halt":
            cp.set_halt(str(body.get("reason", "dashboard")))
            self._json(200, {"ok": True})
        elif path == "/api/resume":
            cp.clear_halt()
            self._json(200, {"ok": True})
        elif path == "/api/command":
            action = str(body.get("action", ""))
            args = body.get("args") or {}
            if action not in cp.ACTIONS:
                self._json(400, {"ok": False, "error": f"unknown action {action!r}"})
                return
            cid = cp.enqueue_command(action, args if isinstance(args, dict) else {})
            self._json(200, {"ok": True, "id": cid})
        elif path == "/api/treasury":
            chain = str(body.get("chain", ""))
            norm = tre.normalize(chain, body.get("address"))
            if not norm:
                self._json(400, {"ok": False, "error": f"not a valid {chain} address"})
                return
            merged = dict((tre.read_treasury() or {}).get("byChain") or {})
            merged[chain] = norm
            tre.write_treasury(merged)
            self._json(200, {"ok": True, "normalized": norm, "commitment": tre.commitment(chain, norm)})
        elif path == "/api/treasury/clear":
            chain = str(body.get("chain", ""))
            merged = dict((tre.read_treasury() or {}).get("byChain") or {})
            merged.pop(chain, None)
            tre.write_treasury(merged)
            self._json(200, {"ok": True})
        else:
            self._json(404, {"error": "unknown endpoint"})


def serve(host: str = "127.0.0.1", port: int = 8787, open_browser: bool = True) -> None:
    try:
        httpd = ThreadingHTTPServer((host, port), Handler)
    except OSError:
        httpd = ThreadingHTTPServer((host, 0), Handler)  # fall back to an ephemeral port
        port = httpd.server_address[1]
    url = f"http://{host}:{port}/"
    print(f"◆ Starling dashboard → {url}")
    print(f"  (local only; session token: {TOKEN[:6]}…)  Ctrl-C to stop.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping…")
        httpd.shutdown()


if __name__ == "__main__":
    serve(open_browser="--no-open" not in sys.argv)
