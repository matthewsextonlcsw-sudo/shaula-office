"""app — shaula-svc HTTP surface (D-FreeStaff, FastAPI).

Multi-tenant office runtime for the practice-facing apps. Callers are
the apps' SERVERS (x-internal-secret), never browsers; practiceId arrives
in the path from the caller's verified session — this service trusts its
peers, not the public.

Surface (everything the Staff page needs):
    GET  /healthz                                  liveness (no auth)
    GET  /v1/roster                                staff + per-staff capability menus
                                                   (+ real read `surface`s — the
                                                   Office Manager fronts the inquiry
                                                   inbox, the Analyst fronts /stats)
    GET  /v1/practices/{pid}                       profile + slug + siteUrl + usage
                                                   (+ missingForWebsite/assumedForWebsite
                                                   — the intake readiness contract)
    GET  /v1/practices/{pid}/stats                 honest office counts (runs, essays,
                                                   inquiries, site) — never an estimate
    POST /v1/practices/{pid}/intake                upsert the practice survey; the
                                                   response reports readiness (fail at
                                                   intake, never mid-run)
    POST /v1/practices/{pid}/runs                  queue a capability run (idempotencyKey
                                                   honored; rapid identical re-clicks replay)
    GET  /v1/practices/{pid}/runs                  inbox feed (newest first; queued runs carry
                                                   queuePosition + an honest queueNote; working
                                                   runs carry currentStep + an honest ETA)
    GET  /v1/practices/{pid}/runs/{rid}            one run, full package
    POST /v1/practices/{pid}/runs/{rid}/approve    the clinician's okay (publishes; idempotent
                                                   on a double-click — usage counts once)
    POST /v1/practices/{pid}/runs/{rid}/reject     park it
    POST /v1/practices/{pid}/runs/{rid}/revise     request changes — a new run (v2) carrying
                                                   the original output + the clinician's note;
                                                   empty note on an honesty stop auto-fills
                                                   "rewrite without this claim"
    GET  /v1/practices/{pid}/inquiries             site contact-form messages (newest first)
    POST /v1/practices/{pid}/inquiries/{iid}/read  mark one read (clears the badge)
    POST /v1/practices/{pid}/site/unpublish        the off switch — live site down
    POST /v1/internal/release-queued               drain queued_next_cycle runs with capacity
                                                   (Cloud Scheduler's hook; secret-walled)
    POST /v1/sites/{slug}/inquiry                  PUBLIC: a published site's contact form
                                                   delivers here (honeypot + rate-limited;
                                                   the only no-secret write, CORS-open
                                                   because the sites live on another origin)

SILENT CAP (Matthew, 2026-06-11): each tier has a monthly task budget
(config.TIER_TASK_CAPS, counted at APPROVAL). At the cap, new runs queue
with status 'queued_next_cycle' — never an error, never a number on screen.
The queue DRAINS whenever capacity frees (SH-F14): the hourly in-process
pump, the internal release endpoint (Cloud Scheduler), and the apps' own
inbox poll all promote queued runs while monthly budget remains — early-
month approvals can no longer starve the backlog for a whole cycle.

NO PHI by construction. Site inquiries are pre-clinical contact messages
(name/email/short note, the form forbids clinical detail) — stored for the
practice to read and reply, surfaced in the staff inbox, NEVER logged as
content. Logs: ids + categories + counts only.
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import re
import time
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import bg
from . import capabilities as caps
from . import authoring, config, publisher, runner
from .store import new_id, store

log = logging.getLogger("shaula.app")

app = FastAPI(title="shaula-svc", version="1.0.0", docs_url=None, redoc_url=None)

# Local publish backend (dev/demo): the svc itself serves the published tree
# at /sites/ so the WHOLE loop — build → preview → approve → live URL —
# runs in a browser with zero cloud. The gcs backend never mounts this.
if config.PUBLISH_BACKEND == "local":
    from fastapi.staticfiles import StaticFiles  # noqa: PLC0415

    _published = config.SITES_DIR.parent / "published"
    _published.mkdir(parents=True, exist_ok=True)
    app.mount("/sites", StaticFiles(directory=str(_published), html=True), name="sites")

# Run execution lives on the svc's DEDICATED background loop (svc/bg.py) —
# requests never share fate with task latency, and no serving-loop lifecycle
# (test harness, reload, drain) can strand a queued run.
def _spawn(coro) -> None:
    bg.submit(coro)


# ── Auth (service-to-service) ────────────────────────────────────────────────

# The ONE public write path: a published site's contact form delivering an
# inquiry. Sites live on another origin (storage.googleapis.com / the local
# /sites/ mount), so the route is CORS-open; abuse is bounded by the honeypot,
# field clamps, and the per-slug rate limit in the handler.
_INQUIRY_PATH_RE = re.compile(r"^/v1/sites/[a-z0-9-]{1,64}/inquiry$")

_INQUIRY_CORS_HEADERS = {
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "POST, OPTIONS",
    "access-control-allow-headers": "content-type",
    "access-control-max-age": "86400",
}


@app.middleware("http")
async def internal_secret(request: Request, call_next):
    # /healthz = liveness; /sites/ = PUBLISHED marketing sites (public by
    # definition — zero PHI by construction; only mounted in local mode);
    # the site-inquiry endpoint = the public contact-form sink (see above).
    if request.url.path == "/healthz" or request.url.path.startswith("/sites/"):
        return await call_next(request)
    if _INQUIRY_PATH_RE.match(request.url.path):
        response = await call_next(request)
        response.headers.update(_INQUIRY_CORS_HEADERS)
        return response
    if config.INTERNAL_SECRET:
        supplied = request.headers.get("x-internal-secret", "")
        # Constant-time compare — no timing side-channel on the shared secret.
        if not hmac.compare_digest(supplied, config.INTERNAL_SECRET):
            from fastapi.responses import JSONResponse  # noqa: PLC0415

            # Method + path only — NEVER the supplied secret (no creds in logs).
            log.warning("auth_failed method=%s path=%s", request.method, request.url.path)
            return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)


@app.on_event("startup")
async def _assert_prod_auth() -> None:
    """Prod posture (gcs state backend) MUST carry an internal secret — without it
    every endpoint is unauthenticated. Fail fast instead of silently serving
    all-public (makes the auth middleware's promise real, not aspirational)."""
    if config.STATE_BACKEND == "gcs" and not config.INTERNAL_SECRET:
        log.error("startup_refused: gcs backend without SHAULA_INTERNAL_SECRET")
        raise RuntimeError(
            "gcs posture requires SHAULA_INTERNAL_SECRET (all endpoints would be public)"
        )


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "service": "shaula-svc"}


