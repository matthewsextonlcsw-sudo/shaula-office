#!/usr/bin/env bash
# e2e_synthetic.sh — end-to-end concierge-beta proof on a SYNTHETIC therapist.
#
# Drives the whole turnkey chain on the engine's own fictional practice
# (fixtures/northstar-denver — "Maya Restrepo", zero PHI):
#
#   survey.json  --concierge_build-->     sites/<slug>/ + honesty receipt
#                --render_run_context-->   Cloud Run deploy context (Dockerfile+nginx+site)
#   [--deploy]   --gcloud run deploy-->    live throwaway URL  --curl-->  verify 200
#                --teardown-->             service deleted (ALWAYS, even on failure)
#
# Default = LOCAL ONLY (no network, no creds, $0): proves the build -> receipt ->
# deploy-context chain and that the built site is honesty-clean — i.e. everything up
# to the gated deploy. `--deploy` adds the live throwaway leg and REQUIRES live gcloud
# auth (Matthew's `gcloud auth login`); the synthetic service is always torn down.
#
# NO PHI anywhere. NO real-therapist site ever goes live here — synthetic fixture only.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FIXTURE="fixtures/northstar-denver/survey.json"
SLUG="north-star-counseling"
DATE="2026-06-15"
REGION="us-central1"
PROJECT="${SHAULA_GCP_PROJECT:?set SHAULA_GCP_PROJECT}"
GCLOUD="$(command -v gcloud || echo /opt/homebrew/bin/gcloud)"
DEPLOY=0
[ "${1:-}" = "--deploy" ] && DEPLOY=1

green() { printf '\033[32m%s\033[0m\n' "$1"; }
red()   { printf '\033[31m%s\033[0m\n' "$1"; }
fail()  { red "E2E FAILED: $1"; exit 1; }

# The CSS-safe banned-phrase subset prove.sh scans rendered output with —
# DERIVED from engine/banned.py (the single source of truth) so this script and
# prove.sh cannot drift from each other or from the Python linter. Fail-closed:
# an empty or failed pattern aborts rather than scanning for nothing.
RENDER_BANNED="$(python3 -c 'import sys; sys.path.insert(0, "engine"); import banned; print(banned.render_banned_shell_regex())')" \
  || fail "could not derive RENDER_BANNED from engine/banned.py"
[ -n "$RENDER_BANNED" ] || fail "derived RENDER_BANNED is empty — refusing to scan with an empty pattern"

WORK="$(mktemp -d)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

BIZ="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["business_name"])' "$FIXTURE")"

echo "== concierge-beta end-to-end — synthetic therapist =="
echo "fixture: $FIXTURE  (synthetic '$BIZ', no PHI)"
echo "workdir: $WORK"
echo

# 1) validate -> build -> honesty receipt (the operator's one command)
echo "--- 1/4  build_site + honesty receipt (concierge_build.py) ---"
python3 scripts/concierge_build.py "$FIXTURE" \
  --sites-dir "$WORK/sites" --receipt-out "$WORK/receipt.md" --date "$DATE" >/dev/null \
  || fail "concierge_build.py failed on the synthetic fixture"
SITE="$WORK/sites/$SLUG"
[ -f "$SITE/index.html" ] || fail "no built site index.html"
[ -f "$SITE/app.js" ]     || fail "no built site app.js"
[ -f "$WORK/receipt.md" ] || fail "no honesty receipt"
grep -qi "honesty receipt" "$WORK/receipt.md" || fail "receipt missing its header"
# Fill actually ran: the practice's own business name reached the built app bundle.
grep -qF "$BIZ" "$SITE/app.js" || fail "built app.js is missing the practice business name"
green "PASS  built site + honesty receipt ($BIZ in the bundle)"
echo

# 2) render the Cloud Run deploy context (the runbook §2 piece)
echo "--- 2/4  render Cloud Run deploy context (render_run_context.py) ---"
CTX="$(python3 scripts/render_run_context.py "$SITE" --out "$WORK/ctx")"
{ [ -f "$CTX/Dockerfile" ] && [ -f "$CTX/nginx.conf" ] && [ -f "$CTX/site/index.html" ]; } \
  || fail "deploy context incomplete (need Dockerfile + nginx.conf + site/index.html)"
grep -qF 'try_files $uri $uri/ /index.html' "$CTX/nginx.conf" || fail "nginx SPA fallback missing"
grep -qF 'EXPOSE 8080' "$CTX/Dockerfile" || fail "Dockerfile missing EXPOSE 8080"
green "PASS  deploy context ready"
echo

