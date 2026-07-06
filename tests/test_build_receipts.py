"""Build-time trust receipts (svc/receipts.py) + the corpus-completion that lets
the claim-provenance gate run HONESTLY over a rendered template SPA.

a1 — honesty_receipt: generated from the build's OWN refusals manifest + the
     _assumed record (never re-linted) — "what Shaula refused to say / held back /
     assumed", surfaced on the approval card.
a2 — provenance_receipt: the built SPA is rendered headless (engine/render_dump.mjs)
     and every visible claim is proven to trace to the COMPLETE approved set
     (practice + generated + engine content banks + template static copy).
       * PASS       on an honest build,
       * FLAG       on a smuggled fabrication,
       * UNVERIFIED if it cannot render (structural gate still stands).

Also pins:
  * pipeline.build_site now returns the actual `generated` (blocks + _refusals),
    so a receipt cannot drift from a brain-enriched site; and
  * provenance.approved_template_extras is what turns the otherwise CRY-WOLF
    rendered gate honest — without it the vetted chrome + real citations flag.

unittest, no network, synthetic northstar fixture, NO PHI. Node-dependent tests
skip when node is absent.
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import pipeline, provenance  # noqa: E402
from svc import receipts  # noqa: E402

SURVEY = json.loads(
    (ROOT / "fixtures" / "northstar-denver" / "survey.json").read_text(encoding="utf-8")
)
HAS_NODE = shutil.which("node") is not None

_TMP = tempfile.mkdtemp(prefix="rcpt-test-")
BUILT = pipeline.build_site(
    SURVEY, sites_dir=pathlib.Path(_TMP) / "sites", slug="rcpt-northstar"
)


def tearDownModule():
    shutil.rmtree(_TMP, ignore_errors=True)


def _render(out_dir):
    return subprocess.run(
        ["node", str(ROOT / "engine" / "render_dump.mjs"), "--out", str(out_dir)],
        capture_output=True, text=True, timeout=60,
    )


class BuildSiteReturnsGenerated(unittest.TestCase):
    """The plumbing the receipts ride on: build_site exposes the real generate()
    output so the corpus/refusals match the published site byte-for-byte."""

    def test_generated_present_with_blocks_and_refusals(self):
        self.assertIn("generated", BUILT)
        self.assertIn("blocks", BUILT["generated"])
        self.assertIn("_refusals", BUILT["generated"])
        self.assertTrue(BUILT["generated"]["blocks"], "generated.blocks must be non-empty")

    def test_built_dir_has_app_js(self):
        self.assertTrue(pathlib.Path(BUILT["dir"], "app.js").is_file())


class HonestyReceipt(unittest.TestCase):
    def setUp(self):
        self.r = receipts.honesty_receipt(BUILT["practice"], BUILT["generated"])

    def test_kind_and_lint_clean(self):
        self.assertEqual(self.r["kind"], "honesty")
        self.assertTrue(self.r["lintClean"], "a successful build is lint-clean by construction")

    def test_refused_language_is_plain_english_not_regex(self):
        rl = self.r["refusedLanguage"]
        self.assertTrue(rl, "the banned-language policy must be surfaced")
        joined = " ".join(rl)
        self.assertNotIn("\\b", joined, "must be plain English, never raw regex")
        self.assertTrue(
            any(("percentage" in x) or ("guarantee" in x) or ("superlative" in x) for x in rl),
            f"expected human-readable policy lines; got {rl!r}",
        )

    def test_modalities_shown_nonempty(self):
        self.assertTrue(self.r["modalitiesShown"], "northstar lists real, cited modalities")

    def test_summary_and_assumed_shape(self):
        self.assertIn("Honesty receipt", self.r["summary"])
        self.assertIsInstance(self.r["assumed"], list)


class ReceiptsForBuild(unittest.TestCase):
    def test_both_receipts_keyed_for_the_run(self):
        out = receipts.receipts_for_build(BUILT)
        self.assertEqual(out["honestyReceipt"]["kind"], "honesty")
        self.assertIn("provenanceReceipt", out)  # always present (unverified if no node)
        if HAS_NODE:
            self.assertEqual(out["provenanceReceipt"]["status"], "pass")


@unittest.skipUnless(HAS_NODE, "node required to render the SPA")
class ProvenanceReceipt(unittest.TestCase):
    def test_honest_build_passes_clean(self):
        r = receipts.provenance_receipt(BUILT["dir"], BUILT["practice"], BUILT["generated"])
        self.assertEqual(r["status"], "pass", f"honest build should pass; got {r}")
        self.assertTrue(r["ok"])
        self.assertEqual(r["offenders"], [])
        self.assertIn("limitNote", r)

    def test_template_extras_are_what_make_it_honest(self):
        # Regression guard for the cry-wolf bug: gating the rendered template
        # against ONLY (practice + generated) flags its own vetted chrome and the
        # engine's real citations; completing the corpus with approved_template_extras
        # is what makes the honest render clean. The fabrication-catching power is
        # proven separately by tests/test_provenance.py (RED fixtures).
        p = _render(BUILT["dir"])
        self.assertEqual(p.returncode, 0, p.stderr)
        rendered = p.stdout
        bare = provenance.gate(rendered, BUILT["practice"], BUILT["generated"])
        self.assertTrue(bare, "without extras the vetted chrome/citations cry wolf")
        app_js = pathlib.Path(BUILT["dir"], "app.js").read_text(encoding="utf-8")
        extras = provenance.approved_template_extras(app_js)
        with_extras = provenance.gate(
            rendered, BUILT["practice"], BUILT["generated"], extra_texts=extras
        )
        self.assertEqual(with_extras, [], "complete approved set → honest render is clean")

    def test_smuggled_fabrication_flags(self):
        # Inject a fabricated stat into the vetted static chrome of a COPY of the
        # build so render_dump renders it; the receipt must FLAG (never pass).
        tdir = pathlib.Path(tempfile.mkdtemp(prefix="rcpt-tamper-"))
        self.addCleanup(shutil.rmtree, tdir, ignore_errors=True)
        dst = tdir / "site"
        shutil.copytree(BUILT["dir"], dst)
        app_js = dst / "app.js"
        src = app_js.read_text(encoding="utf-8")
        anchor = "the next move is small."
        self.assertIn(anchor, src, "stable chrome anchor must exist to tamper against")
        app_js.write_text(
            src.replace(anchor, anchor + " 92% of clients report meaningful improvement."),
            encoding="utf-8",
        )
        r = receipts.provenance_receipt(str(dst), BUILT["practice"], BUILT["generated"])
        self.assertEqual(r["status"], "flag")
        self.assertFalse(r["ok"])
        self.assertTrue(
            any("92%" in o["text"] for o in r["offenders"]),
            f"the fabricated stat must be named; got {r['offenders']!r}",
        )

    def test_missing_render_is_unverified_not_pass(self):
        # A build that cannot be rendered must NOT silently read as "clean".
        empty = pathlib.Path(tempfile.mkdtemp(prefix="rcpt-empty-"))
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        r = receipts.provenance_receipt(str(empty), BUILT["practice"], BUILT["generated"])
        self.assertEqual(r["status"], "unverified")
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main()
