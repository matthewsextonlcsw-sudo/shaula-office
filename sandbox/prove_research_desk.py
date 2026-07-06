#!/usr/bin/env python3
"""prove_research_desk — Option C real-model end-to-end proof (SYNTHETIC).

Runs the research-engine capability two ways on a LOCAL Ollama model and writes
a side-by-side proof artifact:

  1) the Shaula->Hermes task-graph (scope -> findings -> brief -> review) via
     workflows.local_executor (DAG handoffs + the real honesty gate per step);
  2) the 1-call baseline (one shot) it must beat.

Both pass through the same real honesty gate (svc.gemini.lint_gate). Zero cost,
zero egress, no PHI — the topic is synthetic and the model is local.

Run:  python3 sandbox/prove_research_desk.py
"""
from __future__ import annotations

import os
import re
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from workflows import local_executor as LE  # noqa: E402
from svc.gemini import BrainError  # noqa: E402

TOPIC = os.environ.get(
    "PROVE_TOPIC", "supporting adult clients with sleep difficulties and anxiety"
)
PROJECT = "Cedar & Sage Therapy (synthetic)"
TEMPLATE = os.path.join(_ROOT, "workflows", "templates", "research-engine.json")


def _structure(text: str) -> dict:
    t = (text or "").lower()
    # Count confidence tags written either bracketed [established] or parenthesised
    # (established) — small models drift between the two; both are valid.
    tags = len(re.findall(r"[\[(](established|commonly described|unverified)[\])]", t))
    return {
        "words": len((text or "").split()),
        "confidence_tags": tags,
        "has_checklist": "checklist" in t,
        "has_disclaimer": any(
            p in t for p in ("not clinical advice", "informational background", "not a substitute")
        ),
        "has_open_questions": any(
            p in t for p in ("open question", "could not verify", "unanswered", "needs a", "literature search")
        ),
    }


def main() -> int:
    model = LE.OllamaModel()
    print(f"# Research Desk — Option C proof (model={model.model}, local Ollama)\n")
    print(f"Topic (synthetic): {TOPIC}\nPractice: {PROJECT}\n")

    print("== Running Shaula->Hermes task-graph ==", flush=True)
    t0 = time.time()
    run = LE.run_template_file(TEMPLATE, {"topic": TOPIC, "project": PROJECT}, model)
    graph_secs = time.time() - t0
    print(
        f"status={run.status}  "
        f"steps={[(s.ref, s.status, round(s.seconds, 1)) for s in run.steps]}  "
        f"total={round(graph_secs, 1)}s"
    )
    print(f"review gate: {run.review_reason or '(n/a)'}")
    if run.status == "honesty_failed":
        print(f"honesty stop at {run.honesty.get('atRef')}: {run.honesty.get('detail')}")
    print()

    print("== Running 1-call baseline ==", flush=True)
    t0 = time.time()
    try:
        baseline = LE.one_call_baseline(TOPIC, PROJECT, model)
        base_status = "ok"
    except BrainError as exc:
        baseline = ""
        base_status = f"honesty_failed:{exc.detail}"
    base_secs = time.time() - t0
    print(f"status={base_status}  total={round(base_secs, 1)}s\n")

    gs = _structure(run.deliverable)
    bs = _structure(baseline)
    print("== STRUCTURE (heuristic) ==")
    print(f"{'metric':20} {'task-graph':>12} {'baseline':>12}")
    for k in ("words", "confidence_tags", "has_checklist", "has_disclaimer", "has_open_questions"):
        print(f"{k:20} {str(gs.get(k)):>12} {str(bs.get(k)):>12}")

    out = os.path.join(os.path.dirname(__file__), "research_desk_proof_output.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("# Research Desk — Option C proof output\n\n")
        f.write(f"- model: `{model.model}` (local Ollama, zero-egress, synthetic)\n")
        f.write(f"- topic (synthetic): {TOPIC}\n- practice: {PROJECT}\n")
        f.write(
            f"- task-graph: **{run.status}** in {round(graph_secs, 1)}s · "
            f"baseline: **{base_status}** in {round(base_secs, 1)}s\n"
        )
        f.write("- honesty gate: real `lint_gate` applied to every step\n\n")
        f.write(f"- structure (task-graph): {gs}\n- structure (baseline): {bs}\n\n")
        f.write("## Task-graph steps\n\n")
        for s in run.steps:
            f.write(f"### {s.ref} — {s.assignee} ({s.status}, {round(s.seconds, 1)}s)\n\n{s.output}\n\n")
        f.write(f"## Task-graph deliverable (the brief)\n\n{run.deliverable or '(none)'}\n\n")
        f.write(f"## 1-call baseline ({base_status})\n\n{baseline or '(honesty-failed / none)'}\n")
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
