#!/usr/bin/env python3
"""Tests for the Shaula workflow builder — every guardrail, zero network.

Run:  python3 -m unittest workflows.test_builder -v
  or: python3 workflows/test_builder.py
"""

from __future__ import annotations

import os
import sys
import unittest

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workflows import builder as B  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
_SEED = os.path.join(_HERE, "templates", "weekly-blog.json")
_GROWTH = os.path.join(_HERE, "templates", "growth-engine.json")
_DISTRO = os.path.join(_HERE, "templates", "distribution-engine.json")
_COPY = os.path.join(_HERE, "templates", "copy-engine.json")
_DECK = os.path.join(_HERE, "templates", "deck-engine.json")
_PROPOSAL = os.path.join(_HERE, "templates", "proposal-engine.json")
_AD = os.path.join(_HERE, "templates", "ad-creative-engine.json")
_NEWSLETTER = os.path.join(_HERE, "templates", "newsletter-engine.json")
_RESEARCH = os.path.join(_HERE, "templates", "research-engine.json")


def _tmpl(**over):
    """A minimal valid no-PHI template, overridable per test."""
    base = {
        "name": "t",
        "description": "d",
        "variables": [],
        "steps": [
            {"ref": "a", "title": "A", "assignee": "blog", "description": "do a"},
            {"ref": "b", "title": "B", "assignee": "reviewer",
             "dependencies": ["a"], "description": "do b"},
        ],
    }
    base.update(over)
    return B.load_template(base)


class GroundTruth(unittest.TestCase):
    def test_vetted_profiles(self):
        self.assertEqual(len(B.VETTED_PROFILES), 15)
        self.assertIn("orchestrator", B.VETTED_PROFILES)
        self.assertIn("scribe", B.VETTED_PROFILES)
        # the OpenGrowth content-engine roles (growth-engine / distribution-engine)
        self.assertIn("strategist", B.VETTED_PROFILES)
        self.assertIn("distributor", B.VETTED_PROFILES)
        # Telegram gateway persona
        self.assertIn("sarah", B.VETTED_PROFILES)

    def test_phi_profiles_subset_of_vetted(self):
        self.assertTrue(B.PHI_PROFILES <= B.VETTED_PROFILES)
        self.assertEqual(len(B.PHI_PROFILES), 6)


class Loading(unittest.TestCase):
    def test_missing_steps_rejected(self):
        with self.assertRaises(B.WorkflowError):
            B.load_template({"name": "x"})

    def test_empty_steps_rejected(self):
        with self.assertRaises(B.WorkflowError):
            B.load_template({"name": "x", "steps": []})

    def test_step_missing_required_field(self):
        with self.assertRaises(B.WorkflowError):
            B.load_template({"name": "x", "steps": [{"ref": "a", "title": "A"}]})


class Validation(unittest.TestCase):
    def test_valid_template_passes(self):
        B.validate(_tmpl())  # no raise

    def test_unknown_assignee_rejected(self):
        with self.assertRaises(B.WorkflowError) as cm:
            B.validate(_tmpl(steps=[
                {"ref": "a", "title": "A", "assignee": "research-agent"}]))
        self.assertTrue(any("not a vetted profile" in v for v in cm.exception.violations))

    def test_duplicate_ref_rejected(self):
        with self.assertRaises(B.WorkflowError) as cm:
            B.validate(_tmpl(steps=[
                {"ref": "a", "title": "A", "assignee": "blog"},
                {"ref": "a", "title": "A2", "assignee": "reviewer"}]))
        self.assertTrue(any("duplicate" in v for v in cm.exception.violations))

    def test_dangling_dependency_rejected(self):
        with self.assertRaises(B.WorkflowError) as cm:
            B.validate(_tmpl(steps=[
                {"ref": "a", "title": "A", "assignee": "blog",
                 "dependencies": ["ghost"]}]))
        self.assertTrue(any("unknown ref" in v for v in cm.exception.violations))

    def test_bad_priority_rejected(self):
        with self.assertRaises(B.WorkflowError) as cm:
            B.validate(_tmpl(steps=[
                {"ref": "a", "title": "A", "assignee": "blog", "priority": "asap"}]))
        self.assertTrue(any("priority" in v for v in cm.exception.violations))

    def test_cycle_detected(self):
        with self.assertRaises(B.WorkflowError) as cm:
            B.validate(_tmpl(steps=[
                {"ref": "a", "title": "A", "assignee": "blog", "dependencies": ["b"]},
                {"ref": "b", "title": "B", "assignee": "reviewer", "dependencies": ["a"]}]))
        self.assertTrue(any("cycle" in v for v in cm.exception.violations))

    def test_honesty_lint_blocks_banned_claim(self):
        with self.assertRaises(B.WorkflowError) as cm:
            B.validate(_tmpl(steps=[
                {"ref": "a", "title": "A", "assignee": "blog",
                 "description": "Our clinically proven method studies show 95% cure."}]))
        self.assertTrue(any("banned language" in v for v in cm.exception.violations))


