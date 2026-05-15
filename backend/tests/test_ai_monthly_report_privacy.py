"""Tests de privacidad reforzada del MonthlyReportUseCase (Ola 3).

Cubre:
1. Shuffle determinista de pseudónimos: misma (club_id, year, month) -> mismo mapping.
2. Rotación entre meses: misma (club_id, year), distinto month -> permutación distinta.
3. Rotación entre clubes: misma (year, month), distinto club_id -> permutación distinta.
4. Threshold n<5: suprime filas individuales y emite attendance_summary agregado.
5. Threshold n>=5: comportamiento normal con filas detalladas.
6. Render del template respeta el agregado y oculta filas individuales.
7. Guardrails siguen rechazando nombres reales cuando n<5 (no regresión).
"""

from __future__ import annotations

import pytest

from app.schemas.training_session import AthleteAttendanceStats, MonthlyMetrics
from app.services.ai.errors import LLMSchemaError
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.providers.fake import FakeLLMProvider
from app.services.ai.use_cases.monthly_report import (
    MIN_ATHLETES_FOR_INDIVIDUAL_ROWS,
    MonthlyReportGuardrails,
    MonthlyReportUseCase,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stat(aid: int, pct: float = 80.0) -> AthleteAttendanceStats:
    """Genera un AthleteAttendanceStats trivial para un atleta."""
    return AthleteAttendanceStats(
        athlete_id=aid,
        count_present=8,
        count_absent=2,
        count_justified=0,
        count_late=0,
        count_injured=0,
        total_sessions=10,
        attendance_pct=pct,
    )


def _metrics(athlete_ids: list[int], percentages: list[float] | None = None) -> MonthlyMetrics:
    """Construye un MonthlyMetrics con los atletas dados."""
    if percentages is None:
        percentages = [80.0] * len(athlete_ids)
    return MonthlyMetrics(
        club_id=1,
        year=2026,
        month=4,
        total_sessions_planned=12,
        total_sessions_executed=10,
        total_sessions_cancelled=2,
        attendance_by_athlete={
            aid: _stat(aid, pct=p)
            for aid, p in zip(athlete_ids, percentages, strict=True)
        },
        technical_focus_list=["Frenado progresivo"],
        avg_rpe=6.5,
        avg_rubric_effort=3.8,
        avg_rubric_attitude=4.1,
        avg_rubric_technique=3.5,
    )


def _make_use_case() -> MonthlyReportUseCase:
    return MonthlyReportUseCase(
        provider=FakeLLMProvider(canned="x" * 80),
        registry=PromptRegistry(),
    )


def _pseudonym_map(ctx_stats, athlete_ids: list[int], metrics: MonthlyMetrics) -> dict[int, str]:
    """Reconstruye el mapping athlete_id -> pseudonym desde ctx.attendance_stats.

    Se basa en el invariante de que (count_present + count_late, total_sessions, pct)
    identifica unívocamente al stats de origen cuando los porcentajes/conteos son
    distintos por atleta.
    """
    mapping: dict[int, str] = {}
    for s in ctx_stats:
        for aid, raw in metrics.attendance_by_athlete.items():
            if (
                raw.count_present + raw.count_late == s.count_present
                and raw.total_sessions == s.count_total
                and abs(raw.attendance_pct - s.percentage) < 0.001
                and aid not in mapping
            ):
                mapping[aid] = s.pseudonym
                break
    return mapping


# ---------------------------------------------------------------------------
# 1. Shuffle determinista — reproducibilidad
# ---------------------------------------------------------------------------


def test_shuffle_determinista_misma_clave_mismo_mapping():
    """Mismo (club_id, year, month) -> mismo mapping pseudónimo<->athlete_id."""
    uc = _make_use_case()
    ids = [101, 202, 303, 404, 505, 606, 707, 808]
    # Porcentajes únicos por atleta para poder reconstruir el mapping
    pcts = [55.0, 60.0, 65.0, 70.0, 75.0, 80.0, 85.0, 90.0]
    m = _metrics(ids, pcts)

    ctx_a = uc.build_context_from_metrics(
        club_id=42, club_name="C", year=2026, month=4, metrics=m
    )
    ctx_b = uc.build_context_from_metrics(
        club_id=42, club_name="C", year=2026, month=4, metrics=m
    )

    map_a = _pseudonym_map(ctx_a.attendance_stats, ids, m)
    map_b = _pseudonym_map(ctx_b.attendance_stats, ids, m)

    assert map_a == map_b
    assert len(map_a) == len(ids)


# ---------------------------------------------------------------------------
# 2. Rotación entre meses — permutación distinta
# ---------------------------------------------------------------------------


def test_shuffle_rota_entre_meses():
    """Mismo club_id+year, distinto month -> permutación distinta para n>=5."""
    uc = _make_use_case()
    ids = list(range(101, 109))  # 8 atletas
    pcts = [55.0 + i * 5 for i in range(8)]
    m_apr = _metrics(ids, pcts)
    # Mismo dataset pero mes distinto
    m_may = m_apr.model_copy(update={"month": 5})

    ctx_apr = uc.build_context_from_metrics(
        club_id=42, club_name="C", year=2026, month=4, metrics=m_apr
    )
    ctx_may = uc.build_context_from_metrics(
        club_id=42, club_name="C", year=2026, month=5, metrics=m_may
    )

    map_apr = _pseudonym_map(ctx_apr.attendance_stats, ids, m_apr)
    map_may = _pseudonym_map(ctx_may.attendance_stats, ids, m_may)

    # Al menos un atleta cambia de pseudónimo entre meses (shuffle uniforme).
    # Con n=8, esperamos que la mayoría cambien.
    changed = sum(1 for aid in ids if map_apr[aid] != map_may[aid])
    assert changed >= 1, (
        f"Esperaba al menos 1 atleta cambie de pseudónimo entre meses; "
        f"obtenido changed={changed}, map_apr={map_apr}, map_may={map_may}"
    )


# ---------------------------------------------------------------------------
# 3. Rotación entre clubes — permutación distinta
# ---------------------------------------------------------------------------


def test_shuffle_rota_entre_clubes():
    """Mismo (year, month), distinto club_id -> permutación distinta para n>=5."""
    uc = _make_use_case()
    ids = list(range(101, 109))
    pcts = [55.0 + i * 5 for i in range(8)]
    m = _metrics(ids, pcts)

    ctx_42 = uc.build_context_from_metrics(
        club_id=42, club_name="C42", year=2026, month=4, metrics=m
    )
    ctx_99 = uc.build_context_from_metrics(
        club_id=99, club_name="C99", year=2026, month=4, metrics=m
    )

    map_42 = _pseudonym_map(ctx_42.attendance_stats, ids, m)
    map_99 = _pseudonym_map(ctx_99.attendance_stats, ids, m)

    changed = sum(1 for aid in ids if map_42[aid] != map_99[aid])
    assert changed >= 1, (
        f"Esperaba al menos 1 atleta cambie de pseudónimo entre clubes; "
        f"obtenido changed={changed}"
    )


# ---------------------------------------------------------------------------
# 4. Threshold n<5 — suprime filas individuales
# ---------------------------------------------------------------------------


def test_threshold_n_menor_a_5_suprime_filas_y_emite_summary():
    """Club con 4 atletas -> attendance_stats=[] y attendance_summary no vacío."""
    uc = _make_use_case()
    ids = [101, 202, 303, 404]
    pcts = [60.0, 70.0, 80.0, 85.0]
    m = _metrics(ids, pcts)

    ctx = uc.build_context_from_metrics(
        club_id=1, club_name="C", year=2026, month=4, metrics=m
    )

    assert ctx.attendance_stats == []
    assert ctx.attendance_summary is not None
    assert "4" in ctx.attendance_summary  # n=4 mencionado
    # Promedio: (60+70+80+85)/4 = 73.75 -> redondeado a 74%
    assert "74" in ctx.attendance_summary
    # Rango 60-85
    assert "60" in ctx.attendance_summary
    assert "85" in ctx.attendance_summary


def test_threshold_n_menor_a_5_formato_summary():
    """Formato esperado del summary cuando n<5."""
    uc = _make_use_case()
    ids = [101, 202, 303]
    pcts = [50.0, 75.0, 100.0]
    m = _metrics(ids, pcts)

    ctx = uc.build_context_from_metrics(
        club_id=1, club_name="C", year=2026, month=4, metrics=m
    )

    summary = ctx.attendance_summary
    assert summary is not None
    # Promedio: (50+75+100)/3 = 75
    assert "3 atletas" in summary
    assert "75%" in summary
    assert "rango" in summary.lower()
    assert "50" in summary and "100" in summary


# ---------------------------------------------------------------------------
# 5. Threshold n>=5 — comportamiento normal
# ---------------------------------------------------------------------------


def test_threshold_n_igual_a_5_emite_filas_individuales():
    """Club con 5 atletas (umbral exacto) -> attendance_stats con 5 filas, summary=None."""
    uc = _make_use_case()
    ids = list(range(101, 106))  # 5 atletas
    pcts = [55.0, 65.0, 75.0, 85.0, 95.0]
    m = _metrics(ids, pcts)

    ctx = uc.build_context_from_metrics(
        club_id=1, club_name="C", year=2026, month=4, metrics=m
    )

    assert len(ctx.attendance_stats) == 5
    assert ctx.attendance_summary is None
    pseudonyms = {s.pseudonym for s in ctx.attendance_stats}
    assert pseudonyms == {"A1", "A2", "A3", "A4", "A5"}


def test_threshold_constante_es_5():
    """El umbral de re-identificación es 5 — verifica la constante exportada."""
    assert MIN_ATHLETES_FOR_INDIVIDUAL_ROWS == 5


# ---------------------------------------------------------------------------
# 6. Render del template
# ---------------------------------------------------------------------------


def test_render_template_con_summary_no_emite_filas():
    """Cuando attendance_summary está presente, el prompt NO debe contener 'A1:' etc."""
    uc = _make_use_case()
    registry = PromptRegistry()
    ids = [101, 202, 303, 404]  # n=4 < 5
    pcts = [60.0, 70.0, 80.0, 85.0]
    m = _metrics(ids, pcts)

    ctx = uc.build_context_from_metrics(
        club_id=1, club_name="Trocha y Ruta", year=2026, month=4, metrics=m
    )

    context_dict = ctx.model_dump(exclude={"forbidden_names"})
    context_dict["attendance_stats"] = [s.model_dump() for s in ctx.attendance_stats]
    rendered = registry.render("monthly_report", context_dict)

    # No filas individuales tipo "- A1: 8/10 (80%)"
    assert "- A1:" not in rendered
    assert "- A2:" not in rendered
    assert "- A3:" not in rendered
    assert "- A4:" not in rendered
    # Sí contiene la frase agregada
    assert ctx.attendance_summary is not None
    assert ctx.attendance_summary in rendered
    # Y la nota inline de supresión por privacidad bajo la sección Asistencia
    assert "detalle individual omitido por privacidad" in rendered


def test_render_template_con_stats_normales_emite_filas():
    """Cuando hay >=5 atletas, el prompt SÍ contiene filas individuales."""
    uc = _make_use_case()
    registry = PromptRegistry()
    ids = list(range(101, 107))  # 6 atletas
    pcts = [50.0 + 10 * i for i in range(6)]
    m = _metrics(ids, pcts)

    ctx = uc.build_context_from_metrics(
        club_id=1, club_name="Trocha y Ruta", year=2026, month=4, metrics=m
    )

    context_dict = ctx.model_dump(exclude={"forbidden_names"})
    context_dict["attendance_stats"] = [s.model_dump() for s in ctx.attendance_stats]
    rendered = registry.render("monthly_report", context_dict)

    # Las 6 filas A1..A6 deben aparecer
    for i in range(1, 7):
        assert f"- A{i}:" in rendered
    # No emite la nota inline de privacidad (la frase de las restricciones
    # del prompt puede contener "grupo pequeño", pero la nota inline
    # "detalle individual omitido por privacidad" NO debe aparecer).
    assert "detalle individual omitido por privacidad" not in rendered


# ---------------------------------------------------------------------------
# 7. No regresión — guardrails siguen rechazando nombres reales cuando n<5
# ---------------------------------------------------------------------------


async def test_guardrails_rechazan_nombre_real_con_n_menor_a_5():
    """Si el LLM intenta meter un nombre real en un club con n<5, el guardrail lo rechaza."""
    # Texto suficiente (>=50 palabras) que contiene un nombre real
    spam_words = " ".join(["palabra"] * 60)
    fake_text = f"Pedro Pérez destacó este mes. {spam_words}"
    fake = FakeLLMProvider(canned=fake_text)
    uc = MonthlyReportUseCase(fake, PromptRegistry())

    ids = [101, 202, 303]
    pcts = [60.0, 70.0, 80.0]
    m = _metrics(ids, pcts)

    ctx = uc.build_context_from_metrics(
        club_id=1,
        club_name="C",
        year=2026,
        month=4,
        metrics=m,
        real_names={"Pedro Pérez"},
    )

    with pytest.raises(LLMSchemaError, match="nombre real"):
        await uc.run(ctx)


def test_guardrails_independientes_del_threshold():
    """Los guardrails operan sobre el output del LLM; no dependen del threshold."""
    g = MonthlyReportGuardrails(forbidden_names=frozenset({"Pedro Pérez"}))
    base = " ".join(
        [
            "Durante el mes de abril el grupo mostró participación sostenida en las",
            "sesiones planificadas por el entrenador del club deportivo. Los focos",
            "técnicos fueron cubiertos satisfactoriamente y la asistencia agregada",
            "se mantuvo dentro de los rangos esperados para la categoría. Pedro Pérez",
            "fue destacado por su constancia durante las jornadas técnicas semanales.",
        ]
    )
    with pytest.raises(LLMSchemaError, match="nombre real"):
        g.scrub(base)
