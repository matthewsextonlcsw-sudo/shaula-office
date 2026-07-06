#!/usr/bin/env python3
"""staff_check — proof gate for the AI-staff engine (blog scaffolder).

Runs BlogScaffold over every synthetic fixture and asserts the honesty
invariants that make the staff engine trustworthy:

  1. run() succeeds and returns the full StaffResult shape.
  2. The rendered markdown is honesty-clean (engine/generate.lint == []).
  3. EVERY further-reading citation is a REAL one from engine/citations
     (KNOWN_CITATIONS) — proves no fabricated reference can appear.
  4. A mandatory, crisis-aware disclaimer (988) is present.
  5. The brief is explicitly labeled a scaffold, never a finished post.
  6. meta_description respects the 155-char budget.

Plus a NEGATIVE test: a practice dict tainted with a banned claim is REJECTED by
the staff gate — defense-in-depth, independent of build_practice's input lint.

Exit 0 = all green. Pure stdlib. No network, no PHI.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "engine"))

import citations as C        # noqa: E402
import generate as G         # noqa: E402
from staff.base import StaffHonestyError  # noqa: E402
from staff.blog import BlogScaffold       # noqa: E402

FIXTURES = ["cedar-sage", "couples-riverbend", "northstar-denver"]


def _fail(msg: str) -> int:
    print("  ✗", msg)
    return 1


def _ok(msg: str) -> None:
    print("  ✓", msg)


def check_fixture(slug: str) -> int:
    errs = 0
    p_path = os.path.join(ROOT, "fixtures", slug, "practice.json")
    with open(p_path, encoding="utf-8") as fh:
        practice = json.load(fh)

    res = BlogScaffold().run(practice)
    pl = res.payload

    # 1) shape
    for k in ("task", "title", "payload", "markdown", "disclaimer"):
        if not getattr(res, k, None):
            errs += _fail(f"{slug}: result missing {k}")
    for k in ("_scope", "title_options", "outline", "further_reading",
              "meta_description", "geo_angles", "voice_notes"):
        if k not in pl:
            errs += _fail(f"{slug}: payload missing {k}")

    # 2) markdown honesty-clean
    hits = G.lint(res.markdown)
    if hits:
        errs += _fail(f"{slug}: markdown contains banned language: {hits}")

    # 3) every cited source is REAL (the strong invariant)
    for fr in pl.get("further_reading", []):
        if fr["citation"] not in C.KNOWN_CITATIONS:
            errs += _fail(f"{slug}: FABRICATED citation: {fr['citation']!r}")

    # 4) crisis-aware disclaimer
    if "988" not in res.disclaimer:
        errs += _fail(f"{slug}: disclaimer missing the 988 crisis line")

    # 5) explicitly a scaffold, not a finished post
    if "not a finished post" not in pl.get("_scope", "").lower():
        errs += _fail(f"{slug}: _scope does not label this a scaffold/brief")

    # 6) meta description budget
    mlen = len(pl.get("meta_description", ""))
    if mlen > 155:
        errs += _fail(f"{slug}: meta_description {mlen} > 155 chars")

    if errs == 0:
        _ok(f"{slug}: honest brief — {len(pl['title_options'])} titles, "
            f"{len(pl['outline'])} sections, {len(pl['further_reading'])} cited "
            f"source(s), disclaimer+988, meta {mlen}c")
    return errs


def check_negative() -> int:
    """A practice tainted with a banned claim must be REJECTED by the staff gate
    (this bypasses build_practice entirely to prove the staff gate is its own,
    independent line of defense)."""
    tainted = {
        "business_name": "Proven Results Therapy",   # contains banned 'proven'
        "owner_name": "Test Clinician", "credential": "LPC",
        "specialties": "anxiety", "modalities": "CBT",
        "populations": "adults", "location": "Somewhere, ST",
        "payment_model": "Out-of-network", "session_length": "50-minute",
        "consult_length": "20-minute",
    }
    try:
        BlogScaffold().run(tainted)
    except StaffHonestyError as e:
        _ok(f"tainted practice rejected ({len(e.problems)} hit-group(s)) — "
            "staff gate is firing")
        return 0
    return _fail("tainted practice was NOT rejected — the staff gate is not firing")


def main() -> int:
    print("staff_check — AI-staff engine (blog scaffolder) honesty gate\n")
    total = 0
    for slug in FIXTURES:
        print(f"[{slug}]")
        total += check_fixture(slug)
    print("[negative path]")
    total += check_negative()

    if total:
        print(f"\nstaff_check FAILED — {total} problem(s)")
        return 1
    print(f"\nstaff_check OK — {len(FIXTURES)} fixtures + negative path, "
          "all honest (every cited source real, every brief crisis-aware).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