class PHIGate(unittest.TestCase):
    def _phi(self, **over):
        base = {
            "name": "p", "allow_phi": False,
            "steps": [{"ref": "n", "title": "Note", "assignee": "scribe"}],
        }
        base.update(over)
        return B.load_template(base)

    def test_phi_rejected_without_optin(self):
        with self.assertRaises(B.WorkflowError) as cm:
            B.validate(self._phi(), allow_phi=False)
        self.assertTrue(any("PHI" in v for v in cm.exception.violations))

    def test_phi_rejected_when_caller_optin_but_template_not(self):
        with self.assertRaises(B.WorkflowError):
            B.validate(self._phi(allow_phi=False), allow_phi=True)

    def test_phi_requires_dir_workspace(self):
        # template opts in, caller opts in, but workspace is scratch → reject
        with self.assertRaises(B.WorkflowError) as cm:
            B.validate(self._phi(allow_phi=True), allow_phi=True)
        self.assertTrue(any("dir workspace" in v for v in cm.exception.violations))

    def test_phi_allowed_with_optin_and_dir(self):
        t = self._phi(allow_phi=True, default_workspace_kind="dir",
                      default_workspace_path="/Volumes/practice")
        B.validate(t, allow_phi=True)  # no raise


class Planning(unittest.TestCase):
    def test_topo_order_parents_first(self):
        plan = B.build_plan(_tmpl())
        refs = [p.ref for p in plan]
        self.assertLess(refs.index("a"), refs.index("b"))

    def test_variable_substitution(self):
        t = _tmpl(variables=["topic"], steps=[
            {"ref": "a", "title": "On {topic}", "assignee": "blog",
             "description": "about {topic}"}])
        plan = B.build_plan(t, {"topic": "sleep"})
        self.assertEqual(plan[0].payload["title"], "On sleep")
        self.assertIn("about sleep", plan[0].payload["body"])

    def test_missing_variable_rejected(self):
        t = _tmpl(variables=["topic"], steps=[
            {"ref": "a", "title": "On {topic}", "assignee": "blog"}])
        with self.assertRaises(B.WorkflowError) as cm:
            B.build_plan(t, {})
        self.assertTrue(any("not provided" in v for v in cm.exception.violations))

    def test_unknown_token_rejected(self):
        t = _tmpl(steps=[
            {"ref": "a", "title": "On {ghost}", "assignee": "blog"}])
        with self.assertRaises(B.WorkflowError) as cm:
            B.build_plan(t, {})
        self.assertTrue(any("unknown variable token" in v for v in cm.exception.violations))

    def test_substituted_banned_claim_rejected(self):
        # A clean template that becomes dirty only after substitution.
        t = _tmpl(variables=["claim"], steps=[
            {"ref": "a", "title": "A", "assignee": "blog",
             "description": "We are {claim}."}])
        with self.assertRaises(B.WorkflowError) as cm:
            B.build_plan(t, {"claim": "the #1 best therapist"})
        self.assertTrue(any("banned language" in v for v in cm.exception.violations))

    def test_priority_mapped_to_int(self):
        t = _tmpl(steps=[
            {"ref": "a", "title": "A", "assignee": "blog", "priority": "high"}])
        self.assertEqual(B.build_plan(t)[0].payload["priority"], 2)

    def test_idempotency_key_format(self):
        plan = B.build_plan(_tmpl(), instance_key="run42")
        self.assertEqual(plan[0].payload["idempotency_key"], "run42:a")

    def test_preamble_injected_and_not_self_linted(self):
        # The preamble names banned phrases as negatives; a clean template must
        # still build (proving we never lint the preamble itself).
        plan = B.build_plan(_tmpl())
        self.assertTrue(plan[0].payload["body"].startswith("[SHAULA HOUSE RULES"))
        self.assertIn("proven", plan[0].payload["body"])  # the negative example

    def test_plan_payload_has_no_parents(self):
        plan = B.build_plan(_tmpl())
        self.assertNotIn("parents", plan[0].payload)
        self.assertEqual(plan[1].dep_refs, ("a",))


