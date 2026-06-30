"""Render service for the per-session printable sheet (feature 019, T023).

Provides :func:`render_training_session_sheet` — loads a ``TrainingSession``
with its ``TechniqueSessionExercise`` rows and associated ``TechniqueExercise``
catalog entries (including ``layout_json``), then renders the Jinja2 template
``documents/pdf/training_session_sheet.html`` and returns the HTML string.

Design notes:
- No HTTP endpoint is added here. The sheet is a pure service function that
  callers (routers, background tasks, tests) can invoke directly.  An endpoint
  can be wired separately once the frontend needs it.
- The function uses the same Jinja2 ``Environment`` / ``FileSystemLoader``
  pattern as ``DocumentGenerator``.  It does NOT re-use ``DocumentGenerator``
  itself to avoid coupling to the notification pipeline (TemplateRegistry,
  DocumentRequest schema, etc.) — this sheet is a lightweight one-off render.
- All DB operations are async (``AsyncSession``).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

_TEMPLATES_ROOT = Path(__file__).parents[3] / "templates"
_BOGOTA_TZ = ZoneInfo("America/Bogota")

# Segment display labels (español neutro — FR-020)
_SEGMENT_LABELS: dict[str, str] = {
    "calentamiento": "Calentamiento",
    "principal": "Parte principal",
    "vuelta_calma": "Vuelta a la calma",
}


def _build_jinja_env():
    """Return a Jinja2 Environment with the same settings as DocumentGenerator."""
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_ROOT)),
        autoescape=select_autoescape(["html"]),
    )


async def render_training_session_sheet(
    session_id: int,
    db: AsyncSession,
    *,
    club_name: str = "Trocha y Ruta",
) -> str:
    """Render the per-session printable sheet as an HTML string.

    Loads ``TrainingSession`` by primary key, eager-loads
    ``technique_exercises → exercise`` (including ``layout_json``), then
    renders ``documents/pdf/training_session_sheet.html`` with the collected
    data.

    Args:
        session_id: Primary key of the ``TrainingSession`` to render.
        db: Active ``AsyncSession``.  Read-only — no writes.
        club_name: Club display name injected into the template header.

    Returns:
        Rendered HTML string (UTF-8).

    Raises:
        ValueError: When ``session_id`` does not exist in the database.
    """
    from app.models.technique_exercise import TechniqueSessionExercise
    from app.models.training_session import TrainingSession

    # ── 1. Load session + technique exercises eagerly ───────────────────────
    result = await db.execute(
        select(TrainingSession)
        .where(TrainingSession.id == session_id)
        .options(
            selectinload(TrainingSession.technique_exercises).selectinload(
                TechniqueSessionExercise.exercise
            )
        )
    )
    ts = result.scalar_one_or_none()
    if ts is None:
        raise ValueError(f"Sesión {session_id} no encontrada.")

    # ── 2. Build context ─────────────────────────────────────────────────────
    session_ctx = {
        "technical_focus": ts.technical_focus,
        "scheduled_date": ts.scheduled_date,
        "objectives": ts.objectives,
        "session_kind": ts.session_kind.value if ts.session_kind else "entrenamiento",
        "duration_min": ts.duration_min,
        "location": ts.location,
    }

    # Sort by (segment enum value order, position) — matches the assembler convention.
    _SEGMENT_ORDER = {"calentamiento": 0, "principal": 1, "vuelta_calma": 2}
    sorted_items = sorted(
        ts.technique_exercises,
        key=lambda e: (_SEGMENT_ORDER.get(e.segment.value, 99), e.position),
    )

    exercise_list = []
    for tse in sorted_items:
        ex = tse.exercise
        exercise_list.append(
            {
                "segment": tse.segment.value,
                "position": tse.position,
                "name": ex.name,
                "how_to": ex.how_to,
                "is_gymkhana": ex.is_gymkhana,
                "layout_json": ex.layout_json,
                "layout_ascii": ex.layout_ascii,
                "layout_alt": ex.layout_alt,
            }
        )

    generated_at = datetime.now(_BOGOTA_TZ).strftime("%Y-%m-%d %H:%M COT")

    # ── 3. Render template ───────────────────────────────────────────────────
    jinja = _build_jinja_env()
    template = jinja.get_template("documents/pdf/training_session_sheet.html")
    html = template.render(
        session=session_ctx,
        exercises=exercise_list,
        club_name=club_name,
        generated_at=generated_at,
    )

    logger.info(
        "training_session_sheet rendered | session_id=%d exercises=%d bytes=%d",
        session_id,
        len(exercise_list),
        len(html),
    )
    return html
