"""Tests T012 — modelos ``StravaConnection`` / ``StravaActivity`` (feature 025).

Cubre (data-model.md §1-3):
  - Colisión de unicidad en ``strava_connections.strava_athlete_id`` (misma
    cuenta de Strava no puede enlazarse a dos atletas — "primer bind gana").
  - Colisión de unicidad en ``strava_connections.athlete_id`` (1:1 atleta↔conexión;
    reconectar debe actualizar la fila existente, no insertar una segunda).
  - Colisión de unicidad en ``strava_activities.strava_activity_id`` (ancla de
    idempotencia del upsert de ingest, FR-005).
  - Valores enum persistidos vía ``values_callable`` (``StravaConnectionStatus``,
    ``StravaUpstreamState``, ``StravaIngestSource``) — se guardan como el
    ``.value`` string, no el nombre Python del miembro.
  - ``strava_connections.consent_id`` es NULLABLE (consentimiento-por-acción:
    autorizar el OAuth de Strava ES el consentimiento; no se exige fila de
    ``parental_consents``).

SQLite async in-memory + StaticPool (patrón repo — ver
``backend/tests/test_race_series_router.py``); no requiere MySQL.
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
from app.models.athlete import Athlete, Sex
from app.models.club import Club
from app.models.parental_consent import ParentalConsent
from app.models.strava_activity import (
    StravaActivity,
    StravaIngestSource,
    StravaUpstreamState,
)
from app.models.strava_connection import StravaConnection, StravaConnectionStatus
from app.models.user import User, UserRole

_TABLES = [
    "users",
    "clubs",
    "athletes",
    "parental_consents",
    "strava_connections",
    "strava_activities",
]
# NOTA: ``privacy_policies`` NO se incluye — usa LONGTEXT, que SQLite no
# compila (mismo patrón que test_race_import_upload_columns.py). Como
# ``ParentalConsent.policy`` es ``lazy="joined"`` a nivel de mapper, CUALQUIER
# SELECT/refresh ORM de ``ParentalConsent`` intentaría el join a esa tabla.
# Por eso los tests de este módulo NUNCA re-consultan ``ParentalConsent`` vía
# ORM tras el commit — leen los atributos ya poblados en la instancia
# in-session (``expire_on_commit=False``) o, cuando se necesita el valor
# crudo de columna, usan ``select(ParentalConsent.__table__.c...)`` (Core,
# sin mapper) igual que para los enums de Strava más abajo.


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


async def _seed_athlete(
    session: AsyncSession, *, athlete_user_id: int = 100, athlete_id_hint: int | None = None
) -> Athlete:
    """Crea (club, user coach-creador, user del atleta ficticio, athlete)."""
    club = Club(name="Club Trocha y Ruta Ficticio", code=f"TYR-{athlete_user_id}")
    coach = User(
        email=f"coach{athlete_user_id}@ficticio.test",
        hashed_password="x",
        first_name="Coach",
        last_name="Ficticio",
        role=UserRole.coach,
        is_active=True,
        can_login=True,
        created_at=datetime.now(timezone.utc),
    )
    athlete_user = User(
        email=f"atleta{athlete_user_id}@ficticio.test",
        hashed_password="x",
        first_name="Juan",
        last_name="Pérez Ficticio",
        role=UserRole.athlete,
        is_active=True,
        can_login=False,
        created_at=datetime.now(timezone.utc),
    )
    session.add_all([club, coach, athlete_user])
    await session.flush()

    athlete = Athlete(
        user_id=athlete_user.id,
        first_name="Juan",
        last_name="Pérez Ficticio",
        birth_date=date(2013, 5, 1),
        sex=Sex.M,
        club_id=club.id,
        created_by=coach.id,
    )
    session.add(athlete)
    await session.flush()
    return athlete


async def _seed_consent(
    session: AsyncSession, athlete: Athlete
) -> ParentalConsent:
    """Seed a plain ``parental_consents`` row used only as an optional legacy
    ``consent_id`` reference on a connection (Strava no longer gates on it)."""
    parent = User(
        email=f"padre{athlete.id}@ficticio.test",
        hashed_password="x",
        first_name="Padre",
        last_name="Ficticio",
        role=UserRole.parent,
        is_active=True,
        can_login=True,
        created_at=datetime.now(timezone.utc),
    )
    session.add(parent)
    await session.flush()

    consent = ParentalConsent(
        parent_user_id=parent.id,
        athlete_id=athlete.id,
        consent_version="v1",
    )
    session.add(consent)
    await session.flush()
    return consent


def _connection_kwargs(
    *, athlete_id: int, user_id: int, consent_id: int | None = None, strava_athlete_id: int
) -> dict:
    now = datetime.now(timezone.utc)
    return dict(
        athlete_id=athlete_id,
        strava_athlete_id=strava_athlete_id,
        access_token_enc=b"enc-access-token",
        refresh_token_enc=b"enc-refresh-token",
        token_expires_at=now,
        scope_granted="activity:read_all",
        authorized_by_user_id=user_id,
        consent_id=consent_id,
        connected_at=now,
    )


# ---------------------------------------------------------------------------
# StravaConnection — uniqueness
# ---------------------------------------------------------------------------


class TestStravaConnectionUniqueness:
    @pytest.mark.asyncio
    async def test_strava_athlete_id_collision_raises(self, session_factory):
        """Enlazar la MISMA cuenta de Strava a DOS atletas distintos falla
        (UNIQUE en ``strava_athlete_id`` — "primer bind gana", data-model.md §1)."""
        async with session_factory() as session:
            athlete1 = await _seed_athlete(session, athlete_user_id=1)
            consent1 = await _seed_consent(session, athlete1)
            await session.commit()

            conn1 = StravaConnection(
                **_connection_kwargs(
                    athlete_id=athlete1.id,
                    user_id=consent1.parent_user_id,
                    consent_id=consent1.id,
                    strava_athlete_id=999888,
                )
            )
            session.add(conn1)
            await session.commit()

        async with session_factory() as session:
            athlete2 = await _seed_athlete(session, athlete_user_id=2)
            consent2 = await _seed_consent(session, athlete2)
            await session.commit()

            conn2 = StravaConnection(
                **_connection_kwargs(
                    athlete_id=athlete2.id,
                    user_id=consent2.parent_user_id,
                    consent_id=consent2.id,
                    strava_athlete_id=999888,  # misma cuenta Strava que conn1
                )
            )
            session.add(conn2)
            with pytest.raises(IntegrityError):
                await session.commit()

    @pytest.mark.asyncio
    async def test_athlete_id_uniqueness_second_row_raises(self, session_factory):
        """Un atleta no puede tener DOS filas ``strava_connections`` (1:1
        con reconectar-actualiza; INSERT de una segunda fila para el mismo
        atleta debe fallar por UNIQUE(athlete_id))."""
        async with session_factory() as session:
            athlete = await _seed_athlete(session)
            consent = await _seed_consent(session, athlete)
            await session.commit()

            conn1 = StravaConnection(
                **_connection_kwargs(
                    athlete_id=athlete.id,
                    user_id=consent.parent_user_id,
                    consent_id=consent.id,
                    strava_athlete_id=111222,
                )
            )
            session.add(conn1)
            await session.commit()

            conn2 = StravaConnection(
                **_connection_kwargs(
                    athlete_id=athlete.id,  # mismo atleta
                    user_id=consent.parent_user_id,
                    consent_id=consent.id,
                    strava_athlete_id=333444,  # cuenta Strava distinta
                )
            )
            session.add(conn2)
            with pytest.raises(IntegrityError):
                await session.commit()

    @pytest.mark.asyncio
    async def test_reconnect_updates_existing_row_not_insert(self, session_factory):
        """El flujo de reconexión (UPDATE de la fila existente) sí funciona:
        cambiar tokens/status en la misma fila no colisiona con la unique."""
        async with session_factory() as session:
            athlete = await _seed_athlete(session)
            consent = await _seed_consent(session, athlete)
            await session.commit()

            conn = StravaConnection(
                **_connection_kwargs(
                    athlete_id=athlete.id,
                    user_id=consent.parent_user_id,
                    consent_id=consent.id,
                    strava_athlete_id=555666,
                )
            )
            session.add(conn)
            await session.commit()

            conn.status = StravaConnectionStatus.disconnected
            conn.disconnected_at = datetime.now(timezone.utc)
            await session.commit()

            reloaded = (
                await session.execute(
                    select(StravaConnection).where(StravaConnection.athlete_id == athlete.id)
                )
            ).scalar_one()
            assert reloaded.status == StravaConnectionStatus.disconnected
            assert reloaded.disconnected_at is not None


# ---------------------------------------------------------------------------
# StravaConnection — enum values_callable
# ---------------------------------------------------------------------------


class TestStravaConnectionEnum:
    @pytest.mark.asyncio
    async def test_status_default_active(self, session_factory):
        async with session_factory() as session:
            athlete = await _seed_athlete(session)
            consent = await _seed_consent(session, athlete)
            await session.commit()

            conn = StravaConnection(
                **_connection_kwargs(
                    athlete_id=athlete.id,
                    user_id=consent.parent_user_id,
                    consent_id=consent.id,
                    strava_athlete_id=777888,
                )
            )
            session.add(conn)
            await session.commit()
            await session.refresh(conn)

            assert conn.status == StravaConnectionStatus.active

    @pytest.mark.asyncio
    async def test_status_persisted_as_value_not_name(self, session_factory):
        """values_callable guarda el ``.value`` string ('broken'), no el
        nombre del miembro Python — verificado leyendo la columna cruda."""
        async with session_factory() as session:
            athlete = await _seed_athlete(session)
            consent = await _seed_consent(session, athlete)
            await session.commit()

            conn = StravaConnection(
                status=StravaConnectionStatus.broken,
                **_connection_kwargs(
                    athlete_id=athlete.id,
                    user_id=consent.parent_user_id,
                    consent_id=consent.id,
                    strava_athlete_id=101010,
                ),
            )
            session.add(conn)
            await session.commit()

            raw = (
                await session.execute(
                    select(StravaConnection.__table__.c.status).where(
                        StravaConnection.__table__.c.id == conn.id
                    )
                )
            ).scalar_one()
            assert raw == "broken"

    @pytest.mark.asyncio
    async def test_all_status_values_round_trip(self, session_factory):
        for i, status in enumerate(StravaConnectionStatus):
            async with session_factory() as session:
                athlete = await _seed_athlete(session, athlete_user_id=2000 + i)
                consent = await _seed_consent(session, athlete)
                await session.commit()

                conn = StravaConnection(
                    status=status,
                    **_connection_kwargs(
                        athlete_id=athlete.id,
                        user_id=consent.parent_user_id,
                        consent_id=consent.id,
                        strava_athlete_id=3_000_000 + i,
                    ),
                )
                session.add(conn)
                await session.commit()
                await session.refresh(conn)
                assert conn.status == status
                assert conn.status.value in {"active", "disconnected", "broken"}


# ---------------------------------------------------------------------------
# StravaActivity — uniqueness + enums
# ---------------------------------------------------------------------------


def _activity_kwargs(*, athlete_id: int, connection_id: int, strava_activity_id: int) -> dict:
    now = datetime.now(timezone.utc)
    return dict(
        strava_activity_id=strava_activity_id,
        athlete_id=athlete_id,
        connection_id=connection_id,
        name="Salida Ficticia XCO",
        sport_type="MountainBikeRide",
        start_date_utc=now,
        start_date_local=now,
        elapsed_time_s=3600,
        ingest_source=StravaIngestSource.webhook,
    )


class TestStravaActivityUniqueness:
    @pytest.mark.asyncio
    async def test_strava_activity_id_collision_raises(self, session_factory):
        """Dos filas con el mismo ``strava_activity_id`` violan la UNIQUE que
        ancla la idempotencia del upsert de ingest (FR-005)."""
        async with session_factory() as session:
            athlete = await _seed_athlete(session)
            consent = await _seed_consent(session, athlete)
            await session.commit()

            conn = StravaConnection(
                **_connection_kwargs(
                    athlete_id=athlete.id,
                    user_id=consent.parent_user_id,
                    consent_id=consent.id,
                    strava_athlete_id=424242,
                )
            )
            session.add(conn)
            await session.commit()

            act1 = StravaActivity(
                **_activity_kwargs(
                    athlete_id=athlete.id,
                    connection_id=conn.id,
                    strava_activity_id=555_000_111,
                )
            )
            session.add(act1)
            await session.commit()

            act2 = StravaActivity(
                **_activity_kwargs(
                    athlete_id=athlete.id,
                    connection_id=conn.id,
                    strava_activity_id=555_000_111,  # colisión
                )
            )
            session.add(act2)
            with pytest.raises(IntegrityError):
                await session.commit()

    @pytest.mark.asyncio
    async def test_upstream_state_and_ingest_source_defaults_and_values(
        self, session_factory
    ):
        async with session_factory() as session:
            athlete = await _seed_athlete(session)
            consent = await _seed_consent(session, athlete)
            await session.commit()

            conn = StravaConnection(
                **_connection_kwargs(
                    athlete_id=athlete.id,
                    user_id=consent.parent_user_id,
                    consent_id=consent.id,
                    strava_athlete_id=636363,
                )
            )
            session.add(conn)
            await session.commit()

            act = StravaActivity(
                **_activity_kwargs(
                    athlete_id=athlete.id,
                    connection_id=conn.id,
                    strava_activity_id=987_654_321,
                )
            )
            session.add(act)
            await session.commit()
            await session.refresh(act)

            # Defaults del modelo (present / summary_complete=True)
            assert act.upstream_state == StravaUpstreamState.present
            assert act.summary_complete is True
            assert act.is_trainer is False
            assert act.ingest_source == StravaIngestSource.webhook

            # Round-trip explícito de removed_upstream + reconcile
            act.upstream_state = StravaUpstreamState.removed_upstream
            await session.commit()

            raw = (
                await session.execute(
                    select(StravaActivity.__table__.c.upstream_state).where(
                        StravaActivity.__table__.c.id == act.id
                    )
                )
            ).scalar_one()
            assert raw == "removed_upstream"

    @pytest.mark.asyncio
    async def test_ingest_source_reconcile_value(self, session_factory):
        async with session_factory() as session:
            athlete = await _seed_athlete(session)
            consent = await _seed_consent(session, athlete)
            await session.commit()

            conn = StravaConnection(
                **_connection_kwargs(
                    athlete_id=athlete.id,
                    user_id=consent.parent_user_id,
                    consent_id=consent.id,
                    strava_athlete_id=707070,
                )
            )
            session.add(conn)
            await session.commit()

            kwargs = _activity_kwargs(
                athlete_id=athlete.id,
                connection_id=conn.id,
                strava_activity_id=111_222_333,
            )
            kwargs["ingest_source"] = StravaIngestSource.reconcile
            act = StravaActivity(**kwargs)
            session.add(act)
            await session.commit()
            await session.refresh(act)

            assert act.ingest_source == StravaIngestSource.reconcile

    @pytest.mark.asyncio
    async def test_no_location_or_map_columns_present(self, session_factory):
        """Privacidad por esquema (data-model.md §2): el modelo NO debe tener
        columnas de ubicación/mapa/descripción/foto — ver docstring del modelo."""
        forbidden = {
            "start_latlng",
            "end_latlng",
            "map_polyline",
            "description",
            "photos",
        }
        actual_columns = set(StravaActivity.__table__.columns.keys())
        assert forbidden.isdisjoint(actual_columns)


# ---------------------------------------------------------------------------
# StravaConnection.consent_id nullable (consentimiento-por-acción)
# ---------------------------------------------------------------------------


class TestStravaConnectionConsentNullable:
    @pytest.mark.asyncio
    async def test_connection_persists_without_consent_row(self, session_factory):
        """Autorizar el OAuth de Strava ES el consentimiento afirmativo: una
        conexión puede persistir con ``consent_id`` NULL (sin fila de
        ``parental_consents``). El rastro de auditoría vive en
        ``authorized_by_user_id`` + ``connected_at``."""
        async with session_factory() as session:
            athlete = await _seed_athlete(session)
            await session.commit()

            conn = StravaConnection(
                **_connection_kwargs(
                    athlete_id=athlete.id,
                    user_id=athlete.created_by,
                    consent_id=None,
                    strava_athlete_id=848484,
                )
            )
            session.add(conn)
            await session.commit()
            await session.refresh(conn)

            assert conn.consent_id is None
            assert conn.authorized_by_user_id == athlete.created_by
            assert conn.connected_at is not None
