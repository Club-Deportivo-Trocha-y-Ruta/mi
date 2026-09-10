"""Alcance por club de los runs agénticos — ``contracts/scope-ai-imports.md`` §11.1.

US6 / FR-028 / FR-029 reemplazan el *creator-lock* por una sola regla: lo que
es del club lo opera cualquier coach del club, el admin siempre, y el coach de
otro club nunca. Este módulo cubre los SIETE endpoints de §2 que antes pasaban
por ``_ensure_run_owner`` (hoy borrado) y ahora por
``permissions.ensure_run_club_access``.

Arnés: motor SQLite in-memory con el subconjunto de tablas que tocan estos
endpoints (patrón de ``tests/routers/test_audit_log_api.py`` y
``tests/routers/test_race_analysis_cancel.py``), más las dos tablas de SQL
crudo (``agent_runs`` / ``agent_run_events``) que no tienen modelo ORM. Nada de
red, nada de LangGraph: ``resume_run`` y ``start_run`` van monkeypatcheados.

Privacidad (Ley 1581): el atleta sembrado es ficticio y ningún nombre de menor
viaja por estas respuestas — los nombres que sí aparecen son de staff adulto.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any, AsyncGenerator, Optional

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

import app.routers.race_analysis as ra
from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.club import ClubRole
from app.models.user import UserRole
from tests.helpers.audit_tables import AUDIT_TABLES

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Escenario — dos coaches del mismo club, uno de otro club
# ---------------------------------------------------------------------------

CLUB_ID = 1
OTHER_CLUB_ID = 2

ADMIN_ID = 1
COACH_A_ID = 10  # lanza los runs
COACH_B_ID = 11  # mismo club que A: la regla nueva le da acceso
COACH_C_ID = 12  # club distinto: 403
PARENT_ID = 5

COACH_A_NAME = "Ana Ficticia Coach"
COACH_B_NAME = "Beto Ficticio Coach"

ATHLETE_ID = 144

#: FR-013 — ningún identificador crudo puede llegar al lector.
_RAW_ID_RE = re.compile(r"^user#\d+$")


_AGENT_RUNS_DDL = """
CREATE TABLE IF NOT EXISTS agent_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    external_run_id TEXT NOT NULL UNIQUE,
    graph_name      TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT NOT NULL DEFAULT 'running',
    input_json      TEXT,
    final_output_json TEXT,
    error_message   TEXT,
    requested_by_user_id INTEGER,
    athlete_id      INTEGER,
    checkpoint_thread_id TEXT NOT NULL,
    explain_mode    INTEGER NOT NULL DEFAULT 0,
    stale_since     TEXT,
    decided_by_user_id INTEGER,
    decided_at      TEXT,
    created_at      TEXT,
    updated_at      TEXT
)
"""

_AGENT_RUN_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS agent_run_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER NOT NULL,
    seq          INTEGER NOT NULL,
    event_type   TEXT NOT NULL,
    node_name    TEXT,
    payload_json TEXT NOT NULL,
    created_at   TEXT NOT NULL
)
"""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _make_user(
    role: UserRole,
    user_id: int,
    club_ids: tuple[int, ...] = (CLUB_ID,),
    *,
    first_name: str = "Staff",
    last_name: str = "Ficticio",
) -> SimpleNamespace:
    """Doble del actor autenticado con membresías de coach explícitas.

    ``coach_club_ids`` lee ``user.club_memberships`` del objeto autenticado
    (no la tabla), así que el doble tiene que traerlas puestas o toda prueba
    de club daría un 403 falso.
    """
    return SimpleNamespace(
        id=user_id,
        first_name=first_name,
        last_name=last_name,
        display_name=f"{first_name} {last_name}",
        email=f"staff{user_id}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[
            SimpleNamespace(club_id=cid, role_in_club=ClubRole.coach)
            for cid in club_ids
        ],
    )


