"""ux/shaula-truth — the five truth contracts (UX audit SH-F1/F7/F16/F17/F18).

F1  the contact form DELIVERS: public inquiry endpoint → practice state →
    staff-inbox surfacing; built sites carry the wired form (or the honest
    direct-contact fallback when no origin is configured) and the privacy
    page tells the truth in both modes.
F7  no fabricated essay cards: the engine floor ships ZERO posts; the only
    cards are real, linked, publisher-written entries.
F16 the staff menu promises what the engine delivers (no PPTX/DOCX claims;
    no phantom "office pptx/docx skill" instructions sent to the model).
F17 manifest copy matches hosting reality + the site unpublish off-switch.
F18 published output carries a visible AI-involvement disclosure, on by
    default, therapist-configurable, single-sourced for site + essays.

All data here is synthetic fixture data (northstar-denver) — no PHI.
"""
from __future__ import annotations

import json
import pathlib

from .conftest import REPO, SURVEY
from .test_svc import _wait_status


# ── helpers ──────────────────────────────────────────────────────────────────

def _bare(c):
    """A client WITHOUT the internal secret — the public internet."""
    bare = c.__class__(c.app)
    return bare


def _launch_site(c, pid):
    """intake → website-launch → needs_approval; returns the claimed slug."""
    assert c.post(f"/v1/practices/{pid}/intake", json={"survey": SURVEY}).status_code == 200
    rid = c.post(
        f"/v1/practices/{pid}/runs", json={"capability": "website-launch"}
    ).json()["runId"]
    _wait_status(c, pid, rid, {"needs_approval"})
    slug = c.get(f"/v1/practices/{pid}").json()["slug"]
    assert slug
    return slug, rid


def _site_dir(svc_env, slug) -> pathlib.Path:
    return svc_env["sites_dir"] / slug


# ── F1: the inquiry rail — a form submission can never evaporate ─────────────

def test_inquiry_delivers_to_the_staff_inbox(client, monkeypatch):
    c, _ = client
    import svc.config as config  # noqa: PLC0415

    monkeypatch.setattr(config, "INQUIRY_ORIGIN", "https://svc.example.test")
    pid = "PRACTICE-INQ"
    slug, _rid = _launch_site(c, pid)

    # The BUILT site is wired to the real endpoint — no dead-end form.
    import svc.config as cfg  # noqa: PLC0415

    app_js = (cfg.SITES_DIR / slug / "app.js").read_text(encoding="utf-8")
    endpoint = f"https://svc.example.test/v1/sites/{slug}/inquiry"
    assert f"const INQUIRY_ENDPOINT = '{endpoint}';" in app_js
    # The privacy page describes what actually happens (inbox, never email-magic).
    assert "delivers your message privately" in app_js
    assert "sends a message directly to" not in app_js  # the old lie is gone

    # A visitor (NO internal secret) submits the form. The browser preflights
    # first (cross-origin JSON POST) — 204 + CORS headers, no secret needed.
    public = _bare(c)
    pre = public.options(f"/v1/sites/{slug}/inquiry")
    assert pre.status_code == 204
    assert pre.headers.get("access-control-allow-origin") == "*"
    assert "POST" in pre.headers.get("access-control-allow-methods", "")
    r = public.post(
        f"/v1/sites/{slug}/inquiry",
        json={
            "name": "Sam Fixture",
            "email": "sam@example.test",
            "phone": "555-0100",
            "state": "Colorado",
            "notes": "Synthetic inquiry — checking consult availability.",
            "website": "",
        },
    )
    assert r.status_code == 200 and r.json()["ok"] is True
    # CORS: the cross-origin site can actually make this call.
    assert r.headers.get("access-control-allow-origin") == "*"

    # The therapist SEES it: dedicated feed + the badge on the runs poll.
    feed = c.get(f"/v1/practices/{pid}/inquiries").json()
    assert feed["new"] == 1
    inq = feed["inquiries"][0]
    assert inq["name"] == "Sam Fixture" and inq["email"] == "sam@example.test"
    assert c.get(f"/v1/practices/{pid}/runs").json()["newInquiries"] == 1
    assert c.get(f"/v1/practices/{pid}").json()["newInquiries"] == 1

    # Reading clears the badge.
    assert c.post(f"/v1/practices/{pid}/inquiries/{inq['id']}/read").json()["ok"]
    assert c.get(f"/v1/practices/{pid}/inquiries").json()["new"] == 0

    # The feed itself stays behind the auth wall.
    assert public.get(f"/v1/practices/{pid}/inquiries").status_code == 401


def test_inquiry_unknown_site_404s(client):
    c, _ = client
    r = _bare(c).post(
        "/v1/sites/never-built-this/inquiry",
        json={"name": "A", "email": "a@example.test"},
    )
    assert r.status_code == 404


