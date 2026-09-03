"""Tests del endpoint ``POST .../regenerate-block`` del router de boletines
mensuales individuales (feature 038, T201).

Mismo patrón que la sección ``TestPatchStageLogV2`` de
``test_athlete_monthly_newsletters_router.py`` (T102): DB real (SQLite
in-memory) + ``AsyncClient`` contra ``app.main.app``, con
``dependency_overrides`` en ``get_db``/``get_current_user`` — necesario
porque este endpoint hace varias queries reales encadenadas
(``select_insight``, boletín anterior para el guardrail de solapamiento)
que un ``MagicMock`` no modela bien.

Cubre: 409 si ``status=sent``, 451 sin consentimiento IA, 200 camino feliz
(bloque actualizado + ``block_states[block] == "ai"`` + override del bloque
limpiado), 503 si el proveedor no genera un bloque válido.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db, get_llm_provider, get_prompt_registry
from app.main import app
from app.models import Base
from app.models.athlete import Athlete, FamilyRelationship, ParentAthlete, Sex
from app.models.athlete_newsletter import AthleteMonthlyNewsletter, NewsletterStatus
from app.services.ai.providers.fake import FakeLLMProvider
from app.services.ai.prompts.registry import PromptRegistry

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "athlete_monthly_newsletters",
    "newsletter_delivery_events",
    "parent_athlete",
    "parental_consents",
)

_SNAPSHOT = {
    "email_blocks": {
        "period": {"year": 2026, "month": 6, "label": "Junio 2026"},
        "attendance": {
            "sessions_present": 9,
            "sessions_total": 10,
            "attendance_pct": 90.0,
            "attendance_pct_prev_month": 85.0,
            "streak_sessions": 6,
        },
        "technical": {
            "focos_tecnicos": ["Frenado"],
            "avg_rpe": 6.2,
            "avg_rubric_technique": 3.8,
        },
        "race_results": {"has_races": False, "results": []},
        "badges": {"items": []},
        "calendar": {"next_race_events": []},
    },
    "pdf_only_blocks": {"weekly": [], "next_focus_groups": []},
}


@pytest_asyncio.fixture
async def v2_engine():
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
async def v2_session_factory(v2_engine):
    return async_sessionmaker(v2_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def v2_session(v2_session_factory):
    async with v2_session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def v2_seed(v2_session):
    """Club + admin (coach access) + un atleta ficticio (sin datos reales)."""
    from app.models.club import Club
    from app.models.user import User, UserRole

    now = datetime.now(timezone.utc)
    admin = User(
        id=1,
        email="admin@test.local",
        first_name="Admin",
        last_name="Test",
        role=UserRole.admin,
        is_active=True,
        can_login=True,
        created_at=now,
    )
    club = Club(id=1, name="Club Test", code="CT1", created_at=now)
    v2_session.add_all([admin, club])
    await v2_session.flush()

    athlete_user = User(
        id=2,
        email=None,
        first_name="Atleta",
        last_name="Ficticio",
        role=UserRole.athlete,
        is_active=True,
        can_login=False,
        created_at=now,
    )
    v2_session.add(athlete_user)
    await v2_session.flush()

    athlete = Athlete(
        id=5,
        user_id=2,
        first_name="Atleta",
        last_name="Ficticio",
        birth_date=date(2013, 5, 1),
        sex=Sex.M,
        club_id=1,
        created_by=1,
    )
    v2_session.add(athlete)
    await v2_session.flush()
    await v2_session.commit()
    return SimpleNamespace(admin=admin, club=club, athlete=athlete)


async def _seed_newsletter(session, **overrides) -> AthleteMonthlyNewsletter:
    defaults: dict[str, Any] = dict(
        athlete_id=5,
        year=2026,
        month=6,
        status=NewsletterStatus.draft,
        metrics_snapshot=_SNAPSHOT,
    )
    defaults.update(overrides)
    nl = AthleteMonthlyNewsletter(**defaults)
    session.add(nl)
    await session.flush()
    await session.commit()
    await session.refresh(nl)
    return nl


async def _deny_ai_consent(session, athlete_id: int, parent_user_id: int = 3) -> None:
    """Vincula un padre al atleta SIN consentimiento IA vigente — reproduce
    el escenario 451 de ``athlete_has_ai_processing_consent`` (Ley 1581)."""
    from app.models.user import User, UserRole

    now = datetime.now(timezone.utc)
    parent = User(
        id=parent_user_id,
        email=f"parent{parent_user_id}@test.local",
        first_name="Padre",
        last_name="Test",
        role=UserRole.parent,
        is_active=True,
        can_login=True,
        created_at=now,
    )
    session.add(parent)
    await session.flush()
    session.add(
        ParentAthlete(
            parent_id=parent_user_id,
            athlete_id=athlete_id,
            relationship_type=FamilyRelationship.padre,
        )
    )
    await session.commit()


@pytest_asyncio.fixture
async def v2_client_factory(v2_session):
    made: list[AsyncClient] = []

    def _make(user, *, llm_provider=None) -> AsyncClient:
        async def _override_db():
            yield v2_session

        async def _override_user():
            return user

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = _override_user
        if llm_provider is not None:
            app.dependency_overrides[get_llm_provider] = lambda: llm_provider
            app.dependency_overrides[get_prompt_registry] = lambda: PromptRegistry()
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        made.append(client)
        return client

    yield _make
    for c in made:
        await c.aclose()
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST .../regenerate-block
# ---------------------------------------------------------------------------


class TestRegenerateBlock:
    @pytest.mark.asyncio
    async def test_409_when_sent(self, v2_seed, v2_session, v2_client_factory):
        nl = await _seed_newsletter(v2_session, status=NewsletterStatus.sent)
        client = v2_client_factory(v2_seed.admin)

        async with client as c:
            resp = await c.post(
                f"/api/athletes/5/monthly-newsletters/{nl.id}/regenerate-block",
                json={"block": "stage_title"},
            )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_451_without_ai_consent(self, v2_seed, v2_session, v2_client_factory):
        nl = await _seed_newsletter(v2_session)
        await _deny_ai_consent(v2_session, athlete_id=5)
        client = v2_client_factory(v2_seed.admin)

        async with client as c:
            resp = await c.post(
                f"/api/athletes/5/monthly-newsletters/{nl.id}/regenerate-block",
                json={"block": "stage_title"},
            )
        assert resp.status_code == 451

    @pytest.mark.asyncio
    async def test_happy_path_updates_block_and_clears_override(
        self, v2_seed, v2_session, v2_client_factory
    ):
        nl = await _seed_newsletter(
            v2_session,
            ai_narrative={
                "stage_title": "Título viejo",
                "model": "fake",
                "prompt_version": "athlete_monthly_newsletter_v2",
                "confidence": "medium",
            },
            stage_overrides={"stage_title": "Un override manual del coach"},
        )
        fake = FakeLLMProvider(
            canned_json={"stage_title": "Una etapa de constancia con 9 de 10 sesiones asistidas"}
        )
        client = v2_client_factory(v2_seed.admin, llm_provider=fake)

        async with client as c:
            resp = await c.post(
                f"/api/athletes/5/monthly-newsletters/{nl.id}/regenerate-block",
                json={"block": "stage_title", "instruction": "más corto"},
            )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["stage_log"]["stage_title"] == (
            "Una etapa de constancia con 9 de 10 sesiones asistidas"
        )
        assert data["stage_log"]["block_states"]["stage_title"] == "ai"
        # El override manual del bloque regenerado se limpia.
        assert (data["stage_overrides"] or {}).get("stage_title") is None
        assert "más corto" in fake.last_request.messages[-1].content

    @pytest.mark.asyncio
    async def test_instruction_with_forbidden_name_is_redacted_before_llm(
        self, v2_seed, v2_session, v2_client_factory
    ):
        """Hallazgo de auditoría de privacidad (feature 038): la instrucción
        libre del coach viaja tal cual al prompt del proveedor de IA — a
        diferencia de ``coach_note`` (solo persistido), este texto SIEMPRE
        llega a un tercero externo, así que también debe pasar por el guard
        de redacción de nombres del club (Ley 1581 / CLAUDE.md: nunca un
        nombre real a un proveedor de IA)."""
        nl = await _seed_newsletter(
            v2_session,
            ai_narrative={
                "stage_title": "Título viejo",
                "model": "fake",
                "prompt_version": "athlete_monthly_newsletter_v2",
                "confidence": "medium",
            },
        )
        fake = FakeLLMProvider(
            canned_json={"stage_title": "Una etapa de constancia con 9 de 10 sesiones asistidas"}
        )
        client = v2_client_factory(v2_seed.admin, llm_provider=fake)

        # "Ficticio" es el apellido del atleta sembrado (v2_seed) — parte de
        # los forbidden_names del club (_build_forbidden_names).
        async with client as c:
            resp = await c.post(
                f"/api/athletes/5/monthly-newsletters/{nl.id}/regenerate-block",
                json={
                    "block": "stage_title",
                    "instruction": "menciona que Ficticio fue el más rápido del grupo",
                },
            )

        assert resp.status_code == 200, resp.text
        sent_prompt = fake.last_request.messages[-1].content
        assert "Ficticio" not in sent_prompt
        assert "[REDACTADO]" in sent_prompt

    @pytest.mark.asyncio
    async def test_503_when_provider_leaves_block_untouched(
        self, v2_seed, v2_session, v2_client_factory
    ):
        nl = await _seed_newsletter(
            v2_session,
            ai_narrative={
                "stage_title": "Título original",
                "model": "fake",
                "prompt_version": "athlete_monthly_newsletter_v2",
                "confidence": "medium",
            },
        )
        # canned_json vacío de claves útiles -> el bloque no pasa guardrails
        # (stage_title ausente) -> regenerate_block devuelve None -> 503.
        fake = FakeLLMProvider(canned_json={})
        client = v2_client_factory(v2_seed.admin, llm_provider=fake)

        async with client as c:
            resp = await c.post(
                f"/api/athletes/5/monthly-newsletters/{nl.id}/regenerate-block",
                json={"block": "stage_title"},
            )

        assert resp.status_code == 503
        await v2_session.refresh(nl)
        assert nl.ai_narrative["stage_title"] == "Título original"

