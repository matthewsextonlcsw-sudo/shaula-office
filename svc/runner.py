"""runner — executes capability runs (D-FreeStaff).

One generic executor for every text capability + a deterministic plan for
website-launch:

  * text capabilities (weekly-blog, newsletter-engine, copy-engine, …):
    each step = one Gemini call (step instruction + every prior step's
    output as context), honesty-linted by gemini.generate_text. The
    reviewer step is the GATE: it lints the whole package and parks the
    run at needs_approval — the clinician's okay is a separate, human act.
  * website-launch: deterministic engine build (engine.pipeline.build_site,
    optionally brain-enriched later) → preview published to the sites
    bucket → needs_approval with the preview URL. Approval triggers the
    real publish (publisher.py) — the office performs the build/publish,
    never a "worker", exactly the office design.

Failure discipline: a step failure parks the run as 'failed' with a
CATEGORY (vertex_http, honesty, build_failed) — content is never logged.
A crisis path cannot exist here: nothing clinical reaches this service.
"""
from __future__ import annotations

import asyncio
import logging
import re
import sys
import time
from typing import Any

from . import bg, capabilities, config, gemini, honesty, publisher, receipts
from .store import new_id, store

log = logging.getLogger("shaula.runner")

if str(config.REPO) not in sys.path:
    sys.path.insert(0, str(config.REPO))

# The honest queued-run note (SH-F14) — shown wherever a queued_next_cycle
# run surfaces. Never a number, never an error: the silent-cap contract.
QUEUE_NOTE = (
    "Queued — this run starts automatically when your monthly capacity "
    "frees up. Nothing for you to do."
)

# What a waiting human-gate step says in the inbox (SH-F15).
GATE_WAITING_OUTPUT = (
    "Waiting for you — this step belongs to a human, not the staff. "
    "Nothing is sent, signed, or published until you approve this run."
)

# What an honestly-silent step says in the inbox (SH-F10): templates instruct
# staff like the Analyst to "reply exactly [SILENT]" when there is no real
# signal. The sentinel is a wire protocol, never a thing a therapist reads —
# and never, ever, an essay body.
SILENT_STEP_OUTPUT = (
    "Nothing to report yet — this teammate only speaks when there is a real "
    "result to show."
)
_SILENT_RE = re.compile(r"^\[?\s*silent\s*\]?\.?$", re.I)

# The note that rides a website-launch approval card alongside the facts the
# engine had to assume (SH-F4): inventions are flagged for confirmation, never
# published silently.
ASSUMED_NOTE = (
    "Shaula assumed these while building — confirm or edit them before you "
    "approve. Approving publishes them as your practice's stated policies; "
    "use Request changes (or update your intake answers) to correct any."
)


SYSTEM_PROMPT = (
    "You are {assignee}, one member of Shaula — the AI office staff of a "
    "therapy practice. Practice facts:\n{profile}\n\n"
    "HOUSE RULES (non-negotiable):\n"
    "- HONEST ONLY: no fabricated statistics, no outcome or efficacy claims, "
    "no 'studies show', no testimonials, no guarantees, no 'proven'.\n"
    "- No clinical advice, no diagnosis language aimed at a reader.\n"
    "- Never make a client's condition the punchline; aim irony at the "
    "system, warmth at the clinician and client.\n"
    "- Plain, warm, specific prose. No hype.\n"
    "Return ONLY the deliverable text for your step — no preamble."
)


def _profile_brief(profile: dict | None) -> str:
    if not profile:
        return "(no practice profile on file yet)"
    keys = [
        "business_name", "owner_name", "credential", "specialties",
        "modalities", "location", "fee", "tone",
    ]
    lines = [f"- {k}: {profile[k]}" for k in keys if profile.get(k)]
    return "\n".join(lines) or "(profile is empty)"


def _find_run(state: dict, run_id: str) -> dict | None:
    return next((r for r in state["runs"] if r["id"] == run_id), None)


