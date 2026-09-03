"""Tests de privacidad de laps + matching (specs/026-structured-interval-training,
T019, SC-007).

Cubre:
  1. ``StravaActivityLap`` (modelo SQLAlchemy) no tiene, ni puede tener sin
     cambiar este test, columnas ni atributos de geo/mapa, ``name`` libre,
     cadencia ni potencia (data-model.md §5 "Explicitly ABSENT columns").
  2. Los schemas Pydantic expuestos a un usuario final (``LapOut``,
     ``MatchBlockOut``, ``ExtraLapOut``, ``MatchActivityOut``,
     ``MatchDetailOut``, ``MatchResultBlock``, ``MatchResultExtraLap``,
     ``MatchResultPayload``) no declaran ningún campo prohibido — defensa en
     profundidad, igual que ``test_strava_privacy.py``.
  3. El allow-list de ``services/intervals/match_runner.py``
     (``_allow_listed_lap`` / ``_replace_laps``) descarta cualquier campo
     inesperado del payload crudo de Strava (geo, ``average_cadence``,
     ``average_watts``, ``name`` de la vuelta) — ni se persiste en
     ``strava_activity_laps`` ni sobrevive en el ``MatchLap`` que alimenta el
     motor de matching.
  4. El pipeline completo (``run_match_deferred``) persiste un
     ``interval_match_results.result_json`` sin coordenadas/cadencia/potencia
     ni el ``name`` libre de la vuelta, aun cuando el payload crudo de Strava
     los incluya — y la respuesta real de
     ``GET /api/intervals/sessions/{id}/match`` tampoco los expone.
  5. Los logs de ``match_runner`` (laps malformadas descartadas, corrida
     fallida) contienen solo identificadores numéricos y nombres de tipo de
     excepción — nunca el contenido crudo de una vuelta.

Ley 1581 (Colombia) — datos de menores. Todos los datos usados son ficticios
(CLAUDE.md §Privacy). Sigue el patrón de
``tests/privacy/test_strava_privacy.py`` (feature 025, T038).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, AsyncGenerator

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

# ``ParentalConsent.policy`` es ``lazy="joined"`` a nivel de mapper: CUALQUIER
# ``select(ParentalConsent)`` emite un LEFT OUTER JOIN contra
# ``privacy_policies`` — la tabla debe existir para el DDL de SQLite, mismo
# shim que ``tests/privacy/test_strava_privacy.py``.
@compiles(LONGTEXT, "sqlite")
def _compile_longtext_as_text_on_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "TEXT"

import app.database as database_module
from app.config import settings
from app.dependencies import get_current_user, get_db
from app.models import Base
from app.models.athlete import Athlete, Sex
from app.models.club import Club, ClubMember, ClubRole
from app.models.interval_structure import (
    HRZone,
    IntervalBlockType,
    IntervalStructure,
    IntervalStructureBlock,
)
from app.models.parental_consent import ParentalConsent
from app.models.strava_activity import StravaActivity, StravaIngestSource
from app.models.strava_activity_lap import (
    IntervalMatchResult,
    MatchTrigger,
    StravaActivityLap,
)
from app.models.strava_connection import StravaConnection, StravaConnectionStatus
from app.models.interval_structure import AgeBand
from app.models.training_session import SessionKind, TrainingSession
from app.models.user import User, UserRole
from app.routers import intervals as intervals_router
from app.schemas.intervals import (
    ExtraLapOut,
    LapOut,
    MatchActivityOut,
    MatchBlockOut,
    MatchDetailOut,
    MatchResultBlock,
    MatchResultExtraLap,
    MatchResultPayload,
    MatchSummary,
)
from app.services.intervals import match_runner
from app.services.strava.token_store import encrypt_token

# NOTE: no module-level ``pytestmark = pytest.mark.asyncio`` — ``pytest.ini``
# fija ``asyncio_mode = "auto"`` en todo el repo (misma nota que
# ``tests/privacy/test_strava_privacy.py``); agregar el marker solo dispara un
# ``PytestWarning`` en los tests síncronos de este módulo.

# ---------------------------------------------------------------------------
# Claves prohibidas para laps/matching — geo/mapa, cadencia, potencia y el
# ``name`` libre de una vuelta (data-model.md §5 "Explicitly ABSENT columns").
# Distinto del set de ``test_strava_privacy.py`` (que deliberadamente excluye
# "name" porque el título de la ACTIVIDAD sí es legítimo ahí); en el universo
# de laps/match de este módulo ningún schema/response legítimo lleva "name",
# así que incluirlo acá no genera falsos positivos.
# ---------------------------------------------------------------------------

FORBIDDEN_LAP_KEYS = {
    "lat",
    "lng",
    "latlng",
    "start_latlng",
    "end_latlng",
    "polyline",
    "map",
    "map_polyline",
    "summary_polyline",
    "average_cadence",
    "cadence",
    "average_watts",
    "watts",
    "power",
    "name",
    "description",
    "photos",
    "segment_efforts",
}

# Cadena ficticia pero distintiva: si apareciera en un log o en una respuesta
# sería inequívocamente una fuga, no una coincidencia con contenido legítimo.
_FICTITIOUS_LAP_NAME = "Vuelta secreta cerca de la casa de Juan"


def _collect_keys(obj: Any) -> set[str]:
    """Recolecta (en minúsculas) todas las claves de un JSON-like anidado."""
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(str(k).lower())
            keys |= _collect_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _collect_keys(item)
    return keys


def _assert_no_forbidden_keys(body: Any, *, where: str) -> None:
    found = FORBIDDEN_LAP_KEYS & _collect_keys(body)
    assert not found, f"Claves prohibidas {found} encontradas en {where}: {body}"


def _assert_fictitious_lap_name_absent(body: Any, *, where: str) -> None:
    text = str(body)
    assert _FICTITIOUS_LAP_NAME not in text, (
        f"El nombre libre de la vuelta apareció en {where} — violación de "
        "privacidad Ley 1581 (data-model.md §5)."
    )


# ===========================================================================
# 1. Modelo SQLAlchemy — sin columnas ni atributos de geo/cadencia/potencia/name
# ===========================================================================


class TestModelHasNoForbiddenAttributes:
    def test_strava_activity_lap_has_no_forbidden_columns_or_attributes(self) -> None:
        columns = {c.lower() for c in StravaActivityLap.__table__.columns.keys()}
        assert FORBIDDEN_LAP_KEYS.isdisjoint(columns)
        for forbidden in FORBIDDEN_LAP_KEYS:
            assert not hasattr(StravaActivityLap, forbidden), (
                f"StravaActivityLap no debe tener el atributo '{forbidden}'"
            )

    def test_strava_activity_lap_columns_are_exactly_the_allow_list(self) -> None:
        """Invariante fuerte: cualquier columna nueva agregada al modelo debe
        pasar por una revisión explícita de este test (data-model.md §5)."""
        columns = set(StravaActivityLap.__table__.columns.keys())
        assert columns == {
            "id",
            "strava_activity_id",
            "lap_index",
            "elapsed_time_s",
            "moving_time_s",
            "average_heartrate",
            "average_speed_m_s",
            "fetched_at",
        }


# ===========================================================================
# 2. Schemas Pydantic — assert estático (defensa en profundidad)
# ===========================================================================


class TestSchemasHaveNoForbiddenFields:
    @pytest.mark.parametrize(
        "model_cls",
        [
            LapOut,
            MatchBlockOut,
            ExtraLapOut,
            MatchActivityOut,
            MatchDetailOut,
            MatchSummary,
            MatchResultBlock,
            MatchResultExtraLap,
            MatchResultPayload,
        ],
    )
    def test_schema_fields_exclude_forbidden_keys(self, model_cls) -> None:
        field_names = {name.lower() for name in model_cls.model_fields}
        found = FORBIDDEN_LAP_KEYS & field_names
        assert not found, (
            f"{model_cls.__name__} declara campo(s) prohibido(s) {found} — "
            "violación de privacidad Ley 1581 (data-model.md §5)."
        )

    def test_match_result_payload_forbids_extra_keys(self) -> None:
        """``MatchResultPayload`` (y su árbol) usa ``extra='forbid'`` — una
        clave inesperada (geo/cadencia/potencia) debe fallar la validación
        antes de poder persistirse, no ser silenciosamente descartada."""
        with pytest.raises(Exception):
            MatchResultPayload(
                blocks=[],
                extra_laps=[],
                summary=MatchSummary(),
                tolerance_pct=30,
                laps_discarded_under_10s=0,
                average_cadence=85,  # type: ignore[call-arg]
            )

    def test_match_result_block_forbids_extra_keys(self) -> None:
        with pytest.raises(Exception):
            MatchResultBlock(
                flat_index=0,
                block_type="warmup",
                planned_duration_s=300,
                target_zone="Z1",
                target_cadence_rpm=70,
                status="cumplido",
                start_latlng=[3.4, -76.5],  # type: ignore[call-arg]
            )


# ===========================================================================
# 3. Fixtures — DB en memoria + seeding ficticio
# ===========================================================================

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "privacy_policies",  # ver shim LONGTEXT arriba
    "parental_consents",
    "strava_connections",
    "strava_activities",
    "training_sessions",
    "interval_structures",
    "interval_structure_blocks",
    "strava_activity_laps",
    "interval_match_results",
)


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _build_app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(intervals_router.router, prefix="/api/intervals")
    return test_app


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
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
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture(autouse=True)
async def _patch_deferred_job_session_factory(
    monkeypatch: pytest.MonkeyPatch, session_factory
) -> None:
    """``match_runner.run_match_deferred`` abre su propia sesión vía
    ``app.database.AsyncSessionLocal`` (import local, docstring del módulo:
    "Opens its own AsyncSessionLocal"). Se apunta ese nombre al engine sqlite
    de este test para poder ejercitar el pipeline diferido completo."""
    monkeypatch.setattr(database_module, "AsyncSessionLocal", session_factory)


@pytest.fixture(autouse=True)
def _strava_token_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings, "strava_token_encryption_key", Fernet.generate_key().decode()
    )


# --- seed helpers (ficticios) ----------------------------------------------


async def _seed_user(session: AsyncSession, user_id: int, role: UserRole) -> User:
    u = User(
        id=user_id,
        email=f"{role.value}{user_id}@ficticio.test",
        hashed_password="x",
        first_name="Test",
        last_name=f"User{user_id}",
        role=role,
        is_active=True,
        can_login=role != UserRole.athlete,
        created_at=_utc(),
    )
    session.add(u)
    await session.flush()
    return u


async def _seed_club(session: AsyncSession, club_id: int = 1) -> Club:
    club = Club(id=club_id, name="Club Trocha y Ruta Ficticio", code=f"TYR-{club_id}")
    session.add(club)
    await session.flush()
    return club


async def _seed_club_member(
    session: AsyncSession, *, user_id: int, club_id: int, role: ClubRole
) -> ClubMember:
    cm = ClubMember(user_id=user_id, club_id=club_id, role_in_club=role)
    session.add(cm)
    await session.flush()
    return cm


async def _seed_athlete(
    session: AsyncSession, athlete_id: int, *, club_id: int = 1
) -> Athlete:
    a = Athlete(
        id=athlete_id,
        user_id=900 + athlete_id,
        first_name="Atleta",
        last_name=f"Ficticio{athlete_id}",
        birth_date=date(2013, 5, 1),
        sex=Sex.M,
        club_id=club_id,
        created_by=1,
    )
    session.add(a)
    await session.flush()
    return a


async def _seed_connection(
    session: AsyncSession,
    *,
    athlete_id: int,
    strava_athlete_id: int,
    authorized_by_user_id: int = 1,
) -> StravaConnection:
    consent = ParentalConsent(
        parent_user_id=authorized_by_user_id,
        athlete_id=athlete_id,
        consent_version="v1",
        consented_at=_utc(),
    )
    session.add(consent)
    await session.flush()

    conn = StravaConnection(
        athlete_id=athlete_id,
        strava_athlete_id=strava_athlete_id,
        status=StravaConnectionStatus.active,
        access_token_enc=encrypt_token("plain-access-token"),
        refresh_token_enc=encrypt_token("plain-refresh-token"),
        token_expires_at=_utc() + timedelta(hours=6),
        scope_granted="activity:read_all",
        authorized_by_user_id=authorized_by_user_id,
        consent_id=consent.id,
        connected_at=_utc(),
    )
    session.add(conn)
    await session.flush()
    return conn


async def _seed_training_session(
    session: AsyncSession, session_id: int, *, club_id: int = 1
) -> TrainingSession:
    from datetime import time as _time

    ts = TrainingSession(
        id=session_id,
        club_id=club_id,
        created_by_user_id=1,
        scheduled_date=date(2026, 6, 1),
        scheduled_start_time=_time(15, 0),
        duration_min=90,
        location="Sede club ficticia",
        technical_focus="Resistencia",
        session_kind=SessionKind.ENTRENAMIENTO,
    )
    session.add(ts)
    await session.flush()
    return ts


async def _seed_activity(
    session: AsyncSession,
    activity_id: int,
    *,
    strava_activity_id: int,
    athlete_id: int,
    connection_id: int,
    training_session_id: int,
) -> StravaActivity:
    now = _utc()
    a = StravaActivity(
        id=activity_id,
        strava_activity_id=strava_activity_id,
        athlete_id=athlete_id,
        connection_id=connection_id,
        name="Salida ficticia XCO",
        sport_type="MountainBikeRide",
        start_date_utc=now,
        start_date_local=now.replace(tzinfo=None),
        elapsed_time_s=3600,
        moving_time_s=3500,
        distance_m=25000.0,
        total_elevation_gain_m=300.0,
        average_heartrate=150.0,
        max_heartrate=175.0,
        is_trainer=False,
        ingest_source=StravaIngestSource.webhook,
        training_session_id=training_session_id,
        linked_at=now,
        linked_by_user_id=1,
    )
    session.add(a)
    await session.flush()
    return a


async def _seed_structure(
    session: AsyncSession, structure_id: int, *, training_session_id: int
) -> IntervalStructure:
    """Estructura 13-15 mínima: warmup Z1 + work Z2 (dos bloques, sin
    repeticiones) — suficiente para ejercitar el matching posicional."""
    structure = IntervalStructure(
        id=structure_id,
        training_session_id=training_session_id,
        target_age_band=AgeBand.BAND_13_15,
        age_gate_confirmed=False,
        created_by_user_id=1,
        created_at=_utc(),
        updated_at=_utc(),
    )
    session.add(structure)
    await session.flush()

    session.add_all(
        [
            IntervalStructureBlock(
                structure_id=structure.id,
                position=1,
                block_type=IntervalBlockType.WARMUP,
                duration_s=300,
                target_zone=HRZone.Z1,
                target_cadence_rpm=70,
            ),
            IntervalStructureBlock(
                structure_id=structure.id,
                position=2,
                block_type=IntervalBlockType.WORK,
                duration_s=120,
                target_zone=HRZone.Z2,
                target_cadence_rpm=80,
            ),
        ]
    )
    await session.flush()
    return structure


def _admin_user_typed(user_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, role=UserRole.admin, club_memberships=[])


def _make_client(session: AsyncSession, *, user) -> AsyncClient:
    test_app = _build_app()

    async def _override_db():
        yield session
        await session.commit()

    async def _override_user():
        return user

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = _override_user

    return AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
        follow_redirects=False,
    )


def _poisoned_raw_lap(
    lap_index: int, *, elapsed_time: int, average_heartrate: float | None = 140.0
) -> dict[str, Any]:
    """Payload crudo de una vuelta de Strava con TODOS los campos permitidos
    más un surtido de campos prohibidos que Strava podría llegar a mandar
    (geo, cadencia, potencia, nombre libre) — el allow-list debe descartarlos
    todos, sin excepción."""
    return {
        "id": 999000 + lap_index,
        "lap_index": lap_index,
        "elapsed_time": elapsed_time,
        "moving_time": elapsed_time - 2,
        "average_heartrate": average_heartrate,
        "average_speed": 3.2,
        # --- prohibidos: nunca deben leerse ni persistirse ---
        "name": _FICTITIOUS_LAP_NAME,
        "start_latlng": [3.4516, -76.5320],
        "end_latlng": [3.4520, -76.5325],
        "map": {"summary_polyline": "abc123poisonpolyline"},
        "average_cadence": 92.5,
        "average_watts": 210.0,
        "max_watts": 340,
        "device_watts": True,
    }


class _FakeStravaClientReturningPoisonedLaps:
    """Doble mínimo de ``StravaClient`` — entrega vueltas con campos
    prohibidos para verificar que ``match_runner`` los descarta antes de
    persistir o loguear nada."""

    def __init__(self, connection: StravaConnection, db: AsyncSession) -> None:
        self._connection = connection

    async def __aenter__(self) -> "_FakeStravaClientReturningPoisonedLaps":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def get_activity_laps(self, activity_id: int) -> list[dict]:
        return [
            _poisoned_raw_lap(0, elapsed_time=312),
            _poisoned_raw_lap(1, elapsed_time=118),
            # Vuelta malformada (sin lap_index) — debe descartarse en
            # silencio, nunca loguear su contenido crudo.
            {
                "elapsed_time": 45,
                "name": _FICTITIOUS_LAP_NAME,
                "average_cadence": 88,
            },
        ]


class _FakeStravaClientRaising:
    """Doble que simula un fallo de Strava (p. ej. 429/5xx) para verificar
    que el log de fallo no incluye contenido crudo."""

    def __init__(self, connection: StravaConnection, db: AsyncSession) -> None:
        self._connection = connection

    async def __aenter__(self) -> "_FakeStravaClientRaising":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def get_activity_laps(self, activity_id: int) -> list[dict]:
        raise RuntimeError(f"strava dijo: {_FICTITIOUS_LAP_NAME}")


async def _seed_full_scenario(session: AsyncSession) -> tuple[IntervalStructure, StravaActivity]:
    await _seed_user(session, 1, UserRole.admin)
    await _seed_club(session, 1)
    await _seed_athlete(session, 100, club_id=1)
    conn = await _seed_connection(
        session, athlete_id=100, strava_athlete_id=555, authorized_by_user_id=1
    )
    ts = await _seed_training_session(session, 1, club_id=1)
    activity = await _seed_activity(
        session,
        1,
        strava_activity_id=111,
        athlete_id=100,
        connection_id=conn.id,
        training_session_id=ts.id,
    )
    structure = await _seed_structure(session, 7, training_session_id=ts.id)
    await session.commit()
    return structure, activity


def _all_log_text(caplog: pytest.LogCaptureFixture) -> str:
    """Texto de mensaje + TODOS los campos ``extra=`` de cada LogRecord
    capturado — igual patrón que ``test_strava_privacy.py`` (los campos
    ``extra`` no viven en ``caplog.messages``)."""
    chunks: list[str] = []
    for record in caplog.records:
        chunks.append(record.getMessage())
        chunks.append(str(record.__dict__))
    return " ".join(chunks)


# ===========================================================================
# 4. Allow-list del runner — nivel función pura (sin DB)
# ===========================================================================


class TestAllowListedLapDiscardsUnexpectedFields:
    def test_allow_listed_lap_drops_every_forbidden_field(self) -> None:
        raw = _poisoned_raw_lap(3, elapsed_time=200)

        lap = match_runner._allow_listed_lap(
            raw, strava_activity_pk=1, fetched_at=_utc()
        )

        assert lap is not None
        # Solo los campos permitidos llegaron al objeto ORM.
        assert lap.lap_index == 3
        assert lap.elapsed_time_s == 200
        assert lap.moving_time_s == 198
        assert lap.average_heartrate == 140.0
        assert lap.average_speed_m_s == 3.2
        # Ningún atributo del modelo puede siquiera existir para cargar un
        # valor prohibido (defensa en profundidad — ver TestModelHasNo...).
        for forbidden in FORBIDDEN_LAP_KEYS:
            assert not hasattr(lap, forbidden)
        # Sanity: el valor ficticio prohibido no sobrevive en ningún atributo
        # del objeto construido.
        assert _FICTITIOUS_LAP_NAME not in str(vars(lap))

    def test_allow_listed_lap_returns_none_for_malformed_entry_without_crash(
        self,
    ) -> None:
        raw = {"name": _FICTITIOUS_LAP_NAME, "average_cadence": 90}
        lap = match_runner._allow_listed_lap(
            raw, strava_activity_pk=1, fetched_at=_utc()
        )
        assert lap is None


class TestReplaceLapsPersistsOnlyAllowedFields:
    async def test_replace_laps_writes_no_forbidden_column_values(
        self, session: AsyncSession
    ) -> None:
        await _seed_user(session, 1, UserRole.admin)
        await _seed_club(session, 1)
        await _seed_athlete(session, 100, club_id=1)
        conn = await _seed_connection(
            session, athlete_id=100, strava_athlete_id=555, authorized_by_user_id=1
        )
        ts = await _seed_training_session(session, 1, club_id=1)
        activity = await _seed_activity(
            session,
            1,
            strava_activity_id=111,
            athlete_id=100,
            connection_id=conn.id,
            training_session_id=ts.id,
        )
        await session.commit()

        raw_laps = [
            _poisoned_raw_lap(0, elapsed_time=312),
            _poisoned_raw_lap(1, elapsed_time=118),
        ]

        match_laps = await match_runner._replace_laps(
            session, strava_activity_pk=activity.id, raw_laps=raw_laps
        )
        await session.commit()

        # Lo que alimenta el motor de matching es estrictamente numérico.
        assert len(match_laps) == 2
        for ml in match_laps:
            assert not hasattr(ml, "name")
            assert not hasattr(ml, "average_cadence")
            assert not hasattr(ml, "start_latlng")

        rows_result = await session.execute(
            select(StravaActivityLap).where(
                StravaActivityLap.strava_activity_id == activity.id
            )
        )
        rows = rows_result.scalars().all()
        assert len(rows) == 2
        for row in rows:
            row_dict = {
                c.name: getattr(row, c.name) for c in StravaActivityLap.__table__.columns
            }
            _assert_no_forbidden_keys(row_dict, where="fila persistida de StravaActivityLap")
            _assert_fictitious_lap_name_absent(
                row_dict, where="fila persistida de StravaActivityLap"
            )


# ===========================================================================
# 5. Pipeline completo diferido — persistencia + respuesta HTTP real
# ===========================================================================


class TestRunMatchDeferredNoLeakageEndToEnd:
    async def test_persisted_result_json_has_no_forbidden_keys_or_lap_name(
        self, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        structure, activity = await _seed_full_scenario(session)
        monkeypatch.setattr(
            match_runner, "StravaClient", _FakeStravaClientReturningPoisonedLaps
        )

        await match_runner.run_match_deferred(
            structure.id, activity.id, MatchTrigger.link
        )

        async with database_module.AsyncSessionLocal() as verify_session:
            result = await verify_session.execute(
                select(IntervalMatchResult).where(
                    IntervalMatchResult.structure_id == structure.id,
                    IntervalMatchResult.strava_activity_id == activity.id,
                )
            )
            row = result.scalar_one()

        _assert_no_forbidden_keys(row.result_json, where="interval_match_results.result_json")
        _assert_fictitious_lap_name_absent(
            row.result_json, where="interval_match_results.result_json"
        )
        # Sanity: el emparejamiento realmente ocurrió (no un JSON vacío que
        # trivializaría el assert anterior).
        assert row.result_json["summary"]["cumplido"] + row.result_json["summary"][
            "fuera_tolerancia"
        ] == 2

        async with database_module.AsyncSessionLocal() as laps_verify_session:
            laps = (
                await laps_verify_session.execute(
                    select(StravaActivityLap).where(
                        StravaActivityLap.strava_activity_id == activity.id
                    )
                )
            ).scalars().all()
        # Las dos vueltas bien formadas se persistieron; la malformada (sin
        # lap_index) se descartó sin fallar la corrida completa.
        assert len(laps) == 2
        for lap in laps:
            lap_dict = {
                c.name: getattr(lap, c.name) for c in StravaActivityLap.__table__.columns
            }
            _assert_no_forbidden_keys(lap_dict, where="StravaActivityLap persistida (pipeline)")
            _assert_fictitious_lap_name_absent(
                lap_dict, where="StravaActivityLap persistida (pipeline)"
            )

    async def test_match_detail_endpoint_response_has_no_forbidden_keys_or_lap_name(
        self, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        structure, activity = await _seed_full_scenario(session)
        await _seed_club_member(
            session, user_id=1, club_id=1, role=ClubRole.admin
        )
        await session.commit()
        monkeypatch.setattr(
            match_runner, "StravaClient", _FakeStravaClientReturningPoisonedLaps
        )

        await match_runner.run_match_deferred(
            structure.id, activity.id, MatchTrigger.link
        )

        async with database_module.AsyncSessionLocal() as query_session:
            async with _make_client(query_session, user=_admin_user_typed()) as client:
                resp = await client.get(
                    f"/api/intervals/sessions/{structure.training_session_id}/match"
                )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "computed"
        assert body["blocks"], "el escenario sembrado debe producir bloques emparejados"

        _assert_no_forbidden_keys(body, where="GET /api/intervals/sessions/{id}/match")
        _assert_fictitious_lap_name_absent(
            body, where="GET /api/intervals/sessions/{id}/match"
        )

    async def test_no_activity_status_response_has_no_forbidden_keys(
        self, session: AsyncSession
    ) -> None:
        """Sesión con estructura pero sin actividad vinculada — envelope
        ``no_activity`` (nunca un error crudo); sanity de que este estado
        vacío tampoco puede filtrar nada."""
        await _seed_user(session, 1, UserRole.admin)
        await _seed_club(session, 1)
        await _seed_club_member(session, user_id=1, club_id=1, role=ClubRole.admin)
        ts = await _seed_training_session(session, 1, club_id=1)
        await _seed_structure(session, 7, training_session_id=ts.id)
        await session.commit()

        async with _make_client(session, user=_admin_user_typed()) as client:
            resp = await client.get(f"/api/intervals/sessions/{ts.id}/match")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "no_activity"
        _assert_no_forbidden_keys(body, where="GET .../match (status=no_activity)")


# ===========================================================================
# 6. Logs — solo IDs numéricos y nombres de tipo de excepción (FR-016 aplicado
#    al feature 026, mismo espíritu que test_strava_privacy.py).
# ===========================================================================


class TestMatchRunnerLogsAreNumericOnly:
    async def test_skipped_malformed_lap_log_excludes_raw_lap_content(
        self,
        session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        structure, activity = await _seed_full_scenario(session)
        monkeypatch.setattr(
            match_runner, "StravaClient", _FakeStravaClientReturningPoisonedLaps
        )

        with caplog.at_level(
            logging.DEBUG, logger="app.services.intervals.match_runner"
        ):
            await match_runner.run_match_deferred(
                structure.id, activity.id, MatchTrigger.link
            )

        log_text = _all_log_text(caplog)
        assert _FICTITIOUS_LAP_NAME not in log_text, (
            "El nombre libre de una vuelta apareció en los logs de "
            "match_runner — violación de privacidad Ley 1581 (data-model.md §5)."
        )
        assert "interval_match_laps_skipped_malformed" in log_text
        assert "1" in log_text  # el conteo numérico de la vuelta descartada

    async def test_failed_run_log_excludes_exception_message_and_lap_name(
        self,
        session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        structure, activity = await _seed_full_scenario(session)
        monkeypatch.setattr(match_runner, "StravaClient", _FakeStravaClientRaising)

        with caplog.at_level(
            logging.DEBUG, logger="app.services.intervals.match_runner"
        ):
            await match_runner.run_match_deferred(
                structure.id, activity.id, MatchTrigger.link
            )

        log_text = _all_log_text(caplog)
        assert _FICTITIOUS_LAP_NAME not in log_text, (
            "El mensaje crudo de una excepción de Strava apareció en los "
            "logs de match_runner (podría contener contenido de la vuelta) — "
            "violación de privacidad Ley 1581."
        )
        assert "interval_match_run_failed" in log_text
        assert "RuntimeError" in log_text  # solo el nombre del tipo, no el mensaje
        assert match_runner.has_failed(structure.id, activity.id) is True


# ===========================================================================
# Sanity: el escenario ficticio en sí no colisiona con las claves prohibidas
# (evita falsos negativos silenciosos en el barrido de FORBIDDEN_LAP_KEYS).
# ===========================================================================


def test_forbidden_lap_keys_set_is_not_accidentally_empty() -> None:
    assert len(FORBIDDEN_LAP_KEYS) >= 10
