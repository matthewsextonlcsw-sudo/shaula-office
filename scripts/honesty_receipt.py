#!/usr/bin/env python3
"""Honesty receipt — the concierge-beta differentiator (spec shaula#20, deliverable C).

A short, human-readable sheet per built site: **"here is what Shaula refused to say
about you, and why."** It answers the therapist's #1 fear — being lied about — by
showing exactly what the honesty engine *omitted*, what it *refused to fabricate*, and
what it *assumed*. This is the trust moment that converts the IP into a felt thing.

GENERATED, not hand-assembled. It renders ONLY what the engine actually emitted:

  * ``generate()``'s ``_refusals`` manifest (stream 1) — modalities resolved vs. listed,
    the generic-method floor, the banned-language policy, and the lint-clean attestation;
  * ``build_practice``'s ``_assumed`` record — neutral defaults that read as commitments,
    flagged rather than presented as fact.

It runs the SAME deterministic ``generate()`` the build used (``brain=None``), so the
receipt cannot drift from the published site. Banned-language patterns are rendered in
plain English by REUSING ``svc/honesty`` — never a second linter, never a re-implemented
translation table.

NO PHI by construction: every field is the provider's own professional information.
Stdlib + sibling modules only; no network, no LLM, no credentials.

Usage:
    honesty_receipt.py --practice <practice.json> [--out <receipt.md>] [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

# scripts/ is a sibling of engine/ and svc/ — wire both onto the path so the
# receipt reuses the canonical engine output and the canonical plain-language
# translations (single source of truth; the two can never drift).
_ROOT = pathlib.Path(__file__).resolve().parent.parent
for _sub in ("engine", "svc"):
    _p = _ROOT / _sub
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import generate as G  # noqa: E402
import honesty as H  # noqa: E402  (svc/honesty — plain-language narration, REUSED)

_BLOCKS_PATH = _ROOT / "engine" / "template_blocks.json"


def build_refusals(practice: dict) -> dict:
    """Run the SAME deterministic generate() the build used and return its
    ``_refusals`` manifest. brain=None → no network, no credentials, $0."""
    blocks = json.loads(_BLOCKS_PATH.read_text(encoding="utf-8"))
    return G.generate(practice, blocks)["_refusals"]


def _plain_banned(patterns: list[str]) -> list[str]:
    """Render the engine's banned-language patterns as deduped plain English by
    reusing svc/honesty. Several regexes (e.g. ``\\bcure\\b`` / ``\\bcures\\b``)
    translate to the same plain phrase — collapse those so the receipt reads once."""
    seen: set[str] = set()
    out: list[str] = []
    for pat in patterns:
        plain = H._plain(pat)
        if plain not in seen:
            seen.add(plain)
            out.append(plain)
    return out


def receipt_markdown(practice: dict, refusals: dict, *,
                     business_name: str = "", generated_on: str = "") -> str:
    """Pure renderer — the receipt for one built site. No IO, no clock; the caller
    supplies ``generated_on`` so this stays deterministic and testable."""
    name = business_name or practice.get("business_name") or practice.get("owner_name") or "your practice"
    listed = refusals.get("modalities_listed", [])
    shown = refusals.get("modalities_shown", [])
    dropped = refusals.get("modalities_dropped_unknown", [])
    capped = refusals.get("modalities_capped", [])
    assumed = practice.get("_assumed", []) or []

    L: list[str] = []
    L.append(f"# Shaula honesty receipt — {name}")
    L.append("")
    L.append("*What Shaula published about you, what it refused to say, and why.*")
    if generated_on:
        L.append("")
        L.append(f"Generated: {generated_on}")
    L.append("")

    # ── Modalities: shown vs. held back ──────────────────────────────────────
    L.append("## Modalities — what we showed, and what we held back")
    L.append("")
    L.append(f"You listed: {', '.join(listed) if listed else '(none)'}.")
    L.append("")
    if shown:
        L.append(f"- **Shown, each with a real foundational citation:** {', '.join(shown)}.")
    if capped:
        L.append(
            f"- **Verified but not displayed** (the homepage caps at four): "
            f"{', '.join(capped)}."
        )
    if dropped:
        L.append(
            f"- **Held back — no verifiable foundational source in our catalog:** "
            f"{', '.join(dropped)}. Shaula omits a modality rather than invent a "
            f"citation for it."
        )
    if not dropped and not capped:
        L.append("- Nothing was held back — every modality you listed resolved to a real citation.")
    L.append("")

    # ── What Shaula refused to fabricate ─────────────────────────────────────
    L.append("## What Shaula refused to fabricate")
    L.append("")
    L.append(
        "- **No invented “signature method.”** Your site presents a generic, "
        "evidence-informed process. Shaula will not brand a proprietary method you did "
        "not name."
    )
    L.append(
        "- **No efficacy, outcome, or superlative claims.** This site cleared Shaula’s "
        "banned-language gate, so it is honest by construction — had any of the "
        "following appeared anywhere on the page, **nothing would have been published:**"
    )
    for plain in _plain_banned(refusals.get("banned_language_enforced", [])):
        L.append(f"  - {plain}")
    L.append("")

    # ── Assumptions (defaults, flagged) ──────────────────────────────────────
    L.append("## Assumptions we made (defaults, not facts — confirm before you rely on them)")
    L.append("")
    if assumed:
        L.append(
            "Where you did not give an answer, Shaula used a neutral default and flagged "
            "it here rather than inventing a fact:"
        )
        L.append("")
        for a in assumed:
            label = a.get("label", a.get("field", "")).strip()
            value = str(a.get("value", "")).strip()
            src = a.get("from", "").strip()
            tail = f" *(from {src})*" if src else ""
            L.append(f"- **{label}:** {value}{tail}")
    else:
        L.append("None — you supplied every field; nothing was defaulted.")
    L.append("")

    # ── Attestation ──────────────────────────────────────────────────────────
    L.append("## Attestation")
    L.append("")
    if refusals.get("lint_clean"):
        L.append(
            "- The build **succeeded**, which means it is lint-clean by construction: a "
            "banned claim would have aborted it before a single line was written."
        )
    else:  # defensive — generate() only returns past the gate, so this should never show
        L.append(
            "- ⚠️ This receipt was generated WITHOUT a verified lint-clean "
            "attestation. Do not publish until the build is re-run clean."
        )
    L.append(
        "- **0 PHI.** This page and this receipt contain only your own professional "
        "information — no client or patient data exists anywhere in what Shaula "
        "generated."
    )
    L.append("")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate a Shaula honesty receipt from a practice.json.")
    ap.add_argument("--practice", required=True, help="path to the built practice.json")
    ap.add_argument("--out", help="write the receipt here (default: stdout)")
    ap.add_argument("--business", default="", help="override the business name in the header")
    ap.add_argument("--date", default="", help="generation date (YYYY-MM-DD); default: today")
    args = ap.parse_args(argv)

    try:
        practice = json.loads(pathlib.Path(args.practice).read_text(encoding="utf-8"))
    except OSError as e:
        sys.stderr.write(
            f"honesty_receipt: cannot open --practice {args.practice!r}: {e}\n"
        )
        return 2
    except json.JSONDecodeError as e:
        sys.stderr.write(
            f"honesty_receipt: --practice {args.practice!r} is not valid JSON ({e}).\n"
            "  It must be the practice.json the build wrote "
            "(concierge_build.py emits it under the build's temp dir).\n"
        )
        return 2
    refusals = build_refusals(practice)
    generated_on = args.date
    if not generated_on:
        import datetime
        generated_on = datetime.date.today().isoformat()
    md = receipt_markdown(practice, refusals, business_name=args.business, generated_on=generated_on)

    if args.out:
        pathlib.Path(args.out).write_text(md, encoding="utf-8")
        print(f"honesty receipt written -> {args.out}")
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
