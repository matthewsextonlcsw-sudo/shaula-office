---
name: website-builder
description: "Build an honest, deterministic marketing website for a therapy practice from a short survey. No invented stats, no fake claims — every block honesty-linted."
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [website, builder, therapy, practice, marketing, honesty]
    related_skills: [blog-scaffolder]
---

# Website Builder (Shaula)

Builds a complete static marketing site for a single therapy practice from a short intake survey —
deterministically, behind a honesty engine that **cannot** emit invented statistics,
"proven"/"evidence-based"/"#1" without a real citation, fake testimonials, or a branded method the
practice doesn't actually hold. Every block is re-linted; the filled site is verified to have
**0 unfilled tokens and 0 AI-GENERATE markers** or the build aborts.

## When to use
The practitioner wants their website built or refreshed from their practice facts. **Public
marketing copy only — never client/PHI data.**

## How to run
The survey is a JSON object with keys like: `owner_name, credential, business_name, tagline,
specialties, populations, modalities, location, service_areas, payment_model_type, session_fee,
session_length`.

```bash
python3 skills/website-builder/scripts/build_site.py --survey <survey.json>
# or:  cat survey.json | python3 skills/website-builder/scripts/build_site.py
```

Output: JSON `{ok, slug, dir, business, owner}`. The finished site lands under `dir`
(`sites/<slug>/`). If `ok:false`, the honesty engine **refused** the input — surface the error
verbatim; do not try to bypass it.

## Honesty contract (do not work around)
This skill's entire value is that the output is honest. If the survey carries a banned marketing
claim, the build fails **by design**. Never edit the engine to force a build through. The optional
model "brain" only *rephrases* already-approved copy and is re-linted afterward — it can never add a
claim. This is the spine; keep it intact.
