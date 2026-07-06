"""svc test harness — local backend, fake brain, fake bucket. NO network.

One import generation, ever. (The first version popped svc.* from
sys.modules per test; `from . import runner` then bound the STALE package
ATTRIBUTE from generation 1 — IMPORT_FROM checks package attrs before
importing — so the runner wrote to a dead tmp dir. Import once; isolate
tests with unique practice ids instead.)
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Env BEFORE the one-and-only svc import generation.
_TMP = tempfile.mkdtemp(prefix="svc-test-")
os.environ.update(
    {
        "SHAULA_STATE_BACKEND": "local",
        "SHAULA_LOCAL_STATE": f"{_TMP}/state",
        "SHAULA_SITES_DIR": f"{_TMP}/sites",
        "SHAULA_INTERNAL_SECRET": "test-secret",
        # Hermetic: site builds use the deterministic floor — never a model
        # call. Brain-wiring tests inject fakes via runner._site_brain.
        "SHAULA_SITE_BRAIN": "off",
    }
)

SURVEY = json.loads(
    (REPO / "fixtures" / "northstar-denver" / "survey.json").read_text(encoding="utf-8")
)


@pytest.fixture()
def svc_env():
    import svc.config as config  # noqa: PLC0415
    import svc.store as store_mod  # noqa: PLC0415

    return {
        "config": config,
        "store": store_mod.store,
        "state_dir": pathlib.Path(_TMP) / "state",
        "sites_dir": pathlib.Path(_TMP) / "sites",
    }


@pytest.fixture()
def client(monkeypatch):
    """FastAPI TestClient with the brain + bucket faked out (per test)."""
    import svc.gemini as gemini  # noqa: PLC0415
    import svc.publisher as publisher  # noqa: PLC0415
    import svc.app as app_mod  # noqa: PLC0415

    calls = {"gemini": [], "uploads": []}

    def fake_generate(system, user, **kw):
        calls["gemini"].append({"system": system, "user": user})
        return (
            "A warm, honest deliverable about the requested topic.\n\n"
            "It describes the work plainly."
        )

    def fake_upload_dir(local, prefix):
        calls["uploads"].append(prefix)
        return 5

    monkeypatch.setattr(gemini, "generate_text", fake_generate)
    monkeypatch.setattr(publisher, "_upload_dir", fake_upload_dir)
    monkeypatch.setattr(
        publisher, "_bucket",
        lambda: (_ for _ in ()).throw(AssertionError("bucket touched in test")),
    )

    from fastapi.testclient import TestClient  # noqa: PLC0415

    # Context entry keeps ONE event loop alive across requests.
    with TestClient(app_mod.app) as test_client:
        test_client.headers.update({"x-internal-secret": "test-secret"})
        yield test_client, calls
