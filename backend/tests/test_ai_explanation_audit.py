"""T030 — auditoría de las dos rutas POST de `/api/ai/*` que generan una
explicación de IA sobre un menor.

Contrato: ``specs/041-multi-coach-governance/contracts/audit-recording.md``
§4.3 (las dos filas `athlete_ai_explanation` de la matriz), §1.4 (R1/R4),
§1.6 (``club_id`` = club del atleta; ``athlete_id`` = el atleta de la ruta) y
§1.7 (``META_ALLOWLIST``).

Rutas cubiertas:

  POST /api/ai/athletes/{id}/phv-explanation                    → create | update
  POST /api/ai/athletes/{id}/measurements/{record_id}/explanation → create | update

Reubicación (feature 042, T038/T039/T043) — LEER ANTES DE TOCAR ESTE ARCHIVO
=============================================================================
Antes de esta feature, `app/routers/ai.py` tenía dos helpers privados
(`_cached_explanation_id`, el pre-SELECT que distingue `create` de `update`,
y `_record_explanation_audit`, que encolaba la fila de auditoría) y los dos
handlers POST los llamaban directamente. Esa responsabilidad se MOVIÓ, no se
eliminó: ahora `app/services/ai/anthro/persist.py` (T038) es el ÚNICO
escritor de `athlete_ai_explanations` para el pipeline nuevo — hace su
propio pre-SELECT (duplicado deliberado, mismo nombre
`_cached_explanation_id`, documentado en su propio docstring como "no
importa un símbolo privado de la capa de routers") y llama a
`app.services.audit.record_audit(...)` DIRECTAMENTE, en línea, sin pasar por
ningún wrapper equivalente a `_record_explanation_audit` (ese símbolo ya NO
existe en ningún módulo). Los dos handlers POST (`phv_explanation`,
`measurement_explanation`) ya no llaman a ninguno de los dos helpers: ahora
delegan TODO a `anthro.pipeline.run_analysis()`, que orquesta
contexto→analista→crítico→guardrails→`persist.persist()` y devuelve
`persisted_explanation_id`/`persisted_action` ya resueltos.

Esta prueba se reescribió para seguir esa responsabilidad hasta donde vive
hoy: ejercita `app.services.ai.anthro.persist.persist()` completo (upsert +
fila de auditoría) en vez de un helper de auditoría aislado que ya no
existe.

**Por qué sigue sin haber cliente HTTP acá.** `persist.persist()` escribe con
`mysql_insert(...).on_duplicate_key_update(...)`, un statement del dialecto
MySQL que sigue sin compilar sobre aiosqlite (verificado:
`sqlalchemy.exc.UnsupportedCompilationError` al intentar renderizar
`OnDuplicateClause` contra el compilador sqlite) — la vía offline todavía no
puede ejercer el upsert MySQL literal. Esta prueba resuelve esa brecha
sustituyendo ÚNICAMENTE la fábrica `persist.mysql_insert` (monkeypatch de un
símbolo de módulo, nunca de producción) por un doble que traduce la MISMA
secuencia de llamadas (`.values()` → `.inserted.<col>` → `.on_duplicate_key_
update()`) a `sqlalchemy.dialects.sqlite.insert(...).on_conflict_do_update(
...)` — un upsert real y compileable sobre sqlite, sobre la clave única
real de la tabla (`athlete_id`, `anthropometric_record_id`, `use_case`). El
resto de `persist.py` (el pre-SELECT, la llamada a `record_audit`) corre sin
ningún mock adicional.

Cableado de fuente (más abajo, `test_persist_pre_selecciona_antes_de_
ejecutar_el_upsert` / `test_los_handlers_generan_via_run_analysis`): la vieja
aserción `"_cached_explanation_id(" in inspect.getsource(handler)` probaba
un detalle de implementación de una función que se movió — se retargeteó al
invariante real y estable ("el pre-SELECT ocurre antes del upsert, dentro de
`persist.py`") en vez de eliminarse sin más, porque es justo el tipo de
regresión de orquestación (perder el orden pre-SELECT → upsert) que un test
de fuente barato sigue pudiendo atrapar sin necesitar MySQL.

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
from types import SimpleNamespace
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
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
from app.routers.ai import measurement_explanation, phv_explanation
from app.services.ai.anthro import persist as persist_module
from app.services.ai.anthro.persist import _cached_explanation_id
from app.services.ai.anthro.schemas import AnthropometryInsightV1, Confidence, ConfidenceLevel
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
# Doble de la fábrica mysql_insert — ver el docstring del módulo ("por qué
# sigue sin haber cliente HTTP acá") para el porqué completo.
# ---------------------------------------------------------------------------


class _SqliteUpsertShim:
    """Traduce `sqlalchemy.dialects.mysql.insert(...)` (lo que `persist.py`
    importa como `mysql_insert`) a `sqlalchemy.dialects.sqlite.insert(...)`
    para poder ejercer `persist()` COMPLETO —upsert real incluido— contra un
    motor sqlite en memoria. Reproduce exactamente la superficie que
    `persist.py` usa de una sentencia mysql (`.values()`, `.inserted.<col>`,
    `.on_duplicate_key_update()`), nada más; el resto de `persist.py` corre
    sin cambios."""

    def __init__(self, table):
        self._stmt = sqlite_insert(table)

    def values(self, **kwargs):
        self._stmt = self._stmt.values(**kwargs)
        return self

    @property
    def inserted(self):
        # Equivalente sqlite de la pseudo-tabla `mysql.dml.Insert.inserted`
        # que `persist.py` referencia dentro de `on_duplicate_key_update(...)`.
        return self._stmt.excluded

    def on_duplicate_key_update(self, **kwargs):
        return self._stmt.on_conflict_do_update(
            index_elements=["athlete_id", "anthropometric_record_id", "use_case"],
            set_=kwargs,
        )


@pytest.fixture(autouse=True)
def _sqlite_upsert_shim(monkeypatch):
    """Autouse: ningún test de este módulo necesita MySQL real para ejercer
    `persist.persist()` — ver el docstring de `_SqliteUpsertShim`."""
    monkeypatch.setattr(persist_module, "mysql_insert", _SqliteUpsertShim)


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


def _build_insight(
    *, audience: str = "family", summary_line: str = "Resumen ficticio de crecimiento estable."
) -> AnthropometryInsightV1:
    """`AnthropometryInsightV1` mínimo y válido — contenido enteramente ficticio."""
    return AnthropometryInsightV1(
        audience=audience,
        summary_line=summary_line,
        changes=["Cambio ficticio uno."],
        meaning=["Significado ficticio uno."],
        next_weeks=["Siguiente paso ficticio."],
        confidence=Confidence(
            level=ConfidenceLevel.MEDIUM, reason="Motivo ficticio de confianza media."
        ),
        word_count=12,
    )


def _persist_state(
    *,
    db: AsyncSession,
    athlete,
    actor,
    record_id: int = RECORD_ID,
    use_case: str = "phv_explainer",
    insight: AnthropometryInsightV1 | None = None,
    rendered_text: str = "Texto ficticio ya renderizado y saneado por guardrails.",
) -> dict:
    """``state`` mínimo que `persist.persist()` necesita — ver el docstring
    de `persist.py` para el contrato completo. `target_record` es un doble
    de solo-``id`` porque `persist.py` únicamente lee `target_record.id`."""
    return {
        "db": db,
        "athlete": athlete,
        "target_record": SimpleNamespace(id=record_id),
        "use_case": use_case,
        "actor": actor,
        "insight": insight or _build_insight(),
        "critic_verdict": "approved",
        "guardrail_rendered_text": rendered_text,
        "prompt_version": "anthropometry_analyst_v1",
        "model": "modelo-ficticio",
        "provider": "fake",
        "age_group": "13-15",
        "maturation_status": "Circa-PHV",
        "generated_at": datetime.now(timezone.utc),
        "tokens_in": 10,
        "tokens_out": 20,
        "cost_usd": 0.001234,
        "latency_ms": 500,
        "langfuse_trace_id": None,
    }


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
# Pre-SELECT: create vs update (ahora en persist.py)
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
# persist() completo — fila de auditoría, create
# ===========================================================================


@pytest.mark.asyncio
async def test_primera_generacion_registra_create(ai_audit_session, escenario):
    state = _persist_state(
        db=ai_audit_session, athlete=escenario["athlete"], actor=escenario["coach"]
    )

    with request_id_scope():
        result = await persist_module.persist(state)
    await ai_audit_session.commit()

    assert result["persisted_action"] == "create"
    fila_id = result["persisted_explanation_id"]

    rows = await _audit_rows(ai_audit_session)
    assert len(rows) == 1
    row = rows[0]
    assert row.entity_type == AuditEntityType.athlete_ai_explanation.value
    assert row.action == AuditAction.create
    assert row.entity_id == fila_id
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
# persist() completo — fila de auditoría, update (regeneración)
# ===========================================================================


@pytest.mark.asyncio
async def test_regeneracion_registra_update_con_nombres_de_columna(
    ai_audit_session, escenario
):
    fila = await _seed_cached_explanation(ai_audit_session, use_case="phv_explainer")
    state = _persist_state(
        db=ai_audit_session, athlete=escenario["athlete"], actor=escenario["coach"]
    )

    with request_id_scope():
        result = await persist_module.persist(state)
    await ai_audit_session.commit()

    assert result["persisted_action"] == "update"
    assert result["persisted_explanation_id"] == fila.id

    rows = await _audit_rows(ai_audit_session)
    assert len(rows) == 1
    row = rows[0]
    assert row.action == AuditAction.update
    assert row.entity_id == fila.id
    # Nombres de columna, nunca valores (mismo criterio que
    # `coach_answer_text` en §4.9). `record_audit` ordena alfabéticamente
    # (paso 6, "minimise") — las 16 columnas que persist.py reescribe en
    # cada corrida (las 7 heredadas de 033 + las nueve nuevas de esta
    # feature), nunca solo un subconjunto.
    assert row.changed_fields == sorted(set(persist_module._EXPLANATION_REWRITTEN_FIELDS))
    assert row.diff_json is None


@pytest.mark.asyncio
async def test_regeneracion_identica_igual_escribe_fila(ai_audit_session, escenario):
    """Una regeneración que devolviera texto idéntico NO puede perderse por la
    regla R7: el entrenador la pidió y el historial debe mostrarlo. Además,
    append-only: la primera fila de auditoría nunca se reescribe, solo se
    agrega una nueva."""
    await _seed_cached_explanation(ai_audit_session, use_case="phv_explainer")

    with request_id_scope():
        for _ in range(2):
            state = _persist_state(
                db=ai_audit_session, athlete=escenario["athlete"], actor=escenario["coach"]
            )
            await persist_module.persist(state)
    await ai_audit_session.commit()

    rows = await _audit_rows(ai_audit_session)
    assert [r.action for r in rows] == [AuditAction.update, AuditAction.update]
    # Append-only: dos filas DISTINTAS, ninguna sobrescrita.
    assert rows[0].id != rows[1].id


# ===========================================================================
# Privacidad (Ley 1581)
# ===========================================================================


@pytest.mark.asyncio
async def test_la_fila_no_lleva_dato_alguno_del_menor(ai_audit_session, escenario):
    await _seed_cached_explanation(ai_audit_session, use_case="phv_explainer")
    state = _persist_state(
        db=ai_audit_session,
        athlete=escenario["athlete"],
        actor=escenario["coach"],
        insight=_build_insight(summary_line=NARRATIVA_FICTICIA),
        rendered_text=NARRATIVA_FICTICIA,
    )

    with request_id_scope():
        await persist_module.persist(state)
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
# Cableado
# ===========================================================================


def test_persist_pre_selecciona_antes_de_ejecutar_el_upsert():
    """Invariante real que reemplaza a la vieja aserción de código fuente
    ``"_cached_explanation_id(" in inspect.getsource(handler)`` sobre
    `app/routers/ai.py`: esa función se movió a `persist.py` (T038) y los
    handlers ya no la llaman directamente (ver el docstring del módulo). Se
    decidió RETARGETEAR la aserción, no eliminarla sin más, porque el
    invariante que protegía sigue siendo real y sigue viviendo en código:
    el pre-SELECT que decide `create`/`update` debe ocurrir SIEMPRE antes
    del upsert — invertir ese orden rompería la propia lógica de
    `persisted_action` de `persist.py`, no solo la auditoría."""
    fuente = inspect.getsource(persist_module.persist)
    primera_llamada = fuente.index("_cached_explanation_id(")
    llamada_execute = fuente.index("await db.execute(stmt)")
    assert primera_llamada < llamada_execute


@pytest.mark.parametrize("handler", [phv_explanation, measurement_explanation])
def test_los_handlers_generan_via_run_analysis(handler):
    """Cableado contra que la instrumentación se caiga en una refactorización.

    Reemplaza a la vieja aserción sobre `_record_explanation_audit(` —ese
    símbolo ya no existe en ningún módulo, la auditoría se dispara en línea
    dentro de `persist.persist()` (ver el docstring del módulo)—. Lo único
    que los handlers todavía garantizan por su cuenta es que generan (y por
    lo tanto auditan) EXCLUSIVAMENTE a través de `anthro.pipeline.
    run_analysis`, nunca escribiendo `athlete_ai_explanations`/`audit_log`
    por su lado (data-model.md §6, invariante 5).

    No se puede ejercer por HTTP en la vía offline (el upsert es del dialecto
    MySQL — ver el docstring del módulo), así que se verifica sobre el código
    fuente del handler.
    """
    fuente = inspect.getsource(handler)
    assert "run_analysis(" in fuente


def test_las_columnas_reescritas_no_incluyen_ninguna_medida():
    """Ningún nombre de columna antropométrica puede colarse en la lista."""
    prohibidas = {"standing_height_cm", "sitting_height_cm", "weight_kg", "birth_date"}
    assert prohibidas.isdisjoint(set(persist_module._EXPLANATION_REWRITTEN_FIELDS))