def _set_run(practice_id: str, run_id: str, **fields: Any) -> dict:
    def fn(state: dict) -> None:
        run = _find_run(state, run_id)
        if run:
            run.update(fields)

    return store.mutate(practice_id, fn)


def _set_step(practice_id: str, run_id: str, index: int, **fields: Any) -> None:
    def fn(state: dict) -> None:
        run = _find_run(state, run_id)
        if run and 0 <= index < len(run["steps"]):
            run["steps"][index].update(fields)

    store.mutate(practice_id, fn)


async def execute_run(practice_id: str, run_id: str) -> None:
    """Drive one run to needs_approval (or failed). Runs on the app's event
    loop via asyncio.create_task; blocking calls go through to_thread."""
    state = store.get(practice_id)
    run = _find_run(state, run_id)
    if not run:
        log.warning("run_execute_missing practice=%s run=%s", practice_id, run_id)
        return
    if run["status"] != "queued":
        log.info("run_execute_skip practice=%s run=%s status=%s", practice_id, run_id, run["status"])
        return
    log.info("run_execute_start practice=%s run=%s cap=%s", practice_id, run_id, run["capability"])
    _set_run(practice_id, run_id, status="working", startedAt=int(time.time()))

    try:
        if run["capability"] == "website-launch":
            await _run_website_launch(practice_id, run_id)
        else:
            await _run_text_capability(practice_id, run_id)
    except Exception as exc:  # noqa: BLE001 — category only, never content
        category = str(getattr(exc, "category", exc.__class__.__name__))[:80]
        log.warning("run_failed practice=%s run=%s category=%s", practice_id, run_id, category)
        # Honesty stops get NARRATED, not dumped as a category string: which
        # claim, in plain words, with the sentence quoted — in the run RECORD
        # (state, never logs). The lint hard-stop itself is untouched (SH-F12).
        honesty_record = None
        if category == "honesty":
            reasons = list(getattr(exc, "explanations", None) or [])
            honesty_record = {
                "reasons": reasons,
                "message": honesty.refusal_message(len(reasons) or 1),
                "canRevise": True,  # the one-click path: POST runs/{rid}/revise
            }

        def fn(state: dict) -> None:
            run = _find_run(state, run_id)
            if not run:
                return
            run.update(status="failed", failureCategory=category)
            if honesty_record:
                run["honesty"] = honesty_record
            # The in-flight step must not stay "working" forever: mark it
            # failed. Output stays content-free except the honesty narration
            # summary (which is banned-vocabulary-safe by construction).
            for step in run["steps"]:
                if step["status"] == "working":
                    step.update(status="failed", finishedAt=int(time.time()))
                    if honesty_record:
                        step["output"] = honesty_record["message"]

        store.mutate(practice_id, fn)


def _revision_context(state: dict, run: dict) -> list[tuple[str, str]]:
    """The revision loop's seam (SH-F3): a revised run starts with the
    previous draft + the clinician's note as ordinary handoff context, so
    every staff step sees exactly what to keep and what to change. These
    blocks are CONTEXT only — they never join the reviewer's lint package
    (the old draft may legitimately contain the refused claim)."""
    blocks: list[tuple[str, str]] = []
    prior = _find_run(state, run.get("revisionOf") or "")
    if prior:
        # done steps only: a failed step's output is the Reviewer's refusal
        # narration, not a draft — it must never masquerade as one.
        package = "\n\n".join(
            s["output"]
            for s in prior["steps"]
            if s.get("output") and s.get("status") == "done"
            and not s.get("isReview") and not s.get("isGate")
        )
        if package:
            version = int(prior.get("revision") or 1)
            blocks.append((f"Previous draft (v{version}) — you are revising it", package))
    note = (run.get("revisionNote") or "").strip()
    if note:
        blocks.append(("The clinician's revision note — follow it precisely", note))
    return blocks


