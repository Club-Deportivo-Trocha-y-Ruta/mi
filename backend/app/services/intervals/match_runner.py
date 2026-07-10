"""Deferred plan-vs-actual match job (feature 026, T021).

Entry point: ``run_match_deferred(structure_id, strava_activity_id,
triggered_by)``. This is the function ``TaskDispatcher.dispatch(...)`` (T022 —
``routers/activities.py::link_activity`` on link, ``services/intervals/
structures.py`` on create/update when the session already has a linked
activity, and ``routers/intervals.py``'s ``POST .../recalculate`` — T023) hands
off to run in the background, exactly the same wiring as
``routers/strava_integration.py::_process_webhook_event_deferred``.

Inputs:
- ``structure_id``: PK of the ``IntervalStructure`` to compare against.
- ``strava_activity_id``: PK of ``strava_activities.id`` (the **internal**
  row id — the same value ``routers/activities.py`` calls ``activity_id`` —
  NOT the external Strava numeric activity id; that one only appears as
  ``StravaActivity.strava_activity_id`` and is resolved internally to call
  ``StravaClient.get_activity_laps``).
- ``triggered_by``: ``MatchTrigger`` — observability column, set by the
  caller to ``link`` / ``structure_change`` / ``manual`` per contracts/api.md.

Outputs: ``None``. All effects are DB mutations (see below) plus the
in-process failure marker described under "Failure state" below. Never
raises — any error is caught, logged, and swallowed, mirroring the webhook
deferred-processing pattern (a background task has no caller left to
propagate an exception to).

Side effects (one transaction, one commit — this module owns both):
- Opens its **own** ``AsyncSessionLocal`` (the request-scoped session that
  dispatched this job is gone by the time a ``BackgroundTasks`` callback
  runs — same rule ``_process_webhook_event_deferred`` documents).
- Calls ``StravaClient.get_activity_laps`` (one outbound Strava call).
- Replaces (delete-then-insert, data-model.md §5 "Refresh semantics")
  ``strava_activity_laps`` for that activity with the allow-listed fields
  from the fresh payload.
- Upserts exactly one ``interval_match_results`` row
  (``UNIQUE(structure_id, strava_activity_id)``).
- Logs numeric identifiers and exception *type* names only — never a lap
  payload, an activity title, or an exception message that might echo
  upstream content (Ley 1581 minors-privacy gate, same rule as
  ``services/strava/client.py``/``ingest.py``).

Privacy (Ley 1581, D4 — allow-list, not deny-list):
``_ALLOWED_RAW_LAP_FIELDS`` is the single place this module reads keys off
the raw Strava lap payload: ``lap_index``, ``elapsed_time``, ``moving_time``,
``average_heartrate``, ``average_speed``. Everything else in the raw
payload — GPS, polyline/map, lap ``name``, ``average_cadence``,
``average_watts`` — is never referenced by name here, so it can never reach
``strava_activity_laps`` even if Strava starts sending it. ``StravaActivityLap``
(the model) has no columns for any of those fields either — a second,
independent layer of the same guarantee. The computed comparison is built
exclusively through ``matching.compute_match``, whose ``MatchResultPayload``
sets ``extra="forbid"`` end to end, so a stray key can never slip into
``result_json`` either.

Failure state (module-local, in-process):
Per data-model.md there is no persisted "job status" column anywhere in this
feature's schema — ``interval_match_results`` only ever holds a *successful*
computed comparison (data-model.md §6), and the match-detail contract
(contracts/api.md) nonetheless requires the endpoint to be able to report
``status="failed"`` (with ``retry_available: true``) as distinct from
``status="computing"`` when no result row exists yet. Since this module is
the only place a run can fail, it exposes a tiny in-process marker —
``has_failed(structure_id, strava_activity_id) -> bool`` — that the
match-detail endpoint (``routers/intervals.py``, T023) can consult: no result
row + ``has_failed(...)`` True → ``failed``; no result row + False →
``computing``. A success clears the marker for that pair. This is
intentionally NOT persisted to the database (no schema exists for it and
none is warranted for a transient, retriable job flag): acceptable at this
club's scale (single Render free-tier instance; ``BackgroundTasks`` runs
in-process) — a process restart between a failed run and the coach's next
view degrades to "computing" rather than "failed", which is a safe direction
to degrade in (the coach can still hit ``recalculate`` manually).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.interval_structure import IntervalStructure
from app.models.strava_activity import StravaActivity
from app.models.strava_activity_lap import (
    IntervalMatchResult,
    MatchTrigger,
    StravaActivityLap,
)
from app.models.strava_connection import StravaConnection
from app.services.intervals.matching import ENGINE_VERSION, MatchLap, compute_match
from app.services.intervals.structures import flatten_blocks
from app.services.strava.client import StravaClient

logger = logging.getLogger(__name__)

#: Allow-list of raw Strava lap payload keys this module will ever read
#: (D4 / Ley 1581 gate). Mirrors the exact list documented on
#: ``StravaClient.get_activity_laps``.
_ALLOWED_RAW_LAP_FIELDS = (
    "lap_index",
    "elapsed_time",
    "moving_time",
    "average_heartrate",
    "average_speed",
)


def _now_utc() -> datetime:
    """Instante UTC actual (mismo patrón de defaults de los modelos)."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# In-process failure tracker — see module docstring "Failure state" section.
