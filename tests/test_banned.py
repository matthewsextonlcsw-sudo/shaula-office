"""Anti-drift contract for the single-sourced banned-language gate.

engine/banned.py is the ONE definition of Shaula's banned-language list. Every
other honesty surface — engine/generate.py, engine/geo.py, scripts/honesty_scan.py,
svc/honesty.py, and the two proof scripts (scripts/prove.sh, scripts/e2e_synthetic.sh)
— must DERIVE from it, never re-list it. This suite is the guarantee that they do:
if any consumer stops resolving to engine/banned.py, or the shell regex stops
equaling the Python render tier, a test here goes red and the proof gate fails.

Four kinds of assertion:

  1. STRUCTURE   — the canonical module's own invariants: two tiers, the render
                   tier is the documented CSS-safe subset, the "number one" hoist
                   is present, no duplicate patterns.
  2. IDENTITY    — every Python consumer's banned set IS this module's object
                   (`is`, not just `==`), so it cannot be a stale hand-copy.
  3. DERIVATION  — the proof scripts derive RENDER_BANNED from banned.py at run
                   time (they neither hardcode it nor omit the derivation).
  4. BEHAVIOR    — the exact `grep -iE` regex prove.sh scans with produces the
                   SAME verdict as the Python render tier across a battery of
                   positive / CSS-false-positive / value-only-tier inputs. This is
                   the real anti-drift proof: shell and Python cannot disagree.

Stdlib only (unittest + subprocess), so scripts/prove.sh runs it with no new
dependency. NO PHI — marketing-claim patterns and synthetic strings only.
"""
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
# Match how each consumer is reached at run time: every module is imported under
# its TOP-LEVEL name (engine/, scripts/, svc/ each on the path), so they all bind
# the same `sys.modules['banned']` object — which is what the identity tests pin.
for _p in (ROOT, ROOT / "engine", ROOT / "scripts", ROOT / "svc"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import banned  # noqa: E402  — the canonical source
import generate as G  # noqa: E402  — engine consumer (re-exports _BANNED / lint)
import geo  # noqa: E402  — engine consumer (compiled VALUE_REGEX)
import honesty_scan  # noqa: E402  — scripts consumer (derives via generate.G.lint)
import honesty  # noqa: E402  — svc narration consumer (_PLAIN keyed by canonical)

PROVE_SH = (ROOT / "scripts" / "prove.sh").read_text(encoding="utf-8")
E2E_SH = (ROOT / "scripts" / "e2e_synthetic.sh").read_text(encoding="utf-8")


def grep_hits(pattern: str, text: str) -> bool:
    """True iff `grep -iE pattern` matches text — the SAME binary + flags (minus
    -r) prove.sh uses. The interactive-shell ugrep shim is not inherited by a
    subprocess, so this resolves to the real system grep, exactly like the
    proof scripts' child bash does."""
    proc = subprocess.run(
        ["grep", "-iE", pattern],
        input=text,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 2:
        raise AssertionError(f"grep errored on {pattern!r}: {proc.stderr.strip()}")
    return proc.returncode == 0


class Structure(unittest.TestCase):
    def test_render_tier_is_proper_subset_of_value_tier(self):
        self.assertTrue(set(banned.RENDER_BANNED_PATTERNS) < set(banned.BANNED_PATTERNS))

    def test_render_excluded_is_exactly_the_documented_three(self):
        self.assertEqual(
            banned._RENDER_EXCLUDED,
            frozenset({r"\b\d{1,3}\s?%", r"#1\b", r"\bnumber one\b"}),
        )

    def test_excluded_set_is_the_tier_difference(self):
        # The render tier is DERIVED (value minus excluded), never re-listed.
        self.assertEqual(
            set(banned.BANNED_PATTERNS) - set(banned.RENDER_BANNED_PATTERNS),
            set(banned._RENDER_EXCLUDED),
        )

    def test_number_one_hoist_present_in_value_tier(self):
        self.assertIn(r"\bnumber one\b", banned.BANNED_PATTERNS)

    def test_no_duplicate_patterns(self):
        self.assertEqual(len(banned.BANNED_PATTERNS), len(set(banned.BANNED_PATTERNS)))

    def test_shell_regex_equals_python_render_join(self):
        self.assertEqual(
            banned.render_banned_shell_regex(),
            "|".join(banned.RENDER_BANNED_PATTERNS),
        )


class Identity(unittest.TestCase):
    def test_generate_reexports_canonical_list_and_linter(self):
        self.assertIs(G._BANNED, banned.BANNED_PATTERNS)
        self.assertIs(G.lint, banned.lint)

    def test_geo_uses_canonical_compiled_value_regex(self):
        self.assertIs(geo._BANNED, banned.VALUE_REGEX)

    def test_honesty_scan_derives_through_generate(self):
        self.assertIs(honesty_scan.G, G)
        self.assertIs(honesty_scan.G.lint, banned.lint)

    def test_receipt_attestation_names_the_canonical_list(self):
        # The honesty receipt's standing-policy line must be the canonical set.
        manifest = G.refusals_manifest({"modalities": "CBT"})
        self.assertEqual(manifest["banned_language_enforced"], list(banned.BANNED_PATTERNS))


class SvcHonestyCoverage(unittest.TestCase):
    def test_plain_words_cover_exactly_the_canonical_set(self):
        # Every canonical pattern has a human-readable translation, and there are
        # no stale extras that no longer correspond to a banned pattern.
        self.assertEqual(set(honesty._PLAIN), set(banned.BANNED_PATTERNS))

    def test_no_unknown_patterns(self):
        self.assertEqual(honesty.unknown_patterns(), [])


class ScriptsDerive(unittest.TestCase):
    def test_scripts_do_not_hardcode_render_banned(self):
        for name, txt in (("prove.sh", PROVE_SH), ("e2e_synthetic.sh", E2E_SH)):
            self.assertNotIn("RENDER_BANNED='", txt, f"{name} still hardcodes RENDER_BANNED")

    def test_scripts_derive_render_banned_from_canonical(self):
        for name, txt in (("prove.sh", PROVE_SH), ("e2e_synthetic.sh", E2E_SH)):
            self.assertIn(
                "banned.render_banned_shell_regex()",
                txt,
                f"{name} must derive RENDER_BANNED from engine/banned.py",
            )


class GrepHonorsWordBoundary(unittest.TestCase):
    """The whole behavioral guarantee rests on grep honoring \\b like Python; if a
    grep build did not, these pinpoint it before the equivalence tests confuse."""

    def test_boundary_matches_whole_word(self):
        self.assertTrue(grep_hits(r"\bcure\b", "a cure today"))

    def test_boundary_rejects_substring(self):
        self.assertFalse(grep_hits(r"\bcure\b", "manicure appointment"))


class RenderTierBehavioralEquivalence(unittest.TestCase):
    """The exact regex prove.sh greps with == the Python render tier, input by input."""

    SHELL = banned.render_banned_shell_regex()

    # Phrases the rendered-output scan MUST catch — Python and grep agree HIT.
    RENDER_POSITIVES = [
        "this is proven to work",
        "results guaranteed",
        "studies show it helps",
        "research proves the method",
        "a clinically proven approach",
        "read a client testimonial",
        "a cure for anxiety",
        "it cures insomnia",
        "a miracle outcome",
        "the best therapist in town",
        "world-class care",
        "world class care",
    ]

    # CSS-in-JS the scan MUST ignore — Python and grep agree MISS (the reason the
    # percentage and #1 rules are excluded from the render tier).
    CSS_NEGATIVES = [
        "width:100%",
        "max-width: 100%;",
        "color:#1a2b3c",
        "background:#1f2937",
    ]

    # Value-tier-ONLY claims — caught by the full value linter, deliberately NOT
    # by the CSS-safe render tier (and so not by the shell scan either).
    VALUE_ONLY = [
        "up 40% in six weeks",
        "the #1 choice",
        "number one in the city",
    ]

    def test_render_positives_hit_both_python_and_grep(self):
        for text in self.RENDER_POSITIVES:
            with self.subTest(text=text):
                self.assertTrue(banned.render_lint(text), f"python render tier missed: {text!r}")
                self.assertTrue(grep_hits(self.SHELL, text), f"grep missed: {text!r}")

    def test_css_negatives_miss_both_python_and_grep(self):
        for text in self.CSS_NEGATIVES:
            with self.subTest(text=text):
                self.assertFalse(banned.render_lint(text), f"python render tier false-positive: {text!r}")
                self.assertFalse(grep_hits(self.SHELL, text), f"grep false-positive: {text!r}")

    def test_value_only_caught_by_value_tier_but_not_render_or_grep(self):
        for text in self.VALUE_ONLY:
            with self.subTest(text=text):
                self.assertTrue(banned.lint(text), f"value tier missed: {text!r}")
                self.assertFalse(banned.render_lint(text), f"render tier should omit: {text!r}")
                self.assertFalse(grep_hits(self.SHELL, text), f"shell scan should omit: {text!r}")


if __name__ == "__main__":
    unittest.main()
