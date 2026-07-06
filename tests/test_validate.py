"""Survey pre-flight validator contract (concierge-beta deliverable A, operator step 2).

The validator predicts a build outcome WITHOUT building, by reusing the engine's
own contracts. These tests pin that it agrees with what the build would actually
do — it catches exactly the three failure modes the build enforces (missing
required field → ValueError; banned input → HonestyError; zero resolvable modality
→ SystemExit abort) and previews the defaults the build would flag.

Stdlib only (unittest). NO PHI — synthetic literals only.
"""
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "engine", ROOT / "svc", ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import validate_survey as V  # noqa: E402

SURVEY = json.loads(
    (ROOT / "fixtures" / "northstar-denver" / "survey.json").read_text(encoding="utf-8")
)


class CleanSurvey(unittest.TestCase):
    def test_full_fixture_is_ready(self):
        v = V.validate(SURVEY)
        self.assertTrue(v["ok"])
        self.assertEqual(v["missing_required"], [])
        self.assertEqual(v["banned_input"], [])
        self.assertFalse(v["zero_modality_abort"])
        # northstar resolves CBT + ACT, drops the bare "mindfulness-based".
        self.assertEqual([m["tag"] for m in v["modalities"]["resolved"]], ["CBT", "ACT"])
        self.assertIn("mindfulness-based", v["modalities"]["dropped"])
        # It still previews the defaults the build would flag (not errors).
        self.assertTrue(v["assumed"])

    def test_report_says_ready(self):
        report = V.format_report("x", V.validate(SURVEY))
        self.assertIn("all 17 required fields present", report)
        self.assertIn("READY to build", report)
        self.assertNotIn("NOT READY", report)


class MissingRequired(unittest.TestCase):
    def test_missing_field_is_not_ready(self):
        survey = {k: val for k, val in SURVEY.items() if k != "license_year"}
        v = V.validate(survey)
        self.assertFalse(v["ok"])
        self.assertIn("license_year", v["missing_required"])


class BannedInput(unittest.TestCase):
    def test_banned_tagline_is_caught_with_plain_reasons(self):
        survey = dict(SURVEY, tagline="Clinically proven, the #1 best therapist in town")
        v = V.validate(survey)
        self.assertFalse(v["ok"])
        self.assertTrue(v["banned_input"])
        hit = v["banned_input"][0]
        self.assertEqual(hit["field"], "tagline")
        # Reasons are plain English (from svc/honesty), not raw regex.
        joined = " ".join(hit["reasons"])
        self.assertIn("efficacy claim", joined)
        for raw in (r"\b", "#1\\b"):
            self.assertNotIn(raw, joined)


class ZeroModalityAbort(unittest.TestCase):
    def test_all_unknown_modalities_predicts_abort(self):
        survey = dict(SURVEY, modalities="Reiki, Astrology Therapy")
        v = V.validate(survey)
        self.assertFalse(v["ok"])
        self.assertTrue(v["zero_modality_abort"])
        self.assertIn("would ABORT", V.format_report("x", v))


if __name__ == "__main__":
    unittest.main()
