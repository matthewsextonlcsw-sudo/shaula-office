#!/usr/bin/env python3
"""CLI for the Shaula workflow builder.

  python3 -m workflows.cli validate  workflows/templates/weekly-blog.json
  python3 -m workflows.cli plan       workflows/templates/weekly-blog.json -v topic="Sleep and anxiety" -v project=cedar-sage
  python3 -m workflows.cli emit       workflows/templates/weekly-blog.json -v topic="Sleep and anxiety" -v project=cedar-sage \
      --base-url http://127.0.0.1:8200 --session-token "$HERMES_DASHBOARD_SESSION_TOKEN"

`plan` is a dry run — it prints the exact task-graph that WOULD be created, no
network. `emit` writes it to the live board (parents-first). `--allow-phi`
unlocks PHI profiles (also requires `allow_phi: true` in the template).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Allow running as a loose script (python3 workflows/cli.py …) as well as a
# module (python3 -m workflows.cli …).
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from workflows import builder as B  # type: ignore
else:
    from . import builder as B


def _parse_vars(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"bad -v {p!r}; expected name=value")
        k, val = p.split("=", 1)
        out[k.strip()] = val
    return out


def _print_violations(e: B.WorkflowError) -> None:
    print(f"✗ {e}", file=sys.stderr)
    for v in e.violations:
        print(f"   - {v}", file=sys.stderr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="workflows.cli", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("validate", "plan", "emit"):
        sp = sub.add_parser(name)
        sp.add_argument("template", help="path to a workflow template JSON")
        sp.add_argument("--allow-phi", action="store_true",
                        help="unlock PHI profiles (template must also opt in)")
        if name in ("plan", "emit"):
            sp.add_argument("-v", "--var", action="append", default=[], dest="vars",
                            help="variable as name=value (repeatable)")
            sp.add_argument("--instance-key", default=None,
                            help="idempotency prefix for re-runnable instantiation")
        if name == "emit":
            sp.add_argument("--base-url",
                            default=os.environ.get("SHAULA_DASHBOARD_URL",
                                                   "http://127.0.0.1:9119"))
            sp.add_argument("--session-token",
                            default=os.environ.get("HERMES_DASHBOARD_SESSION_TOKEN"))
            sp.add_argument("--board", default=None,
                            help="board slug to emit into (overrides template.board)")
            sp.add_argument("--create-board", action="store_true",
                            help="create the board first (idempotent); needs a slug")
            sp.add_argument("--dispatch", action="store_true",
                            help="kick a dispatch pass after creating (build AND run)")
            sp.add_argument("--dispatch-max", type=int, default=8,
                            help="max workers to spawn in the dispatch pass (default 8)")
            sp.add_argument("--dispatch-dry-run", action="store_true",
                            help="preview what dispatch WOULD spawn (no workers spawned)")

    args = ap.parse_args(argv)

    try:
        tmpl = B.load_template_file(args.template)
    except (OSError, ValueError) as e:
        if isinstance(e, B.WorkflowError):
            _print_violations(e)
        else:
            print(f"✗ cannot load template: {e}", file=sys.stderr)
        return 2

    try:
        if args.cmd == "validate":
            B.validate(tmpl, allow_phi=args.allow_phi)
            print(f"✓ {tmpl.name}: {len(tmpl.steps)} steps, valid "
                  f"({'PHI' if tmpl.allow_phi else 'no-PHI'}).")
            return 0

        variables = _parse_vars(args.vars)

        if args.cmd == "plan":
            out = B.instantiate(tmpl, variables, allow_phi=args.allow_phi,
                                instance_key=args.instance_key, dry_run=True)
            print(json.dumps(out, indent=2, ensure_ascii=False))
            return 0

        if args.cmd == "emit":
            if not args.session_token:
                print("✗ no session token (pass --session-token or set "
                      "HERMES_DASHBOARD_SESSION_TOKEN)", file=sys.stderr)
                return 2
            out = B.instantiate(tmpl, variables, allow_phi=args.allow_phi,
                                instance_key=args.instance_key,
                                base_url=args.base_url,
                                session_token=args.session_token,
                                board=args.board,
                                create_board=args.create_board,
                                dispatch=args.dispatch,
                                dispatch_max=args.dispatch_max,
                                dispatch_dry_run=args.dispatch_dry_run,
                                dry_run=False)
            if out.get("board"):
                tag = " (created)" if "board_result" in out else ""
                print(f"▸ board: {out['board']}{tag}")
            for c in out["created"]:
                line = f"✓ {c['ref']:<10} → {c['id']}  ({c['assignee']})"
                if c["parents"]:
                    line += f"  parents={c['parents']}"
                if c.get("warning"):
                    line += f"  ⚠ {c['warning']}"
                print(line)
            if "dispatch" in out:
                d = out["dispatch"] or {}
                spawned = d.get("spawned") or d.get("dispatched") or d.get("count")
                print(f"▸ dispatch: {spawned if spawned is not None else d}")
            return 0
    except B.WorkflowError as e:
        _print_violations(e)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