# ---------------------------------------------------------------------------

_FAILED_RUNS: set[tuple[int, int]] = set()


def has_failed(structure_id: int, strava_activity_id: int) -> bool:
    """``True`` if the last run for this pair ended in failure and no
    successful run has happened since (see module docstring).

    Consumed by the match-detail endpoint (T023) to distinguish
    ``status="failed"`` from ``status="computing"`` when no
    ``interval_match_results`` row exists yet for ``(structure_id,
    strava_activity_id)``.
    """
    return (structure_id, strava_activity_id) in _FAILED_RUNS


def _mark_failed(structure_id: int, strava_activity_id: int) -> None:
    _FAILED_RUNS.add((structure_id, strava_activity_id))


def _clear_failed(structure_id: int, strava_activity_id: int) -> None:
    _FAILED_RUNS.discard((structure_id, strava_activity_id))


# ---------------------------------------------------------------------------
# Allow-list + replace-persist laps
# ---------------------------------------------------------------------------


def _allow_listed_lap(
    raw: dict[str, Any], *, strava_activity_pk: int, fetched_at: datetime
) -> StravaActivityLap | None:
    """Builds one ``StravaActivityLap`` row from a raw Strava lap payload.

    Reads ONLY ``_ALLOWED_RAW_LAP_FIELDS`` off ``raw`` — nothing else is ever
    referenced (see module docstring "Privacy"). Returns ``None`` for a
    malformed entry missing the two fields the model requires as NOT NULL
    (``lap_index``/``elapsed_time``) — skipped rather than raised, since one
    odd lap must not fail the whole activity's comparison.
    """
    lap_index = raw.get("lap_index")
    elapsed_time = raw.get("elapsed_time")
    if lap_index is None or elapsed_time is None:
        return None
    return StravaActivityLap(
        strava_activity_id=strava_activity_pk,
        lap_index=lap_index,
        elapsed_time_s=elapsed_time,
        moving_time_s=raw.get("moving_time"),
        average_heartrate=raw.get("average_heartrate"),
        average_speed_m_s=raw.get("average_speed"),
        fetched_at=fetched_at,
    )


