"""Tests for the newsletter "Composición corporal" PDF block (feature 046, T076).

Source of truth: ``specs/046-body-composition-skinfolds/contracts/body-composition-reading.md``
(family projection, §4 copy) plus ``specs/046-body-composition-skinfolds/tasks.md`` T076.

Cubre:
(a) El bloque solo aparece en el mes de la ``evaluation_date`` de un set
    **contado**; ausente en otro mes sin toma y en el mes cuya única toma
    fue declinada por completo.
(b) El bloque tiene exactamente las claves ``{family_label, family_sentence,
    notice_text}``.
(c) Fixture rojo (patrón de disponibilidad energética) -> copy ámbar.
(d) Fixture de referencia únicamente (single set, tríceps >= P95) -> copy
    verde (family projection §3c: un ámbar solo por referencia se ve como
    verde para la familia).
(e) El PDF de bitácora renderizado contiene "Composición corporal" y el
    aviso del mes de la toma, y no contiene cifras (``%``/``mm``) ni
    "Requiere acompañamiento profesional" (frase exclusiva del coach).
(f) El contexto/solicitud que recibe el proveedor de IA (fake) nunca
    contiene ``body_composition``, ``family_band``, "pliegue" ni un código
    de banda.

Todos los datos son ficticios (CLAUDE.md §Privacidad): ningún nombre real,
fecha de nacimiento real ni nota de un menor aparece en este archivo.
"""
from __future__ import annotations

import io
import re
from datetime import date
from decimal import Decimal
from typing import AsyncGenerator

import pdfplumber
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
from app.models.anthropometry import AnthropometricRecord, MaturationStatus
from app.models.athlete import Athlete, Sex
from app.models.growth import GrowthIndicator, GrowthReferenceLms, GrowthSource
from app.models.skinfold_measurement import SkinfoldMeasurement
from app.services.body_composition import FAMILY_COPY, NEWSLETTER_NOTICE
from app.services.training.newsletter_builder import _build_body_composition_block
from tests.helpers.audit_tables import AUDIT_TABLES

_MEASURED_BY = 1
_EVALUATED_BY = 1


# ---------------------------------------------------------------------------
# Fixtures: motor SQLite in-memory + sesión
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
            "athletes",
            "anthropometric_records",
            "skinfold_measurements",
            "growth_reference_lms",
            *AUDIT_TABLES,
        )
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _make_athlete(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    athlete_id: int,
    birth_date: date,
    sex: Sex = Sex.M,
) -> Athlete:
    async with session_factory() as s:
        ath = Athlete(
            id=athlete_id,
            user_id=athlete_id,
            first_name="Deportista",
            last_name="Prueba",
            birth_date=birth_date,
            sex=sex,
            club_id=1,
            created_by=1,
        )
        s.add(ath)
        await s.commit()
        await s.refresh(ath)
        s.expunge(ath)
        return ath


def _record_kwargs(athlete_id: int, evaluation_date: date, *, weight: float, height: float) -> dict[str, object]:
    return dict(
        athlete_id=athlete_id,
        evaluation_date=evaluation_date,
        weight_kg=Decimal(str(weight)),
        standing_height_cm=Decimal(str(height)),
        sitting_height_cm=Decimal("78.0"),
        leg_length_cm=Decimal("72.0"),
        leg_sitting_ratio=Decimal("0.9231"),
        maturity_offset=Decimal("-1.0"),
        age_at_phv=Decimal("13.5"),
        maturation_status=MaturationStatus.pre_phv,
        evaluated_by=_EVALUATED_BY,
    )


def _skinfold_kwargs(
    athlete_id: int,
    *,
    sum4: float | None,
    triceps_mm: float | None = 8.0,
    subscapular_mm: float | None = 8.0,
    all_declined: bool = False,
) -> SkinfoldMeasurement:
    if all_declined:
        return SkinfoldMeasurement(
            athlete_id=athlete_id,
            triceps_declined=True,
            biceps_declined=True,
            subscapular_declined=True,
            medial_calf_declined=True,
            iliac_crest_declined=True,
            supraspinale_declined=True,
            measured_by=_MEASURED_BY,
        )
    return SkinfoldMeasurement(
        athlete_id=athlete_id,
        triceps_mm=Decimal(str(triceps_mm)) if triceps_mm is not None else None,
        biceps_mm=Decimal("5.0"),
        subscapular_mm=Decimal(str(subscapular_mm)) if subscapular_mm is not None else None,
        medial_calf_mm=Decimal("10.0"),
        iliac_crest_mm=Decimal("12.0"),
        supraspinale_mm=Decimal("6.0"),
        sum4_mm=Decimal(str(sum4)) if sum4 is not None else None,
        measured_by=_MEASURED_BY,
    )


