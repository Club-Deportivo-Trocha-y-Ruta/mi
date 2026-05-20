"""Nodo 5: ``retrieve_principles`` — RAG sobre marco teórico.

Deriva 2-3 queries del contexto del atleta (edad, ltad_group) y llama
:func:`rag.retriever.retrieve_principles` para cada una. Dedupe por
``chunk_id`` y retorna top-3 por score combinado.

Edad / ltad_group derivado:
- Para MVP: no recuperamos edad real de la DB en este nodo (sería
  otra query). Asumimos que F5 lo inyecta vía ``state["athlete_age"]``
  y ``state["ltad_group"]`` (TODO F5). Si no están: usa queries
  genéricas que aún devuelven contenido útil del marco teórico.
"""

from __future__ import annotations

from typing import Any

from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry
from app.services.race.rag.retriever import Citation, retrieve_principles as rag_retrieve

NODE_NAME = "retrieve_principles"


def _build_queries(state: dict) -> list[str]:
    """Construye 2-3 queries diversificadas del contexto del atleta."""
    ltad = state.get("ltad_group", "bambino")
    age = state.get("athlete_age", 12)
    return [
        f"ventana entrenabilidad {ltad}",
        f"carga juvenil {age} años",
        "principios LTAD ciclismo de montaña",
    ]


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def retrieve_principles(state: dict) -> dict[str, Any]:
    queries = _build_queries(state)

    all_citations: list[Citation] = []
    seen: set[str] = set()

    for q in queries:
        try:
            cites = rag_retrieve(query=q, top_k=3)
        except Exception:
            # Si el retriever no está configurado (sin AI_API_KEY en CI),
            # degradamos silenciosamente — el analyst opera sin RAG.
            cites = []
        for c in cites:
            if c.chunk_id not in seen:
                seen.add(c.chunk_id)
                all_citations.append(c)

    # Top-3 global por score (chunks de varias queries fusionados).
    all_citations.sort(key=lambda c: c.score, reverse=True)
    top3 = all_citations[:3]

    return {"principles": top3}


__all__ = ["retrieve_principles", "NODE_NAME"]
