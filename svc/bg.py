"""bg — the svc's background executor (D-FreeStaff).

One dedicated thread running one dedicated event loop, started lazily.
Run execution is submitted here instead of onto the SERVING loop:

  * requests never share fate with task latency,
  * the server framework's loop lifecycle (test harnesses, reloads,
    graceful drains) cannot strand a queued run,
  * submitted futures are strongly referenced until done (the create_task
    GC gotcha cannot occur).
"""
from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from typing import Any, Coroutine

_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None
_futures: set[Future] = set()


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _loop
    with _lock:
        if _loop is None or _loop.is_closed():
            loop = asyncio.new_event_loop()
            thread = threading.Thread(
                target=loop.run_forever, name="shaula-bg", daemon=True
            )
            thread.start()
            _loop = loop
        return _loop


def submit(coro: Coroutine[Any, Any, Any]) -> Future:
    """Fire-and-forget a coroutine on the background loop (strongly held)."""
    future = asyncio.run_coroutine_threadsafe(coro, _ensure_loop())
    _futures.add(future)
    future.add_done_callback(_futures.discard)
    return future