async def _add_set(
    session: AsyncSession,
    athlete_id: int,
    evaluation_date: date,
    *,
    weight: float,
    height: float,
    sum4: float | None,
    triceps_mm: float | None = 8.0,
    subscapular_mm: float | None = 8.0,
    all_declined: bool = False,
) -> None:
    record = AnthropometricRecord(**_record_kwargs(athlete_id, evaluation_date, weight=weight, height=height))
    record.skinfolds = _skinfold_kwargs(
        athlete_id,
        sum4=sum4,
        triceps_mm=triceps_mm,
        subscapular_mm=subscapular_mm,
        all_declined=all_declined,
    )
    session.add(record)
    await session.flush()


# ---------------------------------------------------------------------------
# (a)+(b)+(c) — rojo fixture: mes con toma, otros meses sin bloque, claves,
# copy ámbar.
# ---------------------------------------------------------------------------

_ROJO_ATHLETE_ID = 101


@pytest_asyncio.fixture
async def rojo_athlete(session_factory: async_sessionmaker[AsyncSession]) -> Athlete:
    return await _make_athlete(
        session_factory, athlete_id=_ROJO_ATHLETE_ID, birth_date=date(2013, 3, 1), sex=Sex.M
    )


@pytest_asyncio.fixture
async def rojo_sets(session_factory: async_sessionmaker[AsyncSession], rojo_athlete: Athlete) -> None:
    """Contract §5 scenario C: Σ4 30->22, weight flat, height growing -> rojo."""
    async with session_factory() as s:
        await _add_set(
            s, _ROJO_ATHLETE_ID, date(2026, 1, 10), weight=40.0, height=145.0, sum4=30.0
        )
        await _add_set(
            s, _ROJO_ATHLETE_ID, date(2026, 5, 10), weight=40.5, height=148.5, sum4=22.0
        )
        # Mes cuya única toma fue declinada por completo — no cuenta.
        await _add_set(
            s, _ROJO_ATHLETE_ID, date(2026, 7, 15), weight=41.0, height=149.0, sum4=None, all_declined=True
        )
        await s.commit()


@pytest.mark.asyncio
async def test_block_present_only_in_the_counted_sets_month(
    session_factory: async_sessionmaker[AsyncSession], rojo_sets: None
) -> None:
    async with session_factory() as s:
        block_may = await _build_body_composition_block(s, _ROJO_ATHLETE_ID, 2026, 5)
        block_other_month = await _build_body_composition_block(s, _ROJO_ATHLETE_ID, 2026, 3)
        block_declined_month = await _build_body_composition_block(s, _ROJO_ATHLETE_ID, 2026, 7)

    assert block_may is not None, "Debe aparecer en el mes de la toma contada (mayo)"
    assert block_other_month is None, "Ausente en un mes sin ninguna toma"
    assert block_declined_month is None, "Ausente cuando la única toma del mes fue declinada"


@pytest.mark.asyncio
async def test_block_has_exactly_the_three_expected_keys(
    session_factory: async_sessionmaker[AsyncSession], rojo_sets: None
) -> None:
    async with session_factory() as s:
        block = await _build_body_composition_block(s, _ROJO_ATHLETE_ID, 2026, 5)

    assert block is not None
    assert set(block.keys()) == {"family_label", "family_sentence", "notice_text"}
    assert block["notice_text"] == NEWSLETTER_NOTICE


@pytest.mark.asyncio
async def test_rojo_fixture_renders_ambar_family_copy(
    session_factory: async_sessionmaker[AsyncSession], rojo_sets: None
) -> None:
    async with session_factory() as s:
        block = await _build_body_composition_block(s, _ROJO_ATHLETE_ID, 2026, 5)

    assert block is not None
    assert block["family_label"] == FAMILY_COPY["ambar"]["family_label"]
    assert block["family_sentence"] == FAMILY_COPY["ambar"]["family_sentence"]
    # Nunca la frase exclusiva del coach para un rojo real (§3c).
    assert "Requiere acompañamiento profesional" not in block["family_sentence"]


# ---------------------------------------------------------------------------
# (d) — referencia únicamente: single set, tríceps >= P95 -> verde (§3c).
# ---------------------------------------------------------------------------

_REF_ATHLETE_ID = 102
_REF_EVAL_DATE = date(2026, 6, 15)