class Emitter(unittest.TestCase):
    def test_emit_resolves_parents_in_order(self):
        calls: list[dict] = []
        counter = {"n": 0}

        def fake_transport(path, body):
            counter["n"] += 1
            calls.append({"path": path, "body": body})
            return {"task": {"id": f"id{counter['n']}"}}

        plan = B.build_plan(_tmpl())  # a → b
        em = B.KanbanEmitter(transport=fake_transport)
        created = em.emit(plan)

        self.assertEqual(created[0]["parents"], [])          # a has no parents
        self.assertEqual(created[1]["parents"], ["id1"])     # b depends on a's id
        self.assertEqual(calls[0]["body"]["parents"], [])
        self.assertEqual(calls[1]["body"]["parents"], ["id1"])

    def test_emit_raises_on_missing_id(self):
        em = B.KanbanEmitter(transport=lambda p, b: {"task": {}})
        with self.assertRaises(B.WorkflowError):
            em.emit(B.build_plan(_tmpl()))


class SeedTemplate(unittest.TestCase):
    def test_seed_loads_validates_and_plans(self):
        t = B.load_template_file(_SEED)
        self.assertEqual(t.name, "weekly-blog")
        self.assertFalse(t.allow_phi)
        B.validate(t)
        plan = B.build_plan(t, {"topic": "Sleep and anxiety", "project": "cedar-sage"})
        self.assertEqual(len(plan), 5)
        # review is last (depends on geo + teasers)
        self.assertEqual(plan[-1].ref, "review")
        # every assignee is vetted + no-PHI
        for p in plan:
            self.assertIn(p.payload["assignee"], B.VETTED_PROFILES)
            self.assertNotIn(p.payload["assignee"], B.PHI_PROFILES)


class ContentEngineTemplates(unittest.TestCase):
    """The OpenGrowth growth-engine + distribution-engine ship as real,
    loadable, honesty-clean, no-PHI templates that plan into the expected DAG."""

    def test_growth_engine_loads_validates_and_plans(self):
        t = B.load_template_file(_GROWTH)
        self.assertEqual(t.name, "growth-engine")
        self.assertFalse(t.allow_phi)
        B.validate(t)  # honesty-lint + allow-list + acyclic, no raise
        plan = B.build_plan(t, {"seed": "Sleep and anxiety", "project": "cedar-sage"})
        self.assertEqual(len(plan), 7)
        refs = [p.ref for p in plan]
        # strategist picks the topic first; analytics logs results last
        self.assertEqual(refs[0], "keywords")
        self.assertEqual(refs[-1], "measure")
        self.assertEqual(plan[0].payload["assignee"], "strategist")  # the new role is exercised
        # topo order: keywords → brief → draft → {geo,teasers} → review → measure
        self.assertLess(refs.index("keywords"), refs.index("brief"))
        self.assertLess(refs.index("brief"), refs.index("draft"))
        self.assertLess(refs.index("draft"), refs.index("geo"))
        self.assertLess(refs.index("geo"), refs.index("review"))
        self.assertLess(refs.index("teasers"), refs.index("review"))
        self.assertLess(refs.index("review"), refs.index("measure"))
        for p in plan:
            self.assertIn(p.payload["assignee"], B.VETTED_PROFILES)
            self.assertNotIn(p.payload["assignee"], B.PHI_PROFILES)

    def test_research_engine_loads_validates_and_plans(self):
        t = B.load_template_file(_RESEARCH)
        self.assertEqual(t.name, "research-engine")
        self.assertFalse(t.allow_phi)
        B.validate(t)  # honesty-lint + allow-list + acyclic, no raise
        plan = B.build_plan(t, {"topic": "EMDR for adolescents",
                                "project": "cedar-sage"})
        self.assertEqual(len(plan), 4)
        refs = [p.ref for p in plan]
        # strategist scopes → writer findings → writer brief → reviewer gate
        self.assertEqual(refs, ["scope", "findings", "brief", "review"])
        self.assertEqual(plan[0].payload["assignee"], "strategist")
        self.assertLess(refs.index("scope"), refs.index("findings"))
        self.assertLess(refs.index("findings"), refs.index("brief"))
        self.assertLess(refs.index("brief"), refs.index("review"))
        # the clinician's question substituted into the work
        self.assertIn("EMDR for adolescents", plan[0].payload["title"])
        # the reviewer step carries the human-review marker — never auto-ships
        self.assertIn("REQUIRES HUMAN REVIEW", plan[-1].payload["body"])
        for p in plan:
            self.assertIn(p.payload["assignee"], B.VETTED_PROFILES)
            self.assertNotIn(p.payload["assignee"], B.PHI_PROFILES)

    def test_distribution_engine_loads_validates_and_plans(self):
        t = B.load_template_file(_DISTRO)
        self.assertEqual(t.name, "distribution-engine")
        self.assertFalse(t.allow_phi)
        B.validate(t)
        plan = B.build_plan(t, {"article_url": "https://cedar-sage.example/post",
                                "topic": "Sleep and anxiety", "project": "cedar-sage"})
        self.assertEqual(len(plan), 3)
        refs = [p.ref for p in plan]
        self.assertEqual(refs, ["syndicate", "review", "approve"])
        self.assertEqual(plan[0].payload["assignee"], "distributor")  # the new role is exercised
        # the human-approval gate is a triage step — a person posts; no auto-post
        approve = plan[refs.index("approve")]
        self.assertTrue(approve.payload["triage"])
        for p in plan:
            self.assertIn(p.payload["assignee"], B.VETTED_PROFILES)
            self.assertNotIn(p.payload["assignee"], B.PHI_PROFILES)


