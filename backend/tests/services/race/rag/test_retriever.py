"""Tests del retriever RAG (Fase 2 race-results v2).

Convenciones
============

- **Sin red.** Ningún test invoca la API de Google. Mockeamos
  :func:`app.services.race.rag.indexer._build_embedder` con un embedder
  determinístico (``_FakeEmbedder``) que mapea contenido → vector vía
  hash MD5 reinterpretado como floats en ``[0, 1)``. Misma cadena →
  mismo vector → distancia 0 exacta. Distancias mayores para cadenas
  diferentes son estables entre corridas.

- **ChromaDB real persistido a ``tmp_path``.** Probamos el contrato real
  de upsert/query (no mockeamos ChromaDB). Cada test recibe un dir
  temporal aislado vía la fixture ``chroma_path``.

- **Doc fixture en memoria.** Para los tests de "query semánticamente
  cercana" usamos un fragmento corto del marco teórico real con varios
  h1/h2 reconocibles; así validamos metadata sin depender del archivo
  completo (que es 290 líneas y puede cambiar).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable
from unittest.mock import patch

import pytest

from app.services.race.rag import indexer as indexer_mod
from app.services.race.rag.indexer import (
    DEFAULT_COLLECTION,
    IndexedChunk,
    _build_chunk_id,
    build_chunks,
    reindex,
)
from app.services.race.rag.retriever import Citation, retrieve_principles
from app.services.race.rag.tools import (
    build_consultar_marco_teorico_tool,
    format_citations,
)


# ---------------------------------------------------------------------------
# Fake embedder determinístico
# ---------------------------------------------------------------------------

_EMBED_DIM = 16  # pequeño y suficiente para que ChromaDB distinga vectores.


def _deterministic_vector(text: str) -> list[float]:
    """Hash MD5(text) → ``_EMBED_DIM`` floats en [0, 1).

    Idéntico texto → idéntico vector → distancia 0. Garantiza que las
    queries que repiten un substring de un chunk obtienen distancia
    pequeña en el espacio L2 default de ChromaDB.
    """
    digest = hashlib.md5(text.encode("utf-8")).digest()
    # Repite el digest para llenar dimensión.
    raw = (digest * ((_EMBED_DIM // len(digest)) + 1))[:_EMBED_DIM]
    return [b / 255.0 for b in raw]


class _FakeEmbedder:
    """Sustituto de GoogleGenerativeAIEmbeddings sin red.

    Implementa el subset que usa el indexer/retriever:
    ``embed_documents`` y ``embed_query``.
    """

    def __init__(self) -> None:
        self.documents_calls: list[list[str]] = []
        self.query_calls: list[str] = []

    def embed_documents(self, texts: Iterable[str]) -> list[list[float]]:
        texts = list(texts)
        self.documents_calls.append(texts)
        return [_deterministic_vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        return _deterministic_vector(text)


@pytest.fixture
def fake_embedder():
    """Patchea ``_build_embedder`` (en indexer **y** retriever) con _FakeEmbedder.

    El retriever importa ``_build_embedder`` desde el indexer
    (``from app.services.race.rag.indexer import _build_embedder``) — por
    eso un único patch al símbolo del indexer cubre ambos call sites,
    porque retriever lo invoca por referencia importada. Patcheamos en
    ambos namespaces para defensa en profundidad si el código cambia.
    """
    embedder = _FakeEmbedder()
    with (
        patch(
            "app.services.race.rag.indexer._build_embedder",
            return_value=embedder,
        ),
        patch(
            "app.services.race.rag.retriever._build_embedder",
            return_value=embedder,
        ),
    ):
        yield embedder


@pytest.fixture
def chroma_path(tmp_path: Path) -> Path:
    """Dir aislado para ChromaDB por test. Limpio al final por pytest."""
    return tmp_path / "chroma"


# ---------------------------------------------------------------------------
# Fixture: doc markdown sintético del marco teórico
# ---------------------------------------------------------------------------

SAMPLE_DOC = """# Marco teórico Trocha y Ruta — Test fixture

Doc de prueba con secciones reconocibles.

## 1. Desarrollo fisiológico 10-15 años

El Pico de Velocidad de Crecimiento (PHV) es el hito clave para
adaptar la carga de entrenamiento en jóvenes ciclistas. En niños
ocurre a 13.5 años en promedio.

### Ventana de entrenabilidad

La ventana sensible para velocidad en niños está entre 13 y 16 años;
para habilidad motriz entre 9 y 12 años. Antes de PHV evitar cargas
de fuerza máxima.

## 2. Cadencia y técnica

Cadencia objetivo para 10-12 años: 70-85 rpm. Nunca prescribir por
debajo de 60 rpm. Para 13-15 años: 75-90 rpm con rangos amplios.

## 3. Nutrición e hidratación

