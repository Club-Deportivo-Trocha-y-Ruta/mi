"""Retriever de la capa RAG sobre marco teórico (Fase 2).

Carga la colección persistente generada por
:mod:`app.services.race.rag.indexer` y expone:

- :class:`Citation` (dataclass JSON-serializable)
- :func:`retrieve_principles(query, top_k=3) -> list[Citation]`
- CLI ``python -m app.services.race.rag.retriever query "..."``.

Decisiones de diseño
====================

- ChromaDB devuelve distancias (menor = mejor); convertimos a "score" en
  ``[0, 1]`` aproximado con ``score = 1 / (1 + distance)`` — orden estable
  y consistente con el contrato esperado por los tests (score DESC =
  mejor primero). No usamos similitud coseno cruda porque depende del
  ``hnsw:space`` configurado en la colección (default ``l2``).
- ``top_k = 0`` retorna ``[]`` sin tocar ChromaDB (corto-circuito).
- El retriever NO embeda la query localmente: pide a Chroma que lo haga
  vía ``query_embeddings=[embedder.embed_query(query)]``. Esto evita
  hacer dos roundtrips al SDK de Google.

Uso (CLI)
=========

.. code-block:: bash

    PYTHONPATH=. python -m app.services.race.rag.retriever query \\
        "ventana entrenabilidad PHV" --top-k 3

Sin ``AI_API_KEY`` el CLI falla con mensaje claro.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.services.race.rag.indexer import (
    DEFAULT_COLLECTION,
    DEFAULT_EMBEDDING_MODEL,
    _build_chroma_collection,
    _build_embedder,
    default_chroma_path,
)

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """Una cita devuelta por el retriever.

    Atributos
    ---------
    chunk_id
        Identificador determinístico (16 hex) generado en el indexer.
        Sirve para trazabilidad (``principles_cited_json`` en
        ``athlete_ai_insights``, sección 3.1 del design).
    source
        Path original del documento (ej. ``../docs/01-marco-teorico.md``).
    content
        Texto del chunk recuperado (≤ chunk_size caracteres).
    score
        Score normalizado ``[0, 1]`` (mayor = más relevante).
    metadata
        Dict con ``{doc, h1, h2, h3, chunk_idx, lines_start, lines_end}``
        para citation tracking. Siempre presente; valores faltantes son
        strings vacíos.
    """

    chunk_id: str
    source: str
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialización JSON-friendly para persistencia y API."""
        return dataclasses.asdict(self)


def _distance_to_score(distance: float) -> float:
    """Convierte distancia ChromaDB (≥0) → score (0,1] DESC = mejor."""
    if distance < 0:
        # ChromaDB con ``cosine`` puede devolver negativos por redondeo.
        distance = 0.0
    return 1.0 / (1.0 + float(distance))


def retrieve_principles(
    query: str,
    top_k: int = 3,
    chroma_path: Optional[Path] = None,
    collection_name: str = DEFAULT_COLLECTION,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    filter_h1: Optional[str] = None,
) -> list[Citation]:
    """Recupera top-k chunks relevantes para ``query``.

    Parameters
    ----------
    query
        Consulta en lenguaje natural. Si está vacía, retorna ``[]``.
    top_k
        Máximo número de resultados. ``0`` → ``[]`` sin embed.
    chroma_path
        Override del store ChromaDB. Default: env ``CHROMA_PATH`` o
        ``./data/chroma``.
    collection_name
        Override de colección. Default ``marco_teorico``.
    embedding_model
        Override del modelo de embedding. Default ``gemini-embedding-001``.
    filter_h1
        Opcional: restringe el match a chunks de un h1 específico
        (metadata ``where={"h1": filter_h1}``). Útil para queries
        focalizadas (ej. solo capítulo de nutrición).
    """
    if top_k <= 0 or not query:
        return []

    chroma_path = Path(chroma_path) if chroma_path else default_chroma_path()
    collection = _build_chroma_collection(chroma_path, collection_name)
    embedder = _build_embedder(model=embedding_model)

    query_emb = embedder.embed_query(query)
    where = {"h1": filter_h1} if filter_h1 else None

    raw = collection.query(
        query_embeddings=[query_emb],
        n_results=top_k,
        where=where,
    )

    # ChromaDB devuelve listas anidadas (1 sub-lista por query).
    ids = (raw.get("ids") or [[]])[0]
    documents = (raw.get("documents") or [[]])[0]
    metadatas = (raw.get("metadatas") or [[]])[0]
    distances = (raw.get("distances") or [[]])[0]

    out: list[Citation] = []
    for cid, content, meta, dist in zip(ids, documents, metadatas, distances):
        meta = dict(meta or {})
        source = str(meta.get("source", ""))
        out.append(
            Citation(
                chunk_id=str(cid),
                source=source,
                content=str(content or ""),
                score=_distance_to_score(float(dist)),
                metadata=meta,
            )
        )

    # ChromaDB ya devuelve por distancia ascendente (= score DESC), pero el
    # contrato es explícito → re-ordenamos defensivamente.
    out.sort(key=lambda c: c.score, reverse=True)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_cli():
    """CLI Typer: ``python -m app.services.race.rag.retriever query "..."``."""
    import typer

    app = typer.Typer(
        add_completion=False,
        help="RAG retriever — marco teórico.",
        no_args_is_help=True,
    )

    @app.callback()
    def _root() -> None:
        """RAG retriever — marco teórico (subcomando: query)."""

    @app.command("query")
    def cli_query(
        text: str = typer.Argument(..., help="Texto de la query."),
        top_k: int = typer.Option(3, "--top-k", "-k"),
        chroma_path: Optional[Path] = typer.Option(None, "--chroma-path"),
        collection: str = typer.Option(DEFAULT_COLLECTION, "--collection"),
        filter_h1: Optional[str] = typer.Option(
            None, "--filter-h1", help="Restringe match a un h1 específico."
        ),
        as_json: bool = typer.Option(
            False, "--json", help="Imprime resultado como JSON."
        ),
    ) -> None:
        """Imprime top-k citations relevantes para ``text``."""
        cites = retrieve_principles(
            query=text,
            top_k=top_k,
            chroma_path=chroma_path,
            collection_name=collection,
            filter_h1=filter_h1,
        )
        if as_json:
            typer.echo(json.dumps([c.to_dict() for c in cites], ensure_ascii=False))
            return

        if not cites:
            typer.echo("(sin resultados)")
            return
        for i, c in enumerate(cites, start=1):
            heading = " > ".join(
                p for p in (c.metadata.get("h1"), c.metadata.get("h2"), c.metadata.get("h3")) if p
            )
            typer.echo(f"[{i}] score={c.score:.4f} id={c.chunk_id}")
            if heading:
                typer.echo(f"    {heading}")
            typer.echo(f"    {c.content[:200].strip()}...")
            typer.echo("")

    return app


def main() -> None:
    """Entry point para ``python -m app.services.race.rag.retriever``."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _build_cli()()


if __name__ == "__main__":  # pragma: no cover
    main()
