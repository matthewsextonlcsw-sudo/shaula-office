"""publisher — the $ anchor: built sites go LIVE (D-FreeStaff).

Ports the PROVEN publish path from bin/shaula-office (publish_site_gcs,
live-verified in a browser 2026-06-08) onto the google-cloud-storage client
(Cloud Run has no gcloud CLI). The sites bucket is public at the bucket
level — a one-time MWS host setup — so publishing is a plain upload.

Layout in gs://SITES_BUCKET/:
    {slug}/...            the LIVE site
    preview/{slug}/...    the pre-approval preview (also public — it is the
                          practice's own marketing copy, zero PHI; the
                          clinician needs a clickable link, not a login)
    {slug}/writing/<post>.html   published essays (standalone pages)

Blog publishing: a standalone, site-styled essay page + an entry prepended
to the site's `const posts = [...]` array (deterministic marker rewrite of
the BUILT app.js — the template's fill/verify already ran; the publisher
owns the built artifact). GEO stays intact; geo.inject is idempotent.

MARKETING ONLY — no PHI can reach this module by construction.
"""
from __future__ import annotations

import datetime as _dt
import html
import json
import logging
import mimetypes
import pathlib
import re
import sys

from . import config

if str(config.REPO) not in sys.path:
    sys.path.insert(0, str(config.REPO))

log = logging.getLogger("shaula.publisher")

POSTS_RE = re.compile(r"const posts = \[.*?\];", re.DOTALL)

# Local publish backend (dev/demo): "publishing" copies the built site into
# a published/ tree the svc itself serves at /sites/ — the WHOLE loop
# (build → preview → approve → live URL) runs in a browser with zero cloud.
PUBLISHED_DIR_NAME = "published"


def _local_publish_dir() -> pathlib.Path:
    out = config.SITES_DIR.parent / PUBLISHED_DIR_NAME
    out.mkdir(parents=True, exist_ok=True)
    return out


def _copy_tree(src: pathlib.Path, dst: pathlib.Path) -> int:
    """Merge-copy src over dst — the SAME upsert semantics as the GCS
    backend's `_upload_dir` (which overwrites floor blobs and leaves
    everything else, e.g. previously published `writing/` essays, intact).
    The old replace-the-tree behavior silently deleted live essay pages on
    every site republish in local mode (SH-F2)."""
    import shutil

    dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return sum(1 for p in src.rglob("*") if p.is_file())


class PublishError(RuntimeError):
    pass


def _bucket():
    from google.cloud import storage  # lazy — tests stub the uploaders

    client = storage.Client(project=config.GCP_PROJECT)
    return client.bucket(config.SITES_BUCKET)


