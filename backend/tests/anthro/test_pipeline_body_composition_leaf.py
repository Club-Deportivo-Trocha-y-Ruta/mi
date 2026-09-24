"""Real pipeline run builds the body-composition AI leaf (feature 046, T080 —
privacy-audit F7, spec FR-029).

Before T080 `context.build_context` read `state["body_composition_reading"]`
but nothing set it, so in production the leaf was always `None`. These tests
drive the REAL `POST /api/ai/athletes/{id}/measurements/{rid}/explanation`
→ `anthro.pipeline.run_analysis` path over an in-memory sqlite session; only
the chat model (`build_chat_llm` in `anthro.analyst`/`anthro.critic`), the
consent lookup and the MySQL-only upsert of `persist.py` are replaced (same
seams as `tests/test_ai_consent_enablement.py`). The fake chat model records
every prompt it receives, which is exactly what the provider would get.

Asserted:
- a measurement WITH a counted skinfold set → the analyst prompt carries the
  "Composición corporal (códigos cualitativos)" block, rendered for the
  requested audience (coach band only for coach; family band only for family);
- the leaf is anchored on the analysed measurement (`at_record_id`): the
  first set reads `sets_count` 1 even though a later set exists;
- a measurement WITHOUT a set → no block;
- no millimetre/percentage figure and no name ever reaches the prompt.

Synthetic data only (CLAUDE.md privacy rule).
"""
from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.anthropometry import AnthropometricRecord, MaturationStatus
from app.models.athlete import Athlete, Sex
from app.models.club import ClubRole
from app.models.skinfold_measurement import SkinfoldMeasurement
from app.models.user import UserRole
from app.services.ai.anthro import analyst as anthro_analyst
from app.services.ai.anthro import critic as anthro_critic
from app.services.ai.anthro import persist as anthro_persist
from tests.helpers.audit_tables import AUDIT_TABLES

pytestmark = pytest.mark.asyncio

_TABLES = (
    "athletes",
    "anthropometric_records",
    "skinfold_measurements",
    "growth_reference_lms",
    "athlete_ai_explanations",
    "session_attendance",
    "training_sessions",
    *AUDIT_TABLES,
)

_ATHLETE_ID = 811
_CLUB_ID = 1
_FIRST_NAME = "Deportista"
_LAST_NAME = "Sintética"
_BLOCK_TITLE = "Composición corporal (códigos cualitativos)"
_NUMERIC_LEAK = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|mm\b)")


class _SqliteUpsertShim:
    """Same double as `tests/test_ai_consent_enablement.py`: only the MySQL
    `on_duplicate_key_update` upsert of `persist.py` is translated."""

    def __init__(self, table):
        self._stmt = sqlite_insert(table)

    def values(self, **kwargs):
        self._stmt = self._stmt.values(**kwargs)
        return self

    @property
    def inserted(self):
        return self._stmt.excluded

    def on_duplicate_key_update(self, **kwargs):
        return self._stmt.on_conflict_do_update(
            index_elements=["athlete_id", "anthropometric_record_id", "use_case"],
            set_=kwargs,
        )


def _insight_json(audience: str) -> str:
    return json.dumps(
        {
            "audience": audience,
            "summary_line": "Crecimiento estable dentro de lo esperado para esta fase.",
            "changes": ["La talla y el peso avanzaron de forma gradual."],
            "meaning": ["Este ritmo es compatible con un desarrollo saludable."],
            "next_weeks": ["Mantener la rutina de entrenamiento habitual."],
            "warning_signs": [],
            "confidence": {
                "level": "medium",
                "reason": "Datos suficientes para esta lectura, sin señales de alerta.",
            },
            "data_gaps": [],
            "word_count": 30,
        },
        ensure_ascii=False,
    )


_CRITIC_APPROVE_JSON = '{"verdict": "approve", "violations": []}'


class _Response:
    def __init__(self, text: str) -> None:
        self.content = text


class _RecordingChatModel:
    """Minimal `.ainvoke` double that keeps every prompt it was sent."""

    def __init__(self, text: str, sink: list[str]) -> None:
        self._text = text
        self._sink = sink

    async def ainvoke(self, messages, config=None):
        del config
        parts = messages if isinstance(messages, (list, tuple)) else [messages]
        self._sink.append("\n".join(str(getattr(m, "content", m)) for m in parts))
        return _Response(self._text)


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
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


def _record(record_id: int, evaluation_date: date, *, weight: float, height: float, stage: MaturationStatus):
    return AnthropometricRecord(
        id=record_id,
        athlete_id=_ATHLETE_ID,
        evaluation_date=evaluation_date,
        weight_kg=Decimal(str(weight)),
        standing_height_cm=Decimal(str(height)),
        sitting_height_cm=Decimal("78.0"),
        leg_length_cm=Decimal("72.0"),
        leg_sitting_ratio=Decimal("0.9231"),
        maturity_offset=Decimal("0.5"),
        age_at_phv=Decimal("12.1"),
        maturation_status=stage,
        height_z_score=Decimal("0.4"),
        bmi=Decimal("17.8"),
        bmi_z_score=Decimal("0.1"),
        weight_z_score=Decimal("0.2"),
        height_percentile=Decimal("65.0"),
        bmi_percentile=Decimal("55.0"),
        weight_percentile=Decimal("60.0"),
        evaluated_by=1,
    )