# ── Roster / capabilities ────────────────────────────────────────────────────

@app.get("/v1/roster")
async def roster() -> dict:
    return {"staff": caps.staff_menu()}


# ── Practice profile (the intake survey — business facts only) ──────────────

SURVEY_FIELDS_MAX = 40
SURVEY_VALUE_MAX = 2000


class IntakeBody(BaseModel):
    survey: dict[str, Any] = Field(..., description="business facts only — never clinical")


def _clean_survey(raw: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for i, (k, v) in enumerate(raw.items()):
        if i >= SURVEY_FIELDS_MAX:
            break
        key = str(k)[:64]
        out[key] = str(v)[:SURVEY_VALUE_MAX]
    return out


def _readiness(profile: dict | None) -> dict:
    """The intake contract (SH-F9/SH-F4): which REQUIRED engine fields are
    still missing for a website build (after honest derivation), and which
    facts Shaula would assume if it built right now. Single source of truth:
    engine/build_practice (the same module that enforces it at build time)."""
    from engine import build_practice as BP  # noqa: PLC0415 — engine import after sys.path

    readiness = BP.survey_readiness(profile or {})
    return {
        "missingForWebsite": readiness["missing"],
        "assumedForWebsite": readiness["assumed"],
    }


@app.get("/v1/practices/{pid}")
async def practice(pid: str) -> dict:
    state = store.get(pid)
    month = time.strftime("%Y-%m")
    return {
        "practiceId": pid,
        "hasProfile": bool(state.get("profile")),
        "slug": state.get("slug", ""),
        "siteUrl": state.get("siteUrl", ""),
        "monthUsage": int(state.get("usage", {}).get(month, 0)),
        "newInquiries": sum(
            1 for i in state.get("inquiries", []) if not i.get("read")
        ),
        # Profile readiness rides the practice view so the apps can drive a
        # complete-your-profile checklist BEFORE offering the build (SH-F9).
        **_readiness(state.get("profile")),
    }


@app.post("/v1/practices/{pid}/intake")
async def intake(pid: str, body: IntakeBody) -> dict:
    survey = _clean_survey(body.survey)

    def fn(state: dict) -> None:
        state["profile"] = survey

    store.mutate(pid, fn)
    log.info("intake_saved practice=%s fields=%d", pid, len(survey))
    # Fail fast AT INTAKE (SH-F9): the response says exactly which fields a
    # website build still needs and which facts would be assumed — the
    # make-or-break first run can never die on a surprise mid-run error.
    return {"ok": True, **_readiness(survey)}


# ── Runs ─────────────────────────────────────────────────────────────────────

class RunBody(BaseModel):
    capability: str
    topic: str = ""
    # The caller's tier word (the app knows the subscription) — silent cap input.
    tier: str = "solo"
    # Optional client idempotency key (SH-F19): the same key always returns
    # the same run — a double-tap can never queue two Gemini chains.
    idempotencyKey: str = ""


class ReviseBody(BaseModel):
    # The clinician's coaching note. Empty is allowed ONLY when the run
    # failed the honesty gate — the note then auto-fills from the Reviewer's
    # record ("rewrite without this claim", SH-F12).
    note: str = ""
    tier: str = ""


def _month_usage(state: dict) -> int:
    return int(state.get("usage", {}).get(time.strftime("%Y-%m"), 0))


# Without a client key, a rapid identical re-click (same capability + topic,
# still in flight or just finished) replays the original run instead of
# queueing a duplicate chain that would later double-count the cap.
DOUBLE_CLICK_WINDOW_S = 10
_REPLAYABLE = ("queued", "queued_next_cycle", "working", "needs_approval")


def _replay_run(state: dict, body: RunBody) -> dict | None:
    key = (body.idempotencyKey or "").strip()[:80]
    if key:
        return next(
            (r for r in state.get("runs", []) if r.get("idempotencyKey") == key),
            None,
        )
    runs = state.get("runs", [])
    newest = runs[0] if runs else None
    if (
        newest
        and newest["capability"] == body.capability
        and newest.get("topic", "") == body.topic[:200]
        and int(time.time()) - int(newest.get("createdAt", 0)) <= DOUBLE_CLICK_WINDOW_S
        and newest["status"] in _REPLAYABLE
    ):
        return newest
    return None


@app.post("/v1/practices/{pid}/runs")
async def create_run(pid: str, body: RunBody) -> dict:
    cap = caps.capability(body.capability)
    if cap is None:
        raise HTTPException(status_code=400, detail="unknown_capability")

    state = store.get(pid)
    if body.capability == "website-launch":
        if not state.get("profile"):
            raise HTTPException(status_code=409, detail="intake_first")
        # Fail fast, fail SPECIFIC (SH-F9): an incomplete profile refuses the
        # run with the exact missing-field list instead of letting the build
        # die mid-run with a cryptic 'ValueError' category.
        missing = _readiness(state.get("profile"))["missingForWebsite"]
        if missing:
            raise HTTPException(
                status_code=409,
                detail={"error": "intake_incomplete", "missingForWebsite": missing},
            )

    replay = _replay_run(state, body)
    if replay is not None:
        log.info("run_replayed practice=%s run=%s", pid, replay["id"])
        out = {"ok": True, "runId": replay["id"], "status": replay["status"], "idempotent": True}
        if replay["status"] == "queued_next_cycle":
            out["queueNote"] = runner.QUEUE_NOTE
        return out

    try:
        steps = caps.plan_for(body.capability, body.topic, state)
    except caps.TemplateVariableError as exc:
        # Template debris ({seed} in a title) must never reach the inbox or
        # the model (SH-F11) — refuse loudly, with the broken template named.
        log.warning("template_invalid capability=%s", body.capability)
        raise HTTPException(status_code=400, detail="template_invalid") from exc

    # SILENT cap: past the monthly budget the run queues for next cycle —
    # never an error, never a number (queue-not-block, the category lesson).
    over_cap = _month_usage(state) >= config.cap_for(body.tier)
    run = {
        "id": new_id("run"),
        "capability": body.capability,
        "label": cap["label"],
        "topic": body.topic[:200],
        # The tier rides the run so the queue drain knows this practice's
        # budget without re-asking the app (SH-F14).
        "tier": (body.tier or "solo").lower(),
        "status": "queued_next_cycle" if over_cap else "queued",
        "createdAt": int(time.time()),
        "steps": steps,
    }
    key = (body.idempotencyKey or "").strip()[:80]
    if key:
        run["idempotencyKey"] = key

    def fn(s: dict) -> None:
        s["runs"].insert(0, run)
        s["runs"][:] = s["runs"][:100]  # keep the inbox bounded

    store.mutate(pid, fn)
    if not over_cap:
        _spawn(runner.execute_run(pid, run["id"]))
    log.info(
        "run_created practice=%s capability=%s queued_next=%s",
        pid, body.capability, over_cap,
    )
    out = {"ok": True, "runId": run["id"], "status": run["status"]}
    if over_cap:
        out["queueNote"] = runner.QUEUE_NOTE
    return out


# Honest ETA bands (SH-F19) — static and truthful, refined live from THIS
# run's own completed-step durations once it has any.
ETA_NOTE_SITE = "Site builds usually finish in under a minute."
ETA_NOTE_TEXT = "Most runs finish in about 2-4 minutes."


def _progress_fields(run: dict) -> dict:
    """currentStep narration + honest ETA + queue note for the inbox views."""
    out: dict = {}
    status = run["status"]
    if status == "queued_next_cycle":
        out["queueNote"] = runner.QUEUE_NOTE
        return out
    if status in ("queued", "working"):
        out["etaNote"] = (
            ETA_NOTE_SITE if run["capability"] == "website-launch" else ETA_NOTE_TEXT
        )
    if status == "working":
        current = next(
            (s for s in run["steps"] if s["status"] == "working"), None
        ) or next((s for s in run["steps"] if s["status"] == "pending"), None)
        if current:
            out["currentStep"] = {
                "index": current["index"],
                "title": current["title"],
                "assignee": current["assignee"],
                **({"startedAt": current["startedAt"]} if current.get("startedAt") else {}),
            }
        durations = [
            s["finishedAt"] - s["startedAt"]
            for s in run["steps"]
            if s["status"] == "done" and s.get("finishedAt") and s.get("startedAt")
        ]
        remaining = sum(
            1 for s in run["steps"] if s["status"] in ("pending", "working")
        )
        if durations and remaining:
            out["etaSeconds"] = max(1, round(sum(durations) / len(durations))) * remaining
    return out


def _queue_positions(runs: list[dict]) -> dict[str, int]:
    """1-based position per queued_next_cycle run, oldest first — the honest
    'where am I in line' the inbox renders (SH-F14)."""
    queued = sorted(
        (r for r in runs if r["status"] == "queued_next_cycle"),
        key=lambda r: int(r.get("createdAt", 0)),
    )
    return {r["id"]: i for i, r in enumerate(queued, start=1)}


def _run_view(run: dict, full: bool, queue_position: int | None = None) -> dict:
    view = {k: v for k, v in run.items() if k != "steps"}
    view.update(_progress_fields(run))
    if queue_position:
        view["queuePosition"] = queue_position
    if full:
        view["steps"] = run["steps"]
    else:
        view["stepsDone"] = sum(1 for s in run["steps"] if s["status"] == "done")
        view["stepsTotal"] = len(run["steps"])
    return view


@app.get("/v1/practices/{pid}/runs")
async def list_runs(pid: str) -> dict:
    state = store.get(pid)
    # The apps' own poll is a wake source (SH-F14): if capacity has freed
    # (month turned, cap raised) the backlog drains the moment the therapist
    # looks at the inbox — no warm instance required for the hourly pump.
    if any(r["status"] == "queued_next_cycle" for r in state.get("runs", [])):
        if _drain_practice(pid, state):
            state = store.get(pid)
    runs = state.get("runs", [])
    positions = _queue_positions(runs)
    return {
        "runs": [_run_view(r, full=False, queue_position=positions.get(r["id"])) for r in runs],
        "needsApproval": sum(1 for r in runs if r["status"] == "needs_approval"),
        # Unread site inquiries ride the same poll the apps already make,
        # so a new lead can badge the staff inbox with zero extra requests.
        "newInquiries": sum(
            1 for i in state.get("inquiries", []) if not i.get("read")
        ),
    }


@app.get("/v1/practices/{pid}/runs/{rid}")
async def get_run(pid: str, rid: str) -> dict:
    state = store.get(pid)
    run = next((r for r in state.get("runs", []) if r["id"] == rid), None)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown_run")
    positions = _queue_positions(state.get("runs", []))
    return _run_view(run, full=True, queue_position=positions.get(rid))


@app.post("/v1/practices/{pid}/runs/{rid}/approve")
async def approve(pid: str, rid: str) -> dict:
    result = await runner.approve_run(pid, rid)
    if not result.get("ok"):
        if result.get("error") == "publish_failed":
            # Honest degrade (SH-F2): nothing went live, the approval was not
            # counted, the run is still approvable — retry or revise. 503 =
            # "the service failed you, try again", never a crash page.
            raise HTTPException(status_code=503, detail="publish_failed_retryable")
        raise HTTPException(status_code=409, detail=result.get("error", "conflict"))
    return result


@app.post("/v1/practices/{pid}/runs/{rid}/reject")
async def reject(pid: str, rid: str) -> dict:
    result = runner.reject_run(pid, rid)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "conflict"))
    return result


