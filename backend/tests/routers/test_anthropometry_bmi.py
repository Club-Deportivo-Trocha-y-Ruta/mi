"""Regresión del bug de acoplamiento BMI↔LMS (feature 003 / T007, FR-001a)
y contrato de referencia única OMS 2007 del router (feature 040 / T018, T022).

Contrato: al crear un registro antropométrico con peso + talla, el BMI se
persiste SIEMPRE, incluso si la tabla de referencia LMS está vacía. Con LMS
sembrada, además se persisten percentiles y z-scores contra la OMS 2007
(``GrowthSource.WHO``, feature 040): todo registro nuevo guarda
``growth_source='WHO'`` y, por encima de los 10 años (120.5 meses), el peso/
edad se guarda en NULL (la OMS no publica esa referencia para esas edades).

Estrategia: app mínima + SQLite async in-memory + overrides de dependencias.
"""
from __future__ import annotations

import json
import math
from datetime import date
from decimal import Decimal
from pathlib import Path
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
from app.models.anthropometry import AnthropometricRecord, MaturationStatus
from app.models.athlete import Athlete, Sex
from app.models.growth import GrowthSource
from app.models.user import User, UserRole
from app.routers import anthropometry as anthropometry_router
from app.seed_growth_data import _parse_who_csv_content, bulk_insert_lms
from tests.helpers.audit_tables import AUDIT_TABLES

# CSV LMS mínimo (formato OMS: ``sex,age_months,L,M,S``) cubriendo la edad/sexo
# del atleta de prueba (varón ~11 años). Valores sintéticos, no reales — solo
# para ejercitar la ruta de cálculo con la tabla poblada.
_WHO_LMS_HEIGHT = "sex,age_months,L,M,S\nM,24,1.0,86.0,0.04\nM,240.5,0.9,175.0,0.045\n"
_WHO_LMS_BMI = "sex,age_months,L,M,S\nM,24,-2.0,16.5,0.08\nM,240.5,-1.5,21.0,0.13\n"
_WHO_LMS_WEIGHT = "sex,age_months,L,M,S\nM,24,-0.2,12.6,0.10\nM,240.5,-1.0,62.0,0.16\n"

# Ruta al JSON fuente del cliente — misma tabla que consume el navegador y que
# alimenta el seed real (``backend/app/data/who_lms/``, feature 040 / T020-T021).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_WHO_JSON_PATH = _REPO_ROOT / "frontend" / "src" / "data" / "growth-reference-who.json"


def _who_json_rows(indicator: str, sex: str = "M") -> list[dict]:
    with _WHO_JSON_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return data["indicators"][indicator][sex]


def _lms_interp_from_json(rows: list[dict], age_months: float) -> tuple[float, float, float]:
    """Interpola L/M/S linealmente entre los dos puntos más cercanos leyendo
    directamente del JSON del cliente — cálculo "a mano", independiente de
    ``get_lms_params``, para verificar el resultado real del servidor."""
    ordered = sorted(rows, key=lambda r: r["age"])
    if age_months <= ordered[0]["age"]:
        r = ordered[0]
        return float(r["L"]), float(r["M"]), float(r["S"])
    if age_months >= ordered[-1]["age"]:
        r = ordered[-1]
        return float(r["L"]), float(r["M"]), float(r["S"])

    lower = upper = None
    for row in ordered:
        if row["age"] <= age_months:
            lower = row
        if row["age"] >= age_months and upper is None:
            upper = row

    assert lower is not None and upper is not None
    if lower["age"] == upper["age"]:
        return float(lower["L"]), float(lower["M"]), float(lower["S"])

    t = (age_months - lower["age"]) / (upper["age"] - lower["age"])
    return (
        float(lower["L"]) + t * (float(upper["L"]) - float(lower["L"])),
        float(lower["M"]) + t * (float(upper["M"]) - float(lower["M"])),
        float(lower["S"]) + t * (float(upper["S"]) - float(lower["S"])),
    )


def _hand_z_score(value: float, L: float, M: float, S: float) -> float:
    """Fórmula LMS de Cole & Green (1992) escrita de forma independiente
    (no importa ``calculate_z_score`` de la app) para el cálculo a mano."""
    if abs(L) < 1e-10:
        z = math.log(value / M) / S
    else:
        z = ((value / M) ** L - 1) / (L * S)
    return max(-3.0, min(3.0, z))


