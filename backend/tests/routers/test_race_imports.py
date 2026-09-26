"""Tests del router ``/api/race-analysis/imports/*`` (F-UP3).

Estrategia: stub mínimo del service layer + DB SQLite in-memory para los
endpoints `/dry-run`, `/commit`, `/` y un stub-storage in-memory para los PDFs.

Amendment 2026-09-26 (contracts/staged-import.md): ``POST /parse`` se retiró
— la web app solo revisa y comitea, nunca sube (FR-044). Un ``RaceImport``
pending para dry-run/commit se staguea ahora vía ``stage_extracted_results``
(``tests/helpers/staging.py::stage_for_test`` / ``_stage_pending_import``),
sin HTTP ni parser real. La cobertura de mecánica de upload (magic bytes,
tamaño, extensión, dedupe de sha) vive en
``tests/services/race/test_import_staging.py``; ``tests/privacy/
test_no_results_upload.py`` prueba el 404 estructural.

Cubre los códigos HTTP del contrato (upload-design.md §4) que sí sobreviven:
- 200 happy path dry-run / commit / list
- 401 sin auth (anon)
- 403 rol parent
- 403 coach de otro club (parse_id de un cargue ajeno al club)
- 404 parse_id inexistente / ya committed
- 409 matches_unresolved (resolved_matches incompletos, feature 044 US5)
- list paginado + filter status
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.dependencies import get_db
from app.main import app
from app.models import Base
from app.models.race_import import RaceImport, RaceImportKind, RaceImportStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole
from app.services.race.import_staging import StageHeader
from app.services.race.staged_document import ParsedCategory, ParsedResults, ResultsRow
from tests.helpers.audit_tables import AUDIT_TABLES
from tests.helpers.staging import stage_for_test


# ---------------------------------------------------------------------------
# Fixture: SQLite + dependency overrides (coach/admin/parent/anon)
# ---------------------------------------------------------------------------


def _make_user(
    role: UserRole, user_id: int = 10, club_ids: tuple[int, ...] = (1,)
) -> SimpleNamespace:
    """Usuario falso con membresías de coach.

    El acceso a un cargue se decide por club y no por autoría
    (``contracts/scope-ai-imports.md`` §6.1), y ``coach_club_ids`` lee
    ``user.club_memberships`` del objeto autenticado — no la tabla. El club 1
    es el que siembran los tests que crean ``club_members``.
    """
    from app.models.club import ClubRole as _ClubRole

    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"{role.value}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[
            SimpleNamespace(club_id=cid, role_in_club=_ClubRole.coach)
            for cid in club_ids
        ],
    )


async def _seed_club_membership(
    db_session_factory, *, user_id: int, club_id: int = 1
) -> None:
    """Crea el club y la fila ``club_members`` de un coach.

    ``import_club_ids`` (§1.2) resuelve el club de un cargue leyendo la
    tabla ``club_members`` de quien lo subió — no el objeto autenticado —,
    así que sin esta fila el cargue queda sin club y decide el respaldo por
    autoría, que es justo lo que estas pruebas NO quieren ejercitar.
    """
    from app.models.club import Club, ClubMember, ClubRole

    async with db_session_factory() as session:
        session.add(Club(id=club_id, name=f"Club {club_id}", code=f"C{club_id}"))
        await session.flush()
        session.add(
            ClubMember(club_id=club_id, user_id=user_id, role_in_club=ClubRole.coach)
        )
        await session.commit()


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncEngine:
    """SQLite async in-memory con solo las tablas necesarias para race_imports.

    Usa StaticPool para que todas las conexiones compartan la misma instancia
    en memoria (de lo contrario cada conexión nueva ve DB vacío).
    """
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    # Crear subgrafo (evita LONGTEXT incompatible)
    from app.models.user import User as _U  # noqa: F401
    from app.models.club import Club as _Cl, ClubMember as _CM  # noqa: F401
    from app.models.athlete import Athlete as _A  # noqa: F401
    from app.models.race_series import RaceSeries as _S  # noqa: F401
    from app.models.race_event import RaceEvent as _E  # noqa: F401
    from app.models.race_import import RaceImport as _I  # noqa: F401
    from app.models.race_category import RaceCategory as _C  # noqa: F401
    from app.models.race_competitor import RaceCompetitor as _Comp  # noqa: F401
    from app.models.race_result import RaceResult as _R  # noqa: F401
    from app.models.race_competitor_signature import (  # noqa: F401
        RaceCompetitorSignature as _Sig,
    )
    from app.models.race_identity_candidate import (  # noqa: F401
        RaceIdentityCandidate as _IdCand,
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
            "race_import_staged_documents",
            "race_categories",
            "race_competitors",
            "race_results",
            # Feature 044 (US4, T050): el candado de identidad de /commit
            # llama identity_review.rebuild, que lee estas dos tablas incluso
            # cuando no hay ningún candidato — sin ellas el commit revienta
            # con "no such table" en vez del 200/409 que el test espera.
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
async def db_session_factory(sqlite_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def seed_test_data(db_session_factory):
    """Inserta usuarios + series base usados por todos los tests."""
    async with db_session_factory() as session:
        # Coach con id 10 (owner default), coach con id 20 (cross-coach)
        coach1 = User(
            id=10, email="coach10@test.com", hashed_password="x",
            first_name="Coach", last_name="Ten",
            role=UserRole.coach, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        coach2 = User(
            id=20, email="coach20@test.com", hashed_password="x",
            first_name="Coach", last_name="Twenty",
            role=UserRole.coach, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        admin = User(
            id=1, email="admin@test.com", hashed_password="x",
            first_name="Admin", last_name="User",
            role=UserRole.admin, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        series = RaceSeries(
            id=1, name="Copa Valle de Ciclomontañismo", season_year=2026,
            organizer="Liga Vallecaucana", points_scheme_code="copa_valle_2026",
        )
        session.add_all([coach1, coach2, admin, series])
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
    # Vaciar envs SFTP para forzar fallback
    monkeypatch.setattr(settings, "hostinger_sftp_host", "")
    monkeypatch.setattr(settings, "hostinger_sftp_user", "")
    monkeypatch.setattr(settings, "hostinger_sftp_pass", "")
    monkeypatch.setattr(settings, "hostinger_sftp_remote_dir", "")
    monkeypatch.setattr(settings, "hostinger_public_base_url", "")
    yield fake_base


@pytest.fixture
def stub_ingestor(monkeypatch):
    """Stub de RaceIngestor.ingest_event — evita interacción con la fake DB
    desde el ingestor real (tiene queries que SQLite no soporta vía Select).

    Simula el contrato del ingestor real para los efectos secundarios mínimos:
    si NO es dry_run y hay pdf_results_sha256, promueve el RaceImport pending
    a committed (como hace el ingestor real). En dry_run no toca BD.
    """
    from sqlalchemy import select
    from app.models.race_import import RaceImport, RaceImportStatus
    from app.schemas.race import IngestReport
    from app.services.race import ingestor as ingestor_mod

    state = {"calls": []}

    async def fake_ingest(self, meta, results_by_category, **kwargs):
        state["calls"].append(
            {
                "valida_num": meta.valida_num,
                "dry_run": kwargs.get("dry_run", False),
                "match_decisions": kwargs.get("match_decisions") or {},
                "sha": kwargs.get("pdf_results_sha256"),
            }
        )
        dry_run = kwargs.get("dry_run", False)
        sha = kwargs.get("pdf_results_sha256")
        # Simular promoción pending→committed cuando es commit real
        if not dry_run and sha:
            result = await self.db.execute(
                select(RaceImport).where(
                    RaceImport.sha256 == sha,
                    RaceImport.status == RaceImportStatus.pending,
                )
            )
            pending = result.scalar_one_or_none()
            if pending is not None:
                pending.status = RaceImportStatus.committed
                pending.stats_json = {
                    "results_inserted": 2,
                    "tyr_count": 1,
                }
                await self.db.flush()
        return IngestReport(
            event_id=100,
            series_id=1,
            competitors_created=5,
            competitors_updated=0,
            results_inserted=2,
            results_skipped=0,
            tyr_count=1,
            warnings=[],
        )

    monkeypatch.setattr(
        ingestor_mod.RaceIngestor, "ingest_event", fake_ingest
    )
    return state


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
    # Override require_role para devolver coach10

    # require_role devuelve callables, los overrideamos por la callable retornada
    # haciendo monkey-patch del dependency creator directamente desde el módulo.
    # Mejor: override get_current_user + require_role retorna current_user.
    from app.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.coach, user_id=10
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def coach2_client(
    sqlite_engine, db_session_factory, seed_test_data, override_storage
):
    """Cliente coach id=20 — usado para los tests de acceso entre coaches."""
    async def _override_db():
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    from app.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.coach, user_id=20
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def coach_otro_club_client(
    sqlite_engine, db_session_factory, seed_test_data, override_storage
):
    """Cliente coach id=20 pero con membresía en el club 2.

    Es el reverso de ``coach2_client``: mismo rol, otro club. Con él, el 403
    prueba la regla de club de ``contracts/scope-ai-imports.md`` §1.4 y no un
    conjunto de membresías vacío.
    """
    async def _override_db():
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    from app.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.coach, user_id=20, club_ids=(2,)
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_client(
    sqlite_engine, db_session_factory, seed_test_data, override_storage
):
    """Cliente admin id=1."""
    async def _override_db():
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    from app.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.admin, user_id=1
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def parent_client(
    sqlite_engine, db_session_factory, seed_test_data, override_storage
):
    """Cliente parent id=5 — debe ser bloqueado."""
    async def _override_db():
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    from app.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.parent, user_id=5
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def anon_client(sqlite_engine, db_session_factory, override_storage):
    """Cliente sin auth — NO override de get_current_user."""
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
# Helpers
# ---------------------------------------------------------------------------


#: Amendment 2026-09-26 (contracts/staged-import.md): ``POST /parse`` se
#: retiró — los tests que antes subían un PDF por multipart para dejar un
#: ``RaceImport`` pending listo para dry-run/commit ahora staguean un
#: documento ya extraído directamente vía ``stage_extracted_results``
#: (``tests/helpers/staging.py::stage_for_test``), sin tocar HTTP/parser.


from app.services.race.staged_document import StagedProfileMeta as _StagedProfileMeta

_TEST_PROFILE = _StagedProfileMeta(
    profile_id="test-race-imports-router",
    profile_sha256="1" * 64,
    engine_version="test-helper",
)


def _stub_document() -> ParsedResults:
    """Documento equivalente al que devolvía el viejo ``stub_parsers``
    (monkeypatch de ``_parse_results_with_timeout``) — mismas filas, para no
    alterar las aserciones de matcher/ingest ya existentes."""
    return ParsedResults(
        categories=[
            ParsedCategory(
                header_raw="TETEROS CON PEDALES",
                code="TET_CP",
                rows=[
                    ResultsRow(
                        position=1, bib="550", name="Sebastian Yule Mendoza",
                        city="Yumbo", club="Club Trocha y Ruta",
                        time_raw="0:03:38", points=40,
                    ),
                    ResultsRow(
                        position=2, bib="551", name="Otro Tetero",
                        city="Cali", club="Club X",
                        time_raw="0:04:00", points=36,
                    ),
                ],
            ),
        ],
        unreadable_rows=[],
    )


def _default_header(**overrides) -> StageHeader:
    from app.models.race_series import RaceSeriesKind, RaceSeriesLevel

    fields = {
        "series_name": "Copa Valle de Ciclomontañismo",
        "series_kind": RaceSeriesKind.cup,
        "series_level": RaceSeriesLevel.departmental,
        "season": 2026,
        "valida_num": 4,
        "event_name": "VALIDA IV CALI",
        "event_date": date(2026, 5, 17),
        "location": "CALI",
    }
    fields.update(overrides)
    return StageHeader(**fields)


async def _stage_pending_import(
    db_session_factory,
    *,
    document: ParsedResults | None = None,
    header: StageHeader | None = None,
    actor_id: int = 10,
) -> int:
    """Reemplaza el viejo flujo ``POST /parse`` para dejar un ``RaceImport``
    pending listo para dry-run/commit — sin HTTP ni parser real."""
    async with db_session_factory() as session:
        actor = await session.get(User, actor_id)
        result = await stage_for_test(
            session,
            document=document if document is not None else _stub_document(),
            header=header,
            actor=actor,
        )
        await session.commit()
        return result.import_id


# ===========================================================================
# Auth / RBAC
# ===========================================================================


class TestAuthRbac:
    @pytest.mark.asyncio
    async def test_anon_get_returns_401_or_403(self, anon_client):
        """Sin auth: el bearer scheme requiere credenciales."""
        r = await anon_client.get("/api/race-analysis/imports/")
        assert r.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_parent_forbidden_on_list(self, parent_client):
        r = await parent_client.get("/api/race-analysis/imports/")
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_coach_ok_on_list_empty(self, coach_client):
        r = await coach_client.get("/api/race-analysis/imports/")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert data["items"] == []


# ===========================================================================
# Staging (sucesor de POST /parse, retirado) — mecánica de sanitización
# ===========================================================================


class TestStagingSanitizesFilename:
    """El upload por multipart (``POST /parse``) se retiró (amendment
    2026-09-26, contracts/staged-import.md) — la web app solo revisa y
    comitea, nunca sube. La cobertura de mecánica de upload (magic bytes,
    tamaño, extensión, filas cero, dedupe de sha committed) vive ahora en
    ``tests/services/race/test_import_staging.py`` (T131) contra
    ``stage_extracted_results`` directamente; ``_sanitize_filename`` sigue
    viva en ese mismo servicio (no era upload-only) y se prueba aquí contra
    la llamada directa, sin HTTP."""

    @pytest.mark.asyncio
    async def test_stage_sanitizes_path_traversal_filename(
        self, db_session_factory, seed_test_data, override_storage
    ):
        """El filename ../../etc/passwd.pdf debe ser sanitizado en BD."""
        from app.services.race.import_staging import stage_extracted_results
        from app.services.request_context import AuditContext

        async with db_session_factory() as session:
            actor = await session.get(User, 10)
            result = await stage_extracted_results(
                session,
                document=_stub_document(),
                profile=_TEST_PROFILE,
                file_bytes=b"content for path traversal test",
                original_filename="../../etc/passwd.pdf",
                results_ext="pdf",
                header=_default_header(),
                actor=actor,
                ctx=AuditContext.for_user(actor, request_id="test-sanitize"),
            )
            await session.commit()
            parse_id = result.import_id

            from sqlalchemy import select as _sel
            imp = (await session.execute(
                _sel(RaceImport).where(RaceImport.id == parse_id)
            )).scalar_one()
            # Sanitizado: no debe contener "/" ni ".."
            assert "/" not in imp.filename
            assert ".." not in imp.filename
            # Original preservado para UI
            assert imp.original_filename == "../../etc/passwd.pdf"


# ===========================================================================
# POST /{parse_id}/dry-run
# ===========================================================================


class TestDryRunEndpoint:
    @pytest.mark.asyncio
    async def test_dry_run_404_unknown_parse_id(self, coach_client):
        r = await coach_client.post(
            "/api/race-analysis/imports/9999/dry-run"
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_dry_run_404_on_already_committed(
        self, coach_client, db_session_factory
    ):
        """parse_id en estado committed → 404 (no se puede dry-run)."""
        async with db_session_factory() as session:
            imp = RaceImport(
                filename="x.pdf", sha256="a" * 64, series_id=1,
                status=RaceImportStatus.committed, stats_json={},
                imported_by_user_id=10,
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados,
            )
            session.add(imp)
            await session.commit()
            pid = imp.id

        r = await coach_client.post(
            f"/api/race-analysis/imports/{pid}/dry-run"
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_dry_run_200_mismo_club_otro_coach(
        self, coach2_client, db_session_factory
    ):
        """coach20, del mismo club que coach10, sí puede hacer dry-run.

        Es el cambio central de US6 (``contracts/scope-ai-imports.md`` §6.1):
        el creator-lock desaparece y manda el club. El dry-run en sí falla
        después por falta de PDF en storage — lo que importa es que NO es 403.
        """
        await _seed_club_membership(db_session_factory, user_id=10, club_id=1)
        async with db_session_factory() as session:
            imp = RaceImport(
                filename="x.pdf", sha256="b" * 64, series_id=1,
                status=RaceImportStatus.pending, stats_json={},
                imported_by_user_id=10,  # cargado por coach10
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados,
                parse_meta_json={"header": {}, "results_ext": "pdf"},
                storage_path="/nonexistent/file.pdf",
            )
            session.add(imp)
            await session.commit()
            pid = imp.id

        r = await coach2_client.post(
            f"/api/race-analysis/imports/{pid}/dry-run"
        )
        assert r.status_code != 403, r.text

    @pytest.mark.asyncio
    async def test_dry_run_403_coach_de_otro_club(
        self, coach_otro_club_client, db_session_factory
    ):
        """coach20, coach del club 2, sobre un cargue del club 1 → 403."""
        await _seed_club_membership(db_session_factory, user_id=10, club_id=1)
        async with db_session_factory() as session:
            imp = RaceImport(
                filename="x.pdf", sha256="b" * 64, series_id=1,
                status=RaceImportStatus.pending, stats_json={},
                imported_by_user_id=10,  # cargado por coach10 (club 1)
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados,
                parse_meta_json={"header": {}},
            )
            session.add(imp)
            await session.commit()
            pid = imp.id

        r = await coach_otro_club_client.post(
            f"/api/race-analysis/imports/{pid}/dry-run"
        )
        assert r.status_code == 403
        assert "otro club" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_dry_run_admin_bypasses_ownership(
        self, admin_client, db_session_factory
    ):
        """Admin puede dry-run sobre parse de cualquier coach.

        Verificamos que pase el chequeo ownership; el dry-run en sí fallará
        después por falta de PDF en storage (410), lo cual nos confirma que
        ownership pasó OK."""
        async with db_session_factory() as session:
            imp = RaceImport(
                filename="x.pdf", sha256="c" * 64, series_id=1,
                status=RaceImportStatus.pending, stats_json={},
                imported_by_user_id=10,  # otro coach
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados,
                parse_meta_json={"header": {}, "results_ext": "pdf"},
                storage_path="/nonexistent/file.pdf",
            )
            session.add(imp)
            await session.commit()
            pid = imp.id

        r = await admin_client.post(
            f"/api/race-analysis/imports/{pid}/dry-run"
        )
        # Admin pasa ownership; falla en reload_parsed_from_storage por 410.
        assert r.status_code != 403


# ===========================================================================
# POST /{parse_id}/commit
# ===========================================================================


class TestCommitEndpoint:
    @pytest.mark.asyncio
    async def test_commit_404_unknown_parse_id(self, coach_client):
        r = await coach_client.post(
            "/api/race-analysis/imports/9999/commit",
            json={"resolved_matches": []},
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_commit_invalid_body_422(self, coach_client):
        r = await coach_client.post(
            "/api/race-analysis/imports/1/commit",
            json={"resolved_matches": [{"athlete_id": 1}]},  # falta normalized_name
        )
        assert r.status_code == 422


# ===========================================================================
# GET / — list paginado
# ===========================================================================


class TestListEndpoint:
    @pytest.mark.asyncio
    async def test_list_empty(self, coach_client):
        r = await coach_client.get("/api/race-analysis/imports/")
        assert r.status_code == 200
        assert r.json() == {"items": [], "total": 0}

    @pytest.mark.asyncio
    async def test_list_returns_seeded_imports(
        self, coach_client, db_session_factory
    ):
        async with db_session_factory() as session:
            for i in range(3):
                session.add(
                    RaceImport(
                        filename=f"r{i}.pdf",
                        original_filename=f"Resultados {i}.pdf",
                        sha256=str(i) * 64,
                        series_id=1,
                        status=RaceImportStatus.committed,
                        stats_json={"results_inserted": 200 + i},
                        imported_by_user_id=10,
                        imported_at=datetime.now(timezone.utc),
                        kind=RaceImportKind.both,
                        event_id=None,
                    )
                )
            await session.commit()

        r = await coach_client.get("/api/race-analysis/imports/")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3
        for item in data["items"]:
            assert item["uploaded_by"]["full_name"] == "Coach Ten"
            assert item["kind"] == "both"
            assert item["status"] == "committed"
            assert item["n_results"] in (200, 201, 202)

    @pytest.mark.asyncio
    async def test_list_paginated(self, coach_client, db_session_factory):
        async with db_session_factory() as session:
            for i in range(5):
                session.add(
                    RaceImport(
                        filename=f"r{i}.pdf",
                        sha256=f"{i:x}" * 32,  # 64 hex chars
                        series_id=1,
                        status=RaceImportStatus.committed,
                        stats_json={},
                        imported_by_user_id=10,
                        imported_at=datetime.now(timezone.utc),
                        kind=RaceImportKind.resultados,
                    )
                )
            await session.commit()

        r = await coach_client.get(
            "/api/race-analysis/imports/?limit=2&offset=1"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_filter_by_status(self, coach_client, db_session_factory):
        async with db_session_factory() as session:
            session.add(
                RaceImport(
                    filename="committed.pdf", sha256="a" * 64, series_id=1,
                    status=RaceImportStatus.committed, stats_json={},
                    imported_by_user_id=10,
                    imported_at=datetime.now(timezone.utc),
                    kind=RaceImportKind.resultados,
                )
            )
            session.add(
                RaceImport(
                    filename="pending.pdf", sha256="b" * 64, series_id=1,
                    status=RaceImportStatus.pending, stats_json={},
                    imported_by_user_id=10,
                    imported_at=datetime.now(timezone.utc),
                    kind=RaceImportKind.resultados,
                )
            )
            await session.commit()

        # Filtrar committed
        r = await coach_client.get(
            "/api/race-analysis/imports/?status=committed"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["status"] == "committed"

        # Filtrar pending
        r = await coach_client.get(
            "/api/race-analysis/imports/?status=pending"
        )
        assert r.status_code == 200
        assert r.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_list_400_on_invalid_status(self, coach_client):
        r = await coach_client.get(
            "/api/race-analysis/imports/?status=invalid_xx"
        )
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_list_query_limit_validation(self, coach_client):
        # limit > 100 inválido
        r = await coach_client.get("/api/race-analysis/imports/?limit=999")
        assert r.status_code == 422
        # offset negativo inválido
        r = await coach_client.get("/api/race-analysis/imports/?offset=-1")
        assert r.status_code == 422


# ===========================================================================
# Helpers y casos adicionales: sanitización + parsing edge cases
# ===========================================================================


class TestCommitValidation:
    @pytest.mark.asyncio
    async def test_commit_404_on_dry_run_status(
        self, coach_client, db_session_factory
    ):
        """status=dry_run no es pending → 404 igual que committed/failed."""
        async with db_session_factory() as session:
            imp = RaceImport(
                filename="x.pdf", sha256="d" * 64, series_id=1,
                status=RaceImportStatus.dry_run, stats_json={},
                imported_by_user_id=10,
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados,
            )
            session.add(imp)
            await session.commit()
            pid = imp.id

        r = await coach_client.post(
            f"/api/race-analysis/imports/{pid}/commit",
            json={"resolved_matches": []},
        )
        assert r.status_code == 404
        assert "pending" in r.json()["detail"].lower()


# ===========================================================================
# Full flow: parse → dry-run → commit (con stub ingestor y storage real local)
# ===========================================================================


class TestFullFlowWithStubIngestor:
    """Pruebas end-to-end del wizard usando el StubIngestor para evitar la
    interacción del ingestor real con SQLite (que rompe en queries Select)."""

    @pytest.mark.asyncio
    async def test_full_flow_parse_dryrun_commit(
        self, coach_client, stub_ingestor, db_session_factory
    ):
        # 1. Stage (reemplaza el viejo POST /parse, retirado — amendment
        # 2026-09-26)
        parse_id = await _stage_pending_import(db_session_factory)

        # 2. Dry-run (el storage_path debe existir gracias al fallback local)
        r = await coach_client.post(
            f"/api/race-analysis/imports/{parse_id}/dry-run"
        )
        assert r.status_code == 200, r.text
        dry = r.json()
        assert dry["parse_id"] == parse_id
        # 1 match TyR (Sebastian del stub) → ambiguous
        assert dry["counts"]["ambiguous"] == 1

        # 3. Commit con resolved_matches que cubre el TyR detectado
        from app.services.race.normalizer import normalize_name

        match_norm = normalize_name("Sebastian Yule Mendoza")
        r = await coach_client.post(
            f"/api/race-analysis/imports/{parse_id}/commit",
            json={
                "resolved_matches": [
                    {"competitor_normalized_name": match_norm, "athlete_id": None}
                ]
            },
        )
        assert r.status_code == 200, r.text
        commit_resp = r.json()
        assert commit_resp["parse_id"] == parse_id
        assert commit_resp["race_event_id"] == 100  # stub ingestor returns event_id=100
        assert commit_resp["n_results_inserted"] == 2

        # 4. Verificar promoción pending → committed en BD
        async with db_session_factory() as session:
            from sqlalchemy import select as _sel
            imp = (await session.execute(
                _sel(RaceImport).where(RaceImport.id == parse_id)
            )).scalar_one()
            assert imp.status == RaceImportStatus.committed
            assert imp.event_id == 100
            # parse_meta limpiado tras commit
            assert imp.parse_meta_json is None
            # storage_path movido a committed/
            assert imp.storage_path and "committed" in imp.storage_path

    @pytest.mark.asyncio
    async def test_dry_run_matcher_returns_real_confidence_and_autoconfirms(
        self, coach_client, stub_ingestor, db_session_factory
    ):
        """Cuando hay roster cargado del club del coach, el dry-run corre el
        matcher real y devuelve ``confidence > 0`` para los TyR que matchean.

        Regresión: antes el endpoint hardcodeaba ``confidence=0.0`` y
        ``is_ambiguous=True`` (MVP) — la UI siempre mostraba 0% en la columna
        Confianza.
        """
        from datetime import date as _date

        from app.models.athlete import Athlete, Sex
        from app.models.club import Club, ClubMember, ClubRole

        async with db_session_factory() as session:
            club = Club(id=1, name="Club Trocha y Ruta", code="TYR")
            session.add(club)
            session.add(
                ClubMember(club_id=1, user_id=10, role_in_club=ClubRole.coach)
            )
            athlete_user = User(
                id=500, email="sebas@test.com", hashed_password="x",
                first_name="Sebastian", last_name="Yule Mendoza",
                role=UserRole.parent, is_active=True, can_login=False,
                created_at=datetime.now(timezone.utc),
            )
            session.add(athlete_user)
            await session.flush()
            session.add(Athlete(
                id=500, user_id=500, first_name="Sebastian",
                last_name="Yule Mendoza", birth_date=_date(2012, 6, 1),
                sex=Sex.M, club_id=1, created_by=10,
            ))
            await session.commit()

        parse_id = await _stage_pending_import(db_session_factory)

        r = await coach_client.post(
            f"/api/race-analysis/imports/{parse_id}/dry-run"
        )
        assert r.status_code == 200, r.text
        dry = r.json()
        # 1 TyR row — debe matchear al atleta seeded con confidence > 0.9
        assert len(dry["matches"]) == 1
        m = dry["matches"][0]
        assert m["tyr_athlete"] is not None
        assert m["tyr_athlete"]["id"] == 500
        assert m["confidence"] > 0.9
        # Top único + score perfecto → auto-confirmado
        assert m["is_ambiguous"] is False
        assert dry["counts"]["confirmed"] == 1
        assert dry["counts"]["ambiguous"] == 0

    @pytest.mark.asyncio
    async def test_commit_missing_resolved_matches_409(
        self, coach_client, stub_ingestor, db_session_factory
    ):
        """Si el TyR detectado no tiene resolved_match → 409 matches_unresolved.

        Feature 044 (US5): antes era un 422 con `detail` como string libre;
        ahora es un código estructurado (`HistoricalLoadPage` commitea
        siempre con `resolved_matches: []` y necesita distinguir esto de
        `identity_review_pending`/`nothing_pending` para mandar al coach al
        Import Wizard).
        """
        parse_id = await _stage_pending_import(db_session_factory)

        # Commit con resolved_matches vacíos
        r = await coach_client.post(
            f"/api/race-analysis/imports/{parse_id}/commit",
            json={"resolved_matches": []},
        )
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert detail["code"] == "matches_unresolved"
        assert detail["missing_count"] >= 1

    @pytest.mark.asyncio
    async def test_download_to_tempfile_fallback_local_raises_fnf_on_missing(
        self, monkeypatch
    ):
        """download_to_tempfile en modo local lanza FileNotFoundError si el path
        no existe (equivalente al test de la capa de servicio pero desde router)."""
        from app.services.training import storage_sftp
        from app.config import settings

        # Forzar modo fallback local (sin SFTP)
        monkeypatch.setattr(settings, "hostinger_sftp_host", "")

        with pytest.raises(FileNotFoundError):
            await storage_sftp.download_to_tempfile("/nonexistent/path/r.pdf", suffix=".pdf")

    @pytest.mark.asyncio
    async def test_dry_run_returns_zero_matches_when_no_tyr(
        self, coach_client, stub_ingestor, db_session_factory
    ):
        """PDF sin atletas TyR (todos clubes externos) → 0 matches."""
        no_tyr_doc = ParsedResults(
            categories=[
                ParsedCategory(
                    header_raw="TETEROS CON PEDALES",
                    code="TET_CP",
                    rows=[
                        ResultsRow(
                            position=1, bib="999", name="External Rider",
                            city="Bogotá", club="Club Externo",
                            time_raw="0:05:00", points=30,
                        ),
                    ],
                ),
            ],
            unreadable_rows=[],
        )
        parse_id = await _stage_pending_import(db_session_factory, document=no_tyr_doc)

        # Dry-run
        r = await coach_client.post(
            f"/api/race-analysis/imports/{parse_id}/dry-run"
        )
        assert r.status_code == 200
        assert r.json()["counts"]["total"] == 0

    @pytest.mark.asyncio
    async def test_dry_run_unknown_category_returns_422(
        self, coach_client, monkeypatch, db_session_factory
    ):
        """Categoría desconocida en parsed_results → ingestor lanza ValueError
        → dry-run debe devolver HTTP 422 con detail que mencione la categoría.

        Regresión: antes del fix el ingestor propagaba ValueError sin handler
        y FastAPI devolvía HTTP 500 sin body (bug producción 2026-05-26).
        """
        from app.services.race import ingestor as ingestor_mod

        _FAKE_CODE = "XYZ_FAKE"
        unknown_cat_doc = ParsedResults(
            categories=[
                ParsedCategory(
                    header_raw=_FAKE_CODE,
                    code=_FAKE_CODE,
                    rows=[
                        ResultsRow(
                            position=1, bib="001", name="Ciclista Fantasma",
                            city="Cali", club="Club Trocha y Ruta",
                            time_raw="0:04:00", points=40,
                        ),
                    ],
                ),
            ],
            unreadable_rows=[],
        )

        # El ingestor real lanza ValueError cuando no encuentra la categoría.
        # Lo replicamos con un stub que no toca la DB pero reproduce el error.
        async def fake_ingest_raises(self, meta, results_by_category, **kwargs):
            for code in results_by_category:
                raise ValueError(
                    f"Categoría desconocida en RESULTADOS: code='{code}'"
                )

        monkeypatch.setattr(ingestor_mod.RaceIngestor, "ingest_event", fake_ingest_raises)

        parse_id = await _stage_pending_import(db_session_factory, document=unknown_cat_doc)

        # 2. Dry-run — debe devolver 422, no 500
        r = await coach_client.post(f"/api/race-analysis/imports/{parse_id}/dry-run")
        assert r.status_code == 422, (
            f"Se esperaba 422 por categoría desconocida, se obtuvo {r.status_code}: {r.text}"
        )
        detail = r.json().get("detail", "")
        assert "Categoría desconocida" in detail, (
            f"El detail debe mencionar 'Categoría desconocida', se obtuvo: {detail!r}"
        )
        assert _FAKE_CODE in detail, (
            f"El detail debe incluir el code inválido '{_FAKE_CODE}', se obtuvo: {detail!r}"
        )

    @pytest.mark.asyncio
    async def test_dry_run_session_rollback_does_not_break_response(
        self, coach_client, db_session_factory, monkeypatch
    ):
        """Regresión: el ingestor real hace `await self.db.rollback()` en
        dry_run. Esto expira todos los ORM objects de la session compartida
        (incluido `imp` cargado por el router). Acceder `imp.id` después dispara
        lazy-load en contexto async sin greenlet adapter → MissingGreenlet HTTP 500.

        El fix snapshotea `imp.id` (y otros attrs leídos post-ingest) antes de
        invocar `ingest_event`. Este test reproduce el ciclo rollback con un
        stub y verifica que la respuesta sigue trayendo `parse_id` válido.
        """
        from app.schemas.race import IngestReport
        from app.services.race import ingestor as ingestor_mod

        async def fake_ingest_with_rollback(self, meta, results_by_category, **kwargs):
            # Reproduce el comportamiento real del ingestor en dry_run.
            await self.db.rollback()
            return IngestReport(
                event_id=200,
                series_id=2,
                competitors_created=0,
                competitors_updated=0,
                results_inserted=0,
                results_skipped=0,
                tyr_count=0,
                warnings=[],
            )

        monkeypatch.setattr(
            ingestor_mod.RaceIngestor, "ingest_event", fake_ingest_with_rollback
        )

        parse_id = await _stage_pending_import(db_session_factory)

        # 2. Dry-run con rollback interno — NO debe romper con MissingGreenlet/500.
        r = await coach_client.post(f"/api/race-analysis/imports/{parse_id}/dry-run")
        assert r.status_code == 200, (
            f"Regresión: dry-run rompió tras rollback del ingestor. "
            f"status={r.status_code} body={r.text}"
        )
        body = r.json()
        assert body["parse_id"] == parse_id, (
            f"parse_id en response debe coincidir con el snapshotted, "
            f"se obtuvo {body['parse_id']!r}"
        )


# ===========================================================================
# Amendment 2026-09-26: las condiciones de carrera (climate/temperature_c/
# surface_condition/altitude_msnm/weather_notes) dejaron de ser un input del
# wizard — ``stage_extracted_results`` no las acepta (contracts/staged-
# import.md: "No conditions. parse_meta_json['conditions'] se escribe con
# cada campo null"). Los tests que cubrían su persistencia y validación se
# retiraron junto con ``POST /parse``.
# ===========================================================================


class TestCommitLocking:
    """Tests para Plan 002: serialización de commits con SELECT FOR UPDATE (diseño two-phase).

    El diseño de bloqueo es two-phase:
    1. Carga inicial con FOR UPDATE — reclama la fila brevemente.
    2. commit temprano — libera la conexión MySQL durante SFTP+parse (slow phase).
    3. Re-verificación con FOR UPDATE justo antes del ingest — si otro commit
       ganó la carrera durante el parse, _load_pending_import lanza 404.

    NOTE: SQLite (aiosqlite) silently omits FOR UPDATE from compiled SQL, so
    these tests cannot verify actual lock contention. Instead they verify the
    ORM-level plumbing: that commit calls _load_pending_import with
    for_update=True (twice) and that dry-run does NOT. Lock contention behavior
    is only exercised in production MySQL InnoDB.
    """

    @pytest.mark.asyncio
    async def test_commit_locks_import_row(
        self, coach_client, stub_ingestor, monkeypatch, db_session_factory
    ):
        """commit_import debe llamar _load_pending_import con for_update=True DOS veces.

        Diseño two-phase: carga inicial con lock → commit temprano (libera
        conexión durante SFTP+parse) → re-verificación con lock justo antes
        del ingest para rechazar commits que ganaron la carrera durante el parse.

        SQLite ignora FOR UPDATE en SQL compilado, por lo que la verificación
        se hace al nivel ORM: interceptamos _load_pending_import y registramos
        el valor de for_update en cada llamada. Ver Plan 002 §Step 5 + revisión.
        """
        from app.routers import race_imports as router_mod
        from app.services.race.normalizer import normalize_name

        parse_id = await _stage_pending_import(db_session_factory)

        # Spy: wrap _load_pending_import para capturar el kwarg for_update
        calls: list[dict] = []
        _original = router_mod._load_pending_import

        async def _spy(db, pid, user, *, for_update=False):
            calls.append({"for_update": for_update})
            return await _original(db, pid, user, for_update=for_update)

        monkeypatch.setattr(router_mod, "_load_pending_import", _spy)

        match_norm = normalize_name("Sebastian Yule Mendoza")
        r = await coach_client.post(
            f"/api/race-analysis/imports/{parse_id}/commit",
            json={
                "resolved_matches": [
                    {"competitor_normalized_name": match_norm, "athlete_id": None}
                ]
            },
        )
        assert r.status_code == 200, r.text
        assert len(calls) >= 2 and all(c["for_update"] is True for c in calls), (
            f"Expected >= 2 calls all with for_update=True (two-phase lock), got {calls}"
        )

    @pytest.mark.asyncio
    async def test_dry_run_does_not_lock(
        self, coach_client, stub_ingestor, monkeypatch, db_session_factory
    ):
        """dry_run_import NO debe solicitar el lock (for_update=False).

        Un dry-run con lock bloquearía un commit concurrente durante el tiempo
        de descarga + parseo del PDF (hasta 30s). Plan 002 §Critical nuance.
        """
        from app.routers import race_imports as router_mod

        parse_id = await _stage_pending_import(db_session_factory)

        calls: list[dict] = []
        _original = router_mod._load_pending_import

        async def _spy(db, pid, user, *, for_update=False):
            calls.append({"for_update": for_update})
            return await _original(db, pid, user, for_update=for_update)

        monkeypatch.setattr(router_mod, "_load_pending_import", _spy)

        r = await coach_client.post(
            f"/api/race-analysis/imports/{parse_id}/dry-run"
        )
        assert r.status_code == 200, r.text
        assert len(calls) >= 1, "dry-run did not call _load_pending_import"
        assert calls[0]["for_update"] is False, (
            f"dry-run must NOT request FOR UPDATE lock, got {calls[0]}"
        )

    @pytest.mark.asyncio
    async def test_commit_integrity_error_returns_409(
        self, coach_client, monkeypatch, db_session_factory
    ):
        """Se ingest_event lanza IntegrityError, commit_import debe retornar 409
        con el mensaje de conflicto en español.

        Cubre el caso de dos imports distintos para el mismo evento/categorías
        que escaparían al lock (solo serializa el mismo parse_id).
        """
        from sqlalchemy.exc import IntegrityError as SAIntegrityError
        from app.services.race import ingestor as ingestor_mod

        parse_id = await _stage_pending_import(db_session_factory)

        # Monkeypatch ingestor para lanzar IntegrityError
        async def _raise_integrity(self, meta, results_by_category, **kwargs):
            raise SAIntegrityError("stmt", {}, Exception("dup key"))

        monkeypatch.setattr(
            ingestor_mod.RaceIngestor, "ingest_event", _raise_integrity
        )

        from app.services.race.normalizer import normalize_name
        match_norm = normalize_name("Sebastian Yule Mendoza")
        r = await coach_client.post(
            f"/api/race-analysis/imports/{parse_id}/commit",
            json={
                "resolved_matches": [
                    {"competitor_normalized_name": match_norm, "athlete_id": None}
                ]
            },
        )
        assert r.status_code == 409, r.text
        detail = r.json()["detail"]
        assert "ya fueron registrados" in detail, (
            f"Expected Spanish conflict message, got: {detail}"
        )

    @pytest.mark.asyncio
    async def test_second_commit_after_committed_is_rejected(
        self, coach_client, stub_ingestor, db_session_factory
    ):
        """Un segundo commit sobre el mismo parse_id (ya committed) debe
        retornar 404 con el mensaje 'no está en estado pending'.

        Verifica que el contrato existente se preserva: cuando el segundo
        request adquiere el lock tras el primero, re-lee status=committed y
        _load_pending_import lanza HTTPException 404.
        """
        from app.services.race.normalizer import normalize_name

        parse_id = await _stage_pending_import(db_session_factory)

        match_norm = normalize_name("Sebastian Yule Mendoza")
        commit_body = {
            "resolved_matches": [
                {"competitor_normalized_name": match_norm, "athlete_id": None}
            ]
        }

        # 2. First commit — should succeed
        r = await coach_client.post(
            f"/api/race-analysis/imports/{parse_id}/commit",
            json=commit_body,
        )
        assert r.status_code == 200, r.text

        # 3. Second commit — must be rejected with 404 (no longer pending)
        r = await coach_client.post(
            f"/api/race-analysis/imports/{parse_id}/commit",
            json=commit_body,
        )
        assert r.status_code == 404, r.text
        detail = r.json()["detail"]
        assert "no está en estado pending" in detail, (
            f"Expected 'no está en estado pending' in detail, got: {detail}"
        )

    @pytest.mark.asyncio
    async def test_commit_recheck_rejects_when_no_longer_pending(
        self, coach_client, monkeypatch, db_session_factory
    ):
        """La re-verificación two-phase rechaza el commit si el import ya no es pending.

        Simula la carrera perdida: entre la carga inicial y el ingest, otra
        operación marcó el import como committed. El spy sobre
        _load_pending_import cambia el status a committed en la DB justo antes
        de la segunda llamada (re-verificación), forzando que ésta lance 404.
        Se verifica también que RaceIngestor.ingest_event NUNCA fue invocado.
        """
        from app.models.race_import import RaceImportStatus
        from app.routers import race_imports as router_mod
        from app.services.race import ingestor as ingestor_mod
        from app.services.race.normalizer import normalize_name

        parse_id = await _stage_pending_import(db_session_factory)

        # 2. Spy: on the SECOND call (re-check), flip status to committed so
        #    _load_pending_import raises 404 (no longer pending).
        call_count = {"n": 0}
        _original = router_mod._load_pending_import

        async def _spy_flip(db, pid, user, *, for_update=False):
            call_count["n"] += 1
            if call_count["n"] >= 2 and for_update:
                # Simulate the lost race: mark the row as committed before the
                # original loader reads it — _load_pending_import will then
                # raise HTTPException 404 because status != pending.
                from sqlalchemy import update as sa_update
                from app.models.race_import import RaceImport as RaceImportModel
                await db.execute(
                    sa_update(RaceImportModel)
                    .where(RaceImportModel.id == pid)
                    .values(status=RaceImportStatus.committed)
                )
                await db.commit()
            return await _original(db, pid, user, for_update=for_update)

        monkeypatch.setattr(router_mod, "_load_pending_import", _spy_flip)

        # 3. Recorder for ingest_event — must never be called
        ingest_called = {"n": 0}

        async def _recorder(self, meta, results_by_category, **kwargs):
            ingest_called["n"] += 1
            raise AssertionError("ingest_event must not be called after failed recheck")

        monkeypatch.setattr(ingestor_mod.RaceIngestor, "ingest_event", _recorder)

        match_norm = normalize_name("Sebastian Yule Mendoza")
        r = await coach_client.post(
            f"/api/race-analysis/imports/{parse_id}/commit",
            json={
                "resolved_matches": [
                    {"competitor_normalized_name": match_norm, "athlete_id": None}
                ]
            },
        )
        assert r.status_code == 404, (
            f"Expected 404 when import no longer pending at recheck, got {r.status_code}: {r.text}"
        )
        assert "no está en estado pending" in r.json()["detail"], r.json()
        assert ingest_called["n"] == 0, "ingest_event was called despite failed recheck"


# ===========================================================================
# GET /{import_id} y POST /{import_id}/discard (feature 045, US3, T025/T026)
# ===========================================================================

_IMPORTS = "/api/race-analysis/imports"

#: Claves de ``parse_meta_json`` que el GET nunca devuelve: rutas internas de
#: storage y el identificador que las arma, y las correcciones manuales, cuyas
#: filas llevan nombre/club/ciudad de un menor (misma sensibilidad que
#: ``race_competitors``).
_INTERNAL_META_KEYS = (
    "results_storage_path",
    "general_storage_path",
    "parse_uuid",
    "results_ext",
    "corrections",
)


def _wizard_meta() -> dict:
    return {
        "header": {
            "series_name": "Copa Valle",
            "season": 2024,
            "valida_num": 3,
            "event_name": "VALIDA III PALMIRA",
            "event_date": "2024-06-14",
            "location": "Palmira",
        },
        "conditions": {"climate": None, "surface_condition": None},
        "categories_found": ["INF_A_F"],
        "n_rows_resultados": 3,
        "n_rows_general": None,
        "categories": [
            {
                "header_raw": "INFANTIL A",
                "code": "INF_A_F",
                "mapping_kind": "exact",
                "rows": 3,
                "completeness": {"status": "ok", "missing": [], "duplicated": []},
            }
        ],
        "unreadable_rows": [],
        "acknowledged": [],
        "pending_categories": [],
        # --- internas: no deben salir ---
        "results_storage_path": "race-imports/pending/uuid-1/resultados.pdf",
        "general_storage_path": None,
        "parse_uuid": "uuid-1",
        "results_ext": "pdf",
        "corrections": [{"op": "add", "row": {"name": "Nombre Ficticio Uno"}, "by": 10}],
    }


async def _seed_import(
    db_session_factory,
    *,
    status: RaceImportStatus = RaceImportStatus.pending,
    sha: str = "d" * 64,
    uploader_id: int = 10,
    **extra: Any,
) -> int:
    fields: dict[str, Any] = dict(
        filename="resultados.pdf",
        original_filename="Resultados III.pdf",
        sha256=sha,
        series_id=1,
        status=status,
        stats_json={},
        imported_by_user_id=uploader_id,
        imported_at=datetime.now(timezone.utc),
        kind=RaceImportKind.resultados,
        parse_meta_json=_wizard_meta(),
    )
    fields.update(extra)
    async with db_session_factory() as session:
        imp = RaceImport(**fields)
        session.add(imp)
        await session.commit()
        return imp.id


async def _status_of(db_session_factory, import_id: int) -> RaceImportStatus:
    from sqlalchemy import select

    async with db_session_factory() as session:
        return (
            await session.execute(
                select(RaceImport.status).where(RaceImport.id == import_id)
            )
        ).scalar_one()


async def _audit_rows(db_session_factory) -> list:
    from sqlalchemy import select

    from app.models.audit_log import AuditLog

    async with db_session_factory() as session:
        return list((await session.execute(select(AuditLog))).scalars().all())


class TestGetImportEndpoint:
    @pytest.mark.asyncio
    async def test_coach_gets_the_import_to_rehydrate_the_wizard(
        self, coach_client, db_session_factory
    ):
        import_id = await _seed_import(db_session_factory)

        r = await coach_client.get(f"{_IMPORTS}/{import_id}")

        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body) == {
            "id", "status", "source_filename", "parse_meta", "created_at", "event_id", "season",
            "parent_committed_at", "restage_required",
        }
        assert body["id"] == import_id
        assert body["status"] == "pending"
        assert body["source_filename"] == "Resultados III.pdf"
        assert body["event_id"] is None
        assert body["season"] == 2024  # de parse_meta.header
        meta = body["parse_meta"]
        assert meta["header"]["valida_num"] == 3
        assert meta["categories"][0]["header_raw"] == "INFANTIL A"
        assert meta["pending_categories"] == []

    @pytest.mark.asyncio
    async def test_parse_meta_omits_storage_paths_and_manual_corrections(
        self, coach_client, db_session_factory
    ):
        import_id = await _seed_import(db_session_factory)

        r = await coach_client.get(f"{_IMPORTS}/{import_id}")

        meta = r.json()["parse_meta"]
        for key in _INTERNAL_META_KEYS:
            assert key not in meta, key
        assert "Nombre Ficticio Uno" not in r.text

    @pytest.mark.asyncio
    async def test_committed_import_without_meta_resolves_season_from_its_event(
        self, coach_client, db_session_factory
    ):
        from datetime import date

        from app.models.race_event import RaceEvent, RaceEventStatus

        async with db_session_factory() as session:
            event = RaceEvent(
                series_id=1, sequence_number=4, name="VALIDA IV CALI",
                event_date=date(2026, 5, 17), location="CALI",
                is_championship=False, status=RaceEventStatus.COMPLETED,
                created_by_user_id=10,
            )
            session.add(event)
            await session.commit()
            event_id = event.id
        import_id = await _seed_import(
            db_session_factory,
            status=RaceImportStatus.committed,
            parse_meta_json=None,
            event_id=event_id,
        )

        r = await coach_client.get(f"{_IMPORTS}/{import_id}")

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["parse_meta"] is None
        assert body["event_id"] == event_id
        assert body["season"] == 2026  # de race_series.season_year

    @staticmethod
    async def _seed_committed_valida(db_session_factory, committed_at: datetime) -> int:
        """Válida III de la serie 1 ya confirmada (``event`` + import
        ``committed``): la carga ``pending`` que la vuelve a subir es una
        revisión. Devuelve el ``event_id``."""
        from datetime import date

        from app.models.race_event import RaceEvent, RaceEventStatus

        async with db_session_factory() as session:
            event = RaceEvent(
                series_id=1, sequence_number=3, name="VALIDA III PALMIRA",
                event_date=date(2024, 6, 14), location="PALMIRA",
                is_championship=False, status=RaceEventStatus.COMPLETED,
                created_by_user_id=10,
            )
            session.add(event)
            await session.commit()
            event_id = event.id
        await _seed_import(
            db_session_factory,
            status=RaceImportStatus.committed,
            sha="e" * 64,
            parse_meta_json=None,
            event_id=event_id,
            imported_at=committed_at,
        )
        return event_id

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "start", [RaceImportStatus.pending, RaceImportStatus.dry_run]
    )
    async def test_staged_revision_reports_when_its_parent_was_committed(
        self, coach_client, db_session_factory, start
    ):
        """Mismo dato que ``ImportParseResponse.parent_committed_at``: el
        wizard retomado lo necesita para el aviso «ya fue importada el …»."""
        await self._seed_committed_valida(db_session_factory, datetime(2024, 6, 20, 18, 42))
        import_id = await _seed_import(db_session_factory, status=start)

        r = await coach_client.get(f"{_IMPORTS}/{import_id}")

        assert r.status_code == 200, r.text
        assert r.json()["parent_committed_at"].startswith("2024-06-20T18:42")

    @pytest.mark.asyncio
    async def test_first_import_of_a_valida_has_no_parent_committed_at(
        self, coach_client, db_session_factory
    ):
        import_id = await _seed_import(db_session_factory)

        r = await coach_client.get(f"{_IMPORTS}/{import_id}")

        assert r.status_code == 200, r.text
        assert r.json()["parent_committed_at"] is None

    @pytest.mark.asyncio
    async def test_committed_import_is_never_its_own_parent(
        self, coach_client, db_session_factory
    ):
        """Un import confirmado a medias conserva su ``header`` (US5) y su
        evento: ``detect_revision`` lo encontraría a él mismo como «previo»."""
        event_id = await self._seed_committed_valida(
            db_session_factory, datetime(2024, 6, 20, 18, 42)
        )
        import_id = await _seed_import(
            db_session_factory,
            status=RaceImportStatus.committed,
            sha="f" * 64,
            event_id=event_id,
        )

        r = await coach_client.get(f"{_IMPORTS}/{import_id}")

        assert r.status_code == 200, r.text
        assert r.json()["parent_committed_at"] is None

    @pytest.mark.asyncio
    async def test_discard_response_carries_no_parent_committed_at(
        self, coach_client, db_session_factory
    ):
        await self._seed_committed_valida(db_session_factory, datetime(2024, 6, 20, 18, 42))
        import_id = await _seed_import(db_session_factory)

        r = await coach_client.post(f"{_IMPORTS}/{import_id}/discard")

        assert r.status_code == 200, r.text
        assert r.json()["parent_committed_at"] is None

    @pytest.mark.asyncio
    async def test_admin_can_get_any_import(self, admin_client, db_session_factory):
        import_id = await _seed_import(db_session_factory)
        r = await admin_client.get(f"{_IMPORTS}/{import_id}")
        assert r.status_code == 200, r.text

    @pytest.mark.asyncio
    async def test_parent_is_forbidden(self, parent_client, db_session_factory):
        import_id = await _seed_import(db_session_factory)
        r = await parent_client.get(f"{_IMPORTS}/{import_id}")
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_coach_of_another_club_gets_404_not_403(
        self, coach_otro_club_client, db_session_factory
    ):
        """No filtra que la carga existe: otro club ve lo mismo que un id ajeno."""
        await _seed_club_membership(db_session_factory, user_id=10, club_id=1)
        import_id = await _seed_import(db_session_factory)

        r = await coach_otro_club_client.get(f"{_IMPORTS}/{import_id}")

        assert r.status_code == 404
        assert "otro club" not in r.text

    @pytest.mark.asyncio
    async def test_unknown_import_is_404(self, coach_client):
        r = await coach_client.get(f"{_IMPORTS}/9999")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_static_get_routes_are_not_shadowed_by_the_id_route(self, coach_client):
        assert (await coach_client.get(f"{_IMPORTS}/revision-reasons")).status_code == 200
        assert (await coach_client.get(f"{_IMPORTS}/acknowledge-reasons")).status_code == 200


class TestDiscardEndpoint:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "start", [RaceImportStatus.pending, RaceImportStatus.dry_run]
    )
    async def test_staged_import_becomes_discarded_and_is_audited(
        self, coach_client, db_session_factory, start
    ):
        import_id = await _seed_import(db_session_factory, status=start)

        r = await coach_client.post(f"{_IMPORTS}/{import_id}/discard")

        assert r.status_code == 200, r.text
        assert r.json()["id"] == import_id
        assert r.json()["status"] == "discarded"
        assert await _status_of(db_session_factory, import_id) == RaceImportStatus.discarded
        (row,) = await _audit_rows(db_session_factory)
        assert row.entity_id == import_id
        assert row.entity_type == "race_import"
        assert row.action.value == "update"
        assert start.value in str(row.diff_json) and "discarded" in str(row.diff_json)

    @pytest.mark.asyncio
    async def test_committed_import_cannot_be_discarded(self, coach_client, db_session_factory):
        import_id = await _seed_import(db_session_factory, status=RaceImportStatus.committed)

        r = await coach_client.post(f"{_IMPORTS}/{import_id}/discard")

        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "import_not_discardable"
        assert await _status_of(db_session_factory, import_id) == RaceImportStatus.committed
        assert await _audit_rows(db_session_factory) == []

    @pytest.mark.asyncio
    async def test_failed_import_cannot_be_discarded(self, coach_client, db_session_factory):
        import_id = await _seed_import(db_session_factory, status=RaceImportStatus.failed)
        r = await coach_client.post(f"{_IMPORTS}/{import_id}/discard")
        assert r.status_code == 409, r.text
        assert await _status_of(db_session_factory, import_id) == RaceImportStatus.failed

    @pytest.mark.asyncio
    async def test_discarding_twice_is_idempotent_and_audits_once(
        self, coach_client, db_session_factory
    ):
        import_id = await _seed_import(db_session_factory)

        first = await coach_client.post(f"{_IMPORTS}/{import_id}/discard")
        second = await coach_client.post(f"{_IMPORTS}/{import_id}/discard")

        assert first.status_code == 200 and second.status_code == 200
        assert second.json()["status"] == "discarded"
        assert len(await _audit_rows(db_session_factory)) == 1

    @pytest.mark.asyncio
    async def test_admin_can_discard(self, admin_client, db_session_factory):
        import_id = await _seed_import(db_session_factory)
        r = await admin_client.post(f"{_IMPORTS}/{import_id}/discard")
        assert r.status_code == 200, r.text

    @pytest.mark.asyncio
    async def test_parent_is_forbidden(self, parent_client, db_session_factory):
        import_id = await _seed_import(db_session_factory)

        r = await parent_client.post(f"{_IMPORTS}/{import_id}/discard")

        assert r.status_code == 403
        assert await _status_of(db_session_factory, import_id) == RaceImportStatus.pending

    @pytest.mark.asyncio
    async def test_coach_of_another_club_gets_404_and_nothing_changes(
        self, coach_otro_club_client, db_session_factory
    ):
        await _seed_club_membership(db_session_factory, user_id=10, club_id=1)
        import_id = await _seed_import(db_session_factory)

        r = await coach_otro_club_client.post(f"{_IMPORTS}/{import_id}/discard")

        assert r.status_code == 404
        assert await _status_of(db_session_factory, import_id) == RaceImportStatus.pending

    @pytest.mark.asyncio
    async def test_unknown_import_is_404(self, coach_client):
        r = await coach_client.post(f"{_IMPORTS}/9999/discard")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_the_same_file_can_be_uploaded_again_after_discarding_it(
        self, coach_client, db_session_factory
    ):
        """``discarded`` no cuenta como staging: re-staguear el mismo archivo
        crea una carga nueva en vez de devolver la abandonada (FR-027 solo
        reusa ``pending``/``dry_run``)."""
        first_id = await _stage_pending_import(db_session_factory)

        assert (await coach_client.post(f"{_IMPORTS}/{first_id}/discard")).status_code == 200

        # Mismo documento + header → mismo sha256 (fingerprint determinístico
        # de ``stage_for_test``) — el import descartado no debe deduplicar.
        second_id = await _stage_pending_import(db_session_factory)

        assert second_id != first_id


class TestListHidesDiscardedByDefault:
    @pytest.mark.asyncio
    async def test_default_listing_excludes_discarded(self, coach_client, db_session_factory):
        await _seed_import(db_session_factory, sha="1" * 64)
        await _seed_import(db_session_factory, sha="2" * 64, status=RaceImportStatus.discarded)
        await _seed_import(db_session_factory, sha="3" * 64, status=RaceImportStatus.committed)

        r = await coach_client.get(f"{_IMPORTS}/")

        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 2
        assert sorted(i["status"] for i in body["items"]) == ["committed", "pending"]

    @pytest.mark.asyncio
    async def test_discarded_are_still_reachable_with_an_explicit_status_filter(
        self, coach_client, db_session_factory
    ):
        await _seed_import(db_session_factory, sha="1" * 64)
        await _seed_import(db_session_factory, sha="2" * 64, status=RaceImportStatus.discarded)

        r = await coach_client.get(f"{_IMPORTS}/?status=discarded")

        assert r.status_code == 200
        assert [i["status"] for i in r.json()["items"]] == ["discarded"]
        assert r.json()["total"] == 1
