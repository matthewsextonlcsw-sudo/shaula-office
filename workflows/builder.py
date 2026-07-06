#!/usr/bin/env python3
"""Shaula workflow builder — a JSON template → a Hermes kanban task-graph.

The no-code workflow layer (DECISIONS D14). A therapist (or Shaula acting on
their behalf) describes a multi-step job as a small JSON template — a DAG of
tasks, each assigned to one of the 15 vetted staff profiles — and this module
*instantiates* it as real rows on the live Hermes kanban board, wiring the
dependency edges so the existing dispatcher runs them in the right order.

Why this exists (the D14 finding): the kanban board is ALREADY a complete
workflow ENGINE — DAG dependencies, auto-decompose, profile-dispatched workers,
honesty rules baked into the seeded prompts. The only missing piece for
therapist self-serve was a safe BUILDER that turns a declarative template into
that task-graph. This is that builder. It ports quentintou/agent-board's
template→task mechanism (MIT) onto Hermes' own `POST /tasks` + `parents=[…]`
DAG-at-create contract.

The guardrails are the whole point. A therapist-built workflow is *composition*
of vetted parts, never new blast radius:

  1. ASSIGNEE ALLOW-LIST — every step must target one of the 15 vetted profiles
     (VETTED_PROFILES). An unknown assignee is rejected. Therapists compose the
     existing staff; they cannot summon a new agent with new powers.
  2. PHI GATE — the six PHI-touching profiles are refused unless the template
     explicitly opts in (`allow_phi: true`) AND the caller passes allow_phi=True;
     and any PHI step must run in the practice's own `dir:` workspace, never
     ephemeral scratch. Default is no-PHI-only — preserving house-nothing and
     the gated-PHI rule.
  3. HONESTY LINT — every template-authored string (post-variable-substitution)
     is run through the SAME linter that guards the site generator
     (engine/generate.py:lint). A banned claim — fabricated stats, "proven/
     guaranteed", "studies show", testimonials, "cure", "#1", … — aborts
     instantiation before anything is written. Each emitted task body is then
     prefixed with the honesty + house-nothing preamble (which is trusted
     boilerplate and is itself never linted).
  4. ACYCLIC — dependencies form a DAG; a cycle, a dangling ref, or a duplicate
     ref is rejected up front (Kahn topological sort).

Scope — what the builder does, and what it deliberately does NOT:
  • DOES: create the task-graph; optionally create/target the board that holds
    it (`POST /boards`, idempotent — "create your own boards"); optionally kick
    a dispatch pass (`POST /dispatch`) so a workflow can build *and* run in one
    shot. Per-step it covers every safe CreateTaskBody field, incl. `triage`
    (land in the triage column for human approval before running) and
    `max_runtime_seconds` (a per-task runtime cap), plus a template-level
    `tenant` (per-practice isolation).
  • DOES NOT (conscious omissions, not gaps): `goal_mode`/`goal_max_turns`
    (unbounded agentic looping — more blast radius than a therapist no-code
    workflow should grant); and the task-edit / delete / link-rewrite / reassign
    / comment / attachment lifecycle endpoints (those are runtime board
    management — the dashboard's job, not build-time instantiation).

Architecture: the pure-stdlib domain layer (load / validate / topo-sort / plan)
is separated from the HTTP emitter, so the entire guardrail surface is
unit-testable with zero network. The emitter takes an injectable transport for
the same reason.

Pure stdlib (urllib for HTTP) — no third-party deps, matching the engine ethos.

Run:  python3 -m workflows.cli --help
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# Import the ONE honesty linter (single source of truth). engine/generate.py
# self-bootstraps its own sibling import (citations) on import, and is guarded
# by `if __name__ == "__main__"`, so importing it here is side-effect-safe.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
from engine.generate import lint as _honesty_lint  # noqa: E402


# --------------------------------------------------------------------------- #
# Vetted ground truth (verified against profiles/). The
# strategist + distributor content-engine roles (OpenGrowth growth-engine /
# distribution-engine) added 2026-06-07.
# --------------------------------------------------------------------------- #
VETTED_PROFILES: frozenset[str] = frozenset({
    "analytics", "biller", "blog", "clinical-admin", "customer-service",
    "distributor", "frontdesk", "marketer", "orchestrator", "reviewer",
    "sarah", "scribe", "strategist", "website", "workspace",
})

# The six profiles that may touch PHI (HARNESS.md staff table). Work assigned to
# any of these is gated: explicit opt-in + a practice-owned dir workspace.
PHI_PROFILES: frozenset[str] = frozenset({
    "workspace", "frontdesk", "customer-service", "scribe", "biller",
    "clinical-admin",
})

# agent-board uses string priorities; Hermes CreateTaskBody.priority is an int.
PRIORITY_MAP: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "urgent": 3}

# Prepended to every emitted task body. TRUSTED boilerplate — deliberately NOT
# run through the honesty linter (it names the banned phrases as negatives).
HONESTY_PREAMBLE: str = (
    "[SHAULA HOUSE RULES — non-negotiable]\n"
    "- Honesty engine: no fabricated statistics or percentages; no "
    '"proven / guaranteed / clinically proven"; no "studies show / research '
    'proves"; no invented testimonials; no "cure / miracle"; no '
    '"#1 / best therapist / world-class". If you lack a real source, say so '
    "and omit the claim.\n"
    "- House-nothing: store no PHI outside the practice's own Google. This "
    "office houses nothing.\n"
    "- Run the office, not the therapy: never handle a clinical crisis; defer "
    "every clinical decision to the licensed clinician.\n"
    "\n---\n\n"
)

_TOKEN_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class WorkflowError(ValueError):
    """Raised on any template / instantiation guardrail violation.

    Carries an optional list of individual `violations` so callers (CLI, UI)
    can show every problem at once rather than one-at-a-time.
    """

    def __init__(self, message: str, violations: Optional[list[str]] = None):
        super().__init__(message)
        self.violations = violations or []


# --------------------------------------------------------------------------- #
# Domain model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class WorkflowStep:
    ref: str
    title: str
    assignee: str
    description: str = ""
    dependencies: tuple[str, ...] = ()
    priority: str = "medium"
    skills: tuple[str, ...] = ()
    workspace_kind: Optional[str] = None       # overrides the template default
    workspace_path: Optional[str] = None
    requires_review: bool = False
    tags: tuple[str, ...] = ()
    triage: bool = False                        # land in triage (human-gate) first
    max_runtime_seconds: Optional[int] = None   # per-task runtime cap


@dataclass(frozen=True)
class BoardSpec:
    """A kanban board this workflow lives on. `slug` is the directory key;
    the rest is display metadata. POST /boards is idempotent on slug."""
    slug: str
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None


@dataclass(frozen=True)
class WorkflowTemplate:
    name: str
    description: str
    steps: tuple[WorkflowStep, ...]
    variables: tuple[str, ...] = ()            # declared variable names
    allow_phi: bool = False
    default_workspace_kind: str = "scratch"
    default_workspace_path: Optional[str] = None
    tenant: Optional[str] = None               # per-practice isolation key
    board: Optional[BoardSpec] = None          # the board to create/target


# --------------------------------------------------------------------------- #
# Loading (dict → dataclass). Strict: unknown shapes fail loudly.
# --------------------------------------------------------------------------- #
def _as_str_tuple(value: Any, fieldname: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise WorkflowError(f"{fieldname} must be a list of strings")
    return tuple(value)


def load_template(data: dict) -> WorkflowTemplate:
    """Parse a JSON-loaded dict into a WorkflowTemplate. Raises WorkflowError."""
    if not isinstance(data, dict):
        raise WorkflowError("template must be a JSON object")
    for required in ("name", "steps"):
        if required not in data:
            raise WorkflowError(f"template missing required field: {required!r}")
    raw_steps = data["steps"]
    if not isinstance(raw_steps, list) or not raw_steps:
        raise WorkflowError("template.steps must be a non-empty list")

    steps: list[WorkflowStep] = []
    for i, s in enumerate(raw_steps):
        if not isinstance(s, dict):
            raise WorkflowError(f"step[{i}] must be an object")
        for required in ("ref", "title", "assignee"):
            if not s.get(required):
                raise WorkflowError(f"step[{i}] missing required field: {required!r}")
        steps.append(WorkflowStep(
            ref=s["ref"],
            title=s["title"],
            assignee=s["assignee"],
            description=s.get("description", ""),
            dependencies=_as_str_tuple(s.get("dependencies"), f"step[{i}].dependencies"),
            priority=s.get("priority", "medium"),
            skills=_as_str_tuple(s.get("skills"), f"step[{i}].skills"),
            workspace_kind=s.get("workspace_kind"),
            workspace_path=s.get("workspace_path"),
            requires_review=bool(s.get("requires_review", False)),
            tags=_as_str_tuple(s.get("tags"), f"step[{i}].tags"),
            triage=bool(s.get("triage", False)),
            max_runtime_seconds=s.get("max_runtime_seconds"),
        ))

    raw_board = data.get("board")
    board: Optional[BoardSpec] = None
    if raw_board is not None:
        if not isinstance(raw_board, dict) or not raw_board.get("slug"):
            raise WorkflowError("template.board must be an object with a 'slug'")
        board = BoardSpec(
            slug=raw_board["slug"],
            name=raw_board.get("name"),
            description=raw_board.get("description"),
            icon=raw_board.get("icon"),
            color=raw_board.get("color"),
        )

    tenant = data.get("tenant")
    if tenant is not None and not isinstance(tenant, str):
        raise WorkflowError("template.tenant must be a string")

    return WorkflowTemplate(
        name=data["name"],
        description=data.get("description", ""),
        steps=tuple(steps),
        variables=_as_str_tuple(data.get("variables"), "template.variables"),
        allow_phi=bool(data.get("allow_phi", False)),
        default_workspace_kind=data.get("default_workspace_kind", "scratch"),
        default_workspace_path=data.get("default_workspace_path"),
        tenant=tenant,
        board=board,
    )


def load_template_file(path: str) -> WorkflowTemplate:
    with open(path, encoding="utf-8") as fh:
        return load_template(json.load(fh))


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def _effective_workspace(step: WorkflowStep, tmpl: WorkflowTemplate) -> tuple[str, Optional[str]]:
    kind = step.workspace_kind or tmpl.default_workspace_kind
    path = step.workspace_path or tmpl.default_workspace_path
    return kind, path


def topo_sort(steps: tuple[WorkflowStep, ...]) -> list[WorkflowStep]:
    """Kahn topological sort. Deterministic: preserves input order among ready
    nodes. Raises WorkflowError on a cycle (reporting the stuck refs)."""
    by_ref = {s.ref: s for s in steps}
    indeg = {s.ref: 0 for s in steps}
    children: dict[str, list[str]] = {s.ref: [] for s in steps}
    for s in steps:
        for dep in s.dependencies:
            if dep not in by_ref:
                continue  # dangling ref — validate() reports it; not a cycle
            indeg[s.ref] += 1
            children[dep].append(s.ref)

    ready = [s.ref for s in steps if indeg[s.ref] == 0]  # input order
    order: list[str] = []
    while ready:
        ref = ready.pop(0)
        order.append(ref)
        for child in children[ref]:
            indeg[child] -= 1
            if indeg[child] == 0:
                ready.append(child)

    if len(order) != len(steps):
        stuck = sorted(r for r in indeg if r not in order)
        raise WorkflowError(
            "dependency cycle detected among steps: " + ", ".join(stuck),
            violations=[f"cycle involves: {', '.join(stuck)}"],
        )
    return [by_ref[r] for r in order]


def _substitute(text: str, variables: dict[str, str], unknown: set[str]) -> str:
    """Replace {tokens} from `variables`; record any unknown token name."""
    def repl(m: re.Match) -> str:
        name = m.group(1)
        if name in variables:
            return str(variables[name])
        unknown.add(name)
        return m.group(0)
    return _TOKEN_RE.sub(repl, text)


# --------------------------------------------------------------------------- #
# Validation — every guardrail, all violations collected
# --------------------------------------------------------------------------- #
def validate(tmpl: WorkflowTemplate, *, allow_phi: bool = False) -> None:
    """Structural + policy validation (no variable substitution, no network).
    Raises WorkflowError listing every violation found."""
    v: list[str] = []

    # Unique refs.
    seen: set[str] = set()
    for s in tmpl.steps:
        if s.ref in seen:
            v.append(f"duplicate step ref: {s.ref!r}")
        seen.add(s.ref)

    # Assignee allow-list.
    for s in tmpl.steps:
        if s.assignee not in VETTED_PROFILES:
            v.append(
                f"step {s.ref!r}: assignee {s.assignee!r} is not a vetted "
                f"profile (allowed: {', '.join(sorted(VETTED_PROFILES))})"
            )

    # Priority vocabulary.
    for s in tmpl.steps:
        if s.priority not in PRIORITY_MAP:
            v.append(
                f"step {s.ref!r}: priority {s.priority!r} invalid "
                f"(use one of {', '.join(PRIORITY_MAP)})"
            )

    # Runtime cap, if set, must be a positive integer.
    for s in tmpl.steps:
        mrs = s.max_runtime_seconds
        if mrs is not None and (not isinstance(mrs, int) or isinstance(mrs, bool) or mrs <= 0):
            v.append(
                f"step {s.ref!r}: max_runtime_seconds must be a positive integer "
                f"(got {mrs!r})"
            )

    # Dependency refs must exist.
    for s in tmpl.steps:
        for dep in s.dependencies:
            if dep not in seen:
                v.append(f"step {s.ref!r}: depends on unknown ref {dep!r}")

    # PHI gate.
    phi_steps = [s for s in tmpl.steps if s.assignee in PHI_PROFILES]
    if phi_steps:
        if not (tmpl.allow_phi and allow_phi):
            names = ", ".join(f"{s.ref}→{s.assignee}" for s in phi_steps)
            v.append(
                "PHI-touching steps present (" + names + ") but PHI is not "
                "enabled. A PHI workflow requires `allow_phi: true` in the "
                "template AND allow_phi=True at instantiation."
            )
        for s in phi_steps:
            kind, path = _effective_workspace(s, tmpl)
            if kind != "dir" or not path:
                v.append(
                    f"step {s.ref!r} ({s.assignee}) handles PHI and must run in "
                    "a practice-owned dir workspace (workspace_kind=\"dir\" + "
                    "workspace_path), never ephemeral scratch."
                )

    # Honesty lint on raw authored strings (fast pre-substitution pass; the
    # authoritative post-substitution lint runs in build_plan).
    for s in tmpl.steps:
        for label, text in (("title", s.title), ("description", s.description)):
            hits = _honesty_lint(text)
            if hits:
                v.append(f"step {s.ref!r} {label}: banned language {hits}")

    # Cycle / dangling structure (only meaningful once refs validated).
    try:
        topo_sort(tmpl.steps)
    except WorkflowError as e:
        v.extend(e.violations or [str(e)])

    if v:
        raise WorkflowError(
            f"template {tmpl.name!r} failed validation ({len(v)} issue(s))",
            violations=v,
        )


# --------------------------------------------------------------------------- #
# Planning — template (+ variables) → ordered, network-free task payloads
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PlannedTask:
    ref: str
    dep_refs: tuple[str, ...]
    payload: dict[str, Any]          # CreateTaskBody-shaped, minus `parents`


def build_plan(
    tmpl: WorkflowTemplate,
    variables: Optional[dict[str, str]] = None,
    *,
    allow_phi: bool = False,
    instance_key: Optional[str] = None,
) -> list[PlannedTask]:
    """Validate, substitute variables, topo-sort, and produce the ordered list
    of task payloads. `parents` is intentionally absent — the emitter resolves
    dep refs to real ids at create time (parents-first, guaranteed by order)."""
    variables = variables or {}
    validate(tmpl, allow_phi=allow_phi)

    # All declared variables must be supplied.
    missing = [name for name in tmpl.variables if name not in variables]
    if missing:
        raise WorkflowError(
            f"missing required variable(s): {', '.join(missing)}",
            violations=[f"variable {m!r} not provided" for m in missing],
        )

    unknown: set[str] = set()
    ordered = topo_sort(tmpl.steps)
    plan: list[PlannedTask] = []
    lint_hits: list[str] = []

    for s in ordered:
        title = _substitute(s.title, variables, unknown)
        desc = _substitute(s.description, variables, unknown)

        # Authoritative honesty lint on the FINAL authored strings (post
        # substitution — a variable could smuggle in a banned claim). The
        # trusted preamble is added AFTER linting and is never itself linted.
        for label, text in (("title", title), ("description", desc)):
            hits = _honesty_lint(text)
            if hits:
                lint_hits.append(f"step {s.ref!r} {label}: banned language {hits}")

        body_parts = [desc] if desc else []
        if s.requires_review:
            body_parts.append(
                "[REQUIRES HUMAN REVIEW — do not publish or send this output "
                "until the licensed clinician (or a human reviewer) approves it.]"
            )
        if s.tags:
            body_parts.append(f"[tags: {', '.join(s.tags)}]")
        authored = "\n\n".join(body_parts).strip()
        body = HONESTY_PREAMBLE + authored if authored else HONESTY_PREAMBLE.rstrip()

        kind, path = _effective_workspace(s, tmpl)
        payload: dict[str, Any] = {
            "title": title,
            "body": body,
            "assignee": s.assignee,
            "priority": PRIORITY_MAP[s.priority],
            "workspace_kind": kind,
        }
        if path:
            payload["workspace_path"] = path
        if s.skills:
            payload["skills"] = list(s.skills)
        if s.triage:
            payload["triage"] = True
        if s.max_runtime_seconds:
            payload["max_runtime_seconds"] = s.max_runtime_seconds
        if tmpl.tenant:
            payload["tenant"] = tmpl.tenant
        if instance_key:
            payload["idempotency_key"] = f"{instance_key}:{s.ref}"

        plan.append(PlannedTask(ref=s.ref, dep_refs=s.dependencies, payload=payload))

    problems: list[str] = []
    if unknown:
        problems.extend(f"unknown variable token {{{u}}}" for u in sorted(unknown))
    problems.extend(lint_hits)
    if problems:
        raise WorkflowError(
            f"template {tmpl.name!r} failed at plan time ({len(problems)} issue(s))",
            violations=problems,
        )
    return plan


# --------------------------------------------------------------------------- #
# Emitter — the only I/O. Injectable transport keeps it unit-testable.
# --------------------------------------------------------------------------- #
Transport = Callable[[str, dict[str, Any]], dict[str, Any]]  # (path, body) -> resp

_KANBAN_PREFIX = "/api/plugins/kanban"


class KanbanEmitter:
    """POSTs a plan to a live Hermes dashboard's kanban plugin API.

    Auth: sends the dashboard session token as both the X-Hermes-Session-Token
    header and a Bearer Authorization header (the server accepts either). Launch
    the dashboard with a known HERMES_DASHBOARD_SESSION_TOKEN so this can
    authenticate non-interactively.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:9119",
        session_token: Optional[str] = None,
        *,
        board: Optional[str] = None,
        timeout: int = 30,
        transport: Optional[Transport] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.session_token = session_token
        self.board = board
        self.timeout = timeout
        self._transport = transport or self._http

    def _http(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = self.base_url + path
        # Task / link / dispatch calls are board-scoped; the /boards CRUD itself
        # is not (it manages boards, it doesn't live inside one).
        if self.board and not path.rstrip("/").endswith("/boards"):
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}board={urllib.parse.quote(self.board)}"
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.session_token:
            req.add_header("X-Hermes-Session-Token", self.session_token)
            req.add_header("Authorization", f"Bearer {self.session_token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            raise WorkflowError(
                f"kanban API {e.code} on POST {path}: {detail[:300]}"
            ) from e
        except urllib.error.URLError as e:
            raise WorkflowError(
                f"cannot reach kanban API at {self.base_url} — is the dashboard "
                f"running? ({e})"
            ) from e

    def ensure_board(self, spec: "BoardSpec", *, switch: bool = False) -> dict[str, Any]:
        """Create the board (idempotent on slug — a collision returns the
        existing one) and target it for every subsequent task POST."""
        body: dict[str, Any] = {"slug": spec.slug}
        for k in ("name", "description", "icon", "color"):
            val = getattr(spec, k)
            if val:
                body[k] = val
        if switch:
            body["switch"] = True
        resp = self._transport(_KANBAN_PREFIX + "/boards", body)
        self.board = spec.slug
        return resp or {}

    def run_dispatch(self, max_n: int = 8, *, dry_run: bool = False) -> dict[str, Any]:
        """Kick one dispatch pass on the (current/target) board. Spawns workers
        for up to `max_n` ready+assigned tasks. `dry_run=True` previews what
        WOULD be dispatched without spawning anything."""
        path = f"{_KANBAN_PREFIX}/dispatch?max={int(max_n)}"
        if dry_run:
            path += "&dry_run=true"
        return self._transport(path, {}) or {}

    def emit(self, plan: list[PlannedTask]) -> list[dict[str, Any]]:
        """Create every task in topo order, resolving dep refs → real ids and
        passing them as `parents`. Returns one record per created task."""
        ref_to_id: dict[str, str] = {}
        created: list[dict[str, Any]] = []
        for node in plan:
            payload = dict(node.payload)
            payload["parents"] = [ref_to_id[r] for r in node.dep_refs]
            resp = self._transport(_KANBAN_PREFIX + "/tasks", payload)
            task = (resp or {}).get("task") or {}
            tid = task.get("id")
            if not tid:
                raise WorkflowError(
                    f"kanban API returned no task id for step {node.ref!r}: {resp!r}"
                )
            ref_to_id[node.ref] = tid
            created.append({
                "ref": node.ref,
                "id": tid,
                "assignee": payload.get("assignee"),
                "parents": payload["parents"],
                "warning": (resp or {}).get("warning"),
            })
        return created


