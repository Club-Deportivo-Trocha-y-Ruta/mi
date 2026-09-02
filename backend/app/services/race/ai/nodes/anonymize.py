"""Nodo 3: ``anonymize`` — sustituye nombres reales por pseudónimos estables.

Estrategia (F4 §4.2 nodo 3):

1. Computa el ``pseudonym`` del atleta principal vía
   :func:`anonymizer.make_pseudonym`.
2. Persiste el mapping en ``anonymization_mappings`` (tabla F0) usando
   SQL crudo con ``text()`` — patrón consistente con chat.py de F3.
3. Construye ``state["anonymized_data"]`` con:
   - ``pseudonym``
   - ``raw_data`` filtrado (sin athlete_id real — solo pseudonym y
     competitor_id, que el LLM no puede mapear a nombre sin contexto).
4. Guarda ``state["mapping"]`` (pseudonym → athlete_id real) — NUNCA
   se serializa hacia el LLM.

Privacidad:
- El LLM solo ve ``pseudonym``. ``athlete_id`` viaja en el state para
  audit pero no se inyecta al prompt (ver schemas.AnalysisInput).
- El nodo final ``rehydrate_names`` revierte para mostrar al coach.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from app.services.race.ai.anonymizer import make_pseudonym
from app.services.race.ai.db import get_session
from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry

logger = logging.getLogger(__name__)

NODE_NAME = "anonymize"

_DEFAULT_SALT = "tyr-race-v2"


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def anonymize(state: dict) -> dict[str, Any]:
    athlete_id = state["athlete_id"]
    competitor_id = state.get("competitor_id")
    run_id = state.get("run_id", "no-run")

    pseudonym = make_pseudonym(athlete_id, salt=_DEFAULT_SALT)
    mapping: dict[str, int] = {pseudonym: athlete_id}

    # Persist mapping (best-effort: si falla, log warning pero el grafo
    # sigue — el pseudonym es estable por hash, así que el coach puede
    # re-mapearlo si fuera necesario).
    try:
        async with get_session() as db:
            await db.execute(
                text(
                    """
                    INSERT INTO anonymization_mappings
                        (run_id, pseudonym, real_competitor_id, real_athlete_id,
                         salt_used, created_at)
                    VALUES (
                        (SELECT id FROM agent_runs WHERE external_run_id = :rid),
                        :pseudo, :comp_id, :ath_id, :salt, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "rid": run_id,
                    "pseudo": pseudonym,
                    "comp_id": competitor_id,
                    "ath_id": athlete_id,
                    "salt": _DEFAULT_SALT,
                },
            )
    except Exception as exc:  # pragma: no cover - best-effort persist
        logger.warning(
            "anonymize: persist mapping falló (run_id=%s): %s — continuo con state-only",
            run_id,
            type(exc).__name__,
        )

    # T020 — load forbidden names once; reused for both coach_note and
    # weather_notes scrubbing.  We read from state first (populated by
    # validate_input / load_race_data upstream); if absent we fall back to an
    # empty list so the scrub still runs (notes pass through unchanged).
    forbidden_names: list[str] = list(state.get("forbidden_names") or [])

    # Anonimiza raw_data: filtra athlete_id real, pseudónimo se aplica
    # solo al atleta objetivo. competitor_id se mantiene (es un opaque ID
    # que no permite identificación sin acceso a la DB).
    raw_data = state.get("raw_data", []) or []
    anonymized_rows = []
    for row in raw_data:
        cleaned = {k: v for k, v in row.items() if k != "athlete_id"}
        # Inyectamos pseudonym SOLO en filas del atleta target — competitors
        # de podio mantienen su competitor_id opaco.
        if row.get("athlete_id") == athlete_id:
            cleaned["pseudonym"] = pseudonym
            # T020 — scrub coach_note in-place for the target athlete's rows.
            # When coach_note is absent (key not present), leave it absent —
            # no placeholder is injected (FR-009: no fabricated context).
            raw_note = cleaned.get("coach_note")
            if raw_note is not None:
                cleaned["coach_note"] = _scrub_note(raw_note, forbidden_names)
        anonymized_rows.append(cleaned)

    update: dict[str, Any] = {
        "anonymized_data": {
            "pseudonym": pseudonym,
            "rows": anonymized_rows,
        },
        "mapping": mapping,
    }

    # Scrub free-text `weather_notes` de las condiciones de carrera antes de
    # que lleguen al LLM (feature 011). Es el único campo PII-capable entre las
    # cinco condiciones; los campos estructurados (enum/numérico) no llevan PII.
    event_conditions = state.get("event_conditions")
    if event_conditions:
        scrubbed_conditions = _scrub_event_conditions(event_conditions, forbidden_names)
        update["event_conditions"] = scrubbed_conditions

    # T020/T021 — scrub {valida_num: raw_coach_note} built by load_race_data.
    # Produces {valida_num: scrubbed_note} that analyst_agent reads from state.
    # Keys with None notes are preserved so analyst_agent can detect absence
    # (FR-009: no fabricated context when note is absent).
    raw_notes_by_valida: dict[int, str | None] = state.get("coach_notes_by_valida") or {}
    if raw_notes_by_valida:
        scrubbed_notes: dict[int, str | None] = {}
        for vn, raw_note in raw_notes_by_valida.items():
            scrubbed_notes[vn] = (
                _scrub_note(raw_note, forbidden_names)
                if raw_note is not None
                else None
            )
        update["coach_notes_by_valida"] = scrubbed_notes

    # Feature 037 (T103) — scrub training_window.coach_feedback con el
    # superset club_forbidden_names (todo el club, no solo el atleta+padres):
    # el feedback de sesión puede mencionar a compañeros de equipo.
    training_window = state.get("training_window")
    if training_window and training_window.get("coach_feedback"):
        club_names = state.get("club_forbidden_names") or forbidden_names
        scrubbed_window = dict(training_window)
        scrubbed_window["coach_feedback"] = [
            _scrub_note(item, club_names) for item in training_window["coach_feedback"]
        ]
        update["training_window"] = scrubbed_window

    return update


