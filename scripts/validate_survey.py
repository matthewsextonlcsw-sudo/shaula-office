#!/usr/bin/env python3
"""Survey pre-flight validator — concierge-beta deliverable A (operator step 2).

The intake form (``docs/INTAKE_FORM.md``) collects the therapist's survey; this
script is the operator's PRE-FLIGHT check before ``build_site``. It predicts —
WITHOUT building — whether the build will succeed and exactly what it will assume,
by REUSING the engine's own contracts (single source of truth; the validator can
never disagree with the build):

  1. **Required fields** — ``build_practice.survey_readiness`` → which of the 17
     REQUIRED keys are still missing (a missing one raises ``ValueError`` at build).
  2. **Honest input** — the canonical engine linter (``generate.lint``) over every
     free-text value (same walk as ``scripts/honesty_scan.py``); a banned claim in
     operator input raises ``HonestyError`` at build, so catch it here first.
  3. **Modality resolution** — ``citations.resolve_modalities_detail`` → which listed
     modalities resolve to a real foundational citation vs. are dropped. **Zero
     resolvable → the build ABORTS** (``generate.py`` SystemExit, "refusing to emit a
     citation-free approach section"); the validator flags this as a hard stop.
  4. **Assumptions** — the defaults the build would flag (``survey_readiness.assumed``),
     so the operator can fill them in or accept them knowingly.

Exit 0 = ready to build; exit 1 = NOT ready (missing required, dishonest input, or a
zero-modality abort); exit 2 = bad usage.

NO PHI — provider's own professional information only. Stdlib + sibling modules.

Usage:
    validate_survey.py <survey.json> [<survey.json> ...]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parent.parent
for _sub in ("engine", "svc", "scripts"):
    _p = _ROOT / _sub
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import build_practice as BP  # noqa: E402
import citations as C  # noqa: E402
import generate as G  # noqa: E402
import honesty as H  # noqa: E402  (svc/honesty — plain-language, REUSED)
import honesty_scan as HS  # noqa: E402  (reuse the canonical string walk)


def validate(survey: dict) -> dict:
    """Pure pre-flight. Returns a structured verdict; no build, no I/O."""
    readiness = BP.survey_readiness(survey or {})

    banned = []
    for path, value in HS.walk(survey or {}):
        hits = G.lint(value)
        if hits:
            banned.append({
                "field": path,
                "reasons": [H._plain(p) for p in hits],
                "clip": value[:80],
            })

    detail = C.resolve_modalities_detail((survey or {}).get("modalities", ""))
    will_abort = len(detail["resolved"]) == 0  # zero resolvable modalities -> build SystemExit

    ok = not readiness["missing"] and not banned and not will_abort
    return {
        "ok": ok,
        "missing_required": readiness["missing"],
        "banned_input": banned,
        "modalities": detail,          # {listed, resolved:[{tag,name,..}], dropped}
        "zero_modality_abort": will_abort,
        "assumed": readiness["assumed"],
    }


def format_report(survey_path: str, v: dict) -> str:
    L = [f"survey pre-flight — {survey_path}"]

    if v["missing_required"]:
        L.append(f"  ✗ MISSING required field(s): {', '.join(v['missing_required'])}")
    else:
        L.append("  ✓ all 17 required fields present")

    if v["banned_input"]:
        L.append("  ✗ banned-language in operator input (would raise HonestyError at build):")
        for b in v["banned_input"]:
            L.append(f"      {b['field']}: {'; '.join(b['reasons'])}  [\"{b['clip']}\"]")
    else:
        L.append("  ✓ free-text input is honesty-clean")

    listed = v["modalities"]["listed"]
    resolved = [m["name"] for m in v["modalities"]["resolved"]]
    dropped = v["modalities"]["dropped"]
    if v["zero_modality_abort"]:
        L.append(
            f"  ✗ ZERO resolvable modalities from {listed or '(none listed)'} — the build "
            f"would ABORT (citation-free approach section refused). Add at least one "
            f"catalog-backed modality."
        )
    else:
        L.append(f"  ✓ modalities resolve: shown={resolved}"
                 + (f"  held-back={dropped}" if dropped else ""))

    if v["assumed"]:
        L.append(f"  • {len(v['assumed'])} field(s) will be DEFAULTED + flagged on the "
                 f"receipt (not errors): " + ", ".join(a["field"] for a in v["assumed"]))

    L.append("  → READY to build." if v["ok"] else "  → NOT READY — fix the ✗ items above.")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="validate_survey.py",
        description="Pre-flight a therapist survey.json before building: required "
                    "fields, banned-language, modality resolution, and the abort "
                    "check. Exit 0 = ready to build; exit 1 = fix the ✗ items.",
    )
    ap.add_argument("survey", nargs="+", help="path(s) to a survey JSON file")
    args = ap.parse_args(argv)

    worst = 0
    for path in args.survey:
        try:
            raw = pathlib.Path(path).read_text(encoding="utf-8")
        except OSError as e:
            print(f"survey pre-flight — {path}\n  ✗ cannot open file: {e}\n  → NOT READY")
            worst = 1
            continue
        try:
            survey = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"survey pre-flight — {path}\n  ✗ not valid JSON ({e}).\n"
                  "    Hint: the file must be a JSON object — check for a trailing comma, "
                  "a missing quote, or smart-quotes pasted from a doc.\n  → NOT READY")
            worst = 1
            continue
        v = validate(survey)
        print(format_report(path, v))
        if not v["ok"]:
            worst = 1
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