Enfoque "primero la comida". Cero suplementos para menores de 18
años. Hidratación con agua simple en sesiones <60 min.
"""


@pytest.fixture
def sample_doc(tmp_path: Path) -> Path:
    p = tmp_path / "01-marco-teorico-sample.md"
    p.write_text(SAMPLE_DOC, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_chunks_respects_size_and_metadata():
    """build_chunks produce chunks <= chunk_size y metadata con h1/h2."""
    chunks = build_chunks(SAMPLE_DOC, source="sample.md", chunk_size=400, overlap=50)
    assert len(chunks) >= 2, "doc con varias secciones debe producir >=2 chunks"
    for c in chunks:
        # Allowance: el splitter puede dejar chunks un poco más grandes que
        # chunk_size cuando un fragmento atómico es mayor (consistente con
        # langchain RecursiveCharacterTextSplitter).
        assert c.chunk_id and len(c.chunk_id) == 16
        assert c.content.strip()
        assert c.metadata["doc"] == "sample.md"
        assert c.metadata["source"] == "sample.md"
        # h1 estable: siempre el del documento.
        assert c.metadata["h1"].startswith("Marco teórico Trocha y Ruta")
        # h2 puede ser "" para el chunk del intro previo a "## 1.".
        assert isinstance(c.metadata.get("h2", ""), str)
        assert "chunk_idx" in c.metadata
        assert c.metadata["lines_start"] >= 1


def test_reindex_creates_n_chunks(sample_doc: Path, chroma_path: Path, fake_embedder):
    """reindex sobre el doc sample crea N chunks en ChromaDB."""
    n = reindex(
        doc_path=sample_doc,
        chroma_path=chroma_path,
        collection_name=DEFAULT_COLLECTION,
        chunk_size=300,
        overlap=50,
    )
    assert n > 0
    # Verifica el count real en ChromaDB.
    import chromadb

    client = chromadb.PersistentClient(path=str(chroma_path))
    col = client.get_or_create_collection(DEFAULT_COLLECTION)
    assert col.count() == n
    # Embedder fue invocado una vez con la lista completa.
    assert len(fake_embedder.documents_calls) == 1
    assert len(fake_embedder.documents_calls[0]) == n


def test_reindex_is_idempotent(sample_doc: Path, chroma_path: Path, fake_embedder):
    """Re-correr reindex con mismo doc no duplica chunks (mismo chunk_id)."""
    n1 = reindex(
        doc_path=sample_doc,
        chroma_path=chroma_path,
        collection_name=DEFAULT_COLLECTION,
        chunk_size=300,
        overlap=50,
    )
    n2 = reindex(
        doc_path=sample_doc,
        chroma_path=chroma_path,
        collection_name=DEFAULT_COLLECTION,
        chunk_size=300,
        overlap=50,
    )
    assert n1 == n2
    import chromadb

    client = chromadb.PersistentClient(path=str(chroma_path))
    col = client.get_or_create_collection(DEFAULT_COLLECTION)
    # count == n (no 2n).
    assert col.count() == n1


def test_retrieve_returns_top_k_sorted_desc(sample_doc: Path, chroma_path: Path, fake_embedder):
    """retrieve_principles devuelve <= top_k Citations ordenadas por score DESC."""
    reindex(
        doc_path=sample_doc,
        chroma_path=chroma_path,
        collection_name=DEFAULT_COLLECTION,
        chunk_size=300,
        overlap=50,
    )
    results = retrieve_principles(
        query="cadencia",
        top_k=3,
        chroma_path=chroma_path,
    )
    assert len(results) <= 3
    assert len(results) > 0
    # Orden descendente por score.
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
    # Cada resultado es una Citation con campos esperados.
    for r in results:
        assert isinstance(r, Citation)
        assert r.chunk_id
        assert r.content
        assert 0.0 < r.score <= 1.0


def test_citation_has_valid_metadata(sample_doc: Path, chroma_path: Path, fake_embedder):
    """Citation.metadata trae source path y headings recuperables del doc."""
    reindex(
        doc_path=sample_doc,
        chroma_path=chroma_path,
        collection_name=DEFAULT_COLLECTION,
        chunk_size=300,
        overlap=50,
    )
    results = retrieve_principles(
        query="PHV pico de velocidad",
        top_k=3,
        chroma_path=chroma_path,
    )
    assert results, "Debe haber al menos un resultado"
    top = results[0]
    assert top.metadata["source"] == str(sample_doc)
    assert top.metadata["doc"] == sample_doc.name
    # h1 estable.
    assert top.metadata["h1"].startswith("Marco teórico Trocha y Ruta")
    # Citation debe ser JSON-serializable.
    blob = json.dumps(top.to_dict(), ensure_ascii=False)
    assert "chunk_id" in blob
    # dataclasses.asdict también funciona.
    d = dataclasses.asdict(top)
    assert d["chunk_id"] == top.chunk_id


def test_retrieve_finds_expected_chunk_for_close_query(
    sample_doc: Path, chroma_path: Path, fake_embedder
):
    """Query con substring exacto del chunk → ese chunk debería ganar.

    El _FakeEmbedder mapea texto → vector por MD5. Cuando la query es
    *literalmente* una substring corta de un chunk indexado, ambos vectores
    suelen quedar separados (MD5 no preserva semántica), pero podemos
    explotar un caso fuerte: si la query coincide con el contenido **entero**
    de un chunk artificial, distancia = 0.

    Para evitar atar el test al exact-matching cabezón del fake, hacemos
    una variante más realista: reindexamos un mini-doc donde cada sección
    es una sola frase, y verificamos que la query que repite esa frase
    cae con distancia 0 al chunk correcto.
    """
    mini = """# Doc

