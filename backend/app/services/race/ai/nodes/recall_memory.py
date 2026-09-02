"""Nodo 6: ``recall_memory`` — últimos 3 insights aprobados del atleta.

Query plana a ``athlete_ai_insights`` (SQL crudo con ``text()`` — mismo
patrón que :mod:`app.services.race.agents.chat`). Retorna lista de
``summary_text`` truncados a 500 chars cada uno.

Si la tabla está vacía o el atleta no tiene insights aún, retorna
``memory=[]`` (analyst funciona OK sin memoria).

Feature 037 (T104) agrega ``coach_dialogue``: los últimos 3 insights
aprobados que SÍ tienen ``structured_json`` (insights v3), cada uno
resumido a ``{headline, coach_question, coach_answer_text, coach_rating,
valida_label, generated_at}`` — le da al analyst el hilo de la
conversación con el coach (AC-4.2: "la respuesta ... se inyecta en la
memoria del siguiente run para ese atleta"). Es una query separada de
``memory`` (que sigue leyendo ``summary_text`` plano de TODOS los
insights aprobados, v1/v2/v3) porque ``coach_dialogue`` solo tiene
sentido para filas v3 con ``structured_json`` poblado.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from app.services.race.ai.db import get_session
from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry

logger = logging.getLogger(__name__)

NODE_NAME = "recall_memory"

_MEMORY_LIMIT = 3
_SUMMARY_MAX_CHARS = 500
_DIALOGUE_LIMIT = 3
_COACH_QUESTION_MAX_CHARS = 240
_COACH_ANSWER_MAX_CHARS = 1000


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def recall_memory(state: dict) -> dict[str, Any]:
    athlete_id = state["athlete_id"]

    try:
        async with get_session() as db:
            result = await db.execute(
                text(
                    """
                    SELECT summary_text
                    FROM athlete_ai_insights
                    WHERE athlete_id = :aid
                      AND coach_approved = 1
                      AND archived_at IS NULL
                    ORDER BY generated_at DESC
                    LIMIT :n
                    """
                ),
                {"aid": athlete_id, "n": _MEMORY_LIMIT},
            )
            rows = result.fetchall() if hasattr(result, "fetchall") else result.all()
    except Exception as exc:
        # Degrada silenciosamente — la memoria es enriquecimiento, no
        # requisito. No queremos romper análisis por falla DB transitoria
        # en lectura opcional.
        logger.warning("recall_memory: query falló (%s) — sin memoria", type(exc).__name__)
        return {"memory": [], "coach_dialogue": []}

    summaries: list[str] = []
    for r in rows or []:
        # Soportamos Row, dict y tuple defensivamente (varios fakes).
        if hasattr(r, "summary_text"):
            text_val = r.summary_text
        elif isinstance(r, dict):
            text_val = r.get("summary_text", "")
        else:
            text_val = r[0] if r else ""
        if text_val:
            summaries.append(str(text_val)[:_SUMMARY_MAX_CHARS])

    coach_dialogue = await _recall_coach_dialogue(athlete_id)

    return {"memory": summaries, "coach_dialogue": coach_dialogue}


async def _recall_coach_dialogue(athlete_id: int) -> list[dict[str, Any]]:
    """Últimos ``_DIALOGUE_LIMIT`` insights v3 aprobados con ``structured_json``.

    Cada item: ``{headline, coach_question, coach_answer_text, coach_rating,
    valida_label, generated_at}``. Degrada a ``[]`` en cualquier falla —
    misma política best-effort que ``memory`` (enriquecimiento, no
    requisito).
    """
    import json as _json

    from app.services.race.race_labels import build_race_label

    try:
        async with get_session() as db:
            result = await db.execute(
                text(
                    """
                    SELECT
                        i.structured_json,
                        i.coach_answer_text,
                        i.coach_rating,
                        i.generated_at,
                        i.valida_num,
                        e.sequence_number,
                        e.location,
                        s.kind AS series_kind,
                        s.level AS series_level
                    FROM athlete_ai_insights i
                    LEFT JOIN race_events e ON e.id = i.event_id
                    LEFT JOIN race_series s ON s.id = e.series_id
                    WHERE i.athlete_id = :aid
                      AND i.coach_approved = 1
                      AND i.archived_at IS NULL
                      AND i.structured_json IS NOT NULL
                    ORDER BY i.generated_at DESC
                    LIMIT :n
                    """
                ),
                {"aid": athlete_id, "n": _DIALOGUE_LIMIT},
            )
            rows = result.fetchall() if hasattr(result, "fetchall") else result.all()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "recall_memory: query coach_dialogue falló (%s) — sin diálogo",
            type(exc).__name__,
        )
        return []

    dialogue: list[dict[str, Any]] = []
    for r in rows or []:
        m = r._mapping if hasattr(r, "_mapping") else {}
        if not m:
            continue

        raw_structured = m.get("structured_json")
        if isinstance(raw_structured, str):
            try:
                structured = _json.loads(raw_structured)
            except (ValueError, TypeError):
                structured = None
        else:
            structured = raw_structured
        if not isinstance(structured, dict):
            continue

        headline = structured.get("headline")
        coach_question = structured.get("coach_question")

        valida_label: str | None = None
        try:
            series_kind_raw = m.get("series_kind")
            sequence_number = m.get("sequence_number")
            if series_kind_raw is not None and sequence_number is not None:
                from app.models.race_series import RaceSeriesKind, RaceSeriesLevel

                level_raw = m.get("series_level")
                valida_label = build_race_label(
                    RaceSeriesKind(series_kind_raw),
                    int(sequence_number),
                    m.get("location"),
                    RaceSeriesLevel(level_raw) if level_raw else RaceSeriesLevel.departmental,
                )
            elif m.get("valida_num") == 0:
                valida_label = "Temporada"
        except (ValueError, TypeError):
            valida_label = None

        answer_text = m.get("coach_answer_text")

        dialogue.append(
            {
                "headline": (str(headline)[:200] if headline else None),
                "coach_question": (
                    str(coach_question)[:_COACH_QUESTION_MAX_CHARS]
                    if coach_question
                    else None
                ),
                "coach_answer_text": (
                    str(answer_text)[:_COACH_ANSWER_MAX_CHARS] if answer_text else None
                ),
                "coach_rating": m.get("coach_rating"),
                "valida_label": valida_label,
                "generated_at": (
                    m["generated_at"].isoformat()
                    if m.get("generated_at") is not None
                    else None
                ),
            }
        )

    return dialogue


__all__ = ["recall_memory", "NODE_NAME"]
