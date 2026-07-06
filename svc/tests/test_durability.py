"""ux/shaula-durability — the six durability + coaching contracts
(UX audit SH-F2/F3/F12/F14/F15/F19).

F2  the Approve click survives instance death: the built tree is a cache,
    the practice STATE DOC (profile + slug + posts registry) is the durable
    truth, publish rebuilds from it; a publish failure degrades honestly
    (503, run stays approvable, regenerate offered) — never a crash, and
    published essay cards survive site republishes.
F3  staff can be COACHED: request-changes creates a v2 run carrying the
    original draft + the clinician's note as context, with lineage visible
    in the inbox (v1 'revised' → v2), silent-cap-respecting.
F12 honesty stops are narrated, not dumped: plain words + the offending
    sentence quoted on the run record, step outputs stay banned-text-free,
    and an empty revise note auto-fills "rewrite without this claim".
    The engine lint itself stays the untouched hard stop.
F14 queued runs can't starve: capacity (not zero-usage) drains the queue,
    the inbox shows queue position + an honest note, and the apps' poll +
    an internal endpoint wake the queue without a warm instance.
F15 human-gate steps are never executed by the AI: the run parks at the
    gate and the step completes only through the clinician's approve.
F19 progress is narrated (currentStep, honest ETA, step timestamps) and
    double-clicks are guarded on create + approve (cap counted once).

All data here is synthetic fixture data (northstar-denver) — no PHI.
"""
from __future__ import annotations

import pathlib
import shutil
import time

from .conftest import SURVEY
from .test_svc import _wait_status


def _local_publish(monkeypatch, tmp_origin="http://svc.local.test"):
    """Flip the publisher to the zero-cloud local backend (the demo rail):
    preview/live trees become REAL directories under sites/../published —
    exactly what restart-survival proofs need."""
    import svc.config as config  # noqa: PLC0415

    monkeypatch.setattr(config, "PUBLISH_BACKEND", "local")
    monkeypatch.setattr(config, "PUBLIC_ORIGIN", tmp_origin)


def _launch_to_needs_approval(c, pid, capability="website-launch", topic=""):
    rid = c.post(
        f"/v1/practices/{pid}/runs",
        json={"capability": capability, "topic": topic},
    ).json()["runId"]
    _wait_status(c, pid, rid, {"needs_approval"})
    return rid


def _intake(c, pid):
    assert c.post(f"/v1/practices/{pid}/intake", json={"survey": SURVEY}).status_code == 200


# ══ SH-F2: the Approve click survives instance death ═════════════════════════

def test_approve_survives_artifact_loss_by_rebuilding(client, monkeypatch, svc_env):
    """Cloud Run scenario: build happens, instance dies (ephemeral disk gone),
    approve lands on a fresh instance. The durable state doc must be enough."""
    c, _ = client
    _local_publish(monkeypatch)
    pid = "PRACTICE-DUR-REBUILD"
    _intake(c, pid)
    rid = _launch_to_needs_approval(c, pid)
    slug = c.get(f"/v1/practices/{pid}").json()["slug"]

    # The restart: the built tree is GONE.
    shutil.rmtree(svc_env["sites_dir"] / slug)
    assert not (svc_env["sites_dir"] / slug).exists()

    r = c.post(f"/v1/practices/{pid}/runs/{rid}/approve")
    assert r.status_code == 200
    live = svc_env["sites_dir"].parent / "published" / slug / "index.html"
    assert live.is_file()  # the site actually went live, rebuilt from state
    assert c.get(f"/v1/practices/{pid}").json()["siteUrl"] == r.json()["publishedUrl"]


