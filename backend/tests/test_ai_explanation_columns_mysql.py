"""T056 — cobertura MySQL real de las nueve columnas de trazabilidad de
``athlete_ai_explanations`` (feature 042).

Cubre ``specs/042-traceable-growth-ai/data-model.md`` §1 (la tabla de las
nueve columnas nuevas: ``schema_version``, ``structured_json``,
``critic_verdict``, ``prompt_version``, ``tokens_in``, ``tokens_out``,
``cost_usd``, ``latency_ms``, ``langfuse_trace_id``) y §6 (invariantes 1 y 3:
``text`` sigue ``NOT NULL`` siempre, y una fila legado con las nueve en
``NULL`` sigue siendo válida y legible sin backfill).

Por qué esto necesita MySQL real y no basta con la vía offline (aiosqlite):
las nueve columnas son aditivas y nulas, así que su *forma* ya está probada
por ``tests/test_ai_explanation_audit.py`` sobre sqlite con un shim de
upsert. Lo que este módulo prueba es específico del dialecto real:

- Precisión exacta de ``Numeric(10, 6)`` para ``cost_usd`` — sqlite no tiene
  un tipo ``NUMERIC`` con precisión fija; devuelve floats o el valor tal cual
  se insertó sin validar escala, así que un redondeo silencioso a 6 decimales
  sólo se detecta contra el motor real.
- El propio ``INSERT ... ON DUPLICATE KEY UPDATE`` del dialecto MySQL
  (``app/services/ai/anthro/persist.py:199-237``) — no el shim de
  ``sqlalchemy.dialects.sqlite.insert(...).on_conflict_do_update(...)`` que
  ``test_ai_explanation_audit.py`` usa para poder correr sin MySQL.
- La restricción ``NOT NULL`` real de ``text`` a nivel de motor (MySQL 8.4 en
  ``STRICT_TRANS_TABLES`` por defecto), no sólo la ausencia de validación en
  el lado de SQLAlchemy/Python.

Sin ``TEST_DATABASE_URL`` (mysql+aiomysql://…, nombre de base terminado en
``_test``) este módulo entero se salta solo, vía la fixture ``mysql_session``
de ``tests/conftest.py`` — igual que ``tests/test_retention.py`` T20/T21.
Correr con::

    TEST_DATABASE_URL="mysql+aiomysql://root:testroot@127.0.0.1:3306/trocha_ruta_test" \\
        pytest -m mysql -q tests/test_ai_explanation_columns_mysql.py

Privacidad (Ley 1581): club/entrenador/atleta/medición son enteramente
ficticios (mismo patrón de ``birth_date`` sintética que el resto de la
suite, p. ej. ``tests/test_ai_router.py``); ningún ``summary_line``/``changes``
de ``structured_json`` es contenido real generado por un modelo, y ningún
dato viaja a logs — este módulo sólo hace INSERT/SELECT directos.

Rango de ids dedicado (961_000+) para no colisionar con otra fila de
``clubs``/``users``/``athletes`` de otro módulo marcado ``mysql`` — la
sesión ``mysql_session`` es de alcance de sesión de pytest y NO se revierte
entre módulos dentro de una misma corrida ``-m mysql`` (sólo
``mysql_engine`` limpia todas las tablas, al final de toda la corrida).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_explanation import AthleteAIExplanation
from app.models.anthropometry import AnthropometricRecord, MaturationStatus
from app.models.club import ClubRole
from app.models.user import UserRole
from app.services.ai.anthro.schemas import (
    AnthropometryInsightV1,
    Confidence,
    ConfidenceLevel,
)
from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_user,
    link_user_to_club,
)

pytestmark = pytest.mark.mysql

_CLUB_ID = 961_000
_COACH_ID = 961_001
_ATHLETE_USER_ID = 961_002
_ATHLETE_ID = 961_000

_USE_CASE = "phv_explainer"

# Sintéticos, nunca una fecha de nacimiento real (Ley 1581) — mismo patrón
# que el resto de la suite (tests/test_ai_router.py y afines).
_BIRTH_DATE = date(2014, 6, 15)


def _insight_payload(summary_line: str) -> dict:
    """Un ``structured_json`` real: ``AnthropometryInsightV1`` serializado tal
    como lo produce ``app/services/ai/anthro/persist.py:197``
    (``insight.model_dump(mode="json")``), no un dict inventado ad-hoc."""
    insight = AnthropometryInsightV1(
        audience="family",
        summary_line=summary_line,
        changes=["Cambio ficticio uno."],
        meaning=["Significado ficticio uno."],
        next_weeks=["Siguiente paso ficticio."],
        confidence=Confidence(
            level=ConfidenceLevel.MEDIUM, reason="Motivo ficticio de confianza media."
        ),
        word_count=12,
    )
    return insight.model_dump(mode="json")


def _record(record_id: int, *, evaluated_by: int = _COACH_ID) -> AnthropometricRecord:
    """Medición mínima y ficticia — un id nuevo por test para que cada fila
    de ``athlete_ai_explanations`` tenga su propia clave única
    ``(athlete_id, anthropometric_record_id, use_case)`` y los tests no se
    pisen entre sí dentro de la sesión compartida."""
    return AnthropometricRecord(
        id=record_id,
        athlete_id=_ATHLETE_ID,
        evaluation_date=date(2026, 3, 1),
        weight_kg=Decimal("40.00"),
        standing_height_cm=Decimal("150.0"),
        sitting_height_cm=Decimal("78.0"),
        leg_length_cm=Decimal("72.0"),
        leg_sitting_ratio=Decimal("0.9231"),
        maturity_offset=Decimal("0.50"),
        age_at_phv=Decimal("12.20"),
        maturation_status=MaturationStatus.circa_phv,
        evaluated_by=evaluated_by,
    )


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def scenario(mysql_session: AsyncSession) -> dict[str, int]:
    """Un club + un entrenador + un atleta, sembrados una sola vez.

    ``scope="module"`` porque ``mysql_session`` (tests/conftest.py) es de
    alcance de sesión de pytest: crear el mismo club/atleta más de una vez
    en este módulo chocaría contra la PK. Cada test siembra su propia
    ``AnthropometricRecord`` en vez de compartirla, así que la independencia
    entre tests no depende de revertir esta siembra.
    """
    await create_club(
        mysql_session, club_id=_CLUB_ID, name="Club Prueba 042 MySQL", code="c042-mysql-cols"
    )
    await create_user(
        mysql_session,
        user_id=_COACH_ID,
        role=UserRole.coach,
        first_name="Entrenador",
        last_name="Prueba042",
    )
    await link_user_to_club(
        mysql_session, user_id=_COACH_ID, club_id=_CLUB_ID, role_in_club=ClubRole.coach
    )
    # El atleta necesita su propio usuario (FK real en MySQL, a diferencia de
    # sqlite sin PRAGMA foreign_keys — Athlete.user_id es NOT NULL + FK).
    await create_user(
        mysql_session,
        user_id=_ATHLETE_USER_ID,
        role=UserRole.athlete,
        first_name="Atleta",
        last_name="Prueba042",
    )
    await create_athlete(
        mysql_session,
        athlete_id=_ATHLETE_ID,
        first_name="Atleta",
        last_name="Prueba042",
        birth_date=_BIRTH_DATE,
        club_id=_CLUB_ID,
        user_id=_ATHLETE_USER_ID,
        created_by=_COACH_ID,
    )
    await mysql_session.commit()
    return {"club_id": _CLUB_ID, "athlete_id": _ATHLETE_ID, "coach_id": _COACH_ID}


async def _fetch(db: AsyncSession, *, record_id: int) -> AthleteAIExplanation:
    """SELECT fresco (no el objeto Python que se acaba de insertar) — lo que
    de verdad viajó a MySQL y volvió, columna por columna."""
    result = await db.execute(
        select(AthleteAIExplanation)
        .where(
            AthleteAIExplanation.athlete_id == _ATHLETE_ID,
            AthleteAIExplanation.anthropometric_record_id == record_id,
            AthleteAIExplanation.use_case == _USE_CASE,
        )
        # Fuerza a releer del motor en vez de devolver el objeto cacheado en
        # la identity map: un `db.expire(row)` posterior dispararía un
        # refresh perezoso síncrono en el primer `row.<attr>` del test, lo
        # que revienta con MissingGreenlet bajo AsyncSession.
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


# ---------------------------------------------------------------------------
# Round-trip de las nueve columnas
# ---------------------------------------------------------------------------


async def test_nueve_columnas_de_trazabilidad_ida_y_vuelta(
    mysql_session: AsyncSession, scenario: dict[str, int]
) -> None:
    record_id = 961_101
    mysql_session.add(_record(record_id))
    await mysql_session.flush()

    structured_json = _insight_payload("Resumen ficticio de ida y vuelta.")
    mysql_session.add(
        AthleteAIExplanation(
            athlete_id=_ATHLETE_ID,
            anthropometric_record_id=record_id,
            use_case=_USE_CASE,
            text="Texto ficticio de prosa renderizada.",
            model="gemini-3.8-flash",
            provider="google",
            generated_at=datetime(2026, 3, 2, 10, 0, 0),
            age_group="10-15",
            maturation_status="Circa-PHV",
            generated_by_user_id=_COACH_ID,
            schema_version="v2",
            structured_json=structured_json,
            critic_verdict="approved",
            prompt_version="anthropometry_analyst_v1",
            tokens_in=512,
            tokens_out=128,
            cost_usd=Decimal("0.014235"),
            latency_ms=2731,
            langfuse_trace_id="lf-roundtrip-0001",
        )
    )
    await mysql_session.commit()

    row = await _fetch(mysql_session, record_id=record_id)

    assert row.schema_version == "v2"
    assert row.structured_json == structured_json
    assert row.critic_verdict == "approved"
    assert row.prompt_version == "anthropometry_analyst_v1"
    assert row.tokens_in == 512
    assert row.tokens_out == 128
    # Numeric(10, 6): el valor exacto debe volver como Decimal, nunca como un
    # float que aproxima 0.014235 (p. ej. 0.014234999999999999).
    assert isinstance(row.cost_usd, Decimal)
    assert row.cost_usd == Decimal("0.014235")
    assert row.latency_ms == 2731
    assert row.langfuse_trace_id == "lf-roundtrip-0001"
    # Invariante 1 (data-model.md §6): text nunca deja de ser NOT NULL, ni
    # siquiera en una fila "v2".
    assert row.text == "Texto ficticio de prosa renderizada."


# ---------------------------------------------------------------------------
# El upsert real del dialecto MySQL sobrescribe las nueve en una regeneración
# ---------------------------------------------------------------------------


async def test_upsert_on_duplicate_key_sobrescribe_las_nueve_columnas(
    mysql_session: AsyncSession, scenario: dict[str, int]
) -> None:
    record_id = 961_102
    mysql_session.add(_record(record_id))
    await mysql_session.flush()

    def _upsert(**cols):
        stmt = mysql_insert(AthleteAIExplanation).values(
            athlete_id=_ATHLETE_ID,
            anthropometric_record_id=record_id,
            use_case=_USE_CASE,
            age_group="10-15",
            maturation_status="Circa-PHV",
            generated_by_user_id=_COACH_ID,
            **cols,
        )
        # Mismas 16 columnas que app/services/ai/anthro/persist.py:220-237
        # (7 heredadas + las 9 de esta feature), para ejercitar exactamente
        # el statement de producción, no una versión recortada.
        return stmt.on_duplicate_key_update(
            text=stmt.inserted.text,
            model=stmt.inserted.model,
            provider=stmt.inserted.provider,
            generated_at=stmt.inserted.generated_at,
            age_group=stmt.inserted.age_group,
            maturation_status=stmt.inserted.maturation_status,
            generated_by_user_id=stmt.inserted.generated_by_user_id,
            schema_version=stmt.inserted.schema_version,
            structured_json=stmt.inserted.structured_json,
            critic_verdict=stmt.inserted.critic_verdict,
            prompt_version=stmt.inserted.prompt_version,
            tokens_in=stmt.inserted.tokens_in,
            tokens_out=stmt.inserted.tokens_out,
            cost_usd=stmt.inserted.cost_usd,
            latency_ms=stmt.inserted.latency_ms,
            langfuse_trace_id=stmt.inserted.langfuse_trace_id,
        )

    primera_generacion = _insight_payload("Resumen ficticio, primera generación.")
    await mysql_session.execute(
        _upsert(
            text="Texto ficticio, primera generación.",
            model="gemini-3.8-flash",
            provider="google",
            generated_at=datetime(2026, 3, 2, 10, 0, 0),
            schema_version="v2",
            structured_json=primera_generacion,
            critic_verdict="approved",
            prompt_version="anthropometry_analyst_v1",
            tokens_in=500,
            tokens_out=120,
            cost_usd=Decimal("0.012345"),
            latency_ms=2500,
            langfuse_trace_id="lf-upsert-gen1",
        )
    )
    await mysql_session.commit()

    fila_inicial = await _fetch(mysql_session, record_id=record_id)
    assert fila_inicial.critic_verdict == "approved"
    assert fila_inicial.cost_usd == Decimal("0.012345")

    # Regeneración: el coach vuelve a pedir el análisis sobre la MISMA
    # medición — misma clave única (athlete_id, record_id, use_case), otro
    # contenido en las 16 columnas reescribibles.
    segunda_generacion = _insight_payload("Resumen ficticio, segunda generación (revisado).")
    await mysql_session.execute(
        _upsert(
            text="Texto ficticio, segunda generación (revisado).",
            model="gemini-3.1-flash-lite",
            provider="google",
            generated_at=datetime(2026, 4, 5, 9, 30, 0),
            schema_version="v2",
            structured_json=segunda_generacion,
            critic_verdict="revised",
            prompt_version="anthropometry_analyst_v2",
            tokens_in=800,
            tokens_out=210,
            cost_usd=Decimal("0.067891"),
            latency_ms=4187,
            langfuse_trace_id="lf-upsert-gen2",
        )
    )
    await mysql_session.commit()

    fila_final = await _fetch(mysql_session, record_id=record_id)

    # Sigue siendo LA MISMA fila (mismo id) — un upsert, no una fila nueva.
    assert fila_final.id == fila_inicial.id
    assert fila_final.text == "Texto ficticio, segunda generación (revisado)."
    assert fila_final.schema_version == "v2"
    assert fila_final.structured_json == segunda_generacion
    assert fila_final.structured_json != primera_generacion
    assert fila_final.critic_verdict == "revised"
    assert fila_final.prompt_version == "anthropometry_analyst_v2"
    assert fila_final.tokens_in == 800
    assert fila_final.tokens_out == 210
    assert isinstance(fila_final.cost_usd, Decimal)
    assert fila_final.cost_usd == Decimal("0.067891")
    assert fila_final.latency_ms == 4187
    assert fila_final.langfuse_trace_id == "lf-upsert-gen2"


# ---------------------------------------------------------------------------
# Fila legado (schema_version/structured_json NULL) — sin backfill
# ---------------------------------------------------------------------------


async def test_fila_legado_con_las_nueve_en_null_sigue_siendo_valida(
    mysql_session: AsyncSession, scenario: dict[str, int]
) -> None:
    """data-model.md §6, invariante 3: una fila pre-042 (``schema_version
    IS NULL``) nunca recibe backfill de las nueve columnas y debe seguir
    siendo perfectamente legible — sólo su forma de prosa libre (033)."""
    record_id = 961_103
    mysql_session.add(_record(record_id))
    await mysql_session.flush()

    mysql_session.add(
        AthleteAIExplanation(
            athlete_id=_ATHLETE_ID,
            anthropometric_record_id=record_id,
            use_case=_USE_CASE,
            text="Texto ficticio de una fila legado (prosa libre, feature 033).",
            model="gemini-2.5-flash",
            provider="google",
            generated_at=datetime(2025, 11, 1, 8, 0, 0),
            age_group="10-15",
            maturation_status="Circa-PHV",
            generated_by_user_id=_COACH_ID,
            # Las nueve nuevas: explícitamente ausentes, como cualquier fila
            # escrita antes de esta feature — ningún script las backfillea.
            schema_version=None,
            structured_json=None,
            critic_verdict=None,
            prompt_version=None,
            tokens_in=None,
            tokens_out=None,
            cost_usd=None,
            latency_ms=None,
            langfuse_trace_id=None,
        )
    )
    await mysql_session.commit()

    row = await _fetch(mysql_session, record_id=record_id)

    assert row.schema_version is None
    assert row.structured_json is None
    assert row.critic_verdict is None
    assert row.prompt_version is None
    assert row.tokens_in is None
    assert row.tokens_out is None
    assert row.cost_usd is None
    assert row.latency_ms is None
    assert row.langfuse_trace_id is None
    # `text` sigue NOT NULL y perfectamente legible, sin backfill de nada más.
    assert row.text == "Texto ficticio de una fila legado (prosa libre, feature 033)."
    assert row.model == "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# `text` sigue NOT NULL a nivel de motor real (no sólo por convención Python)
# ---------------------------------------------------------------------------


async def test_text_sigue_siendo_not_null_en_mysql_real(
    mysql_session: AsyncSession, scenario: dict[str, int]
) -> None:
    """data-model.md §6, invariante 1 — el motor, no sólo el ORM, rechaza un
    ``text`` nulo. ``Mapped[str]`` no impide asignar ``None`` en Python; la
    garantía real vive en la columna ``NOT NULL`` de MySQL."""
    record_id = 961_104
    mysql_session.add(_record(record_id))
    await mysql_session.flush()

    mysql_session.add(
        AthleteAIExplanation(
            athlete_id=_ATHLETE_ID,
            anthropometric_record_id=record_id,
            use_case=_USE_CASE,
            text=None,  # type: ignore[arg-type]  # deliberado: probar la restricción real
            model="gemini-3.8-flash",
            provider="google",
            generated_at=datetime(2026, 3, 2, 10, 0, 0),
            age_group="10-15",
            maturation_status="Circa-PHV",
            generated_by_user_id=_COACH_ID,
        )
    )
    with pytest.raises(DBAPIError):
        await mysql_session.commit()

    # La sesión queda en estado "pending rollback" tras el error del motor;
    # se revierte explícitamente porque `mysql_session` es de alcance de
    # sesión y la comparte todo el resto de la corrida `-m mysql`.
    await mysql_session.rollback()