#: Actores del escenario: ``(user_id, rol, clubes, nombre, apellido)``.
_ACTORS: dict[str, tuple[int, UserRole, tuple[int, ...], str, str]] = {
    "admin": (ADMIN_ID, UserRole.admin, (CLUB_ID,), "Admin", "Ficticio"),
    "coach_a": (COACH_A_ID, UserRole.coach, (CLUB_ID,), "Ana Ficticia", "Coach"),
    "coach_b": (COACH_B_ID, UserRole.coach, (CLUB_ID,), "Beto Ficticio", "Coach"),
    "coach_c": (COACH_C_ID, UserRole.coach, (OTHER_CLUB_ID,), "Carla Ficticia", "Coach"),
    "parent": (PARENT_ID, UserRole.parent, (), "Padre", "Ficticio"),
}


@pytest_asyncio.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    from app.models.athlete import Athlete as _A  # noqa: F401
    from app.models.club import Club as _Cl, ClubMember as _CM  # noqa: F401
    from app.models.user import User as _U  # noqa: F401

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    table_names = ["users", "clubs", "club_members", "athletes", *AUDIT_TABLES]
    tables = [Base.metadata.tables[t] for t in table_names]

    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        await conn.execute(text(_AGENT_RUNS_DDL))
        await conn.execute(text(_AGENT_RUN_EVENTS_DDL))

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await _seed_scenario(session)
        await session.commit()

    yield factory
    await engine.dispose()


async def _seed_scenario(session: AsyncSession) -> None:
    """Dos clubes, cuatro miembros de staff y un atleta ficticio del club 1."""
    from app.models.athlete import Athlete, Sex
    from app.models.club import Club, ClubMember
    from app.models.user import User

    session.add_all(
        [
            Club(id=CLUB_ID, name="Club Ficticio Uno", code="CFU", is_active=True,
                 created_at=_utc_now()),
            Club(id=OTHER_CLUB_ID, name="Club Ficticio Dos", code="CFD", is_active=True,
                 created_at=_utc_now()),
        ]
    )
    await session.flush()

    for key, (uid, role, club_ids, first, last) in _ACTORS.items():
        session.add(
            User(
                id=uid,
                email=f"{key}@test.local",
                hashed_password="x",
                first_name=first,
                last_name=last,
                role=role,
                is_active=True,
                can_login=True,
                created_at=_utc_now(),
            )
        )
        await session.flush()
        for cid in club_ids:
            session.add(
                ClubMember(club_id=cid, user_id=uid, role_in_club=ClubRole.coach)
            )
    await session.flush()

    # Usuario técnico del atleta: `athletes.user_id` es FK a `users`.
    session.add(
        User(
            id=1900 + ATHLETE_ID,
            email="atleta.ficticio@test.local",
            hashed_password="x",
            first_name="Mariana Ficticia",
            last_name="Restrepo",
            role=UserRole.parent,
            is_active=True,
            can_login=False,
            created_at=_utc_now(),
        )
    )
    await session.flush()
    session.add(
        Athlete(
            id=ATHLETE_ID,
            user_id=1900 + ATHLETE_ID,
            club_id=CLUB_ID,
            first_name="Mariana Ficticia",
            last_name="Restrepo",
            birth_date=date(2013, 6, 20),
            sex=Sex.F,
            created_by=COACH_A_ID,
            created_at=_utc_now(),
        )
    )


@pytest_asyncio.fixture
async def client_factory(session_factory):
    """``await client_factory("coach_b")`` → ``AsyncClient`` autenticado."""

    async def _make(actor: str) -> AsyncClient:
        uid, role, club_ids, first, last = _ACTORS[actor]

        async def _override_db() -> AsyncGenerator[AsyncSession, None]:
            async with session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: _make_user(
            role, uid, club_ids, first_name=first, last_name=last
        )
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    yield _make
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Siembra de runs
# ---------------------------------------------------------------------------


_FINAL_OUTPUT = {
    "raw_markdown": "## Analisis de prueba\n\nTexto sintetico.",
    "sections": {},
    "recommendations": [],
    "risk_flags": [],
}