@app.post("/v1/practices/{pid}/runs/{rid}/revise")
async def revise(pid: str, rid: str, body: ReviseBody) -> dict:
    """Request changes — staff you can coach, not just fire (SH-F3)."""
    result = runner.revise_run(pid, rid, note=body.note, tier=body.tier)
    if not result.get("ok"):
        err = result.get("error", "conflict")
        status = {"unknown_run": 404, "note_required": 400}.get(err, 409)
        raise HTTPException(status_code=status, detail=err)
    return result


# ── Therapist self-serve authoring (P2) — behind config.AUTHORING_ENABLED ───
# A therapist describes a job in plain words; Shaula drafts a vetted, honesty-
# gated workflow (+ optional skill) for review (draft), then runs the approved
# template through the SAME runner as every built-in capability (create). The
# model AND the client are untrusted: draft_preview / prepare_run re-validate
# every byte (assignee allow-list + PHI gate + honesty lint + acyclic) before it
# becomes a task. Default OFF — no live behaviour changes until the flag flips.

class WorkflowDraftBody(BaseModel):
    description: str = Field(..., max_length=2000)
    withSkill: bool = False
    # Optional client idempotency key (mirrors WorkflowCreateBody): the same key
    # replays the cached preview — a double-tap or retry can never spend a second
    # (up to 3-call) Vertex draft chain.
    idempotencyKey: str = ""