async def _run_text_capability(practice_id: str, run_id: str) -> None:
    state = store.get(practice_id)
    run = _find_run(state, run_id)
    profile = state.get("profile")
    context_blocks = _revision_context(state, run)  # [] for a v1 run
    outputs: list[tuple[str, str]] = []  # THIS run's produced steps only

    for step in run["steps"]:
        idx = step["index"]
        if step.get("isGate"):
            # A human-gate step is the clinician's, never the model's
            # (SH-F15). Park the run — the approval card IS the gate; the
            # step completes only through approve_run. Zero model calls.
            def fn(s: dict) -> None:
                r = _find_run(s, run_id)
                if not r:
                    return
                r["steps"][idx].update(status="waiting", output=GATE_WAITING_OUTPUT)
                r.update(status="needs_approval", readyAt=int(time.time()))

            store.mutate(practice_id, fn)
            log.info(
                "run_gate_parked practice=%s run=%s step=%d", practice_id, run_id, idx
            )
            return
        _set_step(practice_id, run_id, idx, status="working", startedAt=int(time.time()))
        system = SYSTEM_PROMPT.format(
            assignee=step["assignee"], profile=_profile_brief(profile)
        )
        context = "\n\n".join(
            f"--- Handoff from {t} ---\n{o}" for t, o in (context_blocks + outputs)
        )
        if step["isReview"]:
            # The reviewer gate: deterministic lint over the whole package,
            # plus a model verdict for the human-readable summary. Lint scope
            # is THIS run's outputs — never the revision context.
            package = "\n\n".join(o for _, o in outputs)
            violations = gemini.lint(package)
            if violations:
                reasons = honesty.explain(package, violations)
                message = honesty.refusal_message(len(reasons))

                def fn(s: dict) -> None:
                    r = _find_run(s, run_id)
                    if not r:
                        return
                    # The step narrates in safe plain words; the exact
                    # sentences live in the run's honesty record (SH-F12).
                    r["steps"][idx].update(
                        status="failed", output=message, finishedAt=int(time.time())
                    )
                    r.update(
                        status="failed",
                        failureCategory="honesty",
                        honesty={"reasons": reasons, "message": message, "canRevise": True},
                    )

                store.mutate(practice_id, fn)
                return
            verdict = await asyncio.to_thread(
                gemini.generate_text,
                system,
                f"{step['instruction']}\n\n{context}\n\n"
                "Reply with a 2-3 sentence reviewer verdict for the clinician.",
                temperature=0.2,
                max_output_tokens=512,
            )
            _set_step(
                practice_id, run_id, idx,
                status="done", output=verdict, finishedAt=int(time.time()),
            )
        else:
            text = await asyncio.to_thread(
                gemini.generate_text,
                system,
                f"YOUR STEP: {step['instruction']}\n\n{context}".strip(),
            )
            if _SILENT_RE.match(text.strip()):
                # The template's silence contract (SH-F10): "[SILENT]" is a
                # wire sentinel, not copy. The inbox gets the honest narration,
                # the step is flagged, and the output joins neither the
                # handoff context nor any publish candidate set.
                _set_step(
                    practice_id, run_id, idx,
                    status="done", output=SILENT_STEP_OUTPUT, silent=True,
                    finishedAt=int(time.time()),
                )
                continue
            _set_step(
                practice_id, run_id, idx,
                status="done", output=text, finishedAt=int(time.time()),
            )
            outputs.append((step["title"], text))

    _set_run(
        practice_id, run_id,
        status="needs_approval", readyAt=int(time.time()),
    )


# ── Site-build enrichment (UX audit SH-F5) ──────────────────────────────────
# The engine's brain seam (engine/brain.py) existed, was tested, and was never
# called — every practice got the identical floor prose. Wired here:
#   * _site_brain()      — a live Vertex brain when available; None otherwise
#                          (the build stays the deterministic floor, byte-for-
#                          byte — tests and the zero-cloud demo rail included).
#   * _RecordingBrain    — captures the accepted enrichments at preview-build.
#   * _ReplayBrain       — replays those exact strings at approve/rebuild, so
#                          the clinician publishes EXACTLY what they previewed
#                          (the SH-F2 byte-for-byte rebuild contract survives
#                          enrichment; the captured copy re-lints in generate).
# The captured blocks live in the practice STATE DOC (CAS store) — durable.

