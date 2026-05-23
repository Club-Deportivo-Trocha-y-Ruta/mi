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

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.models.club import ClubMember, ClubRole
from app.models.user import User, UserRole
from app.schemas.athlete_newsletter import (
    AthleteNewsletterBatchCreate,
    AthleteNewsletterBatchResult,
    AthleteNewsletterCreate,
    AthleteNewsletterPatch,
    AthleteNewsletterRead,
)
from app.services.permissions import user_club_role

logger = logging.getLogger(__name__)

router = APIRouter()
clubs_router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


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
    """Crea o regenera el borrador del boletín para un atleta."""
    from app.services.privacy import assert_ai_consent_for_newsletter
    from app.services.training.newsletter_builder import build_newsletter_metrics
    from app.services.ai.use_cases.athlete_monthly_newsletter import (
        AthleteNewsletterLLMTimeout,
        AthleteNewsletterUseCase,
        build_context_from_metrics,
    )
    from app.services.ai.errors import LLMSchemaError

    # Verificar consentimiento Ley 1581
    await assert_ai_consent_for_newsletter(db, athlete.id)

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

    # Construir nombres prohibidos para guardrails
    from sqlalchemy import select as sa_select
    from app.models.athlete import ParentAthlete

    # Compañeros del club (para redacción)
    club_athletes_result = await db.execute(
        sa_select(Athlete).where(Athlete.club_id == athlete.club_id)
    )
    club_athletes = club_athletes_result.scalars().all()
    forbidden_names: frozenset[str] = frozenset(
        name
        for a in club_athletes
        for name in [a.first_name, a.last_name, f"{a.first_name} {a.last_name}"]
        if name
    )

    # Generar narrativa IA
    ai_narrative_dict: dict | None = None
    error_message: str | None = None

    try:
        ai_use_case = AthleteNewsletterUseCase(
            provider=llm_provider,
            registry=prompt_registry,
        )
        ai_ctx = build_context_from_metrics(
            metrics_snapshot=metrics_snapshot,
            year=year,
            month=month,
            forbidden_names=forbidden_names,
        )
        ai_result = await ai_use_case.run(ai_ctx)
        ai_narrative_dict = ai_result.model_dump()
    except AthleteNewsletterLLMTimeout:
        logger.warning(
            "Timeout IA para boletín | athlete_id=%d period=%d-%02d",
            athlete.id, year, month,
        )
        error_message = "llm_timeout"
    except LLMSchemaError as exc:
        logger.warning(
            "Error guardrails IA | athlete_id=%d period=%d-%02d error=%s",
            athlete.id, year, month, type(exc).__name__,
        )
        # Catálogo de mensajes genéricos — el detalle técnico queda solo en logs
        # para evitar exponer mensajes del LLM o señales de qué pasó por guardrails.
        error_message = "guardrails_rejected"
    except Exception as exc:
        logger.error(
            "Error IA inesperado | athlete_id=%d period=%d-%02d error_type=%s",
            athlete.id, year, month, type(exc).__name__,
        )
        error_message = "llm_internal_error"

    now = datetime.now(timezone.utc)
    final_status = NewsletterStatus.draft if error_message is None else NewsletterStatus.failed

    if existing is not None:
        existing.status = final_status
        existing.metrics_snapshot = metrics_snapshot
        existing.ai_narrative = ai_narrative_dict
        existing.coach_narrative_overrides = None
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
        coach_narrative_overrides=None,
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
    return AthleteNewsletterRead.from_orm_model(nl)


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
    """Descarga el PDF del boletín (genera si no existe aún)."""
    athlete = await _verify_coach_athlete_access(db, current_user, athlete_id)
    nl = await _get_newsletter_or_404(db, newsletter_id, athlete_id)

    from app.services.notification.athlete_newsletter_pdf import generate_newsletter_pdf

    snapshot = nl.metrics_snapshot or {}
    email_blocks = snapshot.get("email_blocks", {})
    pdf_only_blocks = snapshot.get("pdf_only_blocks", {})

    doc, sha256 = await generate_newsletter_pdf(
        generator=document_generator,
        athlete_first_name=athlete.first_name,
        athlete_last_name=athlete.last_name,
        athlete_id=athlete.id,
        year=nl.year,
        month=nl.month,
        email_blocks=email_blocks,
        pdf_only_blocks=pdf_only_blocks,
        ai_narrative=nl.ai_narrative,
        coach_narrative_overrides=nl.coach_narrative_overrides,
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
    """Edita la narrativa del boletín (solo si status=draft)."""
    await _verify_coach_athlete_access(db, current_user, athlete_id)
    nl = await _get_newsletter_or_404(db, newsletter_id, athlete_id)

    if nl.status != NewsletterStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Solo se puede editar un boletín en estado 'draft'. Estado actual: '{nl.status.value}'.",
        )

    nl.coach_narrative_overrides = body.coach_narrative_overrides.model_dump(exclude_none=True)
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    email_settings=Depends(get_email_settings),
    template_registry=Depends(get_template_registry),
    document_generator=Depends(get_document_generator),
) -> dict:
    """Envía el boletín a los padres del atleta.

    - Requiere status=approved.
    - Si el padre tiene otros hijos con newsletter en draft del mismo periodo,
      bloquea el envío a menos que force_individual=true.
    - Es idempotente: si ya está sent, retorna 409.
    """
    await _verify_coach_athlete_access(db, current_user, athlete_id)
    nl = await _get_newsletter_or_404(db, newsletter_id, athlete_id)

    if nl.status == NewsletterStatus.sent:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este boletín ya fue enviado. Usa force_resend si necesitas reenviar.",
        )

    if nl.status != NewsletterStatus.approved:
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
        force_resend=False,
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