class NewTaskFields(unittest.TestCase):
    def test_triage_maps(self):
        t = _tmpl(steps=[{"ref": "a", "title": "A", "assignee": "blog", "triage": True}])
        self.assertTrue(B.build_plan(t)[0].payload["triage"])

    def test_triage_absent_by_default(self):
        self.assertNotIn("triage", B.build_plan(_tmpl())[0].payload)

    def test_max_runtime_maps(self):
        t = _tmpl(steps=[{"ref": "a", "title": "A", "assignee": "blog",
                          "max_runtime_seconds": 900}])
        self.assertEqual(B.build_plan(t)[0].payload["max_runtime_seconds"], 900)

    def test_max_runtime_rejects_nonpositive(self):
        for bad in (0, -5):
            with self.assertRaises(B.WorkflowError):
                B.validate(_tmpl(steps=[{"ref": "a", "title": "A", "assignee": "blog",
                                         "max_runtime_seconds": bad}]))

    def test_max_runtime_rejects_bool(self):
        # bool is an int subclass — must not sneak through as a runtime cap.
        with self.assertRaises(B.WorkflowError):
            B.validate(_tmpl(steps=[{"ref": "a", "title": "A", "assignee": "blog",
                                     "max_runtime_seconds": True}]))

    def test_tenant_maps_to_every_task(self):
        plan = B.build_plan(_tmpl(tenant="cedar-sage"))
        self.assertTrue(all(p.payload["tenant"] == "cedar-sage" for p in plan))

    def test_tenant_absent_by_default(self):
        self.assertNotIn("tenant", B.build_plan(_tmpl())[0].payload)

    def test_tenant_must_be_string(self):
        with self.assertRaises(B.WorkflowError):
            B.load_template({"name": "x", "tenant": 123,
                             "steps": [{"ref": "a", "title": "A", "assignee": "blog"}]})


class BoardLoading(unittest.TestCase):
    def test_board_spec_parsed(self):
        t = B.load_template({"name": "x", "board": {"slug": "cedar", "name": "Cedar",
                                                    "color": "#0a0"},
                             "steps": [{"ref": "a", "title": "A", "assignee": "blog"}]})
        self.assertEqual(t.board.slug, "cedar")
        self.assertEqual(t.board.name, "Cedar")
        self.assertEqual(t.board.color, "#0a0")

    def test_board_requires_slug(self):
        with self.assertRaises(B.WorkflowError):
            B.load_template({"name": "x", "board": {"name": "no slug"},
                             "steps": [{"ref": "a", "title": "A", "assignee": "blog"}]})

    def test_dry_run_surfaces_board_tenant_dispatch(self):
        t = _tmpl(tenant="cedar", board={"slug": "cedar"})
        out = B.instantiate(t, dry_run=True, dispatch=True)
        self.assertEqual(out["board"], "cedar")
        self.assertEqual(out["tenant"], "cedar")
        self.assertTrue(out["dispatch"])
        self.assertEqual(len(out["tasks"]), 2)


