"""Nodo 12: ``render_outputs`` — renderiza markdown final para el coach.

Para MVP, el ``raw_markdown`` ya está listo (el analyst lo genera en
formato markdown nativo y ``rehydrate_names`` reemplazó pseudónimos).
Este nodo:

1. Toma ``final_analysis.raw_markdown`` (o fallback ``draft_analysis``).
2. Si ``no_data_for_season=True`` y ya hay ``rendered_markdown`` (poblado
   por ``validate_input``), lo respeta tal cual.
3. Si no hay análisis y NO viene de ``no_data_for_season`` → marca el run
   como ``failed`` y agrega un error explícito. Sin contenido es bug.
4. En caso normal, asegura un header con metadata y guarda el markdown.

PDF / export se generan en F5 al request del endpoint, no aquí.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry

NODE_NAME = "render_outputs"


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@with_events(NODE_NAME)
@with_retry(max_attempts=1, backoff=0)
async def render_outputs(state: dict) -> dict[str, Any]:
    if state.get("no_data_for_season"):
        existing = state.get("rendered_markdown")
        if existing:
            return {"rendered_markdown": existing}
        season = state.get("season", "")
        md = (
            f"# Análisis de carrera — temporada {season}\n\n"
            f"_Sin carreras registradas para temporada {season}._\n"
        )
        return {"rendered_markdown": md, "status": "no_data"}

    final = state.get("final_analysis") or state.get("draft_analysis")
    if final is None:
        prior_errors = list(state.get("errors") or [])
        prior_errors.append(
            {
                "node": NODE_NAME,
                "error": "EmptyRender",
                "message": "Render sin contenido — analista no produjo output",
            }
        )
        return {
            "status": "failed",
            "errors": prior_errors,
            "rendered_markdown": "_(sin análisis disponible)_",
        }

    body = (final.raw_markdown or "").strip()
    if not body:
        prior_errors = list(state.get("errors") or [])
        prior_errors.append(
            {
                "node": NODE_NAME,
                "error": "EmptyRender",
                "message": "Render sin contenido — analista no produjo output",
            }
        )
        return {
            "status": "failed",
            "errors": prior_errors,
            "rendered_markdown": "_(sin análisis disponible)_",
        }

    season = state.get("season", "")
    header = (
        f"# Análisis de carrera — temporada {season}\n"
        f"_Generado: {_now_str()}_\n\n"
    )
    if body.startswith("# "):
        md = body
    else:
        md = header + body

    return {"rendered_markdown": md}


__all__ = ["render_outputs", "NODE_NAME"]