@pytest_asyncio.fixture
async def reference_only_athlete(session_factory: async_sessionmaker[AsyncSession]) -> Athlete:
    # ~13.5 años en la fecha de evaluación -> dentro de 108-216 meses FUPRECOL.
    return await _make_athlete(
        session_factory, athlete_id=_REF_ATHLETE_ID, birth_date=date(2013, 1, 1), sex=Sex.F
    )


@pytest_asyncio.fixture
async def reference_only_set(
    session_factory: async_sessionmaker[AsyncSession], reference_only_athlete: Athlete
) -> None:
    async with session_factory() as s:
        # Banda FUPRECOL sintética: L=0, M=1.0, S=0.3 -> con tríceps=8.0mm el
        # z-score se satura en +3 (percentil ~99.9) -> high_extreme, sin tocar
        # ninguna otra pierna (sum_change "none" por ser el único set).
        s.add(
            GrowthReferenceLms(
                source=GrowthSource.FUPRECOL,
                indicator=GrowthIndicator.triceps_skinfold_for_age,
                sex="F",
                age_months=Decimal("162.0"),
                L=Decimal("0.0"),
                M=Decimal("1.0"),
                S=Decimal("0.3"),
            )
        )
        await _add_set(
            s,
            _REF_ATHLETE_ID,
            _REF_EVAL_DATE,
            weight=45.0,
            height=155.0,
            sum4=30.0,
            triceps_mm=8.0,
            subscapular_mm=8.0,
        )
        await s.commit()


@pytest.mark.asyncio
async def test_reference_only_ambar_renders_verde_family_copy(
    session_factory: async_sessionmaker[AsyncSession], reference_only_set: None
) -> None:
    async with session_factory() as s:
        block = await _build_body_composition_block(s, _REF_ATHLETE_ID, 2026, 6)

    assert block is not None
    assert block["family_label"] == FAMILY_COPY["verde"]["family_label"]
    assert block["family_sentence"] == FAMILY_COPY["verde"]["family_sentence"]


# ---------------------------------------------------------------------------
# (e) — PDF de bitácora: título + aviso presentes, sin cifras/porcentajes/mm
# ni la frase exclusiva del coach.
# ---------------------------------------------------------------------------

_NUM_MM_RE = re.compile(r"\d+(?:[.,]\d+)?\s*mm")
_NUM_PCT_RE = re.compile(r"\d+\s*%")


@pytest.mark.asyncio
async def test_stage_log_pdf_renders_fixed_copy_without_numbers(
    session_factory: async_sessionmaker[AsyncSession], rojo_sets: None
) -> None:
    from app.services.notification.athlete_newsletter_pdf import generate_stage_log_pdf
    from app.services.notification.document_generator import DocumentGenerator
    from app.services.notification.template_registry import TemplateRegistry
    from app.services.training.stage_log import StageLog, to_parent_dto

    async with session_factory() as s:
        block = await _build_body_composition_block(s, _ROJO_ATHLETE_ID, 2026, 5)
    assert block is not None

    stage_log = StageLog(
        stage_number=5,
        period_label="Mayo 2026",
        athlete_first_name="Deportista",
        athlete_reference="su hijo",
        stage_title="Una etapa de constancia.",
    )
    dto = to_parent_dto(stage_log, hidden_blocks=None)

    generator = DocumentGenerator(TemplateRegistry())
    doc, _sha256 = await generate_stage_log_pdf(
        generator=generator,
        athlete_first_name="Deportista",
        athlete_last_name="Prueba",
        athlete_id=_ROJO_ATHLETE_ID,
        year=2026,
        month=5,
        stage_log=dto,
        body_composition=block,
    )

    with pdfplumber.open(io.BytesIO(doc.data)) as pdf:
        text = "\n".join((page.extract_text() or "") for page in pdf.pages)

    normalized_text = re.sub(r"\s+", " ", text)
    normalized_notice = re.sub(r"\s+", " ", NEWSLETTER_NOTICE)

    assert "Composición corporal" in text
    assert normalized_notice in normalized_text
    assert "Requiere acompañamiento profesional" not in text
    assert _NUM_PCT_RE.search(text) is None, "El anexo no debe imprimir porcentajes"
    assert _NUM_MM_RE.search(text) is None, "El anexo no debe imprimir milímetros"


