---
name: blog-scaffolder
description: "Produce an honest blog brief/scaffold (titles + section outlines + real citations) for a therapy practice. A scaffold for the human to finish — never an auto-published post."
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [blog, scaffold, content, therapy, practice, honesty, citations]
    related_skills: [website-builder]
---

# Blog Scaffolder (Shaula)

Turns a practice survey into an **honest blog brief**: post titles, per-post section outlines, and
**real citations** — explicitly a *scaffold the clinician finishes*, never a finished or
auto-published article. The shared honesty engine forbids invented statistics,
"proven"/"#1" without a real citation, fake testimonials, and any branded method the practice
doesn't actually hold.

## When to use
The practitioner wants help planning blog content from their practice facts. **Public marketing
input only — never client/PHI data.**

## How to run
Same survey shape as `website-builder` (`owner_name, credential, business_name, specialties,
modalities, location, payment_model_type, …`).

```bash
python3 skills/blog-scaffolder/scripts/scaffold_blog.py --survey <survey.json>
# or:  cat survey.json | python3 skills/blog-scaffolder/scripts/scaffold_blog.py
```

Output: JSON `{ok, brief}` where `brief` carries the titles, outlines, and cited sources. If
`ok:false`, the honesty engine refused — surface the error; do not bypass.

## Honesty contract (do not work around)
The output is a **brief, not a post** — that labeling is intentional and load-bearing. Do not
present the scaffold as a finished article, do not invent citations, and never edit the engine to
force banned copy through.