async def _seed_full_who_lms(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Siembra las tablas OMS reales para sexo M (T018).

    Reusa el seed real de ``app.seed_growth_data`` (T020/T021, en desarrollo
    concurrente); si el path OMS aún no está disponible cuando corre este
    test, cae a sembrar las filas mínimas necesarias leyendo directamente el
    JSON del cliente (misma fuente ya revisada que alimenta el seed real).
    """
    async with session_factory() as s:
        try:
            from app.seed_growth_data import WHO_DATA_DIR, WHO_SOURCES, parse_who_csv_file

            for source_info in WHO_SOURCES:
                csv_path = WHO_DATA_DIR / source_info["filename"]
                if not csv_path.exists():
                    raise ImportError(f"WHO seed CSV aún no disponible: {csv_path}")
                await bulk_insert_lms(s, parse_who_csv_file(csv_path, source_info["indicator"]))
        except (ImportError, AttributeError):
            for indicator in ("height_for_age", "bmi_for_age", "weight_for_age"):
                rows = [
                    {
                        "source": "WHO",
                        "indicator": indicator,
                        "sex": "M",
                        "age_months": float(point["age"]),
                        "L": float(point["L"]),
                        "M": float(point["M"]),
                        "S": float(point["S"]),
                    }
                    for point in _who_json_rows(indicator, "M")
                ]
                await bulk_insert_lms(s, rows)
        await s.commit()


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
        for t in ("athletes", "anthropometric_records", "growth_reference_lms", *AUDIT_TABLES)
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
    # Sembrar LMS (formato OMS) antes del POST — feature 040: el router ahora
    # calcula contra GrowthSource.WHO, no CDC.
    async with session_factory() as s:
        for content, indicator in (
            (_WHO_LMS_HEIGHT, "height_for_age"),
            (_WHO_LMS_BMI, "bmi_for_age"),
            (_WHO_LMS_WEIGHT, "weight_for_age"),
        ):
            await bulk_insert_lms(s, _parse_who_csv_content(content, indicator))
        await s.commit()

    resp = await client.post(f"/api/athletes/{athlete.id}/anthropometry", json=_BODY)
    assert resp.status_code == 201, resp.text

    record = await _latest_record(factory)
    assert record.bmi is not None
    assert record.bmi_percentile is not None
    assert record.height_percentile is not None
    assert record.bmi_z_score is not None


@pytest.mark.asyncio
async def test_growth_source_persisted_as_who_on_create(app_client, athlete) -> None:
    """Feature 040 (T022): el router persiste growth_source='WHO' en todo
    registro nuevo — tanto en la respuesta (POST y GET) como en la fila."""
    client, factory = app_client
    resp = await client.post(f"/api/athletes/{athlete.id}/anthropometry", json=_BODY)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["growth_source"] == "WHO"

    record = await _latest_record(factory)
    assert record is not None
    assert record.growth_source == GrowthSource.WHO

    list_resp = await client.get(f"/api/athletes/{athlete.id}/anthropometry")
    assert list_resp.status_code == 200, list_resp.text
    records = list_resp.json()
    assert len(records) == 1
    assert records[0]["growth_source"] == "WHO"


@pytest.mark.asyncio
async def test_growth_source_null_for_legacy_rows_not_recomputed(
    app_client, athlete, session_factory
) -> None:
    """Feature 040: una fila legacy (creada antes de esta feature, o no
    recalculada aún por el backfill idempotente de T023) conserva
    growth_source=NULL — el GET no debe inventar un valor para ella."""
    client, factory = app_client
    async with session_factory() as s:
        legacy = AnthropometricRecord(
            athlete_id=athlete.id,
            evaluation_date=date(2024, 1, 1),
            weight_kg=Decimal("30.0"),
            standing_height_cm=Decimal("130.0"),
            sitting_height_cm=Decimal("68.0"),
            leg_length_cm=Decimal("62.0"),
            leg_sitting_ratio=Decimal("0.9118"),
            maturity_offset=Decimal("-2.5"),
            age_at_phv=Decimal("13.0"),
            maturation_status=MaturationStatus.pre_phv,
            evaluated_by=1,
            growth_source=None,
        )
        s.add(legacy)
        await s.commit()

    list_resp = await client.get(f"/api/athletes/{athlete.id}/anthropometry")
    assert list_resp.status_code == 200, list_resp.text
    records = list_resp.json()
    assert len(records) == 1
    assert records[0]["growth_source"] is None


# ---------------------------------------------------------------------------
# T018 — referencia única OMS 2007 en el POST: growth_source, z-scores a mano
# y umbral de los 10 años (120.5 meses) para peso/edad.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_stores_who_source_and_matches_hand_computed_z(
    app_client, athlete, session_factory
) -> None:
    """Atleta de ~8 años (100.44 meses, <= 120.5): growth_source='WHO', los
    z-scores de talla/IMC coinciden (±0.02) con un cálculo LMS hecho a mano
    desde las filas del JSON del cliente, y peso/edad queda poblado."""
    client, factory = app_client
    await _seed_full_who_lms(factory)

    birth_date = date(2016, 9, 1)
    eval_date = date(2025, 1, 15)
    athlete.birth_date = birth_date  # mismo objeto que usa el override de FastAPI

    weight_kg = 25.0
    standing_height_cm = 128.0
    body = {
        "evaluation_date": eval_date.isoformat(),
        "weight_kg": str(weight_kg),
        "standing_height_cm": str(standing_height_cm),
        "sitting_height_cm": "68.0",
    }
    resp = await client.post(f"/api/athletes/{athlete.id}/anthropometry", json=body)
    assert resp.status_code == 201, resp.text
    payload = resp.json()

    assert payload["growth_source"] == "WHO"

    age_decimal = round((eval_date - birth_date).days / 365.25, 2)
    age_months = age_decimal * 12

    l_h, m_h, s_h = _lms_interp_from_json(_who_json_rows("height_for_age"), age_months)
    expected_height_z = _hand_z_score(standing_height_cm, l_h, m_h, s_h)
    assert payload["height_z_score"] == pytest.approx(expected_height_z, abs=0.02)

    bmi_value = weight_kg / (standing_height_cm / 100) ** 2
    l_b, m_b, s_b = _lms_interp_from_json(_who_json_rows("bmi_for_age"), age_months)
    expected_bmi_z = _hand_z_score(bmi_value, l_b, m_b, s_b)
    assert payload["bmi_z_score"] == pytest.approx(expected_bmi_z, abs=0.02)

    # 8 años (<= 120.5 meses): peso/edad OMS sigue disponible
    assert payload["weight_z_score"] is not None
    assert payload["weight_percentile"] is not None
    l_w, m_w, s_w = _lms_interp_from_json(_who_json_rows("weight_for_age"), age_months)
    expected_weight_z = _hand_z_score(weight_kg, l_w, m_w, s_w)
    assert payload["weight_z_score"] == pytest.approx(expected_weight_z, abs=0.02)


@pytest.mark.asyncio
async def test_create_nulls_weight_fields_for_athlete_older_than_10_years(
    app_client, athlete, session_factory
) -> None:
    """Atleta de ~14 años (172.44 meses, > 120.5): la OMS no publica peso/
    edad para esa edad — weight_z_score/weight_percentile deben ser NULL,
    mientras que talla/IMC (publicados hasta los 19 años) sí se calculan."""
    client, factory = app_client
    await _seed_full_who_lms(factory)

    athlete.birth_date = date(2010, 9, 1)
    body = {
        "evaluation_date": "2025-01-15",
        "weight_kg": "48.0",
        "standing_height_cm": "160.0",
        "sitting_height_cm": "82.0",
    }
    resp = await client.post(f"/api/athletes/{athlete.id}/anthropometry", json=body)
    assert resp.status_code == 201, resp.text
    payload = resp.json()

    assert payload["growth_source"] == "WHO"
    assert payload["weight_z_score"] is None
    assert payload["weight_percentile"] is None
    assert payload["height_z_score"] is not None
    assert payload["bmi_z_score"] is not None

    record = await _latest_record(factory)
    assert record is not None
    assert record.growth_source == GrowthSource.WHO
    assert record.weight_z_score is None
    assert record.weight_percentile is None
