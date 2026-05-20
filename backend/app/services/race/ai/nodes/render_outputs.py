"""Nodo 12: ``render_outputs`` — renderiza markdown final para el coach.

Para MVP, el ``raw_markdown`` ya está listo (el analyst lo genera en
formato markdown nativo y ``rehydrate_names`` reemplazó pseudónimos).
Este nodo solo:

1. Toma ``final_analysis.raw_markdown`` (o fallback si no hay final).
2. Asegura un header con metadata (atleta, temporada, fecha).
3. Lo guarda en ``state["rendered_markdown"]``.

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
    final = state.get("final_analysis") or state.get("draft_analysis")
    if final is None:
        md = "_(sin análisis disponible)_"
    else:
        body = (final.raw_markdown or "").strip()
        season = state.get("season", "")
        header = (
            f"# Análisis de carrera — temporada {season}\n"
            f"_Generado: {_now_str()}_\n\n"
        )
        # Si el body ya empieza con un H1, no duplicamos.
        if body.startswith("# "):
            md = body
        else:
            md = header + body

    return {"rendered_markdown": md}


__all__ = ["render_outputs", "NODE_NAME"]
