"""Engine-side contracts for UX-audit wave 3 (SH-F4 / SH-F5 / SH-F6 / SH-F8 / SH-F9).

Pins:
  * the 9-Q intake contract — INTAKE_CORE, key aliasing, honest derivation,
    missing_for_website (single source of truth shared with the svc);
  * the assumption record — commitment defaults are FLAGGED, the old
    fabricated business facts are gone;
  * deterministic personalization — two practices, two different homepages;
  * the GEO pass ships on the pipeline path (not just prove.sh's rail);
  * the mobile nav exists in the template and in every built site.

All data synthetic — no PHI. No network, no LLM.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "engine") not in sys.path:
    sys.path.insert(0, str(ROOT / "engine"))

import build_practice as BP  # noqa: E402
import generate as G  # noqa: E402
import pipeline  # noqa: E402

SURVEY = json.loads(
    (ROOT / "fixtures" / "northstar-denver" / "survey.json").read_text(encoding="utf-8")
)

# Exactly what the apps' 9-question unboxing collects (web/src/lib/shaula.ts
# INTAKE_QUESTIONS in both apps key off this engine contract).
NINE_Q = {
    "owner_name": "Iris Calder",
    "credential": "LCSW",
    "business_name": "Calder Counseling",
    "tagline": "Therapy that respects your time.",
    "specialties": "anxiety, life transitions",
    "populations": "adults, new parents",
    "modalities": "CBT, ACT",
    "location": "Portland, OR",
    "fee": "$160",
}


# ── SH-F9: the intake contract ───────────────────────────────────────────────

def test_intake_core_matches_the_nine_questions():
    assert set(BP.INTAKE_CORE) == set(NINE_Q)


def test_derive_survey_aliases_and_derives_honestly():
    derived, assumptions = BP.derive_survey(NINE_Q)
    # fee -> session_fee is the therapist's own answer, never an assumption.
    assert derived["session_fee"] == "$160"
    assert all(a["field"] != "session_fee" for a in assumptions)
    # Location-driven derivations, each marked.
    assert derived["service_areas"] == "Oregon"
    assert derived["license_state"] == "OR"
    # Defaults that read as commitments are marked too.
    assert derived["payment_model_type"] == "out-of-network"
    assert derived["session_length"] == "50-minute"
    marked = {a["field"] for a in assumptions}
    assert marked == {"service_areas", "license_state", "payment_model_type", "session_length"}
    assert all(a["label"] and a["value"] for a in assumptions)


def test_derive_survey_never_invents_identity_facts():
    derived, _ = BP.derive_survey(NINE_Q)
    for field in ("phone", "email", "education", "founded_date",
                  "license_number", "license_year"):
        assert not derived.get(field), field


def test_missing_for_website_is_the_exact_gap():
    assert BP.missing_for_website(NINE_Q) == [
        "phone", "email", "education", "founded_date",
        "license_number", "license_year",
    ]
    # The full fixture survey is ready — nothing missing.
    assert BP.missing_for_website(SURVEY) == []


def test_survey_readiness_previews_build_assumptions():
    readiness = BP.survey_readiness(SURVEY)
    assert readiness["missing"] == []
    fields = {a["field"] for a in readiness["assumed"]}
    # northstar supplies none of the commitment fields -> all defaulted+flagged.
    assert {"sliding_scale_policy", "availability_status", "consult_length",
            "response_time", "cancellation_policy", "pull_quote"} <= fields


# ── SH-F4: inventions are flagged; the worst fabrications are gone ──────────

def test_build_practice_records_assumptions():
    practice = BP.build_practice(SURVEY)
    assumed = {a["field"]: a for a in practice["_assumed"]}
    assert "sliding_scale_policy" in assumed
    assert assumed["availability_status"]["value"] == BP.DEFAULT_AVAILABILITY
    # Supplying a field removes its flag.
    supplied = dict(SURVEY, cancellation_policy="48-hour notice, no fee")
    practice2 = BP.build_practice(supplied)
    assert all(a["field"] != "cancellation_policy" for a in practice2["_assumed"])
    assert practice2["cancellation_policy"] == "48-hour notice, no fee"


def test_fabricated_business_facts_are_replaced_with_honest_copy():
    practice = BP.build_practice(SURVEY)
    # The old defaults invented a reduced-fee program and an open caseload.
    assert "reserved each year" not in practice["sliding_scale_policy"]
    assert practice["sliding_scale_policy"] == BP.DEFAULT_SLIDING_SCALE
    assert practice["availability_status"] == BP.DEFAULT_AVAILABILITY
    assert "welcoming new clients" not in practice["availability_status"].lower()


# ── SH-F5: deterministic personalization from the unboxing answers ──────────

def test_two_practices_two_homepages():
    blocks = json.loads((ROOT / "engine" / "template_blocks.json").read_text())
    p1 = BP.build_practice(SURVEY)
    p2 = BP.build_practice(dict(
        SURVEY,
        business_name="Calder Counseling",
        tagline="Therapy that respects your time.",
        populations="new parents, couples",
    ))
    g1 = G.generate(p1, blocks)["blocks"]
    g2 = G.generate(p2, blocks)["blocks"]
    assert g1["hero_headline"]["replace"] != g2["hero_headline"]["replace"]
    assert g1["hero_sub"]["replace"] != g2["hero_sub"]["replace"]
    # The therapist's OWN tagline is the headline (accented tail).
    assert "Therapy for the" in g1["hero_headline"]["replace"]
    assert 'class="accent"' in g1["hero_headline"]["replace"]
    # The populations answer names the audience.
    assert "graduate students" in g1["hero_sub"]["replace"]
    assert "new parents" in g2["hero_sub"]["replace"]


def test_pull_quote_is_the_therapists_own_line_when_supplied():
    blocks = json.loads((ROOT / "engine" / "template_blocks.json").read_text())
    own = dict(SURVEY, pull_quote="Slow is smooth, and smooth is honest work.")
    g = G.generate(BP.build_practice(own), blocks)["blocks"]
    assert "Slow is smooth" in g["pull_quote"]["replace"]
    # No pull_quote -> the floor quote ships AND is flagged for confirmation.
    practice = BP.build_practice(SURVEY)
    g2 = G.generate(practice, blocks)["blocks"]
    assert G.FLOOR_PULL_QUOTE[:30] in g2["pull_quote"]["replace"]
    assert any(a["field"] == "pull_quote" for a in practice["_assumed"])


def test_no_tagline_falls_back_to_the_floor_headline():
    blocks = json.loads((ROOT / "engine" / "template_blocks.json").read_text())
    no_tag = {k: v for k, v in SURVEY.items() if k != "tagline"}
    g = G.generate(BP.build_practice(no_tag), blocks)["blocks"]
    assert g["hero_headline"]["replace"] == blocks["blocks"]["hero_headline"]["find"]


# ── SH-F6 + SH-F8: every pipeline build ships GEO + a mobile nav ─────────────

@pytest.fixture(scope="module")
def built_site():
    with tempfile.TemporaryDirectory(prefix="shaula-contract-") as td:
        built = pipeline.build_site(
            SURVEY, sites_dir=pathlib.Path(td), slug="contract-check",
            site_url="https://example.test/contract-check",
        )
        site = pathlib.Path(built["dir"])
        yield {
            "index": (site / "index.html").read_text(encoding="utf-8"),
            "app_js": (site / "app.js").read_text(encoding="utf-8"),
            "css": (site / "styles.css").read_text(encoding="utf-8"),
            "llms": (site / "llms.txt").read_text(encoding="utf-8"),
        }


def test_pipeline_build_ships_geo(built_site):
    index = built_site["index"]
    assert "shaula-geo:start" in index
    assert "MedicalBusiness" in index and "FAQPage" in index
    assert 'property="og:title"' in index
    assert '"url": "https://example.test/contract-check"' in index
    # llms.txt exists and lists only routes that actually exist (hash SPA).
    llms = built_site["llms"]
    assert "/#about" in llms and "/#fees" in llms
    assert "- /services" not in llms
    assert "988" in llms


def test_built_site_has_a_mobile_nav(built_site):
    index = built_site["index"]
    assert 'class="nav-toggle"' in index
    assert 'aria-expanded="false"' in index and 'aria-controls="navLinks"' in index
    css = built_site["css"]
    assert ".nav-toggle{ display:inline-flex; }" in css
    assert ".nav-open .nav-links{ display:flex; }" in css
    app_js = built_site["app_js"]
    assert "function setNavOpen" in app_js
    assert "setNavOpen(false); // picking a destination closes the mobile menu" in app_js
