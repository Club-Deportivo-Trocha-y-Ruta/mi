"""Tests T046 (feature 043 — race course profile, User Story 4).

Contrato vinculante: ``specs/043-race-course-profile/contracts/ai-course-block.md``.
Landing en modo TDD: ``fetch_course_context`` (``app/services/race/queries.py``),
``format_course_meta`` y ``AnalystV3Input.course_meta`` (``race/agents/analyst.py``)
todavía NO existen — los implementa un task hermano (T047-049). Este módulo
falla al *importar* hasta entonces; eso es lo esperado (ver reporte de T046).

Cubre:

1. ``fetch_course_context`` — cada válida solicitada es una clave (incluso sin
   evento o sin setup para la categoría → ``{}``); claves EXACTAS cuando hay
   datos; ``course_notes`` estructuralmente excluido (FR-020) — a nivel de
   dict (la comprobación robusta e independiente de la implementación) y,
   best-effort, a nivel de SQL compilado de las queries que tocan
   ``race_course_category_setups``/``race_course_variants``.
2. ``format_course_meta`` — ``None``/``{}`` → ``None``; bullets parciales;
   los seis bullets exactos del contrato §2 (comas decimales).
3. Render de ``race_analyst_v3`` y ``race_season_summary_v3`` con
   ``course_meta`` presente/ausente → bloque "Circuito registrado" /
   "Circuito — SIN DATO" + veto "PROHIBIDO mencionar distancia".
4. ``race_analyst_v2`` sigue renderizando (``strict=False``, ignora claves
   de contexto no usadas) aunque el contexto cargue las claves nuevas.
5. Un chequeo "end-to-end" simplificado (fetch + format + render, sin
   LLM/grafo) que encadena una válida con datos de circuito y otra sin ellos.
6. Privacidad: un ``course_notes`` sintético con un nombre-prohibido
   fabricado (``"Estudiante Ficticio Uno"`` — NUNCA un menor real, CLAUDE.md)
   nunca sale como clave del dict devuelto.

Toda la data de fixture es 100% ficticia.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.race_category import CategoryGender, RaceCategory
from app.models.race_course_category_setup import RaceCourseCategorySetup
from app.models.race_course_variant import RaceCourseVariant
from app.models.race_event import RaceEvent, RaceEventStatus, TerrainType
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole

# Las tres piezas de abajo son el sujeto de esta feature y AÚN NO EXISTEN
# (T047-049 las implementan). El import falla hasta entonces — ver
# ``--collect-only`` en el reporte de T046.
from app.services.race.agents.analyst import (
    PROMPT_VERSION_ANALYST_V3,
    PROMPT_VERSION_SEASON_SUMMARY_V3,
    AnalystV3Input,
    RaceAnalystAgent,
    format_course_meta,
)
from app.services.race.prompts import render_prompt
from app.services.race.queries import fetch_course_context, fetch_course_context_by_event
from app.services.race.schemas import AnalysisInput, LTADGroup
from tests.helpers.audit_tables import AUDIT_TABLES

# NOTA: ``asyncio_mode = "auto"`` (pyproject.toml) detecta las funciones
# ``async def`` solas — no se fija ``pytestmark = pytest.mark.asyncio`` a
# nivel de módulo porque este archivo mezcla tests síncronos (formateo,
# render de prompts) con tests async (DB real); fijarlo emite un
# ``PytestWarning`` espurio en cada test síncrono.

_SEASON = 2026
_COACH_ID = 900

_TABLES = (
    "users",
    "race_series",
    "race_categories",
    "race_events",
    "race_course_variants",
    "race_course_category_setups",
    *AUDIT_TABLES,
)


# ---------------------------------------------------------------------------
# DB real aiosqlite in-memory (mismo patrón que test_athlete_context.py)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncSession:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Helpers de seed (datos 100% ficticios)
# ---------------------------------------------------------------------------


def _seed_coach(session: AsyncSession) -> User:
    coach = User(
        id=_COACH_ID,
        first_name="Coach",
        last_name="Ficticio",
        role=UserRole.coach,
        is_active=True,
        can_login=True,
    )
    session.add(coach)
    return coach


def _seed_series(session: AsyncSession, *, series_id: int = 1, season: int = _SEASON) -> RaceSeries:
    series = RaceSeries(
        id=series_id,
        name=f"Copa Ficticia {season}",
        season_year=season,
        organizer="Liga Ficticia",
        points_scheme_code="copa_ficticia_test",
    )
    session.add(series)
    return series


def _seed_category(session: AsyncSession, *, category_id: int, code: str) -> RaceCategory:
    category = RaceCategory(
        id=category_id,
        code=code,
        label=f"Categoría {code}",
        sex=CategoryGender.MIXED,
        sort_order=category_id,
        is_active=True,
    )
    session.add(category)
    return category


def _seed_event(
    session: AsyncSession,
    *,
    event_id: int,
    series_id: int,
    sequence_number: int,
    course_notes: str | None = None,
    terrain_type: TerrainType | None = None,
    technical_difficulty: int | None = None,
    key_sectors: list[str] | None = None,
) -> RaceEvent:
    event = RaceEvent(
        id=event_id,
        series_id=series_id,
        sequence_number=sequence_number,
        name=f"VALIDA FICTICIA {sequence_number}",
        event_date=date(_SEASON, 1, min(max(sequence_number, 1), 28)),
        status=RaceEventStatus.COMPLETED,
        created_by_user_id=_COACH_ID,
        terrain_type=terrain_type,
        technical_difficulty=technical_difficulty,
        key_sectors=key_sectors,
        course_notes=course_notes,
    )
    session.add(event)
    return event


def _seed_variant(
    session: AsyncSession,
    *,
    variant_id: int,
    race_event_id: int,
    lap_distance_m: int = 4200,
    elevation_gain_m: int | None = 110,
    label: str = "Circuito completo",
) -> RaceCourseVariant:
    variant = RaceCourseVariant(
        id=variant_id,
        race_event_id=race_event_id,
        label=label,
        lap_distance_m=lap_distance_m,
        elevation_gain_m=elevation_gain_m,
        has_elevation=elevation_gain_m is not None,
        point_count=3,
        geometry=[[3.40, -76.50, 1500.0], [3.41, -76.51, 1510.0], [3.42, -76.52, 1505.0]],
        detection_method="single",
        recorded_laps=1,
        source_sha256="a" * 64,
        created_by_user_id=_COACH_ID,
    )
    session.add(variant)
    return variant


def _seed_setup(
    session: AsyncSession,
    *,
    race_event_id: int,
    category_id: int,
    variant_id: int,
    laps: int = 3,
) -> RaceCourseCategorySetup:
    setup = RaceCourseCategorySetup(
        race_event_id=race_event_id,
        category_id=category_id,
        variant_id=variant_id,
        laps=laps,
    )
    session.add(setup)
    return setup


# ---------------------------------------------------------------------------
# 1. fetch_course_context
# ---------------------------------------------------------------------------


async def test_fetch_course_context_every_requested_valida_is_a_key(db: AsyncSession):
    """Contrato §1 + descripción de la tarea: TODA válida solicitada aparece
    como clave, incluida una sin evento en la temporada y una con evento
    pero sin setup para la categoría del corredor."""
    _seed_coach(db)
    series = _seed_series(db)
    target_category = _seed_category(db, category_id=10, code="PJUV_A")
    other_category = _seed_category(db, category_id=11, code="PJUV_B")

    # Válida 1: datos completos de circuito para la categoría objetivo.
    event1 = _seed_event(
        db, event_id=1, series_id=series.id, sequence_number=1,
        terrain_type=TerrainType.mixto, technical_difficulty=4,
        key_sectors=["subida_larga", "rock_garden"],
    )
    variant1 = _seed_variant(db, variant_id=1, race_event_id=event1.id)
    _seed_setup(db, race_event_id=event1.id, category_id=target_category.id, variant_id=variant1.id, laps=3)

    # Válida 2: el evento existe pero SOLO tiene setup para la OTRA categoría.
    event2 = _seed_event(db, event_id=2, series_id=series.id, sequence_number=2)
    variant2 = _seed_variant(db, variant_id=2, race_event_id=event2.id)
    _seed_setup(db, race_event_id=event2.id, category_id=other_category.id, variant_id=variant2.id, laps=2)

    await db.commit()

    # Válida 3: no existe ningún RaceEvent con sequence_number=3 en la temporada.
    result = await fetch_course_context(db, _SEASON, [1, 2, 3], target_category.id)

    assert set(result.keys()) == {1, 2, 3}
    assert result[2] == {}
    assert result[3] == {}
    assert result[1] != {}


async def test_fetch_course_context_entry_has_exact_keys_when_present(db: AsyncSession):
    _seed_coach(db)
    series = _seed_series(db)
    category = _seed_category(db, category_id=10, code="PJUV_A")
    event = _seed_event(
        db, event_id=1, series_id=series.id, sequence_number=1,
        terrain_type=TerrainType.mixto, technical_difficulty=4,
        key_sectors=["subida_larga", "rock_garden"],
    )
    variant = _seed_variant(db, variant_id=1, race_event_id=event.id, lap_distance_m=4200, elevation_gain_m=110)
    _seed_setup(db, race_event_id=event.id, category_id=category.id, variant_id=variant.id, laps=3)
    await db.commit()

    result = await fetch_course_context(db, _SEASON, [1], category.id)

    expected_keys = {
        "lap_distance_m",
        "elevation_gain_m",
        "laps",
        "terrain_type",
        "technical_difficulty",
        "key_sectors",
    }
    assert set(result[1].keys()) == expected_keys
    assert "course_notes" not in result[1]
    assert result[1]["lap_distance_m"] == 4200
    assert result[1]["elevation_gain_m"] == 110
    assert result[1]["laps"] == 3


async def test_fetch_course_context_never_exposes_course_notes_key(db: AsyncSession):
    """Privacidad (bullet dedicado de la tarea): un ``course_notes`` con un
    nombre-prohibido fabricado nunca sale como CLAVE del dict — no basta con
    que el valor esté ausente, la clave misma no debe existir."""
    _seed_coach(db)
    series = _seed_series(db)
    category = _seed_category(db, category_id=10, code="PJUV_A")
    forbidden = "Estudiante Ficticio Uno"  # sintético — nunca un menor real
    event = _seed_event(
        db, event_id=1, series_id=series.id, sequence_number=1,
        course_notes=f"{forbidden} ayudó a marcar el sector técnico (dato ficticio)",
        terrain_type=TerrainType.trocha, technical_difficulty=2,
    )
    variant = _seed_variant(db, variant_id=1, race_event_id=event.id)
    _seed_setup(db, race_event_id=event.id, category_id=category.id, variant_id=variant.id, laps=2)
    await db.commit()

    result = await fetch_course_context(db, _SEASON, [1], category.id)

    assert "course_notes" not in result[1]
    assert forbidden not in str(result[1])


async def test_fetch_course_context_course_table_queries_never_select_course_notes(
    db: AsyncSession,
):
    """FR-020 — comprobación estructural adicional a nivel de SQL compilado.

    Best-effort: intercepta cada ``db.execute`` y, de las statements cuyo SQL
    compilado toca ``race_course_category_setups``/``race_course_variants``
    (las tablas NUEVAS de esta feature — ``course_notes`` no vive en
    ninguna de las dos), verifica que ninguna incluya esa columna.

    Deliberadamente NO se exige lo mismo del loader de eventos reutilizado
    (``load_events``/``load_series``, el mismo patrón que
    ``fetch_event_conditions`` ya usa): ese ``select(RaceEvent)`` trae la
    fila completa — ``course_notes`` incluido como columna del esquema,
    igual que hoy trae ``weather_notes`` — y el contrato solo exige que
    ``fetch_course_context`` LEA de esos objustos en memoria únicamente
    ``terrain_type``/``technical_difficulty``/``key_sectors``, nunca
    ``course_notes`` (ya cubierto por las dos pruebas de arriba, a nivel de
    dict). La garantía que esta prueba añade es que la query DEDICADA de
    circuito en sí nunca seleccione la columna.
    """
    _seed_coach(db)
    series = _seed_series(db)
    category = _seed_category(db, category_id=10, code="PJUV_A")
    event = _seed_event(
        db, event_id=1, series_id=series.id, sequence_number=1,
        course_notes="Estudiante Ficticio Uno — dato ficticio",
        terrain_type=TerrainType.mixto, technical_difficulty=4,
    )
    variant = _seed_variant(db, variant_id=1, race_event_id=event.id)
    _seed_setup(db, race_event_id=event.id, category_id=category.id, variant_id=variant.id, laps=3)
    await db.commit()

    executed: list[Any] = []
    original_execute = db.execute

    async def _spy(stmt, *args, **kwargs):
        executed.append(stmt)
        return await original_execute(stmt, *args, **kwargs)

    db.execute = _spy
    try:
        await fetch_course_context(db, _SEASON, [1], category.id)
    finally:
        db.execute = original_execute

    compiled_texts: list[str] = []
    for stmt in executed:
        try:
            compiled_texts.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
        except Exception:
            compiled_texts.append(str(stmt))

    course_table_stmts = [
        c
        for c in compiled_texts
        if "race_course_category_setups" in c or "race_course_variants" in c
    ]
    assert course_table_stmts, (
        "fetch_course_context no ejecutó ninguna query visible sobre las "
        "tablas de circuito — revisar el spy de db.execute en este test."
    )
    for compiled in course_table_stmts:
        assert "course_notes" not in compiled


# ---------------------------------------------------------------------------
# 1b. fetch_course_context — series_id (hotfix identidad de válida)
#
# Dos copas de la misma temporada, ambas con un evento sequence_number=4,
# cada una con su propio setup para la misma categoría. Sin series_id, la
# ambigüedad preexistente no se afirma (solo se documenta); con series_id
# cada copa ve únicamente su propio circuito.
# ---------------------------------------------------------------------------


async def test_fetch_course_context_series_id_scopes_to_own_series(db: AsyncSession):
    _seed_coach(db)
    series_valle = _seed_series(db, series_id=1, season=_SEASON)
    series_letsgo = RaceSeries(
        id=2,
        name="Copa Let's Go Ficticia",
        season_year=_SEASON,
        organizer="Liga Ficticia",
        points_scheme_code="copa_ficticia_test",
    )
    db.add(series_letsgo)
    category = _seed_category(db, category_id=10, code="PJUV_A")

    event_valle_v4 = _seed_event(
        db, event_id=41, series_id=series_valle.id, sequence_number=4,
        terrain_type=TerrainType.mixto, technical_difficulty=3,
    )
    variant_valle = _seed_variant(db, variant_id=41, race_event_id=event_valle_v4.id, lap_distance_m=4200)
    _seed_setup(db, race_event_id=event_valle_v4.id, category_id=category.id, variant_id=variant_valle.id, laps=3)

    event_letsgo_v4 = _seed_event(
        db, event_id=42, series_id=series_letsgo.id, sequence_number=4,
        terrain_type=TerrainType.trocha, technical_difficulty=5,
    )
    variant_letsgo = _seed_variant(db, variant_id=42, race_event_id=event_letsgo_v4.id, lap_distance_m=6000)
    _seed_setup(db, race_event_id=event_letsgo_v4.id, category_id=category.id, variant_id=variant_letsgo.id, laps=2)

    await db.commit()

    result_valle = await fetch_course_context(db, _SEASON, [4], category.id, series_id=series_valle.id)
    assert result_valle[4]["lap_distance_m"] == 4200
    assert result_valle[4]["laps"] == 3

    result_letsgo = await fetch_course_context(db, _SEASON, [4], category.id, series_id=series_letsgo.id)
    assert result_letsgo[4]["lap_distance_m"] == 6000
    assert result_letsgo[4]["laps"] == 2


async def test_fetch_course_context_without_series_id_behaviour_unchanged(db: AsyncSession):
    """Sin ``series_id`` la ambigüedad entre las dos copas en V4 preexiste:
    solo se afirma que se resuelve UNA entrada, NUNCA cuál copa "gana"."""
    _seed_coach(db)
    series_valle = _seed_series(db, series_id=1, season=_SEASON)
    series_letsgo = RaceSeries(
        id=2,
        name="Copa Let's Go Ficticia",
        season_year=_SEASON,
        organizer="Liga Ficticia",
        points_scheme_code="copa_ficticia_test",
    )
    db.add(series_letsgo)
    category = _seed_category(db, category_id=10, code="PJUV_A")

    event_valle_v4 = _seed_event(db, event_id=41, series_id=series_valle.id, sequence_number=4)
    variant_valle = _seed_variant(db, variant_id=41, race_event_id=event_valle_v4.id, lap_distance_m=4200)
    _seed_setup(db, race_event_id=event_valle_v4.id, category_id=category.id, variant_id=variant_valle.id, laps=3)

    event_letsgo_v4 = _seed_event(db, event_id=42, series_id=series_letsgo.id, sequence_number=4)
    variant_letsgo = _seed_variant(db, variant_id=42, race_event_id=event_letsgo_v4.id, lap_distance_m=6000)
    _seed_setup(db, race_event_id=event_letsgo_v4.id, category_id=category.id, variant_id=variant_letsgo.id, laps=2)

    await db.commit()

    result = await fetch_course_context(db, _SEASON, [4], category.id)
    assert set(result.keys()) == {4}
    assert result[4]["lap_distance_m"] in (4200, 6000)


# ---------------------------------------------------------------------------
# 1c. fetch_course_context_by_event
# ---------------------------------------------------------------------------


async def test_fetch_course_context_by_event_keys_both_events_no_course_notes(
    db: AsyncSession,
):
    _seed_coach(db)
    series = _seed_series(db)
    category = _seed_category(db, category_id=10, code="PJUV_A")
    other_category = _seed_category(db, category_id=11, code="PJUV_B")

    event1 = _seed_event(
        db, event_id=1, series_id=series.id, sequence_number=1,
        course_notes="Estudiante Ficticio Uno — dato ficticio",
        terrain_type=TerrainType.mixto, technical_difficulty=4,
    )
    variant1 = _seed_variant(db, variant_id=1, race_event_id=event1.id, lap_distance_m=4200)
    _seed_setup(db, race_event_id=event1.id, category_id=category.id, variant_id=variant1.id, laps=3)

    # event2 solo tiene setup para la OTRA categoría -> entrada {} para la pedida.
    event2 = _seed_event(db, event_id=2, series_id=series.id, sequence_number=2)
    variant2 = _seed_variant(db, variant_id=2, race_event_id=event2.id)
    _seed_setup(db, race_event_id=event2.id, category_id=other_category.id, variant_id=variant2.id, laps=2)

    await db.commit()

    # event_id 999: no existe -> {}.
    result = await fetch_course_context_by_event(db, [event1.id, event2.id, 999], category.id)

    assert set(result.keys()) == {event1.id, event2.id, 999}
    assert result[event1.id]["lap_distance_m"] == 4200
    assert "course_notes" not in result[event1.id]
    assert result[event2.id] == {}
    assert result[999] == {}


async def test_fetch_course_context_by_event_none_category_all_empty(db: AsyncSession):
    _seed_coach(db)
    series = _seed_series(db)
    event1 = _seed_event(db, event_id=1, series_id=series.id, sequence_number=1)
    await db.commit()

    result = await fetch_course_context_by_event(db, [event1.id], None)
    assert result == {event1.id: {}}


# ---------------------------------------------------------------------------
# 2. format_course_meta
# ---------------------------------------------------------------------------


def test_format_course_meta_empty_dict_is_none():
    assert format_course_meta({}) is None


def test_format_course_meta_none_is_none():
    assert format_course_meta(None) is None


def test_format_course_meta_partial_only_description_fields_no_distance_or_laps():
    course = {
        "lap_distance_m": None,
        "elevation_gain_m": None,
        "laps": None,
        "terrain_type": "mixto",
        "technical_difficulty": 4,
        "key_sectors": None,
    }
    text = format_course_meta(course)
    assert text is not None
    assert "- Tipo de superficie: mixto" in text
    assert "- Dificultad técnica: 4/5 (técnico)" in text
    assert "Distancia por vuelta" not in text
    assert "Desnivel positivo" not in text
    assert "Vueltas de la categoría" not in text
    assert "Sectores clave" not in text
    assert text.count("\n") == 1  # exactamente dos bullets


def test_format_course_meta_every_field_present_matches_contract_worked_example():
    """Ejemplo resuelto del contrato §2 — comas decimales, seis bullets."""
    course = {
        "lap_distance_m": 4200,
        "elevation_gain_m": 110,
        "laps": 3,
        "terrain_type": "mixto",
        "technical_difficulty": 4,
        "key_sectors": ["subida_larga", "rock_garden"],
    }
    text = format_course_meta(course)
    assert text is not None
    assert "- Distancia por vuelta: 4,2 km" in text
    assert "- Desnivel positivo por vuelta: 110 m" in text
    assert "- Vueltas de la categoría: 3 (distancia total 12,6 km)" in text
    assert "- Tipo de superficie: mixto" in text
    assert "- Dificultad técnica: 4/5 (técnico)" in text
    assert "- Sectores clave: subida larga, rock garden" in text
    assert text.count("\n") == 5  # exactamente seis bullets, ni uno más


# ---------------------------------------------------------------------------
# 3. Prompts v3 (per-válida + temporada) — patrón de test_prompt_v3_blocks.py
# ---------------------------------------------------------------------------


def render(input_: AnalystV3Input, name: str) -> str:
    context = RaceAnalystAgent()._build_v3_context(input_)
    return render_prompt(name, context, strict=True)


def test_analyst_v3_prompt_shows_registered_course_block_when_present():
    text = render(
        AnalystV3Input(valida_num=4, course_meta="- Distancia por vuelta: 4,2 km"),
        PROMPT_VERSION_ANALYST_V3,
    )
    assert "Circuito registrado" in text


def test_analyst_v3_prompt_shows_sin_dato_veto_when_course_meta_absent():
    text = render(AnalystV3Input(valida_num=4), PROMPT_VERSION_ANALYST_V3)
    assert "Circuito — SIN DATO" in text
    assert "PROHIBIDO mencionar distancia" in text


def test_analyst_v3_conditions_veto_does_not_forbid_course_vocabulary():
    """Sin condiciones y con circuito: el veto de condiciones no puede prohibir
    las palabras que el bloque de circuito imprime unas líneas más abajo."""
    text = render(
        AnalystV3Input(valida_num=4, course_meta="- Tipo de superficie: mixto"),
        PROMPT_VERSION_ANALYST_V3,
    )
    veto_start = text.index("## Condiciones registradas — SIN DATO")
    veto = text[veto_start : text.index("## Circuito registrado", veto_start)]
    assert "PROHIBIDO mencionar clima" in veto
    assert "terreno" not in veto.lower()
    assert "superficie" not in veto.lower()
    assert "- Tipo de superficie: mixto" in text


def test_season_v3_prompt_shows_registered_course_block_when_present():
    """NOTA (T046, escrito antes de que aterricen T047-049 — actualizado en T050b):

    El contrato (``ai-course-block.md`` §2) dejaba abierto EXACTAMENTE cómo el
    resumen de temporada transporta el circuito por-válida ("un
    ``course_block`` por válida... o un nuevo mapping ``course_by_valida`` —
    elección del implementador, documentada en el header del prompt"). T049
    optó por el mapping ``course_by_valida`` (``_build_v3_context`` expone
    ``input_.course_by_valida or {}`` bajo esa clave, separada de
    ``course_block`` que solo alimenta el analyst por-válida) y T050b agregó
    a ``race_season_summary_v3.md`` una sección propia ("## Circuitos
    registrados por válida") que itera ese mapping — distinta del bloque
    singular "## Circuito registrado" del prompt por-válida.

    NOTA 2 (hotfix multicopa): ``course_by_valida`` pasó de estar keyed por
    número de válida a estar keyed por ETIQUETA con copa (dos copas de la
    misma temporada pueden compartir "Válida 4" — un dict int-keyed
    perdería una de las dos, ver plans/multicopa-identidad-valida.md).
    """
    text = render(
        AnalystV3Input(
            valida_num=0,
            analysis_kind="season",
            course_by_valida={"Copa Valle · Válida IV": "- Distancia por vuelta: 4,2 km"},
        ),
        PROMPT_VERSION_SEASON_SUMMARY_V3,
    )
    assert "Circuitos registrados por válida" in text
    assert "**Copa Valle · Válida IV:**" in text
    assert "- Distancia por vuelta: 4,2 km" in text


def test_season_v3_prompt_shows_sin_dato_veto_when_course_meta_absent():
    text = render(
        AnalystV3Input(valida_num=0, analysis_kind="season"),
        PROMPT_VERSION_SEASON_SUMMARY_V3,
    )
    assert "Circuitos — SIN DATO" in text
    assert "PROHIBIDO mencionar distancia" in text


# ---------------------------------------------------------------------------
# 4. race_analyst_v2 no se rompe con las claves de contexto nuevas
# ---------------------------------------------------------------------------


def _minimal_v2_input() -> AnalysisInput:
    return AnalysisInput(
        athlete_pseudonym="AzulZorro",
        age=13,
        ltad_group=LTADGroup.JUVENIL,
        athlete_id=1,
        season=_SEASON,
    )


def test_race_analyst_v2_per_valida_still_renders_with_course_keys_added():
    """v2 usa ``strict=False`` (``ChainableUndefined``): una clave de más en
    el contexto nunca revienta el render — Jinja solo falla en modo strict
    por variables USADAS y no definidas, jamás por claves sin usar."""
    agent = RaceAnalystAgent()
    context = agent._build_v2_context(_minimal_v2_input(), valida_num=4)
    context["course_block"] = "- Distancia por vuelta: 4,2 km"
    text = render_prompt("race_analyst_v2", context, strict=False)
    assert text
    assert "course_block" not in text  # el template v2 no referencia esta clave


def test_race_analyst_v2_season_summary_still_renders_with_course_keys_added():
    agent = RaceAnalystAgent()
    context = agent._build_v2_context(_minimal_v2_input(), valida_num=0, is_season_summary=True)
    context["course_block"] = None
    text = render_prompt("race_analyst_v2", context, strict=False)
    assert text


# ---------------------------------------------------------------------------
# 5. "End-to-end" simplificado (sin LLM/grafo) — ver reporte de T046
# ---------------------------------------------------------------------------


async def test_end_to_end_course_present_vs_absent_changes_the_rendered_prompt(
    db: AsyncSession,
):
    """Sustituto simplificado del end-to-end con FakeLLM del contrato §5:
    encadena ``fetch_course_context`` + ``format_course_meta`` +
    ``render_prompt`` sin invocar el grafo ni ningún proveedor — cubre el
    reclamo esencial ("una válida con datos de circuito produce un prompt
    distinto de una sin ellos") sin el costo de montar un run completo.
    """
    _seed_coach(db)
    series = _seed_series(db)
    category = _seed_category(db, category_id=10, code="PJUV_A")

    event_with = _seed_event(
        db, event_id=1, series_id=series.id, sequence_number=1,
        terrain_type=TerrainType.mixto, technical_difficulty=4,
        key_sectors=["subida_larga", "rock_garden"],
    )
    variant = _seed_variant(
        db, variant_id=1, race_event_id=event_with.id, lap_distance_m=4200, elevation_gain_m=110
    )
    _seed_setup(db, race_event_id=event_with.id, category_id=category.id, variant_id=variant.id, laps=3)

    _seed_event(db, event_id=2, series_id=series.id, sequence_number=2)  # sin setup de circuito

    await db.commit()

    course_ctx = await fetch_course_context(db, _SEASON, [1, 2], category.id)

    text_present = render(
        AnalystV3Input(valida_num=1, course_meta=format_course_meta(course_ctx[1])),
        PROMPT_VERSION_ANALYST_V3,
    )
    text_absent = render(
        AnalystV3Input(valida_num=2, course_meta=format_course_meta(course_ctx[2])),
        PROMPT_VERSION_ANALYST_V3,
    )

    assert "Circuito registrado" in text_present
    assert "4,2 km" in text_present
    assert "Circuito — SIN DATO" in text_absent
    assert "PROHIBIDO mencionar distancia" in text_absent
    assert text_present != text_absent


# ---------------------------------------------------------------------------
# 5. Verdad de campo del critic v3 — mismo circuito que vio el analista
# ---------------------------------------------------------------------------

_COURSE_ENTRY = {
    "lap_distance_m": 4200,
    "elevation_gain_m": 110,
    "laps": 3,
    "terrain_type": "mixto",
    "technical_difficulty": 4,
    "key_sectors": ["subida_larga"],
}


def test_critic_ground_truth_v3_includes_registered_course():
    from app.services.race.ai.nodes.critic_agent import _build_ground_truth

    state = {"course_context": {4: _COURSE_ENTRY}}
    text = _build_ground_truth(state, 4, include_course=True)
    assert "### Circuito registrado" in text
    assert "- Distancia por vuelta: 4,2 km" in text
    assert "- Tipo de superficie: mixto" in text


def test_critic_ground_truth_v3_declares_absent_course():
    from app.services.race.ai.nodes.critic_agent import _build_ground_truth

    text = _build_ground_truth({"course_context": {4: None}}, 4, include_course=True)
    assert "### Circuito registrado\nsin circuito registrado" in text


def test_critic_ground_truth_default_excludes_course_for_v2():
    from app.services.race.ai.nodes.critic_agent import _build_ground_truth

    text = _build_ground_truth({"course_context": {4: _COURSE_ENTRY}}, 4)
    assert "Circuito registrado" not in text
    assert "Tipo de superficie" not in text


def test_critic_ground_truth_season_lists_course_per_valida():
    from app.services.race.ai.nodes.critic_agent import _build_ground_truth

    state = {
        "analysis_kind": "season",
        "course_context": {3: _COURSE_ENTRY, 5: None},
    }
    text = _build_ground_truth(state, 0, include_course=True)
    assert "Válida 3:\n- Distancia por vuelta: 4,2 km" in text
    assert "Válida 5:" not in text
    assert "sin circuito registrado" not in text


def test_critic_ground_truth_never_prints_course_notes():
    from app.services.race.ai.nodes.critic_agent import _build_ground_truth

    entry = {**_COURSE_ENTRY, "course_notes": "texto libre del coach"}
    text = _build_ground_truth({"course_context": {4: entry}}, 4, include_course=True)
    assert "texto libre del coach" not in text
