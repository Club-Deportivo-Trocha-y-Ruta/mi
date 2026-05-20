"""Indexer del marco teórico para la capa RAG (Fase 2).

Lee ``docs/01-marco-teorico.md``, lo chunkea respetando jerarquía markdown,
genera embeddings con ``gemini-embedding-001`` (vía
``langchain_google_genai.GoogleGenerativeAIEmbeddings``) y persiste todo en
ChromaDB local (``./data/chroma`` por default; parametrizable vía
``CHROMA_PATH``).

Decisión de diseño — splitter inline
====================================

El workflow original (``docs/10-race-results/v2-agentic-design.md`` §6.1) pide
``langchain.text_splitter.RecursiveCharacterTextSplitter``. Esa clase vive
en el paquete ``langchain-text-splitters`` que **no es** dependencia
transitiva de ``langchain-google-genai`` 4.x en este venv (verificado:
``pip list | grep langchain`` → solo ``langchain-core`` y
``langchain-google-genai``).

Para no agregar deps (regla explícita de la fase) implementamos un splitter
recursivo equivalente en este módulo (``_recursive_split``): respeta los
separadores ``["\\n## ", "\\n### ", "\\n\\n", "\\n", ". "]`` en el orden
dado y produce chunks de ``chunk_size`` caracteres con ``overlap`` de
solape — semántica idéntica a la implementación de LangChain para nuestros
documentos (markdown corto, sin tokens raros que requieran una tokenización
tipo ``tiktoken``). Si en el futuro se agrega ``langchain-text-splitters``
como dep, basta con sustituir ``_recursive_split`` por la versión oficial:
la firma pública del módulo no cambia.

Idempotencia
============

``chunk_id = sha256(source_path | chunk_idx | content)[:16]``. ``upsert``
sobre ChromaDB usa este id, así que re-correr ``reindex`` no duplica
embeddings ni gasta cuota de API de Google si el contenido no cambió.

Uso (CLI)
=========

Con ``AI_API_KEY`` válida (Google AI Studio) y dentro de ``backend/``:

.. code-block:: bash

    # Indexa docs/01-marco-teorico.md → ./data/chroma/marco_teorico
    PYTHONPATH=. python -m app.services.race.rag.indexer reindex

    # Path/colección/doc custom
    PYTHONPATH=. python -m app.services.race.rag.indexer reindex \\
        --doc ../docs/01-marco-teorico.md \\
        --chroma-path ./data/chroma_test \\
        --collection marco_teorico

Sin ``AI_API_KEY`` el reindex real falla con error claro (los tests usan
mocks — ver ``tests/services/race/rag/test_retriever.py``).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

# Defaults — todos parametrizables vía CLI o env.
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 100
DEFAULT_SEPARATORS: tuple[str, ...] = ("\n## ", "\n### ", "\n\n", "\n", ". ")
DEFAULT_COLLECTION = "marco_teorico"
DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"


def default_chroma_path() -> Path:
    """Lee ``CHROMA_PATH`` (env) o cae a ``./data/chroma`` relativo al cwd.

    Se evalúa en cada llamada para que los tests puedan monkeypatchear la
    env var sin reimportar el módulo.
    """
    return Path(os.environ.get("CHROMA_PATH", "./data/chroma"))


def default_marco_teorico_path() -> Path:
    """Ruta del marco teórico relativa al cwd ``backend/``.

    El doc vive en el repo raíz, en ``docs/01-marco-teorico.md``.
    """
    return Path("../docs/01-marco-teorico.md")


# ---------------------------------------------------------------------------
# Splitter recursivo (equivalente a langchain.text_splitter.Recursive...)
# ---------------------------------------------------------------------------


def _split_by_separator(text: str, separator: str) -> list[str]:
    """Split conservando el separador como prefijo del chunk siguiente.

    Réplica del comportamiento ``keep_separator=True`` de LangChain (que es
    el default de ``RecursiveCharacterTextSplitter``). Si el separador es
    ``""`` partimos por carácter.
    """
    if separator == "":
        return list(text)

    parts = text.split(separator)
    out: list[str] = []
    for i, part in enumerate(parts):
        if i == 0:
            if part:
                out.append(part)
        else:
            out.append(separator + part)
    return out


def _merge_splits(
    splits: Sequence[str], chunk_size: int, overlap: int
) -> list[str]:
    """Re-empaqueta fragmentos crudos en chunks de tamaño <= chunk_size.

    Aplica overlap: cada chunk arrastra los últimos ``overlap`` caracteres
    del anterior cuando se cierra y queda buffer suficiente. Mismo
    contrato que LangChain.
    """
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0

    def _flush_buffer() -> None:
        nonlocal buf, buf_len
        if not buf:
            return
        chunk = "".join(buf).strip()
        if chunk:
            chunks.append(chunk)
        # Mantén overlap: descarta desde el principio hasta que quede `overlap`.
        if overlap > 0 and chunks:
            keep = chunks[-1][-overlap:]
            buf = [keep]
            buf_len = len(keep)
        else:
            buf = []
            buf_len = 0

    for piece in splits:
        piece_len = len(piece)
        if buf_len + piece_len > chunk_size and buf:
            _flush_buffer()
        buf.append(piece)
        buf_len += piece_len

    # Flush final sin reseed de overlap (no hay siguiente chunk).
    if buf:
        chunk = "".join(buf).strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def _recursive_split(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    separators: Sequence[str] = DEFAULT_SEPARATORS,
) -> list[str]:
    """Splitter recursivo equivalente a ``RecursiveCharacterTextSplitter``.

    Aplica el primer separador que aparezca; recursa sobre los chunks que
    excedan ``chunk_size`` con el siguiente separador en la lista. Si
    ningún separador particiona suficiente, cae al split por carácter.
    """
    # Filtra separadores que existen en el texto, conservando el orden.
    if not text:
        return []

    # Elige el primer separador presente.
    chosen_sep: Optional[str] = None
    remaining_seps: list[str] = []
    for i, sep in enumerate(separators):
        if sep == "" or sep in text:
            chosen_sep = sep
            remaining_seps = list(separators[i + 1 :])
            break

    if chosen_sep is None:
        # Ningún separador presente — fallback a split por carácter.
        chosen_sep = ""
        remaining_seps = []

    raw_pieces = _split_by_separator(text, chosen_sep)

    # Re-particiona recursivamente piezas que solas ya exceden chunk_size.
    expanded: list[str] = []
    for piece in raw_pieces:
        if len(piece) > chunk_size and remaining_seps:
            expanded.extend(
                _recursive_split(piece, chunk_size, overlap, remaining_seps)
            )
        else:
            expanded.append(piece)

    # Ahora empaqueta piezas vecinas hasta chunk_size con overlap.
    return _merge_splits(expanded, chunk_size, overlap)


# ---------------------------------------------------------------------------
# Metadata por chunk (headings, líneas, source)
# ---------------------------------------------------------------------------


_H1 = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_H2 = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_H3 = re.compile(r"^###\s+(.+)$", re.MULTILINE)


@dataclass
class IndexedChunk:
    """Una unidad chunk + metadata lista para upsert en ChromaDB."""

    chunk_id: str
    content: str
    metadata: dict[str, str | int]


def _build_chunk_id(source: str, idx: int, content: str) -> str:
    """SHA256 de ``source|idx|content`` truncado a 16 hex → 64 bits."""
    raw = f"{source}|{idx}|{content}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _compute_chunk_metadata(
    chunk: str,
    full_text: str,
    source: str,
    idx: int,
) -> dict[str, str | int]:
    """Calcula metadata por chunk: heading h1/h2/h3 y rango de líneas.

    Para heading: busca el primer h1 del documento (más estable que recorrer
    cada chunk) y el h2/h3 más reciente *antes* de la primera línea del chunk
    dentro de ``full_text``.
    """
    # Localiza el chunk en el doc original para deducir headings ascendentes.
    start = full_text.find(chunk[:60]) if len(chunk) >= 60 else full_text.find(chunk)
    if start < 0:
        # No encontrado (caso raro: chunk reempaquetado de varios fragmentos
        # con overlap reseed). Fallback: marcar como "?".
        start = 0
    prefix = full_text[: max(start, 1)]

    h1_match = _H1.search(full_text)
    h1 = h1_match.group(1).strip() if h1_match else ""

    h2_matches = list(_H2.finditer(prefix))
    h2 = h2_matches[-1].group(1).strip() if h2_matches else ""

    h3_matches = list(_H3.finditer(prefix))
    h3 = h3_matches[-1].group(1).strip() if h3_matches else ""

    # Rango de líneas aproximado (1-based).
    lines_start = prefix.count("\n") + 1
    lines_end = lines_start + chunk.count("\n")

    return {
        "doc": Path(source).name,
        "source": source,
        "h1": h1,
        "h2": h2,
        "h3": h3,
        "chunk_idx": idx,
        "lines_start": lines_start,
        "lines_end": lines_end,
    }


def build_chunks(
    text: str,
    source: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    separators: Sequence[str] = DEFAULT_SEPARATORS,
) -> list[IndexedChunk]:
    """Pública: chunkea ``text`` con metadata listo para indexar.

    No requiere ChromaDB ni embeddings → ideal para tests unitarios.
    """
    raw_chunks = _recursive_split(text, chunk_size, overlap, separators)
    out: list[IndexedChunk] = []
    for idx, chunk in enumerate(raw_chunks):
        if not chunk.strip():
            continue
        chunk_id = _build_chunk_id(source, idx, chunk)
        meta = _compute_chunk_metadata(chunk, text, source, idx)
        out.append(IndexedChunk(chunk_id=chunk_id, content=chunk, metadata=meta))
    return out


# ---------------------------------------------------------------------------
# Embeddings + ChromaDB
# ---------------------------------------------------------------------------


def _build_embedder(model: str = DEFAULT_EMBEDDING_MODEL):  # pragma: no cover
    """Construye el embedder real de Google.

    Apartado en función para que los tests puedan mockear con
    ``patch("app.services.race.rag.indexer._build_embedder", ...)``. El cuerpo
    falla con mensaje claro si no hay API key.
    """
    api_key = os.environ.get("AI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "AI_API_KEY (o GOOGLE_API_KEY) no está definida. "
            "Define una key de Google AI Studio para reindex real, "
            "o mockea _build_embedder en los tests."
        )

    # Import diferido: la lib trae mucho equipaje y solo se necesita aquí.
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(model=model, google_api_key=api_key)


def _build_chroma_collection(chroma_path: Path, collection_name: str):  # pragma: no cover
    """Construye/abre la colección persistente de ChromaDB.

    Apartado para mockeo. ChromaDB crea el directorio si no existe.
    """
    chroma_path.mkdir(parents=True, exist_ok=True)

    import chromadb

    client = chromadb.PersistentClient(path=str(chroma_path))
    return client.get_or_create_collection(name=collection_name)


def reindex(
    doc_path: Optional[Path] = None,
    chroma_path: Optional[Path] = None,
    collection_name: str = DEFAULT_COLLECTION,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    separators: Sequence[str] = DEFAULT_SEPARATORS,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
) -> int:
    """Indexa ``doc_path`` en ChromaDB. Retorna número de chunks upserted.

    Idempotente: ``chunk_id`` determinístico + ``collection.upsert`` →
    re-correr con el mismo doc no duplica.
    """
    doc_path = Path(doc_path) if doc_path else default_marco_teorico_path()
    chroma_path = Path(chroma_path) if chroma_path else default_chroma_path()

    if not doc_path.exists():
        raise FileNotFoundError(f"Documento no encontrado: {doc_path}")

    text = doc_path.read_text(encoding="utf-8")
    chunks = build_chunks(
        text=text,
        source=str(doc_path),
        chunk_size=chunk_size,
        overlap=overlap,
        separators=separators,
    )
    if not chunks:
        logger.warning("Documento vacío o sin chunks: %s", doc_path)
        return 0

    embedder = _build_embedder(model=embedding_model)
    collection = _build_chroma_collection(chroma_path, collection_name)

    contents = [c.content for c in chunks]
    ids = [c.chunk_id for c in chunks]
    metadatas = [c.metadata for c in chunks]
    embeddings = embedder.embed_documents(contents)

    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=contents,
        metadatas=metadatas,
    )

    logger.info(
        "Indexed %d chunks from %s into %s (collection=%s)",
        len(chunks),
        doc_path,
        chroma_path,
        collection_name,
    )
    return len(chunks)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_cli():
    """Construye el CLI Typer. Lazy: typer es dep del proyecto, no del módulo."""
    import typer

    # invoke_without_command=False y un solo subcomando colapsan a un app
    # sin grupo en Typer; forzamos modo "multi-command" para que
    # ``python -m … reindex`` funcione como subcomando explícito.
    app = typer.Typer(
        add_completion=False,
        help="RAG indexer — marco teórico.",
        no_args_is_help=True,
    )

    # Subcomando dummy para forzar el modo multi-command (solo `reindex` real).
    @app.callback()
    def _root() -> None:
        """RAG indexer — marco teórico (subcomando: reindex)."""

    @app.command("reindex")
    def cli_reindex(
        doc: Optional[Path] = typer.Option(
            None,
            "--doc",
            help="Ruta al markdown a indexar. Default: docs/01-marco-teorico.md.",
        ),
        chroma_path: Optional[Path] = typer.Option(
            None,
            "--chroma-path",
            help="Directorio del store persistente (env CHROMA_PATH).",
        ),
        collection: str = typer.Option(
            DEFAULT_COLLECTION,
            "--collection",
            help="Nombre de colección en ChromaDB.",
        ),
        chunk_size: int = typer.Option(DEFAULT_CHUNK_SIZE, "--chunk-size"),
        overlap: int = typer.Option(DEFAULT_CHUNK_OVERLAP, "--overlap"),
    ) -> None:
        """Reindexa el doc en ChromaDB. Requiere AI_API_KEY."""
        n = reindex(
            doc_path=doc,
            chroma_path=chroma_path,
            collection_name=collection,
            chunk_size=chunk_size,
            overlap=overlap,
        )
        typer.echo(f"Indexed {n} chunks from {doc or default_marco_teorico_path()}")

    return app


def main() -> None:
    """Entry point para ``python -m app.services.race.rag.indexer``."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _build_cli()()


if __name__ == "__main__":  # pragma: no cover
    main()
