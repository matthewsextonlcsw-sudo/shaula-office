"""ux/shaula-personalization — wave-3 svc contracts
(UX audit SH-F4 / SH-F5 / SH-F9 / SH-F10 / SH-F11 / SH-F13 / SH-F20).

F4  invented defaults are flagged: the website-launch approval card carries
    assumedFacts ("Shaula assumed these — confirm or edit"), never silent.
F5  the personalization seam is WIRED: a live brain enriches the build, the
    capture/replay record makes approve publish exactly what was previewed,
    and SHAULA_SITE_BRAIN=off stays the pure deterministic floor.
F9  intake fails fast with the exact missing-field list (intake response,
    practice view, and run creation) — never a cryptic mid-run ValueError.
F10 placeholder/sentinel content cannot publish: '[SILENT]' is an inbox
    state with honest narration, and the publish boundary refuses it.
F11 template variables substitute for every capability; {placeholder} debris
    can never reach the inbox or the model.
F13 published essays carry rendered markdown + a real head (meta description,
    OG/Twitter, Article JSON-LD) — sanitized by construction.
F20 every roster member is honest: the Office Manager fronts the inquiry
    inbox, the Analyst fronts the real /stats counts; no dead cards.

All data synthetic (northstar-denver) — no PHI. No network, no model.
"""
from __future__ import annotations

import json
import re
import shutil
import time

from .conftest import REPO, SURVEY
from .test_svc import _wait_status
from .test_truth import _launch_site


# ── SH-F9: fail at intake, never at run ──────────────────────────────────────

NINE_Q = {
    "owner_name": "Iris Calder",
    "credential": "LCSW",
    "business_name": "Calder Counseling",
    "tagline": "Therapy that respects your time.",
    "specialties": "anxiety, life transitions",
    "populations": "adults, new parents",
    "modalities": "CBT, ACT",
    "location": "Portland, OR",
    "fee": "$160",
}

MISSING_AFTER_9Q = [
    "phone", "email", "education", "founded_date",
    "license_number", "license_year",
]


def test_intake_reports_readiness(client):
    c, _ = client
    pid = "PRACTICE-READY"
    r = c.post(f"/v1/practices/{pid}/intake", json={"survey": NINE_Q})
    assert r.status_code == 200
    body = r.json()
    assert body["missingForWebsite"] == MISSING_AFTER_9Q
    # Derivations + commitment defaults are previewed as assumptions.
    fields = {a["field"] for a in body["assumedForWebsite"]}
    assert {"service_areas", "license_state", "payment_model_type",
            "sliding_scale_policy", "availability_status"} <= fields
    # The practice view carries the same contract for the checklist UI.
    view = c.get(f"/v1/practices/{pid}").json()
    assert view["missingForWebsite"] == MISSING_AFTER_9Q


def test_incomplete_profile_refuses_website_launch_with_the_list(client):
    c, _ = client
    pid = "PRACTICE-INCOMPLETE"
    c.post(f"/v1/practices/{pid}/intake", json={"survey": NINE_Q})
    r = c.post(f"/v1/practices/{pid}/runs", json={"capability": "website-launch"})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["error"] == "intake_incomplete"
    assert detail["missingForWebsite"] == MISSING_AFTER_9Q


def test_complete_profile_reports_ready_and_launches(client):
    c, _ = client
    pid = "PRACTICE-READY-FULL"
    r = c.post(f"/v1/practices/{pid}/intake", json={"survey": SURVEY})
    assert r.json()["missingForWebsite"] == []
    rid = c.post(
        f"/v1/practices/{pid}/runs", json={"capability": "website-launch"}
    ).json()["runId"]
    _wait_status(c, pid, rid, {"needs_approval"})


# ── SH-F4: assumptions ride the approval card ────────────────────────────────

def test_website_launch_card_carries_assumed_facts(client):
    c, _ = client
    pid = "PRACTICE-ASSUMED"
    slug, rid = _launch_site(c, pid)
    run = c.get(f"/v1/practices/{pid}/runs/{rid}").json()
    facts = {a["field"]: a for a in run["assumedFacts"]}
    # northstar's survey supplies none of the commitment fields.
    assert "sliding_scale_policy" in facts
    assert "availability_status" in facts
    assert "pull_quote" in facts
    assert all(a["label"] and a["value"] for a in run["assumedFacts"])
    assert "confirm or edit" in run["assumedNote"]
    # The inbox summary view (no steps) carries it too — the card needs it.
    feed = c.get(f"/v1/practices/{pid}/runs").json()["runs"]
    mine = next(r for r in feed if r["id"] == rid)
    assert mine["assumedFacts"]


