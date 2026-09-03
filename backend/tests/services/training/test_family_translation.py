"""Tests para ``family_translation.py`` (feature 038, T103).

Cobertura:

- ``filter_for_family``: descarta observaciones de dominio ``field`` y
  acciones de prioridad ``low``; elige la de mayor prioridad respetando
  el orden de aparición en empate; retorna ``None`` sin acción elegible.
- ``select_insight``: sin consentimiento retorna ``None`` sin consultar la
  DB; respeta el orden de ``selected_race_insight_ids``; salta insights
  inactivos / sin ``structured_json``; descarta eventos fuera del mes del
  boletín.

Estrategia: SQLite async in-memory real (mismo patrón que
``tests/routers/test_athlete_race_analysis.py``), reutilizando
``tests/fixtures/race_history_fixtures.py``.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock

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
from app.models.athlete_newsletter import AthleteMonthlyNewsletter, NewsletterStatus
from app.models.user import UserRole
from app.services.race.insight_v3 import (
    ActionCategory,
    ActionV3,
    EvidenceDomain,
    FieldReading,
    Horizon,
    InsightV3,
    Observation,
    Priority,
)
from app.services.training.family_translation import (
    FamilyInsightInput,
    _eligible_observations,
    filter_for_family,
    select_insight,
)

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_insight,
    create_race_event,
    create_race_series,
    create_user,
)


# ---------------------------------------------------------------------------
# Helpers InsightV3
# ---------------------------------------------------------------------------


def _observation(
    claim: str = "El deportista mejoró su ritmo en subida.",
    domain: EvidenceDomain = EvidenceDomain.TRAINING,
) -> Observation:
    return Observation(
        claim=claim,
        evidence=["8.6% más rápido que la válida anterior"],
        domain=domain,
    )


def _action(
    text: str = "Practicar 2 sesiones de técnica de frenado por semana.",
    priority: Priority = Priority.MED,
    category: ActionCategory = ActionCategory.TECHNIQUE,
) -> ActionV3:
    return ActionV3(
        text=text,
        category=category,
        priority=priority,
        horizon=Horizon.NEXT_WEEK,
    )


def _insight_v3(
    *,
    headline: str = "El deportista mejoró su consistencia en curvas técnicas.",
    observations: list[Observation] | None = None,
    actions: list[ActionV3] | None = None,
) -> InsightV3:
    return InsightV3(
        headline=headline,
        observations=observations
        or [_observation(), _observation(domain=EvidenceDomain.RACE)],
        actions=actions
        or [_action(), _action(text="Segunda acción de relleno", priority=Priority.MED)],
        coach_question="¿El deportista duerme bien la noche antes de competir?",
    )


# ---------------------------------------------------------------------------
# filter_for_family
# ---------------------------------------------------------------------------


class TestFilterForFamily:
    def test_drops_field_domain_observations(self) -> None:
        """``_eligible_observations`` descarta dominio 'field' (AC-3.2)."""
        insight = _insight_v3(
            observations=[
                _observation(domain=EvidenceDomain.FIELD),
                _observation(claim="Segunda observación", domain=EvidenceDomain.TRAINING),
            ]
        )
        remaining = _eligible_observations(insight)
        assert len(remaining) == 1
        assert remaining[0].domain == EvidenceDomain.TRAINING

    def test_drops_low_priority_actions(self) -> None:
        insight = _insight_v3(
            actions=[
                _action(text="Acción de baja prioridad", priority=Priority.LOW),
                _action(text="Acción elegible", priority=Priority.MED),
            ]
        )
        result = filter_for_family(insight)
        assert result is not None
        assert result.action_text == "Acción elegible"

    def test_returns_none_when_no_eligible_action(self) -> None:
        """Todas las acciones son 'low' → no hay lectura publicable."""
        insight = _insight_v3(
            actions=[
                _action(text="Primera, baja", priority=Priority.LOW),
                _action(text="Segunda, baja", priority=Priority.LOW),
            ]
        )
        assert filter_for_family(insight) is None

    def test_picks_highest_priority_action(self) -> None:
        insight = _insight_v3(
            actions=[
                _action(text="Prioridad media", priority=Priority.MED),
                _action(text="Prioridad alta", priority=Priority.HIGH),
                _action(text="Baja, descartada", priority=Priority.LOW),
            ]
        )
        result = filter_for_family(insight)
        assert result is not None
        assert result.action_text == "Prioridad alta"

    def test_tie_keeps_first_in_appearance_order(self) -> None:
        insight = _insight_v3(
            actions=[
                _action(text="Primera alta", priority=Priority.HIGH),
                _action(text="Segunda alta", priority=Priority.HIGH),
            ]
        )
        result = filter_for_family(insight)
        assert result is not None
        assert result.action_text == "Primera alta"

    def test_valida_label_defaults_empty_and_can_be_supplied(self) -> None:
        insight = _insight_v3()
        assert filter_for_family(insight).valida_label == ""
        result = filter_for_family(insight, valida_label="Válida III — Cali")
        assert result is not None
        assert result.valida_label == "Válida III — Cali"

    def test_output_shape_is_family_insight_input(self) -> None:
        insight = _insight_v3(headline="Titular de prueba")
        result = filter_for_family(insight)
        assert isinstance(result, FamilyInsightInput)
        assert result.headline == "Titular de prueba"
        assert result.action_category == ActionCategory.TECHNIQUE.value

    def test_adversarial_field_reading_and_coach_only_data_never_leak(self) -> None:
        """Auditoría de privacidad (feature 038): aunque el ``InsightV3`` de
        entrada traiga poblados TODOS los campos coach-only (comparación con
        el pelotón, señales a vigilar, vacíos de datos, pregunta abierta al
        coach y una acción derivada de una observación con ese contenido),
        ``filter_for_family`` nunca debe dejarlos llegar a la familia — ni
        siquiera indirectamente, vía ``model_dump()``.

        ``FamilyInsightInput`` ya usa ``extra='forbid'`` (garantía a nivel
        de tipo), pero este test es la defensa "en negro": asume que el
        recorte pudiera fallar en el futuro y verifica el resultado
        serializado, no solo la clase.
        """
        secret_field_reading = FieldReading(
            percentile=87.0,
            expected_position=3,
            actual_position=1,
            delta_vs_expected=2,
            series_label="Prejuvenil A Masculino — SECRETO_PELOTON",
            summary="SECRETO_PELOTON: por delante del percentil esperado del grupo.",
        )
        insight = InsightV3(
            headline="El deportista mejoró su consistencia en curvas técnicas.",
            field_reading=secret_field_reading,
            observations=[
                _observation(claim="Observación de pista", domain=EvidenceDomain.FIELD),
                _observation(domain=EvidenceDomain.TRAINING),
            ],
            actions=[
                ActionV3(
                    text="Acción elegible para familia",
                    category=ActionCategory.TECHNIQUE,
                    priority=Priority.HIGH,
                    horizon=Horizon.NEXT_WEEK,
                    derived_from=0,  # deriva de la observación de dominio field
                ),
                _action(text="Acción de relleno de baja prioridad", priority=Priority.LOW),
            ],
            watch_signals=["SECRETO_VIGILAR: comparar con el líder de la categoría"],
            coach_question="SECRETO_COACH: ¿cómo va el sueño la noche antes de competir?",
            data_gaps=["SECRETO_GAP: falta el split de la vuelta 2"],
        )

        result = filter_for_family(insight, valida_label="Válida III — Cali")
        assert result is not None

        dumped = result.model_dump()
        assert set(dumped.keys()) == {
            "headline",
            "action_text",
            "action_category",
            "valida_label",
        }

        serialized = " ".join(str(v) for v in dumped.values())
        for forbidden_marker in (
            "SECRETO_PELOTON",
            "SECRETO_VIGILAR",
            "SECRETO_COACH",
            "SECRETO_GAP",
            "percentile",
            "expected_position",
            "derived_from",
        ):
            assert forbidden_marker not in serialized, (
                f"{forbidden_marker!r} se filtró a FamilyInsightInput"
            )


# ---------------------------------------------------------------------------
# select_insight — fixtures DB
# ---------------------------------------------------------------------------


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
        for t in (
            "users",
            "clubs",
            "athletes",
            "race_series",
            "race_events",
            "athlete_ai_insights",
            "athlete_monthly_newsletters",
        )
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def _utc(y: int = 2026, m: int = 6, d: int = 10) -> datetime:
    return datetime(y, m, d, tzinfo=timezone.utc)


def _newsletter(
    *,
    athlete_id: int = 144,
    year: int = 2026,
    month: int = 6,
    selected_race_insight_ids: list[int] | None,
) -> AthleteMonthlyNewsletter:
    now = _utc(year, month)
    return AthleteMonthlyNewsletter(
        athlete_id=athlete_id,
        year=year,
        month=month,
        status=NewsletterStatus.draft,
        selected_race_insight_ids=selected_race_insight_ids,
        created_at=now,
        updated_at=now,
    )


def _structured_json(**overrides) -> dict:
    return _insight_v3(**overrides).model_dump(mode="json")


# ---------------------------------------------------------------------------
# select_insight
# ---------------------------------------------------------------------------


class TestSelectInsight:
    @pytest.mark.asyncio
    async def test_no_consent_returns_none_without_queries(self) -> None:
        """Sin consentimiento IA: ``None`` inmediato, sin tocar la DB."""
        db = AsyncMock()
        newsletter = _newsletter(selected_race_insight_ids=[1, 2])
        result = await select_insight(db, newsletter, athlete_has_ai_consent=False)
        assert result is None
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_selected_ids_returns_none(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            newsletter = _newsletter(selected_race_insight_ids=None)
            result = await select_insight(session, newsletter, athlete_has_ai_consent=True)
            assert result is None

    @pytest.mark.asyncio
    async def test_event_outside_month_returns_none(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            await create_club(session)
            await create_user(session, user_id=10, role=UserRole.coach)
            await create_user(session, user_id=144, role=UserRole.athlete, can_login=False)
            await create_athlete(session, athlete_id=144, user_id=144, created_by=10)
            await create_race_series(session, series_id=1, season_year=2026)
            # Evento en mayo, boletín es de junio.
            await create_race_event(
                session, event_id=1, series_id=1, sequence_number=1,
                event_date=date(2026, 5, 15), created_by_user_id=10,
            )
            insight = await create_insight(
                session,
                athlete_id=144,
                event_id=1,
                is_active=1,
                structured_json=_structured_json(),
            )
            await session.commit()

            newsletter = _newsletter(
                athlete_id=144, year=2026, month=6,
                selected_race_insight_ids=[insight.id],
            )
            result = await select_insight(session, newsletter, athlete_has_ai_consent=True)
            assert result is None

    @pytest.mark.asyncio
    async def test_inactive_or_missing_structured_json_skips_to_next_id(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            await create_club(session)
            await create_user(session, user_id=10, role=UserRole.coach)
            await create_user(session, user_id=144, role=UserRole.athlete, can_login=False)
            await create_athlete(session, athlete_id=144, user_id=144, created_by=10)
            await create_race_series(session, series_id=1, season_year=2026)
            await create_race_event(
                session, event_id=1, series_id=1, sequence_number=1,
                event_date=date(2026, 6, 5), created_by_user_id=10,
            )
            await create_race_event(
                session, event_id=2, series_id=1, sequence_number=2,
                event_date=date(2026, 6, 20), created_by_user_id=10,
            )
            # id=1: inactivo (superado) — se salta.
            inactive = await create_insight(
                session,
                athlete_id=144,
                event_id=1,
                valida_num=1,
                is_active=None,
                deprecated_at=_utc(),
                superseded_by_insight_id=None,
                structured_json=_structured_json(),
            )
            # id=2: activo pero sin structured_json (v1/v2) — se salta.
            no_structured = await create_insight(
                session,
                athlete_id=144,
                event_id=1,
                valida_num=2,
                is_active=1,
                structured_json=None,
            )
            # id=3: activo + structured_json + evento en el mes → elegible.
            eligible = await create_insight(
                session,
                athlete_id=144,
                event_id=2,
                valida_num=3,
                is_active=1,
                structured_json=_structured_json(headline="El elegible"),
            )
            await session.commit()

            newsletter = _newsletter(
                athlete_id=144, year=2026, month=6,
                selected_race_insight_ids=[inactive.id, no_structured.id, eligible.id],
            )
            result = await select_insight(session, newsletter, athlete_has_ai_consent=True)
            assert result is not None
            insight_id, parsed = result
            assert insight_id == eligible.id
            assert parsed.headline == "El elegible"

    @pytest.mark.asyncio
    async def test_respects_selected_race_insight_ids_order(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            await create_club(session)
            await create_user(session, user_id=10, role=UserRole.coach)
            await create_user(session, user_id=144, role=UserRole.athlete, can_login=False)
            await create_athlete(session, athlete_id=144, user_id=144, created_by=10)
            await create_race_series(session, series_id=1, season_year=2026)
            await create_race_event(
                session, event_id=1, series_id=1, sequence_number=1,
                event_date=date(2026, 6, 5), created_by_user_id=10,
            )
            await create_race_event(
                session, event_id=2, series_id=1, sequence_number=2,
                event_date=date(2026, 6, 20), created_by_user_id=10,
            )
            first = await create_insight(
                session, athlete_id=144, event_id=1, valida_num=1, is_active=1,
                structured_json=_structured_json(headline="Primero en la lista"),
            )
            second = await create_insight(
                session, athlete_id=144, event_id=2, valida_num=2, is_active=1,
                structured_json=_structured_json(headline="Segundo en la lista"),
            )
            await session.commit()

            # El orden en selected_race_insight_ids pone 'second' primero.
            newsletter = _newsletter(
                athlete_id=144, year=2026, month=6,
                selected_race_insight_ids=[second.id, first.id],
            )
            result = await select_insight(session, newsletter, athlete_has_ai_consent=True)
            assert result is not None
            insight_id, parsed = result
            assert insight_id == second.id
            assert parsed.headline == "Segundo en la lista"

    @pytest.mark.asyncio
    async def test_no_eligible_insight_returns_none(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            await create_club(session)
            await create_user(session, user_id=10, role=UserRole.coach)
            await create_user(session, user_id=144, role=UserRole.athlete, can_login=False)
            await create_athlete(session, athlete_id=144, user_id=144, created_by=10)
            newsletter = _newsletter(
                athlete_id=144, year=2026, month=6,
                selected_race_insight_ids=[999],
            )
            result = await select_insight(session, newsletter, athlete_has_ai_consent=True)
            assert result is None