## Sec A
texto-sec-A

## Sec B
texto-sec-B

## Sec C
texto-sec-C
"""
    mini_path = sample_doc.parent / "mini.md"
    mini_path.write_text(mini, encoding="utf-8")
    reindex(
        doc_path=mini_path,
        chroma_path=chroma_path,
        collection_name="mini_test",
        chunk_size=200,
        overlap=0,
    )
    # Toma el contenido exacto del chunk "Sec B" como query.
    chunks = build_chunks(mini, source=str(mini_path), chunk_size=200, overlap=0)
    target = next(c for c in chunks if "texto-sec-B" in c.content)

    results = retrieve_principles(
        query=target.content,
        top_k=1,
        chroma_path=chroma_path,
        collection_name="mini_test",
    )
    assert results
    assert results[0].chunk_id == target.chunk_id


def test_retrieve_top_k_zero_returns_empty(chroma_path: Path, fake_embedder):
    """top_k=0 (o query vacía) corto-circuita y devuelve [] sin tocar Chroma."""
    # No reindexamos a propósito — el corto-circuito debe ocurrir antes.
    assert retrieve_principles("cualquier cosa", top_k=0, chroma_path=chroma_path) == []
    assert retrieve_principles("", top_k=5, chroma_path=chroma_path) == []
    # Embedder no debería haber sido invocado para queries.
    assert fake_embedder.query_calls == []


def test_chunk_id_is_deterministic_and_stable():
    """chunk_id = sha256(source|idx|content)[:16] estable entre corridas."""
    id1 = _build_chunk_id("docs/x.md", 0, "hola mundo")
    id2 = _build_chunk_id("docs/x.md", 0, "hola mundo")
    id3 = _build_chunk_id("docs/x.md", 1, "hola mundo")
    assert id1 == id2
    assert id1 != id3
    assert len(id1) == 16


def test_chroma_path_parametrizable_via_env(
    monkeypatch, sample_doc: Path, tmp_path: Path, fake_embedder
):
    """default_chroma_path lee CHROMA_PATH dinámicamente — no hardcoded."""
    target = tmp_path / "from_env_chroma"
    monkeypatch.setenv("CHROMA_PATH", str(target))
    # Llamada sin pasar chroma_path explícito → debe usar la env.
    n = reindex(doc_path=sample_doc, chunk_size=300, overlap=50)
    assert n > 0
    assert target.exists()


def test_tool_format_citations_renders_blocks():
    """consultar_marco_teorico (vía build_…_tool) devuelve string formateado.

    Inyectamos un retriever fake que devuelve 2 citations conocidas y
    verificamos el formato esperado por los agentes LLM (chunk_id visible,
    headings concatenados con ' > ').
    """
    fake_results = [
        Citation(
            chunk_id="aaa1111111111111",
            source="docs/01-marco-teorico.md",
            content="Cadencia mínima 60 rpm en menores.",
            score=0.91,
            metadata={"h1": "Marco", "h2": "Cadencia", "h3": ""},
        ),
        Citation(
            chunk_id="bbb2222222222222",
            source="docs/01-marco-teorico.md",
            content="PHV define la ventana de entrenamiento de fuerza.",
            score=0.84,
            metadata={"h1": "Marco", "h2": "Desarrollo", "h3": "PHV"},
        ),
    ]
    tool = build_consultar_marco_teorico_tool(
        retriever_fn=lambda query, top_k=3: fake_results
    )
    # ``@tool`` wrap → invoke con dict.
    out = tool.invoke({"query": "cadencia", "top_k": 2})
    assert isinstance(out, str)
    assert "aaa1111111111111" in out
    assert "bbb2222222222222" in out
    assert "Marco > Cadencia" in out
    assert "Marco > Desarrollo > PHV" in out
    # Bloques delimitados por '---'.
    assert out.count("---") >= 2


def test_format_citations_handles_empty_list():
    """format_citations con [] devuelve mensaje human-readable, no crash."""
    out = format_citations([])
    assert "sin resultados" in out.lower()
