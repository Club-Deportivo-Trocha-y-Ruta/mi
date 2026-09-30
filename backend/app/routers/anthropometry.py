from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.dependencies import (
    get_current_user,
    get_db,
    get_notification_service,
    get_task_dispatcher,
    require_role,
    verify_athlete_access,
)
from app.models.ai_explanation import AthleteAIExplanation
from app.models.anthropometry import AnthropometricRecord
from app.models.athlete import Athlete, ParentAthlete
from app.models.skinfold_measurement import SkinfoldMeasurement
from app.models.user import User, UserRole
from app.routers.body_composition import skinfold_set_out
from app.schemas.anthropometry import (
    AnthropometryCreate,
    AnthropometryOut,
    AnthropometryUpdate,
    GrowthPercentiles,
    MorphologyMetrics,
    PlausibilityCheckIn,
    PlausibilityCheckOut,
    PlausibilityWarningOut,
)
from app.schemas.notification import NotificationRecipient, NotificationRequest, NotificationTemplate
from app.services.anthropometry import (  # noqa: F401 — WEIGHT_AGE_MAX_MONTHS se re-exporta
    WEIGHT_AGE_MAX_MONTHS,
    apply_derived_fields,
    derive_record_fields,
)
from app.services.anthropometry_plausibility import (
    MeasureSet,
    check_plausibility,
    flags_for_series,
    measure_set_of,
)
from app.services.body_composition import (
    AthleteTooYoungError,
    SkinfoldIntervalTooShortError,
    check_interval_for_date,
    check_min_age,
    recompute_estimates_for_record,
)
from app.services.growth import classify_nutritional_status_height
from app.services.measurement_alerts import detect_approaching_circa
from app.services.morphology import calculate_arm_span_metrics
from app.services.notification.service import NotificationService
from app.services.notification.task_dispatcher import TaskDispatcher
from app.services.permissions import can_modify_anthropometric_record
from app.models.audit_log import AuditAction
from app.services.audit import AuditEntityType, record_audit

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_growth_percentiles(
    record: AnthropometricRecord,
    nutritional_status_height: str | None,
) -> GrowthPercentiles | None:
    """
    Construye el objeto GrowthPercentiles a partir de los campos del ORM.
    Retorna None si no hay datos de percentiles en el registro.
    """
    if record.bmi_z_score is None and record.height_z_score is None:
        return None

    # nutritional_status en el ORM almacena la clasificación IMC/E
    nutritional_status_bmi: str | None = None
    if record.nutritional_status is not None:
        # El ORM retorna el objeto enum; .value da el string
        nutritional_status_bmi = (
            record.nutritional_status.value
            if hasattr(record.nutritional_status, "value")
            else str(record.nutritional_status)
        )

    return GrowthPercentiles(
        bmi=record.bmi,
        height_z_score=record.height_z_score,
        height_percentile=record.height_percentile,
        bmi_z_score=record.bmi_z_score,
        bmi_percentile=record.bmi_percentile,
        weight_z_score=record.weight_z_score,
        weight_percentile=record.weight_percentile,
        nutritional_status_height=nutritional_status_height,
        nutritional_status_bmi=nutritional_status_bmi,
    )


def _build_morphology(record: AnthropometricRecord) -> MorphologyMetrics | None:
    """Calcula métricas de envergadura si el registro tiene arm_span_cm."""
    if record.arm_span_cm is None:
        return None
    metrics = calculate_arm_span_metrics(
        arm_span_cm=float(record.arm_span_cm),
        standing_height_cm=float(record.standing_height_cm),
        maturation_status=(
            record.maturation_status.value
            if hasattr(record.maturation_status, "value")
            else record.maturation_status
        ),
    )
    if metrics is None:
        return None
    return MorphologyMetrics(**metrics)


def _infer_nutritional_status_height(record: AnthropometricRecord) -> str | None:
    """
    Infiere el estado nutricional T/E a partir del height_z_score almacenado.
    Usado en el GET para registros que tienen percentiles pero no guardaron ns_height.
    """
    if record.height_z_score is None:
        return None
    return classify_nutritional_status_height(float(record.height_z_score)).value


