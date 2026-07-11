"""Tests: GET /api/training/athlete-newsletters/summary (spec 028, T036-T037).

Estrategia: mismo patrón que test_athlete_monthly_newsletters_router.py —
SimpleNamespace + app.dependency_overrides + httpx.AsyncClient para los
tests HTTP-level, más llamada directa a la función del router para
verificar el guard anti-N+1 (una sola query) y el mapeo de estados.

Nota sobre RBAC en tests HTTP: `require_role([...])` construye una closure
nueva en cada invocación, así que sobreescribir
`app.dependency_overrides[require_role([...])]` directamente no aplica de
forma confiable (mismo patrón ya usado, con asserts laxos, en
test_athlete_monthly_newsletters_router.py). Para probar 403/422 con una
request HTTP real que sí llegue a la validación de query params,
sobreescribimos `get_current_user` (función estable, importada una sola
vez), igual que en tests/routers/conftest.py (race_analysis).

Cubre:
- Query única (no N+1) + mapeo de status: none/draft/sent, incluyendo
  approved/failed -> draft y outdated -> sent.
- Coach sin clubes -> items=[] sin consultar DB.
- Admin -> sin filtro de club.
- RBAC: sin auth -> 401; parent -> 403.
- Validación: month=13 -> 422; year=1999 -> 422.
- Happy path HTTP end-to-end.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models.athlete_newsletter import NewsletterStatus
from app.models.club import ClubRole
from app.models.user import UserRole


# ---------------------------------------------------------------------------
# Helpers: SimpleNamespace factories (estilo del archivo hermano)
# ---------------------------------------------------------------------------


def make_user(
    id_: int = 1,
    role: UserRole = UserRole.coach,
    club_id: int | None = 1,
) -> Any:
    memberships = []
    if role == UserRole.coach and club_id is not None:
        memberships = [SimpleNamespace(club_id=club_id, role_in_club=ClubRole.coach)]
    return SimpleNamespace(
        id=id_,
        email=f"{role.value}@test.com",
        first_name="Test",
        last_name="User",
        role=role,
        is_active=True,
        can_login=True,
        club_memberships=memberships,
    )


class _FakeResult:
    """Imita el resultado de db.execute(stmt) para un select de columnas."""

    def __init__(self, rows: list[tuple]):
        self._rows = rows

    def all(self) -> list[tuple]:
        return self._rows


@pytest.fixture(autouse=True)
def _clear_overrides_after_each_test():
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Unit-level: llamada directa a la función del router
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summary_single_query_and_status_mapping():
    """Una sola query (db.execute) y mapeo correcto de los 5 estados a 3 buckets."""
    from app.routers.athlete_monthly_newsletters import get_newsletter_status_summary

    generated = datetime(2026, 7, 2, 14, 3, 0, tzinfo=timezone.utc)
    sent = datetime(2026, 7, 2, 14, 10, 0, tzinfo=timezone.utc)

    rows = [
        (12, 345, NewsletterStatus.sent, generated, sent),
        (13, None, None, None, None),
        (14, 50, NewsletterStatus.draft, generated, None),
        (15, 60, NewsletterStatus.approved, generated, None),
        (16, 70, NewsletterStatus.failed, generated, None),
        (17, 80, NewsletterStatus.outdated, generated, sent),
    ]

    db = MagicMock()
    db.execute = AsyncMock(return_value=_FakeResult(rows))

    coach = make_user(role=UserRole.coach, club_id=1)

    result = await get_newsletter_status_summary(
        year=2026, month=7, db=db, current_user=coach,
    )

    assert db.execute.await_count == 1
    assert result.year == 2026
    assert result.month == 7
    assert len(result.items) == 6

    by_id = {item.athlete_id: item for item in result.items}

    assert by_id[12].status == "sent"
    assert by_id[12].newsletter_id == 345
    assert by_id[12].generated_at == generated
    assert by_id[12].sent_at == sent

    assert by_id[13].status == "none"
    assert by_id[13].newsletter_id is None
    assert by_id[13].generated_at is None
    assert by_id[13].sent_at is None

    assert by_id[14].status == "draft"
    assert by_id[15].status == "draft"  # approved -> draft bucket
    assert by_id[16].status == "draft"  # failed -> draft bucket
    assert by_id[17].status == "sent"  # outdated -> sent bucket (ya se envió)


@pytest.mark.asyncio
async def test_summary_coach_without_clubs_returns_empty_without_querying_db():
    """Coach sin clubes asignados -> items=[] y NO se consulta la DB (alerts.py)."""
    from app.routers.athlete_monthly_newsletters import get_newsletter_status_summary

    coach = make_user(role=UserRole.coach, club_id=None)
    db = MagicMock()
    db.execute = AsyncMock()

    result = await get_newsletter_status_summary(
        year=2026, month=7, db=db, current_user=coach,
    )

    assert result.year == 2026
    assert result.month == 7
    assert result.items == []
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_summary_admin_no_club_filter_single_query():
    """Admin ve todos los clubes (sin filtro) y sigue usando una sola query."""
    from app.routers.athlete_monthly_newsletters import get_newsletter_status_summary

    admin = make_user(id_=99, role=UserRole.admin)
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=_FakeResult([(1, None, None, None, None), (2, None, None, None, None)])
    )

    result = await get_newsletter_status_summary(
        year=2026, month=7, db=db, current_user=admin,
    )

    assert db.execute.await_count == 1
    assert len(result.items) == 2
    assert all(item.status == "none" for item in result.items)


# ---------------------------------------------------------------------------
# HTTP-level: RBAC + validación de query params
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summary_requires_auth():
    """Sin autenticación -> 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/training/athlete-newsletters/summary?year=2026&month=7"
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_summary_parent_forbidden():
    """Parent no puede acceder al resumen -> 403."""
    app.dependency_overrides[get_current_user] = lambda: make_user(role=UserRole.parent)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/training/athlete-newsletters/summary?year=2026&month=7"
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_summary_invalid_month_422():
    """month=13 -> 422 (fuera de rango 1-12)."""
    app.dependency_overrides[get_current_user] = lambda: make_user(role=UserRole.coach)

    async def _override_db():
        db = MagicMock()
        db.execute = AsyncMock(return_value=_FakeResult([]))
        yield db

    app.dependency_overrides[get_db] = _override_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/training/athlete-newsletters/summary?year=2026&month=13"
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_summary_invalid_year_422():
    """year=1999 -> 422 (fuera de rango 2020-2100)."""
    app.dependency_overrides[get_current_user] = lambda: make_user(role=UserRole.coach)

    async def _override_db():
        db = MagicMock()
        db.execute = AsyncMock(return_value=_FakeResult([]))
        yield db

    app.dependency_overrides[get_db] = _override_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/training/athlete-newsletters/summary?year=1999&month=5"
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_summary_missing_required_params_422():
    """Sin year/month -> 422 (ambos son requeridos)."""
    app.dependency_overrides[get_current_user] = lambda: make_user(role=UserRole.coach)

    async def _override_db():
        db = MagicMock()
        db.execute = AsyncMock(return_value=_FakeResult([]))
        yield db

    app.dependency_overrides[get_db] = _override_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/training/athlete-newsletters/summary")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_summary_happy_path_http_one_item_per_athlete():
    """200 + un item por atleta, incluyendo el caso status='none'."""
    coach = make_user(role=UserRole.coach, club_id=1)
    app.dependency_overrides[get_current_user] = lambda: coach

    rows = [
        (
            12,
            345,
            NewsletterStatus.sent,
            datetime(2026, 7, 2, 14, 3, tzinfo=timezone.utc),
            datetime(2026, 7, 2, 14, 10, tzinfo=timezone.utc),
        ),
        (13, None, None, None, None),
    ]

    async def _override_db():
        db = MagicMock()
        db.execute = AsyncMock(return_value=_FakeResult(rows))
        yield db

    app.dependency_overrides[get_db] = _override_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/training/athlete-newsletters/summary?year=2026&month=7"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["year"] == 2026
    assert data["month"] == 7
    assert len(data["items"]) == 2

    by_id = {item["athlete_id"]: item for item in data["items"]}
    assert by_id[12]["status"] == "sent"
    assert by_id[12]["newsletter_id"] == 345
    assert by_id[13]["status"] == "none"
    assert by_id[13]["newsletter_id"] is None
    assert by_id[13]["generated_at"] is None
    assert by_id[13]["sent_at"] is None

    # Privacidad: nunca nombres/DOB, solo IDs y estado.
    assert "first_name" not in str(data)
    assert "birth_date" not in str(data)
