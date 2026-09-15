"""Pure derivation of distance/speed figures for a race result row.

Binding contract: ``specs/043-race-course-profile/contracts/results-derived-figures.md``
§2. Kept dependency-free (stdlib only) because it is imported from three call
sites (``results_read.py``, ``analytics_charts.py``, season-summary rows) that
must not risk a circular import with SQLAlchemy models.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


def _round1(value: Decimal) -> float:
    """Round a ``Decimal`` to one decimal place using ``ROUND_HALF_UP``.

    Avoids Python's native banker's rounding, which can disagree with the
    expected result exactly at ``.x5`` ties (e.g. ``round(1.25, 1) == 1.2``
    natively, but the contract requires ``1.3``). The caller is responsible
    for building ``value`` as an *exact* ``Decimal`` from the original
    integers (laps, metres, milliseconds) rather than from a float that has
    already been through lossy division — see ``derive_figures`` below for
    why that distinction matters at low-speed boundary values.
    """
    return float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class DerivedFigures:
    distance_km: float | None
    avg_speed_kmh: float | None
    lap_distance_km: float | None
    elevation_gain_m: int | None


_NONE_FIGURES = DerivedFigures(
    distance_km=None, avg_speed_kmh=None, lap_distance_km=None, elevation_gain_m=None
)


def derive_figures(
    setup: Any,
    status: str,
    race_time_ms: int | None,
    laps_behind: int | None,
) -> DerivedFigures:
    """Derive distance/speed/lap/elevation figures for one result row.

    ``setup`` is anything duck-typed with ``.laps: int`` and
    ``.variant.lap_distance_m: int`` / ``.variant.elevation_gain_m: int | None``
    (the real ORM ``RaceCourseCategorySetup``/``RaceCourseVariant``, or a
    lightweight test double). ``None`` means the category has no course setup
    configured — all four figures are ``None`` regardless of ``status`` or
    ``race_time_ms``.

    When the race dynamics don't support computing a distance (unfinished
    status, missing time, or an unknown ``laps_behind`` on ``minus_laps``),
    every field comes back ``None`` together — ``lap_distance_km`` and
    ``elevation_gain_m`` are not reported in isolation without a matching
    ``distance_km``/``avg_speed_kmh``.
    """
    if setup is None:
        return _NONE_FIGURES

    status_ok = status in {"finished", "minus_laps"} and race_time_ms is not None
    if not status_ok:
        return _NONE_FIGURES
    if status == "minus_laps" and laps_behind is None:
        return _NONE_FIGURES

    laps_completed = setup.laps - (laps_behind or 0)
    if laps_completed <= 0:
        # Defensive: shouldn't happen with real data (can't lose more laps
        # than the category has), but never return a negative/zero distance.
        return _NONE_FIGURES

    # Compute distance once, unrounded, and reuse it for both the returned
    # (rounded) distance_km and the speed division below — so the average
    # speed is derived from the true distance, not from a value that has
    # already been rounded once for display (no compounding of roundings).
    #
    # Built as an exact Decimal from the original integers rather than via
    # float division: chaining two float divisions (m -> km, then km -> a
    # speed) can lose just enough precision to land a fraction like 0.05 on
    # the wrong side of a rounding tie (str(1*300/1000 / (21_600_000/3_600_000))
    # is "0.049999999999999996", not "0.05", which would wrongly round down
    # to 0.0 instead of up to 0.1). Decimal arithmetic on the integers is
    # exact here (division by powers of ten and by race_time_ms both resolve
    # well within the default 28-digit context precision for these
    # magnitudes), so the final ROUND_HALF_UP quantize sees the true value.
    distance_km_exact = Decimal(laps_completed) * Decimal(setup.variant.lap_distance_m) / Decimal(1000)
    hours_exact = Decimal(race_time_ms) / Decimal(3_600_000)
    lap_distance_km_exact = Decimal(setup.variant.lap_distance_m) / Decimal(1000)

    return DerivedFigures(
        distance_km=_round1(distance_km_exact),
        avg_speed_kmh=_round1(distance_km_exact / hours_exact),
        lap_distance_km=_round1(lap_distance_km_exact),
        elevation_gain_m=setup.variant.elevation_gain_m,
    )