def _site_brain():
    if config.SITE_BRAIN == "off":
        return None
    try:
        from engine.brain import Brain  # noqa: PLC0415 — optional seam

        brain = Brain(project=config.GCP_PROJECT or None)
        return brain if brain.available() else None
    except Exception:  # noqa: BLE001 — enrichment is never load-bearing
        return None


class _RecordingBrain:
    """Wraps a live brain; remembers every accepted block enrichment."""

    def __init__(self, inner) -> None:
        self.BRAIN_BLOCKS = inner.BRAIN_BLOCKS
        self._inner = inner
        self.captured: dict[str, str] = {}

    def enrich_block(self, bid: str, practice: dict, find: str):
        out = self._inner.enrich_block(bid, practice, find)
        if out is not None:
            self.captured[bid] = out
        return out


class _ReplayBrain:
    """Replays captured enrichments — deterministic, no model, no network."""

    def __init__(self, blocks: dict[str, str]) -> None:
        self.BRAIN_BLOCKS = set(blocks)
        self._blocks = blocks

    def enrich_block(self, bid: str, practice: dict, find: str):
        return self._blocks.get(bid)


async def _run_website_launch(practice_id: str, run_id: str) -> None:
    """Deterministic build (+ optional recorded enrichment) → public preview
    → needs_approval, with the engine's assumed facts on the approval card."""
    state = store.get(practice_id)
    profile = state.get("profile")
    if not profile:
        _set_run(practice_id, run_id, status="failed", failureCategory="no_profile")
        return

    from engine import pipeline  # noqa: PLC0415 — engine import after sys.path

    live = _site_brain()
    recorder = _RecordingBrain(live) if live is not None else None

    _set_step(practice_id, run_id, 0, status="working", startedAt=int(time.time()))
    built = await asyncio.to_thread(
        pipeline.build_site, profile,
        sites_dir=config.SITES_DIR, slug=state.get("slug") or None,
        brain=recorder,
        # The contact form on the built site POSTs inquiries back to this
        # service (the staff-inbox delivery rail). Empty origin → the site
        # renders its honest direct-contact card instead of a form.
        inquiry_origin=config.INQUIRY_ORIGIN,
    )
    slug = built["slug"]
    # The facts the engine assumed (derivations + commitment defaults) — the
    # approval card renders these as "Shaula assumed these — confirm or edit"
    # (SH-F4). Pulled from the build itself so card and site cannot disagree.
    assumed = list(built.get("practice", {}).get("_assumed") or [])
    # Claim slug → practice in the index so a public site inquiry can find
    # its owner (preview pages carry the live form too — by design).
    store.claim_slug(slug, practice_id)
    # The durable posts registry renders into every build (SH-F2): a site
    # REbuild must show the essays already published, not a bare floor.
    posts = state.get("posts") or []
    if posts:
        publisher.inject_posts_file(config.SITES_DIR / slug, posts)
    _set_step(
        practice_id, run_id, 0,
        status="done", finishedAt=int(time.time()),
        output=f"Built a 9-page practice site for {built['business_name']}.",
    )

    _set_step(practice_id, run_id, 1, status="working", startedAt=int(time.time()))
    preview_url = await asyncio.to_thread(publisher.publish_preview, slug)
    _set_step(
        practice_id, run_id, 1,
        status="done", output=preview_url, finishedAt=int(time.time()),
    )

    # Build trust artifacts (svc/receipts): the honesty receipt (what Shaula
    # refused to say / held back / assumed) and the provenance receipt (every
    # rendered claim traces to approved content). Both ride the approval card.
    # ADDITIVE — the site already built; a receipt failure must never fail it, so
    # this is best-effort and degrades honestly (provenance → 'unverified'). The
    # provenance flag is an ATTESTATION on the fixed-template path, not a block.
    receipts_payload: dict = {}
    try:
        receipts_payload = await asyncio.to_thread(receipts.receipts_for_build, built)
        prov = receipts_payload.get("provenanceReceipt") or {}
        if prov.get("status") == "flag":
            log.warning(
                "provenance_flag practice=%s run=%s offenders=%d",
                practice_id, run_id, len(prov.get("offenders") or []),
            )
        elif prov.get("status") == "unverified":
            log.info("provenance_unverified practice=%s run=%s", practice_id, run_id)
    except Exception as exc:  # noqa: BLE001 — receipts are additive, never fail a built site
        log.warning(
            "receipts_failed practice=%s run=%s category=%s",
            practice_id, run_id, type(exc).__name__,
        )

    def fn(s: dict) -> None:
        s["slug"] = slug
        # Durable enrichment record (SH-F5 ∩ SH-F2): the approve/rebuild path
        # replays exactly these strings — publish always matches the preview.
        s["brainBlocks"] = dict(recorder.captured) if recorder else {}
        run = _find_run(s, run_id)
        if run:
            run.update(
                status="needs_approval",
                readyAt=int(time.time()),
                previewUrl=preview_url,
                **(
                    {"assumedFacts": assumed, "assumedNote": ASSUMED_NOTE}
                    if assumed else {}
                ),
                **receipts_payload,
            )

    store.mutate(practice_id, fn)


