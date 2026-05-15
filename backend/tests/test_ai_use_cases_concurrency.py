"""Tests de concurrencia para los use cases de IA.

Cubre el bug crítico de race condition descubierto en `BaseUseCase`:
previamente cada `run()` mutaba `self._guardrails` como atributo de
instancia, así que dos requests concurrentes sobre la misma instancia
podían pisarse las reglas (p. ej., un padre 10-12 perdía las reglas
anti-potenciómetro porque otro request 13-15 sobrescribía el atributo
entre `_ask` y `_scrub`).

La corrección: `_scrub` recibe `Guardrails` como parámetro local, no lee
de instancia. Estos tests instancian un solo use case y disparan dos
`run()` con `asyncio.gather`, verificando que cada llamada recibe las
reglas que le corresponden.
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.anthropometry import MaturationStatus
from app.models.athlete import Sex
from app.services.ai.guardrails import Guardrails
from app.services.ai.models import LLMRequest, LLMResponse, TokenUsage
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.providers.fake import FakeLLMProvider
from app.services.ai.use_cases.monthly_report import (
    AnonymizedAthleteStats,
    MonthlyReportContext,
    MonthlyReportGuardrails,
    MonthlyReportUseCase,
)
from app.services.ai.use_cases.phv_explainer import PHVExplainerUseCase


# ---------------------------------------------------------------------------
# Fakes específicos para concurrencia
# ---------------------------------------------------------------------------


class SlowDispatchingLLMProvider:
    """Provider asíncrono que duerme para forzar entrelazado entre `run()`s.

    Inspecciona el mensaje de usuario renderizado y devuelve un texto
    distinguible por request. El `sleep` se programa entre `_ask` y
    `_scrub`, que es justo la ventana donde el bug original permitía que
    un request pisara el `self._guardrails` del otro.
    """

    name = "slow-fake"
    model = "slow-fake-model"

    def __init__(self, sleep_seconds: float = 0.05) -> None:
        self._sleep = sleep_seconds
        self.requests: list[LLMRequest] = []
        self.lock = asyncio.Lock()

    async def complete(self, req: LLMRequest) -> LLMResponse:
        # Registro thread-safe para inspección desde el test.
        async with self.lock:
            self.requests.append(req)
        # Pausa cooperativa: cede el loop para que el otro `run()` avance
        # entre `_ask` y `_scrub`.
        await asyncio.sleep(self._sleep)
        user_text = req.messages[-1].content
        # Texto canned distinguible: el cuerpo se basa en cuál request es.
        # Para PHV usamos el grupo de edad como marca; para Monthly Report
        # incluimos el nombre del club. Ambos casos solo aportan texto neutro.
        if "10-12" in user_text:
            text = (
                "Texto generado para grupo 10-12. Recomendamos pedalear con "
                "cadencia adecuada y disfrutar la sesión."
            )
        elif "13-15" in user_text:
            text = (
                "Texto generado para grupo 13-15. Pueden incorporar trabajo "
                "estructurado con intervalos suaves."
            )
        else:
            text = (
                "Texto neutral genérico de prueba sin datos sensibles "
                "para el reporte mensual del club."
            )
        return LLMResponse(
            text=text,
            usage=TokenUsage(input_tokens=len(user_text), output_tokens=len(text)),
            model=self.model,
            provider=self.name,
            latency_ms=int(self._sleep * 1000),
        )

    async def complete_json(self, req: LLMRequest, schema: dict) -> dict:
        return {}


class _ScrubRecorder:
    """Captura los `Guardrails` recibidos por `_scrub` en cada llamada."""

    def __init__(self) -> None:
        self.calls: list[Guardrails] = []
        self.lock = asyncio.Lock()


def _make_recording_phv_use_case(
    provider, registry, recorder: _ScrubRecorder
) -> PHVExplainerUseCase:
    """Construye un PHVExplainerUseCase que registra cada `_scrub`."""
    uc = PHVExplainerUseCase(provider=provider, registry=registry)
    original_scrub = uc._scrub

    def spying_scrub(text: str, guardrails: Guardrails | None = None) -> str:
        # No usamos async lock aquí porque _scrub es síncrono y CPython
        # garantiza atomicidad del append a una lista.
        recorder.calls.append(guardrails)
        return original_scrub(text, guardrails=guardrails)

    uc._scrub = spying_scrub  # type: ignore[assignment]
    return uc


def _make_recording_monthly_use_case(
    provider, registry, recorder: _ScrubRecorder
) -> MonthlyReportUseCase:
    uc = MonthlyReportUseCase(provider=provider, registry=registry)
    original_scrub = uc._scrub

    def spying_scrub(text: str, guardrails: Guardrails | None = None) -> str:
        recorder.calls.append(guardrails)
        return original_scrub(text, guardrails=guardrails)

    uc._scrub = spying_scrub  # type: ignore[assignment]
    return uc


# ---------------------------------------------------------------------------
# Fixtures de dominio
# ---------------------------------------------------------------------------


def _athlete_10_12():
    """Atleta A: 11 años aprox, sexo M (grupo 10-12)."""
    return SimpleNamespace(
        id=1001,
        first_name="AtletaA",
        last_name="Anonimo",
        birth_date=date(2015, 1, 15),
        sex=Sex.M,
        user_id=2001,
        club_id=1,
    )


def _athlete_13_15():
    """Atleta B: 14 años aprox, sexo F (grupo 13-15)."""
    return SimpleNamespace(
        id=1002,
        first_name="AtletaB",
        last_name="Anonimo",
        birth_date=date(2012, 1, 15),
        sex=Sex.F,
        user_id=2002,
        club_id=1,
    )


def _record_for_10_12():
    return SimpleNamespace(
        id=11,
        athlete_id=1001,
        evaluation_date=date(2026, 4, 1),
        weight_kg=Decimal("38.0"),
        standing_height_cm=Decimal("145.0"),
        arm_span_cm=Decimal("147.0"),
        sitting_height_cm=Decimal("73.0"),
        leg_length_cm=Decimal("72.0"),
        maturity_offset=Decimal("-2.0"),
        age_at_phv=Decimal("13.5"),
        maturation_status=MaturationStatus.pre_phv,
        training_implications="Habilidades y juego.",
        height_z_score=Decimal("0.2"),
        bmi=Decimal("18.0"),
        bmi_z_score=Decimal("0.0"),
        weight_z_score=Decimal("0.1"),
        height_percentile=None,
        bmi_percentile=None,
        weight_percentile=None,
        nutritional_status=None,
        notes=None,
    )


def _record_for_13_15():
    return SimpleNamespace(
        id=12,
        athlete_id=1002,
        evaluation_date=date(2026, 4, 1),
        weight_kg=Decimal("52.0"),
        standing_height_cm=Decimal("162.0"),
        arm_span_cm=Decimal("163.0"),
        sitting_height_cm=Decimal("82.0"),
        leg_length_cm=Decimal("80.0"),
        maturity_offset=Decimal("0.5"),
        age_at_phv=Decimal("12.0"),
        maturation_status=MaturationStatus.post_phv,
        training_implications="Trabajo estructurado moderado.",
        height_z_score=Decimal("0.5"),
        bmi=Decimal("19.8"),
        bmi_z_score=Decimal("0.3"),
        weight_z_score=Decimal("0.4"),
        height_percentile=None,
        bmi_percentile=None,
        weight_percentile=None,
        nutritional_status=None,
        notes=None,
    )


# ---------------------------------------------------------------------------
# Test 1 — PHV concurrente: 10-12 vs 13-15
# ---------------------------------------------------------------------------


async def test_phv_concurrent_runs_do_not_cross_guardrails():
    """Dos `run()` concurrentes sobre la misma instancia deben recibir
    guardrails independientes y correctos por edad."""
    provider = SlowDispatchingLLMProvider(sleep_seconds=0.05)
    registry = PromptRegistry()
    recorder = _ScrubRecorder()
    uc = _make_recording_phv_use_case(provider, registry, recorder)

    results = await asyncio.gather(
        uc.run(_athlete_10_12(), _record_for_10_12()),
        uc.run(_athlete_13_15(), _record_for_13_15()),
    )

    # Cada run() debe haber pasado por _scrub exactamente una vez.
    assert len(recorder.calls) == 2

    # Ningún guardrail debe ser None ni el mismo objeto: cada run() construye
    # el suyo localmente.
    g1, g2 = recorder.calls
    assert g1 is not None
    assert g2 is not None
    assert g1 is not g2, (
        "Los dos runs concurrentes están compartiendo la misma instancia "
        "de Guardrails — el bug de race condition sigue presente."
    )

    # Verificamos que cada guardrail tiene el age_group esperado. Para no
    # depender del orden de finalización (asyncio.gather no garantiza orden
    # de ejecución entre las corrutinas), comparamos como conjunto.
    age_groups = {g._age_group for g in recorder.calls}
    assert age_groups == {"10-12", "13-15"}, (
        f"Se esperaban guardrails para 10-12 y 13-15, llegaron {age_groups}"
    )

    # Smoke: ambos run() devolvieron texto coherente con su grupo.
    texts = {r.age_group: r.text for r in results}
    assert "10-12" in texts and "13-15" in texts
    assert "10-12" in texts["10-12"]
    assert "13-15" in texts["13-15"]


# ---------------------------------------------------------------------------
# Test 2 — MonthlyReport concurrente: forbidden_names disjuntos
# ---------------------------------------------------------------------------


def _monthly_ctx(*, club_name: str, forbidden: frozenset[str]) -> MonthlyReportContext:
    return MonthlyReportContext(
        club_name=club_name,
        period_year=2026,
        period_month=4,
        total_sessions_planned=10,
        total_sessions_executed=9,
        total_sessions_cancelled=1,
        attendance_stats=[
            AnonymizedAthleteStats(
                pseudonym="A1", count_present=8, count_total=9, percentage=89.0
            ),
        ],
        focos_técnicos=["Frenado"],
        avg_rpe=6.0,
        avg_rubric_effort=3.8,
        avg_rubric_attitude=4.0,
        avg_rubric_technique=3.5,
        coach_observations=None,
        forbidden_names=forbidden,
    )


async def test_monthly_report_concurrent_runs_respect_per_request_forbidden_names():
    """Dos reportes mensuales concurrentes con listas de nombres prohibidos
    distintas deben aplicar cada uno sus propias reglas. Se simula el caso
    donde el LLM "filtra" un nombre real: el run() correspondiente debe
    rechazar; el otro, que no tiene ese nombre en su lista, debe pasar."""

    # Provider que devuelve textos distintos según el club_name del contexto
    # renderizado. El texto contiene "Pedro Pérez" solo para el Club Norte,
    # con largo suficiente para no fallar por longitud (>50 palabras).
    class _DispatchingProvider:
        name = "dispatch-fake"
        model = "dispatch-fake-model"

        def __init__(self) -> None:
            self.requests: list[LLMRequest] = []

        async def complete(self, req: LLMRequest) -> LLMResponse:
            self.requests.append(req)
            await asyncio.sleep(0.05)
            user = req.messages[-1].content
            if "Club Norte" in user:
                # Texto canned con un nombre real "Pedro Pérez" embebido.
                text = (
                    "Durante el mes de abril, el Club Norte ejecutó las "
                    "sesiones planificadas y la asistencia grupal fue "
                    "satisfactoria, con buena participación general. Los "
                    "focos técnicos se cumplieron de manera adecuada. "
                    "Pedro Pérez destacó esta semana, pero el comité "
                    "trabaja en variar los focos del siguiente mes para "
                    "ampliar habilidades del grupo."
                )
            else:
                # Texto sin nombre real para Club Sur (≥50 palabras para
                # cumplir el mínimo del MonthlyReportGuardrails).
                text = (
                    "Durante el mes de abril, el Club Sur completó las "
                    "sesiones planificadas con asistencia grupal sostenida "
                    "y se reforzaron los focos técnicos previstos. El "
                    "grupo mostró buena actitud y compromiso a lo largo "
                    "de las sesiones, sin novedades destacables, y el "
                    "comité valora continuar con el plan vigente. Se "
                    "recomienda al comité mantener el foco actual y revisar "
                    "los indicadores grupales en el cierre del mesociclo "
                    "siguiente para confirmar la tendencia observada."
                )
            return LLMResponse(
                text=text,
                usage=TokenUsage(input_tokens=len(user), output_tokens=len(text)),
                model=self.model,
                provider=self.name,
                latency_ms=50,
            )

        async def complete_json(self, req: LLMRequest, schema: dict) -> dict:
            return {}

    provider = _DispatchingProvider()
    registry = PromptRegistry()
    recorder = _ScrubRecorder()
    uc = _make_recording_monthly_use_case(provider, registry, recorder)

    ctx_norte = _monthly_ctx(
        club_name="Club Norte", forbidden=frozenset({"Pedro Pérez"})
    )
    ctx_sur = _monthly_ctx(
        club_name="Club Sur", forbidden=frozenset({"Ana García"})
    )

    # El Norte debe rechazarse (nombre real filtrado en su output). El Sur
    # debe pasar (su lista forbidden es disjunta del nombre filtrado).
    results = await asyncio.gather(
        uc.run(ctx_norte),
        uc.run(ctx_sur),
        return_exceptions=True,
    )

    assert isinstance(results[0], Exception), (
        "Club Norte debió rechazarse: su output contiene 'Pedro Pérez' y "
        "'Pedro Pérez' está en sus forbidden_names."
    )
    assert not isinstance(results[1], Exception), (
        f"Club Sur no debió fallar; falló con: {results[1]!r}. "
        "Esto sugeriría que se aplicó forbidden_names del Norte al Sur — "
        "race condition entre requests."
    )

    # Verificamos que se invocaron dos _scrub con guardrails distintos
    # cada uno apuntando a su propia lista forbidden.
    assert len(recorder.calls) == 2
    g_a, g_b = recorder.calls
    assert isinstance(g_a, MonthlyReportGuardrails)
    assert isinstance(g_b, MonthlyReportGuardrails)
    assert g_a is not g_b
    forbidden_sets = {frozenset(g._forbidden_names) for g in recorder.calls}
    assert forbidden_sets == {
        frozenset({"Pedro Pérez"}),
        frozenset({"Ana García"}),
    }


# ---------------------------------------------------------------------------
# Test 3 — Smoke: scrub con guardrails None no rompe el camino feliz
# ---------------------------------------------------------------------------


async def test_scrub_with_no_guardrails_returns_text_unchanged():
    """Garantiza compatibilidad: si un test legacy construye un use case
    sin guardrails y `_scrub` se llama sin argumento, el texto pasa intacto.
    """
    fake = FakeLLMProvider(canned="texto neutro de prueba")
    registry = PromptRegistry()
    uc = PHVExplainerUseCase(fake, registry)

    # Llamada directa a _scrub sin guardrails ni default — debe devolver
    # el texto sin tocar (no debe lanzar AttributeError por self._guardrails).
    assert uc._scrub("texto de prueba") == "texto de prueba"
    assert uc._scrub("texto de prueba", guardrails=None) == "texto de prueba"


async def test_scrub_uses_default_guardrails_when_no_argument():
    """Si el constructor recibe `guardrails=...`, `_scrub` sin argumento
    aplica ese default. Esto preserva compatibilidad con callers que no
    pasen el argumento explícito."""
    fake = FakeLLMProvider(canned="placeholder")
    registry = PromptRegistry()

    # Construimos un BaseUseCase-derivado mínimo para no depender de la
    # plantilla concreta. Reusamos PHVExplainerUseCase y reemplazamos su
    # default_guardrails post-init para emular el caso.
    uc = PHVExplainerUseCase(fake, registry)
    uc._default_guardrails = Guardrails(age_group="10-12")

    # "vatios" debe sustituirse por "RPE (percepción de esfuerzo)" porque
    # _AGE_DEPENDENT_RULES se activa para 10-12.
    result = uc._scrub("Trabajar con vatios constantes hoy.")
    assert "vatios" not in result.lower()
