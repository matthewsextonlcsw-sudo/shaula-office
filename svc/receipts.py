"""receipts — per-build trust artifacts attached to a website-launch run.

Two receipts, both GENERATED from what the build actually produced (never hand-
assembled, never a second linter), so neither can drift from the published site:

  * honesty_receipt — "what Shaula refused to say about you, and why." Built from
    the engine's refusals manifest (``generated["_refusals"]``) + build_practice's
    ``_assumed`` record. The same IP ``scripts/honesty_receipt.py`` renders as a
    CLI; here it rides the RUN so the therapist sees it on the approval card. The
    banned-language policy is rendered in plain English by REUSING ``svc.honesty``
    (no second translation table).

  * provenance_receipt — belt-and-suspenders that every visible CLAIM on the
    RENDERED site traces to approved content. The built site is an SPA (``app.js``
    renders the body client-side), so the static ``index.html`` shell carries no
    body claims; we execute the site headless (``engine/render_dump.mjs``) and run
    the claim-provenance gate (``engine/provenance.py``) over the rendered HTML
    against the COMPLETE approved set — practice + generated + the engine content
    banks + the template's vetted static copy (``provenance.approved_template_extras``).
    On the fixed-template path honesty is already STRUCTURAL, so this is an
    attestation, not a hard block: a v1-coverage flag is surfaced, never used to
    fail a working build. The HARD gate is reserved for 3a/3b imported/freehand
    HTML, where the candidate's structure is untrusted and the corpus is the
    controlled approved set.

Pure stdlib + engine siblings + node (already a build-path dependency via fill).
NO PHI: every input is the provider's own public marketing data.
"""
from __future__ import annotations

import logging
import pathlib
import subprocess
import sys

from . import config, honesty

if str(config.REPO) not in sys.path:
    sys.path.insert(0, str(config.REPO))

from engine import provenance as PROV  # noqa: E402 — engine sibling, after sys.path

log = logging.getLogger("shaula.receipts")

# The v1 honest-limit caveat carried into every provenance receipt (matches
# engine/provenance.py's own documented MISSES — coverage, not entailment).
PROVENANCE_LIMIT_NOTE = (
    "Coverage-based check (v1): catches fabricated statistics, testimonials, "
    "invented credentials, and banned marketing language. It does not yet catch a "
    "false claim assembled only from approved words, or a semantic paraphrase "
    "(v2 = entailment). The fixed template's honesty is structural regardless."
)

RENDER_TIMEOUT_S = 60


# --------------------------------------------------------------------------- #
# a1 — honesty receipt (what Shaula refused to say / held back / assumed).
# --------------------------------------------------------------------------- #
def _plain_banned(patterns: list[str]) -> list[str]:
    """Engine banned-language patterns → deduped plain English, REUSING
    svc.honesty (several regexes collapse to one phrase). Single source of truth;
    never a second translation table."""
    seen: set[str] = set()
    out: list[str] = []
    for pat in patterns:
        plain = honesty._plain(pat)
        if plain not in seen:
            seen.add(plain)
            out.append(plain)
    return out


def honesty_receipt(practice: dict, generated: dict) -> dict:
    """Structured honesty receipt from the build's OWN refusals manifest +
    _assumed record. Reads what generate() already attested — never re-lints."""
    refusals = (generated or {}).get("_refusals") or {}
    assumed = list((practice or {}).get("_assumed") or [])
    shown = list(refusals.get("modalities_shown") or [])
    held_back = list(refusals.get("modalities_dropped_unknown") or [])
    refused_language = _plain_banned(list(refusals.get("banned_language_enforced") or []))
    lint_clean = bool(refusals.get("lint_clean"))

    bits: list[str] = []
    if lint_clean:
        bits.append("every published line cleared the banned-language gate")
    if held_back:
        bits.append(f"{len(held_back)} modality(ies) held back with no verifiable source")
    if assumed:
        bits.append(f"{len(assumed)} assumption(s) flagged for your confirmation")
    summary = (
        "Honesty receipt — " + "; ".join(bits) + "."
        if bits else
        "Honesty receipt — nothing refused or assumed; every field you supplied was used."
    )

    return {
        "kind": "honesty",
        "lintClean": lint_clean,
        "summary": summary,
        "refusedLanguage": refused_language,
        "modalitiesShown": shown,
        "modalitiesHeldBack": held_back,
        "assumed": assumed,
    }


