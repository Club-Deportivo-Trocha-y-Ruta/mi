"""Alcance por club de los cargues de resultados — ``scope-ai-imports.md`` §11.1.

US6 AS2: un coach parsea el PDF oficial, otro coach del MISMO club confirma el
cargue, y la fila conserva a los dos — ``imported_by_user_id`` es quien parseó,
``committed_by_user_id`` quien commiteó (§6.2). El coach de otro club recibe
403 (``permissions.ensure_import_club_access``, §6.1) y el listado no cambia
para nadie (§6.3).

Arnés: motor SQLite in-memory con el subconjunto de tablas de ``race_imports``
(mismo patrón que ``tests/routers/test_race_imports.py``), almacenamiento local
en ``tmp_path`` en vez de SFTP, y los parsers de PDF stubbeados. El ingestor es
el REAL: es él quien escribe ``committed_by_user_id`` / ``committed_at``, así
que stubbearlo dejaría la prueba verificando su propio doble.

Privacidad (Ley 1581): todos los nombres son sintéticos.
"""

from __future__ import annotations

from datetime import datetime, timezone
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

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.club import ClubRole
from app.models.race_import import RaceImport, RaceImportStatus
from app.models.user import UserRole
from tests.helpers.audit_tables import AUDIT_TABLES

pytestmark = pytest.mark.asyncio


CLUB_ID = 1
OTHER_CLUB_ID = 2

ADMIN_ID = 1
COACH_A_ID = 10  # parsea
COACH_B_ID = 11  # commitea — mismo club que A
COACH_C_ID = 12  # club distinto → 403
PARENT_ID = 5

#: Nombre sintético del deportista TyR que devuelve el parser stubbeado. No
#: corresponde a ninguna persona real (CLAUDE.md, Ley 1581).
TYR_ATHLETE_NAME = "Mariana Ficticia Restrepo"

CATEGORY_CODE = "TET_CP"

_PDF_HEADER = b"%PDF-1.4\n"

#: ``(user_id, rol, clubes, nombre, apellido)``
_ACTORS: dict[str, tuple[int, UserRole, tuple[int, ...], str, str]] = {
    "admin": (ADMIN_ID, UserRole.admin, (CLUB_ID,), "Admin", "Ficticio"),
    "coach_a": (COACH_A_ID, UserRole.coach, (CLUB_ID,), "Ana Ficticia", "Coach"),
    "coach_b": (COACH_B_ID, UserRole.coach, (CLUB_ID,), "Beto Ficticio", "Coach"),
    "coach_c": (COACH_C_ID, UserRole.coach, (OTHER_CLUB_ID,), "Carla Ficticia", "Coach"),
    "parent": (PARENT_ID, UserRole.parent, (), "Padre", "Ficticio"),
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _make_user(actor: str) -> SimpleNamespace:
    """Doble del actor autenticado, con sus membresías de coach puestas."""
    uid, role, club_ids, first, last = _ACTORS[actor]
    return SimpleNamespace(
        id=uid,
        first_name=first,
        last_name=last,
        display_name=f"{first} {last}",
        email=f"{actor}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[
            SimpleNamespace(club_id=cid, role_in_club=ClubRole.coach)
            for cid in club_ids
        ],
    )


