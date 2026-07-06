#!/usr/bin/env bash
# install-hub-skills.sh — install the curated Hermes-hub skills into the box (HERMES_HOME).
# Idempotent. Trusted/official only (see config/hub-skills.txt). Runs the Hermes security scan per skill.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES="$ROOT/vendor/hermes/.venv-shaula/bin/hermes"
MANIFEST="$ROOT/config/hub-skills.txt"
[ -x "$HERMES" ] || { echo "install-hub-skills: hermes not found at $HERMES" >&2; exit 1; }
[ -f "$MANIFEST" ] || { echo "install-hub-skills: $MANIFEST missing" >&2; exit 1; }

# Canonicalize HERMES_HOME — macOS /tmp is a symlink to /private/tmp, and the installer's subpath
# check rejects the mismatch ("not in the subpath of ..."). pwd -P resolves it so install completes clean.
export HERMES_HOME="$(cd "${HERMES_HOME:-/tmp/shaula-hermes-home}" && pwd -P)"
echo "HERMES_HOME=$HERMES_HOME"

fail=0
grep -vE '^[[:space:]]*#|^[[:space:]]*$' "$MANIFEST" | awk '{print $1}' | while read -r id; do
  [ -n "$id" ] || continue
  echo "── installing: $id"
  if "$HERMES" skills install "$id" --yes --category office 2>&1 | tail -3; then :; else echo "  (warn: $id reported an issue)"; fi
done

echo "── office skills now present:"
"$HERMES" skills list 2>/dev/null | grep -iE "docx|pdf|pptx|xlsx" || { echo "NONE — install failed"; exit 1; }
echo "install-hub-skills: done."
