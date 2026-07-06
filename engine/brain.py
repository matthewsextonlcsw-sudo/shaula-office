#!/usr/bin/env python3
"""brain — OPTIONAL Gemini-on-Vertex enrichment seam for the Shaula site engine.

This is slice #1 of "the brain": an *additive* prose-enrichment layer that slots
into the EXISTING deterministic website builder. It is NOT a rewrite and NOT a
dependency.

WHAT IT DOES
  For a small set of *pure-prose* blocks (the method narrative, the journey-phase
  prose, the fees rationale, the about paragraphs) it asks Gemini to re-author the
  human copy with more warmth/flow — then runs that model output back through the
  SAME honesty rails the deterministic floor already passes. If the model is
  absent, unconfigured, errors, returns empty, or trips a rail, the block falls
  back to the deterministic floor, byte-for-byte. "Still renders if the model is
  emptied" stays true.

THE RAILS IT REUSES (it adds no new honesty authority)
  * generate.lint() / generate._BANNED  — the one box-wide banned-claim linter.
    It is authoritative: generate.generate() ALSO re-lints every block after
    enrichment, so a banned claim cannot survive even if this file had a bug.
  * generate._emit_rows() — the exact row serializer the resolvers use, so an
    enriched row block is byte-shaped like the floor (same map closure, arity).
  * citations.GENERIC_* (via generate._method_cards/_method_steps/_journey) — the
    real floor content, used as the seed + the per-cell fallback.

WHY GOOGLE VERTEX ONLY (locked)
  Vertex AI runs under the operator's org BAA. The
  consumer Gemini API (api_key) is BANNED here. `genai.Client(vertexai=True, ...)`
  is the only client this file constructs. Default model `gemini-2.5-pro` (GA,
  HIPAA-eligible on Vertex); swap to a GA Gemini 3 via SHAULA_BRAIN_MODEL.

OPTIONAL DEPENDENCY
  `google-genai` is imported LAZILY (only when a real client is built). Importing
  this module is pure stdlib, so the box's zero-dependency floor (D2) is intact:
  `import brain` never pulls google.genai at module load.

ACCEPTANCE HEURISTIC vs HONESTY GATE (read before editing)
  `_prose_ok()` is a *floor-biased acceptance heuristic*, NOT a second honesty
  linter. It can only ever cause MORE fallback to the already-honest floor; it
  never lets through anything the canonical lint rejects. The single source of
  honesty truth remains generate.lint() (D6). Example heuristic: the enrichable
  floor prose is digit-free, so a stray digit in model output reads as a possible
  fabricated statistic → reject toward the floor. Cheap insurance, never a risk.

Pure stdlib at import. Run `python3 engine/brain.py` for a no-network self-test.
"""
from __future__ import annotations

import html
import os
import re
import sys
import time

# Reuse the box-wide engine (linter + serializers + floor content). generate.py
# imports nothing from here, so there is no import cycle.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate as G  # noqa: E402

# --------------------------------------------------------------------------- #
# Configuration (all via environment — no secrets, no service-account JSON).
# --------------------------------------------------------------------------- #
_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("SHAULA_GCP_PROJECT")
_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
_MODEL = os.environ.get("SHAULA_BRAIN_MODEL", "gemini-2.5-pro")

# Gemini 2.5 models THINK before answering, and the thinking tokens are drawn
# from the SAME max_output_tokens budget as the visible answer. Verified live on
# Vertex 2026-06-05: gemini-2.5-pro spent 242-933 thinking tokens on a 2-sentence
# rephrase, starving or truncating the JSON (finish_reason=MAX_TOKENS, text=None)
# at the per-block caps below — every block silently fell back to the floor, so
# the seam "worked" but never actually enriched. Capping the thinking budget
# leaves headroom for the prose (with budget=128 the same call returned a clean,
# complete rewrite). 2.5 Pro's minimum is 128 (it rejects 0 with INVALID_ARGUMENT);
# a Flash model or a future Gemini 3 can set 0 via the env knob.
_THINKING_BUDGET = int(os.environ.get("SHAULA_BRAIN_THINKING_BUDGET", "128"))