def _ensure_built(state: dict):
    """The durable-artifact seam (SH-F2): publishing must never depend on the
    instance that built the site still being alive. The built tree under
    SITES_DIR is an ephemeral cache; the durable truth is the practice STATE
    DOC (profile + slug + posts registry + captured brain blocks) and the
    rebuild is deterministic — a missing tree is reproduced from state,
    byte-for-byte, right here (enrichment replays from the captured record,
    never from a fresh model call — publish always equals preview, SH-F5).
    Raises PublishError('artifact_missing…') only when state itself cannot
    reproduce the site (no slug / no profile)."""
    slug = state.get("slug") or ""
    if not slug:
        raise publisher.PublishError("artifact_missing: practice has no site slug")
    site = config.SITES_DIR / slug
    if site.is_dir():
        return site
    profile = state.get("profile")
    if not profile:
        raise publisher.PublishError("artifact_missing: no profile to rebuild from")
    from engine import pipeline  # noqa: PLC0415 — engine import after sys.path

    captured = state.get("brainBlocks") or {}
    pipeline.build_site(
        profile, sites_dir=config.SITES_DIR, slug=slug,
        brain=_ReplayBrain(captured) if captured else None,
        inquiry_origin=config.INQUIRY_ORIGIN,
    )
    posts = state.get("posts") or []
    if posts:
        publisher.inject_posts_file(site, posts)
    log.info("site_rebuilt_for_publish slug=%s", slug)  # ids only, never content
    return site


APPROVE_ERROR_MESSAGE = (
    "Publishing didn't complete — nothing went live and your approval was "
    "not counted. Try Approve again; if it keeps failing, use Request "
    "changes to regenerate this run."
)

CONTENT_INVALID_MESSAGE = (
    "Nothing was published and your approval was not counted: this run's "
    "draft isn't a finished essay (it still contains placeholder content). "
    "Use Request changes and the staff will produce a real draft."
)

POSTS_MAX = 100  # bounded, like the runs inbox