# ---------------------------------------------------------------------------
# Feature 048 — helpers de edición, borrado y fecha repetida
# ---------------------------------------------------------------------------

#: Código estable del 409 por fecha repetida (research R4).
SAME_DATE_EXISTS = "anthropometry_same_date_exists"
#: Código estable del 403 de autoría (research R2).
NOT_RECORD_AUTHOR = "not_record_author"

# Escala de las columnas Numeric: la comparación de `same_values` y de
# `changed_fields` se hace con el mismo redondeo que aplica la BD.
_WEIGHT_Q = Decimal("0.01")
_LENGTH_Q = Decimal("0.1")
_MEASURE_SCALES: dict[str, Decimal] = {
    "weight_kg": _WEIGHT_Q,
    "standing_height_cm": _LENGTH_Q,
    "sitting_height_cm": _LENGTH_Q,
    "arm_span_cm": _LENGTH_Q,
}
#: Campos editables por PUT, en el orden en que se reportan.
_EDITABLE_FIELDS: tuple[str, ...] = (
    "evaluation_date",
    "weight_kg",
    "standing_height_cm",
    "sitting_height_cm",
    "arm_span_cm",
    "notes",
)


def _q(value: object, scale: Decimal) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(scale)


def _same_measures(record: AnthropometricRecord, body: AnthropometryCreate) -> bool:
    """¿Las 4 medidas de `body` coinciden con las guardadas (tras cuantizar)?"""
    return all(
        _q(getattr(record, field), scale) == _q(getattr(body, field), scale)
        for field, scale in _MEASURE_SCALES.items()
    )


def _changed_fields(record: AnthropometricRecord, body: AnthropometryUpdate) -> list[str]:
    """Nombres de los campos editables cuyo valor cambia (nunca los valores)."""
    changed: list[str] = []
    for field in _EDITABLE_FIELDS:
        old, new = getattr(record, field), getattr(body, field)
        scale = _MEASURE_SCALES.get(field)
        if scale is not None:
            old, new = _q(old, scale), _q(new, scale)
        if old != new:
            changed.append(field)
    return changed


async def _find_same_date_record(
    db: AsyncSession,
    athlete_id: int,
    evaluation_date: date,
    *,
    exclude_record_id: int | None = None,
) -> AnthropometricRecord | None:
    stmt = select(AnthropometricRecord).where(
        AnthropometricRecord.athlete_id == athlete_id,
        AnthropometricRecord.evaluation_date == evaluation_date,
    )
    if exclude_record_id is not None:
        stmt = stmt.where(AnthropometricRecord.id != exclude_record_id)
    result = await db.execute(stmt.order_by(AnthropometricRecord.id).limit(1))
    return result.scalar_one_or_none()