@pytest.mark.asyncio
async def test_stage_log_pdf_omits_section_when_block_is_none(
    session_factory: async_sessionmaker[AsyncSession], rojo_sets: None
) -> None:
    from app.services.notification.athlete_newsletter_pdf import generate_stage_log_pdf
    from app.services.notification.document_generator import DocumentGenerator
    from app.services.notification.template_registry import TemplateRegistry
    from app.services.training.stage_log import StageLog, to_parent_dto

    stage_log = StageLog(
        stage_number=3,
        period_label="Marzo 2026",
        athlete_first_name="Deportista",
        athlete_reference="su hijo",
        stage_title="Un mes tranquilo.",
    )
    dto = to_parent_dto(stage_log, hidden_blocks=None)

    generator = DocumentGenerator(TemplateRegistry())
    doc, _sha256 = await generate_stage_log_pdf(
        generator=generator,
        athlete_first_name="Deportista",
        athlete_last_name="Prueba",
        athlete_id=_ROJO_ATHLETE_ID,
        year=2026,
        month=3,
        stage_log=dto,
        body_composition=None,
    )

    with pdfplumber.open(io.BytesIO(doc.data)) as pdf:
        text = "\n".join((page.extract_text() or "") for page in pdf.pages)

    assert "Composición corporal" not in text


# ---------------------------------------------------------------------------
# (f) — el bloque nunca llega al contexto/solicitud de la IA.
# ---------------------------------------------------------------------------


def _snapshot_with_body_composition() -> dict:
    return {
        "email_blocks": {
            "period": {"year": 2026, "month": 5, "label": "Mayo 2026"},
            "attendance": {
                "sessions_present": 8,
                "sessions_total": 8,
                "attendance_pct": 100.0,
                "attendance_pct_prev_month": None,
                "streak_sessions": 8,
            },
            "technical": {"focos_tecnicos": [], "avg_rpe": None, "avg_rubric_technique": None},
            "race_results": {"has_races": False, "results": []},
            "badges": {"items": []},
            "calendar": {"next_race_events": []},
        },
        "pdf_only_blocks": {
            "weekly": [],
            "next_focus_groups": [],
            "body_composition": {
                "family_label": FAMILY_COPY["ambar"]["family_label"],
                "family_sentence": FAMILY_COPY["ambar"]["family_sentence"],
                "notice_text": NEWSLETTER_NOTICE,
            },
        },
    }


def test_context_v2_never_carries_body_composition_data() -> None:
    import dataclasses

    from app.services.ai.use_cases.athlete_monthly_newsletter_v2 import (
        build_context_from_metrics_v2,
    )

    ctx = build_context_from_metrics_v2(
        _snapshot_with_body_composition(), 2026, 5, frozenset(), athlete_sex="M"
    )

    ctx_dump = str(dataclasses.asdict(ctx))
    for forbidden in ("body_composition", "family_band", "pliegue", "ambar", "rojo", "verde"):
        assert forbidden not in ctx_dump.lower()


@pytest.mark.asyncio
async def test_fake_provider_request_never_carries_body_composition_data() -> None:
    from app.services.ai.providers.fake import FakeLLMProvider
    from app.services.ai.prompts.registry import PromptRegistry
    from app.services.ai.use_cases.athlete_monthly_newsletter_v2 import (
        AthleteMonthlyNewsletterV2UseCase,
        build_context_from_metrics_v2,
    )

    ctx = build_context_from_metrics_v2(
        _snapshot_with_body_composition(), 2026, 5, frozenset(), athlete_sex="M"
    )
    canned_json = {
        "stage_title": "Una etapa de constancia perfecta.",
        "summit_caption": None,
        "observations": [
            {"claim": "Asistió a todas las sesiones.", "evidence": "8/8 sesiones.", "block_ref": "attendance"},
            {"claim": "Mantuvo la racha todo el mes.", "evidence": "Racha de 8.", "block_ref": "streak"},
            {"claim": "Buen cierre de mes.", "evidence": "Sin novedades.", "block_ref": "attendance"},
        ],
        "next_segment_text": None,
        "family_compass": {
            "conversation_question": "¿Qué fue lo mejor del mes?",
            "monthly_challenge": "Seguir disfrutando cada sesión.",
            "what_to_watch": "Cómo se siente en la próxima semana.",
        },
        "analyst_reading": None,
    }
    fake = FakeLLMProvider(canned_json=canned_json)
    uc = AthleteMonthlyNewsletterV2UseCase(fake, PromptRegistry())

    await uc.run(ctx)

    sent = fake.last_request.messages[-1].content.lower()
    for forbidden in ("body_composition", "family_band", "pliegue", "ambar", "rojo"):
        assert forbidden not in sent
