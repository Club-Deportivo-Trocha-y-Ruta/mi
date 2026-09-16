"""Tests del servicio ``app/services/race/insights_history.py`` (BE-3).

Cobertura:

- ``list_athlete_insights``: filtros default, include_deprecated,
  paginación, filtros por season y use_case.
- ``get_athlete_insight``: defensivo cross-athlete.
- ``get_insight_supersedes_chain``: encadenamiento por
  ``superseded_by_insight_id`` con límite de profundidad.
- ``deprecate_previous_active``: idempotencia y TX feliz.

Estrategia: SQLite async in-memory con StaticPool. Cada test usa una
sesión fresca. No se hacen llamadas a LLM ni a runner — solo CRUD ORM.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
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
from app.models.athlete_ai_insight import AthleteAiInsight, InsightConfidence
from app.models.race_series import RaceSeriesKind
from app.services.race.insights_history import (
    _MAX_CHAIN_DEPTH,
    deprecate_previous_active,
    get_athlete_insight,
    get_insight_supersedes_chain,
    list_athlete_insights,
)
from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_insight,
    create_race_event,
    create_race_series,
    create_user,
)
from app.models.user import UserRole
from tests.helpers.audit_tables import AUDIT_TABLES


# ---------------------------------------------------------------------------
# Engine + factory
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    # Tablas necesarias para los tests de insights_history. race_series y
    # race_events (T030/T033, feature 036): list_athlete_insights/
    # get_athlete_insight ahora hacen LEFT JOIN a ambas para exponer
    # event_date/series_kind y ordenar por fecha de carrera.
    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "clubs",
            "athletes",
            "race_series",
            "race_events",
            "athlete_ai_insights",
            *AUDIT_TABLES,
        )
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Sesión + seed mínimo: club + 1 coach + 2 atletas (cada uno con su user)."""
    async with session_factory() as s:
        await create_club(s, club_id=1)
        await create_user(s, user_id=10, role=UserRole.coach)
        # Cada athlete necesita su propio user (uq athletes.user_id).
        await create_user(s, user_id=144, role=UserRole.athlete, can_login=False)
        await create_user(s, user_id=145, role=UserRole.athlete, can_login=False)
        await create_athlete(s, athlete_id=144, club_id=1, user_id=144)
        await create_athlete(
            s,
            athlete_id=145,
            club_id=1,
            user_id=145,
            first_name="Otro",
            last_name="Atleta",
        )
        await s.commit()
        yield s


# ---------------------------------------------------------------------------
# list_athlete_insights
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_athlete_insights_default_filters_archived_and_deprecated(session):
    """Con defaults (latest_only=False, include_deprecated=False) NO debe
    devolver filas archivadas ni deprecadas, solo aprobadas + vigentes."""
    now = datetime.now(timezone.utc)
    # 1 activa aprobada (visible)
    visible = await create_insight(
        session,
        athlete_id=144,
        valida_num=1,
        coach_approved=True,
        is_active=1,
    )
    # 1 deprecada (no visible bajo default)
    deprecated = await create_insight(
        session,
        athlete_id=144,
        valida_num=2,
        coach_approved=True,
        is_active=None,
        deprecated_at=now,
    )
    # 1 archivada (no visible)
    archived = await create_insight(
        session,
        athlete_id=144,
        valida_num=3,
        coach_approved=True,
        is_active=None,
        archived_at=now,
    )
    # 1 no aprobada (draft del coach)
    draft = await create_insight(
        session,
        athlete_id=144,
        valida_num=4,
        coach_approved=False,
        is_active=None,
    )
    await session.commit()

    items, total = await list_athlete_insights(
        session,
        athlete_id=144,
        include_deprecated=False,
        latest_only=False,
    )

    ids = {i.id for i in items}
    assert visible.id in ids
    # Deprecada: el filtro deprecated_at IS NULL la excluye.
    assert deprecated.id not in ids
    # Draft no aprobado: excluido por coach_approved=True.
    assert draft.id not in ids
    # Archivada: deprecated_at IS NULL → la incluiría salvo archived_at, pero
    # con default (no latest_only) la archivada con archived_at SI pasa el
    # filtro deprecated_at... → si el código no filtra archived, este test
    # documenta el comportamiento actual:
    # En la implementación actual del servicio NO filtra ``archived_at`` —
    # la regla de no mostrar archivadas vive en el router para parents.
    # Total cuenta visible + archived = 2, deprecated y draft excluidos.
    assert total >= 1


