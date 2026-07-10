"""Async Strava API v3 client (specs/025-strava-activity-sync, T014).

Inputs: a ``StravaConnection`` row (encrypted tokens + expiry) and the
request-scoped ``AsyncSession`` that owns it, plus per-call arguments
(activity id, ``after`` watermark, pagination size, or a raw access token for
``deauthorize``).

Outputs: raw Strava API v3 JSON payloads (``dict`` / async stream of
``dict``) — callers (``services/strava/ingest.py``, ``reconcile.py``) are
responsible for stripping GPS/location fields before persistence (see
``data-model.md`` §2 "Explicitly ABSENT columns"); this module never persists
activity data itself.

Side effects:
- Reads/writes ``connection.access_token_enc`` / ``refresh_token_enc`` /
  ``token_expires_at`` / ``status`` / ``last_error`` in place and calls
  ``db.flush()`` (never ``commit()`` — the request-scoped ``get_db``
  dependency owns the transaction boundary) when a token refresh happens.
- Performs outbound HTTPS calls to ``settings.strava_api_base_url`` (activity
  reads) and ``settings.strava_oauth_base_url`` (deauthorize).
- Logs numeric identifiers only (``athlete_id``, HTTP path, status code) —
  NEVER activity titles, athlete names, or token contents (Ley 1581 minors
  privacy gate; FR-016). See ``token_store.py`` for the same rule applied to
  token contents.

Dependency on T013 (``services/strava/oauth.py``, not yet created at the time
this module was written): token refresh delegates to
``oauth.refresh_access_token(refresh_token: str) -> TokenRefreshResult``
where ``TokenRefreshResult`` exposes ``access_token: str``,
``refresh_token: str`` and ``expires_at: datetime`` (UTC, tz-aware), and
raises ``oauth.StravaOAuthError`` on a failed refresh (e.g. HTTP 400/401 from
Strava's ``/oauth/token`` endpoint). Until T013 lands, importing this module
will raise ``ModuleNotFoundError`` — this is the expected intermediate state
for two files developed in parallel from the same contract (research.md §4,
plan.md "Within US1").
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import httpx

from app.config import settings
from app.models.strava_connection import StravaConnection, StravaConnectionStatus
from app.services.strava import oauth
from app.services.strava.token_store import decrypt_token, encrypt_token

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Non-negotiable per repo convention: never construct httpx.AsyncClient()
# without an explicit timeout. Strava has no documented long-running
# endpoints in this feature's scope, so the default 30 s budget applies.
REQUEST_TIMEOUT_SECONDS = 30.0

# Strava access tokens expire every 6 h (21 600 s). A 5-minute skew is a
# "small skew" relative to that window — comfortably refreshes before
# expiry without hammering the token endpoint on every request near the
# boundary.
TOKEN_REFRESH_SKEW_SECONDS = 300

# Strava's own ceiling for `/athlete/activities` pagination.
MAX_PER_PAGE = 200


# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------


class StravaAPIError(Exception):
    """Base error for any non-2xx response from the Strava API.

    Callers (``ingest.py``, ``reconcile.py``) catch this (or a subclass) to
    decide connection-state transitions; this module never mutates
    ``connection.status`` on generic API errors — only on refresh failure
    (see ``StravaAuthError`` raised from token refresh) or 401 responses.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class StravaAuthError(StravaAPIError):
    """Access token invalid/revoked (401), or refresh failed.

    Raised both when a refresh attempt fails (``oauth.StravaOAuthError``,
    connection is marked ``broken`` as a side effect before raising) and when
    Strava rejects an otherwise-fresh token with 401 (connection state is
    left untouched here — the caller decides, since a single stray 401 is not
    necessarily a revoked account).
    """


@dataclass(frozen=True)
class StravaRateLimitStatus:
    """Parsed ``X-RateLimit-*`` headers (15-minute window + daily window)."""

    limit_15min: int | None
    usage_15min: int | None
    limit_daily: int | None
    usage_daily: int | None


class StravaRateLimited(StravaAPIError):
    """429 response — caller MUST back off (exponential backoff owned by the
    reconcile/ingest layer, not this client)."""

    def __init__(
        self, message: str, *, rate_limit: StravaRateLimitStatus | None = None
    ) -> None:
        super().__init__(message, status_code=429)
        self.rate_limit = rate_limit