async def approve_run(practice_id: str, run_id: str) -> dict:
    """The clinician's okay — the ONLY path to published. Counts usage
    exactly once (CAS-guarded), flips waiting human-gate steps, and degrades
    honestly when the publish leg fails (the run stays approvable)."""
    state = store.get(practice_id)
    run = _find_run(state, run_id)
    if not run:
        return {"ok": False, "error": "not_awaiting_approval"}
    if run["status"] in ("approved", "published"):
        # Double-click / retry replay (SH-F19): the first click won; tell
        # the truth idempotently instead of erroring at the second.
        return {
            "ok": True,
            "publishedUrl": run.get("publishedUrl", ""),
            "alreadyDone": True,
        }
    if run["status"] != "needs_approval":
        return {"ok": False, "error": "not_awaiting_approval"}

    published_url = ""
    new_posts: list[dict] | None = None
    try:
        if run["capability"] == "website-launch":
            await asyncio.to_thread(_ensure_built, state)
            published_url = await asyncio.to_thread(
                publisher.publish_site, state["slug"], state.get("posts") or []
            )
        elif run["capability"] in ("weekly-blog", "growth-engine") and state.get("slug") and state.get("siteUrl"):
            # A finished post publishes onto the live site when one exists;
            # otherwise the approved package is copy-paste (still real value).
            # Silent steps (the Analyst's "[SILENT]" contract) are inbox
            # states, never publish candidates (SH-F10).
            post_steps = [
                s for s in run["steps"]
                if not s["isReview"] and not s.get("isGate")
                and not s.get("silent") and s["output"]
            ]
            if post_steps:
                # AI-involvement disclosure (on by default; the practice's survey
                # can turn it off or supply its own text). Single source of truth:
                # the same engine helper that stamps the site footer.
                from engine import build_practice as BP  # noqa: PLC0415

                disclosure = BP.ai_disclosure(state.get("profile") or {})
                await asyncio.to_thread(_ensure_built, state)
                entry, _title, _body = publisher.post_entry(post_steps)
                # Durable registry, newest first, idempotent on retry (an
                # entry with the same slug is replaced, never duplicated).
                new_posts = [entry] + [
                    p for p in (state.get("posts") or [])
                    if p.get("slug") != entry["slug"]
                ]
                published_url = await asyncio.to_thread(
                    publisher.publish_post,
                    state["slug"], run, post_steps, disclosure, new_posts,
                )
    except Exception as exc:  # noqa: BLE001 — degrade honestly, never a 500
        detail = str(exc)
        if detail.startswith("content_invalid"):
            # The publishable-content invariant fired (SH-F10/SH-F11): the
            # draft is placeholder/sentinel/empty. Retrying the same approve
            # cannot help — Request changes regenerates the draft.
            log.warning(
                "approve_content_invalid practice=%s run=%s", practice_id, run_id,
            )
            _set_run(
                practice_id, run_id,
                approveError={
                    "category": "content_invalid",
                    "message": CONTENT_INVALID_MESSAGE,
                    "canRevise": True,
                    "at": int(time.time()),
                },
            )
            return {"ok": False, "error": "content_invalid", "retryable": False}
        category = "artifact_missing" if detail.startswith("artifact_missing") else "publish_failed"
        log.warning(
            "approve_publish_failed practice=%s run=%s category=%s",
            practice_id, run_id, category,
        )
        _set_run(
            practice_id, run_id,
            approveError={
                "category": category,
                "message": APPROVE_ERROR_MESSAGE,
                "canRevise": True,  # regenerate via POST runs/{rid}/revise
                "at": int(time.time()),
            },
        )
        return {"ok": False, "error": "publish_failed", "retryable": True}

    month = time.strftime("%Y-%m")
    applied: list[bool] = []

    def fn(s: dict) -> None:
        applied.clear()
        r = _find_run(s, run_id)
        if not r or r["status"] != "needs_approval":
            applied.append(False)  # raced — another click already landed
            return
        applied.append(True)
        now = int(time.time())
        r.pop("approveError", None)
        # The human gate completes through the human act — and says so.
        for step in r["steps"]:
            if step.get("isGate") and step["status"] == "waiting":
                step.update(
                    status="done", finishedAt=now,
                    output=f"Approved by the clinician — {time.strftime('%Y-%m-%d')}.",
                )
        r.update(status="published" if published_url else "approved",
                 approvedAt=now,
                 **({"publishedUrl": published_url} if published_url else {}))
        if published_url and run["capability"] == "website-launch":
            s["siteUrl"] = published_url
        if new_posts is not None:
            s["posts"] = new_posts[:POSTS_MAX]
        # Usage counts INSIDE the CAS mutate, guarded by the status check —
        # a double-click can never burn two monthly tasks (SH-F19).
        s["usage"][month] = int(s["usage"].get(month, 0)) + 1

    store.mutate(practice_id, fn)
    if applied and not applied[-1]:
        current = _find_run(store.get(practice_id), run_id) or {}
        return {
            "ok": True,
            "publishedUrl": current.get("publishedUrl", ""),
            "alreadyDone": True,
        }
    return {"ok": True, "publishedUrl": published_url}


