#!/usr/bin/env python3
"""geo_pass — thin skill wrapper over engine/geo.py.

Lets the `marketer` profile run the GEO/SEO finishing pass as a skill without
re-implementing logic. All the work (JSON-LD + OG meta + llms.txt, honesty-gated)
lives in engine/geo.py — the single reusable, prove.sh-covered source of truth.

Usage:
    python3 skills/geo-seo-pass/scripts/geo_pass.py --practice <p.json> --site <dir> [--url URL]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Resolve repo root (skills/geo-seo-pass/scripts/ -> repo root is parents[3]) so the
# engine package imports cleanly whatever the cwd.
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from engine.geo import inject  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="GEO/SEO finishing pass (skill wrapper).")
    ap.add_argument("--practice", required=True)
    ap.add_argument("--site", required=True)
    ap.add_argument("--url", default="")
    args = ap.parse_args()

    practice = json.loads(Path(args.practice).read_text(encoding="utf-8"))
    report = inject(Path(args.site), practice, args.url)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
