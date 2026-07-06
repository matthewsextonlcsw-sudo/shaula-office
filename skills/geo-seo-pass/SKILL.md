---
name: geo-seo-pass
description: "Add the structured-data layer that wins AI answer engines + local search to a finished practice site — JSON-LD (MedicalBusiness + founder + a factual FAQPage), OpenGraph/Twitter meta, and llms.txt. Deterministic, no LLM, honesty-gated. Public marketing only — never PHI."
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [geo, seo, schema, json-ld, llms-txt, marketing, therapy, honesty]
    related_skills: [website-builder, blog-scaffolder]
---

# GEO/SEO finishing pass (Shaula)

Takes a site already produced by `website-builder` (generate.py → fill.py) and adds the
**Generative-Engine-Optimization** layer so the practice gets cited by ChatGPT/Perplexity/Google AI
answers and ranks in local search — **without any LLM and without inventing a single claim.** Every
value is pulled straight from the practice's already-honesty-linted tokens.

## What it emits (idempotently, into the site dir)
- **JSON-LD** in `<head>`: a `MedicalBusiness`/`ProfessionalService` node (name, founder `Person` with
  the real license credential, specialties, area served, fee range, contact) **+ a `FAQPage`** whose
  Q&A come *only* from factual practice data (insurance/payment, session fee, sliding scale, location,
  consultation). No invented answers.
- **OpenGraph + Twitter `<meta>`** — reuses the page's own title + description.
- **`llms.txt`** at the site root — the AI-crawler summary (who/what/where/pages/contact), ending with
  an explicit "this is not a crisis service → 988 / 741741" note.

## When to use
After a site is built, as the final marketing step. **Public marketing input only — never client/PHI.**

## How to run
```
python3 engine/geo.py --practice <practice.json> --site <site dir> [--url https://canonical]
# or via the skill wrapper:
python3 skills/geo-seo-pass/scripts/geo_pass.py --practice <practice.json> --site <site dir>
```

## Honesty by construction
- Pulls only from `practice.json` (build_practice already linted it).
- A hard banned-phrase gate runs over the JSON-LD **and** llms.txt before writing — any
  "proven/guarantee/#1/best/cures/world-class" aborts the pass (`SystemExit`), same spine as the
  website engine. Re-running replaces the prior block (marked `shaula-geo:start/end`), never doubles.
- Covered by `scripts/prove.sh` (runs after fill, render-verified) — keep it green.

## Hermes slot
The `marketer` profile's final step in the **marketing/GEO kanban** (workflow L). No PHI, so it may run
on the cloud brain or fully local — but it needs no model at all; it's deterministic.
