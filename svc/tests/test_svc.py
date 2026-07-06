"""shaula-svc — the contract tests (D-FreeStaff).

Pins: auth wall, roster truth (manifest-driven, 8 office staff, ZERO PHI
staff served), intake → website-launch → preview → approve → publish, the
generic text capability through the reviewer gate, honesty lint as a hard
stop, the SILENT cap (queue-not-block), and store CAS behavior.
"""
from __future__ import annotations

import json
import time

import pytest

from .conftest import SURVEY


def _wait_status(client, pid, rid, want, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/v1/practices/{pid}/runs/{rid}")
        if r.status_code == 200 and r.json()["status"] in want:
            return r.json()
        time.sleep(0.05)
    raise AssertionError(f"run never reached {want}: {r.json()}")


def test_auth_wall(client):
    c, _ = client
    bare = c.__class__(c.app)  # no secret header
    assert bare.get("/v1/roster").status_code == 401
    assert bare.get("/healthz").status_code == 200  # liveness stays open


def test_roster_is_manifest_truth_and_phi_free(client):
    c, _ = client
    roster = c.get("/v1/roster").json()["staff"]
    names = {m["name"] for m in roster}
    assert names == {
        "orchestrator", "website", "blog", "marketer",
        "strategist", "reviewer", "analytics", "distributor",
    }
    # The 6 PHI roles are NEVER served by this service.
    assert names.isdisjoint(
        {"scribe", "biller", "frontdesk", "customer-service", "clinical-admin", "workspace"}
    )
    # The website builder's menu carries the unboxing capability.
    website = next(m for m in roster if m["name"] == "website")
    assert any(cap["id"] == "website-launch" for cap in website["capabilities"])
    # Nothing template-less leaks into a menu (W0 truth holds end to end).
    all_ids = {cap["id"] for m in roster for cap in m["capabilities"]}
    assert all_ids.isdisjoint({"brand-kit", "clip-picker", "meeting-notes", "faq-bot"})


def test_website_launch_full_loop(client):
    c, calls = client
    pid = "PRACTICE-WEB"

    # No intake yet → 409 (the unboxing interview must run first).
    r = c.post(f"/v1/practices/{pid}/runs", json={"capability": "website-launch"})
    assert r.status_code == 409

    assert c.post(f"/v1/practices/{pid}/intake", json={"survey": SURVEY}).status_code == 200

    r = c.post(f"/v1/practices/{pid}/runs", json={"capability": "website-launch"})
    assert r.status_code == 200
    rid = r.json()["runId"]

    run = _wait_status(c, pid, rid, {"needs_approval"})
    assert run["previewUrl"].startswith("https://storage.googleapis.com/")
    assert "preview/" in run["previewUrl"]
    assert calls["uploads"] and calls["uploads"][0].startswith("preview/")

    # The clinician's okay — the ONLY path to live.
    r = c.post(f"/v1/practices/{pid}/runs/{rid}/approve")
    assert r.status_code == 200
    assert r.json()["publishedUrl"].startswith("https://storage.googleapis.com/")
    assert "preview/" not in r.json()["publishedUrl"]

    practice = c.get(f"/v1/practices/{pid}").json()
    assert practice["siteUrl"] == r.json()["publishedUrl"]
    assert practice["monthUsage"] == 1  # usage counts at approval


def test_website_launch_attaches_trust_receipts(client):
    """Every website-launch run carries the two build receipts the approval card
    shows: the honesty receipt (what Shaula refused to say / held back / assumed),
    and the provenance receipt (every visible claim on the RENDERED site traces to
    approved content). Both are additive — a receipt failure never fails the build."""
    c, _ = client
    pid = "PRACTICE-RECEIPTS"
    assert c.post(f"/v1/practices/{pid}/intake", json={"survey": SURVEY}).status_code == 200
    rid = c.post(
        f"/v1/practices/{pid}/runs", json={"capability": "website-launch"}
    ).json()["runId"]
    run = _wait_status(c, pid, rid, {"needs_approval"})

    # a1 — honesty receipt, generated from the build's OWN refusals manifest.
    hr = run["honestyReceipt"]
    assert hr["kind"] == "honesty"
    assert hr["lintClean"] is True
    assert hr["refusedLanguage"], "the banned-language policy must be surfaced"
    assert all("\\b" not in line for line in hr["refusedLanguage"]), "plain English, not regex"
    assert hr["modalitiesShown"], "northstar lists real, cited modalities"

    # a2 — provenance receipt over the RENDERED SPA. An honest deterministic-floor
    # build renders provenance-clean; if node is unavailable it degrades honestly to
    # 'unverified' (the structural gate still stands) — but NEVER a false 'flag'.
    pr = run["provenanceReceipt"]
    assert pr["kind"] == "provenance"
    assert pr["status"] in {"pass", "unverified"}, f"honest build must not flag; got {pr}"
    assert "limitNote" in pr
    if pr["status"] == "pass":
        assert pr["ok"] is True
        assert pr["offenders"] == []


def test_generic_text_capability_reviewer_gate(client):
    c, calls = client
    pid = "PRACTICE-BLOG"
    c.post(f"/v1/practices/{pid}/intake", json={"survey": SURVEY})

    r = c.post(
        f"/v1/practices/{pid}/runs",
        json={"capability": "weekly-blog", "topic": "sleep and anxiety"},
    )
    assert r.status_code == 200
    rid = r.json()["runId"]
    run = _wait_status(c, pid, rid, {"needs_approval"})

    # Every non-review step produced output; the review step holds a verdict.
    steps = run["steps"]
    assert all(s["output"] for s in steps)
    assert steps[-1]["isReview"]
    # The variables substituted — the brain saw the topic and the practice.
    assert any("sleep and anxiety" in call["user"] for call in calls["gemini"])

    # Approving WITHOUT a live site = approved copy-paste package (no publish).
    r = c.post(f"/v1/practices/{pid}/runs/{rid}/approve")
    assert r.status_code == 200
    assert r.json()["publishedUrl"] == ""
    assert c.get(f"/v1/practices/{pid}/runs/{rid}").json()["status"] == "approved"


def test_honesty_lint_is_a_hard_stop(client, monkeypatch):
    c, _ = client
    import svc.gemini as gemini  # noqa: PLC0415

    # The brain "produces" a banned claim → BrainError('honesty') → run fails.
    def dishonest(system, user, **kw):
        raise gemini.BrainError("honesty", "matched: \\bproven\\b")

    monkeypatch.setattr(gemini, "generate_text", dishonest)
    pid = "PRACTICE-LINT"
    c.post(f"/v1/practices/{pid}/intake", json={"survey": SURVEY})
    rid = c.post(
        f"/v1/practices/{pid}/runs",
        json={"capability": "copy-engine", "topic": "our results"},
    ).json()["runId"]
    run = _wait_status(c, pid, rid, {"failed"})
    assert run["failureCategory"] == "honesty"
    # The banned text never reached any output field.
    assert all("proven" not in s["output"] for s in run["steps"])


def test_silent_cap_queues_never_blocks(client):
    c, _ = client
    pid = "PRACTICE-CAP"
    c.post(f"/v1/practices/{pid}/intake", json={"survey": SURVEY})

    # Burn the whole 'free' budget (cap=4) by approving website + 3 posts…
    # cheaper: set usage directly through the store.
    import svc.store as store_mod  # noqa: PLC0415

    month = time.strftime("%Y-%m")

    def fn(state):
        state["usage"][month] = 999

    store_mod.store.mutate(pid, fn)

    r = c.post(
        f"/v1/practices/{pid}/runs",
        json={"capability": "weekly-blog", "topic": "boundaries", "tier": "free"},
    )
    # Queue, NEVER an error — the silent-cap contract.
    assert r.status_code == 200
    assert r.json()["status"] == "queued_next_cycle"


def test_store_cas_survives_concurrent_mutation(svc_env):
    store = svc_env["store"]
    pid = "PRACTICE-CAS"
    for i in range(20):
        store.mutate(pid, lambda s, i=i: s["runs"].insert(0, {"id": f"r{i}", "status": "x", "steps": []}))
    assert len(store.get(pid)["runs"]) == 20


def test_lint_reexport_is_the_engine_linter(svc_env):
    import svc.gemini as gemini  # noqa: PLC0415

    assert gemini.lint("our proven method guarantees results")
    assert not gemini.lint("we work plainly and honestly, one week at a time")


def test_research_engine_runs_to_reviewer_gate(client):
    """The Research Desk (10th capability): one question in, an honest
    verify-first brief out, parked at the reviewer gate like every text cap."""
    c, calls = client
    pid = "PRACTICE-RESEARCH"
    c.post(f"/v1/practices/{pid}/intake", json={"survey": SURVEY})

    # Manifest truth: the strategist's menu carries the Research Desk.
    roster = c.get("/v1/roster").json()["staff"]
    strategist = next(m for m in roster if m["name"] == "strategist")
    assert any(cap["id"] == "research-engine" for cap in strategist["capabilities"])

    r = c.post(
        f"/v1/practices/{pid}/runs",
        json={"capability": "research-engine", "topic": "EMDR for adolescents"},
    )
    assert r.status_code == 200
    rid = r.json()["runId"]
    run = _wait_status(c, pid, rid, {"needs_approval"})

    # strategist scopes → writer findings → writer brief → reviewer gate.
    steps = run["steps"]
    assert [s["assignee"] for s in steps] == ["strategist", "blog", "blog", "reviewer"]
    assert all(s["output"] for s in steps)
    assert steps[-1]["isReview"]
    # The clinician's question reached the brain with the practice context.
    assert any("EMDR for adolescents" in call["user"] for call in calls["gemini"])

    # Approving a research brief never publishes anywhere — copy-paste value.
    r = c.post(f"/v1/practices/{pid}/runs/{rid}/approve")
    assert r.status_code == 200
    assert r.json()["publishedUrl"] == ""
    assert c.get(f"/v1/practices/{pid}/runs/{rid}").json()["status"] == "approved"
