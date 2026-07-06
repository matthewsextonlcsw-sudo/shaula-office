"""vertex_ai transport — the actual Vertex call, reusing the client proven live this session.

The ``generate()`` here is the SAME google-genai Vertex round-trip verified in ``engine/brain.py``
(gemini-2.5-pro on Vertex, ``thinking_budget`` capped so the model actually emits text). It is the
*proven core*; the only unverified part is the thin glue that conforms it to Hermes' transport base
class — which is read + wired at install time.

To register with Hermes (Phase 3-runtime; needs the full Hermes install):
    from agent.transports import register_transport            # vendor/hermes/agent/transports/
    from <this module> import VertexTransport
    register_transport("vertex_ai", VertexTransport)
    # and add "vertex_ai" to _VALID_API_MODES (vendor/hermes/.../runtime_provider.py)

GATE (honest): a live harness round-trip needs (a) ``uv sync`` of the vendored Hermes and (b) the
therapist's ADC / Google account. NEVER the consumer ``api_key`` path — vertexai=True only.
"""
from __future__ import annotations

import os


def _client(project: str | None = None, location: str | None = None):
    """Build the BAA-covered Vertex client. vertexai=True is mandatory (no api_key path)."""
    from google import genai  # optional dependency
    return genai.Client(
        vertexai=True,
        project=project or os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=location or os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )


def generate(
    model: str,
    contents,
    *,
    project: str | None = None,
    location: str | None = None,
    max_output_tokens: int = 1024,
    temperature: float = 0.4,
    thinking_budget: int = 128,
) -> str | None:
    """One Vertex round-trip — the brain.py-proven pattern (incl. the thinking-budget fix).

    Returns ``resp.text`` (or None). The ``thinking_budget`` cap is load-bearing: gemini-2.5-pro
    is a thinking model and starves its own output without it (verified live this session).
    """
    from google.genai import types
    client = _client(project, location)
    cfg = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        thinking_config=types.ThinkingConfig(thinking_budget=thinking_budget),
    )
    resp = client.models.generate_content(model=model, contents=contents, config=cfg)
    return resp.text
