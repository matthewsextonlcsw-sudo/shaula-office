"""test_cockpit_authoring — the cockpit's server-side bridge to shaula-svc.

The cockpit holds the x-internal-secret and calls the svc on the browser's
behalf (the browser never reaches the svc — svc/app.py). These tests pin that
seam WITHOUT a network: ``svc_client._post`` is stubbed to return canned
(status, body) tuples, so we prove three things deterministically —

  1. request shaping  — the right svc path + payload (truncation, flags),
  2. success passthrough — a 200 body rides back to the browser verbatim,
  3. honest error mapping — every svc failure becomes a plain-language result
     with the raw error code (and violations) preserved for the surface.

Pure stdlib; runs under the repo's default py3.14 pytest path (no fastapi).
NO PHI — the only data on this seam is a business description + vetted template.
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


class _StubPost:
    """Replaces svc_client._post: records the call, returns a canned (status, body)."""

    def __init__(self, status: int, body: dict) -> None:
        self.status, self.body = status, body
        self.calls: list[tuple[str, dict, float]] = []

    def __call__(self, path: str, payload: dict, *, timeout: float = 60.0):
        self.calls.append((path, payload, timeout))
        return self.status, self.body


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_post = svc_client._post
        self._saved_env = {
            k: os.environ.get(k)
            for k in ("SHAULA_SVC_URL", "SHAULA_INTERNAL_SECRET",
                      "SHAULA_PRACTICE_ID", "SHAULA_TIER")
        }
        os.environ["SHAULA_SVC_URL"] = "http://svc.local"
        os.environ["SHAULA_PRACTICE_ID"] = "cockpit-demo"
        os.environ.pop("SHAULA_TIER", None)

    def tearDown(self) -> None:
        svc_client._post = self._saved_post
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _stub(self, status: int, body: dict) -> _StubPost:
        stub = _StubPost(status, body)
        svc_client._post = stub
        return stub


class TestConfigured(_Base):
    def test_configured_true_with_url(self):
        self.assertTrue(svc_client.configured())

    def test_configured_false_without_url(self):
        os.environ["SHAULA_SVC_URL"] = ""
        self.assertFalse(svc_client.configured())

    def test_pid_default_and_override(self):
        os.environ.pop("SHAULA_PRACTICE_ID", None)
        self.assertEqual(svc_client._pid(), "cockpit-demo")
        os.environ["SHAULA_PRACTICE_ID"] = "north-star"
        self.assertEqual(svc_client._pid(), "north-star")


class TestDraft(_Base):
    def test_empty_description_short_circuits(self):
        stub = self._stub(200, {"ok": True})
        out = svc_client.draft("   ")
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "empty")
        self.assertEqual(stub.calls, [])  # never touches the svc

    def test_success_passes_body_through(self):
        body = {"ok": True, "name": "ref-outreach", "steps": [{"ref": "draft"}],
                "template": {"name": "ref-outreach", "steps": []}}
        stub = self._stub(200, body)
        out = svc_client.draft("monthly referral outreach", with_skill=True)
        self.assertEqual(out, body)
        # right path + payload shape (description trimmed, withSkill forwarded)
        path, payload, _ = stub.calls[0]
        self.assertEqual(path, "/v1/practices/cockpit-demo/workflows/draft")
        self.assertEqual(payload["description"], "monthly referral outreach")
        self.assertTrue(payload["withSkill"])

    def test_description_truncated_to_2000(self):
        stub = self._stub(200, {"ok": True})
        svc_client.draft("x" * 5000)
        self.assertEqual(len(stub.calls[0][1]["description"]), 2000)

    def test_404_maps_to_authoring_disabled(self):
        self._stub(404, {"detail": "authoring_disabled"})
        out = svc_client.draft("anything")
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "authoring_disabled")
        self.assertIn("switched on", out["message"])

    def test_401_maps_to_unauthorized(self):
        self._stub(401, {"error": "unauthorized"})
        out = svc_client.draft("anything")
        self.assertEqual(out["error"], "unauthorized")
        self.assertIn("SHAULA_INTERNAL_SECRET", out["message"])

    def test_422_carries_violations(self):
        self._stub(422, {"detail": {"error": "could_not_author",
                                    "violations": ["fabricated a statistic"]}})
        out = svc_client.draft("promise 100% cure rates")
        self.assertEqual(out["error"], "could_not_author")
        self.assertEqual(out["violations"], ["fabricated a statistic"])

    def test_transport_failure_maps_to_unreachable(self):
        self._stub(0, {})
        out = svc_client.draft("anything")
        self.assertEqual(out["error"], "unreachable")
        self.assertIn("running", out["message"])

    def test_unexpected_status_maps_generic(self):
        self._stub(500, {})
        out = svc_client.draft("anything")
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "http_500")


class TestCreate(_Base):
    def _tmpl(self) -> dict:
        return {"name": "ref-outreach",
                "steps": [{"ref": "draft", "title": "Draft", "assignee": "blog"}]}

    def test_empty_template_short_circuits(self):
        stub = self._stub(200, {"ok": True})
        out = svc_client.create({})
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "empty")
        self.assertEqual(stub.calls, [])

    def test_template_without_steps_short_circuits(self):
        stub = self._stub(200, {"ok": True})
        out = svc_client.create({"name": "x", "steps": []})
        self.assertEqual(out["error"], "empty")
        self.assertEqual(stub.calls, [])

    def test_success_passes_body_through(self):
        body = {"ok": True, "runId": "run-1", "status": "queued"}
        stub = self._stub(200, body)
        out = svc_client.create(self._tmpl(), idempotency_key="abc")
        self.assertEqual(out, body)
        path, payload, _ = stub.calls[0]
        self.assertEqual(path, "/v1/practices/cockpit-demo/workflows/create")
        self.assertEqual(payload["template"], self._tmpl())
        self.assertEqual(payload["tier"], "solo")            # default
        self.assertEqual(payload["idempotencyKey"], "abc")

    def test_tier_from_env(self):
        os.environ["SHAULA_TIER"] = "group"
        stub = self._stub(200, {"ok": True, "runId": "r", "status": "queued"})
        svc_client.create(self._tmpl())
        self.assertEqual(stub.calls[0][1]["tier"], "group")

    def test_idempotency_key_truncated_to_80(self):
        stub = self._stub(200, {"ok": True, "runId": "r", "status": "queued"})
        svc_client.create(self._tmpl(), idempotency_key="k" * 200)
        self.assertEqual(len(stub.calls[0][1]["idempotencyKey"]), 80)

    def test_422_maps_with_violations(self):
        self._stub(422, {"detail": {"error": "invalid_workflow",
                                    "violations": ["non-vetted assignee: hacker"]}})
        out = svc_client.create(self._tmpl())
        self.assertEqual(out["error"], "invalid_workflow")
        self.assertEqual(out["violations"], ["non-vetted assignee: hacker"])

    def test_404_maps_to_authoring_disabled(self):
        self._stub(404, {"detail": "authoring_disabled"})
        out = svc_client.create(self._tmpl())
        self.assertEqual(out["error"], "authoring_disabled")


class TestDetailParsing(unittest.TestCase):
    """_detail unwraps FastAPI's {"detail": ...} for both string and dict shapes."""

    def test_string_detail_becomes_error(self):
        self.assertEqual(svc_client._detail({"detail": "authoring_disabled"}),
                         {"error": "authoring_disabled"})

    def test_dict_detail_passes_through(self):
        d = {"error": "could_not_author", "violations": ["x"]}
        self.assertEqual(svc_client._detail({"detail": d}), d)

    def test_no_detail_returns_body(self):
        self.assertEqual(svc_client._detail({"error": "raw"}), {"error": "raw"})


if __name__ == "__main__":
    unittest.main()