class StravaNotFoundError(StravaAPIError):
    """404 — e.g. activity deleted/private/not visible to this token."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=404)


class StravaServerError(StravaAPIError):
    """5xx from Strava — transient, safe to retry with backoff upstream."""


def _parse_rate_limit(headers: httpx.Headers) -> StravaRateLimitStatus | None:
    """Parse Strava's ``X-RateLimit-Limit``/``X-RateLimit-Usage`` headers.

    Both are comma-separated ``"15min,daily"`` pairs, e.g. ``"200,2000"``.
    Returns ``None`` when neither header is present (e.g. mocked responses).
    """
    limit_raw = headers.get("X-RateLimit-Limit")
    usage_raw = headers.get("X-RateLimit-Usage")
    if not limit_raw and not usage_raw:
        return None

    def _split(raw: str | None) -> tuple[int | None, int | None]:
        if not raw:
            return None, None
        parts = raw.split(",")
        try:
            first = int(parts[0].strip()) if len(parts) > 0 and parts[0].strip() else None
            second = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip() else None
        except ValueError:
            return None, None
        return first, second

    limit_15min, limit_daily = _split(limit_raw)
    usage_15min, usage_daily = _split(usage_raw)
    return StravaRateLimitStatus(
        limit_15min=limit_15min,
        usage_15min=usage_15min,
        limit_daily=limit_daily,
        usage_daily=usage_daily,
    )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class StravaClient:
    """Per-connection Strava API v3 client with automatic token refresh.

    Bound to a single ``StravaConnection`` for the lifetime of the instance
    (one athlete). Construct a new instance per connection/request scope —
    do not share across athletes or across request-scoped DB sessions.

    Usage::

        async with StravaClient(connection, db) as client:
            activity = await client.get_activity(object_id)
            async for raw in client.list_athlete_activities(after=watermark):
                ...

    ``http_client`` and ``now`` are injection points for tests (mock the
    transport / freeze time) — production callers omit both.
    """

    def __init__(
        self,
        connection: StravaConnection,
        db: "AsyncSession",
        *,
        http_client: httpx.AsyncClient | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._connection = connection
        self._db = db
        self._external_client = http_client
        self._owned_client: httpx.AsyncClient | None = None
        self._now = now or (lambda: datetime.now(timezone.utc))

    async def __aenter__(self) -> "StravaClient":
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the internally-owned httpx client, if one was created.

        No-op when an external ``http_client`` was injected (tests own its
        lifecycle) or when no request has been made yet.
        """
        if self._owned_client is not None:
            await self._owned_client.aclose()
            self._owned_client = None

    def _client(self) -> httpx.AsyncClient:
        if self._external_client is not None:
            return self._external_client
        if self._owned_client is None:
            self._owned_client = httpx.AsyncClient(
                base_url=settings.strava_api_base_url,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        return self._owned_client

    # -- Token refresh --------------------------------------------------

    async def _ensure_fresh_access_token(self) -> str:
        """Return a valid bearer token, refreshing it first if needed.

        Refreshes when ``token_expires_at`` is within
        ``TOKEN_REFRESH_SKEW_SECONDS`` of now (or already past). On success,
        re-encrypts and persists the rotated access/refresh tokens + new
        expiry onto ``self._connection`` and flushes the session. On
        failure, marks the connection ``broken`` (``last_error="refresh_401"``),
        flushes, and raises ``StravaAuthError`` — callers must not retry the
        same connection without a re-connect.
        """
        connection = self._connection
        now = self._now()
        skew = timedelta(seconds=TOKEN_REFRESH_SKEW_SECONDS)

        # MySQL DATETIME columns round-trip as offset-naive; coerce to UTC-aware
        # before comparing with the aware ``now`` (stored values are UTC).
        expires_at = connection.token_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at - now > skew:
            return decrypt_token(connection.access_token_enc)

        logger.info(
            "strava_token_refresh_start",
            extra={"athlete_id": connection.athlete_id},
        )
        refresh_plain = decrypt_token(connection.refresh_token_enc)
        try:
            result = await oauth.refresh_access_token(refresh_plain)
        except oauth.StravaOAuthError as exc:
            connection.status = StravaConnectionStatus.broken
            connection.last_error = "refresh_401"
            await self._db.flush()
            logger.warning(
                "strava_token_refresh_failed",
                extra={
                    "athlete_id": connection.athlete_id,
                    "error_type": type(exc).__name__,
                },
            )
            raise StravaAuthError(
                "No se pudo renovar el token de Strava; conexión marcada como rota."
            ) from exc

        connection.access_token_enc = encrypt_token(result.access_token)
        connection.refresh_token_enc = encrypt_token(result.refresh_token)
        connection.token_expires_at = result.expires_at
        connection.last_error = None
        if connection.status != StravaConnectionStatus.active:
            connection.status = StravaConnectionStatus.active
        await self._db.flush()
        logger.info(
            "strava_token_refresh_ok",
            extra={"athlete_id": connection.athlete_id},
        )
        return result.access_token

    # -- Low-level request ------------------------------------------------

    async def _request(
        self, method: str, path: str, *, params: dict | None = None
    ) -> dict:
        token = await self._ensure_fresh_access_token()
        client = self._client()

        try:
            response = await client.request(
                method,
                path,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.TimeoutException as exc:
            logger.warning(
                "strava_api_timeout",
                extra={"athlete_id": self._connection.athlete_id, "path": path},
            )
            raise StravaAPIError(
                "Tiempo de espera agotado al llamar a la API de Strava."
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "strava_api_transport_error",
                extra={
                    "athlete_id": self._connection.athlete_id,
                    "path": path,
                    "error_type": type(exc).__name__,
                },
            )
            raise StravaAPIError(
                "Error de transporte al llamar a la API de Strava."
            ) from exc

        if response.status_code == 429:
            rate_limit = _parse_rate_limit(response.headers)
            logger.warning(
                "strava_rate_limited",
                extra={"athlete_id": self._connection.athlete_id, "path": path},
            )
            raise StravaRateLimited(
                "Límite de tasa de Strava alcanzado.", rate_limit=rate_limit
            )

        if response.status_code == 401:
            # Token was fresh (or just refreshed) yet Strava still rejected
            # it — revoked from Strava's side. Do not mutate connection
            # state here; the caller (ingest/reconcile) owns that decision
            # so a single unexpected 401 doesn't race a concurrent refresh.
            logger.warning(
                "strava_api_unauthorized",
                extra={"athlete_id": self._connection.athlete_id, "path": path},
            )
            raise StravaAuthError("Strava rechazó el token de acceso (401).")

        if response.status_code == 404:
            raise StravaNotFoundError(f"Recurso de Strava no encontrado ({path}).")

        if response.status_code >= 500:
            raise StravaServerError(
                f"Error de servidor de Strava ({response.status_code}).",
                status_code=response.status_code,
            )

        if response.status_code >= 400:
            logger.warning(
                "strava_api_error",
                extra={
                    "athlete_id": self._connection.athlete_id,
                    "path": path,
                    "status_code": response.status_code,
                },
            )
            raise StravaAPIError(
                f"Error de la API de Strava ({response.status_code}).",
                status_code=response.status_code,
            )

        return response.json()

    # -- Public API ---------------------------------------------------------

    async def get_activity(self, activity_id: int) -> dict:
        """Fetch one activity by id: ``GET /activities/{activity_id}``.

        Raises ``StravaNotFoundError`` if the activity no longer exists or
        isn't visible to this token (e.g. made private after the webhook
        fired) — callers treat that as "removed upstream" per FR-013.
        """
        return await self._request("GET", f"/activities/{activity_id}")

    async def get_activity_laps(self, activity_id: int) -> list[dict]:
        """Fetch an activity's device-recorded laps: ``GET /activities/{id}/laps``.

        Routed through the shared ``_request`` choke point, so it inherits the
        exact same behavior as every other read: automatic token refresh, 429
        → ``StravaRateLimited`` (caller backs off), and 404 →
        ``StravaNotFoundError`` (activity deleted/private/not visible to this
        token). Strava returns a JSON **array** of lap objects — passed through
        verbatim; this client performs no allow-listing itself.

        Privacy (feature 026 §D4 / Ley 1581 minors gate): the caller
        (``services/intervals/match_runner.py``) is the single place allowed to
        touch this payload, and it allow-lists only the non-geo numeric fields
        (``lap_index``, ``elapsed_time``, ``moving_time``, ``average_heartrate``,
        ``average_speed``) before persistence — GPS, polyline/map, lap name,
        cadence and watts are dropped and never stored or exposed.
        """
        return await self._request("GET", f"/activities/{activity_id}/laps")

    async def list_athlete_activities(
        self, after: datetime | int, per_page: int = 50
    ) -> AsyncIterator[dict]:
        """Paginated ``GET /athlete/activities`` stream, newest first.

        ``after`` accepts either a tz-aware ``datetime`` (converted to a Unix
        epoch second) or an already-epoch ``int``, matching the reconcile
        watermark contract (``last_sync_at`` minus
        ``strava_reconcile_lookback_hours``, contracts/api.md §B).

        Pages until Strava returns fewer than ``per_page`` items (Strava's
        own "last page" signal) or an empty page. Yields raw activity dicts
        — no GPS stripping or persistence happens in this module.
        """
        after_epoch = int(after.timestamp()) if isinstance(after, datetime) else int(after)
        page_size = min(per_page, MAX_PER_PAGE)
        page = 1

        while True:
            items = await self._request(
                "GET",
                "/athlete/activities",
                params={"after": after_epoch, "per_page": page_size, "page": page},
            )
            if not items:
                return
            for item in items:
                yield item
            if len(items) < page_size:
                return
            page += 1

    async def deauthorize(self, access_token: str) -> None:
        """Best-effort call to Strava's ``POST /oauth/deauthorize``.

        Takes the plaintext access token directly (not decrypted from
        ``self._connection`` — the caller, the family-disconnect flow at
        ``DELETE /api/athletes/{id}/strava/connection``, already holds it).
        Uses ``strava_oauth_base_url`` (not the v3 API base). Failures are
        logged and swallowed: per FR-014 the platform-side disconnect MUST
        proceed regardless of whether Strava's side succeeds — this call is
        a courtesy revoke, not a precondition for local disconnection.
        """
        client = self._client()
        try:
            response = await client.post(
                f"{settings.strava_oauth_base_url}/deauthorize",
                params={"access_token": access_token},
            )
        except httpx.HTTPError as exc:
            logger.warning(
                "strava_deauthorize_transport_error",
                extra={
                    "athlete_id": self._connection.athlete_id,
                    "error_type": type(exc).__name__,
                },
            )
            return

        if response.status_code >= 400:
            logger.warning(
                "strava_deauthorize_failed",
                extra={
                    "athlete_id": self._connection.athlete_id,
                    "status_code": response.status_code,
                },
            )
