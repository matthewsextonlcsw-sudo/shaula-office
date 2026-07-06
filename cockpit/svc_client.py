"""svc_client — the cockpit's SERVER-SIDE bridge to shaula-svc authoring.

The svc is service-to-service only ("browsers never reach this service": app.py).
So the cockpit server is a trusted peer — it holds the x-internal-secret and
calls the svc on the browser's behalf. The browser talks only to the cockpit;
the secret never leaves the server. This preserves the svc's auth invariant
while giving the therapist a real browser surface.

Pure functions over stdlib urllib (the router.py idiom — zero new deps). Every
svc error is mapped to a friendly, honest UI message; raw status/violations ride
along so the surface can show exactly why a draft was refused.

Config (env, so local-dev and a live svc share one code path):
  SHAULA_SVC_URL          base origin of shaula-svc (empty = authoring not wired)
  SHAULA_INTERNAL_SECRET  the x-internal-secret (server-side only; never to a browser)
  SHAULA_PRACTICE_ID      which practice the cockpit drives (default 'cockpit-demo')
  SHAULA_TIER             tier word for the silent monthly cap (default 'solo')

NO PHI: the only data crossing this seam is a business description + the vetted
workflow template — never a client, a chart, or a session.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


def _svc_url() -> str:
    return os.environ.get("SHAULA_SVC_URL", "").rstrip("/")


def _secret() -> str:
    return os.environ.get("SHAULA_INTERNAL_SECRET", "")


def _pid() -> str:
    return os.environ.get("SHAULA_PRACTICE_ID", "cockpit-demo")


def _tier() -> str:
    return os.environ.get("SHAULA_TIER", "solo")


def configured() -> bool:
    """True when a svc origin is wired — the surface hides authoring otherwise
    instead of offering a button that can only fail."""
    return bool(_svc_url())


def _post(path: str, payload: dict, *, timeout: float = 60.0) -> tuple[int, dict]:
    """POST JSON to the svc with the internal secret. Returns (status, body).

    A transport failure (svc down / DNS) surfaces as status 0 — the one code
    the caller maps to 'unreachable' rather than a real HTTP refusal.
    """
    url = _svc_url() + path
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    secret = _secret()
    if secret:
        headers["x-internal-secret"] = secret
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, _read_json(resp.read())
    except urllib.error.HTTPError as exc:  # 4xx/5xx — the svc answered
        return exc.code, _read_json(exc.read())
    except (urllib.error.URLError, OSError, TimeoutError):  # never reached the svc
        return 0, {}


def _read_json(raw: bytes) -> dict:
    try:
        out = json.loads(raw or b"{}")
        return out if isinstance(out, dict) else {"value": out}
    except (ValueError, TypeError):
        return {}


# FastAPI wraps a handler's `detail` under {"detail": ...}; a string detail is a
# simple code (e.g. "authoring_disabled"), a dict detail carries violations.
def _detail(body: dict) -> dict:
    d = body.get("detail", body)
    return d if isinstance(d, dict) else {"error": str(d)}


def _map_error(status: int, body: dict) -> dict:
    """Translate a non-200 svc response into an honest, plain-language result."""
    if status == 0:
        return {"ok": False, "error": "unreachable",
                "message": "Couldn't reach the Shaula service. Is it running?"}
    if status == 404:
        return {"ok": False, "error": "authoring_disabled",
                "message": "Workflow authoring isn't switched on for this service yet."}
    if status == 401:
        return {"ok": False, "error": "unauthorized",
                "message": "The cockpit isn't authorized to reach the service "
                           "(check SHAULA_INTERNAL_SECRET)."}
    detail = _detail(body)
    if status == 422:
        return {"ok": False, "error": detail.get("error", "could_not_author"),
                "violations": detail.get("violations", []),
                "message": "Shaula couldn't turn that into an honest workflow. "
                           "Try describing the outcome more plainly."}
    return {"ok": False, "error": detail.get("error", f"http_{status}"),
            "message": f"The service returned an unexpected error ({status})."}


def draft(description: str, *, with_skill: bool = False) -> dict:
    """Plain-language request -> a vetted, honesty-gated workflow PREVIEW for the
    therapist to approve. On success returns the svc body (name, steps, template,
    skill?); on any refusal returns {ok: False, error, message, violations?}."""
    description = (description or "").strip()
    if not description:
        return {"ok": False, "error": "empty", "message": "Describe the job first."}
    status, body = _post(
        f"/v1/practices/{_pid()}/workflows/draft",
        {"description": description[:2000], "withSkill": bool(with_skill)},
    )
    if status == 200:
        return body
    return _map_error(status, body)


def create(template: dict, *, idempotency_key: str = "") -> dict:
    """Run a therapist-approved template through the svc's honesty-gated runner.
    The svc re-validates the (untrusted) template before any task is created."""
    if not isinstance(template, dict) or not template.get("steps"):
        return {"ok": False, "error": "empty", "message": "Nothing to run — draft a workflow first."}
    status, body = _post(
        f"/v1/practices/{_pid()}/workflows/create",
        {"template": template, "tier": _tier(), "idempotencyKey": (idempotency_key or "")[:80]},
    )
    if status == 200:
        return body
    return _map_error(status, body)


def _get(path: str, *, timeout: float = 15.0) -> tuple[int, dict]:
    """GET JSON from the svc with the internal secret. (status, body); 0 = unreachable."""
    headers = {}
    secret = _secret()
    if secret:
        headers["x-internal-secret"] = secret
    req = urllib.request.Request(_svc_url() + path, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, _read_json(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, _read_json(exc.read())
    except (urllib.error.URLError, OSError, TimeoutError):
        return 0, {}


# ── Task board (runs) ───────────────────────────────────────────────────────
# These power the cockpit's live Tasks board: a run is a task that shows up the
# moment it's queued and updates in place (queued → working → needs_approval)
# until the therapist approves it. NO PHI — capability + topic only.

def list_runs() -> dict:
    """The live task feed: {runs, needsApproval, newInquiries}, or an error w/ runs=[]."""
    if not _svc_url():
        return {"ok": False, "error": "unreachable", "runs": [], "needsApproval": 0,
                "message": "The Shaula service isn't wired (set SHAULA_SVC_URL)."}
    status, body = _get(f"/v1/practices/{_pid()}/runs")
    if status == 200:
        return body
    return {**_map_error(status, body), "runs": [], "needsApproval": 0}


def create_run(capability: str, topic: str = "", *, idempotency_key: str = "") -> dict:
    """Queue a capability run (a task). Returns {ok, runId, status} or an honest error."""
    capability = (capability or "").strip()
    if not capability:
        return {"ok": False, "error": "empty", "message": "No task to run."}
    status, body = _post(
        f"/v1/practices/{_pid()}/runs",
        {"capability": capability, "topic": (topic or "")[:200],
         "tier": _tier(), "idempotencyKey": (idempotency_key or "")[:80]},
    )
    if status == 200:
        return {"ok": True, **body}
    return _map_error(status, body)


def approve_run(rid: str, *, note: str = "") -> dict:
    """The therapist's okay — advances/publishes the task."""
    status, body = _post(f"/v1/practices/{_pid()}/runs/{rid}/approve", {"note": note[:500]})
    return {"ok": True, **body} if status == 200 else _map_error(status, body)