async def _seed_run(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    external_run_id: str = "run-a",
    db_status: str = "awaiting_hitl",
    athlete_id: Optional[int] = ATHLETE_ID,
    input_athlete_id: Optional[int] = ATHLETE_ID,
    requested_by: Optional[int] = COACH_A_ID,
    final_output: Any = None,
) -> None:
    """Inserta un run de ``agent_runs``.

    ``athlete_id`` a ``None`` con ``input_athlete_id`` puesto reproduce las
    filas históricas del §1.3 (columna en NULL, el id sólo dentro del JSON).
    """
    payload: dict[str, Any] = {"season": 2026, "valida_nums": [4], "explain_mode": False}
    if input_athlete_id is not None:
        payload["athlete_id"] = input_athlete_id

    async with session_factory() as session:
        await session.execute(
            text(
                """
                INSERT INTO agent_runs (
                    external_run_id, graph_name, prompt_version, started_at,
                    status, input_json, final_output_json, requested_by_user_id,
                    checkpoint_thread_id, explain_mode, athlete_id
                ) VALUES (
                    :rid, 'race-analyst', 'race_analyst_v3', :sa, :st, :inp, :fo,
                    :uid, :rid, 0, :aid
                )
                """
            ),
            {
                "rid": external_run_id,
                "sa": _utc_now(),
                "st": db_status,
                "inp": json.dumps(payload),
                "fo": json.dumps(final_output) if final_output else None,
                "uid": requested_by,
                "aid": athlete_id,
            },
        )
        await session.commit()


async def _fetch_run(
    session_factory: async_sessionmaker[AsyncSession], external_run_id: str
) -> dict[str, Any]:
    async with session_factory() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT id, status, decided_by_user_id, decided_at
                    FROM agent_runs WHERE external_run_id = :rid
                    """
                ),
                {"rid": external_run_id},
            )
        ).first()
    assert row is not None
    return dict(row._mapping)


async def _fetch_audit(
    session_factory: async_sessionmaker[AsyncSession], action: str
) -> list[dict[str, Any]]:
    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT actor_user_id, entity_type, action, entity_id, club_id,
                           athlete_id, meta_json
                    FROM audit_log WHERE action = :a
                    """
                ),
                {"a": action},
            )
        ).fetchall()
    return [dict(r._mapping) for r in rows]


@pytest.fixture
def stub_resume(monkeypatch):
    """Evita LangGraph: ``resume_run`` sólo registra la llamada."""
    calls: list[tuple[str, dict]] = []

    async def _fake_resume(run_id, resume_value, on_complete=None):  # noqa: ANN001
        calls.append((run_id, resume_value))

    monkeypatch.setattr(ra, "resume_run", _fake_resume)
    return calls


@pytest.fixture
def stub_start_run(monkeypatch):
    """Evita el lanzador real en ``re-execute`` (AI, presupuesto, backpressure)."""
    calls: list[dict[str, Any]] = []

    async def _fake_start_run(*, body, db, current_user):  # noqa: ANN001
        from app.schemas.race_ai import RunState, StartRunResponse

        calls.append({"athlete_id": body.athlete_id, "actor_id": current_user.id})
        return StartRunResponse(
            run_id="run-nuevo",
            status=RunState.RUNNING,
            started_at=_utc_now(),
            status_url="/api/race-analysis/runs/run-nuevo/status",
            estimated_seconds=20,
        )

    monkeypatch.setattr(ra, "start_run", _fake_start_run)
    return calls


# ---------------------------------------------------------------------------
# Peticiones a los siete endpoints de §2
# ---------------------------------------------------------------------------


async def _call_endpoint(client: AsyncClient, name: str, run_id: str = "run-a"):
    """Una petición por endpoint de la tabla de §2, con el cuerpo mínimo."""
    base = f"/api/race-analysis/runs/{run_id}"
    if name == "status":
        return await client.get(f"{base}/status")
    if name == "hitl":
        return await client.post(
            f"{base}/hitl/gate_review", json={"decision": "approve"}
        )
    if name == "result":
        return await client.get(f"{base}/result")
    if name == "pdf":
        return await client.get(f"{base}/pdf")
    if name == "invalidate":
        return await client.post(f"{base}/invalidate")
    if name == "cancel":
        return await client.post(f"{base}/cancel")
    if name == "re-execute":
        return await client.post(f"{base}/re-execute")
    raise AssertionError(f"endpoint desconocido: {name}")


