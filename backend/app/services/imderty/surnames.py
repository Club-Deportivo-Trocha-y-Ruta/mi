"""Surname-split heuristic for the IMDERTY monthly attendance sheet (feature 047, US2).

``Athlete.last_name`` remains the single source of truth for the full
surname text (research.md R7) — nothing here mutates it. This module only
proposes how to split that text into ``first_surname`` / ``second_surname``
for the IMDERTY profile, and checks whether a candidate split still rebuilds
the original text (the invariant the service layer enforces before it lets
a coach confirm a split).
"""

from __future__ import annotations

import unicodedata

# Spanish surname particles kept attached to the surname that follows them.
_SINGLE_TOKEN_PARTICLES = {"DE", "DEL"}
_DE_COMPOUND_PARTICLES = {"LA", "LOS", "LAS"}


def _normalize(text: str) -> str:
    """Fold accents, case and whitespace so splits compare equal regardless of them."""
    stripped = unicodedata.normalize("NFKD", text.strip())
    without_accents = "".join(ch for ch in stripped if not unicodedata.combining(ch))
    return " ".join(without_accents.upper().split())


def propose_split(last_name: str) -> tuple[str, str | None]:
    """Propose a (first_surname, second_surname) split for ``last_name``.

    Spanish particles ``DE``, ``DEL``, ``DE LA``, ``DE LOS``, ``DE LAS`` stay
    attached to the token that follows them when they open the surname text,
    so e.g. "DE LA CRUZ GÓMEZ" splits as ("DE LA CRUZ", "GÓMEZ"), never
    ("DE", "LA CRUZ GÓMEZ"). A single surname (with or without a leading
    particle) yields ``second_surname=None``.
    """
    tokens = last_name.split()
    if not tokens:
        return (last_name, None)

    idx = 0
    particle_tokens: list[str] = []
    if tokens[0].upper() in _SINGLE_TOKEN_PARTICLES:
        particle_tokens.append(tokens[0])
        idx = 1
        if (
            tokens[0].upper() == "DE"
            and idx < len(tokens)
            and tokens[idx].upper() in _DE_COMPOUND_PARTICLES
        ):
            particle_tokens.append(tokens[idx])
            idx += 1

    if idx < len(tokens):
        first_tokens = [*particle_tokens, tokens[idx]]
        idx += 1
    else:
        # Particle-only text with nothing following it (unusual input) — fall
        # back to keeping the original first token whole.
        first_tokens = particle_tokens or [tokens[0]]

    first_surname = " ".join(first_tokens)
    remaining = tokens[idx:]
    second_surname = " ".join(remaining) if remaining else None
    return (first_surname, second_surname)


def rebuilds(last_name: str, first: str, second: str | None) -> bool:
    """Return whether ``first``/``second`` reconstruct ``last_name``.

    Comparison is accent-, case- and whitespace-insensitive (research.md R7);
    a mismatch means the split must be rejected before it can be confirmed.
    """
    combined = first if not second else f"{first} {second}"
    return _normalize(combined) == _normalize(last_name)
