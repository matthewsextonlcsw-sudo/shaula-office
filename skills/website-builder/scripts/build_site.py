#!/usr/bin/env python3
"""Shaula website-builder — invoked by the website-builder skill.

Reads a synthetic practice SURVEY (JSON; --survey path or stdin), builds an honest marketing
site via the deterministic engine, and prints the output dir. The honesty engine (engine/)
re-lints every block and verifies the filled site has 0 token leaks / 0 AI-GENERATE markers;
a banned claim aborts the build (ok:false).

NO PHI — public practice marketing input only (name, credential, fees, modalities, …).
"""
import argparse
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]  # skills/website-builder/scripts -> repo root
sys.path.insert(0, str(REPO / "engine"))
import pipeline as P  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build an honest practice website from a survey.")
    ap.add_argument("--survey", help="path to survey JSON (default: read stdin)")
    ap.add_argument("--sites-dir", default=str(REPO / "sites"))
    args = ap.parse_args(argv)

    raw = pathlib.Path(args.survey).read_text(encoding="utf-8") if args.survey else sys.stdin.read()
    survey = json.loads(raw)
    try:
        res = P.build_site(survey, sites_dir=args.sites_dir)
    except Exception as exc:  # honesty refusal / bad input → report, never bypass
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        return 1
    print(json.dumps({
        "ok": True,
        "slug": res["slug"],
        "dir": str(res["dir"]),
        "business": res.get("business_name"),
        "owner": res.get("owner_name"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
