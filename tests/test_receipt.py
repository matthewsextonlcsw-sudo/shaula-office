"""Honesty receipt contract (concierge-beta deliverable C — the differentiator).

The receipt is GENERATED from the engine's structured refusal output (stream 1),
never hand-assembled. These tests pin that it:

  * names what was shown vs. honestly held back (resolved vs. dropped modalities);
  * renders the banned-language policy in DEDUPED plain English (reusing
    svc/honesty), never raw regex;
  * flags every default as an assumption (from build_practice's ``_assumed``);
  * attests lint-clean only when the manifest says so, and warns loudly otherwise;
  * is deterministic — the pure renderer takes the date, never reads a clock;
  * cannot drift from the site — ``build_refusals`` runs the same deterministic
    ``generate()`` the build used.

Stdlib only (unittest), so prove.sh runs it with no new dependency. NO PHI —
synthetic fixture + literal names only.
"""
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "engine", ROOT / "svc", ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import build_practice as BP  # noqa: E402
import honesty_receipt as R  # noqa: E402

SURVEY = json.loads(
    (ROOT / "fixtures" / "northstar-denver" / "survey.json").read_text(encoding="utf-8")
)


class BuildRefusals(unittest.TestCase):
    def test_runs_the_same_generate_and_returns_a_clean_manifest(self):
        practice = BP.build_practice(SURVEY)
        ref = R.build_refusals(practice)
        # The receipt's source of truth: the engine's own manifest, lint-clean.
        self.assertTrue(ref["lint_clean"])
        self.assertEqual(ref["modalities_shown"][:2],
                         ["Cognitive Behavioral Therapy", "Acceptance & Commitment Therapy"])
        self.assertIn("mindfulness-based", ref["modalities_dropped_unknown"])


class ReceiptRender(unittest.TestCase):
    def setUp(self):
        self.practice = BP.build_practice(SURVEY)
        self.refusals = R.build_refusals(self.practice)
        self.md = R.receipt_markdown(
            self.practice, self.refusals,
            business_name="North Star Counseling", generated_on="2026-06-15",
        )

    def test_names_shown_and_held_back_modalities(self):
        self.assertIn("North Star Counseling", self.md)
        self.assertIn("Cognitive Behavioral Therapy", self.md)
        self.assertIn("Acceptance & Commitment Therapy", self.md)
        # The honest refusal: a listed modality with no real citation is held back.
        self.assertIn("Held back", self.md)
        self.assertIn("mindfulness-based", self.md)

    def test_banned_policy_is_plain_english_not_regex(self):
        # Plain words ride in; the raw linter patterns must NOT leak to the page.
        self.assertIn("therapy outcomes cannot be guaranteed", self.md)
        for raw in (r"\b", "\\d{1,3}", "world[- ]class"):
            self.assertNotIn(raw, self.md)

    def test_cure_phrase_is_deduped(self):
        # \bcure\b and \bcures\b both map to the same plain phrase — render once.
        self.assertEqual(self.md.count("a 'cure' promise"), 1)

    def test_assumptions_are_flagged_with_labels(self):
        self.assertIn("Assumptions we made", self.md)
        # northstar supplies none of the commitment fields -> defaults, each flagged.
        labels = {a["label"] for a in self.practice["_assumed"]}
        self.assertTrue(labels)  # there ARE assumptions to show
        for label in labels:
            self.assertIn(label, self.md)

    def test_attestation_present(self):
        self.assertIn("lint-clean by construction", self.md)
        self.assertIn("0 PHI", self.md)

    def test_renderer_is_deterministic(self):
        again = R.receipt_markdown(
            self.practice, self.refusals,
            business_name="North Star Counseling", generated_on="2026-06-15",
        )
        self.assertEqual(self.md, again)


class ReceiptEdgeCases(unittest.TestCase):
    def test_no_assumptions_renders_the_none_branch(self):
        practice = {"business_name": "Fully Supplied LLC", "_assumed": []}
        refusals = {
            "modalities_listed": ["CBT"], "modalities_shown": ["Cognitive Behavioral Therapy"],
            "modalities_dropped_unknown": [], "modalities_capped": [],
            "banned_language_enforced": [r"\bcure\b"], "lint_clean": True,
        }
        md = R.receipt_markdown(practice, refusals, generated_on="2026-06-15")
        self.assertIn("you supplied every field", md)
        self.assertIn("Nothing was held back", md)

    def test_missing_lint_clean_warns_loudly(self):
        practice = {"business_name": "X", "_assumed": []}
        refusals = {
            "modalities_listed": [], "modalities_shown": [],
            "modalities_dropped_unknown": [], "modalities_capped": [],
            "banned_language_enforced": [], "lint_clean": False,
        }
        md = R.receipt_markdown(practice, refusals, generated_on="2026-06-15")
        self.assertIn("WITHOUT a verified lint-clean", md)
        self.assertNotIn("lint-clean by construction", md)


if __name__ == "__main__":
    unittest.main()