# 3) honesty: the built site carries no banned claim (independent re-scan)
echo "--- 3/4  honesty re-scan of the built site ---"
if grep -riE "$RENDER_BANNED" "$SITE/app.js" "$SITE/index.html" "$SITE/llms.txt" >/dev/null 2>&1; then
  grep -rinE "$RENDER_BANNED" "$SITE/app.js" "$SITE/index.html" "$SITE/llms.txt" || true
  fail "banned claim phrase in the built synthetic site"
fi
green "PASS  built site is honesty-clean"
echo

if [ "$DEPLOY" -eq 0 ]; then
  echo "--- 4/4  LOCAL ONLY (no --deploy) ---"
  echo "Live leg skipped. To prove it (requires live gcloud auth — 'gcloud auth login'):"
  echo "    bash scripts/e2e_synthetic.sh --deploy"
  echo "  which deploys a throwaway Cloud Run service from the context above, curls it,"
  echo "  and tears it down. The deploy context is at: $CTX"
  echo
  green "==================================="
  green "E2E PASSED (local) — build -> receipt -> deploy-context, honesty-clean, no PHI"
  green "live deploy+verify+teardown leg is gated on gcloud auth (re-run with --deploy)"
  green "==================================="
  exit 0
fi

# 4) LIVE throwaway leg — deploy, verify, ALWAYS teardown
SVC="shaula-e2e-$SLUG"; SVC="${SVC:0:58}"
echo "--- 4/4  LIVE throwaway deploy + verify + teardown (service: $SVC) ---"
# Fail fast with a clean message if auth is dead, before any partial work.
if ! timeout 30 "$GCLOUD" auth print-access-token >/dev/null 2>&1; then
  fail "gcloud auth is dead — run 'gcloud auth login' (Matthew), then re-run with --deploy"
fi

teardown_live() {
  echo "  tearing down $SVC ..."
  "$GCLOUD" run services delete "$SVC" --region "$REGION" --project "$PROJECT" -q >/dev/null 2>&1 || true
}
# From here on, any exit tears the throwaway service down first, then the workdir.
trap 'teardown_live; cleanup' EXIT

DEPLOY_OUT="$("$GCLOUD" run deploy "$SVC" --source "$CTX" --region "$REGION" \
  --allow-unauthenticated --project "$PROJECT" --quiet 2>&1)" \
  || { printf '%s\n' "$DEPLOY_OUT" | tail -8; fail "gcloud run deploy failed"; }
URL="$(printf '%s\n' "$DEPLOY_OUT" | grep -oE 'https://[a-z0-9.-]+\.run\.app' | head -1)"
[ -n "$URL" ] || { printf '%s\n' "$DEPLOY_OUT" | tail -8; fail "could not parse the run.app URL"; }
echo "  deployed: $URL"

# Verify live: index 200; assets served; honesty holds on the LIVE bytes; the
# practice's own data is actually being served (business name in the live app.js).
CODE="$(curl -s -o "$WORK/live.html" -w '%{http_code}' "$URL/" || echo 000)"
[ "$CODE" = "200" ] || fail "live index returned HTTP $CODE"
ACODE="$(curl -s -o "$WORK/live.app.js" -w '%{http_code}' "$URL/app.js" || echo 000)"
[ "$ACODE" = "200" ] || fail "live app.js returned HTTP $ACODE"
grep -qF "$BIZ" "$WORK/live.app.js" || fail "live app.js missing the practice business name"
if grep -riE "$RENDER_BANNED" "$WORK/live.html" "$WORK/live.app.js" >/dev/null 2>&1; then
  fail "banned claim phrase in the LIVE served bytes"
fi
green "PASS  live $URL -> HTTP 200, '$BIZ' served, honesty-clean"
echo

# Teardown now (explicitly), then confirm it actually went.
teardown_live
trap cleanup EXIT
sleep 3
if "$GCLOUD" run services describe "$SVC" --region "$REGION" --project "$PROJECT" >/dev/null 2>&1; then
  red "WARN: $SVC still present after teardown — verify + delete manually"
else
  green "PASS  $SVC torn down — no throwaway service left running"
fi
echo
green "==================================="
green "E2E PASSED (live) — synthetic deploy -> HTTP 200 -> torn down, honesty-clean, no PHI"
green "==================================="
