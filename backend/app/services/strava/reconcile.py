"""Reconcile fallback: per-connection catch-up pull (specs/025-strava-activity-sync, T016).

Guarantees eventual delivery when the Strava webhook is missed or delayed
(FR-004, SC-002 — 100% of activities visible within 24 h). Triggered by
``POST /api/integrations/strava/reconcile`` (T017/T018, not yet wired), which
in turn is invoked by the daily GitHub Actions schedule
(contracts/api.md §E).

Inputs: the request-scoped ``AsyncSession`` (``db``). No other arguments —
``reconcile_all`` discovers every ``active`` ``StravaConnection`` itself.

Outputs: ``reconcile_all`` returns
``{"connections_processed": int, "activities_upserted": int,
"connections_broken": int}`` — numeric counters only, per FR-016 (no athlete
ids, names, or activity titles in the return value or in any log line this
module emits).

Side effects:
- Reads every ``StravaConnection`` with ``status=active``.
- For each, opens a ``StravaClient`` (services/strava/client.py), which
  transparently refreshes the access token when it is near/at expiry — a
  refresh failure is handled entirely inside the client (marks the
  connection ``broken``, sets ``last_error``, flushes); this module only
  observes the resulting ``connection.status`` afterward, it never mutates
  token fields itself.
- Pages through ``GET /athlete/activities?after=<last_sync_at - lookback>``
  and idempotently upserts each item into ``strava_activities``
  (``ingest_source=reconcile``).
- Re-fetches (``GET /activities/{id}``) any of the athlete's existing rows
  still flagged ``summary_complete=False`` (typically left that way by a
  webhook delivery with null fields, FR-015) and completes them in place.
- Advances ``connection.last_sync_at`` to "now" once a connection's pull
  finishes without a fatal error, and flushes (never commits — the
  request-scoped ``get_db`` dependency owns the transaction boundary, same
  convention as ``client.py``).
- Logs numeric identifiers only (``athlete_id``, counts, error types) — NEVER
  activity titles or athlete names (Ley 1581 minors-privacy gate; FR-016).

Field-stripping note: ``strava_activities`` has no GPS/location/description
columns at all (see ``models/strava_activity.py``), so this module enforces
data minimization by construction — it only ever reads the specific summary
keys listed in ``_apply_fields`` off the raw Strava payload, never a raw
passthrough. ``services/strava/ingest.py`` (T015, developed in parallel from
the same contract — see ``client.py``'s equivalent note about T013) owns the
webhook-triggered version of this same idempotent-upsert logic; the two
should be reconciled into one shared helper once T015 lands rather than
maintaining two field-mapping copies long-term.

Known limitation: the SELECT-then-INSERT upsert has a small race window if a
webhook delivery for the same ``strava_activity_id`` commits between this
module's existence check and its flush — the ``UNIQUE(strava_activity_id)``
constraint prevents an actual duplicate row (the flush would raise
``IntegrityError``), it just is not retried into an update within this run.
Acceptable for a once-daily batch job; not expected in practice given
Strava's own webhook-then-reconcile cadence.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.config import settings
from app.models.strava_activity import (
    StravaActivity,
    StravaIngestSource,
    StravaUpstreamState,
)
from app.models.strava_connection import StravaConnection, StravaConnectionStatus
from app.services.strava.client import (
    StravaAPIError,
    StravaAuthError,
    StravaClient,
    StravaNotFoundError,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Payload parsing helpers
# ---------------------------------------------------------------------------


def _parse_utc(raw: str | None) -> datetime | None:
    """Parse a Strava ISO-8601 UTC timestamp (e.g. ``"2018-02-16T14:52:54Z"``).

    Returns ``None`` for missing/malformed input — callers treat that as a
    reason to skip the payload rather than raise; one bad activity payload
    must not abort reconciliation for the rest of the connection.
    """
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_local_naive(raw: str | None) -> datetime | None:
    """Parse Strava's ``start_date_local`` as a naive local-time datetime.

    Strava formats this field with a spurious trailing ``"Z"`` even though it
    represents the athlete's local wall-clock time, not UTC — stripping
    ``tzinfo`` after parsing avoids implying a (false) UTC offset.
    """
    parsed = _parse_utc(raw)
    if parsed is None:
        return None
    return parsed.replace(tzinfo=None)


def _summary_complete(raw: dict[str, Any]) -> bool:
    """Heuristic completeness check for a raw Strava activity payload.

    ``average_heartrate``/``max_heartrate`` are legitimately absent for
    athletes without a HR sensor — that is NOT incompleteness. Incompleteness
    is: a bare ``resource_state=1`` ("meta" — Strava's sparsest shape), or a
    missing core stat (``elapsed_time``/``moving_time``/``distance``) that
    every real ride reports once Strava finishes processing it.
    """
    if raw.get("resource_state") == 1:
        return False
    return (
        raw.get("elapsed_time") is not None
        and raw.get("moving_time") is not None
        and raw.get("distance") is not None
    )


async def _upsert_activity(
    db: "AsyncSession",
    connection: StravaConnection,
    raw: dict[str, Any],
    *,
    ingest_source: StravaIngestSource,
) -> bool:
    """Idempotent upsert of one raw Strava activity payload (FR-005).

    Looks up the existing row by ``strava_activity_id``; creates one if
    absent, otherwise updates in place. Only the explicit summary fields
    below are ever read off ``raw`` — no GPS/location/description field is
    read or persisted (data-model.md §2 "Explicitly ABSENT columns").

    Returns ``True`` when a row was created or updated, ``False`` when the
    payload was missing a required field (``id`` or a start date) and was
    skipped — logged with numeric ids only, never the raw payload.
    """
    strava_activity_id = raw.get("id")
    start_utc = _parse_utc(raw.get("start_date"))
    start_local = _parse_local_naive(raw.get("start_date_local"))

    if strava_activity_id is None or start_utc is None or start_local is None:
        logger.warning(
            "strava_reconcile_skip_malformed",
            extra={"athlete_id": connection.athlete_id},
        )
        return False

    result = await db.execute(
        select(StravaActivity).where(
            StravaActivity.strava_activity_id == strava_activity_id
        )
    )
    activity = result.scalar_one_or_none()
    if activity is None:
        activity = StravaActivity(
            strava_activity_id=strava_activity_id,
            athlete_id=connection.athlete_id,
            connection_id=connection.id,
        )
        db.add(activity)

    activity.name = raw.get("name") or ""
    activity.sport_type = raw.get("sport_type") or raw.get("type") or "Ride"
    activity.start_date_utc = start_utc
    activity.start_date_local = start_local
    activity.elapsed_time_s = raw.get("elapsed_time") or 0
    activity.moving_time_s = raw.get("moving_time")
    activity.distance_m = raw.get("distance")
    activity.total_elevation_gain_m = raw.get("total_elevation_gain")
    activity.average_heartrate = raw.get("average_heartrate")
    activity.max_heartrate = raw.get("max_heartrate")
    activity.is_trainer = bool(raw.get("trainer", False))
    activity.upstream_state = StravaUpstreamState.present
    activity.ingest_source = ingest_source
    activity.summary_complete = _summary_complete(raw)

    return True


# ---------------------------------------------------------------------------
# Reconcile entrypoint
# ---------------------------------------------------------------------------


async def _reconcile_connection(
    db: "AsyncSession", connection: StravaConnection, *, now: datetime
) -> int:
    """Pull + upsert one active connection's window, then re-fetch its
    incomplete rows. Returns the number of activities upserted.

    Raises ``StravaAuthError``/``StravaAPIError`` (subclasses) on a fatal
    per-connection failure — the caller decides how to account for it;
    ``connection.status`` is the source of truth for whether it went
    ``broken`` (set internally by ``StravaClient`` on a refresh failure).
    """
    lookback = timedelta(hours=settings.strava_reconcile_lookback_hours)
    watermark = connection.last_sync_at or now
    after = watermark - lookback

    upserted = 0
    async with StravaClient(connection, db) as client:
        async for raw in client.list_athlete_activities(after=after, per_page=50):
            if await _upsert_activity(
                db, connection, raw, ingest_source=StravaIngestSource.reconcile
            ):
                upserted += 1

        incomplete = await db.execute(
            select(StravaActivity).where(
                StravaActivity.athlete_id == connection.athlete_id,
                StravaActivity.summary_complete.is_(False),
            )
        )
        for activity in incomplete.scalars().all():
            try:
                detail = await client.get_activity(activity.strava_activity_id)
            except StravaNotFoundError:
                activity.upstream_state = StravaUpstreamState.removed_upstream
                continue
            if await _upsert_activity(
                db, connection, detail, ingest_source=StravaIngestSource.reconcile
            ):
                upserted += 1

    connection.last_sync_at = now
    return upserted


async def reconcile_all(db: "AsyncSession") -> dict[str, int]:
    """Run the daily catch-up reconcile across every active connection.

    Iterates ``strava_connections`` with ``status=active`` (disconnected/
    broken connections are skipped — they need a re-connect, not a pull),
    calls ``_reconcile_connection`` for each, and flushes after every
    connection so a failure on connection N does not roll back connections
    1..N-1 (this module never calls ``commit`` — the request-scoped ``get_db``
    dependency owns the transaction boundary).

    A connection counts toward ``connections_broken`` when, after processing
    (success or failure), its ``status`` is ``broken`` — that transition only
    ever happens inside ``StravaClient`` on a refresh failure (401), so this
    is an observation, not a duplicate decision.
    """
    connections_processed = 0
    activities_upserted = 0
    connections_broken = 0
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(StravaConnection).where(
            StravaConnection.status == StravaConnectionStatus.active
        )
    )
    connections = result.scalars().all()

    for connection in connections:
        connections_processed += 1
        try:
            activities_upserted += await _reconcile_connection(db, connection, now=now)
            await db.flush()
        except StravaAuthError:
            logger.warning(
                "strava_reconcile_auth_error",
                extra={"athlete_id": connection.athlete_id},
            )
            await db.flush()
        except StravaAPIError as exc:
            logger.warning(
                "strava_reconcile_api_error",
                extra={
                    "athlete_id": connection.athlete_id,
                    "error_type": type(exc).__name__,
                },
            )
            await db.flush()
        finally:
            if connection.status == StravaConnectionStatus.broken:
                connections_broken += 1

    logger.info(
        "strava_reconcile_summary",
        extra={
            "connections_processed": connections_processed,
            "activities_upserted": activities_upserted,
            "connections_broken": connections_broken,
        },
    )

    return {
        "connections_processed": connections_processed,
        "activities_upserted": activities_upserted,
        "connections_broken": connections_broken,
    }