class WorkflowCreateBody(BaseModel):
    template: dict[str, Any]
    # The caller's tier word (mirrors RunBody) — drives the silent monthly cap.
    tier: str = "solo"
    # Optional client idempotency key (mirrors RunBody): the same key always
    # replays the same authored run — a double-tap or retry can never queue a
    # second billable Vertex chain.
    idempotencyKey: str = ""


# A draft preview costs up to 3 Vertex calls but persists no run to dedup against,
# so the draft endpoint coalesces repeats onto a small per-practice cache and brakes
# the burst rate — the create-side guards (monthly cap + run replay) have no purchase
# on a preview. Both bound Vertex spend from a buggy/looping caller.
DRAFTS_CACHE_MAX = 20  # bounded, like the runs / inquiries inboxes


# Per-practice sliding-hour window for draft requests. Per-instance and in-memory:
# a Vertex-spend brake, not a security boundary (callers are secret-authenticated);
# mirrors the inquiry limiter below. The replay coalesce runs FIRST, so a retry
# storm is absorbed before it reaches this — only genuine new drafts count.
_draft_hits: dict[str, list[float]] = {}


def _draft_rate_ok(pid: str) -> bool:
    now = time.time()
    hits = [t for t in _draft_hits.get(pid, []) if now - t < 3600.0]
    if len(hits) >= config.DRAFT_MAX_PER_HOUR:
        _draft_hits[pid] = hits
        return False
    hits.append(now)
    _draft_hits[pid] = hits
    return True


