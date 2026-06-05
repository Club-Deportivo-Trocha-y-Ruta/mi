"""Tests para el bloque antropométrico del newsletter mensual individual (T013).

Cubre (en orden):
(a) El builder emite BMI y percentiles numéricos para un registro completo con LMS.
(b) El builder emite 'unavailable_reasons' (no un guion) para un registro sin talla.
(c) Las claves antropométricas aparecen SOLO en pdf_only_blocks y NUNCA en
    email_blocks (FR-004 / SC-008).

Estrategia: se testea _build_anthropometry_block directamente con una sesión
SQLite async in-memory para evitar levantar la app completa.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.anthropometry import AnthropometricRecord, MaturationStatus, NutritionalStatus
from app.models.athlete import Athlete, Sex
from app.services.training.newsletter_builder import (
    _build_anthropometry_block,
    _anthropometry_unavailable_reason,
)


# ---------------------------------------------------------------------------
# Fixtures: motor SQLite in-memory + sessión
# ---------------------------------------------------------------------------

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
        for t in ("athletes", "anthropometric_records")
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def athlete(session_factory: async_sessionmaker[AsyncSession]) -> Athlete:
    async with session_factory() as s:
        ath = Athlete(
            user_id=1,
            first_name="Deportista",
            last_name="Prueba",
            birth_date=date(2013, 6, 15),
            sex=Sex.M,
            club_id=1,
            created_by=1,
        )
        s.add(ath)
        await s.commit()
        await s.refresh(ath)
        s.expunge(ath)
        return ath


def _make_complete_record(athlete_id: int) -> AnthropometricRecord:
    """Registro con todos los campos derivados populados (simula post-fix T007)."""
    return AnthropometricRecord(
        athlete_id=athlete_id,
        evaluation_date=date(2026, 5, 10),
        weight_kg=Decimal("42.0"),
        standing_height_cm=Decimal("152.0"),
        sitting_height_cm=Decimal("78.0"),
        leg_length_cm=Decimal("74.0"),
        leg_sitting_ratio=Decimal("0.9487"),
        maturity_offset=Decimal("-0.45"),
        age_at_phv=Decimal("13.78"),
        maturation_status=MaturationStatus.pre_phv,
        training_implications="Consolidar técnica de pedaleo.",
        evaluated_by=1,
        # Campos derivados presentes
        bmi=Decimal("18.18"),
        height_z_score=Decimal("0.32"),
        height_percentile=Decimal("62.6"),
        bmi_z_score=Decimal("-0.12"),
        bmi_percentile=Decimal("45.2"),
        weight_z_score=Decimal("0.08"),
        weight_percentile=Decimal("53.2"),
        nutritional_status=NutritionalStatus.adecuado,
    )


def _make_serialized_record_no_height() -> dict:
    """Diccionario serializado que simula un registro con talla=None y derivados=None.

    No se inserta en BD (standing_height_cm es NOT NULL); se usa para probar
    _anthropometry_unavailable_reason directamente.
    """
    return {
        "evaluation_date": "2026-04-05",
        "weight_kg": 40.0,
        "standing_height_cm": None,
        "sitting_height_cm": None,
        "bmi": None,
        "height_z_score": None,
        "height_percentile": None,
        "bmi_z_score": None,
        "bmi_percentile": None,
        "weight_z_score": None,
        "weight_percentile": None,
        "maturity_offset": -0.50,
        "age_at_phv": 13.73,
        "maturation_status": "Pre-PHV",
        "nutritional_status": None,
        "training_implications": None,
    }


# ---------------------------------------------------------------------------
# (a) Registro completo: el builder emite valores numéricos
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_record_emits_numeric_values(
    session_factory: async_sessionmaker[AsyncSession],
    athlete: Athlete,
) -> None:
    """Con peso + talla + LMS populados, BMI y percentiles son numéricos (no None)."""
    async with session_factory() as s:
        s.add(_make_complete_record(athlete.id))
        await s.commit()

    async with session_factory() as s:
        block = await _build_anthropometry_block(s, athlete.id, 2026, 5)

    assert block["has_records"] is True
    assert len(block["records"]) == 1

    rec = block["records"][0]
    assert rec["bmi"] is not None, "BMI debe ser numérico para un registro completo"
    assert rec["height_percentile"] is not None, "Percentil de talla debe estar presente"
    assert rec["bmi_percentile"] is not None, "Percentil de IMC debe estar presente"
    assert rec["weight_percentile"] is not None, "Percentil de peso debe estar presente"

    # unavailable_reasons debe estar vacío (todo disponible)
    assert rec.get("unavailable_reasons") == {}, (
        "No deben existir razones de no disponibilidad cuando todos los campos están presentes"
    )

    # Verificar que el latest incluye maturation_pedagogy (español neutro)
    latest = block["latest"]
    assert latest.get("maturation_pedagogy"), "maturation_pedagogy debe tener texto para Pre-PHV"
    assert "diagnós" not in latest["maturation_pedagogy"].lower(), (
        "maturation_pedagogy NO debe contener lenguaje diagnóstico"
    )


# ---------------------------------------------------------------------------
# (b) Registro sin talla: emite unavailable_reasons, no guiones vacíos
#
# standing_height_cm es NOT NULL en el esquema real, por lo que no podemos
# insertar NULL en SQLite. Probamos _build_anthropometry_block con una sesión
# mock que devuelve un objeto con standing_height_cm=None en memoria.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_height_emits_unavailable_reasons() -> None:
    """Con standing_height_cm=None en el objeto ORM, el builder emite unavailable_reasons."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    from app.models.anthropometry import MaturationStatus

    raw = _make_serialized_record_no_height()

    # Construir un namespace que imita AnthropometricRecord con talla None
    fake_record = SimpleNamespace(
        athlete_id=1,
        evaluation_date=date(2026, 4, 5),
        weight_kg=Decimal(str(raw["weight_kg"])),
        standing_height_cm=None,          # campo ausente
        sitting_height_cm=None,
        bmi=None,
        height_z_score=None,
        height_percentile=None,
        bmi_z_score=None,
        bmi_percentile=None,
        weight_z_score=None,
        weight_percentile=None,
        maturity_offset=Decimal("-0.50"),
        age_at_phv=Decimal("13.73"),
        maturation_status=MaturationStatus.pre_phv,
        nutritional_status=None,
        training_implications=None,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_result
    mock_result.all.return_value = [fake_record]

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    block = await _build_anthropometry_block(mock_db, athlete_id=1, year=2026, month=4)

    assert block["has_records"] is True
    rec = block["records"][0]

    ur = rec.get("unavailable_reasons", {})
    assert isinstance(ur, dict), "unavailable_reasons debe ser un dict"

    # Con standing_height_cm=None, al menos BMI y height_lms deben tener razón
    assert ur.get("bmi"), (
        "Debe haber unavailable_reason para 'bmi' cuando falta la talla"
    )
    assert ur.get("height_lms"), (
        "Debe haber unavailable_reason para 'height_lms' cuando falta la talla"
    )

    # Las razones son texto no vacío y en español (sanidad básica)
    for key, reason in ur.items():
        assert isinstance(reason, str) and len(reason) > 5, (
            f"unavailable_reason[{key!r}] debe ser una cadena descriptiva, got {reason!r}"
        )

    # Los valores numéricos afectados deben ser None (no cadenas ni guiones)
    assert rec["bmi"] is None
    assert rec["height_percentile"] is None
    assert rec["bmi_percentile"] is None


# ---------------------------------------------------------------------------
# (c) Separación estricta: antropometría SOLO en pdf_only_blocks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_anthropometry_only_in_pdf_only_blocks(
    session_factory: async_sessionmaker[AsyncSession],
    athlete: Athlete,
) -> None:
    """email_blocks NUNCA contiene claves antropométricas (FR-004 / SC-008)."""
    from app.services.training.newsletter_builder import build_newsletter_metrics
    from unittest.mock import MagicMock
    from types import SimpleNamespace

    # Insertar un registro completo para que anthropometry_block tenga has_records=True
    async with session_factory() as s:
        s.add(_make_complete_record(athlete.id))
        await s.commit()

    # Construimos un mock de DB que delega las consultas de antropometría
    # a la sesión SQLite real y devuelve listas vacías para el resto.
    real_session_factory = session_factory
    athlete_ns = SimpleNamespace(
        id=athlete.id,
        club_id=1,
        first_name="Deportista",
        last_name="Prueba",
        birth_date=date(2013, 6, 15),
        height_cm=152.0,
    )

    call_count = 0

    class _HybridSession:
        """Mock que sirve la consulta de AnthropometricRecord desde SQLite real
        y responde con listas vacías al resto de consultas."""

        def __init__(self) -> None:
            self._real: AsyncSession | None = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            if self._real is not None:
                await self._real.__aexit__(*_)

        async def execute(self, stmt):
            nonlocal call_count
            from sqlalchemy.sql.dml import Delete
            if isinstance(stmt, Delete):
                return MagicMock()

            call_count += 1
            stmt_str = str(stmt)

            # Consulta del Athlete (primera)
            if call_count == 1:
                result = MagicMock()
                result.scalars.return_value = result
                result.all.return_value = [athlete_ns]
                result.scalar_one_or_none.return_value = athlete_ns
                return result

            # Consultas de AnthropometricRecord: delegamos a SQLite real
            if "anthropometric_records" in stmt_str.lower():
                if self._real is None:
                    self._real = real_session_factory()
                    await self._real.__aenter__()
                return await self._real.execute(stmt)

            # Todo lo demás: listas vacías
            result = MagicMock()
            result.scalars.return_value = result
            result.all.return_value = []
            result.scalar_one_or_none.return_value = None
            return result

        async def flush(self):
            pass

        def add(self, obj):
            pass

    db = _HybridSession()
    snapshot = await build_newsletter_metrics(db, athlete.id, 2026, 5)

    email_blocks = snapshot["email_blocks"]
    pdf_only_blocks = snapshot["pdf_only_blocks"]

    # Regla FR-004 / SC-008: NUNCA en email_blocks
    forbidden_keys = {
        "anthropometry", "bmi", "height_percentile", "bmi_percentile",
        "weight_percentile", "height_z_score", "bmi_z_score", "weight_z_score",
        "maturity_offset", "age_at_phv", "maturation_status", "nutritional_status",
    }
    for key in forbidden_keys:
        assert key not in email_blocks, (
            f"Clave antropométrica '{key}' encontrada en email_blocks — "
            "viola FR-004 / SC-008 (datos sensibles de menores)"
        )

    # anthropometry SÍ debe estar en pdf_only_blocks
    assert "anthropometry" in pdf_only_blocks, (
        "pdf_only_blocks debe contener la clave 'anthropometry'"
    )
    assert pdf_only_blocks["anthropometry"]["has_records"] is True


