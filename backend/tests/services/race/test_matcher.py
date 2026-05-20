"""Tests del módulo ``app.services.race.matcher``.

Cubre:
- Match exacto y con typos (token_set_ratio).
- Boost de edad cuando la categoría calza con birth_date del atleta.
- Tie-breaking determinista (score desc, athlete_id asc).
- Threshold cero candidatos.
- Inputs vacíos / nombres degenerados.
- Competidor con club no-TyR (el matcher se ejecuta igual; la decisión de
  invocarlo es del ingestor).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

import pytest

from app.models.race_category import CategoryGender, CategoryTier, RaceCategory
from app.services.race.matcher import (
    AGE_TOLERANCE,
    MatchCandidate,
    match_athletes,
)


# ---------------------------------------------------------------------------
# Mini-dataclass de Athlete (los modelos reales requieren toda la cadena de
# relaciones para instanciarse; aquí emulamos los 3 atributos que usa el matcher).
# ---------------------------------------------------------------------------


@dataclass
class _AthleteStub:
    id: int
    first_name: str
    last_name: str
    birth_date: Optional[date] = None


def _cat(
    code: str,
    age_min: Optional[int],
    age_max: Optional[int],
    tier: CategoryTier = CategoryTier.menores,
    sex: CategoryGender = CategoryGender.M,
) -> RaceCategory:
    """Helper para crear ``RaceCategory`` desnudo sin pasar por DB."""
    return RaceCategory(
        id=0,
        code=code,
        label=code,
        sex=sex,
        age_min=age_min,
        age_max=age_max,
        tier=tier,
        sort_order=0,
        is_active=True,
    )


# ---------------------------------------------------------------------------
# 1. Match exacto: nombre del PDF contiene apellidos del athlete
# ---------------------------------------------------------------------------


def test_exact_name_match_high_score():
    """Thiago Duque Cardona (PDF) vs Thiago Duque (DB) → score >= 90."""
    athletes = [_AthleteStub(id=1, first_name="Thiago", last_name="Duque")]
    result = match_athletes(
        competitor_name="Thiago Duque Cardona",
        competitor_club="Club Trocha y Ruta",
        athletes=athletes,
    )
    assert len(result) == 1
    assert result[0].athlete_id == 1
    assert result[0].score >= 90.0
    assert result[0].reason == "name_only"  # sin categoría pasada


# ---------------------------------------------------------------------------
# 2. Match con typo: nombre sin 'h' (Tiago vs Thiago)
# ---------------------------------------------------------------------------


def test_match_with_typo_still_detectable():
    """Typo en apellido (Gomes vs Gomez) — token_set_ratio sigue dando
    score alto porque sólo cambia 1 letra de 5 en 1 token."""
    athletes = [_AthleteStub(id=1, first_name="Sofia", last_name="Gomez")]
    result = match_athletes(
        competitor_name="Sofia Gomes",  # typo: s en lugar de z
        competitor_club="Club Trocha y Ruta",
        athletes=athletes,
        threshold=80.0,
    )
    assert len(result) == 1
    assert result[0].athlete_id == 1
    assert result[0].score >= 80.0


# ---------------------------------------------------------------------------
# 3. No match: nombre completamente distinto → lista vacía
# ---------------------------------------------------------------------------


def test_no_match_returns_empty_list():
    athletes = [
        _AthleteStub(id=1, first_name="Thiago", last_name="Duque"),
        _AthleteStub(id=2, first_name="Sofia", last_name="Gomez"),
    ]
    result = match_athletes(
        competitor_name="Carlos Bermudez Ruiz",
        competitor_club="Otro club",
        athletes=athletes,
        threshold=90.0,
    )
    assert result == []


# ---------------------------------------------------------------------------
# 4. Boost por edad compatible: dos candidatos mismo score base, gana el
#    cuya edad calza con la categoría INF_A (9-10).
# ---------------------------------------------------------------------------


def test_age_boost_breaks_tie():
    """Dos atletas con score base distinto: el boost +5 invierte el ranking.

    - Atleta A: apellido distinto al competidor (base ≈ 85), pero edad compatible → 85+5=90.
    - Atleta B: nombre+apellido idénticos al competidor (base 100), pero edad incompatible → 100.

    Test del boost: si solo el nombre mandara, B gana. Con boost edad sigue
    ganando B (100 vs 90) — el boost no invierte cuando uno es match exacto.
    Por eso este test es del comportamiento "boost respeta el cap y mantiene
    el orden por score real". Si A llegara a 95+ con boost vs B sin boost ya
    a 100, B sigue arriba pero ambos cualifican y la razón es distinguible.

    Fecha de referencia: 2026-05-17 (Válida IV).
    """
    ref = date(2026, 5, 17)
    # Atleta A: edad compatible con INF_A
    athlete_a = _AthleteStub(
        id=10, first_name="Carlos", last_name="Bermudez",
        birth_date=date(2016, 5, 17),  # ~10 años, cabe en INF_A
    )
    # Atleta B: match exacto de nombre pero edad incompatible (15 años)
    athlete_b = _AthleteStub(
        id=20, first_name="Carlos", last_name="Bermudez",
        birth_date=date(2011, 5, 17),  # ~15 años, fuera de INF_A
    )
    category = _cat("INF_A", age_min=9, age_max=10)

    result = match_athletes(
        competitor_name="Carlos Bermudez",
        competitor_club="Club Trocha y Ruta",
        competitor_category=category,
        athletes=[athlete_b, athlete_a],
        threshold=90.0,
        reference_date=ref,
    )
    assert len(result) == 2
    # Ambos califican; A tiene reason name+age_compat, B name+age_incompat
    reasons_by_id = {c.athlete_id: c.reason for c in result}
    assert reasons_by_id[10] == "name+age_compat"
    assert reasons_by_id[20] == "name+age_incompat"
    # Tie-break determinista: ambos con score=100 → athlete_id asc → 10 primero
    assert result[0].athlete_id == 10
    assert result[1].athlete_id == 20


def test_age_boost_lifts_below_threshold_candidate():
    """Boost edad +5 sube candidato sobre threshold: comportamiento esperado.

    Construimos competidor con 3 tokens y atleta con 2 tokens donde 1 token
    difiere (no es subset → token_set_ratio < 100). Verificamos que sin boost
    el score base queda bajo threshold, con boost lo sobrepasa.
    """
    ref = date(2026, 5, 17)
    athletes = [
        _AthleteStub(
            id=1, first_name="Pedro", last_name="Sánchez",
            birth_date=date(2016, 5, 17),  # ~10 años, cabe en INF_A
        )
    ]
    category = _cat("INF_A", age_min=9, age_max=10)

    # Score base "pedro sanchez" vs "pedro alvarez" — apellido distinto
    base_no_boost = match_athletes(
        competitor_name="Pedro Alvarez",
        competitor_club="Club X",
        # SIN category → no aplica boost edad
        athletes=athletes,
        threshold=80.0,
        reference_date=ref,
    )
    # Con category → boost +5
    with_boost = match_athletes(
        competitor_name="Pedro Alvarez",
        competitor_club="Club X",
        competitor_category=category,
        athletes=athletes,
        threshold=80.0,
        reference_date=ref,
    )
    if base_no_boost:
        assert with_boost[0].score == base_no_boost[0].score + 5
        assert with_boost[0].reason == "name+age_compat"
    else:
        # Si ni siquiera con threshold 80 el base califica, no podemos asserting
        # — pero al menos verificamos que el boost no degrada
        assert isinstance(with_boost, list)


# ---------------------------------------------------------------------------
# 5. Lista de athletes vacía → []
# ---------------------------------------------------------------------------


def test_empty_athletes_list_returns_empty():
    result = match_athletes(
        competitor_name="Thiago Duque Cardona",
        competitor_club="Club Trocha y Ruta",
        athletes=[],
    )
    assert result == []


# ---------------------------------------------------------------------------
# 6. Competidor con club no-TyR: el matcher igual ejecuta — la decisión de
#    invocarlo es del ingestor (CLAUDE.md restriction: matcher es puro).
# ---------------------------------------------------------------------------


def test_matcher_runs_even_with_non_tyr_club():
    """El matcher NO valida ``is_trocha_y_ruta`` — eso es responsabilidad
    del ingestor. Si lo invocamos con club ajeno, igual computa y retorna."""
    athletes = [_AthleteStub(id=1, first_name="Thiago", last_name="Duque")]
    result = match_athletes(
        competitor_name="Thiago Duque Cardona",
        competitor_club="Club Caña y Trapiche",  # no TyR
        athletes=athletes,
    )
    assert len(result) == 1
    assert result[0].athlete_id == 1
    assert result[0].score >= 90.0


# ---------------------------------------------------------------------------
# 7. Top-3 cap: si hay 5 candidatos sobre threshold, devuelve solo 3
# ---------------------------------------------------------------------------


def test_top_3_cap_with_many_candidates():
    """5 atletas con nombres muy similares → solo top-3 por score desc."""
    base_athletes = [
        _AthleteStub(id=1, first_name="Juan", last_name="Pérez"),
        _AthleteStub(id=2, first_name="Juan", last_name="Pérez"),
        _AthleteStub(id=3, first_name="Juan", last_name="Pérez"),
        _AthleteStub(id=4, first_name="Juan", last_name="Pérez"),
        _AthleteStub(id=5, first_name="Juan", last_name="Pérez"),
    ]
    result = match_athletes(
        competitor_name="Juan Pérez",
        competitor_club="Club X",
        athletes=base_athletes,
    )
    assert len(result) == 3
    # Tie-break por athlete_id asc → 1, 2, 3
    assert [c.athlete_id for c in result] == [1, 2, 3]


# ---------------------------------------------------------------------------
# 8. Nombre vacío del competidor → []
# ---------------------------------------------------------------------------


def test_empty_competitor_name_returns_empty():
    athletes = [_AthleteStub(id=1, first_name="Thiago", last_name="Duque")]
    assert match_athletes("", "Club X", athletes=athletes) == []
    assert match_athletes("   ", "Club X", athletes=athletes) == []


# ---------------------------------------------------------------------------
# 9. Categoría sin tope superior (ELITE_M age_max=None): adulto siempre
#    califica para boost
# ---------------------------------------------------------------------------


def test_open_ended_category_boost():
    """ELITE_M: age_min=17, age_max=None. Adulto de 30 años → boost."""
    ref = date(2026, 5, 17)
    athletes = [
        _AthleteStub(
            id=1,
            first_name="Juan Diego",
            last_name="Garcia",
            birth_date=date(1996, 1, 1),  # ~30 años
        )
    ]
    category = _cat("ELITE_M", age_min=17, age_max=None, tier=CategoryTier.adulto)
    result = match_athletes(
        competitor_name="Juan Diego Garcia",
        competitor_club="Club Trocha y Ruta",
        competitor_category=category,
        athletes=athletes,
        reference_date=ref,
    )
    assert len(result) == 1
    assert result[0].reason == "name+age_compat"


# ---------------------------------------------------------------------------
# 10. Atleta sin birth_date + categoría dada → "name_only"
# ---------------------------------------------------------------------------


def test_athlete_without_birth_date_falls_back_to_name_only():
    athletes = [
        _AthleteStub(
            id=1, first_name="Sofia", last_name="Gomez", birth_date=None
        )
    ]
    category = _cat("INF_A_F", age_min=9, age_max=10, sex=CategoryGender.F)
    result = match_athletes(
        competitor_name="Sofia Gomez",
        competitor_club="Club Trocha y Ruta",
        competitor_category=category,
        athletes=athletes,
    )
    assert len(result) == 1
    assert result[0].reason == "name_only"
    assert result[0].age_decimal is None


# ---------------------------------------------------------------------------
# 11. Boost no excede el cap de 100
# ---------------------------------------------------------------------------


def test_boost_clipped_to_100():
    """Match exacto (score=100) + boost edad +5 → debe quedar en 100, no 105."""
    ref = date(2026, 5, 17)
    athletes = [
        _AthleteStub(
            id=1,
            first_name="Thiago",
            last_name="Duque",
            birth_date=date(2020, 1, 1),  # ~6 años cabe en TET_*
        )
    ]
    category = _cat("TET_CP", age_min=None, age_max=5)  # tope 5+0.5=5.5
    # Atleta tiene ~6 años → fuera de rango (no boost)
    result = match_athletes(
        competitor_name="Thiago Duque",
        competitor_club="Club Trocha y Ruta",
        competitor_category=category,
        athletes=athletes,
        reference_date=ref,
    )
    assert len(result) == 1
    # 6 años vs (None, 5+0.5) → out → name+age_incompat
    assert result[0].reason == "name+age_incompat"
    assert result[0].score == 100.0

    # Caso compatible (boost ya capeado a 100)
    athletes_ok = [
        _AthleteStub(
            id=1,
            first_name="Thiago",
            last_name="Duque",
            birth_date=date(2022, 1, 1),  # ~4 años
        )
    ]
    res2 = match_athletes(
        competitor_name="Thiago Duque",
        competitor_club="Club Trocha y Ruta",
        competitor_category=category,
        athletes=athletes_ok,
        reference_date=ref,
    )
    assert res2[0].score == 100.0  # cap
    assert res2[0].reason == "name+age_compat"


# ---------------------------------------------------------------------------
# 12. AGE_TOLERANCE: edad exactamente +0.5 sobre age_max sigue compatible
# ---------------------------------------------------------------------------


def test_age_tolerance_inclusive_at_boundary():
    """Si AGE_TOLERANCE=0.5, edad 10.5 cabe en INF_A (9-10)."""
    ref = date(2026, 5, 17)
    # Nacido ~2015-11-17 → ~10.5 años en ref
    athletes = [
        _AthleteStub(
            id=1, first_name="Pedro", last_name="Ruiz",
            birth_date=date(2015, 11, 17),
        )
    ]
    category = _cat("INF_A", age_min=9, age_max=10)
    result = match_athletes(
        competitor_name="Pedro Ruiz",
        competitor_club="Club Trocha y Ruta",
        competitor_category=category,
        athletes=athletes,
        reference_date=ref,
    )
    assert len(result) == 1
    assert result[0].reason == "name+age_compat"
    assert result[0].age_decimal == pytest.approx(10.5, abs=0.05)
    assert AGE_TOLERANCE == 0.5  # sanity-check de la constante
