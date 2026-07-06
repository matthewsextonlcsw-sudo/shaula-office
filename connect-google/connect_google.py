#!/usr/bin/env python3
"""connect_google.py — "Connect Google" for a Shaula box (Phase 4).

Authenticates the therapist's OWN Google account via the OAuth 2.0 **loopback / installed-app
flow with PKCE** — the correct flow for a local desktop box that has no public redirect URL. The
box then operates inside *their* Google tenant (Workspace + Vertex) under *their* Google BAA. We
house nothing: the refresh token lives only in the box's encrypted HERMES_HOME, never in the repo,
never in chat.

WHY THIS FLOW
  A therapist installs a local box. There is no server to host an OAuth redirect, so we use the
  installed-app loopback flow: the box opens the therapist's browser to Google's consent screen,
  Google redirects back to http://127.0.0.1:<random-port>, the box exchanges the code (PKCE) for
  tokens, and stores the refresh token locally. No client secret needs to be confidential (PKCE),
  but we still keep the client config + tokens out of git.

SECURITY
  - Tokens stored at $HERMES_HOME/google-creds.json, chmod 600, on the encrypted volume.
  - The OAuth client config (downloaded from the therapist's Google Cloud Console) is read from a
    path or env — never committed, never pasted into chat.
  - Vertex-only for the model path elsewhere; this module only establishes the Google connection.

USAGE
  python3 connect_google.py connect --client /path/to/oauth_client.json
  python3 connect_google.py status
  python3 connect_google.py revoke

Optional dependency: google-auth-oauthlib (see requirements-connect-google.txt). The box runs
without it; this feature is off until a therapist connects their Google.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.request

# Slice #1 scopes: identify the account + prove Workspace access. cloud-platform (Vertex) is added
# when the their-Google model path is wired — keep the consent minimal until then.
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/drive.metadata.readonly",  # proof of Workspace access
    "https://www.googleapis.com/auth/cloud-platform",           # Vertex (their-Google Gemini) model path
]

_USERINFO = "https://www.googleapis.com/oauth2/v3/userinfo"


def _store_path() -> pathlib.Path:
    home = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
    return pathlib.Path(home) / "google-creds.json"


def _client_path(arg: str | None) -> pathlib.Path:
    p = arg or os.environ.get("SHAULA_GOOGLE_CLIENT")
    if not p:
        sys.exit("ERROR: provide the OAuth client JSON via --client or $SHAULA_GOOGLE_CLIENT "
                 "(download it from your Google Cloud Console; never paste it in chat).")
    path = pathlib.Path(p).expanduser()
    if not path.exists():
        sys.exit(f"ERROR: OAuth client file not found: {path}")
    return path


def connect(client_arg: str | None) -> int:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        sys.exit("ERROR: pip install -r requirements-connect-google.txt first "
                 "(google-auth-oauthlib is an optional dependency).")
    client = _client_path(client_arg)
    flow = InstalledAppFlow.from_client_secrets_file(str(client), scopes=SCOPES)
    # Loopback: opens the therapist's browser; they approve; redirect to 127.0.0.1:<port>.
    creds = flow.run_local_server(port=0, prompt="consent", open_browser=True)

    store = _store_path()
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(creds.to_json(), encoding="utf-8")
    os.chmod(store, 0o600)

    email = _whoami(creds.token)
    print(json.dumps({"ok": True, "connected_as": email, "store": str(store),
                      "scopes": SCOPES}, indent=2))
    return 0


def _whoami(access_token: str) -> str | None:
    req = urllib.request.Request(_USERINFO, headers={"Authorization": f"Bearer {access_token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()).get("email")
    except Exception:
        return None


def status() -> int:
    store = _store_path()
    if not store.exists():
        print(json.dumps({"connected": False, "store": str(store)}))
        return 0
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        # Without the lib we can still report that a token file exists (no refresh).
        print(json.dumps({"connected": True, "store": str(store), "note": "lib not installed; cannot refresh"}))
        return 0
    creds = Credentials.from_authorized_user_file(str(store), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        store.write_text(creds.to_json(), encoding="utf-8")
        os.chmod(store, 0o600)
    print(json.dumps({"connected": True, "connected_as": _whoami(creds.token),
                      "store": str(store)}, indent=2))
    return 0


def revoke() -> int:
    store = _store_path()
    if store.exists():
        store.unlink()
        print(json.dumps({"revoked": True, "store": str(store)}))
    else:
        print(json.dumps({"revoked": False, "note": "nothing stored"}))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Connect a therapist's own Google account to the box.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("connect", help="run the loopback OAuth flow")
    c.add_argument("--client", help="path to the OAuth client JSON (or $SHAULA_GOOGLE_CLIENT)")
    sub.add_parser("status", help="show the stored connection")
    sub.add_parser("revoke", help="delete the stored connection")
    a = ap.parse_args(argv)
    if a.cmd == "connect":
        return connect(a.client)
    if a.cmd == "status":
        return status()
    if a.cmd == "revoke":
        return revoke()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