class BoardAndDispatchEmitter(unittest.TestCase):
    def test_ensure_board_posts_and_targets(self):
        calls: list[tuple] = []

        def fake(path, body):
            calls.append((path, body))
            return {"board": {"slug": body.get("slug")}}

        em = B.KanbanEmitter(transport=fake)
        em.ensure_board(B.BoardSpec(slug="cedar", name="Cedar"))
        self.assertEqual(em.board, "cedar")             # now targets the board
        self.assertTrue(calls[0][0].endswith("/boards"))
        self.assertEqual(calls[0][1]["slug"], "cedar")
        self.assertEqual(calls[0][1]["name"], "Cedar")

    def test_run_dispatch_posts(self):
        calls: list[str] = []

        def fake(path, body):
            calls.append(path)
            return {"spawned": 3}

        em = B.KanbanEmitter(transport=fake)
        r = em.run_dispatch(5)
        self.assertTrue(calls[0].endswith("/dispatch?max=5"))
        self.assertEqual(r["spawned"], 3)

    def test_run_dispatch_dry_run_adds_flag(self):
        """dry_run=True must add &dry_run=true so the wire is verifiable
        without spawning real workers."""
        calls: list[str] = []

        def fake(path, body):
            calls.append(path)
            return {"would_dispatch": 2}

        em = B.KanbanEmitter(transport=fake)
        r = em.run_dispatch(5, dry_run=True)
        self.assertIn("max=5", calls[0])
        self.assertIn("dry_run=true", calls[0])
        self.assertEqual(r["would_dispatch"], 2)

    def test_instantiate_threads_dispatch_dry_run(self):
        """instantiate(dispatch=True, dispatch_dry_run=True) must forward the
        dry-run flag into run_dispatch (no network)."""
        tmpl = B.load_template({
            "name": "t", "board": {"slug": "verify"},
            "steps": [{"ref": "a", "title": "Draft a post", "assignee": "blog"}],
        })
        seen: dict[str, object] = {}
        orig_emit = B.KanbanEmitter.emit
        orig_dispatch = B.KanbanEmitter.run_dispatch
        try:
            B.KanbanEmitter.emit = lambda self, plan: [
                {"ref": p.ref, "id": "T1", "assignee": "blog",
                 "parents": [], "warning": None} for p in plan
            ]
            B.KanbanEmitter.run_dispatch = lambda self, max_n=8, *, dry_run=False: (
                seen.update(max_n=max_n, dry_run=dry_run) or {"ok": True}
            )
            out = B.instantiate(
                tmpl, {}, session_token="x",
                dispatch=True, dispatch_max=4, dispatch_dry_run=True,
            )
        finally:
            B.KanbanEmitter.emit = orig_emit
            B.KanbanEmitter.run_dispatch = orig_dispatch
        self.assertEqual(seen, {"max_n": 4, "dry_run": True})
        self.assertEqual(out["dispatch"], {"ok": True})