def test_approve_publish_failure_degrades_honestly(client, monkeypatch):
    """A publish-leg failure must never 500, never silently fail, never lose
    the approval intent: 503 + retryable, run stays needs_approval with an
    honest approveError carrying the regenerate hint — and a retry succeeds."""
    c, _ = client
    import svc.publisher as publisher  # noqa: PLC0415
    import svc.runner as runner_mod  # noqa: PLC0415

    pid = "PRACTICE-DUR-DEGRADE"
    _intake(c, pid)
    rid = _launch_to_needs_approval(c, pid)

    def boom(slug, posts=None):
        raise publisher.PublishError("artifact_missing: no profile to rebuild from")

    monkeypatch.setattr(publisher, "publish_site", boom)
    r = c.post(f"/v1/practices/{pid}/runs/{rid}/approve")
    assert r.status_code == 503
    assert r.json()["detail"] == "publish_failed_retryable"

    run = c.get(f"/v1/practices/{pid}/runs/{rid}").json()
    assert run["status"] == "needs_approval"  # the approval intent stands
    err = run["approveError"]
    assert err["category"] == "artifact_missing"
    assert err["canRevise"] is True  # the regenerate affordance (SH-F3)
    assert "approval was not counted" in err["message"]
    assert c.get(f"/v1/practices/{pid}").json()["monthUsage"] == 0  # honest: no count

    # The degrade is retryable: with the publisher healthy again, the SAME
    # approve succeeds and the error record clears.
    monkeypatch.setattr(publisher, "publish_site", lambda slug, posts=None: "https://example.test/site")
    r = c.post(f"/v1/practices/{pid}/runs/{rid}/approve")
    assert r.status_code == 200 and r.json()["publishedUrl"]
    run = c.get(f"/v1/practices/{pid}/runs/{rid}").json()
    assert run["status"] == "published" and "approveError" not in run
    assert runner_mod  # imported for clarity of what's under test


def test_published_posts_survive_restart_and_republish(client, monkeypatch, svc_env):
    """The durable posts registry (state doc) is the source of the site's
    essay cards: an instance restart before a blog approve, and a later full
    site republish, must both keep the published essay live + linked."""
    c, _ = client
    _local_publish(monkeypatch)
    pid = "PRACTICE-DUR-POSTS"
    _intake(c, pid)

    # Site live first (publish_post only fires onto a live site).
    rid_site = _launch_to_needs_approval(c, pid)
    assert c.post(f"/v1/practices/{pid}/runs/{rid_site}/approve").status_code == 200
    slug = c.get(f"/v1/practices/{pid}").json()["slug"]

    # Blog run reaches the inbox; the instance "restarts" before the okay.
    rid_post = _launch_to_needs_approval(c, pid, "weekly-blog", "honest rest")
    shutil.rmtree(svc_env["sites_dir"] / slug)

    r = c.post(f"/v1/practices/{pid}/runs/{rid_post}/approve")
    assert r.status_code == 200 and "/writing/" in r.json()["publishedUrl"]

    live = svc_env["sites_dir"].parent / "published" / slug
    page = next((live / "writing").glob("*.html"))
    app_js = (live / "app.js").read_text(encoding="utf-8")
    assert f"writing/{page.name}" in app_js  # card links the real page

    # Now the practice relaunches its site (new run, fresh floor build).
    # The registry must re-render the card — never a bare floor again.
    rid_site2 = _launch_to_needs_approval(c, pid)
    assert c.post(f"/v1/practices/{pid}/runs/{rid_site2}/approve").status_code == 200
    app_js = (live / "app.js").read_text(encoding="utf-8")
    assert f"writing/{page.name}" in app_js  # the card survived the republish
    assert page.is_file()  # the essay page survived too (merge semantics)


# ══ SH-F3: the revision loop — staff you can coach ═══════════════════════════

def test_revise_creates_v2_with_lineage_and_context(client):
    c, calls = client
    pid = "PRACTICE-REV"
    _intake(c, pid)
    rid = _launch_to_needs_approval(c, pid, "weekly-blog", "sleep routines")

    note = "Soften the headline and mention evening walks."
    r = c.post(f"/v1/practices/{pid}/runs/{rid}/revise", json={"note": note})
    assert r.status_code == 200
    body = r.json()
    rid2 = body["runId"]
    assert rid2 != rid and body["revision"] == 2

    # Lineage on both sides, visible in the inbox views.
    v2 = _wait_status(c, pid, rid2, {"needs_approval"})
    assert v2["revisionOf"] == rid and v2["revision"] == 2 and v2["revisionNote"] == note
    v1 = c.get(f"/v1/practices/{pid}/runs/{rid}").json()
    assert v1["status"] == "revised" and v1["supersededBy"] == rid2
    feed = c.get(f"/v1/practices/{pid}/runs").json()
    assert feed["needsApproval"] == 1  # v1 stopped asking; v2 is the live ask

    # The staff actually SAW the coaching: the original draft + the note
    # both ride the executor's handoff context (the existing seam).
    v2_prompts = [call["user"] for call in calls["gemini"]]
    assert any(note in p for p in v2_prompts)
    assert any("Previous draft (v1)" in p for p in v2_prompts)
    # And the v1 output text itself is in the context (the fake brain's text).
    assert any("warm, honest deliverable" in p and note in p for p in v2_prompts)


