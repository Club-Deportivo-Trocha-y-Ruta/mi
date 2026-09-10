"""T070 — autoría de la nota del entrenador (feature 041, FR-012).

Contrato: ``specs/041-multi-coach-governance/contracts/concurrency-and-approvals.md``
§3.1 (columnas ``coach_note_author_id`` / ``coach_note_updated_at``) y §3.2 (la
matriz de exposición). Cubre los casos 9–13 de §9.

**La regla que este módulo protege**: el TEXTO de la nota es la voz
institucional del club y la familia ya lo lee; el NOMBRE de quien la escribió
es exclusivo de la superficie de coach/admin. Nunca aparece en
``ParentNewsletterOut``, ni en ``to_parent_dto``, ni en el PDF de la familia,
ni en el correo de la familia.

Vía offline: motor aiosqlite in-memory con un subconjunto explícito de tablas
(idioma R-32). No se usa la fixture ``client`` de ``tests/conftest.py`` — esa
necesita MySQL real.

Todos los nombres son sintéticos (Ley 1581, CLAUDE.md). El apellido del
entrenador de prueba es un token deliberadamente raro para que "aparece cero
veces" sea una aserción real y no una coincidencia.
"""
from __future__ import annotations

import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.athlete_newsletter import AthleteMonthlyNewsletter, NewsletterStatus
from app.models.club import ClubRole
from app.models.user import User, UserRole
from app.services.training.stage_log import _PARENT_DTO_KEYS, StageLog, to_parent_dto

from tests.fixtures.race_history_fixtures import create_user, link_user_to_club
from tests.fixtures.two_coaches import TwoCoachesScenario, seed_two_coaches
from tests.helpers.audit_tables import AUDIT_TABLES

# asyncio_mode = "auto" en pyproject.toml: las pruebas async no necesitan marca.


# Apellido sintético del entrenador autor: token distintivo que no aparece en
# ninguna plantilla ni en el resto del escenario, así "cero ocurrencias" es
# comprobable de verdad.
AUTHOR_LAST_NAME = "Quindalabra"
AUTHOR_FIRST_NAME = "Entrenadora"
AUTHOR_USER_ID = 951

COACH_NOTE = "Este mes sostuviste el ritmo en las subidas largas."


# ---------------------------------------------------------------------------
# Motor con subconjunto de tablas
# ---------------------------------------------------------------------------

