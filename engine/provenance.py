#!/usr/bin/env python3
r"""provenance — the CLAIM-PROVENANCE GATE for arbitrary / freehand HTML.

WHY THIS EXISTS
---------------
Shaula's published-honesty guarantee is, today, STRUCTURAL. Content flows through
known ``{{tokens}}`` and linted ``<!-- AI-GENERATE -->`` blocks into one fixed
template (``templates/private-practice/``); ``engine/banned.py`` bans invented
stats / "proven" / "#1" / fake-testimonial language at the value level; and
``engine/fill.py`` proves 0 token-leaks / 0 surviving markers. Because the
structure is fixed and every value is linted, a fabricated claim has nowhere to
hide.

That guarantee EVAPORATES the moment we accept content whose structure we do NOT
control:
  * (3a) a user IMPORTS their own arbitrary HTML design, or
  * (3b) a model produces a FREEHAND layout.
Now a fabricated stat ("92% of clients improve"), a fake testimonial ("Best
therapist I've ever had! —Jane"), or a credential the clinician does not hold can
be smuggled in ANY tag, anywhere. The fixed-template lint never sees it as a
distinct, governed value — it's just text in a blob.

WHAT THIS GATE DOES
-------------------
Given (a) finished/arbitrary HTML and (b) the APPROVED content set — the
practice's linted token values (``practice.json``) plus the generated block text
(``generated.json``) — it proves that every factual, claim-bearing unit of
VISIBLE text in the HTML TRACES BACK to approved content, and FLAGS/REJECTS
anything un-sourced. It is the keystone that lets 3a/3b stay honest.

THE PIPELINE (v1 — pragmatic, string/coverage-based; limits documented below)
-----------------------------------------------------------------------------
  1. Build the APPROVED CORPUS from the approved set:
       - every shipped string token value from practice.json (normalized), and
       - every generated block's ``replace`` string, from which we ALSO extract
         the visible text and resolve any ``{{tokens}}`` against practice.json
         (so a block like ``hero_sub`` contributes its FILLED prose, the way it
         actually renders).
  2. Extract VISIBLE TEXT from the candidate HTML: drop <script>/<style> BODIES,
     strip all tags, unescape HTML entities, collapse whitespace.
  3. SEGMENT that visible text into claim-bearing units — sentences, list items,
     and headings — using sentence punctuation plus the structural line breaks
     we inserted at block-level tags during extraction.
  4. CLASSIFY each unit:
       - SOURCED  if its normalized content is COVERED by a single approved
         source string (high token-set containment), OR every one of its content
         tokens appears SOMEWHERE in the approved vocabulary (honest
         RECOMBINATION — the static masthead/title/footer that glues approved
         names with generic connectors), OR it is generic, non-claim boilerplate
         on a small ALLOWLIST (nav labels, the crisis 988 / 741741 / Text HOME
         line, "Telehealth", etc.).
       - else FLAGGED (un-sourced claim-bearing text — it imports at least one
         word that appears nowhere in the approved set).
  5. Independently, run ``engine/banned.py`` (REUSED, not reinvented) over the
     full visible text. Any AFFIRMATIVE banned-language hit is a separate, hard
     offender class — it does not matter whether the phrase happens to also
     appear in the approved set; banned marketing language is refused outright.

A non-empty offender list => REJECT (CLI exits non-zero, naming each offender).

WHAT v1 CATCHES vs MISSES (be honest — this is coverage-based, NOT entailment)
-----------------------------------------------------------------------------
CATCHES (high confidence):
  * Verbatim or lightly-reordered FABRICATIONS not present in the approved set:
    invented stats, fake testimonials, invented credentials, awards, "as seen
    in" lines — the dominant smuggling vectors for imported/freehand HTML.
  * All affirmative banned-language claims (delegated to banned.lint), even when
    paraphrased into otherwise-"sourced"-looking sentences.

MISSES (by construction — these are the v2 mandate):
  * SEMANTIC / paraphrased fabrication whose WORDS overlap heavily with approved
    content but whose MEANING is new (e.g. approved "we track outcomes" vs
    injected "outcomes always improve") can slip if token-overlap is high. v1 is
    coverage, not natural-language INFERENCE.
  * Claims assembled by RECOMBINING approved fragments into a new, false whole.
  * A fabrication a malicious author pads with enough approved tokens to clear
    the coverage threshold. (We default the threshold high to make this hard, and
    the banned-language gate still fires independently — but coverage alone is
    defeatable by a determined adversary; treat this gate as a strong honest-
    mistake / careless-import catch, not an adversarial proof.)
  * Text rendered only by client-side JS at runtime (we read the static HTML the
    fill engine emits; the render-time scan in prove.sh remains the companion
    for executed output).

v2 PATH: replace step-4 coverage with an ENTAILMENT check — embed each candidate
unit and the approved corpus, and require every claim unit to be ENTAILED by
(not merely lexically similar to) some approved sentence, via an NLI model or an
embedding-similarity floor with a human-tuned threshold. That closes the
semantic-paraphrase and recombination gaps coverage cannot. See README / report.

Pure stdlib (Python 3.8+), no network, no third-party packages — same constraints
as the rest of the engine. NO PHI: operates on synthetic practice data + markup.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import unicodedata
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import banned  # noqa: E402 — single source of truth for the banned-language gate
import citations  # noqa: E402 — curated approved content banks (template-path corpus)


# --------------------------------------------------------------------------- #
# Tunables.
# --------------------------------------------------------------------------- #
# A claim unit counts as COVERED when at least this fraction of its
# "content tokens" (after dropping stopwords + the {{token}} placeholders) is
# present in SOME approved string's token set. Default is deliberately high: a
# real sentence assembled from approved content clears it comfortably, while an
# injected fabrication padded with a few approved words does not. Exposed on the
# CLI for experimentation, but the strict default is the honest one.
DEFAULT_COVERAGE_THRESHOLD = 0.85

# Units with fewer than this many content tokens are treated as too short to
# carry a standalone factual claim and are NOT flagged on coverage grounds
# (e.g. "Maya Restrepo", "Denver, CO", "$175"). They are STILL subject to the
# banned-language gate and the allowlist. Short proper-noun/figure fragments are
# overwhelmingly labels, not claims; flagging them produces noise, not safety.
MIN_CLAIM_TOKENS = 4

# Block-level tags: when stripping markup we insert a hard break here so two
# adjacent blocks' text cannot fuse into one bogus "sentence", and so headings /
# list items segment on their own. Inline tags (<span>, <em>, <a>, <strong>…)
# are NOT in this set — their text stays joined, which is correct.
_BLOCK_TAGS = frozenset({
    "p", "div", "section", "article", "header", "footer", "main", "aside", "nav",
    "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul", "ol", "blockquote", "figure",
    "figcaption", "table", "tr", "td", "th", "thead", "tbody", "br", "hr",
    "form", "label", "button", "option", "select", "fieldset", "legend",
    "dl", "dt", "dd", "details", "summary", "title",
})

# Tags whose TEXT CONTENT is never visible prose — dropped wholesale.
_DROP_CONTENT_TAGS = frozenset({"script", "style", "template", "noscript"})


# --------------------------------------------------------------------------- #
# Normalization + tokenization.
# --------------------------------------------------------------------------- #
# Tokens are lowercased alphanumeric runs. The {{token}} placeholders that may
# survive inside an approved block string ("{{owner_name}}") are stripped BEFORE
# tokenizing so they never count as content (they are resolved separately).
_PLACEHOLDER_RE = re.compile(r"\{\{\s*[a-zA-Z0-9_]+\s*\}\}")
_WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")

# Generic English + therapy-site connective words that carry no claim by
# themselves. Used only to decide how much of a unit is *substantive* before
# scoring coverage and the min-token floor. Conservative: dropping a content
# word here can only ever make the gate STRICTER on that unit (smaller
# denominator), never looser — coverage is fraction-of-content-tokens-found.
_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "nor", "so", "yet", "of", "to", "in",
    "on", "at", "by", "for", "with", "from", "as", "into", "onto", "over",
    "is", "are", "was", "were", "be", "been", "being", "am",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "its", "our", "their", "this", "that", "these", "those",
    "do", "does", "did", "done", "doing", "will", "would", "can", "could",
    "shall", "should", "may", "might", "must", "have", "has", "had", "having",
    "not", "no", "if", "then", "than", "when", "where", "who", "whom", "which",
    "what", "how", "why", "all", "any", "each", "few", "more", "most", "some",
    "such", "only", "own", "same", "very", "just", "about", "up", "out", "down",
    "here", "there", "now", "also", "both", "between", "through", "during",
    "before", "after", "while", "because", "rather", "instead",
})


def _strip_placeholders(text: str) -> str:
    return _PLACEHOLDER_RE.sub(" ", text or "")


def normalize(text: str) -> str:
    """Unicode-fold, unescape entities, lowercase, and collapse whitespace.

    NFKC folds the typographic punctuation the engine emits (curly quotes, en/em
    dashes, the middle dot ·) toward ASCII-ish forms so the approved corpus and
    the rendered HTML compare on equal footing.
    """
    if not text:
        return ""
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    # Normalize the handful of typographic glyphs NFKC leaves alone but that the
    # generator uses heavily, so they don't fracture token comparison.
    text = (text.replace("’", "'").replace("‘", "'")
                .replace("“", '"').replace("”", '"')
                .replace("—", " ").replace("–", " ")
                .replace("·", " ").replace(" ", " "))
    return re.sub(r"\s+", " ", text).strip().lower()


def content_tokens(text: str) -> list[str]:
    """Substantive tokens of a unit: placeholders removed, lowercased word runs,
    stopwords dropped. Apostrophes are stripped so "don't" -> "dont" (matching
    banned.py's tokenizer family)."""
    norm = normalize(_strip_placeholders(text))
    toks = [w.replace("'", "") for w in _WORD_RE.findall(norm)]
    return [t for t in toks if t and t not in _STOPWORDS]


def all_tokens(text: str) -> set[str]:
    """Every lowercased word-run token (stopwords INCLUDED, placeholders removed).
    Used to build an approved string's coverage vocabulary — keeping stopwords on
    the APPROVED side never hurts (it can only let a real unit match), and avoids
    a sourced sentence being penalized for a connective the approved copy used."""
    norm = normalize(_strip_placeholders(text))
    return {w.replace("'", "") for w in _WORD_RE.findall(norm)}


# --------------------------------------------------------------------------- #
# Allowlist — generic, non-claim boilerplate that is honest by nature and must
# not be flagged. These assert nothing about the practice's efficacy, history,
# or credentials. Two kinds:
#   * EXACT short labels (nav, form, generic UI), matched on the normalized unit.
#   * SUBSTRING safety/disclosure lines (the crisis numbers especially) — these
#     MUST always be allowed; refusing a 988 / 741741 crisis line would be the
#     opposite of safe. Matched as normalized substrings.
# Kept intentionally small and auditable. NOT a place to whitelist real claims.
# --------------------------------------------------------------------------- #
_ALLOWLIST_EXACT = frozenset(normalize(s) for s in {
    "home", "about", "approach", "method", "the work", "journey", "fees",
    "writing", "essays", "contact", "blog", "faq", "services", "work with me",
    "get in touch", "book a consult", "request a consult", "schedule a consult",
    "free consult", "menu", "close", "back", "next", "previous", "read more",
    "learn more", "send", "submit", "send message", "name", "email", "phone",
    "message", "state", "other", "your name", "your email", "telehealth",
    "in person", "in-person", "online therapy", "privacy policy", "terms",
    "all rights reserved", "skip to content", "loading",
})

_ALLOWLIST_SUBSTRINGS = tuple(normalize(s) for s in (
    # Crisis / safety lines — ALWAYS honest, ALWAYS allowed.
    "988", "741741", "text home to 741741", "call or text 988",
    "suicide & crisis lifeline", "crisis text line", "988 lifeline",
    "if you are in crisis", "in an emergency call 911", "call 911",
    # Standing AI-disclosure / honesty-footer phrasing the engine ships.
    "created with ai assistance from shaula",
    "reviewed and approved by",
    # Generic, claimless availability/telehealth framing.
    "telehealth", "accepting consult requests", "currently accepting",
))


def _is_allowlisted(norm_unit: str) -> bool:
    if norm_unit in _ALLOWLIST_EXACT:
        return True
    for sub in _ALLOWLIST_SUBSTRINGS:
        if sub and sub in norm_unit:
            return True
    return False


# --------------------------------------------------------------------------- #
# HTML -> visible text (with structural line breaks at block tags).
# --------------------------------------------------------------------------- #
class _VisibleTextExtractor(HTMLParser):
    """Collect human-visible text, dropping <script>/<style>/<template> bodies
    and inserting a newline at block-level boundaries so segmentation can treat
    headings / list items / paragraphs as separate units. Inline tags keep their
    text joined. Also captures a few claim-bearing ATTRIBUTES (img alt, input
    placeholder, aria-label) since a fabricated claim can hide there too."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._suppress_depth = 0  # inside a drop-content tag

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _DROP_CONTENT_TAGS:
            self._suppress_depth += 1
            return
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")
        # Claim-bearing attribute text.
        if self._suppress_depth == 0:
            ad = dict((k.lower(), v or "") for k, v in attrs)
            for key in ("alt", "placeholder", "aria-label", "title"):
                if ad.get(key):
                    self._parts.append(" " + ad[key] + " ")

    def handle_startendtag(self, tag, attrs):
        # e.g. <br/>, <img .../>, <input .../>
        self.handle_starttag(tag, attrs)
        t = tag.lower()
        if t in _DROP_CONTENT_TAGS:
            # self-closing script/style carries no body; undo the depth bump.
            self._suppress_depth = max(0, self._suppress_depth - 1)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _DROP_CONTENT_TAGS:
            self._suppress_depth = max(0, self._suppress_depth - 1)
            return
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data):
        if self._suppress_depth == 0 and data:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def extract_visible_text(html_src: str) -> str:
    """Return the human-visible text of an HTML document, with block-level line
    breaks preserved for segmentation and script/style bodies removed."""
    parser = _VisibleTextExtractor()
    parser.feed(html_src or "")
    parser.close()
    return parser.text()


# --------------------------------------------------------------------------- #
# Segmentation into claim-bearing units.
# --------------------------------------------------------------------------- #
# Split first on the structural newlines the extractor inserted, then on
# sentence punctuation WITHIN a line. A unit is one sentence / list item /
# heading. We keep raw (un-normalized) units for honest offender reporting and
# normalize lazily during classification.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def segment_units(visible_text: str) -> list[str]:
    units: list[str] = []
    for line in (visible_text or "").split("\n"):
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        for sentence in _SENTENCE_SPLIT.split(line):
            s = sentence.strip()
            if s:
                units.append(s)
    return units


# --------------------------------------------------------------------------- #
# Approved corpus.
# --------------------------------------------------------------------------- #
class ApprovedCorpus:
    """The approved content set, prepared for coverage checks.

    Holds, per approved source string, the set of its tokens; a candidate unit is
    COVERED when some single approved string's token set contains a high-enough
    fraction of the unit's content tokens. We match against the strongest single
    source (max over sources) rather than the global union, so an injected
    sentence cannot be "covered" by scavenging one word each from many unrelated
    approved strings.
    """

    def __init__(self, token_values: list[str], block_texts: list[str]) -> None:
        self._sources: list[set[str]] = []
        self._raw_sources: list[str] = []  # for debugging / receipts
        for s in list(token_values) + list(block_texts):
            toks = all_tokens(s)
            if toks:
                self._sources.append(toks)
                self._raw_sources.append(s)
        # A global bag too, used only for the short-unit safety net (a short unit
        # all of whose tokens are approved-somewhere is not a fabrication).
        self._global: set[str] = set()
        for toks in self._sources:
            self._global |= toks

    @property
    def source_count(self) -> int:
        return len(self._sources)

    def coverage(self, unit_content_tokens: list[str]) -> float:
        """Best fraction of the unit's content tokens found in any one approved
        source string. 1.0 == fully covered; 0.0 == nothing in common with the
        single best source. Empty unit -> 1.0 (nothing to source)."""
        uniq = set(unit_content_tokens)
        if not uniq:
            return 1.0
        best = 0.0
        for src in self._sources:
            hit = len(uniq & src)
            frac = hit / len(uniq)
            if frac > best:
                best = frac
                if best >= 1.0:
                    break
        return best

    def all_tokens_known(self, unit_content_tokens: list[str]) -> bool:
        uniq = set(unit_content_tokens)
        return bool(uniq) and uniq <= self._global


def build_corpus(
    practice: dict, generated: dict, extra_texts: list[str] | None = None
) -> ApprovedCorpus:
    """Assemble the approved corpus from practice.json + generated.json.

    Token values: every shipped string value of practice.json (``_``-prefixed
    metadata skipped, matching honesty_scan / fill semantics).
    Block texts: for each generated block, the visible text of its ``replace``
    string with its ``{{tokens}}`` resolved against practice.json — i.e. the
    prose as it actually renders. This is what makes a block like ``hero_sub``
    ("Evidence-based work for adults, graduate students, and healthcare workers")
    available to source the corresponding sentence in the finished HTML.

    ``extra_texts`` adds further APPROVED source strings to the corpus. For the
    FIXED-TEMPLATE build path the approved set is larger than practice+generated:
    it also includes the vetted template's own static UI copy (CTAs, contact
    prompts, section ledes authored in the template — identical for every
    practice and already honesty-scanned by prove.sh) and the engine's curated
    content banks (modality names/descriptions/citations, the generic method &
    journey floor). Passing those here lets the gate run honestly over a rendered
    template SPA without crying wolf on its own vetted chrome, while a genuinely
    FOREIGN fabrication (a fake stat's "92", an invented "harvard" credential,
    a "—Jane" testimonial byline) still imports tokens absent from the whole
    approved set and is flagged. Left None, behaviour is unchanged (the 3a/3b
    import/freehand contract, where the candidate's structure is not ours).
    """
    token_values: list[str] = []
    for key, val in practice.items():
        if key.startswith("_"):
            continue
        if isinstance(val, str) and val.strip():
            token_values.append(val)
        elif isinstance(val, list):
            # nested arrays (e.g. career[]) — pull their string leaves
            for item in val:
                if isinstance(item, str) and item.strip():
                    token_values.append(item)
                elif isinstance(item, dict):
                    for v in item.values():
                        if isinstance(v, str) and v.strip():
                            token_values.append(v)

    # A simple token map for resolving {{tokens}} inside block replace strings.
    token_map = {k: v for k, v in practice.items()
                 if not k.startswith("_") and isinstance(v, str)}

    def _resolve(s: str) -> str:
        return re.sub(
            r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}",
            lambda m: token_map.get(m.group(1), m.group(0)),
            s,
        )

    block_texts: list[str] = []
    for spec in (generated.get("blocks") or {}).values():
        replace = spec.get("replace")
        if not isinstance(replace, str) or not replace.strip():
            continue
        resolved = _resolve(replace)
        # The replace strings are HTML/JS fragments; pull their visible text the
        # same way we pull it from the candidate document, then split into the
        # individual rendered strings so each becomes its own source.
        visible = extract_visible_text(resolved)
        for piece in segment_units(visible):
            block_texts.append(piece)
        # Also keep the whole resolved fragment as one source so multi-sentence
        # prose that renders contiguously can match as a block.
        block_texts.append(visible)

    # Extra approved sources (template static UI + engine content banks for the
    # fixed-template path). Each string becomes its own source; multi-sentence
    # strings are ALSO segmented so a single rendered sentence can match one of
    # their sentences directly (same treatment as generated blocks above).
    for extra in (extra_texts or []):
        if not isinstance(extra, str) or not extra.strip():
            continue
        visible = extract_visible_text(extra)
        for piece in segment_units(visible):
            block_texts.append(piece)
        block_texts.append(visible)

    return ApprovedCorpus(token_values, block_texts)


def approved_template_extras(app_js: str = "") -> list[str]:
    """Approved source strings for the FIXED-TEMPLATE build path, beyond the
    (practice, generated) corpus — pass as ``extra_texts`` to gate/build_corpus.

    The vetted private-practice template renders content from two approved
    origins the practice+generated corpus does not contain on its own:
      * the engine's curated content banks (``engine/citations.py``) — modality
        names / plain-language descriptions / the REAL foundational citations,
        plus the generic method & journey floor prose. All honesty-reviewed,
        identical for every practice, and the SAME source the site renders from.
      * the template's own static UI copy (CTAs, contact prompts, section ledes
        authored in ``app.js`` — also identical per practice, already scanned for
        banned language by prove.sh). Supplied via ``app_js`` (the built site's
        app.js); omit it to include only the engine banks.

    Why this is safe: extra approved sources can only RAISE coverage / widen the
    known vocabulary, so they can never manufacture a false offender — only let
    honest vetted chrome pass. The banned-language gate runs independently of the
    corpus, so a smuggled efficacy claim is still caught. Do NOT feed arbitrary
    candidate HTML here for the 3a/3b path — there the candidate's structure is
    untrusted and coverage must stay strict.
    """
    extras: list[str] = []
    for m in citations.MODALITIES.values():
        extras += [m.get("name", ""), m.get("what", ""),
                   m.get("citation", ""), m.get("tag", "")]
    for step in citations.GENERIC_METHOD_STEPS:
        extras += [s for s in step if isinstance(s, str)]
    for phase in citations.GENERIC_JOURNEY_PHASES:
        extras += [s for s in phase if isinstance(s, str)]
    extras += [v for v in citations.CREDENTIAL_FULL.values() if isinstance(v, str)]
    if app_js and app_js.strip():
        extras.append(extract_visible_text(app_js))
    return [e for e in extras if e and e.strip()]


# --------------------------------------------------------------------------- #
# The gate.
# --------------------------------------------------------------------------- #
class Offender:
    """One reason the HTML fails the gate."""

    KIND_UNSOURCED = "unsourced-claim"
    KIND_BANNED = "banned-language"

    def __init__(self, kind: str, text: str, detail: str) -> None:
        self.kind = kind
        self.text = text
        self.detail = detail

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"Offender({self.kind!r}, {self.text!r}, {self.detail!r})"

    def as_dict(self) -> dict:
        return {"kind": self.kind, "text": self.text, "detail": self.detail}


def check_html(
    html_src: str,
    corpus: ApprovedCorpus,
    *,
    coverage_threshold: float = DEFAULT_COVERAGE_THRESHOLD,
    min_claim_tokens: int = MIN_CLAIM_TOKENS,
) -> list[Offender]:
    """Return the list of offenders in ``html_src`` (empty == provenance-clean).

    Two independent offender classes:
      * BANNED-LANGUAGE — any affirmative banned-claim phrase in the visible
        text, via the canonical ``banned.lint`` (reused, negation-aware). Refused
        regardless of whether the phrase also appears in approved content.
      * UNSOURCED-CLAIM — a claim-bearing unit whose content tokens are not
        sufficiently covered by any single approved source and that is not on the
        boilerplate allowlist.
    """
    offenders: list[Offender] = []
    visible = extract_visible_text(html_src)

    # 1) Banned-language gate over the whole visible text (REUSED engine gate).
    for pattern in banned.lint(visible):
        offenders.append(Offender(
            Offender.KIND_BANNED,
            _quote_banned(visible, pattern),
            f"matches banned pattern /{pattern}/",
        ))

    # 2) Per-unit provenance coverage.
    for unit in segment_units(visible):
        norm = normalize(unit)
        if not norm:
            continue
        if _is_allowlisted(norm):
            continue
        ctoks = content_tokens(unit)
        if len(ctoks) < min_claim_tokens:
            # Too short to be a standalone claim; coverage not asserted. (Banned
            # gate above still applies to the whole text, so a short banned line
            # is still caught.)
            continue
        cov = corpus.coverage(ctoks)
        if cov >= coverage_threshold:
            continue
        # Secondary path — RECOMBINATION of approved vocabulary. A unit whose
        # EVERY content token appears somewhere in the approved set, but not
        # concentrated in a single source (so single-source coverage fell short),
        # is honest token-recombination: the static SPA masthead/title/footer
        # ("North Star Counseling — Home", "© 2026 North Star Counseling",
        # "Maya Restrepo, LPC · Private Psychotherapy · Colorado") glue approved
        # names with generic connectors. We ACCEPT it because it introduces NO
        # new claim-word — every fabrication in the wild instead imports
        # non-approved tokens (a stat "92", a school "harvard", a name "jane").
        # DOCUMENTED LIMIT: this is exactly the recombination seam a determined
        # adversary could exploit to assemble approved fragments into a new false
        # whole; v1 coverage cannot tell honest glue from adversarial assembly.
        # v2 entailment closes it. The banned-language gate still fires here.
        if corpus.all_tokens_known(ctoks):
            continue
        offenders.append(Offender(
            Offender.KIND_UNSOURCED,
            unit,
            f"coverage {cov:.2f} < {coverage_threshold:.2f}; "
            f"{len(ctoks)} content tokens, {_unknown_count(corpus, ctoks)} "
            f"not present in approved content at all",
        ))
    return offenders


def _unknown_count(corpus: "ApprovedCorpus", ctoks: list[str]) -> int:
    return len([t for t in set(ctoks) if t not in corpus._global])


def _quote_banned(visible: str, pattern: str) -> str:
    """Best-effort: quote the affirmative sentence that tripped a banned pattern,
    so the offender names the offending text rather than just the regex."""
    for unit in segment_units(visible):
        for m in re.finditer(pattern, unit, re.I):
            if not banned.is_negated(unit, m.start()):
                return unit
    return f"(banned pattern {pattern})"


# --------------------------------------------------------------------------- #
# Public convenience API.
# --------------------------------------------------------------------------- #
def gate(
    html_src: str,
    practice: dict,
    generated: dict,
    *,
    extra_texts: list[str] | None = None,
    coverage_threshold: float = DEFAULT_COVERAGE_THRESHOLD,
    min_claim_tokens: int = MIN_CLAIM_TOKENS,
) -> list[Offender]:
    """One-call gate: build the corpus and check the HTML. Returns offenders."""
    corpus = build_corpus(practice, generated, extra_texts=extra_texts)
    return check_html(
        html_src, corpus,
        coverage_threshold=coverage_threshold,
        min_claim_tokens=min_claim_tokens,
    )


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def _load_json(path: str, label: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        print(f"provenance.py: {label} not found: {path}", file=sys.stderr)
        raise SystemExit(2)
    except json.JSONDecodeError as exc:
        print(f"provenance.py: {label} is not valid JSON ({path}): {exc}",
              file=sys.stderr)
        raise SystemExit(2)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Claim-provenance gate for arbitrary / freehand HTML. "
                    "Proves every visible claim traces to approved content "
                    "(practice.json token values + generated.json block text); "
                    "rejects un-sourced claims and banned marketing language.",
    )
    ap.add_argument("--html", required=True,
                    help="Path to the finished/arbitrary HTML file to check.")
    ap.add_argument("--practice", required=True,
                    help="Path to practice.json (approved linted token values).")
    ap.add_argument("--generated", required=True,
                    help="Path to generated.json (approved generated block text).")
    ap.add_argument("--coverage-threshold", type=float,
                    default=DEFAULT_COVERAGE_THRESHOLD,
                    help=f"Min token-coverage to count a unit as sourced "
                         f"(default {DEFAULT_COVERAGE_THRESHOLD}).")
    ap.add_argument("--min-claim-tokens", type=int, default=MIN_CLAIM_TOKENS,
                    help=f"Units with fewer content tokens are treated as labels "
                         f"(default {MIN_CLAIM_TOKENS}).")
    ap.add_argument("--json", action="store_true",
                    help="Emit the offender list as JSON instead of text.")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.html):
        print(f"provenance.py: HTML not found: {args.html}", file=sys.stderr)
        return 2
    with open(args.html, encoding="utf-8") as fh:
        html_src = fh.read()
    practice = _load_json(args.practice, "practice.json")
    generated = _load_json(args.generated, "generated.json")

    offenders = gate(
        html_src, practice, generated,
        coverage_threshold=args.coverage_threshold,
        min_claim_tokens=args.min_claim_tokens,
    )

    if args.json:
        print(json.dumps({
            "html": args.html,
            "ok": not offenders,
            "offenders": [o.as_dict() for o in offenders],
        }, indent=2, ensure_ascii=False))
    else:
        if not offenders:
            print(f"PASS  {args.html} — every claim traces to approved content "
                  f"(provenance-clean).")
        else:
            print(f"FAIL  {args.html} — {len(offenders)} un-sourced / banned "
                  f"claim(s):")
            for o in offenders:
                print(f"  [{o.kind}] {o.text!r}")
                print(f"      → {o.detail}")
            print(f"\nREJECTED: {len(offenders)} offender(s). This HTML cannot "
                  f"be published as-is — every claim must trace to approved "
                  f"content.", file=sys.stderr)

    return 1 if offenders else 0


if __name__ == "__main__":
    raise SystemExit(main())
