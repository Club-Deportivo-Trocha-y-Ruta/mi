"""T038 (+ servicio de T047) — revisión de identidad (feature 044, US4).

Parte 1 — núcleo puro ``build_candidates`` sobre ``IdentityRecord`` hechos a
mano: reglas del contrato (apellido extra, apellidos invertidos, acentos;
``same_valida_two_categories``, ``sex_conflict``, ``age_path_backwards``,
``club_and_city_differ``; un cambio de club solo no levanta nada), bloqueo por
apellido y estabilidad de ``pair_hash``.

Parte 2 — cáscara de base de datos (aiosqlite): ``rebuild`` idempotente sobre
imports en staging + competidores existentes, decisiones nunca reiniciadas,
``decide``/``reverse`` antes y después del commit (split y merge), auditoría
sin nombres.

Nombres sintéticos, evidentemente ficticios.
"""
from __future__ import annotations

import json
import logging

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models.audit_log import AuditLog
from app.models.race_competitor import RaceCompetitor
from app.models.race_competitor_link_audit import LinkAuditAction, RaceCompetitorLinkAudit
from app.models.race_competitor_signature import RaceCompetitorSignature
from app.models.race_identity_candidate import (
    IdentityCandidateKind,
    IdentityCandidateState,
    RaceIdentityCandidate,
)
from app.models.race_result import RaceResult
from app.services.race import identity_review as ir
from app.services.race.identity_resolver import IdentityUnresolved, signature_triple
from tests.services.race.identity_support import (
    actor,
    ingest,
    loader_for,
    make_engine,
    row,
    session_factory,
    stage_import,
)

CLUB_A, CLUB_B = "Club Sintetico Norte", "Club Sintetico Sur"
CITY_A, CITY_B = "Ciudad Uno", "Ciudad Dos"
SYNTHETIC_NAMES = ("Ana Prueba Uno", "Ana Prueba Uno Dos", "Bruno Ficticio Tres")


# ---------------------------------------------------------------------------
# Parte 1 — núcleo puro
# ---------------------------------------------------------------------------


def rec(
    name: str,
    club: str = CLUB_A,
    city: str = CITY_A,
    *,
    sex: str | None = "F",
    competitor_id: int | None = None,
    linked: bool = False,
    apps: tuple[tuple[int, int, str, int | None], ...] = ((1, 2025, "INF_A_F", 9),),
) -> ir.IdentityRecord:
    """``apps``: ``(valida, season, code, age_rank)``; serie fija por temporada."""
    triple = signature_triple(name, club, city)
    return ir.IdentityRecord(
        key=ir.record_key(triple),
        name_printed=name,
        normalized_name=triple[0],
        club=club,
        club_norm=triple[1],
        city=city,
        city_norm=triple[2],
        sex=sex,
        competitor_id=competitor_id,
        athlete_linked=linked,
        appearances=tuple(
            ir.Appearance((season, valida), season, code, rank)
            for valida, season, code, rank in apps
        ),
    )


def _kinds(drafts):
    return [(d.kind, d.signals) for d in drafts]


#: Lado "atleta del club": competidor existente vinculado (decisión
#: 2026-09-22 — sin él, ningún par se pregunta).
CLUB = {"competitor_id": 900, "linked": True}


def test_extra_surname_is_same_person_suspect():
    drafts = ir.build_candidates(
        [
            rec("Ana Prueba Uno", apps=((1, 2025, "INF_A_F", 9),), **CLUB),
            rec("Ana Prueba Uno Dos", apps=((1, 2024, "INF_A_F", 9),)),
        ]
    )
    assert _kinds(drafts) == [(IdentityCandidateKind.same_person_suspect, ["extra_or_missing_surname"])]
    assert drafts[0].score >= ir.SAME_PERSON_MIN_SCORE


def test_inverted_surnames_is_same_person_suspect():
    drafts = ir.build_candidates(
        [
            rec("Ana Prueba Uno", apps=((1, 2025, "INF_A_F", 9),), **CLUB),
            rec("Ana Uno Prueba", apps=((2, 2025, "INF_A_F", 9),)),
        ]
    )
    assert _kinds(drafts) == [(IdentityCandidateKind.same_person_suspect, ["inverted_surname_order"])]


def test_accents_normalise_to_the_same_record_key():
    """Con y sin tilde es la misma terna: no hay par que preguntar."""
    assert signature_triple("Ána Pruéba Uno", CLUB_A, CITY_A) == signature_triple(
        "Ana Prueba Uno", CLUB_A, CITY_A
    )
    drafts = ir.build_candidates(
        [rec("Ána Pruéba Uno", club=CLUB_B, **CLUB), rec("Ana Prueba Uno", apps=((2, 2025, "INF_A_F", 9),))]
    )
    assert drafts == []  # mismo nombre, cambio de club solo


def test_club_only_change_raises_nothing():
    drafts = ir.build_candidates(
        [
            rec("Ana Prueba Uno", club=CLUB_A, apps=((1, 2024, "INF_A_F", 9),), **CLUB),
            rec("Ana Prueba Uno", club=CLUB_B, apps=((1, 2025, "INF_A_F", 9),)),
        ]
    )
    assert drafts == []


def test_club_and_city_both_differ_is_homonym_signal():
    drafts = ir.build_candidates(
        [
            rec("Ana Prueba Uno", club=CLUB_A, city=CITY_A, apps=((1, 2024, "INF_A_F", 9),), **CLUB),
            rec("Ana Prueba Uno", club="Escuadra Lejana", city="Pueblo Remoto", apps=((1, 2025, "INF_A_F", 9),)),
        ]
    )
    assert _kinds(drafts) == [(IdentityCandidateKind.homonym_suspect, ["club_and_city_differ"])]


def test_empty_city_never_counts_as_divergent():
    drafts = ir.build_candidates(
        [
            rec("Ana Prueba Uno", club=CLUB_A, city="", **CLUB),
            rec("Ana Prueba Uno", club="Escuadra Lejana", city="Pueblo Remoto", apps=((2, 2025, "INF_A_F", 9),)),
        ]
    )
    assert drafts == []


def test_same_valida_two_categories_is_homonym_signal():
    drafts = ir.build_candidates(
        [
            rec("Ana Prueba Uno", club=CLUB_A, apps=((1, 2025, "INF_A_F", 9),), **CLUB),
            rec("Ana Prueba Uno", club=CLUB_B, apps=((1, 2025, "MAS_F", None),)),
        ]
    )
    assert _kinds(drafts) == [
        (IdentityCandidateKind.homonym_suspect, ["same_valida_two_categories"])
    ]


