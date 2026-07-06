"""Operator build wrapper contract (concierge-beta deliverable B).

`scripts/concierge_build.py` is the single by-hand command the concierge operator
runs per therapist: validate → build → honesty receipt, then PRINT (never run) the
gated publish step. These tests pin that contract:

  * a clean survey produces a real site + a receipt written OUTSIDE the served tree;
  * a bad survey is stopped at pre-flight with NOTHING built (no half-built site);
  * the publish hint is a gated pointer, not an executed deploy.

Everything runs in a temp dir — no repo `sites/` or `receipts/` is touched. Stdlib
unittest only, deterministic date, NO PHI (synthetic northstar fixture).
"""
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "engine", ROOT / "svc", ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import concierge_build as CB  # noqa: E402

SURVEY = json.loads(
    (ROOT / "fixtures" / "northstar-denver" / "survey.json").read_text(encoding="utf-8")
)


class BuildsCleanFixture(unittest.TestCase):
    def test_clean_survey_builds_site_and_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            result = CB.run(
                SURVEY,
                sites_dir=tmp / "sites",
                receipts_dir=tmp / "receipts",
                generated_on="2026-06-15",
            )
            # A real, hostable site landed under the temp sites dir.
            site_dir = pathlib.Path(result["dir"])
            self.assertTrue((site_dir / "index.html").is_file())
            self.assertTrue((site_dir / "app.js").is_file())
            self.assertEqual(site_dir.name, result["slug"])
            # The receipt is generated and names the shown modalities + the header.
            receipt = pathlib.Path(result["receipt_path"])
            self.assertTrue(receipt.is_file())
            md = receipt.read_text(encoding="utf-8")
            self.assertIn("honesty receipt", md.lower())
            self.assertIn("Cognitive Behavioral Therapy", md)
            # northstar drops the bare "mindfulness-based" (omit-not-fabricate).
            self.assertEqual(result["modalities_dropped"], ["mindfulness-based"])
            self.assertTrue(result["validation"]["ok"])

    def test_receipt_is_written_outside_the_served_site(self):
        # Design invariant: the published site stays exactly the site; the receipt
        # is the operator's out-of-band trust artifact, never a public page.
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            result = CB.run(
                SURVEY,
                sites_dir=tmp / "sites",
                receipts_dir=tmp / "receipts",
                generated_on="2026-06-15",
            )
            receipt = pathlib.Path(result["receipt_path"]).resolve()
            site_dir = pathlib.Path(result["dir"]).resolve()
            self.assertNotIn(site_dir, receipt.parents)


class BlocksBadSurvey(unittest.TestCase):
    def test_missing_required_blocks_with_nothing_built(self):
        survey = {k: v for k, v in SURVEY.items() if k != "license_year"}
        with tempfile.TemporaryDirectory() as td:
            sites = pathlib.Path(td) / "sites"
            with self.assertRaises(CB.BuildBlocked) as ctx:
                CB.run(survey, sites_dir=sites, receipts_dir=pathlib.Path(td) / "receipts")
            self.assertIn("license_year", ctx.exception.validation["missing_required"])
            # Nothing was built — pre-flight stopped before build_site ran.
            self.assertFalse(sites.exists() and any(sites.iterdir()))

    def test_banned_input_blocks_at_preflight(self):
        survey = dict(SURVEY, tagline="Clinically proven, the #1 best therapist in town")
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(CB.BuildBlocked) as ctx:
                CB.run(survey, sites_dir=pathlib.Path(td) / "sites",
                       receipts_dir=pathlib.Path(td) / "receipts")
            self.assertTrue(ctx.exception.validation["banned_input"])


class PublishHint(unittest.TestCase):
    def test_publish_commands_are_gated_pointers_not_a_deploy(self):
        txt = CB.publish_commands("demo-slug")
        self.assertIn("mws-shaula-sites", txt)
        self.assertIn("demo-slug", txt)
        self.assertIn("WEBSITE_PUBLISH_RUNBOOK.md", txt)
        self.assertIn("gated", txt.lower())


if __name__ == "__main__":
    unittest.main()