def test_revise_respects_the_silent_cap(client):
    c, _ = client
    import svc.store as store_mod  # noqa: PLC0415

    pid = "PRACTICE-REV-CAP"
    _intake(c, pid)
    rid = _launch_to_needs_approval(c, pid, "weekly-blog", "boundaries")

    month = time.strftime("%Y-%m")
    store_mod.store.mutate(pid, lambda s: s["usage"].__setitem__(month, 999))

    r = c.post(
        f"/v1/practices/{pid}/runs/{rid}/revise",
        json={"note": "Make it shorter.", "tier": "free"},
    )
    # Queue, NEVER an error — the silent-cap contract holds for revisions too.
    assert r.status_code == 200
    assert r.json()["status"] == "queued_next_cycle"
    assert r.json()["queueNote"]


def test_revise_guards(client):
    c, _ = client
    pid = "PRACTICE-REV-GUARD"
    _intake(c, pid)

    # Unknown run → 404.
    assert c.post(f"/v1/practices/{pid}/runs/nope/revise", json={"note": "x"}).status_code == 404

    # Approved (terminal-happy) runs are not revisable → 409; new work is a new run.
    rid = _launch_to_needs_approval(c, pid, "weekly-blog", "rest")
    assert c.post(f"/v1/practices/{pid}/runs/{rid}/approve").status_code == 200
    assert c.post(f"/v1/practices/{pid}/runs/{rid}/revise", json={"note": "x"}).status_code == 409

    # Empty note without an honesty record to auto-fill from → 400.
    rid2 = _launch_to_needs_approval(c, pid, "weekly-blog", "walks")
    assert c.post(f"/v1/practices/{pid}/runs/{rid2}/revise", json={"note": "  "}).status_code == 400


# ══ SH-F12: the Reviewer speaks plainly (lint stays the hard stop) ═══════════

def test_honesty_stop_is_narrated_not_regex(client, monkeypatch):
    """The production path: the model drafts a banned claim, the REAL lint
    gate (gemini.lint_gate — not a mimic) refuses it, and the run narrates
    the refusal instead of dumping a category string."""
    c, _ = client
    import svc.gemini as gemini  # noqa: PLC0415

    def dishonest(system, user, **kw):
        return gemini.lint_gate("We offer a proven method. Honest support, every week.")

    monkeypatch.setattr(gemini, "generate_text", dishonest)
    pid = "PRACTICE-HONEST-NARRATE"
    _intake(c, pid)
    rid = c.post(
        f"/v1/practices/{pid}/runs",
        json={"capability": "weekly-blog", "topic": "our method"},
    ).json()["runId"]
    run = _wait_status(c, pid, rid, {"failed"})

    assert run["failureCategory"] == "honesty"
    record = run["honesty"]
    assert record["canRevise"] is True
    reasons = record["reasons"]
    assert reasons, "the run record must say WHICH claim tripped"
    assert any("efficacy claim" in r["plain"] for r in reasons)
    # The offending sentence is QUOTED on the record (state, never logs) …
    assert any("We offer a proven method." == r["quote"] for r in reasons)
    # … while step outputs stay banned-text-free (the wave-1 pinned contract)
    # and free of raw regex fragments.
    assert all("proven" not in s["output"] for s in run["steps"])
    assert all("\\b" not in s["output"] for s in run["steps"])
    # The failed step narrates in the Reviewer's voice, with a path forward.
    failed_steps = [s for s in run["steps"] if s["status"] == "failed"]
    assert failed_steps and "Request changes" in failed_steps[-1]["output"]
    assert "honesty gate working, not a crash" in failed_steps[-1]["output"]