def test_supplied_commitments_are_not_flagged(client):
    c, _ = client
    pid = "PRACTICE-SUPPLIED"
    survey = dict(
        SURVEY,
        sliding_scale_policy="Three sliding-scale slots, $90-$120, currently open.",
        availability_status="Waitlist only this season",
        pull_quote="Steady work, honestly described.",
    )
    assert c.post(f"/v1/practices/{pid}/intake", json={"survey": survey}).status_code == 200
    rid = c.post(
        f"/v1/practices/{pid}/runs", json={"capability": "website-launch"}
    ).json()["runId"]
    run = _wait_status(c, pid, rid, {"needs_approval"})
    flagged = {a["field"] for a in run.get("assumedFacts", [])}
    assert flagged.isdisjoint({"sliding_scale_policy", "availability_status", "pull_quote"})


# ── SH-F5: the enrichment seam is wired (capture at preview, replay at publish) ──

class _FakeModels:
    """Answers ONLY the fees_why schema; every other block falls back to the
    floor — exactly the brain contract (per-block graceful fallback)."""

    def generate_content(self, *, model, contents, config):
        class _Resp:
            text = json.dumps({
                "prose": (
                    "We keep decisions about your care between us, and a "
                    "free consult is the kindest way to find out if we fit."
                )
            })
        return _Resp()


class _FakeClient:
    models = _FakeModels()


ENRICHED_MARK = "kindest way to find out if we fit"


def test_site_brain_off_means_floor(monkeypatch):
    import svc.config as config  # noqa: PLC0415
    import svc.runner as runner  # noqa: PLC0415

    monkeypatch.setattr(config, "SITE_BRAIN", "off")
    assert runner._site_brain() is None


def test_brain_enriches_preview_and_replay_publishes_the_same_bytes(
    client, monkeypatch, svc_env
):
    import svc.runner as runner  # noqa: PLC0415
    from engine.brain import Brain  # noqa: PLC0415

    monkeypatch.setattr(runner, "_site_brain", lambda: Brain(client=_FakeClient()))
    c, _ = client
    pid = "PRACTICE-BRAIN"
    slug, rid = _launch_site(c, pid)

    site = svc_env["sites_dir"] / slug
    enriched_app = (site / "app.js").read_text(encoding="utf-8")
    assert ENRICHED_MARK in enriched_app  # the seam actually ran

    # The accepted enrichment is DURABLE state (capture), keyed by block.
    state = svc_env["store"].get(pid)
    assert "fees_why" in state["brainBlocks"]

    # Cloud Run restart between preview and approve: the built tree is gone.
    shutil.rmtree(site)
    # The replay rebuild must NOT need the model — kill the live brain.
    monkeypatch.setattr(runner, "_site_brain", lambda: None)
    r = c.post(f"/v1/practices/{pid}/runs/{rid}/approve")
    assert r.status_code == 200
    rebuilt_app = (site / "app.js").read_text(encoding="utf-8")
    assert rebuilt_app == enriched_app  # publish == preview, byte for byte


# ── SH-F11: variables substitute for EVERY capability ────────────────────────

def test_no_capability_plan_carries_template_debris(svc_env):
    import svc.capabilities as caps  # noqa: PLC0415

    state = {"profile": dict(SURVEY), "siteUrl": "https://example.test/x"}
    for cap in caps.capabilities():
        steps = caps.plan_for(cap["id"], "sleep and anxiety", state)
        for s in steps:
            assert not caps.UNRESOLVED_RE.search(s["title"]), (cap["id"], s["title"])
            assert not caps.UNRESOLVED_RE.search(s["instruction"]), (cap["id"], s["title"])


def test_topic_lands_in_the_templates_own_slot(svc_env):
    import svc.capabilities as caps  # noqa: PLC0415

    state = {"profile": dict(SURVEY)}
    steps = caps.plan_for("growth-engine", "sleep and anxiety", state)
    assert steps[0]["title"] == "Pick topic + angle: sleep and anxiety"
    steps = caps.plan_for("proposal-engine", "Dr. Reyes referral pact", state)
    blob = json.dumps(steps)
    assert "{recipient}" not in blob and "Dr. Reyes referral pact" in blob


