"""providers — the LLM provider registry + the two-plane gate.

The whole compliance story lives here. Two planes, one gate (Matthew's rule):

  marketing (NO PHI)         : ANY provider, BYO key. A keyed BYO provider needs a
                               billing-consent ack first — Anthropic, OpenAI/ChatGPT
                               and xAI/Grok each bill differently, and WE never bill
                               for or control those tokens; the customer does.

  phi (clinical plane)  : a BAA-COVERED provider ONLY, and the customer must
                               attest the signed BAA. No BAA -> refused (HIPAA risk).
                               Consumer ChatGPT / Grok are never BAA -> never PHI.
                               Local (Ollama) is self-hosted — no third-party
                               processor — so it is PHI-eligible with no external BAA.

`authorize()` is a pure function (no I/O) so the gate is trivially testable and
fails CLOSED on anything it does not recognise. `ConsentStore` persists the
consent/attestation flags and the BYO key — and `get()` NEVER hands the key back,
so logging a consent record can never leak it. No key is ever logged here.

No PHI in this module: it moves only routing/consent metadata.
"""
from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass

# The two planes. Anything else -> the gate fails closed.
PLANE_MARKETING = "marketing"
PLANE_PHI = "phi"


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    # phi_ok: may this provider ever touch PHI? True only for BAA third-parties
    # (Google Vertex, Azure OpenAI) and self-hosted local (Ollama).
    phi_ok: bool
    # needs_attestation: PHI use requires the customer to confirm a signed BAA.
    # True for third-party BAA providers; False for self-hosted (no third party).
    needs_attestation: bool
    # needs_key: a BYO API key is supplied by the customer (and they get billed).
    needs_key: bool
    billed_by: str
    rate: str           # human-readable list price, for the UI billing notice
    note: str


# The registry. Order = the order the UI shows them.
_REGISTRY: tuple[Provider, ...] = (
    Provider(
        id="vertex",
        label="Google Vertex / Gemini (your Workspace)",
        phi_ok=True, needs_attestation=True, needs_key=False,
        billed_by="Google Cloud — your own account",
        rate="Gemini list pricing (per your Google billing)",
        note="Runs on the customer's own Workspace Vertex under their Google BAA. "
             "House-nothing. The default for the clinical/PHI plane.",
    ),
    Provider(
        id="azure_openai",
        label="Azure OpenAI",
        phi_ok=True, needs_attestation=True, needs_key=True,
        billed_by="Microsoft Azure — your own account",
        rate="Azure OpenAI list pricing",
        note="BAA-covered via Microsoft. PHI-eligible once the BAA is attested.",
    ),
    Provider(
        id="openai",
        label="OpenAI / ChatGPT",
        phi_ok=False, needs_attestation=False, needs_key=True,
        billed_by="OpenAI — your own account",
        rate="OpenAI list pricing (per 1M tokens)",
        note="No BAA — marketing / no-PHI only. Never touches clinical data.",
    ),
    Provider(
        id="anthropic",
        label="Anthropic / Claude",
        phi_ok=False, needs_attestation=False, needs_key=True,
        billed_by="Anthropic — your own account",
        rate="Anthropic list pricing (per 1M tokens) — bills differently from OpenAI",
        note="No BAA — marketing / no-PHI only.",
    ),
    Provider(
        id="xai",
        label="xAI / Grok",
        phi_ok=False, needs_attestation=False, needs_key=True,
        billed_by="xAI — your own account",
        rate="xAI list pricing (per 1M tokens)",
        note="No BAA — marketing / no-PHI only.",
    ),
    Provider(
        id="ollama",
        label="Local (Ollama)",
        phi_ok=True, needs_attestation=False, needs_key=False,
        billed_by="nobody — runs on your machine",
        rate="free (self-hosted)",
        note="Self-hosted: PHI never leaves the box, no third-party processor, "
             "so it is PHI-eligible with no external BAA.",
    ),
)

_BY_ID = {p.id: p for p in _REGISTRY}


def all() -> list[Provider]:  # noqa: A001 — deliberate: providers.all()
    """Every provider, in display order."""
    return list(_REGISTRY)


def get(provider_id: str) -> Provider | None:
    """The provider, or None if unknown."""
    return _BY_ID.get(provider_id)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    provider: str | None


