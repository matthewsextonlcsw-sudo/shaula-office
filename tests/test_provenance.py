"""Claim-provenance gate (engine/provenance.py) — the keystone that lets Shaula
accept ARBITRARY imported HTML (3a) and AI-FREEHAND layouts (3b) without losing
its published-honesty guarantee.

Where the fixed template makes honesty STRUCTURAL, this gate makes it PROVABLE on
content whose structure we do not control: every visible, claim-bearing unit of
the HTML must TRACE BACK to the approved content set (practice.json token values
+ generated.json block text), and anything un-sourced — or any affirmative
banned-language claim — is FLAGGED and the build REJECTED.

TDD shape (prove.sh-style, RED + GREEN):
  * RED  — HTML injecting a fake stat / fabricated testimonial / invented
           credential is REJECTED, and the offending text is NAMED.
  * GREEN — HTML assembled ONLY from approved northstar tokens/blocks (a
           deliberately arbitrary freehand layout) is ACCEPTED.

Plus unit coverage of the pieces (extraction, segmentation, corpus coverage,
allowlist, banned-gate reuse) and the CLI exit-code contract.

Stdlib only (unittest), no network, synthetic fixtures — runs inside prove.sh
with no new dependency. NO PHI.
"""
import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "engine"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import provenance as P  # noqa: E402

FIX = ROOT / "fixtures" / "provenance"
PRACTICE_PATH = ROOT / "fixtures" / "northstar-denver" / "practice.json"
GENERATED_PATH = ROOT / "engine" / "generated.northstar-denver.json"

PRACTICE = json.loads(PRACTICE_PATH.read_text(encoding="utf-8"))
GENERATED = json.loads(GENERATED_PATH.read_text(encoding="utf-8"))