@app.post("/v1/practices/{pid}/workflows/draft")
async def workflows_draft(pid: str, body: WorkflowDraftBody) -> dict:
    if not config.AUTHORING_ENABLED:
        raise HTTPException(status_code=404, detail="authoring_disabled")
    state = store.get(pid)
    # Idempotency / double-click coalesce (mirrors workflows_create): a repeated
    # idempotencyKey — or a rapid re-submit of the same description — replays the
    # cached preview instead of spending a second (up to 3-call) Vertex chain.
    fingerprint = authoring.draft_fingerprint(body.description, body.withSkill)
    cached = authoring.find_draft_replay(
        state.get("drafts", []), body.idempotencyKey, fingerprint
    )
    if cached is not None:
        log.info("workflow_draft_replayed practice=%s", pid)
        return {"ok": True, "idempotent": True, **cached}
    # Per-practice hourly brake on NEW drafts (the replay above already absorbed the
    # retry-storm case). Bounds burst Vertex spend from a buggy/looping caller.
    if not _draft_rate_ok(pid):
        raise HTTPException(status_code=429, detail="slow_down")
    project = (state.get("profile") or {}).get("business_name", "the practice")
    try:
        preview = await asyncio.to_thread(
            authoring.draft_preview, body.description, project, with_skill=body.withSkill
        )
    except authoring.AuthoringError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "could_not_author", "violations": exc.violations},
        )
    # Cache the preview so an idempotent retry / double-click replays it (bounded,
    # newest-first; keyed by the explicit key when given, else the input fingerprint).
    key = (body.idempotencyKey or "").strip()[:80]
    entry: dict[str, Any] = {
        "fingerprint": fingerprint,
        "createdAt": int(time.time()),
        "preview": preview,
    }
    if key:
        entry["idempotencyKey"] = key

    def fn(s: dict) -> None:
        s.setdefault("drafts", []).insert(0, entry)
        s["drafts"][:] = s["drafts"][:DRAFTS_CACHE_MAX]

    store.mutate(pid, fn)
    log.info("workflow_drafted practice=%s steps=%d", pid, len(preview["steps"]))
    return {"ok": True, **preview}