def test_sex_conflict_is_homonym_signal():
    drafts = ir.build_candidates(
        [
            rec("Ana Prueba Uno", club=CLUB_A, sex="F", apps=((1, 2024, "INF_A_F", 9),), **CLUB),
            rec("Ana Prueba Uno", club=CLUB_B, sex="M", apps=((1, 2025, "INF_A", 9),)),
        ]
    )
    assert _kinds(drafts) == [(IdentityCandidateKind.homonym_suspect, ["sex_conflict"])]


def test_age_path_backwards_is_homonym_signal():
    drafts = ir.build_candidates(
        [
            rec("Ana Prueba Uno", club=CLUB_A, apps=((1, 2024, "INF_B_F", 11),), **CLUB),
            rec("Ana Prueba Uno", club=CLUB_B, apps=((1, 2025, "INF_A_F", 9),)),
        ]
    )
    assert _kinds(drafts) == [(IdentityCandidateKind.homonym_suspect, ["age_path_backwards"])]


@pytest.mark.parametrize(
    "other",
    [
        rec("Ana Prueba Uno Dos", sex="M", apps=((1, 2024, "INF_A", 9),)),  # sexo
        rec("Ana Prueba Uno Dos", apps=((1, 2025, "INF_B_F", 11),)),  # misma válida
        rec("Ana Prueba Uno Dos", apps=((1, 2026, "INF_A_F", 7),)),  # edad hacia atrás
    ],
)
def test_same_person_suspect_requires_compatible_evidence(other):
    assert ir.build_candidates([rec("Ana Prueba Uno", **CLUB), other]) == []


def test_blocking_needs_a_shared_surname_token():
    """Sin token de apellido compartido (≥ 3, sin el primero) no se compara."""
    drafts = ir.build_candidates(
        [rec("Carla Ejemplo", **CLUB), rec("Carla Ejemplos", apps=((2, 2025, "INF_A_F", 9),))]
    )
    assert drafts == []


def test_records_of_the_same_competitor_never_pair():
    drafts = ir.build_candidates(
        [
            rec("Ana Prueba Uno", competitor_id=5),
            rec("Ana Prueba Uno Dos", competitor_id=5, apps=((2, 2025, "INF_A_F", 9),)),
        ]
    )
    assert drafts == []


def test_two_existing_competitors_pair_only_as_same_person():
    homonyms = ir.build_candidates(
        [
            rec("Ana Prueba Uno", competitor_id=5, sex="F"),
            rec("Ana Prueba Uno", club=CLUB_B, competitor_id=6, sex="M"),
        ]
    )
    assert homonyms == []
    merge_question = ir.build_candidates(
        [
            rec("Ana Prueba Uno", competitor_id=5, linked=True, apps=((1, 2024, "INF_A_F", 9),)),
            rec("Ana Prueba Uno Dos", competitor_id=6),
        ]
    )
    assert [d.kind for d in merge_question] == [IdentityCandidateKind.same_person_suspect]


def test_name_shared_by_several_competitors_raises_signal_for_staged_record():
    drafts = ir.build_candidates(
        [
            rec("Ana Prueba Uno", club=CLUB_A, competitor_id=5, linked=True, apps=((1, 2024, "INF_A_F", 9),)),
            rec("Ana Prueba Uno", club=CLUB_B, competitor_id=6, linked=True, apps=((2, 2024, "INF_A_F", 9),)),
            rec("Ana Prueba Uno", club="Club Tercero", apps=((3, 2025, "INF_A_F", 9),)),
        ]
    )
    assert len(drafts) == 2
    assert all("multiple_existing_competitors" in d.signals for d in drafts)


def test_linked_athlete_involved_flag():
    drafts = ir.build_candidates(
        [
            rec("Ana Prueba Uno", competitor_id=5, linked=True, apps=((1, 2024, "INF_A_F", 9),)),
            rec("Ana Prueba Uno Dos"),
        ]
    )
    assert drafts[0].linked_athlete_involved is True


def test_pair_hash_is_order_independent_and_deterministic():
    a, b = rec("Ana Prueba Uno", **CLUB), rec("Ana Prueba Uno Dos", apps=((2, 2025, "INF_A_F", 9),))
    assert ir.pair_hash(a.key, b.key) == ir.pair_hash(b.key, a.key)
    assert ir.build_candidates([a, b]) == ir.build_candidates([b, a]) != []


# --- Alcance: solo pares con un atleta del club (decisión 2026-09-22) -------

_THIRD_PARTY_PAIRS = {
    "extra_surname": (
        rec("Ana Prueba Uno", apps=((1, 2025, "INF_A_F", 9),)),
        rec("Ana Prueba Uno Dos", apps=((1, 2024, "INF_A_F", 9),)),
    ),
    "club_and_city_differ": (
        rec("Ana Prueba Uno", apps=((1, 2024, "INF_A_F", 9),)),
        rec("Ana Prueba Uno", club="Escuadra Lejana", city="Pueblo Remoto"),
    ),
    "same_valida_two_categories": (
        rec("Ana Prueba Uno"),
        rec("Ana Prueba Uno", club=CLUB_B, apps=((1, 2025, "MAS_F", None),)),
    ),
    "sex_conflict": (
        rec("Ana Prueba Uno", sex="F", apps=((1, 2024, "INF_A_F", 9),)),
        rec("Ana Prueba Uno", club=CLUB_B, sex="M", apps=((1, 2025, "INF_A", 9),)),
    ),
    "existing_unlinked_vs_staged": (
        rec("Ana Prueba Uno", competitor_id=5, apps=((1, 2024, "INF_A_F", 9),)),
        rec("Ana Prueba Uno Dos"),
    ),
}


@pytest.mark.parametrize("pair", list(_THIRD_PARTY_PAIRS.values()), ids=list(_THIRD_PARTY_PAIRS))
def test_third_party_pairs_raise_nothing(pair):
    assert ir.build_candidates(list(pair)) == []


@pytest.mark.parametrize(
    "pair,kind",
    [
        (_THIRD_PARTY_PAIRS["extra_surname"], IdentityCandidateKind.same_person_suspect),
        (_THIRD_PARTY_PAIRS["sex_conflict"], IdentityCandidateKind.homonym_suspect),
    ],
    ids=["same_person", "homonym"],
)
def test_the_same_pair_with_a_club_side_still_raises(pair, kind):
    first, second = pair
    club_side = ir.IdentityRecord(
        **{**first.__dict__, "competitor_id": 900, "athlete_linked": True}
    )
    drafts = ir.build_candidates([club_side, second])
    assert [d.kind for d in drafts] == [kind]
    assert drafts[0].linked_athlete_involved is True


# ---------------------------------------------------------------------------
# Parte 2 — base de datos
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db():
    engine = await make_engine()
    async with session_factory(engine)() as session:
        yield session
    await engine.dispose()


