#!/usr/bin/env python3
"""Shaula blog-scaffolder — invoked by the blog-scaffolder skill.

Reads a synthetic practice SURVEY (JSON; --survey path or stdin), derives the practice, and
produces an HONEST blog brief/scaffold (titles + section outlines + real citations) — never a
finished, auto-published post. The shared honesty engine forbids invented stats, "proven"/"#1"
without a real citation, fake testimonials, and branded methods the practice doesn't hold.

NO PHI — public practice marketing input only.
"""
import argparse
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]  # skills/blog-scaffolder/scripts -> repo root
sys.path.insert(0, str(REPO))            # for `from staff.blog import ...`
sys.path.insert(0, str(REPO / "engine"))  # for build_practice + engine deps
import build_practice as BP  # noqa: E402
from staff.blog import BlogScaffold  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Scaffold an honest blog brief from a survey.")
    ap.add_argument("--survey", help="path to survey JSON (default: read stdin)")
    args = ap.parse_args(argv)

    raw = pathlib.Path(args.survey).read_text(encoding="utf-8") if args.survey else sys.stdin.read()
    survey = json.loads(raw)
    try:
        practice = BP.build_practice(survey)
        brief = BlogScaffold().run(practice)
    except Exception as exc:  # honesty refusal / bad input → report, never bypass
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        return 1
    print(json.dumps({"ok": True, "brief": brief}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
