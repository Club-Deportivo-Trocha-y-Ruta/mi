"""Age-driven instrument selection with the under-13 safeguard.

Constitution Principle V: SAS-2 is forced/suggested for athletes under 13;
CSAI-2R is the default for 13–15. Applying CSAI-2/2R to an under-13 athlete is
allowed only as an explicit override and MUST surface a warning (FR-002/003).
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_UNDER_13 = "sas2"
DEFAULT_13_15 = "csai2r"
_ANXIETY_ADULT = {"csai2", "csai2r"}

UNDER_13_OVERRIDE_WARNING = (
    "El instrumento {instrument} está por debajo de su rango validado para "
    "menores de 13 años. Para este grupo se recomienda SAS-2. Confirma el "
    "override solo si tienes una razón clínica/metodológica."
)


@dataclass(frozen=True)
class InstrumentSelection:
    instrument: str
    override_used: bool
    warning: str | None


def select_instrument(
    age_years: float,
    override: str | None = None,
) -> InstrumentSelection:
    """Resolve the instrument for an athlete of ``age_years``.

    ``override`` (if given) forces that instrument; for under-13 athletes an
    anxiety-adult override (CSAI-2/2R) returns a warning. Raises ``ValueError``
    for an unknown override value.
    """
    if override is not None and override not in ("sas2", "csai2r", "csai2"):
        raise ValueError(f"Unknown instrument override: {override!r}")

    under_13 = age_years < 13

    if override is None:
        instrument = DEFAULT_UNDER_13 if under_13 else DEFAULT_13_15
        return InstrumentSelection(instrument=instrument, override_used=False, warning=None)

    default = DEFAULT_UNDER_13 if under_13 else DEFAULT_13_15
    override_used = override != default
    warning = None
    if under_13 and override in _ANXIETY_ADULT:
        warning = UNDER_13_OVERRIDE_WARNING.format(instrument=override.upper())
    return InstrumentSelection(
        instrument=override,
        override_used=override_used,
        warning=warning,
    )
