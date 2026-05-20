"""Nodo 11: ``rehydrate_names`` — revierte pseudónimos a nombres reales.

Solo afecta el **output FINAL** que ve el coach. Lo que vio el LLM (draft)
SIEMPRE tenía pseudónimo — el mapping nunca se exporta al modelo.

Para MVP, el "nombre real" se busca por SQL crudo en la tabla
``athletes`` usando el ``athlete_id`` del state (es info que el coach
ya tiene). Si la query falla, degradamos a "Atleta #{id}".

Output: ``state["final_analysis"]`` con el mismo :class:`AnalysisOutput`
pero con ``raw_markdown`` re-escrito.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from app.services.race.ai.db import get_session
from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry
from app.services.race.schemas import AnalysisOutput

logger = logging.getLogger(__name__)

NODE_NAME = "rehydrate_names"


async def _fetch_athlete_name(db: Any, athlete_id: int) -> str:
    try:
        result = await db.execute(
            text(
                "SELECT first_name, last_name FROM athletes WHERE id = :aid LIMIT 1"
            ),
            {"aid": athlete_id},
        )
        rows = result.fetchall() if hasattr(result, "fetchall") else result.all()
    except Exception as exc:  # pragma: no cover - degradación silenciosa
        logger.warning("rehydrate_names: query falló (%s)", type(exc).__name__)
        return f"Atleta #{athlete_id}"

    if not rows:
        return f"Atleta #{athlete_id}"
    row = rows[0]
    first = getattr(row, "first_name", None) or (row[0] if hasattr(row, "__getitem__") else None)
    last = getattr(row, "last_name", None) or (row[1] if hasattr(row, "__getitem__") and len(row) > 1 else None)
    name_parts = [p for p in (first, last) if p]
    return " ".join(name_parts) if name_parts else f"Atleta #{athlete_id}"


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def rehydrate_names(state: dict) -> dict[str, Any]:
    draft = state.get("draft_analysis")
    if draft is None:
        return {}

    mapping: dict[str, int] = state.get("mapping") or {}
    if not mapping:
        # Sin mapping (ej. tests sin anonymize), devolvemos el draft tal cual.
        return {"final_analysis": draft}

    # Resolvemos cada pseudónimo → nombre real (única consulta por uno).
    pseudonym_to_name: dict[str, str] = {}
    try:
        async with get_session() as db:
            for pseudo, ath_id in mapping.items():
                pseudonym_to_name[pseudo] = await _fetch_athlete_name(db, ath_id)
    except RuntimeError:
        # db_factory no configurado (tests). Usamos fallback "Atleta #{id}".
        for pseudo, ath_id in mapping.items():
            pseudonym_to_name[pseudo] = f"Atleta #{ath_id}"

    # Re-escribir markdown y secciones.
    md = draft.raw_markdown or ""
    for pseudo, name in pseudonym_to_name.items():
        md = md.replace(pseudo, name)

    sections = {
        k: (v or "")
        for k, v in (draft.sections or {}).items()
    }
    for pseudo, name in pseudonym_to_name.items():
        sections = {k: v.replace(pseudo, name) for k, v in sections.items()}

    final = AnalysisOutput(
        pseudonym=draft.pseudonym,  # el output preserva el pseudónimo original
        sections=sections,
        citations_used=list(draft.citations_used),
        recommendations=list(draft.recommendations),
        risk_flags=list(draft.risk_flags),
        raw_markdown=md,
        word_count=draft.word_count,
    )
    return {"final_analysis": final}


__all__ = ["rehydrate_names", "NODE_NAME"]
