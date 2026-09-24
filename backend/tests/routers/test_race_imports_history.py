"""Tests de la carga histórica US5 sobre el flujo confiable de siempre
(feature 044, T057 — contracts/historical-load.md).

Cubre, vía HTTP real (``/parse`` → ``/dry-run`` → ``/commit`` /
``/commit-pending``) con PDFs sintéticos:

- FR-028: parrilla completa — categorías sin ningún atleta del club se
  commitean igual.
- FR-026: los puntos impresos se persisten verbatim, sin recalcular.
- Commit parcial: categorías consistentes/reconocidas entran; las demás
  quedan en ``pending_categories``. ``POST .../commit-pending`` las termina
  y respeta el mismo candado de identidad que ``/commit`` (FR-018); ``409
  nothing_pending`` cuando no queda nada.
- FR-027: re-stagear o re-commitear un archivo idéntico no crea filas
  nuevas en ninguna tabla.
- ``is_calculated`` en la clasificación (T062).

Requiere WeasyPrint (vía ``tests/helpers/results_pdf_builder.py``) —
anteponer ``DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`` al comando de
pytest en este Mac.

Fixtures de auth/DB duplicadas de ``tests/routers/test_race_imports.py`` a
propósito (convención ya establecida en el módulo).
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
from app.models.race_category import RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_import import RaceImport
from app.models.race_result import RaceResult
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole
from tests.helpers.audit_tables import AUDIT_TABLES
from tests.helpers.results_pdf_builder import (
    CategorySpec,
    FakeNameGenerator,
    build_results_pdf,
    sequential_category,
)
from tests.services.race.conftest import _SEED_CATEGORIES

_IMPORTS_URL = "/api/race-analysis/imports"
_EVENTS_URL = "/api/race-analysis/race-events"


# ---------------------------------------------------------------------------
# Fixtures de auth/DB
# ---------------------------------------------------------------------------


def _make_user(role: UserRole, user_id: int, club_ids: tuple[int, ...] = (1,)) -> SimpleNamespace:
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
    from app.models.athlete import Athlete as _A  # noqa: F401
    from app.models.club import Club as _Cl, ClubMember as _CM  # noqa: F401
    from app.models.race_category import RaceCategory as _C  # noqa: F401
    from app.models.race_competitor import RaceCompetitor as _Comp  # noqa: F401
    from app.models.race_competitor_signature import (  # noqa: F401
        RaceCompetitorSignature as _Sig,
    )
    from app.models.race_event import RaceEvent as _E  # noqa: F401
    from app.models.race_identity_candidate import (  # noqa: F401
        RaceIdentityCandidate as _IdCand,
    )
    from app.models.race_import import RaceImport as _I  # noqa: F401
    from app.models.race_result import RaceResult as _R  # noqa: F401
    from app.models.race_series import RaceSeries as _S  # noqa: F401
    from app.models.user import User as _U  # noqa: F401

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
    async with db_session_factory() as session:
        coach1 = User(
            id=10, email="coach10@test.com", hashed_password="x",
            first_name="Coach", last_name="Ten",
            role=UserRole.coach, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        session.add(coach1)
        for code, label, sex, age_min, age_max, tier, sort_order in _SEED_CATEGORIES:
            session.add(
                RaceCategory(
                    code=code, label=label, sex=sex, age_min=age_min,
                    age_max=age_max, tier=tier, sort_order=sort_order,
                    is_active=True,
                )
            )
        await session.commit()
    yield


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


@pytest_asyncio.fixture
async def coach_client(sqlite_engine, db_session_factory, seed_test_data, override_storage):
    async def _override_db():
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.coach, user_id=10)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers de upload
# ---------------------------------------------------------------------------


def _historical_form(**overrides) -> dict:
    form = {
        "series_name": "Copa Valle de Ciclomontañismo",
        "season": "2024",
        "valida_num": "3",
        "event_name": "VALIDA III PALMIRA",
        "event_date": "2024-06-14",
        "location": "Palmira",
    }
    form.update({k: str(v) for k, v in overrides.items()})
    return form


def _build_pdf_bytes(
    tmp_path: Path, categories: list[CategorySpec], *, valida_num: int = 3,
    location: str = "Palmira", event_date: date = date(2024, 6, 14),
) -> bytes:
    path = build_results_pdf(
        tmp_path / f"sintetico_{valida_num}.pdf",
        valida_num=valida_num,
        location=location,
        event_date=event_date,
        categories=categories,
        name_generator=FakeNameGenerator(),
    )
    return path.read_bytes()


async def _parse(client, tmp_path, categories, **form_overrides) -> dict:
    pdf_bytes = _build_pdf_bytes(tmp_path, categories)
    files = {"resultados_pdf": ("resultados.pdf", pdf_bytes, "application/pdf")}
    r = await client.post(
        f"{_IMPORTS_URL}/parse", data=_historical_form(**form_overrides), files=files
    )
    assert r.status_code == 200, r.text
    return r.json()


def _external_category(header: str, n: int, bib_start: int) -> CategorySpec:
    """Categoría con ``n`` filas de un club ajeno — nunca Trocha y Ruta."""
    cat = sequential_category(header, n)
    for i, row in enumerate(cat.rows, start=1):
        row.bib = str(bib_start + i)
        row.club = "Club Externo Ficticio"
    return cat


def _category_with_gap(header: str, bib_start: int) -> CategorySpec:
    """3 filas, ordinales [1, 2, 4] — falta el 3 (research R-05)."""
    cat = sequential_category(header, 3)
    for i, row in enumerate(cat.rows, start=1):
        row.bib = str(bib_start + i)
        row.club = "Club Externo Ficticio"
    cat.rows[2].position = 4
    return cat


async def _keys_of_import(db_session_factory, parse_id: int) -> list[str]:
    """Claves de registro de las filas que la carga aún tiene por ingestar
    (feature 045, R-08): el candado de identidad solo mira candidatos que
    las involucran. Las filas llevan nombres generados, así que se leen del
    archivo almacenado en vez de adivinarlos."""
    from app.routers import race_imports as router_mod
    from app.services.race import identity_review

    async with db_session_factory() as db:
        imp = (
            await db.execute(select(RaceImport).where(RaceImport.id == parse_id))
        ).scalar_one()
    loaded = await router_mod.load_identity_rows(imp)
    return sorted(identity_review.import_record_keys(loaded.results, loaded.general))


# ===========================================================================
# FR-028 — parrilla completa, sin atletas del club
# ===========================================================================


class TestFullStartListCommitted:
    @pytest.mark.asyncio
    async def test_categories_without_club_athletes_are_committed(
        self, coach_client, tmp_path, db_session_factory
    ):
        cat_a = _external_category("INFANTIL A", 2, 100)
        cat_b = _external_category("MASTER A", 3, 200)
        parsed = await _parse(coach_client, tmp_path, [cat_a, cat_b])
        parse_id = parsed["parse_id"]

        r = await coach_client.post(f"{_IMPORTS_URL}/{parse_id}/dry-run")
        assert r.status_code == 200, r.text

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/commit", json={"resolved_matches": []}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["pending_categories"] == []
        assert body["n_results_inserted"] == 5  # 2 + 3, ninguno es TyR

        async with db_session_factory() as db:
            n_results = len((await db.execute(select(RaceResult))).scalars().all())
            assert n_results == 5

    @pytest.mark.asyncio
    async def test_printed_points_kept_verbatim(
        self, coach_client, tmp_path, db_session_factory
    ):
        cat = _external_category("JUNIOR", 2, 300)
        # Puntos deliberadamente NO estándar — si algo los recalculara contra
        # un esquema de puntos, no coincidirían con lo impreso.
        cat.rows[0].points = 17
        cat.rows[1].points = 3

        parsed = await _parse(coach_client, tmp_path, [cat])
        parse_id = parsed["parse_id"]
        await coach_client.post(f"{_IMPORTS_URL}/{parse_id}/dry-run")
        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/commit", json={"resolved_matches": []}
        )
        assert r.status_code == 200, r.text

        async with db_session_factory() as db:
            results = (
                (await db.execute(select(RaceResult).order_by(RaceResult.position)))
                .scalars()
                .all()
            )
        points = sorted(res.points_awarded for res in results)
        assert points == [3, 17]


# ===========================================================================
# Commit parcial + commit-pending
# ===========================================================================


class TestPartialCommitAndCommitPending:
    @pytest.mark.asyncio
    async def test_partial_commit_lists_pending_then_commit_pending_finishes(
        self, coach_client, tmp_path, db_session_factory
    ):
        ok_cat = _external_category("INFANTIL B", 2, 400)
        gap_cat = _category_with_gap("PREJUVENIL A", 500)

        parsed = await _parse(coach_client, tmp_path, [ok_cat, gap_cat])
        parse_id = parsed["parse_id"]
        await coach_client.post(f"{_IMPORTS_URL}/{parse_id}/dry-run")

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/commit", json={"resolved_matches": []}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["pending_categories"] == ["PREJUVENIL A"]
        assert body["n_results_inserted"] == 2  # solo INFANTIL B

        # El listado expone el contador de categorías pendientes, y agrupa
        # por season/valida_num/series_name (aquí, desde parse_meta_json
        # ["header"] — el import sigue con pending_categories, meta viva).
        r = await coach_client.get(f"{_IMPORTS_URL}/")
        item = next(i for i in r.json()["items"] if i["id"] == parse_id)
        assert item["status"] == "committed"
        assert item["pending_categories_count"] == 1
        assert item["season"] == 2024
        assert item["valida_num"] == 3
        assert item["series_name"] == "Copa Valle de Ciclomontañismo"

        # commit-pending sin reconocer todavía la categoría: sigue sin nada
        # elegible -> 409 nothing_pending.
        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/commit-pending", json={"resolved_matches": []}
        )
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "nothing_pending"

        # El coach reconoce la categoría (el acta oficial salta un puesto).
        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/acknowledge",
            json={
                "category_header": "PREJUVENIL A",
                "reason": "source_missing_ordinal",
            },
        )
        assert r.status_code == 200, r.text

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/commit-pending", json={"resolved_matches": []}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["pending_categories"] == []
        assert body["n_results_inserted"] == 3  # PREJUVENIL A tenía 3 filas

        async with db_session_factory() as db:
            n_results = len((await db.execute(select(RaceResult))).scalars().all())
            assert n_results == 5  # 2 (INFANTIL B) + 3 (PREJUVENIL A)
            imp = (
                await db.execute(select(RaceImport).where(RaceImport.id == parse_id))
            ).scalar_one()
            assert imp.parse_meta_json is None  # todo consistente, meta limpio

        # Ya no queda nada pendiente.
        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/commit-pending", json={"resolved_matches": []}
        )
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "nothing_pending"

    @pytest.mark.asyncio
    async def test_commit_pending_obeys_identity_review_gate(
        self, coach_client, tmp_path, db_session_factory
    ):
        """Feature 045 (R-08): el candado de ``/commit-pending`` frena solo con
        un candidato pendiente que involucre a las filas que va a ingestar."""
        from app.models.race_identity_candidate import (
            IdentityCandidateKind,
            IdentityCandidateState,
            RaceIdentityCandidate,
        )

        ok_cat = _external_category("MASTER B1", 2, 600)
        gap_cat = _category_with_gap("MASTER C1", 700)

        parsed = await _parse(coach_client, tmp_path, [ok_cat, gap_cat])
        parse_id = parsed["parse_id"]
        await coach_client.post(f"{_IMPORTS_URL}/{parse_id}/dry-run")
        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/commit", json={"resolved_matches": []}
        )
        assert r.status_code == 200, r.text
        assert r.json()["pending_categories"] == ["MASTER C1"]

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/acknowledge",
            json={
                "category_header": "MASTER C1",
                "reason": "verified_against_source",
            },
        )
        assert r.status_code == 200, r.text

        # Un candidato pendiente sobre una fila de MASTER C1 (la categoría que
        # falta por ingestar), creado después de la carga: la cola está al día.
        (own_key, *_rest) = await _keys_of_import(db_session_factory, parse_id)
        async with db_session_factory() as db:
            db.add(
                RaceIdentityCandidate(
                    pair_hash="p" * 64,
                    kind=IdentityCandidateKind.same_person_suspect,
                    state=IdentityCandidateState.pending,
                    score=95,
                    signals=["extra_or_missing_surname"],
                    left_record={"key": own_key},
                    right_record={"key": "otra\x1fterna\x1f"},
                    linked_athlete_involved=True,
                )
            )
            await db.commit()

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/commit-pending", json={"resolved_matches": []}
        )
        assert r.status_code == 409, r.text
        assert r.json() == {
            "detail": "identity_pending",
            "pending_for_import": 1,
            "review_path": f"/competitions/imports?seccion=identidades&import={parse_id}",
        }


# ===========================================================================
# FR-027 — idempotencia
# ===========================================================================


class TestIdempotence:
    @pytest.mark.asyncio
    async def test_restaging_and_recommitting_identical_file_creates_nothing(
        self, coach_client, tmp_path, db_session_factory
    ):
        cat = _external_category("ELITE HOMBRES", 2, 800)
        pdf_bytes = _build_pdf_bytes(tmp_path, [cat])
        files = {"resultados_pdf": ("resultados.pdf", pdf_bytes, "application/pdf")}

        r1 = await coach_client.post(
            f"{_IMPORTS_URL}/parse", data=_historical_form(), files=files
        )
        assert r1.status_code == 200, r1.text
        parse_id = r1.json()["parse_id"]

        await coach_client.post(f"{_IMPORTS_URL}/{parse_id}/dry-run")
        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/commit", json={"resolved_matches": []}
        )
        assert r.status_code == 200, r.text

        async def _counts():
            async with db_session_factory() as db:
                n_imports = len((await db.execute(select(RaceImport))).scalars().all())
                n_results = len((await db.execute(select(RaceResult))).scalars().all())
                n_competitors = len(
                    (await db.execute(select(RaceCompetitor))).scalars().all()
                )
                n_series = len((await db.execute(select(RaceSeries))).scalars().all())
                return n_imports, n_results, n_competitors, n_series

        before = await _counts()

        # Re-stagear el mismo archivo (ya committed) -> 409, nada nuevo.
        files_again = {"resultados_pdf": ("resultados.pdf", pdf_bytes, "application/pdf")}
        r2 = await coach_client.post(
            f"{_IMPORTS_URL}/parse", data=_historical_form(), files=files_again
        )
        assert r2.status_code == 409, r2.text

        # Re-commitear el mismo parse_id -> ya no está pending -> 404.
        r3 = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/commit", json={"resolved_matches": []}
        )
        assert r3.status_code == 404, r3.text

        after = await _counts()
        assert after == before


# ===========================================================================
# is_calculated en la clasificación (T062)
# ===========================================================================


class TestStandingsIsCalculated:
    @pytest.mark.asyncio
    async def test_standings_response_carries_is_calculated_true(
        self, coach_client, tmp_path
    ):
        cat = _external_category("MASTER D", 2, 900)
        parsed = await _parse(coach_client, tmp_path, [cat])
        parse_id = parsed["parse_id"]
        await coach_client.post(f"{_IMPORTS_URL}/{parse_id}/dry-run")
        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/commit", json={"resolved_matches": []}
        )
        assert r.status_code == 200, r.text
        event_id = r.json()["race_event_id"]

        r = await coach_client.get(f"{_EVENTS_URL}/{event_id}/standings")
        assert r.status_code == 200, r.text
        assert r.json()["is_calculated"] is True


# ===========================================================================
# G4 mitigation — un segundo rebuild no vuelve a descargar/parsear (plan.md
# Complexity Tracking)
# ===========================================================================


class TestG4CacheAvoidsReparseOnSecondRebuild:
    @pytest.mark.asyncio
    async def test_second_rebuild_does_not_redownload_or_reparse(
        self, coach_client, tmp_path, monkeypatch
    ):
        from app.services.training import storage_sftp

        # Dos válidas en staging (pending) — nunca se commitean, para que
        # sigan formando parte del universo de identidad en ambos rebuilds.
        for i in range(2):
            cat = _external_category("MASTER B1", 2, 1000 + i * 10)
            await _parse(
                coach_client, tmp_path, [cat],
                valida_num=str(i + 1), event_name=f"VALIDA {i + 1}",
            )

        real_download = storage_sftp.download_to_tempfile
        download_calls = {"n": 0}

        async def counting_download(*args, **kwargs):
            download_calls["n"] += 1
            return await real_download(*args, **kwargs)

        monkeypatch.setattr(storage_sftp, "download_to_tempfile", counting_download)

        r = await coach_client.post("/api/race-identity/rebuild")
        assert r.status_code == 200, r.text
        first_run_calls = download_calls["n"]
        assert first_run_calls >= 2, (
            "el primer rebuild debe descargar cada uno de los 2 imports en "
            "staging al menos una vez"
        )

        download_calls["n"] = 0
        r = await coach_client.post("/api/race-identity/rebuild")
        assert r.status_code == 200, r.text
        assert download_calls["n"] == 0, (
            "un segundo rebuild con la misma revisión de correcciones no debe "
            "volver a descargar/parsear ningún import (caché G4, "
            "routers/race_imports.py::_reload_results_document)"
        )


# ===========================================================================
# Listado — season/valida_num/series_name (pedido de w4-load-ui)
# ===========================================================================


class TestListSeasonFieldsAfterFullCommit:
    @pytest.mark.asyncio
    async def test_fully_committed_import_resolves_season_via_event(
        self, coach_client, tmp_path
    ):
        """Sin `pending_categories`, `parse_meta_json` queda en ``None`` — el
        listado debe resolver season/valida_num/series_name vía
        ``RaceEvent``/``RaceSeries`` en vez de la meta (que ya no existe)."""
        cat = _external_category("MASTER C1", 2, 1100)
        parsed = await _parse(
            coach_client, tmp_path, [cat], season="2025", valida_num="6",
            event_name="VALIDA VI TULUA",
        )
        parse_id = parsed["parse_id"]
        await coach_client.post(f"{_IMPORTS_URL}/{parse_id}/dry-run")
        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/commit", json={"resolved_matches": []}
        )
        assert r.status_code == 200, r.text
        assert r.json()["pending_categories"] == []

        r = await coach_client.get(f"{_IMPORTS_URL}/")
        item = next(i for i in r.json()["items"] if i["id"] == parse_id)
        assert item["pending_categories_count"] == 0
        assert item["season"] == 2025
        assert item["valida_num"] == 6
        assert item["series_name"] == "Copa Valle de Ciclomontañismo"


# ===========================================================================
# 409 matches_unresolved — HistoricalLoadPage siempre commitea con
# resolved_matches: [] (no tiene UI de resolución de matches)
# ===========================================================================


class TestMatchesUnresolved:
    @pytest.mark.asyncio
    async def test_commit_with_unresolved_tyr_match_returns_409(
        self, coach_client, tmp_path
    ):
        cat = sequential_category("ELITE HOMBRES", 1)
        cat.rows[0].bib = "1200"
        cat.rows[0].club = "Club Trocha y Ruta"

        parsed = await _parse(coach_client, tmp_path, [cat])
        parse_id = parsed["parse_id"]
        await coach_client.post(f"{_IMPORTS_URL}/{parse_id}/dry-run")

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/commit", json={"resolved_matches": []}
        )
        assert r.status_code == 409, r.text
        detail = r.json()["detail"]
        assert detail["code"] == "matches_unresolved"
        assert detail["missing_count"] == 1

    @pytest.mark.asyncio
    async def test_commit_pending_with_unresolved_tyr_match_returns_409(
        self, coach_client, tmp_path
    ):
        ok_cat = _external_category("MASTER D", 2, 1300)
        gap_cat = _category_with_gap("MASTER B2", 1400)
        # La fila TyR vive en la categoría que primero queda pendiente — su
        # resolved_match solo se exige en el commit-pending que la ingesta.
        gap_cat.rows[0].club = "Club Trocha y Ruta"

        parsed = await _parse(coach_client, tmp_path, [ok_cat, gap_cat])
        parse_id = parsed["parse_id"]
        await coach_client.post(f"{_IMPORTS_URL}/{parse_id}/dry-run")
        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/commit", json={"resolved_matches": []}
        )
        assert r.status_code == 200, r.text
        assert r.json()["pending_categories"] == ["MASTER B2"]

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/acknowledge",
            json={"category_header": "MASTER B2", "reason": "verified_against_source"},
        )
        assert r.status_code == 200, r.text

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/commit-pending", json={"resolved_matches": []}
        )
        assert r.status_code == 409, r.text
        detail = r.json()["detail"]
        assert detail["code"] == "matches_unresolved"
        assert detail["missing_count"] == 1


class TestIdentityGateSkipsRedundantRebuild:
    """T050 + hotfix 2026-09-22: el rebuild del candado reparsea TODOS los
    imports en staging. Con las quince válidas históricas eso tarda minutos en
    Render y la conexión MySQL ociosa se cae. Solo debe correr si algún import
    en staging es más nuevo que el último candidato calculado."""

    @pytest.mark.asyncio
    async def test_rebuild_skipped_when_queue_is_up_to_date(
        self, coach_client, tmp_path, monkeypatch, db_session_factory
    ):
        from app.models.race_identity_candidate import (
            IdentityCandidateKind,
            IdentityCandidateState,
            RaceIdentityCandidate,
        )
        from app.routers import race_imports as router_mod

        parsed = await _parse(coach_client, tmp_path, [sequential_category("ELITE HOMBRES", 3)])
        parse_id = parsed["parse_id"]
        await coach_client.post(f"{_IMPORTS_URL}/{parse_id}/dry-run")

        # Un candidato pendiente sobre una fila de ESTE import (feature 045:
        # solo esos frenan el commit) creado DESPUÉS de subirlo: la cola está
        # al día.
        (own_key, *_rest) = await _keys_of_import(db_session_factory, parse_id)
        async with db_session_factory() as db:
            db.add(
                RaceIdentityCandidate(
                    pair_hash="h" * 64,
                    kind=IdentityCandidateKind.same_person_suspect,
                    state=IdentityCandidateState.pending,
                    score=95,
                    signals=["extra_or_missing_surname"],
                    left_record={"key": own_key, "name_printed": "Ana Prueba Uno"},
                    right_record={"key": "otra\x1fterna\x1f", "name_printed": "Ana Prueba Uno Dos"},
                    linked_athlete_involved=True,
                )
            )
            await db.commit()

        called = {"n": 0}

        async def _boom(*args, **kwargs):  # pragma: no cover - no debe llamarse
            called["n"] += 1
            raise AssertionError("rebuild no debía correr: la cola está al día")

        monkeypatch.setattr(router_mod.identity_review, "rebuild", _boom)
        resp = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_id}/commit", json={"resolved_matches": []}
        )
        assert resp.status_code == 409
        assert resp.json()["detail"] == "identity_pending"
        assert resp.json()["pending_for_import"] == 1
        assert called["n"] == 0
