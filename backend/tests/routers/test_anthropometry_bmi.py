"""Regresión del bug de acoplamiento BMI↔LMS (feature 003 / T007, FR-001a).

Contrato: al crear un registro antropométrico con peso + talla, el BMI se
persiste SIEMPRE, incluso si la tabla de referencia LMS está vacía. Con LMS
sembrada, además se persisten percentiles y z-scores.

Este test FALLA en `main` (donde `bmi = growth.bmi if growth else None` deja el
BMI en NULL cuando la LMS está vacía) y PASA tras el fix.

Estrategia: app mínima + SQLite async in-memory + overrides de dependencias.
"""
from __future__ import annotations

from datetime import date
from typing import AsyncGenerator
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.dependencies import (
    get_current_user,
    get_db,
    get_notification_service,
    get_task_dispatcher,
    verify_athlete_access,
)
from app.models import Base
from app.models.anthropometry import AnthropometricRecord
from app.models.athlete import Athlete, Sex
from app.models.user import User, UserRole
from app.routers import anthropometry as anthropometry_router
from app.seed_growth_data import _parse_csv_content, bulk_insert_lms

# CSV LMS mínimo cubriendo la edad/sexo del atleta de prueba (varón ~11 años).
_LMS_HEIGHT = "Sex,Agemos,L,M,S\n1,24,1.0,86.0,0.04\n1,240.5,0.9,175.0,0.045\n"
_LMS_BMI = "Sex,Agemos,L,M,S\n1,24,-2.0,16.5,0.08\n1,240.5,-1.5,21.0,0.13\n"
_LMS_WEIGHT = "Sex,Agemos,L,M,S\n1,24,-0.2,12.6,0.10\n1,240.5,-1.0,62.0,0.16\n"


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Base.metadata.tables[t]
        for t in ("athletes", "anthropometric_records", "growth_reference_lms")
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def athlete(session_factory) -> Athlete:
    async with session_factory() as s:
        ath = Athlete(
            user_id=1,
            first_name="Test",
            last_name="Atleta",
            birth_date=date(2015, 1, 1),
            sex=Sex.M,
            club_id=1,
            created_by=1,
        )
        s.add(ath)
        await s.commit()
        await s.refresh(ath)
        # desligar de la sesión para usarlo en el override
        s.expunge(ath)
        return ath


@pytest_asyncio.fixture
async def app_client(
    session_factory, athlete, monkeypatch
) -> AsyncGenerator[tuple[AsyncClient, async_sessionmaker], None]:
    # Nunca disparar la rama de notificación (consultaría tablas inexistentes)
    monkeypatch.setattr(
        anthropometry_router, "detect_approaching_circa", lambda _offset: False
    )

    app = FastAPI()
    app.include_router(anthropometry_router.router, prefix="/api/athletes")

    coach = User(id=1, email="c@x.co", role=UserRole.coach)

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as s:
            yield s
            await s.commit()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[verify_athlete_access] = lambda: athlete
    # require_role([...]) depende de get_current_user; basta con overridear este.
    app.dependency_overrides[get_current_user] = lambda: coach
    app.dependency_overrides[get_notification_service] = lambda: MagicMock()
    app.dependency_overrides[get_task_dispatcher] = lambda: MagicMock()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, session_factory
    app.dependency_overrides.clear()


_BODY = {
    "evaluation_date": "2026-05-01",
    "weight_kg": "38.0",
    "standing_height_cm": "145.0",
    "sitting_height_cm": "74.0",
}


async def _latest_record(session_factory) -> AnthropometricRecord:
    async with session_factory() as s:
        result = await s.execute(
            select(AnthropometricRecord).order_by(AnthropometricRecord.id.desc())
        )
        return result.scalars().first()


@pytest.mark.asyncio
async def test_bmi_persisted_when_lms_empty(app_client, athlete) -> None:
    client, factory = app_client
    resp = await client.post(f"/api/athletes/{athlete.id}/anthropometry", json=_BODY)
    assert resp.status_code == 201, resp.text

    record = await _latest_record(factory)
    assert record is not None
    # BMI = 38.0 / (1.45**2) = 18.07 — DEBE persistirse aun con LMS vacía
    assert record.bmi is not None
    assert float(record.bmi) == pytest.approx(18.07, abs=0.05)
    # Sin LMS: percentiles permanecen NULL
    assert record.bmi_percentile is None
    assert record.height_percentile is None


@pytest.mark.asyncio
async def test_percentiles_persisted_when_lms_seeded(
    app_client, athlete, session_factory
) -> None:
    client, factory = app_client
    # Sembrar LMS antes del POST
    async with session_factory() as s:
        for content, indicator in (
            (_LMS_HEIGHT, "height_for_age"),
            (_LMS_BMI, "bmi_for_age"),
            (_LMS_WEIGHT, "weight_for_age"),
        ):
            await bulk_insert_lms(s, _parse_csv_content(content, indicator))
        await s.commit()

    resp = await client.post(f"/api/athletes/{athlete.id}/anthropometry", json=_BODY)
    assert resp.status_code == 201, resp.text

    record = await _latest_record(factory)
    assert record.bmi is not None
    assert record.bmi_percentile is not None
    assert record.height_percentile is not None
    assert record.bmi_z_score is not None