def reject_run(rid: str, *, note: str = "") -> dict:
    """Park the task."""
    status, body = _post(f"/v1/practices/{_pid()}/runs/{rid}/reject", {"note": note[:500]})
    return {"ok": True, **body} if status == 200 else _map_error(status, body)


def upsert_intake(survey: dict) -> dict:
    """Seed/refresh the practice profile (lets website-launch run on the demo box)."""
    status, body = _post(f"/v1/practices/{_pid()}/intake", {"survey": survey})
    return {"ok": True, **body} if status == 200 else _map_error(status, body)


def get_run(rid: str) -> dict:
    """One full run incl. every step's OUTPUT (the deliverable) + previewUrl. This is
    how the board shows what a task actually produced — the post text, the site, etc."""
    rid = (rid or "").strip()
    if not _svc_url() or not rid:
        return {"ok": False, "error": "unreachable", "message": "No run to open."}
    status, body = _get(f"/v1/practices/{_pid()}/runs/{rid}")
    return {"ok": True, **body} if status == 200 else _map_error(status, body)


# ── Roster + read surfaces ───────────────────────────────────────────────────
# The cockpit's staff list and the two read-only surfaces (Office Manager inbox,
# Analyst counts) are driven straight from the svc so they can NEVER drift from
# the manifest ("the manifest is the product surface"). Every workflow the svc
# can run becomes reachable here. NO PHI — staff names, capability labels, and
# synthetic marketing counts only.

def roster() -> dict:
    """The live staff menu: {staff:[{name,title,tagline,surface?,capabilities[]}]}.
    On any failure returns staff=[] with an honest message so the UI degrades to a
    banner instead of a dead roster."""
    if not _svc_url():
        return {"ok": False, "error": "unreachable", "staff": [],
                "message": "The Shaula service isn't wired (set SHAULA_SVC_URL)."}
    status, body = _get("/v1/roster")
    if status == 200:
        return body
    return {**_map_error(status, body), "staff": []}


def stats() -> dict:
    """The Analyst surface — real counts only (runs/posts/inquiries), never an
    estimate. On failure: an honest error the surface can show in place."""
    if not _svc_url():
        return {"ok": False, "error": "unreachable",
                "message": "The Shaula service isn't wired (set SHAULA_SVC_URL)."}
    status, body = _get(f"/v1/practices/{_pid()}/stats")
    return {"ok": True, **body} if status == 200 else _map_error(status, body)


def inquiries() -> dict:
    """The Office Manager surface — consult inquiries from the practice's site.
    {inquiries:[...], new:int}; on failure an honest error with inquiries=[]."""
    if not _svc_url():
        return {"ok": False, "error": "unreachable", "inquiries": [], "new": 0,
                "message": "The Shaula service isn't wired (set SHAULA_SVC_URL)."}
    status, body = _get(f"/v1/practices/{_pid()}/inquiries")
    if status == 200:
        return body
    return {**_map_error(status, body), "inquiries": [], "new": 0}
