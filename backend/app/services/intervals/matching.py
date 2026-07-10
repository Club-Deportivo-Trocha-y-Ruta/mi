"""Motor de correlación plan-vs-real (feature 026, decisión D5 de research.md).

Función **pura, determinística y sin I/O**: recibe los bloques del plan ya
aplanados (las repeticiones ya expandidas — NO se importa ``flatten`` acá) y las
vueltas (laps) persistidas de la actividad Strava, y devuelve el
``MatchResultPayload`` que valida el ``result_json`` antes de persistirse
(``interval_match_results.result_json``; ver data-model.md §6).

Reglas de emparejamiento (D5):
1. Se descartan las vueltas con ``elapsed_time_s < 10`` (ruido de doble-click en
   el botón de vuelta); se cuentan en ``laps_discarded_under_10s``.
2. Se conserva el orden del dispositivo por ``lap_index``.
3. Emparejamiento posicional: ``plan[i] ↔ lap[i]`` (sobre las vueltas ya
   filtradas).
4. Estado por bloque:
   - ``cumplido``          si ``|dur_lap − dur_plan| / dur_plan <= 0.30``.
   - ``fuera_tolerancia``  si excede la tolerancia.
   - ``sin_dato``          si el bloque planificado no tiene vuelta emparejada.
   - ``extra``             vueltas sobrantes sin bloque — se reportan como filas
                           informativas, NUNCA se descartan en silencio ni se
                           fuerzan sobre un bloque.

Privacidad (Ley 1581 / menores): solo se propagan métricas numéricas de la
vuelta (duración, FC). El ``MatchResultPayload`` (``extra="forbid"`` en todo el
árbol) rechaza cualquier clave de GPS/mapa/cadencia/potencia que se colara.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.schemas.intervals import (
    MatchResultBlock,
    MatchResultExtraLap,
    MatchResultPayload,
    MatchSummary,
)

# ---------------------------------------------------------------------------
# Constantes del motor
# ---------------------------------------------------------------------------

#: Versión del motor de matching. Se incrementa cuando cambian estas reglas
#: (se persiste en ``interval_match_results.engine_version``).
ENGINE_VERSION = 1

#: Tolerancia de duración por bloque (±30 %). Vive en una sola constante (D5).
DURATION_TOLERANCE_FRACTION = 0.30

#: ``tolerance_pct`` del ``result_json`` — la fracción como porcentaje entero.
TOLERANCE_PCT = int(round(DURATION_TOLERANCE_FRACTION * 100))  # 30

#: Vueltas por debajo de este umbral (en segundos) se descartan como ruido.
MIN_LAP_ELAPSED_S = 10


# ---------------------------------------------------------------------------
# Contratos de entrada (estructuras livianas — el match_runner las construye)
# ---------------------------------------------------------------------------


@runtime_checkable
class FlattenedBlockLike(Protocol):
    """Bloque de plan ya aplanado que consume el motor.

    Cualquier objeto (dataclass, modelo ORM, namedtuple) con estos atributos
    sirve — tipado estructural para no acoplar este módulo a ``structures.py``.
    """

    block_id: int | None
    block_type: str
    repeat_iteration: int | None
    planned_duration_s: int
    target_zone: str
    target_cadence_rpm: int


@runtime_checkable
class LapLike(Protocol):
    """Vuelta persistida que consume el motor (solo campos numéricos, sin geo)."""

    lap_index: int
    elapsed_time_s: int
    average_heartrate: float | None


@dataclass(frozen=True, slots=True)
class FlattenedBlock:
    """Implementación concreta de :class:`FlattenedBlockLike`.

    Provista por conveniencia para el ``match_runner`` (que aplana la estructura
    y arma esta lista). ``block_id``/``repeat_iteration`` son opcionales.
    """

    block_type: str
    planned_duration_s: int
    target_zone: str
    target_cadence_rpm: int
    block_id: int | None = None
    repeat_iteration: int | None = None


@dataclass(frozen=True, slots=True)
class MatchLap:
    """Implementación concreta de :class:`LapLike` (vuelta numérica sin geo)."""

    lap_index: int
    elapsed_time_s: int
    average_heartrate: float | None = None


# ---------------------------------------------------------------------------
# Motor
# ---------------------------------------------------------------------------


def _is_within_tolerance(lap_elapsed_s: int, planned_duration_s: int) -> bool:
    """``True`` si la duración de la vuelta cae dentro de la tolerancia del plan.

    ``planned_duration_s`` siempre es > 0 (garantizado por el schema/servicio),
    así que la división es segura.
    """
    deviation = abs(lap_elapsed_s - planned_duration_s) / planned_duration_s
    return deviation <= DURATION_TOLERANCE_FRACTION


def compute_match(
    flattened_blocks: Sequence[FlattenedBlockLike],
    laps: Sequence[LapLike],
) -> MatchResultPayload:
    """Empareja el plan aplanado contra las vueltas y arma el ``result_json``.

    Determinística y sin efectos secundarios (D5). No lee ni escribe nada, no
    consulta la red ni la base: dadas las mismas entradas produce la misma
    salida. Ver reglas completas en el docstring del módulo.

    Args:
        flattened_blocks: Bloques del plan YA aplanados por repetición, en orden.
        laps: Vueltas de la actividad (se ordenan por ``lap_index`` y se filtran
            las < 10 s internamente; el orden de entrada no importa).

    Returns:
        ``MatchResultPayload`` listo para persistir en
        ``interval_match_results.result_json``.
    """
    # 1) Descartar vueltas de ruido (< 10 s) y conservar el orden del dispositivo.
    ordered = sorted(laps, key=lambda lap: lap.lap_index)
    kept: list[LapLike] = [lap for lap in ordered if lap.elapsed_time_s >= MIN_LAP_ELAPSED_S]
    laps_discarded_under_10s = len(ordered) - len(kept)

    result_blocks: list[MatchResultBlock] = []
    summary = MatchSummary()

    # 2-4) Emparejamiento posicional plan[i] ↔ lap[i] + estado por bloque.
    for flat_index, block in enumerate(flattened_blocks):
        if flat_index < len(kept):
            lap = kept[flat_index]
            status: str = (
                "cumplido"
                if _is_within_tolerance(lap.elapsed_time_s, block.planned_duration_s)
                else "fuera_tolerancia"
            )
            result_blocks.append(
                MatchResultBlock(
                    flat_index=flat_index,
                    block_id=block.block_id,
                    block_type=block.block_type,
                    repeat_iteration=block.repeat_iteration,
                    planned_duration_s=block.planned_duration_s,
                    target_zone=block.target_zone,
                    target_cadence_rpm=block.target_cadence_rpm,
                    lap_index=lap.lap_index,
                    lap_elapsed_time_s=lap.elapsed_time_s,
                    lap_average_heartrate=lap.average_heartrate,
                    status=status,
                )
            )
        else:
            # Bloque planificado sin vuelta emparejada → sin_dato.
            status = "sin_dato"
            result_blocks.append(
                MatchResultBlock(
                    flat_index=flat_index,
                    block_id=block.block_id,
                    block_type=block.block_type,
                    repeat_iteration=block.repeat_iteration,
                    planned_duration_s=block.planned_duration_s,
                    target_zone=block.target_zone,
                    target_cadence_rpm=block.target_cadence_rpm,
                    lap_index=None,
                    lap_elapsed_time_s=None,
                    lap_average_heartrate=None,
                    status=status,
                )
            )

        _increment_summary(summary, status)

    # 5) Vueltas sobrantes → filas extra (informativas, nunca descartadas).
    extra_laps: list[MatchResultExtraLap] = []
    for lap in kept[len(flattened_blocks):]:
        extra_laps.append(
            MatchResultExtraLap(
                lap_index=lap.lap_index,
                elapsed_time_s=lap.elapsed_time_s,
                average_heartrate=lap.average_heartrate,
            )
        )
        summary.extra += 1

    return MatchResultPayload(
        blocks=result_blocks,
        extra_laps=extra_laps,
        summary=summary,
        tolerance_pct=TOLERANCE_PCT,
        laps_discarded_under_10s=laps_discarded_under_10s,
    )


def _increment_summary(summary: MatchSummary, status: str) -> None:
    """Suma 1 al contador del estado dado (``extra`` se cuenta aparte)."""
    if status == "cumplido":
        summary.cumplido += 1
    elif status == "fuera_tolerancia":
        summary.fuera_tolerancia += 1
    elif status == "sin_dato":
        summary.sin_dato += 1
