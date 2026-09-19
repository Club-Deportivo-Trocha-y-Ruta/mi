"""Fixtures compartidas para tests del módulo ``app.services.race.ai``.

Pieza clave: :class:`FakeSession` mínima que emula los métodos usados
por nodos (``execute`` para SQL crudo ``text(...)`` y por las queries
ORM). Para tests del grafo, además se monta un ``set_db_factory`` que
retorna un :class:`FakeAsyncSession` reutilizable.

Convención: tests acá NO tocan DB real ni Gemini real. Todo mock.
"""
from __future__ import annotations

from typing import Any, Iterable

import pytest
import pytest_asyncio

from app.services.race.ai.db import set_db_factory


# ---------------------------------------------------------------------------
# Fake DB session (SQL text() + ORM queries)
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows: list[Any]):
        self._rows = list(rows)

    def fetchall(self) -> list[Any]:
        return list(self._rows)

    def all(self) -> list[Any]:
        return list(self._rows)

    def scalars(self) -> "_FakeResult":
        return self

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> Any:
        return self._rows[0] if self._rows else 0


class FakeSession:
    """Sesión async mínima para tests de nodos.

    - ``execute(stmt, params)`` busca un response pre-cargado por
      string-match del SQL o por nombre del statement (test-driven).
    - ``add(obj)`` / ``flush()`` / ``commit()`` son no-op.
    - Para tests del nodo ``recall_memory`` etc, el test puede cargar
      ``self.row_responses["SELECT summary_text"] = [Row1, Row2]`` antes
      de invocar.
    """

    def __init__(self) -> None:
        self.row_responses: dict[str, list[Any]] = {}
        self.executed_statements: list[tuple[str, dict]] = []
        self._ext_results: list[Any] = []
        self.added_objects: list[Any] = []

    async def execute(self, stmt: Any, params: dict | None = None) -> _FakeResult:
        sql_text = getattr(stmt, "text", None)
        if sql_text is None:
            sql_text = str(stmt)
        params = params or {}
        self.executed_statements.append((sql_text, params))

        # Match por substring (más laxo y robusto a formatting cambios).
        for key, rows in self.row_responses.items():
            if key in sql_text:
                return _FakeResult(rows)
        if self._ext_results:
            return _FakeResult(self._ext_results)
        # ORM-style queries (select(Model)) — devolvemos vacío.
        return _FakeResult([])

    async def commit(self) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    def add(self, obj: Any) -> None:
        self.added_objects.append(obj)

    def seed_competitor(self, competitor_id: int, *, athlete_id: int | None) -> None:
        """Registra un ``RaceCompetitor`` para el candado de terceros.

        Feature 044 (FR-012…FR-015): los nodos que reciben un
        ``competitor_id`` pasan primero por
        ``third_party_guard.require_club_competitor``, que ejecuta
        ``select(RaceCompetitor).where(id == competitor_id)``. Sin esta fila
        el fake devuelve vacío y el candado rechaza con
        ``reason="unknown_competitor"`` — que es el comportamiento correcto,
        así que los tests que ejercitan el camino feliz deben declarar
        explícitamente que su competidor es del club.

        Se seedea a propósito por test y NO por defecto en la fixture
        ``fake_session``: un default silencioso volvería a hacer invisible el
        candado, que es justo lo que la feature quiere evitar.

        Args:
            competitor_id: PK del competidor a registrar.
            athlete_id: ``None`` → tercero sin vincular (el candado rechaza
                con ``not_linked``); un int → competidor del club.

        Nombres sintéticos evidentemente ficticios — nunca un dato real de un
        menor (CLAUDE.md, Ley 1581).
        """
        from app.models.race_competitor import RaceCompetitor

        linked = athlete_id is not None
        display_name = (
            "Deportista Club Ficticio" if linked else "Tercero Ajeno Ficticio"
        )
        self.row_responses["FROM race_competitors"] = [
            RaceCompetitor(
                id=competitor_id,
                normalized_name=display_name.lower(),
                display_name=display_name,
                club_text="Club Trocha y Ruta" if linked else "Club Externo Ficticio",
                athlete_id=athlete_id,
            )
        ]

    def link_competitor(self, competitor_id: int, athlete_id: int = 4242) -> None:
        """Azúcar de :meth:`seed_competitor` para el caso "competidor del club"."""
        self.seed_competitor(competitor_id, athlete_id=athlete_id)


@pytest_asyncio.fixture
async def fake_session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def configure_db_factory():
    """Helper para inyectar un db_factory con la session pasada.

    Yields la session usada, garantiza limpieza al final.
    """
    sessions: list[FakeSession] = []

    def _setup(session: FakeSession) -> None:
        sessions.append(session)
        set_db_factory(lambda: session)

    yield _setup
    set_db_factory(None)


# ---------------------------------------------------------------------------
# Checkpointer in-memory para tests del grafo
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def memory_checkpointer():
    """AsyncSqliteSaver con conexión in-memory para tests del grafo.

    LangGraph 1.2 requiere saver async cuando el grafo se ejecuta vía
    ``ainvoke``. Cerramos el conn al final del test para evitar warnings.
    """
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    conn = await aiosqlite.connect(":memory:")
    saver = AsyncSqliteSaver(conn)
    await saver.setup()
    yield saver
    await conn.close()


# ---------------------------------------------------------------------------
# Fake AnalysisOutput / FakeAgents
# ---------------------------------------------------------------------------


from app.services.race.schemas import (  # noqa: E402
    AnalysisOutput,
    CriticFeedback,
    CriticIssueSeverity,
    RunMetrics,
)


def make_analysis_output(
    pseudonym: str = "AzulZorro",
    markdown: str = "## Evolución\nProgreso constante.\n## Recomendaciones\n- Más fuerza.",
) -> AnalysisOutput:
    return AnalysisOutput(
        pseudonym=pseudonym,
        sections={"evolution": "Progreso constante.", "recommendations": "Más fuerza."},
        citations_used=[],
        recommendations=[],
        risk_flags=[],
        raw_markdown=markdown,
        word_count=len(markdown.split()),
    )


def make_zero_metrics(prompt_version: str = "race_analyst_v1") -> RunMetrics:
    return RunMetrics(
        tokens_in=10,
        tokens_out=20,
        latency_ms=5,
        cost_usd=0.0001,
        prompt_version=prompt_version,
    )


def make_critic_feedback(approved: bool = True, must_block: bool = False) -> CriticFeedback:
    return CriticFeedback(
        approved=approved,
        severity=CriticIssueSeverity.LOW,
        issues=[],
        must_block=must_block,
    )


class FakeAnalystAgent:
    def __init__(self, output: AnalysisOutput | None = None, raises: Exception | None = None):
        self._output = output or make_analysis_output()
        self._raises = raises

    async def invoke(self, input_):
        if self._raises:
            raise self._raises
        return self._output, make_zero_metrics("race_analyst_v1")


class FakeCriticAgent:
    def __init__(self, feedback: CriticFeedback | None = None):
        self._fb = feedback or make_critic_feedback()

    @staticmethod
    def is_enabled() -> bool:
        return True

    async def invoke(self, draft):
        return self._fb, make_zero_metrics("race_critic_v1")