async def _count(db, model, *where) -> int:
    stmt = select(func.count()).select_from(model)
    if where:
        stmt = stmt.where(*where)
    return int((await db.execute(stmt)).scalar_one())


async def _us4_universe(db):
    """Escenario de la prueba independiente de US4.

    Confirmado 2026: "Ana Prueba Uno" (club A, ciudad A), vinculada a un
    atleta del club.
    En staging 2025: la misma persona con segundo apellido y un homónimo de
    otro club y otra ciudad.
    """
    await ingest(db, 2026, 1, {"INF_A_F": [row("Ana Prueba Uno", club=CLUB_A, city=CITY_A)]})
    # Atleta del club: sin él ningún par entra a la cola (decisión 2026-09-22).
    (await db.execute(select(RaceCompetitor))).scalars().one().athlete_id = 4242
    imp = await stage_import(db, 2025, 3, sha="f" * 64)
    staged = {
        imp.id: {
            "INF_A_F": [
                row("Ana Prueba Uno Dos", club=CLUB_A, city=CITY_A, bib="11"),
                row("Ana Prueba Uno", club="Escuadra Lejana", city="Pueblo Remoto", bib="12", position=2),
            ]
        }
    }
    await db.commit()
    return imp, loader_for(staged), staged[imp.id]


async def _candidate_by_kind(db, kind):
    return (
        await db.execute(select(RaceIdentityCandidate).where(RaceIdentityCandidate.kind == kind))
    ).scalars().one()


@pytest.mark.asyncio
async def test_rebuild_raises_both_pairs_and_is_idempotent(db):
    _imp, loader, _rows = await _us4_universe(db)
    first = await ir.rebuild(db, rows_loader=loader)
    assert (first.created, first.unchanged, first.pending) == (2, 0, 2)
    kinds = sorted(
        c.kind.value for c in (await db.execute(select(RaceIdentityCandidate))).scalars()
    )
    assert kinds == ["homonym_suspect", "same_person_suspect"]

    second = await ir.rebuild(db, rows_loader=loader)
    assert (second.created, second.unchanged, second.pending) == (0, 2, 2)
    assert await _count(db, RaceIdentityCandidate) == 2


@pytest.mark.asyncio
async def test_rebuild_never_resets_a_decided_candidate(db):
    _imp, loader, _rows = await _us4_universe(db)
    await ir.rebuild(db, rows_loader=loader)
    homonym = await _candidate_by_kind(db, IdentityCandidateKind.homonym_suspect)
    await ir.decide(db, homonym.id, "different_people", actor=actor())
    result = await ir.rebuild(db, rows_loader=loader)
    assert result.created == 0 and result.pending == 1
    await db.refresh(homonym)
    assert homonym.state == IdentityCandidateState.different_people


@pytest.mark.asyncio
async def test_partially_committed_import_keeps_its_pending_rows_in_the_universe(db):
    """US5: tras un commit parcial, las categorías pendientes siguen en el
    universo — un homónimo entre ellas y una carga posterior se levanta, así
    que ``/commit-pending`` queda detrás del mismo gate. Un import confirmado
    sin pendientes sale del universo."""
    from app.models.race_import import RaceImportStatus

    await ingest(db, 2026, 1, {"INF_A_F": [row("Ana Prueba Uno", club=CLUB_A, city=CITY_A)]})
    (await db.execute(select(RaceCompetitor))).scalars().one().athlete_id = 4242
    partial = await stage_import(db, 2025, 3, sha="c" * 64)
    partial.status = RaceImportStatus.committed
    partial.parse_meta_json = {
        **partial.parse_meta_json,
        "pending_categories": ["INFANTIL A DAMAS"],
    }
    later = await stage_import(db, 2025, 4, sha="d" * 64)
    await db.commit()
    rows = {
        # El loader real ya filtra a las categorías pendientes del import.
        partial.id: {"INF_A_F": [row("Ana Prueba Uno Dos", club=CLUB_A, city=CITY_A)]},
        later.id: {"INF_A_F": [row("Bruno Ficticio Tres", bib="12")]},
    }
    result = await ir.rebuild(db, rows_loader=loader_for(rows))
    assert result.pending == 1
    assert (await _candidate_by_kind(db, IdentityCandidateKind.same_person_suspect)) is not None

    partial.parse_meta_json = {**partial.parse_meta_json, "pending_categories": []}
    await db.commit()
    universe = await ir.load_universe(db, loader_for(rows))
    assert universe.imports_scanned == 1


@pytest.mark.asyncio
async def test_unreadable_staged_import_is_reported_not_silenced(db):
    await stage_import(db, 2025, 4, sha="e" * 64)
    result = await ir.rebuild(db, rows_loader=loader_for({}))
    assert len(result.imports_unreadable) == 1


@pytest.mark.asyncio
async def test_us4_independent_test_end_to_end(db):
    """Ambos pares levantados; tras decidir, una persona para el primero y
    dos para el homónimo; nada se vuelve a preguntar en un nuevo rebuild."""
    _imp, loader, staged_rows = await _us4_universe(db)
    await ir.rebuild(db, rows_loader=loader)
    same = await _candidate_by_kind(db, IdentityCandidateKind.same_person_suspect)
    homonym = await _candidate_by_kind(db, IdentityCandidateKind.homonym_suspect)
    same_id, homonym_id = same.id, homonym.id
    await db.commit()

    # Con candidatos pendientes, la ingesta estricta es imposible (y el
    # ingestor hace rollback completo).
    with pytest.raises(IdentityUnresolved):
        await ingest(db, 2025, 3, staged_rows)

    await ir.decide(db, same_id, "same_person", actor=actor())
    await ir.decide(db, homonym_id, "different_people", actor=actor())
    await db.commit()
    assert await ir.summary(db) == {"pending": 0, "same_person": 1, "different_people": 1}

    report = await ingest(db, 2025, 3, staged_rows, sha="f" * 64)
    assert report.results_inserted == 2
    comps = (await db.execute(select(RaceCompetitor).order_by(RaceCompetitor.id))).scalars().all()
    assert len(comps) == 2  # la persona original + el homónimo
    results = (await db.execute(select(RaceResult).order_by(RaceResult.id))).scalars().all()
    assert results[0].competitor_id == results[1].competitor_id == comps[0].id
    assert results[2].competitor_id == comps[1].id

    rerun = await ir.rebuild(db, rows_loader=loader_for({}))
    assert rerun.created == 0 and rerun.pending == 0


