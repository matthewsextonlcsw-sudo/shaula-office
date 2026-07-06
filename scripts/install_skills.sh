#!/usr/bin/env bash
# install_skills.sh — install Shaula's skills into the box's Hermes skills dir.
#
# Hermes loads skills from $HERMES_HOME/skills/<category>/<name>/SKILL.md (and seeds them into
# profiles). We ship our skills in the repo under skills/<name>/ and copy them into the "shaula"
# category here. Idempotent. (Copy-based rather than `hermes skills install` so it works offline
# and isn't tripped by the macOS /tmp→/private/tmp realpath check; the scan-on-install is run
# separately during vetting — every bundled skill here is first-party or vetted MIT.)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_HOME="${HERMES_HOME:-/tmp/shaula-hermes-home}"
DEST="$HERMES_HOME/skills/shaula"
mkdir -p "$DEST"

# First-party (built this project) + vetted third-party (karpathy-guidelines, MIT).
SKILLS=(website-builder blog-scaffolder geo-seo-pass remotion-video karpathy-guidelines brand-kit clip-picker meeting-notes faq-bot)

n=0
for s in "${SKILLS[@]}"; do
  src="$ROOT/skills/$s"
  if [ -d "$src" ] && [ -f "$src/SKILL.md" ]; then
    rm -rf "${DEST:?}/$s"
    cp -R "$src" "$DEST/$s"
    echo "  ✓ shaula/$s"
    n=$((n+1))
  else
    echo "  ✗ missing repo skill (no SKILL.md): $s" >&2
  fi
done
echo "Installed $n skill(s) into $DEST"