# Retry-with-backoff around the single generate_content call.
_TRIES = 2
_BACKOFF = 0.6  # seconds, multiplied by the (1-based) attempt number

# The honesty contract handed to the model itself. The rails do not trust it —
# every output is re-linted — but a clear instruction reduces wasted calls.
_SYSTEM = (
    "You are the in-house copy editor for a single licensed psychotherapy "
    "practice's marketing website. You only ever REPHRASE copy that is handed to "
    "you, in plain, warm, professional American English. Hard rules you must "
    "never break:\n"
    "1. Invent NO facts. No statistics, percentages, numbers, counts, dates, "
    "outcomes, success rates, client testimonials, awards, rankings, or "
    "credentials that are not already in the text you were given.\n"
    "2. Make NO efficacy or superiority claims. Never 'proven', 'guaranteed', "
    "'evidence-based' as a boast, 'clinically proven', 'cure', '#1', "
    "'best', or 'world-class'.\n"
    "3. Preserve every {{token}} placeholder EXACTLY as written, verbatim, and "
    "do not add new ones.\n"
    "4. Do not add HTML tags, markdown, links, or emoji unless they were already "
    "present in the input.\n"
    "5. Keep each rewrite close in length to the original. Return ONLY the JSON "
    "the response schema asks for, nothing else.\n"
    "When in doubt, stay closer to the wording you were given."
)

# The blocks this seam may enrich. Every other block stays 100% deterministic.
# Deliberately EXCLUDED: fees_faq (its answers carry the literal fee, session
# length, and program duration — fact-dense cells where a model rewrite could
# silently alter a dollar amount; the floor already weaves the real facts), and
# every citation-bound / token-only block (modalities `what` is citation-bound;
# headings/ledes are fixed template constants).
BRAIN_BLOCKS = {
    "fees_why",          # the fees rationale paragraph (pure prose)
    "method_intro_cards",  # 6 cards: enrich the one-line subtitle only
    "method_steps",      # 6 steps: enrich the science + practice prose only
    "journey_phases",    # 3 phases: enrich the paragraph only
    "about_body",        # the about paragraphs (token-bearing; tokens preserved)
}

# --------------------------------------------------------------------------- #
# Acceptance heuristics (floor-biased — can only reject toward the honest floor).
# --------------------------------------------------------------------------- #
_TOKEN = re.compile(r"\{\{[a-z0-9_]+\}\}")
_DIGIT = re.compile(r"\d")


def _tokens(s: str) -> list[str]:
    """Sorted multiset of {{token}} placeholders in a string."""
    return sorted(_TOKEN.findall(s or ""))


def _prose_ok(text: str, *, allow_tokens: bool = False, max_len: int = 1400) -> bool:
    """True iff model prose is safe to swap in for the deterministic floor.

    NOT an honesty authority — generate.lint() is. This only ever rejects toward
    the floor:
      * empty / whitespace            -> floor
      * absurdly long (runaway)       -> floor
      * trips the canonical linter    -> floor (authoritative gate)
      * introduces a digit            -> floor (enrichable floor prose is
                                          digit-free; a digit reads as a possible
                                          fabricated number/percentage/stat)
    """
    if not text or not text.strip():
        return False
    if len(text) > max_len:
        return False
    if G.lint(text):  # canonical honesty gate
        return False
    probe = _TOKEN.sub("", text) if allow_tokens else text
    if _DIGIT.search(probe):
        return False
    return True


