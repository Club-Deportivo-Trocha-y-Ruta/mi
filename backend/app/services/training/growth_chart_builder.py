"""Construye el contexto SVG de curvas de percentiles para el boletín PDF.

Geometría calculada en Python; el template Jinja renderiza el SVG directamente
sin ningún JS. Solo va a pdf_only_blocks, NUNCA a email_blocks.

Privacidad:
  - El dict retornado no contiene nombre, fecha de nacimiento, z-scores
    ni etiquetas diagnósticas del atleta.
  - Los logs usan solo athlete.id (int), nunca PII.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.growth import GrowthIndicator, GrowthSource

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes de layout
# ---------------------------------------------------------------------------

_W: int = 400
_H: int = 260
_PAD_LEFT: int = 42
_PAD_RIGHT: int = 16
_PAD_TOP: int = 16
_PAD_BOTTOM: int = 36

_PLOT_W: int = _W - _PAD_LEFT - _PAD_RIGHT   # 342
_PLOT_H: int = _H - _PAD_TOP - _PAD_BOTTOM   # 208

# Solo las 5 curvas para PDF B/N A4
_CURVES_CFG: dict[str, tuple[str, str]] = {
    "p3":  ("#e74c3c", "2,2"),
    "p25": ("#f39c12", "6,2"),
    "p50": ("#27ae60", ""),
    "p75": ("#f39c12", "6,2"),
    "p97": ("#e74c3c", "2,2"),
}

_INDICATOR_LABEL: dict[str, str] = {
    "height": "Talla (cm)",
    "bmi":    "IMC (kg/m²)",
    "weight": "Peso (kg)",
}

_INDICATOR_TO_GROWTH: dict[str, GrowthIndicator] = {
    "height": GrowthIndicator.height_for_age,
    "bmi":    GrowthIndicator.bmi_for_age,
    "weight": GrowthIndicator.weight_for_age,
}

# Edad mínima/máxima del CDC que queremos cubrir (meses)
_CDC_AGE_MIN: float = 60.0    # 5 años
_CDC_AGE_MAX: float = 228.0   # 19 años


# ---------------------------------------------------------------------------
# TypedDicts internos (IDE / mypy)
# ---------------------------------------------------------------------------

class _AxisInfo(TypedDict):
    min_months: float
    max_months: float
    ticks: list[float]


class _YAxisInfo(TypedDict):
    min: float
    max: float
    ticks: list[float]


class _CurveEntry(TypedDict):
    path: str
    stroke_dasharray: str
    color: str


class _AthletePoints(TypedDict):
    polyline_points: str
    points: list[dict[str, float]]


class _PhvMarker(TypedDict):
    x: float
    label: str


class GrowthChartCtx(TypedDict):
    enough_data: bool
    reason_no_data: str | None
    indicator: str
    indicator_label_es: str
    sex: str
    viewbox: str
    width: int
    height: int
    x_axis: _AxisInfo
    y_axis: _YAxisInfo
    curves: dict[str, _CurveEntry]
    athlete: _AthletePoints
    phv_marker: _PhvMarker | None


# ---------------------------------------------------------------------------
# Helpers de geometría
# ---------------------------------------------------------------------------

def _age_months_from_birth(birth_date: date, eval_date: date) -> float:
    """Calcula la edad en meses entre dos fechas con precisión de días."""
    delta_days = (eval_date - birth_date).days
    return delta_days / 30.4375  # promedio gregoriano


def _scale_x(age_months: float, x_min: float, x_max: float) -> float:
    """Convierte edad en meses a coordenada X del SVG."""
    if x_max == x_min:
        return _PAD_LEFT
    frac = (age_months - x_min) / (x_max - x_min)
    return round(_PAD_LEFT + frac * _PLOT_W, 1)


def _scale_y(value: float, y_min: float, y_max: float) -> float:
    """Convierte valor a coordenada Y del SVG (Y invertido: mayor valor = menor Y)."""
    if y_max == y_min:
        return _PAD_TOP + _PLOT_H / 2
    frac = (value - y_min) / (y_max - y_min)
    return round(_PAD_TOP + _PLOT_H - frac * _PLOT_H, 1)


def _build_svg_path(points: list[tuple[float, float]]) -> str:
    """Genera un SVG path string tipo 'M x,y L x,y ...'"""
    if not points:
        return ""
    parts = [f"M {points[0][0]},{points[0][1]}"]
    for px, py in points[1:]:
        parts.append(f"L {px},{py}")
    return " ".join(parts)


def _nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    """Genera n ticks 'bonitos' entre lo y hi."""
    rng = hi - lo
    if rng <= 0:
        return [round(lo, 1)]
    raw_step = rng / (n - 1)
    # Redondear el step a 1 cifra significativa
    magnitude = 10 ** (len(str(int(raw_step))) - 1) if raw_step >= 1 else 1
    step = round(raw_step / magnitude) * magnitude or magnitude
    start = (lo // step) * step
    ticks: list[float] = []
    t = start
    while t <= hi + step * 0.01:
        if lo - step * 0.1 <= t <= hi + step * 0.1:
            ticks.append(round(t, 1))
        t = round(t + step, 8)
    return ticks[:n + 2]  # tolerar algún tick extra


def _months_to_year_ticks(x_min: float, x_max: float) -> list[float]:
    """Genera ticks anuales (cada 12 meses) dentro del rango."""
    first_year = int(x_min // 12) + 1
    last_year = int(x_max // 12)
    return [float(y * 12) for y in range(first_year, last_year + 1)]


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

async def build_percentile_chart_ctx(
    db: AsyncSession,
    athlete_id: int,
    birth_date: date,
    sex: str,
    records: list,          # list[AnthropometricRecord]
    indicator: str,         # "height" | "bmi" | "weight"
    phv_age_decimal: float | None = None,
) -> GrowthChartCtx:
    """Construye el dict de contexto SVG para un gráfico de percentiles.

    Args:
        db: sesión async (requerida para get_reference_curve).
        athlete_id: solo para logging (sin PII).
        birth_date: fecha de nacimiento del atleta.
        sex: "M" o "F".
        records: lista de AnthropometricRecord ordenados por fecha asc.
        indicator: "height", "bmi" o "weight".
        phv_age_decimal: edad decimal en el momento del PHV (si existe).

    Returns:
        GrowthChartCtx con enough_data=False si no hay datos suficientes.
    """
    from app.services.growth import get_reference_curve

    label = _INDICATOR_LABEL.get(indicator, indicator)
    growth_indicator = _INDICATOR_TO_GROWTH.get(indicator)

    # -----------------------------------------------------------------------
    # Guardas de datos insuficientes
    # -----------------------------------------------------------------------
    if not sex or sex not in ("M", "F"):
        return _empty_ctx(indicator, label, sex or "M", "missing_sex")

    if not records or len(records) < 2:
        return _empty_ctx(indicator, label, sex, "insufficient_records")

    # -----------------------------------------------------------------------
    # Construir puntos del atleta
    # -----------------------------------------------------------------------
    athlete_raw: list[tuple[float, float]] = []
    for r in records:
        if r.evaluation_date is None:
            continue
        age_months = _age_months_from_birth(birth_date, r.evaluation_date)

        if indicator == "height":
            if r.standing_height_cm is None:
                continue
            value = float(r.standing_height_cm)
        elif indicator == "weight":
            if r.weight_kg is None:
                continue
            value = float(r.weight_kg)
        elif indicator == "bmi":
            if r.weight_kg is None or r.standing_height_cm is None:
                continue
            height_m = float(r.standing_height_cm) / 100.0
            if height_m <= 0:
                continue
            value = float(r.weight_kg) / (height_m ** 2)
        else:
            continue

        athlete_raw.append((age_months, value))

    if len(athlete_raw) < 2:
        return _empty_ctx(indicator, label, sex, "insufficient_records")

    min_age = min(a[0] for a in athlete_raw)
    max_age = max(a[0] for a in athlete_raw)

    # Verificar rango etario cubierto por CDC
    if max_age < _CDC_AGE_MIN or min_age > _CDC_AGE_MAX:
        return _empty_ctx(indicator, label, sex, "age_out_of_range")

    # -----------------------------------------------------------------------
    # Dominio de ejes
    # -----------------------------------------------------------------------
    x_min = max(_CDC_AGE_MIN, min_age - 12.0)
    x_max = min(_CDC_AGE_MAX, max_age + 24.0)

    # -----------------------------------------------------------------------
    # Curvas de referencia (solo rango relevante)
    # -----------------------------------------------------------------------
    if growth_indicator is None:
        logger.error("Indicador desconocido: %s (athlete_id=%s)", indicator, athlete_id)
        raise ValueError("growth_chart_unavailable")

    try:
        ref_points = await get_reference_curve(
            db=db,
            indicator=growth_indicator,
            sex=sex,
            source=GrowthSource.CDC,
            age_range=(x_min, x_max),
        )
    except Exception:
        logger.error("get_reference_curve falló (athlete_id=%s, indicator=%s)", athlete_id, indicator)
        raise ValueError("growth_chart_unavailable")

    if not ref_points:
        return _empty_ctx(indicator, label, sex, "age_out_of_range")

    # -----------------------------------------------------------------------
    # Dominio Y: padding 5% sobre [min, max] de todas las series visibles
    # -----------------------------------------------------------------------
    all_y_values: list[float] = [v for _, v in athlete_raw]
    for pt in ref_points:
        all_y_values.append(pt["P3"])
        all_y_values.append(pt["P97"])

    raw_y_min = min(all_y_values)
    raw_y_max = max(all_y_values)
    y_pad = (raw_y_max - raw_y_min) * 0.05
    y_min = raw_y_min - y_pad
    y_max = raw_y_max + y_pad

    # -----------------------------------------------------------------------
    # Construir paths SVG de curvas de referencia
    # -----------------------------------------------------------------------
    percentile_keys = {"p3": "P3", "p25": "P25", "p50": "P50", "p75": "P75", "p97": "P97"}
    curves: dict[str, _CurveEntry] = {}

    for curve_key, p_key in percentile_keys.items():
        color, dasharray = _CURVES_CFG[curve_key]
        svg_points: list[tuple[float, float]] = []
        for pt in ref_points:
            sx = _scale_x(float(pt["age_months"]), x_min, x_max)
            sy = _scale_y(float(pt[p_key]), y_min, y_max)
            svg_points.append((sx, sy))
        curves[curve_key] = _CurveEntry(
            path=_build_svg_path(svg_points),
            stroke_dasharray=dasharray,
            color=color,
        )

    # -----------------------------------------------------------------------
    # Puntos del atleta en coordenadas SVG
    # -----------------------------------------------------------------------
    athlete_svg: list[dict[str, float]] = []
    for age_m, val in sorted(athlete_raw, key=lambda t: t[0]):
        sx = _scale_x(age_m, x_min, x_max)
        sy = _scale_y(val, y_min, y_max)
        athlete_svg.append({"x": sx, "y": sy})

    polyline_pts = " ".join(f"{p['x']},{p['y']}" for p in athlete_svg)

    # -----------------------------------------------------------------------
    # Marker PHV
    # -----------------------------------------------------------------------
    phv_marker: _PhvMarker | None = None
    if phv_age_decimal is not None:
        phv_months = phv_age_decimal * 12.0
        if x_min <= phv_months <= x_max:
            phv_x = _scale_x(phv_months, x_min, x_max)
            phv_marker = _PhvMarker(x=phv_x, label="PHV")

    # -----------------------------------------------------------------------
    # Ticks de ejes
    # -----------------------------------------------------------------------
    x_ticks = _months_to_year_ticks(x_min, x_max)
    y_ticks = _nice_ticks(y_min, y_max, n=5)

    return GrowthChartCtx(
        enough_data=True,
        reason_no_data=None,
        indicator=indicator,
        indicator_label_es=label,
        sex=sex,
        viewbox=f"0 0 {_W} {_H}",
        width=_W,
        height=_H,
        x_axis=_AxisInfo(
            min_months=round(x_min, 1),
            max_months=round(x_max, 1),
            ticks=x_ticks,
        ),
        y_axis=_YAxisInfo(
            min=round(y_min, 1),
            max=round(y_max, 1),
            ticks=y_ticks,
        ),
        curves=curves,
        athlete=_AthletePoints(
            polyline_points=polyline_pts,
            points=athlete_svg,
        ),
        phv_marker=phv_marker,
    )


# ---------------------------------------------------------------------------
# Helper: dict vacío (enough_data=False)
# ---------------------------------------------------------------------------

def _empty_ctx(indicator: str, label: str, sex: str, reason: str) -> GrowthChartCtx:
    return GrowthChartCtx(
        enough_data=False,
        reason_no_data=reason,
        indicator=indicator,
        indicator_label_es=label,
        sex=sex,
        viewbox=f"0 0 {_W} {_H}",
        width=_W,
        height=_H,
        x_axis=_AxisInfo(min_months=0.0, max_months=0.0, ticks=[]),
        y_axis=_YAxisInfo(min=0.0, max=0.0, ticks=[]),
        curves={},
        athlete=_AthletePoints(polyline_points="", points=[]),
        phv_marker=None,
    )
