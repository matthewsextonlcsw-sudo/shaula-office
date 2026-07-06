"""Unit tests for engine/geo.py — the deterministic GEO/SEO finishing pass.

Covers: JSON-LD shape (MedicalBusiness + founder Person + credential), the factual FAQPage,
llms.txt, idempotent injection, and the hard honesty gate. No network, no LLM — pure + fast.
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import geo  # noqa: E402

PRACTICE = {
    "owner_name": "Maya Restrepo",
    "credential": "LPC",
    "credential_full": "Licensed Professional Counselor",
    "business_name": "North Star Counseling",
    "tagline": "Therapy for the overextended.",
    "specialties": "burnout, anxiety, perfectionism",
    "location": "Denver, CO",
    "service_areas": "Colorado",
    "session_fee": "$175",
    "session_length": "50-minute",
    "payment_model": "Out-of-network, no insurance billed",
    "sliding_scale_policy": "A few reduced-fee slots open each year.",
    "consult_length": "20-minute",
    "availability_status": "Now welcoming new clients",
    "phone": "303-555-0166",
    "email": "hello@northstarcounseling.com",
    "education": "MA, University of Denver, 2014",
    "address_line1": "",
}

INDEX_HTML = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
              '<title>Maya Restrepo, LPC — Colorado</title>'
              '<meta name="description" content="Private therapy in Denver." /></head>'
              '<body><h1>hi</h1></body></html>')


class TestJsonLd(unittest.TestCase):
    def test_shape(self):
        d = geo.build_jsonld(PRACTICE, site_url="https://x.example")
        self.assertEqual(d["@type"], ["MedicalBusiness", "ProfessionalService"])
        self.assertEqual(d["name"], "North Star Counseling")
        self.assertEqual(d["founder"]["@type"], "Person")
        self.assertEqual(d["founder"]["jobTitle"], "Licensed Professional Counselor")
        self.assertEqual(d["founder"]["hasCredential"]["credentialCategory"], "license")
        self.assertIn("burnout", d["knowsAbout"])
        self.assertEqual(d["priceRange"], "$175")
        self.assertEqual(d["address"]["addressLocality"], "Denver")
        self.assertEqual(d["address"]["addressRegion"], "CO")

    def test_no_banned_phrases(self):
        d = geo.build_jsonld(PRACTICE)
        self.assertFalse(geo._BANNED.search(json.dumps(d)))

    def test_no_fake_street(self):
        # address_line1 empty -> no streetAddress fabricated
        d = geo.build_jsonld(PRACTICE)
        self.assertNotIn("streetAddress", d.get("address", {}))


class TestFaqPage(unittest.TestCase):
    def test_factual_questions(self):
        faq = geo.build_faqpage(PRACTICE)
        self.assertEqual(faq["@type"], "FAQPage")
        self.assertGreaterEqual(len(faq["mainEntity"]), 4)
        for qa in faq["mainEntity"]:
            self.assertEqual(qa["@type"], "Question")
            self.assertTrue(qa["acceptedAnswer"]["text"].strip())
        joined = json.dumps(faq)
        self.assertIn("Out-of-network", joined)   # answer is the REAL payment model
        self.assertFalse(geo._BANNED.search(joined))

    def test_none_when_no_data(self):
        self.assertIsNone(geo.build_faqpage({"business_name": "X"}))


class TestLlmsTxt(unittest.TestCase):
    def test_content(self):
        t = geo.build_llms_txt(PRACTICE)
        self.assertIn("North Star Counseling", t)
        self.assertIn("988", t)                    # crisis note present
        self.assertIn("not a crisis service", t)
        self.assertFalse(geo._BANNED.search(t))


class TestInject(unittest.TestCase):
    def _site(self) -> Path:
        import tempfile
        d = Path(tempfile.mkdtemp())
        (d / "index.html").write_text(INDEX_HTML, encoding="utf-8")
        return d

    def test_injects_and_is_idempotent(self):
        site = self._site()
        r1 = geo.inject(site, PRACTICE, "https://x.example")
        self.assertTrue(r1["injected"])
        html1 = (site / "index.html").read_text()
        n1 = len(re.findall(r'<script type="application/ld\+json">', html1))
        self.assertEqual(n1, 2)                    # MedicalBusiness + FAQPage
        self.assertTrue((site / "llms.txt").exists())
        # second run must REPLACE, not duplicate
        geo.inject(site, PRACTICE, "https://x.example")
        html2 = (site / "index.html").read_text()
        n2 = len(re.findall(r'<script type="application/ld\+json">', html2))
        self.assertEqual(n2, 2)
        # all JSON-LD still valid JSON
        for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html2, re.S):
            json.loads(b)

    def test_honesty_gate_blocks_banned(self):
        site = self._site()
        tainted = {**PRACTICE, "business_name": "The Best Proven Therapy"}
        with self.assertRaises(SystemExit):
            geo.inject(site, tainted, "https://x.example")


if __name__ == "__main__":
    unittest.main()
