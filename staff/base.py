"""staff/base.py — the AI-staff engine seam.

A common contract for every "staff member" the box will run (blog, front desk,
customer service, marketer, ...). A `StaffTask` turns a practice dict (exactly
what engine/build_practice.py produces) into a `StaffResult`: a structured
payload + rendered markdown + a mandatory disclaimer.

THE HONESTY CONTRACT (enforced here, once, for every staff member):
  * `_walk_strings` recursively visits every string in the payload, then the
    rendered markdown and the disclaimer, and runs each through
    engine/generate.py `lint` — the SINGLE source of truth for banned claims
    (percentages, "proven", "guarantee", "studies show", testimonials, "cure",
    "#1", "best therapist", "world-class", ...). It is the same gate the website
    builder uses.
  * Any hit raises `StaffHonestyError` and NOTHING is returned. A half-honest
    artifact can never leave this module — the same spine as the website engine.

THE LLM SEAM (D3):
  * `synthesize()` is a no-op pass-through today. When an on-device model
    (Ollama) is wired, a staff member may override it to enrich the deterministic
    floor. The floor is always the verified baseline, and `run()` lints AFTER
    synthesis — so a model can never smuggle a banned claim past the gate.

Pure stdlib. No network, no LLM dependency, no PHI.
"""
from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator

# Canonical banned-claim linter (single source of truth, shared with the website
# engine). Add the engine dir to sys.path so this imports whether we are launched
# by office.py, imported as a package, or run as `python3 -m staff.blog`.
_ENGINE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine"
)
if _ENGINE not in sys.path:
    sys.path.insert(0, _ENGINE)
import generate as G  # noqa: E402  (the honesty linter — engine/generate.py)


class StaffHonestyError(ValueError):
    """Raised when a staff member's output contains a banned marketing claim.

    `.problems` is a list of ``(json_path, [banned_patterns])`` so the caller can
    show exactly what tripped and where. Mirrors build_practice.HonestyError.
    """

    def __init__(self, problems: list[tuple[str, list[str]]]):
        self.problems = problems
        lines = [f"  {path}: {pats}" for path, pats in problems]
        super().__init__("dishonest claim(s) in staff output:\n" + "\n".join(lines))


@dataclass
class StaffResult:
    """The validated output of one staff task."""

    task: str                        # staff member id, e.g. "blog"
    title: str                       # human title of the artifact
    payload: dict                    # structured, machine-usable result
    markdown: str                    # rendered, human-readable artifact
    disclaimer: str                  # mandatory legal/clinical footer
    produces_phi: bool = False       # True only for staff that touch client data
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "title": self.title,
            "payload": self.payload,
            "markdown": self.markdown,
            "disclaimer": self.disclaimer,
            "produces_phi": self.produces_phi,
            "meta": self.meta,
        }


def _walk_strings(obj, path: str = "payload") -> Iterator[tuple[str, str]]:
    """Yield ``(json_path, string)`` for every string in a nested structure.

    Recurses dicts, lists, and tuples. Numbers/bools/None carry nothing to lint.
    Keys are not exempted — even ``_``-prefixed scaffolding keys are linted,
    because they can surface to the user; the path just records where a hit came
    from.
    """
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_strings(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from _walk_strings(v, f"{path}[{i}]")


class StaffTask(ABC):
    """Base class for every AI-staff member.

    Subclasses implement the deterministic, honest baseline (`floor`), the
    markdown rendering (`render`), and the mandatory `disclaimer`. The lifecycle
    in `run()` is fixed and identical for every member:

        floor -> (optional) synthesize -> render -> HONESTY GATE -> StaffResult
    """

    id: str = "staff"
    title: str = "Staff task"
    produces_phi: bool = False

    # --- subclass surface ------------------------------------------------- #
    @abstractmethod
    def floor(self, practice: dict, **inputs) -> dict:
        """Deterministic, no-LLM payload built from the practice dict. Honest by
        construction — the same discipline as engine/generate.py."""

    @abstractmethod
    def render(self, practice: dict, payload: dict) -> str:
        """Render the structured payload to human-readable markdown."""

    @abstractmethod
    def disclaimer(self, practice: dict) -> str:
        """The mandatory legal/clinical disclaimer for this artifact."""

    def synthesize(self, practice: dict, payload: dict, **inputs) -> dict:
        """LLM-enrichment seam (D3). No-op by default: returns the deterministic
        payload unchanged. A future on-device model may override this to enrich
        the floor — but `run()` lints AFTER synthesize, so it can never introduce
        a banned claim. Today there is no LLM in the loop and this never runs
        unless ``use_ollama=True`` is explicitly passed."""
        return payload

    # --- fixed lifecycle -------------------------------------------------- #
    def run(self, practice: dict, *, use_ollama: bool = False, **inputs) -> StaffResult:
        if not isinstance(practice, dict) or not practice.get("business_name"):
            raise ValueError(
                "staff task requires a built practice dict (run build_practice first)"
            )

        payload = self.floor(practice, **inputs)
        if use_ollama:
            payload = self.synthesize(practice, payload, **inputs)

        markdown = self.render(practice, payload)
        disclaimer = self.disclaimer(practice)

        # Honesty gate — lint payload + markdown + disclaimer. Any hit aborts and
        # nothing is returned.
        problems: list[tuple[str, list[str]]] = []
        for pth, s in _walk_strings(payload, "payload"):
            hits = G.lint(s)
            if hits:
                problems.append((pth, hits))
        for label, s in (("markdown", markdown), ("disclaimer", disclaimer)):
            hits = G.lint(s)
            if hits:
                problems.append((label, hits))
        if problems:
            raise StaffHonestyError(problems)

        return StaffResult(
            task=self.id,
            title=self.title,
            payload=payload,
            markdown=markdown,
            disclaimer=disclaimer,
            produces_phi=self.produces_phi,
            meta={
                "use_ollama": bool(use_ollama),
                "engine": "deterministic-floor",
            },
        )
