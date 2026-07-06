# Getting started with Shaula

Shaula is an AI-staffed back office for a therapy practice: a hardened agent
harness (vendored Nous Research Hermes, MIT) with an honesty engine, a kanban
work board, and 17 ready-made office workflows — website, blog, FAQ, review
replies, newsletters, paperwork drafts, and more. It runs **on your machine**.
Nothing is hosted by us; we house nothing.

Two ways to power the brain — pick one (you can add the other later):

| Tier | What runs the model | Cost | Privacy posture |
|---|---|---|---|
| **Local** (`--local`) | Ollama on this machine | $0 | Offline. Nothing ever leaves the box. |
| **Cloud brain** (`--cloud`) | Gemini on **your own** Google Cloud Vertex project | Your Google billing (pay-per-use) | Your project, your data terms, your Google BAA. Shaula's maker sees nothing. |

Either way, every output passes the same honesty gate (no invented statistics,
no outcome promises, no fake credentials — the linter refuses to ship them),
and anything that would be published or sent stops at a **human gate**: you
approve it, or it does not happen.

---

## Quickstart (local, free, ~10 minutes + one model download)

Prereqs: macOS or Linux · [Python 3.11–3.13](https://www.python.org/downloads/)
(3.14 not yet supported; 3.11 is the smoothest) · [Ollama](https://ollama.com/download)
· git · Node 20+ (for the kanban board UI's one-time build) ·
[uv](https://docs.astral.sh/uv/) recommended (`brew install uv`) — setup falls
back to pip without it, but uv matches the vendored lockfile's resolution.

```bash
git clone https://github.com/matthewsextonlcsw-sudo/shaula-office.git
cd shaula-office
bin/shaula-setup --local          # the walkthrough: preflight → install → doctor
```

The walkthrough is idempotent — re-run it any time; it skips what's already
done. It will:

1. **Preflight** — checks git, a supported Python, disk space (~2 GB for the
   harness, ~5 GB for the local model), and Ollama.
2. **Install the harness** — creates `vendor/hermes/.venv-shaula` and installs
   the vendored, security-pinned Hermes (CVE constraints from
   `config/constraints-shaula.txt` applied automatically).
3. **Create your home** — `~/.shaula-home` (override with `HERMES_HOME`), and
   writes the **hardened config** for your tier. The hardening is not optional
   decoration: sandboxed shell, self-evolution frozen, high-risk toolsets off,
   manual approvals.
4. **Hire the staff** — installs the vetted profiles and first-party skills.
5. **Pull the local model** — offers `ollama pull qwen2.5:7b-instruct`
   (asks first; ~4–5 GB).
6. **Doctor** — runs `hermes doctor` and refuses to call the install done
   unless it's healthy.

Then talk to it:

```bash
export HERMES_HOME=~/.shaula-home
ollama serve &                          # if not already running
bin/shaula --local chat -q "hello"
```

## Quickstart (cloud brain — your own Google project)

Prereqs: the local prereqs minus Ollama, plus the
[gcloud CLI](https://cloud.google.com/sdk/docs/install) and a Google Cloud
project **you own** (with billing enabled — the model usage is billed to you,
by Google, at Vertex rates; there is no Shaula fee).

```bash
git clone https://github.com/matthewsextonlcsw-sudo/shaula-office.git
cd shaula-office
bin/shaula-setup --cloud YOUR_PROJECT_ID
```

Setup installs the same harness and staff, and writes the hardened config
pointed at **your** Vertex endpoint. It will then print — and deliberately NOT
run for you, because they touch your account and your billing — these:

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable aiplatform.googleapis.com
gcloud auth application-default login
bash scripts/verify-harden.sh           # must PASS before first use
```

Then:

```bash
bin/shaula chat -q "hello"
```

Each run mints a **short-lived access token** (~1 hour) to your Vertex — no
long-lived API key exists anywhere, and the banned consumer
`GEMINI_API_KEY`/`GOOGLE_API_KEY` path stays off (the hardening check enforces
this).

**If your practice handles PHI under HIPAA:** use a Google Cloud / Workspace
setup covered by **your** Google BAA. That agreement is between you and Google
— Shaula is software you run, not a party in the middle. The shipped office
workflows are no-PHI by construction either way; the PHI-touching staff
profiles are locked behind an explicit double opt-in and disabled by default.

---

## Your first workflow (the kanban board)

The board is Shaula's single source of work-state truth: every job becomes
cards with dependency edges, and the human gates are real columns, not
promises.

```bash
export HERMES_HOME=~/.shaula-home

# 1) Boot the board (dashboard on http://127.0.0.1:9121)
bin/shaula-board

# 2) In another terminal — see exactly what a workflow WOULD create (no writes):
python3 -m workflows.cli plan workflows/templates/weekly-blog.json \
    -v topic="Sleep and anxiety" -v project=my-practice

# 3) Put it on the board for real:
python3 -m workflows.cli emit workflows/templates/weekly-blog.json \
    -v topic="Sleep and anxiety" -v project=my-practice \
    --base-url http://127.0.0.1:9121 \
    --session-token "$HERMES_DASHBOARD_SESSION_TOKEN" \
    --instance-key blog-week-1
```

`--instance-key` makes re-runs safe: emitting the same key twice updates the
same cards instead of duplicating them.

**The 17 capabilities** live in `workflows/templates/` — website launch, weekly
blog, growth engine, FAQ page, review replies, content calendar, local
presence, welcome emails, social clips, practice paperwork, research desk,
decks, proposals, ads, newsletters, page copy, backlinks. Each is a small JSON
file you can read in a minute; `workflows/README.md` documents the format and
the four guardrails every template must pass (vetted staff only · PHI gate ·
honesty lint · acyclic dependencies).

There's also a friendlier front door — `bin/shaula-office` serves a simple
chat + build UI on http://127.0.0.1:8800 — and a Telegram gateway
(`bin/shaula-gateway`) once you want the office reachable from your phone.

---

## Where things live

| Thing | Where |
|---|---|
| The harness venv | `vendor/hermes/.venv-shaula/` (inside the repo) |
| Your config, staff, skills, board | `$HERMES_HOME` (default `~/.shaula-home`) |
| The kanban SQLite boards | `$HERMES_HOME/kanban/boards/` |
| Workflow templates | `workflows/templates/*.json` |
| The hardened config template | `config/shaula-harden.yaml` |

Back up `$HERMES_HOME` and you've backed up your office. Delete it and you've
factory-reset (the repo itself stays clean either way).

## Troubleshooting

- **Board tab renders but the API 404s** → the venv is missing
  `python-multipart` (Hermes doesn't declare it). `bin/shaula-setup` installs
  it; if you built the venv by hand:
  `vendor/hermes/.venv-shaula/bin/pip install python-multipart`.
- **`no supported Python found`** → Python 3.14 is too new for the pinned
  dependencies; install 3.11 alongside it (`brew install python@3.11`).
- **`ResolutionImpossible` during install** → you're on plain pip with a newer
  Python. Install uv (`brew install uv`) and re-run `bin/shaula-setup` — its
  resolver matches the vendored lockfile (Python 3.11 + uv is the known-good
  pair).
- **`ollama unreachable`** → start it: `ollama serve` (and confirm the model:
  `ollama list`).
- **Cloud tier: `could not mint a Vertex token`** → `gcloud auth login`
  again — the token is short-lived by design (~1 h) and `bin/shaula` mints a
  fresh one per run.
- **Everything vanished after a reboot** → your `HERMES_HOME` was under
  `/tmp`. Use the default (`~/.shaula-home`) or any persistent path
  (ideally on an encrypted volume).
- **Board says `Pre-build first: cd web && npm install && npm run build`** →
  the dashboard bundle hasn't been built on this machine yet. Re-run
  `bin/shaula-setup` (it offers the build), or run exactly that command inside
  `vendor/hermes/`.
- **Chat errors with `does not support tools`** → your local model can't run
  the agent loop. Use a tool-capable model — the default
  `qwen2.5:7b-instruct` is; small gemma-class chat models are not.
- **Port busy** → board: `SHAULA_BOARD_PORT=9122 bin/shaula-board` · office:
  `SHAULA_OFFICE_PORT=8801 bin/shaula-office`.

## What Shaula will not do

No invented statistics, reviews, or credentials — the honesty linter blocks
them at generation time, again at review, and the reviewer step cannot be
auto-approved by a model. No auto-publishing: every outward-facing artifact
ends at a human gate. No crisis handling: the office runs the practice's
paperwork and marketing; clinical judgment and clinical crises belong to the
clinician, always.
