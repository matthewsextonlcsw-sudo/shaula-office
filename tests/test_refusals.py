"""Stream-1 contract: structured refusal output (concierge-beta deliverable C).

The engine already ENFORCES omit-not-fabricate + banned-language abort; these
tests pin that it now also EMITS a machine-readable record of what it refused:

  * ``citations.resolve_modalities_detail`` reports listed + resolved + dropped,
    and ``resolve_modalities`` stays byte-identical (it delegates to it);
  * ``generate.refusals_manifest`` summarizes the refusal taxonomy and only
    attests ``lint_clean`` when the caller vouches for it;
  * ``generate()`` attaches a ``_refusals`` manifest AFTER the lint gate without
    disturbing the ``blocks`` payload ``fill.py`` consumes.

Stdlib only (unittest), so prove.sh runs it with no new dependency. NO PHI —
synthetic fixture + literal modality names only.
"""
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "engine"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import build_practice as BP  # noqa: E402
import citations as C  # noqa: E402
import generate as G  # noqa: E402

BLOCKS = json.loads((ROOT / "engine" / "template_blocks.json").read_text(encoding="utf-8"))
SURVEY = json.loads(
    (ROOT / "fixtures" / "northstar-denver" / "survey.json").read_text(encoding="utf-8")
)


class ResolveDetail(unittest.TestCase):
    def test_reports_resolved_dropped_and_listed(self):
        d = C.resolve_modalities_detail("CBT, Reiki, ACT, Astrology Therapy")
        self.assertEqual([m["tag"] for m in d["resolved"]], ["CBT", "ACT"])
        self.assertEqual(d["dropped"], ["Reiki", "Astrology Therapy"])
        self.assertEqual(d["listed"], ["CBT", "Reiki", "ACT", "Astrology Therapy"])

    def test_dedup_is_not_a_refusal(self):
        d = C.resolve_modalities_detail("CBT, cbt, EMDR")
        self.assertEqual([m["tag"] for m in d["resolved"]], ["CBT", "EMDR"])
        self.assertEqual(d["dropped"], [])  # the duplicate cbt is collapsed, not dropped

    def test_resolve_modalities_byte_identical_via_delegation(self):
        # The exact assertion citations.py's own self-test makes — proving the
        # refactor to delegate did not change resolve_modalities' output.
        got = [m["tag"] for m in C.resolve_modalities("CBT, cbt, EMDR, Reiki, Gottman Method")]
        self.assertEqual(got, ["CBT", "EMDR", "Gottman"])

    def test_list_input_supported(self):
        d = C.resolve_modalities_detail(["EMDR", "made up thing"])
        self.assertEqual([m["tag"] for m in d["resolved"]], ["EMDR"])
        self.assertEqual(d["dropped"], ["made up thing"])

    def test_empty_input_is_all_empty(self):
        d = C.resolve_modalities_detail("")
        self.assertEqual(d, {"listed": [], "resolved": [], "dropped": []})


class Manifest(unittest.TestCase):
    def test_standalone_defaults_to_not_attested(self):
        # A caller that has not run the lint gate must NOT get a lint-clean claim.
        m = G.refusals_manifest({"modalities": "CBT"})
        self.assertFalse(m["lint_clean"])

    def test_dropped_unknown_recorded(self):
        m = G.refusals_manifest({"modalities": "CBT, Reiki, ACT"}, lint_clean=True)
        self.assertEqual(m["modalities_dropped_unknown"], ["Reiki"])
        self.assertIn("Cognitive Behavioral Therapy", m["modalities_shown"])
        self.assertTrue(m["lint_clean"])

    def test_caps_shown_at_four(self):
        m = G.refusals_manifest({"modalities": "CBT, ACT, EMDR, DBT, IFS, SE"})
        self.assertEqual(len(m["modalities_shown"]), 4)
        # IFS + SE resolve to real citations but fall beyond the 4-card display cap.
        self.assertEqual(len(m["modalities_capped"]), 2)
        self.assertEqual(m["modalities_dropped_unknown"], [])

    def test_no_invented_signature_method(self):
        m = G.refusals_manifest({"modalities": "CBT"})
        self.assertEqual(m["method"], "generic-evidence-informed-floor")

    def test_banned_language_patterns_are_exposed(self):
        m = G.refusals_manifest({"modalities": "CBT"})
        # The receipt names the standing policy; it must match the live linter.
        self.assertEqual(m["banned_language_enforced"], list(G._BANNED))


class GenerateAttachesRefusals(unittest.TestCase):
    def test_generate_emits_refusals_after_lint_gate(self):
        practice = BP.build_practice(SURVEY)
        result = G.generate(practice, BLOCKS)
        self.assertIn("_refusals", result)
        ref = result["_refusals"]
        self.assertTrue(ref["lint_clean"])
        # northstar lists "CBT, ACT, mindfulness-based"; the catalog carries MBCT
        # and MBSR but not a bare "mindfulness-based", so it is honestly dropped.
        self.assertIn("mindfulness-based", ref["modalities_dropped_unknown"])
        self.assertEqual(
            ref["modalities_shown"][:2],
            ["Cognitive Behavioral Therapy", "Acceptance & Commitment Therapy"],
        )

    def test_blocks_payload_untouched_by_manifest(self):
        practice = BP.build_practice(SURVEY)
        result = G.generate(practice, BLOCKS)
        # fill.py consumes ONLY ["blocks"]; the manifest must never leak into it.
        self.assertIn("blocks", result)
        self.assertNotIn("_refusals", result["blocks"])
        self.assertNotIn("_refusals", result["blocks"].keys())


if __name__ == "__main__":
    unittest.main()
