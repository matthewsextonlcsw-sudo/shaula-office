#!/usr/bin/env python3
"""prove_authoring — therapist self-serve authoring, real-model proof (SYNTHETIC).

A therapist sentence -> Shaula drafts a vetted workflow -> kanban task-graph + a
honesty-gated skill, on a LOCAL Ollama model (zero cost, zero egress, no PHI).
Proves the full authoring path; the safety wall (vetted assignees + honesty gate)
is enforced regardless of what the untrusted model returns.

Run:  python3 sandbox/prove_authoring.py
"""
from __future__ import annotations

import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from svc.gemini import BrainError  # noqa: E402
from workflows import author as A  # noqa: E402
from workflows import local_executor as LE  # noqa: E402
from workflows.builder import VETTED_PROFILES, build_plan  # noqa: E402

REQUEST = os.environ.get(
    "PROVE_REQUEST",
    "I want a monthly campaign to reach local primary-care doctors and invite referrals",
)
PROJECT = "Cedar & Sage Therapy (synthetic)"


def main() -> int:
    model = LE.OllamaModel()
    print(f"# Therapist authoring proof (model={model.model}, local Ollama)\n")
    print(f'Therapist says: "{REQUEST}"\nPractice: {PROJECT}\n')

    print("== Drafting workflow (plain language -> vetted template) ==", flush=True)
    t0 = time.time()
    try:
        tmpl = A.draft_workflow(REQUEST, PROJECT, model, max_repair=2)
    except A.AuthoringError as exc:
        print(f"AUTHORING REFUSED (safety wall held): {exc}")
        print(f"violations={exc.violations}")
        return 0
    secs = time.time() - t0
    print(f"name={tmpl.name}  steps={len(tmpl.steps)}  in {round(secs, 1)}s")
    for s in tmpl.steps:
        print(f"  - {s.ref:12} [{s.assignee}] {s.title}")
    vetted_ok = all(s.assignee in VETTED_PROFILES for s in tmpl.steps)
    print(f"all assignees vetted: {vetted_ok}\n")

    print("== Building kanban task-graph ==")
    plan = build_plan(tmpl, {}, allow_phi=False)
    for p in plan:
        print(f"  task {p.ref:12} assignee={p.payload['assignee']:12} parents={list(p.dep_refs)}")
    print()

    print("== Drafting a skill (honesty-gated) ==", flush=True)
    skill = None
    try:
        skill = A.draft_skill(f"staff guidance for: {REQUEST}", PROJECT, model)
        print(f"skill: {skill['name']} — {skill['description']}")
        print(skill["body"][:400])
    except BrainError as exc:
        print(f"skill honesty-gated: {exc.category} {exc.detail}")
    except A.AuthoringError as exc:
        print(f"skill draft issue: {exc}")

    out = os.path.join(os.path.dirname(__file__), "authoring_proof_output.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("# Therapist authoring proof output\n\n")
        f.write(f"- model: `{model.model}` (local Ollama, zero-egress, synthetic)\n")
        f.write(f'- therapist request: "{REQUEST}"\n')
        f.write(f"- generated workflow: **{tmpl.name}** ({len(tmpl.steps)} steps); all assignees vetted: {vetted_ok}\n\n")
        f.write("## Generated workflow steps\n\n")
        for s in tmpl.steps:
            gate = " (review gate)" if s.requires_review else ""
            f.write(f"### {s.ref} — {s.assignee}{gate}\n\n**{s.title}**\n\n{s.description}\n\n")
        f.write("## Kanban task-graph (parents = DAG edges)\n\n")
        for p in plan:
            f.write(f"- `{p.ref}` -> {p.payload['assignee']}, parents={list(p.dep_refs)}\n")
        if skill:
            f.write(f"\n## Drafted skill: {skill['name']}\n\n{skill['description']}\n\n{skill['body']}\n")
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