@app.post("/v1/practices/{pid}/workflows/create")
async def workflows_create(pid: str, body: WorkflowCreateBody) -> dict:
    """Run a therapist-approved authored workflow. The template is re-validated
    here (the safety wall) before any task is created — the client cannot smuggle
    a non-vetted assignee or a banned claim past build_plan."""
    if not config.AUTHORING_ENABLED:
        raise HTTPException(status_code=404, detail="authoring_disabled")
    state = store.get(pid)
    # Idempotency (mirrors create_run): a repeated idempotencyKey — or a rapid
    # re-submit of the same template — replays the original run instead of
    # spawning a second billable Vertex chain (SH double-click / retry storm).
    fingerprint = authoring.template_fingerprint(body.template)
    replay = authoring.find_replay(state.get("runs", []), body.idempotencyKey, fingerprint)
    if replay is not None:
        log.info("authored_run_replayed practice=%s run=%s", pid, replay["id"])
        return {"ok": True, "runId": replay["id"], "status": replay["status"], "idempotent": True}
    try:
        prepared = authoring.prepare_run(body.template)
    except authoring.AuthoringError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_workflow", "violations": exc.violations},
        )
    tier = (body.tier or "solo").lower()
    # Silent monthly cap (mirrors create_run): past budget the run queues for next
    # cycle instead of spawning — never an error, bounds per-tenant Vertex spend.
    over_cap = authoring.authored_over_cap(state, tier)
    key = (body.idempotencyKey or "").strip()[:80]
    run = {
        "id": new_id("run"),
        "capability": "authored",
        "label": prepared["name"],
        "topic": "",
        "tier": tier,
        "status": "queued_next_cycle" if over_cap else "queued",
        "createdAt": int(time.time()),
        "steps": prepared["steps"],
        "templateFingerprint": fingerprint,
        "authored": True,
    }
    if key:
        run["idempotencyKey"] = key

    def fn(s: dict) -> None:
        s["runs"].insert(0, run)
        s["runs"][:] = s["runs"][:100]

    store.mutate(pid, fn)
    if not over_cap:
        _spawn(runner.execute_run(pid, run["id"]))
    log.info(
        "authored_run_created practice=%s steps=%d queued_next=%s",
        pid, len(run["steps"]), over_cap,
    )
    out = {"ok": True, "runId": run["id"], "status": run["status"]}
    if over_cap:
        out["queueNote"] = runner.QUEUE_NOTE
    return out


# ── Office stats — the Analyst's REAL surface (UX audit SH-F20) ─────────────
# The roster's Analyst promises "what actually happened"; this endpoint is
# that promise kept with data that genuinely exists today: run outcomes, the
# published-essay registry, the inquiry inbox, and the live-site flag. Counts
# only — never an estimate, never a fabricated metric. (Search/traffic data
# arrives only if a real signal source is ever attached; until then the
# Analyst stays honestly silent about it.)