def test_undeclared_variable_fails_loudly(svc_env, monkeypatch):
    import svc.capabilities as caps  # noqa: PLC0415
    import pytest  # noqa: PLC0415

    broken = {"variables": ["topic"], "steps": [
        {"ref": "x", "title": "Use {mystery}", "description": "…", "assignee": "blog"},
    ]}
    monkeypatch.setattr(caps, "template_for", lambda cap_id: broken)
    with pytest.raises(caps.TemplateVariableError):
        caps.step_plan("weekly-blog", {"topic": "t"})


# ── SH-F10: sentinel content cannot publish; silence is narrated ─────────────

def test_publish_picker_selects_the_draft_not_the_log(svc_env):
    import svc.publisher as publisher  # noqa: PLC0415

    steps = [
        {"ref": "keywords", "title": "Pick topic + angle: sleep", "isReview": False,
         "assignee": "strategist", "output": "Topic: sleep. Angle: routines."},
        {"ref": "draft", "title": "Stage the post: sleep", "isReview": False,
         "assignee": "website", "output": "# Sleep, honestly\n\nA real essay body."},
        {"ref": "measure", "title": "Log results: sleep", "isReview": False,
         "assignee": "analytics", "output": "[SILENT]"},
    ]
    entry, title, body = publisher.post_entry(steps)
    assert title == "Sleep, honestly"
    assert "[SILENT]" not in body


def test_assert_publishable_refuses_sentinel_empty_and_debris(svc_env):
    import pytest  # noqa: PLC0415
    import svc.publisher as publisher  # noqa: PLC0415

    for bad in ("[SILENT]", "", "   ", "Intro {seed} body", "Hello {{owner_name}}"):
        with pytest.raises(publisher.PublishError) as exc:
            publisher.assert_publishable("A title", bad)
        assert str(exc.value).startswith("content_invalid"), bad
    publisher.assert_publishable("A title", "A perfectly honest finished essay.")


def test_silent_step_narrates_honestly_in_the_inbox(client, monkeypatch):
    c, _ = client
    import svc.gemini as gemini  # noqa: PLC0415
    import svc.runner as runner  # noqa: PLC0415

    def scripted(system, user, **kw):
        # The measure step's instruction carries the template's silence
        # contract ("…reply exactly [SILENT]") — answer it literally.
        if "[SILENT]" in user:
            return "[SILENT]"
        return "An honest deliverable about the topic.\n\nPlain prose."

    monkeypatch.setattr(gemini, "generate_text", scripted)
    pid = "PRACTICE-SILENT"
    c.post(f"/v1/practices/{pid}/intake", json={"survey": SURVEY})
    rid = c.post(
        f"/v1/practices/{pid}/runs",
        json={"capability": "growth-engine", "topic": "rest"},
    ).json()["runId"]
    run = _wait_status(c, pid, rid, {"needs_approval"})
    measure = next(s for s in run["steps"] if s.get("ref") == "measure")
    assert measure["silent"] is True
    assert measure["output"] == runner.SILENT_STEP_OUTPUT
    # The sentinel never reaches anything a therapist reads (titles/outputs);
    # the step INSTRUCTION legitimately carries the template's contract text.
    rendered = json.dumps(
        [(s["title"], s["output"]) for s in run["steps"]]
    )
    assert "[SILENT]" not in rendered


def test_approve_refuses_a_sentinel_draft_without_burning_usage(client, svc_env):
    c, _ = client
    pid = "PRACTICE-SENTINEL"
    # A live site first (the publish leg only fires onto one).
    slug, rid = _launch_site(c, pid)
    assert c.post(f"/v1/practices/{pid}/runs/{rid}/approve").status_code == 200
    usage_before = c.get(f"/v1/practices/{pid}").json()["monthUsage"]

    # A weekly-blog run whose staged draft is the raw sentinel (a model that
    # answered the contract literally) — crafted directly in state.
    bad_run = {
        "id": "run-sentinel-1", "capability": "weekly-blog", "label": "Weekly Blog",
        "topic": "rest", "tier": "solo", "status": "needs_approval",
        "createdAt": int(time.time()),
        "steps": [{
            "index": 0, "ref": "draft", "assignee": "blog",
            "title": "Draft the rest post", "instruction": "…",
            "isReview": False, "isGate": False, "status": "done",
            "output": "[SILENT]",
        }],
    }
    svc_env["store"].mutate(pid, lambda s: s["runs"].insert(0, bad_run))

    r = c.post(f"/v1/practices/{pid}/runs/run-sentinel-1/approve")
    assert r.status_code == 409
    assert r.json()["detail"] == "content_invalid"
    run = c.get(f"/v1/practices/{pid}/runs/run-sentinel-1").json()
    assert run["approveError"]["category"] == "content_invalid"
    assert run["approveError"]["canRevise"] is True
    assert run["status"] == "needs_approval"  # still parked, still revisable
    # Nothing published, nothing counted.
    assert c.get(f"/v1/practices/{pid}").json()["monthUsage"] == usage_before