def _upload_dir(local: pathlib.Path, prefix: str) -> int:
    """Upload every file under local/ to {prefix}/... Returns file count."""
    bucket = _bucket()
    count = 0
    for path in sorted(local.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(local).as_posix()
        blob = bucket.blob(f"{prefix}/{rel}")
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        blob.cache_control = "public, max-age=300"
        blob.upload_from_filename(str(path), content_type=ctype)
        count += 1
    return count


def _public_url(prefix: str) -> str:
    return f"https://storage.googleapis.com/{config.SITES_BUCKET}/{prefix}/index.html"


def _site_dir(slug: str) -> pathlib.Path:
    site = config.SITES_DIR / slug
    if not site.is_dir():
        raise PublishError(f"no built site at sites/{slug}")
    return site


def publish_preview(slug: str) -> str:
    """Pre-approval preview — the clickable link in the approval card."""
    if config.PUBLISH_BACKEND == "local":
        n = _copy_tree(_site_dir(slug), _local_publish_dir() / "preview" / slug)
        log.info("preview_published slug=%s files=%d backend=local", slug, n)
        return f"{config.PUBLIC_ORIGIN}/sites/preview/{slug}/index.html"
    n = _upload_dir(_site_dir(slug), f"preview/{slug}")
    log.info("preview_published slug=%s files=%d", slug, n)
    return _public_url(f"preview/{slug}")


def publish_site(slug: str, posts: list[dict] | None = None) -> str:
    """The clinician approved — the site goes LIVE.

    ``posts`` is the practice's durable essay registry (state doc, SH-F2).
    When supplied, the shipped ``app.js`` carries the FULL registry, so the
    site's essay cards survive instance restarts and later site rebuilds —
    a fresh floor build can never silently erase published work.
    """
    site = _site_dir(slug)
    if posts:
        inject_posts_file(site, posts)
    if config.PUBLISH_BACKEND == "local":
        n = _copy_tree(site, _local_publish_dir() / slug)
        log.info("site_published slug=%s files=%d backend=local", slug, n)
        return f"{config.PUBLIC_ORIGIN}/sites/{slug}/index.html"
    n = _upload_dir(site, slug)
    log.info("site_published slug=%s files=%d", slug, n)
    return _public_url(slug)


def unpublish_site(slug: str) -> int:
    """The off switch — take the LIVE site down. Returns files removed.

    A therapist who publishes and then has second thoughts must have a real
    way back (the trust promise in docs/THERAPIST_ONBOARDING.md). Removes the
    live prefix only; the preview and the built artifact stay, so re-approving
    a later run can put the site back up.
    """
    if config.PUBLISH_BACKEND == "local":
        import shutil  # noqa: PLC0415

        live = _local_publish_dir() / slug
        n = sum(1 for p in live.rglob("*") if p.is_file()) if live.is_dir() else 0
        if live.is_dir():
            shutil.rmtree(live)
        log.info("site_unpublished slug=%s files=%d backend=local", slug, n)
        return n
    bucket = _bucket()
    n = 0
    for blob in list(bucket.list_blobs(prefix=f"{slug}/")):
        blob.delete()
        n += 1
    log.info("site_unpublished slug=%s files=%d", slug, n)
    return n


# ── Blog post publishing ─────────────────────────────────────────────────────
#
# Durability model (SH-F2): the practice STATE DOC owns the posts registry
# (state["posts"], newest first) — the same CAS-backed durable store as the
# profile. The built/published app.js is a RENDER of that registry, never the
# source of truth, so a Cloud Run restart, a wiped build dir, or a later site
# rebuild can never silently lose published essay cards. The old behavior
# (prepend one entry into whatever array the ephemeral built app.js happened
# to carry) was the root cause the audit flagged.

def _post_slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", title.lower()).strip("-")
    return (s[:48].strip("-")) or "essay"


def _split_post(text: str) -> tuple[str, str]:
    """First line (stripped of md heading marks) = title; rest = body."""
    lines = [l for l in text.strip().splitlines()]
    title = re.sub(r"^#+\s*", "", lines[0]).strip() if lines else "Essay"
    body = "\n".join(lines[1:]).strip()
    return title or "Essay", body


# Sentinel/placeholder content that must NEVER publish as an essay body
# (UX audit SH-F10): the growth-engine analytics step legitimately replies
# "[SILENT]" pre-publication — that is an inbox state, not client-facing copy.
_SENTINEL_RE = re.compile(r"\[\s*SILENT\s*\]", re.I)
# Unresolved template debris — {seed}-style placeholders or {{token}} leaks —
# is a build bug, not publishable prose (ties SH-F11's invariant to publish).
_PLACEHOLDER_RE = re.compile(r"\{\{[a-zA-Z0-9_]+\}\}|\{[a-z][a-z0-9_]*\}")


def assert_publishable(title: str, body: str) -> None:
    """The render-check of the essay path: refuse placeholder/sentinel/empty
    content at the publish boundary (SH-F10/SH-F11). Raises PublishError with
    a 'content_invalid:' prefix the approve path maps to an honest, revisable
    refusal — never a silent wrong-content publication."""
    text = f"{title}\n{body}".strip()
    if not (body or "").strip():
        raise PublishError("content_invalid: the draft body is empty")
    if _SENTINEL_RE.search(text):
        raise PublishError(
            "content_invalid: the draft contains the [SILENT] sentinel — "
            "an inbox state, never an essay"
        )
    leftovers = sorted(set(_PLACEHOLDER_RE.findall(text)))
    if leftovers:
        raise PublishError(
            "content_invalid: unresolved placeholder(s) in the draft: "
            + ", ".join(leftovers[:5])
        )


def pick_draft_step(post_steps: list[dict]) -> dict:
    """Select the publishable draft by SEMANTICS, not title sniffing
    (UX audit SH-F10). Preference order:
      1. the step whose template ref is 'draft' (the staged post),
      2. a step whose title says draft (legacy plans without refs),
      3. the last step that produced content and is not analytics/silent.
    The old rule ("last step's output") published the growth-engine's
    measurement log — or the literal text '[SILENT]' — as the essay."""
    by_ref = next((s for s in post_steps if s.get("ref") == "draft"), None)
    if by_ref:
        return by_ref
    by_title = next(
        (s for s in post_steps if "draft" in (s.get("title") or "").lower()), None
    )
    if by_title:
        return by_title
    candidates = [
        s for s in post_steps
        if (s.get("output") or "").strip()
        and not s.get("silent")
        and s.get("assignee") != "analytics"
        and not _SENTINEL_RE.fullmatch((s.get("output") or "").strip())
    ]
    if not candidates:
        raise PublishError("content_invalid: no publishable draft step in this run")
    return candidates[-1]


def post_entry(post_steps: list[dict]) -> tuple[dict, str, str]:
    """The approved package → (registry entry, title, body).

    The entry is what the runner persists into the durable state doc; title
    and body feed the standalone page render. Pure — no I/O. Raises
    PublishError('content_invalid: …') for sentinel/empty/placeholder drafts."""
    draft = pick_draft_step(post_steps)["output"]
    title, body = _split_post(draft)
    assert_publishable(title, body)
    pslug = _post_slug(title)
    words = max(1, len(body.split()))
    entry = {
        "slug": pslug,
        "title": title,
        "description": _plain_text(body.split("\n")[0])[:140] or title,
        "date": _dt.date.today().isoformat(),
        "readingTime": f"{max(1, round(words / 220))} min",
        "tag": "Essay",
        "href": f"writing/{pslug}.html",
    }
    return entry, title, body


def _js(s: object) -> str:
    """JS string literal: HTML-escaped (values land in HTML text via the
    template's `${...}` — the engine's own emitter idiom) then repr-quoted
    (Python string repr is a valid JS literal; single quotes, matching the
    array style the original publisher emitted and tests pin)."""
    return repr(html.escape(str(s), quote=False))


def render_posts_js(posts: list[dict]) -> str:
    """Registry → the template's `const posts = [...];` block. Rendering the
    WHOLE registry (instead of prepending one entry) is what makes the block
    idempotent and rebuild-proof."""
    rows = []
    for p in posts:
        rows.append(
            "  { slug: %s, title: %s, description: %s, date: %s, "
            "readingTime: %s, tag: %s, href: %s },"
            % tuple(
                _js(p.get(k, ""))
                for k in ("slug", "title", "description", "date", "readingTime", "tag", "href")
            )
        )
    inner = ("\n" + "\n".join(rows) + "\n") if rows else "\n"
    return "const posts = [" + inner + "];"


def inject_posts_file(site_dir: pathlib.Path | str, posts: list[dict]) -> None:
    """Rewrite a built site's app.js posts array from the durable registry."""
    app_js = pathlib.Path(site_dir) / "app.js"
    if not app_js.is_file():
        raise PublishError(f"no app.js to carry the posts registry in {site_dir}")
    src = app_js.read_text(encoding="utf-8")
    match = POSTS_RE.search(src)
    if not match:
        raise PublishError("posts marker missing from app.js — cannot inject registry")
    app_js.write_text(
        src[: match.start()] + render_posts_js(posts) + src[match.end():],
        encoding="utf-8",
    )


# ── Markdown rendering (UX audit SH-F13) ─────────────────────────────────────
# The model writes standard markdown; readers were seeing literal asterisks.
# This renders the honest subset (bold/italic/links/ordered+unordered lists/
# headings/paragraphs) with sanitization BY CONSTRUCTION: every character is
# HTML-escaped FIRST, then the markdown transforms re-introduce only our own
# vetted tags. Raw HTML in model output can never reach the page. Links are
# restricted to http(s) — no javascript: or data: schemes, rel hardened.

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_MD_ITALIC_RE = re.compile(r"(?<![*\w])\*([^*\n]+?)\*(?![*\w])")
_OL_ITEM_RE = re.compile(r"^\d+[.)]\s+")
# Single-backslash \s — the old inline r'^[-*]\\s*' matched a literal
# backslash, so "- item" rendered with its dash still attached.
_UL_ITEM_RE = re.compile(r"^[-*]\s*")


def _inline_md(escaped: str) -> str:
    """Inline markdown over ALREADY-ESCAPED text (links → bold → italics)."""
    out = _MD_LINK_RE.sub(
        lambda m: (
            f'<a href="{html.escape(m.group(2), quote=True)}" '
            f'rel="noopener">{m.group(1)}</a>'
        ),
        escaped,
    )
    out = _MD_BOLD_RE.sub(r"<strong>\1</strong>", out)
    out = _MD_ITALIC_RE.sub(r"<em>\1</em>", out)
    return out


def _plain_text(md: str) -> str:
    """Markdown → plain text (for meta descriptions; no tags, no md tokens)."""
    s = _MD_LINK_RE.sub(r"\1", md or "")
    s = re.sub(r"[*_#`]+", "", s)
    return " ".join(s.split()).strip()


def _body_html(body: str) -> str:
    """Honest markdown subset → sanitized HTML (escape first, transform after):
    paragraphs, # headings, -/* lists, 1. lists, **bold**, *italic*, [links]."""
    out: list[str] = []
    for block in re.split(r"\n\s*\n", body):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        if block.startswith("#"):
            text = re.sub(r"^#+\s*", "", block)
            out.append(f"<h2>{_inline_md(html.escape(text))}</h2>")
        elif all(l.lstrip().startswith(("-", "*")) and not l.lstrip().startswith("**")
                 for l in lines):
            items = "".join(
                f"<li>{_inline_md(html.escape(_UL_ITEM_RE.sub('', l.strip())))}</li>"
                for l in lines
            )
            out.append(f"<ul>{items}</ul>")
        elif all(_OL_ITEM_RE.match(l.strip()) for l in lines):
            items = "".join(
                f"<li>{_inline_md(html.escape(_OL_ITEM_RE.sub('', l.strip())))}</li>"
                for l in lines
            )
            out.append(f"<ol>{items}</ol>")
        else:
            out.append(f"<p>{_inline_md(html.escape(block))}</p>")
    return "\n".join(out)


def _post_page(
    site_title: str,
    title: str,
    body: str,
    date: str,
    disclosure: str = "",
    description: str = "",
    url: str = "",
) -> str:
    """A published essay page with a REAL head (UX audit SH-F13): meta
    description, OG/Twitter cards, and Article JSON-LD — the pieces the
    'get found on Google + AI search' promise needs on every essay, reusing
    the engine's structured-data builder (engine/geo.py)."""
    from engine import geo  # noqa: PLC0415 — engine import after sys.path

    # The AI-involvement disclosure is a VISIBLE footer line (transparency is
    # a feature, not an HTML comment). Empty string = the practice opted out.
    disclosure_html = (
        f'\n  <p class="meta ai-note" style="opacity:.65;font-size:13px;'
        f'margin-top:44px;border-top:1px solid rgba(0,0,0,.12);'
        f'padding-top:14px;">{html.escape(disclosure)}</p>'
        if disclosure else ""
    )
    description = (description or title).strip()[:155]
    page_title = f"{title} — {site_title}"
    article = geo.build_article_jsonld(
        title, description, date, site_title, site_title, url
    )
    head_extra = "\n".join(
        [
            f'<meta name="description" content="{html.escape(description, quote=True)}">',
            '<meta property="og:type" content="article" />',
            f'<meta property="og:title" content="{html.escape(page_title, quote=True)}" />',
            f'<meta property="og:description" content="{html.escape(description, quote=True)}" />',
            f'<meta property="og:site_name" content="{html.escape(site_title, quote=True)}" />',
            *( [f'<meta property="og:url" content="{html.escape(url, quote=True)}" />'] if url else [] ),
            '<meta name="twitter:card" content="summary" />',
            f'<meta name="twitter:title" content="{html.escape(page_title, quote=True)}" />',
            f'<meta name="twitter:description" content="{html.escape(description, quote=True)}" />',
            '<script type="application/ld+json">',
            json.dumps(article, indent=2, ensure_ascii=False),
            "</script>",
        ]
    )
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(page_title)}</title>
{head_extra}
<link rel="stylesheet" href="../styles.css">
</head><body>
<main class="post-page" style="max-width:720px;margin:0 auto;padding:48px 20px;">
  <p><a class="text-link" href="../index.html">← {html.escape(site_title)}</a></p>
  <h1>{html.escape(title)}</h1>
  <p class="meta" style="opacity:.7">{html.escape(date)}</p>
  {body}{disclosure_html}
