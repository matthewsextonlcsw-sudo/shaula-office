"""test_cockpit_local_runner — the desktop app's built-in office, CI-safe.

The v0.1.x desktop app shipped without its workflows because the cockpit's
capability surface only spoke to a hosted svc. local_runner serves the same
contract locally; these tests pin it with a stub model (zero network, zero
Ollama): the roster carries every manifest capability, a run executes with
handoffs and PARKS at the reviewer step (a model never approves its own
review), an affirmative banned claim kills the run at the honesty gate, and
approve/reject flip states the way the UI expects.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import time
import unittest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
for p in (str(_ROOT), str(_ROOT / "cockpit"), str(_ROOT / "engine")):
    if p not in sys.path:
        sys.path.insert(0, p)

import local_runner as LR  # noqa: E402
import router  # noqa: E402


def _wait(rid, statuses, tries=100):
    for _ in range(tries):
        run = LR.get_run(rid)["run"]
        if run["status"] in statuses:
            return run
        time.sleep(0.05)
    raise AssertionError(f"run never reached {statuses}: {LR.get_run(rid)['run']['status']}")


class LocalOffice(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["SHAULA_STATE_DIR"] = os.path.join(self._tmp.name, "state")
        os.environ["SHAULA_SITES_DIR"] = os.path.join(self._tmp.name, "sites")
        LR._RUNS.clear()
        LR._LOADED = True  # each test starts from an empty, isolated board
        self._orig = router._call_ollama

    def tearDown(self):
        router._call_ollama = self._orig
        os.environ.pop("SHAULA_STATE_DIR", None)
        os.environ.pop("SHAULA_SITES_DIR", None)
        self._tmp.cleanup()

    # ── roster is manifest truth ─────────────────────────────────────────────
    def test_roster_serves_every_manifest_capability(self):
        manifest = json.loads((_ROOT / "workflows" / "CAPABILITY_MANIFEST.json").read_text())
        expected = {c["id"] for c in manifest["capabilities"]}
        staff = LR.roster()["staff"]
        served = {c["id"] for s in staff for c in s["capabilities"]}
        self.assertEqual(served, expected, "roster drifted from the manifest")
        self.assertEqual(len(staff), 8, "the 8 no-PHI office roles")

    # ── a run executes and parks at the human gate ──────────────────────────
    def test_run_parks_at_review_with_handoffs(self):
        seen_prompts = []

        def stub(system, message, max_tokens, history=None):
            seen_prompts.append(message)
            return "An honest draft about rest, with no big claims."
        router._call_ollama = stub

        out = LR.create_run("weekly-blog", "rest")
        self.assertTrue(out["ok"], out)
        run = _wait(out["runId"], {"needs_approval"})
        done = [s for s in run["steps"] if s["status"] == "done"]
        self.assertEqual(len(done), run["stepsTotal"] - 1, "all non-review steps done")
        waiting = run["steps"][-1]
        self.assertTrue(waiting["isReview"] and waiting["status"] == "waiting")
        # Handoffs: later steps saw earlier steps' output.
        self.assertIn("WORK FROM EARLIER STEPS", seen_prompts[-1])

    # ── the moat ─────────────────────────────────────────────────────────────
    def test_banned_claim_fails_the_run(self):
        router._call_ollama = lambda *a, **k: "Our therapy is clinically proven to cure anxiety."
        out = LR.create_run("faq-engine", "anxiety")
        run = _wait(out["runId"], {"failed"})
        self.assertEqual(run["error"], "honesty gate")
        failed = [s for s in run["steps"] if s["status"] == "failed"]
        self.assertIn("honesty gate", failed[0]["output"].lower().replace("refused by the ", ""))

    # ── model silence is an honest failure ───────────────────────────────────
    def test_no_model_answer_fails_honestly(self):
        router._call_ollama = lambda *a, **k: None
        out = LR.create_run("copy-engine", "about page")
        run = _wait(out["runId"], {"failed"})
        self.assertIn("Ollama", run["error"])

    # ── approve / reject ─────────────────────────────────────────────────────
    def test_approve_and_reject_flip_states(self):
        router._call_ollama = lambda *a, **k: "Plain, honest copy."
        a = LR.create_run("weekly-blog", "sleep")
        _wait(a["runId"], {"needs_approval"})
        self.assertEqual(LR.approve_run(a["runId"])["status"], "approved")
        self.assertEqual(LR.get_run(a["runId"])["run"]["status"], "approved")

        b = LR.create_run("weekly-blog", "boundaries")
        _wait(b["runId"], {"needs_approval"})
        self.assertEqual(LR.reject_run(b["runId"], note="not my voice")["status"], "rejected")

    # ── unknown capability is refused, not crashed ───────────────────────────
    def test_unknown_capability_refused(self):
        out = LR.create_run("nonsense-engine", "x")
        self.assertFalse(out["ok"])

    # ── interrupted runs load as failed, never silently resume ──────────────
    def test_interrupted_run_marked_failed_on_load(self):
        state = pathlib.Path(os.environ["SHAULA_STATE_DIR"])
        state.mkdir(parents=True, exist_ok=True)
        (state / "runs.json").write_text(json.dumps([
            {"id": "r_x", "capability": "weekly-blog", "topic": "t",
             "status": "working", "steps": [], "stepsDone": 0, "stepsTotal": 5,
             "currentStep": "", "created": 0}]))
        LR._RUNS.clear()
        LR._LOADED = False
        LR._load()
        self.assertEqual(LR._RUNS["r_x"]["status"], "failed")
        self.assertIn("interrupted", LR._RUNS["r_x"]["error"])


if __name__ == "__main__":
    unittest.main()
