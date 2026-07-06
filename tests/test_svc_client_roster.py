"""test_svc_client_roster — the cockpit's read bridges to shaula-svc.

The staff roster and the two read surfaces (Office Manager inbox, Analyst counts)
are driven straight from the svc so the cockpit can NEVER drift from the manifest.
These tests pin that seam WITHOUT a network: ``svc_client._get`` is stubbed to
return canned (status, body) tuples, proving deterministically —

  1. request shaping     — the right svc path (roster is unscoped; stats/inquiries
     are practice-scoped),
  2. success passthrough  — a 200 body rides back to the browser verbatim,
  3. honest degradation   — every failure (and a not-wired svc) yields a SAFE
     empty shape (staff=[] / inquiries=[]) with a plain-language message, so the
     surface shows a banner, never a dead roster or a crash.

Pure stdlib; runs under the repo's default py3.14 pytest path (no fastapi).
NO PHI — only staff names, capability labels, and synthetic marketing counts.
"""
from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_COCKPIT = os.path.join(_ROOT, "cockpit")
if _COCKPIT not in sys.path:
    sys.path.insert(0, _COCKPIT)

import svc_client  # noqa: E402


class _StubGet:
    """Replaces svc_client._get: records the call, returns a canned (status, body)."""

    def __init__(self, status: int, body: dict) -> None:
        self.status, self.body = status, body
        self.calls: list[tuple[str, float]] = []

    def __call__(self, path: str, *, timeout: float = 15.0):
        self.calls.append((path, timeout))
        return self.status, self.body


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_get = svc_client._get
        self._saved_env = {
            k: os.environ.get(k)
            for k in ("SHAULA_SVC_URL", "SHAULA_INTERNAL_SECRET", "SHAULA_PRACTICE_ID")
        }
        os.environ["SHAULA_SVC_URL"] = "http://svc.local"
        os.environ["SHAULA_PRACTICE_ID"] = "cockpit-demo"

    def tearDown(self) -> None:
        svc_client._get = self._saved_get
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _stub(self, status: int, body: dict) -> _StubGet:
        stub = _StubGet(status, body)
        svc_client._get = stub
        return stub


class TestRoster(_Base):
    def test_success_passes_body_through(self):
        body = {"staff": [
            {"name": "website", "title": "Website Builder", "tagline": "…",
             "capabilities": [{"id": "website-launch", "label": "Practice Website",
                               "description": "…"}]},
            {"name": "analytics", "title": "Analyst", "tagline": "…",
             "surface": {"kind": "stats", "title": "Office report", "description": "…"},
             "capabilities": []},
        ]}
        stub = self._stub(200, body)
        out = svc_client.roster()
        self.assertEqual(out, body)
        self.assertEqual(stub.calls[0][0], "/v1/roster")  # unscoped — not per-practice

    def test_unreachable_degrades_to_empty_roster(self):
        self._stub(0, {})
        out = svc_client.roster()
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "unreachable")
        self.assertEqual(out["staff"], [])            # safe shape — UI shows a banner
        self.assertIn("running", out["message"])

    def test_not_wired_short_circuits_without_call(self):
        os.environ["SHAULA_SVC_URL"] = ""
        stub = self._stub(200, {"staff": [{"name": "x"}]})
        out = svc_client.roster()
        self.assertFalse(out["ok"])
        self.assertEqual(out["staff"], [])
        self.assertIn("SHAULA_SVC_URL", out["message"])
        self.assertEqual(stub.calls, [])              # never touches the svc

    def test_http_error_still_safe_empty(self):
        self._stub(500, {})
        out = svc_client.roster()
        self.assertFalse(out["ok"])
        self.assertEqual(out["staff"], [])            # always a list, even on 5xx


class TestStats(_Base):
    def test_success_passes_body_through(self):
        body = {"practiceId": "cockpit-demo", "runs": {"total": 3},
                "postsPublished": 1, "inquiries": {"total": 2, "new": 1},
                "siteLive": True}
        stub = self._stub(200, body)
        out = svc_client.stats()
        self.assertTrue(out["ok"])
        self.assertEqual(out["runs"], {"total": 3})
        self.assertEqual(stub.calls[0][0], "/v1/practices/cockpit-demo/stats")

    def test_unreachable_is_honest(self):
        self._stub(0, {})
        out = svc_client.stats()
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "unreachable")

    def test_not_wired_short_circuits_without_call(self):
        os.environ["SHAULA_SVC_URL"] = ""
        stub = self._stub(200, {"runs": {"total": 9}})
        out = svc_client.stats()
        self.assertFalse(out["ok"])
        self.assertEqual(stub.calls, [])


class TestInquiries(_Base):
    def test_success_passes_body_through(self):
        body = {"inquiries": [{"id": "i1", "name": "Pat", "read": False}], "new": 1}
        stub = self._stub(200, body)
        out = svc_client.inquiries()
        self.assertEqual(out["inquiries"], body["inquiries"])
        self.assertEqual(out["new"], 1)
        self.assertEqual(stub.calls[0][0], "/v1/practices/cockpit-demo/inquiries")

    def test_unreachable_degrades_to_empty_inbox(self):
        self._stub(0, {})
        out = svc_client.inquiries()
        self.assertFalse(out["ok"])
        self.assertEqual(out["inquiries"], [])
        self.assertEqual(out["new"], 0)

    def test_not_wired_short_circuits_without_call(self):
        os.environ["SHAULA_SVC_URL"] = ""
        stub = self._stub(200, {"inquiries": [{"id": "x"}], "new": 1})
        out = svc_client.inquiries()
        self.assertFalse(out["ok"])
        self.assertEqual(out["inquiries"], [])
        self.assertEqual(out["new"], 0)
        self.assertEqual(stub.calls, [])


if __name__ == "__main__":
    unittest.main()
