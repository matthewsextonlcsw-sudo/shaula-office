"""test_local_executor — the Option-C wiring proof, deterministic + CI-safe.

Uses a stub model (no network, no cloud, no Ollama) so the harness — the
builder bridge, DAG handoffs, the real honesty gate, and human-review parking —
is provable in CI without burning a single real model call. The real-model run
(Ollama) lives in sandbox/prove_research_desk.py, not here.
"""
from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from workflows import local_executor as LE  # noqa: E402
from workflows.builder import build_plan, load_template_file  # noqa: E402

_RESEARCH = os.path.join(_ROOT, "workflows", "templates", "research-engine.json")
_VARS = {"topic": "sleep hygiene and anxiety", "project": "Cedar & Sage Therapy"}

# A banned-claim payload that trips multiple linter rules (studies show / % /
# guaranteed / proven) — proves the gate is the real one, not a stub.
_BANNED = "Studies show 95% of clients improve — a guaranteed, proven outcome."


class StubModel:
    """Deterministic model. Records every call; returns tagged honest text, or
    the banned payload on the Nth call when armed."""

    def __init__(self, banned_call: int | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.banned_call = banned_call

    def __call__(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        n = len(self.calls)
        if self.banned_call == n:
            return _BANNED
        return f"STEP{n}: plain general wellness information, not advice. [established]"


class TestPlanShape(unittest.TestCase):
    def test_research_template_plans_four_steps_review_is_gate(self):
        plan = build_plan(load_template_file(_RESEARCH), _VARS)
        self.assertEqual([t.ref for t in plan], ["scope", "findings", "brief", "review"])
        self.assertFalse(LE._is_human_gate(plan[0]))   # scope = model step
        self.assertTrue(LE._is_human_gate(plan[-1]))    # review = human gate
        # build_plan must have stamped the house rules on every task body.
        self.assertIn("SHAULA HOUSE RULES", plan[0].payload["body"])


class TestCleanRun(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = build_plan(load_template_file(_RESEARCH), _VARS)
        self.model = StubModel()
        self.run = LE.execute_plan(
            self.plan, self.model, template_name="research-engine", topic=_VARS["topic"]
        )

    def test_parks_at_human_review(self):
        self.assertEqual(self.run.status, "needs_review")
        self.assertTrue(self.run.review_reason.startswith("review-required:"))

    def test_only_the_three_model_steps_called(self):
        # scope, findings, brief run; review is NOT sent to the model.
        self.assertEqual(len(self.model.calls), 3)
        self.assertEqual(self.run.step("review").status, "parked-review")
        for ref in ("scope", "findings", "brief"):
            self.assertEqual(self.run.step(ref).status, "done")

    def test_deliverable_is_the_brief(self):
        self.assertIn("STEP3", self.run.deliverable)  # brief = 3rd call

    def test_dag_handoffs_propagate(self):
        # findings (call 2) must carry scope's output; brief (call 3) must carry findings'.
        self.assertIn("Handoff from", self.model.calls[1][1])
        self.assertIn("STEP1", self.model.calls[1][1])
        self.assertIn("STEP2", self.model.calls[2][1])


class TestHonestyMoat(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = build_plan(load_template_file(_RESEARCH), _VARS)

    def _run(self, banned_call: int) -> LE.RunResult:
        return LE.execute_plan(self.plan, StubModel(banned_call=banned_call))

    def test_banned_at_first_step_parks_run(self):
        r = self._run(banned_call=1)
        self.assertEqual(r.status, "honesty_failed")
        self.assertEqual(r.honesty["atRef"], "scope")
        self.assertTrue(r.honesty["reasons"], "explanations must ride the failure")
        self.assertEqual(r.deliverable, "", "nothing ships when the gate fires")

    def test_banned_at_brief_blocks_delivery(self):
        r = self._run(banned_call=3)
        self.assertEqual(r.status, "honesty_failed")
        self.assertEqual(r.honesty["atRef"], "brief")
        self.assertEqual(r.deliverable, "")
        # the run dies at the brief — it never reaches the review gate.
        self.assertIsNone(r.step("review"))


if __name__ == "__main__":
    unittest.main()
