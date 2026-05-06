"""Métricas derivadas de envergadura (arm span)."""

from __future__ import annotations

POSTURE_SCREENING_THRESHOLD_CM = 3.0

POSTURE_SCREENING_MESSAGE = (
    "Diferencia talla–envergadura > 3 cm detectada. "
    "Informar al acudiente y sugerir consulta con médico deportivo "
    "de confianza si persiste en próximas mediciones."
)

APE_INDEX_INSTABILITY_ADVISORY = (
    "Dato orientativo. En fase de crecimiento activo, la envergadura "
    "crece antes que la talla — re-evaluar al completar el brote (Post-PHV)."
)


def _classify_bike_fit(ape_index: float) -> tuple[str, str]:
    if ape_index < 0.97:
        return (
            "short_reach",
            "Reach corto. Considerar potencia (stem) más corta y "
            "manillar con menor barrido. Re-evaluar ajuste cada 3-6 meses.",
        )
    if ape_index > 1.03:
        return (
            "long_reach",
            "Reach largo. Considerar potencia (stem) más larga o cuadro "
            "con reach mayor. Re-evaluar ajuste cada 3-6 meses.",
        )
    return (
        "standard",
        "Proporciones estándar. Ajuste de bici según talla y altura "
        "del sillín habituales. Re-evaluar cada 3-6 meses.",
    )


def calculate_arm_span_metrics(
    arm_span_cm: float | None,
    standing_height_cm: float,
    maturation_status: str | None,
) -> dict | None:
    """Devuelve métricas morfológicas a partir de envergadura, o None si no hay dato.

    Returns:
        dict con keys: ape_index, arm_span_height_delta_cm, posture_screening_flag,
        posture_screening_message, bike_fit_category, bike_fit_guidance,
        ape_index_advisory.
    """
    if arm_span_cm is None or standing_height_cm <= 0:
        return None

    delta = arm_span_cm - standing_height_cm
    abs_delta = abs(delta)
    ape_index = arm_span_cm / standing_height_cm

    posture_flag = abs_delta > POSTURE_SCREENING_THRESHOLD_CM
    posture_msg = POSTURE_SCREENING_MESSAGE if posture_flag else None

    bike_fit_category, bike_fit_guidance = _classify_bike_fit(ape_index)

    advisory: str | None = None
    if maturation_status in ("Pre-PHV", "Circa-PHV"):
        advisory = APE_INDEX_INSTABILITY_ADVISORY
    elif maturation_status is None:
        advisory = APE_INDEX_INSTABILITY_ADVISORY

    return {
        "ape_index": round(ape_index, 3),
        "arm_span_height_delta_cm": round(delta, 1),
        "posture_screening_flag": posture_flag,
        "posture_screening_message": posture_msg,
        "bike_fit_category": bike_fit_category,
        "bike_fit_guidance": bike_fit_guidance,
        "ape_index_advisory": advisory,
    }