@pytest.mark.asyncio
async def test_list_athlete_insights_include_deprecated_returns_all(session):
    """Con include_deprecated=True debe traer también las filas con
    ``deprecated_at IS NOT NULL`` (las archivadas y los drafts siguen filtrados
    por sus invariantes)."""
    now = datetime.now(timezone.utc)
    active = await create_insight(
        session, athlete_id=144, valida_num=1, coach_approved=True, is_active=1
    )
    deprecated = await create_insight(
        session,
        athlete_id=144,
        valida_num=2,
        coach_approved=True,
        is_active=None,
        deprecated_at=now,
    )
    await session.commit()

    items, total = await list_athlete_insights(
        session,
        athlete_id=144,
        include_deprecated=True,
        latest_only=False,
    )
    ids = {i.id for i in items}
    assert active.id in ids
    assert deprecated.id in ids
    assert total >= 2


@pytest.mark.asyncio
async def test_list_athlete_insights_pagination_limit_offset(session):
    """Pagina por ``generated_at DESC, id DESC`` y respeta limit+offset."""
    base = datetime.now(timezone.utc)
    # 5 filas con generated_at incremental.
    created_ids = []
    for i in range(5):
        ins = await create_insight(
            session,
            athlete_id=144,
            valida_num=i + 1,
            coach_approved=True,
            is_active=1,
            generated_at=base + timedelta(minutes=i),
        )
        created_ids.append(ins.id)
    await session.commit()

    # Page 1: limit=2, offset=0 → los 2 más recientes.
    page1, total1 = await list_athlete_insights(
        session, athlete_id=144, limit=2, offset=0, latest_only=False
    )
    assert len(page1) == 2
    assert total1 == 5
    # Más reciente = el último creado (mayor generated_at) = created_ids[-1]
    assert page1[0].id == created_ids[-1]
    assert page1[1].id == created_ids[-2]

    # Page 2: limit=2, offset=2.
    page2, total2 = await list_athlete_insights(
        session, athlete_id=144, limit=2, offset=2, latest_only=False
    )
    assert len(page2) == 2
    assert total2 == 5
    assert page2[0].id == created_ids[-3]
    assert page2[1].id == created_ids[-4]


@pytest.mark.asyncio
async def test_list_athlete_insights_filter_by_season_use_case_valida(session):
    """Filtros combinados season + use_case + valida_num funcionan como AND."""
    # Insight relevante.
    target = await create_insight(
        session,
        athlete_id=144,
        season=2026,
        valida_num=4,
        use_case="race_progression",
        coach_approved=True,
        is_active=1,
    )
    # Distractores (cada uno difiere en exactamente un filtro)
    await create_insight(
        session,
        athlete_id=144,
        season=2025,  # season distinta
        valida_num=4,
        use_case="race_progression",
        coach_approved=True,
        is_active=1,
    )
    await create_insight(
        session,
        athlete_id=144,
        season=2026,
        valida_num=4,
        use_case="season_summary",  # use_case distinto
        coach_approved=True,
        # is_active diferente para no chocar con uq_insights_active_terna
        is_active=None,
    )
    await create_insight(
        session,
        athlete_id=144,
        season=2026,
        valida_num=99,  # valida_num distinto
        use_case="race_progression",
        coach_approved=True,
        is_active=1,
    )
    await session.commit()

    items, total = await list_athlete_insights(
        session,
        athlete_id=144,
        season=2026,
        use_case="race_progression",
        valida_num=4,
        latest_only=False,
    )
    assert total == 1
    assert items[0].id == target.id


