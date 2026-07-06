#!/usr/bin/env bash
# prove.sh — the hard proof gate for the Shaula website engine.
#
# Runs ALL demo fixtures through the full pipeline:
#     generate.py  (deterministic content + block-level honesty lint, exit 2 on a
#                    banned claim) ->
#     fill.py      (apply blocks, substitute tokens, verify 0 leaks / 0 markers,
#                    node --check) ->
#     render_check (execute the SPA headless, assert every route renders real
#                    filled HTML with the practice's own data + 6 method rows)
# then two honesty gates:
#     - rendered-output phrase scan (CSS-safe subset of banned claims)
#     - operator-input scan over every fixtures/*/practice.json (honesty_scan.py)
#
# Any failure aborts the whole run non-zero. This is the regression gate the
# box's "build my website" button must keep green. No network, no LLM, stdlib +
# node only.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FIXTURES=(cedar-sage couples-riverbend northstar-denver)
TEMPLATE="templates/private-practice"

green() { printf '\033[32m%s\033[0m\n' "$1"; }
red()   { printf '\033[31m%s\033[0m\n' "$1"; }
fail()  { red "PROVE FAILED: $1"; exit 1; }

# Rendered-output banned phrases — the CSS-safe SUBSET of the canonical gate.
# DERIVED at run time from engine/banned.py (the single source of truth) so the
# shell scan here and the Python linter can never disagree. The subset omits the
# percentage and "#1" rules, which would false-positive on CSS-in-JS
# (width:100%, #1a2b3c hex); those stay enforced at the value level by
# generate.py / honesty_scan.py, where there is no CSS to confuse them. Derive
# fail-closed: an empty or failed pattern aborts rather than scanning for nothing.
RENDER_BANNED="$(python3 -c 'import sys; sys.path.insert(0, "engine"); import banned; print(banned.render_banned_shell_regex())')" \
  || fail "could not derive RENDER_BANNED from engine/banned.py"
[ -n "$RENDER_BANNED" ] || fail "derived RENDER_BANNED is empty — refusing to scan with an empty pattern"

echo "== Shaula website engine — proof gate =="
echo "root: $ROOT"
echo

# Banned-language single-source contract (anti-drift). engine/banned.py is the
# ONE definition every honesty surface derives from; this suite pins that
# generate/geo/honesty_scan/svc-honesty all resolve to it, that the RENDER tier
# is the documented CSS-safe subset, and — critically — that the RENDER_BANNED
# this script just derived equals the canonical subset (shell ≡ python, so they
# cannot drift). Run FIRST so a broken wiring fails before any fixture work.
echo "--- banned-language single-source contract (anti-drift) ---"
python3 -m unittest tests.test_banned >/dev/null 2>&1 \
  || fail "banned-language single-source test suite failed (tests/test_banned.py)"
green "PASS  banned single-source — one definition, two tiers, shell≡python render regex"
echo

for fx in "${FIXTURES[@]}"; do
  echo "--- fixture: $fx ---"
  practice="fixtures/$fx/practice.json"
  generated="engine/generated.$fx.json"
  out="sites/$fx"

  # Survey-driven fixtures regenerate practice.json from survey.json via
  # build_practice — this proves the full survey -> site path the box uses.
  survey="fixtures/$fx/survey.json"
  if [ -f "$survey" ]; then
    python3 engine/build_practice.py --survey "$survey" --out "$practice" \
      || fail "$fx: build_practice (survey -> practice.json) failed"
  fi

  [ -f "$practice" ] || fail "missing $practice"

  python3 engine/generate.py --practice "$practice" --out "$generated" \
    || fail "$fx: generate.py (block/honesty lint) failed"

  python3 engine/fill.py --template "$TEMPLATE" --practice "$practice" \
    --generated "$generated" --out "$out" \
    || fail "$fx: fill.py failed (token leak / marker / syntax)"

  # GEO/SEO finishing pass — inject JSON-LD (MedicalBusiness + FAQPage) + OG meta +
  # llms.txt, deterministically from honest tokens; geo.py self-aborts on a banned phrase.
  python3 engine/geo.py --practice "$practice" --site "$out" --url "https://example.com/$fx" \
    || fail "$fx: geo.py failed (honesty / injection)"

  node engine/render_check.mjs --out "$out" --practice "$practice" \
    || fail "$fx: render_check failed (route render / spot-check)"

  # rendered-output honesty (CSS-safe phrase subset)
  if grep -riE "$RENDER_BANNED" "$out/app.js" "$out/index.html" "$out/llms.txt" >/dev/null 2>&1; then
    echo "  banned phrase(s) in rendered output:"
    grep -rinE "$RENDER_BANNED" "$out/app.js" "$out/index.html" "$out/llms.txt" || true
    fail "$fx: banned claim phrase in rendered output"
  fi

  green "PASS  $fx — generate + fill + geo + render + rendered-honesty"
  echo
