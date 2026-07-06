# google-vertex provider (Shaula "their Google" model path)

Runs Gemini inside the **therapist's own Google Cloud (Vertex)** under **their BAA** — house-nothing.
PHI never reaches us. `vertexai=True` only; the consumer Gemini `api_key` path is **banned** (no BAA).

## Files
- `plugin.yaml` / `__init__.py` — the `ProviderProfile` (mirrors `vendor/hermes/.../bedrock/`).
- `transport.py` — the Vertex round-trip, **reusing the exact call proven live in `engine/brain.py`**
  (gemini-2.5-pro on Vertex, `thinking_budget` capped).

## Status (honest)
- ✅ **Proven core:** the `genai.Client(vertexai=True).generate_content` call was run live this
  session (brain.py) — real enrichment, clean finish.
- 🚧 **Gated (SUSPECT until done):** registering the `vertex_ai` transport into Hermes + a live
  *harness* round-trip need (a) a full Hermes install (`uv sync` the vendored tree) and (b) the
  therapist's ADC / Google account. The profile/transport are written to mirror the bedrock
  precedent but are **not yet install-verified**.

## Wiring (Phase 3-runtime)
1. Load via Hermes' plugin scan (place under `$HERMES_HOME/plugins/model-providers/` or ship in-box).
2. `register_transport("vertex_ai", ...)` + add `"vertex_ai"` to `_VALID_API_MODES`
   (`vendor/hermes/.../runtime_provider.py`) — read the transport base class at install time.
3. `gcloud auth application-default login` in the therapist's BAA-covered project; set
   `GOOGLE_CLOUD_PROJECT`. Smoke-test, then this becomes the cloud model path.

The **local Ollama floor** (`config/shaula-harden.yaml` → `provider: custom`, `localhost:11434`) is
the $0, PHI-never-leaves-box default; it's gated only on `ollama` being installed on the box.
