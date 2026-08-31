"""Tests de ``get_conjoint_sessions`` (``app/services/training/reports.py``).

El módulo Sesiones quedó restringido a entrenamientos: las salidas y
actividades conjuntas se registran ahora como eventos del Calendario. El
apartado "Actividades conjuntas y salidas" del informe al financiador debe
por tanto unir dos fuentes:

(happy) eventos de calendario ``club_event`` / ``group_training`` del mes.
(happy) sesiones históricas con ``session_kind`` actividad_conjunta/salida
        (creadas antes de la restricción) — siguen apareciendo.
(edge)  el resultado va ordenado por fecha, mezclando ambas fuentes.
(edge)  se excluyen: eventos cancelados, eventos fuera del mes, eventos ya
        enlazados a una sesión (no se duplica la fila) y entrenamientos
        normales.

Estrategia: SQLite async in-memory real, mismo patrón que
``tests/test_report_photo_evidence_sections.py``.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.calendar_event import CalendarEvent, EventStatus, EventType
from app.models.training_session import SessionKind, SessionStatus, TrainingSession
from app.models.user import UserRole
from app.services.training.reports import get_conjoint_sessions

from tests.fixtures.race_history_fixtures import create_club, create_user

CLUB_ID = 1
COACH_ID = 10


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Base.metadata.tables[t]
        for t in ("users", "clubs", "training_sessions", "calendar_events")
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await create_club(session, club_id=CLUB_ID)
        await create_user(session, user_id=COACH_ID, role=UserRole.coach)
        await session.commit()
        yield session


async def _add_event(
    db: AsyncSession,
    *,
    event_id: int,
    day: int,
    event_type: EventType = EventType.CLUB_EVENT,
    status: EventStatus = EventStatus.SCHEDULED,
    title: str = "Salida al Bike Park",
    month: int = 8,
    hours: int = 2,
) -> CalendarEvent:
    start = datetime(2026, month, day, 7, 0)
    ev = CalendarEvent(
        id=event_id,
        club_id=CLUB_ID,
        event_type=event_type,
        status=status,
        title=title,
        description="Objetivo de la actividad",
        location="La Buitrera",
        start_at=start,
        end_at=start.replace(hour=7 + hours),
        created_by_user_id=COACH_ID,
    )
    db.add(ev)
    await db.flush()
    return ev


async def _add_session(
    db: AsyncSession,
    *,
    session_id: int,
    day: int,
    session_kind: SessionKind,
    calendar_event_id: int | None = None,
    month: int = 8,
) -> TrainingSession:
    ts = TrainingSession(
        id=session_id,
        club_id=CLUB_ID,
        created_by_user_id=COACH_ID,
        status=SessionStatus.EXECUTED,
        scheduled_date=date(2026, month, day),
        scheduled_start_time=time(16, 0),
        duration_min=90,
        location="Cerrito",
        technical_focus="Zona aeróbica",
        session_kind=session_kind,
        calendar_event_id=calendar_event_id,
    )
    db.add(ts)
    await db.flush()
    return ts


@pytest.mark.asyncio
async def test_incluye_eventos_de_calendario(db: AsyncSession) -> None:
    await _add_event(db, event_id=1, day=15)
    await db.commit()

    rows = await get_conjoint_sessions(db, CLUB_ID, 2026, 8)

    assert len(rows) == 1
    assert rows[0]["date"] == "15/08/2026"
    assert rows[0]["kind_label"] == "Actividad conjunta"
    assert rows[0]["technical_focus"] == "Salida al Bike Park"
    assert rows[0]["location"] == "La Buitrera"
    assert rows[0]["duration_min"] == 120


@pytest.mark.asyncio
async def test_group_training_se_etiqueta_como_salida(db: AsyncSession) -> None:
    await _add_event(
        db, event_id=1, day=9, event_type=EventType.GROUP_TRAINING, title="Ruta grupal"
    )
    await db.commit()

    rows = await get_conjoint_sessions(db, CLUB_ID, 2026, 8)

    assert [r["kind_label"] for r in rows] == ["Salida"]


@pytest.mark.asyncio
async def test_mezcla_historico_y_calendario_ordenado_por_fecha(
    db: AsyncSession,
) -> None:
    await _add_event(db, event_id=1, day=20, title="Integración familias")
    await _add_session(db, session_id=1, day=5, session_kind=SessionKind.SALIDA)
    await db.commit()

    rows = await get_conjoint_sessions(db, CLUB_ID, 2026, 8)

    assert [r["date"] for r in rows] == ["05/08/2026", "20/08/2026"]
    assert [r["kind_label"] for r in rows] == ["Salida", "Actividad conjunta"]


@pytest.mark.asyncio
async def test_excluye_cancelados_entrenamientos_y_otros_meses(
    db: AsyncSession,
) -> None:
    await _add_event(db, event_id=1, day=10, status=EventStatus.CANCELLED)
    await _add_event(db, event_id=2, day=10, event_type=EventType.TRAINING_SESSION)
    await _add_event(db, event_id=3, day=10, month=7)
    await _add_session(db, session_id=1, day=12, session_kind=SessionKind.ENTRENAMIENTO)
    await _add_session(db, session_id=2, day=12, session_kind=SessionKind.OTRO)
    await db.commit()

    rows = await get_conjoint_sessions(db, CLUB_ID, 2026, 8)

    assert rows == []


@pytest.mark.asyncio
async def test_no_duplica_evento_ya_enlazado_a_sesion(db: AsyncSession) -> None:
    await _add_event(db, event_id=1, day=18)
    await _add_session(
        db,
        session_id=1,
        day=18,
        session_kind=SessionKind.ACTIVIDAD_CONJUNTA,
        calendar_event_id=1,
    )
    await db.commit()

    rows = await get_conjoint_sessions(db, CLUB_ID, 2026, 8)

    assert len(rows) == 1
    assert rows[0]["technical_focus"] == "Zona aeróbica"