def test_reviewer_package_gate_narrates_too(client, monkeypatch):
    """Defense in depth: if banned text ever reaches the reviewer step (a
    misbehaving integration that skipped the per-step gate), the package
    lint still hard-stops — and narrates the same way, never raw regex."""
    c, _ = client
    import svc.gemini as gemini  # noqa: PLC0415

    # Deliberately NO lint_gate — simulating output that dodged the step net.
    monkeypatch.setattr(
        gemini, "generate_text",
        lambda system, user, **kw: "Our results are guaranteed. A warm note.",
    )
    pid = "PRACTICE-HONEST-PACKAGE"
    _intake(c, pid)
    rid = c.post(
        f"/v1/practices/{pid}/runs",
        json={"capability": "weekly-blog", "topic": "results"},
    ).json()["runId"]
    run = _wait_status(c, pid, rid, {"failed"})

    assert run["failureCategory"] == "honesty"
    assert any("guarantee" in r["plain"] for r in run["honesty"]["reasons"])
    assert any("Our results are guaranteed." == r["quote"] for r in run["honesty"]["reasons"])
    review = next(s for s in run["steps"] if s["isReview"])
    assert review["status"] == "failed"
    # The reviewer's own output: plain words, no regex, no banned echo.
    assert "\\b" not in review["output"] and "guarantee" not in review["output"]
    assert "Request changes" in review["output"]


def test_one_click_revise_after_honesty_stop(client, monkeypatch):
    """The 'rewrite without this claim' button: revise with NO note on an
    honesty-failed run auto-fills the note from the Reviewer's record."""
    c, _ = client
    import svc.gemini as gemini  # noqa: PLC0415

    drafts = iter([
        "Our care is guaranteed to work for everyone.",  # v1: tripped
    ])
    prompts: list[str] = []

    def first_dishonest(system, user, **kw):
        prompts.append(user)
        try:
            text = next(drafts)
        except StopIteration:
            text = "A warm, honest deliverable about the requested topic."
        return gemini.lint_gate(text)  # the REAL gate, not a mimic

    monkeypatch.setattr(gemini, "generate_text", first_dishonest)
    pid = "PRACTICE-HONEST-ONECLICK"
    _intake(c, pid)
    rid = c.post(
        f"/v1/practices/{pid}/runs",
        json={"capability": "copy-engine", "topic": "homepage"},
    ).json()["runId"]
    _wait_status(c, pid, rid, {"failed"})

    r = c.post(f"/v1/practices/{pid}/runs/{rid}/revise", json={"note": ""})
    assert r.status_code == 200
    rid2 = r.json()["runId"]
    v2 = _wait_status(c, pid, rid2, {"needs_approval"})
    # The auto-note quotes the refused sentence and forbids repeating it.
    assert "guaranteed to work" in v2["revisionNote"]
    assert "Do not repeat" in v2["revisionNote"]
    # And the staff received it as context.
    assert any("guaranteed to work" in p for p in prompts)
    assert any("revision note" in p for p in prompts)


def test_honesty_explain_unit():
    from svc import honesty  # noqa: PLC0415

    text = "We have a proven method. Sessions guarantee progress.\n\nPlain honest line."
    violations = [r"\bproven\b", r"\bguarantee"]
    reasons = honesty.explain(text, violations)
    assert reasons[0]["quote"] == "We have a proven method."
    assert "efficacy claim" in reasons[0]["plain"]
    assert reasons[1]["quote"] == "Sessions guarantee progress."
    assert "guaranteed" not in honesty.refusal_message(2)
    # The step-safe summary must never echo banned vocabulary.
    import generate as engine_generate  # noqa: PLC0415 — conftest put repo on sys.path

    assert engine_generate.lint(honesty.refusal_message(1)) == []
    assert engine_generate.lint(honesty.refusal_message(3)) == []
    # The auto-note exists and carries the quotes for the staff to avoid.
    note = honesty.revise_note(reasons)
    assert '"We have a proven method."' in note and "Do not repeat" in note


# ══ SH-F14: the queue is honest and actually drains ══════════════════════════