# ---------------------------------------------------------------------------
# Tests unitarios de _anthropometry_unavailable_reason (función pura)
# ---------------------------------------------------------------------------

def test_no_reasons_when_all_present() -> None:
    """Sin campos ausentes, el dict debe estar vacío."""
    reasons = _anthropometry_unavailable_reason(
        weight_kg=42.0,
        standing_height_cm=152.0,
        bmi=18.2,
        height_z_score=0.3,
        height_percentile=62.0,
        bmi_z_score=-0.1,
        bmi_percentile=45.0,
        weight_z_score=0.1,
        weight_percentile=53.0,
    )
    assert reasons == {}, f"Se esperaba dict vacío, got {reasons}"


def test_reason_for_missing_height() -> None:
    """Sin talla: razón para bmi, height_lms y bmi_lms."""
    reasons = _anthropometry_unavailable_reason(
        weight_kg=40.0,
        standing_height_cm=None,
        bmi=None,
        height_z_score=None,
        height_percentile=None,
        bmi_z_score=None,
        bmi_percentile=None,
        weight_z_score=None,
        weight_percentile=None,
    )
    assert "bmi" in reasons
    assert "height_lms" in reasons
    # Sin IMC calculado, la razón de bmi_lms es "Se requiere IMC calculado"
    assert "bmi_lms" in reasons
    # Razones deben ser strings no vacíos
    for key, val in reasons.items():
        assert val, f"Razón para '{key}' no debe ser vacía"


