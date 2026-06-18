"""Tests for the dashboard's withdraw-destination writer.

The commitment vectors here are GOLDEN and must stay byte-identical to the MCP
side (Starling-MCP/src/withdraw/pinned-file.test.ts + treasury-seal.ts). If
normalization ever drifts on either side, both suites fail together.

Run:  python -m unittest discover -s tests -t .
(stdlib only — needs neither `mcp` nor `rich`, so it runs without the venv.)
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

from starling_dashboard import treasury as t

EVM = "0x1111111111111111111111111111111111111111"
SOL = "11111111111111111111111111111111"  # 32 base58 '1's = 32 zero bytes (System Program)


class TestValidation(unittest.TestCase):
    def test_evm_validated_and_lowercased(self):
        self.assertEqual(
            t.normalize("polygon", "0xABCDEF0000000000000000000000000000000001"),
            "0xabcdef0000000000000000000000000000000001",
        )
        self.assertEqual(t.normalize("polygon", f"  {EVM}  "), EVM)  # trimmed
        self.assertIsNone(t.normalize("polygon", "0x123"))  # too short
        self.assertIsNone(t.normalize("polygon", EVM[2:]))  # missing 0x
        self.assertIsNone(t.normalize("polygon", ""))
        self.assertIsNone(t.normalize("polygon", 123))  # non-string

    def test_solana_base58_32_bytes(self):
        self.assertEqual(t.normalize("solana", SOL), SOL)
        self.assertIsNone(t.normalize("solana", "0OIl-not-base58"))
        self.assertIsNone(t.normalize("solana", "abc"))  # decodes to < 32 bytes


class TestCommitment(unittest.TestCase):
    def test_golden_vectors(self):
        # MUST equal the MCP's treasuryCommitment (pinned-file.test.ts).
        self.assertEqual(t.commitment("polygon", EVM), "aae22ddc")
        self.assertEqual(t.commitment("polygon", "0xAbC0000000000000000000000000000000000001"), "6b2290f4")
        self.assertEqual(t.commitment("solana", SOL), "538f69a0")

    def test_evm_commitment_is_case_insensitive(self):
        self.assertEqual(
            t.commitment("polygon", "0xABCDEF0000000000000000000000000000000001"),
            t.commitment("polygon", "0xabcdef0000000000000000000000000000000001"),
        )


class TestWrite(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix="starling-treasury-")
        self._prev = os.environ.get("STARLING_DIR")
        os.environ["STARLING_DIR"] = self._dir

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("STARLING_DIR", None)
        else:
            os.environ["STARLING_DIR"] = self._prev
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_write_roundtrip_and_commitments(self):
        path = t.write_treasury({"polygon": EVM, "solana": SOL})
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["byChain"]["polygon"], EVM)
        self.assertEqual(data["commitment"]["polygon"], "aae22ddc")
        self.assertEqual(data["commitment"]["solana"], "538f69a0")
        self.assertIn("updatedAt", data)

    def test_write_is_0600_on_posix(self):
        path = t.write_treasury({"polygon": EVM})
        if os.name != "nt":
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_overwrite_replaces_atomically(self):
        t.write_treasury({"polygon": EVM})
        path = t.write_treasury({"solana": SOL})  # second write must succeed (no O_EXCL clobber)
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["byChain"], {"solana": SOL})


if __name__ == "__main__":
    unittest.main()
