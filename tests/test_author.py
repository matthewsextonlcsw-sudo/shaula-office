"""test_author — therapist self-serve authoring, deterministic + CI-safe.

Stub models stand in for the LLM so the SAFETY WALL is provable in CI without a
real model: a non-vetted assignee is rejected, a banned claim is rejected, and a
clean request becomes a vetted, honesty-gated kanban task-graph + a linted skill.
"""
from __future__ import annotations

import json
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from svc.gemini import BrainError  # noqa: E402
from workflows import author as A  # noqa: E402


def _wf(steps: list[dict], name: str = "monthly-referral-outreach") -> str:
    return json.dumps({"name": name, "description": "Draft a monthly referral note.", "steps": steps})


_GOOD_STEPS = [
    {"ref": "draft", "title": "Draft the outreach note", "assignee": "blog",
     "description": "Write a warm, honest note to a referral partner.", "dependencies": []},
    {"ref": "review", "title": "Honesty review", "assignee": "reviewer",
     "description": "Check the note against the honesty rules.",
     "dependencies": ["draft"], "requires_review": True},
]


class ConstModel:
    """Returns the same canned reply every call (records call count)."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0

    def __call__(self, system: str, user: str) -> str:
        self.calls += 1
        return self.reply


class TestDraftWorkflow(unittest.TestCase):
    def test_clean_request_becomes_vetted_plan(self):
        tmpl, plan = A.author_to_plan("monthly referral outreach", "Cedar & Sage", ConstModel(_wf(_GOOD_STEPS)))
        self.assertEqual([t.ref for t in plan], ["draft", "review"])
        self.assertTrue(all(p.payload["assignee"] in A.VETTED_PROFILES for p in plan))
        # build_plan stamps the house rules on every task body.
        self.assertIn("SHAULA HOUSE RULES", plan[0].payload["body"])

    def test_non_vetted_assignee_is_rejected(self):
        bad = [
            {"ref": "x", "title": "Do a thing", "assignee": "hacker", "description": "..."},
            {"ref": "review", "title": "Review", "assignee": "reviewer",
             "description": "check", "dependencies": ["x"], "requires_review": True},
        ]
        m = ConstModel(_wf(bad))
        with self.assertRaises(A.AuthoringError) as ctx:
            A.draft_workflow("escalate to my custom bot", "Cedar & Sage", m)
        # it tried, fed the violation back, retried, then refused — the safety wall.
        self.assertGreaterEqual(m.calls, 2)
        self.assertTrue(any("hacker" in v or "vetted" in v for v in ctx.exception.violations))

    def test_banned_claim_in_step_is_rejected(self):
        bad = [
            {"ref": "draft", "title": "Write a proven, #1 outreach note", "assignee": "blog",
             "description": "Promise guaranteed results — studies show 95% success."},
            {"ref": "review", "title": "Review", "assignee": "reviewer",
             "description": "check", "dependencies": ["draft"], "requires_review": True},
        ]
        with self.assertRaises(A.AuthoringError):
            A.draft_workflow("aggressive marketing campaign", "Cedar & Sage", ConstModel(_wf(bad)))

    def test_garbage_reply_is_rejected_not_crashed(self):
        with self.assertRaises(A.AuthoringError):
            A.draft_workflow("do something", "Cedar & Sage", ConstModel("sorry, I cannot help"))


class TestModelRaisedErrorIsRepairable(unittest.TestCase):
    """The repair loop runs model() INSIDE its try. In prod the model callable can
    itself raise AuthoringError (the svc adapter translates a gemini honesty trip);
    that must be re-prompted like any validation failure, never an unhandled escape."""

    def test_model_raised_authoring_error_is_repaired(self):
        class TripThenClean:
            def __init__(self) -> None:
                self.calls = 0

            def __call__(self, system: str, user: str) -> str:
                self.calls += 1
                if self.calls == 1:
                    raise A.AuthoringError(
                        "draft used banned language",
                        violations=["a percent sign reads like a statistic"],
                    )
                return _wf(_GOOD_STEPS)

        m = TripThenClean()
        tmpl = A.draft_workflow("monthly outreach", "Cedar & Sage", m)
        self.assertEqual(m.calls, 2)  # tripped once, re-prompted, then clean
        self.assertEqual([s.ref for s in tmpl.steps], ["draft", "review"])

    def test_model_raised_authoring_error_exhausts_to_refusal(self):
        class AlwaysTrips:
            def __init__(self) -> None:
                self.calls = 0

            def __call__(self, system: str, user: str) -> str:
                self.calls += 1
                raise A.AuthoringError("draft used banned language", violations=["banned: proven"])

        m = AlwaysTrips()
        with self.assertRaises(A.AuthoringError) as ctx:
            A.draft_workflow("x", "Cedar & Sage", m)
        self.assertEqual(m.calls, 2)  # max_repair + 1 attempts, then the safety wall
        self.assertTrue(ctx.exception.violations)


class TestDraftSkill(unittest.TestCase):
    def test_clean_skill_is_linted_and_returned(self):
        reply = json.dumps({
            "name": "Referral Outreach",
            "description": "How to write an honest referral-partner note.",
            "body": "## When to use\nWhen reaching a new referral partner.\n## How\nBe warm, specific, honest. Refuse to overpromise.",
        })
        skill = A.draft_skill("referral outreach guidance", "Cedar & Sage", ConstModel(reply))
        self.assertEqual(skill["name"], "referral-outreach")  # slugified
        self.assertIn("When to use", skill["body"])

    def test_banned_skill_body_trips_the_honesty_gate(self):
        reply = json.dumps({
            "name": "hype",
            "description": "Guaranteed results.",
            "body": "Tell clients our therapy is clinically proven and #1 — studies show 95% are cured.",
        })
        with self.assertRaises(BrainError) as ctx:
            A.draft_skill("growth hacking", "Cedar & Sage", ConstModel(reply))
        self.assertEqual(ctx.exception.category, "honesty")


if __name__ == "__main__":
    unittest.main()