def _queue_two_runs(c, pid):
    import svc.store as store_mod  # noqa: PLC0415

    _intake(c, pid)
    month = time.strftime("%Y-%m")
    store_mod.store.mutate(pid, lambda s: s["usage"].__setitem__(month, 999))
    rids = []
    for topic in ("first queued", "second queued"):
        r = c.post(
            f"/v1/practices/{pid}/runs",
            json={"capability": "weekly-blog", "topic": topic, "tier": "free"},
        )
        assert r.json()["status"] == "queued_next_cycle"
        assert r.json()["queueNote"]  # the create response already narrates
        rids.append(r.json()["runId"])
        time.sleep(1.1)  # distinct createdAt so order (and dedupe) is determinate
    return rids, month, store_mod


def test_queued_runs_show_position_and_note(client):
    c, _ = client
    pid = "PRACTICE-QPOS"
    (rid1, rid2), _month, _sm = _queue_two_runs(c, pid)

    feed = {r["id"]: r for r in c.get(f"/v1/practices/{pid}/runs").json()["runs"]}
    assert feed[rid1]["queuePosition"] == 1  # oldest first — honest FIFO
    assert feed[rid2]["queuePosition"] == 2
    assert "capacity frees" in feed[rid1]["queueNote"]
    one = c.get(f"/v1/practices/{pid}/runs/{rid1}").json()
    assert one["queuePosition"] == 1 and one["queueNote"]


def test_queue_drains_on_capacity_not_zero_usage(client):
    """THE starvation fix: usage > 0 (the clinician approved something early
    in the month) must no longer freeze the backlog — capacity is the test."""
    c, _ = client
    import svc.app as app_mod  # noqa: PLC0415

    pid = "PRACTICE-QSTARVE"
    (rid1, rid2), month, store_mod = _queue_two_runs(c, pid)

    # Month turned; one task already approved (usage=1 — the OLD code's
    # poison pill) but tier 'free' (cap 4) has plenty of capacity left.
    store_mod.store.mutate(pid, lambda s: s["usage"].__setitem__(month, 1))
    promoted = app_mod._drain_practice(pid)
    assert promoted == 2  # both fit inside the remaining budget
    _wait_status(c, pid, rid1, {"needs_approval"})
    _wait_status(c, pid, rid2, {"needs_approval"})  # drain before teardown


def test_queue_drain_respects_remaining_budget(client):
    c, _ = client
    import svc.app as app_mod  # noqa: PLC0415

    pid = "PRACTICE-QBUDGET"
    (rid1, rid2), month, store_mod = _queue_two_runs(c, pid)

    # free cap = 4, usage = 3 → exactly ONE slot frees: oldest goes, second waits.
    store_mod.store.mutate(pid, lambda s: s["usage"].__setitem__(month, 3))
    assert app_mod._drain_practice(pid) == 1
    _wait_status(c, pid, rid1, {"needs_approval"})
    second = c.get(f"/v1/practices/{pid}/runs/{rid2}").json()
    assert second["status"] == "queued_next_cycle"
    assert second["queuePosition"] == 1  # it moved up the line
    # Park the leftover for good so later full-scan drains can't adopt it
    # mid-teardown (test hygiene, not product behavior).
    store_mod.store.mutate(pid, lambda s: s["usage"].__setitem__(month, 999))


def test_inbox_poll_wakes_the_queue(client):
    """Scale-to-zero Cloud Run: no warm pump — the therapist opening their
    inbox must still drain the queue when capacity has freed."""
    c, _ = client
    pid = "PRACTICE-QPOLL"
    (rid1, rid2), month, store_mod = _queue_two_runs(c, pid)
    store_mod.store.mutate(pid, lambda s: s["usage"].__setitem__(month, 0))

    c.get(f"/v1/practices/{pid}/runs")  # the poll IS the wake
    _wait_status(c, pid, rid1, {"needs_approval"})
    _wait_status(c, pid, rid2, {"needs_approval"})  # drain before teardown


