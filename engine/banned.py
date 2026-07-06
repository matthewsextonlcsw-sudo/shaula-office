#!/usr/bin/env python3
r"""banned — the single source of truth for Shaula's banned-language gate.

Every honesty surface in the system refuses to publish the SAME set of marketing
claims (fabricated stats, efficacy claims, superlatives, testimonial language).
That list used to be defined or hand-copied in five places — engine/generate.py,
engine/geo.py, svc/honesty.py, scripts/honesty_scan.py, and the two proof scripts
(scripts/prove.sh, scripts/e2e_synthetic.sh) — which could silently DRIFT apart.
This module is the ONE definition they all derive from. tests/test_banned.py pins
that every consumer's effective banned set is this module's, so they cannot diverge.

TWO TIERS, because the gate runs against two different kinds of text:

  * VALUE tier (``BANNED_PATTERNS`` / ``lint`` / ``VALUE_REGEX``) — the FULL list,
    applied to TEXT VALUES: operator input (honesty_scan.py), every generated block
    (generate.py), and the GEO/SEO structured-data pass (geo.py). This is the
    primary gate; there is no CSS here to confuse the patterns.

  * RENDER tier (``RENDER_BANNED_PATTERNS`` / ``render_lint`` /
    ``render_banned_shell_regex``) — a deliberately CSS-safe SUBSET, applied to
    RENDERED OUTPUT (app.js / index.html / llms.txt) by the proof scripts. It omits
    patterns that false-positive on CSS-in-JS:
      - ``\b\d{1,3}\s?%``  would hit ``width:100%``
      - ``#1\b``           would hit hex colors like ``#1a2b3c``
    and also ``\bnumber one\b``, which carries no CSS risk but is ALREADY enforced
    on the very same rendered site by geo.py at the value level (geo runs before
    the render scan), so it belongs in the value tier, not this safety-net subset.

The VALUE tier is a strict superset of the historical per-file lists. The one
behavioral consolidation: ``\bnumber one\b`` was previously enforced ONLY by
geo.py's regex. Hoisting it here keeps geo's protection when geo derives from this
module, AND closes the same gap in generate.py / honesty_scan.py — it is the
spelled-out form of the already-banned ``#1``. Nothing is relaxed; one phrase is
now enforced in more places.

Pure stdlib, dependency-free leaf module — safe for any engine / svc / script to
import without a cycle. NO PHI: these are marketing-claim patterns only.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# VALUE tier — the full banned-language list, applied to text values.
# Order is preserved for stable, human-readable lint output and receipts.
# --------------------------------------------------------------------------- #
BANNED_PATTERNS: list[str] = [
    r"\b\d{1,3}\s?%",          # any percentage claim
    r"\bproven\b",
    r"\bguarantee",            # guarantee / guaranteed / guarantees
    r"studies show",
    r"research proves",
    r"clinically proven",
    r"\btestimonial",
    r"\bcure\b",
    r"\bcures\b",
    r"\bmiracle",
    r"#1\b",
    r"\bbest therapist",
    r"\bworld[- ]class\b",
    r"\bnumber one\b",         # spelled-out form of "#1" (hoisted from geo.py)
]

# --------------------------------------------------------------------------- #
# RENDER tier — CSS-safe subset for scanning rendered output. See module docstring
# for why each excluded pattern is excluded. Derived (not re-listed) so it cannot
# drift from the value tier.
# --------------------------------------------------------------------------- #
_RENDER_EXCLUDED: frozenset[str] = frozenset({
    r"\b\d{1,3}\s?%",   # CSS false-positive: width:100%
    r"#1\b",            # CSS false-positive: #1a2b3c hex colors
    r"\bnumber one\b",  # already enforced at the value level by geo on the same site
})
RENDER_BANNED_PATTERNS: list[str] = [p for p in BANNED_PATTERNS if p not in _RENDER_EXCLUDED]

# Singleton compiled value-tier regex. geo.py consumes this for .search()/.findall();
# compiling once keeps the GEO pass cheap and guarantees it uses the canonical set.
VALUE_REGEX = re.compile("|".join(BANNED_PATTERNS), re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Negation awareness (VALUE tier only) ---------------------------------------- #
# A banned word is only a marketing CLAIM when asserted affirmatively. The SAME
# word inside a disclaimer — "not a guarantee", "rather than cures" — is the
# OPPOSITE of a claim. Templates explicitly ask staff to WRITE disclaimers and to
# FLAG claims a clinician must verify, so a pure substring linter refuses its own
# safety language (this is exactly what failed deck-engine at step 0). lint()
# therefore exempts a hit a negator GOVERNS: scanning left within the sentence, a
# negator is reached before any "scope breaker" — a fresh subject / assertion
# verb / clause that would start a new, affirmative predicate. The asymmetry is
# deliberate and one-directional: it only ever REMOVES false positives. An
# affirmative claim, or a negator shielded by a new predicate ("we don't just
# help — we guarantee results"), still trips — no false negative is introduced.
#
# The RENDER tier stays a DUMB substring match: render_lint feeds a `grep -iE`
# scan and tests/test_banned.py pins Python==grep, so this logic must never leak
# into it. VALUE_REGEX (geo's compiled scan over rendered structured data) is
# likewise left untouched — that surface keeps its conservative substring match.
_WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
_SENT_BOUND = re.compile(r"[.!?\n]")
_NEGATORS: frozenset[str] = frozenset({
    "not", "no", "never", "without", "cannot", "nor", "neither", "none",
    "dont", "doesnt", "didnt", "isnt", "arent", "wasnt", "werent",
    "wont", "wouldnt", "cant", "couldnt", "shouldnt", "havent", "hasnt", "aint",
})
# Two-word negators sitting immediately before the banned token.
_NEG_BIGRAMS: frozenset[tuple[str, str]] = frozenset({
    ("rather", "than"), ("instead", "of"), ("as", "opposed"),
    ("free", "of"), ("free", "from"),
})
# A scope breaker ends the negator's reach: a new subject or assertion verb
# starts a fresh predicate the earlier negator no longer governs. Reaching one
# (while scanning left, before any negator) means the word is NOT negated.
_SCOPE_BREAKERS: frozenset[str] = frozenset({
    "we", "i", "you", "they", "he", "she", "our", "my", "your", "their", "its",
    "offer", "offers", "offering", "provide", "provides", "promise", "promises",
    "deliver", "delivers", "ensure", "ensures", "guarantee", "guarantees",
    "give", "gives", "claim", "claims", "and", "but", "or", "so", "because",
    "yet",
})


def _tokens_before(text: str, start: int) -> list[str]:
    """Words from the start of the banned token's sentence up to ``start``,
    lowercased and apostrophe-stripped (so "don't" -> "dont")."""
    bound = 0
    for m in _SENT_BOUND.finditer(text, 0, start):
        bound = m.end()
    left = text[bound:start].lower().replace("’", "'")
    return [w.replace("'", "") for w in _WORD_RE.findall(left)]


def is_negated(text: str, start: int) -> bool:
    """True when the banned token at ``text[start]`` is GOVERNED by a negator
    (a disclaimer / denied claim) rather than asserted. Scans left within the
    sentence and returns True iff a negator is met before any scope breaker.

    Public so the narration layer (svc/honesty.py) can quote the AFFIRMATIVE
    sentence instead of a disclaimer that merely shares the banned word.
    """
    toks = _tokens_before(text, start)
    for i in range(len(toks) - 1, -1, -1):
        tok = toks[i]
        if tok in _NEGATORS:
            return True
        if i > 0 and (toks[i - 1], tok) in _NEG_BIGRAMS:
            return True
        if tok in _SCOPE_BREAKERS:
            return False
    return False


def lint(text: str) -> list[str]:
    """Return the VALUE-tier banned patterns AFFIRMATIVELY present in ``text``
    (empty == clean). Negation-aware: a banned word a negator governs
    ("not a guarantee", "rather than cures") is a disclaimer and does not count,
    while an affirmative claim still trips (see the negation note above).

    This is THE box-wide honesty linter: generate.py re-exports it as
    ``generate.lint`` and every caller (build_practice, staff, gemini, brain,
    honesty_scan, validate_survey, the workflow builder) routes through it.
    """
    text = text or ""
    hits: list[str] = []
    for pattern in BANNED_PATTERNS:
        for m in re.finditer(pattern, text, re.I):
            if not is_negated(text, m.start()):
                hits.append(pattern)
                break  # one affirmative occurrence is enough; keep list order
    return hits


def render_lint(text: str) -> list[str]:
    """Return the RENDER-tier (CSS-safe subset) banned patterns found in ``text``."""
    return [p for p in RENDER_BANNED_PATTERNS if re.search(p, text, re.I)]


def render_banned_shell_regex() -> str:
    """The RENDER-tier patterns as a single ``grep -E`` alternation.

    scripts/prove.sh and scripts/e2e_synthetic.sh scan rendered output with
    ``grep -riE`` using EXACTLY this string (derived at run time via
    ``python3 -c '... print(banned.render_banned_shell_regex())'``), so the shell
    gate and the Python gate cannot disagree. BSD and GNU ``grep -E`` both honor
    ``\b`` word boundaries, matching Python's semantics for these patterns.
    """
    return "|".join(RENDER_BANNED_PATTERNS)


if __name__ == "__main__":  # tiny self-check / introspection aid
    import json

    print(json.dumps({
        "value_tier": BANNED_PATTERNS,
        "render_tier": RENDER_BANNED_PATTERNS,
        "render_excluded": sorted(_RENDER_EXCLUDED),
        "render_shell_regex": render_banned_shell_regex(),
    }, indent=2))