SEVEN_ENDPOINTS = (
    "status",
    "hitl",
    "result",
    "pdf",
    "invalidate",
    "cancel",
    "re-execute",
)


# ===========================================================================
# 1-3. El coach B opera lo que lanzó el coach A
# ===========================================================================


async def test_coach_b_lee_status_de_run_del_coach_a(client_factory, session_factory):
    """§11.1-1 y §11.1-3: 200, y la respuesta dice quién lo lanzó."""
    await _seed_run(session_factory)

    async with await client_factory("coach_b") as client:
        resp = await _call_endpoint(client, "status")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["requested_by_user_id"] == COACH_A_ID
    assert body["requested_by_display_name"] == COACH_A_NAME
    # Nadie ha decidido todavía: FK NULL → ambos campos en null (§4.1).
    assert body["decided_by_user_id"] is None
    assert body["decided_by_display_name"] is None


async def test_coach_b_decide_hitl_de_run_del_coach_a(
    client_factory, session_factory, stub_resume
):
    """§11.1-2 y §11.1-3: la decisión queda persistida a nombre de B."""
    await _seed_run(session_factory)

    async with await client_factory("coach_b") as client:
        resp = await _call_endpoint(client, "hitl")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is True
    assert body["decided_by_user_id"] == COACH_B_ID
    assert body["decided_by_display_name"] == COACH_B_NAME

    row = await _fetch_run(session_factory, "run-a")
    assert row["decided_by_user_id"] == COACH_B_ID
    assert row["decided_at"] is not None
    assert stub_resume, "resume_run debió invocarse tras aceptar el gate"


async def test_status_tras_decidir_muestra_ambos_nombres(
    client_factory, session_factory, stub_resume
):
    """§11.1-3: "Lanzado por A · Decidido por B" sale del mismo ``/status``."""
    await _seed_run(session_factory)

    async with await client_factory("coach_b") as client:
        assert (await _call_endpoint(client, "hitl")).status_code == 200
        resp = await _call_endpoint(client, "status")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["requested_by_display_name"] == COACH_A_NAME
    assert body["decided_by_user_id"] == COACH_B_ID
    assert body["decided_by_display_name"] == COACH_B_NAME


async def test_coach_b_cancela_run_del_coach_a(client_factory, session_factory):
    """§11.1-10: cancelar deja la fila ``cancel`` a nombre de B, sin tocar
    ``decided_by_user_id`` — cancelar no es decidir (§3)."""
    await _seed_run(session_factory)

    async with await client_factory("coach_b") as client:
        resp = await _call_endpoint(client, "cancel")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"run_id": "run-a", "state": "cancelled"}

    row = await _fetch_run(session_factory, "run-a")
    assert row["status"] == "cancelled"
    assert row["decided_by_user_id"] is None
    assert row["decided_at"] is None

    rows = await _fetch_audit(session_factory, "cancel")
    assert len(rows) == 1
    assert rows[0]["actor_user_id"] == COACH_B_ID
    assert rows[0]["entity_type"] == "agent_run"
    assert rows[0]["club_id"] == CLUB_ID
    assert json.loads(rows[0]["meta_json"])["previous_status"] == "awaiting_hitl"


async def test_coach_b_re_ejecuta_run_del_coach_a(
    client_factory, session_factory, stub_start_run
):
    """El coach B relanza el análisis que lanzó A."""
    await _seed_run(session_factory, db_status="completed", final_output=_FINAL_OUTPUT)

    async with await client_factory("coach_b") as client:
        resp = await _call_endpoint(client, "re-execute")

    assert resp.status_code == 200, resp.text
    assert resp.json()["run_id"] == "run-nuevo"
    assert stub_start_run == [{"athlete_id": ATHLETE_ID, "actor_id": COACH_B_ID}]


