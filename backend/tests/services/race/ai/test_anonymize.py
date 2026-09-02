"""Tests del nodo anonymize + módulo anonymizer.

Validación clave (sentinela privacidad): el state después del nodo NO
debe contener nombres reales TyR — solo pseudónimos.
"""
from __future__ import annotations

import pytest

from app.services.race.ai.anonymizer import ANIMALS, COLORS, make_pseudonym
from app.services.race.ai.nodes.anonymize import anonymize


def test_pseudonym_is_stable():
    p1 = make_pseudonym(42)
    p2 = make_pseudonym(42)
    assert p1 == p2


def test_pseudonym_changes_with_salt():
    p1 = make_pseudonym(42, salt="s1")
    p2 = make_pseudonym(42, salt="s2")
    assert p1 != p2


def test_pseudonym_format_is_color_plus_animal():
    p = make_pseudonym(7)
    # Algún color + algún animal
    matches_color = any(p.startswith(c) for c in COLORS)
    assert matches_color, f"pseudonym {p} no empieza con color conocido"
    matches_animal = any(p.endswith(a) for a in ANIMALS)
    assert matches_animal, f"pseudonym {p} no termina con animal conocido"


def test_pseudonym_lists_have_30_each():
    assert len(COLORS) == 30
    assert len(ANIMALS) == 30


@pytest.mark.asyncio
async def test_anonymize_node_filters_real_athlete_id(configure_db_factory, fake_session):
    configure_db_factory(fake_session)
    state = {
        "athlete_id": 101,
        "competitor_id": 555,
        "run_id": "abc123",
        "raw_data": [
            {"athlete_id": 101, "competitor_id": 555, "position": 1},
            {"athlete_id": None, "competitor_id": 888, "position": 2},  # rival anónimo
        ],
    }
    update = await anonymize(state)
    anon = update["anonymized_data"]
    mapping = update["mapping"]

    pseudo = anon["pseudonym"]
    assert pseudo == make_pseudonym(101)
    # Mapping pseudonym -> athlete_id real (NUNCA se exporta al LLM).
    assert mapping == {pseudo: 101}

    # athlete_id real eliminado de raw_data anonimizado.
    for row in anon["rows"]:
        assert "athlete_id" not in row

    # Pseudónimo solo aparece en filas del atleta target.
    target_rows = [r for r in anon["rows"] if r.get("pseudonym")]
    assert len(target_rows) == 1
    assert target_rows[0]["pseudonym"] == pseudo


@pytest.mark.asyncio
async def test_anonymize_node_persists_mapping(configure_db_factory, fake_session):
    configure_db_factory(fake_session)
    state = {
        "athlete_id": 7,
        "competitor_id": 22,
        "run_id": "RUN_X",
        "raw_data": [{"athlete_id": 7, "competitor_id": 22}],
    }
    await anonymize(state)
    # Verifica que el INSERT al anon mapping table fue ejecutado.
    inserts = [
        stmt for stmt, _ in fake_session.executed_statements
        if "anonymization_mappings" in stmt
    ]
    assert len(inserts) == 1


@pytest.mark.asyncio
async def test_anonymize_sentinel_no_real_tyr_names_in_events(
    configure_db_factory, fake_session
):
    """Sentinela privacidad: nombres reales TyR JAMÁS en state['events'].

    Lista cerrada de nombres conocidos del club (CLAUDE.md menciona
    privacidad de menores). Cualquier ocurrencia → fallo de privacidad.
    """
    BANNED = ["Mariana", "Thiago", "Sofia", "Miguel", "Isabel", "Jostin"]
    configure_db_factory(fake_session)

    for athlete_id in range(1, 11):  # 10 IDs distintos
        state = {
            "athlete_id": athlete_id,
            "competitor_id": 100 + athlete_id,
            "run_id": f"R{athlete_id}",
            "raw_data": [{"athlete_id": athlete_id, "competitor_id": 100 + athlete_id}],
        }
        await anonymize(state)
        # Serializa state["events"] como JSON-ish y verifica.
        import json

        dump = json.dumps(state.get("events", []), default=str, ensure_ascii=False)
        for banned in BANNED:
            assert banned not in dump, (
                f"PRIVACY LEAK: nombre real '{banned}' encontrado en events "
                f"para athlete_id={athlete_id}"
            )


@pytest.mark.asyncio
async def test_anonymize_scrubs_training_window_coach_feedback(
    configure_db_factory, fake_session
):
    """Feature 037 (T103): training_window.coach_feedback se scrubea con
    club_forbidden_names (superset de todo el club, no solo el atleta+padres)."""
    configure_db_factory(fake_session)
    state = {
        "athlete_id": 7,
        "competitor_id": 22,
        "run_id": "abc",
        "raw_data": [{"athlete_id": 7, "competitor_id": 22}],
        "club_forbidden_names": ["Juan Pérez Ficticio", "Ana Gómez Ficticio"],
        "training_window": {
            "window_days": 28,
            "coach_feedback": [
                "Juan Pérez Ficticio mejoró el frenado en curva.",
                "Buen ritmo sostenido toda la sesión.",
            ],
        },
    }
    update = await anonymize(state)

    scrubbed = update["training_window"]["coach_feedback"]
    assert "Juan Pérez Ficticio" not in scrubbed[0]
    assert scrubbed[1] == "Buen ritmo sostenido toda la sesión."
    # window_days y demás claves de training_window se preservan intactas.
    assert update["training_window"]["window_days"] == 28


@pytest.mark.asyncio
async def test_anonymize_falls_back_to_forbidden_names_without_club_superset(
    configure_db_factory, fake_session
):
    """Sin club_forbidden_names en state, usa forbidden_names (atleta+padres)."""
    configure_db_factory(fake_session)
    state = {
        "athlete_id": 7,
        "competitor_id": 22,
        "run_id": "abc",
        "raw_data": [{"athlete_id": 7, "competitor_id": 22}],
        "forbidden_names": ["Juan Pérez Ficticio"],
        "training_window": {
            "coach_feedback": ["Juan Pérez Ficticio faltó a la sesión del jueves."],
        },
    }
    update = await anonymize(state)
    assert "Juan Pérez Ficticio" not in update["training_window"]["coach_feedback"][0]


@pytest.mark.asyncio
async def test_anonymize_leaves_training_window_untouched_without_coach_feedback(
    configure_db_factory, fake_session
):
    configure_db_factory(fake_session)
    state = {
        "athlete_id": 7,
        "competitor_id": 22,
        "run_id": "abc",
        "raw_data": [{"athlete_id": 7, "competitor_id": 22}],
        "training_window": {"window_days": 28, "coach_feedback": []},
    }
    update = await anonymize(state)
    assert "training_window" not in update
