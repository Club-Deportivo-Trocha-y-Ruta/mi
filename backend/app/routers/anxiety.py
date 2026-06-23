"""Endpoints ``/api/anxiety/*`` — evaluación de ansiedad competitiva (feature 017).

Coach/admin: configuración, puntuación, interpretación on-demand, dashboards e
import/export. El endpoint de respuesta por token es NO autenticado pero está
protegido por un token de un solo uso. Todo el copy en español neutro; sin PII
de menores en logs.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.dependencies import (
    get_anxiety_interpretation_use_case,
    get_current_user,
    get_db,
    require_role,
)
from app.models.anxiety_assessment import AnxietyAssessment, AssessmentStatus
from app.models.athlete import Athlete
from app.models.race_event import RaceEvent
from app.models.user import User, UserRole
from app.schemas.anxiety import (
    AnswerForm,
    AnswerItem,
    AnswerResult,
    AnswerSubmit,
    AssessmentCreate,
    AssessmentCreated,
    AssessmentRead,
    AthleteSeries,
    BatchCreate,
    BatchCreated,
    BatchItemResult,
    GroupMember,
    GroupTriage,
    ImportResult,
    ImportRowError,
    InterpretationRead,
    InterpretationResponse,
    InterpretGroupRequest,
    InterpretGroupResponse,
    IssuedToken,
    SeriesPoint,
    SubscaleRead,
)
from app.services.anxiety import baseline as baseline_svc
from app.services.anxiety import interpretation as interpretation_svc
from app.services.anxiety import tokens
from app.services.anxiety.analysis import dominant_pattern
from app.services.anxiety.assessments import (
    AssessmentCreationError,
    ConsentMissingError,
    OverrideRequiredError,
    create_assessment,
)
from app.services.anxiety.importer import import_csv
from app.services.anxiety.instrument_keys import load_key
from app.services.anxiety.scoring import score_assessment
from app.services.anxiety.submit import apply_answers

logger = logging.getLogger(__name__)
router = APIRouter()

_coach_or_admin = require_role([UserRole.admin, UserRole.coach])

_INTRO = (
    "Antes de tu carrera, cuéntanos cómo te sientes hoy. No hay respuestas "
    "buenas ni malas. Marca para cada frase qué tanto se parece a lo que "
    "sientes ahora (1 = nada, 4 = mucho)."
)
_SHORT_MESSAGE = "¡Gracias! Recuerda disfrutar y enfocarte en tu proceso. 🚴"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _age_group(athlete: Athlete, at: datetime) -> str:
    age = (at.date() - athlete.birth_date).days / 365.25
    return "10-12" if age < 13 else "13-15"


async def _load_assessment(db: AsyncSession, assessment_id: int) -> AnxietyAssessment:
    result = await db.execute(
        select(AnxietyAssessment)
        .options(
            selectinload(AnxietyAssessment.instrument),
            selectinload(AnxietyAssessment.athlete),
        )
        .where(AnxietyAssessment.id == assessment_id)
    )
    assessment = result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluación no encontrada.",
        )
    return assessment


def _scores_of(assessment: AnxietyAssessment) -> dict[str, float | None]:
    return {
        "cognitive": assessment.score_cognitive,
        "somatic": assessment.score_somatic,
        "selfconfidence": assessment.score_selfconfidence,
    }


async def _build_read(
    db: AsyncSession, assessment: AnxietyAssessment
) -> AssessmentRead:
    instrument_type = assessment.instrument.type.value
    scores = _scores_of(assessment)
    baselines = await baseline_svc.get_baselines(
        db, assessment.athlete_id, instrument_type
    )
    deltas = baseline_svc.deltas(scores, baselines)

    def sub(name: str) -> SubscaleRead:
        return SubscaleRead(
            score=scores[name], baseline=baselines.get(name), delta=deltas[name]
        )

    interpretation = None
    if assessment.interpretation_json:
        interpretation = InterpretationRead(**assessment.interpretation_json)

    return AssessmentRead(
        id=assessment.id,
        athlete_id=assessment.athlete_id,
        instrument_type=instrument_type,
        event_id=assessment.event_id,
        priority=assessment.priority.value if assessment.priority else None,
        scheduled_at=assessment.scheduled_at,
        status=assessment.status.value,
        is_partial=assessment.is_partial,
        instrument_override=assessment.instrument_override,
        cognitive=sub("cognitive"),
        somatic=sub("somatic"),
        selfconfidence=sub("selfconfidence"),
        interpretation=interpretation,
        interpretation_source=(
            assessment.interpretation_source.value
            if assessment.interpretation_source
            else None
        ),
        flags=list(assessment.flags_json or []),
    )


async def _event_or_none(db: AsyncSession, event_id: int | None) -> RaceEvent | None:
    if event_id is None:
        return None
    return await db.get(RaceEvent, event_id)


# ---------------------------------------------------------------------------
# US1 — Configuration
# ---------------------------------------------------------------------------


@router.post(
    "/assessments",
    response_model=AssessmentCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_one(
    payload: AssessmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_coach_or_admin),
) -> AssessmentCreated:
    athlete = await db.get(Athlete, payload.athlete_id)
    if athlete is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Atleta no encontrado."
        )
    event = await _event_or_none(db, payload.event_id)

    try:
        created = await create_assessment(
            db,
            athlete=athlete,
            scheduled_at=payload.scheduled_at,
            created_by_user_id=current_user.id,
            event=event,
            instrument_override=payload.instrument_type,
            override_confirmed=payload.override,
        )
    except ConsentMissingError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except OverrideRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.warning
        )
    except AssessmentCreationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )

    return AssessmentCreated(
        id=created.assessment.id,
        athlete_id=created.assessment.athlete_id,
        instrument_type=created.instrument_type,
        status=created.assessment.status.value,
        instrument_override=created.assessment.instrument_override,
        scheduled_at=created.assessment.scheduled_at,
        warning=created.warning,
        token=IssuedToken(
            token=created.raw_token, expires_at=created.token.expires_at
        ),
    )


@router.post(
    "/assessments/batch",
    response_model=BatchCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_batch(
    payload: BatchCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_coach_or_admin),
) -> BatchCreated:
    event = await _event_or_none(db, payload.event_id)
    items: list[BatchItemResult] = []

    for athlete_id in payload.athlete_ids:
        athlete = await db.get(Athlete, athlete_id)
        if athlete is None:
            items.append(
                BatchItemResult(
                    athlete_id=athlete_id,
                    created=False,
                    error="Atleta no encontrado.",
                )
            )
            continue
        try:
            created = await create_assessment(
                db,
                athlete=athlete,
                scheduled_at=payload.scheduled_at,
                created_by_user_id=current_user.id,
                event=event,
            )
        except AssessmentCreationError as exc:
            items.append(
                BatchItemResult(
                    athlete_id=athlete_id, created=False, error=str(exc)
                )
            )
            continue

        items.append(
            BatchItemResult(
                athlete_id=athlete_id,
                created=True,
                warning=created.warning,
                assessment=AssessmentCreated(
                    id=created.assessment.id,
                    athlete_id=athlete_id,
                    instrument_type=created.instrument_type,
                    status=created.assessment.status.value,
                    instrument_override=created.assessment.instrument_override,
                    scheduled_at=created.assessment.scheduled_at,
                    warning=created.warning,
                    token=IssuedToken(
                        token=created.raw_token,
                        expires_at=created.token.expires_at,
                    ),
                ),
            )
        )

    return BatchCreated(items=items)


# ---------------------------------------------------------------------------
# US2 — Answering via token (no auth)
# ---------------------------------------------------------------------------


@router.get("/answer/{token}", response_model=AnswerForm)
async def get_answer_form(
    token: str, db: AsyncSession = Depends(get_db)
) -> AnswerForm:
    row = await tokens.resolve_active_token(db, token)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace ya fue usado o expiró.",
        )
    assessment = await _load_assessment(db, row.assessment_id)
    key = load_key(assessment.instrument.type.value)
    items = [AnswerItem(item_id=i, text=None) for i in range(1, key.item_count + 1)]
    return AnswerForm(
        instrument_type=assessment.instrument.type.value,
        intro=_INTRO,
        scale_min=key.likert[0],
        scale_max=key.likert[1],
        items=items,
    )


@router.post("/answer/{token}", response_model=AnswerResult)
async def submit_answer(
    token: str,
    payload: AnswerSubmit,
    db: AsyncSession = Depends(get_db),
) -> AnswerResult:
    now = datetime.now(timezone.utc)
    row = await tokens.resolve_active_token(db, token, now=now)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace ya fue usado o expiró.",
        )
    assessment = await _load_assessment(db, row.assessment_id)
    instrument_type = assessment.instrument.type.value

    try:
        await apply_answers(db, assessment, instrument_type, payload.answers, now=now)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )

    tokens.consume(row, now=now)
    return AnswerResult(
        status="partial" if assessment.is_partial else "completed",
        short_message=_SHORT_MESSAGE,
    )


# ---------------------------------------------------------------------------
# US3 — Read & recompute
# ---------------------------------------------------------------------------


@router.get("/assessments/{assessment_id}", response_model=AssessmentRead)
async def read_assessment(
    assessment_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_coach_or_admin),
) -> AssessmentRead:
    assessment = await _load_assessment(db, assessment_id)
    return await _build_read(db, assessment)


@router.post("/assessments/{assessment_id}/recompute", response_model=AssessmentRead)
async def recompute(
    assessment_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_coach_or_admin),
) -> AssessmentRead:
    assessment = await _load_assessment(db, assessment_id)
    if not assessment.answers_json:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La evaluación no tiene respuestas para recalcular.",
        )
    instrument_type = assessment.instrument.type.value
    answers = {int(k): int(v) for k, v in assessment.answers_json.items()}
    scores = score_assessment(instrument_type, answers)
    score_dict = scores.as_dict()
    assessment.score_cognitive = score_dict["cognitive"]
    assessment.score_somatic = score_dict["somatic"]
    assessment.score_selfconfidence = score_dict["selfconfidence"]
    assessment.is_partial = scores.is_partial
    assessment.updated_at = datetime.now(timezone.utc)
    return await _build_read(db, assessment)


# ---------------------------------------------------------------------------
# US4 — Interpretation (on-demand, cached, rule fallback)
# ---------------------------------------------------------------------------


async def _interpret_and_cache(
    db: AsyncSession,
    assessment: AnxietyAssessment,
    use_case,
) -> interpretation_svc.InterpretationResult:
    instrument_type = assessment.instrument.type.value
    scores = _scores_of(assessment)
    baselines = await baseline_svc.get_baselines(
        db, assessment.athlete_id, instrument_type
    )
    event = await _event_or_none(db, assessment.event_id)
    event_label = getattr(event, "name", None) or "sin evento"
    age_group = _age_group(assessment.athlete, assessment.scheduled_at)

    result = await interpretation_svc.interpret(
        use_case=use_case,
        ai_enabled=settings.ai_enabled,
        instrument_type=instrument_type,
        scores=scores,
        baselines=baselines,
        age_group=age_group,
        event_label=event_label,
        priority=assessment.priority.value if assessment.priority else None,
        is_partial=assessment.is_partial,
    )

    from app.models.anxiety_assessment import InterpretationSource

    assessment.interpretation_json = result.interpretation
    assessment.interpretation_source = InterpretationSource(result.source)
    assessment.interpretation_model = result.model
    assessment.interpreted_at = datetime.now(timezone.utc)
    return result


@router.post(
    "/assessments/{assessment_id}/interpret",
    response_model=InterpretationResponse,
)
async def interpret_one(
    assessment_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_coach_or_admin),
    use_case=Depends(get_anxiety_interpretation_use_case),
) -> InterpretationResponse:
    assessment = await _load_assessment(db, assessment_id)
    if assessment.status == AssessmentStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La evaluación aún no tiene respuestas para interpretar.",
        )
    result = await _interpret_and_cache(db, assessment, use_case)
    return InterpretationResponse(
        assessment_id=assessment.id,
        interpretation=InterpretationRead(**result.interpretation),
        source=result.source,
        model=result.model,
    )


@router.post(
    "/assessments/interpret-group", response_model=InterpretGroupResponse
)
async def interpret_group(
    payload: InterpretGroupRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_coach_or_admin),
    use_case=Depends(get_anxiety_interpretation_use_case),
) -> InterpretGroupResponse:
    items: list[InterpretationResponse] = []
    for assessment_id in payload.assessment_ids:
        assessment = await _load_assessment(db, assessment_id)
        if assessment.status == AssessmentStatus.pending:
            continue
        result = await _interpret_and_cache(db, assessment, use_case)
        items.append(
            InterpretationResponse(
                assessment_id=assessment.id,
                interpretation=InterpretationRead(**result.interpretation),
                source=result.source,
                model=result.model,
            )
        )
    return InterpretGroupResponse(items=items)


# ---------------------------------------------------------------------------
# US5 — Dashboards
# ---------------------------------------------------------------------------


@router.get("/athletes/{athlete_id}/series", response_model=AthleteSeries)
async def athlete_series(
    athlete_id: int,
    instrument_type: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_coach_or_admin),
) -> AthleteSeries:
    load_key(instrument_type)  # validate type
    result = await db.execute(
        select(AnxietyAssessment)
        .options(selectinload(AnxietyAssessment.instrument))
        .where(AnxietyAssessment.athlete_id == athlete_id)
        .order_by(AnxietyAssessment.scheduled_at.asc())
    )
    assessments = list(result.scalars().all())

    families = {a.instrument.type.value for a in assessments}
    filtered = [
        a for a in assessments if a.instrument.type.value == instrument_type
    ]
    points = [
        SeriesPoint(
            assessment_id=a.id,
            scheduled_at=a.scheduled_at,
            event_id=a.event_id,
            cognitive=a.score_cognitive,
            somatic=a.score_somatic,
            selfconfidence=a.score_selfconfidence,
            flags=list(a.flags_json or []),
        )
        for a in filtered
    ]
    baselines = await baseline_svc.get_baselines(db, athlete_id, instrument_type)
    note = None
    if len(families) > 1:
        note = (
            "Hay evaluaciones con instrumentos distintos; las series no son "
            "comparables entre familias de instrumentos."
        )
    return AthleteSeries(
        athlete_id=athlete_id,
        instrument_type=instrument_type,
        baseline_cognitive=baselines.get("cognitive"),
        baseline_somatic=baselines.get("somatic"),
        baseline_selfconfidence=baselines.get("selfconfidence"),
        points=points,
        note=note,
    )


@router.get("/groups/by-event/{event_id}", response_model=GroupTriage)
async def group_by_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_coach_or_admin),
) -> GroupTriage:
    result = await db.execute(
        select(AnxietyAssessment)
        .options(selectinload(AnxietyAssessment.instrument))
        .where(
            AnxietyAssessment.event_id == event_id,
            AnxietyAssessment.status != AssessmentStatus.pending,
        )
    )
    assessments = list(result.scalars().all())

    buckets: dict[str, list[GroupMember]] = {
        "somatic_high": [],
        "cognitive_high": [],
        "confidence_low": [],
        "favorable": [],
    }
    alerts: list[GroupMember] = []
    for a in assessments:
        scores = _scores_of(a)
        member = GroupMember(
            athlete_id=a.athlete_id,
            assessment_id=a.id,
            cognitive=a.score_cognitive,
            somatic=a.score_somatic,
            selfconfidence=a.score_selfconfidence,
            flags=list(a.flags_json or []),
        )
        pattern = dominant_pattern(a.instrument.type.value, scores)
        buckets[pattern].append(member)
        if member.flags:
            alerts.append(member)

    return GroupTriage(event_id=event_id, buckets=buckets, alerts=alerts)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# US6 — Import / export
# ---------------------------------------------------------------------------


@router.post("/import", response_model=ImportResult)
async def import_assessments(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_coach_or_admin),
) -> ImportResult:
    content = await file.read()
    outcome = await import_csv(db, content, created_by_user_id=current_user.id)
    return ImportResult(
        imported=outcome.imported,
        skipped=outcome.skipped,
        errors=[ImportRowError(row=e.row, error=e.error) for e in outcome.errors],
    )


@router.get("/export")
async def export_assessments(
    format: str = Query("json", pattern="^(csv|json)$"),
    athlete_id: int | None = Query(None),
    season: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_coach_or_admin),
) -> Response:
    stmt = (
        select(AnxietyAssessment)
        .options(selectinload(AnxietyAssessment.instrument))
        .order_by(AnxietyAssessment.scheduled_at.asc())
    )
    if athlete_id is not None:
        stmt = stmt.where(AnxietyAssessment.athlete_id == athlete_id)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    if season is not None:
        rows = [r for r in rows if r.scheduled_at.year == season]

    records = [
        {
            "assessment_id": r.id,
            "athlete_id": r.athlete_id,
            "instrument_type": r.instrument.type.value,
            "scheduled_at": r.scheduled_at.isoformat(),
            "status": r.status.value,
            "score_cognitive": r.score_cognitive,
            "score_somatic": r.score_somatic,
            "score_selfconfidence": r.score_selfconfidence,
            "answers": r.answers_json or {},
        }
        for r in rows
    ]

    if format == "json":
        import json

        return Response(
            content=json.dumps({"assessments": records}, ensure_ascii=False),
            media_type="application/json",
        )

    # CSV: one row per assessment, item answers flattened as i1..iN columns.
    import csv
    import io

    max_items = 0
    for rec in records:
        if rec["answers"]:
            max_items = max(max_items, max(int(k) for k in rec["answers"]))
    fieldnames = [
        "assessment_id",
        "athlete_id",
        "instrument_type",
        "scheduled_at",
        "status",
        "score_cognitive",
        "score_somatic",
        "score_selfconfidence",
    ] + [f"i{i}" for i in range(1, max_items + 1)]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for rec in records:
        answers = rec.pop("answers")
        for i in range(1, max_items + 1):
            rec[f"i{i}"] = answers.get(str(i), "")
        writer.writerow(rec)
    return Response(content=buf.getvalue(), media_type="text/csv")