# Ningún nombre de esta lista puede repetir uno de AUDIT_TABLES: `create_all`
# no deduplica y un duplicado tumba el módulo entero.
_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parent_athlete",
    "password_reset_tokens",
    "athlete_monthly_newsletters",
    "newsletter_delivery_events",
    "parental_consents",
    "athlete_ai_insights",
    "race_events",
    *AUDIT_TABLES,
)


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[name] for name in _TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def scenario(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[TwoCoachesScenario, None]:
    async with session_factory() as session:
        sc = await seed_two_coaches(session)
        # Entrenadora adicional con apellido distintivo — la autora de la nota.
        author = await create_user(
            session,
            user_id=AUTHOR_USER_ID,
            role=UserRole.coach,
            first_name=AUTHOR_FIRST_NAME,
            last_name=AUTHOR_LAST_NAME,
        )
        await link_user_to_club(
            session,
            user_id=author.id,
            club_id=sc.club_id,
            role_in_club=ClubRole.coach,
        )
        await session.commit()
        yield sc


@pytest_asyncio.fixture
async def make_client(session_factory: async_sessionmaker[AsyncSession]):
    """Fábrica ``make_client(user_id)`` con ``club_memberships`` reales."""

    @asynccontextmanager
    async def _make(user_id: int) -> AsyncGenerator[AsyncClient, None]:
        async with session_factory() as load_session:
            result = await load_session.execute(
                select(User)
                .options(selectinload(User.club_memberships))
                .where(User.id == user_id)
            )
            actor = result.scalar_one()

        async def _override_db() -> AsyncGenerator[AsyncSession, None]:
            async with session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: actor
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                yield ac
        finally:
            app.dependency_overrides.clear()

    return _make


# ---------------------------------------------------------------------------
# Helpers de siembra
# ---------------------------------------------------------------------------


def _stage_log(coach_note: str | None) -> StageLog:
    """``StageLog`` mínimo y ficticio, con la nota del entrenador incluida."""
    return StageLog(
        stage_number=8,
        period_label="Agosto 2026",
        athlete_first_name="Mariana",
        athlete_reference="ella",
        stage_title="Etapa de montaña",
        coach_note=coach_note,
    )


async def _seed_newsletter(
    session_factory: async_sessionmaker[AsyncSession],
    scenario: TwoCoachesScenario,
    *,
    status: NewsletterStatus = NewsletterStatus.draft,
    coach_note: str | None = None,
    coach_note_author_id: int | None = None,
    edit_version: int = 4,
) -> int:
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        nl = AthleteMonthlyNewsletter(
            athlete_id=scenario.athlete_id,
            year=2026,
            month=8,
            status=status,
            metrics_snapshot={"email_blocks": {}},
            stage_log_json=_stage_log(coach_note).model_dump(mode="json"),
            coach_note=coach_note,
            coach_note_author_id=coach_note_author_id,
            coach_note_updated_at=now if coach_note_author_id else None,
            edit_version=edit_version,
            generated_by_user_id=scenario.coach_a_user_id,
            sent_at=now if status == NewsletterStatus.sent else None,
            created_at=now,
            updated_at=now,
        )
        session.add(nl)
        await session.commit()
        return nl.id


async def _reload(
    session_factory: async_sessionmaker[AsyncSession], newsletter_id: int
) -> AthleteMonthlyNewsletter:
    async with session_factory() as session:
        return (
            await session.execute(
                select(AthleteMonthlyNewsletter).where(
                    AthleteMonthlyNewsletter.id == newsletter_id
                )
            )
        ).scalar_one()


def _url(athlete_id: int, newsletter_id: int) -> str:
    return f"/api/athletes/{athlete_id}/monthly-newsletters/{newsletter_id}"


# ---------------------------------------------------------------------------
# §9.9 — El PATCH escribe autor y fecha; otro entrenador los reescribe
# ---------------------------------------------------------------------------


async def test_patch_records_author_and_timestamp(
    session_factory, scenario, make_client
) -> None:
    nl_id = await _seed_newsletter(session_factory, scenario)
    before = datetime.now(timezone.utc).replace(tzinfo=None)

    async with make_client(AUTHOR_USER_ID) as client:
        resp = await client.patch(
            _url(scenario.athlete_id, nl_id),
            headers={"If-Match": 'W/"4"'},
            json={"coach_note": COACH_NOTE},
        )
    assert resp.status_code == 200, resp.text

    row = await _reload(session_factory, nl_id)
    assert row.coach_note == COACH_NOTE
    assert row.coach_note_author_id == AUTHOR_USER_ID
    assert row.coach_note_updated_at is not None
    assert row.coach_note_updated_at >= before


async def test_second_coach_rewrites_both_author_columns(
    session_factory, scenario, make_client
) -> None:
    nl_id = await _seed_newsletter(session_factory, scenario)

    async with make_client(AUTHOR_USER_ID) as client:
        first = await client.patch(
            _url(scenario.athlete_id, nl_id),
            headers={"If-Match": 'W/"4"'},
            json={"coach_note": COACH_NOTE},
        )
    assert first.status_code == 200, first.text
    first_time = (await _reload(session_factory, nl_id)).coach_note_updated_at

    async with make_client(scenario.coach_b_user_id) as client:
        second = await client.patch(
            _url(scenario.athlete_id, nl_id),
            headers={"If-Match": 'W/"5"'},
            json={"coach_note": "Nos vemos en la próxima válida."},
        )
    assert second.status_code == 200, second.text

    row = await _reload(session_factory, nl_id)
    assert row.coach_note_author_id == scenario.coach_b_user_id
    assert row.coach_note_updated_at >= first_time


# ---------------------------------------------------------------------------
# §9.13 — Borrar la nota también deja actor y hora
# ---------------------------------------------------------------------------


async def test_clearing_the_note_still_records_the_actor(
    session_factory, scenario, make_client
) -> None:
    """``coach_note: null`` es una edición con autor: "quién la borró" tiene
    que quedar respondido (§3.1)."""
    nl_id = await _seed_newsletter(
        session_factory,
        scenario,
        coach_note=COACH_NOTE,
        coach_note_author_id=AUTHOR_USER_ID,
    )

    async with make_client(scenario.coach_b_user_id) as client:
        resp = await client.patch(
            _url(scenario.athlete_id, nl_id),
            headers={"If-Match": 'W/"4"'},
            json={"coach_note": None},
        )
    assert resp.status_code == 200, resp.text

    row = await _reload(session_factory, nl_id)
    assert row.coach_note is None
    assert row.coach_note_author_id == scenario.coach_b_user_id
    assert row.coach_note_updated_at is not None


# ---------------------------------------------------------------------------
# §9.10 — El autor se ve solo del lado del entrenador
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("actor", ["coach", "admin"])
async def test_author_visible_to_coach_and_admin(
    session_factory, scenario, make_client, actor
) -> None:
    nl_id = await _seed_newsletter(
        session_factory,
        scenario,
        coach_note=COACH_NOTE,
        coach_note_author_id=AUTHOR_USER_ID,
    )
    user_id = (
        scenario.coach_a_user_id if actor == "coach" else scenario.admin_user_id
    )

    async with make_client(user_id) as client:
        resp = await client.get(_url(scenario.athlete_id, nl_id))

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["coach_note"] == COACH_NOTE
    assert payload["coach_note_author"] == {
        "user_id": AUTHOR_USER_ID,
        "display_name": f"{AUTHOR_FIRST_NAME} {AUTHOR_LAST_NAME}",
    }
    assert payload["coach_note_updated_at"] is not None


async def test_author_absent_from_parent_surface(
    session_factory, scenario, make_client
) -> None:
    """La familia lee la nota, nunca el nombre de quien la escribió (§3.2)."""
    nl_id = await _seed_newsletter(
        session_factory,
        scenario,
        status=NewsletterStatus.sent,
        coach_note=COACH_NOTE,
        coach_note_author_id=AUTHOR_USER_ID,
    )

    async with make_client(scenario.parent_user_id) as client:
        resp = await client.get(
            f"/api/parents/me/athletes/{scenario.athlete_id}/newsletters/{nl_id}"
        )

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    # La nota SÍ llega — es la voz institucional del club.
    assert payload["stage_log"]["coach_note"] == COACH_NOTE
    # El autor no, en ninguna forma ni en ningún nivel del árbol.
    serialized = resp.text
    assert not re.search(r"coach_note_author", serialized)
    assert not re.search(r"coach_note_updated_at", serialized)
    assert AUTHOR_LAST_NAME not in serialized
    assert AUTHOR_FIRST_NAME not in serialized


def test_parent_newsletter_schema_has_no_author_field() -> None:
    """Barrera de schema: ``ParentNewsletterOut`` ni siquiera declara el campo."""
    from app.schemas.parent_newsletter import ParentNewsletterOut

    for name in ParentNewsletterOut.model_fields:
        assert "coach_note_author" not in name
        assert "coach_note_updated_at" not in name


# ---------------------------------------------------------------------------
# §9.11 — to_parent_dto sigue siendo un allow-list cerrado
# ---------------------------------------------------------------------------


def test_to_parent_dto_keys_are_exactly_the_allow_list() -> None:
    """Si mañana alguien agrega un campo de autor a ``StageLog``, esta prueba
    falla antes de que llegue a una superficie de familia."""
    dto = to_parent_dto(_stage_log(COACH_NOTE))
    assert set(dto.keys()) == set(_PARENT_DTO_KEYS)
    assert dto["coach_note"] == COACH_NOTE


def test_stage_log_model_has_no_author_field() -> None:
    """Segunda barrera independiente: el autor no entra a ``StageLog``."""
    for name in StageLog.model_fields:
        assert "author" not in name


def test_stage_log_rejects_an_injected_author_key() -> None:
    """Tercera barrera: ``StageLog`` prohíbe campos extra, así que un
    ``stage_log_json`` manipulado ni siquiera valida — el autor no tiene por
    dónde colarse hacia el DTO del padre."""
    from pydantic import ValidationError

    raw = _stage_log(COACH_NOTE).model_dump(mode="json")
    raw["coach_note_author"] = {"user_id": AUTHOR_USER_ID, "display_name": "X"}
    with pytest.raises(ValidationError):
        StageLog.model_validate(raw)


# ---------------------------------------------------------------------------
# §9.12 — El PDF y el correo de la familia no llevan el nombre del entrenador
# ---------------------------------------------------------------------------


async def test_family_pdf_has_the_note_but_never_the_coach_name() -> None:
    """Renderiza el PDF real de la bitácora y extrae su texto con pdfplumber."""
    import io

    import pdfplumber

    from app.config import settings
    from app.services.notification.athlete_newsletter_pdf import generate_stage_log_pdf
    from app.services.notification.document_generator import DocumentGenerator
    from app.services.notification.template_registry import TemplateRegistry

    generator = DocumentGenerator(TemplateRegistry(), settings)
    doc, _sha = await generate_stage_log_pdf(
        generator=generator,
        athlete_first_name="Mariana",
        athlete_last_name="Ficticia",
        athlete_id=941,
        year=2026,
        month=8,
        stage_log=to_parent_dto(_stage_log(COACH_NOTE)),
    )

    with pdfplumber.open(io.BytesIO(doc.data)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    assert "Nota del entrenador" in text
    assert COACH_NOTE.rstrip(".") in text.replace("\n", " ")
    assert text.count(AUTHOR_LAST_NAME) == 0
    assert text.count(AUTHOR_FIRST_NAME) == 0


def test_family_email_body_has_no_coach_name() -> None:
    """El correo mantiene la fórmula institucional del pie, sin nombre propio."""
    from app.services.notification.newsletter_dispatcher import _render_email_template
    from app.services.notification.template_registry import TemplateRegistry

    context = {
        "parent_name": "Familia Ficticia",
        "month_label": "Agosto 2026",
        "club_name": "Club Ficticio Uno",
        "children": [
            {
                "athlete_first_name": "Mariana",
                "stage_log": to_parent_dto(_stage_log(COACH_NOTE)),
                "cta_url": "https://example.test/bitacora",
                "cta_label": "Ver la bitácora",
            }
        ],
    }
    html = _render_email_template(
        TemplateRegistry(), context, body_path="email/athlete_stage_log.html"
    )

    assert "preparada por el entrenador de" in html
    assert html.count(AUTHOR_LAST_NAME) == 0
    assert html.count(AUTHOR_FIRST_NAME) == 0
    assert "coach_note_author" not in html


def test_family_templates_never_reference_the_author_variable() -> None:
    """Guard estático sobre las dos plantillas de familia: el identificador
    ``coach_note_author`` no aparece fuera de un comentario Jinja."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "templates"
    for rel in (
        "documents/pdf/athlete_stage_log.html",
        "email/athlete_stage_log.html",
    ):
        source = (root / rel).read_text(encoding="utf-8")
        # Se quitan los comentarios Jinja ({# ... #}), donde la mención es
        # deliberada y documenta justamente esta prohibición.
        without_comments = re.sub(r"\{#.*?#\}", "", source, flags=re.DOTALL)
        assert "coach_note_author" not in without_comments, rel
        assert "coach_note_updated_at" not in without_comments, rel
