"""T027 — categorías propias de temporada, invisibles fuera de su temporada
(feature 044, US2). Contrato: ``category-mapping.md`` ("Read paths") y
``research.md`` R-03 ("season-specific codes absent from every current
selector").

Alcance: identificar las fuentes de selección/validación de categorías de la
temporada corriente y probar, una por una, si ya filtran ``is_active``:

1. **Setups de recorrido** (feature 043, ``PUT .../course/setups``) — YA
   filtra (``course/service.py::replace_setups``, línea ~651). Test de
   regresión — debe pasar HOY.
2. **Filtros de resultados / clasificación** (``GET .../results``,
   ``GET .../standings``, query param ``category_id``) — NO tienen un filtro
   explícito ``is_active``, pero no lo necesitan: ambos derivan la lista de
   categorías exclusivamente de ``RaceResult.category_id`` con join a
   ``race_categories``, nunca de un ``SELECT`` independiente sobre el
   catálogo completo. Una categoría propia de temporada sólo puede aparecer
   si existe un ``race_result`` real que la usa — y eso únicamente pasa en
   la válida histórica a la que pertenece. Agregar un filtro ``is_active``
   aquí sería INCORRECTO: ocultaría datos legítimos de las temporadas
   2024/2025. Tests de regresión que prueban las dos direcciones (temporada
   corriente: nunca aparece; temporada histórica dueña del dato: si
   aparece) — deben pasar HOY.
3. **Ingesta / asistente de importación** (``RaceIngestor.ingest_event``,
   llamado por ``POST /commit``) — éste SÍ es el hallazgo: `_load_category_cache`
   (``app/services/race/ingestor.py``) hace ``select(RaceCategory)`` sin
   filtro alguno, y el loop de RESULTADOS acepta cualquier code conocido del
   catálogo — activo o no — sin generar ni una advertencia. Para una carga
   histórica (2024/2025) esto es necesario (R-12: el mismo staging de
   histórico pasa por este mismo ingestor). Pero HOY nada distingue esa
   carga histórica de un import de temporada corriente que, por un header
   mal escrito o un archivo re-subido por error, resuelva a un code
   ``is_active=False`` — se ingesta en silencio, sin ninguna señal, igual
   que ``INF_A`` o cualquier categoría 2026 real. Test que lo demuestra
   fallando abajo.

Privacidad: nombres ficticios ("Ana Ficticia", "Leo Ficticio").
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.race_category import CategoryGender, CategoryTier, RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_event import RaceEvent, RaceEventStatus, SurfaceCondition
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole
from app.schemas.race import EventMeta
from app.services.race.ingestor import RaceIngestor
from app.services.race.pdf_parser import ResultsRow
from tests.helpers.audit_tables import AUDIT_TABLES
from tests.helpers.gpx_builder import circle_gpx

_BASE = "/api/race-analysis/race-events"


def _course_url(event_id: int, suffix: str = "") -> str:
    return f"{_BASE}/{event_id}/course{suffix}"


def _gpx_files(content: bytes) -> dict:
    return {"file": ("recorrido.gpx", content, "application/gpx+xml")}


# ---------------------------------------------------------------------------
# Catálogo — un code activo 2026 + los tres codes propios de temporada
# (mismos valores que ``scripts/seed_race_categories.py``, feature 044).
# ---------------------------------------------------------------------------

CAT_ACTIVE_ID = 1  # INF_A, 2026, is_active=True
CAT_MAS_B_2025_ID = 2  # is_active=False
CAT_MAS_C_2025_ID = 3  # is_active=False
CAT_PRE_F_U_ID = 4  # is_active=False


def _make_user(role: UserRole, user_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"{role.value}{user_id}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


def _seed_categories() -> list[RaceCategory]:
    return [
        RaceCategory(
            id=CAT_ACTIVE_ID, code="INF_A", label="Infantil A",
            sex=CategoryGender.M, age_min=9, age_max=10,
            tier=CategoryTier.menores, sort_order=30, is_active=True,
        ),
        RaceCategory(
            id=CAT_MAS_B_2025_ID, code="MAS_B_2025", label="Máster B (2025)",
            sex=CategoryGender.M, age_min=None, age_max=None,
            tier=CategoryTier.master, sort_order=86, is_active=False,
        ),
        RaceCategory(
            id=CAT_MAS_C_2025_ID, code="MAS_C_2025", label="Máster C (2025)",
            sex=CategoryGender.M, age_min=None, age_max=None,
            tier=CategoryTier.master, sort_order=87, is_active=False,
        ),
        RaceCategory(
            id=CAT_PRE_F_U_ID, code="PRE_F_U",
            label="Preinfantil femenino (grupo único)",
            sex=CategoryGender.F, age_min=6, age_max=8,
            tier=CategoryTier.menores, sort_order=24, is_active=False,
        ),
    ]


# ===========================================================================
# 1. Setups de recorrido (feature 043) — YA filtra is_active. Regresión.
# ===========================================================================


@pytest_asyncio.fixture
async def course_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "race_series",
            "race_events",
            "race_categories",
            "race_course_variants",
            "race_course_category_setups",
            *AUDIT_TABLES,
        )
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def course_session_factory(course_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(course_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def course_coach_client(course_session_factory):
    async with course_session_factory() as s:
        coach = User(
            id=10, email="coach@test.com", hashed_password="x",
            first_name="Coach", last_name="Diez", role=UserRole.coach,
            is_active=True, can_login=True, created_at=datetime.now(timezone.utc),
        )
        series = RaceSeries(
            id=1, name="Copa Valle de Ciclomontañismo", season_year=2026,
            organizer="Liga", points_scheme_code="copa_valle_2026",
        )
        event = RaceEvent(
            id=100, series_id=1, sequence_number=4, name="VALIDA IV CALI",
            event_date=date(2026, 5, 17), location="CALI",
            is_championship=False, status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
        )
        s.add_all([coach, series, event, *_seed_categories()])
        await s.commit()

    async def _override_db():
        async with course_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.coach, 10)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    app.dependency_overrides.clear()


class TestCourseSetupsRejectsInactiveCategory:
    """Ya implementado (``course/service.py`` línea ~651) — confirma que NO
    hay regresión, no es el hallazgo de este archivo."""

    @pytest.mark.asyncio
    async def test_put_setups_with_season_specific_category_returns_422(
        self, course_coach_client
    ):
        content = circle_gpx(radius_m=640, points=800, laps=1)
        upload = await course_coach_client.post(
            _course_url(100, "/variants"),
            data={"label": "Circuito completo"},
            files=_gpx_files(content),
        )
        assert upload.status_code == 201, upload.text
        variant_id = upload.json()["variants"][0]["id"]

        r = await course_coach_client.put(
            _course_url(100, "/setups"),
            json={
                "setups": [
                    {
                        "category_id": CAT_MAS_B_2025_ID,
                        "laps": 3,
                        "variant_id": variant_id,
                    }
                ]
            },
        )
        assert r.status_code == 422, r.text
        assert r.json()["detail"]["code"] == "unknown_category"

    @pytest.mark.asyncio
    async def test_put_setups_with_active_category_still_works(
        self, course_coach_client
    ):
        """Sanity check del fixture: una categoría activa SÍ pasa — si esto
        fallara, el 422 de arriba no probaría nada (podría ser cualquier
        otro error de validación)."""
        content = circle_gpx(radius_m=640, points=800, laps=1)
        upload = await course_coach_client.post(
            _course_url(100, "/variants"),
            data={"label": "Circuito completo"},
            files=_gpx_files(content),
        )
        variant_id = upload.json()["variants"][0]["id"]

        r = await course_coach_client.put(
            _course_url(100, "/setups"),
            json={
                "setups": [
                    {"category_id": CAT_ACTIVE_ID, "laps": 3, "variant_id": variant_id}
                ]
            },
        )
        assert r.status_code == 200, r.text


# ===========================================================================
# 2. Filtros de resultados / clasificación — correctos por construcción.
# ===========================================================================


@pytest_asyncio.fixture
async def results_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "race_series",
            "race_events",
            "race_categories",
            "race_competitors",
            "race_results",
            # get_event_results (results_read.py) SIEMPRE corre una query de
            # setups de recorrido (contrato feature 043: "+1 statement" fijo,
            # sin importar si hay datos de circuito) — sin estas dos tablas
            # el SELECT falla con "no such table", aunque este test no toca
            # circuitos en absoluto.
            "race_course_variants",
            "race_course_category_setups",
            *AUDIT_TABLES,
        )
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def results_session_factory(results_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(results_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def results_coach_client(results_session_factory):
    """Sembrado con DOS válidas: 100 (temporada 2026, corriente — SIN
    resultados en categorías propias de temporada) y 200 (temporada 2025,
    histórica — CON un resultado real en ``MAS_B_2025``, la categoría
    propia de esa temporada)."""
    async with results_session_factory() as s:
        coach = User(
            id=10, email="coach@test.com", hashed_password="x",
            first_name="Coach", last_name="Diez", role=UserRole.coach,
            is_active=True, can_login=True, created_at=datetime.now(timezone.utc),
        )
        series_2026 = RaceSeries(
            id=1, name="Copa Valle de Ciclomontañismo", season_year=2026,
            organizer="Liga", points_scheme_code="copa_valle_2026",
        )
        series_2025 = RaceSeries(
            id=2, name="Copa Valle de Ciclomontañismo", season_year=2025,
            organizer="Liga", points_scheme_code="copa_valle_2025",
        )
        event_current = RaceEvent(
            id=100, series_id=1, sequence_number=4, name="VALIDA IV CALI 2026",
            event_date=date(2026, 5, 17), location="CALI",
            is_championship=False, status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
        )
        event_historical = RaceEvent(
            id=200, series_id=2, sequence_number=3, name="VALIDA III CALI 2025",
            event_date=date(2025, 4, 12), location="CALI",
            is_championship=False, status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
        )
        competitor_current = RaceCompetitor(
            id=1, normalized_name="ana ficticia", display_name="Ana Ficticia",
            club_text="Club Trocha y Ruta",
        )
        competitor_historical = RaceCompetitor(
            id=2, normalized_name="leo ficticio", display_name="Leo Ficticio",
            club_text="Otro Club",
        )
        result_current = RaceResult(
            id=1, event_id=100, category_id=CAT_ACTIVE_ID, competitor_id=1,
            bib_number=501, position=1, status=ResultStatus.FINISHED,
            race_time_ms=1_200_000, points_awarded=40, created_by_user_id=10,
        )
        result_historical = RaceResult(
            id=2, event_id=200, category_id=CAT_MAS_B_2025_ID, competitor_id=2,
            bib_number=42, position=1, status=ResultStatus.FINISHED,
            race_time_ms=1_500_000, points_awarded=40, created_by_user_id=10,
        )
        s.add_all(
            [
                coach, series_2026, series_2025, event_current, event_historical,
                *_seed_categories(),
                competitor_current, competitor_historical,
                result_current, result_historical,
            ]
        )
        await s.commit()

    async def _override_db():
        async with results_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.coach, 10)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    app.dependency_overrides.clear()


class TestResultsFilterNeverLeaksSeasonSpecificIntoCurrentSeason:
    @pytest.mark.asyncio
    async def test_current_season_event_filtered_by_season_specific_category_is_empty(
        self, results_coach_client
    ):
        """La válida 2026 no tiene NINGÚN resultado en MAS_B_2025 — filtrar
        por ese ``category_id`` da lista vacía, no un error ni un leak."""
        r = await results_coach_client.get(
            f"{_BASE}/100/results", params={"category_id": CAT_MAS_B_2025_ID}
        )
        assert r.status_code == 200, r.text
        assert r.json()["categories"] == []

    @pytest.mark.asyncio
    async def test_historical_event_that_owns_the_season_specific_category_shows_it(
        self, results_coach_client
    ):
        """La válida 2025 SÍ corrió MAS_B_2025 — debe seguir siendo visible
        para su propia temporada histórica; un filtro ``is_active`` aquí
        rompería esto."""
        r = await results_coach_client.get(
            f"{_BASE}/200/results", params={"category_id": CAT_MAS_B_2025_ID}
        )
        assert r.status_code == 200, r.text
        categories = r.json()["categories"]
        assert len(categories) == 1
        assert categories[0]["code"] == "MAS_B_2025"
        assert len(categories[0]["rows"]) == 1


class TestStandingsFilterNeverLeaksSeasonSpecificIntoCurrentSeason:
    @pytest.mark.asyncio
    async def test_current_season_event_filtered_by_season_specific_category_is_empty(
        self, results_coach_client
    ):
        r = await results_coach_client.get(
            f"{_BASE}/100/standings", params={"category_id": CAT_MAS_B_2025_ID}
        )
        assert r.status_code == 200, r.text
        assert r.json()["categories"] == []

    @pytest.mark.asyncio
    async def test_historical_event_that_owns_the_season_specific_category_shows_it(
        self, results_coach_client
    ):
        r = await results_coach_client.get(
            f"{_BASE}/200/standings", params={"category_id": CAT_MAS_B_2025_ID}
        )
        assert r.status_code == 200, r.text
        categories = r.json()["categories"]
        assert len(categories) == 1
        assert categories[0]["code"] == "MAS_B_2025"


# ===========================================================================
# 3. Ingesta (RaceIngestor, camino de POST /commit) — EL HALLAZGO.
# ===========================================================================


@pytest_asyncio.fixture
async def ingest_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "race_series",
            "race_events",
            "race_categories",
            "race_competitors",
            "race_results",
            "race_imports",
            # El ingestor resuelve la identidad por firma (feature 044, US4).
            "race_competitor_signatures",
            "race_identity_candidates",
            *AUDIT_TABLES,
        )
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def ingest_session_factory(ingest_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(ingest_engine, expire_on_commit=False)


class TestIngestSilentlyAcceptsSeasonSpecificCategoryForCurrentSeason:
    """HALLAZGO T027: ``RaceIngestor.ingest_event`` — el camino real detrás de
    ``POST /commit`` del asistente de importación — resuelve categorías por
    code sin distinguir activo/inactivo (``ingestor.py::_load_category_cache``
    hace ``select(RaceCategory)`` sin ``WHERE``). Para un import de
    TEMPORADA CORRIENTE (``meta.season=2026``) que por cualquier motivo
    (header mal escrito, archivo histórico re-subido por error) resuelva a
    un code propio de temporada (``MAS_B_2025``), hoy no se genera ninguna
    advertencia — se trata exactamente igual que una categoría 2026
    legítima. El contrato de ``category-mapping.md`` exige lo contrario:
    "Current-season selectors filter is_active = true". Bloquear del todo
    (igual que una categoría desconocida) rompería la carga histórica
    legítima (R-12 reusa este mismo ingestor para 2024/2025) — por eso este
    test pide sólo el mínimo defendible: AL MENOS una advertencia, en la
    misma línea que ``tiempo_anomalo``. No es un test contra T030 en sí —
    T030 no está en el scope de esta tarea — pero documenta el hueco para
    que T030 lo cierre con el criterio que decida (advertencia, bloqueo, o
    un flag explícito de "carga histórica" en la firma del ingestor)."""

    @pytest.mark.asyncio
    async def test_no_warning_emitted_today_for_season_specific_category_in_current_season(
        self, ingest_session_factory
    ):
        async with ingest_session_factory() as db:
            coach = User(
                id=10, email="coach@test.com", hashed_password="x",
                first_name="Coach", last_name="Diez", role=UserRole.coach,
                is_active=True, can_login=True, created_at=datetime.now(timezone.utc),
            )
            db.add(coach)
            db.add_all(_seed_categories())
            await db.commit()

            meta = EventMeta(
                season=2026,
                valida_num=4,
                name="Valida 4",
                event_date=date(2026, 5, 17),
                location="Cali",
                climate=None,
                temperature_c=Decimal("25.0"),
                surface_condition=SurfaceCondition.seca,
            )
            row = ResultsRow(
                position=1, bib="900", name="Ana Ficticia", city="Yumbo",
                club="Club Trocha y Ruta", time_raw="0:40:00", points=40,
            )

            ingestor = RaceIngestor(db)
            report = await ingestor.ingest_event(
                meta=meta,
                # "MAS_B_2025" no puede salir de un header 2026 legítimo —
                # simula el escenario de riesgo (re-subida por error /
                # mapeo incorrecto) sin necesitar el parser PDF completo.
                results_by_category={"MAS_B_2025": [row]},
                ingested_by_user_id=10,
            )

            # Comportamiento actual: se ingesta igual que cualquier
            # categoría activa, sin ninguna señal.
            assert report.results_inserted == 1
            persisted = (
                await db.execute(
                    select(RaceResult).where(RaceResult.category_id == CAT_MAS_B_2025_ID)
                )
            ).scalar_one()
            assert persisted.event_id is not None

            # Hallazgo: se esperaría al menos una advertencia — hoy no hay
            # ninguna. Este assert debe FALLAR hasta que T030 (o una tarea
            # de seguimiento) decida cómo señalizar el caso.
            assert report.warnings, (
                "RaceIngestor.ingest_event no genera ninguna advertencia al "
                "ingestar una categoría propia de temporada (is_active=False) "
                "para un evento de temporada corriente (season=2026). Ver "
                "docstring de esta clase — hallazgo T027, pendiente de T030."
            )