class FreeToolTemplates(unittest.TestCase):
    """Phase 1 free-tool capability templates: copy-, deck-, proposal-,
    ad-creative-, newsletter-engine. Each must load, validate honesty-clean,
    plan into the expected DAG with a triage human-gate as the final step,
    and use only no-PHI vetted profiles."""

    def _check_common(self, tmpl, plan, expected_steps):
        self.assertFalse(tmpl.allow_phi)
        for p in plan:
            self.assertIn(p.payload["assignee"], B.VETTED_PROFILES)
            self.assertNotIn(p.payload["assignee"], B.PHI_PROFILES)
        self.assertEqual(len(plan), expected_steps)
        # last step must be a triage human gate
        last = plan[-1].payload
        self.assertTrue(last.get("triage"), "final step must be a triage human gate")

    def test_copy_engine_loads_validates_and_plans(self):
        t = B.load_template_file(_COPY)
        self.assertEqual(t.name, "copy-engine")
        B.validate(t)
        plan = B.build_plan(t, {"page_type": "about page", "project": "cedar-sage"})
        self._check_common(t, plan, 4)
        refs = [p.ref for p in plan]
        # brief → draft → review → publish(triage)
        self.assertLess(refs.index("brief"), refs.index("draft"))
        self.assertLess(refs.index("draft"), refs.index("review"))
        self.assertLess(refs.index("review"), refs.index("publish"))
        self.assertEqual(refs[-1], "publish")

    def test_deck_engine_loads_validates_and_plans(self):
        t = B.load_template_file(_DECK)
        self.assertEqual(t.name, "deck-engine")
        B.validate(t)
        plan = B.build_plan(t, {"purpose": "trauma workshop", "project": "cedar-sage"})
        self._check_common(t, plan, 5)
        refs = [p.ref for p in plan]
        # brief → outline → deck → review → deliver(triage)
        self.assertLess(refs.index("brief"), refs.index("outline"))
        self.assertLess(refs.index("outline"), refs.index("deck"))
        self.assertLess(refs.index("deck"), refs.index("review"))
        self.assertLess(refs.index("review"), refs.index("deliver"))
        self.assertEqual(refs[-1], "deliver")

    def test_proposal_engine_loads_validates_and_plans(self):
        t = B.load_template_file(_PROPOSAL)
        self.assertEqual(t.name, "proposal-engine")
        B.validate(t)
        plan = B.build_plan(t, {"recipient": "Oak Street Pediatrics",
                                 "project": "cedar-sage"})
        self._check_common(t, plan, 4)
        refs = [p.ref for p in plan]
        # brief → draft → review → send(triage)
        self.assertLess(refs.index("brief"), refs.index("draft"))
        self.assertLess(refs.index("draft"), refs.index("review"))
        self.assertLess(refs.index("review"), refs.index("send"))
        self.assertEqual(refs[-1], "send")

    def test_ad_creative_engine_loads_validates_and_plans(self):
        t = B.load_template_file(_AD)
        self.assertEqual(t.name, "ad-creative-engine")
        B.validate(t)
        plan = B.build_plan(t, {"campaign": "fall-groups", "project": "cedar-sage"})
        self._check_common(t, plan, 5)
        refs = [p.ref for p in plan]
        # brief → copy_variants → image_brief → review → approve(triage)
        self.assertLess(refs.index("brief"), refs.index("copy_variants"))
        self.assertLess(refs.index("copy_variants"), refs.index("image_brief"))
        self.assertLess(refs.index("image_brief"), refs.index("review"))
        self.assertLess(refs.index("review"), refs.index("approve"))
        self.assertEqual(refs[-1], "approve")

    def test_newsletter_engine_loads_validates_and_plans(self):
        t = B.load_template_file(_NEWSLETTER)
        self.assertEqual(t.name, "newsletter-engine")
        B.validate(t)
        plan = B.build_plan(t, {"edition": "July practitioner update",
                                 "project": "cedar-sage"})
        self._check_common(t, plan, 4)
        refs = [p.ref for p in plan]
        # brief → draft → review → send(triage)
        self.assertLess(refs.index("brief"), refs.index("draft"))
        self.assertLess(refs.index("draft"), refs.index("review"))
        self.assertLess(refs.index("review"), refs.index("send"))
        self.assertEqual(refs[-1], "send")

    def test_all_five_are_no_phi(self):
        for path in (_COPY, _DECK, _PROPOSAL, _AD, _NEWSLETTER):
            t = B.load_template_file(path)
            self.assertFalse(t.allow_phi, f"{t.name} must be no-PHI")


_FAQ = os.path.join(_HERE, "templates", "faq-engine.json")
_REPUTATION = os.path.join(_HERE, "templates", "reputation-engine.json")
_CALENDAR = os.path.join(_HERE, "templates", "content-calendar-engine.json")
_LOCAL_SEO = os.path.join(_HERE, "templates", "local-seo-engine.json")
_ONBOARDING = os.path.join(_HERE, "templates", "onboarding-email-engine.json")
_CLIP = os.path.join(_HERE, "templates", "social-clip-engine.json")
_FORMS = os.path.join(_HERE, "templates", "practice-forms-engine.json")