</main>
</body></html>"""


def publish_post(
    slug: str,
    run: dict,
    post_steps: list[dict],
    disclosure: str = "",
    posts: list[dict] | None = None,
) -> str:
    """Approved weekly-blog package → live essay on the practice site.

    The whole package keeps its copy-paste value in the inbox; this is the
    on-site leg. ``disclosure`` is the practice's AI-involvement footer line
    (engine.build_practice.ai_disclosure — on by default, therapist-
    configurable). ``posts`` is the COMPLETE durable registry to render into
    app.js, already including this post's entry (the runner owns persisting
    it to state). Callers without a registry get just this post's card.
    """
    site = _site_dir(slug)
    entry, title, body = post_entry(post_steps)  # raises on sentinel/empty drafts
    pslug = entry["slug"]

    practice_name = slug.replace("-", " ").title()
    public_url = (
        f"{config.PUBLIC_ORIGIN}/sites/{slug}/writing/{pslug}.html"
        if config.PUBLISH_BACKEND == "local"
        else f"https://storage.googleapis.com/{config.SITES_BUCKET}/{slug}/writing/{pslug}.html"
    )
    writing_dir = site / "writing"
    writing_dir.mkdir(exist_ok=True)
    page = _post_page(
        practice_name, title, _body_html(body), entry["date"], disclosure,
        description=_plain_text(entry["description"]), url=public_url,
    )
    (writing_dir / f"{pslug}.html").write_text(page, encoding="utf-8")

    # Render the FULL registry into the built app.js (idempotent — a retried
    # approval or a rebuilt floor produces the same array, never a dupe).
    inject_posts_file(site, posts if posts else [entry])

    # Ship only what changed.
    if config.PUBLISH_BACKEND == "local":
        live = _local_publish_dir() / slug
        for rel in (f"writing/{pslug}.html", "app.js"):
            src = site / rel
            if src.is_file():
                dst = live / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(src.read_bytes())
        log.info("post_published slug=%s post=%s backend=local", slug, pslug)
        return f"{config.PUBLIC_ORIGIN}/sites/{slug}/writing/{pslug}.html"
    bucket = _bucket()
    for rel in (f"writing/{pslug}.html", "app.js"):
        path = site / rel
        if path.is_file():
            blob = bucket.blob(f"{slug}/{rel}")
            blob.cache_control = "public, max-age=300"
            blob.upload_from_filename(
                str(path), content_type=mimetypes.guess_type(path.name)[0] or "text/html"
            )
    log.info("post_published slug=%s post=%s", slug, pslug)
    return f"https://storage.googleapis.com/{config.SITES_BUCKET}/{slug}/writing/{pslug}.html"
