"""Tests for the web dashboard server — focused on the security-critical token
gate and the read API. Stdlib only (http.client + unittest); starts the real
handler on an ephemeral local port against a scratch STARLING_DIR."""
from __future__ import annotations

import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer


class WebApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Point at a throwaway dir so we never read the real ~/.starling.
        cls._tmp = tempfile.mkdtemp(prefix="starling-web-test-")
        os.environ["STARLING_DIR"] = cls._tmp
        # Import AFTER STARLING_DIR is set.
        from starling_dashboard import web
        cls.web = web
        cls.token = web.TOKEN
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _req(self, method, path, token=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Starling-Token"] = token
        conn.request(method, path, body=json.dumps(body) if body else None, headers=headers)
        r = conn.getresponse()
        data = r.read().decode("utf-8")
        conn.close()
        return r.status, data

    def test_index_serves_and_injects_token(self):
        status, body = self._req("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(self.token, body)
        self.assertNotIn("__STARLING_TOKEN__", body)

    def test_api_requires_token(self):
        status, _ = self._req("GET", "/api/state")  # no token
        self.assertEqual(status, 403)

    def test_api_state_with_token(self):
        status, body = self._req("GET", "/api/state", token=self.token)
        self.assertEqual(status, 200)
        obj = json.loads(body)
        for key in ("present", "live", "halted", "status", "treasury"):
            self.assertIn(key, obj)

    def test_validate_good_and_bad_address(self):
        good = "6mzinuCDcQy5wivni1qDSCH9DpmeY7PamhVs7kPK9NYu"  # 32-byte base58
        status, body = self._req("GET", f"/api/validate?chain=solana&address={good}", token=self.token)
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["valid"])

        status, body = self._req("GET", "/api/validate?chain=solana&address=nope", token=self.token)
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["valid"])

    def test_post_requires_token(self):
        status, _ = self._req("POST", "/api/halt", body={"reason": "test"})  # no token
        self.assertEqual(status, 403)

    def test_unknown_api_endpoint_404s(self):
        status, _ = self._req("GET", "/api/nope", token=self.token)
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