def _same_date_conflict(existing: AnthropometricRecord, same_values: bool) -> JSONResponse:
    """409 con el cuerpo exacto de contracts/api.md (claves en el nivel raíz)."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": SAME_DATE_EXISTS,
            "existing_record_id": existing.id,
            "same_values": same_values,
        },
    )


async def _load_modifiable_record(
    db: AsyncSession,
    athlete: Athlete,
    record_id: int,
    current_user: User,
) -> AnthropometricRecord:
    """Registro del atleta (si no, 404) que `current_user` puede modificar
    (si no, 403 `not_record_author`). `verify_athlete_access` ya corrió."""
    result = await db.execute(
        select(AnthropometricRecord)
        .options(
            selectinload(AnthropometricRecord.athlete),
            selectinload(AnthropometricRecord.skinfolds).selectinload(
                SkinfoldMeasurement.record
            ),
        )
        .where(
            AnthropometricRecord.id == record_id,
            AnthropometricRecord.athlete_id == athlete.id,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="anthropometric_record_not_found",
        )
    if not can_modify_anthropometric_record(current_user, record):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=NOT_RECORD_AUTHOR,
        )
    return record


async def _load_record_explanations(
    db: AsyncSession, athlete_id: int, record_id: int
) -> list[AthleteAIExplanation]:
    result = await db.execute(
        select(AthleteAIExplanation)
        .where(
            AthleteAIExplanation.athlete_id == athlete_id,
            AthleteAIExplanation.anthropometric_record_id == record_id,
        )
        .order_by(AthleteAIExplanation.id)
    )
    return list(result.scalars().all())


async def _delete_explanations_audited(
    db: AsyncSession,
    explanations: list[AthleteAIExplanation],
    *,
    athlete: Athlete,
    record_id: int,
    actor: User,
) -> None:
    """Borra las explicaciones de IA del registro, una fila de auditoría por
    cada una (tabla en AUDIT_STRICT). Solo ids: nunca el texto generado."""
    for explanation in explanations:
        await record_audit(
            db,
            action=AuditAction.delete,
            entity_type=AuditEntityType.athlete_ai_explanation,
            entity_id=explanation.id,
            actor=actor,
            club_id=athlete.club_id,
            athlete_id=athlete.id,
            meta={"related_entity_id": record_id},
        )
        await db.delete(explanation)


class _AtDate:
    """Vista mínima de un registro "movido" a otra fecha para `check_min_age`,
    que solo lee `evaluation_date` (evita mutar el ORM antes de validar)."""

    def __init__(self, evaluation_date: date) -> None:
        self.evaluation_date = evaluation_date


def _record_out(
    record: AnthropometricRecord,
    *,
    nutritional_status_height: str | None,
) -> AnthropometryOut:
    out = AnthropometryOut.model_validate(record)
    out.growth_percentiles = _build_growth_percentiles(
        record=record, nutritional_status_height=nutritional_status_height
    )
    out.morphology = _build_morphology(record)
    out.skinfolds = (
        skinfold_set_out(record.skinfolds) if record.skinfolds is not None else None
    )
    return out


# ---------------------------------------------------------------------------
# POST /api/athletes/{athlete_id}/anthropometry
# ---------------------------------------------------------------------------
@router.post(
    "/{athlete_id}/anthropometry",
    response_model=AnthropometryOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_anthropometry(
    body: AnthropometryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    athlete: Athlete = Depends(verify_athlete_access),
    notification_service: NotificationService = Depends(get_notification_service),
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),
) -> AnthropometryOut | JSONResponse:

    # Feature 048 (research R4): nunca dos registros del mismo atleta en la
    # misma fecha. `same_values=true` le dice al frontend que un reintento ya
    # había llegado (FR-029); si difieren, ofrece abrir el existente (FR-021).
    existing = await _find_same_date_record(db, athlete.id, body.evaluation_date)
    if existing is not None:
        return _same_date_conflict(existing, _same_measures(existing, body))

    # Campos derivados (Mirwald, OMS 2007, IMC) — feature 048 / R1: la misma
    # derivación la reutiliza el PUT; ver app/services/anthropometry.py.
    derived = await derive_record_fields(
        db,
        athlete,
        evaluation_date=body.evaluation_date,
        weight_kg=body.weight_kg,
        standing_height_cm=body.standing_height_cm,
        sitting_height_cm=body.sitting_height_cm,
    )

    record = AnthropometricRecord(
        athlete_id=athlete.id,
        evaluation_date=body.evaluation_date,
        weight_kg=body.weight_kg,
        standing_height_cm=body.standing_height_cm,
        arm_span_cm=body.arm_span_cm,
        sitting_height_cm=body.sitting_height_cm,
        evaluated_by=current_user.id,
        notes=body.notes,
    )
    apply_derived_fields(record, derived)
    db.add(record)
    await db.flush()
    # Feature 046: a just-created record never has a skinfold set yet. Mark
    # the relationship as already-loaded (empty) via `set_committed_value`
    # rather than assigning `None` directly — a plain assignment on a
    # `cascade="all, delete-orphan"` relationship first loads the previous
    # value to reconcile the cascade, which is an async lazy-load outside a
    # greenlet here (`AnthropometryOut.model_validate` below reads it
    # synchronously) and, in older test harnesses that don't create the
    # `skinfold_measurements` table, a hard failure.
    from sqlalchemy.orm.attributes import set_committed_value

    set_committed_value(record, "skinfolds", None)

    await record_audit(
        db,
        action=AuditAction.create,
        entity_type=AuditEntityType.anthropometric_record,
        entity_id=record.id,
        actor=current_user,
        club_id=athlete.club_id,
        athlete_id=athlete.id,
        meta={"event_date": record.evaluation_date.isoformat()},
    )

    # -----------------------------------------------------------------------
    # Notificación a padres sobre nueva medición (Paso 11)
    # -----------------------------------------------------------------------
    if detect_approaching_circa(derived.maturity_offset):
        from app.models.club import Club
        club_result = await db.execute(select(Club).where(Club.id == athlete.club_id))
        club = club_result.scalar_one()

        # Buscar padres/acudientes vinculados al atleta
        parents_result = await db.execute(
            select(User)
            .join(ParentAthlete, ParentAthlete.parent_id == User.id)
            .where(ParentAthlete.athlete_id == athlete.id)
        )
        parents = parents_result.scalars().all()

        # CC al atleta si tiene email registrado
        athlete_user_result = await db.execute(
            select(User).where(User.id == athlete.user_id)
        )
        athlete_user = athlete_user_result.scalar_one_or_none()
        cc_emails = [athlete_user.email] if athlete_user and athlete_user.email else []

        for parent in parents:
            notification_req = NotificationRequest(
                recipient=NotificationRecipient(
                    email=parent.email,
                    name=f"{parent.first_name} {parent.last_name}",
                ),
                template=NotificationTemplate.ANTHROPOMETRY_ALERT,
                send_async=True,
                cc_emails=cc_emails,
                context={
                    "parent_name": parent.first_name,
                    "athlete_first_name": athlete.first_name,
                    "club_name": club.name,
                    "evaluation_date": body.evaluation_date.isoformat(),
                    "maturation_status": derived.maturation_status,
                },
            )
            await notification_service.send(notification_req, dispatcher=dispatcher)

    out = AnthropometryOut.model_validate(record)
    out.growth_percentiles = _build_growth_percentiles(
        record=record,
        nutritional_status_height=derived.nutritional_status_height,
    )
    out.morphology = _build_morphology(record)
    # Commit explícitamente aquí en vez de dejarlo solo al teardown de
    # `get_db` (post-`yield`): FastAPI cierra el `AsyncExitStack` de las
    # dependencias DESPUÉS de enviar la respuesta al cliente
    # (`fastapi.routing.request_response`: `await response(...)` corre
    # dentro del `async with AsyncExitStack()` pero antes de que ese bloque
    # salga), así que sin este commit explícito el 201 podía llegar al
    # cliente con la fila todavía sin persistir — una carrera real: el
    # siguiente GET (p. ej. "Guardar y agregar pliegues" navegando al
    # asistente) podía no ver el registro recién creado. Confirmado
    # reproduciendo con httpx contra la MySQL aislada de e2e: ~80% de las
    # veces el registro faltaba en un GET disparado inmediatamente después
    # del POST. Ver `tests/test_athletes.py::TestCreateAnthropometry::
    # test_created_record_is_immediately_visible_in_list`.
    await db.commit()
    return out


# ---------------------------------------------------------------------------
# GET /api/athletes/{athlete_id}/anthropometry
# ---------------------------------------------------------------------------
@router.get("/{athlete_id}/anthropometry", response_model=list[AnthropometryOut])
async def list_anthropometry(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    athlete: Athlete = Depends(verify_athlete_access),
) -> list[AnthropometryOut]:
    # Feature 046: eager-load skinfolds (+ its own `record` back-ref, needed
    # by `skinfold_set_out` for `evaluation_date`) — no N+1 for the list view.
    result = await db.execute(
        select(AnthropometricRecord)
        .options(
            selectinload(AnthropometricRecord.skinfolds).selectinload(
                SkinfoldMeasurement.record
            )
        )
        .where(AnthropometricRecord.athlete_id == athlete.id)
        .order_by(AnthropometricRecord.evaluation_date.desc())
    )
    records = result.scalars().all()

    # Feature 048: `can_modify` y `plausibility_flags` solo para staff. Para
    # padres (y cualquier otro rol) quedan en None → claves omitidas del JSON.
    is_staff = current_user.role in (UserRole.admin, UserRole.coach)
    flags_by_id = flags_for_series(records) if is_staff else {}

    output: list[AnthropometryOut] = []
    for record in records:
        # Para registros existentes, nutritional_status_height se infiere del z-score almacenado
        out = _record_out(
            record, nutritional_status_height=_infer_nutritional_status_height(record)
        )
        if is_staff:
            out.can_modify = can_modify_anthropometric_record(current_user, record)
            out.plausibility_flags = flags_by_id.get(record.id, [])
        # Filtrar datos sensibles para padres (privacidad del entrenamiento)
        if current_user.role == UserRole.parent:
            out.notes = None
            out.morphology = None
            out.skinfolds = None
        output.append(out)

    return output


# ---------------------------------------------------------------------------
# PUT /api/athletes/{athlete_id}/anthropometry/{record_id} — feature 048
# ---------------------------------------------------------------------------
@router.put(
    "/{athlete_id}/anthropometry/{record_id}",
    response_model=AnthropometryOut,
)
async def update_anthropometry(
    record_id: int,
    body: AnthropometryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    athlete: Athlete = Depends(verify_athlete_access),
) -> AnthropometryOut | JSONResponse:
    """Corrige una medición (reemplazo completo de los campos editables).

    Recalcula los derivados con las mismas reglas del POST (R1), re-aplica las
    reglas de pliegues si cambió la fecha (R6/FR-007), recalcula la
    estimación de grasa si cambió el peso, borra las explicaciones de IA del
    registro (FR-006) y audita solo nombres de campos (FR-004).

    Nunca notifica a la familia (research R3 / FR-008): una edición corrige
    una medición ya tomada, aunque cruce el umbral de circa-PHV.

    Todas las lecturas van ANTES de mutar el registro: una consulta posterior
    dispararía un autoflush del registro sucio sin su fila de auditoría.
    """
    record = await _load_modifiable_record(db, athlete, record_id, current_user)

    changed = _changed_fields(record, body)
    if not changed:
        # Nada que corregir: sin escritura, sin auditoría, sin invalidar la IA.
        out = _record_out(
            record, nutritional_status_height=_infer_nutritional_status_height(record)
        )
        out.can_modify = True
        return out

    date_changed = "evaluation_date" in changed
    if date_changed:
        existing = await _find_same_date_record(
            db, athlete.id, body.evaluation_date, exclude_record_id=record.id
        )
        if existing is not None:
            return _same_date_conflict(existing, _same_measures(existing, body))

        if record.skinfolds is not None:
            # Mismos códigos y cuerpo que el asistente de pliegues (046).
            try:
                check_min_age(athlete, _AtDate(body.evaluation_date), settings)
            except AthleteTooYoungError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": "athlete_too_young", "message": str(exc)},
                ) from exc
            try:
                await check_interval_for_date(
                    db, athlete.id, record, body.evaluation_date, settings
                )
            except SkinfoldIntervalTooShortError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "skinfold_interval_too_short",
                        "message": str(exc),
                        "previous_set_date": exc.previous_set_date.isoformat(),
                        "next_allowed_date": exc.next_allowed_date.isoformat(),
                    },
                ) from exc

    derived = await derive_record_fields(
        db,
        athlete,
        evaluation_date=body.evaluation_date,
        weight_kg=body.weight_kg,
        standing_height_cm=body.standing_height_cm,
        sitting_height_cm=body.sitting_height_cm,
    )
    explanations = await _load_record_explanations(db, athlete.id, record.id)

    # --- A partir de aquí solo escrituras (sin más SELECT hasta el flush). ---
    previous_date = record.evaluation_date
    weight_changed = "weight_kg" in changed
    for field in _EDITABLE_FIELDS:
        setattr(record, field, getattr(body, field))
    apply_derived_fields(record, derived)
    record.updated_by_user_id = current_user.id

    if weight_changed and record.skinfolds is not None:
        # Hook de corrección de peso (feature 046, T022): solo cambian las
        # columnas de estimación; Σ4/Σ6 y los valores por sitio no.
        recompute_estimates_for_record(record)

    await _delete_explanations_audited(
        db, explanations, athlete=athlete, record_id=record.id, actor=current_user
    )
    await record_audit(
        db,
        action=AuditAction.update,
        entity_type=AuditEntityType.anthropometric_record,
        entity_id=record.id,
        actor=current_user,
        club_id=athlete.club_id,
        athlete_id=athlete.id,
        changed_fields=changed,
        # Solo `evaluation_date` está en VALUE_ALLOWLIST: record_audit descarta
        # cualquier otro valor; aquí ni siquiera se le pasan.
        diff=(
            {
                "evaluation_date": (
                    previous_date.isoformat(),
                    record.evaluation_date.isoformat(),
                )
            }
            if date_changed
            else None
        ),
        meta={"event_date": record.evaluation_date.isoformat()},
    )
    await db.flush()

    out = _record_out(record, nutritional_status_height=derived.nutritional_status_height)
    out.can_modify = True
    # Commit explícito antes de responder: misma carrera que documenta el POST.
    await db.commit()
    return out


# ---------------------------------------------------------------------------
# DELETE /api/athletes/{athlete_id}/anthropometry/{record_id} — feature 048
# ---------------------------------------------------------------------------
@router.delete(
    "/{athlete_id}/anthropometry/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_anthropometry(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    athlete: Athlete = Depends(verify_athlete_access),
) -> Response:
    """Elimina la medición, su set de pliegues (cascada ORM) y sus
    explicaciones de IA (borrado explícito y auditado: SQLite no garantiza
    el `ON DELETE CASCADE`). Auditoría `delete` con `{"had_skinfolds": bool}`.
    """
    record = await _load_modifiable_record(db, athlete, record_id, current_user)
    explanations = await _load_record_explanations(db, athlete.id, record.id)
    had_skinfolds = record.skinfolds is not None
    deleted_id = record.id

    await _delete_explanations_audited(
        db, explanations, athlete=athlete, record_id=deleted_id, actor=current_user
    )
    await record_audit(
        db,
        action=AuditAction.delete,
        entity_type=AuditEntityType.anthropometric_record,
        entity_id=deleted_id,
        actor=current_user,
        club_id=athlete.club_id,
        athlete_id=athlete.id,
        meta={"had_skinfolds": had_skinfolds},
    )
    await db.delete(record)
    await db.flush()
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# POST /api/athletes/{athlete_id}/anthropometry/plausibility — feature 048
# ---------------------------------------------------------------------------
@router.post(
    "/{athlete_id}/anthropometry/plausibility",
    response_model=PlausibilityCheckOut,
)
async def check_anthropometry_plausibility(
    body: PlausibilityCheckIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    athlete: Athlete = Depends(verify_athlete_access),
) -> PlausibilityCheckOut:
    """Dry-run de las advertencias (research R5): no escribe ni audita.

    "Anterior" = el último registro con fecha ESTRICTAMENTE anterior a la del
    cuerpo, excluyendo `record_id` (el que se está editando). Misma regla que
    usa `flags_for_series` para la marca «Revisar» del historial.
    """
    stmt = select(AnthropometricRecord).where(
        AnthropometricRecord.athlete_id == athlete.id,
        AnthropometricRecord.evaluation_date < body.evaluation_date,
    )
    if body.record_id is not None:
        stmt = stmt.where(AnthropometricRecord.id != body.record_id)
    result = await db.execute(
        stmt.order_by(
            AnthropometricRecord.evaluation_date.desc(), AnthropometricRecord.id.desc()
        ).limit(1)
    )
    previous_record = result.scalar_one_or_none()

    current = MeasureSet(
        evaluation_date=body.evaluation_date,
        weight_kg=body.weight_kg,
        standing_height_cm=body.standing_height_cm,
        sitting_height_cm=body.sitting_height_cm,
        arm_span_cm=body.arm_span_cm,
    )
    previous = measure_set_of(previous_record) if previous_record is not None else None
    warnings = check_plausibility(current, previous)
    return PlausibilityCheckOut(
        warnings=[PlausibilityWarningOut(code=w.code, measure=w.measure) for w in warnings],
        previous_evaluation_date=(
            previous_record.evaluation_date if previous_record is not None else None
        ),
    )
