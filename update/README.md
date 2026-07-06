# Shaula fleet updater (gate → review → push)

The field box has **no runtime self-update path** (Hermes is CLI-only here). This is the *only* way a
deployed box changes — and it accepts a release only if it is **our-signed, intact, newer, and
gate-passing**.

## Flow
1. Build a release: a `.tar.gz` of the box + `manifest.json` = `{version, artifact, sha256, sig_b64}`.
2. **Sign** the artifact with our Ed25519 private key (kept offline / in a secret manager — **never** in the repo).
3. The box runs `shaula_update.py --release <dir> --install <dir> --pubkey pub.pem`. It applies the
   release **only if**: signed by our key, sha256-intact, strictly newer, **and** the staged tree passes
   `verify-harden.sh` + `prove.sh`. Otherwise it rejects/rolls back. The previous install is kept for rollback.

## Sign a release (operator)
```bash
openssl genpkey -algorithm ed25519 -out shaula-release-priv.pem      # ONE TIME — keep offline
openssl pkey -in shaula-release-priv.pem -pubout -out update/pub.pem # ship pub.pem inside the box
tar -czf shaula-<v>.tar.gz -C <box-dir> .
openssl pkeyutl -sign -inkey shaula-release-priv.pem -rawin -in shaula-<v>.tar.gz -out sig.bin
# manifest.json: {"version":"<v>","artifact":"shaula-<v>.tar.gz",
#                 "sha256":"<shasum -a 256>","sig_b64":"<base64 sig.bin>"}
```

## Verification
`update/test_update.sh` proves — with a real Ed25519 key — signed apply · reject tampered · reject
unsigned-by-us · skip older · **gate-rollback**. Runs in CI on every push.

## The Apple-notarization gate (your identity)
If the box also ships as a notarized macOS **.app**, that wrapper needs **Apple Developer
signing/notarization** (your account) — a SEPARATE last-mile that does **not** replace this
payload-signing gate. The update-payload security above is fully autonomous + tested; only the `.app`
notarization is gated on you.
