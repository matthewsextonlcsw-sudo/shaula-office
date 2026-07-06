#!/usr/bin/env python3
"""test_brain — the OPTIONAL Gemini (Vertex) enrichment seam, proven WITHOUT creds.

Every test here injects a FAKE client (or none at all): no Google project, no
network, no `google-genai` call is ever made against a live endpoint. What we are
proving is the *contract*, not the model:

  1. available() is honest        — no project / no SDK  -> unavailable.
  2. a clean rewrite is accepted  — and is re-linted, so it is honest by the
                                    SAME box-wide gate the floor passes.
  3. a banned rewrite is refused  — the honesty linter fires on MODEL output and
                                    the block falls back to the deterministic floor.
  4. an empty rewrite is refused  — falls back to the floor.
  5. tokens are sacred            — the about block keeps every {{token}} verbatim
                                    or it falls back; new HTML is refused.
  6. ZERO regression              — generate(..., brain=None) is byte-identical to
                                    the floor, and a full build still renders.
  7. a real build with a fake brain renders AND is leak-free, with the model copy
     visibly present in the output (the seam actually flowed end to end).

Pure stdlib (`unittest`). Runs three ways, all green, all credential-free:
    python3 -m pytest tests/test_brain.py -q
    python3 -m unittest tests.test_brain -v
    python3 tests/test_brain.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

# The engine modules import each other by bare name (they live in engine/ and
# insert that dir on sys.path at import). Mirror that so `import brain` resolves
# its `import generate as G` the same way the box does.
_REPO = pathlib.Path(__file__).resolve().parent.parent
_ENGINE = _REPO / "engine"
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))

import build_practice as BP   # noqa: E402
import generate as G          # noqa: E402
import pipeline as P          # noqa: E402
import brain as BR            # noqa: E402

_BLOCKS = json.loads((_ENGINE / "template_blocks.json").read_text(encoding="utf-8"))["blocks"]
_PRACTICE = BP.build_practice(BP.DEMO_SURVEY)

# A distinctive, honesty-clean, digit-free fees rationale the floor never emits,
# so its presence in output is unambiguous proof the model copy flowed through.
_FEES_PROSE = (
    "We keep the choices about your care between you and your clinician, never an "
    "insurer, and a free consultation is the kindest way to find out whether we "
    "are a good fit."
)
_FEES_FRAGMENT = "kindest way to find out whether we"

# Clean, digit-free filler for the row blocks (each passes _prose_ok + lint).
_SUBTITLES = [
    "Find steady ground together",
    "Notice what tends to surface",
    "Make sense of the pattern",
    "Try gentle new moves",
    "Weave it into daily life",
    "Keep the momentum going",
]
_STEP = {
    "science": (
        "We start by helping your nervous system feel a little safer, because "
        "lasting change is easier to reach from steady ground."
    ),
    "practice": "This week, notice one moment your shoulders drop, and let yourself stay there.",
}
_PHASE = {
    "paragraph": (
        "Early on we focus on building trust and getting clear about what matters "
        "most to you, so the work has a foundation to stand on."
    ),
}


# --------------------------------------------------------------------------- #
# Fake SDK surface. No google-genai client is constructed; we inject these.
# --------------------------------------------------------------------------- #
class _Resp:
    """Mimics the one attribute brain.py reads off a response: .text (a JSON str)."""

    def __init__(self, text: str):
        self.text = text


class _ScriptedModels:
    """models.generate_content that returns a single canned body, ignoring args."""

    def __init__(self, text: str):
        self._text = text

    def generate_content(self, *, model, contents, config):  # noqa: D401, ANN001
        return _Resp(self._text)


class _ScriptedClient:
    """A google-genai-shaped client whose every call returns the same body."""

    def __init__(self, payload):
        self.models = _ScriptedModels(payload if isinstance(payload, str) else json.dumps(payload))


class _FlexibleModels:
    """A client that answers each enrichable block correctly, by sniffing the
    prompt text brain.py builds (stable, fully under brain.py's control). Used by
    the full-build test so all five blocks get a valid, honest rewrite at once."""

    def __init__(self, about_inners):
        self._about_inners = list(about_inners)

    def generate_content(self, *, model, contents, config):  # noqa: ANN001
        c = contents
        if "billing model is" in c:                       # fees_why
            payload = {"prose": _FEES_PROSE}
        elif "Rewrite EACH subtitle" in c:                # method_intro_cards
            payload = {"subtitles": list(_SUBTITLES)}
        elif "the 'science'" in c:                        # method_steps
            payload = {"steps": [dict(_STEP) for _ in range(6)]}
        elif "three phases of a generic therapy journey" in c:  # journey_phases
            payload = {"phases": [dict(_PHASE) for _ in range(3)]}
        elif "about' paragraphs" in c:                    # about_body (echo = token-safe)
            payload = {"paragraphs": list(self._about_inners)}
        else:
            payload = {}
        return _Resp(json.dumps(payload))


class _FlexibleClient:
    def __init__(self, about_inners):
        self.models = _FlexibleModels(about_inners)


def _about_inners(find: str):
    import re
    return [m[1] for m in re.findall(r"(<p[^>]*>)(.*?)(</p>)", find, flags=re.S)]


# =========================================================================== #
# 1. availability is honest
# =========================================================================== #
class TestAvailability(unittest.TestCase):
    def test_unavailable_when_no_project_and_no_client(self):
        # No project -> unavailable regardless of SDK (short-circuits before SDK).
        self.assertFalse(BR.Brain(project=None).available())

    def test_unavailable_when_project_but_no_sdk(self):
        with mock.patch.object(BR, "_sdk_present", return_value=False):
            self.assertFalse(BR.Brain(project="proj-x").available())

    def test_available_when_project_and_sdk(self):
        with mock.patch.object(BR, "_sdk_present", return_value=True):
            self.assertTrue(BR.Brain(project="proj-x").available())

    def test_available_with_injected_client(self):
        # An injected (fake) client is always 'available' — no creds path taken.
        self.assertTrue(BR.Brain(client=_ScriptedClient({"prose": "x"})).available())

    def test_unavailable_brain_enriches_nothing(self):
        b = BR.Brain(project=None)
        self.assertIsNone(b.enrich_block("fees_why", _PRACTICE, _BLOCKS["fees_why"]["find"]))


# =========================================================================== #
# 2-4. the honesty gate fires on MODEL output
# =========================================================================== #
class TestHonestyGateOnModelOutput(unittest.TestCase):
    def _enrich(self, payload, bid="fees_why"):
        b = BR.Brain(client=_ScriptedClient(payload))
        return b.enrich_block(bid, _PRACTICE, _BLOCKS[bid]["find"])

    def test_clean_fees_why_is_accepted(self):
        out = self._enrich({"prose": _FEES_PROSE})
        self.assertIsNotNone(out)
        self.assertIn(_FEES_FRAGMENT, out)
        self.assertTrue(out.startswith('<p style="margin-top:18px;">'))
        self.assertEqual(G.lint(out), [])          # the result IS honesty-clean
        self.assertNotIn("{{", out)                # fees_why carries no tokens

    def test_banned_output_falls_back_to_floor(self):
        # 'proven' / 'cure' / '#1' must be caught on the model's own text.
        self.assertIsNone(self._enrich(
            {"prose": "Our proven method is clinically proven to cure you — the #1 choice."}
        ))

    def test_percentage_output_falls_back(self):
        # A fabricated statistic (digit + %) must not survive.
        self.assertIsNone(self._enrich({"prose": "It works for 92% of clients."}))

    def test_empty_output_falls_back_to_floor(self):
        self.assertIsNone(self._enrich({"prose": "   "}))

    def test_malformed_json_falls_back(self):
        self.assertIsNone(self._enrich("this is not json at all"))

    def test_missing_key_falls_back(self):
        self.assertIsNone(self._enrich({"wrong_key": "hello"}))

    def test_unknown_block_returns_none(self):
        self.assertIsNone(self._enrich({"prose": _FEES_PROSE}, bid="fees_faq"))


# =========================================================================== #
# 5. tokens are sacred (the only token-bearing block this seam touches)
# =========================================================================== #
class TestAboutTokenSafety(unittest.TestCase):
    # A self-contained 3-paragraph about block with known tokens — independent of
    # whatever the live template text happens to be.
    FIND = (
        '<p>Hi, I am {{owner_name}}, {{credential}}.</p>'
        '<p>{{business_name}} serves {{service_areas}}.</p>'
        '<p>Reach out about {{modalities}}.</p>'
    )

    def _enrich(self, paragraphs):
        b = BR.Brain(client=_ScriptedClient({"paragraphs": paragraphs}))
        return b.enrich_block("about_body", _PRACTICE, self.FIND)

    def test_echo_preserves_every_token(self):
        inners = _about_inners(self.FIND)
        out = self._enrich(inners)                 # echo = a valid no-op rewrite
        self.assertIsNotNone(out)
        self.assertEqual(BR._tokens(out), BR._tokens(self.FIND))

    def test_reworded_but_token_preserving_is_accepted_and_changes_bytes(self):
        reworded = [
            "Hello there — I am {{owner_name}}, {{credential}} by training.",
            "Here at {{business_name}}, we proudly serve {{service_areas}}.",
            "Please reach out to talk about {{modalities}}.",
        ]
        out = self._enrich(reworded)
        self.assertIsNotNone(out)
        self.assertNotEqual(out, self.FIND)         # genuinely enriched
        self.assertEqual(BR._tokens(out), BR._tokens(self.FIND))  # tokens intact
        self.assertEqual(G.lint(out), [])

    def test_dropping_a_token_falls_back(self):
        self.assertIsNone(self._enrich(["no tokens here", "still none", "nope"]))

    def test_introducing_html_falls_back(self):
        self.assertIsNone(self._enrich([
            "Hi, I am {{owner_name}}, {{credential}}.",
            "<b>{{business_name}}</b> serves {{service_areas}}.",   # smuggled tag
            "Reach out about {{modalities}}.",
        ]))

    def test_wrong_paragraph_count_falls_back(self):
        self.assertIsNone(self._enrich(["only one paragraph {{owner_name}}"]))


# =========================================================================== #
# 6. ZERO regression at the generate() seam
# =========================================================================== #
class TestGenerateSeam(unittest.TestCase):
    def test_brain_none_is_byte_identical_to_floor(self):
        a = G.generate(_PRACTICE, {"blocks": _BLOCKS})
        b = G.generate(_PRACTICE, {"blocks": _BLOCKS}, brain=None)
        self.assertEqual(a, b)

    def test_fake_brain_enriches_fees_block_in_generate(self):
        brain = BR.Brain(client=_FlexibleClient(_about_inners(_BLOCKS["about_body"]["find"])))
        out = G.generate(_PRACTICE, {"blocks": _BLOCKS}, brain=brain)
        self.assertIn(_FEES_FRAGMENT, out["blocks"]["fees_why"]["replace"])
        # every non-enrichable block is byte-identical to the floor.
        floor = G.generate(_PRACTICE, {"blocks": _BLOCKS})
        non_brain = [b for b in _BLOCKS if b not in BR.BRAIN_BLOCKS]
        self.assertTrue(non_brain)
        for bid in non_brain:
            self.assertEqual(
                out["blocks"][bid]["replace"],
                floor["blocks"][bid]["replace"],
                msg=f"non-enrichable block {bid!r} changed under brain",
            )

    def test_brain_that_raises_is_swallowed_and_floor_used(self):
        class _Boom:
            BRAIN_BLOCKS = {"fees_why"}

            def enrich_block(self, *a, **k):
                raise RuntimeError("brain on fire")

        floor = G.generate(_PRACTICE, {"blocks": _BLOCKS})
        out = G.generate(_PRACTICE, {"blocks": _BLOCKS}, brain=_Boom())
        # a brain that explodes must not change the deterministic output at all.
        self.assertEqual(out, floor)


# =========================================================================== #
# 7. a real end-to-end build still renders — with and without the brain
# =========================================================================== #
class TestFullBuild(unittest.TestCase):
    def _site_text(self, out_dir: pathlib.Path) -> str:
        chunks = []
        for f in sorted(out_dir.rglob("*")):
            if f.is_file() and f.suffix in (".html", ".js", ".css"):
                chunks.append(f.read_text(encoding="utf-8", errors="ignore"))
        return "\n".join(chunks)

    def test_build_with_brain_none_renders(self):
        with tempfile.TemporaryDirectory() as td:
            res = P.build_site(BP.DEMO_SURVEY, sites_dir=td, brain=None)
            out = pathlib.Path(res["dir"])
            self.assertTrue((out / "index.html").is_file())
            text = self._site_text(out)
            self.assertNotIn("{{", text)            # no token leak
            self.assertNotIn("AI-GENERATE", text)   # no marker leak
            self.assertNotIn(_FEES_FRAGMENT, text)  # floor never says this

    def test_build_with_fake_brain_renders_and_flows(self):
        inners = _about_inners(_BLOCKS["about_body"]["find"])
        brain = BR.Brain(client=_FlexibleClient(inners))
        with tempfile.TemporaryDirectory() as td:
            res = P.build_site(BP.DEMO_SURVEY, sites_dir=td, brain=brain)
            out = pathlib.Path(res["dir"])
            self.assertTrue((out / "index.html").is_file())
            text = self._site_text(out)
            self.assertNotIn("{{", text)            # still zero token leaks
            self.assertNotIn("AI-GENERATE", text)   # still zero marker leaks
            self.assertIn(_FEES_FRAGMENT, text)     # the model copy actually flowed


# =========================================================================== #
# 8. the SDK is TRULY optional — the fake-client path needs no google-genai (D2)
# =========================================================================== #
class TestZeroDependencyPath(unittest.TestCase):
    def test_fake_client_enriches_even_with_sdk_absent(self):
        # Simulate google-genai NOT installed: importing it raises, so _config
        # falls back to a stdlib namespace and the injected fake client still
        # enriches. This is the bare-Mac floor guarantee for the seam.
        with mock.patch.dict(sys.modules, {"google.genai": None, "google.genai.types": None}):
            self.assertFalse(BR._sdk_present())
            b = BR.Brain(client=_ScriptedClient({"prose": _FEES_PROSE}))
            out = b.enrich_block("fees_why", _PRACTICE, _BLOCKS["fees_why"]["find"])
            self.assertIsNotNone(out)
            self.assertIn(_FEES_FRAGMENT, out)

    def test_real_brain_is_unavailable_with_sdk_absent(self):
        # A non-injected brain cannot run without the SDK — it must say so, not
        # crash, so callers fall back to the deterministic floor.
        with mock.patch.dict(sys.modules, {"google.genai": None}):
            self.assertFalse(BR.Brain(project="proj-x").available())


if __name__ == "__main__":
    unittest.main(verbosity=2)
