"""capabilities — the manifest is the product surface (D-FreeStaff).

workflows/CAPABILITY_MANIFEST.json (truthed 2026-07-05: 17 capabilities, all
with real templates) drives everything: the staff menus the apps render, and
the step plans the runner executes. NEVER a flow editor — therapists pick a
capability off a staff member's "things I can do" menu; the DAG underneath
is ours.

The runner equivalence: every template step is PURE TEXT (the office design
— "the staff return … as their kanban_complete summaries"), so one generic
Gemini executor runs ANY capability: each step's description becomes the
instruction, parent handoffs become the context, the reviewer step becomes
a lint + verdict gate. website-launch additionally triggers the
deterministic build + publish AFTER the human okay (the office performs the
build — never a worker).
"""
from __future__ import annotations

import json
import re
import sys
from functools import lru_cache

from . import config

if str(config.REPO) not in sys.path:
    sys.path.insert(0, str(config.REPO))

MANIFEST_PATH = config.REPO / "workflows" / "CAPABILITY_MANIFEST.json"
TEMPLATES_DIR = config.REPO / "workflows" / "templates"

# Staff the apps may show (the 8 no-PHI office roles). The 6 PHI roles are
# NOT served by this service, ever — they live inside the clinical perimeter.
#
# Roster honesty (UX audit SH-F20): every member must point at something REAL.
# Members without run capabilities carry a `surface` — an existing read
# surface the apps already poll (the Office Manager fronts the wave-1 inquiry
# inbox; the Analyst fronts GET /v1/practices/{pid}/stats — real counts, never
# an estimate). No member may render as a dead card or an unfulfillable promise.
OFFICE_STAFF = [
    {"name": "orchestrator", "title": "Office Manager",
     "tagline": "Runs the front desk — every website inquiry lands in this inbox.",
     "surface": {
         "kind": "inquiries",
         "title": "Front-desk inbox",
         "description": "Consult inquiries from your website, delivered and badged the moment they arrive.",
     }},
    {"name": "website", "title": "Website Builder", "tagline": "Your practice site — built, published, maintained."},
    {"name": "blog", "title": "Writer", "tagline": "Honest, cited essays in your voice."},
    {"name": "marketer", "title": "Marketer", "tagline": "Teasers, ads, and reach — never hype."},
    {"name": "strategist", "title": "Strategist", "tagline": "Picks topics people actually search for."},
    {"name": "reviewer", "title": "Reviewer", "tagline": "The honesty gate. Nothing ships past them."},
    {"name": "analytics", "title": "Analyst",
     "tagline": "Counts what actually happened — runs, essays, inquiries. Never an estimate.",
     "surface": {
         "kind": "stats",
         "title": "Office report",
         "description": "Real counts only: runs finished, essays live, inquiries received. Silent when there is nothing to report.",
     }},
    {"name": "distributor", "title": "Distributor", "tagline": "Gets your writing seen — white-hat only."},
]


@lru_cache(maxsize=1)
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def capabilities() -> list[dict]:
    return list(manifest()["capabilities"])


def capability(cap_id: str) -> dict | None:
    return next((c for c in capabilities() if c["id"] == cap_id), None)


@lru_cache(maxsize=32)
def template_for(cap_id: str) -> dict | None:
    cap = capability(cap_id)
    if not cap or not cap.get("template"):
        return None
    path = config.REPO / "workflows" / cap["template"]
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def substitute(text: str, variables: dict[str, str]) -> str:
    out = text or ""
    for key, val in variables.items():
        out = out.replace("{" + key + "}", str(val))
    return out


# Template-variable debris ("{seed}" in an inbox title) is a contract bug,
# never something a therapist should read (UX audit SH-F11). After
# substitution, NO user-visible plan string may carry an unresolved
# {placeholder}; plan_for() maps every variable a template declares, so a hit
# here means an UNDECLARED variable in the template — fail loudly at plan
# time, before a model call or an inbox card exists.
UNRESOLVED_RE = re.compile(r"\{[a-z][a-z0-9_]*\}")


class TemplateVariableError(ValueError):
    """A template step still carries an unresolved {placeholder}."""


