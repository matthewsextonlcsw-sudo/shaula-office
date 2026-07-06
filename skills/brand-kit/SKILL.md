---
name: brand-kit
description: "Practice brand reference — voice, colors, tagline, differentiator. Staff read this before drafting any copy, deck, ad, or newsletter so every output stays in the practice's own voice without re-prompting each run."
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [brand, voice, marketing, consistency]
    related_skills: [copy-engine, deck-engine, ad-creative-engine, newsletter-engine]
---

# Brand Kit (Shaula)

A single reference file the marketer, blog, website, and distributor staff read before producing
any public-facing content. Eliminates re-explaining the practice's identity on every run.

## When to use

Whenever a staff member is about to write copy, draft a deck slide, write ad variants, or compose
a newsletter. Instruct the staff member: "Read the Brand Kit before drafting. Every output must
match the voice and stay within the facts listed there."

## What the Brand Kit contains

The clinician fills in the following once. Staff read it; they do not modify it.

```
PRACTICE_NAME:       [e.g., Cedar Sage Therapy]
CLINICIAN_NAME:      [e.g., Dr. Jordan Lee, LCSW]
TAGLINE:             [one line the clinician actually uses, e.g., "Real talk. Real change."]
PRIMARY_CREDENTIAL:  [e.g., LCSW, LPC, LMFT — exactly as licensed]
POPULATIONS_SERVED:  [e.g., adults, adolescents 14+, couples]
SPECIALTIES:         [plain list — what the clinician is licensed and trained to do]
MODALITIES:          [e.g., CBT, EMDR, somatic — only what the clinician actually practices]
VOICE_NOTES:         [e.g., "Direct and warm. Never clinical jargon. First-person OK. No wellness clichés."]
COLORS_HEX:          [e.g., primary #2D6A4F, accent #F4A261 — for image briefs and deck design direction]
LOGO_FILE:           [path or URL to logo, or "none yet"]
DIFFERENTIATOR:      [one honest sentence: what makes this practice the right fit vs. any other — no superlative, just the real thing]
HARD_NOES:           [phrases, claims, or comparisons the clinician never wants associated with their practice]
```

## Honesty contract

The Brand Kit is a constraint file, not a license to invent. Staff use it to match voice and stay
factual — they may not expand the specialties list, add a credential the clinician didn't list, or
soften a HARD_NOE. If the kit is incomplete, staff flag the missing field as [FILL IN] rather than
inventing a plausible value.

## How to create / update

The clinician or practice manager fills in the template above and saves it as
`brand-kit.md` in the practice's workspace. Reference it in workflow steps as:
`"Read brand-kit.md in this workspace before drafting."` No engine or script required.
