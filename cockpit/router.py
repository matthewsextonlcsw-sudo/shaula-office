"""router — decides which LLM answers which task, and calls it. The "what LLM for what"
decision, expressed as code.

Defaults (override via env SHAULA_ROUTE_<TASK>=<backend>:<model>):
  chat      -> vertex:gemini-2.5-flash   (fast, good, the therapist's own Google/BAA)
  content   -> vertex:gemini-2.5-pro     (quality marketing prose)
  humanize  -> vertex:gemini-2.5-flash   (de-AI a passage via the ported humanizer skill)
  fallback  -> ollama:<local>            ($0, offline, the floor) on any vertex failure

Backends:
  vertex : the therapist's OWN Google (Vertex/Gemini) under their BAA. House-nothing.
  ollama : local OpenAI-compatible server (http://localhost:11434/v1). $0, PHI never leaves box.

No PHI in this module; it only moves chat/marketing text. Vertex-only for Google (no api_key path).
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

# Make this package's own dir importable wherever router is loaded from (the
# server adds cockpit/ to sys.path, but the office imports router in-process).
_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import providers  # noqa: E402 — the registry + two-plane gate

_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "veterancheck-ai")
_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
_SA = os.environ.get("SHAULA_VERTEX_SA", "veterancheck-vertex@veterancheck-ai.iam.gserviceaccount.com")
_OLLAMA = os.environ.get("SHAULA_OLLAMA_URL", "http://localhost:11434/v1")
_OLLAMA_MODEL = os.environ.get("SHAULA_OLLAMA_MODEL", "qwen2.5:0.5b")

# BYO provider defaults (the customer can override per provider via env). These
# are the no-PHI/marketing models; the PHI plane uses the customer's Vertex.
_BYO_MODELS = {
    "openai":       os.environ.get("SHAULA_MODEL_OPENAI", "gpt-4o-mini"),
    "anthropic":    os.environ.get("SHAULA_MODEL_ANTHROPIC", "claude-sonnet-4-6"),
    "xai":          os.environ.get("SHAULA_MODEL_XAI", "grok-2-latest"),
    "azure_openai": os.environ.get("SHAULA_AZURE_DEPLOYMENT", ""),
}
_OPENAI_COMPAT_BASE = {
    "openai": os.environ.get("SHAULA_OPENAI_BASE", "https://api.openai.com/v1"),
    "xai":    os.environ.get("SHAULA_XAI_BASE", "https://api.x.ai/v1"),
}
# The consent/attestation + BYO-key store (keys never logged; get() never leaks them).
_BYO = providers.ConsentStore()

_ROUTES = {
    "chat":     os.environ.get("SHAULA_ROUTE_CHAT", "vertex:gemini-3.1-flash-lite"),
    "content":  os.environ.get("SHAULA_ROUTE_CONTENT", "vertex:gemini-2.5-pro"),
    "humanize": os.environ.get("SHAULA_ROUTE_HUMANIZE", "vertex:gemini-2.5-flash"),
}

_HUMANIZER = (pathlib.Path(__file__).parent / "skills/humanizer/SKILL.md")

# --- Vertex (their Google) -------------------------------------------------- #
_tok = {"value": None, "exp": 0.0}


def _vertex_token() -> str | None:
    """Mint + cache a short-lived access token for the Vertex service account."""
    if _tok["value"] and time.time() < _tok["exp"]:
        return _tok["value"]
    try:
        t = subprocess.run(["gcloud", "auth", "print-access-token", _SA],
                           capture_output=True, text=True, timeout=20)
        if t.returncode == 0 and t.stdout.strip():
            _tok["value"] = t.stdout.strip()
            _tok["exp"] = time.time() + 2700  # ~45 min
            return _tok["value"]
    except Exception:
        pass
    return None


def _call_vertex(model: str, system: str | None, message: str,
                 max_tokens: int, thinking_budget: int,
                 history: list | None = None) -> str | None:
    token = _vertex_token()
    if not token:
        return None
    try:
        from google.oauth2.credentials import Credentials
        from google import genai
        from google.genai import types
        # Gemini 3.x serves on the GLOBAL endpoint (404s on regional like us-central1).
        loc = "global" if model.startswith("gemini-3") else _LOCATION
        client = genai.Client(vertexai=True, project=_PROJECT, location=loc,
                              credentials=Credentials(token=token))
        cfg = types.GenerateContentConfig(
            temperature=0.6, max_output_tokens=max_tokens,
            system_instruction=system or None,
            thinking_config=types.ThinkingConfig(thinking_budget=thinking_budget),
        )
        # Multi-turn: prior turns give Shaula memory of the conversation so it can
        # follow up instead of answering each message cold (the "amnesiac" feel).
        contents = []
        for h in (history or []):
            t = (h.get("text") or "").strip()
            if not t:
                continue
            role = "user" if h.get("role") in ("user", "me", "you") else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=t)]))
        contents.append(types.Content(role="user", parts=[types.Part(text=message)]))
        resp = client.models.generate_content(model=model, contents=contents, config=cfg)
        return (resp.text or "").strip() or None
    except Exception:
        return None


# --- Ollama (local floor) --------------------------------------------------- #
def _call_ollama(system: str | None, message: str, max_tokens: int,
                 history: list | None = None) -> str | None:
    msgs = [{"role": "system", "content": system}] if system else []
    for h in (history or []):
        t = (h.get("text") or "").strip()
        if not t:
            continue
        role = "user" if h.get("role") in ("user", "me", "you") else "assistant"
        msgs.append({"role": role, "content": t})
    msgs.append({"role": "user", "content": message})
    body = json.dumps({"model": _OLLAMA_MODEL, "messages": msgs,
                       "max_tokens": max_tokens, "temperature": 0.6}).encode()
    req = urllib.request.Request(_OLLAMA + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
            return (d["choices"][0]["message"]["content"] or "").strip() or None
    except Exception:
        return None


# --- BYO providers (no-PHI plane) ------------------------------------------- #
def _openai_messages(system: str | None, message: str, history: list | None) -> list:
    msgs = [{"role": "system", "content": system}] if system else []
    for h in (history or []):
        t = (h.get("text") or "").strip()
        if not t:
            continue
        role = "user" if h.get("role") in ("user", "me", "you") else "assistant"
        msgs.append({"role": role, "content": t})
    msgs.append({"role": "user", "content": message})
    return msgs


def _call_openai_compat(base: str, key: str | None, model: str, system: str | None,
                        message: str, max_tokens: int, history: list | None = None) -> str | None:
    """OpenAI-compatible chat/completions (OpenAI, xAI/Grok, Azure-OpenAI). BYO key."""
    if not key or not base or not model:
        return None
    body = json.dumps({"model": model, "messages": _openai_messages(system, message, history),
                       "max_tokens": max_tokens, "temperature": 0.6}).encode()
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
            return (d["choices"][0]["message"]["content"] or "").strip() or None
    except Exception:
        return None  # never log — the key rides in the header


def _call_anthropic(key: str | None, model: str, system: str | None,
                    message: str, max_tokens: int, history: list | None = None) -> str | None:
    """Anthropic Messages API (distinct shape: x-api-key, top-level system). BYO key."""
    if not key or not model:
        return None
    msgs = []
    for h in (history or []):
        t = (h.get("text") or "").strip()
        if not t:
            continue
        role = "user" if h.get("role") in ("user", "me", "you") else "assistant"
        msgs.append({"role": role, "content": t})
    msgs.append({"role": "user", "content": message})
    payload = {"model": model, "max_tokens": max_tokens, "messages": msgs}
    if system:
        payload["system"] = system
    req = urllib.request.Request("https://api.anthropic.com/v1/messages",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          "x-api-key": key,
                                          "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
            parts = d.get("content") or []
            text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
            return text.strip() or None
    except Exception:
        return None  # never log — the key rides in the header


def _dispatch_byo(provider: str, system: str | None, message: str,
                  max_tokens: int, history: list | None) -> tuple[str | None, str]:
    """Call the chosen BYO provider with its stored key. Returns (text, model)."""
    model = _BYO_MODELS.get(provider, "")
    if provider in ("openai", "xai"):
        return _call_openai_compat(_OPENAI_COMPAT_BASE[provider], _BYO.key(provider),
                                   model, system, message, max_tokens, history), model
    if provider == "anthropic":
        return _call_anthropic(_BYO.key(provider), model, system, message, max_tokens, history), model
    if provider == "azure_openai":
        base = os.environ.get("SHAULA_AZURE_ENDPOINT", "")  # needs the deployment endpoint
        return _call_openai_compat(base, _BYO.key(provider), model, system,
                                   message, max_tokens, history), model
    if provider == "vertex":
        thinking = 1024
        m = model or _ROUTES["chat"].partition(":")[2]
        return _call_vertex(m, system, message, max_tokens, thinking, history), m
    if provider == "ollama":
        return _call_ollama(system, message, max_tokens, history), _OLLAMA_MODEL
    return None, model


# --- public ----------------------------------------------------------------- #
def route(task: str, message: str, *, system: str | None = None,
          history: list | None = None, provider: str | None = None,
          plane: str = providers.PLANE_MARKETING) -> dict:
    """Answer `message` for `task`, with optional conversation `history` (list of
    {role, text}) so chat isn't amnesiac. Returns {text, backend, model}.

    `provider` (optional) forces a specific BYO/registered backend, GATED by the
    two-plane rule: a PHI plane refuses any non-BAA provider (and any unattested
    one); a marketing plane refuses a BYO-keyed provider without billing consent.
    With no `provider`, the default vertex->ollama route runs unchanged."""
    max_tokens = 1500 if task in ("content", "chat") else 700

    if provider:
        rec = _BYO.get(provider)
        dec = providers.authorize(plane, provider,
                                  consent=rec["consent"], baa_attested=rec["baa_attested"])
        if not dec.allowed:
            # Fail closed: a blocked choice is NEVER silently downgraded to another model.
            return {"text": f"[blocked] {dec.reason}", "backend": "blocked", "model": None}
        text, model = _dispatch_byo(provider, system, message, max_tokens, history)
        if text:
            return {"text": text, "backend": provider, "model": model}
        return {"text": f"({providers.get(provider).label} unreachable — check the key/endpoint)",
                "backend": provider, "model": model or None}

    spec = _ROUTES.get(task, _ROUTES["chat"])
    backend, _, model = spec.partition(":")
    # Chat gets a real thinking budget even on flash — turns shallow one-liners into
    # reasoned answers while staying far faster than pro. pro (content) reasons too.
    thinking = 1024 if task == "chat" else (256 if model.endswith("pro") else 0)
    if backend == "vertex":
        text = _call_vertex(model, system, message, max_tokens, thinking, history)
        if text:
            return {"text": text, "backend": "vertex", "model": model}
    # fallback / explicit ollama
    text = _call_ollama(system, message, max_tokens, history)
    if text:
        return {"text": text, "backend": "ollama", "model": _OLLAMA_MODEL}
    return {"text": "(no model reachable — start Ollama or configure Vertex)",
            "backend": "none", "model": None}


def humanize(text: str) -> dict:
    """Run text through the ported humanizer skill (de-AI it) via the humanize route."""
    guide = _HUMANIZER.read_text(encoding="utf-8") if _HUMANIZER.exists() else ""
    system = (guide + "\n\nRewrite ONLY the user's text below to remove AI-writing patterns. "
              "Preserve meaning and length. Return only the rewritten text.")
    return route("humanize", text, system=system)
