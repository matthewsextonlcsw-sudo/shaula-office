#!/usr/bin/env python3
"""test_providers — the LLM provider registry + the two-plane gate.

The whole compliance story lives here, proven WITHOUT a network or a key:

  Two planes, one gate (Matthew's rule, 2026-06-16):
    - marketing (NO PHI): ANY provider, BYO key, but a keyed BYO provider needs a
      billing-consent ack first (Anthropic/OpenAI/xAI each bill differently).
    - phi (clinical perimeter): a BAA-COVERED provider ONLY, and the customer
      must attest the signed BAA. No BAA -> refused (HIPAA risk). Consumer
      ChatGPT / Grok are never BAA -> never touch PHI. Local (Ollama) is self-
      hosted (no third-party processor) so it is PHI-eligible with no external BAA.

  The consent store never hands a key back through get() -> logging a consent
  record can never leak the key.

Pure stdlib (`unittest`), credential-free. Runs:
    python3 -m pytest tests/test_providers.py -q
    python3 -m unittest tests.test_providers -v
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

# cockpit/ modules import each other by bare name (server.py inserts cockpit/ on
# sys.path at boot). Mirror that so `import providers` resolves.
_REPO = pathlib.Path(__file__).resolve().parent.parent
_COCKPIT = _REPO / "cockpit"
if str(_COCKPIT) not in sys.path:
    sys.path.insert(0, str(_COCKPIT))

import providers as PR  # noqa: E402


# =========================================================================== #
# 1. the registry is honest about who is BAA-covered
# =========================================================================== #
class TestRegistry(unittest.TestCase):
    def test_known_providers_present(self):
        ids = {p.id for p in PR.all()}
        self.assertEqual(
            ids, {"vertex", "azure_openai", "openai", "anthropic", "xai", "ollama"}
        )

    def test_baa_providers_are_phi_ok(self):
        # The only PHI-eligible providers: BAA third-parties + self-hosted local.
        for pid in ("vertex", "azure_openai", "ollama"):
            self.assertTrue(PR.get(pid).phi_ok, f"{pid} should be PHI-eligible")

    def test_consumer_providers_are_not_phi_ok(self):
        # No BAA -> never PHI. This is the unbreakable line.
        for pid in ("openai", "anthropic", "xai"):
            self.assertFalse(PR.get(pid).phi_ok, f"{pid} must NOT be PHI-eligible")

    def test_third_party_baa_providers_need_attestation_but_local_does_not(self):
        self.assertTrue(PR.get("vertex").needs_attestation)
        self.assertTrue(PR.get("azure_openai").needs_attestation)
        self.assertFalse(PR.get("ollama").needs_attestation)  # self-hosted, no 3rd party

    def test_byo_keyed_providers_flagged_and_carry_billing_facts(self):
        for pid in ("openai", "anthropic", "xai", "azure_openai"):
            p = PR.get(pid)
            self.assertTrue(p.needs_key, f"{pid} is BYO-keyed")
            self.assertTrue(p.billed_by, f"{pid} must name who bills")
        # vertex = their existing Google billing (no separate key here); ollama = free.
        self.assertFalse(PR.get("vertex").needs_key)
        self.assertFalse(PR.get("ollama").needs_key)

    def test_unknown_provider_is_none(self):
        self.assertIsNone(PR.get("gpt5-ultra-from-a-dream"))


# =========================================================================== #
# 2. the PHI gate — BAA-covered only, attested
# =========================================================================== #
class TestPhiGate(unittest.TestCase):
    def test_consumer_provider_refused_for_phi(self):
        for pid in ("openai", "anthropic", "xai"):
            d = PR.authorize(PR.PLANE_PHI, pid, baa_attested=True)
            self.assertFalse(d.allowed, f"{pid} must be refused for PHI")
            self.assertIn("BAA", d.reason)

    def test_baa_provider_refused_for_phi_without_attestation(self):
        d = PR.authorize(PR.PLANE_PHI, "vertex", baa_attested=False)
        self.assertFalse(d.allowed)
        self.assertIn("attest", d.reason.lower())

    def test_baa_provider_allowed_for_phi_with_attestation(self):
        d = PR.authorize(PR.PLANE_PHI, "vertex", baa_attested=True)
        self.assertTrue(d.allowed)

    def test_local_allowed_for_phi_without_external_baa(self):
        # Ollama is self-hosted: PHI never leaves the box, no third-party processor.
        d = PR.authorize(PR.PLANE_PHI, "ollama")
        self.assertTrue(d.allowed)

    def test_unknown_provider_refused_for_phi(self):
        d = PR.authorize(PR.PLANE_PHI, "nope")
        self.assertFalse(d.allowed)
        self.assertIn("unknown", d.reason.lower())


# =========================================================================== #
# 3. the marketing gate — any provider, BYO needs billing consent
# =========================================================================== #
class TestMarketingGate(unittest.TestCase):
    def test_keyed_provider_refused_without_consent(self):
        for pid in ("openai", "anthropic", "xai"):
            d = PR.authorize(PR.PLANE_MARKETING, pid, consent=False)
            self.assertFalse(d.allowed, f"{pid} needs billing consent")
            self.assertIn("consent", d.reason.lower())

    def test_keyed_provider_allowed_with_consent(self):
        for pid in ("openai", "anthropic", "xai"):
            d = PR.authorize(PR.PLANE_MARKETING, pid, consent=True)
            self.assertTrue(d.allowed, f"{pid} should run once consent is given")

    def test_no_key_providers_need_no_consent(self):
        # vertex (their Google) + ollama (local) just run.
        self.assertTrue(PR.authorize(PR.PLANE_MARKETING, "vertex").allowed)
        self.assertTrue(PR.authorize(PR.PLANE_MARKETING, "ollama").allowed)

    def test_unknown_provider_refused(self):
        self.assertFalse(PR.authorize(PR.PLANE_MARKETING, "nope").allowed)

    def test_bad_plane_is_refused_closed(self):
        # An unrecognized plane must fail closed, never default to allow.
        d = PR.authorize("clinical-ish-maybe", "vertex", baa_attested=True)
        self.assertFalse(d.allowed)


# =========================================================================== #
# 4. the consent store — round-trips, and NEVER leaks a key through get()
# =========================================================================== #
class TestConsentStore(unittest.TestCase):
    def _store(self, td):
        return PR.ConsentStore(base_dir=td)

    def test_record_and_read_consent(self):
        with tempfile.TemporaryDirectory() as td:
            s = self._store(td)
            s.set("anthropic", consent=True, baa_attested=False, key="sk-ant-SECRET")
            rec = s.get("anthropic")
            self.assertTrue(rec["consent"])
            self.assertFalse(rec["baa_attested"])

    def test_get_never_returns_the_key(self):
        with tempfile.TemporaryDirectory() as td:
            s = self._store(td)
            s.set("openai", consent=True, baa_attested=False, key="sk-openai-SECRET")
            rec = s.get("openai")
            # The whole serialized record must not contain the secret anywhere.
            self.assertNotIn("SECRET", repr(rec))
            self.assertNotIn("key", rec)

    def test_key_is_retrievable_only_through_the_explicit_key_accessor(self):
        with tempfile.TemporaryDirectory() as td:
            s = self._store(td)
            s.set("xai", consent=True, baa_attested=False, key="xai-SECRET")
            self.assertEqual(s.key("xai"), "xai-SECRET")

    def test_keys_file_is_owner_only(self):
        with tempfile.TemporaryDirectory() as td:
            s = self._store(td)
            s.set("openai", consent=True, baa_attested=False, key="sk-SECRET")
            mode = (pathlib.Path(td) / s.KEYS_FILE).stat().st_mode & 0o777
            self.assertEqual(mode, 0o600, f"keys file must be 0600, got {oct(mode)}")

    def test_missing_provider_reads_empty_not_crash(self):
        with tempfile.TemporaryDirectory() as td:
            s = self._store(td)
            self.assertEqual(s.get("never-set"), {"consent": False, "baa_attested": False})
            self.assertIsNone(s.key("never-set"))


# =========================================================================== #
# 5. end-to-end: store + gate together (the way the server will use it)
# =========================================================================== #
class TestStoreGateIntegration(unittest.TestCase):
    def test_phi_blocked_until_baa_attested_in_store(self):
        with tempfile.TemporaryDirectory() as td:
            s = PR.ConsentStore(base_dir=td)
            s.set("vertex", consent=True, baa_attested=False)
            rec = s.get("vertex")
            self.assertFalse(
                PR.authorize(PR.PLANE_PHI, "vertex", baa_attested=rec["baa_attested"]).allowed
            )
            s.set("vertex", consent=True, baa_attested=True)
            rec = s.get("vertex")
            self.assertTrue(
                PR.authorize(PR.PLANE_PHI, "vertex", baa_attested=rec["baa_attested"]).allowed
            )

    def test_marketing_blocked_until_consent_in_store(self):
        with tempfile.TemporaryDirectory() as td:
            s = PR.ConsentStore(base_dir=td)
            s.set("anthropic", consent=False, baa_attested=False, key="sk-x")
            rec = s.get("anthropic")
            self.assertFalse(
                PR.authorize(PR.PLANE_MARKETING, "anthropic", consent=rec["consent"]).allowed
            )
            s.set("anthropic", consent=True, baa_attested=False, key="sk-x")
            rec = s.get("anthropic")
            self.assertTrue(
                PR.authorize(PR.PLANE_MARKETING, "anthropic", consent=rec["consent"]).allowed
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
