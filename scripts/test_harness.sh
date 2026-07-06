#!/usr/bin/env bash
# test_harness.sh — static assertions that the whole Shaula harness is installed + wired correctly.
# Fast, offline, no model calls, no network — safe for CI. (The LIVE brain round-trip is verified
# separately via `bin/shaula chat`; this gate proves the structure can't silently drift.)
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
fail=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad() { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=1; }
has() { grep -q "$1" "$2" 2>/dev/null; }

echo "== Shaula harness test =="

echo "-- launcher --"
[ -x bin/shaula ] && ok "bin/shaula is executable" || bad "bin/shaula missing/not executable"
has "GOOGLEAPIS_API_KEY" bin/shaula && ok "launcher mints the Vertex token" || bad "launcher missing token mint"
grep -qF -- "--local" bin/shaula && ok "launcher has the --local floor flag" || bad "launcher missing --local"

echo "-- brain config (D13: their-Vertex default, house-nothing) --"
CFG=config/shaula-harden.yaml
has 'api_mode: "chat_completions"' "$CFG" && ok "api_mode chat_completions" || bad "api_mode not chat_completions"
has "aiplatform.googleapis.com" "$CFG" && ok "base_url = their Vertex (BAA)" || bad "base_url not Vertex"
has "generativelanguage.googleapis.com" "$CFG" && bad "consumer Gemini endpoint present (no BAA)" || ok "no consumer-Gemini endpoint"
grep -qiE '^\s*(GOOGLE_API_KEY|GEMINI_API_KEY):' "$CFG" && bad "consumer key set in config" || ok "no consumer key in config"

echo "-- hardening gate --"
bash scripts/verify-harden.sh "$CFG" >/dev/null 2>&1 && ok "verify-harden PASSES" || bad "verify-harden FAILS"

echo "-- staff: 12 profiles, each with the CORE soul invariants --"
PROFILES="orchestrator website blog marketer reviewer analytics workspace frontdesk customer-service scribe biller clinical-admin"
nprof=0
for p in $PROFILES; do
  s="profiles/$p/SOUL.md"
  if [ -f "$s" ]; then nprof=$((nprof+1)); else bad "missing profile $p"; continue; fi
  has "HOUSE-NOTHING" "$s"        || bad "$p soul missing HOUSE-NOTHING"
  has "NEVER HANDLE A CRISIS" "$s" || bad "$p soul missing crisis rule"
  has "HONESTY ENGINE" "$s"       || bad "$p soul missing honesty rule"
done
[ "$nprof" -eq 12 ] && ok "12 profile souls present, each carrying the CORE rules" || bad "expected 12 profiles, found $nprof"
[ -x scripts/install_profiles.py ] || [ -f scripts/install_profiles.py ] && ok "profile factory present" || bad "profile factory missing"

echo "-- skills: 5 installed (built + vetted karpathy) --"
nsk=0
for sk in website-builder blog-scaffolder geo-seo-pass remotion-video karpathy-guidelines; do
  [ -f "skills/$sk/SKILL.md" ] && nsk=$((nsk+1)) || bad "missing skill $sk"
done
[ "$nsk" -eq 5 ] && ok "5 skills present with SKILL.md" || bad "expected 5 skills, found $nsk"
has "license: MIT" skills/karpathy-guidelines/SKILL.md && ok "karpathy-guidelines is MIT (vetted)" || bad "karpathy license not MIT"
[ -f scripts/install_skills.sh ] && ok "skill installer present" || bad "skill installer missing"

echo "-- engine geo unit tests --"
python3 -m unittest tests.test_geo >/dev/null 2>&1 && ok "tests/test_geo.py green" || bad "tests/test_geo.py FAILED"

echo "-- content engine still green (prove.sh references intact) --"
[ -x scripts/prove.sh ] && has "geo.py" scripts/prove.sh && ok "prove.sh wired with geo" || bad "prove.sh missing/geo not wired"

echo
[ "$fail" -eq 0 ] && { printf '\033[32mHARNESS OK\033[0m — all structural checks pass.\n'; exit 0; } \
                  || { printf '\033[31mHARNESS FAIL\033[0m — see ✗ above.\n'; exit 1; }
