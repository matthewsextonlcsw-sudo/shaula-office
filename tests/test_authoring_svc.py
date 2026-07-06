"""test_authoring_svc — the svc authoring adapter, deterministic + CI-safe.

Stub model, no network. Proves the svc-side safety wall: a non-vetted assignee is
rejected at draft AND at create (the client is untrusted too), the run-step shape
matches what the existing runner executes, and the reviewer step is the gate.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from svc import authoring, config, gemini  # noqa: E402
from workflows.builder import build_plan, load_template  # noqa: E402

# The route-wiring tests below need the FastAPI app + TestClient. The CI honesty
# seam (scripts/prove.sh) runs this module in a venv that installs only
# google-genai + httpx — NOT fastapi — so the app import is optional and the route
# class self-skips there. It runs (and is proven) in any fastapi-equipped venv.
try:
    from fastapi.testclient import TestClient  # noqa: E402
    from svc import app as svc_app  # noqa: E402

    _HAS_APP = True
except Exception:  # noqa: BLE001 — fastapi/starlette absent in the CI seam venv
    _HAS_APP = False

_GOOD = {
    "name": "ref-outreach",
    "description": "Draft a monthly referral-partner note.",
    "steps": [
        {"ref": "draft", "title": "Draft the note", "assignee": "blog",
         "description": "Write a warm, honest note.", "dependencies": []},
        {"ref": "review", "title": "Honesty review", "assignee": "reviewer",
         "description": "Check against the honesty rules.",
         "dependencies": ["draft"], "requires_review": True},
    ],
}


def _bad_assignee() -> dict:
    bad = json.loads(json.dumps(_GOOD))
    bad["steps"][0]["assignee"] = "hacker"
    return bad


class Stub:
    def __init__(self, obj) -> None:
        self.obj = obj

    def __call__(self, system: str, user: str) -> str:
        return json.dumps(self.obj) if isinstance(self.obj, dict) else self.obj


class TestDraftPreview(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = authoring.MODEL

    def tearDown(self) -> None:
        authoring.MODEL = self._saved

    def test_clean_preview_is_vetted(self):
        authoring.MODEL = Stub(_GOOD)
        p = authoring.draft_preview("monthly referral outreach", "Cedar & Sage")
        self.assertEqual([s["ref"] for s in p["steps"]], ["draft", "review"])
        self.assertTrue(p["steps"][-1]["isReview"])
        self.assertIn("template", p)  # rides back for approve+resubmit

    def test_nonvetted_rejected(self):
        authoring.MODEL = Stub(_bad_assignee())
        with self.assertRaises(authoring.AuthoringError):
            authoring.draft_preview("escalate to my bot", "Cedar & Sage")


class _HonestyStub:
    """Mimics the PROD model path: the raw draft is honesty-linted inside
    gemini.generate_text, so a banned first sketch surfaces as BrainError('honesty')
    BEFORE the svc adapter ever parses it. Goes clean after ``clean_after`` trips so
    the repair path is testable (default: trips forever)."""

    def __init__(self, clean_after: int = 999) -> None:
        self.calls = 0
        self.clean_after = clean_after

    def __call__(self, system: str, user: str) -> str:
        self.calls += 1
        if self.calls > self.clean_after:
            return json.dumps(_GOOD)
        err = gemini.BrainError("honesty", r"\bproven\b")
        err.explanations = [
            {"pattern": r"\bproven\b",
             "plain": "the word 'proven' reads like an unbacked claim",
             "quote": "proven outreach"}
        ]
        raise err


class _OutageStub:
    """A real brain outage (not a content problem) — vertex_http 503."""

    def __call__(self, system: str, user: str) -> str:
        raise gemini.BrainError("vertex_http", "status 503")


class TestHonestyTripIsGraceful(unittest.TestCase):
    """The live canary bug: a banned first draft tripped the honesty gate inside
    generate_text → BrainError('honesty') escaped unhandled → HTTP 500. It must
    surface as AuthoringError (→ 422 at the route), and a real outage must NOT be
    masked as a content refusal."""

    def setUp(self) -> None:
        self._saved = authoring.MODEL

    def tearDown(self) -> None:
        authoring.MODEL = self._saved

    def test_honesty_trip_is_authoring_error_never_brainerror(self):
        authoring.MODEL = _HonestyStub()  # trips every attempt
        with self.assertRaises(authoring.AuthoringError) as cm:
            authoring.draft_preview("write a proven workflow", "Cedar & Sage")
        # NOT a BrainError (which would escape the route's except → 500)…
        self.assertNotIsInstance(cm.exception, gemini.BrainError)
        # …and the plain-language reason rides back for the 422 body / UI.
        self.assertTrue(cm.exception.violations)
        self.assertTrue(any("proven" in v for v in cm.exception.violations))

    def test_honesty_trip_is_repaired_then_succeeds(self):
        stub = _HonestyStub(clean_after=1)  # trips once, clean on retry
        authoring.MODEL = stub
        p = authoring.draft_preview("monthly referral outreach", "Cedar & Sage")
        self.assertEqual([s["ref"] for s in p["steps"]], ["draft", "review"])
        self.assertGreaterEqual(stub.calls, 2)  # proved the loop re-prompted

    def test_infra_outage_propagates_not_masked(self):
        # An outage is not "couldn't write honestly" — it must propagate as BrainError
        # so the svc reports an outage, not a 422 content refusal.
        authoring.MODEL = _OutageStub()
        with self.assertRaises(gemini.BrainError) as cm:
            authoring.draft_preview("anything", "Cedar & Sage")
        self.assertEqual(cm.exception.category, "vertex_http")


class TestToRunSteps(unittest.TestCase):
    def test_shape_matches_runner(self):
        plan = build_plan(load_template(_GOOD), {}, allow_phi=False)
        steps = authoring.to_run_steps(plan)
        self.assertEqual([s["index"] for s in steps], [0, 1])
        self.assertEqual([s["status"] for s in steps], ["pending", "pending"])
        self.assertIn("SHAULA HOUSE RULES", steps[0]["instruction"])  # preamble present
        self.assertTrue(steps[-1]["isReview"])  # reviewer = the honesty gate
        self.assertFalse(steps[0]["isReview"])


class TestPrepareRun(unittest.TestCase):
    def test_validates_and_shapes(self):
        r = authoring.prepare_run(_GOOD)
        self.assertEqual(r["name"], "ref-outreach")
        self.assertEqual(len(r["steps"]), 2)

    def test_rejects_nonvetted_client_template(self):
        # the client is untrusted: /create re-validates and refuses.
        with self.assertRaises(authoring.AuthoringError):
            authoring.prepare_run(_bad_assignee())


class TestIdempotency(unittest.TestCase):
    """workflows_create dedup — a retry storm must not queue a second Vertex chain."""

    def test_fingerprint_stable_and_distinct(self):
        self.assertEqual(
            authoring.template_fingerprint(_GOOD),
            authoring.template_fingerprint(json.loads(json.dumps(_GOOD))),
        )
        self.assertNotEqual(
            authoring.template_fingerprint(_GOOD),
            authoring.template_fingerprint(_bad_assignee()),
        )

    def test_explicit_key_replays(self):
        runs = [{"id": "run-1", "idempotencyKey": "abc", "capability": "authored", "status": "working"}]
        self.assertEqual(authoring.find_replay(runs, "abc", "fp-x")["id"], "run-1")

    def test_unknown_key_no_replay(self):
        runs = [{"id": "run-1", "idempotencyKey": "abc", "capability": "authored", "status": "working"}]
        self.assertIsNone(authoring.find_replay(runs, "zzz", "fp-x"))

    def test_double_click_same_template_replays(self):
        fp = authoring.template_fingerprint(_GOOD)
        runs = [{"id": "run-1", "capability": "authored", "templateFingerprint": fp,
                 "createdAt": 1000, "status": "queued"}]
        self.assertEqual(authoring.find_replay(runs, "", fp, now=1005)["id"], "run-1")

    def test_different_template_not_deduped(self):
        # correctness point: two DISTINCT authored workflows in the window must NOT
        # collapse (capability+topic are degenerate for authored runs).
        fp_a = authoring.template_fingerprint(_GOOD)
        runs = [{"id": "run-1", "capability": "authored", "templateFingerprint": fp_a,
                 "createdAt": 1000, "status": "queued"}]
        self.assertIsNone(authoring.find_replay(runs, "", "fp-different", now=1005))

    def test_double_click_outside_window(self):
        fp = authoring.template_fingerprint(_GOOD)
        runs = [{"id": "run-1", "capability": "authored", "templateFingerprint": fp,
                 "createdAt": 1000, "status": "queued"}]
        self.assertIsNone(authoring.find_replay(runs, "", fp, now=1011))  # >10s

    def test_terminal_status_not_replayed(self):
        fp = authoring.template_fingerprint(_GOOD)
        runs = [{"id": "run-1", "capability": "authored", "templateFingerprint": fp,
                 "createdAt": 1000, "status": "failed"}]
        self.assertIsNone(authoring.find_replay(runs, "", fp, now=1005))


class TestAuthoredCap(unittest.TestCase):
    """workflows_create cost gate — authored runs queue past the monthly cap
    instead of spawning unbounded Vertex chains (mirrors create_run)."""

    def test_under_cap_is_false(self):
        self.assertFalse(authoring.authored_over_cap({"usage": {}}, "solo", month="2026-06"))

    def test_at_cap_is_true(self):
        from svc import config
        cap = config.cap_for("solo")
        self.assertTrue(
            authoring.authored_over_cap({"usage": {"2026-06": cap}}, "solo", month="2026-06")
        )

    def test_unknown_tier_uses_default_cap(self):
        from svc import config
        self.assertTrue(
            authoring.authored_over_cap(
                {"usage": {"2026-06": config.DEFAULT_TASK_CAP}}, "mystery", month="2026-06"
            )
        )


class TestDraftReplay(unittest.TestCase):
    """workflows_draft coalesce — a retry/double-click must not spend a second (up
    to 3-call) Vertex draft chain. Mirrors TestIdempotency for the draft side, with
    the key correction that a draft fingerprints its INPUTS (the model output is
    non-deterministic), never the output template."""

    def test_fingerprint_stable_and_whitespace_normalized(self):
        self.assertEqual(
            authoring.draft_fingerprint("monthly referral outreach", False),
            authoring.draft_fingerprint("monthly referral outreach", False),
        )
        self.assertEqual(
            authoring.draft_fingerprint("  outreach  ", False),
            authoring.draft_fingerprint("outreach", False),
        )

    def test_fingerprint_changes_with_description(self):
        self.assertNotEqual(
            authoring.draft_fingerprint("referral outreach", False),
            authoring.draft_fingerprint("intake checklist", False),
        )

    def test_fingerprint_changes_with_with_skill(self):
        # withSkill drives an extra Vertex call, so it must be part of the identity.
        self.assertNotEqual(
            authoring.draft_fingerprint("referral outreach", False),
            authoring.draft_fingerprint("referral outreach", True),
        )

    def test_explicit_key_replays_cached_preview(self):
        drafts = [{"idempotencyKey": "abc", "fingerprint": "fp-x",
                   "createdAt": 1000, "preview": {"name": "ref-outreach"}}]
        # the explicit key replays regardless of fingerprint or age — retry-safe.
        self.assertEqual(
            authoring.find_draft_replay(drafts, "abc", "fp-anything")["name"],
            "ref-outreach",
        )

    def test_unknown_key_no_replay(self):
        drafts = [{"idempotencyKey": "abc", "fingerprint": "fp-x",
                   "createdAt": 1000, "preview": {"name": "ref-outreach"}}]
        self.assertIsNone(authoring.find_draft_replay(drafts, "zzz", "fp-x"))

    def test_double_click_same_request_replays(self):
        fp = authoring.draft_fingerprint("referral outreach", False)
        drafts = [{"fingerprint": fp, "createdAt": 1000, "preview": {"name": "ref"}}]
        self.assertEqual(
            authoring.find_draft_replay(drafts, "", fp, now=1010)["name"], "ref"
        )

    def test_different_request_not_deduped(self):
        # correctness point: two DISTINCT asks within the window must NOT collapse.
        fp_a = authoring.draft_fingerprint("referral outreach", False)
        drafts = [{"fingerprint": fp_a, "createdAt": 1000, "preview": {"name": "ref"}}]
        fp_b = authoring.draft_fingerprint("intake checklist", False)
        self.assertIsNone(authoring.find_draft_replay(drafts, "", fp_b, now=1010))

    def test_double_click_outside_window(self):
        fp = authoring.draft_fingerprint("referral outreach", False)
        drafts = [{"fingerprint": fp, "createdAt": 1000, "preview": {"name": "ref"}}]
        # 31s > DRAFT_REPLAY_WINDOW_S (30) — a fresh draft, not a double-click.
        self.assertIsNone(authoring.find_draft_replay(drafts, "", fp, now=1031))

    def test_empty_cache_no_replay(self):
        self.assertIsNone(authoring.find_draft_replay([], "", "fp-x"))
        self.assertIsNone(authoring.find_draft_replay([], "abc", "fp-x"))


class _CountingStub:
    """Clean model that COUNTS calls — proves a replay spends no new Vertex call."""

    def __init__(self, obj) -> None:
        self.obj = obj
        self.calls = 0

    def __call__(self, system: str, user: str) -> str:
        self.calls += 1
        return json.dumps(self.obj)


@unittest.skipUnless(_HAS_APP, "fastapi/TestClient absent (CI honesty-seam venv)")
class TestDraftRouteWiring(unittest.TestCase):
    """End-to-end proof of the workflows_draft cost guards: a replay returns the
    cached preview with NO second model call, and the per-practice hourly brake
    429s a burst of distinct drafts. Skips where fastapi is absent (the prove.sh
    seam venv installs only google-genai + httpx); runs in any fastapi venv."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="shaula-draft-test-")
        self._saved_dir = config.LOCAL_STATE_DIR
        self._saved_model = authoring.MODEL
        self._saved_flag = config.AUTHORING_ENABLED
        self._saved_rate = config.DRAFT_MAX_PER_HOUR
        # store._path reads config.LOCAL_STATE_DIR live → redirect writes to a tmp dir.
        config.LOCAL_STATE_DIR = pathlib.Path(self._tmp)
        config.AUTHORING_ENABLED = True
        self.stub = _CountingStub(_GOOD)
        authoring.MODEL = self.stub
        svc_app._draft_hits.clear()
        self.client = TestClient(svc_app.app)

    def tearDown(self) -> None:
        config.LOCAL_STATE_DIR = self._saved_dir
        authoring.MODEL = self._saved_model
        config.AUTHORING_ENABLED = self._saved_flag
        config.DRAFT_MAX_PER_HOUR = self._saved_rate
        svc_app._draft_hits.clear()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_flag_off_404(self):
        config.AUTHORING_ENABLED = False
        r = self.client.post(
            "/v1/practices/p1/workflows/draft",
            json={"description": "monthly referral outreach"},
        )
        self.assertEqual(r.status_code, 404)

    def test_explicit_key_replays_without_second_model_call(self):
        body = {"description": "monthly referral outreach", "idempotencyKey": "k1"}
        r1 = self.client.post("/v1/practices/p1/workflows/draft", json=body)
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(self.stub.calls, 1)
        r2 = self.client.post("/v1/practices/p1/workflows/draft", json=body)
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(r2.json().get("idempotent"))
        self.assertEqual(self.stub.calls, 1)  # NO second Vertex chain on the replay
        self.assertEqual(r1.json()["steps"], r2.json()["steps"])  # same preview

    def test_double_click_no_key_replays_without_second_model_call(self):
        body = {"description": "monthly referral outreach"}  # no idempotencyKey
        r1 = self.client.post("/v1/practices/p1/workflows/draft", json=body)
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(self.stub.calls, 1)
        r2 = self.client.post("/v1/practices/p1/workflows/draft", json=body)
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(r2.json().get("idempotent"))
        self.assertEqual(self.stub.calls, 1)  # fingerprint double-click guard held

    def test_rate_limit_429_on_distinct_burst(self):
        config.DRAFT_MAX_PER_HOUR = 1
        r1 = self.client.post(
            "/v1/practices/p1/workflows/draft", json={"description": "referral outreach"}
        )
        self.assertEqual(r1.status_code, 200)
        # a DISTINCT ask (no replay) past the brake → 429, no second Vertex chain.
        r2 = self.client.post(
            "/v1/practices/p1/workflows/draft",
            json={"description": "intake checklist process"},
        )
        self.assertEqual(r2.status_code, 429)
        self.assertEqual(self.stub.calls, 1)

    def test_replay_bypasses_rate_limit(self):
        # the brake counts NEW drafts only — an idempotent replay still succeeds.
        config.DRAFT_MAX_PER_HOUR = 1
        body = {"description": "referral outreach", "idempotencyKey": "k9"}
        first = self.client.post("/v1/practices/p1/workflows/draft", json=body)
        self.assertEqual(first.status_code, 200)
        again = self.client.post("/v1/practices/p1/workflows/draft", json=body)
        self.assertEqual(again.status_code, 200)
        self.assertTrue(again.json().get("idempotent"))


if __name__ == "__main__":
    unittest.main()
