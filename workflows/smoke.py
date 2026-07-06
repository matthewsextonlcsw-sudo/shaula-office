#!/usr/bin/env python3
"""Shaula workflow builder — re-runnable end-to-end smoke / proof.

One command that proves the D14 builder actually works, so it can be trusted
without hand-poking the API. Two phases:

  PHASE A — OFFLINE (always runs, zero network):
    1. runs the full unit suite (workflows.test_builder) and asserts it's green;
    2. positive plan assertions on an embedded synthetic no-PHI template
       (build → topo order → triage / max_runtime_seconds / tenant / preamble /
       idempotency-key mapping);
    3. the four guardrails each REJECT what they should — bad assignee, a PHI
       profile without opt-in, a dependency cycle, a banned honesty claim, and a
       dangling dependency ref.

  PHASE B — LIVE (runs only if a dashboard is reachable):
    instantiates the same synthetic template against the running dashboard on a
    dedicated, idempotent board (`shaula-smoke`), then reads the state back over
    HTTP and asserts the server actually persisted it — the board exists, the
    DAG edge is wired (`links.parents`), the triage step landed in the triage
    column, `tenant` + `max_runtime_seconds` stuck on the rows, and the dispatch
    DRY-RUN spawned zero workers (the `running` column stays empty).

Safe to run repeatedly: a FIXED board slug + a FIXED instance key mean every
re-run dedups onto the same rows (Hermes' idempotency_key contract) — nothing
accrues, nothing is deleted, the `default` board is never touched. The session
token is auto-discovered the same way a browser gets it (the dashboard injects
`window.__HERMES_SESSION_TOKEN__` into its own index.html), so no token has to
be passed by hand; a bare curl is still 401.

Run:
    python3 -m workflows.smoke                      # offline + live (if up)
    python3 -m workflows.smoke --offline-only        # offline proof only
    python3 -m workflows.smoke --base-url http://127.0.0.1:8200
    python3 -m workflows.smoke --session-token "$HERMES_DASHBOARD_SESSION_TOKEN"

Exit code is 0 iff every check that ran passed. Pure stdlib (urllib) — no deps.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

# Dual-mode import (run as `python3 -m workflows.smoke` or `python3 workflows/smoke.py`).
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from workflows import builder as B
else:
    from . import builder as B

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_KANBAN = "/api/plugins/kanban"

# A dedicated, throwaway board + a fixed instance key. Both fixed on purpose:
# re-runs dedup onto the same rows instead of piling up, and we never have to
# delete anything to stay clean (honoring additive-by-default + no-delete).
_SMOKE_BOARD = "shaula-smoke"
_SMOKE_KEY = "shaula-smoke"

# Embedded synthetic, no-PHI template — the smoke owns its own fixture so it
# never depends on a file in /tmp. Two steps, one dependency edge, exercising
# triage, max_runtime_seconds, tenant, a board, and one {variable}.
SYNTHETIC: dict = {
    "name": "shaula-smoke",
    "description": "Synthetic no-PHI template for the end-to-end smoke. Safe to delete.",
    "tenant": "verify-practice",
    "board": {
        "slug": _SMOKE_BOARD,
        "name": "Shaula Smoke",
        "description": "Throwaway end-to-end smoke board (safe to delete).",
        "icon": "🧪",
        "color": "#4f8a5b",
    },
    "variables": ["topic"],
    "steps": [
        {
            "ref": "draft",
            "title": "Draft a short blog outline on {topic}",
            "assignee": "blog",
            "description": "Write a short, plain outline. No claims, just structure.",
            "triage": True,
            "max_runtime_seconds": 600,
        },
        {
            "ref": "review",
            "title": "Read the {topic} outline and note anything to change",
            "assignee": "reviewer",
            "description": "Read the outline and flag anything unclear or overstated.",
            "dependencies": ["draft"],
            "max_runtime_seconds": 300,
        },
    ],
}
_VARS = {"topic": "sleep and anxiety"}

_TOKEN_RE = re.compile(r'window\.__HERMES_SESSION_TOKEN__="([^"]+)"')


# --------------------------------------------------------------------------- #
# Tiny pass/fail harness — readable evidence, exact failure on mismatch.
# --------------------------------------------------------------------------- #
class Checks:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def ok(self, label: str, cond: bool, detail: str = "") -> bool:
        mark = "✓" if cond else "✗"
        line = f"  {mark} {label}"
        if detail:
            line += f"  — {detail}"
        print(line)
        if cond:
            self.passed += 1
        else:
            self.failed += 1
        return cond

    def expect_error(self, label: str, fn) -> None:
        """Assert fn() raises WorkflowError (a guardrail firing)."""
        try:
            fn()
        except B.WorkflowError as e:
            n = len(e.violations) or 1
            self.ok(label, True, f"rejected ({n} violation(s))")
        except Exception as e:  # noqa: BLE001 — wrong error type is still a failure
            self.ok(label, False, f"raised {type(e).__name__}, expected WorkflowError")
        else:
            self.ok(label, False, "no error raised — guardrail did NOT fire")


# --------------------------------------------------------------------------- #
# PHASE A — offline proof (always runs)
# --------------------------------------------------------------------------- #
def phase_a(c: Checks) -> None:
    print("\n=== PHASE A — offline (no network) ===")

    # 1. The unit suite must be green.
    print("\n[A1] unit suite (workflows.test_builder)")
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "workflows.test_builder"],
        cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    tail = (proc.stderr.strip().splitlines() or ["<no output>"])[-1]
    ran = re.search(r"Ran (\d+) test", proc.stderr)
    c.ok("unit suite passes", proc.returncode == 0,
         f"{tail}" + (f" ({ran.group(1)} tests)" if ran else ""))

    # 2. Positive: the embedded template builds into the expected plan.
    print("\n[A2] positive — plan shape from the synthetic template")
    tmpl = B.load_template(SYNTHETIC)
    plan = B.build_plan(tmpl, _VARS, instance_key=_SMOKE_KEY)
    by_ref = {p.ref: p for p in plan}
    refs = [p.ref for p in plan]

    c.ok("builds 2 tasks", len(plan) == 2, f"refs={refs}")
    c.ok("topo order: draft before review",
         "draft" in refs and "review" in refs and refs.index("draft") < refs.index("review"))

    draft = by_ref.get("draft")
    review = by_ref.get("review")
    if draft:
        dp = draft.payload
        c.ok("draft title substituted", dp["title"] == "Draft a short blog outline on sleep and anxiety",
             repr(dp["title"]))
        c.ok("draft triage=True", dp.get("triage") is True)
        c.ok("draft max_runtime_seconds=600", dp.get("max_runtime_seconds") == 600)
        c.ok("draft tenant=verify-practice", dp.get("tenant") == "verify-practice")
        c.ok("draft body starts with house-rules preamble",
             dp["body"].startswith("[SHAULA HOUSE RULES"))
        c.ok("draft idempotency_key=shaula-smoke:draft",
             dp.get("idempotency_key") == "shaula-smoke:draft")
        c.ok("plan payload carries no parents (emitter resolves)", "parents" not in dp)
    if review:
        rp = review.payload
        c.ok("review depends on draft", review.dep_refs == ("draft",), repr(review.dep_refs))
        c.ok("review max_runtime_seconds=300", rp.get("max_runtime_seconds") == 300)

    # 3. Negative: each guardrail must reject.
    print("\n[A3] negative — every guardrail rejects what it should")
    c.expect_error("bad assignee rejected (allow-list)", lambda: B.validate(B.load_template({
        "name": "bad", "steps": [{"ref": "a", "title": "A", "assignee": "research-agent"}]})))
    c.expect_error("PHI profile without opt-in rejected (PHI gate)", lambda: B.validate(B.load_template({
        "name": "phi", "steps": [{"ref": "n", "title": "Note", "assignee": "scribe"}]})))
    c.expect_error("dependency cycle rejected (acyclic)", lambda: B.validate(B.load_template({
        "name": "cyc", "steps": [
            {"ref": "a", "title": "A", "assignee": "blog", "dependencies": ["b"]},
            {"ref": "b", "title": "B", "assignee": "reviewer", "dependencies": ["a"]}]})))
    c.expect_error("banned honesty claim rejected (lint)", lambda: B.validate(B.load_template({
        "name": "lie", "steps": [{"ref": "a", "title": "A", "assignee": "blog",
                                  "description": "Our guaranteed cure for anxiety."}]})))
    c.expect_error("dangling dependency ref rejected (acyclic)", lambda: B.validate(B.load_template({
        "name": "dang", "steps": [{"ref": "a", "title": "A", "assignee": "blog",
                                   "dependencies": ["ghost"]}]})))


# --------------------------------------------------------------------------- #
# PHASE B — live proof (only if a dashboard answers)
# --------------------------------------------------------------------------- #
def _http_get(base_url: str, path: str, token: str | None, timeout: int = 30) -> dict:
    """Authenticated GET against the dashboard (mirrors the emitter's headers)."""
    req = urllib.request.Request(base_url.rstrip("/") + path, method="GET")
    if token:
        req.add_header("X-Hermes-Session-Token", token)
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def discover_token(base_url: str, timeout: int = 10) -> str | None:
    """Pull the session token the same way the browser does — the dashboard
    injects it into its own index.html as window.__HERMES_SESSION_TOKEN__."""
    try:
        req = urllib.request.Request(base_url.rstrip("/") + "/", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, urllib.error.HTTPError):
        return None
    m = _TOKEN_RE.search(html)
    return m.group(1) if m else None


def reachable(base_url: str, token: str | None = None, timeout: int = 5) -> bool:
    """Liveness probe against the kanban API that Phase B actually drives.

    Works across server modes. The standalone ``--local`` dashboard serves an
    unauthenticated landing page at ``/``, but the desktop app's backend runs
    auth-on and (in dev) serves no page at ``/`` at all — the UI is the Vite
    renderer — so a ``GET / == 200`` check would wrongly report it down. Probe
    the kanban boards route instead: 200 → live and authorized; 401/403 → live
    but needs auth (``phase_b`` authenticates with the token); anything else or
    a connection error → down."""
    req = urllib.request.Request(base_url.rstrip("/") + _KANBAN + "/boards", method="GET")
    if token:
        req.add_header("X-Hermes-Session-Token", token)
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        return e.code in (401, 403)
    except Exception:  # noqa: BLE001
        return False


def phase_b(c: Checks, base_url: str, token: str | None) -> None:
    print(f"\n=== PHASE B — live (dashboard at {base_url}) ===")

    if token is None:
        token = discover_token(base_url)
    if token:
        # Never print the secret; just prove we have one.
        print(f"  session token: discovered ({len(token)} chars, not shown)")
    else:
        c.ok("session token available", False,
             "no token via index.html, --session-token, or env — cannot auth")
        return

    tmpl = B.load_template(SYNTHETIC)

    # Instantiate: create the board (idempotent), wire the DAG, then preview a
    # dispatch pass as a DRY-RUN (spawns nothing). Fixed key ⇒ re-run-safe.
    print("\n[B1] instantiate against the live board")
    try:
        out = B.instantiate(
            tmpl, _VARS,
            base_url=base_url, session_token=token,
            board=_SMOKE_BOARD, create_board=True,
            dispatch=True, dispatch_dry_run=True,
            instance_key=_SMOKE_KEY,
        )
    except B.WorkflowError as e:
        c.ok("instantiate succeeded", False, str(e))
        return

    created = {r["ref"]: r for r in out.get("created", [])}
    c.ok("two tasks created/deduped", len(created) == 2, f"refs={sorted(created)}")
    c.ok("board targeted = shaula-smoke", out.get("board") == _SMOKE_BOARD)

    draft_id = created.get("draft", {}).get("id")
    review_id = created.get("review", {}).get("id")
    c.ok("emitter resolved DAG edge (review.parents == [draft_id])",
         created.get("review", {}).get("parents") == [draft_id],
         f"review.parents={created.get('review', {}).get('parents')}")

    # Read the server state back and assert it persisted.
    print("\n[B2] read-back — the server actually persisted it")

    boards = _http_get(base_url, f"{_KANBAN}/boards", token)
    slugs = [b.get("slug") for b in boards.get("boards", [])]
    c.ok("board exists server-side", _SMOKE_BOARD in slugs, f"boards={slugs}")

    board = _http_get(base_url, f"{_KANBAN}/board?board={urllib.parse.quote(_SMOKE_BOARD)}", token)
    cols = {col["name"]: col.get("tasks", []) for col in board.get("columns", [])}
    triage_ids = [t.get("id") for t in cols.get("triage", [])]
    running_ids = [t.get("id") for t in cols.get("running", [])]

    c.ok("triage step landed in the triage column", draft_id in triage_ids,
         f"triage={triage_ids}")
    c.ok("dispatch DRY-RUN spawned nothing (running column empty)",
         len(running_ids) == 0, f"running={running_ids}")
    c.ok("tenant present on the board", "verify-practice" in json.dumps(board.get("tenants", [])),
         f"tenants={board.get('tenants')}")

    if review_id:
        detail = _http_get(
            base_url, f"{_KANBAN}/tasks/{review_id}?board={urllib.parse.quote(_SMOKE_BOARD)}", token)
        task = detail.get("task", {})
        links = detail.get("links", {})
        c.ok("DAG edge persisted (review links.parents == [draft_id])",
             links.get("parents") == [draft_id], f"links.parents={links.get('parents')}")
        c.ok("tenant persisted on the review row", task.get("tenant") == "verify-practice",
             repr(task.get("tenant")))
        c.ok("max_runtime_seconds persisted on the review row",
             task.get("max_runtime_seconds") == 300, repr(task.get("max_runtime_seconds")))

    # Evidence (not asserted — DispatchResult shape isn't pinned; the durable
    # invariant 'running is empty' above is the real proof dispatch was a no-op).
    print(f"\n  dispatch dry-run result: {json.dumps(out.get('dispatch'))}")


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Shaula workflow builder end-to-end smoke.")
    ap.add_argument("--base-url", default=os.environ.get("SHAULA_DASHBOARD_URL", "http://127.0.0.1:8200"),
                    help="dashboard base URL (default 127.0.0.1:8200 or $SHAULA_DASHBOARD_URL)")
    ap.add_argument("--session-token", default=os.environ.get("HERMES_DASHBOARD_SESSION_TOKEN"),
                    help="dashboard session token (default: auto-discovered from index.html)")
    ap.add_argument("--offline-only", action="store_true",
                    help="run only PHASE A (skip the live dashboard checks)")
    args = ap.parse_args()

    c = Checks()
    phase_a(c)

    if args.offline_only:
        print("\n(--offline-only: skipping live PHASE B)")
    else:
        # Resolve the token once (explicit flag / env, else the browser trick),
        # so the liveness probe can authenticate against an auth-on backend.
        token = args.session_token or discover_token(args.base_url)
        if reachable(args.base_url, token):
            phase_b(c, args.base_url, token)
        else:
            print(f"\n=== PHASE B — SKIPPED (no dashboard at {args.base_url}) ===")
            print("  start one with:  bin/shaula --local dashboard --port 8200 --no-open --skip-build")

    print(f"\n{'='*52}\nRESULT: {c.passed} passed, {c.failed} failed")
    return 0 if c.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
