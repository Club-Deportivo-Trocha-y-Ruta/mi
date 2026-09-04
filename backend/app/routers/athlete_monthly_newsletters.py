"""Router: Boletín Mensual Individual por Atleta (Fase 1.8).

Endpoints:
  POST /api/clubs/{club_id}/monthly-newsletters/batch
    — Crea drafts para todos los atletas activos del periodo (idempotente).
  POST /api/athletes/{athlete_id}/monthly-newsletters
    — Crea o regenera un borrador para un atleta.
  GET  /api/athletes/{athlete_id}/monthly-newsletters
    — Lista boletines del atleta.
  GET  /api/athletes/{athlete_id}/monthly-newsletters/{id}
    — Detalle de un boletín.
  GET  /api/athletes/{athlete_id}/monthly-newsletters/{id}/pdf
    — Descarga el PDF (genera si no existe).
  PATCH /api/athletes/{athlete_id}/monthly-newsletters/{id}
    — Edita narrativa (solo si status=draft).
  POST /api/athletes/{athlete_id}/monthly-newsletters/{id}/approve
    — Aprueba el boletín (draft → approved).
  POST /api/athletes/{athlete_id}/monthly-newsletters/{id}/send
    — Envía a los padres (approved → sent).

RBAC:
  - Solo coach del club o admin global.
  - Para operaciones sobre un atleta concreto, verifica que el atleta
    pertenece al club del coach.

Privacidad:
  - Nunca loguear nombres, emails, DOB.
  - La respuesta JSON nunca incluye pdf_only_blocks (antropometría).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import (
    get_db,
    get_document_generator,
    get_email_settings,
    get_llm_provider,
    get_prompt_registry,
    get_template_registry,
    require_role,
)
from app.models.athlete import Athlete
from app.models.athlete_newsletter import AthleteMonthlyNewsletter, NewsletterStatus
from app.models.club import ClubRole
from app.models.user import User, UserRole
from app.schemas.athlete_newsletter import (
    AthleteNewsletterBatchCreate,
    AthleteNewsletterBatchResult,
    AthleteNewsletterCreate,
    AthleteNewsletterPatch,
    AthleteNewsletterRead,
    AttachInsightsRequest,
    AttachInsightsResponse,
    DeliveryRow,
    NewsletterStatusSummary,
    NewsletterStatusSummaryItem,
    RegenerateBlockRequest,
)
from app.models.newsletter_delivery_event import DeliveryEventType, NewsletterDeliveryEvent
from app.services.permissions import user_club_role

logger = logging.getLogger(__name__)

router = APIRouter()
clubs_router = APIRouter()
training_router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _mask_email(email: str) -> str:
    """Enmascara un email para el panel de entrega (`j***@gmail.com`)."""
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    masked_local = f"{local[0]}***" if local else "***"
    return f"{masked_local}@{domain}"


async def _build_delivery_rows(db: AsyncSession, newsletter_id: int) -> list[DeliveryRow]:
    """Arma `delivery: list[DeliveryRow]` a partir de `newsletter_delivery_events`
    (feature 038, T401). Agrupa por `parent_user_id` cuando está disponible
    (eventos `sent` / `web_read`); los eventos del webhook de Resend
    (`delivered`/`opened`/`bounced`) no traen `parent_user_id` — se
    correlacionan por `provider_message_id` compartido con el evento `sent`.
    """
    result = await db.execute(
        select(NewsletterDeliveryEvent).where(
            NewsletterDeliveryEvent.newsletter_id == newsletter_id
        )
    )
    events = result.scalars().all()
    if not events:
        return []

    # message_id -> parent_user_id, a partir de los eventos `sent`.
    message_to_parent: dict[str, int] = {}
    for ev in events:
        if (
            ev.event_type == DeliveryEventType.sent
            and ev.provider_message_id
            and ev.parent_user_id is not None
        ):
            message_to_parent[ev.provider_message_id] = ev.parent_user_id

    rows_by_parent: dict[int, dict] = {}

    def _row(parent_id: int) -> dict:
        return rows_by_parent.setdefault(
            parent_id,
            {
                "parent_user_id": parent_id,
                "sent_at": None,
                "delivered_at": None,
                "opened_at": None,
                "web_read_at": None,
                "bounced": False,
            },
        )

    for ev in events:
        parent_id = ev.parent_user_id
        if parent_id is None and ev.provider_message_id:
            parent_id = message_to_parent.get(ev.provider_message_id)
        if parent_id is None:
            continue

        row = _row(parent_id)
        if ev.event_type == DeliveryEventType.sent:
            if row["sent_at"] is None or ev.occurred_at < row["sent_at"]:
                row["sent_at"] = ev.occurred_at
        elif ev.event_type == DeliveryEventType.delivered:
            row["delivered_at"] = ev.occurred_at
        elif ev.event_type == DeliveryEventType.opened:
            row["opened_at"] = ev.occurred_at
        elif ev.event_type == DeliveryEventType.bounced:
            row["bounced"] = True
        elif ev.event_type == DeliveryEventType.web_read:
            row["web_read_at"] = ev.occurred_at

    if not rows_by_parent:
        return []

    parent_ids = list(rows_by_parent.keys())
    users_result = await db.execute(select(User).where(User.id.in_(parent_ids)))
    users_by_id = {u.id: u for u in users_result.scalars().all()}

    delivery: list[DeliveryRow] = []
    for parent_id, row in rows_by_parent.items():
        user = users_by_id.get(parent_id)
        if user is None or not user.email:
            continue
        delivery.append(
            DeliveryRow(
                parent_user_id=parent_id,
                email_masked=_mask_email(user.email),
                has_account=True,
                sent_at=row["sent_at"],
                delivered_at=row["delivered_at"],
                opened_at=row["opened_at"],
                web_read_at=row["web_read_at"],
                bounced=row["bounced"],
            )
        )
    delivery.sort(key=lambda r: r.email_masked)
    return delivery


def _coach_club_ids(user: User) -> set[int]:
    return {m.club_id for m in user.club_memberships if m.role_in_club == ClubRole.coach}


async def _verify_coach_athlete_access(
    db: AsyncSession,
    current_user: User,
    athlete_id: int,
) -> Athlete:
    """Verifica que el coach tiene acceso al atleta (mismo club)."""
    athlete_result = await db.execute(
        select(Athlete).where(Athlete.id == athlete_id)
    )
    athlete = athlete_result.scalar_one_or_none()
    if athlete is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Atleta {athlete_id} no encontrado.",
        )

    if current_user.role == UserRole.admin:
        return athlete

    # Coach: verificar que el atleta pertenece a un club donde es coach
    club_role = await user_club_role(db, current_user.id, athlete.club_id)
    if club_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este atleta.",
        )
    return athlete


async def _get_newsletter_or_404(
    db: AsyncSession,
    newsletter_id: int,
    athlete_id: int,
) -> AthleteMonthlyNewsletter:
    result = await db.execute(
        select(AthleteMonthlyNewsletter).where(
            AthleteMonthlyNewsletter.id == newsletter_id,
            AthleteMonthlyNewsletter.athlete_id == athlete_id,
        )
    )
    nl = result.scalar_one_or_none()
    if nl is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Boletín {newsletter_id} no encontrado para el atleta {athlete_id}.",
        )
    return nl


async def _build_forbidden_names(db: AsyncSession, club_id: int) -> frozenset[str]:
    """Nombres/apellidos de los atletas del club — input de ``_redact_names``.

    Compartido entre la generación de narrativa IA (v1/v2) y el guard de
    redacción de ``coach_note`` (feature 038, T102): cualquier texto libre
    del coach que llegue a una familia pasa por el mismo forbidden-names.
    """
    club_athletes_result = await db.execute(
        select(Athlete).where(Athlete.club_id == club_id)
    )
    club_athletes = club_athletes_result.scalars().all()
    return frozenset(
        name
        for a in club_athletes
        for name in [a.first_name, a.last_name, f"{a.first_name} {a.last_name}"]
        if name
    )


def _athlete_sex_value(athlete: Athlete) -> str | None:
    """``Athlete.sex`` como ``str`` plano ("M"/"F"/None) — mismo criterio que
    ``newsletter_builder._derive_athlete_reference`` (duplicado deliberado,
    ver comentario ahí: evita acoplar routers a un import de modelo extra)."""
    sex = getattr(athlete, "sex", None)
    return sex.value if hasattr(sex, "value") else sex


async def _resolve_family_insight(
    db: AsyncSession,
    nl: AthleteMonthlyNewsletter,
    athlete: Athlete,
    has_ai_consent: bool,
) -> dict | None:
    """Traducción familiar del análisis de carrera (037) lista para la
    narrativa v2 y ``build_stage_log`` (feature 038, T201).

    Combina ``family_translation.select_insight`` (elige el primer
    ``AthleteAiInsight`` elegible de ``nl.selected_race_insight_ids``) con
    ``family_translation.filter_for_family`` (recorte determinista) y el
    ``valida_label`` de la carrera (``RaceEvent.name`` — no reinventa
    ``race_labels.build_race_label``, fuera de alcance de T201). Retorna
    ``None`` si no hay insight elegible o el recorte no deja ninguna acción
    apta para familia (sin llamar nunca a un proveedor de IA).
    """
    from app.models.athlete_ai_insight import AthleteAiInsight
    from app.services.training.family_translation import filter_for_family, select_insight
    from sqlalchemy.orm import selectinload

    selected = await select_insight(db, nl, has_ai_consent)
    if selected is None:
        return None
    insight_id, insight_v3 = selected

    row_result = await db.execute(
        select(AthleteAiInsight)
        .where(AthleteAiInsight.id == insight_id)
        .options(selectinload(AthleteAiInsight.event))
    )
    row = row_result.scalar_one_or_none()
    valida_label = (row.event.name if row is not None and row.event is not None else "") or ""

    family_input = filter_for_family(insight_v3, valida_label=valida_label)
    if family_input is None:
        return None
    return {**family_input.model_dump(), "source_insight_id": insight_id}


async def _previous_stage_texts(
    db: AsyncSession, athlete_id: int, year: int, month: int
) -> tuple[str | None, str | None]:
    """Título (para el prompt) y título+observaciones (para el guardrail de
    solapamiento) del boletín v2 anterior más reciente del mismo atleta.

    Busca hacia atrás mes a mes, hasta 12 meses, porque puede haber huecos
    (periodos sin boletín generado) — no asume que el mes previo exista.
    """
    prev_year, prev_month = year, month
    for _ in range(12):
        prev_month -= 1
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1
        result = await db.execute(
            select(AthleteMonthlyNewsletter).where(
                AthleteMonthlyNewsletter.athlete_id == athlete_id,
                AthleteMonthlyNewsletter.year == prev_year,
                AthleteMonthlyNewsletter.month == prev_month,
            )
        )
        prev_nl = result.scalar_one_or_none()
        if prev_nl is not None and prev_nl.stage_log_json:
            stage_log = prev_nl.stage_log_json
            title = stage_log.get("stage_title")
            observations = stage_log.get("observations") or []
            claims = " ".join(
                o.get("claim", "") for o in observations if isinstance(o, dict)
            )
            text = f"{title or ''} {claims}".strip() or None
            return title, text
    return None, None


def _serialize_block_value(value):
    """JSON-serializa el valor de un bloque narrativo v2 (str, lista de
    ``Observation`` o modelo Pydantic único) para persistir en ``ai_narrative``."""
    if isinstance(value, list):
        return [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else item
            for item in value
        ]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


async def _build_v2_stage_log_content(
    db: AsyncSession,
    athlete: Athlete,
    year: int,
    month: int,
    metrics_snapshot: dict,
    forbidden_names: frozenset[str],
    has_ai_consent: bool,
    llm_provider,
    prompt_registry,
    nl_for_insight_selection: AthleteMonthlyNewsletter,
) -> tuple[dict | None, dict, str | None]:
    """Genera ``(ai_narrative_dict, stage_log_json_dict, error_message)`` para
    la bitácora de etapa (feature 038, T201).

    Nunca lanza: sin consentimiento IA, o ante cualquier fallo del proveedor
    (timeout/guardrails/error interno), la narrativa queda en ``None`` y
    ``build_stage_log`` (Wave 1) produce una bitácora 100% estática — AC-2.5,
    mismo criterio que el flujo v1 (``_generate_newsletter_for_athlete``).
    """
    from app.services.ai.errors import LLMSchemaError
    from app.services.ai.use_cases.athlete_monthly_newsletter_v2 import (
        AthleteMonthlyNewsletterV2UseCase,
        StageNarrativeLLMTimeout,
        build_context_from_metrics_v2,
    )
    from app.services.training.stage_log_builder import build_stage_log

    family_input = await _resolve_family_insight(
        db, nl_for_insight_selection, athlete, has_ai_consent
    )
    previous_stage_title, previous_stage_text = await _previous_stage_texts(
        db, athlete.id, year, month
    )

    narrative = None
    error_message: str | None = None

    if has_ai_consent:
        ctx = build_context_from_metrics_v2(
            metrics_snapshot,
            year,
            month,
            forbidden_names,
            athlete_sex=_athlete_sex_value(athlete),
            analyst_reading_input=family_input,
            previous_stage_title=previous_stage_title,
            previous_stage_text=previous_stage_text,
        )
        try:
            uc = AthleteMonthlyNewsletterV2UseCase(provider=llm_provider, registry=prompt_registry)
            narrative = await uc.run(ctx)
        except StageNarrativeLLMTimeout:
            logger.warning(
                "Timeout IA v2 para bitácora | athlete_id=%d period=%d-%02d",
                athlete.id, year, month,
            )
            error_message = "llm_timeout"
        except LLMSchemaError as exc:
            logger.warning(
                "Error de parseo IA v2 | athlete_id=%d period=%d-%02d error=%s",
                athlete.id, year, month, type(exc).__name__,
            )
            error_message = "guardrails_rejected"
        except Exception as exc:
            logger.error(
                "Error IA v2 inesperado | athlete_id=%d period=%d-%02d error_type=%s",
                athlete.id, year, month, type(exc).__name__,
            )
            error_message = "llm_internal_error"

    ai_narrative_dict = narrative.model_dump() if narrative is not None else None

    stage_log = build_stage_log(
        metrics_snapshot,
        narrative,
        family_input,
        None,
        None,
        None,
        _athlete_sex_value(athlete),
        athlete.first_name,
    )
    if narrative is not None and narrative.grounding_violations:
        stage_log.grounding_violations = list(narrative.grounding_violations)

    return ai_narrative_dict, stage_log.model_dump(mode="json"), error_message


def _validate_period(year: int, month: int, force: bool = False) -> None:
    """Valida que el periodo está cerrado (no puede generar boletín del mes actual)."""
    today = date.today()
    if not force and (year > today.year or (year == today.year and month >= today.month)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"El periodo {year}-{month:02d} no está cerrado. "
                "Solo se pueden generar boletines de meses anteriores. "
                "Usa ?force=true para forzar (solo admins/coaches)."
            ),
        )


async def _generate_newsletter_for_athlete(
    db: AsyncSession,
    athlete: Athlete,
    year: int,
    month: int,
    current_user: User,
    force: bool,
    llm_provider,
    prompt_registry,
) -> AthleteMonthlyNewsletter:
    """Crea o regenera el borrador de la bitácora (StageLog v2) para un atleta."""
    from app.services.privacy import athlete_has_ai_processing_consent
    from app.services.training.newsletter_builder import build_newsletter_metrics

    # Consentimiento Ley 1581 para procesamiento con IA.
    # US3 (FR-009/FR-010): la ausencia de consentimiento ya NO bloquea el
    # boletín — solo desactiva la narrativa generada por IA. Los subtítulos,
    # el resumen del mes y el apoyo en casa caen al fallback estático.
    has_ai_consent = await athlete_has_ai_processing_consent(athlete.id, db)

    # Verificar si ya existe
    existing_result = await db.execute(
        select(AthleteMonthlyNewsletter).where(
            AthleteMonthlyNewsletter.athlete_id == athlete.id,
            AthleteMonthlyNewsletter.year == year,
            AthleteMonthlyNewsletter.month == month,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing is not None and not force:
        if existing.status in {NewsletterStatus.approved, NewsletterStatus.sent}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Ya existe un boletín {existing.status.value} para el periodo "
                    f"{year}-{month:02d}. Usa force=true para regenerar."
                ),
            )

    # Construir métricas
    metrics_snapshot = await build_newsletter_metrics(db, athlete.id, year, month)

    # Construir nombres prohibidos para guardrails (compañeros del club)
    forbidden_names = await _build_forbidden_names(db, athlete.club_id)

    # ``existing`` ya trae ``selected_race_insight_ids`` si el coach adjuntó
    # insights vía attach-insights antes de generar (upsert). Sin fila
    # previa, un objeto transitorio (nunca añadido a la sesión) basta para
    # ``select_insight`` — solo lee athlete_id/year/month/
    # selected_race_insight_ids, y una lista vacía retorna None de inmediato
    # sin tocar la DB.
    nl_for_insight_selection = existing or AthleteMonthlyNewsletter(
        athlete_id=athlete.id, year=year, month=month, selected_race_insight_ids=None
    )
    ai_narrative_dict, stage_log_json, error_message = await _build_v2_stage_log_content(
        db=db,
        athlete=athlete,
        year=year,
        month=month,
        metrics_snapshot=metrics_snapshot,
        forbidden_names=forbidden_names,
        has_ai_consent=has_ai_consent,
        llm_provider=llm_provider,
        prompt_registry=prompt_registry,
        nl_for_insight_selection=nl_for_insight_selection,
    )

    now = datetime.now(timezone.utc)
    # El boletín se considera 'draft' aunque la IA haya fallado: el fallback
    # estático garantiza un documento válido y revisable por el entrenador.
    # error_message se conserva para trazabilidad/telemetría.
    final_status = NewsletterStatus.draft

    if existing is not None:
        existing.status = final_status
        existing.metrics_snapshot = metrics_snapshot
        existing.ai_narrative = ai_narrative_dict
        existing.stage_log_json = stage_log_json
        existing.badges_earned = metrics_snapshot.get("email_blocks", {}).get("badges", {}).get("items")
        existing.generated_by_user_id = current_user.id
        existing.error_message = error_message
        existing.pdf_storage_url = None
        existing.pdf_generated_at = None
        existing.pdf_sha256 = None
        await db.flush()
        return existing

    nl = AthleteMonthlyNewsletter(
        athlete_id=athlete.id,
        year=year,
        month=month,
        status=final_status,
        metrics_snapshot=metrics_snapshot,
        ai_narrative=ai_narrative_dict,
        stage_log_json=stage_log_json,
        badges_earned=metrics_snapshot.get("email_blocks", {}).get("badges", {}).get("items"),
        generated_by_user_id=current_user.id,
        error_message=error_message,
        created_at=now,
        updated_at=now,
    )
    db.add(nl)
    await db.flush()
    return nl


# ---------------------------------------------------------------------------
# Endpoint batch — POST /api/clubs/{club_id}/monthly-newsletters/batch
# ---------------------------------------------------------------------------


@clubs_router.post(
    "/{club_id}/monthly-newsletters/batch",
    response_model=AthleteNewsletterBatchResult,
    status_code=status.HTTP_200_OK,
    tags=["athlete-newsletters"],
)
async def batch_create_newsletters(
    club_id: int,
    body: AthleteNewsletterBatchCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    llm_provider=Depends(get_llm_provider),
    prompt_registry=Depends(get_prompt_registry),
) -> AthleteNewsletterBatchResult:
    """Crea drafts para todos los atletas activos del club en el periodo.

    Idempotente: atletas que ya tienen newsletter en cualquier estado se omiten.
    """
    # Verificar acceso al club
    club_role = await user_club_role(db, current_user.id, club_id)
    if current_user.role != UserRole.admin and club_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este club.",
        )

    _validate_period(body.year, body.month, force=body.force)

    # Obtener atletas activos del club
    athletes_result = await db.execute(
        select(Athlete).where(Athlete.club_id == club_id)
    )
    athletes = athletes_result.scalars().all()

    total = len(athletes)
    created = 0
    skipped = 0
    failed = 0
    newsletter_ids: list[int] = []
    errors: list[str] = []

    for athlete in athletes:
        # Verificar si ya existe
        existing_result = await db.execute(
            select(AthleteMonthlyNewsletter).where(
                AthleteMonthlyNewsletter.athlete_id == athlete.id,
                AthleteMonthlyNewsletter.year == body.year,
                AthleteMonthlyNewsletter.month == body.month,
            )
        )
        if existing_result.scalar_one_or_none() is not None:
            skipped += 1
            continue

        try:
            nl = await _generate_newsletter_for_athlete(
                db=db,
                athlete=athlete,
                year=body.year,
                month=body.month,
                current_user=current_user,
                force=body.force,
                llm_provider=llm_provider,
                prompt_registry=prompt_registry,
            )
            newsletter_ids.append(nl.id)
            if nl.status == NewsletterStatus.failed:
                failed += 1
                # error_message ya está sanitizado (catálogo genérico)
                errors.append(f"Atleta ID {athlete.id}: {nl.error_message or 'unknown'}")
            else:
                created += 1
        except HTTPException as exc:
            skipped += 1
            if exc.status_code == status.HTTP_409_CONFLICT:
                errors.append(f"Atleta ID {athlete.id}: consent_missing")
            else:
                errors.append(f"Atleta ID {athlete.id}: http_{exc.status_code}")
        except Exception:
            failed += 1
            # No exponer el tipo de excepción — puede revelar detalles de implementación
            errors.append(f"Atleta ID {athlete.id}: internal_error")

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return AthleteNewsletterBatchResult(
        period_year=body.year,
        period_month=body.month,
        total_athletes=total,
        created=created,
        skipped=skipped,
        failed=failed,
        newsletter_ids=newsletter_ids,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# POST /api/athletes/{athlete_id}/monthly-newsletters
# ---------------------------------------------------------------------------


@router.post(
    "/{athlete_id}/monthly-newsletters",
    response_model=AthleteNewsletterRead,
    status_code=status.HTTP_201_CREATED,
    tags=["athlete-newsletters"],
)
async def create_newsletter(
    athlete_id: int,
    body: AthleteNewsletterCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    llm_provider=Depends(get_llm_provider),
    prompt_registry=Depends(get_prompt_registry),
) -> AthleteNewsletterRead:
    """Crea o regenera el borrador del boletín para un atleta."""
    athlete = await _verify_coach_athlete_access(db, current_user, athlete_id)
    _validate_period(body.year, body.month, force=body.force)

    try:
        nl = await _generate_newsletter_for_athlete(
            db=db,
            athlete=athlete,
            year=body.year,
            month=body.month,
            current_user=current_user,
            force=body.force,
            llm_provider=llm_provider,
            prompt_registry=prompt_registry,
        )
        await db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        logger.error(
            "Error generando newsletter | athlete_id=%d period=%d-%02d error_type=%s",
            athlete_id, body.year, body.month, type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al generar el boletín.",
        ) from exc

    return AthleteNewsletterRead.from_orm_model(nl)


# ---------------------------------------------------------------------------
# GET /api/athletes/{athlete_id}/monthly-newsletters
# ---------------------------------------------------------------------------


@router.get(
    "/{athlete_id}/monthly-newsletters",
    response_model=list[AthleteNewsletterRead],
    tags=["athlete-newsletters"],
)
async def list_newsletters(
    athlete_id: int,
    limit: int = Query(default=12, ge=1, le=60),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> list[AthleteNewsletterRead]:
    """Lista los boletines de un atleta (coach del mismo club)."""
    await _verify_coach_athlete_access(db, current_user, athlete_id)

    result = await db.execute(
        select(AthleteMonthlyNewsletter)
        .where(AthleteMonthlyNewsletter.athlete_id == athlete_id)
        .order_by(
            AthleteMonthlyNewsletter.year.desc(),
            AthleteMonthlyNewsletter.month.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    newsletters = result.scalars().all()
    return [AthleteNewsletterRead.from_orm_model(nl) for nl in newsletters]


# ---------------------------------------------------------------------------
# GET /api/athletes/{athlete_id}/monthly-newsletters/{id}
# ---------------------------------------------------------------------------


@router.get(
    "/{athlete_id}/monthly-newsletters/{newsletter_id}",
    response_model=AthleteNewsletterRead,
    tags=["athlete-newsletters"],
)
async def get_newsletter(
    athlete_id: int,
    newsletter_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> AthleteNewsletterRead:
    """Detalle de un boletín."""
    await _verify_coach_athlete_access(db, current_user, athlete_id)
    nl = await _get_newsletter_or_404(db, newsletter_id, athlete_id)
    delivery = await _build_delivery_rows(db, nl.id)
    return AthleteNewsletterRead.from_orm_model(nl, delivery=delivery)


# ---------------------------------------------------------------------------
# GET /api/athletes/{athlete_id}/monthly-newsletters/{id}/pdf
# ---------------------------------------------------------------------------


@router.get(
    "/{athlete_id}/monthly-newsletters/{newsletter_id}/pdf",
    tags=["athlete-newsletters"],
)
async def download_newsletter_pdf(
    athlete_id: int,
    newsletter_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    document_generator=Depends(get_document_generator),
) -> Response:
    """Descarga el PDF de la bitácora (genera si no existe aún).

    ``generate_stage_log_pdf`` — máx. 3 páginas, anexo de crecimiento
    condicional (solo cuando hubo medición o carrera en el mes).
    """
    athlete = await _verify_coach_athlete_access(db, current_user, athlete_id)
    nl = await _get_newsletter_or_404(db, newsletter_id, athlete_id)

    if not nl.stage_log_json:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este boletín todavía no tiene una bitácora generada.",
        )

    snapshot = nl.metrics_snapshot or {}
    pdf_only_blocks = snapshot.get("pdf_only_blocks", {})
    email_blocks = snapshot.get("email_blocks", {})

    from app.services.notification.athlete_newsletter_pdf import generate_stage_log_pdf
    from app.services.training.stage_log import StageLog, to_parent_dto

    stage_log_obj = StageLog.model_validate(nl.stage_log_json)
    parent_dto = to_parent_dto(stage_log_obj, nl.hidden_blocks)

    doc, sha256 = await generate_stage_log_pdf(
        generator=document_generator,
        athlete_first_name=athlete.first_name,
        athlete_last_name=athlete.last_name,
        athlete_id=athlete.id,
        year=nl.year,
        month=nl.month,
        stage_log=parent_dto,
        anthropometry=pdf_only_blocks.get("anthropometry"),
        charts_context=pdf_only_blocks.get("charts_context"),
        percentile_curves=pdf_only_blocks.get("percentile_curves"),
        race_results=email_blocks.get("race_results"),
    )

    # Actualizar hash si cambió
    if nl.pdf_sha256 != sha256:
        nl.pdf_sha256 = sha256
        nl.pdf_generated_at = datetime.now(timezone.utc)
        await db.flush()
        await db.commit()

    return Response(
        content=doc.data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{doc.filename}"',
            "X-PDF-SHA256": sha256,
        },
    )


# ---------------------------------------------------------------------------
# GET /api/athletes/{athlete_id}/monthly-newsletters/{id}/render?surface=email
# ---------------------------------------------------------------------------


@router.get(
    "/{athlete_id}/monthly-newsletters/{newsletter_id}/render",
    tags=["athlete-newsletters"],
)
async def render_newsletter_surface(
    athlete_id: int,
    newsletter_id: int,
    surface: Literal["email"] = Query(default="email"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    template_registry=Depends(get_template_registry),
) -> Response:
    """Devuelve el HTML del email tal como lo verá la familia (feature 038,
    AC-4.1: toggle "Correo" del studio, ``EmailPreviewFrame`` en un
    ``<iframe sandbox>``).

    - Único ``surface`` soportado hoy: ``email`` (contracts/api.md §Coach).
    - El nombre del padre se reemplaza por "Familia" — este preview es
      accesible al coach, que no debe ver el nombre real de un padre que no
      sea el suyo (defensa en profundidad, aunque hoy la ruta ya exige que
      el atleta pertenezca al club del coach).
    - 409 si ``stage_log_json`` todavía no se derivó — nada family-safe que
      renderizar (mismo criterio que ``parent_newsletters.py``).
    - ``Content-Security-Policy: sandbox`` — el HTML nunca debe poder
      ejecutar scripts ni navegar el resto del studio.
    """
    athlete = await _verify_coach_athlete_access(db, current_user, athlete_id)
    nl = await _get_newsletter_or_404(db, newsletter_id, athlete_id)

    if not nl.stage_log_json:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Este boletín todavía no tiene una bitácora generada para "
                "previsualizar."
            ),
        )

    from app.services.notification.newsletter_dispatcher import _render_email_template
    from app.services.training.stage_log import StageLog, to_parent_dto

    stage_log_obj = StageLog.model_validate(nl.stage_log_json)
    parent_dto = to_parent_dto(stage_log_obj, nl.hidden_blocks)

    cta_url = f"{settings.frontend_base_url}/my-athletes/{athlete_id}/bitacora/{nl.id}"

    email_context = {
        "parent_name": "Familia",
        "club_name": "Club Deportivo Trocha y Ruta",
        "month_label": _month_label(nl.year, nl.month),
        "season_year": str(nl.year),
        "children": [
            {
                "athlete_id": athlete_id,
                "athlete_first_name": athlete.first_name,
                "stage_log": parent_dto,
                "cta_url": cta_url,
                "cta_label": "Ver la bitácora completa",
            }
        ],
    }

    html = _render_email_template(
        template_registry, email_context, body_path="email/athlete_stage_log.html"
    )

    return Response(
        content=html,
        media_type="text/html",
        headers={"Content-Security-Policy": "sandbox"},
    )


def _month_label(year: int, month: int) -> str:
    months_es = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]
    return f"{months_es[month - 1]} {year}"


async def _rederive_stage_log(
    db: AsyncSession,
    nl: AthleteMonthlyNewsletter,
    athlete: Athlete,
) -> None:
    """Re-deriva ``stage_log_json`` tras un PATCH que tocó contenido de la bitácora.

    Se protege con un ``except Exception`` amplio (no solo ``ImportError``):
    la responsabilidad de contenido (``stage_overrides``, ``hidden_blocks``,
    ``coach_note``) ya se persistió antes de llamar a este helper, así que un
    fallo acá nunca tira la respuesta 200 del PATCH — el coach sigue viendo
    el ``stage_log_json`` previo hasta el próximo PATCH o regeneración
    exitosa.

    ``build_stage_log`` firma:
    ``build_stage_log(snapshot, narrative, family_input, overrides,
    coach_note, hidden_blocks, athlete_sex, athlete_first_name) -> StageLog``.
    """
    try:
        from app.services.training.stage_log_builder import build_stage_log
        from app.services.privacy import athlete_has_ai_processing_consent
    except Exception as exc:  # noqa: BLE001 — ver docstring: import defensivo
        logger.debug(
            "stage_log_builder aun no disponible (o con error de import) — "
            "PATCH persiste columnas v2 pero no re-deriva stage_log_json "
            "todavia | newsletter_id=%d error_type=%s",
            nl.id, type(exc).__name__,
        )
        return

    try:
        consent = await athlete_has_ai_processing_consent(athlete.id, db)
        # ``_resolve_family_insight`` combina select_insight (037) +
        # filter_for_family (recorte determinista) + el valida_label del
        # evento — pasar el tuple crudo de select_insight acá (versión
        # anterior de este helper) dejaba analyst_reading siempre vacío,
        # porque build_stage_log espera un Mapping/objeto con
        # valida_label/source_insight_id, no un tuple (insight_id, InsightV3).
        family_input = await _resolve_family_insight(db, nl, athlete, consent)
        stage_log = build_stage_log(
            nl.metrics_snapshot,
            nl.ai_narrative,
            family_input,
            nl.stage_overrides,
            nl.coach_note,
            nl.hidden_blocks,
            _athlete_sex_value(athlete),
            athlete.first_name,
        )
        if nl.ai_narrative:
            persisted_violations = nl.ai_narrative.get("grounding_violations")
            if persisted_violations:
                stage_log.grounding_violations = list(persisted_violations)
        nl.stage_log_json = stage_log.model_dump(mode="json")
    except Exception as exc:
        # Best-effort: las columnas ya persistieron (stage_overrides,
        # hidden_blocks, coach_note); si la re-derivación falla el coach
        # sigue viendo el stage_log_json previo hasta el próximo PATCH o
        # regeneración exitosa, en vez de perder la edición.
        logger.warning(
            "Error re-derivando stage_log_json en PATCH | newsletter_id=%d "
            "error_type=%s",
            nl.id, type(exc).__name__,
        )


# ---------------------------------------------------------------------------
# PATCH /api/athletes/{athlete_id}/monthly-newsletters/{id}
# ---------------------------------------------------------------------------


@router.patch(
    "/{athlete_id}/monthly-newsletters/{newsletter_id}",
    response_model=AthleteNewsletterRead,
    tags=["athlete-newsletters"],
)
async def patch_newsletter(
    athlete_id: int,
    newsletter_id: int,
    body: AthleteNewsletterPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> AthleteNewsletterRead:
    """Edita el contenido de la bitácora (feature 038).

    - Se acepta con status ``draft`` o ``approved``; si estaba ``approved``
      y el PATCH cambió algo, vuelve a ``draft`` (una edición invalida la
      aprobación previa — feature 038 AC-4.4 / contracts/api.md §Coach
      PATCH). Cualquier otro estado (``sent``, ``failed``, ``outdated``) →
      409.
    - PATCH parcial por diseño: solo se tocan las columnas cuyo campo llegó
      en el body (``stage_overrides``, ``hidden_blocks``, ``coach_note``,
      ``selected_race_insight_ids``).
    - ``selected_race_insight_ids`` solo reordena: debe ser una permutación
      exacta del valor ya guardado (mismo multiset), si no → 422. Para
      agregar/quitar insights se usa ``POST .../attach-insights``.
    - ``coach_note`` pasa por el mismo guard de redacción de nombres
      (compañeros del club) que la narrativa IA del boletín antes de
      persistir.
    - Cualquier PATCH que cambie contenido invalida el PDF ya generado
      (``pdf_sha256 = None``) para que "Descargar PDF" regenere en la
      próxima descarga (lógica ya existente, reutilizada acá).
    """
    athlete = await _verify_coach_athlete_access(db, current_user, athlete_id)
    nl = await _get_newsletter_or_404(db, newsletter_id, athlete_id)

    if nl.status not in (NewsletterStatus.draft, NewsletterStatus.approved):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Solo se puede editar un boletín en estado 'draft' o "
                f"'approved'. Estado actual: '{nl.status.value}'."
            ),
        )

    content_changed = False

    if body.stage_overrides is not None:
        nl.stage_overrides = body.stage_overrides
        content_changed = True

    if body.hidden_blocks is not None:
        nl.hidden_blocks = body.hidden_blocks
        content_changed = True

    if body.coach_note is not None:
        from app.services.ai.use_cases.monthly_report import _redact_names

        forbidden_names = await _build_forbidden_names(db, athlete.club_id)
        nl.coach_note = _redact_names(body.coach_note, forbidden_names) or None
        content_changed = True

    if body.selected_race_insight_ids is not None:
        current_ids = nl.selected_race_insight_ids or []
        if sorted(body.selected_race_insight_ids) != sorted(current_ids):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "selected_race_insight_ids debe ser una permutación de "
                    "los insights ya adjuntados a este boletín. Usa "
                    "POST .../attach-insights para agregar o quitar."
                ),
            )
        nl.selected_race_insight_ids = body.selected_race_insight_ids
        content_changed = True

    if content_changed and nl.status == NewsletterStatus.approved:
        nl.status = NewsletterStatus.draft
        nl.approved_by_user_id = None
        nl.approved_at = None

    if content_changed:
        nl.pdf_sha256 = None
        await _rederive_stage_log(db, nl, athlete)

    nl.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.commit()

    return AthleteNewsletterRead.from_orm_model(nl)


# ---------------------------------------------------------------------------
# POST /api/athletes/{athlete_id}/monthly-newsletters/{id}/regenerate-block
# ---------------------------------------------------------------------------


@router.post(
    "/{athlete_id}/monthly-newsletters/{newsletter_id}/regenerate-block",
    response_model=AthleteNewsletterRead,
    tags=["athlete-newsletters"],
)
async def regenerate_newsletter_block(
    athlete_id: int,
    newsletter_id: int,
    body: RegenerateBlockRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    llm_provider=Depends(get_llm_provider),
    prompt_registry=Depends(get_prompt_registry),
) -> AthleteNewsletterRead:
    """Regenera un único bloque narrativo de la bitácora (feature 038, T201).

    contracts/api.md §Coach POST .../regenerate-block:
    - 409 si el boletín no es v2, o si ``status == sent``.
    - 451 si el atleta no tiene consentimiento IA (Ley 1581/2012 Art. 9).
    - 503 si el proveedor falla (timeout/JSON inválido incluso tras
      reparación) o si los guardrails rechazan el bloque regenerado — en
      ambos casos el bloque anterior queda intacto, sin persistir nada.
    - 200: el bloque queda en ``ai_narrative[block]``, cualquier override
      manual de ese bloque se limpia (``stage_overrides``), y
      ``stage_log_json`` se re-deriva (``block_states[block] = "ai"``).
    """
    athlete = await _verify_coach_athlete_access(db, current_user, athlete_id)
    nl = await _get_newsletter_or_404(db, newsletter_id, athlete_id)

    if nl.status == NewsletterStatus.sent:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede regenerar un bloque de un boletín ya enviado.",
        )

    from app.services.privacy import athlete_has_ai_processing_consent

    has_consent = await athlete_has_ai_processing_consent(athlete.id, db)
    if not has_consent:
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail=(
                "No se puede regenerar con IA: el atleta no tiene "
                "consentimiento de procesamiento con IA (Ley 1581/2012 Art. 9)."
            ),
        )

    from app.services.ai.errors import LLMSchemaError
    from app.services.ai.use_cases.athlete_monthly_newsletter_v2 import (
        AthleteMonthlyNewsletterV2UseCase,
        StageNarrativeLLMTimeout,
        build_context_from_metrics_v2,
    )
    from app.services.ai.use_cases.monthly_report import _redact_names

    forbidden_names = await _build_forbidden_names(db, athlete.club_id)
    family_input = await _resolve_family_insight(db, nl, athlete, has_consent)
    previous_stage_title, previous_stage_text = await _previous_stage_texts(
        db, athlete.id, nl.year, nl.month
    )

    ctx = build_context_from_metrics_v2(
        nl.metrics_snapshot or {},
        nl.year,
        nl.month,
        forbidden_names,
        athlete_sex=_athlete_sex_value(athlete),
        analyst_reading_input=family_input,
        previous_stage_title=previous_stage_title,
        previous_stage_text=previous_stage_text,
    )

    # La instrucción libre del coach ("menciona la lluvia") se inserta tal
    # cual en el prompt (ver athlete_monthly_newsletter_v2.j2 §"Bloque
    # solicitado") — a diferencia de coach_note (que solo se persiste), este
    # texto viaja SIEMPRE a un proveedor de IA externo, así que debe pasar
    # por el mismo guard de redacción de nombres antes de llegar ahí (Ley
    # 1581 / CLAUDE.md: nunca nombres reales a un proveedor de IA).
    safe_instruction = (
        _redact_names(body.instruction, forbidden_names) if body.instruction else None
    )

    uc = AthleteMonthlyNewsletterV2UseCase(provider=llm_provider, registry=prompt_registry)
    try:
        new_value = await uc.regenerate_block(ctx, body.block, instruction=safe_instruction)
    except (StageNarrativeLLMTimeout, LLMSchemaError) as exc:
        logger.warning(
            "Fallo del proveedor IA regenerando bloque | newsletter_id=%d "
            "block=%s error_type=%s",
            nl.id, body.block, type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El proveedor de IA no pudo generar el bloque. Intenta de nuevo.",
        ) from exc
    except Exception as exc:
        logger.error(
            "Error IA inesperado regenerando bloque | newsletter_id=%d "
            "block=%s error_type=%s",
            nl.id, body.block, type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El proveedor de IA no pudo generar el bloque. Intenta de nuevo.",
        ) from exc

    if new_value is None:
        # Guardrails rechazaron el bloque regenerado (grounding/frase
        # prohibida/nombre/etc.) — mismo tratamiento que un fallo del
        # proveedor: el bloque anterior queda intacto, nada se persiste.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El proveedor de IA no generó un bloque válido. Intenta de nuevo.",
        )

    ai_narrative = dict(nl.ai_narrative or {})
    ai_narrative[body.block] = _serialize_block_value(new_value)
    nl.ai_narrative = ai_narrative

    if nl.stage_overrides and body.block in nl.stage_overrides:
        overrides = dict(nl.stage_overrides)
        overrides.pop(body.block, None)
        nl.stage_overrides = overrides or None

    if nl.status == NewsletterStatus.approved:
        nl.status = NewsletterStatus.draft
        nl.approved_by_user_id = None
        nl.approved_at = None

    nl.pdf_sha256 = None
    await _rederive_stage_log(db, nl, athlete)
    nl.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.commit()

    return AthleteNewsletterRead.from_orm_model(nl)


# ---------------------------------------------------------------------------
# POST /api/athletes/{athlete_id}/monthly-newsletters/{id}/approve
# ---------------------------------------------------------------------------


@router.post(
    "/{athlete_id}/monthly-newsletters/{newsletter_id}/approve",
    response_model=AthleteNewsletterRead,
    tags=["athlete-newsletters"],
)
async def approve_newsletter(
    athlete_id: int,
    newsletter_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> AthleteNewsletterRead:
    """Aprueba el boletín (draft → approved)."""
    await _verify_coach_athlete_access(db, current_user, athlete_id)
    nl = await _get_newsletter_or_404(db, newsletter_id, athlete_id)

    if nl.status != NewsletterStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Solo se puede aprobar un boletín en estado 'draft'. Estado actual: '{nl.status.value}'.",
        )

    now = datetime.now(timezone.utc)
    nl.status = NewsletterStatus.approved
    nl.approved_by_user_id = current_user.id
    nl.approved_at = now
    nl.updated_at = now
    await db.flush()
    await db.commit()

    return AthleteNewsletterRead.from_orm_model(nl)


# ---------------------------------------------------------------------------
# POST /api/athletes/{athlete_id}/monthly-newsletters/{id}/send
# ---------------------------------------------------------------------------


@router.post(
    "/{athlete_id}/monthly-newsletters/{newsletter_id}/send",
    status_code=status.HTTP_200_OK,
    tags=["athlete-newsletters"],
)
async def send_newsletter(
    athlete_id: int,
    newsletter_id: int,
    force_individual: bool = Query(default=False),
    force_resend: bool = Query(
        default=False,
        description=(
            "(feature 038, T302 DeliveryPanel) Reenvía aunque el boletín ya "
            "esté en status=sent. Sin este flag, un boletín sent → 409."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    email_settings=Depends(get_email_settings),
    template_registry=Depends(get_template_registry),
    document_generator=Depends(get_document_generator),
) -> dict:
    """Envía el boletín a los padres del atleta.

    - Requiere status=approved (o status=sent con force_resend=true).
    - Si el padre tiene otros hijos con newsletter en draft del mismo periodo,
      bloquea el envío a menos que force_individual=true.
    - Es idempotente: si ya está sent y no se pide force_resend, retorna 409.
    """
    await _verify_coach_athlete_access(db, current_user, athlete_id)
    nl = await _get_newsletter_or_404(db, newsletter_id, athlete_id)

    if nl.status == NewsletterStatus.sent and not force_resend:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este boletín ya fue enviado. Usa force_resend si necesitas reenviar.",
        )

    resending_sent = force_resend and nl.status == NewsletterStatus.sent
    if nl.status != NewsletterStatus.approved and not resending_sent:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Solo se puede enviar un boletín aprobado. Estado actual: '{nl.status.value}'.",
        )

    from app.services.notification import create_email_client
    from app.services.notification.newsletter_dispatcher import dispatch_newsletters

    email_client = create_email_client(email_settings)

    dispatch_result = await dispatch_newsletters(
        db=db,
        email_client=email_client,
        registry=template_registry,
        newsletter_ids=[nl.id],
        force_individual=force_individual,
        force_resend=force_resend,
    )

    if dispatch_result.newsletters_blocked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No se puede enviar: el padre tiene otros atletas con boletines "
                "en estado 'draft' para este periodo. Apruébalos primero o "
                "usa force_individual=true."
            ),
        )

    return {
        "newsletter_id": nl.id,
        "status": "sent" if nl.id in dispatch_result.newsletters_sent else "failed",
        "emails_sent": dispatch_result.emails_sent,
        "errors": dispatch_result.errors,
    }


# ---------------------------------------------------------------------------
# POST /api/athletes/{athlete_id}/monthly-newsletters/attach-insights
# ---------------------------------------------------------------------------


@router.post(
    "/{athlete_id}/monthly-newsletters/attach-insights",
    response_model=AttachInsightsResponse,
    status_code=status.HTTP_200_OK,
    tags=["athlete-newsletters"],
)
async def attach_insights(
    athlete_id: int,
    body: AttachInsightsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> AttachInsightsResponse:
    """Adjunta insights de race-analysis aprobados a un boletín mensual.

    Lógica:
    - RBAC: solo coach del club del atleta o admin global. Parent → 403.
    - Valida que todos los insight_ids pertenecen al atleta y tienen is_active=1.
    - Si algún insight no cumple → 400 con detalle de cuáles fallaron.
    - Si algún insight tiene is_fallback=True (feature 036, US4, T026) → 422:
      un placeholder de análisis fallido nunca se adjunta, ni siquiera si el
      coach envía su ID explícitamente.
    - year/month default al mes/año actuales en zona Colombia (America/Bogota).
    - Upsert del newsletter:
        - Si existe: append + dedupe preservando orden (items nuevos al final). created=False.
        - Si no existe: crea con status=draft, selected_race_insight_ids=[...]. created=True.

    Privacidad Ley 1581:
    - selected_race_insight_ids solo accesible a coach/admin.
    - Parent NUNCA llega aquí (RBAC require_role bloquea en Depends).
    """
    from zoneinfo import ZoneInfo

    from app.models.athlete_ai_insight import AthleteAiInsight

    # 1. Verificar acceso al atleta
    await _verify_coach_athlete_access(db, current_user, athlete_id)

    # 2. Resolver year/month con default Colombia
    tz_bogota = ZoneInfo("America/Bogota")
    now_bogota = datetime.now(tz_bogota)
    year = body.year if body.year is not None else now_bogota.year
    month = body.month if body.month is not None else now_bogota.month

    # 3. Validar que todos los insights pertenecen al atleta y están activos
    insights_result = await db.execute(
        select(AthleteAiInsight).where(
            AthleteAiInsight.id.in_(body.insight_ids),
            AthleteAiInsight.athlete_id == athlete_id,
            AthleteAiInsight.is_active == 1,
        )
    )
    valid_insights = insights_result.scalars().all()
    valid_ids = {i.id for i in valid_insights}
    invalid_ids = [iid for iid in body.insight_ids if iid not in valid_ids]

    if invalid_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Los siguientes insight_ids no son válidos para este atleta "
                f"(no existen, pertenecen a otro atleta o están inactivos): {invalid_ids}"
            ),
        )

    # 3b. Rechazar insights marcados como fallback (feature 036, US4, T026):
    # un análisis que falló al generarse no puede llegar al boletín de una
    # familia aunque el coach lo haya aprobado sin darse cuenta. La supresión
    # en el cliente (checkbox oculta) NO es el punto de aplicación — se
    # revalida acá porque el cliente puede enviar el ID igual.
    fallback_ids = sorted(i.id for i in valid_insights if i.is_fallback)
    if fallback_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Los siguientes insight_ids no se pueden adjuntar porque el "
                f"análisis no se generó correctamente: {fallback_ids}. Genera "
                "un nuevo análisis para esa válida antes de adjuntarlo al "
                "boletín."
            ),
        )

    # 4. Lookup newsletter por (athlete_id, year, month)
    nl_result = await db.execute(
        select(AthleteMonthlyNewsletter).where(
            AthleteMonthlyNewsletter.athlete_id == athlete_id,
            AthleteMonthlyNewsletter.year == year,
            AthleteMonthlyNewsletter.month == month,
        )
    )
    nl = nl_result.scalar_one_or_none()
    created = False

    now_utc = datetime.now(timezone.utc)

    if nl is not None:
        # Append + dedupe preservando orden: existentes primero, luego nuevos
        existing_ids: list[int] = nl.selected_race_insight_ids or []
        existing_set = set(existing_ids)
        new_ids = [iid for iid in body.insight_ids if iid not in existing_set]
        nl.selected_race_insight_ids = existing_ids + new_ids
        nl.updated_at = now_utc
        await db.flush()
    else:
        # Crear newsletter mínimo con status draft
        nl = AthleteMonthlyNewsletter(
            athlete_id=athlete_id,
            year=year,
            month=month,
            status=NewsletterStatus.draft,
            selected_race_insight_ids=list(body.insight_ids),
            created_at=now_utc,
            updated_at=now_utc,
        )
        db.add(nl)
        await db.flush()
        created = True

    await db.commit()

    return AttachInsightsResponse(
        newsletter_id=nl.id,
        athlete_id=athlete_id,
        year=year,
        month=month,
        status=nl.status,
        selected_race_insight_ids=nl.selected_race_insight_ids or [],
        created=created,
    )


# ---------------------------------------------------------------------------
# GET /api/training/athlete-newsletters/summary
# ---------------------------------------------------------------------------


def _summarize_newsletter_status(
    status_value: NewsletterStatus | None,
) -> Literal["none", "draft", "sent"]:
    """Colapsa el estado completo del boletín en los 3 estados públicos del resumen.

    - Sin fila (status_value=None) -> "none": el atleta aún no tiene boletín
      para el periodo.
    - sent / outdated -> "sent": 'outdated' solo se alcanza a partir de
      'sent' (ver app/services/race/run_staleness.py, que solo marca
      outdated boletines con status==sent) y sent_at permanece poblado en
      ambos casos.
    - draft / approved / failed -> "draft": todavía no llegó a los padres.
      El dashboard ya agrupa 'failed' junto con 'draft' para la acción
      "regenerar" (ver frontend AthleteNewslettersDashboardPage: canRegenerate).
    """
    if status_value is None:
        return "none"
    if status_value in (NewsletterStatus.sent, NewsletterStatus.outdated):
        return "sent"
    return "draft"


@training_router.get(
    "/athlete-newsletters/summary",
    response_model=NewsletterStatusSummary,
    tags=["athlete-newsletters"],
)
async def get_newsletter_status_summary(
    year: int = Query(..., ge=2020, le=2100, description="Año del periodo."),
    month: int = Query(..., ge=1, le=12, description="Mes del periodo (1=enero)."),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> NewsletterStatusSummary:
    """Resumen de estado del boletín mensual por atleta activo, para un periodo dado.

    Reemplaza el fan-out de una petición por atleta (una por tarjeta en el
    dashboard) por una única respuesta de tamaño constante: exactamente un
    item por atleta activo en el alcance del usuario, obtenido vía una sola
    query SQL con LEFT JOIN (sin queries por atleta).

    - Coach: alcance limitado a sus propios clubes (rol coach en
      club_memberships, mismo patrón que app/routers/alerts.py). Sin clubes
      asignados -> items=[] (no se consulta la DB).
    - Admin: todos los clubes, sin filtro.
    - status='none' si el atleta no tiene boletín para (year, month).
    """
    club_filter = None
    if current_user.role != UserRole.admin:
        coach_clubs = _coach_club_ids(current_user)
        if not coach_clubs:
            return NewsletterStatusSummary(year=year, month=month, items=[])
        club_filter = Athlete.club_id.in_(coach_clubs)

    stmt = (
        select(
            Athlete.id,
            AthleteMonthlyNewsletter.id,
            AthleteMonthlyNewsletter.status,
            AthleteMonthlyNewsletter.created_at,
            AthleteMonthlyNewsletter.sent_at,
        )
        .select_from(Athlete)
        .outerjoin(
            AthleteMonthlyNewsletter,
            and_(
                AthleteMonthlyNewsletter.athlete_id == Athlete.id,
                AthleteMonthlyNewsletter.year == year,
                AthleteMonthlyNewsletter.month == month,
            ),
        )
        .order_by(Athlete.id)
    )
    if club_filter is not None:
        stmt = stmt.where(club_filter)

    result = await db.execute(stmt)
    rows = result.all()

    items = [
        NewsletterStatusSummaryItem(
            athlete_id=athlete_id,
            newsletter_id=newsletter_id,
            status=_summarize_newsletter_status(nl_status),
            generated_at=created_at,
            sent_at=sent_at,
        )
        for athlete_id, newsletter_id, nl_status, created_at, sent_at in rows
    ]

    return NewsletterStatusSummary(year=year, month=month, items=items)