# --------------------------------------------------------------------------- #
# Native structured-output schemas (Vertex-canonical uppercase types). Passed to
# response_schema so Gemini returns parseable JSON, not free text.
# --------------------------------------------------------------------------- #
_SCHEMA_FEES_WHY = {
    "type": "OBJECT",
    "properties": {"prose": {"type": "STRING"}},
    "required": ["prose"],
}
_SCHEMA_SUBTITLES = {
    "type": "OBJECT",
    "properties": {"subtitles": {"type": "ARRAY", "items": {"type": "STRING"}}},
    "required": ["subtitles"],
}
_SCHEMA_STEPS = {
    "type": "OBJECT",
    "properties": {
        "steps": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "science": {"type": "STRING"},
                    "practice": {"type": "STRING"},
                },
                "required": ["science", "practice"],
            },
        }
    },
    "required": ["steps"],
}
_SCHEMA_PHASES = {
    "type": "OBJECT",
    "properties": {
        "phases": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"paragraph": {"type": "STRING"}},
                "required": ["paragraph"],
            },
        }
    },
    "required": ["phases"],
}
_SCHEMA_ABOUT = {
    "type": "OBJECT",
    "properties": {"paragraphs": {"type": "ARRAY", "items": {"type": "STRING"}}},
    "required": ["paragraphs"],
}


