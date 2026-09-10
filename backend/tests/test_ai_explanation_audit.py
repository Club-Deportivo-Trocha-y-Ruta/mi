"""T030 — auditoría de las dos rutas POST de `/api/ai/*` que generan una
explicación de IA sobre un menor.

Contrato: ``specs/041-multi-coach-governance/contracts/audit-recording.md``
§4.3 (las dos filas `athlete_ai_explanation` de la matriz), §1.4 (R1/R4),
§1.6 (``club_id`` = club del atleta; ``athlete_id`` = el atleta de la ruta) y
§1.7 (``META_ALLOWLIST``).

Rutas cubiertas:

  POST /api/ai/athletes/{id}/phv-explanation                    → create | update
  POST /api/ai/athletes/{id}/measurements/{record_id}/explanation → create | update

**Por qué no hay cliente HTTP acá.** Ambos handlers persisten con
``mysql_insert(...).on_duplicate_key_update(...)``, un statement del dialecto
MySQL que no compila sobre aiosqlite; la vía offline no puede ejercer el
upsert. Lo que sí se puede ejercer —y es donde vive toda la decisión de
auditoría— son los dos helpers del router: el pre-SELECT que distingue
``create`` de ``update`` y el que encola la fila. Se prueban directamente
contra un motor sqlite propio, y una prueba de cableado verifica que los dos
handlers los sigan llamando.

Privacidad (Ley 1581, menores): estas son justo las rutas donde es fácil
filtrar un dato del menor. Las pruebas afirman explícitamente que ni el texto
narrativo, ni el ``age_group``, ni el ``maturation_status``, ni el nombre del
atleta aparecen en ``diff_json`` ni en ``meta_json``; solo viajan NOMBRES de
columna e identificadores. Todos los datos del escenario son ficticios.
"""
from __future__ import annotations

import inspect
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.ai_explanation import AthleteAIExplanation
from app.models.anthropometry import AnthropometricRecord, MaturationStatus
from app.models.audit_log import AuditAction, AuditActorKind, AuditLog
from app.models.club import ClubRole
from app.models.user import UserRole
from app.routers import ai as ai_router
from app.routers.ai import (
    _cached_explanation_id,
    _record_explanation_audit,
    measurement_explanation,
    phv_explanation,
)
from app.services.audit import AuditEntityType
from app.services.request_context import request_id_scope

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_user,
    link_user_to_club,
)
from tests.helpers.audit_tables import AUDIT_TABLES

CLUB_ID = 1
COACH_ID = 10
ATHLETE_ID = 941
ATHLETE_USER_ID = 1941
RECORD_ID = 77

# Texto narrativo ficticio: nunca debe aparecer en una fila de auditoría.
NARRATIVA_FICTICIA = "Texto ficticio de la explicación generada para la familia."

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "anthropometric_records",
    "athlete_ai_explanations",
    *AUDIT_TABLES,
)