async def _replace_laps(
    db: Any, *, strava_activity_pk: int, raw_laps: list[dict[str, Any]]
) -> list[MatchLap]:
    """Delete-then-insert an activity's laps within the caller's transaction.

    Data-model.md §5 "Refresh semantics": recalculation replaces the
    activity's lap rows so ``UNIQUE(strava_activity_id, lap_index)`` always
    reflects the latest upstream state. Only called AFTER
    ``StravaClient.get_activity_laps`` succeeds, so a fetch failure (429,
    404, timeout, ...) never wipes previously-good laps.

    Returns the allow-listed laps as ``MatchLap`` (matching engine input) —
    built from the same allow-listed values persisted, so the comparison
    that follows in the same run is guaranteed consistent with what was
    just written.

    Side-effects: DELETE + INSERT + flush on ``db``. No commit (caller owns
    the transaction boundary).
    """
    await db.execute(
        sa_delete(StravaActivityLap).where(
            StravaActivityLap.strava_activity_id == strava_activity_pk
        )
    )

    fetched_at = _now_utc()
    lap_rows: list[StravaActivityLap] = []
    match_laps: list[MatchLap] = []
    skipped = 0
    for raw in raw_laps:
        lap_row = _allow_listed_lap(
            raw, strava_activity_pk=strava_activity_pk, fetched_at=fetched_at
        )
        if lap_row is None:
            skipped += 1
            continue
        lap_rows.append(lap_row)
        match_laps.append(
            MatchLap(
                lap_index=lap_row.lap_index,
                elapsed_time_s=lap_row.elapsed_time_s,
                average_heartrate=lap_row.average_heartrate,
            )
        )

    if lap_rows:
        db.add_all(lap_rows)
    await db.flush()

    if skipped:
        logger.warning(
            "interval_match_laps_skipped_malformed",
            extra={"strava_activity_id": strava_activity_pk, "skipped": skipped},
        )

    return match_laps


# ---------------------------------------------------------------------------
# Upsert IntervalMatchResult
# ---------------------------------------------------------------------------


async def _upsert_match_result(
    db: Any,
    *,
    structure_id: int,
    strava_activity_pk: int,
    result_json: dict[str, Any],
    triggered_by: MatchTrigger,
) -> None:
    """Upserts the single ``interval_match_results`` row for this pair
    (``UNIQUE(structure_id, strava_activity_id)`` — recompute = upsert,
    data-model.md §6). Side-effects: SELECT + INSERT/UPDATE + flush.
    """
    existing_result = await db.execute(
        select(IntervalMatchResult).where(
            IntervalMatchResult.structure_id == structure_id,
            IntervalMatchResult.strava_activity_id == strava_activity_pk,
        )
    )
    row = existing_result.scalar_one_or_none()
    computed_at = _now_utc()

    if row is None:
        db.add(
            IntervalMatchResult(
                structure_id=structure_id,
                strava_activity_id=strava_activity_pk,
                engine_version=ENGINE_VERSION,
                computed_at=computed_at,
                result_json=result_json,
                triggered_by=triggered_by,
            )
        )
    else:
        row.engine_version = ENGINE_VERSION
        row.computed_at = computed_at
        row.result_json = result_json
        row.triggered_by = triggered_by

    await db.flush()


# ---------------------------------------------------------------------------
# Core (one DB session, no session lifecycle decisions — caller commits)
# ---------------------------------------------------------------------------


class _MatchRunSkipped(Exception):
    """Internal signal: nothing to compute (structure/activity vanished
    mid-flight). NOT a failure — never marks the failure marker, never logs
    at warning+ beyond a single debug line. Caught only inside this module.
    """