def test_reason_for_out_of_range_lms() -> None:
    """Con talla y BMI presentes pero sin LMS (out-of-range): razón en lms keys."""
    reasons = _anthropometry_unavailable_reason(
        weight_kg=65.0,
        standing_height_cm=178.0,
        bmi=20.5,
        height_z_score=None,    # fuera de rango LMS
        height_percentile=None,
        bmi_z_score=None,
        bmi_percentile=None,
        weight_z_score=None,
        weight_percentile=None,
    )
    assert "height_lms" in reasons
    assert "bmi_lms" in reasons
    assert "weight_lms" in reasons
    # bmi NO debe estar en reasons (está calculado)
    assert "bmi" not in reasons
    # Las razones no deben contener lenguaje diagnóstico
    for val in reasons.values():
        assert "diagnós" not in val.lower()
        assert "problema" not in val.lower()
        assert "riesgo" not in val.lower()


def test_no_diagnostic_language_in_pedagogy_texts() -> None:
    """Las interpretaciones pedagógicas no usan lenguaje diagnóstico ni comparativo."""
    from app.services.training.newsletter_builder import _MATURATION_PEDAGOGY

    forbidden_terms = ["diagnós", "riesgo", "problema", "déficit", "deficiencia",
                       "inferior", "bajo la media", "por encima de la media"]
    for status, text in _MATURATION_PEDAGOGY.items():
        for term in forbidden_terms:
            assert term not in text.lower(), (
                f"Texto pedagógico para '{status}' contiene término inapropiado: '{term}'"
            )
