#!/usr/bin/env python3
"""concierge_build — the operator's one-command "make this therapist turnkey".

Concierge-beta **deliverable B** (spec shaula#20): the by-hand operator runs this
once per therapist. One ``survey.json`` in → a built, honesty-receipted site out,
ready for the gated publish step. It chains three proven, independently-tested
stages with NO network, NO LLM, and NO deploy:

    survey.json
      → validate_survey.validate()   # PRE-FLIGHT: required + honest input + modality abort
      → pipeline.build_site()         # survey → sites/<slug>/  (deterministic, $0)
      → honesty_receipt               # _refusals + _assumed → receipts/<slug>-...md

Why a wrapper and not just the HTTP ``POST /api/website``: the concierge operator
works by hand on ≤10 runs (no server, no dashboard). This is the single command
that turns a filled intake into the two artifacts the operator hands the therapist:
the **site** and the **honesty receipt**.

**Publish is deliberately NOT done here.** Going live for a real practice is a
Matthew-gated action, and during the beta no real-therapist site goes live at all.
On success the script PRINTS the exact gated publish commands as the next step;
running them is a separate, human decision. (Reconciling the publish paths into one
runbook is concierge-beta stream 7.)

NO PHI by construction — the survey is the provider's own professional information
only. Stdlib + sibling engine modules; Python 3.8+.

Usage:
    concierge_build.py <survey.json> [--slug S] [--inquiry-origin URL]
                       [--site-url URL] [--receipt-out PATH] [--date YYYY-MM-DD]
                       [--sites-dir DIR]
Exit: 0 built · 1 blocked (bad survey / honesty / build failure) · 2 bad usage.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

# scripts/ is a sibling of engine/ and svc/. Wire all four onto the path so this
# reuses the SAME validator, pipeline, and receipt the rest of the beta uses —
# single source of truth, nothing re-implemented here.
_ROOT = pathlib.Path(__file__).resolve().parent.parent
for _sub in ("", "engine", "svc", "scripts"):
    _p = _ROOT / _sub if _sub else _ROOT
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pipeline as PIPE  # noqa: E402  (engine/pipeline — the proven build_site)
import validate_survey as V  # noqa: E402  (deliverable A pre-flight, REUSED)
import honesty_receipt as R  # noqa: E402  (deliverable C receipt, REUSED)

DEFAULT_RECEIPTS_DIR = _ROOT / "receipts"

# The proven Google publish host (one-time MWS setup; see WEBSITE_PUBLISH_RUNBOOK.md).
_GCS_BUCKET = "mws-shaula-sites"
_GCP_PROJECT = ""  # set your own GCP project id


class BuildBlocked(RuntimeError):
    """Pre-flight validation failed — the survey would not build cleanly.

    Carries the human-readable ``report`` and the structured ``validation`` so the
    caller can show the operator exactly which ✗ items to fix, WITHOUT having
    attempted (and half-completed) a build.
    """

    def __init__(self, report: str, validation: dict):
        super().__init__(report)
        self.report = report
        self.validation = validation


def run(
    survey: dict,
    *,
    sites_dir: pathlib.Path | str = PIPE.DEFAULT_SITES_DIR,
    slug: str | None = None,
    inquiry_origin: str = "",
    site_url: str = "",
    receipt_out: pathlib.Path | str | None = None,
    receipts_dir: pathlib.Path | str = DEFAULT_RECEIPTS_DIR,
    generated_on: str = "",
    brain=None,
) -> dict:
    """Validate → build → receipt, in one call. Returns a structured result.

    Raises:
      * ``BuildBlocked``        — pre-flight caught a problem; nothing was built.
      * ``PIPE.HonestyError`` / ``ValueError`` / ``PIPE.PipelineError`` — a build-stage
        failure that slipped past pre-flight (defensive; pre-flight mirrors these).
    """
    # 1) PRE-FLIGHT (reuse the deliverable-A validator; it can never disagree with
    #    the build because it calls the same engine contracts). Stop here on a bad
    #    survey so the operator never sees a half-built site or a raw stack trace.
    v = V.validate(survey)
    if not v["ok"]:
        raise BuildBlocked(V.format_report("<survey>", v), v)

    # 2) BUILD (deterministic, brain=None → no network, no credentials, $0).
    built = PIPE.build_site(
        survey,
        sites_dir=sites_dir,
        slug=slug,
        inquiry_origin=inquiry_origin,
        site_url=site_url,
        brain=brain,
    )
    slug = built["slug"]
    practice = built["practice"]

    # 3) HONESTY RECEIPT (generated from the same engine output — cannot drift from
    #    the site). Written OUTSIDE the served site tree so the published site stays
    #    exactly the site; the receipt is the operator's out-of-band trust artifact.
    refusals = R.build_refusals(practice)
    md = R.receipt_markdown(
        practice, refusals,
        business_name=built["business_name"],
        generated_on=generated_on,
    )
    if receipt_out is not None:
        receipt_path = pathlib.Path(receipt_out)
    else:
        receipt_path = pathlib.Path(receipts_dir) / f"{slug}-honesty-receipt.md"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(md, encoding="utf-8")

    return {
        "slug": slug,
        "dir": built["dir"],
        "receipt_path": str(receipt_path),
        "owner_name": built["owner_name"],
        "business_name": built["business_name"],
        "validation": v,
        "assumed_count": len(practice.get("_assumed", []) or []),
        "modalities_shown": refusals.get("modalities_shown", []),
        "modalities_dropped": refusals.get("modalities_dropped_unknown", []),
    }


def publish_commands(slug: str) -> str:
    """The PROVEN, Matthew-gated Google publish options for ``sites/<slug>/``.

    Printed as the next step — never executed here. Two GCP paths exist today
    (stream 7 reconciles them into one runbook):

      A. GCS static (proven 2026-06-08; no Dockerfile) — instant public HTTPS.
      B. Cloud Run + nginx (docs/WEBSITE_PUBLISH_RUNBOOK.md) — adds a custom domain
         via the LB stack.
    """
    return "\n".join([
        "Next step — PUBLISH (Matthew-gated; no real-therapist site goes live in beta):",
        "",
        "  A) GCS static host (simplest, proven):",
        f"       gcloud storage cp -r sites/{slug} gs://{_GCS_BUCKET}/ --project {_GCP_PROJECT}",
        f"       → https://storage.googleapis.com/{_GCS_BUCKET}/{slug}/index.html",
        "",
        "  B) Cloud Run + custom domain: see docs/WEBSITE_PUBLISH_RUNBOOK.md §2–3",
        f"       (service name = {slug}; needs the nginx context — stream 7).",
    ])


def _format_summary(result: dict) -> str:
    shown = result["modalities_shown"]
    dropped = result["modalities_dropped"]
    L = [
        f"✓ BUILT — {result['business_name']} ({result['owner_name']})",
        f"  site:    {result['dir']}",
        f"  receipt: {result['receipt_path']}",
        f"  modalities shown: {', '.join(shown) if shown else '(none)'}"
        + (f"   held back: {', '.join(dropped)}" if dropped else ""),
        f"  defaults assumed + flagged on the receipt: {result['assumed_count']}",
        "",
        publish_commands(result["slug"]),
    ]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Validate a therapist survey, build the site, and write the honesty receipt."
    )
    ap.add_argument("survey", help="path to the no-PHI survey.json (see docs/INTAKE_FORM.md)")
    ap.add_argument("--slug", default=None, help="override the derived site slug")
    ap.add_argument("--inquiry-origin", default="",
                    help="public base URL of the contact-form sink (empty = honest direct-contact card)")
    ap.add_argument("--site-url", default="", help="eventual public URL (for JSON-LD canonical)")
    ap.add_argument("--receipt-out", default=None, help="write the receipt here (default: receipts/<slug>-...md)")
    ap.add_argument("--sites-dir", default=None, help="build under this dir (default: ./sites)")
    ap.add_argument("--date", default="", help="receipt generation date YYYY-MM-DD (default: today)")
    args = ap.parse_args(argv)

    try:
        survey = json.loads(pathlib.Path(args.survey).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write(f"cannot read survey {args.survey!r}: {e}\n")
        return 2

    generated_on = args.date
    if not generated_on:
        import datetime
        generated_on = datetime.date.today().isoformat()

    kw = dict(
        slug=args.slug,
        inquiry_origin=args.inquiry_origin,
        site_url=args.site_url,
        receipt_out=args.receipt_out,
        generated_on=generated_on,
    )
    if args.sites_dir:
        kw["sites_dir"] = args.sites_dir

    try:
        result = run(survey, **kw)
    except BuildBlocked as e:
        print(e.report)
        print("\n✗ NOT BUILT — fix the survey above, then re-run. (Nothing was written.)")
        return 1
    except (PIPE.HonestyError, ValueError, PIPE.PipelineError) as e:
        sys.stderr.write(f"✗ build failed: {e}\n")
        return 1

    print(_format_summary(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
