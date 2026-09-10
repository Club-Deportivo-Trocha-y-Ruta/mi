"""T069 — concurrencia optimista del boletín mensual (feature 041, US5).

Contrato: ``specs/041-multi-coach-governance/contracts/concurrency-and-approvals.md``
§1 (token de versión y ``ETag``), §2 (precondición del PATCH, tabla de
resolución §2.2, escritura guardada §2.3, errores §2.5) y §2.6 (qué escrituras
mueven ``edit_version``). Cubre los casos 1–7 de §9; el caso 8 (dos sesiones
contra MySQL real) queda marcado ``@pytest.mark.mysql`` y no corre en la vía
offline.

Vía offline: motor aiosqlite in-memory con un subconjunto explícito de tablas
(idioma R-32, igual que ``tests/routers/test_audit_log_api.py``). No se usa la
fixture ``client`` de ``tests/conftest.py`` — esa necesita MySQL real.

Los nombres de atleta, coaches, padre y club vienen del escenario ficticio
compartido (``tests/fixtures/two_coaches.py``): ninguna persona real, ningún
dato de un menor en aserciones ni en mensajes (Ley 1581, CLAUDE.md).
"""
from __future__ import annotations

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
from app.models.user import User

from tests.fixtures.two_coaches import TwoCoachesScenario, seed_two_coaches
from tests.helpers.audit_tables import AUDIT_TABLES

# asyncio_mode = "auto" en pyproject.toml: las pruebas async no necesitan marca.


# ---------------------------------------------------------------------------
# Motor con subconjunto de tablas
# ---------------------------------------------------------------------------

# Ninguno de estos nombres puede repetir uno de AUDIT_TABLES: `create_all` no
# deduplica y la lista repetida tumba el módulo entero.
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
        yield await seed_two_coaches(session)


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
# Siembra de un boletín
# ---------------------------------------------------------------------------


