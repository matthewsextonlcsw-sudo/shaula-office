#!/usr/bin/env bash
# verify-harden.sh — Shaula HIPAA guardrail gate. Exits NONZERO if any guardrail is off.
# Spec/evidence: docs/SECURITY_AUDIT_hermes.md. Keys verified vs vendor/hermes/cli-config.yaml.example.
# Phase 1: static config + live-ENV checks. Phase 1-runtime TODO (see docs/PHASE1_harden.md):
#   docker backend actually live · egress allowlist enforced · HERMES_HOME on encrypted vol · dep bumps install-tested.
set -uo pipefail
CFG="${1:-config/shaula-harden.yaml}"
fail=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad() { printf '  \033[31m✗\033[0m %s — %s\n' "$1" "$2"; fail=1; }
[ -f "$CFG" ] || { echo "FATAL: $CFG not found"; exit 2; }

# assert "key: value" at any indent, tolerant of quotes + trailing comment
kv() {
  if grep -Eq "^[[:space:]]*$1:[[:space:]]*\"?$2\"?[[:space:]]*(#.*)?$" "$CFG"; then ok "$1: $2"; else bad "$1" "expected '$2'"; fi
}

echo "== Shaula hardening gate =="

echo "-- model: house-nothing (no Bedrock, no our-cloud; local OR their-Vertex BAA) --"
kv provider custom
# Brain must be the LOCAL floor (localhost) OR the therapist's OWN Vertex (aiplatform.googleapis.com, their BAA).
if grep -Eq '^[[:space:]]*base_url:[[:space:]]*"?(http://(localhost|127\.0\.0\.1)|https://[a-z0-9.-]*aiplatform\.googleapis\.com)' "$CFG"; then
  ok "base_url is local OR the therapist's Vertex (BAA)"
else bad "base_url" "must be local OR their Vertex (aiplatform.googleapis.com)"; fi
# The consumer Gemini endpoint has NO BAA — banned (Vertex only).
grep -Eqi 'generativelanguage\.googleapis\.com' "$CFG" && bad "base_url" "consumer Gemini endpoint (no BAA) — Vertex only" || ok "no consumer-Gemini endpoint"
grep -Eqi '^[[:space:]]*provider:[[:space:]]*"?bedrock' "$CFG" && bad "provider" "is bedrock — house-nothing violated" || ok "provider is not bedrock"
# (a Bedrock/AWS base_url can't pass the positive local-OR-Vertex check above, so no separate grep — that grep would false-match the 'NEVER Bedrock' comment.)

echo "-- shell sandbox (container, no PHI mount) --"
kv backend docker
kv docker_mount_cwd_to_workspace false

echo "-- self-evolution frozen --"
kv creation_nudge_interval 0
kv inline_shell false
kv memory_enabled false
kv user_profile_enabled false
kv nudge_interval 0
kv flush_min_turns 0
n=$(grep -cE '^[[:space:]]*enabled:[[:space:]]*false[[:space:]]*(#.*)?$' "$CFG")
[ "$n" -ge 2 ] && ok "curator.enabled + model_catalog.enabled = false" || bad "enabled flags" "curator + model_catalog must both be false ($n found)"

echo "-- toolsets: skills + memory disabled --"
if grep -Eq '^[[:space:]]*disabled_toolsets:.*skills' "$CFG" && grep -Eq '^[[:space:]]*disabled_toolsets:.*memory' "$CFG"; then
  ok "disabled_toolsets has skills + memory"
else bad "disabled_toolsets" "must disable skills AND memory"; fi

echo "-- approvals: human-in-the-loop --"
kv mode manual

echo "-- live ENV invariants --"
[ -z "${HERMES_YOLO_MODE:-}" ] && ok "HERMES_YOLO_MODE unset" || bad HERMES_YOLO_MODE "must be unset"
for v in TELEGRAM_BOT_TOKEN SLACK_BOT_TOKEN DISCORD_BOT_TOKEN WHATSAPP_ENABLED EMAIL_ENABLED \
         HERMES_LANGFUSE_PUBLIC_KEY HERMES_LANGFUSE_SECRET_KEY GOOGLE_API_KEY GEMINI_API_KEY; do
  [ -z "${!v:-}" ] && ok "$v unset" || bad "$v" "must stay unset"
done

echo
[ "$fail" -eq 0 ] && { printf '\033[32mPASS\033[0m — all guardrails set.\n'; exit 0; } \
                  || { printf '\033[31mFAIL\033[0m — guardrail(s) off (see ✗).\n'; exit 1; }