def _sdk_present() -> bool:
    """True iff the optional google-genai SDK can be imported (no client built)."""
    try:
        import google.genai  # noqa: F401
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# The brain.
# --------------------------------------------------------------------------- #
class Brain:
    """Optional Gemini (Vertex) enrichment over the deterministic floor.

    Construct with no arguments to use the ambient GOOGLE_CLOUD_PROJECT / ADC, or
    inject a pre-built ``client`` (the tests inject a fake one — no creds needed).
    """

    # Surface the enrichable-block set on the instance too, so a caller holding
    # only a Brain (generate.py) can gate on ``brain.BRAIN_BLOCKS`` without
    # importing this module.
    BRAIN_BLOCKS = BRAIN_BLOCKS

    def __init__(
        self,
        client=None,
        *,
        project: str | None = _PROJECT,
        location: str = _LOCATION,
        model: str = _MODEL,
    ):
        self._client = client
        self.project = project
        self.location = location
        self.model = model

    # -- availability ------------------------------------------------------- #
    def available(self) -> bool:
        """True iff this brain can attempt a call (injected client, or a project
        plus an importable SDK). False → callers use the deterministic floor."""
        if self._client is not None:
            return True
        return bool(self.project) and _sdk_present()

    def _ensure_client(self):
        """Lazily build a Vertex client. google.genai is imported HERE, never at
        module load, so the box's zero-dependency floor stays intact."""
        if self._client is None:
            from google import genai  # lazy, optional dependency
            # vertexai=True is mandatory: BAA-covered Vertex only, never the
            # consumer Gemini API (no api_key path here, by design).
            self._client = genai.Client(
                vertexai=True, project=self.project, location=self.location
            )
        return self._client

    def _config(self, schema: dict, max_tokens: int):
        """Build the generation config.

        Uses the real SDK type when google-genai is installed — the only path a
        real Vertex call ever takes. When the SDK is absent (possible ONLY with an
        injected fake client, since a real, non-injected brain is unavailable()
        without it) fall back to a stdlib namespace carrying the same fields, so
        the fake-client tests and self-test stay zero-dependency (D2). A real
        client never receives the stand-in; only a fake one (which ignores it)."""
        try:
            from google.genai import types  # lazy, optional dependency
        except ImportError:
            import types as _t  # stdlib stand-in — fake-client / no-SDK path only
            return _t.SimpleNamespace(
                temperature=0.4,
                max_output_tokens=max_tokens,
                system_instruction=_SYSTEM,
                response_mime_type="application/json",
                response_schema=schema,
            )
        return types.GenerateContentConfig(
            temperature=0.4,
            max_output_tokens=max_tokens,
            system_instruction=_SYSTEM,
            response_mime_type="application/json",
            response_schema=schema,
            # Cap thinking so it can't eat the whole output budget (see
            # _THINKING_BUDGET above). Omitted from the stdlib stand-in branch:
            # that path is only ever hit by a fake client, which ignores config.
            thinking_config=types.ThinkingConfig(thinking_budget=_THINKING_BUDGET),
        )

    def _generate_json(self, prompt: str, schema: dict, *, max_tokens: int = 640):
        """One structured call, retried with backoff. Returns parsed dict or None.

        Any failure (no client, SDK error, empty body, unparseable JSON, transport
        error) returns None → the caller falls back to the floor. Never raises.
        """
        try:
            client = self._ensure_client()
        except Exception:
            return None
        try:
            cfg = self._config(schema, max_tokens)
        except Exception:
            return None

        import json  # stdlib; local to keep the hot path obvious
        for attempt in range(_TRIES):
            try:
                resp = client.models.generate_content(
                    model=self.model, contents=prompt, config=cfg
                )
                raw = (getattr(resp, "text", None) or "").strip()
                if not raw:
                    raise ValueError("empty response body")
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError("response was not a JSON object")
                return data
            except Exception:
                if attempt + 1 < _TRIES:
                    time.sleep(_BACKOFF * (attempt + 1))
                    continue
                return None
        return None

    # -- public entrypoint -------------------------------------------------- #
    def enrich_block(self, bid: str, practice: dict, find: str):
        """Return an enriched, honesty-clean ``replace`` string for ``bid``, or
        None to fall back to the deterministic floor.

        The returned string is the SAME serialized shape the floor resolver
        emits (so generate.py just swaps it in and re-lints). Never raises — any
        problem returns None.
        """
        if bid not in BRAIN_BLOCKS or not self.available():
            return None
        try:
            if bid == "fees_why":
                return self._fees_why(practice)
            if bid == "method_intro_cards":
                return self._method_intro_cards(practice, find)
            if bid == "method_steps":
                return self._method_steps(practice, find)
            if bid == "journey_phases":
                return self._journey_phases(practice, find)
            if bid == "about_body":
                return self._about_body(practice, find)
        except Exception:
            return None
        return None

    # -- per-block authoring ------------------------------------------------ #
    def _fees_why(self, practice: dict):
        biz = practice.get("business_name", "this practice")
        model = "out-of-network" if G._is_oon(practice) else "in-network"
        prompt = (
            f"The practice is {biz}. Its billing model is {model}. Rewrite this "
            "single short paragraph that explains, honestly and warmly, WHY the "
            "practice bills this way (what it protects about the clinical work) "
            "and why a free consult is the best way to find out if it is the "
            "right fit. 2-3 sentences. No fees, no numbers, no claims.\n\n"
            "Current paragraph:\n"
            "This practice's billing model keeps clinical decisions between the "
            "client and the clinician; a free consult is the most honest way to "
            "find out if it is the right fit."
        )
        data = self._generate_json(prompt, _SCHEMA_FEES_WHY, max_tokens=384)
        if not data:
            return None
        prose = (data.get("prose") or "").strip()
        if not _prose_ok(prose, max_len=600):
            return None
        return f'<p style="margin-top:18px;">{html.escape(prose, quote=False)}</p>'

    def _method_intro_cards(self, practice: dict, find: str):
        rows = G._method_cards(practice)  # [[letter, name, subtitle], ...] x6
        names = [r[1] for r in rows]
        subs = [r[2] for r in rows]
        prompt = (
            "Here are the six steps of a generic, evidence-informed therapy "
            "framework, each with a one-line subtitle. Rewrite EACH subtitle to "
            "be a little warmer and clearer, same meaning, at most ~8 words, no "
            "numbers, no claims. Return exactly six, in the same order.\n\n"
            + "\n".join(f"{i+1}. {n} — {s}" for i, (n, s) in enumerate(zip(names, subs)))
        )
        data = self._generate_json(prompt, _SCHEMA_SUBTITLES, max_tokens=320)
        if not data:
            return None
        new_subs = data.get("subtitles")
        if not isinstance(new_subs, list) or len(new_subs) != len(rows):
            return None
        out = []
        for (letter, name, sub), cand in zip(rows, new_subs):
            cand = (cand or "").strip()
            out.append([letter, name, cand if _prose_ok(cand, max_len=120) else sub])
        return G._emit_rows(find, out)

    def _method_steps(self, practice: dict, find: str):
        rows = G._method_steps(practice)  # [letter,name,num,subtitle,science,practice] x6
        listing = "\n\n".join(
            f"Step {i+1} ({r[1]}):\n  science: {r[4]}\n  practice: {r[5]}"
            for i, r in enumerate(rows)
        )
        prompt = (
            "Here are the six steps of a generic, evidence-informed therapy "
            "framework. For EACH step rewrite the 'science' explanation (2-4 "
            "plain-language sentences, same clinical meaning, warmer) and the "
            "'practice' line (one concrete thing the reader can try this week). "
            "No statistics, no numbers, no efficacy claims. Return exactly six "
            "steps in the same order.\n\n" + listing
        )
        data = self._generate_json(prompt, _SCHEMA_STEPS, max_tokens=1100)
        if not data:
            return None
        steps = data.get("steps")
        if not isinstance(steps, list) or len(steps) != len(rows):
            return None
        out = []
        for r, st in zip(rows, steps):
            letter, name, num, subtitle, sci, prac = r
            cand_sci = (st.get("science") or "").strip() if isinstance(st, dict) else ""
            cand_prac = (st.get("practice") or "").strip() if isinstance(st, dict) else ""
            # per-cell fallback: a bad cell uses the floor cell (both are honest).
            new_sci = cand_sci if _prose_ok(cand_sci) else sci
            new_prac = cand_prac if _prose_ok(cand_prac) else prac
            out.append([letter, name, num, subtitle, new_sci, new_prac])
        return G._emit_rows(find, out)

    def _journey_phases(self, practice: dict, find: str):
        rows = G._journey(practice)  # [Phase 0N, size, detail, name, paragraph] x3
        listing = "\n\n".join(
            f"Phase {i+1} ({r[3]}):\n  {r[4]}" for i, r in enumerate(rows)
        )
        prompt = (
            "Here are the three phases of a generic therapy journey, each with a "
            "paragraph. Rewrite EACH paragraph to be warmer and clearer, same "
            "meaning, no numbers, no week counts, no claims. Return exactly three "
            "in the same order.\n\n" + listing
        )
        data = self._generate_json(prompt, _SCHEMA_PHASES, max_tokens=700)
        if not data:
            return None
        phases = data.get("phases")
        if not isinstance(phases, list) or len(phases) != len(rows):
            return None
        out = []
        for r, ph in zip(rows, phases):
            phase, size, detail, name, para = r
            cand = (ph.get("paragraph") or "").strip() if isinstance(ph, dict) else ""
            out.append([phase, size, detail, name, cand if _prose_ok(cand) else para])
        return G._emit_rows(find, out)

    def _about_body(self, practice: dict, find: str):
        """Enrich the about paragraphs while PRESERVING every {{token}} verbatim.

        The about block is the only token-bearing block this seam touches, so the
        guard is the strictest: the model rewrites only the inner sentence text of
        each <p>, the exact <p ...> wrappers from the template are kept, every
        original {{token}} must reappear, and no new HTML may be introduced. Any
        deviation -> None -> deterministic floor (the verbatim template).
        """
        parts = re.findall(r"(<p[^>]*>)(.*?)(</p>)", find, flags=re.S)
        if len(parts) != 3:
            return None
        inners = [p[1] for p in parts]
        listing = "\n\n".join(
            f"Paragraph {i+1} (must contain these placeholders verbatim: "
            f"{', '.join(_tokens(inner)) or 'none'}):\n{inner}"
            for i, inner in enumerate(inners)
        )
        prompt = (
            "Here are three short 'about' paragraphs for a therapist's website. "
            "Rewrite EACH to read a little warmer and more human, SAME facts, "
            "same length. You MUST keep every {{placeholder}} exactly as written "
            "and add no new ones. Add no HTML tags. Invent nothing — no numbers, "
            "no credentials, no outcomes. Return exactly three paragraphs in "
            "order.\n\n" + listing
        )
        data = self._generate_json(prompt, _SCHEMA_ABOUT, max_tokens=900)
        if not data:
            return None
        new_inners = data.get("paragraphs")
        if not isinstance(new_inners, list) or len(new_inners) != 3:
            return None

        rebuilt_inners = []
        for original, cand in zip(inners, new_inners):
            cand = (cand or "").strip()
            # no new tags, honesty-clean, tokens preserved EXACTLY for this para
            if not cand or "<" in cand or ">" in cand:
                return None
            if not _prose_ok(cand, allow_tokens=True, max_len=700):
                return None
            if _tokens(cand) != _tokens(original):
                return None
            rebuilt_inners.append(cand)

        rebuilt = "".join(o + ni + c for (o, _i, c), ni in zip(parts, rebuilt_inners))
        # the find string is the 3 <p> blocks joined by their original separators;
        # swap each original inner for its rewrite, preserving those separators.
        out = find
        for original, ni in zip(inners, rebuilt_inners):
            out = out.replace(original, ni, 1)
        # whole-block invariants: token multiset unchanged, still honesty-clean.
        if _tokens(out) != _tokens(find) or G.lint(out):
            return None
        return out


