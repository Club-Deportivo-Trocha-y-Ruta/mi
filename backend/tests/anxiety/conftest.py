"""Integration test harness for the anxiety module (feature 017).

Real aiosqlite DB (in-memory) + ``Base.metadata.create_all`` for the anxiety
tables and their dependencies, plus an ``AsyncClient`` factory that overrides
``get_db`` / ``get_current_user`` / the interpretation use case so router tests
exercise real SQL without MySQL or JWT.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.dependencies import (
    get_anxiety_interpretation_use_case,
    get_current_user,
    get_db,
)
from app.main import app
from app.models import Base
from app.models.anxiety_instrument import (
    AnxietyInstrument,
    InstrumentAgeBand,
    InstrumentType,
)
from app.models.athlete import Athlete, Sex
from app.models.parental_consent import ParentalConsent
from app.models.user import User, UserRole
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.providers.fake import FakeLLMProvider
from app.services.ai.use_cases.anxiety_interpretation import (
    AnxietyInterpretationUseCase,
)

_KEYS_DIR = Path("app/data/anxiety_keys")

_TABLES = (
    "users",
    "clubs",
    "athletes",
    "parental_consents",
    "race_series",
    "race_events",
    "anxiety_instruments",
    "anxiety_assessments",
    "anxiety_response_tokens",
    "anxiety_baselines",
)

# A valid interpretation JSON the fake LLM can return.
VALID_INTERPRETATION = {
    "resumen": "Llega con activación moderada respecto a su línea base; foco en el proceso.",
    "por_dimension": {
        "cognitiva": "Preocupación en rango habitual.",
        "somatica": "Activación corporal moderada.",
        "autoconfianza": "Confianza sólida.",
    },
    "estrategias": [
        "Respiración 4-7-8 en el calentamiento.",
        "Fijar 2 metas de proceso para la primera vuelta.",
    ],
    "mensaje_para_el_atleta": "Disfruta y enfócate en tu primera sección; lo demás se acomoda.",
    "banderas": [],
}


def _utc() -> datetime:
    return datetime.now(timezone.utc)


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


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


async def seed_instruments(session: AsyncSession) -> None:
    band = {
        "csai2r": InstrumentAgeBand.band_13_15,
        "sas2": InstrumentAgeBand.band_10_12,
        "csai2": InstrumentAgeBand.import_only,
    }
    for type_ in ("csai2r", "sas2", "csai2"):
        key = json.loads((_KEYS_DIR / f"{type_}.json").read_text(encoding="utf-8"))
        session.add(
            AnxietyInstrument(
                type=InstrumentType(type_),
                version=key["version"],
                age_band=band[type_],
                item_count=key["item_count"],
                scoring_key_json=key,
                is_active=True,
                created_at=_utc(),
                updated_at=_utc(),
            )
        )
    await session.flush()


async def seed_user(
    session: AsyncSession, user_id: int, role: UserRole
) -> User:
    u = User(
        id=user_id,
        email=f"{role.value}{user_id}@test.com",
        hashed_password="x",
        first_name="Test",
        last_name="User",
        role=role,
        is_active=True,
        can_login=True,
        created_at=_utc(),
    )
    session.add(u)
    await session.flush()
    return u


async def seed_athlete(
    session: AsyncSession,
    athlete_id: int,
    birth_date: date,
    *,
    user_id: int,
    club_id: int = 1,
) -> Athlete:
    a = Athlete(
        id=athlete_id,
        user_id=user_id,
        first_name="Atleta",
        last_name=f"N{athlete_id}",
        birth_date=birth_date,
        sex=Sex.M,
        club_id=club_id,
        created_by=1,
    )
    session.add(a)
    await session.flush()
    return a


async def grant_consent(
    session: AsyncSession,
    athlete_id: int,
    parent_user_id: int,
    *,
    psychological: bool = True,
) -> ParentalConsent:
    c = ParentalConsent(
        parent_user_id=parent_user_id,
        athlete_id=athlete_id,
        consent_version="v1",
        consented_at=_utc(),
        psychological_assessment=psychological,
    )
    session.add(c)
    await session.flush()
    return c


def coach_user(user_id: int = 10) -> User:
    return User(
        id=user_id,
        email="coach@test.com",
        hashed_password="x",
        first_name="Coach",
        last_name="User",
        role=UserRole.coach,
        is_active=True,
        can_login=True,
    )


def parent_user(user_id: int = 20) -> User:
    return User(
        id=user_id,
        email="parent@test.com",
        hashed_password="x",
        first_name="Parent",
        last_name="User",
        role=UserRole.parent,
        is_active=True,
        can_login=True,
    )


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------


def make_client(
    session: AsyncSession,
    *,
    user: User | None = None,
    fake_provider: FakeLLMProvider | None = None,
    authed: bool = True,
) -> AsyncClient:
    """Build an AsyncClient with DB/auth/use-case overrides for ``app``."""

    async def _override_db():
        yield session
        await session.commit()

    app.dependency_overrides[get_db] = _override_db

    if authed:
        resolved_user = user or coach_user()

        async def _override_user():
            return resolved_user

        app.dependency_overrides[get_current_user] = _override_user

    provider = fake_provider or FakeLLMProvider(
        canned=json.dumps(VALID_INTERPRETATION)
    )

    def _override_use_case():
        return AnxietyInterpretationUseCase(
            provider=provider, registry=PromptRegistry()
        )

    app.dependency_overrides[get_anxiety_interpretation_use_case] = (
        _override_use_case
    )

    return AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    )


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()
