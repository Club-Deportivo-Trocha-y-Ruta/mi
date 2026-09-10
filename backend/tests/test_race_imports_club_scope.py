"""Regresión de seguridad — alcance por club de ``/api/race-analysis/imports/*``.

Feature 041 (multi-coach governance) reemplazó el creator-lock de imports por
la regla de club de ``contracts/scope-ai-imports.md`` §1/§6: *cualquier cosa
del club la puede operar cualquier coach del club; el admin siempre; el coach
de otro club nunca.* Este módulo cubre tres hallazgos de la revisión de
seguridad de la corrida anterior que seguían abiertos:

- **H4** (cross-club listing): ``GET /imports/`` devolvía TODOS los cargues
  (ids + nombres de uploader) a cualquier coach, sin filtrar por club —
  solo la ruta de detalle estaba cerrada por ``ensure_import_club_access``.
- **H5**: el fallback de nombre de uploader emitía ``f"user#{id}"``, un
  identificador crudo prohibido por FR-013 (contracts/scope-ai-imports.md
  §4.1) cuando el join no resuelve.
- **H7** (fails closed pero rompe al coach en producción): un cargue subido
  por el ADMIN del club resolvía a un set de clubes vacío (solo se miraba
  ``role_in_club='coach'``), dejándolo alcanzable únicamente por ese admin —
  los demás coaches del club veían un 403 espurio.

Patrón: motor sqlite en memoria propio + subconjunto de tablas (igual que
``tests/routers/test_audit_log_api.py``) — NO se usa el fixture ``client``
del ``conftest.py`` raíz porque aquí no hay MySQL disponible y ese fixture
falla. Tampoco se importa nada de ``tests/routers/conftest.py``: ese módulo
está roto en esta rama por trabajo concurrente de otro agente sobre
``app/routers/race_analysis.py`` (import de ``_admin_only``, que ese archivo
no es propiedad de esta tarea) — vivir fuera de ``tests/routers/`` evita ese
conftest por completo.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
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
from app.models.club import Club, ClubMember, ClubRole
from app.models.race_import import RaceImport, RaceImportKind, RaceImportStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole
from tests.helpers.audit_tables import AUDIT_TABLES

# IDs seedeados (ver fixture ``seed``):
#   users:   101 coach A (club 1) · 102 coach B (club 1) · 103 coach C (club 2)
#            104 admin DE CLUB (role_in_club=admin, club 1; User.role=coach)
#   imports: 1 subido por 101 (club 1) · 2 subido por 104 (club-admin, club 1)
#            3 subido por 103 (club 2)  · 4 subido por un user_id inexistente (999)
COACH_A_ID = 101
COACH_B_ID = 102
COACH_C_ID = 103
CLUB_ADMIN_ID = 104
GHOST_UPLOADER_ID = 999

IMPORT_CLUB1_BY_COACH_A = 1
IMPORT_CLUB1_BY_CLUB_ADMIN = 2
IMPORT_CLUB2_BY_COACH_C = 3
IMPORT_GHOST_UPLOADER = 4


def _make_user(
    role: UserRole,
    user_id: int,
    club_ids: tuple[tuple[int, ClubRole], ...] = (),
) -> SimpleNamespace:
    """Usuario falso — ``coach_club_ids`` lee ``user.club_memberships`` del
    objeto autenticado (no la tabla), igual que en ``test_race_imports.py``.
    """
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name=f"User{user_id}",
        email=f"user{user_id}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[
            SimpleNamespace(club_id=cid, role_in_club=r) for cid, r in club_ids
        ],
    )


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncEngine:
    """SQLite async in-memory con solo las tablas necesarias (StaticPool para
    que todas las conexiones compartan la misma instancia en memoria)."""
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
async def seed(db_session_factory) -> None:
    """Dos clubes, cuatro coaches (uno de ellos admin DE CLUB) y cuatro imports."""
    now = datetime.now(timezone.utc)
    async with db_session_factory() as session:
        session.add_all(
            [
                Club(id=1, name="Club Uno", code="C1"),
                Club(id=2, name="Club Dos", code="C2"),
            ]
        )
        session.add_all(
            [
                User(
                    id=COACH_A_ID, email="a@test.local", hashed_password="x",
                    first_name="Coach", last_name="A",
                    role=UserRole.coach, is_active=True, can_login=True,
                    created_at=now,
                ),
                User(
                    id=COACH_B_ID, email="b@test.local", hashed_password="x",
                    first_name="Coach", last_name="B",
                    role=UserRole.coach, is_active=True, can_login=True,
                    created_at=now,
                ),
                User(
                    id=COACH_C_ID, email="c@test.local", hashed_password="x",
                    first_name="Coach", last_name="C",
                    role=UserRole.coach, is_active=True, can_login=True,
                    created_at=now,
                ),
                # "Admin del club": rol de sistema coach, pero role_in_club
                # 'admin' en club_members — el caso que H7 rompía.
                User(
                    id=CLUB_ADMIN_ID, email="clubadmin@test.local", hashed_password="x",
                    first_name="Club", last_name="Admin",
                    role=UserRole.coach, is_active=True, can_login=True,
                    created_at=now,
                ),
                RaceSeries(
                    id=1, name="Copa Valle de Ciclomontañismo", season_year=2026,
                    organizer="Liga Vallecaucana", points_scheme_code="copa_valle_2026",
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                ClubMember(club_id=1, user_id=COACH_A_ID, role_in_club=ClubRole.coach),
                ClubMember(club_id=1, user_id=COACH_B_ID, role_in_club=ClubRole.coach),
                ClubMember(club_id=2, user_id=COACH_C_ID, role_in_club=ClubRole.coach),
                ClubMember(club_id=1, user_id=CLUB_ADMIN_ID, role_in_club=ClubRole.admin),
            ]
        )
        session.add_all(
            [
                RaceImport(
                    id=IMPORT_CLUB1_BY_COACH_A, filename="a.pdf", sha256="a" * 64,
                    series_id=1, status=RaceImportStatus.pending, stats_json={},
                    imported_by_user_id=COACH_A_ID, imported_at=now,
                    kind=RaceImportKind.resultados,
                    parse_meta_json={"header": {}, "results_ext": "pdf"},
                    storage_path="/nonexistent/a.pdf",
                ),
                RaceImport(
                    id=IMPORT_CLUB1_BY_CLUB_ADMIN, filename="admin.pdf", sha256="b" * 64,
                    series_id=1, status=RaceImportStatus.pending, stats_json={},
                    imported_by_user_id=CLUB_ADMIN_ID, imported_at=now,
                    kind=RaceImportKind.resultados,
                    parse_meta_json={"header": {}, "results_ext": "pdf"},
                    storage_path="/nonexistent/admin.pdf",
                ),
                RaceImport(
                    id=IMPORT_CLUB2_BY_COACH_C, filename="c.pdf", sha256="c" * 64,
                    series_id=1, status=RaceImportStatus.pending, stats_json={},
                    imported_by_user_id=COACH_C_ID, imported_at=now,
                    kind=RaceImportKind.resultados,
                    parse_meta_json={"header": {}, "results_ext": "pdf"},
                    storage_path="/nonexistent/c.pdf",
                ),
                # Uploader cuyo id ya no resuelve a ningún User (fila borrada
                # / editada a mano) — ejercita el fallback de nombre H5.
                RaceImport(
                    id=IMPORT_GHOST_UPLOADER, filename="ghost.pdf", sha256="d" * 64,
                    series_id=1, status=RaceImportStatus.committed,
                    stats_json={"results_inserted": 1},
                    imported_by_user_id=GHOST_UPLOADER_ID, imported_at=now,
                    kind=RaceImportKind.resultados,
                ),
            ]
        )
        await session.commit()


def _override_db(db_session_factory):
    async def _inner():
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _inner


@pytest_asyncio.fixture
async def client_factory(sqlite_engine, db_session_factory, seed):
    """Fábrica de clientes HTTP autenticados como distintos usuarios falsos.

    Uso: ``async with client_factory(user) as ac: ...``
    """

    def _factory(user: SimpleNamespace) -> AsyncClient:
        app.dependency_overrides[get_db] = _override_db(db_session_factory)
        app.dependency_overrides[get_current_user] = lambda: user
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    yield _factory
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Coach B (mismo club que coach A) puede operar el cargue de coach A
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coach_same_club_can_act_on_import_from_another_coach(client_factory):
    """La regla de club (no el creator-lock) decide: coach B, coach del club
    1 igual que el uploader (coach A), puede iniciar el dry-run.

    El dry-run en sí falla después por falta de PDF real en storage — lo que
    prueba este test es que el chequeo de club (ownership) NO devuelve 403.
    """
    coach_b = _make_user(UserRole.coach, COACH_B_ID, club_ids=((1, ClubRole.coach),))
    async with client_factory(coach_b) as ac:
        r = await ac.post(
            f"/api/race-analysis/imports/{IMPORT_CLUB1_BY_COACH_A}/dry-run"
        )
    assert r.status_code != 403, r.text


# ---------------------------------------------------------------------------
# Coach de otro club → 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coach_other_club_gets_403(client_factory):
    coach_c = _make_user(UserRole.coach, COACH_C_ID, club_ids=((2, ClubRole.coach),))
    async with client_factory(coach_c) as ac:
        r = await ac.post(
            f"/api/race-analysis/imports/{IMPORT_CLUB1_BY_COACH_A}/dry-run"
        )
    assert r.status_code == 403
    assert "otro club" in r.json()["detail"]


# ---------------------------------------------------------------------------
# H4 — el listado solo muestra los cargues del propio club
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_listing_shows_only_same_club_imports(client_factory):
    """Regresión H4: antes ``GET /imports/`` devolvía TODOS los cargues a
    cualquier coach. Coach B (club 1) debe ver los dos cargues del club 1
    (el suyo propio no existe en el seed, pero sí el de coach A y el del
    admin de club) y jamás el del club 2 ni el de uploader fantasma (que
    solo su propio autor —inexistente— podría ver por respaldo de autoría).
    """
    coach_b = _make_user(UserRole.coach, COACH_B_ID, club_ids=((1, ClubRole.coach),))
    async with client_factory(coach_b) as ac:
        r = await ac.get("/api/race-analysis/imports/")

    assert r.status_code == 200
    data = r.json()
    visible_ids = {item["id"] for item in data["items"]}

    assert visible_ids == {IMPORT_CLUB1_BY_COACH_A, IMPORT_CLUB1_BY_CLUB_ADMIN}
    assert data["total"] == 2
    assert IMPORT_CLUB2_BY_COACH_C not in visible_ids
    assert IMPORT_GHOST_UPLOADER not in visible_ids


@pytest.mark.asyncio
async def test_listing_admin_sees_every_club(client_factory):
    """El admin no se ve afectado por el filtro: sigue viendo todo."""
    admin = _make_user(UserRole.admin, 1)
    async with client_factory(admin) as ac:
        r = await ac.get("/api/race-analysis/imports/")

    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 4
    assert {item["id"] for item in data["items"]} == {
        IMPORT_CLUB1_BY_COACH_A,
        IMPORT_CLUB1_BY_CLUB_ADMIN,
        IMPORT_CLUB2_BY_COACH_C,
        IMPORT_GHOST_UPLOADER,
    }


# ---------------------------------------------------------------------------
# H7 — un cargue subido por el admin del club sigue siendo alcanzable por
# los coaches del club (antes resolvía a un set de clubes vacío)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_uploaded_by_club_admin_reachable_by_club_coaches(client_factory):
    """Regresión H7: ``_coach_membership_club_ids`` solo miraba
    ``role_in_club='coach'``; un cargue subido por el admin del club (rol
    'admin' en ``club_members``) resolvía a ``set()`` y solo ese admin podía
    alcanzarlo. Ahora ``import_club_ids`` ensancha a (coach, admin) y el
    resto de coaches del club vuelven a poder operarlo.
    """
    coach_b = _make_user(UserRole.coach, COACH_B_ID, club_ids=((1, ClubRole.coach),))
    async with client_factory(coach_b) as ac:
        r = await ac.post(
            f"/api/race-analysis/imports/{IMPORT_CLUB1_BY_CLUB_ADMIN}/dry-run"
        )
    assert r.status_code != 403, r.text

    # También debe aparecer en su listado (mismo club).
    async with client_factory(coach_b) as ac:
        r = await ac.get("/api/race-analysis/imports/")
    ids = {item["id"] for item in r.json()["items"]}
    assert IMPORT_CLUB1_BY_CLUB_ADMIN in ids


@pytest.mark.asyncio
async def test_import_uploaded_by_club_admin_still_403_for_other_club(client_factory):
    """Contraparte: un coach de OTRO club sigue sin acceso al cargue del
    admin de club 1 — H7 no ensancha el acceso, solo repara el club correcto.
    """
    coach_c = _make_user(UserRole.coach, COACH_C_ID, club_ids=((2, ClubRole.coach),))
    async with client_factory(coach_c) as ac:
        r = await ac.post(
            f"/api/race-analysis/imports/{IMPORT_CLUB1_BY_CLUB_ADMIN}/dry-run"
        )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# H5 — el fallback de nombre de uploader nunca es "user#{id}"
# ---------------------------------------------------------------------------


_RAW_USER_ID_RE = re.compile(r"^user#\d+$")


@pytest.mark.asyncio
async def test_uploader_fallback_never_renders_raw_user_id(client_factory):
    """Regresión H5 (FR-013): un cargue cuyo ``imported_by_user_id`` no
    resuelve a ningún ``User`` debe mostrar ``"Usuario no disponible"``,
    nunca ``f"user#{id}"``. Se usa el admin para ver el cargue del uploader
    fantasma (fuera del alcance de cualquier coach)."""
    admin = _make_user(UserRole.admin, 1)
    async with client_factory(admin) as ac:
        r = await ac.get("/api/race-analysis/imports/")

    data = r.json()
    by_id = {item["id"]: item for item in data["items"]}
    ghost_item = by_id[IMPORT_GHOST_UPLOADER]

    assert ghost_item["uploaded_by"]["full_name"] == "Usuario no disponible"
    for item in data["items"]:
        assert not _RAW_USER_ID_RE.match(item["uploaded_by"]["full_name"])