# --------------------------------------------------------------------------- #
# a2 — provenance receipt (every rendered claim traces to approved content).
# --------------------------------------------------------------------------- #
def _render_spa(built_dir: str) -> str:
    """Execute the built SPA headless and return its rendered HTML (all routes).
    Raises RuntimeError on any failure (no node / no app.js / a route throwing)."""
    script = str(config.REPO / "engine" / "render_dump.mjs")
    try:
        proc = subprocess.run(
            ["node", script, "--out", str(built_dir)],
            capture_output=True, text=True, timeout=RENDER_TIMEOUT_S,
        )
    except FileNotFoundError as exc:  # node not installed
        raise RuntimeError("node not available") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("render timed out") from exc
    if proc.returncode != 0:
        last = (proc.stderr or "render failed").strip().splitlines()
        raise RuntimeError(last[-1][:160] if last else "render failed")
    html = proc.stdout
    if not html or len(html) < 200:
        raise RuntimeError("rendered output empty")
    return html


def _dedupe_offenders(offenders) -> list[dict]:
    """Shared partials (the contact CTA, footer) render on every route, so the
    same offender recurs — collapse on (kind, normalized text) for a clean card."""
    seen: set = set()
    out: list[dict] = []
    for o in offenders:
        d = o.as_dict()
        key = (d["kind"], PROV.normalize(d["text"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def provenance_receipt(built_dir: str, practice: dict, generated: dict) -> dict:
    """Render the built SPA and prove every visible claim traces to approved
    content. status: ``pass`` | ``flag`` | ``unverified``. NEVER raises — a
    verification failure degrades to ``unverified`` (structural gate still holds)."""
    base = {"kind": "provenance", "checked": "rendered-spa", "limitNote": PROVENANCE_LIMIT_NOTE}
    try:
        rendered = _render_spa(built_dir)
    except RuntimeError as exc:
        return {
            **base, "status": "unverified", "ok": False, "offenders": [],
            "summary": f"Could not render the site to verify claims ({exc}); "
                       "the fixed template's structural honesty gate still applied.",
        }

    # The built app.js carries the template's vetted static copy — fold it into
    # the approved set so honest chrome is not flagged (foreign fabrications still
    # import non-approved tokens and ARE flagged; banned-language fires regardless).
    app_js_src = ""
    try:
        p = pathlib.Path(built_dir) / "app.js"
        if p.is_file():
            app_js_src = p.read_text(encoding="utf-8")
    except OSError:
        app_js_src = ""

    extras = PROV.approved_template_extras(app_js_src)
    offenders = PROV.gate(rendered, practice or {}, generated or {}, extra_texts=extras)
    deduped = _dedupe_offenders(offenders)
    if not deduped:
        return {
            **base, "status": "pass", "ok": True, "offenders": [],
            "summary": "Every visible claim on the rendered site traces to your "
                       "approved content; no banned language.",
        }
    return {
        **base, "status": "flag", "ok": False, "offenders": deduped,
        "summary": f"{len(deduped)} item(s) on the rendered site did not trace to "
                   "approved content — review before publishing.",
    }


# --------------------------------------------------------------------------- #
# Orchestration — both receipts for one build, keyed for the run.
# --------------------------------------------------------------------------- #
def receipts_for_build(built: dict) -> dict:
    """Both build receipts, keyed for attaching to the run. ``built`` is the
    ``pipeline.build_site`` result (carries 'practice' + 'generated' + 'dir').
    Synchronous + blocking (node subprocess) — call via asyncio.to_thread."""
    practice = built.get("practice") or {}
    generated = built.get("generated") or {}
    out = {"honestyReceipt": honesty_receipt(practice, generated)}
    built_dir = built.get("dir")
    if built_dir:
        out["provenanceReceipt"] = provenance_receipt(built_dir, practice, generated)
    return out
