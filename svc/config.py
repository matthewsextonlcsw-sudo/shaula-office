"""config — shaula-svc environment (D-FreeStaff, 2026-06-11).

The multi-tenant office runtime: Cloud Run service that runs the 8 no-PHI
office staff for every practice. House rules baked in:

  * ZERO PHI by construction — this service never sees a client, a chart,
    or a session. Practice surveys are business facts only.
  * Browsers never reach this service: callers are the practice-app servers,
    authenticated by a shared internal secret (the x-internal-secret idiom).
  * Caps are SILENT (Matthew, 2026-06-11): per-tier monthly task budgets,
    queue when reached — never an error, never a number on a screen.
  * Shaula tasks do NOT draw from the apps' Credit balances — free means
    free; the silent cap is the only throttle (supersedes the earlier
    metering note in the plan; clinical AI must never 402 because a blog
    post ate the balance).

All knobs are env vars so Cloud Run + local dev share one code path.
"""
from __future__ import annotations

import os
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent

# Service-to-service auth. Empty = dev mode (auth middleware refuses to start
# in production posture without it; see app.py).
INTERNAL_SECRET = os.environ.get("SHAULA_INTERNAL_SECRET", "")

# Storage. STATE_BACKEND: 'gcs' (Cloud Run) | 'local' (dev/tests).
STATE_BACKEND = os.environ.get("SHAULA_STATE_BACKEND", "local")
STATE_BUCKET = os.environ.get("SHAULA_STATE_BUCKET", "mws-shaula-state")
# Local fallback root (dev/tests) — never used when backend=gcs.
LOCAL_STATE_DIR = pathlib.Path(
    os.environ.get("SHAULA_LOCAL_STATE", str(REPO / ".svc-state"))
)

# Published sites. Public bucket (one-time host setup — the proven
# publish_site_gcs path from bin/shaula-office, 2026-06-08).
# PUBLISH_BACKEND: 'gcs' (Cloud Run) | 'local' (dev/demo — the svc serves
# the published tree itself at /sites/, zero cloud, full loop in a browser).
PUBLISH_BACKEND = os.environ.get("SHAULA_PUBLISH_BACKEND", "gcs")
SITES_BUCKET = os.environ.get("SHAULA_SITES_BUCKET", "mws-shaula-sites")
GCP_PROJECT = os.environ.get("SHAULA_GCP_PROJECT", "")
# Public origin for local-published URLs (the svc's own address in dev).
PUBLIC_ORIGIN = os.environ.get("SHAULA_PUBLIC_ORIGIN", "http://127.0.0.1:8080")

# Where built sites land before publish (ephemeral on Cloud Run — the GCS
# copy is the durable artifact).
SITES_DIR = pathlib.Path(os.environ.get("SHAULA_SITES_DIR", str(REPO / "sites")))

# Contact-form delivery (the inquiry rail). Published sites POST visitor
# inquiries to {INQUIRY_ORIGIN}/v1/sites/{slug}/inquiry — the ONE public
# write endpoint (honeypot + rate-limited; messages land in the practice's
# staff inbox). Local backend defaults to the svc's own origin so the whole
# loop works on the zero-cloud demo rail; on the gcs backend this MUST be
# set to the service's public URL or built sites render the honest
# direct-contact card instead of a form (never a dead-end form).
INQUIRY_ORIGIN = os.environ.get(
    "SHAULA_INQUIRY_ORIGIN",
    PUBLIC_ORIGIN if PUBLISH_BACKEND == "local" else "",
)
# Per-slug inquiry rate limit (per hour, per instance — spam brake, not a
# security boundary; the endpoint stores bounded plain text only).
INQUIRY_MAX_PER_HOUR = int(os.environ.get("SHAULA_INQUIRY_MAX_PER_HOUR", "20"))

# Vertex brain (the BAA path — never consumer Gemini keys).
VERTEX_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
VERTEX_MODEL = os.environ.get("SHAULA_MODEL", "gemini-2.5-flash")

# Site-build enrichment (UX audit SH-F5): the engine/brain.py seam, wired into
# website-launch. 'auto' = enrich when the brain is available (ADC + SDK),
# falling back to the deterministic floor byte-for-byte; 'off' = floor only
# (tests + zero-cloud demo set this). Never consumer Gemini — Vertex only.
SITE_BRAIN = os.environ.get("SHAULA_SITE_BRAIN", "auto").lower()

# Therapist self-serve workflow authoring (P2). Default OFF — additive and gated:
# the /v1/practices/{pid}/workflows/* endpoints 404 until this is "1". Lets the
# code ship dark and flip on per-environment without a redeploy.
AUTHORING_ENABLED = os.environ.get("SHAULA_AUTHORING_ENABLED", "") == "1"

# Per-practice draft rate brake (per hour, per instance). A workflow draft is up to
# THREE Vertex calls (the repair loop + an optional skill); this bounds burst spend
# from a buggy or looping caller hammering the authoring draft endpoint. A cost
# brake, not a security boundary (callers are already secret-authenticated); over
# the brake the endpoint 429s. The replay coalesce (authoring.find_draft_replay)
# runs FIRST, so a retry storm is absorbed before it ever reaches this counter —
# only genuine new Vertex chains count against it.
DRAFT_MAX_PER_HOUR = int(os.environ.get("SHAULA_DRAFT_MAX_PER_HOUR", "30"))

# Silent per-tier monthly task caps (queue past the cap, never block).
# Keys match both ladders' tier words; unknown tiers get DEFAULT.
TIER_TASK_CAPS = {
    "free": int(os.environ.get("SHAULA_CAP_FREE", "4")),
    "solo": int(os.environ.get("SHAULA_CAP_SOLO", "12")),
    "pro": int(os.environ.get("SHAULA_CAP_PRO", "24")),
    "group": int(os.environ.get("SHAULA_CAP_GROUP", "24")),
    "practice": int(os.environ.get("SHAULA_CAP_PRACTICE", "48")),
    "enterprise": int(os.environ.get("SHAULA_CAP_ENTERPRISE", "200")),
}
DEFAULT_TASK_CAP = int(os.environ.get("SHAULA_CAP_DEFAULT", "12"))


def cap_for(tier: str) -> int:
    return TIER_TASK_CAPS.get((tier or "").lower(), DEFAULT_TASK_CAP)
