"""Group free-text ``technical_focus`` strings into presentation skill families.

Coaches type ``technical_focus`` as free text per training session (e.g. "curvas
cerradas y frenado en descenso"). For the monthly newsletter we need a coarse,
human-readable breakdown of how many sessions touched each skill family instead
of the raw text. This module provides a pure, deterministic classifier: no DB
access, no I/O, safe to call from services and to unit test in isolation.

Matching strategy
------------------
- Accent-insensitive, lowercase substring keyword matching (NFKD strip of
  combining marks) so "cadéncia"/"cadencia" or "presión"/"presion" match alike.
- First-match-wins in a fixed priority order (``_PRIORITY_ORDER``): a session
  focus is assigned to the first family whose keyword set matches, even if a
  later family's keyword would also match. This keeps overlapping vocabulary
  (e.g. "descenso" touching both braking and terrain skills) deterministic.
- Unmatched non-empty strings fall into the ``otros`` bucket. Empty/blank
  strings are ignored entirely (not counted, not bucketed).

Destination families
---------------------
Eight canonical A-H skill families (slug/name kept verbatim from the retired
technique catalog module), plus two presentation-only buckets that never
belonged to that catalog:

- ``resistencia_acondicionamiento`` — conditioning/endurance-flavoured focus
  text (zona 2, VO2, umbral, etc.) that is not a PMBIA technical skill at all.
- ``otros`` — catch-all for anything that matches no keyword set.

Keyword-to-family mapping rationale (documented per R6 instructions):
- "curva"/"trazado"/"trazar" -> ``curvas`` (E, matches catalog focus verbatim).
- "descenso"/"bajada"/"downhill" -> ``presion_terreno`` (G): the catalog's own
  focus text for G is "Pump, raíces/rocas, drops", i.e. descent/terrain
  technique, not braking modulation specifically.
- "frenado"/"freno" -> ``frenado`` (C) only for explicit braking vocabulary.
- Conditioning vocabulary (zona 2, VO2, umbral, FTP, fuerza...) is diverted to
  ``resistencia_acondicionamiento`` before it can fall through to ``otros``.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FocusGroup:
    """One skill family with how many sessions were classified into it."""

    slug: str
    name: str
    session_count: int


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _normalize(text: str) -> str:
    return _strip_accents(text).lower()


# Priority-ordered (slug, name, keywords). First match wins.
# Names for A-H are copied verbatim from the retired technique catalog module.
_PRIORITY_ORDER: list[tuple[str, str, tuple[str, ...]]] = [
    (
        "posicion",
        "Posición neutra/lista y equilibrio",
        ("posicion", "equilibrio", "trackstand", "postura"),
    ),
    (
        "vision",
        "Mirada / visión",
        ("vision", "mirada", "mirar lejos"),
    ),
    (
        "frenado",
        "Frenado modulado",
        ("frenado", "freno", "frenar"),
    ),
    (
        "control_baja_velocidad",
        "Control a baja velocidad",
        ("baja velocidad", "control lento", "maniobrar lento", "pie al suelo"),
    ),
    (
        "curvas",
        "Trazado de curvas",
        ("curva", "trazado", "trazar", "inclinar"),
    ),
    (
        "separacion",
        "Separación cuerpo-bici",
        ("separacion", "manual", "bunny hop", "levantar rueda"),
    ),
    (
        "presion_terreno",
        "Control de presión / terreno",
        (
            "presion",
            "pump",
            "raices",
            "rocas",
            "drop",
            "descenso",
            "bajada",
            "downhill",
            "terreno",
        ),
    ),
    (
        "cambios_cadencia",
        "Cambios y cadencia",
        ("cambios", "cadencia", "engranar", "cambio de piñon", "piñon"),
    ),
    (
        "resistencia_acondicionamiento",
        "Resistencia y acondicionamiento",
        (
            "zona 2",
            "z2",
            "vo2",
            "resistencia",
            "intervalo",
            "fuerza",
            "base aerobica",
            "ftp",
            "umbral",
        ),
    ),
]

_OTROS_SLUG = "otros"
_OTROS_NAME = "Otros"


def group_focus_texts(focus_list: list[str]) -> list[FocusGroup]:
    """Classify per-session free-text focus strings into skill families.

    Args:
        focus_list: Raw ``technical_focus`` values, one per session (not
            deduplicated — repeated text across sessions increments the same
            family's count).

    Returns:
        Groups with ``session_count > 0``, sorted by ``session_count``
        descending. The sum of all ``session_count`` equals the number of
        non-empty (post-``strip()``) entries in ``focus_list``.
    """
    counts: dict[str, int] = {}

    for raw_text in focus_list:
        if not raw_text or not raw_text.strip():
            continue

        normalized_text = _normalize(raw_text)
        matched_slug = _OTROS_SLUG

        for slug, _name, keywords in _PRIORITY_ORDER:
            if any(keyword in normalized_text for keyword in keywords):
                matched_slug = slug
                break

        counts[matched_slug] = counts.get(matched_slug, 0) + 1

    names_by_slug = {slug: name for slug, name, _keywords in _PRIORITY_ORDER}
    names_by_slug[_OTROS_SLUG] = _OTROS_NAME

    groups = [
        FocusGroup(slug=slug, name=names_by_slug[slug], session_count=count)
        for slug, count in counts.items()
    ]
    groups.sort(key=lambda group: group.session_count, reverse=True)
    return groups
