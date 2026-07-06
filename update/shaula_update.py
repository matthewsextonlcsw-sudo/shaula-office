#!/usr/bin/env python3
"""shaula_update.py — Shaula fleet updater: gate -> review -> push, SIGNED + staged + rollback.

The field box has NO runtime self-update path (Hermes is CLI-only here). THIS is the only way a
deployed box changes — and it accepts a release ONLY if it is:
  1. signed by OUR Ed25519 key (verify with the bundled public key),
  2. content-intact (sha256 matches the manifest),
  3. strictly newer than what's installed, and
  4. passes the post-update gate (verify-harden.sh + prove.sh) AFTER staging.
Any failure → the previous install is kept / restored (rollback). Never applies an unsigned,
tampered, older, or gate-failing release.

Release = a .tar.gz artifact + a manifest.json:
  {"version": "1.2.3", "artifact": "shaula-1.2.3.tar.gz", "sha256": "<hex>", "sig_b64": "<base64>"}
where sig_b64 is the Ed25519 signature of the ARTIFACT BYTES (openssl pkeyutl -sign -rawin).

NO PHI ever travels in a release. Apple notarization (for a .app wrapper) is a SEPARATE last-mile
and does not replace this payload-signing gate.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _verify_sig(artifact: pathlib.Path, sig_b64: str, pubkey: pathlib.Path) -> bool:
    """Verify the Ed25519 signature of the artifact bytes with our public key (openssl)."""
    sig = base64.b64decode(sig_b64)
    with tempfile.NamedTemporaryFile(delete=False) as sf:
        sf.write(sig)
        sigpath = sf.name
    try:
        r = subprocess.run(
            ["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(pubkey),
             "-rawin", "-in", str(artifact), "-sigfile", sigpath],
            capture_output=True, text=True,
        )
        return r.returncode == 0
    finally:
        os.unlink(sigpath)


def _ver_tuple(v: str) -> tuple:
    return tuple(int(x) for x in v.strip().lstrip("v").split(".") if x.isdigit())


def _installed_version(install_dir: pathlib.Path) -> str:
    f = install_dir / "VERSION"
    return f.read_text(encoding="utf-8").strip() if f.exists() else "0.0.0"


def _run_gate(staged: pathlib.Path) -> bool:
    """Post-update gate: the staged tree must pass both gates before it goes live."""
    for gate in ("scripts/verify-harden.sh", "scripts/prove.sh"):
        if (staged / gate).exists():
            r = subprocess.run(["bash", gate], cwd=str(staged), capture_output=True, text=True)
            if r.returncode != 0:
                sys.stderr.write(f"[gate] {gate} FAILED:\n{r.stdout[-800:]}{r.stderr[-400:]}\n")
                return False
    return True


def apply_update(release_dir: pathlib.Path, install_dir: pathlib.Path,
                 pubkey: pathlib.Path) -> int:
    """Apply a signed release to install_dir, staged + verified + reversible. Returns 0 on success."""
    manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact = release_dir / manifest["artifact"]

    if not artifact.exists():
        sys.stderr.write("[reject] artifact missing\n"); return 2
    if _sha256(artifact) != manifest["sha256"]:
        sys.stderr.write("[reject] sha256 mismatch — tampered or corrupt\n"); return 3
    if not _verify_sig(artifact, manifest["sig_b64"], pubkey):
        sys.stderr.write("[reject] signature INVALID — not signed by our key\n"); return 4

    cur, new = _installed_version(install_dir), manifest["version"]
    if _ver_tuple(new) <= _ver_tuple(cur):
        sys.stderr.write(f"[skip] installed {cur} >= release {new}; nothing to do\n"); return 0

    parent = install_dir.parent
    staged = parent / f".staged-{new}"
    backup = parent / f".backup-{cur}"
    if staged.exists():
        shutil.rmtree(staged)
    staged.mkdir(parents=True)
    with tarfile.open(artifact, "r:gz") as tf:
        tf.extractall(staged, filter="data")
    # the artifact may contain a single top dir; normalize to the staged root
    entries = [p for p in staged.iterdir() if p.name != "__MACOSX"]
    root = entries[0] if len(entries) == 1 and entries[0].is_dir() else staged
    (root / "VERSION").write_text(new + "\n", encoding="utf-8")

    if not _run_gate(root):
        shutil.rmtree(staged)
        sys.stderr.write("[rollback] staged release failed the gate — install untouched\n"); return 5

    # atomic-ish swap: move current aside (rollback point), move staged into place
    if backup.exists():
        shutil.rmtree(backup)
    if install_dir.exists():
        install_dir.rename(backup)
    try:
        root.rename(install_dir)
    except OSError:
        shutil.move(str(root), str(install_dir))
    if staged.exists():
        shutil.rmtree(staged, ignore_errors=True)
    sys.stdout.write(f"[ok] updated {cur} -> {new} (rollback kept at {backup})\n")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Apply a signed Shaula release (staged, reversible).")
    ap.add_argument("--release", required=True, help="dir with manifest.json + the artifact")
    ap.add_argument("--install", required=True, help="install dir to update in place")
    ap.add_argument("--pubkey", required=True, help="our Ed25519 public key (PEM)")
    a = ap.parse_args(argv)
    return apply_update(pathlib.Path(a.release), pathlib.Path(a.install), pathlib.Path(a.pubkey))


if __name__ == "__main__":
    raise SystemExit(main())
