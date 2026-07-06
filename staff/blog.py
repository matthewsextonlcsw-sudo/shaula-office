"""staff/blog.py — BlogScaffold: the first live AI-staff member.

WHAT IT IS (and what it deliberately is NOT):
  * IT IS an honest editorial *scaffold / content brief*. From a practice dict it
    produces working title options, a section-by-section outline with a job and
    writing prompts per section, a real "further reading" list drawn from the
    cited modality catalog (engine/citations.py), a meta description, GEO
    (generative-engine-optimization) angles, and voice notes — everything a
    person (or, later, an on-device model) needs to WRITE the post.
  * IT IS NOT a finished, publishable blog post. Authoring polished prose in the
    practice's own voice is an LLM-enrichment deliverable (the base-class
    `synthesize()` seam, D3). The deterministic floor refuses to fake that,
    exactly as the website engine refuses to fake a branded method (D5).

Why ship a brief instead of a post? Because the brief is real, useful, and
honest with zero LLM dependency, and it never pretends to be a final draft. The
dashboard labels this capability precisely: "Blog brief builder", not "drafts
finished posts."

No PHI: it reads only the practice dict (operator-supplied / synthetic).

CLI:
    python3 -m staff.blog --survey survey.json   [--topic "..."] [--json] [--use-ollama]
    python3 -m staff.blog --practice practice.json [--topic "..."] [--json]
    python3 -m staff.blog --demo                  [--topic "..."] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

try:  # normal: imported as part of the `staff` package
    from .base import StaffHonestyError, StaffTask
except ImportError:  # fallback: run as a loose script
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from staff.base import StaffHonestyError, StaffTask

import citations as C  # noqa: E402  (engine dir is on sys.path via staff.base)


# --------------------------------------------------------------------------- #
# Small text helpers (kept local so this module is self-contained and does not
# depend on private functions in the website engine).
# --------------------------------------------------------------------------- #
_SMALL = {"and", "or", "of", "the", "a", "an", "for", "to", "in",
          "on", "with", "at", "by", "but", "nor", "vs"}


def _split(s) -> list[str]:
    """Split a comma/semicolon/slash list into trimmed, non-empty parts."""
    if isinstance(s, (list, tuple)):
        return [str(x).strip() for x in s if str(x).strip()]
    return [p.strip() for p in re.split(r"[,;/]", s or "") if p.strip()]


def _title(s: str) -> str:
    """Title-case, keeping small words lowercase (except first) and preserving
    existing all-caps acronyms (EMDR, CBT)."""
    words = (s or "").split()
    out = []
    for i, w in enumerate(words):
        if w.isupper() and len(w) > 1:
            out.append(w)
            continue
        lw = w.lower()
        if i > 0 and lw in _SMALL:
            out.append(lw)
        else:
            out.append("-".join((p[:1].upper() + p[1:]) if p else p
                                for p in lw.split("-")))
    return " ".join(out)


def _clip(s: str, n: int) -> str:
    """Clip to <= n chars on a word boundary, no trailing punctuation."""
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= n:
        return s
    cut = s[:n].rstrip()
    if " " in cut:
        cut = cut[:cut.rfind(" ")].rstrip()
    return cut.rstrip(" ,.;:-—")


def _is_oon(practice: dict) -> bool:
    blob = " ".join([
        practice.get("payment_model", ""),
        practice.get("payment_model_short", ""),
        practice.get("practice_model", ""),
    ]).lower()
    if "in-network" in blob or "in network" in blob:
        return False
    return "out" in blob


class BlogScaffold(StaffTask):
    """Build an honest editorial brief for one blog post from a practice dict."""

    id = "blog"
    title = "Blog brief"
    produces_phi = False

    # ----------------------------------------------------------------- floor
    def floor(self, practice: dict, *, topic: str | None = None, **_) -> dict:
        specialties = _split(practice.get("specialties")) or ["the work"]
        topic_clean = (topic or "").strip()
        primary = topic_clean or specialties[0]
        primary_t = _title(primary)
        primary_l = primary.lower()

        biz = practice.get("business_name", "this practice")
        owner = practice.get("owner_name", "the therapist")
        cred = practice.get("credential", "")
        location = practice.get("location", "")
        populations = _split(practice.get("populations")) or ["adults"]
        # a non-generic audience word, if the practice named one
        audience = next((p for p in populations if p.lower() != "adults"),
                        populations[0])
        mods = C.resolve_modalities(practice.get("modalities", ""))
        mod_names = [m["name"] for m in mods]
        oon = _is_oon(practice)
        session_length = practice.get("session_length", "")
        consult_length = practice.get("consult_length") or "20-minute"

        # -- working title options (honest: no outcomes, no superlatives) ---
        titles = [
            f"What {primary_l} actually looks like — and why it's not a character flaw",
            f"{primary_t}: what tends to keep it going",
            f"What helps with {primary_l}, and what the work really involves",
            f"Therapy for {primary_l}: what to expect",
        ]
        if audience.lower() != "adults":
            titles.insert(2, f"{primary_t} in {audience.lower()}: a clinician's plain-language guide")
        if mod_names:
            titles.append(f"How {mod_names[0]} is used for {primary_l}")
        titles = titles[:5]

        # -- outline: section heading + the section's job + writing prompts --
        outline = [
            {
                "heading": f"What {primary_l} feels like from the inside",
                "angle": "Validate the reader's experience in concrete, everyday "
                         "terms. Describe, do not diagnose.",
                "prompts": [
                    f"What are 3-4 specific, recognizable ways {primary_l} shows "
                    f"up day to day for {audience.lower()}?",
                    "What does the reader most likely fear it means about them — "
                    "and how do you gently reframe that?",
                ],
            },
            {
                "heading": "What tends to keep it going",
                "angle": "Explain the maintaining cycle in plain language. Make it "
                         "make sense, so it feels changeable rather than shameful.",
                "prompts": [
                    "Describe the loop (trigger → response → short-term relief → "
                    "longer-term cost) without jargon.",
                    "Name one common, well-meant coping move that quietly makes it "
                    "worse — and why.",
                ],
            },
            {
                "heading": "What actually helps",
                "angle": "Connect the approach to the problem. Reference the "
                         "further-reading sources rather than asserting results.",
                "prompts": [
                    (f"How do {', '.join(mod_names[:2])} apply to {primary_l}? "
                     "Describe the mechanism, not a result."
                     if mod_names else
                     f"Which evidence-informed approaches fit {primary_l}, and "
                     "what does each one actually do?"),
                    "What is the honest part most people skip — that change takes "
                    "practice and repetition, not just insight?",
                ],
            },
            {
                "heading": f"What working with {biz} looks like",
                "angle": "Set expectations honestly: logistics, fit, and the "
                         "billing model — no pressure, no promises.",
                "prompts": [
                    (f"How does the {session_length} session and the "
                     f"{'out-of-network / superbill' if oon else 'in-network'} "
                     "billing model actually work for the client?"),
                    f"Who is {owner}, {cred}, a good fit for here — and who would "
                    "be better served by a referral elsewhere?",
                ],
            },
            {
                "heading": "Getting started — and when to reach out sooner",
                "angle": "A clear, low-pressure next step, plus the life-safety "
                         "resources every clinical post should carry.",
                "prompts": [
                    f"Invite the reader to book the {consult_length} consult; say "
                    "what happens on that call so it feels safe.",
                    "State plainly when someone should not wait — and point to the "
                    "crisis lines in the disclaimer below.",
                ],
            },
        ]

        # -- real further reading (omit-on-unknown; never fabricated) --------
        further_reading = [
            {"tag": m["tag"], "name": m["name"], "citation": m["citation"]}
            for m in mods
        ][:5]

        # -- meta description (<=155 chars, honest) --------------------------
        meta_bits = f"{primary_t}: what it looks like, what tends to keep it going, and what helps."
        if location:
            meta_bits += f" From {biz}, {cred} in {location}."
        else:
            meta_bits += f" From {biz}, {cred}."
        meta_description = _clip(meta_bits, 155)

        # -- GEO angles: real questions a person asks an AI assistant --------
        geo_angles = [
            f"What helps with {primary_l}?",
            f"How do I find a therapist for {primary_l}"
            + (f" in {location}?" if location else "?"),
            f"What should I expect in my first therapy session for {primary_l}?",
        ]
        if mod_names:
            geo_angles.append(
                f"What is {mod_names[0]} and is it right for {primary_l}?")
        geo_angles.append(
            "How does therapy billing work if a practice is "
            + ("out-of-network?" if oon else "in-network?"))

        # -- voice notes: how to write it, derived from the practice ---------
        voice_notes = [
            f"Keep {cred} visible and write from clinical experience — but frame "
            "everything as general education, never individual medical advice.",
            f"Speak directly to {audience.lower()}; use second person and concrete "
            "examples over abstractions.",
            ("Be transparent about the out-of-network model and superbills; do not "
             "imply insurance is billed directly."
             if oon else
             "Be clear about the in-network billing model and what the client's "
             "share covers."),
            "Avoid efficacy superlatives, success percentages, client quotes, and "
            "recovery promises — the platform's honesty gate rejects that "
            "language automatically.",
            "This is a brief, not a draft: a person (or a future on-device model) "
            "writes the actual prose from this structure.",
        ]
        if not mod_names:
            voice_notes.append(
                "No recognized modalities were listed, so further reading is "
                "empty — add your modalities in the survey to populate cited "
                "sources.")

        return {
            "_scope": (
                "EDITORIAL SCAFFOLD / CONTENT BRIEF — not a finished post. This "
                "gives the structure, angles, prompts, sourcing, and voice to "
                "write a post; it does not write the prose. Polished drafting in "
                "the practice's voice is a planned on-device-model capability."
            ),
            "topic": primary_t,
            "topic_is_custom": bool(topic_clean),
            "audience": _title(audience),
            "title_options": titles,
            "outline": outline,
            "further_reading": further_reading,
            "meta_description": meta_description,
            "geo_angles": geo_angles,
            "voice_notes": voice_notes,
        }

    # ---------------------------------------------------------------- render
    def render(self, practice: dict, payload: dict) -> str:
        L: list[str] = []
        L.append(f"# Blog brief: {payload['topic']}")
        L.append("")
        L.append(f"> **{payload['_scope']}**")
        L.append("")
        L.append(f"*Practice:* {practice.get('business_name','')} — "
                 f"{practice.get('owner_name','')}, {practice.get('credential','')}  ")
        L.append(f"*Audience:* {payload['audience']}  ")
        L.append(f"*Meta description ({len(payload['meta_description'])} chars):* "
                 f"{payload['meta_description']}")
        L.append("")

        L.append("## Working title options")
        for t in payload["title_options"]:
            L.append(f"- {t}")
        L.append("")

        L.append("## Outline")
        for i, sec in enumerate(payload["outline"], 1):
            L.append(f"### {i}. {sec['heading']}")
            L.append(f"*Section job:* {sec['angle']}")
            L.append("")
            L.append("Writing prompts:")
            for p in sec["prompts"]:
                L.append(f"- {p}")
            L.append("")

        L.append("## Further reading (real, cited sources)")
        if payload["further_reading"]:
            for fr in payload["further_reading"]:
                L.append(f"- **{fr['name']}** ({fr['tag']}) — {fr['citation']}")
        else:
            L.append("- *(none — no recognized modalities listed; add them to "
                     "populate cited sources)*")
        L.append("")

        L.append("## GEO angles (questions to answer directly)")
        for q in payload["geo_angles"]:
            L.append(f"- {q}")
        L.append("")

        L.append("## Voice notes")
        for v in payload["voice_notes"]:
            L.append(f"- {v}")
        L.append("")

        L.append("---")
        L.append(self.disclaimer(practice))
        return "\n".join(L)

    # ------------------------------------------------------------ disclaimer
    def disclaimer(self, practice: dict) -> str:
        biz = practice.get("business_name", "This practice")
        owner = practice.get("owner_name", "")
        cred = practice.get("credential", "")
        who = f"{owner}, {cred}".strip(", ").strip()
        lic = f"{biz} provides services only where {who} is licensed." if who \
            else f"{biz} provides services only where it is licensed."
        return (
            "**Disclaimer.** This article is for general educational purposes "
            "only and is not a substitute for professional diagnosis, treatment, "
            "or advice. Reading it does not create a therapist–client "
            "relationship. If you are in crisis or thinking about harming "
            "yourself, call or text **988** (Suicide & Crisis Lifeline) or text "
            "**HOME** to **741741** (Crisis Text Line); in a life-threatening "
            f"emergency call **911**. {lic}"
        )


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def _load_practice(args) -> dict:
    """Resolve a practice dict from --practice, --survey, or --demo."""
    import build_practice as BP  # engine dir on sys.path via staff.base

    if args.demo:
        return BP.build_practice(dict(BP.DEMO_SURVEY))
    if args.practice:
        with open(args.practice, encoding="utf-8") as fh:
            return json.load(fh)
    if args.survey:
        with open(args.survey, encoding="utf-8") as fh:
            survey = json.load(fh)
        return BP.build_practice(survey)
    raise SystemExit("one of --practice, --survey, or --demo is required")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Build an honest blog brief (scaffold) from a therapist practice.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--survey", help="path to a survey.json (expanded via build_practice)")
    src.add_argument("--practice", help="path to an already-built practice.json")
    src.add_argument("--demo", action="store_true", help="use the bundled demo practice")
    ap.add_argument("--topic", help="optional blog topic (defaults to the first specialty)")
    ap.add_argument("--json", action="store_true", help="emit the structured payload as JSON")
    ap.add_argument("--use-ollama", action="store_true",
                    help="enable the LLM-enrichment seam (no-op until a model is wired)")
    args = ap.parse_args(argv)

    try:
        practice = _load_practice(args)
        result = BlogScaffold().run(practice, topic=args.topic, use_ollama=args.use_ollama)
    except StaffHonestyError as e:
        print(f"blog: HONESTY GATE FAILED — nothing emitted:\n{e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"blog: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(result.markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