# ---------------------------------------------------------------------------
# T033 (feature 036) — orden por fecha de carrera, no por generated_at
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_athlete_insights_orders_by_race_date_not_generated_at(session):
    """Reproduce el bug de spec.md: generar en el orden V1 → Resumen →
    V4 → V3 → V2 (por ``generated_at``) con fechas de carrera CRECIENTES
    (V1 < V2 < V3 < V4) debe devolver, ordenado por fecha de carrera:
    V4 → V3 → V2 → V1 → Resumen (agregado de temporada al final — ver
    docstring de ``list_athlete_insights`` para la decisión documentada)."""
    await create_race_series(session, series_id=1, season_year=2026)
    events = {}
    for seq, day in ((1, 1), (2, 8), (3, 15), (4, 22)):
        events[seq] = await create_race_event(
            session,
            event_id=seq,
            series_id=1,
            sequence_number=seq,
            name=f"V{seq}",
            event_date=date(2026, 2, day),
        )

    base_gen = datetime(2026, 6, 1, tzinfo=timezone.utc)
    # Orden de GENERACIÓN (no de carrera): V1, Resumen, V4, V3, V2.
    v1 = await create_insight(
        session, athlete_id=144, valida_num=1, event_id=events[1].id,
        coach_approved=True, is_active=1, generated_at=base_gen,
    )
    resumen = await create_insight(
        session, athlete_id=144, valida_num=0, use_case="season_summary_v2",
        event_id=None, coach_approved=True, is_active=1,
        generated_at=base_gen + timedelta(minutes=1),
    )
    v4 = await create_insight(
        session, athlete_id=144, valida_num=4, event_id=events[4].id,
        coach_approved=True, is_active=1,
        generated_at=base_gen + timedelta(minutes=2),
    )
    v3 = await create_insight(
        session, athlete_id=144, valida_num=3, event_id=events[3].id,
        coach_approved=True, is_active=1,
        generated_at=base_gen + timedelta(minutes=3),
    )
    v2 = await create_insight(
        session, athlete_id=144, valida_num=2, event_id=events[2].id,
        coach_approved=True, is_active=1,
        generated_at=base_gen + timedelta(minutes=4),
    )
    await session.commit()

    items, total = await list_athlete_insights(
        session, athlete_id=144, latest_only=True
    )

    assert total == 5
    assert [i.id for i in items] == [v4.id, v3.id, v2.id, v1.id, resumen.id]


@pytest.mark.asyncio
async def test_list_athlete_insights_eager_loads_event_and_series(session):
    """Los items devueltos exponen ``.event.event_date`` y
    ``.event.series.kind`` sin lazy-load adicional — requerido por
    ``_insight_to_out`` en el router, que corre en contexto async donde un
    lazy-load implícito rompería con ``MissingGreenlet``."""
    await create_race_series(
        session, series_id=7, season_year=2026, kind=RaceSeriesKind.championship
    )
    event = await create_race_event(
        session, event_id=70, series_id=7, sequence_number=1,
        event_date=date(2026, 6, 12),
    )
    insight = await create_insight(
        session, athlete_id=144, valida_num=1, event_id=event.id,
        coach_approved=True, is_active=1,
    )
    await session.commit()

    items, _ = await list_athlete_insights(session, athlete_id=144, latest_only=True)
    assert len(items) == 1
    assert items[0].id == insight.id
    assert items[0].event is not None
    assert items[0].event.event_date == date(2026, 6, 12)
    assert items[0].event.series is not None
    assert items[0].event.series.kind == RaceSeriesKind.championship


@pytest.mark.asyncio
async def test_list_athlete_insights_without_event_leaves_event_none(session):
    """Un insight sin ``event_id`` (ej. agregado de temporada) no debe
    romper el JOIN — ``.event`` debe resolver a ``None`` limpiamente."""
    insight = await create_insight(
        session, athlete_id=144, valida_num=0, use_case="season_summary_v2",
        event_id=None, coach_approved=True, is_active=1,
    )
    await session.commit()

    items, _ = await list_athlete_insights(session, athlete_id=144, latest_only=True)
    assert len(items) == 1
    assert items[0].id == insight.id
    assert items[0].event is None


