"""Google Vertex AI (Gemini) provider profile — Shaula "their Google" path.

Runs the model inside the THERAPIST'S OWN Google Cloud (Vertex) under THEIR BAA — house-nothing.
Uses ``genai.Client(vertexai=True, ...)`` — the SAME client proven live this session in
``engine/brain.py`` (gemini-2.5-pro on Vertex, thinking budget capped). The consumer Gemini
``api_key`` path is BANNED (no BAA); this profile is vertexai-only.

STATUS (honest): this profile + plugin.yaml faithfully mirror the bedrock precedent
(``vendor/hermes/plugins/model-providers/bedrock/``) — verified structure. The ``vertex_ai``
transport (``transport.py``) carries the proven call, but its registration into Hermes' transport
registry + a live harness round-trip are GATED on (a) a full Hermes install (uv) and (b) the
therapist's ADC / Google account. See README.md. Not yet install-verified → SUSPECT until then.
"""
from providers import register_provider
from providers.base import ProviderProfile


class VertexProfile(ProviderProfile):
    """Google Vertex AI (Gemini) under the customer's own Google BAA. No REST /v1/models endpoint."""

    def fetch_models(self, *, api_key: str | None = None, timeout: float = 8.0) -> list[str] | None:
        # Vertex model listing uses the google-genai SDK / aiplatform, not a REST call.
        return None


vertex = VertexProfile(
    name="vertex",
    aliases=("google-vertex", "vertex-ai", "gemini-vertex"),
    api_mode="vertex_ai",                       # custom transport — see transport.py + README
    env_vars=("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"),
    base_url="https://us-central1-aiplatform.googleapis.com",
    auth_type="google_adc",                     # Application Default Credentials (their Workspace) — NOT api_key
)

register_provider(vertex)