async def _seed_newsletter(
    session_factory: async_sessionmaker[AsyncSession],
    scenario: TwoCoachesScenario,
    *,
    edit_version: int = 4,
    status: NewsletterStatus = NewsletterStatus.draft,
    coach_note: str | None = None,
) -> int:
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        nl = AthleteMonthlyNewsletter(
            athlete_id=scenario.athlete_id,
            year=2026,
            month=8,
            status=status,
            metrics_snapshot={"email_blocks": {}},
            coach_note=coach_note,
            edit_version=edit_version,
            generated_by_user_id=scenario.coach_a_user_id,
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


def _fake_insight(insight_id: int, scenario: TwoCoachesScenario):
    """Insight de carrera mínimo y ficticio, solo para poder llamar a
    ``attach-insights`` (el contenido nunca se inspecciona en estas pruebas)."""
    from app.models.athlete_ai_insight import AthleteAiInsight

    now = datetime.now(timezone.utc)
    return AthleteAiInsight(
        id=insight_id,
        athlete_id=scenario.athlete_id,
        generated_by_user_id=scenario.coach_a_user_id,
        season=2026,
        use_case="race_analysis",
        summary_text="Análisis ficticio.",
        recommendations_json=[],
        metrics_snapshot_json={},
        principles_cited_json=[],
        confidence="medium",
        is_fallback=False,
        model="fake",
        prompt_version="v3",
        coach_approved=True,
        coach_edits_count=0,
        generated_at=now,
        is_active=1,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# §9.1 — Carrera entre dos entrenadores → 409 (SC-006)
# ---------------------------------------------------------------------------


async def test_stale_second_writer_gets_409_and_first_write_survives(
    session_factory, scenario, make_client
) -> None:
    """Regresión SC-006: A y B cargan la v4; A guarda, B queda obsoleto."""
    nl_id = await _seed_newsletter(session_factory, scenario, edit_version=4)

    async with make_client(scenario.coach_a_user_id) as client_a:
        read_a = await client_a.get(_url(scenario.athlete_id, nl_id))
        assert read_a.status_code == 200
        assert read_a.headers["ETag"] == 'W/"4"'
        token_both_read = read_a.headers["ETag"]

        patch_a = await client_a.patch(
            _url(scenario.athlete_id, nl_id),
            headers={"If-Match": token_both_read},
            json={"coach_note": "Sostuviste el ritmo en las subidas largas."},
        )
    assert patch_a.status_code == 200, patch_a.text
    assert patch_a.json()["edit_version"] == 5

    async with make_client(scenario.coach_b_user_id) as client_b:
        patch_b = await client_b.patch(
            _url(scenario.athlete_id, nl_id),
            headers={"If-Match": token_both_read},
            json={"stage_overrides": {"observations": ["Otra observación."]}},
        )
    assert patch_b.status_code == 409
    body = patch_b.json()
    assert body["current_version"] == 5
    assert "Recarga" in body["detail"]

    reloaded = await _reload(session_factory, nl_id)
    assert reloaded.coach_note == "Sostuviste el ritmo en las subidas largas."
    assert reloaded.stage_overrides is None
    assert reloaded.edit_version == 5


# ---------------------------------------------------------------------------
# §9.2 — Camino feliz con If-Match
# ---------------------------------------------------------------------------


async def test_if_match_happy_path_bumps_once_and_refreshes_etag(
    session_factory, scenario, make_client
) -> None:
    nl_id = await _seed_newsletter(session_factory, scenario, edit_version=4)

    async with make_client(scenario.coach_b_user_id) as client:
        resp = await client.patch(
            _url(scenario.athlete_id, nl_id),
            headers={"If-Match": 'W/"4"'},
            json={"coach_note": "Nos vemos en la próxima válida."},
        )

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["edit_version"] == 5
    assert payload["last_edited_by"] == {
        "user_id": scenario.coach_b_user_id,
        "display_name": "Coach Ficticio B",
    }
    assert resp.headers["ETag"] == 'W/"5"'

    reloaded = await _reload(session_factory, nl_id)
    assert reloaded.edit_version == 5
    assert reloaded.last_edited_by_user_id == scenario.coach_b_user_id


async def test_strong_and_weak_etag_forms_are_equivalent(
    session_factory, scenario, make_client
) -> None:
    nl_id = await _seed_newsletter(session_factory, scenario, edit_version=4)

    async with make_client(scenario.coach_a_user_id) as client:
        resp = await client.patch(
            _url(scenario.athlete_id, nl_id),
            headers={"If-Match": '"4"'},  # forma fuerte
            json={"hidden_blocks": ["photos"]},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["edit_version"] == 5


# ---------------------------------------------------------------------------
# §9.3 — expected_version en el body
# ---------------------------------------------------------------------------


async def test_expected_version_body_fallback_behaves_like_header(
    session_factory, scenario, make_client
) -> None:
    nl_id = await _seed_newsletter(session_factory, scenario, edit_version=4)

    async with make_client(scenario.coach_a_user_id) as client:
        ok = await client.patch(
            _url(scenario.athlete_id, nl_id),
            json={"expected_version": 4, "coach_note": "Buen mes."},
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["edit_version"] == 5
        assert ok.headers["ETag"] == 'W/"5"'

        stale = await client.patch(
            _url(scenario.athlete_id, nl_id),
            json={"expected_version": 4, "coach_note": "Otro intento."},
        )
    assert stale.status_code == 409
    assert stale.json()["current_version"] == 5


async def test_expected_version_is_never_persisted_as_a_field(
    session_factory, scenario, make_client
) -> None:
    """``expected_version`` es precondición, nunca payload (§2.1)."""
    nl_id = await _seed_newsletter(session_factory, scenario, edit_version=4)

    async with make_client(scenario.coach_a_user_id) as client:
        resp = await client.patch(
            _url(scenario.athlete_id, nl_id),
            json={"expected_version": 4, "hidden_blocks": ["badges"]},
        )
    assert resp.status_code == 200, resp.text
    reloaded = await _reload(session_factory, nl_id)
    assert reloaded.stage_overrides is None
    assert reloaded.hidden_blocks == ["badges"]
    assert not hasattr(reloaded, "expected_version")


# ---------------------------------------------------------------------------
# §9.4 — Sin precondición → 428 con ETag
# ---------------------------------------------------------------------------


async def test_missing_precondition_returns_428_with_etag(
    session_factory, scenario, make_client
) -> None:
    nl_id = await _seed_newsletter(session_factory, scenario, edit_version=4)

    async with make_client(scenario.coach_a_user_id) as client:
        resp = await client.patch(
            _url(scenario.athlete_id, nl_id),
            json={"coach_note": "Sin versión."},
        )

    assert resp.status_code == 428
    assert resp.headers["ETag"] == 'W/"4"'
    assert "If-Match" in resp.json()["detail"]

    reloaded = await _reload(session_factory, nl_id)
    assert reloaded.edit_version == 4
    assert reloaded.coach_note is None


# ---------------------------------------------------------------------------
# §9.5 — 400: comodín, malformados y desacuerdo header/body
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("headers", "body", "expected_status"),
    [
        ({"If-Match": "*"}, {"coach_note": "x"}, 428),
        ({"If-Match": '"abc"'}, {"coach_note": "x"}, 400),
        ({"If-Match": 'W/""'}, {"coach_note": "x"}, 400),
        ({"If-Match": "4"}, {"expected_version": 5, "coach_note": "x"}, 400),
    ],
    ids=["wildcard", "no-numerico", "vacio", "header-vs-body"],
)
async def test_invalid_preconditions_are_refused(
    session_factory, scenario, make_client, headers, body, expected_status
) -> None:
    """El comodín se rechaza con 428 (§2.2: no hay modo "crear si no existe");
    el resto de formas inválidas con 400."""
    nl_id = await _seed_newsletter(session_factory, scenario, edit_version=4)

    async with make_client(scenario.coach_a_user_id) as client:
        resp = await client.patch(
            _url(scenario.athlete_id, nl_id), headers=headers, json=body
        )

    assert resp.status_code == expected_status, resp.text
    assert "current_version" not in resp.json()
    reloaded = await _reload(session_factory, nl_id)
    assert reloaded.edit_version == 4


async def test_matching_header_and_body_are_accepted(
    session_factory, scenario, make_client
) -> None:
    nl_id = await _seed_newsletter(session_factory, scenario, edit_version=4)

    async with make_client(scenario.coach_a_user_id) as client:
        resp = await client.patch(
            _url(scenario.athlete_id, nl_id),
            headers={"If-Match": '"4"'},
            json={"expected_version": 4, "coach_note": "Coinciden."},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["edit_version"] == 5


# ---------------------------------------------------------------------------
# §9.6 — El estado terminal gana sobre la versión
# ---------------------------------------------------------------------------


async def test_sent_newsletter_is_immutable_even_with_valid_token(
    session_factory, scenario, make_client
) -> None:
    nl_id = await _seed_newsletter(
        session_factory, scenario, edit_version=4, status=NewsletterStatus.sent
    )

    async with make_client(scenario.coach_a_user_id) as client:
        resp = await client.patch(
            _url(scenario.athlete_id, nl_id),
            headers={"If-Match": 'W/"4"'},
            json={"coach_note": "Ya no."},
        )

    assert resp.status_code == 409
    body = resp.json()
    assert "current_version" not in body
    assert "'sent'" in body["detail"]

    reloaded = await _reload(session_factory, nl_id)
    assert reloaded.edit_version == 4
    assert reloaded.coach_note is None


async def test_sent_newsletter_state_guard_runs_before_precondition(
    session_factory, scenario, make_client
) -> None:
    """Sin ``If-Match`` y en estado terminal manda el 409 de estado, no el 428."""
    nl_id = await _seed_newsletter(
        session_factory, scenario, edit_version=4, status=NewsletterStatus.sent
    )

    async with make_client(scenario.coach_a_user_id) as client:
        resp = await client.patch(
            _url(scenario.athlete_id, nl_id), json={"coach_note": "Ya no."}
        )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# §9.7 — Otras escrituras también mueven edit_version (§2.6)
# ---------------------------------------------------------------------------


async def test_approve_bumps_version_and_invalidates_pre_approval_token(
    session_factory, scenario, make_client
) -> None:
    nl_id = await _seed_newsletter(session_factory, scenario, edit_version=4)

    async with make_client(scenario.coach_a_user_id) as client:
        approve = await client.post(
            f"{_url(scenario.athlete_id, nl_id)}/approve", json={}
        )
        assert approve.status_code == 200, approve.text
        assert approve.json()["edit_version"] == 5
        assert approve.json()["approved_by"] == {
            "user_id": scenario.coach_a_user_id,
            "display_name": "Coach Ficticio A",
        }

        stale = await client.patch(
            _url(scenario.athlete_id, nl_id),
            headers={"If-Match": 'W/"4"'},
            json={"coach_note": "Con token viejo."},
        )
    assert stale.status_code == 409
    assert stale.json()["current_version"] == 5


async def test_attach_insights_create_path_starts_at_version_one(
    session_factory, scenario, make_client
) -> None:
    """Camino de creación de ``attach-insights`` (§2.6): la fila nace en v1 y
    con autoría, de modo que el estudio puede hacer PATCH sin un GET extra."""
    async with session_factory() as session:
        session.add(_fake_insight(5001, scenario))
        await session.commit()

    async with make_client(scenario.coach_a_user_id) as client:
        resp = await client.post(
            f"/api/athletes/{scenario.athlete_id}/monthly-newsletters/attach-insights",
            json={"insight_ids": [5001], "year": 2026, "month": 7},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["created"] is True
        new_id = resp.json()["newsletter_id"]

        read = await client.get(_url(scenario.athlete_id, new_id))
    assert read.headers["ETag"] == 'W/"1"'
    assert read.json()["edit_version"] == 1

    created = await _reload(session_factory, new_id)
    assert created.edit_version == 1
    assert created.last_edited_by_user_id == scenario.coach_a_user_id


async def test_attach_insights_update_path_bumps_version(
    session_factory, scenario, make_client
) -> None:
    nl_id = await _seed_newsletter(session_factory, scenario, edit_version=4)
    async with session_factory() as session:
        session.add(_fake_insight(5002, scenario))
        await session.commit()

    async with make_client(scenario.coach_b_user_id) as client:
        resp = await client.post(
            f"/api/athletes/{scenario.athlete_id}/monthly-newsletters/attach-insights",
            json={"insight_ids": [5002], "year": 2026, "month": 8},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["created"] is False

        stale = await client.patch(
            _url(scenario.athlete_id, nl_id),
            headers={"If-Match": 'W/"4"'},
            json={"coach_note": "Token viejo."},
        )

    assert stale.status_code == 409
    assert stale.json()["current_version"] == 5
    reloaded = await _reload(session_factory, nl_id)
    assert reloaded.edit_version == 5
    assert reloaded.last_edited_by_user_id == scenario.coach_b_user_id


async def test_list_endpoint_exposes_edit_version(
    session_factory, scenario, make_client
) -> None:
    """§1.2: la lista trae ``edit_version`` para que el tablero pueda hacer
    PATCH sin un segundo fetch."""
    nl_id = await _seed_newsletter(session_factory, scenario, edit_version=7)

    async with make_client(scenario.coach_a_user_id) as client:
        resp = await client.get(
            f"/api/athletes/{scenario.athlete_id}/monthly-newsletters"
        )
    assert resp.status_code == 200, resp.text
    rows = {row["id"]: row for row in resp.json()}
    assert rows[nl_id]["edit_version"] == 7


# ---------------------------------------------------------------------------
# §9.8 — Concurrencia real (MySQL). No corre en la vía offline.
# ---------------------------------------------------------------------------


@pytest.mark.mysql
async def test_two_sessions_only_one_update_takes_effect(mysql_engine) -> None:
    """Igual que §9.1 pero con el dialecto real y dos sesiones simultáneas.

    Requiere ``TEST_DATABASE_URL`` (mysql+aiomysql, base terminada en
    ``_test``); sqlite no reproduce el bloqueo de fila de InnoDB. Las dos
    sesiones leen la v4; la primera reclama la versión y retiene el candado,
    la segunda queda esperando en su UPDATE y, cuando la primera confirma,
    su ``WHERE edit_version = 4`` ya no encuentra fila.
    """
    import asyncio

    from app.models.user import UserRole
    from app.routers.athlete_monthly_newsletters import _claim_version
    from tests.fixtures.race_history_fixtures import create_user
    from tests.fixtures.two_coaches import ATHLETE_USER_ID

    factory = async_sessionmaker(mysql_engine, expire_on_commit=False)
    async with factory() as session:
        # seed_two_coaches no crea la cuenta del atleta; sqlite no aplica la FK
        # athletes.user_id → users.id, InnoDB sí.
        await create_user(
            session, user_id=ATHLETE_USER_ID, role=UserRole.athlete, can_login=False
        )
        scenario = await seed_two_coaches(session)
    try:
        nl_id = await _seed_newsletter(factory, scenario, edit_version=4)
        now = datetime.now(timezone.utc)

        async with factory() as session_a, factory() as session_b:
            nl_a = await session_a.get(AthleteMonthlyNewsletter, nl_id)
            nl_b = await session_b.get(AthleteMonthlyNewsletter, nl_id)
            assert nl_a.edit_version == nl_b.edit_version == 4

            assert await _claim_version(
                session_a, nl_a, 4, scenario.coach_a_user_id, now
            )
            claim_b = asyncio.create_task(
                _claim_version(session_b, nl_b, 4, scenario.coach_b_user_id, now)
            )
            await asyncio.sleep(0.5)
            assert not claim_b.done(), "el UPDATE de B debía esperar el candado de fila"

            await session_a.commit()
            assert await asyncio.wait_for(claim_b, timeout=10) is False
            await session_b.rollback()

        reloaded = await _reload(factory, nl_id)
        assert reloaded.edit_version == 5
        assert reloaded.last_edited_by_user_id == scenario.coach_a_user_id
    finally:
        # La base del carril es compartida por toda la sesión de pytest y los
        # ids fijos de R-32 chocan con otras pruebas mysql (p. ej. el 901).
        from sqlalchemy import text as sa_text

        async with mysql_engine.begin() as conn:
            await conn.execute(sa_text("SET FOREIGN_KEY_CHECKS = 0"))
            for stmt in (
                "DELETE FROM athlete_monthly_newsletters WHERE athlete_id = :athlete",
                "DELETE FROM parent_athlete WHERE athlete_id = :athlete",
                "DELETE FROM athletes WHERE id = :athlete",
                "DELETE FROM club_members WHERE club_id IN (:club, :other_club)",
                "DELETE FROM users WHERE id IN (:admin, :coach_a, :coach_b, "
                ":other_coach, :parent, :athlete_user)",
                "DELETE FROM clubs WHERE id IN (:club, :other_club)",
            ):
                await conn.execute(
                    sa_text(stmt),
                    {
                        "athlete": scenario.athlete_id,
                        "club": scenario.club_id,
                        "other_club": scenario.other_club_id,
                        "admin": scenario.admin_user_id,
                        "coach_a": scenario.coach_a_user_id,
                        "coach_b": scenario.coach_b_user_id,
                        "other_coach": scenario.other_club_coach_user_id,
                        "parent": scenario.parent_user_id,
                        "athlete_user": scenario.athlete_user_id,
                    },
                )
            await conn.execute(sa_text("SET FOREIGN_KEY_CHECKS = 1"))