@pytest.mark.asyncio
async def test_list_candidates_orders_by_score_and_hides_internal_keys(db):
    _imp, loader, _rows = await _us4_universe(db)
    await ir.rebuild(db, rows_loader=loader)
    page = await ir.list_candidates(db, state="pending", page=1, page_size=1)
    assert page.total == 2 and len(page.items) == 1
    assert set(page.items[0]["left"]) == {
        "name_printed", "club", "city", "seasons", "category_labels", "competitor_id",
        "athlete_linked",
    }
    second = await ir.list_candidates(db, page=2, page_size=1)
    assert page.items[0]["score"] >= second.items[0]["score"]
    assert {page.items[0]["kind"], second.items[0]["kind"]} == {
        "same_person_suspect", "homonym_suspect",
    }
    assert (await ir.list_candidates(db, kind="homonym_suspect")).total == 1


@pytest.mark.asyncio
async def test_decide_twice_is_refused(db):
    _imp, loader, _rows = await _us4_universe(db)
    await ir.rebuild(db, rows_loader=loader)
    same = await _candidate_by_kind(db, IdentityCandidateKind.same_person_suspect)
    await ir.decide(db, same.id, "same_person", actor=actor())
    with pytest.raises(ir.CandidateNotPending):
        await ir.decide(db, same.id, "different_people", actor=actor())
    with pytest.raises(ir.CandidateNotFound):
        await ir.decide(db, 99999, "same_person", actor=actor())
    with pytest.raises(ValueError):
        await ir.decide(db, same.id, "pending", actor=actor())


@pytest.mark.asyncio
async def test_reverse_before_commit_only_returns_to_queue(db):
    _imp, loader, _rows = await _us4_universe(db)
    await ir.rebuild(db, rows_loader=loader)
    same = await _candidate_by_kind(db, IdentityCandidateKind.same_person_suspect)
    await ir.decide(db, same.id, "same_person", actor=actor())
    outcome = await ir.reverse(db, same.id, actor=actor())
    assert outcome.state == "pending" and outcome.split is False
    assert same.reversed_at is not None and same.decided_at is not None
    with pytest.raises(ir.CandidateNotDecided):
        await ir.reverse(db, same.id, actor=actor())


@pytest.mark.asyncio
async def test_reverse_same_person_after_commit_splits_and_clears_link(db):
    _imp, loader, staged_rows = await _us4_universe(db)
    original = (await db.execute(select(RaceCompetitor))).scalars().one()
    await db.commit()
    await ir.rebuild(db, rows_loader=loader)
    same = await _candidate_by_kind(db, IdentityCandidateKind.same_person_suspect)
    homonym = await _candidate_by_kind(db, IdentityCandidateKind.homonym_suspect)
    await ir.decide(db, same.id, "same_person", actor=actor())
    await ir.decide(db, homonym.id, "different_people", actor=actor())
    await db.commit()
    await ingest(db, 2025, 3, staged_rows, sha="f" * 64)

    attached = (
        await db.execute(select(RaceResult).where(RaceResult.bib_number == 11))
    ).scalars().one()
    assert attached.competitor_id == original.id and attached.athlete_id == 4242

    outcome = await ir.reverse(db, same.id, actor=actor())
    await db.commit()
    assert outcome.split and outcome.results_moved == 1 and outcome.links_cleared == 1

    await db.refresh(attached)
    assert attached.competitor_id != original.id
    assert attached.athlete_id is None
    split_off = await db.get(RaceCompetitor, attached.competitor_id)
    assert split_off.athlete_id is None
    moved_sig = (
        await db.execute(
            select(RaceCompetitorSignature).where(
                RaceCompetitorSignature.competitor_id == split_off.id
            )
        )
    ).scalars().one()
    assert moved_sig.source_candidate_id is None
    link_audit = (await db.execute(select(RaceCompetitorLinkAudit))).scalars().one()
    assert link_audit.action == LinkAuditAction.unlink
    assert link_audit.competitor_id == split_off.id
    # El original conserva su resultado y su vínculo.
    await db.refresh(original)
    assert original.athlete_id == 4242
    assert await _count(db, RaceResult, RaceResult.competitor_id == original.id) == 1


@pytest.mark.asyncio
async def test_reverse_different_people_after_commit_keeps_them_apart(db):
    _imp, loader, staged_rows = await _us4_universe(db)
    await ir.rebuild(db, rows_loader=loader)
    same = await _candidate_by_kind(db, IdentityCandidateKind.same_person_suspect)
    homonym = await _candidate_by_kind(db, IdentityCandidateKind.homonym_suspect)
    await ir.decide(db, same.id, "same_person", actor=actor())
    await ir.decide(db, homonym.id, "different_people", actor=actor())
    await db.commit()
    await ingest(db, 2025, 3, staged_rows, sha="f" * 64)
    before = await _count(db, RaceCompetitor)

    outcome = await ir.reverse(db, homonym.id, actor=actor())
    assert outcome.split is False and outcome.results_moved == 0
    assert await _count(db, RaceCompetitor) == before == 2


@pytest.mark.asyncio
async def test_same_person_between_two_committed_competitors_merges_and_reverses(db):
    await ingest(db, 2024, 1, {"INF_A_F": [row("Ana Prueba Uno Dos", bib="21")]})
    await ingest(db, 2025, 1, {"INF_A_F": [row("Ana Prueba Uno", bib="22")]})
    older, newer = (
        await db.execute(select(RaceCompetitor).order_by(RaceCompetitor.id))
    ).scalars().all()
    newer.athlete_id = 4242  # la ficha vinculada es la más nueva
    await db.commit()

    await ir.rebuild(db, rows_loader=loader_for({}))
    cand = (await db.execute(select(RaceIdentityCandidate))).scalars().one()
    assert cand.kind == IdentityCandidateKind.same_person_suspect
    assert cand.linked_athlete_involved is True

    outcome = await ir.decide(db, cand.id, "same_person", actor=actor())
    await db.commit()
    assert outcome.merged and outcome.results_moved == 1
    assert await _count(db, RaceCompetitor) == 1
    survivor = (await db.execute(select(RaceCompetitor))).scalars().one()
    assert survivor.id == older.id and survivor.athlete_id == 4242
    results = (await db.execute(select(RaceResult))).scalars().all()
    assert {r.competitor_id for r in results} == {older.id}
    assert {r.athlete_id for r in results} == {4242}
    assert await _count(db, RaceCompetitorSignature) == 2

    split = await ir.reverse(db, cand.id, actor=actor())
    await db.commit()
    assert split.split and split.results_moved == 1
    assert await _count(db, RaceCompetitor) == 2
    moved = (await db.execute(select(RaceResult).where(RaceResult.bib_number == 22))).scalars().one()
    assert moved.competitor_id != older.id and moved.athlete_id is None