class OfficeExpansionTemplates(unittest.TestCase):
    """The office-expansion capability templates: faq-, reputation-,
    content-calendar-, local-seo-, onboarding-email-, social-clip-, and
    practice-forms-engine. Each must load, validate honesty-clean, plan into
    the expected linear chain with a triage human-gate as the final step, and
    use only no-PHI vetted profiles."""

    _ALL = (_FAQ, _REPUTATION, _CALENDAR, _LOCAL_SEO, _ONBOARDING, _CLIP, _FORMS)

    def _check_common(self, tmpl, plan, expected_steps):
        self.assertFalse(tmpl.allow_phi)
        for p in plan:
            self.assertIn(p.payload["assignee"], B.VETTED_PROFILES)
            self.assertNotIn(p.payload["assignee"], B.PHI_PROFILES)
        self.assertEqual(len(plan), expected_steps)
        last = plan[-1].payload
        self.assertTrue(last.get("triage"), "final step must be a triage human gate")
        self.assertIn("REQUIRES HUMAN REVIEW", last["body"])

    def test_faq_engine_loads_validates_and_plans(self):
        t = B.load_template_file(_FAQ)
        self.assertEqual(t.name, "faq-engine")
        B.validate(t)
        plan = B.build_plan(t, {"focus": "telehealth for anxiety", "project": "cedar-sage"})
        self._check_common(t, plan, 5)
        refs = [p.ref for p in plan]
        # questions → answers → schema → review → publish(triage)
        self.assertEqual(refs, ["questions", "answers", "schema", "review", "publish"])
        self.assertEqual(plan[0].payload["assignee"], "strategist")
        # the publish gate belongs to the website persona (a site page goes live)
        self.assertEqual(plan[-1].payload["assignee"], "website")

    def test_reputation_engine_loads_validates_and_plans(self):
        t = B.load_template_file(_REPUTATION)
        self.assertEqual(t.name, "reputation-engine")
        B.validate(t)
        plan = B.build_plan(t, {"review_text": "Kind office, hard to reach by phone",
                                "project": "cedar-sage"})
        self._check_common(t, plan, 4)
        refs = [p.ref for p in plan]
        self.assertEqual(refs, ["assess", "draft", "review", "post"])
        # the confidentiality rule is baked into the task bodies themselves —
        # the assess AND draft steps both instruct never-confirm-clienthood
        for ref in ("assess", "draft"):
            body = plan[refs.index(ref)].payload["body"]
            self.assertIn("never confirm or deny", body.lower())

    def test_content_calendar_engine_loads_validates_and_plans(self):
        t = B.load_template_file(_CALENDAR)
        self.assertEqual(t.name, "content-calendar-engine")
        B.validate(t)
        plan = B.build_plan(t, {"period": "September", "project": "cedar-sage"})
        self._check_common(t, plan, 5)
        refs = [p.ref for p in plan]
        self.assertEqual(refs, ["signal", "calendar", "briefs", "review", "adopt"])
        self.assertEqual(plan[0].payload["assignee"], "strategist")
        # the clinician's period substituted into the work
        self.assertIn("September", plan[0].payload["title"])

    def test_local_seo_engine_loads_validates_and_plans(self):
        t = B.load_template_file(_LOCAL_SEO)
        self.assertEqual(t.name, "local-seo-engine")
        B.validate(t)
        plan = B.build_plan(t, {"service_area": "Astoria, Queens", "project": "cedar-sage"})
        self._check_common(t, plan, 5)
        refs = [p.ref for p in plan]
        self.assertEqual(refs, ["audit", "profiles", "schema", "review", "apply"])
        self.assertEqual(plan[0].payload["assignee"], "strategist")

    def test_onboarding_email_engine_loads_validates_and_plans(self):
        t = B.load_template_file(_ONBOARDING)
        self.assertEqual(t.name, "onboarding-email-engine")
        B.validate(t)
        plan = B.build_plan(t, {"audience": "new adult individual clients",
                                "project": "cedar-sage"})
        self._check_common(t, plan, 4)
        refs = [p.ref for p in plan]
        self.assertEqual(refs, ["map", "drafts", "review", "load"])
        # blank-by-construction: the draft step demands bracketed placeholders
        self.assertIn("[FIRST NAME]", plan[refs.index("drafts")].payload["body"])

    def test_social_clip_engine_loads_validates_and_plans(self):
        t = B.load_template_file(_CLIP)
        self.assertEqual(t.name, "social-clip-engine")
        B.validate(t)
        plan = B.build_plan(t, {"source": "Rest, honestly", "project": "cedar-sage"})
        self._check_common(t, plan, 4)
        refs = [p.ref for p in plan]
        self.assertEqual(refs, ["pick", "package", "review", "render"])
        # the render gate: office renders only AFTER the clinician's okay
        self.assertIn("approval", plan[-1].payload["body"])

    def test_practice_forms_engine_loads_validates_and_plans(self):
        t = B.load_template_file(_FORMS)
        self.assertEqual(t.name, "practice-forms-engine")
        B.validate(t)
        plan = B.build_plan(t, {"form_type": "cancellation policy",
                                "project": "cedar-sage"})
        self._check_common(t, plan, 4)
        refs = [p.ref for p in plan]
        self.assertEqual(refs, ["outline", "draft", "review", "adopt"])
        # not-legal-advice framing is in the task bodies, start to finish
        self.assertIn("legal advice", plan[refs.index("outline")].payload["body"])
        self.assertIn("attorney", plan[-1].payload["body"])

    def test_all_seven_are_no_phi(self):
        for path in self._ALL:
            t = B.load_template_file(path)
            self.assertFalse(t.allow_phi, f"{t.name} must be no-PHI")
            for s in t.steps:
                self.assertNotIn(s.assignee, B.PHI_PROFILES,
                                 f"{t.name}:{s.ref} uses a PHI profile")


