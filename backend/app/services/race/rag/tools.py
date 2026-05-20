"""LangChain tools que exponen la capa RAG a los agentes (Fase 2 → Fase 3).

El ``analyst_agent`` (Fase 3) registrará ``consultar_marco_teorico`` en su
toolset; el LLM decide cuándo invocarlo y con qué query. El tool retorna
**texto formateado** (no Python objects) porque ese es el contrato esperado
por LangChain Agents — y porque los modelos LLM citan mejor cuando ven
las secciones como bloques de texto delimitados.

Decisión de diseño — inyección del retriever
============================================

LangChain ``@tool`` decora funciones puras. Para mantener la posibilidad
de testear con un retriever fake (sin tocar ChromaDB ni la API de Google)
exponemos dos formas:

1. :func:`build_consultar_marco_teorico_tool(retriever_fn)` — fábrica que
   toma un callable con la firma de :func:`retrieve_principles` y retorna
   el tool decorado. Esto es lo que usan los tests.
2. :data:`consultar_marco_teorico` — instancia default ya enlazada al
   retriever real. Listo para registrar en el agente en Fase 3.

Formato de salida
-----------------

El tool serializa cada cita como un bloque markdown:

::

    [1] <h1 > h2 > h3>   (chunk_id=ab12..., score=0.84)
    <contenido>
    ---

Razón: el LLM puede citar con ``[1]`` en su respuesta, y el coach front-end
mapea ese ``[1]`` al ``chunk_id`` real (persistido en
``principles_cited_json``).
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional

from app.services.race.rag.retriever import Citation, retrieve_principles

# Type alias del callable: (query, top_k) → lista de Citation.
RetrieverFn = Callable[..., list[Citation]]


def format_citations(cites: Iterable[Citation]) -> str:
    """Convierte una lista de citations a string formateado para el LLM.

    Mantén el orden recibido (ya viene por score DESC desde el retriever).
    """
    cites = list(cites)
    if not cites:
        return "(sin resultados en el marco teórico para esa query)"

    out: list[str] = []
    for i, c in enumerate(cites, start=1):
        heading_parts = [
            str(c.metadata.get(k, "")).strip()
            for k in ("h1", "h2", "h3")
        ]
        heading = " > ".join(p for p in heading_parts if p)
        header = f"[{i}] {heading}   (chunk_id={c.chunk_id}, score={c.score:.3f})"
        out.append(header)
        out.append(c.content.strip())
        out.append("---")
    return "\n".join(out).strip()


def build_consultar_marco_teorico_tool(
    retriever_fn: Optional[RetrieverFn] = None,
):
    """Fábrica del tool LangChain ``consultar_marco_teorico``.

    Parameters
    ----------
    retriever_fn
        Callable con la misma firma que :func:`retrieve_principles`. Si
        es ``None`` usa el retriever real (ChromaDB + Gemini embeddings).
        Inyectable para tests sin red.
    """
    from langchain_core.tools import tool

    fn = retriever_fn or retrieve_principles

    @tool("consultar_marco_teorico")
    def consultar_marco_teorico(query: str, top_k: int = 3) -> str:
        """Consulta el marco teórico-metodológico del club.

        Úsalo cuando necesites fundamentar una recomendación de
        entrenamiento, periodización o nutrición de ciclistas juveniles
        (10-15 años) en evidencia documental del club Trocha y Ruta.

        Parameters
        ----------
        query
            Pregunta o concepto en lenguaje natural (español).
            Ej.: "ventana entrenabilidad PHV", "cadencia mínima 10-12 años".
        top_k
            Número de citas a recuperar (default 3, max recomendado 5).

        Returns
        -------
        str
            Bloques formateados ``[1]/[2]/...`` con heading + contenido +
            chunk_id, listos para citar en la respuesta.
        """
        cites = fn(query=query, top_k=top_k)
        return format_citations(cites)

    return consultar_marco_teorico


# Instancia default — enlazada al retriever real. Importable directamente
# por el agente de Fase 3:  from app.services.race.rag.tools import consultar_marco_teorico
consultar_marco_teorico = build_consultar_marco_teorico_tool()


__all__ = [
    "Citation",
    "RetrieverFn",
    "build_consultar_marco_teorico_tool",
    "consultar_marco_teorico",
    "format_citations",
]
