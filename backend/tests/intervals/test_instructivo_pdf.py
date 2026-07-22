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
   including this one. Asserts the block table lists DISTINCT blocks
   WITHOUT flattening repeat groups (no "Rep 1 de 2"/"Rep 2 de 2" badges —
   a repeated group is annotated a single time as "Se repite ×N veces"),
   the per-brand configuration steps (including the iGPSport BCS200 vs.
   no-editor-model distinction), the mandatory "Desactivá la vuelta
   automática" (auto-lap) step present in the render for all three brands
   (FR-010/FR-011, D8), and that the removed "Cómo configurar tu {marca}"
   heading no longer appears.
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
    (``services/intervals/instructivo_pdf.py``) — DISTINCT blocks, NOT
    flattened, in ``position`` order, with ``repeat_group``/``repeat_count``
    set on the two grouped steps so the template annotates the group once
    ("Se repite ×2 veces") instead of expanding it into repeated rows."""
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
            {"order": 1, "block_type": "warmup", "duration_type": "fixed", "duration_s": 300, "target_zone": "Z1", "target_cadence_rpm": 70, "repeat_group": None, "repeat_count": None},
            {"order": 2, "block_type": "work", "duration_type": "fixed", "duration_s": 120, "target_zone": "Z3", "target_cadence_rpm": 85, "repeat_group": 1, "repeat_count": 2},
            {"order": 3, "block_type": "recovery", "duration_type": "fixed", "duration_s": 60, "target_zone": "Z1", "target_cadence_rpm": 65, "repeat_group": 1, "repeat_count": 2},
            {"order": 4, "block_type": "cooldown", "duration_type": "fixed", "duration_s": 300, "target_zone": "Z1", "target_cadence_rpm": 65, "repeat_group": None, "repeat_count": None},
        ],
        "club_name": "Club Ficticio de Prueba",
        "generated_at": "2026-07-15 10:00 COT",
    }


def _template_context_with_open_warmup(brand: str) -> dict:
    """Same session context as ``_template_context`` but the warmup block is
    ``open_lap`` (feature 034) — mirrors ``_build_blocks_context`` output
    shape for an open block: ``duration_s`` is ``None``."""
    ctx = _template_context(brand)
    ctx["blocks"] = [
        {"order": 1, "block_type": "warmup", "duration_type": "open_lap", "duration_s": None, "target_zone": "Z1", "target_cadence_rpm": 70, "repeat_group": None, "repeat_count": None},
        {"order": 2, "block_type": "work", "duration_type": "fixed", "duration_s": 300, "target_zone": "Z2", "target_cadence_rpm": 80, "repeat_group": None, "repeat_count": None},
        {"order": 3, "block_type": "cooldown", "duration_type": "fixed", "duration_s": 300, "target_zone": "Z1", "target_cadence_rpm": 65, "repeat_group": None, "repeat_count": None},
    ]
    return ctx


class TestInstructivoTemplateRendering:
    def test_html_contains_distinct_blocks_not_flattened(self):
        """Repeat groups are NOT expanded into repeated rows — distinct
        blocks are listed once each, in ``position`` order, and the
        work/recovery group is annotated a single time as
        "Se repite ×N veces" (never as "Rep 1 de 2"/"Rep 2 de 2")."""
        html = _env().get_template(_TEMPLATE).render(**_template_context("garmin"))

        assert "Calentamiento" in html
        assert "Vuelta a la calma" in html
        assert "Rep 1 de 2" not in html
        assert "Rep 2 de 2" not in html
        assert "se repite" in html
        assert "&times;2" in html  # repeat_count = 2, annotated once
        # The group annotation row itself appears exactly once (the caption
        # below the table also mentions "se repite" in prose, hence the more
        # specific substring here rather than a blanket count of "se repite"):
        assert html.count("Este conjunto de bloques se repite") == 1
        # Distinct rows only — no flattening, so each target appears once
        # per its single row (work=85rpm once; recovery + cooldown=65rpm twice):
        assert html.count("85 rpm") == 1
        assert html.count("65 rpm") == 2

    @pytest.mark.parametrize("brand", ["garmin", "magene", "igpsport"])
    def test_html_desactiva_autolap_appears(self, brand):
        """FR-010/FR-011/D8: the auto-lap step is mandatory for all 3 brands."""
        html = _env().get_template(_TEMPLATE).render(**_template_context(brand))
        assert "Desactivá la vuelta automática" in html

    @pytest.mark.parametrize("brand", ["garmin", "magene", "igpsport"])
    def test_html_como_configurar_heading_removed(self, brand):
        """The per-brand "Cómo configurar tu {marca}" <h2> heading was
        removed from the template — the per-brand instructions still
        render below, just without that heading."""
        html = _env().get_template(_TEMPLATE).render(**_template_context(brand))
        assert "Cómo configurar tu" not in html

    def test_html_garmin_specific_steps(self):
        html = _env().get_template(_TEMPLATE).render(**_template_context("garmin"))
        assert "Type = Open" in html
        assert "botón de" in html and "vuelta" in html

    def test_html_magene_specific_steps(self):
        html = _env().get_template(_TEMPLATE).render(**_template_context("magene"))
        assert "training-create" in html
        assert "duración fija" in html

    def test_html_igpsport_specific_steps(self):
        """iGPSport support depends on the model: the BCS200 (and other
        models with a training editor) DOES support loading blocks on the
        device, unlike the old blanket "no tiene editor" framing."""
        html = _env().get_template(_TEMPLATE).render(**_template_context("igpsport"))
        assert "BCS200" in html
        assert "sí permite crear el entrenamiento por bloques" in html
        assert "hoja de referencia" in html

    def test_html_no_power_watts_mentioned(self):
        """D2/FR-005: the instructivo explicitly states no power/watts target
        is used (there is no watts *column* in the block table — only the
        explanatory caption mentions the word, to rule it out)."""
        html = _env().get_template(_TEMPLATE).render(**_template_context("garmin"))
        assert "No se usa potencia (watts)" in html

    @pytest.mark.parametrize("brand", ["garmin", "magene", "igpsport"])
    def test_html_open_block_renders_libre_text(self, brand):
        """Feature 034 (T025/T027): an open_lap warmup renders the open-block
        text instead of a duration, for every brand, keeping zone + cadence."""
        html = (
            _env()
            .get_template(_TEMPLATE)
            .render(**_template_context_with_open_warmup(brand))
        )
        assert "Libre — hasta botón de vuelta" in html
        assert "Z1" in html
        assert "70 rpm" in html
        # The fixed sibling blocks still render their duration normally.
        assert "5 min" in html

    def test_html_fixed_blocks_unaffected_by_open_block_conditional(self):
        """Regression: adding the open-block conditional does not change
        the rendering of fixed blocks in a structure that also has an open
        one — durations still show as 'X min Y s' / 'X min' / 'Y s'."""
        html = (
            _env()
            .get_template(_TEMPLATE)
            .render(**_template_context_with_open_warmup("garmin"))
        )
        assert "Libre — hasta botón de vuelta" in html
        # Both fixed blocks (300s = 5 min each) render as "5 min".
        assert html.count("5 min") == 2