def reject_run(practice_id: str, run_id: str) -> dict:
    state = store.get(practice_id)
    run = _find_run(state, run_id)
    if not run or run["status"] != "needs_approval":
        return {"ok": False, "error": "not_awaiting_approval"}

    def fn(s: dict) -> None:
        r = _find_run(s, run_id)
        if not r or r["status"] != "needs_approval":
            return
        now = int(time.time())
        for step in r["steps"]:
            if step.get("isGate") and step["status"] == "waiting":
                step.update(
                    status="skipped", finishedAt=now,
                    output="Not approved — the run was rejected by the clinician.",
                )
        r.update(status="rejected", rejectedAt=now)

    store.mutate(practice_id, fn)
    return {"ok": True}


def revise_run(practice_id: str, run_id: str, note: str = "", tier: str = "") -> dict:
    """Request changes (SH-F3) — the third verb between approve and reject.

    Creates a NEW run (v2, v3, …) of the same capability that carries the
    original output + the clinician's note as revision context; the original
    parks as 'revised' with the lineage recorded on both sides. An empty note
    on an honesty-stopped run auto-fills from the Reviewer's record — the
    one-click "rewrite without this claim" path (SH-F12). Respects the silent
    cap exactly like run creation.
    """
    state = store.get(practice_id)
    orig = _find_run(state, run_id)
    if not orig:
        return {"ok": False, "error": "unknown_run"}
    if orig["status"] not in ("needs_approval", "failed", "rejected"):
        return {"ok": False, "error": "not_revisable"}

    note = (note or "").strip()[:1000]
    if not note:
        note = honesty.revise_note((orig.get("honesty") or {}).get("reasons") or [])
    if not note:
        return {"ok": False, "error": "note_required"}

    cap = capabilities.capability(orig["capability"])
    if cap is None:
        return {"ok": False, "error": "unknown_capability"}
    try:
        steps = capabilities.plan_for(orig["capability"], orig.get("topic", ""), state)
    except capabilities.TemplateVariableError:
        # Template debris can never reach the inbox or the model (SH-F11).
        return {"ok": False, "error": "template_invalid"}

    tier = (tier or orig.get("tier") or "solo").lower()
    month = time.strftime("%Y-%m")
    over_cap = int(state.get("usage", {}).get(month, 0)) >= config.cap_for(tier)
    new_run = {
        "id": new_id("run"),
        "capability": orig["capability"],
        "label": orig.get("label") or cap["label"],
        "topic": orig.get("topic", ""),
        "tier": tier,
        "status": "queued_next_cycle" if over_cap else "queued",
        "createdAt": int(time.time()),
        "steps": steps,
        "revisionOf": run_id,
        "revision": int(orig.get("revision") or 1) + 1,
        "revisionNote": note,
    }

    def fn(s: dict) -> None:
        o = _find_run(s, run_id)
        if o:
            o["supersededBy"] = new_run["id"]
            if o["status"] == "needs_approval":
                # v1 stops asking for approval — v2 is the live ask. Lineage
                # stays visible in the inbox (v1 'revised' → v2).
                o["status"] = "revised"
                o["revisedAt"] = int(time.time())
        s["runs"].insert(0, new_run)
        s["runs"][:] = s["runs"][:100]  # keep the inbox bounded

    store.mutate(practice_id, fn)
    if not over_cap:
        bg.submit(execute_run(practice_id, new_run["id"]))
    log.info(
        "run_revised practice=%s run=%s revision_of=%s v=%d queued_next=%s",
        practice_id, new_run["id"], run_id, new_run["revision"], over_cap,
    )
    result = {
        "ok": True,
        "runId": new_run["id"],
        "revision": new_run["revision"],
        "status": new_run["status"],
    }
    if over_cap:
        result["queueNote"] = QUEUE_NOTE
    return result