# ---------------------------------------------------------------------------
# Arnés
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncGenerator[AsyncEngine, None]:
    # Importes sólo para registrar los modelos en ``Base.metadata`` antes de
    # crear el subconjunto de tablas.
    from app.models.athlete import Athlete as _A  # noqa: F401
    from app.models.club import Club as _Cl  # noqa: F401
    from app.models.club import ClubMember as _CM  # noqa: F401
    from app.models.race_category import RaceCategory as _C  # noqa: F401
    from app.models.race_competitor import RaceCompetitor as _Comp  # noqa: F401
    from app.models.race_event import RaceEvent as _E  # noqa: F401
    from app.models.race_import import RaceImport as _I2  # noqa: F401
    from app.models.race_result import RaceResult as _R  # noqa: F401
    from app.models.race_series import RaceSeries as _S  # noqa: F401
    from app.models.user import User as _U  # noqa: F401

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
            "clubs",
            "club_members",
            "athletes",
            "race_series",
            "race_events",
            "race_imports",
            "race_categories",
            "race_competitors",
            "race_results",
            *AUDIT_TABLES,
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
async def seed(db_session_factory):
    """Dos clubes, cuatro miembros de staff con su fila en ``club_members``,
    la serie base y la categoría que devuelve el parser stubbeado.

    Las filas de ``club_members`` son imprescindibles: ``import_club_ids``
    (§1.2) resuelve el club del cargue leyendo esa tabla para el usuario que
    lo subió, no el objeto autenticado.
    """
    from app.models.club import Club, ClubMember
    from app.models.race_category import CategoryGender, CategoryTier, RaceCategory
    from app.models.race_series import RaceSeries
    from app.models.user import User

    async with db_session_factory() as session:
        session.add_all(
            [
                Club(id=CLUB_ID, name="Club Ficticio Uno", code="CFU"),
                Club(id=OTHER_CLUB_ID, name="Club Ficticio Dos", code="CFD"),
            ]
        )
        await session.flush()

        for actor, (uid, role, club_ids, first, last) in _ACTORS.items():
            session.add(
                User(
                    id=uid,
                    email=f"{actor}@test.local",
                    hashed_password="x",
                    first_name=first,
                    last_name=last,
                    role=role,
                    is_active=True,
                    can_login=True,
                    created_at=_utc_now(),
                )
            )
            await session.flush()
            for cid in club_ids:
                session.add(
                    ClubMember(club_id=cid, user_id=uid, role_in_club=ClubRole.coach)
                )

        session.add(
            RaceSeries(
                id=1,
                name="Copa Valle",
                season_year=2026,
                organizer="Liga Ficticia",
                points_scheme_code="copa_valle_2026",
            )
        )
        session.add(
            RaceCategory(
                id=1,
                code=CATEGORY_CODE,
                label="Teteros Copa",
                sex=CategoryGender.MIXED,
                age_min=5,
                age_max=6,
                sort_order=1,
                is_active=True,
                tier=CategoryTier.menores,
            )
        )
        await session.commit()
    yield


@pytest.fixture
def override_storage(monkeypatch, tmp_path):
    """Redirige el almacenamiento SFTP al respaldo local en ``tmp_path``."""
    from app.services.training import storage_sftp

    fake_base = tmp_path / "uploads-test"
    monkeypatch.setattr(storage_sftp, "_LOCAL_FALLBACK_BASE", fake_base)
    monkeypatch.setattr(
        storage_sftp, "_LOCAL_FALLBACK_URL_PREFIX", "/static/uploads/test"
    )
    for attr in (
        "hostinger_sftp_host",
        "hostinger_sftp_user",
        "hostinger_sftp_pass",
        "hostinger_sftp_remote_dir",
        "hostinger_public_base_url",
    ):
        monkeypatch.setattr(settings, attr, "")
    yield fake_base


@pytest.fixture
def stub_parsers(monkeypatch):
    """Stub de los parsers de PDF — una fila TyR y una ajena, sin tocar disco."""
    from app.routers import race_imports as router_mod
    from app.services.race.pdf_parser import ResultsRow

    async def _fake_results(path, ext):
        return {
            CATEGORY_CODE: [
                ResultsRow(
                    position=1,
                    bib="550",
                    name=TYR_ATHLETE_NAME,
                    city="Yumbo",
                    club="Club Trocha y Ruta",
                    time_raw="0:03:38",
                    points=40,
                ),
                ResultsRow(
                    position=2,
                    bib="551",
                    name="Competidora Ficticia Externa",
                    city="Cali",
                    club="Club Ficticio Dos",
                    time_raw="0:04:00",
                    points=36,
                ),
            ]
        }

    async def _fake_general(path):
        return {}

    monkeypatch.setattr(router_mod, "_parse_results_with_timeout", _fake_results)
    monkeypatch.setattr(router_mod, "_parse_general_with_timeout", _fake_general)


@pytest_asyncio.fixture
async def client_factory(db_session_factory, seed, override_storage):
    """``await client_factory("coach_b")`` → ``AsyncClient`` autenticado."""

    async def _make(actor: str) -> AsyncClient:
        async def _override_db() -> AsyncGenerator[AsyncSession, None]:
            async with db_session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: _make_user(actor)
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    yield _make
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers de petición
# ---------------------------------------------------------------------------


def _parse_form() -> dict[str, str]:
    return {
        "series_name": "Copa Valle",
        "season": "2026",
        "valida_num": "4",
        "event_name": "VALIDA IV FICTICIA",
        "event_date": "2026-05-17",
        "location": "CALI",
    }