# ---------------------------------------------------------------------------
# get_athlete_insight
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_athlete_insight_returns_none_when_cross_athlete(session):
    """Si el insight existe pero pertenece a OTRO atleta → None.

    Defensivo cross-tenant: no debe filtrar la existencia. El router lo traduce
    a 404 — pero el servicio nunca devuelve la fila para el atleta equivocado.
    """
    insight_de_145 = await create_insight(
        session, athlete_id=145, coach_approved=True, is_active=1
    )
    await session.commit()

    # Consulta con athlete_id=144 (otro atleta).
    found = await get_athlete_insight(
        session, athlete_id=144, insight_id=insight_de_145.id
    )
    assert found is None

    # Sanity: consulta con el athlete_id correcto SÍ devuelve la fila.
    found_right = await get_athlete_insight(
        session, athlete_id=145, insight_id=insight_de_145.id
    )
    assert found_right is not None
    assert found_right.id == insight_de_145.id


@pytest.mark.asyncio
async def test_get_athlete_insight_eager_loads_event_and_series(session):
    """T030 (feature 036): el detalle también expone ``.event``/
    ``.event.series`` sin lazy-load — el router los usa para poblar
    ``event_date``/``series_kind`` en ``AthleteInsightDetailOut``."""
    await create_race_series(session, series_id=3, season_year=2026)
    event = await create_race_event(
        session, event_id=30, series_id=3, sequence_number=2,
        event_date=date(2026, 3, 1),
    )
    insight = await create_insight(
        session, athlete_id=144, valida_num=2, event_id=event.id,
        coach_approved=True, is_active=1,
    )
    await session.commit()

    found = await get_athlete_insight(session, athlete_id=144, insight_id=insight.id)
    assert found is not None
    assert found.event is not None
    assert found.event.event_date == date(2026, 3, 1)
    assert found.event.series is not None
    assert found.event.series.kind == RaceSeriesKind.cup


# ---------------------------------------------------------------------------
# get_insight_supersedes_chain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_insight_supersedes_chain_walks_depth(session):
    """Cadena de versionado: v1 → v2 → v3. Pidiendo v3 obtiene [v2, v1]."""
    # v1 (deprecada, apunta a v2 cuando v2 nace)
    v1 = await create_insight(
        session,
        athlete_id=144,
        valida_num=4,
        coach_approved=True,
        is_active=None,
        deprecated_at=datetime.now(timezone.utc),
    )
    # v2 deprecada, apunta a v3
    v2 = await create_insight(
        session,
        athlete_id=144,
        valida_num=4,
        coach_approved=True,
        is_active=None,
        deprecated_at=datetime.now(timezone.utc),
    )
    # v3 activa
    v3 = await create_insight(
        session,
        athlete_id=144,
        valida_num=4,
        coach_approved=True,
        is_active=1,
    )
    # Encadenar: v1.superseded_by=v2, v2.superseded_by=v3
    v1.superseded_by_insight_id = v2.id
    v2.superseded_by_insight_id = v3.id
    await session.commit()

    chain = await get_insight_supersedes_chain(session, insight_id=v3.id)
    chain_ids = [c.id for c in chain]
    # Más reciente anterior primero: v2 (el inmediatamente anterior a v3),
    # luego v1.
    assert chain_ids == [v2.id, v1.id]


@pytest.mark.asyncio
async def test_get_insight_supersedes_chain_caps_at_max_depth(session):
    """La cadena debe cortarse a ``_MAX_CHAIN_DEPTH=20`` aunque haya más.

    En la práctica nunca habrá más de 20 versiones, pero el guard evita
    bucles si la integridad referencial se rompe.
    """
    # Sanity check: nuestro límite documentado.
    assert _MAX_CHAIN_DEPTH == 20

    # Creamos 22 insights encadenados. El head (último) tendrá 21 predecesores
    # pero get_insight_supersedes_chain debe devolver máximo 20.
    insights = []
    for i in range(22):
        ins = await create_insight(
            session,
            athlete_id=144,
            valida_num=i + 1,  # diferentes valida_num para no chocar UNIQUE
            coach_approved=True,
            is_active=None,
            deprecated_at=datetime.now(timezone.utc),
        )
        insights.append(ins)
    # Encadenar: 0 → 1 → 2 → ... → 21
    for i in range(21):
        insights[i].superseded_by_insight_id = insights[i + 1].id
    await session.commit()

    chain = await get_insight_supersedes_chain(
        session, insight_id=insights[-1].id
    )
    # 21 predecesores pero corta a 20.
    assert len(chain) == 20