@pytest.mark.asyncio
async def test_merge_refused_when_linked_to_different_athletes(db):
    await ingest(db, 2024, 1, {"INF_A_F": [row("Ana Prueba Uno Dos", bib="21")]})
    await ingest(db, 2025, 1, {"INF_A_F": [row("Ana Prueba Uno", bib="22")]})
    a, b = (await db.execute(select(RaceCompetitor).order_by(RaceCompetitor.id))).scalars().all()
    a.athlete_id, b.athlete_id = 1, 2
    await db.commit()
    await ir.rebuild(db, rows_loader=loader_for({}))
    cand = (await db.execute(select(RaceIdentityCandidate))).scalars().one()
    with pytest.raises(ir.IdentityDecisionConflict) as exc:
        await ir.decide(db, cand.id, "same_person", actor=actor())
    assert exc.value.code == "linked_to_different_athletes"


@pytest.mark.asyncio
async def test_audit_and_logs_carry_ids_never_names(db, caplog):
    caplog.set_level(logging.DEBUG, logger="app")
    _imp, loader, staged_rows = await _us4_universe(db)
    await ir.rebuild(db, rows_loader=loader)
    same = await _candidate_by_kind(db, IdentityCandidateKind.same_person_suspect)
    await ir.decide(db, same.id, "same_person", actor=actor())
    await ir.reverse(db, same.id, actor=actor())
    await db.commit()

    rows = (
        await db.execute(
            select(AuditLog).where(AuditLog.entity_type == "race_identity_candidate")
        )
    ).scalars().all()
    assert len(rows) == 2
    assert rows[0].meta_json["pair_hash"] == same.pair_hash
    dumped = json.dumps([[r.meta_json, r.diff_json] for r in rows]).lower()
    # Solo los logs de la aplicación (el driver de sqlite loguea parámetros
    # en DEBUG por su cuenta; eso no es código del proyecto).
    logs = "\n".join(
        r.getMessage() for r in caplog.records if r.name.startswith("app")
    ).lower()
    assert "race_identity_decided" in logs
    for name in SYNTHETIC_NAMES + (CLUB_A, CITY_A, "Escuadra Lejana", "Pueblo Remoto"):
        assert name.lower() not in dumped
        assert name.lower() not in logs


# ---------------------------------------------------------------------------
# Separación por categoría — padre e hijo con el mismo nombre, club y ciudad
# (decisión del dueño 2026-09-21)
# ---------------------------------------------------------------------------

PARENT_CHILD = "Mateo Ficticio Igual"


def test_split_by_category_groups_a_growing_child_and_separates_the_parent():
    apps = [
        ir.Appearance((1, 1), 2025, "INF_A", 9, "M", 9, 10),
        ir.Appearance((1, 1), 2025, "MAS_A", None, "M", 30, 39),
        ir.Appearance((2, 1), 2026, "INF_B", 11, "M", 11, 12),
        ir.Appearance((2, 1), 2026, "MAS_A", None, "M", 30, 39),
    ]
    groups = ir.split_by_category(apps)
    assert [d for d, _ in groups] == ["M:9-10@2025", "M:30-39@2025"]
    assert [sorted(a.category_code for a in m) for _, m in groups] == [
        ["INF_A", "INF_B"], ["MAS_A", "MAS_A"],
    ]
    one_child = [apps[0], apps[2]]
    assert len(ir.split_by_category(one_child)) == 1


async def _stage_parent_child(db):
    imp = await stage_import(db, 2025, 5, sha="a" * 64)
    rows = {
        "INF_A": [row(PARENT_CHILD, bib="31")],
        "MAS_A": [row(PARENT_CHILD, bib="32")],
    }
    await db.commit()
    return loader_for({imp.id: rows}), rows


async def _club_child(db, *, bib: str = "30"):
    """El hijo ya confirmado en 2024 (Infantil A) y vinculado a un atleta del
    club: la terna la gestiona la cola (decisión 2026-09-22)."""
    await ingest(db, 2024, 1, {"INF_A": [row(PARENT_CHILD, bib=bib)]})
    child = (await db.execute(select(RaceCompetitor))).scalars().one()
    child.athlete_id = 4242
    await db.commit()
    return child


@pytest.mark.asyncio
async def test_parent_and_child_of_a_club_athlete_end_as_two_competitors(db):
    child = await _club_child(db, bib="30")
    loader, rows = await _stage_parent_child(db)
    result = await ir.rebuild(db, rows_loader=loader)
    assert result.created == 1
    cand = (await db.execute(select(RaceIdentityCandidate))).scalars().one()
    assert cand.kind == IdentityCandidateKind.homonym_suspect
    assert cand.linked_athlete_involved is True
    page = await ir.list_candidates(db)
    assert "discriminator" not in page.items[0]["left"]

    await ir.decide(db, cand.id, "different_people", actor=actor())
    await db.commit()
    report = await ingest(db, 2025, 5, rows, sha="a" * 64)
    assert report.results_inserted == 2
    comps = (await db.execute(select(RaceCompetitor))).scalars().all()
    assert len(comps) == 2
    by_bib = {
        r.bib_number: r.competitor_id
        for r in (await db.execute(select(RaceResult))).scalars().all()
    }
    assert by_bib[31] == by_bib[30] == child.id and by_bib[32] != child.id

    # La válida siguiente se reparte sola por categoría.
    await ingest(
        db, 2026, 1,
        {"INF_B": [row(PARENT_CHILD, bib="41")], "MAS_A": [row(PARENT_CHILD, bib="42")]},
    )
    by_bib = {
        r.bib_number: r.competitor_id
        for r in (await db.execute(select(RaceResult))).scalars().all()
    }
    assert by_bib[41] == by_bib[31] and by_bib[42] == by_bib[32]
    assert by_bib[31] != by_bib[32]

    rerun = await ir.rebuild(db, rows_loader=loader_for({}))
    assert rerun.created == 0 and rerun.pending == 0


@pytest.mark.asyncio
async def test_third_party_parent_and_child_split_without_asking(db):
    """Solo terceros: la cola no pregunta y la ingesta los separa por
    categoría (misma válida, dos categorías) sin perder filas."""
    loader, rows = await _stage_parent_child(db)
    result = await ir.rebuild(db, rows_loader=loader)
    assert (result.created, result.pending) == (0, 0)

    report = await ingest(db, 2025, 5, rows, sha="a" * 64)
    assert report.results_inserted == 2
    by_bib = {
        r.bib_number: r.competitor_id
        for r in (await db.execute(select(RaceResult))).scalars().all()
    }
    assert by_bib[31] != by_bib[32]
    await ingest(
        db, 2026, 1,
        {"INF_B": [row(PARENT_CHILD, bib="41")], "MAS_A": [row(PARENT_CHILD, bib="42")]},
    )
    by_bib = {
        r.bib_number: r.competitor_id
        for r in (await db.execute(select(RaceResult))).scalars().all()
    }
    assert by_bib[41] == by_bib[31] and by_bib[42] == by_bib[32]
    assert await _count(db, RaceIdentityCandidate) == 0


