"""Shaula workflows — no-code template → Hermes kanban task-graph (D14).

Public surface:
  load_template / load_template_file  — dict|file → WorkflowTemplate
  validate                            — guardrail check (raises WorkflowError)
  build_plan                          — ordered, network-free task payloads
  KanbanEmitter / instantiate         — emit a plan to the live board
  VETTED_PROFILES / PHI_PROFILES      — the allow-list + PHI gate
  WorkflowError                       — carries `.violations`
"""

from .builder import (  # noqa: F401
    HONESTY_PREAMBLE,
    PHI_PROFILES,
    PRIORITY_MAP,
    VETTED_PROFILES,
    BoardSpec,
    KanbanEmitter,
    PlannedTask,
    WorkflowError,
    WorkflowStep,
    WorkflowTemplate,
    build_plan,
    instantiate,
    load_template,
    load_template_file,
    topo_sort,
    validate,
)

__all__ = [
    "HONESTY_PREAMBLE",
    "PHI_PROFILES",
    "PRIORITY_MAP",
    "VETTED_PROFILES",
    "BoardSpec",
    "KanbanEmitter",
    "PlannedTask",
    "WorkflowError",
    "WorkflowStep",
    "WorkflowTemplate",
    "build_plan",
    "instantiate",
    "load_template",
    "load_template_file",
    "topo_sort",
    "validate",
]