async def test_coach_b_baja_el_pdf_del_run_del_coach_a(
    client_factory, session_factory
):
    """El PDF de un run del club lo baja cualquier coach del club.

    ``weasyprint`` necesita librerías nativas: donde no están, el endpoint
    responde 501 por diseño. Lo que esta prueba fija es que NUNCA es 403 y
    que, cuando sí renderiza, deja la fila ``export`` a nombre de B.
    """
    await _seed_run(session_factory, db_status="completed", final_output=_FINAL_OUTPUT)

    async with await client_factory("coach_b") as client:
        resp = await _call_endpoint(client, "pdf")

    assert resp.status_code in (200, 501), resp.text
    if resp.status_code == 200:
        assert resp.headers["content-type"].startswith("application/pdf")
        rows = await _fetch_audit(session_factory, "export")
        assert len(rows) == 1
        assert rows[0]["actor_user_id"] == COACH_B_ID
        assert json.loads(rows[0]["meta_json"])["document_kind"] == "race_analysis_pdf"


async def test_coach_b_lee_result_de_run_del_coach_a(client_factory, session_factory):
    await _seed_run(session_factory, db_status="completed", final_output=_FINAL_OUTPUT)

    async with await client_factory("coach_b") as client:
        resp = await _call_endpoint(client, "result")

    assert resp.status_code == 200, resp.text
    assert resp.json()["final"]["raw_markdown"] == _FINAL_OUTPUT["raw_markdown"]


@pytest.mark.parametrize("endpoint", SEVEN_ENDPOINTS)
async def test_coach_del_mismo_club_nunca_recibe_403(
    client_factory, session_factory, stub_resume, stub_start_run, endpoint
):
    """§11.1-1: los siete endpoints de §2, parametrizados, para el coach B."""
    await _seed_run(session_factory, db_status="awaiting_hitl")

    async with await client_factory("coach_b") as client:
        resp = await _call_endpoint(client, endpoint)

    assert resp.status_code != 403, f"{endpoint} → 403 para un coach del club"


# ===========================================================================
# 4. Ningún identificador crudo llega al lector (FR-013)
# ===========================================================================


def _iter_strings(value: Any):
    """Recorre recursivamente todos los valores string de un JSON."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _iter_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _iter_strings(v)


@pytest.mark.parametrize("endpoint", SEVEN_ENDPOINTS)
async def test_ninguna_respuesta_expone_user_id_crudo(
    client_factory, session_factory, stub_resume, stub_start_run, endpoint
):
    """§11.1-4: ``user#7`` no es un valor legal en ninguna de las siete."""
    await _seed_run(session_factory)

    async with await client_factory("coach_b") as client:
        resp = await _call_endpoint(client, endpoint)

    if resp.headers.get("content-type", "").startswith("application/json"):
        for text_value in _iter_strings(resp.json()):
            assert not _RAW_ID_RE.match(text_value), (
                f"{endpoint} devolvió un identificador crudo: {text_value!r}"
            )


async def test_fk_puesta_sin_usuario_resoluble_da_usuario_no_disponible(
    client_factory, session_factory
):
    """§4.1: FK a una fila inexistente → ``"Usuario no disponible"``."""
    await _seed_run(session_factory, requested_by=7777)

    async with await client_factory("coach_b") as client:
        resp = await _call_endpoint(client, "status")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["requested_by_user_id"] == 7777
    assert body["requested_by_display_name"] == "Usuario no disponible"


async def test_fk_nula_deja_ambos_campos_en_null(client_factory, session_factory):
    """§4.1: ``requested_by_user_id`` NULL → ambos campos ``null``."""
    await _seed_run(session_factory, requested_by=None)

    async with await client_factory("coach_b") as client:
        resp = await _call_endpoint(client, "status")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["requested_by_user_id"] is None
    assert body["requested_by_display_name"] is None


# ===========================================================================
# 5-7. Caminos denegados y bypass de admin
# ===========================================================================


@pytest.mark.parametrize("endpoint", SEVEN_ENDPOINTS)
async def test_coach_de_otro_club_403_en_los_siete(
    client_factory, session_factory, endpoint
):
    """§11.1-5."""
    await _seed_run(session_factory)

    async with await client_factory("coach_c") as client:
        resp = await _call_endpoint(client, endpoint)

    assert resp.status_code == 403, f"{endpoint} → {resp.status_code}"
    assert resp.json()["detail"] == "No tienes acceso a este run"


