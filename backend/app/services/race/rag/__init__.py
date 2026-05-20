"""Capa RAG (Retrieval-Augmented Generation) sobre el marco teórico.

Fase 2 del workflow race-results v2 (`docs/10-race-results/v2-agentic-design.md` §6).

Módulos:

- :mod:`indexer` — chunkea ``docs/01-marco-teorico.md``, genera embeddings
  con ``gemini-embedding-001`` y persiste en ChromaDB.
- :mod:`retriever` — consulta top-k chunks relevantes para una query y
  devuelve :class:`retriever.Citation` con metadata para citation tracking.
- :mod:`tools` — wrap LangChain ``@tool`` (``consultar_marco_teorico``) que
  inyectan el retriever en los agentes (Fase 3).

Configuración por entorno:

- ``CHROMA_PATH``  — ruta del store persistente. Default ``./data/chroma``.
- ``CHROMA_COLLECTION`` — nombre de colección. Default ``marco_teorico``.
- ``AI_API_KEY`` — Google AI Studio key requerida para reindex real.
- ``AI_MODEL_EMBEDDINGS`` — modelo de embedding. Default
  ``gemini-embedding-001``.

Convenciones:
- ``chunk_id = sha256(doc_path + chunk_idx + content)[:16]`` → idempotencia.
- Los chunks llevan metadata ``{doc, source, h1, h2, h3, chunk_idx,
  lines_start, lines_end}`` para que las citas del agente apunten a la
  sección exacta del documento.
"""

__all__ = [
    "indexer",
    "retriever",
    "tools",
]