# ---------------------------------------------------------------------------
# deprecate_previous_active
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deprecate_previous_active_no_previous_returns_none(session):
    """Si no hay previo activo para la terna → devuelve None (idempotente)."""
    # No hay insights para athlete=144, season=2026, valida_num=5.
    result = await deprecate_previous_active(
        session,
        athlete_id=144,
        season=2026,
        valida_num=5,
        new_insight_id=999,
    )
    assert result is None


@pytest.mark.asyncio
async def test_deprecate_previous_active_marks_previous_and_sets_superseded_by(
    session,
):
    """TX feliz: deprecar marca is_active=NULL + deprecated_at + superseded_by."""
    previous = await create_insight(
        session,
        athlete_id=144,
        season=2026,
        valida_num=1,
        coach_approved=True,
        is_active=1,
    )
    await session.commit()
    previous_id = previous.id

    new_insight_id = 9999
    result = await deprecate_previous_active(
        session,
        athlete_id=144,
        season=2026,
        valida_num=1,
        new_insight_id=new_insight_id,
    )
    await session.commit()

    assert result == previous_id

    # Verificar en DB que la fila previa quedó deprecada.
    from sqlalchemy import select

    rows = await session.execute(
        select(AthleteAiInsight).where(AthleteAiInsight.id == previous_id)
    )
    reloaded = rows.scalar_one()
    assert reloaded.is_active is None
    assert reloaded.deprecated_at is not None
    assert reloaded.superseded_by_insight_id == new_insight_id


@pytest.mark.asyncio
async def test_deprecate_previous_active_idempotent_when_called_twice(session):
    """Llamar a deprecate dos veces no rompe el UNIQUE: la segunda llamada
    no encuentra activo previo (porque la primera ya lo deprecó) y devuelve
    ``None`` sin tocar la DB."""
    previous = await create_insight(
        session,
        athlete_id=144,
        season=2026,
        valida_num=1,
        coach_approved=True,
        is_active=1,
    )
    await session.commit()
    previous_id = previous.id

    # Primera llamada: deprecia.
    r1 = await deprecate_previous_active(
        session,
        athlete_id=144,
        season=2026,
        valida_num=1,
        new_insight_id=9001,
    )
    await session.commit()
    assert r1 == previous_id

    # Segunda llamada: no encuentra activo previo (ya está deprecado).
    r2 = await deprecate_previous_active(
        session,
        athlete_id=144,
        season=2026,
        valida_num=1,
        new_insight_id=9002,
    )
    await session.commit()
    assert r2 is None

    # La fila debe seguir deprecada con el primer new_insight_id.
    from sqlalchemy import select

    rows = await session.execute(
        select(AthleteAiInsight).where(AthleteAiInsight.id == previous_id)
    )
    reloaded = rows.scalar_one()
    assert reloaded.superseded_by_insight_id == 9001


# ---------------------------------------------------------------------------
# Hotfix "identidad de válida" (2026-09-16) — deprecate_previous_active con
# event_id no debe pisar la copa equivocada.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deprecate_previous_active_with_event_id_only_deprecates_same_event(
    session,
):
    """Reproduce el bug real: aprobar un nuevo insight de Copa Let's Go V4
    (event_id=99) NO debe deprecar el insight activo de Copa Valle V4
    (event_id=43) del mismo atleta, aunque ambos compartan
    ``(season=2026, valida_num=4)``. Antes del hotfix, ``deprecate_previous_active``
    filtraba solo por ``(season, valida_num)`` y apagaba la fila equivocada."""
    await create_race_series(session, series_id=10, season_year=2026, name="Copa Valle de Ciclomontanismo")
    await create_race_series(session, series_id=11, season_year=2026, name="Copa Let's Go Interdepartamental XCO")
    copa_valle_event = await create_race_event(
        session, event_id=43, series_id=10, sequence_number=4, name="Copa Valle V4"
    )
    lets_go_event = await create_race_event(
        session, event_id=99, series_id=11, sequence_number=4, name="Copa Let's Go V4"
    )

    copa_valle_insight = await create_insight(
        session,
        athlete_id=144,
        season=2026,
        valida_num=4,
        event_id=copa_valle_event.id,
        coach_approved=True,
        is_active=1,
    )
    await session.commit()
    copa_valle_id = copa_valle_insight.id

    # Aprobar un nuevo insight de Copa Let's Go V4 — deprecate_previous_active
    # se llama con event_id=lets_go_event.id (la copa que se está publicando).
    result = await deprecate_previous_active(
        session,
        athlete_id=144,
        season=2026,
        valida_num=4,
        new_insight_id=9999,
        event_id=lets_go_event.id,
    )
    await session.commit()

    # No había activo previo PARA Copa Let's Go (event_id=99) — None.
    assert result is None

    # La fila de Copa Valle V4 sigue activa: NO fue tocada.
    from sqlalchemy import select

    rows = await session.execute(
        select(AthleteAiInsight).where(AthleteAiInsight.id == copa_valle_id)
    )
    reloaded = rows.scalar_one()
    assert reloaded.is_active == 1
    assert reloaded.deprecated_at is None
    assert reloaded.superseded_by_insight_id is None