@pytest.mark.asyncio
async def test_third_party_same_category_collision_keeps_every_row(db):
    """Misma terna, misma válida y misma categoría (terceros): dos
    competidores por dorsal, ninguna pregunta, ninguna fila perdida."""
    imp = await stage_import(db, 2025, 6, sha="9" * 64)
    rows = {"MAS_A": [row(PARENT_CHILD, bib="81"), row(PARENT_CHILD, bib="82", position=2)]}
    await db.commit()
    result = await ir.rebuild(db, rows_loader=loader_for({imp.id: rows}))
    assert result.pending == 0
    report = await ingest(db, 2025, 6, rows, sha="9" * 64)
    assert report.results_inserted == 2
    assert await _count(db, RaceCompetitor) == 2
    assert await _count(db, RaceResult) == 2


async def _mixture_across_validas(db):
    """Padre e hijo de terceros confirmados en válidas distintas bajo una
    misma terna: un solo competidor (datos previos al alcance por club)."""
    await ingest(db, 2026, 1, {"INF_A": [row(PARENT_CHILD, bib="51")]})
    await ingest(db, 2026, 2, {"MAS_A": [row(PARENT_CHILD, bib="52")]})
    assert await _count(db, RaceCompetitor) == 1


@pytest.mark.asyncio
async def test_third_party_committed_mixture_raises_nothing(db):
    await _mixture_across_validas(db)
    result = await ir.rebuild(db, rows_loader=loader_for({}))
    assert (result.created, result.pending) == (0, 0)


@pytest.mark.asyncio
async def test_committed_mixture_is_split_on_different_people(db, monkeypatch):
    """Un candidato previo a la decisión 2026-09-22 (fuera del alcance de
    hoy, pero ya en la cola) sigue partiendo la mezcla, resultados
    incluidos."""
    await _mixture_across_validas(db)
    monkeypatch.setattr(ir, "in_club_scope", lambda a, b: True)
    await ir.rebuild(db, rows_loader=loader_for({}))
    cand = (await db.execute(select(RaceIdentityCandidate))).scalars().one()

    outcome = await ir.decide(db, cand.id, "different_people", actor=actor())
    await db.commit()
    assert outcome.results_moved == 1
    by_bib = {
        r.bib_number: r.competitor_id
        for r in (await db.execute(select(RaceResult))).scalars().all()
    }
    assert by_bib[51] != by_bib[52]
    discs = sorted(
        s.discriminator for s in (await db.execute(select(RaceCompetitorSignature))).scalars()
    )
    assert discs == ["M:30-39@2026", "M:9-10@2026"]
    rerun = await ir.rebuild(db, rows_loader=loader_for({}))
    assert rerun.created == 0


@pytest.mark.asyncio
async def test_committed_mixture_linked_to_an_athlete_is_refused(db):
    await _mixture_across_validas(db)
    comp = (await db.execute(select(RaceCompetitor))).scalars().one()
    comp.athlete_id = 4242
    await db.commit()
    await ir.rebuild(db, rows_loader=loader_for({}))
    cand = (await db.execute(select(RaceIdentityCandidate))).scalars().one()
    with pytest.raises(ir.IdentityDecisionConflict) as exc:
        await ir.decide(db, cand.id, "different_people", actor=actor())
    assert exc.value.code == "linked_competitor_ambiguous"


@pytest.mark.asyncio
async def test_reversing_a_label_only_split_restores_the_plain_signature(db):
    """Una sola persona confirmada (atleta del club) + la otra en staging: la
    decisión solo etiqueta la firma; revertir antes del commit la deja como
    estaba."""
    await ingest(db, 2025, 1, {"MAS_A": [row(PARENT_CHILD, bib="61")]})
    (await db.execute(select(RaceCompetitor))).scalars().one().athlete_id = 4242
    loader, _rows = await _stage_parent_child(db)
    await ir.rebuild(db, rows_loader=loader)
    cand = (await db.execute(select(RaceIdentityCandidate))).scalars().one()
    await ir.decide(db, cand.id, "different_people", actor=actor())
    sig = (await db.execute(select(RaceCompetitorSignature))).scalars().one()
    assert sig.discriminator == "M:30-39@2025"

    await ir.reverse(db, cand.id, actor=actor())
    await db.refresh(sig)
    assert sig.discriminator == ""


@pytest.mark.asyncio
async def test_reversal_stays_exact_after_a_category_split(db):
    """Un par same_person sobre un competidor separado por categoría sigue
    revirtiendo exactamente sus resultados."""
    await _club_child(db, bib="30")
    loader, rows = await _stage_parent_child(db)
    await ir.rebuild(db, rows_loader=loader)
    homonym = (await db.execute(select(RaceIdentityCandidate))).scalars().one()
    await ir.decide(db, homonym.id, "different_people", actor=actor())
    await db.commit()
    await ingest(db, 2025, 5, rows, sha="a" * 64)

    # El niño aparece luego con segundo apellido: misma persona.
    imp = await stage_import(db, 2026, 2, sha="b" * 64)
    staged = {"INF_B": [row(PARENT_CHILD + " Dos", bib="71")]}
    await db.commit()
    await ir.rebuild(db, rows_loader=loader_for({imp.id: staged}))
    same = (
        await db.execute(
            select(RaceIdentityCandidate).where(
                RaceIdentityCandidate.kind == IdentityCandidateKind.same_person_suspect
            )
        )
    ).scalars().all()
    child_pair = [
        c for c in same
        if "M:9-10@2024" in (c.left_record.get("discriminator", ""), c.right_record.get("discriminator", ""))
    ]
    assert len(child_pair) == 1
    for other in same:
        if other is not child_pair[0]:
            await ir.decide(db, other.id, "different_people", actor=actor())
    await ir.decide(db, child_pair[0].id, "same_person", actor=actor())
    await db.commit()
    await ingest(db, 2026, 2, staged, sha="b" * 64)
    by_bib = {
        r.bib_number: r.competitor_id
        for r in (await db.execute(select(RaceResult))).scalars().all()
    }
    assert by_bib[71] == by_bib[31]

    outcome = await ir.reverse(db, child_pair[0].id, actor=actor())
    await db.commit()
    assert outcome.split and outcome.results_moved == 1
    by_bib = {
        r.bib_number: r.competitor_id
        for r in (await db.execute(select(RaceResult))).scalars().all()
    }
    assert by_bib[71] not in (by_bib[31], by_bib[32])
    assert by_bib[31] != by_bib[32]


# ---------------------------------------------------------------------------
# Rebuild: poda de la cola fuera de alcance (decisión 2026-09-22)
# ---------------------------------------------------------------------------