def _is_human_gate(raw: dict) -> bool:
    """A template step that belongs to a HUMAN, never the model (SH-F15).

    The manifest's own marker is the ``triage: true`` flag every "Human
    gate — clinician …" step carries (verified across all 17 templates:
    exactly the 13 gate steps, nothing else). The title prefix is the
    belt-and-suspenders fallback so a future template that forgets the
    flag still cannot have its gate executed by the AI.
    """
    return bool(raw.get("triage")) or (raw.get("title") or "").lower().startswith("human gate")


def step_plan(cap_id: str, variables: dict[str, str]) -> list[dict]:
    """Template → ordered executable steps (sequential = the DAG order the
    builder validated; templates here are linear chains by construction).

    Raises TemplateVariableError if any step still carries an unresolved
    {placeholder} after substitution (SH-F11 — template debris must never
    reach the inbox or the model)."""
    tmpl = template_for(cap_id)
    if tmpl is None:
        raise KeyError(f"unknown capability: {cap_id}")
    steps = []
    for i, raw in enumerate(tmpl.get("steps", [])):
        title = substitute(raw.get("title", f"Step {i + 1}"), variables)
        instruction = substitute(raw.get("description", ""), variables)
        leftover = sorted(
            set(UNRESOLVED_RE.findall(title) + UNRESOLVED_RE.findall(instruction))
        )
        if leftover:
            raise TemplateVariableError(
                f"{cap_id} step {i + 1}: unresolved template variable(s) "
                f"{', '.join(leftover)} — declare them in the template's "
                "'variables' list"
            )
        steps.append(
            {
                "index": i,
                # The template's own step id ('draft', 'review', …) rides the
                # plan so downstream consumers can select by SEMANTICS, not by
                # sniffing titles (SH-F10: the publish picker keys off this).
                "ref": raw.get("ref", ""),
                "assignee": raw.get("assignee", "orchestrator"),
                "title": title,
                "instruction": instruction,
                # The reviewer's step is the honesty gate — it parks the run
                # at needs_approval instead of producing more copy.
                "isReview": raw.get("assignee") == "reviewer",
                # A human-gate step STOPS the run and waits for the clinician
                # — the runner must never send it to the model (SH-F15).
                "isGate": _is_human_gate(raw),
                "status": "pending",
                "output": "",
            }
        )
    return steps


def website_launch_steps() -> list[dict]:
    """The deterministic website-launch plan — the office performs the
    build, never a worker (no template/model steps involved)."""
    return [
        {"index": 0, "ref": "build", "assignee": "website",
         "title": "Build the practice site",
         "instruction": "deterministic engine build", "isReview": False,
         "isGate": False, "status": "pending", "output": ""},
        {"index": 1, "ref": "preview", "assignee": "website",
         "title": "Stage the preview",
         "instruction": "publish preview to the sites bucket", "isReview": False,
         "isGate": False, "status": "pending", "output": ""},
    ]


def plan_for(cap_id: str, topic: str, state: dict) -> list[dict]:
    """One place that turns (capability, topic, practice state) into steps —
    shared by run creation and the revision loop so the two can never drift.

    Variable mapping (UX audit SH-F11): the single `topic` field the apps send
    fills EVERY content slot the template declares (seed, edition, page_type,
    purpose, recipient, campaign, article_url, …) — declared-but-unmapped
    variables previously passed through verbatim, so the inbox rendered
    "Pick topic + angle: {seed}" and the model received raw placeholders."""
    if cap_id == "website-launch":
        return website_launch_steps()
    profile = state.get("profile") or {}
    cap = capability(cap_id)
    topic_value = (topic or "")[:200] or (cap["label"] if cap else cap_id)
    variables = {
        "topic": topic_value,
        "project": profile.get("business_name", "the practice"),
        "practice": profile.get("business_name", "the practice"),
        "domain": state.get("siteUrl", ""),
    }
    tmpl = template_for(cap_id) or {}
    for declared in tmpl.get("variables", []):
        # The therapist's one answer lands in the template's own slot name.
        variables.setdefault(declared, topic_value)
    return step_plan(cap_id, variables)


def staff_menu() -> list[dict]:
    """Roster + per-staff capability menus — the discovery surface the apps
    render (competitor pattern: capabilities live INSIDE the employees)."""
    caps = capabilities()
    roster = []
    for member in OFFICE_STAFF:
        mine = [
            {"id": c["id"], "label": c["label"], "description": c["description"]}
            for c in caps
            if member["name"] in (c.get("staff") or [])
        ]
        roster.append({**member, "capabilities": mine})
    return roster