def test_internal_release_endpoint_drains_and_is_walled(client):
    c, _ = client
    pid = "PRACTICE-QENDPOINT"
    (rid1, rid2), month, store_mod = _queue_two_runs(c, pid)
    store_mod.store.mutate(pid, lambda s: s["usage"].__setitem__(month, 0))

    # The public internet cannot pull the drain.
    bare = c.__class__(c.app)
    assert bare.post("/v1/internal/release-queued").status_code == 401

    r = c.post("/v1/internal/release-queued")
    assert r.status_code == 200 and r.json()["promoted"] >= 2
    _wait_status(c, pid, rid1, {"needs_approval"})
    _wait_status(c, pid, rid2, {"needs_approval"})  # drain before teardown


# ══ SH-F15: human gates belong to humans ═════════════════════════════════════

def test_gate_detection_is_manifest_truth():
    import svc.capabilities as caps  # noqa: PLC0415

    state = {"profile": {"business_name": "North Star"}, "siteUrl": ""}
    gated = {
        "copy-engine", "deck-engine", "proposal-engine",
        "newsletter-engine", "ad-creative-engine", "distribution-engine",
        # office-expansion capabilities — every one ends at a triage human gate
        "faq-engine", "reputation-engine", "content-calendar-engine",
        "local-seo-engine", "onboarding-email-engine", "social-clip-engine",
        "practice-forms-engine",
    }
    ungated = {"weekly-blog", "growth-engine", "website-launch"}
    for cap_id in gated:
        steps = caps.plan_for(cap_id, "t", state)
        gates = [s for s in steps if s["isGate"]]
        assert len(gates) == 1, cap_id
        assert gates[0] is steps[-1], f"{cap_id}: the gate is the final step"
        assert not gates[0]["isReview"]
    for cap_id in ungated:
        assert not any(s.get("isGate") for s in caps.plan_for(cap_id, "t", state)), cap_id


def test_human_gate_is_never_executed_by_the_ai(client):
    c, calls = client
    pid = "PRACTICE-GATE"
    _intake(c, pid)
    rid = c.post(
        f"/v1/practices/{pid}/runs",
        json={"capability": "proposal-engine", "topic": "Group practice referral"},
    ).json()["runId"]
    run = _wait_status(c, pid, rid, {"needs_approval"})

    gate = run["steps"][-1]
    assert gate["isGate"] and gate["status"] == "waiting"
    assert "Waiting for you" in gate["output"]
    assert "belongs to a human" in gate["output"]
    # ZERO model calls carried the gate instruction (no wasted spend, no
    # fabricated 'done' on a human act).
    assert all(gate["instruction"][:40] not in call["user"] for call in calls["gemini"])
    # The reviewer still ran (the gate parks AFTER the honesty review).
    review = next(s for s in run["steps"] if s["isReview"])
    assert review["status"] == "done"


def test_gate_completes_only_through_the_clinician(client):
    c, _ = client
    pid = "PRACTICE-GATE-OK"
    _intake(c, pid)
    rid = _launch_to_needs_approval(c, pid, "newsletter-engine", "June edition")

    assert c.post(f"/v1/practices/{pid}/runs/{rid}/approve").status_code == 200
    run = c.get(f"/v1/practices/{pid}/runs/{rid}").json()
    gate = run["steps"][-1]
    assert gate["status"] == "done"
    assert gate["output"].startswith("Approved by the clinician")
    assert gate.get("finishedAt")

    # And the rejected path tells the truth too.
    rid2 = _launch_to_needs_approval(c, pid, "newsletter-engine", "July edition")
    assert c.post(f"/v1/practices/{pid}/runs/{rid2}/reject").status_code == 200
    gate2 = c.get(f"/v1/practices/{pid}/runs/{rid2}").json()["steps"][-1]
    assert gate2["status"] == "skipped"
    assert "rejected by the clinician" in gate2["output"]


# ══ SH-F19: progress model + double-click guards ═════════════════════════════