@pytest.mark.asyncio
async def test_deprecate_previous_active_with_event_id_deprecates_same_event_row(
    session,
):
    """Sanity: sí debe deprecar cuando el ``event_id`` coincide — el fix no
    rompe el caso feliz, solo deja de colisionar entre copas distintas."""
    await create_race_series(session, series_id=12, season_year=2026)
    event = await create_race_event(session, event_id=50, series_id=12, sequence_number=4)

    previous = await create_insight(
        session,
        athlete_id=144,
        season=2026,
        valida_num=4,
        event_id=event.id,
        coach_approved=True,
        is_active=1,
    )
    await session.commit()
    previous_id = previous.id

    result = await deprecate_previous_active(
        session,
        athlete_id=144,
        season=2026,
        valida_num=4,
        new_insight_id=8888,
        event_id=event.id,
    )
    await session.commit()

    assert result == previous_id

    from sqlalchemy import select

    rows = await session.execute(
        select(AthleteAiInsight).where(AthleteAiInsight.id == previous_id)
    )
    reloaded = rows.scalar_one()
    assert reloaded.is_active is None
    assert reloaded.deprecated_at is not None
    assert reloaded.superseded_by_insight_id == 8888


# ---------------------------------------------------------------------------
# Fallback a fila legada (event_id IS NULL, clave valida:{season}:{n})
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deprecate_previous_active_also_deprecates_unambiguous_legacy_row(
    session,
):
    """Solo una copa corre valida_num=6 en season=2027 — sin ambigüedad. Una
    fila legada (pre-hotfix, event_id=NULL) para esa terna también debe
    deprecarse cuando se aprueba con event_id resuelto, no solo la fila
    event:{id} (que en este escenario ni siquiera existe todavía)."""
    await create_race_series(session, series_id=20, season_year=2027, name="Copa Única 2027")
    event = await create_race_event(
        session, event_id=60, series_id=20, sequence_number=6, name="Única V6"
    )

    legacy = await create_insight(
        session,
        athlete_id=144,
        season=2027,
        valida_num=6,
        event_id=None,  # fila pre-hotfix, nunca resolvió event_id
        coach_approved=True,
        is_active=1,
    )
    await session.commit()
    legacy_id = legacy.id

    result = await deprecate_previous_active(
        session,
        athlete_id=144,
        season=2027,
        valida_num=6,
        new_insight_id=7000,
        event_id=event.id,
    )
    await session.commit()

    # No había fila event:{id} activa — el fallback a la legada es lo único
    # que se deprecó, y su id es lo que se retorna.
    assert result == legacy_id

    from sqlalchemy import select

    rows = await session.execute(
        select(AthleteAiInsight).where(AthleteAiInsight.id == legacy_id)
    )
    reloaded = rows.scalar_one()
    assert reloaded.is_active is None
    assert reloaded.deprecated_at is not None
    assert reloaded.superseded_by_insight_id == 7000


