"""store — per-practice state with compare-and-swap (D-FreeStaff).

One JSON document per practice: profile (the intake survey), runs (each an
instantiated capability with its steps), and the monthly task counter. Low
volume by nature (a practice queues a handful of tasks a week), so a
document store with optimistic concurrency beats standing up a database:

  * gcs backend  — the durable Cloud Run path. GCS generation preconditions
    give real CAS (`if_generation_match`); a lost race re-reads and retries.
  * local backend — dev/tests. Same interface over files + an in-process lock.

NO PHI: profiles are business facts (name, specialty, city, fees); runs are
marketing copy. Nothing clinical can reach this module by construction.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any, Callable

from . import config


class StoreConflict(RuntimeError):
    """CAS lost after retries — caller's mutation never landed."""


def _now() -> int:
    return int(time.time())


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def empty_state(practice_id: str) -> dict:
    return {
        "practiceId": practice_id,
        "profile": None,  # the intake survey (business facts only)
        "slug": "",  # claimed site slug ('' until intake)
        "siteUrl": "",  # live URL once published
        "runs": [],  # newest first
        "drafts": [],  # authoring-draft preview cache (idempotent replay), newest
        #                first, bounded — coalesces retry/double-click Vertex spend
        "inquiries": [],  # site contact-form messages, newest first
        "posts": [],  # published-essay registry, newest first — the DURABLE
        #               source of the site's posts array (the built app.js is
        #               a render of this, never the truth; SH-F2)
        "usage": {},  # {'YYYY-MM': completed-task count} — the silent cap
        "updated": _now(),
    }


# Reserved document id for the slug → practiceId index (published sites POST
# inquiries by SLUG; the svc resolves the owning practice through this doc).
# The leading underscore keeps it out of any practice-id namespace the apps
# mint, and the safe-id filter preserves it verbatim.
SLUG_INDEX_ID = "_slug-index"


class _LocalBackend:
    """File-per-practice with a process lock (dev/tests)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        config.LOCAL_STATE_DIR.mkdir(parents=True, exist_ok=True)

    def _path(self, practice_id: str):
        safe = "".join(c for c in practice_id if c.isalnum() or c in "-_")[:80]
        return config.LOCAL_STATE_DIR / f"{safe}.json"

    def read(self, practice_id: str) -> tuple[dict, Any]:
        p = self._path(practice_id)
        if not p.is_file():
            return empty_state(practice_id), 0
        state = json.loads(p.read_text(encoding="utf-8"))
        return state, int(state.get("_v", 0))

    def write(self, practice_id: str, state: dict, token: Any) -> None:
        # Real CAS (same contract as the GCS backend — a lost race must be
        # SEEN, not silently last-write-wins between the bg loop and request
        # threads) + atomic replace so a reader never catches a half-write.
        with self._lock:
            path = self._path(practice_id)
            current = 0
            if path.is_file():
                try:
                    current = int(json.loads(path.read_text(encoding="utf-8")).get("_v", 0))
                except (json.JSONDecodeError, OSError):
                    current = 0
            if int(token or 0) != current:
                raise StoreConflict(f"version {token} != {current}")
            state["_v"] = current + 1
            tmp = path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            import os  # noqa: PLC0415

            os.replace(tmp, path)


class _GcsBackend:
    """state/{practiceId}.json in the state bucket, CAS via generation match."""

    def __init__(self) -> None:
        from google.cloud import storage  # lazy — local dev needs no GCP libs

        self._client = storage.Client(project=config.GCP_PROJECT)
        self._bucket = self._client.bucket(config.STATE_BUCKET)

    def _blob(self, practice_id: str):
        safe = "".join(c for c in practice_id if c.isalnum() or c in "-_")[:80]
        return self._bucket.blob(f"state/{safe}.json")

    def read(self, practice_id: str) -> tuple[dict, Any]:
        blob = self._blob(practice_id)
        try:
            data = blob.download_as_bytes()
        except Exception:  # noqa: BLE001 — absent object = fresh practice
            return empty_state(practice_id), 0  # 0 = "must not exist" precondition
        blob.reload()
        return json.loads(data.decode("utf-8")), blob.generation

    def write(self, practice_id: str, state: dict, token: Any) -> None:
        blob = self._blob(practice_id)
        body = json.dumps(state, ensure_ascii=False).encode("utf-8")
        from google.api_core import exceptions as gex  # noqa: PLC0415

        try:
            blob.upload_from_string(
                body, content_type="application/json", if_generation_match=token
            )
        except gex.PreconditionFailed as exc:
            raise StoreConflict(str(exc)) from exc


class Store:
    """mutate(practice_id, fn) — read-modify-write with CAS retry."""

    def __init__(self, backend: str | None = None) -> None:
        kind = backend or config.STATE_BACKEND
        self._backend = _GcsBackend() if kind == "gcs" else _LocalBackend()

    def get(self, practice_id: str) -> dict:
        state, _ = self._backend.read(practice_id)
        return state

    def mutate(self, practice_id: str, fn: Callable[[dict], None], retries: int = 4) -> dict:
        for _attempt in range(retries):
            state, token = self._backend.read(practice_id)
            fn(state)
            state["updated"] = _now()
            try:
                self._backend.write(practice_id, state, token)
                return state
            except StoreConflict:
                time.sleep(0.2 * (_attempt + 1))
        raise StoreConflict(f"CAS lost {retries} times for {practice_id}")

    # ── Slug index (the inquiry rail's reverse lookup) ───────────────────────

    def claim_slug(self, slug: str, practice_id: str) -> None:
        """Record slug → practiceId so a public site inquiry can find its
        practice. Same CAS document machinery as practice state; idempotent."""

        def fn(state: dict) -> None:
            state.setdefault("slugs", {})[slug] = practice_id

        self.mutate(SLUG_INDEX_ID, fn)

    def practice_for_slug(self, slug: str) -> str:
        """The owning practiceId for a published slug, or '' if unclaimed."""
        doc = self.get(SLUG_INDEX_ID)
        return str(doc.get("slugs", {}).get(slug, ""))


# Process-wide singleton (app + runner share one).
store = Store()
