"""Tests T007 — ``StravaClient.get_activity_laps`` (feature 026).

Cubre:
  - Happy path: ``GET /activities/{id}/laps`` devuelve la lista de vueltas
    (array JSON de Strava) tal cual — el client NO hace allow-listing; eso
    corre en ``services/intervals/match_runner.py`` (contracts/api.md §laps).
  - Herencia del choke point ``_request``: 429 → ``StravaRateLimited``
    (con ``X-RateLimit-*`` parseado), 404 → ``StravaNotFoundError``.
  - Herencia del refresh de token: un token dentro del margen de expiración
    (``TOKEN_REFRESH_SKEW_SECONDS``) dispara el refresh ANTES de la llamada a
    laps y la request sale con el bearer nuevo.
  - Forma de la request: método ``GET``, path ``/activities/{id}/laps``,
    header ``Authorization: Bearer <token>``.

Patrón httpx: se inyecta un ``httpx.AsyncClient`` real respaldado por
``httpx.MockTransport`` a través del punto de inyección ``http_client=`` que
``StravaClient.__init__`` ya expone para tests (docstring del client). No hay
red real ni ``respx`` (no es dependencia del repo). El refresh se cubre
parcheando la referencia ``oauth.refresh_access_token`` que usa el client.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from cryptography.fernet import Fernet

from app.config import settings
from app.services.strava import client as client_module
from app.services.strava.client import (
    StravaClient,
    StravaNotFoundError,
    StravaRateLimited,
)
from app.services.strava.token_store import encrypt_token
from app.models.strava_connection import StravaConnection, StravaConnectionStatus

# NOTE: no module-level ``pytestmark = pytest.mark.asyncio`` — pytest.ini
# sets ``asyncio_mode = "auto"`` repo-wide.


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _strava_token_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide a valid Fernet key so ``token_store`` can encrypt/decrypt the
    fixture connection's tokens (mirrors the feature-025 test convention)."""
    monkeypatch.setattr(
        settings, "strava_token_encryption_key", Fernet.generate_key().decode()
    )


class _FakeDB:
    """Minimal stand-in for the request-scoped ``AsyncSession``.

    ``StravaClient`` only ever calls ``flush()`` on the token-refresh path;
    the happy/error paths never touch the DB. Counting flushes lets the
    refresh test assert the rotated token was persisted.
    """

    def __init__(self) -> None:
        self.flush_calls = 0

    async def flush(self) -> None:
        self.flush_calls += 1


def _make_connection(
    *, access_token: str = "AT_PLAIN", expires_in_seconds: int = 3600
) -> StravaConnection:
    now = datetime.now(timezone.utc)
    return StravaConnection(
        id=1,
        athlete_id=1,
        strava_athlete_id=999_000,
        status=StravaConnectionStatus.active,
        access_token_enc=encrypt_token(access_token),
        refresh_token_enc=encrypt_token("RT_PLAIN"),
        token_expires_at=now + timedelta(seconds=expires_in_seconds),
        scope_granted="activity:read_all",
        authorized_by_user_id=1,
        connected_at=now,
    )


def _mock_http_client(handler) -> httpx.AsyncClient:
    """Injectable ``httpx.AsyncClient`` backed by ``MockTransport``.

    Same ``base_url`` as production (``settings.strava_api_base_url``) so the
    relative path the client builds resolves identically.
    """
    return httpx.AsyncClient(
        base_url=settings.strava_api_base_url,
        transport=httpx.MockTransport(handler),
        timeout=5.0,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_get_activity_laps_returns_raw_lap_list() -> None:
    laps_payload = [
        {
            "id": 100,
            "lap_index": 0,
            "elapsed_time": 312,
            "moving_time": 300,
            "average_heartrate": 142.0,
            "average_speed": 5.1,
        },
        {
            "id": 101,
            "lap_index": 1,
            "elapsed_time": 90,
            "moving_time": 88,
            "average_heartrate": 158.0,
            "average_speed": 6.4,
        },
    ]
    recorded: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(request)
        return httpx.Response(200, json=laps_payload)

    async with _mock_http_client(handler) as http:
        client = StravaClient(_make_connection(), _FakeDB(), http_client=http)
        result = await client.get_activity_laps(456)

    # Passed through verbatim — the client does NOT allow-list (match_runner does).
    assert result == laps_payload
    assert len(recorded) == 1
    assert recorded[0].method == "GET"
    assert recorded[0].url.path.endswith("/activities/456/laps")
    assert recorded[0].headers["Authorization"] == "Bearer AT_PLAIN"


async def test_get_activity_laps_returns_empty_list_when_no_laps() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    async with _mock_http_client(handler) as http:
        client = StravaClient(_make_connection(), _FakeDB(), http_client=http)
        result = await client.get_activity_laps(789)

    assert result == []


# ---------------------------------------------------------------------------
# Error paths inherited from ``_request`` choke point
# ---------------------------------------------------------------------------


async def test_get_activity_laps_429_raises_rate_limited() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={
                "X-RateLimit-Limit": "200,2000",
                "X-RateLimit-Usage": "180,1500",
            },
            json={"message": "Rate Limit Exceeded"},
        )

    async with _mock_http_client(handler) as http:
        client = StravaClient(_make_connection(), _FakeDB(), http_client=http)
        with pytest.raises(StravaRateLimited) as excinfo:
            await client.get_activity_laps(1)

    assert excinfo.value.status_code == 429
    assert excinfo.value.rate_limit is not None
    assert excinfo.value.rate_limit.usage_15min == 180
    assert excinfo.value.rate_limit.limit_daily == 2000


async def test_get_activity_laps_404_raises_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Resource Not Found"})

    async with _mock_http_client(handler) as http:
        client = StravaClient(_make_connection(), _FakeDB(), http_client=http)
        with pytest.raises(StravaNotFoundError) as excinfo:
            await client.get_activity_laps(1)

    assert excinfo.value.status_code == 404


# ---------------------------------------------------------------------------
# Token-refresh inheritance
# ---------------------------------------------------------------------------


async def test_get_activity_laps_refreshes_near_expiry_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A connection whose token is within ``TOKEN_REFRESH_SKEW_SECONDS`` of
    expiry refreshes BEFORE the laps call, and the request goes out with the
    rotated bearer — proving ``get_activity_laps`` inherits the refresh from
    the ``_request``/``_ensure_fresh_access_token`` choke point."""

    async def fake_refresh(refresh_token: str) -> SimpleNamespace:
        return SimpleNamespace(
            access_token="AT_REFRESHED",
            refresh_token="RT_REFRESHED",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
        )

    monkeypatch.setattr(client_module.oauth, "refresh_access_token", fake_refresh)

    recorded: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(request)
        return httpx.Response(200, json=[])

    # 10 s to expiry < 300 s skew → refresh path.
    connection = _make_connection(expires_in_seconds=10)
    db = _FakeDB()

    async with _mock_http_client(handler) as http:
        client = StravaClient(connection, db, http_client=http)
        result = await client.get_activity_laps(7)

    assert result == []
    assert recorded[0].headers["Authorization"] == "Bearer AT_REFRESHED"
    # Refresh persisted the rotated tokens via a single flush.
    assert db.flush_calls == 1
    assert connection.status == StravaConnectionStatus.active
