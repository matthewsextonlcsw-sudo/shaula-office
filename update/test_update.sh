#!/usr/bin/env bash
# test_update.sh — proves update/shaula_update.py end to end with a REAL Ed25519 key:
#   signed apply · reject tampered · reject unsigned-by-us · skip older · gate-rollback.
# Synthetic releases only, no PHI. Run from anywhere.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
UP="$HERE/shaula_update.py"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail=0
ok(){ printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad(){ printf '  \033[31m✗\033[0m %s\n' "$1"; fail=1; }

openssl genpkey -algorithm ed25519 -out "$T/priv.pem" 2>/dev/null
openssl pkey -in "$T/priv.pem" -pubout -out "$T/pub.pem" 2>/dev/null
openssl genpkey -algorithm ed25519 -out "$T/evil.pem" 2>/dev/null

make_release(){ # <ver> <srcdir> <signkey> -> echoes the release dir
  local ver="$1" src="$2" key="$3"
  local rel="$T/rel-$ver"
  mkdir -p "$rel"; local art="$rel/shaula-$ver.tar.gz"
  tar -czf "$art" -C "$src" .
  local sha; sha=$(shasum -a 256 "$art" | awk '{print $1}')
  openssl pkeyutl -sign -inkey "$key" -rawin -in "$art" -out "$T/sig.bin" 2>/dev/null
  local sig; sig=$(base64 < "$T/sig.bin" | tr -d '\n')
  printf '{"version":"%s","artifact":"shaula-%s.tar.gz","sha256":"%s","sig_b64":"%s"}' \
    "$ver" "$ver" "$sha" "$sig" > "$rel/manifest.json"
  echo "$rel"
}
run(){ python3 "$UP" --release "$1" --install "$INST" --pubkey "$T/pub.pem" >/dev/null 2>&1; }
ver(){ cat "$INST/VERSION" 2>/dev/null; }

INST="$T/install"; mkdir -p "$INST"; echo "1.0.0" > "$INST/VERSION"; echo v1 > "$INST/marker.txt"

s="$T/s2"; mkdir -p "$s"; echo v2-content > "$s/marker.txt"
run "$(make_release 2.0.0 "$s" "$T/priv.pem")" && [ "$(ver)" = "2.0.0" ] && grep -q v2-content "$INST/marker.txt" \
  && ok "signed apply 1.0.0 -> 2.0.0" || bad "signed apply"

s="$T/s3"; mkdir -p "$s"; echo v3 > "$s/marker.txt"; R=$(make_release 3.0.0 "$s" "$T/priv.pem")
echo tampered >> "$R/shaula-3.0.0.tar.gz"
run "$R" && bad "tampered accepted" || { [ "$(ver)" = "2.0.0" ] && ok "tampered rejected, install unchanged" || bad "tampered changed install"; }

s="$T/s4"; mkdir -p "$s"; echo v4 > "$s/marker.txt"
run "$(make_release 4.0.0 "$s" "$T/evil.pem")" && bad "evil-signed accepted" \
  || { [ "$(ver)" = "2.0.0" ] && ok "evil signature rejected" || bad "evil changed install"; }

s="$T/s0"; mkdir -p "$s"; echo old > "$s/marker.txt"
run "$(make_release 0.5.0 "$s" "$T/priv.pem")" && [ "$(ver)" = "2.0.0" ] && ok "older release skipped" || bad "older not skipped"

s="$T/s5"; mkdir -p "$s/scripts"; echo v5 > "$s/marker.txt"; printf '#!/usr/bin/env bash\nexit 1\n' > "$s/scripts/verify-harden.sh"
run "$(make_release 5.0.0 "$s" "$T/priv.pem")" && bad "gate-failing accepted" \
  || { [ "$(ver)" = "2.0.0" ] && ok "gate-failing release rolled back, install @ 2.0.0" || bad "gate-rollback changed install"; }

echo
[ $fail -eq 0 ] && { echo "PASS — updater: signed apply · reject tampered/unsigned/older · gate-rollback."; exit 0; } \
                || { echo "FAIL"; exit 1; }
