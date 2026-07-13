"""Shared SQL-SELECT-counting async context manager for N+1 perf tests.

Extracted (feature 031, T004 — research.md R13) from the canonical form in
``backend/tests/technique/test_perf_queries.py:79-118``, which had already
been duplicated independently in ``backend/tests/strength/test_perf_queries.py``,
``backend/tests/intervals/test_perf_queries.py``, and
``backend/tests/routers/test_activities.py`` — past the rule-of-three
threshold. New N+1 guard tests should import ``count_selects`` from here
instead of adding a fifth local copy.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine


@asynccontextmanager
async def count_selects(engine: AsyncEngine):
    """Context manager that counts SQL SELECT statements issued via *engine*.

    Uses the synchronous SQLAlchemy ``before_cursor_execute`` Core event, which
    fires for every statement sent to the DBAPI driver regardless of whether it
    originates from an ORM query or a raw ``text()`` call.

    Yields:
        A one-element list ``[count]``.  Read ``counter[0]`` after the ``async
        with`` block to get the total number of SELECT statements executed
        inside the block.

    Implementation note:
        ``AsyncEngine`` wraps a synchronous ``Engine``; the Core event must be
        registered on the *sync* engine (``engine.sync_engine``).  The event
        fires on the thread that executes the DBAPI call, which is the asyncio
        event loop's executor thread — the list append is safe because aiosqlite
        serialises all calls via a background thread per connection.
    """
    counter: list[int] = [0]

    def _before_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        if statement.strip().upper().startswith("SELECT"):
            counter[0] += 1

    sync_engine = engine.sync_engine
    sa_event.listen(sync_engine, "before_cursor_execute", _before_cursor_execute)
    try:
        yield counter
    finally:
        sa_event.remove(sync_engine, "before_cursor_execute", _before_cursor_execute)