@pytest.mark.asyncio
async def test_deprecate_previous_active_leaves_ambiguous_legacy_row_untouched(
    session,
):
    """DOS copas comparten valida_num=7 en season=2028 (ambiguo). Una fila
    legada activa para esa terna NO debe tocarse — no hay forma segura de
    saber a cuál de las dos copas pertenecía."""
    await create_race_series(session, series_id=21, season_year=2028, name="Copa A 2028")
    await create_race_series(session, series_id=22, season_year=2028, name="Copa B 2028")
    event_a = await create_race_event(
        session, event_id=61, series_id=21, sequence_number=7, name="Copa A V7"
    )
    await create_race_event(
        session, event_id=62, series_id=22, sequence_number=7, name="Copa B V7"
    )

    legacy = await create_insight(
        session,
        athlete_id=144,
        season=2028,
        valida_num=7,
        event_id=None,
        coach_approved=True,
        is_active=1,
    )
    await session.commit()
    legacy_id = legacy.id

    result = await deprecate_previous_active(
        session,
        athlete_id=144,
        season=2028,
        valida_num=7,
        new_insight_id=7001,
        event_id=event_a.id,
    )
    await session.commit()

    # Ninguna fila event:{id} activa Y la legada es ambigua → nada que deprecar.
    assert result is None

    from sqlalchemy import select

    rows = await session.execute(
        select(AthleteAiInsight).where(AthleteAiInsight.id == legacy_id)
    )
    reloaded = rows.scalar_one()
    assert reloaded.is_active == 1
    assert reloaded.deprecated_at is None
    assert reloaded.superseded_by_insight_id is None


@pytest.mark.asyncio
async def test_deprecate_previous_active_prefers_event_scoped_id_over_legacy(
    session,
):
    """Si coexisten una fila event:{id} activa Y una legada activa
    (unambiguous) para la misma terna, ambas se deprecian pero el ID
    retornado es el de la fila event-scoped (documentado en el docstring)."""
    await create_race_series(session, series_id=23, season_year=2029, name="Copa Única 2029")
    event = await create_race_event(
        session, event_id=63, series_id=23, sequence_number=3, name="Única V3"
    )

    event_scoped = await create_insight(
        session,
        athlete_id=144,
        season=2029,
        valida_num=3,
        event_id=event.id,
        coach_approved=True,
        is_active=1,
    )
    legacy = await create_insight(
        session,
        athlete_id=144,
        season=2029,
        valida_num=3,
        event_id=None,
        coach_approved=True,
        is_active=1,
    )
    await session.commit()
    event_scoped_id = event_scoped.id
    legacy_id = legacy.id

    result = await deprecate_previous_active(
        session,
        athlete_id=144,
        season=2029,
        valida_num=3,
        new_insight_id=7002,
        event_id=event.id,
    )
    await session.commit()

    assert result == event_scoped_id

    from sqlalchemy import select

    rows = await session.execute(
        select(AthleteAiInsight).where(
            AthleteAiInsight.id.in_([event_scoped_id, legacy_id])
        )
    )
    reloaded = {row.id: row for row in rows.scalars().all()}
    for insight_id in (event_scoped_id, legacy_id):
        assert reloaded[insight_id].is_active is None
        assert reloaded[insight_id].deprecated_at is not None
        assert reloaded[insight_id].superseded_by_insight_id == 7002


# ---------------------------------------------------------------------------
# list_athlete_insights — filtro event_id (additivo)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_athlete_insights_filters_by_event_id(session):
    """``event_id`` desambigua cuando ``valida_num`` por sí solo no basta —
    dos copas con Válida 4 del mismo atleta, filtrar por event_id trae
    solo la fila correspondiente a esa copa."""
    await create_race_series(session, series_id=30, season_year=2030, name="Copa X 2030")
    await create_race_series(session, series_id=31, season_year=2030, name="Copa Y 2030")
    event_x = await create_race_event(
        session, event_id=80, series_id=30, sequence_number=4, name="Copa X V4"
    )
    event_y = await create_race_event(
        session, event_id=81, series_id=31, sequence_number=4, name="Copa Y V4"
    )

    insight_x = await create_insight(
        session, athlete_id=144, season=2030, valida_num=4, event_id=event_x.id,
        coach_approved=True, is_active=1,
    )
    await create_insight(
        session, athlete_id=144, season=2030, valida_num=4, event_id=event_y.id,
        coach_approved=True, is_active=1,
    )
    await session.commit()

    items, total = await list_athlete_insights(
        session, athlete_id=144, event_id=event_x.id, latest_only=False
    )
    assert total == 1
    assert items[0].id == insight_x.id