done

echo "--- operator-input honesty scan (all fixtures) ---"
python3 scripts/honesty_scan.py fixtures/*/practice.json \
  || fail "operator-input honesty scan failed"
echo

echo "--- AI-staff engine honesty gate (blog scaffolder) ---"
python3 scripts/staff_check.py \
  || fail "AI-staff engine honesty gate failed (blog scaffolder)"
echo

# OPTIONAL brain seam (engine/brain.py) — proven WITHOUT creds, WITHOUT network,
# and WITHOUT the google-genai SDK. The fixture loop above already exercises the
# brain=None deterministic floor (generate.py's CLI takes no brain). Here we prove
# the seam itself: a clean model rewrite is accepted and re-linted; a banned/empty
# rewrite falls back to the floor; tokens are preserved; a full build still renders
# leak-free with a fake brain. All via injected fakes, so this stays zero-dependency
# and safe to keep in the mandatory gate.
echo "--- brain seam — floor-fallback contract (no creds, no SDK) ---"
python3 engine/brain.py \
  || fail "brain.py self-test failed (floor-fallback contract)"
python3 -m unittest tests.test_brain >/dev/null 2>&1 \
  || fail "brain seam test suite failed (tests/test_brain.py)"
green "PASS  brain seam — enrich/reject/preserve + build-renders, all credential-free"
echo

# Authoring seam (workflows/author.py + svc/authoring.py) — the therapist self-serve
# authoring path. Same honesty-gate theme as the brain seam: these pin the moat on the
# authoring path — a non-vetted assignee / banned claim is REJECTED by builder.validate,
# an honesty trip on a workflow draft surfaces as a graceful AuthoringError (the PR #26
# 422-not-500 fix, re-prompted by the repair loop), and a genuine infra outage is NOT
# masked as a content refusal. Stub models, zero network; the only extra dep is httpx
# (svc.gemini's import chain), installed credential-free alongside google-genai above.
echo "--- authoring seam — vetted-compose + honesty-gate contract (no creds, no SDK) ---"
python3 -m unittest tests.test_author >/dev/null 2>&1 \
  || fail "author seam suite failed (tests/test_author.py)"
python3 -m unittest tests.test_authoring_svc >/dev/null 2>&1 \
  || fail "authoring svc seam suite failed (tests/test_authoring_svc.py)"
green "PASS  authoring seam — non-vetted/banned rejected + honesty trip → graceful 422, outage propagates"
echo

# Workflow builder + capability surface (workflows/builder.py + the shipped
# templates + CAPABILITY_MANIFEST.json). This is the D14 no-code layer's own
# moat — the 15-profile allow-list, the PHI gate, the honesty lint on every
# authored template string, the acyclic check, and the manifest-integrity pin
# (every capability points at a real template that validates; staff lists are
# exactly the template's assignees; menu copy is itself lint-clean). Plus the
# local-executor seam: the task-graph runs against a stub model with the REAL
# lint_gate on every step and the human-review step parks the run — never
# model-approved. Stdlib + the same credential-free httpx as the seams above.
echo "--- workflow builder — guardrails + templates + manifest integrity (no creds, no SDK) ---"
python3 -m unittest workflows.test_builder >/dev/null 2>&1 \
  || fail "workflow builder suite failed (workflows/test_builder.py)"
python3 -m unittest tests.test_local_executor >/dev/null 2>&1 \
  || fail "local executor seam suite failed (tests/test_local_executor.py)"
green "PASS  workflow builder — allow-list/PHI/honesty/DAG + manifest pinned + executor parks at the human gate"
echo

# Onboarding truth (docs/GETTING_STARTED.md + bin/shaula-setup). The front-door
# docs are pinned to the artifacts they describe — cited paths exist, ports
# match the launchers, the capability count matches the manifest, the setup
# script's local-model default matches the hardened floor, and the guide itself
# passes the house banned-language linter. A stale guide fails here, not on a
# stranger's first ten minutes. Stdlib, zero network.
echo "--- onboarding truth — guide + walkthrough pinned to reality ---"
python3 -m unittest tests.test_getting_started_truth >/dev/null 2>&1 \
  || fail "onboarding truth suite failed (tests/test_getting_started_truth.py)"
green "PASS  onboarding truth — guide paths/ports/counts/model floor verified + lint-clean"
echo

# Structured refusal output (concierge-beta deliverable C). The engine already
# ENFORCES omit-not-fabricate + banned-language abort above; this suite pins that
# it now also EMITS a machine-readable refusals manifest (the honesty receipt is
# generated from it) WITHOUT disturbing the byte-identical blocks payload fill.py
# consumes. Stdlib unittest, no new dependency, no network, synthetic fixtures.
echo "--- structured refusal output — manifest contract (no creds, no SDK) ---"
python3 -m unittest tests.test_refusals >/dev/null 2>&1 \
  || fail "refusals manifest test suite failed (tests/test_refusals.py)"
green "PASS  refusals manifest — resolved/dropped record + lint-clean attestation, blocks untouched"
echo

# Honesty receipt (concierge-beta deliverable C — the differentiator). Proves the
# receipt is GENERATED from the engine's refusals manifest + build_practice's
# _assumed record (never hand-assembled), renders the banned policy in deduped
# plain English via svc/honesty (no second linter), and cannot drift from the site
# (build_refusals runs the same deterministic generate()). Also smoke-runs the CLI
# on the synthetic northstar fixture so the operator path itself is exercised.
echo "--- honesty receipt — generated-from-manifest contract (no creds, no SDK) ---"
python3 -m unittest tests.test_receipt >/dev/null 2>&1 \
  || fail "honesty receipt test suite failed (tests/test_receipt.py)"
python3 scripts/honesty_receipt.py --practice fixtures/northstar-denver/practice.json \
  --date 2026-06-15 >/dev/null \
  || fail "honesty_receipt.py CLI failed on the northstar fixture"
green "PASS  honesty receipt — shown/held-back + plain banned policy + flagged assumptions"
echo

# Claim-provenance gate + build-time receipts. The provenance gate (engine/provenance.py)
# is the keystone that keeps Shaula honest on content whose STRUCTURE it does not control
# (3a import / 3b freehand); it is pinned here now that the build path depends on it.
# svc/receipts.py attaches two trust artifacts to every website-launch run: the honesty
# receipt (what Shaula refused to say / held back / assumed) and the provenance receipt —
# which renders the SPA headless (engine/render_dump.mjs; the static index.html is a shell,
# the body claims live in app.js) and proves every visible claim traces to the COMPLETE
# approved set (practice + generated + engine banks + template static copy). The smoke is
# the CRY-WOLF regression guard: an honest northstar render MUST be provenance-clean once
# the approved set is completed. node + stdlib only; no creds, no SDK, no network.
echo "--- claim-provenance gate + build receipts (no creds, no SDK) ---"
python3 -m unittest tests.test_provenance >/dev/null 2>&1 \
  || fail "claim-provenance gate suite failed (tests/test_provenance.py)"
python3 -m unittest tests.test_render_dump >/dev/null 2>&1 \
  || fail "SPA render-dump suite failed (tests/test_render_dump.py)"
python3 -m unittest tests.test_build_receipts >/dev/null 2>&1 \
  || fail "build receipts suite failed (tests/test_build_receipts.py)"
_rcptmp="$(mktemp -d)"
python3 engine/build_practice.py --survey fixtures/northstar-denver/survey.json --out "$_rcptmp/p.json" >/dev/null 2>&1 \
  && python3 engine/generate.py --practice "$_rcptmp/p.json" --out "$_rcptmp/g.json" >/dev/null 2>&1 \
  && python3 engine/fill.py --template "$TEMPLATE" --practice "$_rcptmp/p.json" --generated "$_rcptmp/g.json" --out "$_rcptmp/site" >/dev/null 2>&1 \
  && node engine/render_dump.mjs --out "$_rcptmp/site" > "$_rcptmp/render.html" 2>/dev/null \
  || { rm -rf "$_rcptmp"; fail "render_dump smoke: northstar build/render failed"; }
python3 - "$_rcptmp" <<'PY' || { rm -rf "$_rcptmp"; fail "rendered northstar SPA is not provenance-clean against its approved set (cry-wolf regression)"; }
import json, pathlib, sys
d = pathlib.Path(sys.argv[1])
sys.path.insert(0, "engine")
import provenance as P
practice = json.loads((d / "p.json").read_text("utf-8"))
generated = json.loads((d / "g.json").read_text("utf-8"))
rendered = (d / "render.html").read_text("utf-8")
app_js = (d / "site" / "app.js").read_text("utf-8")
off = P.gate(rendered, practice, generated, extra_texts=P.approved_template_extras(app_js))
sys.exit(0 if not off else 1)
PY
rm -rf "$_rcptmp"
green "PASS  provenance gate + render-dump + receipts — honest SPA clean, fabrications flagged"
echo

# Survey pre-flight validator (concierge-beta deliverable A — operator step 2). The
# intake form collects the survey; this validator PREDICTS the build outcome WITHOUT
# building, by reusing the engine's own contracts (survey_readiness for required +
# defaults, generate.lint for honest input, resolve_modalities_detail for the
# zero-modality abort). These tests pin that the prediction agrees with what the build
# would actually do, and the CLI smoke proves the operator path on the clean fixture.
echo "--- survey pre-flight validator — deliverable A contract (no creds, no SDK) ---"
python3 -m unittest tests.test_validate >/dev/null 2>&1 \
  || fail "survey validator test suite failed (tests/test_validate.py)"
python3 scripts/validate_survey.py fixtures/northstar-denver/survey.json >/dev/null \
  || fail "validate_survey.py failed on the clean northstar fixture"
green "PASS  survey validator — required + honesty + modality-abort pre-flight"
echo

# Operator build wrapper (concierge-beta deliverable B). The operator's one-command
# validate → build → honesty-receipt. These tests pin that a clean survey yields a
# real site + an out-of-tree receipt, a bad survey is stopped at pre-flight with
# NOTHING built, and the publish step is a gated pointer (never a deploy). The CLI
# smoke runs the whole chain on the synthetic northstar fixture into a throwaway dir
# so the repo tree stays pristine.
echo "--- operator build wrapper — deliverable B contract (no creds, no SDK) ---"
python3 -m unittest tests.test_concierge_build >/dev/null 2>&1 \
  || fail "operator build wrapper test suite failed (tests/test_concierge_build.py)"
_cbtmp="$(mktemp -d)"
python3 scripts/concierge_build.py fixtures/northstar-denver/survey.json \
  --sites-dir "$_cbtmp/sites" --receipt-out "$_cbtmp/receipt.md" --date 2026-06-15 >/dev/null \
  || { rm -rf "$_cbtmp"; fail "concierge_build.py CLI failed on the clean northstar fixture"; }
[ -f "$_cbtmp/sites/north-star-counseling/index.html" ] && [ -f "$_cbtmp/receipt.md" ] \
  || { rm -rf "$_cbtmp"; fail "concierge_build.py did not produce both site + receipt"; }
rm -rf "$_cbtmp"
green "PASS  operator build wrapper — validate→build→receipt, publish gated, nothing built on a bad survey"
echo

# Cloud Run deploy-context generator (concierge-beta stream 7 — publish reconcile).
# The proven publish runbook (docs/WEBSITE_PUBLISH_RUNBOOK.md §2) deploys a built site
# to Cloud Run with a "tiny nginx Dockerfile" that was DESCRIBED but generated nowhere —
# so the Cloud Run leg could not run from code. render_run_context.py is that generator;
# these tests pin the context it writes, and the smoke builds the synthetic northstar
# site then renders a real deploy context from it (Dockerfile + nginx.conf + the copied
# site), asserting the SPA fallback + port the runbook needs. Deterministic, no network,
# no gcloud — the actual `gcloud run deploy` stays Matthew-gated.
echo "--- Cloud Run deploy-context generator — publish reconcile (no creds, no gcloud) ---"
python3 -m unittest tests.test_render_run_context >/dev/null 2>&1 \
  || fail "Cloud Run deploy-context test suite failed (tests/test_render_run_context.py)"
_rctmp="$(mktemp -d)"
python3 scripts/concierge_build.py fixtures/northstar-denver/survey.json \
  --sites-dir "$_rctmp/sites" --receipt-out "$_rctmp/receipt.md" --date 2026-06-15 >/dev/null \
  || { rm -rf "$_rctmp"; fail "concierge_build.py CLI failed building the render-context fixture"; }
python3 scripts/render_run_context.py "$_rctmp/sites/north-star-counseling" \
  --out "$_rctmp/ctx" >/dev/null \
  || { rm -rf "$_rctmp"; fail "render_run_context.py failed on the built northstar site"; }
{ [ -f "$_rctmp/ctx/Dockerfile" ] && [ -f "$_rctmp/ctx/nginx.conf" ] \
  && [ -f "$_rctmp/ctx/site/index.html" ]; } \
  || { rm -rf "$_rctmp"; fail "render_run_context.py did not produce Dockerfile + nginx.conf + site/"; }
grep -qF 'try_files $uri $uri/ /index.html' "$_rctmp/ctx/nginx.conf" \
  || { rm -rf "$_rctmp"; fail "rendered nginx.conf is missing the SPA try_files fallback"; }
grep -qF 'EXPOSE 8080' "$_rctmp/ctx/Dockerfile" \
  || { rm -rf "$_rctmp"; fail "rendered Dockerfile is missing EXPOSE 8080"; }
rm -rf "$_rctmp"
green "PASS  Cloud Run deploy-context — Dockerfile + nginx SPA-fallback + copied site, gcloud gated"
echo

green "==================================="
green "PROVE PASSED — all ${#FIXTURES[@]} fixtures GREEN + staff + brain seam + refusals + receipt + validate + operator + run-context"
green "==================================="