# --------------------------------------------------------------------------- #
# Top-level convenience
# --------------------------------------------------------------------------- #
def instantiate(
    tmpl: WorkflowTemplate,
    variables: Optional[dict[str, str]] = None,
    *,
    base_url: str = "http://127.0.0.1:9119",
    session_token: Optional[str] = None,
    board: Optional[str] = None,
    create_board: bool = False,
    dispatch: bool = False,
    dispatch_max: int = 8,
    dispatch_dry_run: bool = False,
    allow_phi: bool = False,
    instance_key: Optional[str] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Build the plan and (unless dry_run) emit it to the live board.

    Board: an explicit `board` slug overrides the template's `board.slug`. With
    `create_board=True` the board is created (idempotent) before the tasks land.
    Dispatch: with `dispatch=True`, one dispatch pass is kicked after creation
    so the workflow builds *and* runs. `dispatch_dry_run=True` previews what the
    dispatcher WOULD spawn without actually spawning workers (safe verification).
    """
    plan = build_plan(tmpl, variables, allow_phi=allow_phi, instance_key=instance_key)

    # Effective board: explicit arg wins, else the template's declared board.
    slug = board or (tmpl.board.slug if tmpl.board else None)

    if dry_run:
        return {
            "template": tmpl.name,
            "dry_run": True,
            "board": slug,
            "tenant": tmpl.tenant,
            "dispatch": bool(dispatch),
            "tasks": [
                {"ref": p.ref, "depends_on": list(p.dep_refs), **p.payload}
                for p in plan
            ],
        }

    emitter = KanbanEmitter(base_url, session_token, board=slug)
    board_result: Optional[dict[str, Any]] = None
    if create_board:
        if not slug:
            raise WorkflowError(
                "create_board requested but no board slug — set template.board.slug "
                "or pass board=…"
            )
        # Use the template's display metadata when its slug matches; otherwise a
        # bare slug (an explicit override targets/creates that slug).
        spec = tmpl.board if (tmpl.board and tmpl.board.slug == slug) else BoardSpec(slug=slug)
        board_result = emitter.ensure_board(spec)

    created = emitter.emit(plan)
    out: dict[str, Any] = {
        "template": tmpl.name,
        "dry_run": False,
        "board": slug,
        "created": created,
    }
    if board_result is not None:
        out["board_result"] = board_result
    if dispatch:
        out["dispatch"] = emitter.run_dispatch(dispatch_max, dry_run=dispatch_dry_run)
    return out
