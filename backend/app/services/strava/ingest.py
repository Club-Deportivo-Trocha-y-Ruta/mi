"""Idempotent Strava activity ingest + webhook event dispatch (specs/025-strava-activity-sync, T015).

Inputs:
- ``upsert_activity``: a ``StravaConnection`` row, a raw Strava activity
  payload (``dict``, as returned by ``services/strava/client.py``'s
  ``get_activity``/``list_athlete_activities``), and the ``StravaIngestSource``
  that produced it (``webhook`` | ``reconcile``).
- ``process_webhook_event``: a validated ``StravaWebhookEvent`` (schemas/strava.py)
  and the request-scoped or background-task ``AsyncSession`` the caller owns.

Outputs: ``upsert_activity`` returns the persisted/updated ``StravaActivity``
row. ``process_webhook_event`` returns ``None`` — its effect is entirely the
DB mutation (create/update an activity row, flag one as removed upstream, or
flip a connection to ``disconnected``).

Side effects:
- Writes to ``strava_activities`` (insert or in-place update) and, for the
  athlete-deauthorization case, to ``strava_connections.status``/``disconnected_at``.
- Calls ``db.flush()`` only — this module NEVER calls ``db.commit()``. The
  caller owns the transaction boundary: for webhook processing that is the
  background-task session opened by the router (T018); for the reconcile
  pull it is ``services/strava/reconcile.py`` (T016), which also reuses
  ``upsert_activity`` directly. This mirrors the convention already
  documented in ``services/strava/client.py``.
- May call the Strava API (``StravaClient.get_activity``) when a webhook
  ``create``/``update`` event needs the full activity payload.
- Logs numeric identifiers and a per-event correlation id ONLY — never an
  activity title, athlete name, or any location field (Ley 1581 minors
  privacy gate, FR-016). See the "Privacy" section below.

Privacy (Ley 1581, minors) — data minimization at the ingest boundary:
``_extract_summary_fields`` is an ALLOW-LIST, not a deny-list: it reads only
the specific keys enumerated below out of the raw Strava payload. GPS/location
fields (``start_latlng``, ``end_latlng``, ``map``/``map.polyline``,
``description``, photos, segment efforts) are never referenced by name here,
so a new field appearing in a future Strava API response can never leak into
the database by accident — it would simply be ignored, the same as any other
field this module doesn't explicitly ask for. ``StravaActivity`` (the model)
has no columns for any of those fields at all, providing a second,
independent layer of the same guarantee (schema-level, not just code-level).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.models.strava_activity import (
    StravaActivity,
    StravaIngestSource,
    StravaUpstreamState,
)
from app.models.strava_connection import StravaConnection, StravaConnectionStatus
from app.services.strava.client import StravaAPIError, StravaClient, StravaNotFoundError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.strava import StravaWebhookEvent

logger = logging.getLogger(__name__)

# Core numeric fields that a fully-synced activity is expected to have.
# ``average_heartrate``/``max_heartrate`` are deliberately EXCLUDED: a device
# with no heart-rate sensor legitimately (and permanently) reports them as
# null — that is not an "incomplete" delivery per FR-015, it is a complete
# delivery with no HR data. Reconcile (T016) re-fetches only rows where one
# of these three is still null, since those are the fields a first
# (typically webhook-triggered) fetch is documented to sometimes omit.
_CORE_SUMMARY_FIELDS: tuple[str, ...] = (
    "distance_m",
    "moving_time_s",
    "total_elevation_gain_m",
)

# Fields updated in place on a re-delivery ONLY when the incoming value is
# not null — a later delivery "completing" the summary must never regress a
# field that an earlier, more complete delivery already populated.
_UPDATABLE_IF_PRESENT: tuple[str, ...] = (
    "distance_m",
    "moving_time_s",
    "total_elevation_gain_m",
    "average_heartrate",
    "max_heartrate",
)


def _new_correlation_id() -> str:
    """Short opaque id for tying together the log lines of one event/upsert.

    Numeric-adjacent by design (hex, no separators) — never derived from or
    containing any athlete-identifying value.
    """
    return uuid.uuid4().hex[:12]


def _parse_strava_datetime(value: str | None) -> datetime | None:
    """Parse a Strava ISO-8601 timestamp (``...Z`` suffix) to a tz-aware UTC datetime."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _extract_summary_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """Allow-list extraction of the fields this module ever persists.

    See the module docstring's "Privacy" section — this is the entire
    boundary; nothing outside this key list is ever read from ``raw``.
    Values are returned as-is (``None`` when absent) — callers decide
    creation defaults vs. update semantics.
    """
    return {
        "name": raw.get("name"),
        "sport_type": raw.get("sport_type") or raw.get("type"),
        "start_date_utc": _parse_strava_datetime(raw.get("start_date")),
        "start_date_local": _parse_strava_datetime(raw.get("start_date_local")),
        "elapsed_time_s": raw.get("elapsed_time"),
        "moving_time_s": raw.get("moving_time"),
        "distance_m": raw.get("distance"),
        "total_elevation_gain_m": raw.get("total_elevation_gain"),
        "average_heartrate": raw.get("average_heartrate"),
        "max_heartrate": raw.get("max_heartrate"),
        "is_trainer": raw.get("trainer"),
    }


def _is_summary_complete(fields: dict[str, Any]) -> bool:
    return all(fields.get(name) is not None for name in _CORE_SUMMARY_FIELDS)


def _apply_incoming_fields(existing: StravaActivity, fields: dict[str, Any]) -> None:
    """Update ``existing`` in place from a re-delivery, never nulling a known value."""
    for key in _UPDATABLE_IF_PRESENT:
        value = fields.get(key)
        if value is not None:
            setattr(existing, key, value)
    if fields.get("name"):
        existing.name = fields["name"]
    if fields.get("sport_type"):
        existing.sport_type = fields["sport_type"]
    if fields.get("elapsed_time_s") is not None:
        existing.elapsed_time_s = fields["elapsed_time_s"]
    if fields.get("is_trainer") is not None:
        existing.is_trainer = bool(fields["is_trainer"])


# ---------------------------------------------------------------------------
# Public: idempotent upsert (FR-005)
# ---------------------------------------------------------------------------


async def upsert_activity(
    db: "AsyncSession",
    connection: StravaConnection,
    raw_activity: dict[str, Any],
    *,
    source: StravaIngestSource,
    correlation_id: str | None = None,
) -> StravaActivity:
    """Idempotently create-or-update one ``StravaActivity`` by ``strava_activity_id``.

    Any number of deliveries of the same activity (webhook replay, webhook +
    reconcile both observing it, reconcile re-fetching an incomplete row)
    collapse to exactly one row (FR-005, SC-003). A row found in
    ``upstream_state=removed_upstream`` is resurrected to ``present`` — a
    fresh create/update delivery is authoritative evidence the activity
    exists again upstream (e.g. it was restored, or the earlier ``delete``
    event was itself a false signal).

    Raises ``ValueError`` if ``raw_activity`` is missing ``id`` or either
    start-date field — both are always present on a real Strava activity
    representation; a payload missing them indicates a malformed mock/fixture
    in tests or an unexpected upstream shape change, and callers (webhook
    dispatch, reconcile) are expected to let this propagate rather than
    silently persist a half-formed row.

    Does NOT commit — see module docstring.
    """
    cid = correlation_id or _new_correlation_id()

    strava_activity_id = raw_activity.get("id")
    if strava_activity_id is None:
        raise ValueError("raw_activity is missing 'id' — cannot upsert without it")

    fields = _extract_summary_fields(raw_activity)
    if fields["start_date_utc"] is None or fields["start_date_local"] is None:
        raise ValueError(
            "raw_activity is missing start_date/start_date_local — cannot persist"
        )

    summary_complete = _is_summary_complete(fields)

    existing = await db.scalar(
        select(StravaActivity).where(
            StravaActivity.strava_activity_id == strava_activity_id
        )
    )

    if existing is None:
        activity = StravaActivity(
            strava_activity_id=strava_activity_id,
            athlete_id=connection.athlete_id,
            connection_id=connection.id,
            name=fields["name"] or "",
            sport_type=fields["sport_type"] or "ride",
            start_date_utc=fields["start_date_utc"],
            start_date_local=fields["start_date_local"],
            elapsed_time_s=fields["elapsed_time_s"] or 0,
            moving_time_s=fields["moving_time_s"],
            distance_m=fields["distance_m"],
            total_elevation_gain_m=fields["total_elevation_gain_m"],
            average_heartrate=fields["average_heartrate"],
            max_heartrate=fields["max_heartrate"],
            is_trainer=bool(fields["is_trainer"]),
            upstream_state=StravaUpstreamState.present,
            ingest_source=source,
            summary_complete=summary_complete,
        )
        db.add(activity)
        await db.flush()
        logger.info(
            "strava_activity_ingested",
            extra={
                "correlation_id": cid,
                "athlete_id": connection.athlete_id,
                "strava_activity_id": strava_activity_id,
                "ingest_source": source.value,
                "summary_complete": summary_complete,
                "row_created": True,
            },
        )
        return activity

    _apply_incoming_fields(existing, fields)
    if summary_complete:
        existing.summary_complete = True
    existing.upstream_state = StravaUpstreamState.present
    existing.ingest_source = source
    await db.flush()
    logger.info(
        "strava_activity_ingested",
        extra={
            "correlation_id": cid,
            "athlete_id": connection.athlete_id,
            "strava_activity_id": strava_activity_id,
            "ingest_source": source.value,
            "summary_complete": existing.summary_complete,
            "row_created": False,
        },
    )
    return existing


# ---------------------------------------------------------------------------
# Public: webhook event dispatch (contracts/api.md §B)
# ---------------------------------------------------------------------------


async def process_webhook_event(event: "StravaWebhookEvent", db: "AsyncSession") -> None:
    """Dispatch one Strava webhook event: activity create/update/delete, or athlete deauth.

    Called from the router's deferred ``BackgroundTasks`` handler (T018)
    AFTER the webhook POST has already returned ``200 {}`` — this function
    does not (and must not) participate in the 2-second ACK. It never raises
    for expected, non-error outcomes (unknown ``owner_id``, activity no
    longer fetchable, inactive connection racing an in-flight event); those
    are logged and swallowed so one bad/late event cannot break processing
    of the next one. Only genuinely unexpected exceptions propagate to the
    caller.

    Dispatch table (contracts/api.md §B):
    - Unknown ``owner_id`` (no ``strava_connections`` row) → ignore silently.
    - ``object_type=activity``, ``aspect_type`` in (``create``, ``update``)
      → fetch the full activity via ``StravaClient.get_activity`` and
      ``upsert_activity`` it (``ingest_source=webhook``).
    - ``object_type=activity``, ``aspect_type=delete`` → flag the existing
      row (if any) ``upstream_state=removed_upstream``; the row and any
      session link are KEPT, never hard-deleted (FR-013).
    - ``object_type=athlete``, ``updates.authorized`` == ``"false"`` (or
      ``False``) → connection ``status=disconnected`` (FR-014).
    - Duplicate/replayed deliveries are a no-op beyond what ``upsert_activity``
      already guarantees (idempotent by ``strava_activity_id``).

    Does NOT commit — see module docstring.
    """
    cid = _new_correlation_id()
    logger.info(
        "strava_webhook_event_received",
        extra={
            "correlation_id": cid,
            "object_type": event.object_type,
            "aspect_type": event.aspect_type,
            "object_id": event.object_id,
            "owner_id": event.owner_id,
        },
    )

    connection = await db.scalar(
        select(StravaConnection).where(
            StravaConnection.strava_athlete_id == event.owner_id
        )
    )
    if connection is None:
        logger.info(
            "strava_webhook_unknown_owner",
            extra={"correlation_id": cid, "owner_id": event.owner_id},
        )
        return

    if event.object_type == "athlete":
        await _process_athlete_event(event, connection, db, correlation_id=cid)
        return

    # object_type == "activity" from here on (schema restricts to these two).
    if connection.status != StravaConnectionStatus.active:
        # A disconnect/broken transition may race an in-flight activity
        # event for the same athlete; ingestion must not silently resume
        # for a connection that isn't active — a fresh connect is required.
        logger.info(
            "strava_webhook_activity_skipped_inactive_connection",
            extra={
                "correlation_id": cid,
                "athlete_id": connection.athlete_id,
                "connection_status": connection.status.value,
            },
        )
        return

    if event.aspect_type == "delete":
        await _process_activity_delete(event, connection, db, correlation_id=cid)
        return

    await _process_activity_upsert(event, connection, db, correlation_id=cid)


async def _process_athlete_event(
    event: "StravaWebhookEvent",
    connection: StravaConnection,
    db: "AsyncSession",
    *,
    correlation_id: str,
) -> None:
    # Strava sends webhook update values as strings ("false"/"true"); accept
    # the boolean form too for robustness against mocked/future payloads.
    authorized = event.updates.get("authorized")
    if authorized in ("false", False):
        connection.status = StravaConnectionStatus.disconnected
        connection.disconnected_at = datetime.now(timezone.utc)
        await db.flush()
        logger.info(
            "strava_connection_deauthorized",
            extra={
                "correlation_id": correlation_id,
                "athlete_id": connection.athlete_id,
            },
        )
        return

    logger.info(
        "strava_webhook_athlete_event_ignored",
        extra={
            "correlation_id": correlation_id,
            "athlete_id": connection.athlete_id,
            "update_keys": sorted(event.updates.keys()),
        },
    )


async def _process_activity_delete(
    event: "StravaWebhookEvent",
    connection: StravaConnection,
    db: "AsyncSession",
    *,
    correlation_id: str,
) -> None:
    activity = await db.scalar(
        select(StravaActivity).where(
            StravaActivity.strava_activity_id == event.object_id
        )
    )
    if activity is None:
        # Never synced (or already purely local) — nothing to flag.
        logger.info(
            "strava_webhook_delete_unknown_activity",
            extra={
                "correlation_id": correlation_id,
                "athlete_id": connection.athlete_id,
                "strava_activity_id": event.object_id,
            },
        )
        return

    activity.upstream_state = StravaUpstreamState.removed_upstream
    await db.flush()
    logger.info(
        "strava_activity_removed_upstream",
        extra={
            "correlation_id": correlation_id,
            "athlete_id": connection.athlete_id,
            "strava_activity_id": event.object_id,
        },
    )


async def _process_activity_upsert(
    event: "StravaWebhookEvent",
    connection: StravaConnection,
    db: "AsyncSession",
    *,
    correlation_id: str,
) -> None:
    async with StravaClient(connection, db) as client:
        try:
            raw_activity = await client.get_activity(event.object_id)
        except StravaNotFoundError:
            # Deleted/private/not visible by the time we fetched — treat as
            # a soft miss, not an error; a later delete/update event (or
            # reconcile) will reconcile the true state.
            logger.info(
                "strava_webhook_activity_not_found",
                extra={
                    "correlation_id": correlation_id,
                    "athlete_id": connection.athlete_id,
                    "strava_activity_id": event.object_id,
                },
            )
            return
        except StravaAPIError as exc:
            logger.warning(
                "strava_webhook_activity_fetch_failed",
                extra={
                    "correlation_id": correlation_id,
                    "athlete_id": connection.athlete_id,
                    "strava_activity_id": event.object_id,
                    "error_type": type(exc).__name__,
                },
            )
            return

    await upsert_activity(
        db,
        connection,
        raw_activity,
        source=StravaIngestSource.webhook,
        correlation_id=correlation_id,
    )