async def _seed_candidate(db, left, right, state, *, decided=False):
    cand = RaceIdentityCandidate(
        kind=IdentityCandidateKind.homonym_suspect,
        pair_hash=ir.pair_hash(left.key, right.key),
        left_record=left.snapshot(),
        right_record=right.snapshot(),
        score=100,
        signals=["club_and_city_differ"],
        state=state,
        linked_athlete_involved=left.athlete_linked or right.athlete_linked,
    )
    if decided:
        from datetime import datetime, timezone

        cand.decided_at = datetime.now(timezone.utc)
    db.add(cand)
    await db.flush()
    return cand


@pytest.mark.asyncio
async def test_rebuild_removes_out_of_scope_pending_but_keeps_decided(db):
    _imp, loader, _rows = await _us4_universe(db)
    third_a = rec("Bruno Ficticio Tres")
    third_b = rec("Bruno Ficticio Tres", club="Escuadra Lejana", city="Pueblo Remoto")
    third_c = rec("Carla Ejemplo")
    third_d = rec("Carla Ejemplo", club="Escuadra Lejana", city="Pueblo Remoto")
    stale = await _seed_candidate(db, third_a, third_b, IdentityCandidateState.pending)
    decided = await _seed_candidate(
        db, third_c, third_d, IdentityCandidateState.different_people, decided=True
    )
    stale_id, decided_id = stale.id, decided.id
    await db.commit()

    result = await ir.rebuild(db, rows_loader=loader)
    await db.commit()
    assert result.removed == 1
    assert result.pending == 2  # los dos pares con el atleta del club
    remaining = {c.id for c in (await db.execute(select(RaceIdentityCandidate))).scalars()}
    assert stale_id not in remaining and decided_id in remaining

    again = await ir.rebuild(db, rows_loader=loader)
    assert again.removed == 0 and again.pending == 2


# ---------------------------------------------------------------------------
# Candado por carga (feature 045, US3, T022 — research R-08)
# ---------------------------------------------------------------------------


def test_import_record_keys_are_bare_triple_keys_and_skip_nameless_rows():
    keys = ir.import_record_keys(
        {
            "INF_A_F": [row("Ana Prueba Uno"), row("Ána Pruéba Uno"), row("   ")],
            "INF_B_F": [row("Bruno Ficticio Tres", club=CLUB_B, city=CITY_B)],
        }
    )
    assert keys == {
        ir.record_key(signature_triple("Ana Prueba Uno", CLUB_A, CITY_A)),
        ir.record_key(signature_triple("Bruno Ficticio Tres", CLUB_B, CITY_B)),
    }


def test_import_record_keys_of_no_rows_is_empty():
    assert ir.import_record_keys({}) == set()
    assert ir.import_record_keys({"INF_A_F": []}) == set()


def test_base_key_drops_the_category_discriminator_only():
    plain = ir.record_key(signature_triple("Ana Prueba Uno", CLUB_A, CITY_A))
    split = ir.record_key(signature_triple("Ana Prueba Uno", CLUB_A, CITY_A), "F:2015-2016")
    assert ir.base_key(split) == plain
    assert ir.base_key(plain) == plain
    empty_club_and_city = ir.record_key(signature_triple("Ana Prueba Uno", "", ""))
    assert ir.base_key(empty_club_and_city) == empty_club_and_city


@pytest.mark.asyncio
async def test_import_record_keys_are_the_keys_of_the_queue_universe(db):
    """La clave con que el candado reconoce las filas de una carga es la
    misma que ``load_universe`` le da a sus registros — así un candidato
    calculado ANTES del commit sigue reconociéndose (R-08, punto (a))."""
    imp, loader, staged_rows = await _us4_universe(db)
    universe_keys = {r.key for r in (await ir.load_universe(db, loader)).records}
    assert ir.import_record_keys(staged_rows) <= universe_keys


@pytest.mark.asyncio
async def test_pending_for_import_matches_either_side_and_only_pending(db):
    mine = rec("Ana Prueba Uno")
    left_hit = await _seed_candidate(db, mine, rec("Bruno Ficticio Tres"), IdentityCandidateState.pending)
    right_hit = await _seed_candidate(db, rec("Carla Ejemplo"), mine, IdentityCandidateState.pending)
    await _seed_candidate(
        db, rec("Bruno Ficticio Tres"), rec("Carla Ejemplo"), IdentityCandidateState.pending
    )  # habla de otra carga
    await _seed_candidate(
        db, mine, rec("Dario Muestra Uno"), IdentityCandidateState.same_person, decided=True
    )  # ya decidido
    await _seed_candidate(
        db, mine, rec("Elena Muestra Dos"), IdentityCandidateState.different_people, decided=True
    )
    await db.commit()

    found = await ir.pending_candidates_for_import(db, {mine.key})

    assert [c.id for c in found] == sorted([left_hit.id, right_hit.id])


@pytest.mark.asyncio
async def test_pending_for_import_with_no_keys_finds_nothing(db):
    await _seed_candidate(
        db, rec("Ana Prueba Uno"), rec("Bruno Ficticio Tres"), IdentityCandidateState.pending
    )
    await db.commit()
    assert await ir.pending_candidates_for_import(db, set()) == []


@pytest.mark.asyncio
async def test_pending_for_import_includes_a_decision_reversed_to_pending(db):
    """Una reversión devuelve el par a la cola con sus sellos ``decided_*``:
    sigue siendo una pregunta sin responder para la carga."""
    mine = rec("Ana Prueba Uno")
    cand = await _seed_candidate(
        db, mine, rec("Bruno Ficticio Tres"), IdentityCandidateState.pending, decided=True
    )
    await db.commit()
    assert [c.id for c in await ir.pending_candidates_for_import(db, {mine.key})] == [cand.id]


@pytest.mark.asyncio
async def test_pending_for_import_matches_a_side_split_by_category(db):
    """El registro de la cola pudo separarse por categoría (clave con
    discriminador) por cómo se ve el universo en ese momento; la carga sigue
    siendo la misma terna y debe frenarse igual."""
    mine = rec("Ana Prueba Uno")
    split = ir.IdentityRecord(
        **{**mine.__dict__, "key": ir.record_key(mine.triple, "F:2015-2016"), "discriminator": "F:2015-2016"}
    )
    cand = await _seed_candidate(db, split, rec("Bruno Ficticio Tres"), IdentityCandidateState.pending)
    await db.commit()
    assert [c.id for c in await ir.pending_candidates_for_import(db, {mine.key})] == [cand.id]


