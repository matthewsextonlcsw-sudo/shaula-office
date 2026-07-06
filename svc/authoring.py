"""authoring — therapist self-serve workflow authoring, svc adapter (P2).

Wraps ``workflows.author`` for the multi-tenant svc. A therapist's plain-language
request becomes a vetted, honesty-gated workflow PREVIEW (draft, for approval),
and an approved template becomes svc run-steps the EXISTING runner executes
(``to_run_steps`` / ``prepare_run``) — no runner change, the same honesty-gated
text executor every built-in capability uses.

The model is UNTRUSTED. ``draft_preview`` and ``prepare_run`` re-validate every
byte through ``workflows.builder`` (assignee allow-list + PHI gate + honesty lint
+ acyclic DAG) before anything can become a task. A non-vetted assignee or a
banned claim is rejected, never executed — the "compose vetted parts, no new
blast radius" invariant.

Model = the svc's Vertex brain by default (``svc.gemini.generate_text``);
injectable via ``MODEL`` so tests run a stub with zero network. No PHI: requests
are business descriptions, never client data.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from typing import Any, Callable

from . import config, gemini

if str(config.REPO) not in sys.path:
    sys.path.insert(0, str(config.REPO))

from workflows import author as _author  # noqa: E402
from workflows.builder import (  # noqa: E402
    PlannedTask,
    WorkflowError,
    build_plan,
    load_template,
    validate,
)

AuthoringError = _author.AuthoringError

Model = Callable[[str, str], str]


def _vertex_model(system: str, user: str) -> str:
    return gemini.generate_text(system, user)


# Injectable so tests inject a stub (no network). Prod = the svc's Vertex brain.
MODEL: Model = _vertex_model


def _repairable_model(model: Model) -> Model:
    """Adapt a model for ``draft_workflow``'s repair loop.

    A drafted workflow's RAW text is honesty-linted inside ``gemini.generate_text``
    (the moat runs on every model byte), so a banned first sketch surfaces there as
    ``BrainError('honesty')``. But ``workflows.author`` is decoupled from gemini and
    only speaks ``AuthoringError``. Translate the honesty trip into that language so
    the repair loop RE-PROMPTS with the offending phrases fed back — a stray banned
    word becomes a redraw, not a 500. A real brain failure (vertex_auth / vertex_http
    / vertex_network / vertex_malformed / vertex_empty) is NOT a content problem; it
    propagates untouched so the svc reports an outage as an outage, never masked as
    "couldn't write honestly".

    Only the WORKFLOW path is wrapped. ``draft_skill`` keeps the raw ``BrainError``
    (its contract: a banned skill claim is "never auto-repaired") so its refusal stays
    an honest hard stop, categorized 'honesty' by ``draft_preview`` below.
    """

    def repairable(system: str, user: str) -> str:
        try:
            return model(system, user)
        except gemini.BrainError as exc:
            if exc.category != "honesty":
                raise  # outage, not banned language — surface it honestly
            plain = [r.get("plain", "") for r in getattr(exc, "explanations", [])]
            raise AuthoringError(
                "draft used banned language",
                violations=[p for p in plain if p] or [exc.detail or exc.category],
            ) from exc

    return repairable


# --------------------------------------------------------------------------- #
# Idempotency / double-click replay for authored runs (svc workflows_create).
# Mirrors create_run's _replay_run, with ONE correction: the no-key double-click
# guard keys on a TEMPLATE FINGERPRINT, not capability+topic. Every authored run
# shares capability "authored" and an empty topic, so create_run's heuristic
# would falsely dedupe two DIFFERENT workflows submitted within the window. The
# fingerprint fires the guard only on a genuine re-submit of the same template;
# the explicit idempotencyKey path is the reliable dedup a client should use.
# --------------------------------------------------------------------------- #
DOUBLE_CLICK_WINDOW_S = 10
_REPLAYABLE = ("queued", "queued_next_cycle", "working", "needs_approval")


def template_fingerprint(template: dict) -> str:
    """Stable short hash of a workflow template — identifies a re-submit of the
    exact same authored workflow (the key-insensitive double-click guard)."""
    blob = json.dumps(template, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def find_replay(
    runs: list[dict],
    idempotency_key: str,
    fingerprint: str,
    *,
    now: int | None = None,
    window: int = DOUBLE_CLICK_WINDOW_S,
) -> dict | None:
    """Return an existing authored run to replay instead of creating a new one.

    1. Explicit key: the same idempotencyKey always replays its run — a retry
       storm can never queue a second billable Vertex chain.
    2. No key: a rapid re-submit of the SAME template (same fingerprint, still
       replayable, within ``window`` seconds) replays — the double-click guard.
    """
    key = (idempotency_key or "").strip()[:80]
    if key:
        return next((r for r in runs if r.get("idempotencyKey") == key), None)
    newest = runs[0] if runs else None
    if (
        newest
        and newest.get("capability") == "authored"
        and newest.get("templateFingerprint") == fingerprint
        and int(now if now is not None else time.time()) - int(newest.get("createdAt", 0)) <= window
        and newest.get("status") in _REPLAYABLE
    ):
        return newest
    return None


def authored_over_cap(state: dict, tier: str, *, month: str | None = None) -> bool:
    """True when this practice has hit its silent monthly task cap. Authored runs
    then queue (queued_next_cycle) instead of spawning, exactly like create_run —
    this is what bounds per-tenant Vertex spend. config.cap_for resolves the tier
    word; an unknown tier falls back to the default cap."""
    m = month or time.strftime("%Y-%m")
    used = int((state.get("usage") or {}).get(m, 0))
    return used >= config.cap_for(tier)


# --------------------------------------------------------------------------- #
# Draft idempotency / double-click coalesce (svc workflows_draft).
#
# The create-side guards above bound a *run*; these bound a *preview*. A draft is
# an ephemeral, model-generated preview that costs up to THREE Vertex calls (the
# draft_workflow repair loop is ≤2, plus an optional skill draft) yet persists no
# run to dedup against — so create's find_replay/authored_over_cap can't protect
# it. The draft endpoint therefore caches recent previews and coalesces a repeat
# request onto the cached one: a retry storm or a double-click can never spend a
# second Vertex chain.
#
# ONE correction vs the create-side fingerprint: a draft fingerprints its INPUTS
# (description + withSkill), never the model OUTPUT. The model is non-deterministic
# — the same request yields a different template each call — so hashing the output
# would never match on a genuine re-submit. The input fingerprint fires the
# double-click guard exactly when the caller asked for the same thing again.
# --------------------------------------------------------------------------- #
DRAFT_REPLAY_WINDOW_S = 30  # a draft is heavier than a click; a human "did it
#                             work? click again" pause runs longer than create's 10s.


def draft_fingerprint(description: str, with_skill: bool) -> str:
    """Stable short hash of a draft REQUEST (its inputs) — identifies a re-submit of
    the same plain-language ask (the key-insensitive double-click guard). Hashes the
    inputs, NOT the non-deterministic model output. withSkill is part of the identity
    because it drives an extra Vertex call."""
    blob = json.dumps(
        {"description": (description or "").strip(), "withSkill": bool(with_skill)},
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def find_draft_replay(
    drafts: list[dict],
    idempotency_key: str,
    fingerprint: str,
    *,
    now: int | None = None,
    window: int = DRAFT_REPLAY_WINDOW_S,
) -> dict | None:
    """Return a cached preview to replay instead of spending a new Vertex chain.

    1. Explicit key: the same idempotencyKey always replays its cached preview — a
       retry can never spend a second (up to 3-call) draft.
    2. No key: a rapid re-submit of the SAME request (same input fingerprint, within
       ``window`` seconds) replays — the double-click guard.

    Returns the cached ``preview`` dict, or None when nothing matches.
    """
    key = (idempotency_key or "").strip()[:80]
    if key:
        hit = next((d for d in drafts if d.get("idempotencyKey") == key), None)
        return hit.get("preview") if hit else None
    newest = drafts[0] if drafts else None
    if (
        newest
        and newest.get("fingerprint") == fingerprint
        and int(now if now is not None else time.time()) - int(newest.get("createdAt", 0)) <= window
    ):
        return newest.get("preview")
    return None


def _preview_steps(plan: list[PlannedTask]) -> list[dict]:
    return [
        {
            "ref": p.ref,
            "assignee": p.payload["assignee"],
            "title": p.payload["title"],
            "dependsOn": list(p.dep_refs),
            "isReview": p.payload["assignee"] == "reviewer",
        }
        for p in plan
    ]


def draft_preview(description: str, project: str, *, with_skill: bool = False) -> dict:
    """Plain-language request -> {name, description, steps[], template, skill?} for
    therapist review. Raises AuthoringError if no vetted/honest workflow drafts."""
    # Workflow path uses the repair-aware model: an honesty trip is re-prompted, not
    # a 500. The skill path below keeps the raw MODEL — its honesty trip is a hard
    # stop ('honesty'), never repaired.
    tmpl = _author.draft_workflow(description, project, _repairable_model(MODEL))
    plan = build_plan(tmpl, {}, allow_phi=False)
    out: dict[str, Any] = {
        "name": tmpl.name,
        "description": tmpl.description,
        "steps": _preview_steps(plan),
        # The validated template rides back so the client can approve + resubmit
        # it to /create verbatim (which re-validates — the client is untrusted too).
        "template": _template_to_dict(tmpl),
    }
    if with_skill:
        try:
            out["skill"] = _author.draft_skill(
                f"staff guidance for: {description}", project, MODEL
            )
        except gemini.BrainError as exc:
            out["skillRefused"] = {"category": exc.category}  # honesty gate fired
        except AuthoringError:
            out["skillRefused"] = {"category": "draft_failed"}
    return out


def to_run_steps(plan: list[PlannedTask]) -> list[dict]:
    """Authored kanban plan -> the svc run-step shape ``runner._run_text_capability``
    executes, so an authored workflow runs through the SAME honesty-gated executor
    as every built-in capability. The reviewer step is the honesty/approval gate."""
    steps: list[dict] = []
    for i, p in enumerate(plan):
        assignee = p.payload["assignee"]
        steps.append(
            {
                "index": i,
                "ref": p.ref,
                "assignee": assignee,
                "title": p.payload["title"],
                # body carries the HONESTY_PREAMBLE build_plan prepends.
                "instruction": p.payload["body"],
                "isReview": assignee == "reviewer",
                "isGate": bool(p.payload.get("triage")),
                "status": "pending",
                "output": "",
            }
        )
    return steps


def prepare_run(template: dict) -> dict:
    """Validate a (client-supplied, untrusted) template and shape it into run
    steps. The safety wall: a non-vetted assignee / banned claim / cycle is
    rejected here before any task is created. Raises AuthoringError."""
    try:
        tmpl = load_template(template)
        validate(tmpl, allow_phi=False)
        plan = build_plan(tmpl, {}, allow_phi=False)
    except WorkflowError as exc:
        raise AuthoringError(
            f"workflow failed validation: {exc}", violations=exc.violations or [str(exc)]
        ) from exc
    return {"name": tmpl.name, "steps": to_run_steps(plan)}


def _template_to_dict(tmpl) -> dict:
    """Round-trip a validated WorkflowTemplate back to the JSON shape /create
    accepts (concrete authored templates: no variables, no PHI)."""
    return {
        "name": tmpl.name,
        "description": tmpl.description,
        "steps": [
            {
                "ref": s.ref,
                "title": s.title,
                "assignee": s.assignee,
                "description": s.description,
                "dependencies": list(s.dependencies),
                "requires_review": s.requires_review,
            }
            for s in tmpl.steps
        ],
    }
