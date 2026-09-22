"""T039 — ``IdentityResolver`` (feature 044, US4, contrato §Resolver).

Cubre las cinco ramas de la tabla del contrato, la persistencia de
``athlete_id`` para un competidor vinculado sea cual sea el club de la fila,
``IdentityUnresolved`` cuando no hay desempate, y la idempotencia de la
resolución (propiedad con hypothesis).

Motor aiosqlite real (UNIQUE de la terna, SAVEPOINTs). Nombres sintéticos.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
import pytest_asyncio
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import func, select

from app.models.race_competitor import RaceCompetitor
from app.models.race_competitor_signature import RaceCompetitorSignature
from app.models.race_identity_candidate import (
    IdentityCandidateKind,
    IdentityCandidateState,
    RaceIdentityCandidate,
)
from app.models.race_result import RaceResult
from app.services.race.identity_resolver import (
    IdentityResolver,
    IdentityUnresolved,
    ResolutionBranch,
    category_discriminator,
    collision_discriminators,
    discriminator_compatible,
    signature_triple,
)
from tests.services.race.identity_support import (
    ingest,
    make_engine,
    row,
    session_factory,
)

NAME = "Ana Prueba Uno"
CLUB_A = "Club Sintetico Norte"
CLUB_B = "Club Sintetico Sur"
CITY_A = "Ciudad Uno"
CITY_B = "Ciudad Dos"


@pytest_asyncio.fixture
async def db():
    engine = await make_engine()
    async with session_factory(engine)() as session:
        yield session
    await engine.dispose()


def _record(name: str, club: str, city: str, competitor_id=None) -> dict:
    n, c, t = signature_triple(name, club, city)
    return {
        "key": f"{n}\x1f{c}\x1f{t}",
        "name_printed": name,
        "normalized_name": n,
        "club": club,
        "club_norm": c,
        "city": city,
        "city_norm": t,
        "seasons": [],
        "category_codes": [],
        "category_labels": [],
        "sex": None,
        "competitor_id": competitor_id,
        "athlete_linked": False,
    }


async def _candidate(db, left: dict, right: dict, state: IdentityCandidateState, kind=None):
    cand = RaceIdentityCandidate(
        kind=kind or IdentityCandidateKind.same_person_suspect,
        pair_hash=(left["key"] + right["key"]).encode().hex()[:64].ljust(64, "0"),
        left_record=left,
        right_record=right,
        score=95,
        signals=["extra_or_missing_surname"],
        state=state,
        linked_athlete_involved=False,
    )
    db.add(cand)
    await db.flush()
    return cand


async def _count(db, model) -> int:
    return int((await db.execute(select(func.count()).select_from(model))).scalar_one())


# ---------------------------------------------------------------------------
# Las cinco ramas del contrato
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_rider_creates_competitor_and_signature(db):
    res = await IdentityResolver(db).resolve(name=NAME, club=CLUB_A, city=CITY_A, season=2024)
    assert res.created and res.branch == ResolutionBranch.new_competitor
    sig = (await db.execute(select(RaceCompetitorSignature))).scalars().one()
    assert sig.competitor_id == res.competitor.id
    assert (sig.first_season, sig.last_season) == (2024, 2024)
    assert res.competitor.city_text == CITY_A


@pytest.mark.asyncio
async def test_signature_exact_hit_reuses_and_widens_seasons(db):
    first = await IdentityResolver(db).resolve(name=NAME, club=CLUB_A, city=CITY_A, season=2025)
    later = await IdentityResolver(db).resolve(name=NAME, club=CLUB_A, city=CITY_A, season=2026)
    earlier = await IdentityResolver(db).resolve(name=NAME, club=CLUB_A, city=CITY_A, season=2024)
    assert later.branch == earlier.branch == ResolutionBranch.signature_hit
    assert first.competitor.id == later.competitor.id == earlier.competitor.id
    sig = (await db.execute(select(RaceCompetitorSignature))).scalars().one()
    assert (sig.first_season, sig.last_season) == (2024, 2026)


@pytest.mark.asyncio
async def test_name_hit_single_competitor_without_signal_attaches(db):
    """Cambio de club solo de un atleta del club: no es señal — se adjunta y
    se agrega una firma."""
    first = await IdentityResolver(db).resolve(name=NAME, club=CLUB_A, city=CITY_A, season=2024)
    first.competitor.athlete_id = 4242
    moved = await IdentityResolver(db).resolve(name=NAME, club=CLUB_B, city=CITY_A, season=2025)
    assert moved.branch == ResolutionBranch.name_attach
    assert moved.competitor.id == first.competitor.id
    assert await _count(db, RaceCompetitor) == 1
    assert await _count(db, RaceCompetitorSignature) == 2


@pytest.mark.asyncio
async def test_third_party_same_name_other_club_is_a_new_competitor(db):
    """Decisión 2026-09-22: un tercero (sin ``athlete_id``) nunca recibe una
    terna distinta por coincidir el nombre — se separa por defecto."""
    first = await IdentityResolver(db).resolve(name=NAME, club=CLUB_A, city=CITY_A, season=2024)
    other = await IdentityResolver(db).resolve(name=NAME, club=CLUB_B, city=CITY_A, season=2025)
    assert other.created and other.branch == ResolutionBranch.new_competitor
    assert other.competitor.id != first.competitor.id
    assert await _count(db, RaceCompetitor) == 2
    assert await _count(db, RaceIdentityCandidate) == 0


@pytest.mark.asyncio
async def test_decision_same_person_attaches_with_source_candidate(db):
    base = await IdentityResolver(db).resolve(name=NAME, club=CLUB_A, city=CITY_A, season=2024)
    cand = await _candidate(
        db,
        _record(NAME, CLUB_A, CITY_A, base.competitor.id),
        _record("Ana Prueba Uno Dos", CLUB_A, CITY_A),
        IdentityCandidateState.same_person,
    )
    res = await IdentityResolver(db).resolve(
        name="Ana Prueba Uno Dos", club=CLUB_A, city=CITY_A, season=2025
    )
    assert res.branch == ResolutionBranch.decision_same_person
    assert res.competitor.id == base.competitor.id
    assert res.source_candidate_id == cand.id
    sig = (
        await db.execute(
            select(RaceCompetitorSignature).where(
                RaceCompetitorSignature.normalized_name == "ana prueba uno dos"
            )
        )
    ).scalars().one()
    assert sig.source_candidate_id == cand.id


@pytest.mark.asyncio
async def test_decision_different_people_creates_new_competitor(db):
    base = await IdentityResolver(db).resolve(name=NAME, club=CLUB_A, city=CITY_A, season=2024)
    await _candidate(
        db,
        _record(NAME, CLUB_A, CITY_A, base.competitor.id),
        _record(NAME, CLUB_B, CITY_B),
        IdentityCandidateState.different_people,
        kind=IdentityCandidateKind.homonym_suspect,
    )
    res = await IdentityResolver(db).resolve(name=NAME, club=CLUB_B, city=CITY_B, season=2025)
    assert res.branch == ResolutionBranch.decision_different_people
    assert res.created and res.competitor.id != base.competitor.id
    assert await _count(db, RaceCompetitor) == 2


@pytest.mark.asyncio
async def test_several_competitors_without_tie_break_raise(db):
    base = await IdentityResolver(db).resolve(name=NAME, club=CLUB_A, city=CITY_A, season=2024)
    await _candidate(
        db,
        _record(NAME, CLUB_A, CITY_A, base.competitor.id),
        _record(NAME, CLUB_B, CITY_B),
        IdentityCandidateState.different_people,
        kind=IdentityCandidateKind.homonym_suspect,
    )
    second = await IdentityResolver(db).resolve(name=NAME, club=CLUB_B, city=CITY_B, season=2025)
    base.competitor.athlete_id, second.competitor.athlete_id = 4242, 4343
    # Tercera forma impresa, sin decisión: dos atletas del club con ese nombre.
    with pytest.raises(IdentityUnresolved) as exc:
        await IdentityResolver(db).resolve(name=NAME, club="Club Tercero", city="Ciudad Tres", season=2026)
    assert exc.value.reason == "varios_competidores"
    assert "ana" not in str(exc.value).lower()


@pytest.mark.asyncio
async def test_pending_candidate_raises_in_strict_and_is_provisional_in_dry_run(db):
    base = await IdentityResolver(db).resolve(name=NAME, club=CLUB_A, city=CITY_A, season=2024)
    await _candidate(
        db,
        _record(NAME, CLUB_A, CITY_A, base.competitor.id),
        _record("Ana Prueba Uno Dos", CLUB_A, CITY_A),
        IdentityCandidateState.pending,
    )
    with pytest.raises(IdentityUnresolved):
        await IdentityResolver(db).resolve(
            name="Ana Prueba Uno Dos", club=CLUB_A, city=CITY_A, season=2025
        )
    res = await IdentityResolver(db, strict=False).resolve(
        name="Ana Prueba Uno Dos", club=CLUB_A, city=CITY_A, season=2025
    )
    assert res.branch == ResolutionBranch.provisional
    # Sin firma: el rollback del dry-run lo descarta y no queda "recordado".
    assert await _count(db, RaceCompetitorSignature) == 1


@pytest.mark.asyncio
async def test_signature_hit_wins_over_pending_candidate(db):
    base = await IdentityResolver(db).resolve(name=NAME, club=CLUB_A, city=CITY_A, season=2024)
    await _candidate(
        db,
        _record(NAME, CLUB_A, CITY_A, base.competitor.id),
        _record("Ana Prueba Uno Dos", CLUB_A, CITY_A),
        IdentityCandidateState.pending,
    )
    res = await IdentityResolver(db).resolve(name=NAME, club=CLUB_A, city=CITY_A, season=2025)
    assert res.branch == ResolutionBranch.signature_hit


@pytest.mark.asyncio
async def test_signature_unique_key_resolves_a_lost_race_on_real_sql(db, monkeypatch):
    """Mismo escenario que ``test_ingestor_concurrency`` pero sobre SQL real:
    el SAVEPOINT deshace competidor + firma y se reusa el ganador."""
    winner = await IdentityResolver(db).resolve(name=NAME, club=CLUB_A, city=CITY_A, season=2024)
    await db.commit()

    async def stale_read(self, triple):
        return []

    async def no_name_hit(self, normalized):
        return []

    monkeypatch.setattr(IdentityResolver, "_signatures_for", stale_read)
    monkeypatch.setattr(IdentityResolver, "_competitors_by_name", no_name_hit)
    res = await IdentityResolver(db).resolve(name=NAME, club=CLUB_A, city=CITY_A, season=2025)
    await db.commit()
    assert res.competitor.id == winner.competitor.id and not res.created
    assert await _count(db, RaceCompetitor) == 1
    assert await _count(db, RaceCompetitorSignature) == 1


# ---------------------------------------------------------------------------
# athlete_id se persiste para un competidor vinculado, sea cual sea el club
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_linked_competitor_carries_athlete_id_whatever_row_club(db):
    await ingest(db, 2026, 1, {"INF_A": [row(NAME, club="Trocha y Ruta")]})
    comp = (await db.execute(select(RaceCompetitor))).scalars().one()
    comp.athlete_id = 4242
    await db.commit()

    # Historia previa al club: misma persona impresa con otro club.
    report = await ingest(db, 2024, 2, {"INF_A": [row(NAME, club=CLUB_B)]})
    assert report.results_inserted == 1
    results = (await db.execute(select(RaceResult).order_by(RaceResult.id))).scalars().all()
    assert [r.athlete_id for r in results] == [None, 4242]
    assert {r.competitor_id for r in results} == {comp.id}


@pytest.mark.asyncio
async def test_unlinked_competitor_with_club_row_still_needs_coach_decision(db):
    """``is_trocha_y_ruta`` solo decide si el wizard pregunta: sin decisión
    del coach no se vincula nada."""
    await ingest(db, 2026, 1, {"INF_A": [row(NAME, club="Trocha y Ruta")]})
    result = (await db.execute(select(RaceResult))).scalars().one()
    assert result.athlete_id is None


@pytest.mark.asyncio
async def test_ingestor_stores_city_text(db):
    await ingest(db, 2025, 1, {"INF_A": [row(NAME, city=CITY_B)]})
    comp = (await db.execute(select(RaceCompetitor))).scalars().one()
    assert comp.city_text == CITY_B


# ---------------------------------------------------------------------------
# Idempotencia (hypothesis)
# ---------------------------------------------------------------------------

_POOL_NAMES = ["Ana Prueba Uno", "Ana Prueba Uno Dos", "Bruno Ficticio Tres", "Carla Ejemplo"]
_POOL_CLUBS = [CLUB_A, CLUB_B, ""]
_POOL_CITIES = [CITY_A, CITY_B, ""]

_rows = st.lists(
    st.tuples(
        st.sampled_from(_POOL_NAMES),
        st.sampled_from(_POOL_CLUBS),
        st.sampled_from(_POOL_CITIES),
        st.integers(min_value=2024, max_value=2026),
    ),
    min_size=1,
    max_size=12,
)


async def _run_twice(rows):
    engine = await make_engine()
    try:
        async with session_factory(engine)() as db:
            first = []
            for name, club, city, season in rows:
                res = await IdentityResolver(db).resolve(
                    name=name, club=club, city=city, season=season
                )
                first.append(res.competitor.id)
            n_comp = await _count(db, RaceCompetitor)
            n_sig = await _count(db, RaceCompetitorSignature)
            second = []
            for name, club, city, season in rows:
                res = await IdentityResolver(db).resolve(
                    name=name, club=club, city=city, season=season
                )
                assert res.branch == ResolutionBranch.signature_hit
                second.append(res.competitor.id)
            return first, second, n_comp, n_sig, await _count(db, RaceCompetitor), await _count(
                db, RaceCompetitorSignature
            )
    finally:
        await engine.dispose()


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(rows=_rows)
def test_resolution_is_idempotent(rows):
    first, second, n_comp, n_sig, n_comp2, n_sig2 = asyncio.run(_run_twice(rows))
    assert first == second
    assert (n_comp, n_sig) == (n_comp2, n_sig2)
    # Sin atletas del club, cada terna es un competidor (nunca se une por nombre).
    assert n_comp == len({signature_triple(n, c, t) for n, c, t, _ in rows})


# ---------------------------------------------------------------------------
# Separación por categoría (decisión del dueño 2026-09-21)
# ---------------------------------------------------------------------------

PARENT_CHILD = "Mateo Ficticio Igual"


def _cat(sex: str, age_min, age_max):
    return SimpleNamespace(sex=SimpleNamespace(value=sex), age_min=age_min, age_max=age_max)


MAS_A = _cat("M", 30, 39)
INF_A = _cat("M", 9, 10)
INF_B = _cat("M", 11, 12)
ELITE = _cat("M", 17, None)
INF_A_F = _cat("F", 9, 10)


def test_category_discriminator_rule():
    assert category_discriminator(MAS_A, 2025) == "M:30-39@2025"
    assert category_discriminator(ELITE, 2024) == "M:17-@2024"
    assert category_discriminator(_cat("MIXED", None, 5), 2026) == "X:-5@2026"


@pytest.mark.parametrize(
    "disc,cat,season,expected",
    [
        ("M:9-10@2025", INF_B, 2026, True),  # el niño crece un año
        ("M:9-10@2025", INF_A, 2025, True),
        ("M:9-10@2025", MAS_A, 2025, False),
        ("M:30-39@2025", INF_B, 2026, False),
        ("M:30-39@2025", ELITE, 2026, True),  # un adulto puede correr élite
        ("M:9-10@2025", INF_A_F, 2025, False),  # sexo
        ("X:-5@2025", INF_A_F, 2029, True),  # mixta no choca por sexo
        ("basura", INF_A, 2025, False),
    ],
)
def test_discriminator_compatibility(disc, cat, season, expected):
    assert (
        discriminator_compatible(disc, cat.sex.value, cat.age_min, cat.age_max, season)
        is expected
    )


async def _separated_pair(db, *, linked: bool = False):
    """Padre (Master A) e hijo (Infantil A), misma terna, ya separados. Con
    ``linked`` el hijo es atleta del club (la terna la gestiona el coach)."""
    parent = RaceCompetitor(normalized_name="mateo ficticio igual", display_name=PARENT_CHILD)
    child = RaceCompetitor(
        normalized_name="mateo ficticio igual",
        display_name=PARENT_CHILD,
        athlete_id=4242 if linked else None,
    )
    db.add_all([parent, child])
    await db.flush()
    n, c, t = signature_triple(PARENT_CHILD, CLUB_A, CITY_A)
    for comp, disc in ((parent, "M:30-39@2025"), (child, "M:9-10@2025")):
        db.add(
            RaceCompetitorSignature(
                competitor_id=comp.id, normalized_name=n, club_norm=c, city_norm=t,
                discriminator=disc, first_season=2025, last_season=2025,
            )
        )
    await db.flush()
    return parent, child


@pytest.mark.asyncio
async def test_resolver_picks_the_right_person_by_category(db):
    parent, child = await _separated_pair(db)
    resolver = IdentityResolver(db)
    kid = await resolver.resolve(
        name=PARENT_CHILD, club=CLUB_A, city=CITY_A, season=2026, category=INF_B
    )
    adult = await resolver.resolve(
        name=PARENT_CHILD, club=CLUB_A, city=CITY_A, season=2026, category=MAS_A
    )
    assert kid.competitor.id == child.id and adult.competitor.id == parent.id
    assert kid.branch == adult.branch == ResolutionBranch.signature_hit


@pytest.mark.asyncio
async def test_separated_triple_without_compatible_category_raises(db):
    await _separated_pair(db, linked=True)
    with pytest.raises(IdentityUnresolved) as exc:
        await IdentityResolver(db).resolve(
            name=PARENT_CHILD, club=CLUB_A, city=CITY_A, season=2025, category=INF_A_F
        )
    assert exc.value.reason == "discriminador_incompatible"
    with pytest.raises(IdentityUnresolved):
        await IdentityResolver(db).resolve(
            name=PARENT_CHILD, club=CLUB_A, city=CITY_A, season=2025, category=None
        )


@pytest.mark.asyncio
async def test_single_signature_triple_keeps_todays_behaviour(db):
    first = await IdentityResolver(db).resolve(
        name=NAME, club=CLUB_A, city=CITY_A, season=2025, category=INF_A
    )
    again = await IdentityResolver(db).resolve(
        name=NAME, club=CLUB_A, city=CITY_A, season=2025, category=MAS_A
    )
    assert again.competitor.id == first.competitor.id
    sig = (await db.execute(select(RaceCompetitorSignature))).scalars().one()
    assert sig.discriminator == ""


@pytest.mark.asyncio
async def test_intra_triple_decision_creates_each_side_on_first_sighting(db):
    left = {**_record(PARENT_CHILD, CLUB_A, CITY_A), "discriminator": "M:9-10@2025"}
    right = {**_record(PARENT_CHILD, CLUB_A, CITY_A), "discriminator": "M:30-39@2025"}
    left["key"] += "\x1fM:9-10@2025"
    right["key"] += "\x1fM:30-39@2025"
    await _candidate(
        db, left, right, IdentityCandidateState.different_people,
        kind=IdentityCandidateKind.homonym_suspect,
    )
    resolver = IdentityResolver(db)
    kid = await resolver.resolve(
        name=PARENT_CHILD, club=CLUB_A, city=CITY_A, season=2025, category=INF_A
    )
    adult = await resolver.resolve(
        name=PARENT_CHILD, club=CLUB_A, city=CITY_A, season=2025, category=MAS_A
    )
    assert kid.created and adult.created and kid.competitor.id != adult.competitor.id
    discs = sorted(
        s.discriminator for s in (await db.execute(select(RaceCompetitorSignature))).scalars()
    )
    assert discs == ["M:30-39@2025", "M:9-10@2025"]


# ---------------------------------------------------------------------------
# Terceros sin coach (decisión del dueño 2026-09-22)
# ---------------------------------------------------------------------------


def _coll_cat(code, sex, age_min, age_max):
    return SimpleNamespace(
        code=code, sex=SimpleNamespace(value=sex), age_min=age_min, age_max=age_max
    )


def test_collision_discriminators_rule():
    inf = _coll_cat("INF_A", "M", 9, 10)
    mas = _coll_cat("MAS_A", "M", 30, 39)
    rows = [
        ("a", PARENT_CHILD, CLUB_A, CITY_A, inf, "11"),
        ("b", PARENT_CHILD, CLUB_A, CITY_A, mas, "12"),
        ("c", "Otra Persona Sola", CLUB_A, CITY_A, inf, "13"),
        ("d", "Doble Mismo Nombre", CLUB_A, CITY_A, inf, "21"),
        ("e", "Doble Mismo Nombre", CLUB_A, CITY_A, inf, "22"),
        ("f", "Triple Sin Dorsal", CLUB_A, CITY_A, inf, ""),
        ("g", "Triple Sin Dorsal", CLUB_A, CITY_A, inf, ""),
    ]
    out = collision_discriminators(rows, 2025)
    assert out == {
        "a": "M:9-10@2025",
        "b": "M:30-39@2025",
        "d": "bib:21@2025",
        "e": "bib:22@2025",
        "f": "row:INF_A-0@2025",
        "g": "row:INF_A-1@2025",
    }
    assert not discriminator_compatible("bib:21@2025", "M", 9, 10, 2025)


@pytest.mark.asyncio
async def test_third_party_collision_same_category_keeps_both_rows(db):
    """Misma terna, misma válida, misma categoría: dos competidores por
    dorsal, ningún candidato y ninguna fila perdida."""
    report = await ingest(
        db, 2025, 1,
        {"INF_A": [row(PARENT_CHILD, bib="21"), row(PARENT_CHILD, bib="22", position=2)]},
    )
    assert report.results_inserted == 2
    comps = (await db.execute(select(RaceCompetitor))).scalars().all()
    assert len(comps) == 2
    discs = sorted(
        s.discriminator for s in (await db.execute(select(RaceCompetitorSignature))).scalars()
    )
    assert discs == ["bib:21@2025", "bib:22@2025"]
    assert await _count(db, RaceIdentityCandidate) == 0

    # Idempotente: reingestar las mismas firmas no crea nada nuevo.
    resolver = IdentityResolver(db)
    again = await resolver.resolve(
        name=PARENT_CHILD, club=CLUB_A, city=CITY_A, season=2025,
        category=INF_A, bib="21", collision_discriminator="bib:21@2025",
    )
    assert not again.created and again.branch == ResolutionBranch.third_party_split
    # Una fila suelta posterior tampoco se queda sin resolver.
    later = await resolver.resolve(
        name=PARENT_CHILD, club=CLUB_A, city=CITY_A, season=2025, category=INF_A, bib="22"
    )
    owner_22 = (
        await db.execute(
            select(RaceCompetitorSignature.competitor_id).where(
                RaceCompetitorSignature.discriminator == "bib:22@2025"
            )
        )
    ).scalar_one()
    assert later.competitor.id == owner_22 and not later.created
    assert await _count(db, RaceCompetitor) == 2


@pytest.mark.asyncio
async def test_third_party_collision_two_categories_splits_by_category(db):
    report = await ingest(
        db, 2025, 1,
        {"INF_A": [row(PARENT_CHILD, bib="11")], "MAS_A": [row(PARENT_CHILD, bib="12")]},
    )
    assert report.results_inserted == 2
    discs = sorted(
        s.discriminator for s in (await db.execute(select(RaceCompetitorSignature))).scalars()
    )
    assert discs == ["M:30-39@2025", "M:9-10@2025"]
    assert await _count(db, RaceCompetitor) == 2


@pytest.mark.asyncio
async def test_separated_third_party_triple_without_compatible_category_falls_back(db):
    """Terceros: sin discriminador compatible no hay 500 — firma ``bib:``."""
    parent, child = await _separated_pair(db)
    res = await IdentityResolver(db).resolve(
        name=PARENT_CHILD, club=CLUB_A, city=CITY_A, season=2025, category=INF_A_F, bib="7"
    )
    assert res.created and res.branch == ResolutionBranch.third_party_split
    assert res.competitor.id not in (parent.id, child.id)


@pytest.mark.asyncio
async def test_collision_on_a_club_triple_is_left_to_the_coach(db):
    """Si la terna es de un atleta del club, el discriminador de colisión se
    ignora: decide la cola (y el candado)."""
    base = await IdentityResolver(db).resolve(
        name=PARENT_CHILD, club=CLUB_A, city=CITY_A, season=2024, category=INF_A
    )
    base.competitor.athlete_id = 4242
    res = await IdentityResolver(db).resolve(
        name=PARENT_CHILD, club=CLUB_A, city=CITY_A, season=2025,
        category=MAS_A, collision_discriminator="M:30-39@2025",
    )
    assert res.branch == ResolutionBranch.signature_hit
    assert res.competitor.id == base.competitor.id