def _scrub_note(text: str, forbidden_names: list[str]) -> str:
    """Elimina nombres reales de un campo de texto libre usando los guardrails v2.

    Reutiliza ``build_race_v2_forbidden_names_rules`` — la misma lógica que
    aplica ``_scrub_event_conditions`` al campo ``weather_notes``. Cuando no
    hay nombres prohibidos, el texto pasa sin cambios.

    Privacidad: NUNCA registrar el contenido del texto en logs.
    """
    if not text or not forbidden_names:
        return text
    from app.services.ai.guardrails import build_race_v2_forbidden_names_rules

    scrubbed = text
    for rule in build_race_v2_forbidden_names_rules(forbidden_names):
        scrubbed = rule.pattern.sub(rule.replacement or "", scrubbed)
    return scrubbed


def _scrub_event_conditions(
    event_conditions: dict[int, dict[str, Any]],
    forbidden_names: list[str],
) -> dict[int, dict[str, Any]]:
    """Devuelve una copia de ``event_conditions`` con ``weather_notes`` saneado.

    Reusa las reglas dinámicas de nombres prohibidos de los guardrails v2
    (``build_race_v2_forbidden_names_rules``). Si no hay nombres prohibidos,
    las notas pasan sin cambios.
    """
    from app.services.ai.guardrails import build_race_v2_forbidden_names_rules

    rules = build_race_v2_forbidden_names_rules(forbidden_names) if forbidden_names else ()
    out: dict[int, dict[str, Any]] = {}
    for valida_num, cond in event_conditions.items():
        new_cond = dict(cond)
        notes = new_cond.get("weather_notes")
        if notes and rules:
            for rule in rules:
                notes = rule.pattern.sub(rule.replacement or "", notes)
            new_cond["weather_notes"] = notes
        out[valida_num] = new_cond
    return out


__all__ = ["anonymize", "NODE_NAME"]
