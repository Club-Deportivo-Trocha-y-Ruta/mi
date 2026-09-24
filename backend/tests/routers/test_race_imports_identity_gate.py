"""Candado de identidad POR CARGA en ``/commit`` y ``/commit-pending``
(feature 045, US3, T021 — research R-08, contracts/api.md §"Changed behaviour").

Antes de 045 el candado miraba la cola entera: cualquier candidato ``pending``
—aunque hablara solo de otra carga— frenaba todos los commits. Ahora una carga
solo la frena un candidato pendiente cuyo ``left_record.key`` o
``right_record.key`` pertenece a las filas de ESA carga (OR: un candidato que
cruza dos cargas frena a ambas; un competidor nuevo de la carga tiene clave
aunque aún no tenga ``competitor_id``).

Los tres casos del contrato se prueban en ``/commit`` y en ``/commit-pending``:

(a) candidato con claves solo de OTRA carga        → 200
(b) candidato que cruza esta carga y otra          → 409 ``identity_pending``
(c) candidato sobre un competidor NUEVO de la carga → 409 ``identity_pending``

Vía HTTP real con PDFs sintéticos (``tests/helpers/results_pdf_builder.py``);
los candidatos se siembran DESPUÉS de subir las cargas, así la cola "está al
día" y el commit no recalcula (``_identity_rebuild_needed`` es False) — el
recálculo podaría los candidatos sembrados a mano por no involucrar a un atleta
del club. Nombres evidentemente ficticios (Ley 1581).

Requiere WeasyPrint: anteponer ``DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib``
al comando de pytest en este Mac. Fixtures de auth/DB duplicadas de
``test_race_imports_history.py`` a propósito (convención del módulo).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

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
from app.models.race_identity_candidate import (
    IdentityCandidateKind,
    IdentityCandidateState,
    RaceIdentityCandidate,
)
from app.models.race_import import RaceImport, RaceImportStatus
from app.models.race_result import RaceResult
from app.models.user import User, UserRole
from app.services.race import identity_review as ir
from app.services.race.identity_resolver import signature_triple
from app.services.race.pdf_parser import GeneralRow
from tests.helpers.audit_tables import AUDIT_TABLES
from tests.helpers.results_pdf_builder import (
    CategorySpec,
    FakeNameGenerator,
    build_results_pdf,
    sequential_category,
)
from tests.services.race.conftest import _SEED_CATEGORIES
from tests.services.race.identity_support import ingest as ingest_rows
from tests.services.race.identity_support import row as results_row

_IMPORTS_URL = "/api/race-analysis/imports"

CLUB = "Club Externo Ficticio"
CITY = "Ciudad Ficticia"

#: Filas de la carga A (la que se commitea) y de la carga B (ajena).
A_NAMES = ("Alba Prueba Uno", "Bruno Prueba Dos", "Carla Prueba Tres")
B_NAMES = ("Dario Muestra Uno", "Elena Muestra Dos", "Fabio Muestra Tres")
#: Competidor existente que no aparece en ninguna de las dos cargas.
OUTSIDER = "Gina Ejemplo Cuatro"
#: Atleta del club ya confirmada, y su casi-duplicado (un apellido de más).
#: Sin apellidos en común con ``A_NAMES``/``B_NAMES``: ninguna otra fila de
#: las cargas puede levantar un candidato contra ella.
CLUB_ATHLETE = "Mateo Nunca Igual"
NEAR_DUPLICATE = "Mateo Nunca Igual Dos"
#: Fila que solo trae el GENERAL de la carga.
GENERAL_ONLY = "Zoe General Solo"


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
            SimpleNamespace(club_id=cid, role_in_club=_ClubRole.coach) for cid in club_ids
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
        session.add(
            User(
                id=10, email="coach10@test.com", hashed_password="x",
                first_name="Coach", last_name="Ten",
                role=UserRole.coach, is_active=True, can_login=True,
                created_at=datetime.now(timezone.utc),
            )
        )
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

    monkeypatch.setattr(storage_sftp, "_LOCAL_FALLBACK_BASE", tmp_path / "uploads-test")
    monkeypatch.setattr(storage_sftp, "_LOCAL_FALLBACK_URL_PREFIX", "/static/uploads/test")
    for attr in (
        "hostinger_sftp_host",
        "hostinger_sftp_user",
        "hostinger_sftp_pass",
        "hostinger_sftp_remote_dir",
        "hostinger_public_base_url",
    ):
        monkeypatch.setattr(settings, attr, "")
    yield


def _install_overrides(db_session_factory, user) -> None:
    async def _override_db():
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: user


@pytest_asyncio.fixture
async def coach_client(sqlite_engine, db_session_factory, seed_test_data, override_storage):
    _install_overrides(db_session_factory, _make_user(UserRole.coach, user_id=10))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def parent_client(sqlite_engine, db_session_factory, seed_test_data, override_storage):
    _install_overrides(db_session_factory, _make_user(UserRole.parent, user_id=20))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers: cargas, candidatos
# ---------------------------------------------------------------------------


def _category(header: str, names: tuple[str, ...], bib_start: int, *, gap: bool = False) -> CategorySpec:
    """Categoría cuyas filas llevan nombre/club/ciudad explícitos, para poder
    calcular su clave de registro sin depender del generador."""
    cat = sequential_category(header, len(names))
    for i, (row, name) in enumerate(zip(cat.rows, names), start=1):
        row.bib = str(bib_start + i)
        row.name = name
        row.club = CLUB
        row.city = CITY
    if gap:
        cat.rows[-1].position += 1  # ordinales [1, 2, 4]: falta el 3 (R-05)
    return cat


async def _stage(
    client,
    tmp_path: Path,
    categories: list[CategorySpec],
    valida_num: int,
    *,
    with_general: bool = False,
) -> int:
    """Sube una carga (``/parse``) y devuelve su ``parse_id`` (queda ``pending``).

    ``with_general`` adjunta un PDF GENERAL: el contenido lo dicta el fixture
    ``general_rows`` (el parser está sustituido)."""
    pdf = build_results_pdf(
        tmp_path / f"sintetico_{valida_num}.pdf",
        valida_num=valida_num,
        location="Palmira",
        event_date=date(2024, 6, valida_num),
        categories=categories,
        name_generator=FakeNameGenerator(),
    )
    form = {
        "series_name": "Copa Valle de Ciclomontañismo",
        "season": "2024",
        "valida_num": str(valida_num),
        "event_name": f"VALIDA {valida_num} PALMIRA",
        "event_date": f"2024-06-{valida_num:02d}",
        "location": "Palmira",
    }
    files = {"resultados_pdf": ("resultados.pdf", pdf.read_bytes(), "application/pdf")}
    if with_general:
        files["general_pdf"] = (
            "general.pdf",
            b"%PDF-1.4 general " + str(valida_num).encode(),
            "application/pdf",
        )
    r = await client.post(f"{_IMPORTS_URL}/parse", data=form, files=files)
    assert r.status_code == 200, r.text
    return r.json()["parse_id"]


def _snapshot(name: str, *, competitor_id: Optional[int] = None) -> dict:
    """Snapshot de un lado de candidato, con la forma que persiste
    ``IdentityRecord.snapshot()`` (la clave es la terna de la fila)."""
    triple = signature_triple(name, CLUB, CITY)
    return {
        "key": ir.record_key(triple),
        "name_printed": name,
        "normalized_name": triple[0],
        "club": CLUB,
        "club_norm": triple[1],
        "city": CITY,
        "city_norm": triple[2],
        "seasons": [2024],
        "category_codes": [],
        "category_labels": [],
        "sex": None,
        "competitor_id": competitor_id,
        "athlete_linked": False,
    }


async def _seed_candidate(
    db_session_factory,
    left: dict,
    right: dict,
    *,
    state: IdentityCandidateState = IdentityCandidateState.pending,
) -> int:
    async with db_session_factory() as db:
        cand = RaceIdentityCandidate(
            kind=IdentityCandidateKind.same_person_suspect,
            pair_hash=ir.pair_hash(left["key"], right["key"]),
            left_record=left,
            right_record=right,
            score=95,
            signals=["extra_or_missing_surname"],
            state=state,
            linked_athlete_involved=False,
        )
        if state != IdentityCandidateState.pending:
            cand.decided_at = datetime.now(timezone.utc)
        db.add(cand)
        await db.commit()
        return cand.id


async def _assert_not_committed(
    db_session_factory, parse_id: int, *, baseline_results: int = 0
) -> None:
    """El 409 no debe haber escrito nada: ni resultados ni cambio de estado.
    ``baseline_results``: resultados que ya había antes de la carga (la atleta
    del club sembrada)."""
    async with db_session_factory() as db:
        assert len((await db.execute(select(RaceResult))).scalars().all()) == baseline_results
        imp = (
            await db.execute(select(RaceImport).where(RaceImport.id == parse_id))
        ).scalar_one()
        assert imp.status == RaceImportStatus.pending


def _identity_pending_body(parse_id: int, n: int) -> dict:
    return {
        "detail": "identity_pending",
        "pending_for_import": n,
        "review_path": f"/competitions/imports?seccion=identidades&import={parse_id}",
    }


@pytest.fixture
def general_rows(monkeypatch) -> dict[str, list[GeneralRow]]:
    """Filas que devuelve el parser de GENERAL (sustituido), por código de
    categoría: el PDF adjunto solo importa para que la carga tenga GENERAL."""
    from app.routers import race_imports as router_mod
    from app.services.race import import_staging as import_staging_mod

    rows: dict[str, list[GeneralRow]] = {}

    async def fake_parse_general(path):  # noqa: ARG001
        return rows

    monkeypatch.setattr(router_mod, "_parse_general_with_timeout", fake_parse_general)
    monkeypatch.setattr(import_staging_mod, "_parse_general_with_timeout", fake_parse_general)
    return rows


def _general_row(name: str, position: int = 1) -> GeneralRow:
    return GeneralRow(
        overall_position=position, bib=str(900 + position), name=name, city=CITY,
        club=CLUB, points_per_valida=[10], total_points=10,
    )


async def _seed_club_athlete(db_session_factory, name: str = CLUB_ATHLETE) -> None:
    """Competidor confirmado (2023, ``INF_A``) vinculado a un atleta del club:
    sin él ningún par entra a la cola (decisión 2026-09-22)."""
    async with db_session_factory() as db:
        await ingest_rows(db, 2023, 1, {"INF_A": [results_row(name, club=CLUB, city=CITY)]})
        (await db.execute(select(RaceCompetitor))).scalars().one().athlete_id = 4242
        await db.commit()


async def _pending_candidate_ids(db_session_factory) -> list[int]:
    async with db_session_factory() as db:
        return list(
            (
                await db.execute(
                    select(RaceIdentityCandidate.id).where(
                        RaceIdentityCandidate.state == IdentityCandidateState.pending
                    )
                )
            ).scalars().all()
        )


async def _decide(client, candidate_id: int, answer: str = "different_people") -> None:
    r = await client.post(
        f"/api/race-identity/candidates/{candidate_id}/decide", json={"answer": answer}
    )
    assert r.status_code == 200, r.text


# ===========================================================================
# POST /{id}/commit
# ===========================================================================


class TestCommitGateIsPerImport:
    @pytest.mark.asyncio
    async def test_candidate_about_another_import_does_not_block(
        self, coach_client, tmp_path, db_session_factory
    ):
        """(a) el candidato solo habla de las filas de la carga B."""
        parse_a = await _stage(coach_client, tmp_path, [_category("INFANTIL A", A_NAMES, 100)], 3)
        await _stage(coach_client, tmp_path, [_category("INFANTIL A", B_NAMES, 200)], 4)
        cand_id = await _seed_candidate(
            db_session_factory, _snapshot(B_NAMES[0]), _snapshot(B_NAMES[1])
        )

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_a}/commit", json={"resolved_matches": []}
        )

        assert r.status_code == 200, r.text
        assert r.json()["n_results_inserted"] == len(A_NAMES)
        async with db_session_factory() as db:  # el gate no toca la decisión pendiente
            cand = (
                await db.execute(select(RaceIdentityCandidate).where(RaceIdentityCandidate.id == cand_id))
            ).scalar_one()
            assert cand.state == IdentityCandidateState.pending

    @pytest.mark.asyncio
    async def test_candidate_spanning_this_and_another_import_blocks(
        self, coach_client, tmp_path, db_session_factory
    ):
        """(b) un lado es de la carga A y el otro de la B."""
        parse_a = await _stage(coach_client, tmp_path, [_category("INFANTIL A", A_NAMES, 100)], 3)
        await _stage(coach_client, tmp_path, [_category("INFANTIL A", B_NAMES, 200)], 4)
        await _seed_candidate(db_session_factory, _snapshot(A_NAMES[0]), _snapshot(B_NAMES[0]))

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_a}/commit", json={"resolved_matches": []}
        )

        assert r.status_code == 409, r.text
        assert r.json() == _identity_pending_body(parse_a, 1)
        await _assert_not_committed(db_session_factory, parse_a)

    @pytest.mark.asyncio
    async def test_candidate_about_a_new_competitor_of_this_import_blocks(
        self, coach_client, tmp_path, db_session_factory
    ):
        """(c) el competidor de la carga es nuevo (sin ``competitor_id``): su
        clave alcanza, no hace falta que ya exista en ``race_competitors``."""
        parse_a = await _stage(coach_client, tmp_path, [_category("INFANTIL A", A_NAMES, 100)], 3)
        await _seed_candidate(
            db_session_factory,
            _snapshot(A_NAMES[1], competitor_id=None),
            _snapshot(OUTSIDER, competitor_id=12345),
        )

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_a}/commit", json={"resolved_matches": []}
        )

        assert r.status_code == 409, r.text
        assert r.json() == _identity_pending_body(parse_a, 1)
        await _assert_not_committed(db_session_factory, parse_a)

    @pytest.mark.asyncio
    async def test_pending_for_import_counts_only_this_imports_candidates(
        self, coach_client, tmp_path, db_session_factory
    ):
        parse_a = await _stage(coach_client, tmp_path, [_category("INFANTIL A", A_NAMES, 100)], 3)
        await _stage(coach_client, tmp_path, [_category("INFANTIL A", B_NAMES, 200)], 4)
        await _seed_candidate(db_session_factory, _snapshot(A_NAMES[0]), _snapshot(OUTSIDER))
        await _seed_candidate(db_session_factory, _snapshot(OUTSIDER), _snapshot(A_NAMES[2]))
        await _seed_candidate(db_session_factory, _snapshot(B_NAMES[0]), _snapshot(B_NAMES[1]))

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_a}/commit", json={"resolved_matches": []}
        )

        assert r.status_code == 409, r.text
        assert r.json()["pending_for_import"] == 2  # el de la carga B no cuenta

    @pytest.mark.asyncio
    async def test_decided_candidate_of_this_import_does_not_block(
        self, coach_client, tmp_path, db_session_factory
    ):
        parse_a = await _stage(coach_client, tmp_path, [_category("INFANTIL A", A_NAMES, 100)], 3)
        await _seed_candidate(
            db_session_factory,
            _snapshot(A_NAMES[0]),
            _snapshot(OUTSIDER),
            state=IdentityCandidateState.different_people,
        )

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_a}/commit", json={"resolved_matches": []}
        )

        assert r.status_code == 200, r.text

    @pytest.mark.asyncio
    async def test_parent_is_denied(self, parent_client):
        r = await parent_client.post(f"{_IMPORTS_URL}/1/commit", json={"resolved_matches": []})
        assert r.status_code == 403


# ===========================================================================
# POST /{id}/commit-pending
# ===========================================================================


async def _stage_partial_import(client, tmp_path: Path) -> int:
    """Sube la carga A con una categoría sana y otra con hueco de posiciones
    (``MASTER C1``: ordinales [1, 2, 4]). Devuelve su ``parse_id``."""
    ok_cat = _category("MASTER B1", ("Hugo Sano Uno", "Iris Sana Dos"), 300)
    gap_cat = _category("MASTER C1", A_NAMES, 100, gap=True)
    return await _stage(client, tmp_path, [ok_cat, gap_cat], 3)


async def _first_commit_and_acknowledge(client, parse_a: int) -> None:
    """El primer ``/commit`` ingesta ``MASTER B1`` y deja ``MASTER C1``
    pendiente; se reconoce y la carga queda lista para ``/commit-pending``."""
    r = await client.post(f"{_IMPORTS_URL}/{parse_a}/commit", json={"resolved_matches": []})
    assert r.status_code == 200, r.text
    assert r.json()["pending_categories"] == ["MASTER C1"]
    r = await client.post(
        f"{_IMPORTS_URL}/{parse_a}/acknowledge",
        json={"category_header": "MASTER C1", "reason": "verified_against_source"},
    )
    assert r.status_code == 200, r.text


class TestCommitPendingGateIsPerImport:
    @pytest.mark.asyncio
    async def test_candidate_about_another_import_does_not_block(
        self, coach_client, tmp_path, db_session_factory
    ):
        parse_a = await _stage_partial_import(coach_client, tmp_path)
        await _stage(coach_client, tmp_path, [_category("INFANTIL A", B_NAMES, 200)], 4)
        await _first_commit_and_acknowledge(coach_client, parse_a)
        await _seed_candidate(db_session_factory, _snapshot(B_NAMES[0]), _snapshot(B_NAMES[1]))

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_a}/commit-pending", json={"resolved_matches": []}
        )

        assert r.status_code == 200, r.text
        assert r.json()["pending_categories"] == []

    @pytest.mark.asyncio
    async def test_candidate_spanning_this_and_another_import_blocks(
        self, coach_client, tmp_path, db_session_factory
    ):
        parse_a = await _stage_partial_import(coach_client, tmp_path)
        await _stage(coach_client, tmp_path, [_category("INFANTIL A", B_NAMES, 200)], 4)
        await _first_commit_and_acknowledge(coach_client, parse_a)
        await _seed_candidate(db_session_factory, _snapshot(A_NAMES[0]), _snapshot(B_NAMES[0]))

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_a}/commit-pending", json={"resolved_matches": []}
        )

        assert r.status_code == 409, r.text
        assert r.json() == _identity_pending_body(parse_a, 1)

    @pytest.mark.asyncio
    async def test_candidate_about_a_new_competitor_of_this_import_blocks(
        self, coach_client, tmp_path, db_session_factory
    ):
        parse_a = await _stage_partial_import(coach_client, tmp_path)
        await _first_commit_and_acknowledge(coach_client, parse_a)
        await _seed_candidate(
            db_session_factory,
            _snapshot(A_NAMES[1], competitor_id=None),
            _snapshot(OUTSIDER, competitor_id=12345),
        )

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_a}/commit-pending", json={"resolved_matches": []}
        )

        assert r.status_code == 409, r.text
        assert r.json() == _identity_pending_body(parse_a, 1)

    @pytest.mark.asyncio
    async def test_candidate_about_rows_already_committed_does_not_block(
        self, coach_client, tmp_path, db_session_factory
    ):
        """Las filas de ``MASTER B1`` ya se ingestaron en el primer commit: un
        candidato sobre ellas no frena el ``/commit-pending`` de otra categoría."""
        parse_a = await _stage_partial_import(coach_client, tmp_path)
        await _first_commit_and_acknowledge(coach_client, parse_a)
        await _seed_candidate(
            db_session_factory, _snapshot("Hugo Sano Uno"), _snapshot(OUTSIDER)
        )

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_a}/commit-pending", json={"resolved_matches": []}
        )

        assert r.status_code == 200, r.text

    @pytest.mark.asyncio
    async def test_parent_is_denied(self, parent_client):
        r = await parent_client.post(
            f"{_IMPORTS_URL}/1/commit-pending", json={"resolved_matches": []}
        )
        assert r.status_code == 403


# ===========================================================================
# Cierre de los huecos del G2 (research R-08, notas 1–3)
# ===========================================================================


class TestGateSeesGeneralRows:
    """Nota 1: el ingestor crea/actualiza competidores desde las filas de
    GENERAL en TODAS las categorías; sus ternas también cuentan."""

    @pytest.mark.asyncio
    async def test_candidate_about_a_general_only_row_blocks_commit(
        self, coach_client, tmp_path, db_session_factory, general_rows
    ):
        general_rows["INF_B"] = [_general_row(GENERAL_ONLY)]  # otra categoría que RESULTADOS
        parse_a = await _stage(
            coach_client, tmp_path, [_category("INFANTIL A", A_NAMES, 100)], 3, with_general=True
        )
        await _seed_candidate(
            db_session_factory,
            _snapshot(GENERAL_ONLY, competitor_id=None),
            _snapshot(OUTSIDER, competitor_id=12345),
        )

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_a}/commit", json={"resolved_matches": []}
        )

        assert r.status_code == 409, r.text
        assert r.json() == _identity_pending_body(parse_a, 1)
        await _assert_not_committed(db_session_factory, parse_a)

    @pytest.mark.asyncio
    async def test_the_same_candidate_does_not_block_an_import_without_that_general_row(
        self, coach_client, tmp_path, db_session_factory, general_rows
    ):
        """Control: lo que frena es la fila de GENERAL, no el candidato."""
        general_rows["INF_B"] = [_general_row("Otra General Solo")]
        parse_a = await _stage(
            coach_client, tmp_path, [_category("INFANTIL A", A_NAMES, 100)], 3, with_general=True
        )
        await _seed_candidate(
            db_session_factory,
            _snapshot(GENERAL_ONLY, competitor_id=None),
            _snapshot(OUTSIDER, competitor_id=12345),
        )

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_a}/commit", json={"resolved_matches": []}
        )

        assert r.status_code == 200, r.text

    @pytest.mark.asyncio
    async def test_commit_pending_gate_sees_general_rows_too(
        self, coach_client, tmp_path, db_session_factory, general_rows
    ):
        """``/commit-pending`` vuelve a pasar GENERAL al ingestor: mismo candado."""
        general_rows["INF_B"] = [_general_row(GENERAL_ONLY)]
        ok_cat = _category("MASTER B1", ("Hugo Sano Uno", "Iris Sana Dos"), 300)
        gap_cat = _category("MASTER C1", A_NAMES, 100, gap=True)
        parse_a = await _stage(coach_client, tmp_path, [ok_cat, gap_cat], 3, with_general=True)
        await _first_commit_and_acknowledge(coach_client, parse_a)
        await _seed_candidate(
            db_session_factory,
            _snapshot(GENERAL_ONLY, competitor_id=None),
            _snapshot(OUTSIDER, competitor_id=12345),
        )

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_a}/commit-pending", json={"resolved_matches": []}
        )

        assert r.status_code == 409, r.text
        assert r.json() == _identity_pending_body(parse_a, 1)

    @pytest.mark.asyncio
    async def test_general_only_near_duplicate_of_a_club_athlete_blocks_until_decided(
        self, coach_client, tmp_path, db_session_factory, general_rows
    ):
        """De punta a punta, sin sembrar candidatos: la cola se recalcula con
        GENERAL en el universo, así que el casi-duplicado que solo trae GENERAL
        levanta la pregunta (antes el commit lo habría creado sin preguntar)."""
        await _seed_club_athlete(db_session_factory)
        general_rows["INF_A"] = [_general_row(NEAR_DUPLICATE)]
        parse_a = await _stage(
            coach_client, tmp_path, [_category("INFANTIL A", A_NAMES, 100)], 3, with_general=True
        )

        blocked = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_a}/commit", json={"resolved_matches": []}
        )

        assert blocked.status_code == 409, blocked.text
        assert blocked.json() == _identity_pending_body(parse_a, 1)
        await _assert_not_committed(db_session_factory, parse_a, baseline_results=1)
        (candidate_id,) = await _pending_candidate_ids(db_session_factory)
        await _decide(coach_client, candidate_id)

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_a}/commit", json={"resolved_matches": []}
        )

        assert r.status_code == 200, r.text


class TestGateWithARealRebuild:
    """Nota 3: los tests de arriba siembran candidatos a mano; aquí la cola la
    arma ``rebuild`` de verdad."""

    @pytest.mark.asyncio
    async def test_near_duplicate_row_blocks_until_the_coach_decides(
        self, coach_client, tmp_path, db_session_factory
    ):
        await _seed_club_athlete(db_session_factory)
        parse_a = await _stage(
            coach_client,
            tmp_path,
            [_category("INFANTIL A", (NEAR_DUPLICATE, *A_NAMES[1:]), 100)],
            3,
        )
        assert await _pending_candidate_ids(db_session_factory) == []  # nada sembrado

        blocked = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_a}/commit", json={"resolved_matches": []}
        )

        assert blocked.status_code == 409, blocked.text
        assert blocked.json() == _identity_pending_body(parse_a, 1)
        await _assert_not_committed(db_session_factory, parse_a, baseline_results=1)

        (candidate_id,) = await _pending_candidate_ids(db_session_factory)
        await _decide(coach_client, candidate_id)
        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_a}/commit", json={"resolved_matches": []}
        )

        assert r.status_code == 200, r.text
        assert r.json()["n_results_inserted"] == len(A_NAMES)

    @pytest.mark.asyncio
    async def test_commit_proceeds_when_the_candidate_is_about_a_row_in_a_gap_category(
        self, coach_client, tmp_path, db_session_factory
    ):
        """«Los commits parciales avanzan»: el candidato habla de una fila que
        solo está en una categoría con hueco (queda ``pending_categories``), o
        sea que este commit no la ingesta."""
        parse_a = await _stage_partial_import(coach_client, tmp_path)
        await _seed_candidate(db_session_factory, _snapshot(A_NAMES[0]), _snapshot(OUTSIDER))

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_a}/commit", json={"resolved_matches": []}
        )

        assert r.status_code == 200, r.text
        assert r.json()["pending_categories"] == ["MASTER C1"]


class TestCorrectionsRefreshTheQueue:
    """Nota 2: ``POST /corrections`` cambia las filas de la carga pero no
    tocaba ``imported_at``, así que la cola parecía «al día» y el candado no
    veía la fila corregida."""

    @staticmethod
    async def _add_row(client, parse_id: int, name: str) -> None:
        r = await client.post(
            f"{_IMPORTS_URL}/{parse_id}/corrections",
            json={
                "op": "add",
                "category_header": "INFANTIL A",
                "ordinal": 4,
                "row": {
                    "position": 4, "bib": "199", "name": name, "city": CITY,
                    "club": CLUB, "time_raw": "0:12:00", "points": 8,
                },
            },
        )
        assert r.status_code == 200, r.text

    @pytest.mark.asyncio
    async def test_correction_adding_a_near_duplicate_blocks_the_commit(
        self, coach_client, tmp_path, db_session_factory
    ):
        await _seed_club_athlete(db_session_factory)
        parse_a = await _stage(coach_client, tmp_path, [_category("INFANTIL A", A_NAMES, 100)], 3)
        # La cola queda al día DESPUÉS de la carga (un candidato de otra cosa).
        await _seed_candidate(db_session_factory, _snapshot(B_NAMES[0]), _snapshot(B_NAMES[1]))
        await self._add_row(coach_client, parse_a, NEAR_DUPLICATE)

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_a}/commit", json={"resolved_matches": []}
        )

        assert r.status_code == 409, r.text
        assert r.json() == _identity_pending_body(parse_a, 1)
        await _assert_not_committed(db_session_factory, parse_a, baseline_results=1)

    @pytest.mark.asyncio
    async def test_harmless_correction_still_commits(
        self, coach_client, tmp_path, db_session_factory
    ):
        """El recálculo por corrección no inventa bloqueos."""
        await _seed_club_athlete(db_session_factory)
        parse_a = await _stage(coach_client, tmp_path, [_category("INFANTIL A", A_NAMES, 100)], 3)
        await _seed_candidate(db_session_factory, _snapshot(B_NAMES[0]), _snapshot(B_NAMES[1]))
        await self._add_row(coach_client, parse_a, "Hugo Distinto Cinco")

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_a}/commit", json={"resolved_matches": []}
        )

        assert r.status_code == 200, r.text
        assert r.json()["n_results_inserted"] == len(A_NAMES) + 1

    @pytest.mark.asyncio
    async def test_queue_newer_than_the_last_correction_is_not_rebuilt(
        self, coach_client, tmp_path, db_session_factory
    ):
        """Si la cola es posterior a la última corrección no hay nada que
        recalcular (un rebuild reparsea todos los imports: minutos en Render).
        Se nota porque un rebuild podaría este candidato sembrado a mano, que
        no involucra a ningún atleta del club."""
        parse_a = await _stage(coach_client, tmp_path, [_category("INFANTIL A", A_NAMES, 100)], 3)
        await self._add_row(coach_client, parse_a, "Hugo Distinto Cinco")
        await _seed_candidate(db_session_factory, _snapshot(A_NAMES[0]), _snapshot(OUTSIDER))

        r = await coach_client.post(
            f"{_IMPORTS_URL}/{parse_a}/commit", json={"resolved_matches": []}
        )

        assert r.status_code == 409, r.text
        assert r.json() == _identity_pending_body(parse_a, 1)


class TestLatestCorrectionAt:
    """``_latest_correction_at``: lee ``corrections[*].at`` (ISO, UTC) del meta."""

    @staticmethod
    def _imp(meta):
        return SimpleNamespace(parse_meta_json=meta)

    def test_a_load_without_corrections_has_none(self):
        from app.routers.race_imports import _latest_correction_at

        assert _latest_correction_at(self._imp(None)) is None
        assert _latest_correction_at(self._imp({})) is None
        assert _latest_correction_at(self._imp({"corrections": []})) is None

    def test_takes_the_newest_as_naive_utc(self):
        from app.routers.race_imports import _latest_correction_at

        meta = {
            "corrections": [
                {"at": "2026-09-23T10:00:00+00:00"},
                {"at": "2026-09-23T12:30:00.250000+00:00"},
                {"at": "2026-09-23T11:00:00+00:00"},
            ]
        }
        assert _latest_correction_at(self._imp(meta)) == datetime(2026, 9, 23, 12, 30, 0, 250000)

    def test_converts_other_offsets_to_utc(self):
        from app.routers.race_imports import _latest_correction_at

        meta = {"corrections": [{"at": "2026-09-23T07:00:00-05:00"}]}
        assert _latest_correction_at(self._imp(meta)) == datetime(2026, 9, 23, 12, 0, 0)

    def test_skips_entries_without_a_readable_at(self):
        from app.routers.race_imports import _latest_correction_at

        meta = {
            "corrections": [
                {"op": "add"},
                {"at": None},
                {"at": "no es una fecha"},
                {"at": "2026-09-23T10:00:00+00:00"},
            ]
        }
        assert _latest_correction_at(self._imp(meta)) == datetime(2026, 9, 23, 10, 0, 0)