@app.get("/v1/practices/{pid}/stats")
async def practice_stats(pid: str) -> dict:
    state = store.get(pid)
    month = time.strftime("%Y-%m")
    runs = state.get("runs", [])
    by_status: dict[str, int] = {}
    for r in runs:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    posts = state.get("posts", [])
    inquiries = state.get("inquiries", [])
    month_start = time.mktime(time.strptime(month, "%Y-%m"))
    return {
        "practiceId": pid,
        "month": month,
        "monthUsage": int(state.get("usage", {}).get(month, 0)),
        "runs": {
            "total": len(runs),
            "byStatus": by_status,
            "approvedThisMonth": sum(
                1 for r in runs
                if r.get("approvedAt") and r["approvedAt"] >= month_start
            ),
        },
        "postsPublished": len(posts),
        "latestPost": (
            {"title": posts[0].get("title", ""), "date": posts[0].get("date", "")}
            if posts else None
        ),
        "inquiries": {
            "total": len(inquiries),
            "new": sum(1 for i in inquiries if not i.get("read")),
        },
        "siteLive": bool(state.get("siteUrl")),
    }


# ── Site inquiries — the contact-form delivery rail ─────────────────────────
# A published site's consult form POSTs here (the form is wired at build time
# via config.INQUIRY_ORIGIN). The message lands in the practice's state and
# surfaces in the staff inbox — a visitor's inquiry can never silently
# evaporate in the browser. Inquiries are pre-clinical contact messages (the
# form forbids clinical detail); their content is stored, NEVER logged.

INQUIRIES_MAX = 200  # bounded, like the runs inbox


class InquiryBody(BaseModel):
    # Generous schema caps reject junk early; the handler then clips to the
    # honest field sizes (same clip-don't-reject idiom as _clean_survey).
    name: str = Field("", max_length=2000)
    email: str = Field("", max_length=2000)
    phone: str = Field("", max_length=2000)
    state: str = Field("", max_length=2000)
    notes: str = Field("", max_length=4000)
    website: str = Field("", max_length=2000)  # honeypot — humans leave this empty


def _clip(value: str, limit: int) -> str:
    return str(value or "").strip()[:limit]


# Per-slug sliding-hour window. Per-instance and in-memory: a spam brake for
# a low-volume public form, not a security boundary (the payload is bounded
# plain text and the honeypot eats the dumb bots).
_inquiry_hits: dict[str, list[float]] = {}


def _inquiry_rate_ok(slug: str) -> bool:
    now = time.time()
    hits = [t for t in _inquiry_hits.get(slug, []) if now - t < 3600.0]
    if len(hits) >= config.INQUIRY_MAX_PER_HOUR:
        _inquiry_hits[slug] = hits
        return False
    hits.append(now)
    _inquiry_hits[slug] = hits
    return True


@app.options("/v1/sites/{slug}/inquiry")
async def inquiry_preflight(slug: str) -> Response:
    # CORS preflight for the cross-origin form POST; headers come from the
    # middleware (the inquiry path is the one CORS-open route).
    return Response(status_code=204)


@app.post("/v1/sites/{slug}/inquiry")
async def site_inquiry(slug: str, body: InquiryBody) -> dict:
    if (body.website or "").strip():
        # Honeypot tripped — swallow silently (don't teach the bot).
        log.info("inquiry_honeypot slug=%s", slug)
        return {"ok": True}
    name = _clip(body.name, 120)
    email = _clip(body.email, 200)
    if not name or "@" not in email:
        raise HTTPException(status_code=400, detail="name_and_email_required")
    pid = store.practice_for_slug(slug)
    if not pid:
        raise HTTPException(status_code=404, detail="unknown_site")
    if not _inquiry_rate_ok(slug):
        raise HTTPException(status_code=429, detail="slow_down")

    inquiry = {
        "id": new_id("inq"),
        "name": name,
        "email": email,
        "phone": _clip(body.phone, 40),
        "state": _clip(body.state, 80),
        "notes": _clip(body.notes, 500),
        "createdAt": int(time.time()),
        "read": False,
    }

    def fn(s: dict) -> None:
        s.setdefault("inquiries", []).insert(0, inquiry)
        s["inquiries"][:] = s["inquiries"][:INQUIRIES_MAX]

    store.mutate(pid, fn)
    log.info("inquiry_received practice=%s slug=%s", pid, slug)  # ids only — never content
    return {"ok": True}


@app.get("/v1/practices/{pid}/inquiries")
async def list_inquiries(pid: str) -> dict:
    state = store.get(pid)
    inquiries = state.get("inquiries", [])
    return {
        "inquiries": inquiries,
        "new": sum(1 for i in inquiries if not i.get("read")),
    }


