"""Negation-awareness for the VALUE-tier honesty linter (engine/banned.py:lint).

THE BUG this pins: the deck-engine 'brief' step is *instructed* to write
disclaimers ("not a substitute for individual treatment") and to flag claims a
clinician must verify. The staff did exactly that — "...is not a guarantee of
specific outcomes..." and "...rather than cures or treatments..." — and the
substring linter refused its own safety language, failing the whole run at step
0. A disclaimer is the OPPOSITE of a marketing claim; the gate must not eat it.

The fix is asymmetric ON PURPOSE — it may only ever REMOVE false positives:

  * affirmative claims STILL trip ("we guarantee results", "it cures insomnia"),
  * a negator shielded by a fresh predicate STILL trips ("we don't just help —
    we guarantee results"): no false negative is introduced,
  * only a banned word a negator actually governs is exempted.

And the RENDER tier stays a dumb substring match: it feeds a `grep -iE` scan and
tests/test_banned.py pins Python==grep, so negation logic must NOT leak into it.

Stdlib only. NO PHI — marketing-claim patterns and synthetic strings only.
"""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "engine", ROOT / "svc"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import banned  # noqa: E402
import honesty  # noqa: E402  — narration layer, must quote the AFFIRMATIVE claim


class AffirmativeClaimsStillCaught(unittest.TestCase):
    """The floor: real claims must never slip through. A miss here is a breach."""

    POSITIVES = [
        "We guarantee results.",
        "Results guaranteed in six weeks.",
        "This approach cures anxiety.",
        "It cures insomnia.",
        "A cure for burnout.",
        "Meditation cures perfectionism.",
        "Our method is proven to work.",
        "The best therapist in the city.",
        "Up 40% in six weeks.",          # percentage — never negatable here
        "The #1 choice for families.",
    ]

    def test_each_positive_trips_the_value_linter(self):
        for text in self.POSITIVES:
            with self.subTest(text=text):
                self.assertTrue(banned.lint(text), f"value tier MISSED a real claim: {text!r}")


class DisclaimersAreExempt(unittest.TestCase):
    """Negated / flagged-to-avoid usage is a disclaimer, not a claim."""

    NEGATED = [
        "This is not a guarantee of specific outcomes.",
        "There is no guarantee of any particular result.",
        "Results are not guaranteed.",
        "Outcomes cannot be guaranteed.",
        "We offer no guarantees.",
        "Without any guarantee of outcome.",
        "This workshop is not a cure.",
        "Meditation is not a cure for anxiety.",
        "Frame practices as supportive rather than cures or treatments.",
        "Describe them as coping tools instead of cures.",
    ]

    def test_each_disclaimer_is_clean(self):
        for text in self.NEGATED:
            with self.subTest(text=text):
                self.assertEqual(banned.lint(text), [], f"disclaimer wrongly refused: {text!r}")


class TheTwoLiveOffendingSentences(unittest.TestCase):
    """Regression-pin the EXACT sentences that failed deck-engine run-2459350ba9."""

    def test_disclaimer_sentence_is_clean(self):
        s = "The information shared today is not a guarantee of specific outcomes or results."
        self.assertEqual(banned.lint(s), [])

    def test_claim_flagging_sentence_is_clean(self):
        s = ("Any statements linking meditation directly to specific clinical outcomes for "
             "anxiety, burnout, or perfectionism must be carefully worded as supportive "
             "practices rather than cures or treatments, and backed by verifiable sources.")
        self.assertEqual(banned.lint(s), [])


class NoFalseNegativesIntroduced(unittest.TestCase):
    """A negator earlier in the sentence must NOT shield a fresh affirmative claim."""

    def test_far_negator_does_not_exempt_a_new_predicate(self):
        s = "We don't just help — we guarantee results."
        self.assertTrue(banned.lint(s), "a real guarantee slipped through behind an earlier 'don't'")

    def test_mixed_sentence_still_flags_the_real_claim(self):
        # disclaimer on 'guarantee' is exempt, but the affirmative 'cure' is not
        s = "This is not a guarantee, but we promise a cure for your anxiety."
        self.assertIn(r"\bcure\b", banned.lint(s))

    def test_no_discourse_marker_is_not_a_negator(self):
        s = "No, we guarantee results."  # 'No,' is a discourse marker, not negating 'guarantee'
        self.assertTrue(banned.lint(s))


class RenderTierStaysDumb(unittest.TestCase):
    """The render tier must keep matching grep — negation logic must NOT leak in."""

    def test_render_lint_still_flags_a_disclaimer_substring(self):
        # 'not a guarantee' still trips render_lint, because that tier is a pure
        # substring scan pinned equal to the shell grep (tests/test_banned.py).
        self.assertTrue(banned.render_lint("this is not a guarantee"))

    def test_value_and_render_now_disagree_on_disclaimers_by_design(self):
        s = "outcomes are not guaranteed"
        self.assertEqual(banned.lint(s), [])              # value tier: clean
        self.assertTrue(banned.render_lint(s))            # render tier: still hits


class NarrationQuotesTheRealClaim(unittest.TestCase):
    """svc/honesty.explain must quote the AFFIRMATIVE sentence, not a disclaimer
    that merely shares the banned word."""

    def test_offending_sentence_skips_the_disclaimer(self):
        text = ("This is not a cure. We promise a cure for your anxiety.")
        reasons = honesty.explain(text, [r"\bcure\b"])
        self.assertEqual(len(reasons), 1)
        self.assertIn("We promise a cure", reasons[0]["quote"])
        self.assertNotIn("not a cure", reasons[0]["quote"])


if __name__ == "__main__":
    unittest.main()
