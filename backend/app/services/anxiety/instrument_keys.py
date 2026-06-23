"""Loader for the licensed instrument scoring keys.

Keys live as JSON under ``app/data/anxiety_keys/`` and are the single source
of truth for scoring (FR-004). Item TEXT is NOT stored here — it is provisioned
from the licensed source — only the item→subscale mapping, reverse flags, and
ranges. Never invent items.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_KEYS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "anxiety_keys"

VALID_TYPES = ("csai2r", "sas2", "csai2")


@dataclass(frozen=True)
class Subscale:
    name: str
    items: tuple[int, ...]
    reverse: frozenset[int]
    range: tuple[int, int]


@dataclass(frozen=True)
class InstrumentKey:
    type: str
    version: str
    age_band: str
    item_count: int
    likert: tuple[int, int]
    scoring_method: str  # "mean_times_10" | "sum"
    subscales: dict[str, Subscale | None]

    def subscale(self, name: str) -> Subscale | None:
        return self.subscales.get(name)


def _parse(raw: dict) -> InstrumentKey:
    subscales: dict[str, Subscale | None] = {}
    for name, body in raw["subscales"].items():
        if body is None:
            subscales[name] = None
            continue
        subscales[name] = Subscale(
            name=name,
            items=tuple(body["items"]),
            reverse=frozenset(body.get("reverse", [])),
            range=tuple(body["range"]),  # type: ignore[arg-type]
        )
    return InstrumentKey(
        type=raw["type"],
        version=raw["version"],
        age_band=raw["age_band"],
        item_count=raw["item_count"],
        likert=tuple(raw["likert"]),  # type: ignore[arg-type]
        scoring_method=raw["scoring_method"],
        subscales=subscales,
    )


@lru_cache(maxsize=None)
def load_key(instrument_type: str) -> InstrumentKey:
    """Load and cache the scoring key for ``instrument_type``.

    Raises ``ValueError`` for unknown types or missing files.
    """
    if instrument_type not in VALID_TYPES:
        raise ValueError(f"Unknown instrument type: {instrument_type!r}")
    path = _KEYS_DIR / f"{instrument_type}.json"
    if not path.exists():
        raise ValueError(f"Scoring key file not found for {instrument_type!r}: {path}")
    with path.open(encoding="utf-8") as fh:
        return _parse(json.load(fh))
