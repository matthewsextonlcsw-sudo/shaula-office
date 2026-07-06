"""publisher — blog publishing onto a REAL engine-built site (fake bucket)."""
from __future__ import annotations

import pathlib

from .conftest import SURVEY


class _FakeBlob:
    def __init__(self, name: str, record: list):
        self.name = name
        self.cache_control = ""
        self._record = record

    def upload_from_filename(self, path, content_type=""):
        self._record.append({"name": self.name, "path": path, "ctype": content_type})


class _FakeBucket:
    def __init__(self, record: list):
        self._record = record

    def blob(self, name: str) -> _FakeBlob:
        return _FakeBlob(name, self._record)


def test_publish_post_lands_on_the_built_site(svc_env, monkeypatch):
    import svc.publisher as publisher  # noqa: PLC0415
    from engine import pipeline  # noqa: PLC0415

    sites_dir = svc_env["sites_dir"]
    built = pipeline.build_site(SURVEY, sites_dir=sites_dir, slug="pubtest")
    site = pathlib.Path(built["dir"])

    uploads: list = []
    monkeypatch.setattr(publisher, "_bucket", lambda: _FakeBucket(uploads))

    run = {"id": "run-x", "capability": "weekly-blog"}
    steps = [
        {"title": "Blog brief: sleep", "isReview": False,
         "output": "Angle: plain talk about sleep."},
        {"title": "Draft the sleep post", "isReview": False,
         "output": "# Sleep, plainly\n\nA short honest essay about rest.\n\n## One habit\n\nKeep a steady wake time."},
    ]
    url = publisher.publish_post("pubtest", run, steps)

    # The standalone essay page exists, styled by the site's own css.
    page = site / "writing" / "sleep-plainly.html"
    assert page.is_file()
    html = page.read_text(encoding="utf-8")
    assert "Sleep, plainly" in html and "../styles.css" in html
    assert "<h2>One habit</h2>" in html

    # The posts array got the new entry, linked to the page.
    app_js = (site / "app.js").read_text(encoding="utf-8")
    assert "writing/sleep-plainly.html" in app_js
    assert "Sleep, plainly" in app_js
    # The template's post cards are real links now (the href patch).
    assert 'class="post-card" href=' in app_js

    # Only the changed files shipped, to the LIVE prefix (not preview/).
    shipped = {u["name"] for u in uploads}
    assert shipped == {"pubtest/writing/sleep-plainly.html", "pubtest/app.js"}
    assert url.endswith("pubtest/writing/sleep-plainly.html")


def test_publish_preview_and_site_prefixes(svc_env, monkeypatch):
    import svc.publisher as publisher  # noqa: PLC0415

    seen: list = []
    monkeypatch.setattr(publisher, "_upload_dir", lambda local, prefix: seen.append(prefix) or 3)
    publisher.publish_preview("pubtest")
    publisher.publish_site("pubtest")
    assert seen == ["preview/pubtest", "pubtest"]
