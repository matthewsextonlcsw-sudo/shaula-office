# Shaula — the AI-staffed office for a therapy practice

Shaula is an open agent harness (built on [Nous Research Hermes](https://github.com/NousResearch/hermes-agent),
MIT, vendored and hardened) that runs a therapy practice's **back office**:
website, blog, FAQ, review replies, newsletters, paperwork drafts, and more —
as **17 ready-made workflows** on a kanban board, each ending at a human gate.

It runs **on your machine**. Nobody hosts your data; this office houses nothing.

## The two promises

1. **Honesty engine.** Every output passes a banned-language gate — no invented
   statistics, no outcome promises, no fake credentials. The linter refuses to
   ship them, the reviewer step re-checks, and a model can never approve its
   own review.
2. **Human gates.** Anything that would be published, posted, or sent stops on
   a triage column until a person approves it. No auto-publishing, ever.

## Get started

```bash
git clone https://github.com/matthewsextonlcsw-sudo/shaula-office.git
cd shaula-office
bin/shaula-setup --local          # free, offline: Ollama on this machine
# or
bin/shaula-setup --cloud YOUR_GCP_PROJECT_ID   # Gemini on YOUR Vertex, YOUR billing
```

Full walkthrough, first workflow, and troubleshooting: **[docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)**.

## What's inside

| Piece | What it is |
|---|---|
| `bin/shaula*` | launchers: chat, kanban board, office UI, Telegram gateway |
| `workflows/` | the template engine + 17 capability templates (vetted staff, PHI gate, honesty lint, acyclic DAG — all enforced, all tested) |
| `engine/` | the deterministic website generator + the banned-language single source |
| `skills/`, `profiles/` | the office staff and their skills |
| `svc/` | optional hosted runtime (self-hosters don't need it) |
| `vendor/hermes/` | the pinned, audited Hermes harness (MIT) |

## Boundaries, stated plainly

Shaula runs the office, not the therapy. It never handles a clinical crisis,
never makes a clinical decision, and the shipped workflows are no-PHI by
construction — the PHI-capable staff profiles are disabled behind an explicit
double opt-in. If your practice is under HIPAA and you use the cloud brain,
use a Google Cloud setup covered by **your** Google BAA.

## License

MIT — see [LICENSE](LICENSE). The vendored Hermes harness keeps its own MIT
license in `vendor/hermes/LICENSE`.