# --------------------------------------------------------------------------- #
# No-network self-test: prove the floor-fallback contract without any creds.
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import json as _json

    failures: list[str] = []

    # A fake client that returns whatever script we hand it (no creds, no net).
    class _Resp:
        def __init__(self, text):
            self.text = text

    class _Models:
        def __init__(self, text):
            self._text = text

        def generate_content(self, *, model, contents, config):
            return _Resp(self._text)

    class _Client:
        def __init__(self, text):
            self.models = _Models(text)

    blocks = _json.loads(
        (os.path.join(os.path.dirname(__file__), "template_blocks.json"))
        and open(os.path.join(os.path.dirname(__file__), "template_blocks.json"),
                 encoding="utf-8").read()
    )["blocks"]
    from build_practice import build_practice, DEMO_SURVEY  # type: ignore
    practice = build_practice(DEMO_SURVEY)

    # 1) no project + no client → unavailable → enrich returns None
    b0 = Brain(project=None)
    if b0.available():
        failures.append("Brain(project=None) should be unavailable")
    if b0.enrich_block("fees_why", practice, blocks["fees_why"]["find"]) is not None:
        failures.append("unavailable brain should not enrich")

    # 2) clean model output is accepted (fees_why)
    clean = _Client(_json.dumps({"prose": "We keep the choices about your care "
                                 "between us, not an insurer; a free consult is "
                                 "the kindest way to learn if we fit."}))
    b1 = Brain(client=clean)
    out = b1.enrich_block("fees_why", practice, blocks["fees_why"]["find"])
    if not out or "free consult" not in out:
        failures.append("clean fees_why was not enriched")

    # 3) banned model output is rejected → None (honesty gate fires on MODEL text)
    dirty = _Client(_json.dumps({"prose": "Our proven method is clinically "
                                 "proven to cure you — the #1 choice."}))
    b2 = Brain(client=dirty)
    if b2.enrich_block("fees_why", practice, blocks["fees_why"]["find"]) is not None:
        failures.append("banned model output should fall back to floor")

    # 4) empty model output → None
    empty = _Client(_json.dumps({"prose": "   "}))
    if Brain(client=empty).enrich_block(
        "fees_why", practice, blocks["fees_why"]["find"]
    ) is not None:
        failures.append("empty model output should fall back to floor")

    # 5) about_body keeps every token
    ab_find = blocks["about_body"]["find"]
    toks = _tokens(ab_find)
    paras = [p[1] for p in re.findall(r"(<p[^>]*>)(.*?)(</p>)", ab_find, flags=re.S)]
    keep = _Client(_json.dumps({"paragraphs": paras}))  # echo = tokens preserved
    ab = Brain(client=keep).enrich_block("about_body", practice, ab_find)
    if ab is None or _tokens(ab) != toks:
        failures.append("about_body should preserve tokens")
    drop = _Client(_json.dumps({"paragraphs": ["no tokens here", "still none", "nope"]}))
    if Brain(client=drop).enrich_block("about_body", practice, ab_find) is not None:
        failures.append("about_body must reject token-dropping output")

    if failures:
        print("BRAIN SELF-TEST FAILED:")
        for f in failures:
            print("  -", f)
        raise SystemExit(1)
    print("brain.py OK — floor-fallback contract holds (no creds, no network).")
