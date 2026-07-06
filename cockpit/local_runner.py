"""local_runner — the desktop app's built-in office: every shipped workflow
(the CAPABILITY_MANIFEST set), run entirely on this machine.

The cockpit UI (index.html) was built against the hosted svc's contract:
GET /api/roster (staff cards with capability menus), POST /api/runs (queue a
capability), GET /api/runs (the live board), approve/reject. The desktop app
has no hosted svc — house-nothing means the office runs HERE. This module
serves the exact same shapes from local parts:

  * capabilities  — workflows/CAPABILITY_MANIFEST.json + workflows/templates/
                    (read via workflows.builder: the allow-list, PHI gate,
                    honesty lint, and acyclic check all still apply)
  * execution     — each step's description becomes the instruction to the
                    LOCAL model (router._call_ollama — 127.0.0.1 only), with
                    parent handoffs as context
  * the moat      — every step output runs through engine.banned.lint (the
                    single box-wide honesty linter). An affirmative banned
                    claim fails the run; it is never repaired by the model.
  * human gates   — the reviewer step and any triage step PARK the run at
                    needs_approval. A model never approves its own review.
                    website-launch's approve performs the deterministic site
                    build (engine/pipeline) — the office builds, no model.

State: runs persist as JSON under SHAULA_STATE_DIR (the app's userData), so
the board survives a restart. NO PHI: capability + topic + generated marketing
text only. Pure stdlib.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import threading
import time
import uuid

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
for p in (str(REPO), str(REPO / "engine"), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import banned  # noqa: E402 — engine/banned.py, the ONE honesty linter
import router  # noqa: E402 — the local-model caller (Ollama on 127.0.0.1)
from workflows import builder as WB  # noqa: E402 — templates + guardrails

MANIFEST_PATH = REPO / "workflows" / "CAPABILITY_MANIFEST.json"


# Env read at CALL time, not import time — tests and the packaged app both set
# these after import ordering they don't control.
def _state_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("SHAULA_STATE_DIR", str(REPO / ".local-office")))


def _sites_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("SHAULA_SITES_DIR", str(REPO / "sites")))


def _runs_file() -> pathlib.Path:
    return _state_dir() / "runs.json"

# The 8 no-PHI office roles the roster shows (mirrors the hosted svc's list —
# svc/capabilities.py OFFICE_STAFF — kept verbatim so the two surfaces read
# identically; the CAPABILITIES themselves come only from the manifest).
OFFICE_STAFF = [
    {"name": "orchestrator", "title": "Office Manager",
     "tagline": "Runs the front desk and keeps every task moving."},
    {"name": "website", "title": "Website Builder", "tagline": "Your practice site — built, published, maintained."},
    {"name": "blog", "title": "Writer", "tagline": "Honest, cited essays in your voice."},
    {"name": "marketer", "title": "Marketer", "tagline": "Teasers, ads, and reach — never hype."},
    {"name": "strategist", "title": "Strategist", "tagline": "Picks topics people actually search for."},
    {"name": "reviewer", "title": "Reviewer", "tagline": "The honesty gate. Nothing ships past them."},
    {"name": "analytics", "title": "Analyst", "tagline": "Counts what actually happened. Never an estimate."},
    {"name": "distributor", "title": "Distributor", "tagline": "Gets your writing seen — white-hat only."},
]

_LOCK = threading.Lock()
_RUNS: dict[str, dict] = {}
_LOADED = False

_STEP_SYSTEM = (
    "You are {assignee}, one member of Shaula — the AI office staff of a therapy "
    "practice. House rules, non-negotiable: no invented statistics or percentages; "
    'no "proven / guaranteed / clinically proven"; no "studies show"; no invented '
    'testimonials; no "cure / miracle"; no "#1 / best / world-class". If you lack '
    "a real source, say so and omit the claim. Return ONLY the deliverable text "
    "for THIS task — no preamble, no meta-commentary."
)


# ── manifest / plans ─────────────────────────────────────────────────────────
def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def capabilities() -> list[dict]:
    return list(_manifest()["capabilities"])


def roster() -> dict:
    """{staff:[…]} — same shape the hosted svc serves at /v1/roster."""
    caps = capabilities()
    staff = []
    for m in OFFICE_STAFF:
        mine = [{"id": c["id"], "label": c["label"], "description": c["description"]}
                for c in caps if m["name"] in (c.get("staff") or [])]
        staff.append({**m, "capabilities": mine})
    return {"ok": True, "staff": staff, "local": True}


def _business_name() -> str:
    prof = _state_dir() / "practice.json"
    try:
        return json.loads(prof.read_text(encoding="utf-8")).get("business_name") or "your practice"
    except Exception:
        return "your practice"


def _plan(cap: dict, topic: str) -> list[dict]:
    """Template → ordered executable steps (the svc's step_plan semantics:
    array order; the one topic fills every declared variable)."""
    tmpl_path = REPO / "workflows" / cap["template"]
    tmpl = WB.load_template_file(str(tmpl_path))
    WB.validate(tmpl)  # allow-list + PHI gate + honesty lint + acyclic — always
    # The svc's plan_for semantics: the therapist's one answer fills every
    # content slot the template declares; project/practice slots get the
    # practice's own name.
    topic_value = (topic or "").strip()[:200] or cap["label"]
    named = {"project": _business_name(), "practice": _business_name(), "domain": ""}
    variables = {n: named.get(n, topic_value) for n in tmpl.variables}
    plan = WB.build_plan(tmpl, variables)
    steps = []
    for p in plan:
        body = p.payload["body"]
        steps.append({
            "ref": p.ref,
            "assignee": p.payload["assignee"],
            "title": p.payload["title"],
            "instruction": body,
            "isReview": p.payload["assignee"] == "reviewer",
            "isGate": bool(p.payload.get("triage")),
            "status": "pending",
            "output": "",
        })
    return steps


# ── persistence ──────────────────────────────────────────────────────────────
def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    try:
        for r in json.loads(_runs_file().read_text(encoding="utf-8")):
            # A run that was mid-flight when the app quit is honestly failed,
            # never silently resumed as if nothing happened.
            if r.get("status") in ("queued", "working"):
                r["status"] = "failed"
                r["error"] = "interrupted — the app closed while this was running; run it again"
            _RUNS[r["id"]] = r
    except Exception:
        pass


def _save() -> None:
    try:
        _state_dir().mkdir(parents=True, exist_ok=True)
        _runs_file().write_text(json.dumps(list(_RUNS.values()), ensure_ascii=False),
                             encoding="utf-8")
    except Exception:
        pass  # the board is a convenience cache; never crash the office over it


# ── execution ────────────────────────────────────────────────────────────────
def _model_step(assignee: str, instruction: str, handoffs: list[tuple[str, str]]) -> str | None:
    user = instruction
    if handoffs:
        user += "\n\n=== WORK FROM EARLIER STEPS ===\n" + "\n\n".join(
            f"--- {t} ---\n{o}" for t, o in handoffs)
    return router._call_ollama(_STEP_SYSTEM.format(assignee=assignee), user, 1400)


def _execute(rid: str) -> None:
    run = _RUNS[rid]
    run["status"] = "working"
    _save()
    handoffs: list[tuple[str, str]] = []
    for i, step in enumerate(run["steps"]):
        run["currentStep"] = step["title"]
        run["stepsDone"] = i
        _save()
        if step["isReview"] or step["isGate"]:
            # THE HUMAN GATE. Every prior output already passed the linter;
            # the run parks here until the therapist clicks approve.
            step["status"] = "waiting"
            step["output"] = ("Waiting for you — this step belongs to a human. "
                              "Review the work above and approve or reject.")
            run["status"] = "needs_approval"
            _save()
            return
        step["status"] = "working"
        _save()
        text = _model_step(step["assignee"], step["instruction"], handoffs)
        if not text:
            step["status"] = "failed"
            run["status"] = "failed"
            run["error"] = "the local model did not answer — is Ollama running?"
            _save()
            return
        hits = banned.lint(text)
        if hits:
            # THE MOAT: an affirmative banned claim kills the step, visibly.
            step["status"] = "failed"
            step["output"] = ("Refused by the honesty gate — the draft contained "
                              "a claim Shaula will not ship: " + ", ".join(hits))
            run["status"] = "failed"
            run["error"] = "honesty gate"
            _save()
            return
        step["status"] = "done"
        step["output"] = text
        handoffs.append((step["title"], text))
        _save()
    run["status"] = "needs_approval" if any(s["isReview"] or s["isGate"] for s in run["steps"]) \
        else "approved"
    run["stepsDone"] = len(run["steps"])
    _save()


def _website_launch_steps() -> list[dict]:
    return [
        {"ref": "build", "assignee": "website", "title": "Build the practice site",
         "instruction": "deterministic engine build", "isReview": False, "isGate": True,
         "status": "waiting",
         "output": "Waiting for you — approve and the office builds and stages your site "
                   "with the deterministic honesty engine (no model writes your pages)."},
    ]


def create_run(capability: str, topic: str = "", *, idempotency_key: str = "") -> dict:
    _load()
    cap = next((c for c in capabilities() if c["id"] == capability), None)
    if not cap:
        return {"ok": False, "error": "unknown", "message": f"No such capability: {capability}"}
    rid = "r_" + uuid.uuid4().hex[:10]
    try:
        steps = _website_launch_steps() if capability == "website-launch" else _plan(cap, topic)
    except WB.WorkflowError as exc:
        return {"ok": False, "error": "invalid_template", "message": str(exc)}
    run = {
        "id": rid, "capability": capability, "topic": (topic or "")[:200],
        "status": "queued", "steps": steps, "stepsDone": 0,
        "stepsTotal": len(steps), "currentStep": steps[0]["title"] if steps else "",
        "created": time.time(), "local": True,
    }
    with _LOCK:
        _RUNS[rid] = run
        _save()
    if capability != "website-launch":
        threading.Thread(target=_execute, args=(rid,), daemon=True).start()
    else:
        run["status"] = "needs_approval"
        _save()
    return {"ok": True, "runId": rid, "status": run["status"]}


def list_runs() -> dict:
    _load()
    runs = sorted(_RUNS.values(), key=lambda r: r.get("created", 0), reverse=True)
    slim = [{k: r.get(k) for k in ("id", "capability", "topic", "status", "stepsDone",
                                   "stepsTotal", "currentStep")} for r in runs]
    return {"ok": True, "runs": slim,
            "needsApproval": sum(1 for r in runs if r.get("status") == "needs_approval"),
            "newInquiries": 0, "local": True}


def get_run(rid: str) -> dict:
    _load()
    run = _RUNS.get((rid or "").strip())
    if not run:
        return {"ok": False, "error": "unknown", "message": "No run with that id."}
    return {"ok": True, "run": run}


def approve_run(rid: str, *, note: str = "") -> dict:
    _load()
    run = _RUNS.get((rid or "").strip())
    if not run:
        return {"ok": False, "error": "unknown", "message": "No run with that id."}
    if run["status"] != "needs_approval":
        return {"ok": False, "error": "not_waiting", "message": "Nothing here is waiting for approval."}
    if run["capability"] == "website-launch":
        # The office performs the deterministic build AFTER the okay (D-FreeStaff:
        # a worker never deploys; here "publish" is a local staged site).
        try:
            import build_practice as BP
            import pipeline as P
            res = P.build_site(BP.DEMO_SURVEY, sites_dir=str(_sites_dir()))
            run["previewUrl"] = f"/sites/{res['slug']}/index.html"
            run["steps"][-1].update(status="done",
                                    output=f"Site built and staged at {run['previewUrl']}")
        except Exception as exc:  # honest failure, never a silent green
            run["status"] = "failed"
            run["error"] = f"site build failed: {exc}"
            _save()
            return {"ok": False, "error": "build", "message": run["error"]}
    else:
        for s in run["steps"]:
            if s["status"] == "waiting":
                s["status"] = "done"
                s["output"] = "Approved by the clinician." + (f" Note: {note[:500]}" if note else "")
    run["status"] = "approved"
    run["stepsDone"] = len(run["steps"])
    _save()
    return {"ok": True, "status": "approved", "previewUrl": run.get("previewUrl")}


def reject_run(rid: str, *, note: str = "") -> dict:
    _load()
    run = _RUNS.get((rid or "").strip())
    if not run:
        return {"ok": False, "error": "unknown", "message": "No run with that id."}
    run["status"] = "rejected"
    if note:
        run["rejectNote"] = note[:500]
    _save()
    return {"ok": True, "status": "rejected"}
