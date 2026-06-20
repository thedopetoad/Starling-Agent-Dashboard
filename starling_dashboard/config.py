"""Dashboard config: where the local Starling MCP lives, plus the refresh rate.

The GUI is meant to be *zero-config after first run*. On launch we:

  1. read ``~/.starling/dashboard.json`` (honoring ``STARLING_DIR``) — if it pins
     an MCP command, use it;
  2. else honor the ``STARLING_MCP_CMD`` env var (same one the CLI uses);
  3. else **auto-detect** a sibling ``Starling-MCP`` build and, if found, *remember*
     it by writing the config — so the next double-click is instant.

Everything here is stdlib-only (no ``mcp`` / ``rich`` / ``tkinter`` import) so it
stays trivially testable and importable. The MCP command is stored as a clean argv
list (``mcpArgs``), not a shell string, so a Windows path with spaces or backslashes
never has to survive shlex quoting.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
from pathlib import Path

from .treasury import starling_dir  # reuse the one true ~/.starling resolver

CONFIG_NAME = "dashboard.json"
DEFAULT_INTERVAL = 5.0

# Relative path, inside a cloned Starling-MCP repo, to its built entry point.
_MCP_BIN = ("dist", "bin", "starling-mcp.js")
_REPO_DIR = Path(__file__).resolve().parents[1]  # the Starling-Agent-Dashboard checkout


def config_path() -> Path:
    return starling_dir() / CONFIG_NAME


def load_config() -> dict:
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> Path:
    d = starling_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = config_path()
    payload = {"version": 1, **cfg}
    tmp = d / f".{CONFIG_NAME}.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)  # atomic on the same filesystem
    return path


def parse_command(text: str) -> list[str]:
    """Split a hand-typed MCP command into argv. POSIX rules off-Windows; on Windows
    we keep backslashes literal (``posix=False``) to match the CLI's behavior."""
    return shlex.split(text.strip(), posix=(os.name != "nt"))


def _mcp_bin_under(repo: Path) -> Path:
    return repo.joinpath(*_MCP_BIN)


def _candidate_mcp_dirs() -> list[Path]:
    """Places a cloned Starling-MCP commonly sits, most explicit first."""
    out: list[Path] = []
    # Explicit env hints (same names the MCP's own config wizard honors).
    env_dir = os.environ.get("STARLING_MCP_DIR")
    if env_dir:
        out.append(Path(env_dir))
    # A sibling of this dashboard checkout — the overwhelmingly common layout.
    out.append(_REPO_DIR.parent / "Starling-MCP")
    # A sibling of the current working directory.
    out.append(Path.cwd().parent / "Starling-MCP")
    # The desktop / home, in case the two repos aren't side by side.
    home = Path.home()
    out += [home / "Desktop" / "Starling-MCP", home / "Starling-MCP"]
    return out


def detect_mcp_args() -> list[str] | None:
    """Best-effort discovery of a runnable local MCP, as a clean ``["node", path]``
    argv. Returns None if nothing plausible is found (caller then prompts once)."""
    # 1) An explicit, ready-to-run command wins.
    env_cmd = os.environ.get("STARLING_MCP_CMD")
    if env_cmd:
        parts = parse_command(env_cmd)
        if parts:
            return parts
    # 2) An explicit path straight to the built bin.
    env_path = os.environ.get("STARLING_MCP_PATH")
    if env_path and Path(env_path).is_file():
        return [_node_exe(), env_path]
    # 3) A sibling Starling-MCP whose dist/ has been built.
    for d in _candidate_mcp_dirs():
        bin_path = _mcp_bin_under(d)
        if bin_path.is_file():
            return [_node_exe(), str(bin_path)]
    return None


def _node_exe() -> str:
    """The node executable to launch the MCP with — full path if we can resolve it
    (more robust under a GUI that may not inherit a login shell PATH), else 'node'."""
    return shutil.which("node") or "node"


def resolve_mcp_args() -> tuple[list[str] | None, str]:
    """Decide the MCP argv for this launch and how we got it.

    Returns ``(args, source)`` where source is one of ``config`` / ``detected`` /
    ``none``. On ``detected`` the result is *persisted* so the next launch is
    zero-config (the "auto-detect, then remember" behavior)."""
    cfg = load_config()
    saved = cfg.get("mcpArgs")
    if isinstance(saved, list) and saved:
        return [str(x) for x in saved], "config"

    found = detect_mcp_args()
    if found:
        remember_mcp_args(found)
        return found, "detected"
    return None, "none"


def remember_mcp_args(args: list[str]) -> Path:
    """Persist the MCP argv (and keep any other config keys intact)."""
    cfg = load_config()
    cfg["mcpArgs"] = list(args)
    return save_config(cfg)


def get_interval() -> float:
    cfg = load_config()
    try:
        val = float(cfg.get("interval", DEFAULT_INTERVAL))
        return val if val > 0 else DEFAULT_INTERVAL
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL


def set_interval(seconds: float) -> Path:
    cfg = load_config()
    cfg["interval"] = float(seconds)
    return save_config(cfg)