def test_inquiry_honeypot_swallows_silently(client, monkeypatch):
    c, _ = client
    import svc.config as config  # noqa: PLC0415

    monkeypatch.setattr(config, "INQUIRY_ORIGIN", "https://svc.example.test")
    pid = "PRACTICE-INQ-BOT"
    slug, _rid = _launch_site(c, pid)
    r = _bare(c).post(
        f"/v1/sites/{slug}/inquiry",
        json={"name": "Bot", "email": "bot@example.test", "website": "https://spam"},
    )
    assert r.status_code == 200  # don't teach the bot
    assert c.get(f"/v1/practices/{pid}/inquiries").json()["inquiries"] == []


def test_inquiry_requires_name_and_email(client, monkeypatch):
    c, _ = client
    import svc.config as config  # noqa: PLC0415

    monkeypatch.setattr(config, "INQUIRY_ORIGIN", "https://svc.example.test")
    pid = "PRACTICE-INQ-VAL"
    slug, _rid = _launch_site(c, pid)
    assert _bare(c).post(
        f"/v1/sites/{slug}/inquiry", json={"name": "", "email": "x@example.test"}
    ).status_code == 400
    assert _bare(c).post(
        f"/v1/sites/{slug}/inquiry", json={"name": "X", "email": "not-an-email"}
    ).status_code == 400


def test_inquiry_rate_limit_brakes(client, monkeypatch):
    c, _ = client
    import svc.app as app_mod  # noqa: PLC0415
    import svc.config as config  # noqa: PLC0415

    monkeypatch.setattr(config, "INQUIRY_ORIGIN", "https://svc.example.test")
    monkeypatch.setattr(config, "INQUIRY_MAX_PER_HOUR", 3)
    app_mod._inquiry_hits.clear()
    pid = "PRACTICE-INQ-RATE"
    slug, _rid = _launch_site(c, pid)
    public = _bare(c)
    body = {"name": "Sam", "email": "sam@example.test"}
    for _ in range(3):
        assert public.post(f"/v1/sites/{slug}/inquiry", json=body).status_code == 200
    assert public.post(f"/v1/sites/{slug}/inquiry", json=body).status_code == 429


def test_built_site_without_origin_has_no_dead_form(svc_env):
    """No inquiry origin configured → the site ships the honest
    direct-contact card, not a form whose submissions go nowhere."""
    from engine import pipeline  # noqa: PLC0415

    built = pipeline.build_site(
        SURVEY, sites_dir=svc_env["sites_dir"], slug="truth-noform"
    )
    app_js = (pathlib.Path(built["dir"]) / "app.js").read_text(encoding="utf-8")
    assert "const INQUIRY_ENDPOINT = '';" in app_js
    assert "consult-direct" in app_js  # the fallback card exists
    assert "This site has no contact form" in app_js  # truthful privacy variant


# ── F7: no fabricated essay cards ────────────────────────────────────────────

def test_floor_ships_zero_fabricated_posts(svc_env):
    from engine import pipeline  # noqa: PLC0415

    built = pipeline.build_site(
        SURVEY, sites_dir=svc_env["sites_dir"], slug="truth-posts"
    )
    app_js = (pathlib.Path(built["dir"]) / "app.js").read_text(encoding="utf-8")
    # The honest floor: an EMPTY posts array …
    assert "const posts = [\n];" in app_js
    # … no invented dates / reading times anywhere …
    assert "min read" not in app_js
    assert "Feb 18" not in app_js and "Jan 21" not in app_js and "Jan 07" not in app_js
    # … and the honest empty state in their place.
    assert "The first essays are being written" in app_js


def test_published_post_card_is_real_and_linked(svc_env, monkeypatch):
    """publisher.publish_post writes the only kind of card allowed to exist:
    a real page, today's date, computed reading time, working href."""
    import datetime as dt  # noqa: PLC0415

    import svc.publisher as publisher  # noqa: PLC0415
    from engine import pipeline  # noqa: PLC0415

    built = pipeline.build_site(
        SURVEY, sites_dir=svc_env["sites_dir"], slug="truth-realpost"
    )
    site = pathlib.Path(built["dir"])
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
    steps = [{"title": "Draft the post", "isReview": False,
              "output": "# Rest, honestly\n\nA short synthetic essay about rest."}]
    publisher.publish_post("truth-realpost", {"id": "r", "capability": "weekly-blog"}, steps)

    app_js = (site / "app.js").read_text(encoding="utf-8")
    assert "href: 'writing/rest-honestly.html'" in app_js
    assert dt.date.today().isoformat() in app_js  # the REAL date, not an invented one
    assert (site / "writing" / "rest-honestly.html").is_file()


# ── F16: the menu promises what the engine delivers ──────────────────────────

def test_capability_menu_is_honest_about_outputs():
    manifest = json.loads(
        (REPO / "workflows" / "CAPABILITY_MANIFEST.json").read_text(encoding="utf-8")
    )
    caps = {c["id"]: c for c in manifest["capabilities"]}
    # The generic executor produces TEXT. The menu may not promise files.
    for cap_id in ("deck-engine", "proposal-engine"):
        desc = caps[cap_id]["description"]
        assert "PPTX" not in desc and "DOCX" not in desc, (cap_id, desc)
    assert "slide-by-slide draft" in caps["deck-engine"]["description"]
    assert "letter draft" in caps["proposal-engine"]["description"]
    # And no template step may instruct the model to use a phantom file skill.
    for cap_id in ("deck-engine", "proposal-engine"):
        tmpl = json.loads(
            (REPO / "workflows" / caps[cap_id]["template"]).read_text(encoding="utf-8")
        )
        blob = json.dumps(tmpl).lower()
        assert "office pptx skill" not in blob and "office docx skill" not in blob