class ManifestIntegrity(unittest.TestCase):
    """CAPABILITY_MANIFEST.json is the product surface (svc/capabilities.py
    renders staff menus from it verbatim). Pin the whole surface: every entry
    points at a real template that passes every guardrail, the staff list is
    exactly the assignees the template uses, and the copy shown to therapists
    is itself honesty-lint clean. A drifted manifest fails here, not in prod."""

    # The 8 no-PHI office roles svc serves (svc/capabilities.py OFFICE_STAFF).
    # sarah (gateway persona) and the 6 PHI roles never appear on a menu.
    _OFFICE = frozenset({
        "orchestrator", "website", "blog", "marketer",
        "strategist", "reviewer", "analytics", "distributor",
    })

    @classmethod
    def setUpClass(cls):
        import json
        with open(os.path.join(_HERE, "CAPABILITY_MANIFEST.json"), encoding="utf-8") as fh:
            cls.manifest = json.load(fh)
        cls.caps = cls.manifest["capabilities"]

    def test_ids_unique(self):
        ids = [c["id"] for c in self.caps]
        self.assertEqual(len(ids), len(set(ids)), "duplicate capability id")

    def test_every_template_exists_loads_and_validates(self):
        for c in self.caps:
            path = os.path.join(_HERE, c["template"].replace("templates/", "templates" + os.sep))
            self.assertTrue(os.path.isfile(path), f"{c['id']}: missing {c['template']}")
            t = B.load_template_file(path)
            B.validate(t)  # allow-list + PHI gate + honesty lint + acyclic

    def test_staff_matches_template_assignees(self):
        for c in self.caps:
            t = B.load_template_file(os.path.join(_HERE, c["template"]))
            used = {s.assignee for s in t.steps}
            self.assertEqual(set(c.get("staff") or []), used,
                             f"{c['id']}: manifest staff ≠ template assignees")

    def test_staff_are_office_roles(self):
        for c in self.caps:
            for name in c.get("staff") or []:
                self.assertIn(name, self._OFFICE,
                              f"{c['id']}: {name!r} is not a no-PHI office role")

    def test_menu_copy_is_honesty_clean(self):
        # The label/description/cap strings render on therapist-facing menus
        # verbatim — they must pass the same linter as every other output.
        from engine.generate import lint
        for c in self.caps:
            for fieldname in ("label", "description", "cap"):
                text = c.get(fieldname) or ""
                self.assertEqual(lint(text), [],
                                 f"{c['id']}.{fieldname}: banned language")

    def test_human_gate_flag_matches_template(self):
        # human_gate: true promises a triage step a person must clear; a
        # template without one makes that promise false (and vice versa is
        # allowed only for the office-publishes lanes that end at reviewer).
        for c in self.caps:
            t = B.load_template_file(os.path.join(_HERE, c["template"]))
            has_triage = any(s.triage for s in t.steps)
            if c.get("human_gate"):
                gated = has_triage or any(s.requires_review for s in t.steps)
                self.assertTrue(gated, f"{c['id']}: human_gate promised, none in template")
            else:
                self.assertFalse(has_triage,
                                 f"{c['id']}: triage step present but human_gate false")


if __name__ == "__main__":
    unittest.main(verbosity=2)
