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


def test_extra_surname_is_same_person_suspect():
    drafts = ir.build_candidates(
        [
            rec("Ana Prueba Uno", apps=((1, 2025, "INF_A_F", 9),)),
            rec("Ana Prueba Uno Dos", apps=((1, 2024, "INF_A_F", 9),)),
        ]
    )
    assert _kinds(drafts) == [(IdentityCandidateKind.same_person_suspect, ["extra_or_missing_surname"])]
    assert drafts[0].score >= ir.SAME_PERSON_MIN_SCORE


def test_inverted_surnames_is_same_person_suspect():
    drafts = ir.build_candidates(
        [
            rec("Ana Prueba Uno", apps=((1, 2025, "INF_A_F", 9),)),
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
        [rec("Ána Pruéba Uno", club=CLUB_B), rec("Ana Prueba Uno", apps=((2, 2025, "INF_A_F", 9),))]
    )
    assert drafts == []  # mismo nombre, cambio de club solo


def test_club_only_change_raises_nothing():
    drafts = ir.build_candidates(
        [
            rec("Ana Prueba Uno", club=CLUB_A, apps=((1, 2024, "INF_A_F", 9),)),
            rec("Ana Prueba Uno", club=CLUB_B, apps=((1, 2025, "INF_A_F", 9),)),
        ]
    )
    assert drafts == []


def test_club_and_city_both_differ_is_homonym_signal():
    drafts = ir.build_candidates(
        [
            rec("Ana Prueba Uno", club=CLUB_A, city=CITY_A, apps=((1, 2024, "INF_A_F", 9),)),
            rec("Ana Prueba Uno", club="Escuadra Lejana", city="Pueblo Remoto", apps=((1, 2025, "INF_A_F", 9),)),
        ]
    )
    assert _kinds(drafts) == [(IdentityCandidateKind.homonym_suspect, ["club_and_city_differ"])]


def test_empty_city_never_counts_as_divergent():
    drafts = ir.build_candidates(
        [
            rec("Ana Prueba Uno", club=CLUB_A, city=""),
            rec("Ana Prueba Uno", club="Escuadra Lejana", city="Pueblo Remoto", apps=((2, 2025, "INF_A_F", 9),)),
        ]
    )
    assert drafts == []


def test_same_valida_two_categories_is_homonym_signal():
    drafts = ir.build_candidates(
        [
            rec("Ana Prueba Uno", club=CLUB_A, apps=((1, 2025, "INF_A_F", 9),)),
            rec("Ana Prueba Uno", club=CLUB_B, apps=((1, 2025, "MAS_F", None),)),
        ]
    )
    assert _kinds(drafts) == [
        (IdentityCandidateKind.homonym_suspect, ["same_valida_two_categories"])
    ]


def test_sex_conflict_is_homonym_signal():
    drafts = ir.build_candidates(
        [
            rec("Ana Prueba Uno", club=CLUB_A, sex="F", apps=((1, 2024, "INF_A_F", 9),)),
            rec("Ana Prueba Uno", club=CLUB_B, sex="M", apps=((1, 2025, "INF_A", 9),)),
        ]
    )
    assert _kinds(drafts) == [(IdentityCandidateKind.homonym_suspect, ["sex_conflict"])]


def test_age_path_backwards_is_homonym_signal():
    drafts = ir.build_candidates(
        [
            rec("Ana Prueba Uno", club=CLUB_A, apps=((1, 2024, "INF_B_F", 11),)),
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
    assert ir.build_candidates([rec("Ana Prueba Uno"), other]) == []


def test_blocking_needs_a_shared_surname_token():
    """Sin token de apellido compartido (≥ 3, sin el primero) no se compara."""
    drafts = ir.build_candidates(
        [rec("Carla Ejemplo"), rec("Carla Ejemplos", apps=((2, 2025, "INF_A_F", 9),))]
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
            rec("Ana Prueba Uno", competitor_id=5, apps=((1, 2024, "INF_A_F", 9),)),
            rec("Ana Prueba Uno Dos", competitor_id=6),
        ]
    )
    assert [d.kind for d in merge_question] == [IdentityCandidateKind.same_person_suspect]


def test_name_shared_by_several_competitors_raises_signal_for_staged_record():
    drafts = ir.build_candidates(
        [
            rec("Ana Prueba Uno", club=CLUB_A, competitor_id=5, apps=((1, 2024, "INF_A_F", 9),)),
            rec("Ana Prueba Uno", club=CLUB_B, competitor_id=6, apps=((2, 2024, "INF_A_F", 9),)),
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
    a, b = rec("Ana Prueba Uno"), rec("Ana Prueba Uno Dos", apps=((2, 2025, "INF_A_F", 9),))
    assert ir.pair_hash(a.key, b.key) == ir.pair_hash(b.key, a.key)
    assert ir.build_candidates([a, b]) == ir.build_candidates([b, a])


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

    Confirmado 2026: "Ana Prueba Uno" (club A, ciudad A).
    En staging 2025: la misma persona con segundo apellido y un homónimo de
    otro club y otra ciudad.
    """
    await ingest(db, 2026, 1, {"INF_A_F": [row("Ana Prueba Uno", club=CLUB_A, city=CITY_A)]})
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
    original.athlete_id = 4242
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


@pytest.mark.asyncio
async def test_parent_and_child_staged_end_as_two_competitors(db):
    loader, rows = await _stage_parent_child(db)
    result = await ir.rebuild(db, rows_loader=loader)
    assert result.created == 1
    cand = (await db.execute(select(RaceIdentityCandidate))).scalars().one()
    assert cand.kind == IdentityCandidateKind.homonym_suspect
    assert "same_valida_two_categories" in cand.signals
    page = await ir.list_candidates(db)
    assert "discriminator" not in page.items[0]["left"]

    await ir.decide(db, cand.id, "different_people", actor=actor())
    await db.commit()
    report = await ingest(db, 2025, 5, rows, sha="a" * 64)
    assert report.results_inserted == 2
    comps = (await db.execute(select(RaceCompetitor))).scalars().all()
    assert len(comps) == 2
    results = (await db.execute(select(RaceResult))).scalars().all()
    assert len({r.competitor_id for r in results}) == 2

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
async def test_committed_mixture_is_split_on_different_people(db):
    """Datos confirmados antes de la 044: padre e hijo quedaron en un solo
    competidor. ``different_people`` los parte, resultados incluidos."""
    await ingest(
        db, 2026, 1,
        {"INF_A": [row(PARENT_CHILD, bib="51")], "MAS_A": [row(PARENT_CHILD, bib="52")]},
    )
    assert await _count(db, RaceCompetitor) == 1
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
    await ingest(
        db, 2026, 1,
        {"INF_A": [row(PARENT_CHILD, bib="51")], "MAS_A": [row(PARENT_CHILD, bib="52")]},
    )
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
    """Una sola persona confirmada + la otra en staging: la decisión solo
    etiqueta la firma; revertir antes del commit la deja como estaba."""
    await ingest(db, 2025, 1, {"MAS_A": [row(PARENT_CHILD, bib="61")]})
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
        if "M:9-10@2025" in (c.left_record.get("discriminator", ""), c.right_record.get("discriminator", ""))
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