# ── F17: hosting copy matches reality + the off switch ───────────────────────

def test_website_launch_copy_matches_hosting_reality():
    manifest = json.loads(
        (REPO / "workflows" / "CAPABILITY_MANIFEST.json").read_text(encoding="utf-8")
    )
    web = next(c for c in manifest["capabilities"] if c["id"] == "website-launch")
    # Sites live on a hosted address today; "own address" is v1.1 — the menu
    # the apps render verbatim must not promise it.
    assert "own address" not in web["description"]
    assert "hosted address" in web["description"]


def test_unpublish_is_a_real_off_switch(client, monkeypatch):
    c, _ = client
    import svc.publisher as publisher  # noqa: PLC0415

    pid = "PRACTICE-UNPUB"
    slug, rid = _launch_site(c, pid)
    assert c.post(f"/v1/practices/{pid}/runs/{rid}/approve").status_code == 200
    assert c.get(f"/v1/practices/{pid}").json()["siteUrl"]

    deleted: list = []

    class _Blob:
        def __init__(self, name):
            self.name = name

        def delete(self):
            deleted.append(self.name)

    class _Bucket:
        def list_blobs(self, prefix=""):
            assert prefix == f"{slug}/"
            return [_Blob(f"{slug}/index.html"), _Blob(f"{slug}/app.js")]

    monkeypatch.setattr(publisher, "_bucket", lambda: _Bucket())
    r = c.post(f"/v1/practices/{pid}/site/unpublish")
    assert r.status_code == 200 and r.json()["filesRemoved"] == 2
    assert deleted == [f"{slug}/index.html", f"{slug}/app.js"]
    assert c.get(f"/v1/practices/{pid}").json()["siteUrl"] == ""
    # Second pull of the switch: nothing live → 409, not a crash.
    assert c.post(f"/v1/practices/{pid}/site/unpublish").status_code == 409


# ── F18: the AI-involvement disclosure ───────────────────────────────────────

def test_site_footer_carries_disclosure_by_default(svc_env):
    from engine import pipeline  # noqa: PLC0415

    built = pipeline.build_site(
        SURVEY, sites_dir=svc_env["sites_dir"], slug="truth-disclose"
    )
    index = (pathlib.Path(built["dir"]) / "index.html").read_text(encoding="utf-8")
    assert (
        "Created with AI assistance from Shaula. Reviewed and approved by "
        "Maya Restrepo, LPC before publication." in index
    )


def test_disclosure_respects_the_off_switch_and_custom_text(svc_env):
    from engine import build_practice as BP  # noqa: PLC0415
    from engine import pipeline  # noqa: PLC0415

    off = dict(SURVEY, ai_disclosure="off")
    built = pipeline.build_site(off, sites_dir=svc_env["sites_dir"], slug="truth-disclose-off")
    index = (pathlib.Path(built["dir"]) / "index.html").read_text(encoding="utf-8")
    assert "Created with AI assistance" not in index

    custom = dict(SURVEY, ai_disclosure_text="Drafted with AI help; every word approved by Maya.")
    assert BP.ai_disclosure(custom) == "Drafted with AI help; every word approved by Maya."
    # A custom line that trips the banned-claim linter falls back to the
    # honest default instead of shipping.
    dishonest = dict(SURVEY, ai_disclosure_text="Our proven AI guarantees results.")
    assert "proven" not in BP.ai_disclosure(dishonest)
    assert "Created with AI assistance from Shaula" in BP.ai_disclosure(dishonest)


def test_published_essay_carries_disclosure(svc_env, monkeypatch):
    import svc.publisher as publisher  # noqa: PLC0415
    from engine import build_practice as BP  # noqa: PLC0415
    from engine import pipeline  # noqa: PLC0415

    built = pipeline.build_site(
        SURVEY, sites_dir=svc_env["sites_dir"], slug="truth-essay-note"
    )
    site = pathlib.Path(built["dir"])

    class _Blob:
        def __init__(self, name):
            self.name, self.cache_control = name, ""

        def upload_from_filename(self, path, content_type=""):
            pass

    class _Bucket:
        def blob(self, name):
            return _Blob(name)

    monkeypatch.setattr(publisher, "_bucket", lambda: _Bucket())
    steps = [{"title": "Draft the essay", "isReview": False,
              "output": "# Steady mornings\n\nA synthetic essay about routines."}]
    publisher.publish_post(
        "truth-essay-note", {"id": "r", "capability": "weekly-blog"}, steps,
        BP.ai_disclosure(SURVEY),
    )
    page = (site / "writing" / "steady-mornings.html").read_text(encoding="utf-8")
    assert "Created with AI assistance from Shaula" in page
    assert 'class="meta ai-note"' in page  # visible, not an HTML comment
