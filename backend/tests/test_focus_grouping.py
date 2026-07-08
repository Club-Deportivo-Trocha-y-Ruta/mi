"""Tests for the pure focus-grouping helper (spec 024, R6).

No DB access, no fixtures — the module under test is a deterministic
classifier over free-text strings.
"""

from app.services.training.focus_grouping import group_focus_texts


def test_descenso_bajada_curva_near_duplicates_collapse_to_fewer_groups():
    """Overlapping descent/terrain vocabulary should not fragment into many
    single-count groups; 'descenso'/'bajada'/'terreno' variants without an
    earlier-priority keyword (frenado/curva) all collapse into
    presion_terreno."""
    groups = group_focus_texts(
        [
            "descenso técnico en pista",
            "bajada en terreno suelto",
            "trabajo de descenso y raíces",
        ]
    )
    assert len(groups) == 1
    assert groups[0].slug == "presion_terreno"
    assert groups[0].session_count == 3


def test_zona2_vo2_map_to_resistencia_acondicionamiento():
    groups = group_focus_texts(["Zona 2 FC", "Vo2 Max"])
    assert len(groups) == 1
    assert groups[0].slug == "resistencia_acondicionamiento"
    assert groups[0].session_count == 2


def test_unrecognized_text_falls_into_otros():
    groups = group_focus_texts(["actividad recreativa libre sin enfoque específico"])
    assert len(groups) == 1
    assert groups[0].slug == "otros"
    assert groups[0].name == "Otros"


def test_accent_and_case_insensitive_matching():
    groups = group_focus_texts(["CADÉNCIA y cambios de piñón", "cadencia y cambios"])
    assert len(groups) == 1
    assert groups[0].slug == "cambios_cadencia"
    assert groups[0].session_count == 2


def test_sum_of_session_counts_equals_non_empty_inputs():
    focus_list = [
        "curvas cerradas",
        "",
        "   ",
        "frenado modulado",
        "zona 2",
        "texto sin clasificar reconocible",
        None if False else "otro texto libre",
    ]
    groups = group_focus_texts(focus_list)
    non_empty_count = sum(1 for f in focus_list if f and f.strip())
    assert sum(g.session_count for g in groups) == non_empty_count


def test_empty_and_blank_strings_are_ignored_not_counted():
    groups = group_focus_texts(["", "   ", "\t"])
    assert groups == []


def test_empty_list_returns_empty_groups():
    assert group_focus_texts([]) == []


def test_groups_ordered_by_session_count_descending():
    groups = group_focus_texts(
        [
            "curvas",
            "curvas",
            "curvas",
            "frenado",
            "frenado",
            "vision",
        ]
    )
    counts = [g.session_count for g in groups]
    assert counts == sorted(counts, reverse=True)
    assert groups[0].slug == "curvas"
    assert groups[0].session_count == 3


def test_first_match_wins_priority_order_deterministic():
    """'descenso' also contains terrain-ish text but should stably resolve
    to presion_terreno, not fall through to otros, regardless of call order."""
    text = "trabajo de descenso en pista"
    first = group_focus_texts([text])
    second = group_focus_texts([text, text])
    assert first[0].slug == second[0].slug == "presion_terreno"


def test_conditioning_vocabulary_diverted_before_otros():
    groups = group_focus_texts(["trabajo de fuerza y umbral en subida larga"])
    assert groups[0].slug == "resistencia_acondicionamiento"
