"""gemini — the svc's Vertex brain client (D-FreeStaff).

Same BAA path as engine/brain.py and every other Vertex caller in the
portfolio: google-auth ADC token + the REST generateContent endpoint on
aiplatform.googleapis.com. NEVER a consumer Gemini key (hardening rule).

Honesty by construction: every model output is run through the SAME linter
that guards the site generator (engine/generate.py:lint). A banned claim
does not get "fixed" — the step fails coded and the run parks for a human.
That is the moat; it is not negotiable per-call.

No PHI: prompts are marketing/business text only — this service cannot see
clinical data by construction. Logs carry categories and counts, never text.
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any

import httpx

from . import config, honesty

log = logging.getLogger("shaula.gemini")

# engine/ is a sibling package of svc/ in the repo — import its linter.
if str(config.REPO) not in sys.path:
    sys.path.insert(0, str(config.REPO))
if str(config.REPO / "engine") not in sys.path:
    sys.path.insert(0, str(config.REPO / "engine"))
import generate as _generate  # noqa: E402  (engine/generate.py)

lint = _generate.lint  # the single source of honesty truth


class BrainError(RuntimeError):
    """Category-coded model failure ('vertex_auth', 'vertex_http', 'honesty')."""

    def __init__(self, category: str, detail: str = "") -> None:
        super().__init__(category)
        self.category = category
        self.detail = detail


def _access_token() -> str:
    try:
        import google.auth  # noqa: PLC0415
        import google.auth.transport.requests  # noqa: PLC0415

        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        creds.refresh(google.auth.transport.requests.Request())
        return creds.token or ""
    except Exception as exc:  # noqa: BLE001
        raise BrainError("vertex_auth", str(exc)[:200]) from exc


def generate_text(
    system: str,
    user: str,
    *,
    temperature: float = 0.5,
    max_output_tokens: int = 4096,
    timeout: float = 90.0,
) -> str:
    """One generateContent round-trip → plain text, honesty-linted.

    Raises BrainError('honesty') when the output trips the linter — the
    caller parks the step for a human; we never auto-repair a banned claim.
    """
    token = _access_token()
    url = (
        f"https://{config.VERTEX_LOCATION}-aiplatform.googleapis.com/v1/projects/"
        f"{config.GCP_PROJECT}/locations/{config.VERTEX_LOCATION}/publishers/google/"
        f"models/{config.VERTEX_MODEL}:generateContent"
    )
    body: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
        },
    }
    try:
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=body,
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise BrainError("vertex_network", str(exc)[:200]) from exc
    if resp.status_code != 200:
        log.warning("vertex_http status=%s", resp.status_code)
        raise BrainError("vertex_http", f"status {resp.status_code}")
    try:
        data = resp.json()
        text = "".join(
            p.get("text", "")
            for p in data["candidates"][0]["content"]["parts"]
        ).strip()
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise BrainError("vertex_malformed", str(exc)[:200]) from exc
    if not text:
        raise BrainError("vertex_empty")

    return lint_gate(text)


def lint_gate(text: str) -> str:
    """The hard stop, narrated. Raises BrainError('honesty') when ``text``
    trips the engine linter; otherwise returns the text unchanged.

    Category only in logs — the text itself is never logged. The humanized
    explanation (plain words + the offending sentence) rides the exception
    into the RUN RECORD so the inbox can narrate the refusal (SH-F12); the
    lint itself stays the untouched hard stop. Factored out of generate_text
    so test fakes can run the REAL gate instead of imitating it.
    """
    violations = lint(text)
    if violations:
        log.info("honesty_lint_tripped count=%d", len(violations))
        err = BrainError("honesty", "; ".join(violations[:3]))
        err.explanations = honesty.explain(text, violations)
        raise err
    return text
