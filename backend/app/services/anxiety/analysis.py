"""Pattern detection and alert flags shared by submit + dashboards (US5).

Coarse bands as fractions of each subscale's official range (guidance only,
not clinical cutoffs — research R3). Reused by the group-triage dashboard and
by the alert-flag computation stored on each assessment.
"""
from __future__ import annotations

from typing import Literal

from app.services.anxiety.instrument_keys import load_key

_LOW = 0.33
_HIGH = 0.66

GroupPattern = Literal[
    "somatic_high", "cognitive_high", "confidence_low", "favorable"
]

HIGH_ANX_LOW_CONF_FLAG = (
    "Ansiedad alta junto con confianza baja: sugiere conversación individual. "
    "Si se sostiene en varias evaluaciones, considerar derivación a un "
    "profesional de salud."
)


def _position(value: float | None, rng: tuple[int, int]) -> float | None:
    if value is None:
        return None
    lo, hi = rng
    if hi == lo:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def _ranges(instrument_type: str) -> dict[str, tuple[int, int]]:
    key = load_key(instrument_type)
    out: dict[str, tuple[int, int]] = {}
    for name in ("cognitive", "somatic", "selfconfidence"):
        sub = key.subscale(name)
        out[name] = sub.range if sub else (0, 1)
    return out


def dominant_pattern(
    instrument_type: str,
    scores: dict[str, float | None],
) -> GroupPattern:
    """Bucket the athlete by dominant pattern for race-day triage."""
    rng = _ranges(instrument_type)
    cog = _position(scores.get("cognitive"), rng["cognitive"])
    som = _position(scores.get("somatic"), rng["somatic"])
    conf = _position(scores.get("selfconfidence"), rng["selfconfidence"])

    conf_low = conf is not None and conf < _LOW
    som_high = som is not None and som >= _HIGH
    cog_high = cog is not None and cog >= _HIGH

    if conf_low and (som_high or cog_high):
        return "confidence_low"
    if som_high and (cog is None or (som or 0) >= (cog or 0)):
        return "somatic_high"
    if cog_high:
        return "cognitive_high"
    if conf_low:
        return "confidence_low"
    return "favorable"


def compute_flags(
    instrument_type: str,
    scores: dict[str, float | None],
) -> list[str]:
    """Return alert flags (e.g. high anxiety + low confidence)."""
    rng = _ranges(instrument_type)
    cog = _position(scores.get("cognitive"), rng["cognitive"])
    som = _position(scores.get("somatic"), rng["somatic"])
    conf = _position(scores.get("selfconfidence"), rng["selfconfidence"])

    anxiety_high = (cog is not None and cog >= _HIGH) or (
        som is not None and som >= _HIGH
    )
    confidence_low = conf is not None and conf < _LOW

    flags: list[str] = []
    if anxiety_high and confidence_low:
        flags.append(HIGH_ANX_LOW_CONF_FLAG)
    return flags