def _set(sum4: float) -> SkinfoldMeasurement:
    return SkinfoldMeasurement(
        athlete_id=_ATHLETE_ID,
        triceps_mm=Decimal("9.0"),
        biceps_mm=Decimal("5.0"),
        subscapular_mm=Decimal("8.0"),
        medial_calf_mm=Decimal("10.0"),
        iliac_crest_mm=Decimal("12.0"),
        supraspinale_mm=Decimal("6.0"),
        sum4_mm=Decimal(str(sum4)),
        body_fat_pct=Decimal("21.4"),
        measured_by=1,
    )


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Contract §5 scenario A (girl, Σ4 32 → 39 with expected growth) plus a
    later measurement without skinfolds."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        s.add(
            Athlete(
                id=_ATHLETE_ID,
                user_id=_ATHLETE_ID,
                first_name=_FIRST_NAME,
                last_name=_LAST_NAME,
                birth_date=date(2013, 6, 1),  # synthetic
                sex=Sex.F,
                club_id=_CLUB_ID,
                created_by=1,
            )
        )
        first = _record(8111, date(2026, 1, 10), weight=38.0, height=148.0, stage=MaturationStatus.circa_phv)
        first.skinfolds = _set(32.0)
        second = _record(8112, date(2026, 6, 10), weight=42.5, height=152.5, stage=MaturationStatus.post_phv)
        second.skinfolds = _set(39.0)
        third = _record(8113, date(2026, 9, 10), weight=43.0, height=153.5, stage=MaturationStatus.post_phv)
        s.add_all([first, second, third])
        await s.commit()
        s.expunge_all()
        yield s
    app.dependency_overrides.clear()


class _PromptSink(list):
    """Prompts sent to the analyst, plus the audience the fake must echo."""

    audience = "family"


@pytest.fixture
def prompts(monkeypatch) -> _PromptSink:
    sink = _PromptSink()
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(anthro_persist, "mysql_insert", _SqliteUpsertShim)
    monkeypatch.setattr(
        anthro_analyst,
        "build_chat_llm",
        lambda *a, **k: _RecordingChatModel(_insight_json(sink.audience), sink),
    )
    monkeypatch.setattr(
        anthro_critic,
        "build_chat_llm",
        lambda *a, **k: _RecordingChatModel(_CRITIC_APPROVE_JSON, []),
    )

    async def _allow(_athlete_id, _db):
        return True

    monkeypatch.setattr("app.routers.ai.athlete_has_ai_processing_consent", _allow)
    return sink


async def _explain(session: AsyncSession, prompts: _PromptSink, record_id: int, audience: str) -> str:
    prompts.audience = audience
    prompts.clear()

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    async def _override_user():
        return SimpleNamespace(
            id=10,
            role=UserRole.coach,
            club_memberships=[SimpleNamespace(club_id=_CLUB_ID, role_in_club=ClubRole.coach)],
        )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/ai/athletes/{_ATHLETE_ID}/measurements/{record_id}/explanation",
            params={"audience": audience},
        )
    assert resp.status_code == 200, resp.text
    assert prompts, "the analyst was never called"
    return prompts[0]


def _block(prompt: str) -> str:
    start = prompt.index(_BLOCK_TITLE)
    return prompt[start : start + 900]


async def test_coach_run_with_a_set_builds_the_leaf(session: AsyncSession, prompts: _PromptSink) -> None:
    prompt = await _explain(session, prompts, 8112, "coach")
    assert _BLOCK_TITLE in prompt
    block = _block(prompt)
    assert "Banda del entrenador: verde" in block
    assert "Sets de pliegues registrados: 2." in block
    assert "un aumento real frente a la medición anterior" in block
    assert "una ganancia esperada asociada a la etapa puberal" in block
    assert not _NUMERIC_LEAK.search(prompt)
    assert _FIRST_NAME not in prompt and _LAST_NAME not in prompt


async def test_family_run_with_a_set_uses_only_the_family_band(
    session: AsyncSession, prompts: _PromptSink
) -> None:
    prompt = await _explain(session, prompts, 8112, "family")
    assert _BLOCK_TITLE in prompt
    block = _block(prompt)
    assert "En su curva esperada" in block
    assert "Banda del entrenador" not in block
    assert "Sets de pliegues registrados" not in block
    assert "referencia poblacional" not in block
    assert not _NUMERIC_LEAK.search(prompt)
    assert _FIRST_NAME not in prompt and _LAST_NAME not in prompt


async def test_leaf_is_anchored_on_the_analysed_measurement(
    session: AsyncSession, prompts: _PromptSink
) -> None:
    """Analysing the first set ignores the later one (no future data)."""
    prompt = await _explain(session, prompts, 8111, "coach")
    block = _block(prompt)
    assert "Sets de pliegues registrados: 1." in block
    assert "sin una medición anterior para comparar" in block


async def test_measurement_without_a_set_has_no_leaf(session: AsyncSession, prompts: _PromptSink) -> None:
    prompt = await _explain(session, prompts, 8113, "coach")
    assert _BLOCK_TITLE not in prompt