async def _run_match_core(
    db: Any,
    *,
    structure_id: int,
    strava_activity_pk: int,
    triggered_by: MatchTrigger,
) -> None:
    """Fetch → allow-list/replace laps → compute → upsert, on one session.

    Raises on any genuine failure (missing Strava connection, Strava API
    error, DB error) — the caller (``run_match_deferred``) is the single
    place that decides what a raised exception means (rollback + mark
    failed + log). Raises nothing (returns early) for the two benign
    race conditions where there is structurally nothing left to compute.
    """
    structure_result = await db.execute(
        select(IntervalStructure)
        .options(selectinload(IntervalStructure.blocks))
        .where(IntervalStructure.id == structure_id)
    )
    structure = structure_result.scalar_one_or_none()
    if structure is None:
        # Structure was deleted between dispatch and job execution — its
        # match results cascade-deleted with it (data-model.md §7); nothing
        # to retry, nothing to store. Not a failure.
        raise _MatchRunSkipped("structure_missing")

    activity_result = await db.execute(
        select(StravaActivity).where(StravaActivity.id == strava_activity_pk)
    )
    activity = activity_result.scalar_one_or_none()
    if activity is None:
        raise _MatchRunSkipped("activity_missing")

    connection_result = await db.execute(
        select(StravaConnection).where(StravaConnection.id == activity.connection_id)
    )
    connection = connection_result.scalar_one_or_none()
    if connection is None:
        # Data-integrity edge case (an activity row with no owning
        # connection should not exist) — genuinely unrecoverable, surfaces
        # as `failed` so the coach sees something is wrong instead of a
        # silent permanent `computing`.
        raise RuntimeError("interval_match_connection_missing")

    async with StravaClient(connection, db) as client:
        raw_laps = await client.get_activity_laps(activity.strava_activity_id)

    match_laps = await _replace_laps(
        db, strava_activity_pk=strava_activity_pk, raw_laps=raw_laps
    )

    flattened_blocks = flatten_blocks(structure.blocks)
    payload = compute_match(flattened_blocks, match_laps)

    await _upsert_match_result(
        db,
        structure_id=structure_id,
        strava_activity_pk=strava_activity_pk,
        result_json=payload.model_dump(mode="json"),
        triggered_by=triggered_by,
    )


# ---------------------------------------------------------------------------
# Public deferred-job entrypoint
# ---------------------------------------------------------------------------


async def run_match_deferred(
    structure_id: int,
    strava_activity_id: int,
    triggered_by: MatchTrigger,
) -> None:
    """Deferred job: dispatch target for ``TaskDispatcher.dispatch(...)``.

    Opens its own ``AsyncSessionLocal`` and owns the full transaction
    (commit on success, rollback on failure) — the request-scoped session
    that triggered the dispatch (link / structure save / recalculate) is
    gone by the time a ``BackgroundTasks`` callback actually runs, same
    rule ``routers/strava_integration.py::_process_webhook_event_deferred``
    documents and follows.

    Never raises: any exception is caught, the transaction is rolled back,
    the in-process failure marker is set (see module docstring "Failure
    state"), and a single numeric-only log line is emitted — a background
    task has no caller left to propagate an exception to, and Strava-side
    hiccups (429/5xx/timeout) or a stale/broken connection must degrade to
    a retriable ``failed`` state, never crash the worker.

    Args:
        structure_id: PK of the ``IntervalStructure`` being compared.
        strava_activity_id: PK of ``strava_activities.id`` (the internal row
            id — same value ``routers/activities.py`` calls ``activity_id``).
        triggered_by: ``MatchTrigger.link`` / ``.structure_change`` /
            ``.manual`` — observability column on the persisted result.
    """
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            await _run_match_core(
                session,
                structure_id=structure_id,
                strava_activity_pk=strava_activity_id,
                triggered_by=triggered_by,
            )
            await session.commit()
            _clear_failed(structure_id, strava_activity_id)
        except _MatchRunSkipped as exc:
            await session.rollback()
            logger.debug(
                "interval_match_run_skipped",
                extra={
                    "structure_id": structure_id,
                    "strava_activity_id": strava_activity_id,
                    "reason": str(exc),
                },
            )
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            _mark_failed(structure_id, strava_activity_id)
            # logger.error (NOT logger.exception) — a traceback would embed the
            # upstream exception message, which can carry free-text lap names /
            # PII from Strava. Numeric IDs + error_type class name only (Ley 1581,
            # FR-016 numeric-only logs).
            logger.error(
                "interval_match_run_failed",
                extra={
                    "structure_id": structure_id,
                    "strava_activity_id": strava_activity_id,
                    "triggered_by": getattr(triggered_by, "value", str(triggered_by)),
                    "error_type": type(exc).__name__,
                },
            )