@pytest.mark.asyncio
async def test_pending_for_import_ignores_snapshots_without_a_key(db):
    db.add(
        RaceIdentityCandidate(
            kind=IdentityCandidateKind.same_person_suspect,
            pair_hash="k" * 64,
            left_record={"name_printed": "Ana Prueba Uno"},
            right_record={},
            score=95,
            signals=[],
            state=IdentityCandidateState.pending,
            linked_athlete_involved=False,
        )
    )
    await db.commit()
    assert await ir.pending_candidates_for_import(db, {rec("Ana Prueba Uno").key}) == []


# ---------------------------------------------------------------------------
# GENERAL en el candado y en el universo (feature 045 — R-08, nota 1 del G2)
#
# El ingestor crea/actualiza competidores desde las filas de GENERAL en TODAS
# las categorías, así que el candado de una carga y el universo de la cola
# deben verlas (antes eran invisibles para ambos).
# ---------------------------------------------------------------------------


def _key_of(name: str, club: str = CLUB_A, city: str = CITY_A) -> str:
    return ir.record_key(signature_triple(name, club, city))


def loader_with_general(by_import: dict[int, "ir.ImportRows"]):
    """``rows_loader`` de prueba que devuelve RESULTADOS + GENERAL."""

    async def _load(imp):
        return by_import[imp.id]

    return _load


async def _club_athlete_and_staged_import(db):
    """"Ana Prueba Uno", atleta del club confirmada en 2026, y un import en
    staging de 2025 (válida 3)."""
    await ingest(db, 2026, 1, {"INF_A_F": [row("Ana Prueba Uno", club=CLUB_A, city=CITY_A)]})
    (await db.execute(select(RaceCompetitor))).scalars().one().athlete_id = 4242
    imp = await stage_import(db, 2025, 3, sha="g" * 64)
    await db.commit()
    return imp


def test_import_record_keys_include_general_rows_of_any_category():
    keys = ir.import_record_keys(
        {"INF_A_F": [row("Ana Prueba Uno")]},
        general_by_category={
            "INF_B_F": [row("Bruno Ficticio Tres", club=CLUB_B, city=CITY_B), row("   ")],
        },
    )
    assert keys == {
        _key_of("Ana Prueba Uno"),
        _key_of("Bruno Ficticio Tres", CLUB_B, CITY_B),
    }


def test_import_record_keys_without_general_are_unchanged():
    rows = {"INF_A_F": [row("Ana Prueba Uno")]}
    assert ir.import_record_keys(rows, general_by_category=None) == ir.import_record_keys(rows)
    assert ir.import_record_keys(rows, general_by_category={}) == ir.import_record_keys(rows)


@pytest.mark.asyncio
async def test_general_only_row_enters_the_universe_and_raises_a_candidate(db):
    imp = await _club_athlete_and_staged_import(db)
    loader = loader_with_general(
        {
            imp.id: ir.ImportRows(
                results={"INF_A_F": [row("Bruno Ficticio Tres", bib="12")]},
                general={"INF_A_F": [row("Ana Prueba Uno Dos")]},
            )
        }
    )

    universe = await ir.load_universe(db, loader)
    general_only = next(r for r in universe.records if r.key == _key_of("Ana Prueba Uno Dos"))
    assert general_only.competitor_id is None  # aún no existe: el commit lo crearía

    result = await ir.rebuild(db, rows_loader=loader)
    assert result.pending == 1
    cand = await _candidate_by_kind(db, IdentityCandidateKind.same_person_suspect)
    assert _key_of("Ana Prueba Uno Dos") in {cand.left_record["key"], cand.right_record["key"]}


@pytest.mark.asyncio
async def test_general_row_of_a_triple_already_in_the_results_adds_nothing(db):
    """La terna ya está en el universo por RESULTADOS (aunque GENERAL la liste
    en dos categorías): no se duplica la aparición."""
    imp = await _club_athlete_and_staged_import(db)
    results = {"INF_A_F": [row("Ana Prueba Uno Dos", bib="11")]}
    plain = await ir.load_universe(db, loader_with_general({imp.id: ir.ImportRows(results=results)}))
    with_general = await ir.load_universe(
        db,
        loader_with_general(
            {
                imp.id: ir.ImportRows(
                    results=results,
                    general={
                        "INF_A_F": [row("Ana Prueba Uno Dos")],
                        "INF_B_F": [row("Ana Prueba Uno Dos")],
                    },
                )
            }
        ),
    )
    key = _key_of("Ana Prueba Uno Dos")
    assert [r for r in with_general.records if r.key == key] == [
        r for r in plain.records if r.key == key
    ]


@pytest.mark.asyncio
async def test_general_row_of_an_existing_competitor_adds_no_appearance(db):
    """Un competidor ya existente está en el universo por su firma; una fila
    de GENERAL con su terna exacta no le suma una aparición de otra
    categoría (evita partirlo en dos personas)."""
    imp = await _club_athlete_and_staged_import(db)
    results = {"INF_A_F": [row("Bruno Ficticio Tres", bib="12")]}
    plain = await ir.load_universe(db, loader_with_general({imp.id: ir.ImportRows(results=results)}))
    with_general = await ir.load_universe(
        db,
        loader_with_general(
            {imp.id: ir.ImportRows(results=results, general={"INF_B_F": [row("Ana Prueba Uno")]})}
        ),
    )
    key = _key_of("Ana Prueba Uno")
    assert [r for r in with_general.records if r.key == key] == [
        r for r in plain.records if r.key == key
    ]


@pytest.mark.asyncio
async def test_general_appearance_is_never_a_valida_shared_with_the_results(db):
    """GENERAL es el acumulado de la temporada, no una válida: que la atleta
    corra ESTA válida en la misma categoría no prueba que la variante de
    GENERAL sea otra persona. Con la válida real, ``same_valida_same_category``
    apagaría el candidato y el gate no vería el casi-duplicado."""
    imp = await _club_athlete_and_staged_import(db)
    loader = loader_with_general(
        {
            imp.id: ir.ImportRows(
                results={"INF_A_F": [row("Ana Prueba Uno", bib="11")]},
                general={"INF_A_F": [row("Ana Prueba Uno Dos")]},
            )
        }
    )

    result = await ir.rebuild(db, rows_loader=loader)

    assert result.pending == 1
    cand = await _candidate_by_kind(db, IdentityCandidateKind.same_person_suspect)
    assert _key_of("Ana Prueba Uno Dos") in {cand.left_record["key"], cand.right_record["key"]}


@pytest.mark.asyncio
async def test_a_plain_mapping_loader_still_works(db):
    """``RowsLoader`` conserva su contrato: un ``dict`` de RESULTADOS sigue
    siendo válido (sin GENERAL)."""
    imp = await _club_athlete_and_staged_import(db)
    loader = loader_for({imp.id: {"INF_A_F": [row("Ana Prueba Uno Dos", bib="11")]}})
    result = await ir.rebuild(db, rows_loader=loader)
    assert result.pending == 1
