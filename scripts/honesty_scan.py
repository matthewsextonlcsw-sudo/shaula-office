#!/usr/bin/env python3
"""Honesty gate for practice *operator input*.

`generate.py` already rejects banned claims inside every GENERATED block (it
exits 2 on a violation). The one surface it does not control is the
`practice.json` an operator hands us — a practice could supply a tagline like
"proven results, #1 therapist in town". This scanner lints every string value
in a practice.json (recursively, including the nested `career[]` array) against
the SAME banned list `generate.py` uses — imported, so there is a single source
of truth and the two can never drift. A dishonest claim in raw input fails the
build before it can reach the page.

Keys beginning with "_" (e.g. `_comment`) are metadata and are skipped.

Usage:
    honesty_scan.py <practice.json> [<practice.json> ...]

Exit 0 = all clean; exit 1 = at least one banned pattern found; 2 = bad usage.
"""
from __future__ import annotations

import json
import pathlib
import sys

# Import the canonical banned-claim linter from the engine (single source of
# truth). honesty_scan.py lives in scripts/, so the engine is a sibling dir.
_ENGINE = pathlib.Path(__file__).resolve().parent.parent / "engine"
sys.path.insert(0, str(_ENGINE))
import generate as G  # noqa: E402  (path must be set before import)


def walk(node, path: str = ""):
    """Yield (json_path, string_value) for every string in a JSON tree."""
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            if k.startswith("_"):
                continue  # metadata (e.g. _comment) is not shipped copy
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")


def scan(path: pathlib.Path):
    """Return a list of (json_path, value, [banned_patterns]) for one file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    hits = []
    for jpath, val in walk(data):
        bad = G.lint(val)
        if bad:
            hits.append((jpath, val, bad))
    return hits


def main(argv) -> int:
    if not argv:
        print("usage: honesty_scan.py <practice.json> [...]", file=sys.stderr)
        return 2
    total = 0
    for arg in argv:
        p = pathlib.Path(arg)
        if not p.is_file():
            print(f"✗ {p}: not found", file=sys.stderr)
            return 2
        hits = scan(p)
        if hits:
            total += len(hits)
            print(f"✗ {p}: {len(hits)} banned claim(s)")
            for jpath, val, bad in hits:
                print(f"    {jpath}: {bad} → {val!r}")
        else:
            print(f"✓ {p}: clean")
    if total:
        print(f"\nFAIL: {total} banned claim(s) in operator input.", file=sys.stderr)
        return 1
    print("\nPASS: all practice input honesty-clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