def test_summary_view_narrates_current_step_and_eta():
    import svc.app as app_mod  # noqa: PLC0415

    run = {
        "id": "run-x", "capability": "weekly-blog", "label": "Weekly Blog",
        "topic": "t", "status": "working", "createdAt": 100,
        "steps": [
            {"index": 0, "assignee": "blog", "title": "Blog brief", "isReview": False,
             "status": "done", "output": "x", "startedAt": 100, "finishedAt": 130},
            {"index": 1, "assignee": "marketer", "title": "3 social teasers",
             "isReview": False, "status": "working", "output": "", "startedAt": 131},
            {"index": 2, "assignee": "reviewer", "title": "Honesty review",
             "isReview": True, "status": "pending", "output": ""},
        ],
    }
    view = app_mod._run_view(run, full=False)
    assert view["currentStep"]["title"] == "3 social teasers"
    assert view["currentStep"]["assignee"] == "marketer"
    assert view["currentStep"]["startedAt"] == 131
    assert view["etaNote"]  # an honest band, always present while running
    assert view["etaSeconds"] == 60  # one 30s sample × 2 remaining steps
    assert view["stepsDone"] == 1 and view["stepsTotal"] == 3

    queued = dict(run, status="queued_next_cycle")
    qview = app_mod._run_view(queued, full=False, queue_position=3)
    assert qview["queuePosition"] == 3 and "capacity frees" in qview["queueNote"]


def test_completed_steps_carry_timestamps(client):
    c, _ = client
    pid = "PRACTICE-TIMES"
    _intake(c, pid)
    rid = _launch_to_needs_approval(c, pid, "weekly-blog", "morning light")
    run = c.get(f"/v1/practices/{pid}/runs/{rid}").json()
    done = [s for s in run["steps"] if s["status"] == "done"]
    assert done
    assert all(s.get("startedAt") and s.get("finishedAt") for s in done)


def test_create_run_idempotency_key_replays(client):
    c, _ = client
    pid = "PRACTICE-IDEM"
    _intake(c, pid)
    body = {"capability": "weekly-blog", "topic": "sleep", "idempotencyKey": "tap-123"}
    first = c.post(f"/v1/practices/{pid}/runs", json=body).json()
    second = c.post(f"/v1/practices/{pid}/runs", json=body).json()
    assert second["runId"] == first["runId"]
    assert second["idempotent"] is True
    runs = c.get(f"/v1/practices/{pid}/runs").json()["runs"]
    assert len(runs) == 1  # one chain, one approval card — never two
    _wait_status(c, pid, first["runId"], {"needs_approval"})  # drain before teardown


def test_double_click_without_key_replays(client):
    c, _ = client
    pid = "PRACTICE-DCLICK"
    _intake(c, pid)
    body = {"capability": "weekly-blog", "topic": "boundaries at work"}
    first = c.post(f"/v1/practices/{pid}/runs", json=body).json()
    second = c.post(f"/v1/practices/{pid}/runs", json=body).json()  # the double-tap
    assert second["runId"] == first["runId"] and second["idempotent"] is True
    assert len(c.get(f"/v1/practices/{pid}/runs").json()["runs"]) == 1
    _wait_status(c, pid, first["runId"], {"needs_approval"})  # drain before teardown


def test_double_click_approve_counts_usage_once(client):
    c, _ = client
    pid = "PRACTICE-DAPPROVE"
    _intake(c, pid)
    rid = _launch_to_needs_approval(c, pid, "weekly-blog", "rest")

    first = c.post(f"/v1/practices/{pid}/runs/{rid}/approve")
    second = c.post(f"/v1/practices/{pid}/runs/{rid}/approve")
    assert first.status_code == 200
    assert second.status_code == 200  # idempotent truth, not an error page
    assert second.json()["alreadyDone"] is True
    assert c.get(f"/v1/practices/{pid}").json()["monthUsage"] == 1  # ONE task burned


def test_distinct_topics_are_not_deduped(client):
    """The guard must never eat a genuine second request."""
    c, _ = client
    pid = "PRACTICE-DISTINCT"
    _intake(c, pid)
    a = c.post(f"/v1/practices/{pid}/runs", json={"capability": "weekly-blog", "topic": "sleep"}).json()
    b = c.post(f"/v1/practices/{pid}/runs", json={"capability": "weekly-blog", "topic": "grief"}).json()
    assert a["runId"] != b["runId"]
    assert len(c.get(f"/v1/practices/{pid}/runs").json()["runs"]) == 2
    for rid in (a["runId"], b["runId"]):  # drain before teardown
        _wait_status(c, pid, rid, {"needs_approval"})