async def _parse_as(client: AsyncClient, marker: bytes = b"contenido") -> int:
    """Sube un PDF sintético y devuelve el ``parse_id`` resultante."""
    files = {"resultados_pdf": ("resultados.pdf", _PDF_HEADER + marker, "application/pdf")}
    resp = await client.post(
        "/api/race-analysis/imports/parse", data=_parse_form(), files=files
    )
    assert resp.status_code == 200, resp.text
    return int(resp.json()["parse_id"])


def _commit_body() -> dict:
    from app.services.race.normalizer import normalize_name

    return {
        "resolved_matches": [
            {
                "competitor_normalized_name": normalize_name(TYR_ATHLETE_NAME),
                "athlete_id": None,
            }
        ]
    }


async def _fetch_import(
    db_session_factory: async_sessionmaker[AsyncSession], parse_id: int
) -> RaceImport:
    async with db_session_factory() as session:
        return (
            await session.execute(select(RaceImport).where(RaceImport.id == parse_id))
        ).scalar_one()


# ===========================================================================
# 11. El coach B commitea el parse del coach A
# ===========================================================================


async def test_coach_b_commitea_el_parse_del_coach_a(
    client_factory, db_session_factory, stub_parsers
):
    """§11.1-11: 200, y la fila conserva a los dos actores.

    ``imported_by_user_id`` nunca se sobrescribe (§6.2): el parse sigue siendo
    del coach A aunque haya sido el coach B quien confirmó.
    """
    async with await client_factory("coach_a") as client_a:
        parse_id = await _parse_as(client_a)

    imp = await _fetch_import(db_session_factory, parse_id)
    assert imp.imported_by_user_id == COACH_A_ID
    assert imp.committed_by_user_id is None
    assert imp.committed_at is None

    async with await client_factory("coach_b") as client_b:
        resp = await client_b.post(
            f"/api/race-analysis/imports/{parse_id}/commit", json=_commit_body()
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["parse_id"] == parse_id

    imp = await _fetch_import(db_session_factory, parse_id)
    assert imp.status == RaceImportStatus.committed
    assert imp.imported_by_user_id == COACH_A_ID
    assert imp.committed_by_user_id == COACH_B_ID
    assert imp.committed_at is not None


async def test_coach_b_hace_dry_run_del_parse_del_coach_a(
    client_factory, stub_parsers
):
    """El paso previo del asistente también es del club, no del autor."""
    async with await client_factory("coach_a") as client_a:
        parse_id = await _parse_as(client_a)

    async with await client_factory("coach_b") as client_b:
        resp = await client_b.post(f"/api/race-analysis/imports/{parse_id}/dry-run")

    assert resp.status_code == 200, resp.text
    assert resp.json()["parse_id"] == parse_id


# ===========================================================================
# 12-13. Coach de otro club y bypass de admin
# ===========================================================================


async def test_coach_de_otro_club_403_en_dry_run(client_factory, stub_parsers):
    """§11.1-12: 403 con la copia en español del contrato (§6.1)."""
    async with await client_factory("coach_a") as client_a:
        parse_id = await _parse_as(client_a)

    async with await client_factory("coach_c") as client_c:
        resp = await client_c.post(f"/api/race-analysis/imports/{parse_id}/dry-run")

    assert resp.status_code == 403
    assert resp.json()["detail"] == (
        "No tienes acceso a este cargue de resultados: pertenece a otro club."
    )


async def test_coach_de_otro_club_403_en_commit(
    client_factory, db_session_factory, stub_parsers
):
    """El mismo muro en el commit: la fila no se promueve."""
    async with await client_factory("coach_a") as client_a:
        parse_id = await _parse_as(client_a)

    async with await client_factory("coach_c") as client_c:
        resp = await client_c.post(
            f"/api/race-analysis/imports/{parse_id}/commit", json=_commit_body()
        )

    assert resp.status_code == 403
    imp = await _fetch_import(db_session_factory, parse_id)
    assert imp.status == RaceImportStatus.pending
    assert imp.committed_by_user_id is None


async def test_parent_403_en_dry_run(client_factory, stub_parsers):
    """El gate de rol sigue delante del chequeo de club (§1.4)."""
    async with await client_factory("coach_a") as client_a:
        parse_id = await _parse_as(client_a)

    async with await client_factory("parent") as client_p:
        resp = await client_p.post(f"/api/race-analysis/imports/{parse_id}/dry-run")

    assert resp.status_code == 403


async def test_admin_no_recibe_403(client_factory, stub_parsers):
    """§11.1-13: el bypass de admin no cambió."""
    async with await client_factory("coach_a") as client_a:
        parse_id = await _parse_as(client_a)

    async with await client_factory("admin") as client_admin:
        resp = await client_admin.post(f"/api/race-analysis/imports/{parse_id}/dry-run")

    assert resp.status_code != 403, resp.text


# ===========================================================================
# 14. El listado no cambió
# ===========================================================================


async def test_listado_identico_para_los_tres_coaches(client_factory, stub_parsers):
    """§11.1-14 / §6.3: ``GET /imports/`` nunca estuvo filtrado por autor y
    sigue sin estarlo — el coach de otro club ve el mismo histórico.
    """
    async with await client_factory("coach_a") as client_a:
        parse_id = await _parse_as(client_a)

    cuerpos = {}
    for actor in ("coach_a", "coach_b", "coach_c"):
        async with await client_factory(actor) as client:
            resp = await client.get("/api/race-analysis/imports/")
            assert resp.status_code == 200, resp.text
            cuerpos[actor] = resp.json()

    assert cuerpos["coach_a"] == cuerpos["coach_b"] == cuerpos["coach_c"]
    assert cuerpos["coach_a"]["total"] == 1
    item = cuerpos["coach_a"]["items"][0]
    assert item["id"] == parse_id
    # El nombre del cargador ya lo resolvía el listado antes de esta feature.
    assert item["uploaded_by"]["id"] == COACH_A_ID
    assert item["uploaded_by"]["full_name"] == "Ana Ficticia Coach"


async def test_listado_muestra_al_cargador_no_al_que_commitea(
    client_factory, stub_parsers
):
    """Tras el commit del coach B, el histórico sigue nombrando al coach A:
    ``UploadUserRef`` es el cargador (§6.3), y el commit no lo reescribe.
    """
    async with await client_factory("coach_a") as client_a:
        parse_id = await _parse_as(client_a)

    async with await client_factory("coach_b") as client_b:
        resp = await client_b.post(
            f"/api/race-analysis/imports/{parse_id}/commit", json=_commit_body()
        )
        assert resp.status_code == 200, resp.text

        listado = await client_b.get("/api/race-analysis/imports/")

    assert listado.status_code == 200, listado.text
    item = listado.json()["items"][0]
    assert item["status"] == "committed"
    assert item["uploaded_by"]["id"] == COACH_A_ID
    assert item["uploaded_by"]["full_name"] == "Ana Ficticia Coach"


# ===========================================================================
# Respaldo cuando el club es irresoluble (§1.4)
# ===========================================================================


async def test_cargue_sin_club_resoluble_solo_lo_abre_su_autor(
    client_factory, db_session_factory
):
    """Un cargue de un coach sin fila en ``club_members`` no tiene club: el
    respaldo por autoría lo mantiene alcanzable para él y para el admin, y
    para nadie más. Nunca ensancha el acceso (§1.4).
    """
    from app.models.race_import import RaceImportKind
    from app.models.user import User

    huerfano = 7777
    async with db_session_factory() as session:
        session.add(
            User(
                id=huerfano,
                email="coach.sin.club@test.local",
                hashed_password="x",
                first_name="Coach",
                last_name="Sin Club",
                role=UserRole.coach,
                is_active=True,
                can_login=True,
                created_at=_utc_now(),
            )
        )
        await session.flush()
        imp = RaceImport(
            filename="huerfano.pdf",
            sha256="e" * 64,
            series_id=1,
            status=RaceImportStatus.pending,
            stats_json={},
            imported_by_user_id=huerfano,
            imported_at=_utc_now(),
            kind=RaceImportKind.resultados,
            parse_meta_json={"header": {}},
        )
        session.add(imp)
        await session.commit()
        parse_id = imp.id

    # Coach del club sembrado: no hay club que intersecar ni autoría propia.
    async with await client_factory("coach_b") as client_b:
        assert (
            await client_b.post(f"/api/race-analysis/imports/{parse_id}/dry-run")
        ).status_code == 403

    # Admin: pasa el chequeo (falla después por falta de PDF en storage).
    async with await client_factory("admin") as client_admin:
        assert (
            await client_admin.post(f"/api/race-analysis/imports/{parse_id}/dry-run")
        ).status_code != 403

    # El autor mismo: también pasa.
    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=huerfano,
        first_name="Coach",
        last_name="Sin Club",
        display_name="Coach Sin Club",
        email="coach.sin.club@test.local",
        role=UserRole.coach,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (
            await client.post(f"/api/race-analysis/imports/{parse_id}/dry-run")
        ).status_code != 403
    app.dependency_overrides.clear()
