# Vendored upstream — Nous Research Hermes Agent

- **Upstream:** https://github.com/NousResearch/hermes-agent
- **License:** **MIT** (preserved verbatim at `vendor/hermes/LICENSE`)
- **Pinned commit:** `66a6b9c930019eeefe0bc089edcf47ff5ce9d0d8` (2026-06-05)
- **Vendored:** 2026-06-05 → `vendor/hermes/`

## What we vendored
The working tree at the pinned commit, **minus** (to keep history lean + drop non-shippable code):
- `.git/` — we track Shaula's history, not theirs
- `skills/red-teaming/` — ships `exec(compile(...))` jailbreak skills (audit: never on a HIPAA box)
- `optional-skills/` — inert self-evolution / experimental content we don't ship
- `infographic/` — marketing images, non-code

The **pristine baseline is always recoverable**: `git clone <upstream> && git checkout 66a6b9c`.
Exact exclusions are also visible in this repo's first vendor commit message.

## Pulling upstream diffs — the gate → review → push model
An `upstream` remote is configured on this repo. We **never auto-pull.** To absorb upstream changes:
```bash
git fetch upstream
git diff 66a6b9c..upstream/main -- vendor/hermes/<path>   # REVIEW before absorbing
# re-run the audit on the diff, then re-run scripts/verify-harden.sh
# absorb deliberately in a tracked commit; bump the pin here
```

## Security audit
Full 6-agent audit of this exact commit: [`../docs/SECURITY_AUDIT_hermes.md`](../docs/SECURITY_AUDIT_hermes.md).
Verdict: clean, self-evolution freezable, local-first. Hardening enforced by `config/shaula-harden.yaml`.
