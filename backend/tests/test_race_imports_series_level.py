"""Tests backend spec 023 — National Championship Level (T015).

Cubre el flujo de import (`POST /api/race-analysis/imports/parse`, que resuelve
la serie vía `_get_or_create_series`) con el nuevo Form field `series_level`:

  (1) Crear una serie NUEVA de campeonato con `series_level="national"` ->
      `series.level == national` y `organizer is None` (NO se aplica el
      default "Liga Vallecaucana de Ciclismo" — decisión D5 del plan 023 /
      research R5).
  (2) Crear una serie NUEVA de copa (sin `series_level`, o `series_level`
      omitido) -> `organizer == "Liga Vallecaucana de Ciclismo"` sin cambios
      (byte-identical al comportamiento pre-023).
  (3) `series_level` inválido -> 422 a nivel de endpoint, y `ValueError` a
      nivel del helper `_get_or_create_series` (llamada directa).

Estado esperado (pre-T020): `_get_or_create_series` todavía NO acepta el
parámetro `level`/`series_level` y el router todavía NO declara el Form field
`series_level`. Por lo tanto:
  - (1) FALLA porque el organizer sigue siendo "Liga Vallecaucana de Ciclismo"
    (el kwarg `series_level` es ignorado silenciosamente por FastAPI al no
    estar declarado como Form field) y `series.level` no existe con el valor
    esperado (queda en el default `departmental` del modelo).
  - (2) PASA hoy (comportamiento no tocado), sirve de regresión.
  - (3) FALLA: el endpoint no valida `series_level` (sigue devolviendo 200) y
    la llamada directa al helper con `level=` lanza `TypeError` (kwarg
    inexistente) en vez de `ValueError`.
Se espera que (1) y (3) FALLEN hasta que T020 aterrice el fix en
`app/routers/race_imports.py`.

Estrategia: SQLite async in-memory + StaticPool; overrides de `get_db` /
`get_current_user`, calcado de `backend/tests/routers/test_race_imports.py`
(mismos fixtures, reducidos a lo necesario para `/parse`).

Privacidad invariante: no se usan datos ficticios de menores; race_series /
race_imports son metadata pública de federación.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

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

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.race_series import RaceSeries, RaceSeriesKind, RaceSeriesLevel
from app.models.user import User, UserRole


def _make_user(role: UserRole, user_id: int = 10) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"{role.value}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncEngine:
    """SQLite async in-memory con solo las tablas necesarias para /parse."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    from app.models.user import User as _U  # noqa: F401
    from app.models.club import Club as _Cl, ClubMember as _CM  # noqa: F401
    from app.models.athlete import Athlete as _A  # noqa: F401
    from app.models.race_series import RaceSeries as _S  # noqa: F401
    from app.models.race_event import RaceEvent as _E  # noqa: F401
    from app.models.race_import import RaceImport as _I  # noqa: F401
    from app.models.race_category import RaceCategory as _C  # noqa: F401
    from app.models.race_competitor import RaceCompetitor as _Comp  # noqa: F401
    from app.models.race_result import RaceResult as _R  # noqa: F401

    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "clubs",
            "club_members",
            "athletes",
            "race_series",
            "race_events",
            "race_imports",
            "race_categories",
            "race_competitors",
            "race_results",
        )
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory(sqlite_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def seed_test_data(db_session_factory):
    """Inserta el coach usado por todos los tests (sin serie preexistente —
    cada test crea su propia serie NUEVA vía /parse para poder observar
    `_get_or_create_series` en su rama "crear")."""
    async with db_session_factory() as session:
        coach1 = User(
            id=10, email="coach10@test.com", hashed_password="x",
            first_name="Coach", last_name="Ten",
            role=UserRole.coach, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        session.add(coach1)
        await session.commit()
    yield


@pytest.fixture
def override_storage(monkeypatch, tmp_path):
    """Redirige storage_sftp al fallback local en tmp_path."""
    from app.services.training import storage_sftp

    fake_base = tmp_path / "uploads-test"
    monkeypatch.setattr(storage_sftp, "_LOCAL_FALLBACK_BASE", fake_base)
    monkeypatch.setattr(
        storage_sftp, "_LOCAL_FALLBACK_URL_PREFIX", "/static/uploads/test"
    )
    monkeypatch.setattr(settings, "hostinger_sftp_host", "")
    monkeypatch.setattr(settings, "hostinger_sftp_user", "")
    monkeypatch.setattr(settings, "hostinger_sftp_pass", "")
    monkeypatch.setattr(settings, "hostinger_sftp_remote_dir", "")
    monkeypatch.setattr(settings, "hostinger_public_base_url", "")
    yield fake_base


@pytest.fixture
def stub_parsers(monkeypatch):
    """Stub de pdf_parser para evitar dependencia de PDFs reales."""
    from app.routers import race_imports as router_mod

    async def fake_parse_results(path, ext):  # noqa: ARG001
        from app.services.race.pdf_parser import ResultsRow
        return {
            "TET_CP": [
                ResultsRow(
                    position=1, bib="550", name="Sebastian Yule Mendoza",
                    city="Yumbo", club="Club Trocha y Ruta",
                    time_raw="0:03:38", points=40,
                ),
            ],
        }

    async def fake_parse_general(path):  # noqa: ARG001
        return {}

    monkeypatch.setattr(
        router_mod, "_parse_results_with_timeout", fake_parse_results
    )
    monkeypatch.setattr(
        router_mod, "_parse_general_with_timeout", fake_parse_general
    )


@pytest_asyncio.fixture
async def coach_client(
    sqlite_engine, db_session_factory, seed_test_data, override_storage
):
    """Cliente HTTP autenticado como coach id=10."""
    async def _override_db():
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.coach, user_id=10
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers de payload
# ---------------------------------------------------------------------------

_PDF_HEADER = b"%PDF-1.4\n"


def _parse_form(**overrides):
    form = {
        "series_name": "Serie Test 023",
        "season": "2026",
        "valida_num": "1",
        "event_name": "EVENTO TEST",
        "event_date": "2026-07-18",
        "location": "PEREIRA",
    }
    form.update({k: str(v) for k, v in overrides.items()})
    return form


def _pdf_file(content_extra: bytes = b"") -> tuple[str, bytes, str]:
    return ("resultados.pdf", _PDF_HEADER + content_extra, "application/pdf")


# ===========================================================================
# (1) Campeonato NUEVO con series_level=national -> organizer NULL
# ===========================================================================


class TestSeriesLevelOnNewSeries:
    @pytest.mark.asyncio
    async def test_new_national_championship_series_has_no_valle_organizer(
        self, coach_client, stub_parsers, db_session_factory
    ):
        """FR-006 / D5: campeonato nacional NUEVO -> organizer None, level=national.

        Pre-T020: `series_level` es un Form field inexistente (ignorado) y
        `_get_or_create_series` no acepta `level`, así que la serie creada
        sigue teniendo `organizer == "Liga Vallecaucana de Ciclismo"` y
        `level == departmental` (default del modelo). Este test debe FALLAR
        hasta que T020 aterrice.
        """
        files = {"resultados_pdf": _pdf_file(b"contenido nacional")}
        r = await coach_client.post(
            "/api/race-analysis/imports/parse",
            data=_parse_form(
                series_name="Campeonato Nacional MTB 2026",
                series_kind="championship",
                series_level="national",
            ),
            files=files,
        )
        assert r.status_code == 200, r.text

        async with db_session_factory() as session:
            result = await session.execute(
                select(RaceSeries).where(
                    RaceSeries.name == "Campeonato Nacional MTB 2026",
                    RaceSeries.season_year == 2026,
                )
            )
            series = result.scalar_one()

        assert series.kind == RaceSeriesKind.championship
        assert series.level == RaceSeriesLevel.national
        assert series.organizer is None, (
            "El campeonato nacional NO debe heredar el organizer "
            "'Liga Vallecaucana de Ciclismo' (D5 / FR-006)."
        )

    @pytest.mark.asyncio
    async def test_new_cup_series_keeps_valle_organizer_default_unchanged(
        self, coach_client, stub_parsers, db_session_factory
    ):
        """Regresión: crear una copa NUEVA (sin series_level) mantiene el
        default de organizer byte-identical al comportamiento pre-023.
        """
        files = {"resultados_pdf": _pdf_file(b"contenido copa")}
        r = await coach_client.post(
            "/api/race-analysis/imports/parse",
            data=_parse_form(series_name="Copa Valle 023 Regresion"),
            files=files,
        )
        assert r.status_code == 200, r.text

        async with db_session_factory() as session:
            result = await session.execute(
                select(RaceSeries).where(
                    RaceSeries.name == "Copa Valle 023 Regresion",
                    RaceSeries.season_year == 2026,
                )
            )
            series = result.scalar_one()

        assert series.kind == RaceSeriesKind.cup
        assert series.level == RaceSeriesLevel.departmental
        assert series.organizer == "Liga Vallecaucana de Ciclismo"


# ===========================================================================
# (3) series_level inválido -> 422 (endpoint) / ValueError (helper)
# ===========================================================================


class TestSeriesLevelInvalid:
    @pytest.mark.asyncio
    async def test_parse_rejects_invalid_series_level(
        self, coach_client, stub_parsers
    ):
        """Pre-T020: `series_level` no está declarado como Form field, así que
        FastAPI lo ignora silenciosamente y el endpoint responde 200 en vez
        de 422. Este test debe FALLAR hasta que T020 valide `series_level`.
        """
        files = {"resultados_pdf": _pdf_file(b"contenido invalido")}
        r = await coach_client.post(
            "/api/race-analysis/imports/parse",
            data=_parse_form(
                series_name="Serie Nivel Invalido",
                series_kind="championship",
                series_level="galactic",
            ),
            files=files,
        )
        assert r.status_code == 422, r.text

    @pytest.mark.asyncio
    async def test_get_or_create_series_helper_rejects_invalid_level(
        self, db_session_factory
    ):
        """Llamada directa al helper con un `level` inválido.

        Pre-T020: `_get_or_create_series` no tiene parámetro `level` -> la
        llamada lanza `TypeError` (kwarg inexistente), no `ValueError`, así
        que este `pytest.raises(ValueError)` FALLA por la razón correcta
        (falta implementar T020).
        """
        from app.routers.race_imports import _get_or_create_series

        async with db_session_factory() as session:
            with pytest.raises(ValueError):
                await _get_or_create_series(
                    session,
                    "Serie Helper Nivel Invalido",
                    2026,
                    RaceSeriesKind.championship,
                    level="galactic",  # type: ignore[arg-type]
                )
