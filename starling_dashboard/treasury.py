"""Pin the human's withdraw destination to a local text file the MCP reads.

This is the ONLY thing the dashboard writes. The point is UX + transcription
integrity: the user pastes a 40/44-char address ONCE, here, and those exact bytes
land in ``~/.starling/treasury.json`` — the trading agent never re-types the
string into a config (where it could drop/flip a character and strand a sweep).

It is NOT a security control: a code-exec'd agent can rewrite this file, same as
it could sign a raw transfer. The 4-byte ``commitment`` is a transcription check
the human eyeballs against their wallet/recovery sheet, not a cryptographic one.

Everything here is stdlib-only (no ``mcp``/``rich`` import) so it stays trivially
testable and importable.

Kept consistent with the MCP side:
  - path:        Starling-MCP ``src/keystore/store.ts`` ``starlingDir()``
  - normalize:   Starling-MCP ``src/withdraw/pinned-file.ts`` ``normalizePinnedAddress``
  - commitment:  Starling-MCP ``src/keystore/treasury-seal.ts`` ``treasuryCommitment``
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CHAINS = ("polygon", "hyperliquid", "solana")

_EVM_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]+$")  # Bitcoin alphabet — no 0 O I l
_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def starling_dir() -> Path:
    """Mirror the MCP's ``starlingDir()`` EXACTLY so both processes agree on the
    file. node ``path.resolve`` = absolute + normalize against cwd (NOT symlink
    resolution), which is ``os.path.abspath`` — not ``realpath``."""
    d = os.environ.get("STARLING_DIR")
    if d:
        return Path(os.path.abspath(d))
    return Path.home() / ".starling"


def treasury_path() -> Path:
    return starling_dir() / "treasury.json"


def _base58_byte_len(s: str) -> int:
    """Decoded byte length of a base58 string (validation only). -1 if invalid."""
    num = 0
    for ch in s:
        i = _BASE58_ALPHABET.find(ch)
        if i < 0:
            return -1
        num = num * 58 + i
    nbytes = (num.bit_length() + 7) // 8
    zeros = 0
    for ch in s:
        if ch == "1":
            zeros += 1
        else:
            break
    return zeros + nbytes


def normalize(chain: str, raw: object) -> str | None:
    """Validate + normalize one chain's address the way the MCP reader does.

    EVM = ``0x`` + 40 hex, lowercased; Solana = base58 decoding to 32 bytes, kept
    as-is (base58 is case-significant). Returns the normalized address or None.
    """
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    if chain == "solana":
        return s if (_BASE58_RE.match(s) and _base58_byte_len(s) == 32) else None
    return s.lower() if _EVM_RE.match(s) else None


def commitment(chain: str, addr: str) -> str:
    """4-byte (8 hex) transcription commitment, byte-identical to the MCP's
    ``treasuryCommitment`` (sha256 of ``"<chain>:<normalized>"``, EVM lowercased)."""
    norm = addr if chain == "solana" else addr.lower()
    return hashlib.sha256(f"{chain}:{norm}".encode("utf-8")).hexdigest()[:8]


def _harden_windows(path: Path, is_dir: bool) -> None:
    """Best-effort: lock a path to the current user via icacls (POSIX chmod is a
    no-op on NTFS). Mirrors Starling-MCP's keystore/store.ts so the dashboard
    never creates a weaker-permissioned ~/.starling than the MCP would. Referenced
    by SID so a `DOMAIN\\user` mapping can't lock the owner out. Never raises."""
    if sys.platform != "win32":
        return
    try:
        out = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, check=False
        ).stdout
        m = re.search(r"S-1-[0-9-]+", out)
        if not m:
            return  # never risk locking the owner out
        grant = f"*{m.group(0)}:(OI)(CI)F" if is_dir else f"*{m.group(0)}:(F)"
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", grant],
            capture_output=True, check=False,
        )
    except OSError:
        pass


def read_treasury() -> dict | None:
    """Read the current pinned file, or None if absent/unparsable."""
    try:
        return json.loads(treasury_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_treasury(by_chain: dict[str, str]) -> Path:
    """Atomically write the pinned destinations at 0600 (mirrors the MCP's
    keystore O_EXCL+rename). ``by_chain`` values must already be normalized."""
    d = starling_dir()
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)  # POSIX; no-op on Windows NTFS
    except OSError:
        pass
    _harden_windows(d, is_dir=True)  # Windows: real ACL lockdown (chmod can't)

    payload = {
        "version": 1,
        "byChain": by_chain,
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "commitment": {c: commitment(c, a) for c, a in by_chain.items()},
    }
    body = json.dumps(payload, indent=2)

    dest = treasury_path()
    tmp = d / f".treasury.{os.getpid()}.tmp"
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        pass
    # O_EXCL create at 0600 so the file never exists at the umask-default mode.
    fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    os.replace(tmp, dest)  # atomic on the same filesystem
    try:
        os.chmod(dest, 0o600)
    except OSError:
        pass
    _harden_windows(dest, is_dir=False)
    return dest
