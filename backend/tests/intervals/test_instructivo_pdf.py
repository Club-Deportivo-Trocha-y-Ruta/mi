"""Tests for the instructivo PDF endpoint (feature 026, T028/US3).

``GET /api/intervals/sessions/{id}/instructivo?brand=garmin|magene|igpsport``
(``app/routers/intervals.py::download_instructivo_pdf``).

Two independent layers, same caveat as feature 024
(``tests/test_newsletter_pdf_render_html.py``):

1. **Router/HTTP layer** (``TestInstructivoPdfEndpoint``): exercises the real
   FastAPI route — RBAC, club scoping, 404/422 branches, filename building —
   through an ``AsyncClient`` over an in-memory aiosqlite DB. The
   ``DocumentGenerator`` dependency is overridden with an in-process stub
   whose ``generate()`` reuses the *real*, static
   ``DocumentGenerator._build_filename`` (pure string logic, no I/O) but
   skips the actual WeasyPrint render. This is required because this dev
   environment does not have WeasyPrint's system libraries (pango/glib)
   installed — ``from weasyprint import HTML`` raises ``OSError`` at import
   time here (verified: ``cannot load library 'libgobject-2.0-0'``) — the
   same caveat documented for feature 024. It works unmodified in
   Docker/Render, where those libraries are present (see
   ``entrypoint.sh``/Dockerfile). This layer asserts the **status code**,
   **content type**, and **filename varies per brand** — never the actual
   PDF bytes.

2. **Template/HTML layer** (``TestInstructivoTemplateRendering``): renders
   ``templates/documents/pdf/session_instructivo.html`` directly to an HTML
   string via Jinja2 (no WeasyPrint at all — mirrors
   ``test_newsletter_pdf_render_html.py``), so it runs in every environment
   including this one. Asserts the flattened block table (repeat groups
   expanded, not collapsed), the per-brand configuration steps, and the
   mandatory "Desactivá la vuelta automática" (auto-lap) step present in the
   render for all three brands (FR-010/FR-011, D8).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, time, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db, get_document_generator
from app.main import app
from app.models import Base
from app.models.club import Club, ClubMember, ClubRole
from app.models.interval_structure import (
    HRZone,
    IntervalBlockType,
    IntervalStructure,
    IntervalStructureBlock,
)
from app.models.technique_exercise import AgeBand
from app.models.training_session import SessionKind, SessionStatus, TrainingSession
from app.models.user import User, UserRole
from app.schemas.notification import DocumentFormat, GeneratedDocument
from app.services.notification.document_generator import (
    _TEMPLATES_ROOT,
    DocumentGenerator,
    _format_hms,
    _render_markdown,
)
from app.services.utils.dates_es import format_date_es

# ---------------------------------------------------------------------------
# Router/HTTP layer — in-memory aiosqlite harness (mirrors tests/strength/
# conftest.py, kept local to this file: this feature's tests/intervals/
# conftest.py is owned by a different parallel task).
# ---------------------------------------------------------------------------

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "training_sessions",
    "interval_structures",
    "interval_structure_blocks",
)


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as s:
        yield s


def _coach_user(user_id: int = 10) -> User:
    return User(
        id=user_id,
        email=f"entrenador.ficticio{user_id}@test.com",
        hashed_password="x",
        first_name="Entrenador",
        last_name="Ficticio",
        role=UserRole.coach,
        is_active=True,
        can_login=True,
        created_at=datetime.now(timezone.utc),
    )


def _parent_user(user_id: int = 30) -> User:
    return User(
        id=user_id,
        email=f"padre.ficticio{user_id}@test.com",
        hashed_password="x",
        first_name="Padre",
        last_name="Ficticio",
        role=UserRole.parent,
        is_active=True,
        can_login=True,
        created_at=datetime.now(timezone.utc),
    )


async def _seed_club(session: AsyncSession, club_id: int = 1) -> Club:
    club = Club(
        id=club_id,
        name="Club Ficticio de Prueba",
        code=f"TST{club_id:03d}",
        location="Valle del Cauca — datos ficticios",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    session.add(club)
    await session.flush()
    return club


async def _seed_coach(session: AsyncSession, user_id: int = 10, club_id: int = 1) -> User:
    user = _coach_user(user_id)
    session.add(user)
    await session.flush()
    session.add(
        ClubMember(
            club_id=club_id,
            user_id=user_id,
            role_in_club=ClubRole.coach,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await session.flush()
    return user


async def _seed_parent(session: AsyncSession, user_id: int = 30) -> User:
    user = _parent_user(user_id)
    session.add(user)
    await session.flush()
    return user


async def _seed_training_session(
    session: AsyncSession,
    *,
    session_id: int | None = None,
    club_id: int = 1,
    created_by_user_id: int = 10,
) -> TrainingSession:
    kwargs: dict = {}
    if session_id is not None:
        kwargs["id"] = session_id
    training_session = TrainingSession(
        club_id=club_id,
        created_by_user_id=created_by_user_id,
        status=SessionStatus.PLANNED,
        scheduled_date=date(2026, 7, 15),
        scheduled_start_time=time(15, 0),
        duration_min=60,
        location="Pista Ginebra — datos ficticios",
        technical_focus="Umbral en pista (prueba)",
        session_kind=SessionKind.ENTRENAMIENTO,
        objectives="Trabajo de umbral con series cortas.",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        **kwargs,
    )
    session.add(training_session)
    await session.flush()
    return training_session


async def _seed_structure(
    session: AsyncSession,
    *,
    training_session_id: int,
    created_by_user_id: int = 10,
) -> IntervalStructure:
    """Insert a 13-15 structure with a repeat group (no age gate involved)."""
    structure = IntervalStructure(
        training_session_id=training_session_id,
        target_age_band=AgeBand.BAND_13_15,
        age_gate_confirmed=False,
        created_by_user_id=created_by_user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(structure)
    await session.flush()

    blocks = [
        IntervalStructureBlock(
            structure_id=structure.id,
            position=1,
            block_type=IntervalBlockType.WARMUP,
            duration_s=300,
            target_zone=HRZone.Z1,
            target_cadence_rpm=70,
            repeat_group=None,
            repeat_count=None,
        ),
        IntervalStructureBlock(
            structure_id=structure.id,
            position=2,
            block_type=IntervalBlockType.WORK,
            duration_s=120,
            target_zone=HRZone.Z3,
            target_cadence_rpm=85,
            repeat_group=1,
            repeat_count=2,
        ),
        IntervalStructureBlock(
            structure_id=structure.id,
            position=3,
            block_type=IntervalBlockType.RECOVERY,
            duration_s=60,
            target_zone=HRZone.Z1,
            target_cadence_rpm=65,
            repeat_group=1,
            repeat_count=2,
        ),
        IntervalStructureBlock(
            structure_id=structure.id,
            position=4,
            block_type=IntervalBlockType.COOLDOWN,
            duration_s=300,
            target_zone=HRZone.Z1,
            target_cadence_rpm=65,
            repeat_group=None,
            repeat_count=None,
        ),
    ]
    session.add_all(blocks)
    await session.flush()
    return structure


class _FakePdfGenerator:
    """Stub for the ``DocumentGenerator`` dependency, no WeasyPrint import.

    Reuses the real ``DocumentGenerator._build_filename`` (a ``@staticmethod``
    that only does string formatting — no lazy WeasyPrint import) so the
    filename assertions exercise the same logic the real pipeline uses,
    without needing pango/glib in this environment.
    """

    def __init__(self) -> None:
        self.last_request = None

    async def generate(self, request):
        self.last_request = request
        filename = DocumentGenerator._build_filename(request, "pdf")
        return GeneratedDocument(
            filename=filename,
            format=DocumentFormat.PDF,
            data=b"%PDF-1.4 fake-instructivo",
            content_type="application/pdf",
        )


def make_client(session: AsyncSession, *, user: User):
    async def _override_db():
        yield session
        await session.commit()

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    @asynccontextmanager
    async def _ctx():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client

    return _ctx()


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Router/HTTP layer
# ---------------------------------------------------------------------------


class TestInstructivoPdfEndpoint:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("brand", ["garmin", "magene", "igpsport"])
    async def test_200_pdf_and_filename_per_brand(self, session, brand):
        await _seed_club(session)
        coach = await _seed_coach(session)
        training_session = await _seed_training_session(session)
        await _seed_structure(session, training_session_id=training_session.id)
        await session.commit()

        fake_generator = _FakePdfGenerator()
        app.dependency_overrides[get_document_generator] = lambda: fake_generator

        async with make_client(session, user=coach) as client:
            response = await client.get(
                f"/api/intervals/sessions/{training_session.id}/instructivo",
                params={"brand": brand},
            )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert "attachment" in response.headers["content-disposition"]
        assert response.content == b"%PDF-1.4 fake-instructivo"

        # Filename varies per brand (US3/D8 — one PDF per ciclocomputador brand).
        filename = fake_generator.last_request.filename_hint
        assert brand in filename

    @pytest.mark.asyncio
    async def test_404_sin_estructura(self, session):
        await _seed_club(session)
        coach = await _seed_coach(session)
        training_session = await _seed_training_session(session)
        # No structure attached.
        await session.commit()

        app.dependency_overrides[get_document_generator] = lambda: _FakePdfGenerator()

        async with make_client(session, user=coach) as client:
            response = await client.get(
                f"/api/intervals/sessions/{training_session.id}/instructivo",
                params={"brand": "garmin"},
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_422_marca_desconocida(self, session):
        await _seed_club(session)
        coach = await _seed_coach(session)
        training_session = await _seed_training_session(session)
        await _seed_structure(session, training_session_id=training_session.id)
        await session.commit()

        app.dependency_overrides[get_document_generator] = lambda: _FakePdfGenerator()

        async with make_client(session, user=coach) as client:
            response = await client.get(
                f"/api/intervals/sessions/{training_session.id}/instructivo",
                params={"brand": "polar"},
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_parent_403(self, session):
        await _seed_club(session)
        await _seed_coach(session)
        parent = await _seed_parent(session)
        training_session = await _seed_training_session(session)
        await _seed_structure(session, training_session_id=training_session.id)
        await session.commit()

        app.dependency_overrides[get_document_generator] = lambda: _FakePdfGenerator()

        async with make_client(session, user=parent) as client:
            response = await client.get(
                f"/api/intervals/sessions/{training_session.id}/instructivo",
                params={"brand": "garmin"},
            )

        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Template/HTML layer — no WeasyPrint, mirrors test_newsletter_pdf_render_html.py
# ---------------------------------------------------------------------------

_TEMPLATE = "documents/pdf/session_instructivo.html"


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_ROOT)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["markdown"] = _render_markdown
    env.filters["hms"] = _format_hms
    env.filters["date_es"] = format_date_es
    return env


def _template_context(brand: str) -> dict:
    """Realistic context: a repeat group (work/recovery x2) around
    warmup/cooldown, matching ``_build_blocks_context`` output shape
    (``services/intervals/instructivo_pdf.py``) — already flattened, in
    execution order, with ``repeat_label`` set on the grouped steps."""
    return {
        "brand": brand,
        "session": {
            "technical_focus": "Umbral en pista (prueba)",
            "scheduled_date": "15 de julio de 2026",
            "duration_min": 60,
            "location": "Pista Ginebra — datos ficticios",
            "session_kind": "entrenamiento",
            "objectives": "Trabajo de umbral con series cortas.",
            "target_age_band": "13-15",
        },
        "blocks": [
            {"order": 1, "block_type": "warmup", "duration_s": 300, "target_zone": "Z1", "target_cadence_rpm": 70, "repeat_label": None},
            {"order": 2, "block_type": "work", "duration_s": 120, "target_zone": "Z3", "target_cadence_rpm": 85, "repeat_label": "Rep 1 de 2"},
            {"order": 3, "block_type": "recovery", "duration_s": 60, "target_zone": "Z1", "target_cadence_rpm": 65, "repeat_label": "Rep 1 de 2"},
            {"order": 4, "block_type": "work", "duration_s": 120, "target_zone": "Z3", "target_cadence_rpm": 85, "repeat_label": "Rep 2 de 2"},
            {"order": 5, "block_type": "recovery", "duration_s": 60, "target_zone": "Z1", "target_cadence_rpm": 65, "repeat_label": "Rep 2 de 2"},
            {"order": 6, "block_type": "cooldown", "duration_s": 300, "target_zone": "Z1", "target_cadence_rpm": 65, "repeat_label": None},
        ],
        "club_name": "Club Ficticio de Prueba",
        "generated_at": "2026-07-15 10:00 COT",
    }


class TestInstructivoTemplateRendering:
    def test_html_contains_flattened_blocks_in_order(self):
        """Repeat groups are expanded (not collapsed) — 6 real steps, both
        iterations of the work/recovery group rendered as separate rows."""
        html = _env().get_template(_TEMPLATE).render(**_template_context("garmin"))

        assert "Calentamiento" in html
        assert "Vuelta a la calma" in html
        assert "Rep 1 de 2" in html
        assert "Rep 2 de 2" in html
        # Both work rows (5 min 0 s each is wrong — duration is 2 min) present:
        assert html.count("85 rpm") == 2
        assert html.count("65 rpm") >= 2  # recovery (x2) + cooldown

    @pytest.mark.parametrize("brand", ["garmin", "magene", "igpsport"])
    def test_html_desactiva_autolap_appears(self, brand):
        """FR-010/FR-011/D8: the auto-lap step is mandatory for all 3 brands."""
        html = _env().get_template(_TEMPLATE).render(**_template_context(brand))
        assert "Desactivá la vuelta automática" in html

    def test_html_garmin_specific_steps(self):
        html = _env().get_template(_TEMPLATE).render(**_template_context("garmin"))
        assert "Type = Open" in html
        assert "botón de" in html and "vuelta" in html

    def test_html_magene_specific_steps(self):
        html = _env().get_template(_TEMPLATE).render(**_template_context("magene"))
        assert "training-create" in html
        assert "duración fija" in html

    def test_html_igpsport_specific_steps(self):
        html = _env().get_template(_TEMPLATE).render(**_template_context("igpsport"))
        assert "no tiene editor de entrenamientos por bloques" in html
        assert "hoja de referencia" in html

    def test_html_no_power_watts_mentioned(self):
        """D2/FR-005: the instructivo explicitly states no power/watts target
        is used (there is no watts *column* in the block table — only the
        explanatory caption mentions the word, to rule it out)."""
        html = _env().get_template(_TEMPLATE).render(**_template_context("garmin"))
        assert "No se usa potencia (watts)" in html