# ---------------------------------------------------------------------------
# Motor sqlite propio con el subconjunto de tablas
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def ai_audit_engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[name] for name in _TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def ai_audit_session(
    ai_audit_engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(ai_audit_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def escenario(ai_audit_session: AsyncSession) -> dict:
    """Club ficticio + entrenador + atleta ficticio + una medición."""
    await create_club(ai_audit_session, club_id=CLUB_ID, name="Club Ficticio", code="cft-ai")
    coach = await create_user(
        ai_audit_session,
        user_id=COACH_ID,
        role=UserRole.coach,
        first_name="Entrenador",
        last_name="Ficticio",
    )
    await link_user_to_club(
        ai_audit_session, user_id=COACH_ID, club_id=CLUB_ID, role_in_club=ClubRole.coach
    )
    athlete = await create_athlete(
        ai_audit_session,
        athlete_id=ATHLETE_ID,
        first_name="Mariana Ficticia",
        last_name="Restrepo",
        birth_date=date(2013, 6, 20),
        club_id=CLUB_ID,
        user_id=ATHLETE_USER_ID,
        created_by=COACH_ID,
    )
    record = AnthropometricRecord(
        id=RECORD_ID,
        athlete_id=ATHLETE_ID,
        evaluation_date=date(2026, 3, 1),
        weight_kg=Decimal("40.00"),
        standing_height_cm=Decimal("150.0"),
        sitting_height_cm=Decimal("78.0"),
        leg_length_cm=Decimal("72.0"),
        leg_sitting_ratio=Decimal("0.9231"),
        maturity_offset=Decimal("0.50"),
        age_at_phv=Decimal("12.20"),
        maturation_status=MaturationStatus.circa_phv,
        evaluated_by=COACH_ID,
    )
    ai_audit_session.add(record)
    await ai_audit_session.commit()
    return {"coach": coach, "athlete": athlete, "record_id": RECORD_ID}


async def _seed_cached_explanation(
    session: AsyncSession, *, use_case: str
) -> AthleteAIExplanation:
    """Fila de caché previa — simula una explicación ya generada."""
    now = datetime.now(timezone.utc)
    row = AthleteAIExplanation(
        athlete_id=ATHLETE_ID,
        anthropometric_record_id=RECORD_ID,
        use_case=use_case,
        text=NARRATIVA_FICTICIA,
        model="modelo-ficticio",
        provider="fake",
        generated_at=now,
        age_group="13-15",
        maturation_status="Circa-PHV",
        generated_by_user_id=COACH_ID,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.commit()
    return row


async def _audit_rows(session: AsyncSession) -> list[AuditLog]:
    result = await session.execute(select(AuditLog).order_by(AuditLog.id))
    return list(result.scalars().all())


# ===========================================================================
# Pre-SELECT: create vs update
# ===========================================================================


@pytest.mark.asyncio
async def test_pre_select_devuelve_none_sin_cache(ai_audit_session, escenario):
    found = await _cached_explanation_id(
        ai_audit_session,
        athlete_id=ATHLETE_ID,
        anthropometric_record_id=RECORD_ID,
        use_case="phv_explainer",
    )
    assert found is None


@pytest.mark.asyncio
async def test_pre_select_discrimina_por_use_case(ai_audit_session, escenario):
    """La clave de caché es `(athlete_id, record_id, use_case)`: la variante
    del entrenador y la familiar son filas distintas."""
    familiar = await _seed_cached_explanation(ai_audit_session, use_case="phv_explainer")

    assert (
        await _cached_explanation_id(
            ai_audit_session,
            athlete_id=ATHLETE_ID,
            anthropometric_record_id=RECORD_ID,
            use_case="phv_explainer",
        )
        == familiar.id
    )
    assert (
        await _cached_explanation_id(
            ai_audit_session,
            athlete_id=ATHLETE_ID,
            anthropometric_record_id=RECORD_ID,
            use_case="phv_explanation_coach",
        )
        is None
    )


# ===========================================================================
# Fila de auditoría — create
# ===========================================================================


@pytest.mark.asyncio
async def test_primera_generacion_registra_create(ai_audit_session, escenario):
    fila = await _seed_cached_explanation(ai_audit_session, use_case="phv_explainer")

    with request_id_scope():
        await _record_explanation_audit(
            ai_audit_session,
            athlete=escenario["athlete"],
            anthropometric_record_id=RECORD_ID,
            use_case="phv_explainer",
            actor=escenario["coach"],
            previous_id=None,
        )
    await ai_audit_session.commit()

    rows = await _audit_rows(ai_audit_session)
    assert len(rows) == 1
    row = rows[0]
    assert row.entity_type == AuditEntityType.athlete_ai_explanation.value
    assert row.action == AuditAction.create
    assert row.entity_id == fila.id
    assert row.club_id == CLUB_ID
    assert row.athlete_id == ATHLETE_ID
    assert row.actor_user_id == COACH_ID
    assert row.actor_kind == AuditActorKind.user
    assert row.actor_role == UserRole.coach
    assert row.meta_json == {"related_entity_id": RECORD_ID}
    # `athlete_ai_explanation` no está en VALUE_ALLOWLIST: nunca hay valores.
    assert row.diff_json is None
    assert row.changed_fields == []
    assert row.request_id


# ===========================================================================
# Fila de auditoría — update (regeneración)
# ===========================================================================


@pytest.mark.asyncio
async def test_regeneracion_registra_update_con_nombres_de_columna(
    ai_audit_session, escenario
):
    fila = await _seed_cached_explanation(ai_audit_session, use_case="phv_explainer")

    with request_id_scope():
        await _record_explanation_audit(
            ai_audit_session,
            athlete=escenario["athlete"],
            anthropometric_record_id=RECORD_ID,
            use_case="phv_explainer",
            actor=escenario["coach"],
            previous_id=fila.id,
        )
    await ai_audit_session.commit()

    rows = await _audit_rows(ai_audit_session)
    assert len(rows) == 1
    row = rows[0]
    assert row.action == AuditAction.update
    assert row.entity_id == fila.id
    # Nombres de columna, nunca valores (mismo criterio que
    # `coach_answer_text` en §4.9).
    assert row.changed_fields == [
        "age_group",
        "generated_at",
        "generated_by_user_id",
        "maturation_status",
        "model",
        "provider",
        "text",
    ]
    assert row.diff_json is None


@pytest.mark.asyncio
async def test_regeneracion_identica_igual_escribe_fila(ai_audit_session, escenario):
    """Una regeneración que devolviera texto idéntico NO puede perderse por la
    regla R7: el entrenador la pidió y el historial debe mostrarlo."""
    fila = await _seed_cached_explanation(ai_audit_session, use_case="phv_explainer")

    with request_id_scope():
        for _ in range(2):
            await _record_explanation_audit(
                ai_audit_session,
                athlete=escenario["athlete"],
                anthropometric_record_id=RECORD_ID,
                use_case="phv_explainer",
                actor=escenario["coach"],
                previous_id=fila.id,
            )
    await ai_audit_session.commit()

    rows = await _audit_rows(ai_audit_session)
    assert [r.action for r in rows] == [AuditAction.update, AuditAction.update]


# ===========================================================================
# Privacidad (Ley 1581)
# ===========================================================================


@pytest.mark.asyncio
async def test_la_fila_no_lleva_dato_alguno_del_menor(ai_audit_session, escenario):
    fila = await _seed_cached_explanation(ai_audit_session, use_case="phv_explainer")

    with request_id_scope():
        await _record_explanation_audit(
            ai_audit_session,
            athlete=escenario["athlete"],
            anthropometric_record_id=RECORD_ID,
            use_case="phv_explainer",
            actor=escenario["coach"],
            previous_id=fila.id,
        )
    await ai_audit_session.commit()

    row = (await _audit_rows(ai_audit_session))[0]
    serializada = json.dumps(
        {
            "changed_fields": row.changed_fields,
            "diff_json": row.diff_json,
            "meta_json": row.meta_json,
            "reason_code": row.reason_code,
        },
        ensure_ascii=False,
    )
    prohibidos = (
        NARRATIVA_FICTICIA,
        "Mariana",
        "Restrepo",
        "2013-06-20",
        "Circa-PHV",
        "13-15",
        "150",
        "40",
    )
    for prohibido in prohibidos:
        assert prohibido not in serializada, prohibido
    # `meta_json` solo puede llevar la clave de identificador de la medición.
    assert set(row.meta_json or {}) == {"related_entity_id"}


# ===========================================================================
# Cableado — los dos handlers siguen llamando al registrador
# ===========================================================================


@pytest.mark.parametrize("handler", [phv_explanation, measurement_explanation])
def test_los_handlers_llaman_al_registrador_de_auditoria(handler):
    """Guardia contra que la instrumentación se caiga en una refactorización.

    No se puede ejercer por HTTP en la vía offline (el upsert es del dialecto
    MySQL), así que se verifica sobre el código fuente del handler.
    """
    fuente = inspect.getsource(handler)
    assert "_cached_explanation_id(" in fuente
    assert "_record_explanation_audit(" in fuente


def test_las_columnas_reescritas_no_incluyen_ninguna_medida():
    """Ningún nombre de columna antropométrica puede colarse en la lista."""
    prohibidas = {"standing_height_cm", "sitting_height_cm", "weight_kg", "birth_date"}
    assert prohibidas.isdisjoint(set(ai_router._EXPLANATION_REWRITTEN_FIELDS))