@pytest.mark.parametrize("endpoint", SEVEN_ENDPOINTS)
async def test_parent_403_en_los_siete(client_factory, session_factory, endpoint):
    """§11.1-6: el gate de rol sigue igual, antes del chequeo de club."""
    await _seed_run(session_factory)

    async with await client_factory("parent") as client:
        resp = await _call_endpoint(client, endpoint)

    assert resp.status_code == 403, f"{endpoint} → {resp.status_code}"


@pytest.mark.parametrize("endpoint", SEVEN_ENDPOINTS)
async def test_admin_nunca_recibe_403(
    client_factory, session_factory, stub_resume, stub_start_run, endpoint
):
    """§11.1-7: el bypass de admin no cambió."""
    await _seed_run(session_factory)

    async with await client_factory("admin") as client:
        resp = await _call_endpoint(client, endpoint)

    assert resp.status_code != 403, f"{endpoint} → 403 para admin"


# ===========================================================================
# 8-9. Escalera de resolución del club (§1.1) y respaldo por autoría (§1.4)
# ===========================================================================


async def test_athlete_id_nulo_resuelve_por_input_json(
    client_factory, session_factory
):
    """§11.1-8: fila histórica con la columna en NULL, id dentro del JSON."""
    await _seed_run(session_factory, athlete_id=None, input_athlete_id=ATHLETE_ID)

    async with await client_factory("coach_b") as client:
        resp = await _call_endpoint(client, "status")

    assert resp.status_code == 200, resp.text


async def test_club_irresoluble_solo_lo_abre_su_autor(client_factory, session_factory):
    """§11.1-9 y §1.4: sin atleta y sin membresía del autor, el respaldo por
    autoría mantiene la fila alcanzable para quien la creó — y para nadie más
    salvo el admin. El autor es un coach sin ninguna fila en ``club_members``.
    """
    orphan_author = 7777  # no existe en `users` ni en `club_members`
    await _seed_run(
        session_factory,
        athlete_id=None,
        input_athlete_id=None,
        requested_by=orphan_author,
    )

    # El coach B, del club sembrado, ya no alcanza la fila: no hay club que
    # intersecar y él no es el autor.
    async with await client_factory("coach_b") as client:
        assert (await _call_endpoint(client, "status")).status_code == 403

    # El admin sigue pasando.
    async with await client_factory("admin") as client:
        assert (await _call_endpoint(client, "status")).status_code == 200

    # Y el autor mismo también, aunque no tenga club.
    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.coach, orphan_author, ()
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await _call_endpoint(client, "status")).status_code == 200
    app.dependency_overrides.clear()


async def test_run_de_otro_club_403_aunque_el_autor_sea_del_club_del_lector(
    client_factory, session_factory
):
    """La escalera de §1.1 privilegia el atleta sobre el autor: un run del
    coach A (club 1) sobre un atleta del club 2 no lo abre un coach del club 1.
    """
    from app.models.athlete import Athlete, Sex
    from app.models.user import User

    async with session_factory() as session:
        session.add(
            User(
                id=1999,
                email="atleta.otro.club@test.local",
                hashed_password="x",
                first_name="Atleta Ficticio",
                last_name="Externo",
                role=UserRole.parent,
                is_active=True,
                can_login=False,
                created_at=_utc_now(),
            )
        )
        await session.flush()
        session.add(
            Athlete(
                id=999,
                user_id=1999,
                club_id=OTHER_CLUB_ID,
                first_name="Atleta Ficticio",
                last_name="Externo",
                birth_date=date(2012, 3, 4),
                sex=Sex.M,
                created_by=COACH_A_ID,
                created_at=_utc_now(),
            )
        )
        await session.commit()

    await _seed_run(
        session_factory,
        external_run_id="run-otro-club",
        athlete_id=999,
        input_athlete_id=999,
        requested_by=COACH_A_ID,
    )

    async with await client_factory("coach_b") as client:
        resp = await _call_endpoint(client, "status", run_id="run-otro-club")

    assert resp.status_code == 403