# ── SH-F13: essays ship rendered markdown + a real head ──────────────────────

def test_published_essay_renders_markdown_and_meta(client, svc_env, monkeypatch):
    import svc.publisher as publisher  # noqa: PLC0415

    c, _ = client
    pid = "PRACTICE-ESSAY-HEAD"
    slug, rid = _launch_site(c, pid)
    assert c.post(f"/v1/practices/{pid}/runs/{rid}/approve").status_code == 200

    steps = [{
        "ref": "draft", "title": "Draft the post", "isReview": False,
        "output": (
            "# Rest, honestly\n\n"
            "Rest is **not** a reward — it is *maintenance*.\n\n"
            "1. Keep a wind-down hour\n2. Park the phone\n\n"
            "- No screens in bed\n- Same wake time\n\n"
            "More in [this primer](https://example.test/primer).\n\n"
            "<script>alert('nope')</script>"
        ),
    }]
    uploads: list = []

    class _Blob:
        def __init__(self, name):
            self.name, self.cache_control = name, ""

        def upload_from_filename(self, path, content_type=""):
            uploads.append(self.name)

    class _Bucket:
        def blob(self, name):
            return _Blob(name)

    monkeypatch.setattr(publisher, "_bucket", lambda: _Bucket())
    publisher.publish_post(slug, {"id": "r", "capability": "weekly-blog"}, steps)

    page = (svc_env["sites_dir"] / slug / "writing" / "rest-honestly.html").read_text(
        encoding="utf-8"
    )
    # Markdown rendered — no literal asterisks in the body copy.
    assert "<strong>not</strong>" in page and "<em>maintenance</em>" in page
    assert "<ol><li>Keep a wind-down hour</li>" in page
    assert "<ul><li>No screens in bed</li>" in page
    assert '<a href="https://example.test/primer" rel="noopener">this primer</a>' in page
    assert "**" not in page.split("<main", 1)[1]
    # Sanitized by construction: raw HTML from the model is escaped.
    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page
    # The head is real: description + OG/Twitter + Article JSON-LD.
    assert '<meta name="description" content="Rest is not a reward' in page
    assert '<meta property="og:type" content="article" />' in page
    assert '<meta name="twitter:card" content="summary" />' in page
    blocks = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', page, re.S
    )
    article = json.loads(blocks[0])
    assert article["@type"] == "Article"
    assert article["headline"] == "Rest, honestly"
    assert article["datePublished"]


# ── SH-F20: an honest roster + the Analyst's real numbers ────────────────────

def test_every_roster_member_is_honest(client):
    c, _ = client
    roster = c.get("/v1/roster").json()["staff"]
    for member in roster:
        assert member["capabilities"] or member.get("surface"), member["name"]
    om = next(m for m in roster if m["name"] == "orchestrator")
    assert om["surface"]["kind"] == "inquiries"  # the wave-1 rail, fronted
    analyst = next(m for m in roster if m["name"] == "analytics")
    assert analyst["surface"]["kind"] == "stats"
    assert "estimate" in analyst["tagline"].lower()


def test_stats_endpoint_reports_real_counts_only(client):
    c, _ = client
    pid = "PRACTICE-STATS"
    slug, rid = _launch_site(c, pid)
    assert c.post(f"/v1/practices/{pid}/runs/{rid}/approve").status_code == 200
    # One real inquiry through the public rail.
    bare = c.__class__(c.app)
    assert bare.post(
        f"/v1/sites/{slug}/inquiry",
        json={"name": "Sam Fixture", "email": "sam@example.test"},
    ).status_code == 200

    stats = c.get(f"/v1/practices/{pid}/stats").json()
    assert stats["runs"]["total"] == 1
    assert stats["runs"]["byStatus"]["published"] == 1
    assert stats["runs"]["approvedThisMonth"] == 1
    assert stats["monthUsage"] == 1
    assert stats["postsPublished"] == 0 and stats["latestPost"] is None
    assert stats["inquiries"] == {"total": 1, "new": 1}
    assert stats["siteLive"] is True
