"""Tests del nodo retrieve_principles."""
from __future__ import annotations

import pytest

from app.services.race.ai.nodes import retrieve_principles as mod
from app.services.race.rag.retriever import Citation


@pytest.mark.asyncio
async def test_retrieve_principles_dedupe_and_top3(monkeypatch):
    calls = {"n": 0}
    cites_pool = {
        "ventana entrenabilidad bambino": [
            Citation(chunk_id="A", source="doc", content="...", score=0.9),
            Citation(chunk_id="B", source="doc", content="...", score=0.7),
        ],
        "carga juvenil 12 años": [
            Citation(chunk_id="B", source="doc", content="...", score=0.95),  # dup
            Citation(chunk_id="C", source="doc", content="...", score=0.6),
        ],
        "principios LTAD ciclismo de montaña": [
            Citation(chunk_id="D", source="doc", content="...", score=0.85),
        ],
    }

    def _fake_rag(query, top_k):
        calls["n"] += 1
        return cites_pool.get(query, [])

    monkeypatch.setattr(mod, "rag_retrieve", _fake_rag)
    update = await mod.retrieve_principles({})
    ids = [c.chunk_id for c in update["principles"]]
    assert len(ids) == 3
    # dedupe: B (score 0.7 — primer aparición) gana sobre B (score 0.95 — dup),
    # luego ordenamos por score: A (0.9) > D (0.85) > B (0.7).
    assert ids == ["A", "D", "B"]
    assert sorted(ids) == sorted(set(ids))


@pytest.mark.asyncio
async def test_retrieve_principles_degrades_on_exception(monkeypatch):
    def _broken(query, top_k):
        raise RuntimeError("no chroma")

    monkeypatch.setattr(mod, "rag_retrieve", _broken)
    update = await mod.retrieve_principles({})
    assert update["principles"] == []
