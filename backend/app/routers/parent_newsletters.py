"""Router: bitácora de etapa — portal de padres (feature 038, T202).

  GET  /api/parents/me/athletes/{athlete_id}/newsletters
    — Lista las bitácoras enviadas (``status == sent``) del atleta, más
      recientes primero.
  GET  /api/parents/me/athletes/{athlete_id}/newsletters/{id}
    — Detalle de una bitácora vía ``to_parent_dto`` (allow-list).
  GET  /api/parents/me/athletes/{athlete_id}/newsletters/{id}/pdf
    — Descarga el PDF (regenera si el hash quedó desactualizado).
  POST /api/parents/me/athletes/{athlete_id}/newsletters/{id}/read
    — Idempotente: primera llamada marca ``read_at`` / ``read_by_user_id``
      y registra un evento ``web_read``.

RBAC (contracts/api.md §Parent):
  - Exclusivo del rol ``parent`` — coach/admin reciben 403.
  - El atleta debe estar vinculado al padre autenticado (``parent_athletes``)
    o el endpoint responde 404 (nunca 403 — no confirmamos existencia de
    atletas ajenos a un padre).

Alcance (desviación documentada, ver T202 en tasks.md):
  la spec solo exige filtrar por ``status == sent``; este router además
  exige ``stage_log_json is not None`` — un boletín ``sent`` cuyo
  ``stage_log_json`` aún no se haya derivado (fallo best-effort en el PATCH
  del coach, ver ``athlete_monthly_newsletters.py::_rederive_stage_log``) no
  aparece aquí todavía — es indistinguible de "no es bitácora" desde este
  router.

Privacidad (Ley 1581, CLAUDE.md):
  - ``stage_log`` SIEMPRE pasa por ``to_parent_dto`` (allow-list) — nunca
    se expone ``stage_log_json`` crudo (tiene ``block_states``,
    ``grounding_violations``, ``analyst_reading.source_insight_id``).
  - Nunca se loguea el nombre del atleta ni el email del padre.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_document_generator, require_role
from app.models.athlete import Athlete
from app.models.athlete_newsletter import AthleteMonthlyNewsletter, NewsletterStatus
from app.models.user import User, UserRole
from app.schemas.parent_newsletter import ParentNewsletterListItem, ParentNewsletterOut
from app.services.permissions import parent_athlete_ids
from app.services.training.stage_log import StageLog, to_parent_dto

logger = logging.getLogger(__name__)

router = APIRouter()


_MONTHS_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def _month_label(year: int, month: int) -> str:
    return f"{_MONTHS_ES[month - 1]} {year}"


async def _verify_parent_athlete_link(
    db: AsyncSession, current_user: User, athlete_id: int
) -> None:
    """404 si el atleta no está vinculado al padre autenticado."""
    linked_ids = await parent_athlete_ids(db, current_user.id)
    if athlete_id not in linked_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atleta no encontrado.",
        )


async def _get_sent_bitacora_or_404(
    db: AsyncSession, athlete_id: int, newsletter_id: int
) -> AthleteMonthlyNewsletter:
    result = await db.execute(
        select(AthleteMonthlyNewsletter).where(
            AthleteMonthlyNewsletter.id == newsletter_id,
            AthleteMonthlyNewsletter.athlete_id == athlete_id,
            AthleteMonthlyNewsletter.status == NewsletterStatus.sent,
        )
    )
    nl = result.scalar_one_or_none()
    # NOTA: el filtro por ``stage_log_json is not None`` se hace en Python,
    # no en SQL — el tipo ``JSON`` de SQLAlchemy persiste un ``None`` de
    # Python como JSON ``null`` (``none_as_null=False`` por defecto), no
    # como SQL ``NULL``, así que ``.is_not(None)`` en el WHERE no filtra lo
    # que uno esperaría en todos los backends.
    if nl is None or nl.stage_log_json is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bitácora no encontrada.",
        )
    return nl


def _to_list_item(nl: AthleteMonthlyNewsletter) -> ParentNewsletterListItem:
    stage_log_json = nl.stage_log_json or {}
    return ParentNewsletterListItem(
        id=nl.id,
        athlete_id=nl.athlete_id,
        year=nl.year,
        month=nl.month,
        period_label=stage_log_json.get("period_label") or _month_label(nl.year, nl.month),
        stage_title=stage_log_json.get("stage_title"),
        sent_at=nl.sent_at,
        read_at=nl.read_at,
    )


def _to_detail(nl: AthleteMonthlyNewsletter) -> ParentNewsletterOut:
    stage_log = StageLog.model_validate(nl.stage_log_json)
    dto = to_parent_dto(stage_log, nl.hidden_blocks)
    return ParentNewsletterOut(
        id=nl.id,
        athlete_id=nl.athlete_id,
        year=nl.year,
        month=nl.month,
        period_label=dto.get("period_label") or _month_label(nl.year, nl.month),
        sent_at=nl.sent_at,
        read_at=nl.read_at,
        has_pdf=bool(nl.pdf_sha256),
        stage_log=dto,
    )


# ---------------------------------------------------------------------------
# GET / — lista de bitácoras enviadas
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ParentNewsletterListItem])
async def list_parent_newsletters(
    athlete_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.parent])),
) -> list[ParentNewsletterListItem]:
    await _verify_parent_athlete_link(db, current_user, athlete_id)

    result = await db.execute(
        select(AthleteMonthlyNewsletter)
        .where(
            AthleteMonthlyNewsletter.athlete_id == athlete_id,
            AthleteMonthlyNewsletter.status == NewsletterStatus.sent,
        )
        .order_by(
            AthleteMonthlyNewsletter.year.desc(),
            AthleteMonthlyNewsletter.month.desc(),
        )
    )
    newsletters = result.scalars().all()
    # Filtro en Python — ver nota en ``_get_sent_bitacora_or_404``.
    return [_to_list_item(nl) for nl in newsletters if nl.stage_log_json is not None]


# ---------------------------------------------------------------------------
# GET /{newsletter_id} — detalle vía to_parent_dto
# ---------------------------------------------------------------------------


@router.get("/{newsletter_id}", response_model=ParentNewsletterOut)
async def get_parent_newsletter(
    athlete_id: int,
    newsletter_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.parent])),
) -> ParentNewsletterOut:
    await _verify_parent_athlete_link(db, current_user, athlete_id)
    nl = await _get_sent_bitacora_or_404(db, athlete_id, newsletter_id)
    return _to_detail(nl)


# ---------------------------------------------------------------------------
# GET /{newsletter_id}/pdf
# ---------------------------------------------------------------------------


@router.get("/{newsletter_id}/pdf")
async def download_parent_newsletter_pdf(
    athlete_id: int,
    newsletter_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.parent])),
    document_generator=Depends(get_document_generator),
) -> Response:
    await _verify_parent_athlete_link(db, current_user, athlete_id)
    nl = await _get_sent_bitacora_or_404(db, athlete_id, newsletter_id)

    athlete_result = await db.execute(select(Athlete).where(Athlete.id == athlete_id))
    athlete = athlete_result.scalar_one_or_none()
    if athlete is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atleta no encontrado.",
        )

    # T203 (misma oleada, feature 038) añadió generate_stage_log_pdf(): el
    # PDF que recibe el padre usa la variante stage-log (máx. 3 páginas,
    # anexo condicional) sobre el mismo `dto` que ya usa la vista web
    # (`_to_detail` arriba) — ambos pasan por to_parent_dto(), nunca por el
    # stage_log_json crudo.
    from app.services.notification.athlete_newsletter_pdf import generate_stage_log_pdf

    snapshot = nl.metrics_snapshot or {}
    pdf_only_blocks = snapshot.get("pdf_only_blocks", {})
    email_blocks = snapshot.get("email_blocks", {})
    stage_log = StageLog.model_validate(nl.stage_log_json)
    dto = to_parent_dto(stage_log, nl.hidden_blocks)

    doc, sha256 = await generate_stage_log_pdf(
        generator=document_generator,
        athlete_first_name=athlete.first_name,
        athlete_last_name=athlete.last_name,
        athlete_id=athlete.id,
        year=nl.year,
        month=nl.month,
        stage_log=dto,
        anthropometry=pdf_only_blocks.get("anthropometry"),
        charts_context=pdf_only_blocks.get("charts_context"),
        percentile_curves=pdf_only_blocks.get("percentile_curves"),
        race_results=email_blocks.get("race_results"),
    )

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
# POST /{newsletter_id}/read — idempotente
# ---------------------------------------------------------------------------


@router.post("/{newsletter_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_parent_newsletter_read(
    athlete_id: int,
    newsletter_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.parent])),
) -> None:
    await _verify_parent_athlete_link(db, current_user, athlete_id)
    nl = await _get_sent_bitacora_or_404(db, athlete_id, newsletter_id)

    if nl.read_at is None:
        nl.read_at = datetime.now(timezone.utc)
        nl.read_by_user_id = current_user.id
        await db.flush()

        try:
            from app.models.newsletter_delivery_event import (
                DeliveryEventType,
                NewsletterDeliveryEvent,
            )

            db.add(
                NewsletterDeliveryEvent(
                    newsletter_id=nl.id,
                    parent_user_id=current_user.id,
                    event_type=DeliveryEventType.web_read,
                    occurred_at=nl.read_at,
                )
            )
            await db.flush()
        except Exception as exc:  # noqa: BLE001 — best-effort, ver docstring del módulo
            logger.warning(
                "Error registrando evento web_read | newsletter_id=%d error_type=%s",
                nl.id, type(exc).__name__,
            )

        await db.commit()

    return None
