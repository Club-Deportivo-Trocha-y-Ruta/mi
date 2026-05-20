"""Fixtures comunes para tests de routers.

Convención del proyecto: ``conftest.py`` raíz expone ``client`` con
``app`` real. Aquí extendemos para tests del router race_analysis con:

- Fake session async tipo "store SQL crudo" — simula MySQL devolviendo
  filas mockeadas según el SQL.
- Override de dependencias ``get_db`` + ``get_current_user`` +
  ``require_role`` para evitar JWT real y MySQL real.
- Stub del runner (no llama LangGraph) y del chat agent.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Optional

import pytest
import pytest_asyncio

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models.user import UserRole
from app.routers.race_analysis import (
    _admin_only,
    _coach_or_admin,
    get_race_chat_agent,
)


# ---------------------------------------------------------------------------
# Fake users
# ---------------------------------------------------------------------------


def make_user(role: UserRole, user_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"{role.value}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


# ---------------------------------------------------------------------------
# Fake DB session
# ---------------------------------------------------------------------------


class FakeRow:
    """Row-like con _mapping para imitar SQLAlchemy Result."""

    def __init__(self, **fields: Any):
        self._mapping = fields
        for k, v in fields.items():
            setattr(self, k, v)

    def __getitem__(self, idx: int) -> Any:
        return list(self._mapping.values())[idx]


class FakeResult:
    def __init__(self, rows: list[FakeRow]):
        self._rows = list(rows)

    def fetchall(self) -> list[FakeRow]:
        return list(self._rows)

    def all(self) -> list[FakeRow]:
        return list(self._rows)

    def first(self) -> Optional[FakeRow]:
        return self._rows[0] if self._rows else None

    def fetchone(self) -> Optional[FakeRow]:
        return self._rows[0] if self._rows else None

    def scalars(self) -> "FakeResult":
        return self

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None


class FakeSession:
    """Sesión async mínima que dispatcha por substrings del SQL."""

    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.events_by_run_db_id: dict[int, list[dict[str, Any]]] = {}
        self.insights: list[dict[str, Any]] = []
        self.executed: list[tuple[str, dict]] = []
        self._next_run_db_id = 1
        self._next_event_id = 1

    # ---- helpers para tests ----

    def seed_run(
        self,
        external_run_id: str,
        status_: str = "running",
        requested_by_user_id: int = 1,
        explain_mode: bool = False,
        final_output_json: Any = None,
        finished_at: Optional[datetime] = None,
    ) -> dict[str, Any]:
        run = {
            "id": self._next_run_db_id,
            "external_run_id": external_run_id,
            "status": status_,
            "started_at": datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc),
            "finished_at": finished_at,
            "input_json": "{}",
            "final_output_json": json.dumps(final_output_json) if final_output_json else None,
            "error_message": None,
            "requested_by_user_id": requested_by_user_id,
            "explain_mode": explain_mode,
        }
        self.runs[external_run_id] = run
        self.events_by_run_db_id.setdefault(run["id"], [])
        self._next_run_db_id += 1
        return run

    def seed_event(
        self,
        run_db_id: int,
        seq: int,
        event_type: str,
        node_name: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> None:
        self.events_by_run_db_id.setdefault(run_db_id, []).append(
            {
                "id": self._next_event_id,
                "seq": seq,
                "event_type": event_type,
                "node_name": node_name,
                "payload_json": payload or {},
                "created_at": datetime(2026, 5, 20, 12, 0, seq, tzinfo=timezone.utc),
            }
        )
        self._next_event_id += 1

    def seed_insight(
        self,
        athlete_id: int = 1,
        cost_total: float = 0.001,
        latency_total: int = 1500,
        prompt_version: str = "race_analyst_v1",
        generated_at: Optional[datetime] = None,
    ) -> None:
        self.insights.append(
            {
                "athlete_id": athlete_id,
                "prompt_version": prompt_version,
                "generated_at": generated_at or datetime.now(timezone.utc),
                "metrics_snapshot_json": json.dumps(
                    {
                        "aggregate": {
                            "cost_usd_total": cost_total,
                            "latency_ms_total": latency_total,
                        }
                    }
                ),
            }
        )

    # ---- SQLAlchemy-compatible API ----

    async def execute(self, stmt: Any, params: Optional[dict] = None) -> FakeResult:
        sql = getattr(stmt, "text", None) or str(stmt)
        params = params or {}
        self.executed.append((sql, params))

        # Routing por substrings — mantenemos la lista ordenada de
        # match más específico a más general.

        # INSERT agent_runs
        if "INSERT INTO agent_runs" in sql:
            rid = params["rid"]
            self.runs[rid] = {
                "id": self._next_run_db_id,
                "external_run_id": rid,
                "status": "running",
                "started_at": params.get("sa"),
                "finished_at": None,
                "input_json": params.get("inp"),
                "final_output_json": None,
                "error_message": None,
                "requested_by_user_id": params.get("uid"),
                "explain_mode": params.get("em"),
            }
            self.events_by_run_db_id.setdefault(self._next_run_db_id, [])
            self._next_run_db_id += 1
            return FakeResult([])

        # INSERT agent_run_events
        if "INSERT INTO agent_run_events" in sql:
            rid = params["rid"]
            self.events_by_run_db_id.setdefault(rid, []).append(
                {
                    "id": self._next_event_id,
                    "seq": params["seq"],
                    "event_type": "hitl_response",
                    "node_name": "hitl_gate_review",
                    "payload_json": params.get("pl") or "{}",
                    "created_at": datetime.now(timezone.utc),
                }
            )
            self._next_event_id += 1
            return FakeResult([])

        # UPDATE agent_runs
        if "UPDATE agent_runs" in sql:
            rid = params.get("rid")
            if rid and rid in self.runs:
                run = self.runs[rid]
                if params.get("st"):
                    run["status"] = params["st"]
                if params.get("fin"):
                    run["finished_at"] = params["fin"]
                if params.get("em"):
                    run["error_message"] = params["em"]
                if params.get("fo"):
                    run["final_output_json"] = params["fo"]
            return FakeResult([])

        # SELECT * FROM agent_runs WHERE external_run_id
        if "FROM agent_runs" in sql and "external_run_id" in sql and "SELECT" in sql.upper():
            rid = params.get("rid")
            run = self.runs.get(rid)
            if run is None:
                return FakeResult([])
            return FakeResult([FakeRow(**run)])

        # SELECT status, COUNT FROM agent_runs (admin metrics)
        if "FROM agent_runs" in sql and "GROUP BY status" in sql:
            counts: dict[str, int] = {}
            for r in self.runs.values():
                counts[r["status"]] = counts.get(r["status"], 0) + 1
            return FakeResult([FakeRow(status=s, c=c) for s, c in counts.items()])

        # SELECT MAX(seq) FROM agent_run_events
        if "MAX(seq)" in sql and "agent_run_events" in sql:
            rid = params.get("rid")
            evs = self.events_by_run_db_id.get(rid, [])
            max_seq = max([e["seq"] for e in evs], default=0)
            return FakeResult([FakeRow(s=max_seq)])

        # SELECT node_name FROM agent_run_events ORDER BY seq DESC LIMIT 1
        if "SELECT node_name FROM agent_run_events" in sql:
            rid = params.get("rid")
            evs = sorted(
                self.events_by_run_db_id.get(rid, []),
                key=lambda e: e["seq"],
                reverse=True,
            )
            if not evs:
                return FakeResult([])
            return FakeResult([FakeRow(node_name=evs[0]["node_name"])])

        # SELECT seq, event_type, ... FROM agent_run_events WHERE run_id=:rid AND seq > :since
        if "FROM agent_run_events" in sql and "seq > :since" in sql:
            rid = params.get("rid")
            since = params.get("since", 0)
            evs = sorted(self.events_by_run_db_id.get(rid, []), key=lambda e: e["seq"])
            filtered = [e for e in evs if e["seq"] > since]
            return FakeResult(
                [
                    FakeRow(
                        seq=e["seq"],
                        event_type=e["event_type"],
                        node_name=e["node_name"],
                        payload_json=e["payload_json"],
                        created_at=e["created_at"],
                    )
                    for e in filtered
                ]
            )

        # Budget guard (F8A): SELECT SUM(...cost_usd_total) AS total FROM athlete_ai_insights
        # No tiene COUNT, no tiene GROUP BY, no tiene latency_ms_total → es la del guard.
        if (
            "FROM athlete_ai_insights" in sql
            and "cost_usd_total" in sql
            and " AS total" in sql
            and "COUNT" not in sql.upper()
            and "GROUP BY" not in sql
        ):
            cutoff = params.get("cutoff")
            filtered = [i for i in self.insights if not cutoff or i["generated_at"] >= cutoff]
            total = 0.0
            for ins in filtered:
                try:
                    total += float(
                        json.loads(ins["metrics_snapshot_json"])
                        ["aggregate"]["cost_usd_total"]
                    )
                except Exception:  # noqa: BLE001
                    pass
            return FakeResult([FakeRow(total=total)])

        # SELECT COUNT/SUM FROM athlete_ai_insights
        if "FROM athlete_ai_insights" in sql and "COUNT" in sql.upper():
            cutoff = params.get("cutoff")
            filtered = [i for i in self.insights if not cutoff or i["generated_at"] >= cutoff]
            n = len(filtered)
            cost = 0.0
            for ins in filtered:
                try:
                    cost += float(
                        json.loads(ins["metrics_snapshot_json"])
                        ["aggregate"]["cost_usd_total"]
                    )
                except Exception:  # noqa: BLE001
                    pass
            return FakeResult([FakeRow(n=n, cost=cost)])

        # SELECT lat FROM athlete_ai_insights
        if "FROM athlete_ai_insights" in sql and "latency_ms_total" in sql and "GROUP BY" not in sql:
            cutoff = params.get("cutoff")
            filtered = [i for i in self.insights if not cutoff or i["generated_at"] >= cutoff]
            rows = []
            for ins in filtered:
                try:
                    lat = int(
                        json.loads(ins["metrics_snapshot_json"])
                        ["aggregate"]["latency_ms_total"]
                    )
                    rows.append(FakeRow(lat=lat))
                except Exception:  # noqa: BLE001
                    pass
            return FakeResult(rows)

        # SELECT prompt_version, COUNT, SUM FROM athlete_ai_insights GROUP BY prompt_version
        if "FROM athlete_ai_insights" in sql and "GROUP BY prompt_version" in sql:
            cutoff = params.get("cutoff")
            filtered = [i for i in self.insights if not cutoff or i["generated_at"] >= cutoff]
            by_pv: dict[str, dict] = {}
            for ins in filtered:
                pv = ins["prompt_version"]
                entry = by_pv.setdefault(pv, {"c": 0, "cost": 0.0})
                entry["c"] += 1
                try:
                    entry["cost"] += float(
                        json.loads(ins["metrics_snapshot_json"])
                        ["aggregate"]["cost_usd_total"]
                    )
                except Exception:  # noqa: BLE001
                    pass
            return FakeResult(
                [FakeRow(prompt_version=pv, c=v["c"], cost=v["cost"]) for pv, v in by_pv.items()]
            )

        return FakeResult([])

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def flush(self) -> None:
        pass

    def add(self, _obj: Any) -> None:
        pass


# ---------------------------------------------------------------------------
# Fake graph runner
# ---------------------------------------------------------------------------


class FakeGraph:
    """Imita compiled_graph.ainvoke — no hace nada (no LLM)."""

    def __init__(self) -> None:
        self.invocations: list[tuple[Any, dict]] = []

    async def ainvoke(self, value: Any, config: Optional[dict] = None) -> dict:
        self.invocations.append((value, config or {}))
        await asyncio.sleep(0)  # ceder loop
        return {"ok": True}


# ---------------------------------------------------------------------------
# Fixtures pytest
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def fake_db() -> FakeSession:
    return FakeSession()


@pytest_asyncio.fixture
async def fake_graph() -> FakeGraph:
    return FakeGraph()


@pytest.fixture
def ai_enabled(monkeypatch):
    """Setea settings.ai_enabled=True para los tests que lo requieran."""
    from app.config import settings

    monkeypatch.setattr(settings, "ai_enabled", True)
    return settings


@pytest_asyncio.fixture
async def coach_client(client, fake_db, fake_graph, monkeypatch):
    """Cliente HTTP con auth=coach, DB fake y runner stub."""
    from app.services.race.ai import runner as runner_mod

    async def _graph_factory():
        return fake_graph

    runner_mod.set_graph_factory(_graph_factory)
    await runner_mod._reset_for_tests()

    async def _override_db():
        yield fake_db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: make_user(UserRole.coach, user_id=10)
    # _coach_or_admin y _admin_only son Depends() callables; los
    # overrides funcionan sobre la callable directa.
    app.dependency_overrides[_coach_or_admin] = lambda: make_user(
        UserRole.coach, user_id=10
    )
    yield client
    app.dependency_overrides.clear()
    runner_mod.set_graph_factory(None)
    await runner_mod._reset_for_tests()


@pytest_asyncio.fixture
async def admin_client(client, fake_db, fake_graph, monkeypatch):
    """Cliente HTTP con auth=admin."""
    from app.services.race.ai import runner as runner_mod

    async def _graph_factory():
        return fake_graph

    runner_mod.set_graph_factory(_graph_factory)
    await runner_mod._reset_for_tests()

    async def _override_db():
        yield fake_db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: make_user(UserRole.admin, user_id=1)
    app.dependency_overrides[_coach_or_admin] = lambda: make_user(
        UserRole.admin, user_id=1
    )
    app.dependency_overrides[_admin_only] = lambda: make_user(UserRole.admin, user_id=1)
    yield client
    app.dependency_overrides.clear()
    runner_mod.set_graph_factory(None)
    await runner_mod._reset_for_tests()


@pytest_asyncio.fixture
async def parent_client(client, fake_db, monkeypatch):
    """Cliente HTTP con auth=parent (debe ser rechazado en endpoints coach+)."""
    from fastapi import HTTPException

    async def _override_db():
        yield fake_db

    def _forbid():
        raise HTTPException(status_code=403, detail="No tienes permisos para esta acción")

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: make_user(UserRole.parent, user_id=5)
    app.dependency_overrides[_coach_or_admin] = _forbid
    app.dependency_overrides[_admin_only] = _forbid
    yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def anon_client(client):
    """Cliente sin auth — debe recibir 401 desde el bearer scheme.

    Para tests donde queremos validar el guard real (no override),
    NO se setea ningún override y se llama directamente.
    """
    # No override — los endpoints usan _coach_or_admin que requiere bearer.
    yield client