@app.post("/v1/practices/{pid}/inquiries/{iid}/read")
async def mark_inquiry_read(pid: str, iid: str) -> dict:
    def fn(s: dict) -> None:
        for i in s.get("inquiries", []):
            if i["id"] == iid:
                i["read"] = True

    state = store.mutate(pid, fn)
    if not any(i["id"] == iid for i in state.get("inquiries", [])):
        raise HTTPException(status_code=404, detail="unknown_inquiry")
    return {"ok": True}


# ── Site off switch ──────────────────────────────────────────────────────────

@app.post("/v1/practices/{pid}/site/unpublish")
async def unpublish_site(pid: str) -> dict:
    """Take the live site down (the trust off-switch). The preview and the
    built artifact stay; approving a later website-launch re-publishes."""
    state = store.get(pid)
    if not state.get("slug") or not state.get("siteUrl"):
        raise HTTPException(status_code=409, detail="no_live_site")
    removed = await asyncio.to_thread(publisher.unpublish_site, state["slug"])

    def fn(s: dict) -> None:
        s["siteUrl"] = ""

    store.mutate(pid, fn)
    log.info("site_unpublished practice=%s files=%d", pid, removed)
    return {"ok": True, "filesRemoved": removed}


# ── Queue drain: queued_next_cycle runs start whenever capacity frees ──────
# Three wake sources (SH-F14): the hourly in-process pump (warm instances),
# the internal release endpoint (Cloud Scheduler — survives scale-to-zero),
# and the apps' inbox poll (drains the moment the therapist looks).

@app.on_event("startup")
async def start_cycle_pump() -> None:
    async def pump() -> None:
        while True:
            await asyncio.sleep(3600)
            try:
                _release_queued()
            except Exception:  # noqa: BLE001
                log.warning("cycle_pump_failed")

    _spawn(pump())


def _drain_practice(pid: str, state: dict | None = None) -> int:
    """Promote this practice's queued_next_cycle runs, oldest first, while
    monthly budget remains. The old rule ('skip unless usage == 0') starved
    the whole backlog for a month if the clinician approved ANYTHING before
    the pump ran — capacity, not zero-usage, is the honest test. Promotion
    never exceeds remaining budget (usage still counts at approval; this
    bounds how much parks at needs_approval per pass)."""
    state = state or store.get(pid)
    queued = sorted(
        (r for r in state.get("runs", []) if r["status"] == "queued_next_cycle"),
        key=lambda r: int(r.get("createdAt", 0)),
    )
    if not queued:
        return 0
    usage = _month_usage(state)
    promoted = 0
    for run in queued:
        cap = config.cap_for(run.get("tier") or "solo")
        if usage + promoted >= cap:
            continue  # no capacity for this run's tier (yet)

        def fn(s: dict, _rid=run["id"]) -> None:
            r = next((x for x in s["runs"] if x["id"] == _rid), None)
            if r and r["status"] == "queued_next_cycle":
                r["status"] = "queued"

        store.mutate(pid, fn)
        _spawn(runner.execute_run(pid, run["id"]))
        promoted += 1
    if promoted:
        log.info("queue_drained practice=%s promoted=%d", pid, promoted)
    return promoted


def _release_queued() -> int:
    """Drain every practice with queued runs and free capacity. Returns the
    number of runs promoted (the internal endpoint reports it)."""
    # Local backend: scan the state dir; GCS backend: scan the state prefix.
    ids: list[str] = []
    if config.STATE_BACKEND == "local":
        ids = [p.stem for p in config.LOCAL_STATE_DIR.glob("*.json")]
    else:
        from google.cloud import storage  # noqa: PLC0415

        client = storage.Client(project=config.GCP_PROJECT)
        for blob in client.list_blobs(config.STATE_BUCKET, prefix="state/"):
            name = blob.name.rsplit("/", 1)[-1]
            if name.endswith(".json"):
                ids.append(name[: -len(".json")])
    promoted = 0
    for pid in ids:
        if pid.startswith("_"):
            continue  # reserved docs (the slug index), never a practice
        promoted += _drain_practice(pid)
    return promoted


@app.post("/v1/internal/release-queued")
async def release_queued_endpoint() -> dict:
    """The scale-to-zero-proof wake hook: Cloud Scheduler POSTs here (with
    the internal secret) so the queue drains near month-turn even when no
    instance stayed warm for the in-process pump."""
    promoted = await asyncio.to_thread(_release_queued)
    return {"ok": True, "promoted": promoted}
