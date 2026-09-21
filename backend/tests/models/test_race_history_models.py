"""Tests T005 — modelos del histórico de resultados (feature 044).

Escrito en TDD contra el contrato (`specs/044-race-history-backfill/data-model.md`
§1-4), no contra el código: `RaceCompetitorSignature`/`RaceIdentityCandidate`
(T007) y las columnas nuevas de `race_results` (T006) todavía no existían al
momento de redactar este archivo. Por una carrera de tareas en paralelo
(T006/T007 corrieron a la vez que T005), los modelos ya estaban en el árbol
al primer `pytest`; los nombres de enum reales (`IdentityCandidateKind`,
`IdentityCandidateState` — sin el prefijo `Race`) se ajustaron una vez
confirmados contra `app/models/race_identity_candidate.py`. El resto del
archivo — nombres de tabla, columnas, constraints — coincidió con el
contrato sin cambios.

Cubre:
  1. `race_results.category_label_raw` / `category_age_min_raw` /
     `category_age_max_raw` — nullable; insertables en NULL y con valor
     (data-model.md §1).
  2. `race_competitors` — dos filas pueden compartir `normalized_name` (el
     UNIQUE se elimina, ver invariante 2); `city_text` existe y es nullable
     (data-model.md §2).
  3. `race_competitor_signatures` — UNIQUE(normalized_name, club_norm,
     city_norm), incluido el caso crítico club_norm/city_norm = '' (por qué
     es crítico: son `NOT NULL DEFAULT ''` precisamente porque MySQL trata
     dos `NULL` como valores distintos en una unique key, lo que anularía la
     protección); dos firmas que solo difieren en `city_norm` conviven;
     `first_season`/`last_season` persisten (data-model.md §3).
  4. `race_identity_candidates` — `pair_hash` único; `state` por defecto
     `pending`; los enums `kind`/`state` guardan sus valores string (no el
     nombre del miembro Python); los campos JSON `left_record`/`right_record`/
     `signals` hacen round-trip (data-model.md §4).

SQLite async in-memory + StaticPool — mismo patrón que
`tests/models/test_strava_models.py`.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.race_category import CategoryGender, RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_competitor_signature import RaceCompetitorSignature
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_identity_candidate import (
    IdentityCandidateKind,
    IdentityCandidateState,
    RaceIdentityCandidate,
)
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole

_TABLES = [
    "users",
    "race_series",
    "race_categories",
    "race_events",
    "race_competitors",
    "race_results",
    "race_identity_candidates",
    "race_competitor_signatures",
]


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(sqlite_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Helpers de seed — fixtures ficticias, nunca datos reales de atletas del club
# ---------------------------------------------------------------------------


async def _seed_coach(session: AsyncSession, *, email: str = "coach1@ficticio.test") -> User:
    coach = User(
        email=email,
        hashed_password="x",
        first_name="Coach",
        last_name="Ficticio",
        role=UserRole.coach,
        is_active=True,
        can_login=True,
        created_at=datetime.now(timezone.utc),
    )
    session.add(coach)
    await session.flush()
    return coach


async def _seed_series(session: AsyncSession, coach: User) -> RaceSeries:
    series = RaceSeries(
        name="Copa Valle Ficticia 2025",
        season_year=2025,
        organizer="Liga Ficticia de Ciclismo",
        points_scheme_code="copa_valle_2025",
        created_by_user_id=coach.id,
    )
    session.add(series)
    await session.flush()
    return series


async def _seed_category(session: AsyncSession, *, code: str = "PJUV_A_F") -> RaceCategory:
    category = RaceCategory(
        code=code,
        label="Pre Juvenil A Femenino",
        sex=CategoryGender.F,
        age_min=13,
        age_max=14,
    )
    session.add(category)
    await session.flush()
    return category


async def _seed_event(
    session: AsyncSession, series: RaceSeries, coach: User, *, sequence_number: int = 1
) -> RaceEvent:
    event = RaceEvent(
        series_id=series.id,
        sequence_number=sequence_number,
        name="Válida I Ficticia",
        event_date=date(2025, 3, 1),
        status=RaceEventStatus.COMPLETED,
        created_by_user_id=coach.id,
    )
    session.add(event)
    await session.flush()
    return event


async def _seed_competitor(
    session: AsyncSession, *, normalized_name: str, display_name: str
) -> RaceCompetitor:
    competitor = RaceCompetitor(
        normalized_name=normalized_name,
        display_name=display_name,
    )
    session.add(competitor)
    await session.flush()
    return competitor


# ---------------------------------------------------------------------------
# 1. race_results — columnas congeladas (category_label_raw + age_min/max_raw)
# ---------------------------------------------------------------------------


class TestRaceResultFrozenColumns:
    @pytest.mark.asyncio
    async def test_category_label_and_age_raw_nullable(self, session_factory):
        """Un resultado se puede insertar sin los campos congelados (NULL)."""
        async with session_factory() as session:
            coach = await _seed_coach(session)
            series = await _seed_series(session, coach)
            category = await _seed_category(session)
            event = await _seed_event(session, series, coach)
            competitor = await _seed_competitor(
                session,
                normalized_name="juan perez ficticio",
                display_name="Juan Pérez Ficticio",
            )
            await session.commit()

            result = RaceResult(
                event_id=event.id,
                category_id=category.id,
                competitor_id=competitor.id,
                status=ResultStatus.DNS,
                created_by_user_id=coach.id,
            )
            session.add(result)
            await session.commit()
            await session.refresh(result)

            assert result.category_label_raw is None
            assert result.category_age_min_raw is None
            assert result.category_age_max_raw is None

    @pytest.mark.asyncio
    async def test_category_label_and_age_raw_store_value(self, session_factory):
        """Con valor: el snapshot congelado persiste tal como fue escrito al insertar."""
        async with session_factory() as session:
            coach = await _seed_coach(session)
            series = await _seed_series(session, coach)
            category = await _seed_category(session)
            event = await _seed_event(session, series, coach)
            competitor = await _seed_competitor(
                session,
                normalized_name="maria lopez ficticia",
                display_name="María López Ficticia",
            )
            await session.commit()

            result = RaceResult(
                event_id=event.id,
                category_id=category.id,
                competitor_id=competitor.id,
                status=ResultStatus.DNS,
                created_by_user_id=coach.id,
                category_label_raw="PRE JUVENIL A FEMENINO",
                category_age_min_raw=13,
                category_age_max_raw=14,
            )
            session.add(result)
            await session.commit()
            await session.refresh(result)

            assert result.category_label_raw == "PRE JUVENIL A FEMENINO"
            assert result.category_age_min_raw == 13
            assert result.category_age_max_raw == 14


# ---------------------------------------------------------------------------
# 2. race_competitors — normalized_name compartido + city_text
# ---------------------------------------------------------------------------


class TestRaceCompetitorSharedNormalizedName:
    @pytest.mark.asyncio
    async def test_two_competitors_can_share_normalized_name(self, session_factory):
        """El UNIQUE de `normalized_name` se reemplaza por un índice no único
        (invariante 2): dos personas distintas con el mismo nombre normalizado
        coexisten como dos filas separadas."""
        async with session_factory() as session:
            comp1 = RaceCompetitor(
                normalized_name="juan perez",
                display_name="Juan Pérez Ficticio",
                club_text="Club Andino Ficticio",
            )
            comp2 = RaceCompetitor(
                normalized_name="juan perez",
                display_name="Juan Pérez Ficticio",
                club_text="Club Montañas Ficticio",
            )
            session.add_all([comp1, comp2])
            await session.commit()  # no debe lanzar IntegrityError

            rows = (
                await session.execute(
                    select(RaceCompetitor).where(RaceCompetitor.normalized_name == "juan perez")
                )
            ).scalars().all()
            assert len(rows) == 2
            assert {r.club_text for r in rows} == {"Club Andino Ficticio", "Club Montañas Ficticio"}

    @pytest.mark.asyncio
    async def test_city_text_nullable_and_persists_when_set(self, session_factory):
        """`city_text` es nullable (señal de desambiguación opcional, FR-014)
        y persiste cuando se asigna."""
        async with session_factory() as session:
            comp = RaceCompetitor(
                normalized_name="ana gomez ficticia",
                display_name="Ana Gómez Ficticia",
            )
            session.add(comp)
            await session.commit()
            await session.refresh(comp)
            assert comp.city_text is None

            comp.city_text = "Cali"
            await session.commit()
            await session.refresh(comp)
            assert comp.city_text == "Cali"


# ---------------------------------------------------------------------------
# 3. race_competitor_signatures — UNIQUE(normalized_name, club_norm, city_norm)
# ---------------------------------------------------------------------------


class TestRaceCompetitorSignature:
    @pytest.mark.asyncio
    async def test_duplicate_triple_raises_integrity_error(self, session_factory):
        async with session_factory() as session:
            competitor = await _seed_competitor(
                session,
                normalized_name="carlos ruiz ficticio",
                display_name="Carlos Ruiz Ficticio",
            )
            await session.commit()

            sig1 = RaceCompetitorSignature(
                competitor_id=competitor.id,
                normalized_name="carlos ruiz ficticio",
                club_norm="club andino",
                city_norm="cali",
                first_season=2024,
                last_season=2024,
            )
            session.add(sig1)
            await session.commit()

            sig2 = RaceCompetitorSignature(
                competitor_id=competitor.id,
                normalized_name="carlos ruiz ficticio",
                club_norm="club andino",
                city_norm="cali",
                first_season=2025,
                last_season=2025,
            )
            session.add(sig2)
            with pytest.raises(IntegrityError):
                await session.commit()

    @pytest.mark.asyncio
    async def test_duplicate_triple_with_empty_club_and_city_raises(self, session_factory):
        """Caso crítico (data-model.md §3): `club_norm`/`city_norm` son
        `NOT NULL DEFAULT ''` justamente porque MySQL trata dos `NULL` como
        valores distintos dentro de una unique key — con `NULL` la unique no
        protegería nada. Este test fija `''` explícito en ambas columnas y
        confirma que el duplicado exacto SÍ colisiona."""
        async with session_factory() as session:
            competitor = await _seed_competitor(
                session,
                normalized_name="sin club ficticio",
                display_name="Sin Club Ficticio",
            )
            await session.commit()

            sig1 = RaceCompetitorSignature(
                competitor_id=competitor.id,
                normalized_name="sin club ficticio",
                club_norm="",
                city_norm="",
                first_season=2024,
                last_season=2024,
            )
            session.add(sig1)
            await session.commit()

            sig2 = RaceCompetitorSignature(
                competitor_id=competitor.id,
                normalized_name="sin club ficticio",
                club_norm="",
                city_norm="",
                first_season=2025,
                last_season=2025,
            )
            session.add(sig2)
            with pytest.raises(IntegrityError):
                await session.commit()

    @pytest.mark.asyncio
    async def test_signatures_differing_only_in_city_norm_coexist(self, session_factory):
        """Dos firmas que solo difieren en `city_norm` sí conviven — la unique
        es sobre la tripleta completa, no sobre (normalized_name, club_norm)."""
        async with session_factory() as session:
            competitor = await _seed_competitor(
                session,
                normalized_name="laura torres ficticia",
                display_name="Laura Torres Ficticia",
            )
            await session.commit()

            sig_cali = RaceCompetitorSignature(
                competitor_id=competitor.id,
                normalized_name="laura torres ficticia",
                club_norm="club andino",
                city_norm="cali",
                first_season=2024,
                last_season=2024,
            )
            sig_palmira = RaceCompetitorSignature(
                competitor_id=competitor.id,
                normalized_name="laura torres ficticia",
                club_norm="club andino",
                city_norm="palmira",
                first_season=2025,
                last_season=2025,
            )
            session.add_all([sig_cali, sig_palmira])
            await session.commit()  # no debe lanzar

            rows = (
                await session.execute(
                    select(RaceCompetitorSignature).where(
                        RaceCompetitorSignature.competitor_id == competitor.id
                    )
                )
            ).scalars().all()
            assert len(rows) == 2
            assert {r.city_norm for r in rows} == {"cali", "palmira"}

    @pytest.mark.asyncio
    async def test_first_and_last_season_persist(self, session_factory):
        async with session_factory() as session:
            competitor = await _seed_competitor(
                session,
                normalized_name="pedro nieto ficticio",
                display_name="Pedro Nieto Ficticio",
            )
            await session.commit()

            sig = RaceCompetitorSignature(
                competitor_id=competitor.id,
                normalized_name="pedro nieto ficticio",
                club_norm="club rio",
                city_norm="tulua",
                first_season=2024,
                last_season=2025,
            )
            session.add(sig)
            await session.commit()
            await session.refresh(sig)

            assert sig.first_season == 2024
            assert sig.last_season == 2025


    @pytest.mark.asyncio
    async def test_same_triple_with_distinct_discriminators_coexist(self, session_factory):
        """Revisión a7c3e5d91f20 (decisión 2026-09-21): padre e hijo con el
        mismo nombre, club y ciudad son dos firmas si su discriminador de
        categoría difiere; con el mismo discriminador siguen colisionando."""
        async with session_factory() as session:
            parent = await _seed_competitor(
                session, normalized_name="mateo ficticio igual", display_name="Mateo Ficticio Igual"
            )
            child = await _seed_competitor(
                session, normalized_name="mateo ficticio igual", display_name="Mateo Ficticio Igual"
            )
            await session.commit()
            for comp, disc in ((parent, "M:30-39@2025"), (child, "M:9-10@2025")):
                session.add(
                    RaceCompetitorSignature(
                        competitor_id=comp.id,
                        normalized_name="mateo ficticio igual",
                        club_norm="club andino",
                        city_norm="cali",
                        discriminator=disc,
                        first_season=2025,
                        last_season=2025,
                    )
                )
            await session.commit()  # no debe lanzar

            session.add(
                RaceCompetitorSignature(
                    competitor_id=child.id,
                    normalized_name="mateo ficticio igual",
                    club_norm="club andino",
                    city_norm="cali",
                    discriminator="M:9-10@2025",
                    first_season=2026,
                    last_season=2026,
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()

    @pytest.mark.asyncio
    async def test_discriminator_defaults_to_empty_string(self, session_factory):
        async with session_factory() as session:
            comp = await _seed_competitor(
                session, normalized_name="sin disc ficticio", display_name="Sin Disc Ficticio"
            )
            sig = RaceCompetitorSignature(
                competitor_id=comp.id,
                normalized_name="sin disc ficticio",
                first_season=2025,
                last_season=2025,
            )
            session.add(sig)
            await session.commit()
            await session.refresh(sig)
            assert sig.discriminator == ""


# ---------------------------------------------------------------------------
# 4. race_identity_candidates — pair_hash único, state default, enums, JSON
# ---------------------------------------------------------------------------


class TestRaceIdentityCandidate:
    @pytest.mark.asyncio
    async def test_pair_hash_unique(self, session_factory):
        async with session_factory() as session:
            cand1 = RaceIdentityCandidate(
                kind=IdentityCandidateKind.homonym_suspect,
                pair_hash="a" * 64,
                left_record={"normalized_name": "juan perez", "seasons": [2024]},
                right_record={"normalized_name": "juan perez", "seasons": [2025]},
                score=80,
                signals=["same_valida_two_categories"],
            )
            session.add(cand1)
            await session.commit()

            cand2 = RaceIdentityCandidate(
                kind=IdentityCandidateKind.homonym_suspect,
                pair_hash="a" * 64,  # mismo hash → debe colisionar
                left_record={"normalized_name": "otro nombre", "seasons": [2024]},
                right_record={"normalized_name": "otro apellido", "seasons": [2025]},
                score=50,
                signals=["club_and_city_differ"],
            )
            session.add(cand2)
            with pytest.raises(IntegrityError):
                await session.commit()

    @pytest.mark.asyncio
    async def test_state_defaults_to_pending(self, session_factory):
        async with session_factory() as session:
            cand = RaceIdentityCandidate(
                kind=IdentityCandidateKind.same_person_suspect,
                pair_hash="b" * 64,
                left_record={"normalized_name": "ana"},
                right_record={"normalized_name": "ana maria"},
                score=92,
                signals=["extra_surname"],
            )
            session.add(cand)
            await session.commit()
            await session.refresh(cand)

            assert cand.state == IdentityCandidateState.pending

    @pytest.mark.asyncio
    async def test_kind_and_state_persist_string_values(self, session_factory):
        """values_callable guarda el `.value` string ('same_person_suspect',
        'same_person'), no el nombre del miembro Python — verificado leyendo
        la columna cruda, igual que en `test_strava_models.py`."""
        async with session_factory() as session:
            cand = RaceIdentityCandidate(
                kind=IdentityCandidateKind.same_person_suspect,
                pair_hash="c" * 64,
                left_record={"normalized_name": "x"},
                right_record={"normalized_name": "y"},
                score=95,
                signals=["extra_surname"],
                state=IdentityCandidateState.same_person,
            )
            session.add(cand)
            await session.commit()

            raw = (
                await session.execute(
                    select(
                        RaceIdentityCandidate.__table__.c.kind,
                        RaceIdentityCandidate.__table__.c.state,
                    ).where(RaceIdentityCandidate.__table__.c.id == cand.id)
                )
            ).one()
            assert raw.kind == "same_person_suspect"
            assert raw.state == "same_person"

    @pytest.mark.asyncio
    async def test_json_fields_round_trip(self, session_factory):
        """`left_record` / `right_record` / `signals` hacen round-trip completo
        tras un commit + expire + re-lectura."""
        async with session_factory() as session:
            left = {
                "name_printed": "Nombre Ficticio Uno",
                "normalized_name": "nombre ficticio uno",
                "club": "Club Ficticio",
                "city": "Cali",
                "seasons": [2024, 2025],
                "category_codes": ["PJUV_A_F"],
                "sex": "F",
                "competitor_id": 1,
                "athlete_linked": False,
            }
            right = {
                "name_printed": "Nombre Ficticio Uno Extra",
                "normalized_name": "nombre ficticio uno extra",
                "club": "Club Ficticio",
                "city": "Cali",
                "seasons": [2025],
                "category_codes": ["JUN_A_F"],
                "sex": "F",
                "competitor_id": None,
                "athlete_linked": False,
            }
            signals = ["extra_surname", "club_and_city_differ"]

            cand = RaceIdentityCandidate(
                kind=IdentityCandidateKind.same_person_suspect,
                pair_hash="d" * 64,
                left_record=left,
                right_record=right,
                score=88,
                signals=signals,
            )
            session.add(cand)
            await session.commit()

            session.expire_all()
            reloaded = (
                await session.execute(
                    select(RaceIdentityCandidate).where(RaceIdentityCandidate.pair_hash == "d" * 64)
                )
            ).scalar_one()

            assert reloaded.left_record == left
            assert reloaded.right_record == right
            assert reloaded.signals == signals
