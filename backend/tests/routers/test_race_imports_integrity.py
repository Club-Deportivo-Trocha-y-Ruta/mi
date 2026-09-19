"""Tests del router — integridad de lectura US1 (feature 044, T014).

Cubre la parte de ``contracts/reading-integrity.md`` §"API deltas" que le
corresponde a T014 (T019 la implementa):

- ``POST /parse`` gana ``categories[]`` (con su ``completeness`` propia) y
  ``unreadable_rows[]``.
- ``POST /{id}/corrections`` levanta el bloqueo de una categoría.
- ``POST /{id}/acknowledge`` con un motivo del catálogo cerrado queda
  auditado; un motivo inventado se rechaza con 422.
- ``GET /acknowledge-reasons`` lista el catálogo cerrado (mismo patrón que
  el ya existente ``GET /revision-reasons``).
- Rutas denegadas: padre 403, deportista 403, coach de otro club 403.

Estrategia: en vez de stubear una función interna del router (no sabemos
qué nombre tendrá tras T019 — ``parse_results_document`` reemplaza al
parser hoy stubeado como ``_parse_results_with_timeout``), estos tests
suben PDFs sintéticos REALES generados con
``tests/helpers/results_pdf_builder.py`` a través del endpoint público
``/parse``. Esto mantiene los tests acoplados solo al contrato HTTP, no a
detalles internos del router que T019 todavía no ha decidido. Requiere
WeasyPrint — anteponer ``DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`` al
comando de pytest en este Mac.

Fixtures de auth/DB duplicadas de ``test_race_imports.py`` a propósito
(convención ya establecida en ``test_race_imports_revision.py``: "los
duplicamos aquí para evitar acoplamiento").
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
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
from app.models.audit_log import AuditLog
from app.models.race_import import RaceImport, RaceImportKind, RaceImportStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole
from tests.helpers.audit_tables import AUDIT_TABLES
from tests.helpers.results_pdf_builder import (
    CategorySpec,
    FakeNameGenerator,
    RowSpec,
    build_results_pdf,
    sequential_category,
)

_IMPORTS_URL = "/api/race-analysis/imports"


# ---------------------------------------------------------------------------
# Fixtures de auth/DB (duplicadas de test_race_imports.py)
# ---------------------------------------------------------------------------


def _make_user(
    role: UserRole, user_id: int, club_ids: tuple[int, ...] = (1,)
) -> SimpleNamespace:
    from app.models.club import ClubRole as _ClubRole

    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"{role.value}{user_id}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[
            SimpleNamespace(club_id=cid, role_in_club=_ClubRole.coach)
            for cid in club_ids
        ],
    )


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncEngine:
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
            # `/parse` resuelve `mapping_kind` por categoría contra el
            # catálogo (``RaceCategory.is_active``, research R-03) — mismo
            # patrón de tablas que ``tests/routers/test_race_imports.py``.
            "race_categories",
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
async def seed_test_data(db_session_factory):
    async with db_session_factory() as session:
        coach1 = User(
            id=10, email="coach10@test.com", hashed_password="x",
            first_name="Coach", last_name="Ten",
            role=UserRole.coach, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        series = RaceSeries(
            id=1, name="Copa Valle de Ciclomontañismo", season_year=2026,
            organizer="Liga Vallecaucana", points_scheme_code="copa_valle_2026",
        )
        session.add_all([coach1, series])
        await session.commit()
    yield


async def _seed_club_membership(
    db_session_factory, *, user_id: int, club_id: int = 1
) -> None:
    from app.models.club import Club, ClubMember, ClubRole

    async with db_session_factory() as session:
        session.add(Club(id=club_id, name=f"Club {club_id}", code=f"C{club_id}"))
        await session.flush()
        session.add(
            ClubMember(club_id=club_id, user_id=user_id, role_in_club=ClubRole.coach)
        )
        await session.commit()


@pytest.fixture
def override_storage(monkeypatch, tmp_path):
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


def _client_fixture_factory(role: UserRole, user_id: int, club_ids: tuple[int, ...] = (1,)):
    @pytest_asyncio.fixture
    async def _client(sqlite_engine, db_session_factory, seed_test_data, override_storage):
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
            role, user_id=user_id, club_ids=club_ids
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
        app.dependency_overrides.clear()

    return _client


coach_client = _client_fixture_factory(UserRole.coach, 10, (1,))
coach_otro_club_client = _client_fixture_factory(UserRole.coach, 20, (2,))
admin_client = _client_fixture_factory(UserRole.admin, 1)
parent_client = _client_fixture_factory(UserRole.parent, 5)
athlete_client = _client_fixture_factory(UserRole.athlete, 6)


@pytest_asyncio.fixture
async def anon_client(sqlite_engine, db_session_factory, override_storage):
    async def _override_db():
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers de upload
# ---------------------------------------------------------------------------


def _parse_form(**overrides) -> dict:
    form = {
        "series_name": "Copa Valle",
        "season": "2026",
        "valida_num": "4",
        "event_name": "VALIDA IV CALI",
        "event_date": "2026-05-17",
        "location": "CALI",
    }
    form.update({k: str(v) for k, v in overrides.items()})
    return form


def _build_pdf(tmp_path: Path, categories: list[CategorySpec]) -> bytes:
    path = build_results_pdf(
        tmp_path / "sintetico.pdf",
        valida_num=8,
        location="Ciudad Ficticia",
        event_date=date(2025, 8, 9),
        categories=categories,
        name_generator=FakeNameGenerator(),
    )
    return path.read_bytes()


async def _parse_pdf(client, tmp_path: Path, categories: list[CategorySpec]) -> dict:
    pdf_bytes = _build_pdf(tmp_path, categories)
    files = {"resultados_pdf": ("resultados.pdf", pdf_bytes, "application/pdf")}
    r = await client.post(f"{_IMPORTS_URL}/parse", data=_parse_form(), files=files)
    assert r.status_code == 200, r.text
    return r.json()


def _gap_category(header: str = "INFANTIL A") -> CategorySpec:
    """Categoría de 3 filas, ordinales [1,2,4] — falta el 3 (R-05)."""
    cat = sequential_category(header, 3)
    for i, row in enumerate(cat.rows, start=1):
        row.bib = str(800 + i)
    cat.rows[2].position = 4  # la 3ra fila queda como ordinal 4, no 3
    return cat


# ===========================================================================
# POST /parse — categories[] + completeness + unreadable_rows
# ===========================================================================


class TestParseReturnsCategoriesAndCompleteness:
    @pytest.mark.asyncio
    async def test_parse_response_has_categories_and_unreadable_rows(
        self, coach_client, tmp_path: Path
    ):
        known_ok = sequential_category("INFANTIL A", 3)
        for i, row in enumerate(known_ok.rows, start=1):
            row.bib = str(700 + i)
        known_ok.rows[1].long_club = True  # defecto real R-01, debe recuperarse

        known_inconsistent = sequential_category("PREJUVENIL A FEMENINO", 4)
        for i, row in enumerate(known_inconsistent.rows, start=1):
            row.bib = str(750 + i)
        # Duplica el 2 (posiciones impresas: 1, 2, 3, 2). El tope de `missing`
        # se recorta al ordinal más alto REALMENTE impreso (research R-05,
        # docstring de `completeness.check_completeness`) para no inventar un
        # "falta el 4" fantasma que la cola desplazada por el duplicado nunca
        # imprimió — mismo caso que el ejemplo `[1, 2, 2, 3, 4]` del módulo.
        known_inconsistent.rows[3].position = 2

        unknown = CategorySpec(
            header="SUPER ELITE COSMICO",
            rows=[
                RowSpec(position=1, bib="601", time_raw="0:20:00", points=50),
                RowSpec(position=2, bib="602", time_raw="0:21:00", points=45),
            ],
        )

        data = await _parse_pdf(
            coach_client, tmp_path, [known_ok, known_inconsistent, unknown]
        )

        assert "categories" in data, "respuesta de /parse sin campo categories[] (T019 pendiente)"
        assert "unreadable_rows" in data
        assert data["unreadable_rows"] == []

        cats = {c["header_raw"]: c for c in data["categories"]}

        assert cats["INFANTIL A"]["code"] == "INF_A"
        assert len(cats["INFANTIL A"]["rows"]) == 3
        assert cats["INFANTIL A"]["completeness"]["status"] == "ok"

        assert cats["PREJUVENIL A FEMENINO"]["code"] == "PJUV_A_F"
        assert cats["PREJUVENIL A FEMENINO"]["completeness"]["status"] == "inconsistent"
        assert cats["PREJUVENIL A FEMENINO"]["completeness"]["missing"] == []
        assert cats["PREJUVENIL A FEMENINO"]["completeness"]["duplicated"] == [2]

        # Categoría desconocida: se conserva CON sus filas, no se descarta.
        assert cats["SUPER ELITE COSMICO"]["code"] is None
        assert len(cats["SUPER ELITE COSMICO"]["rows"]) == 2


# ===========================================================================
# POST /{id}/corrections — levanta el bloqueo
# ===========================================================================


class TestCorrectionsEndpoint:
    @pytest.mark.asyncio
    async def test_correction_add_lifts_the_block(self, coach_client, tmp_path: Path):
        data = await _parse_pdf(coach_client, tmp_path, [_gap_category()])
        parse_id = data["parse_id"]
        assert "categories" in data, "respuesta de /parse sin campo categories[] (T019 pendiente)"
        cats = {c["header_raw"]: c for c in data["categories"]}
        assert cats["INFANTIL A"]["completeness"]["status"] == "inconsistent"
        assert cats["INFANTIL A"]["completeness"]["missing"] == [3]

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/corrections",
            json={
                "op": "add",
                "category_header": "INFANTIL A",
                "ordinal": 3,
                "row": {
                    "position": 3, "bib": "899", "name": "Nombre Ficticio",
                    "city": "Ciudad Ficticia", "club": "Club Ficticio",
                    "time_raw": "0:12:00", "points": 8,
                },
            },
        )
        assert r.status_code == 200, r.text
        completeness = r.json()["completeness"]
        assert completeness["status"] == "ok"
        assert completeness["missing"] == []

    @pytest.mark.asyncio
    async def test_correction_unknown_category_returns_422(
        self, coach_client, tmp_path: Path
    ):
        data = await _parse_pdf(coach_client, tmp_path, [_gap_category()])
        parse_id = data["parse_id"]

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/corrections",
            json={
                "op": "add",
                "category_header": "CATEGORIA QUE NO EXISTE",
                "ordinal": 1,
                "row": {
                    "position": 1, "bib": "1", "name": "X", "city": "Y",
                    "club": "Z", "time_raw": "0:10:00", "points": 1,
                },
            },
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_correction_add_without_position_returns_422(
        self, coach_client, tmp_path: Path
    ):
        """Una fila ``add``/``edit`` sin ``position`` desaparecería en
        silencio de ``check_completeness`` (que solo mira filas con
        ``position``) — la categoría podría quedar reportada ``ok`` con la
        fila corregida sin contar para nada. El borde HTTP la rechaza antes
        de llegar a ``apply_corrections``.
        """
        data = await _parse_pdf(coach_client, tmp_path, [_gap_category()])
        parse_id = data["parse_id"]

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/corrections",
            json={
                "op": "add",
                "category_header": "INFANTIL A",
                "ordinal": 3,
                "row": {
                    # `position` omitido a propósito.
                    "bib": "899", "name": "Nombre Ficticio",
                    "city": "Ciudad Ficticia", "club": "Club Ficticio",
                    "time_raw": "0:12:00", "points": 8,
                },
            },
        )
        assert r.status_code == 422
        assert "position" in r.text.lower()

    @pytest.mark.asyncio
    async def test_correction_edit_with_null_position_returns_422(
        self, coach_client, tmp_path: Path
    ):
        """Mismo hueco que arriba pero con ``op=edit`` y ``position`` enviado
        explícitamente en ``null`` (en vez de omitido) — ambas formas deben
        rechazarse igual."""
        data = await _parse_pdf(coach_client, tmp_path, [_gap_category()])
        parse_id = data["parse_id"]

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/corrections",
            json={
                "op": "edit",
                "category_header": "INFANTIL A",
                "ordinal": 1,
                "row": {
                    "position": None, "bib": "700", "name": "Nombre Ficticio",
                    "city": "Ciudad Ficticia", "club": "Club Ficticio",
                    "time_raw": "0:12:00", "points": 8,
                },
            },
        )
        assert r.status_code == 422
        assert "position" in r.text.lower()

    @pytest.mark.asyncio
    async def test_correction_with_position_still_lifts_the_block(
        self, coach_client, tmp_path: Path
    ):
        """Regresión de la validación nueva: una corrección `add` que SÍ
        trae `position` sigue funcionando igual que antes y sigue cerrando
        el hueco de completitud (mismo caso que
        ``test_correction_add_lifts_the_block``, aquí explícito para dejar
        el contraste con los dos 422 de arriba)."""
        data = await _parse_pdf(coach_client, tmp_path, [_gap_category()])
        parse_id = data["parse_id"]

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/corrections",
            json={
                "op": "add",
                "category_header": "INFANTIL A",
                "ordinal": 3,
                "row": {
                    "position": 3, "bib": "899", "name": "Nombre Ficticio",
                    "city": "Ciudad Ficticia", "club": "Club Ficticio",
                    "time_raw": "0:12:00", "points": 8,
                },
            },
        )
        assert r.status_code == 200, r.text
        completeness = r.json()["completeness"]
        assert completeness["status"] == "ok"
        assert completeness["missing"] == []


# ===========================================================================
# POST /{id}/acknowledge — catálogo cerrado + auditoría
# ===========================================================================


class TestAcknowledgeEndpoint:
    @pytest.mark.asyncio
    async def test_acknowledge_with_catalogue_reason_is_audited(
        self, coach_client, tmp_path: Path, db_session_factory
    ):
        data = await _parse_pdf(coach_client, tmp_path, [_gap_category()])
        parse_id = data["parse_id"]

        async with db_session_factory() as session:
            before = (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.entity_type == "race_import",
                        AuditLog.entity_id == parse_id,
                    )
                )
            ).scalars().all()

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/acknowledge",
            json={
                "category_header": "INFANTIL A",
                "reason": "source_missing_ordinal",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["completeness"]["status"] == "acknowledged"

        async with db_session_factory() as session:
            after = (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.entity_type == "race_import",
                        AuditLog.entity_id == parse_id,
                    )
                )
            ).scalars().all()

        assert len(after) > len(before), (
            "esperaba una fila nueva en audit_log (entity_type=race_import) "
            "tras el acknowledge — record_audit (R-05)"
        )
        assert any(row.actor_user_id == 10 for row in after)

    @pytest.mark.asyncio
    async def test_acknowledge_unknown_reason_returns_422(
        self, coach_client, tmp_path: Path
    ):
        data = await _parse_pdf(coach_client, tmp_path, [_gap_category()])
        parse_id = data["parse_id"]

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/acknowledge",
            json={"category_header": "INFANTIL A", "reason": "motivo_inventado"},
        )
        assert r.status_code == 422


# ===========================================================================
# GET /acknowledge-reasons — catálogo cerrado
# ===========================================================================


class TestAcknowledgeReasonsCatalogue:
    @pytest.mark.asyncio
    async def test_lists_the_closed_catalogue(self, coach_client):
        r = await coach_client.get(f"{_IMPORTS_URL}/acknowledge-reasons")
        assert r.status_code == 200, r.text
        options = r.json()["options"]
        codes = {o["code"] for o in options}
        assert codes == {
            "source_duplicate_ordinal",
            "source_missing_ordinal",
            "source_disqualification_gap",
            "verified_against_source",
        }
        assert all(o["label"] for o in options)

    @pytest.mark.asyncio
    async def test_parent_forbidden(self, parent_client):
        r = await parent_client.get(f"{_IMPORTS_URL}/acknowledge-reasons")
        assert r.status_code == 403


# ===========================================================================
# Rutas denegadas — padre 403, deportista 403, coach de otro club 403
# ===========================================================================


_VALID_CORRECTION_BODY = {
    "op": "add",
    "category_header": "INFANTIL A",
    "ordinal": 1,
    "row": {
        "position": 1, "bib": "1", "name": "X", "city": "Y",
        "club": "Z", "time_raw": "0:10:00", "points": 1,
    },
}
_VALID_ACKNOWLEDGE_BODY = {
    "category_header": "INFANTIL A",
    "reason": "source_missing_ordinal",
}


class TestDeniedPaths:
    @pytest.mark.asyncio
    async def test_parent_forbidden_on_corrections(self, parent_client):
        r = await parent_client.post(
            f"{_IMPORTS_URL}/9999/corrections", json=_VALID_CORRECTION_BODY
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_athlete_forbidden_on_corrections(self, athlete_client):
        r = await athlete_client.post(
            f"{_IMPORTS_URL}/9999/corrections", json=_VALID_CORRECTION_BODY
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_parent_forbidden_on_acknowledge(self, parent_client):
        r = await parent_client.post(
            f"{_IMPORTS_URL}/9999/acknowledge", json=_VALID_ACKNOWLEDGE_BODY
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_athlete_forbidden_on_acknowledge(self, athlete_client):
        r = await athlete_client.post(
            f"{_IMPORTS_URL}/9999/acknowledge", json=_VALID_ACKNOWLEDGE_BODY
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_coach_de_otro_club_forbidden_on_corrections(
        self, coach_otro_club_client, db_session_factory
    ):
        """coach20 (club 2) contra un cargue de coach10 (club 1) -> 403."""
        await _seed_club_membership(db_session_factory, user_id=10, club_id=1)
        async with db_session_factory() as session:
            imp = RaceImport(
                filename="x.pdf", sha256="d" * 64, series_id=1,
                status=RaceImportStatus.pending, stats_json={},
                imported_by_user_id=10,
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados,
                parse_meta_json={"categories": []},
            )
            session.add(imp)
            await session.commit()
            pid = imp.id

        r = await coach_otro_club_client.post(
            f"{_IMPORTS_URL}/{pid}/corrections", json=_VALID_CORRECTION_BODY
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_coach_de_otro_club_forbidden_on_acknowledge(
        self, coach_otro_club_client, db_session_factory
    ):
        await _seed_club_membership(db_session_factory, user_id=10, club_id=1)
        async with db_session_factory() as session:
            imp = RaceImport(
                filename="x.pdf", sha256="e" * 64, series_id=1,
                status=RaceImportStatus.pending, stats_json={},
                imported_by_user_id=10,
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados,
                parse_meta_json={"categories": []},
            )
            session.add(imp)
            await session.commit()
            pid = imp.id

        r = await coach_otro_club_client.post(
            f"{_IMPORTS_URL}/{pid}/acknowledge", json=_VALID_ACKNOWLEDGE_BODY
        )
        assert r.status_code == 403
