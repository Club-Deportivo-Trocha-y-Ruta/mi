"""Tests v2 — persist_insight con fan-out por válida usando ``per_valida_drafts``.

Task #9 (race-results v2). Contratos asumidos (otros agentes implementan
en paralelo):

- El nodo ``persist_insight`` lee ``state["per_valida_drafts"]: dict[int,
  AnalysisOutput]`` cuando ``prompt_version=race_analyst_v2`` y persiste
  UNA fila por entrada del dict, cada una con su ``summary_text`` derivado
  de ese ``AnalysisOutput``. Esto sustituye al fan-out por
  ``valida_nums`` del flujo v1 (donde todas las filas comparten un único
  ``summary_text``).

- Compat v1: si ``per_valida_drafts`` está ausente o vacío, el nodo
  conserva el comportamiento histórico (fan-out con un ``draft_analysis``
  replicado y mismo ``summary_text`` por cada ``valida_nums``).

Feature 036 (T081): el contrato ``per_valida_drafts`` está implementado en
``persist_insight`` (rama ``is_v2`` — ver docstring del módulo bajo
"Fix BUG-001"), así que los dos tests que antes llevaban
``@pytest.mark.xfail`` ahora pasan de verdad y el marcador se retiró.
"""

from __future__ import annotations

from app.services.race.ai.nodes.persist_insight import persist_insight
from tests.services.race.ai.conftest import make_analysis_output


async def test_persist_insight_v2_per_valida_drafts_distinct_summaries(
    configure_db_factory, fake_session
):
    """Dos drafts → dos filas con ``summary_text`` distinto cada una."""
    configure_db_factory(fake_session)

    draft_a = make_analysis_output(
        markdown="## Qué pasó\nVálida 1: progreso técnico en frenada."
    )
    draft_b = make_analysis_output(
        markdown="## Qué pasó\nVálida 2: mejora en cadencia sostenida."
    )

    state = {
        "athlete_id": 1,
        "season": 2026,
        "coach_id": 99,
        # v2: drafts indexados por valida_num
        "per_valida_drafts": {1: draft_a, 2: draft_b},
        # draft_analysis se mantiene para compat (puede ser cualquiera de los dos)
        "draft_analysis": draft_a,
        "valida_nums": [1, 2],
        "hitl_decision": {"decision": "approve"},
        "aggregate_metrics": {"prompt_version_analyst": "race_analyst_v2"},
        "principles": [],
        "metrics": {},
    }

    await persist_insight(state)

    # Una fila por válida con summary_text propio.
    assert len(fake_session.added_objects) == 2

    summaries = sorted(row.summary_text for row in fake_session.added_objects)
    assert any("Válida 1" in s for s in summaries)
    assert any("Válida 2" in s for s in summaries)
    # Los summaries son distintos (no replicados).
    assert summaries[0] != summaries[1]


async def test_persist_insight_v2_prompt_version_propagated_per_row(
    configure_db_factory, fake_session
):
    """Cada fila persiste con ``prompt_version=race_analyst_v2``."""
    configure_db_factory(fake_session)

    state = {
        "athlete_id": 1,
        "season": 2026,
        "coach_id": 99,
        "per_valida_drafts": {
            1: make_analysis_output(markdown="## Qué pasó\nA"),
            3: make_analysis_output(markdown="## Qué pasó\nC"),
        },
        "draft_analysis": make_analysis_output(),
        "valida_nums": [1, 3],
        "hitl_decision": {"decision": "approve"},
        "aggregate_metrics": {"prompt_version_analyst": "race_analyst_v2"},
        "principles": [],
        "metrics": {},
    }

    await persist_insight(state)

    assert len(fake_session.added_objects) == 2
    for row in fake_session.added_objects:
        assert row.prompt_version == "race_analyst_v2"
        # valida_num debe coincidir con la key del dict, no con un sentinel.
        assert row.valida_num in (1, 3)


async def test_persist_insight_v1_compat_no_per_valida_drafts(
    configure_db_factory, fake_session
):
    """Compat v1: ausencia de ``per_valida_drafts`` mantiene el fan-out
    histórico — todas las filas comparten ``summary_text`` del único draft.
    """
    configure_db_factory(fake_session)

    shared_draft = make_analysis_output(
        markdown="## Evolución\nProgreso constante en válidas 1-3."
    )

    state = {
        "athlete_id": 1,
        "season": 2026,
        "coach_id": 99,
        "draft_analysis": shared_draft,
        # No incluimos per_valida_drafts. Compat v1 → fan-out por valida_nums.
        "valida_nums": [1, 2, 3],
        "hitl_decision": {"decision": "approve"},
        "aggregate_metrics": {"prompt_version_analyst": "race_analyst_v1"},
        "principles": [],
        "metrics": {},
    }

    await persist_insight(state)

    # Comportamiento v1: 3 filas, todas con el mismo summary_text.
    assert len(fake_session.added_objects) == 3
    summaries = {row.summary_text for row in fake_session.added_objects}
    assert len(summaries) == 1  # Replicado, no fan-out por contenido.


async def test_persist_insight_v1_compat_single_draft_one_row(
    configure_db_factory, fake_session
):
    """Compat v1 puntual: un solo ``valida_num`` → una fila."""
    configure_db_factory(fake_session)

    state = {
        "athlete_id": 1,
        "season": 2026,
        "coach_id": 99,
        "draft_analysis": make_analysis_output(),
        "valida_num": 4,  # singular
        "hitl_decision": {"decision": "approve"},
        "aggregate_metrics": {"prompt_version_analyst": "race_analyst_v1"},
        "principles": [],
        "metrics": {},
    }

    await persist_insight(state)
    assert len(fake_session.added_objects) == 1
    assert fake_session.added_objects[0].valida_num == 4