def authorize(plane: str, provider_id: str, *,
              consent: bool = False, baa_attested: bool = False) -> Decision:
    """Decide whether `provider_id` may run on `plane`. Pure; fails CLOSED.

    marketing : any provider; a BYO-keyed one needs billing `consent`.
    phi       : `phi_ok` providers only; third-party ones need `baa_attested`.
    """
    p = get(provider_id)
    if p is None:
        return Decision(False, f"Unknown provider {provider_id!r}.", None)

    if plane == PLANE_PHI:
        if not p.phi_ok:
            return Decision(
                False,
                f"{p.label} is not BAA-covered — PHI requires a BAA provider "
                f"(no BAA = HIPAA risk). Use your Workspace Vertex/Gemini or Azure OpenAI.",
                p.id,
            )
        if p.needs_attestation and not baa_attested:
            return Decision(
                False,
                f"PHI requires you to attest a signed BAA with {p.label} before it runs.",
                p.id,
            )
        return Decision(True, "ok", p.id)

    if plane == PLANE_MARKETING:
        if p.needs_key and not consent:
            return Decision(
                False,
                f"{p.label} needs your billing consent first — you bring the key and "
                f"{p.billed_by.split(' — ')[0]} bills you directly.",
                p.id,
            )
        return Decision(True, "ok", p.id)

    # Unrecognised plane -> fail closed. Never default to allow.
    return Decision(False, f"Unknown plane {plane!r} — refused.", p.id)


# --------------------------------------------------------------------------- #
# ConsentStore — persists the consent/attestation flags + the BYO key.
# get() NEVER returns the key (so a logged consent record can't leak it); the
# key is reachable only through the explicit key() accessor. Keys file is 0600.
# L11 (CSO 2026-06-29): the BYO-key dir defaults under HERMES_HOME (fallback
# ~/.hermes), NOT world-traversable /tmp, and is created 0700 (owner-only). Both
# defaults sit in $HOME but OUTSIDE the macOS TCC-protected dirs (Desktop/
# Documents/Downloads), so the macOS-Desktop gotcha that pushed this to /tmp does
# not apply. SHAULA_BYO_DIR still overrides for explicit placement.
# --------------------------------------------------------------------------- #
class ConsentStore:
    CONSENT_FILE = "consent.json"
    KEYS_FILE = "keys.json"

    def __init__(self, base_dir: str | os.PathLike | None = None):
        explicit = base_dir or os.environ.get("SHAULA_BYO_DIR")
        if explicit:
            self.base = pathlib.Path(explicit)
        else:
            hermes_home = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
            self.base = pathlib.Path(hermes_home) / "shaula-byo"
        # mode=0o700 sets the intended bits on create; chmod enforces it even when
        # the dir already exists or umask would have masked the create mode.
        self.base.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(self.base, 0o700)
        except OSError:
            pass  # best-effort on filesystems that don't support chmod

    def _read(self, name: str) -> dict:
        f = self.base / name
        if not f.exists():
            return {}
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write(self, name: str, data: dict, *, secret: bool = False) -> None:
        f = self.base / name
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        if secret:
            os.chmod(tmp, 0o600)
        os.replace(tmp, f)
        if secret:
            os.chmod(f, 0o600)

    def set(self, provider_id: str, *, consent: bool, baa_attested: bool,
            key: str | None = None) -> None:
        """Record consent/attestation for a provider; optionally store its BYO key.
        The key lives in a SEPARATE 0600 file and is never mixed into the consent
        record. A key of None leaves any existing key untouched."""
        consents = self._read(self.CONSENT_FILE)
        consents[provider_id] = {"consent": bool(consent),
                                 "baa_attested": bool(baa_attested)}
        self._write(self.CONSENT_FILE, consents)
        if key:
            keys = self._read(self.KEYS_FILE)
            keys[provider_id] = key
            self._write(self.KEYS_FILE, keys, secret=True)

    def get(self, provider_id: str) -> dict:
        """The consent record for a provider — WITHOUT the key, ever. Missing ->
        a closed default ({consent: False, baa_attested: False})."""
        rec = self._read(self.CONSENT_FILE).get(provider_id)
        if not rec:
            return {"consent": False, "baa_attested": False}
        # Defensive: never let a key field ride along even if one were written.
        return {"consent": bool(rec.get("consent")),
                "baa_attested": bool(rec.get("baa_attested"))}

    def key(self, provider_id: str) -> str | None:
        """The BYO key for a provider, or None. The ONLY way to read a key."""
        return self._read(self.KEYS_FILE).get(provider_id)
