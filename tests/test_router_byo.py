#!/usr/bin/env python3
"""test_router_byo — router.route()'s BYO/plane gating, proven WITHOUT a network.

We never call a live provider: the per-provider backends are patched to a fake,
and the consent store is redirected to a tmp dir. What we prove is the GATE wiring:

  - PHI plane refuses a non-BAA provider (openai/anthropic/xai) — even with consent.
  - PHI plane refuses a BAA provider until the BAA is attested; allows it after.
  - Marketing plane refuses a BYO-keyed provider until billing consent; allows after.
  - A BLOCKED choice is NEVER silently downgraded to vertex/ollama (fail closed).
  - The default (no provider) route is unchanged.
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from unittest import mock

_REPO = pathlib.Path(__file__).resolve().parent.parent
_COCKPIT = _REPO / "cockpit"
if str(_COCKPIT) not in sys.path:
    sys.path.insert(0, str(_COCKPIT))

import providers as PR  # noqa: E402
import router as R       # noqa: E402


class _RouterGateBase(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        # Redirect the module-level consent store to an isolated tmp dir.
        self._store = PR.ConsentStore(base_dir=self._td.name)
        self._patch_store = mock.patch.object(R, "_BYO", self._store)
        self._patch_store.start()
        self.addCleanup(self._patch_store.stop)
        # Patch the BYO dispatcher so a permitted call returns a deterministic body
        # (no provider is ever actually contacted).
        self._patch_dispatch = mock.patch.object(
            R, "_dispatch_byo", lambda provider, *a, **k: (f"FAKE[{provider}]", "fake-model")
        )
        self._patch_dispatch.start()
        self.addCleanup(self._patch_dispatch.stop)


class TestPhiPlaneGate(_RouterGateBase):
    def test_consumer_provider_blocked_for_phi_even_with_consent(self):
        self._store.set("anthropic", consent=True, baa_attested=True, key="sk-x")
        out = R.route("chat", "hi", provider="anthropic", plane=PR.PLANE_PHI)
        self.assertEqual(out["backend"], "blocked")
        self.assertIn("BAA", out["text"])

    def test_baa_provider_blocked_until_attested(self):
        self._store.set("vertex", consent=True, baa_attested=False)
        out = R.route("chat", "hi", provider="vertex", plane=PR.PLANE_PHI)
        self.assertEqual(out["backend"], "blocked")

    def test_baa_provider_runs_once_attested(self):
        self._store.set("vertex", consent=True, baa_attested=True)
        out = R.route("chat", "hi", provider="vertex", plane=PR.PLANE_PHI)
        self.assertEqual(out["backend"], "vertex")
        self.assertEqual(out["text"], "FAKE[vertex]")


class TestMarketingPlaneGate(_RouterGateBase):
    def test_byo_keyed_blocked_until_consent(self):
        self._store.set("openai", consent=False, baa_attested=False, key="sk-x")
        out = R.route("chat", "hi", provider="openai", plane=PR.PLANE_MARKETING)
        self.assertEqual(out["backend"], "blocked")
        self.assertIn("consent", out["text"].lower())

    def test_byo_keyed_runs_once_consented(self):
        self._store.set("xai", consent=True, baa_attested=False, key="xai-x")
        out = R.route("chat", "hi", provider="xai", plane=PR.PLANE_MARKETING)
        self.assertEqual(out["backend"], "xai")
        self.assertEqual(out["text"], "FAKE[xai]")


class TestFailClosed(_RouterGateBase):
    def test_blocked_is_never_downgraded_to_another_backend(self):
        # The whole point: a refused PHI choice must not quietly answer on ollama/vertex.
        self._store.set("openai", consent=True, baa_attested=True, key="sk-x")
        out = R.route("chat", "hi", provider="openai", plane=PR.PLANE_PHI)
        self.assertEqual(out["backend"], "blocked")
        self.assertIsNone(out["model"])
        self.assertNotIn(out["backend"], ("vertex", "ollama", "openai"))


class TestDefaultRouteUnchanged(unittest.TestCase):
    def test_no_provider_uses_default_vertex_path(self):
        # With no provider override, the existing vertex->ollama route runs as before.
        with mock.patch.object(R, "_call_vertex", return_value="DEFAULT-VERTEX"):
            out = R.route("chat", "hello")
        self.assertEqual(out["backend"], "vertex")
        self.assertEqual(out["text"], "DEFAULT-VERTEX")

    def test_no_provider_falls_back_to_ollama_when_vertex_down(self):
        with mock.patch.object(R, "_call_vertex", return_value=None), \
             mock.patch.object(R, "_call_ollama", return_value="FLOOR-OLLAMA"):
            out = R.route("chat", "hello")
        self.assertEqual(out["backend"], "ollama")
        self.assertEqual(out["text"], "FLOOR-OLLAMA")


if __name__ == "__main__":
    unittest.main(verbosity=2)