def _html(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _kinds(offenders):
    return sorted({o.kind for o in offenders})


def _texts(offenders):
    return [o.text for o in offenders]


# --------------------------------------------------------------------------- #
# RED — fabrications are rejected, offender named.
# --------------------------------------------------------------------------- #
class RedFabricationsRejected(unittest.TestCase):
    """The three smuggling vectors arbitrary HTML opens up. Each MUST fail."""

    def test_fake_stat_rejected_and_named(self):
        offenders = P.gate(_html("red-fake-stat.html"), PRACTICE, GENERATED)
        self.assertTrue(offenders, "a fabricated statistic must be rejected")
        # Named: the injected stat sentence appears in the offender texts.
        self.assertTrue(
            any("92%" in t for t in _texts(offenders)),
            f"offenders must name the fake stat; got {_texts(offenders)!r}",
        )
        # Caught BOTH ways: banned percentage AND un-sourced coverage.
        self.assertEqual(_kinds(offenders),
                         ["banned-language", "unsourced-claim"])

    def test_fake_testimonial_rejected_and_named(self):
        offenders = P.gate(_html("red-fake-testimonial.html"), PRACTICE, GENERATED)
        self.assertTrue(offenders, "a fabricated testimonial must be rejected")
        joined = " || ".join(_texts(offenders))
        # The invented praise body and/or its byline are surfaced.
        self.assertIn("saved my marriage", joined)
        self.assertTrue(
            any("Jane" in t for t in _texts(offenders)),
            f"the fake byline should be flagged; got {_texts(offenders)!r}",
        )

    def test_invented_credential_rejected_as_unsourced(self):
        # The clinician is an LPC; "board-certified psychiatrist / Harvard MD /
        # PhD" is a credential they do not hold. This carries NO banned word —
        # so it is the pure-provenance catch the banned linter alone would MISS.
        offenders = P.gate(_html("red-fake-credential.html"), PRACTICE, GENERATED)
        self.assertTrue(offenders, "an invented credential must be rejected")
        self.assertIn(P.Offender.KIND_UNSOURCED, _kinds(offenders))
        self.assertTrue(
            any("board-certified" in t.lower() or "harvard" in t.lower()
                for t in _texts(offenders)),
            f"the invented credential must be named; got {_texts(offenders)!r}",
        )

    def test_invented_credential_has_no_banned_word(self):
        # Proves the provenance layer adds protection the banned gate cannot:
        # the credential line trips NO banned pattern on its own.
        import banned
        cred = ("Maya is a board-certified psychiatrist and Harvard-trained MD "
                "with a PhD in neuroscience.")
        self.assertEqual(banned.lint(cred), [],
                         "control: credential line is banned-clean; only "
                         "provenance coverage catches it")

    def test_all_red_fixtures_rejected(self):
        for name in ("red-fake-stat.html", "red-fake-testimonial.html",
                     "red-fake-credential.html"):
            with self.subTest(fixture=name):
                self.assertTrue(
                    P.gate(_html(name), PRACTICE, GENERATED),
                    f"{name} must be rejected",
                )


# --------------------------------------------------------------------------- #
# GREEN — honest arbitrary layout is accepted.
# --------------------------------------------------------------------------- #
class GreenApprovedAccepted(unittest.TestCase):
    def test_green_northstar_accepted(self):
        offenders = P.gate(_html("green-northstar.html"), PRACTICE, GENERATED)
        self.assertEqual(
            offenders, [],
            "an arbitrary layout built only from approved content must be "
            f"accepted; offenders: {[ (o.kind, o.text) for o in offenders ]!r}",
        )

    def test_green_script_body_fabrication_is_ignored(self):
        # The GREEN fixture hides "98% ... cured, guaranteed" inside <script>.
        # The gate drops script bodies, so it must NOT be seen — proving we scan
        # VISIBLE prose, not source. If extraction regressed, this page would
        # suddenly fail; pin it explicitly.
        visible = P.extract_visible_text(_html("green-northstar.html"))
        self.assertNotIn("98%", visible)
        self.assertNotIn("guaranteed", visible.lower())


# --------------------------------------------------------------------------- #
# Visible-text extraction.
# --------------------------------------------------------------------------- #
class Extraction(unittest.TestCase):
    def test_drops_script_and_style_bodies(self):
        src = ("<style>.a{width:100%}</style><p>Real text.</p>"
               "<script>var x='92% fake';</script>")
        vis = P.extract_visible_text(src)
        self.assertIn("Real text.", vis)
        self.assertNotIn("92% fake", vis)
        self.assertNotIn("width:100%", vis)

    def test_unescapes_entities(self):
        vis = P.extract_visible_text("<p>Maya &amp; clients &mdash; here.</p>")
        self.assertIn("Maya & clients", vis)

    def test_block_tags_force_segment_breaks(self):
        # Two adjacent paragraphs must not fuse into one sentence-spanning unit.
        src = "<p>Out-of-network private psychotherapy</p><p>92% fabricated</p>"
        units = P.segment_units(P.extract_visible_text(src))
        self.assertIn("Out-of-network private psychotherapy", units)
        self.assertIn("92% fabricated", units)
        self.assertFalse(
            any("psychotherapy" in u and "fabricated" in u for u in units),
            "block boundary must split adjacent paragraphs",
        )

    def test_captures_claim_bearing_attributes(self):
        # A fabrication hidden in img@alt is still visible-ish and must surface.
        src = '<img alt="Winner of the 2024 national therapy award" />'
        vis = P.extract_visible_text(src)
        self.assertIn("Winner of the 2024 national therapy award", vis)

    def test_inline_tags_stay_joined(self):
        src = "<p>Therapy for the <span>overextended.</span></p>"
        units = P.segment_units(P.extract_visible_text(src))
        self.assertIn("Therapy for the overextended.", units)


# --------------------------------------------------------------------------- #
# Approved corpus + coverage scoring.
# --------------------------------------------------------------------------- #
class Corpus(unittest.TestCase):
    def setUp(self):
        self.corpus = P.build_corpus(PRACTICE, GENERATED)

    def test_corpus_has_sources(self):
        self.assertGreater(self.corpus.source_count, 50)

    def test_real_approved_sentence_fully_covered(self):
        unit = ("Evidence-based work for adults, graduate students, and "
                "healthcare workers.")
        self.assertGreaterEqual(self.corpus.coverage(P.content_tokens(unit)),
                                P.DEFAULT_COVERAGE_THRESHOLD)

    def test_fabricated_sentence_under_threshold(self):
        for fab in (
            "92% of clients improve within six weeks.",
            "Voted the number-one practice in the Rocky Mountain region.",
            "Our patented protocol eliminates anxiety permanently.",
        ):
            with self.subTest(fab=fab):
                self.assertLess(self.corpus.coverage(P.content_tokens(fab)),
                                P.DEFAULT_COVERAGE_THRESHOLD)

    def test_coverage_uses_strongest_single_source(self):
        # A unit must match ONE approved string, not scavenge a word each from
        # many. Tokens drawn from three unrelated approved strings should NOT add
        # up to coverage of a sentence none of them contains.
        corpus = P.ApprovedCorpus(
            token_values=["burnout anxiety perfectionism", "Colorado", "$175"],
            block_texts=[],
        )
        # "burnout in Colorado costs $175 per cure" — words exist across sources
        # but no single source covers the claim.
        cov = corpus.coverage(P.content_tokens("burnout in Colorado costs cure"))
        self.assertLess(cov, P.DEFAULT_COVERAGE_THRESHOLD)

    def test_empty_unit_is_trivially_covered(self):
        self.assertEqual(self.corpus.coverage([]), 1.0)

    def test_block_tokens_resolved_into_corpus(self):
        # hero_sub ships "{{practice_model}} private psychotherapy with
        # {{owner_name}}..." — resolving tokens must put "Maya"/"Restrepo" into
        # the corpus so the rendered hero sentence is sourceable.
        self.assertTrue(self.corpus.all_tokens_known(["maya", "restrepo"]))


# --------------------------------------------------------------------------- #
# Recombination secondary path — honest glue of approved tokens passes; a
# fabrication that imports new words still fails through it.
# --------------------------------------------------------------------------- #
class RecombinationPath(unittest.TestCase):
    def setUp(self):
        self.corpus = P.build_corpus(PRACTICE, GENERATED)

    def test_static_masthead_recombination_accepted(self):
        # These are the real static-shell lines the fill engine emits (SPA
        # <title>, masthead, footer ©). Every token is approved; they glue names
        # with generic connectors and must NOT be flagged.
        for line in (
            "<title>Maya Restrepo, LPC — Private Psychotherapy · Colorado</title>",
            "<header><p>North Star Counseling — Home</p></header>",
            "<footer><p>© 2026 North Star Counseling</p></footer>",
        ):
            with self.subTest(line=line):
                self.assertEqual(P.check_html(line, self.corpus), [])

    def test_fabrication_with_new_words_still_fails_through_recombination(self):
        # The recombination escape hatch must NOT launder a fabrication: each
        # of these imports a token absent from the approved set, so it is still
        # flagged unsourced.
        for line in (
            "<p>Maya completely changed my life and saved my marriage.</p>",
            "<p>Winner of the 2024 national therapy excellence award.</p>",
            "<p>Maya is a Harvard-trained psychiatrist with a doctoral degree.</p>",
        ):
            with self.subTest(line=line):
                offenders = P.check_html(line, self.corpus)
                self.assertTrue(
                    any(o.kind == P.Offender.KIND_UNSOURCED for o in offenders),
                    f"{line!r} imports non-approved words and must be flagged",
                )

    @unittest.expectedFailure
    def test_DOCUMENTED_MISS_recombination_of_approved_tokens(self):
        # TRUTH-IN-ADVERTISING: v1 is coverage-based, not entailment-based. A
        # false claim assembled from ONLY approved tokens (no imported word) is
        # NOT caught — every token of "Maya Restrepo sees the most clients in
        # Colorado" is approved, so the recombination path accepts a sentence the
        # practice never approved. This test is an EXPECTED FAILURE: it asserts
        # the (desirable) v2 behavior and documents that v1 does not yet meet it.
        # When v2 entailment lands, flip this to a normal assertion.
        false_recombo = ("<p>Maya Restrepo sees the most clients in "
                         "Colorado.</p>")
        offenders = P.check_html(false_recombo, self.corpus)
        self.assertTrue(
            offenders,
            "v2 (entailment) should reject a false whole built from approved "
            "fragments; v1 (coverage) does not — this is the known gap",
        )

    def test_real_pipeline_index_html_is_clean(self):
        # Brutal anti-false-positive check: build a REAL northstar site through
        # the actual generate->fill pipeline and gate its static index.html. An
        # honest, engine-produced page must pass with zero offenders, or the gate
        # is unusable in practice.
        import tempfile
        import generate as G
        import fill as F
        blocks = json.loads(
            (ROOT / "engine" / "template_blocks.json").read_text(encoding="utf-8"))
        result = G.generate(PRACTICE, blocks)
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            gen_path = td / "generated.json"
            gen_path.write_text(json.dumps(result), encoding="utf-8")
            site = td / "site"
            rc = F.run(
                ROOT / "templates" / "private-practice",
                PRACTICE_PATH, gen_path, site, lenient=False,
            )
            self.assertEqual(rc, 0)
            index_html = (site / "index.html").read_text(encoding="utf-8")
        offenders = P.gate(index_html, PRACTICE, GENERATED)
        self.assertEqual(
            offenders, [],
            "the real pipeline-built index.html must be provenance-clean; "
            f"false positives: {[(o.kind, o.text) for o in offenders]!r}",
        )


# --------------------------------------------------------------------------- #
# Allowlist — generic boilerplate is honest and must pass.
# --------------------------------------------------------------------------- #
class Allowlist(unittest.TestCase):
    def setUp(self):
        self.corpus = P.build_corpus(PRACTICE, GENERATED)

    def test_nav_and_form_labels_pass(self):
        page = ("<nav><a>Home</a><a>About</a><a>Contact</a></nav>"
                "<form><label>Your name</label><label>Your email</label>"
                "<button>Send message</button></form>")
        self.assertEqual(P.check_html(page, self.corpus), [])

    def test_crisis_line_always_allowed(self):
        # A 988/741741 crisis line must NEVER be flagged — refusing it would be
        # the opposite of safe — even though it is generic, not practice-specific.
        page = ("<footer><p>988 Suicide &amp; Crisis Lifeline — Call or text "
                "988. Text HOME to 741741.</p></footer>")
        self.assertEqual(P.check_html(page, self.corpus), [])

    def test_ai_disclosure_allowed(self):
        page = ("<p>Created with AI assistance from Shaula. Reviewed and "
                "approved by Maya Restrepo, LPC before publication.</p>")
        self.assertEqual(P.check_html(page, self.corpus), [])


# --------------------------------------------------------------------------- #
# Banned-language gate is REUSED (not reinvented).
# --------------------------------------------------------------------------- #
class BannedReuse(unittest.TestCase):
    def setUp(self):
        self.corpus = P.build_corpus(PRACTICE, GENERATED)

    def test_banned_phrase_flagged_even_if_words_are_approved(self):
        # "proven" trips banned.lint independently of coverage. Build a sentence
        # whose other words ARE approved so coverage might pass — banned must
        # still fire, proving the two gates are independent.
        page = "<p>Our evidence-based work for adults is clinically proven.</p>"
        offenders = P.check_html(page, self.corpus)
        self.assertTrue(any(o.kind == P.Offender.KIND_BANNED for o in offenders))

    def test_negated_disclaimer_not_flagged_as_banned(self):
        # banned.lint is negation-aware; a disclaimer that shares a banned word
        # ("not a guarantee") must not be reported as a banned claim. (It may
        # still be unsourced, so check the BANNED kind specifically.)
        page = "<p>This is not a guarantee of any particular outcome.</p>"
        banned_offenders = [o for o in P.check_html(page, self.corpus)
                            if o.kind == P.Offender.KIND_BANNED]
        self.assertEqual(banned_offenders, [])

    def test_uses_canonical_banned_module(self):
        import banned
        self.assertIs(P.banned, banned)


# --------------------------------------------------------------------------- #
# Normalization details that make coverage robust.
# --------------------------------------------------------------------------- #
class Normalization(unittest.TestCase):
    def test_curly_quotes_and_dashes_fold(self):
        a = P.normalize("It’s evidence–based — here.")
        self.assertIn("it's evidence based", a)

    def test_placeholders_dropped_from_content_tokens(self):
        toks = P.content_tokens("{{owner_name}} private psychotherapy")
        self.assertNotIn("owner_name", toks)
        self.assertIn("psychotherapy", toks)

    def test_stopwords_dropped(self):
        toks = P.content_tokens("the work is for the people")
        self.assertNotIn("the", toks)
        self.assertIn("work", toks)
        self.assertIn("people", toks)


# --------------------------------------------------------------------------- #
# CLI exit-code contract (prove.sh-style end-to-end).
# --------------------------------------------------------------------------- #
class Cli(unittest.TestCase):
    def _run(self, html_name):
        return subprocess.run(
            [sys.executable, str(ROOT / "engine" / "provenance.py"),
             "--html", str(FIX / html_name),
             "--practice", str(PRACTICE_PATH),
             "--generated", str(GENERATED_PATH)],
            capture_output=True, text=True,
        )

    def test_cli_green_exits_zero(self):
        res = self._run("green-northstar.html")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("PASS", res.stdout)

    def test_cli_red_exits_nonzero_and_lists_offenders(self):
        for name in ("red-fake-stat.html", "red-fake-testimonial.html",
                     "red-fake-credential.html"):
            with self.subTest(fixture=name):
                res = self._run(name)
                self.assertEqual(res.returncode, 1)
                self.assertIn("FAIL", res.stdout)
                self.assertIn("REJECTED", res.stderr)

    def test_cli_json_mode(self):
        res = subprocess.run(
            [sys.executable, str(ROOT / "engine" / "provenance.py"),
             "--html", str(FIX / "red-fake-stat.html"),
             "--practice", str(PRACTICE_PATH),
             "--generated", str(GENERATED_PATH), "--json"],
            capture_output=True, text=True,
        )
        self.assertEqual(res.returncode, 1)
        payload = json.loads(res.stdout)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["offenders"])

    def test_cli_missing_html_is_usage_error(self):
        res = subprocess.run(
            [sys.executable, str(ROOT / "engine" / "provenance.py"),
             "--html", str(FIX / "does-not-exist.html"),
             "--practice", str(PRACTICE_PATH),
             "--generated", str(GENERATED_PATH)],
            capture_output=True, text=True,
        )
        self.assertEqual(res.returncode, 2)


if __name__ == "__main__":
    unittest.main()
