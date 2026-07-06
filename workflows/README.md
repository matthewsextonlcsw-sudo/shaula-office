# Shaula workflows — the no-code workflow builder (D14)

Turn a small JSON **template** (a DAG of tasks, each assigned to one of the 15
vetted staff) into real rows on the live Hermes **kanban board**, with the
dependency edges wired so the existing dispatcher runs them in order.

**Why this layer exists.** The kanban board is already a complete workflow
*engine* — DAG dependencies, auto-decompose, profile-dispatched workers, honesty
rules in the seeded prompts. The only missing piece for therapist self-serve was
a safe *builder* that turns a declarative template into that task-graph. This is
it. It ports [quentintou/agent-board](https://github.com/quentintou/agent-board)'s
template→task mechanism (MIT) onto Hermes' own `POST /tasks` + `parents=[…]`
DAG-at-create contract.

## The guardrails (the whole point)

A therapist-built workflow is **composition of vetted parts, never new blast
radius**. Four gates, all enforced in `builder.py`, all unit-tested:

1. **Assignee allow-list** — every step must target one of the 15 vetted
   profiles (`VETTED_PROFILES`). An unknown assignee is rejected. Therapists
   compose the existing staff; they cannot summon a new agent with new powers.
2. **PHI gate** — the six PHI-touching profiles (`workspace, frontdesk,
   customer-service, scribe, biller, clinical-admin`) are refused unless the
   template sets `allow_phi: true` **and** the caller passes `--allow-phi`; and
   any PHI step must run in a practice-owned `dir:` workspace, never ephemeral
   scratch. Default is **no-PHI-only** — house-nothing holds.
3. **Honesty lint** — every template-authored string (post variable
   substitution) is run through the **same** linter that guards the site
   generator (`engine/generate.py:lint`). A banned claim — fabricated stats,
   "proven/guaranteed", "studies show", testimonials, "cure", "#1", … — aborts
   instantiation before anything is written. Each emitted task body is then
   prefixed with the honesty + house-nothing preamble (trusted boilerplate,
   never itself linted).
4. **Acyclic** — dependencies form a DAG; a cycle, a dangling ref, or a
   duplicate ref is rejected up front (Kahn topological sort).

Pure-stdlib domain logic (load / validate / topo-sort / plan) is separated from
the HTTP emitter, so the entire guardrail surface is unit-testable with **zero
network**. The emitter takes an injectable transport for the same reason.

## Template schema

```jsonc
{
  "name": "weekly-blog",                 // required
  "description": "…",
  "variables": ["topic", "project"],     // names that may appear as {token}s
  "allow_phi": false,                    // must be true to use a PHI profile
  "default_workspace_kind": "scratch",   // "scratch" | "dir"
  "default_workspace_path": null,        // required (a real dir) for PHI work
  "tenant": "cedar-sage",                // optional per-practice isolation key (stamped on every task)
  "board": {                             // optional — the board to create/target ("your own boards")
    "slug": "cedar-sage",                //   required if `board` is present; idempotent on slug
    "name": "Cedar & Sage",              //   display metadata (optional)
    "description": "…", "icon": "🌲", "color": "#4f8a5b"
  },
  "steps": [
    {
      "ref": "brief",                    // required, unique within the template
      "title": "Blog brief: {topic}",    // required
      "assignee": "blog",                // required, must be a vetted profile
      "description": "…",                // becomes the task body (after the preamble)
      "dependencies": ["other_ref"],     // refs this step waits on (the DAG edges)
      "priority": "medium",              // low | medium | high | urgent
      "skills": ["…"],                   // optional Hermes skills passthrough
      "workspace_kind": "dir",           // optional per-step override of the default
      "workspace_path": "/Volumes/…",    // required if this step touches PHI
      "requires_review": true,           // appends a human-review note to the body
      "tags": ["geo"],                   // optional, recorded in the body footer
      "triage": true,                    // optional — land in the triage column for human approval before it runs
      "max_runtime_seconds": 600         // optional — per-task runtime cap (positive int)
    }
  ]
}
```

Field mapping to Hermes `CreateTaskBody`: `title→title`, `(preamble+description)
→body`, `assignee→assignee`, `priority→int (low0/med1/high2/urgent3)`,
`workspace_kind/path→workspace_kind/path`, `dependencies→parents` (resolved to
real task ids at emit time, parents-first), `skills→skills`, `triage→triage`,
`max_runtime_seconds→max_runtime_seconds`, template `tenant→tenant` (on every
task), and `--instance-key X` → `idempotency_key = "X:<ref>"` (re-runnable
instantiation). The template `board` maps to `POST /boards` (created with
`--create-board`, idempotent on slug); `--board SLUG` overrides it.

### Deliberately *not* exposed (conscious omissions, not gaps)

The builder covers every **safe** `CreateTaskBody` field. Two areas are withheld
on purpose:

- **`goal_mode` / `goal_max_turns`** — unbounded agentic looping. More blast
  radius than a therapist no-code workflow should hand out; a workflow is a
  bounded DAG of discrete steps, not an open-ended agent.
- **Task lifecycle endpoints** — edit / delete / link-rewrite / reassign /
  comment / attachment. Those are *runtime board management* (the dashboard's
  job), not *build-time instantiation* (this builder's job). The builder builds
  the graph; the board operates it.

## CLI

```bash
# 1) Validate a template (structure + every guardrail, no network):
python3 -m workflows.cli validate workflows/templates/weekly-blog.json

# 2) Dry-run — print the exact task-graph that WOULD be created (no network):
python3 -m workflows.cli plan workflows/templates/weekly-blog.json \
    -v topic="Sleep and anxiety" -v project=cedar-sage

# 3) Emit to the live board (parents-first). Needs a running dashboard + token:
python3 -m workflows.cli emit workflows/templates/weekly-blog.json \
    -v topic="Sleep and anxiety" -v project=cedar-sage \
    --base-url http://127.0.0.1:8200 \
    --session-token "$HERMES_DASHBOARD_SESSION_TOKEN" \
    --instance-key blog-2026w23

# 4) Create your own board + build the graph on it, then preview a dispatch
#    pass (dry-run spawns nothing) — build now, run when you promote it:
python3 -m workflows.cli emit workflows/templates/weekly-blog.json \
    -v topic="Sleep and anxiety" -v project=cedar-sage \
    --base-url http://127.0.0.1:8200 --session-token "$HERMES_DASHBOARD_SESSION_TOKEN" \
    --board cedar-sage --create-board \
    --dispatch --dispatch-dry-run --instance-key blog-2026w23
```

The emitter authenticates with the dashboard session token (sent as both
`X-Hermes-Session-Token` and `Authorization: Bearer …`). Launch the dashboard
with a known `HERMES_DASHBOARD_SESSION_TOKEN` so `emit` can authenticate
non-interactively. `--allow-phi` unlocks PHI profiles (template must also opt in).

`emit` flags: `--board SLUG` targets/overrides the template's board;
`--create-board` creates it first (idempotent on slug); `--dispatch` kicks one
dispatch pass after the graph lands (build **and** run); `--dispatch-max N` caps
workers spawned (default 8); `--dispatch-dry-run` previews what dispatch *would*
spawn **without spawning anything** (safe to verify the wire).

## Adding a template

Drop a new `*.json` in `workflows/templates/`, then `validate` it. Keep every
assignee in the 15 vetted profiles, keep claims honest (the linter will catch
you), prefer an explicit `reviewer` step for anything that gets published or
sent, and — if the capability ships on a product menu — add its
`CAPABILITY_MANIFEST.json` entry with `staff` exactly equal to the template's
assignees (the `ManifestIntegrity` suite pins all of this). Seventeen
capability templates ship in `workflows/templates/`:

- **`weekly-blog.json`** — the seed (the no-PHI marketing/GEO lane, HARNESS
  workflow L): `brief → draft → {geo, teasers} → review`.
- **`growth-engine.json`** — the OpenGrowth content loop: generalizes
  weekly-blog with a data-driven topic-pick front (`strategist`, from REAL
  demand signal only) and a results-log back (`analytics`). Still stops at the
  honesty review — **no auto-publish**.
- **`distribution-engine.json`** — earned backlinks the white-hat way
  (`distributor` drafts platform-native syndication carrying `rel=canonical`),
  honesty-reviewed, then held in a **human-approval (`triage`) column** — a
  person posts each piece in context. No link exchange, no auto-posting.
- **`website-launch.json`**, **`copy-engine.json`**, **`deck-engine.json`**,
  **`proposal-engine.json`**, **`ad-creative-engine.json`**,
  **`newsletter-engine.json`**, **`research-engine.json`** — the free-tool
  lanes (site, page copy, decks, letters, ads, newsletter, research brief),
  each ending at the honesty review or a triage human gate.
- **The office expansion** (2026-07-05) — seven recurring back-office lanes,
  every one a linear chain ending in a **triage human gate**:
  - **`faq-engine.json`** — real questions → honest answers → FAQPage JSON-LD
    → review → clinician publishes.
  - **`reputation-engine.json`** — a compliant public review reply: never
    confirms or denies a care relationship (the rule is written into the task
    bodies AND checked at review); the clinician posts it themselves.
  - **`content-calendar-engine.json`** — a month of topics from named real
    signal, briefed to feed weekly-blog / growth-engine; the clinician adopts
    or cuts each slot.
  - **`local-seo-engine.json`** — off-site presence: profile/directory audit,
    honest profile copy, consistent name-address-phone, local JSON-LD; the
    clinician applies changes in their own accounts.
  - **`onboarding-email-engine.json`** — blank welcome-sequence templates
    (bracketed placeholders, zero client data); clinical outreach explicitly
    gets **no** template.
  - **`social-clip-engine.json`** — one approved essay → verbatim passage →
    clip beats + caption; the OFFICE renders deterministically only after the
    clinician's okay.
  - **`practice-forms-engine.json`** — starting drafts of practice paperwork,
    not-legal-advice framing enforced start to finish; the clinician finalizes
    (attorney review where required).

## Tests

```bash
python3 -m unittest workflows.test_builder -v   # 66 tests, no network
```

Covers: the 14-profile allow-list, the PHI gate (opt-in + dir-workspace),
honesty lint (pre- and post-substitution), cycle / dangling / duplicate
rejection, variable substitution + missing/unknown tokens, priority mapping,
idempotency keys, preamble injection (and proof the preamble is never
self-linted), the dry-run plan shape, the emitter's parents-first ref→id
resolution (via an injected transport); plus the completeness-pass fields —
`triage` / `max_runtime_seconds` mapping + rejection of a non-positive or bool
cap, template `tenant` stamped on every task + rejection of a non-string,
`board` parsing + slug-required, the dry-run surfacing of board/tenant/dispatch,
`ensure_board` POST + target switch, and `run_dispatch` with the `dry_run` flag
threaded end-to-end through `instantiate`; plus the two shipped content-engine
templates — `growth-engine` loads/validates/plans to its 7-task DAG
(`keywords`→…→`measure`, strategist exercised, all vetted + no-PHI) and
`distribution-engine` to its 3-task DAG (`syndicate`→`review`→`approve`, the
`approve` step carrying `triage` for the human gate).

## Smoke test — the one-command proof

```bash
python3 -m workflows.smoke                 # offline proof + live proof (if a dashboard is up)
python3 -m workflows.smoke --offline-only  # guardrails + plan shape only, zero network
python3 -m workflows.smoke --base-url http://127.0.0.1:8200
```

One command that proves the whole builder end to end, so you can trust it
*before* poking the API by hand. It is **re-runnable and side-effect-clean**: it
uses a dedicated throwaway board (`shaula-smoke`) and a fixed instance key, so
every re-run dedups onto the same rows — nothing accrues, nothing is deleted,
the `default` board is never touched. The dashboard session token is
**auto-discovered the way a browser gets it** (the server injects
`window.__HERMES_SESSION_TOKEN__` into its own page); pass `--session-token` or
set `$HERMES_DASHBOARD_SESSION_TOKEN` to override. A bare curl is still 401.
Exit code is 0 iff every check that ran passed.

- **Phase A — offline (always runs, no network):** runs the 45-test suite and
  asserts it's green; builds the embedded synthetic template and checks the plan
  shape (topo order, `triage` / `max_runtime_seconds` / `tenant` / preamble /
  idempotency-key mapping, `{variable}` substitution); then drives each guardrail
  to its rejection — bad assignee, PHI-without-opt-in, dependency cycle, banned
  honesty claim, dangling dependency ref.
- **Phase B — live (only if a dashboard answers):** instantiates the template on
  `shaula-smoke`, then reads the state back over HTTP and asserts the **server**
  persisted it — board created, DAG edge wired (`links.parents`), the triage step
  in the triage column, `tenant` + `max_runtime_seconds` on the rows — and that
  the dispatch **dry-run** spawned zero workers (the `running` column stays
  empty, `spawned: []`).

**Result (live, dashboard on :8200, 2026-06-06):** `27 passed, 0 failed`. A
second back-to-back run returned the identical `t_…` draft id in the triage
column (deduped, no accrual), proving the re-run contract holds.

## Live-verified (2026-06-06)

`weekly-blog` instantiated against a running dashboard (`bin/shaula --local
dashboard --port 8200`): 5 tasks created, board 7→12, the DAG persisted
server-side (`link_counts`): `brief`(0p/1c) → `draft`(1p/2c) → `geo`(1p/1c) +
`teasers`(1p/1c) → `review`(2p/0c). `brief` landed in **Ready** (deps satisfied),
the 4 dependents in **Todo** (waiting on deps). Screenshot:
`../docs/screenshots/shaula-workflow-board.png`.

**Completeness-pass fields (also live-verified, 2026-06-06).** A synthetic
no-PHI template (`/tmp/shaula-verify-newfields.json`) emitted with
`--create-board --instance-key verify-001` against the same dashboard:

- **board create** — a new `verify-newfields` board appeared in `GET /boards`
  (total 2), separate from `default` (additive, didn't touch it).
- **triage column** — the `triage:true` step landed in **triage**; the board
  reported `counts={'todo':1,'triage':1}` and the row read back `status:triage`.
- **tenant** — `verify-practice` stamped on **both** task rows server-side.
- **max_runtime_seconds** — `600` / `300` persisted on the two rows.
- **DAG edge** — the dependent's `links.parents=['<parent-id>']` server-side.
- **dispatch dry-run** — `run_dispatch(dry_run=True)` through the real emitter
  returned the dispatcher preview (`spawned: []`) and the board counts were
  **unchanged** — zero workers spawned, the wire confirmed safe.

## Not yet decided — the UI surface (porcelain, Matthew's call)

This is the **plumbing**: the emitter, schema, guardrails, CLI, tests. How the
builder *surfaces* in the dashboard — a reskinned kanban "workflow boxes" tab, a
new "Workflows" tab with a visual template editor, or CLI/preset-only for now —
is a UX decision and stays open.
