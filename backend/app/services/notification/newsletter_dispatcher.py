"""Dispatcher de boletines mensuales individuales (Fase 1.8).

Responsabilidades:
  1. Agrupar newsletters `approved` por padre (parent_user_id).
  2. Verificar que TODOS los hijos del padre con newsletter del periodo
     estén `approved` antes de enviar (a menos que force_individual=True).
  3. Construir 1 OutboundEmail con N PDFs adjuntos por padre.
  4. Marcar cada newsletter como `sent` con `sent_at` y `sent_to`.
  5. Idempotencia: si ya está `sent`, no reenviar sin flag explícito.

Privacidad:
  - NUNCA loguear emails de padres, nombres de atletas ni contenido del email.
  - Solo loguear: template_ref, newsletter_id, athlete_id (como IDs numéricos).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.athlete import Athlete, ParentAthlete
from app.models.athlete_newsletter import AthleteMonthlyNewsletter, NewsletterStatus
from app.models.newsletter_delivery_event import DeliveryEventType, NewsletterDeliveryEvent
from app.models.user import User
from app.schemas.notification import NotificationResult
from app.services.notification.email_client import (
    BaseEmailClient,
    OutboundEmail,
    ResendEmailClient,
)
from app.services.notification.template_registry import TemplateRegistry
from app.services.training.stage_log import StageLog, to_parent_dto

logger = logging.getLogger(__name__)

_TEMPLATES_ROOT = Path(__file__).parents[3] / "templates"


@dataclass
class DispatchResult:
    """Resultado del dispatch de un lote de newsletters."""

    newsletters_sent: list[int] = field(default_factory=list)
    newsletters_blocked: list[int] = field(default_factory=list)  # hermanos en draft
    newsletters_skipped: list[int] = field(default_factory=list)  # ya sent
    errors: list[str] = field(default_factory=list)
    emails_sent: int = 0


async def dispatch_newsletters(
    db: AsyncSession,
    email_client: BaseEmailClient,
    registry: TemplateRegistry,
    newsletter_ids: list[int],
    force_individual: bool = False,
    force_resend: bool = False,
) -> DispatchResult:
    """Envía los newsletters indicados a los padres.

    Args:
        db: AsyncSession.
        email_client: Cliente de email configurado.
        registry: TemplateRegistry con spec del template email.
        newsletter_ids: IDs de AthleteMonthlyNewsletter a enviar.
        force_individual: Si True, envía aunque otros hijos del periodo estén en draft.
        force_resend: Si True, reenvía aunque ya estén `sent`.

    Returns:
        DispatchResult con stats del envío.
    """
    result = DispatchResult()

    if not newsletter_ids:
        return result

    # Cargar newsletters
    stmt = select(AthleteMonthlyNewsletter).where(
        AthleteMonthlyNewsletter.id.in_(newsletter_ids)
    )
    newsletters_result = await db.execute(stmt)
    newsletters = newsletters_result.scalars().all()

    # Filtrar según estado
    to_dispatch: list[AthleteMonthlyNewsletter] = []
    for nl in newsletters:
        if nl.status == NewsletterStatus.sent and not force_resend:
            result.newsletters_skipped.append(nl.id)
            logger.info(
                "Newsletter ya enviado, omitiendo | newsletter_id=%d",
                nl.id,
            )
            continue
        if nl.status not in {NewsletterStatus.approved, NewsletterStatus.sent}:
            result.newsletters_blocked.append(nl.id)
            logger.info(
                "Newsletter no aprobado, omitiendo | newsletter_id=%d status=%s",
                nl.id,
                nl.status.value,
            )
            continue
        to_dispatch.append(nl)

    if not to_dispatch:
        return result

    # Agrupar por padre
    grouped = await _group_by_parent(db, to_dispatch)

    for parent_id, parent_newsletters in grouped.items():
        try:
            sent_ids = await _send_for_parent(
                db=db,
                email_client=email_client,
                registry=registry,
                parent_id=parent_id,
                newsletters=parent_newsletters,
                force_individual=force_individual,
                result=result,
            )
            if sent_ids:
                result.emails_sent += 1
        except Exception as exc:
            # No loguear PII — solo tipo de error y IDs
            ids = [nl.id for nl in parent_newsletters]
            logger.error(
                "Error enviando newsletters | newsletter_ids=%s error_type=%s",
                ids,
                type(exc).__name__,
            )
            result.errors.append(
                f"Error enviando newsletters {ids}: {type(exc).__name__}"
            )

    await db.commit()
    return result


async def _group_by_parent(
    db: AsyncSession,
    newsletters: list[AthleteMonthlyNewsletter],
) -> dict[int, list[AthleteMonthlyNewsletter]]:
    """Agrupa newsletters por padre (parent_user_id).

    Para cada atleta, busca los padres vinculados. Si un atleta tiene
    múltiples padres, se envía a todos. Si un padre tiene múltiples atletas,
    se agrupa en un solo email.
    """
    athlete_ids = list({nl.athlete_id for nl in newsletters})
    nl_by_athlete = {nl.athlete_id: nl for nl in newsletters}

    # Obtener padres de estos atletas
    pa_result = await db.execute(
        select(ParentAthlete).where(
            ParentAthlete.athlete_id.in_(athlete_ids)
        )
    )
    parent_athletes = pa_result.scalars().all()

    # parent_id → lista de newsletters de sus atletas
    grouped: dict[int, list[AthleteMonthlyNewsletter]] = {}
    for pa in parent_athletes:
        nl = nl_by_athlete.get(pa.athlete_id)
        if nl is None:
            continue
        grouped.setdefault(pa.parent_id, [])
        if nl not in grouped[pa.parent_id]:
            grouped[pa.parent_id].append(nl)

    # Atletas sin padres vinculados: marcar newsletter como failed con código de catálogo
    athletes_with_parent = {pa.athlete_id for pa in parent_athletes}
    for nl in newsletters:
        if nl.athlete_id not in athletes_with_parent:
            nl.status = NewsletterStatus.failed
            nl.error_message = "no_parent_linked"
            await db.flush()
            logger.info(
                "Atleta sin padres vinculados, newsletter marcado failed | newsletter_id=%d",
                nl.id,
            )

    return grouped


async def _send_for_parent(
    db: AsyncSession,
    email_client: BaseEmailClient,
    registry: TemplateRegistry,
    parent_id: int,
    newsletters: list[AthleteMonthlyNewsletter],
    force_individual: bool,
    result: DispatchResult,
) -> list[int]:
    """Envía a un padre las bitácoras de sus hijos para el periodo.

    Si force_individual=False, verifica que todos los hijos con newsletter
    del periodo estén approved. Si alguno está en draft, bloquea el envío.

    Returns:
        Lista de IDs de newsletters marcados como sent.
    """
    if not newsletters:
        return []

    # Verificar que todos los hijos del periodo estén approved
    year = newsletters[0].year
    month = newsletters[0].month

    if not force_individual:
        blocked = await _check_sibling_newsletters(db, parent_id, year, month, newsletters)
        if blocked:
            result.newsletters_blocked.extend([nl.id for nl in newsletters])
            logger.info(
                "Newsletters bloqueados: hermanos en draft | newsletter_ids=%s blocked_ids=%s",
                [nl.id for nl in newsletters],
                blocked,
            )
            return []

    # Cargar datos del padre
    parent_result = await db.execute(
        select(User).where(User.id == parent_id)
    )
    parent = parent_result.scalar_one_or_none()
    if parent is None:
        logger.warning("Padre no encontrado | parent_id=%d", parent_id)
        return []

    return await _send_v2_email(
        db=db,
        email_client=email_client,
        registry=registry,
        parent=parent,
        newsletters=newsletters,
        year=year,
        month=month,
        result=result,
    )


async def _send_v2_email(
    db: AsyncSession,
    email_client: BaseEmailClient,
    registry: TemplateRegistry,
    parent: User,
    newsletters: list[AthleteMonthlyNewsletter],
    year: int,
    month: int,
    result: DispatchResult,
) -> list[int]:
    """Bitácora de etapa (feature 038): deep link al portal (o "Activa tu
    cuenta" cuando el padre no tiene contraseña definida todavía —
    invitación pendiente, AC-5.1)."""
    # `hashed_password` solo se llena cuando el padre acepta la invitación
    # (ver app/services/invitations.py::accept_invite) — antes de eso el
    # usuario puede existir "pre-creado" pero sin poder autenticarse.
    has_account = bool(getattr(parent, "hashed_password", None))

    children_data: list[dict[str, Any]] = []
    for nl in newsletters:
        if not nl.stage_log_json:
            # Sin stage_log_json no hay nada family-safe que enviar (debería
            # haberse re-derivado al aprobar; degradar sin romper el envío
            # de los demás hijos del mismo padre).
            logger.warning(
                "Bitácora sin stage_log_json al enviar | newsletter_id=%d",
                nl.id,
            )
            continue

        athlete_result = await db.execute(
            select(Athlete).where(Athlete.id == nl.athlete_id)
        )
        athlete = athlete_result.scalar_one_or_none()
        if athlete is None:
            continue

        stage_log = StageLog.model_validate(nl.stage_log_json)
        parent_dto = to_parent_dto(stage_log, nl.hidden_blocks)

        if has_account:
            cta_url = (
                f"{settings.frontend_base_url}/my-athletes/{nl.athlete_id}"
                f"/bitacora/{nl.id}"
            )
            cta_label = "Ver la bitácora completa"
        else:
            cta_url = f"{settings.frontend_base_url}/onboarding"
            cta_label = "Activa tu cuenta"

        children_data.append(
            {
                "athlete_id": nl.athlete_id,
                "athlete_first_name": athlete.first_name,
                "stage_log": parent_dto,
                "cta_url": cta_url,
                "cta_label": cta_label,
            }
        )

    if not children_data:
        return []

    month_label = _month_label(year, month)
    email_context = {
        "parent_name": parent.first_name,
        "club_name": "Club Deportivo Trocha y Ruta",
        "month_label": month_label,
        "season_year": str(year),
        "children": children_data,
    }

    html_body = _render_email_template(
        registry, email_context, body_path="email/athlete_stage_log.html"
    )
    subject = _render_subject(registry, "athlete_stage_log", email_context)

    msg = OutboundEmail(
        to_email=parent.email,
        to_name=parent.first_name,
        subject=subject,
        html_body=html_body,
        template_ref="athlete_stage_log",
        attachments=[],
    )

    return await _dispatch_email(
        db=db,
        email_client=email_client,
        parent=parent,
        newsletters=newsletters,
        msg=msg,
        template_ref="athlete_stage_log",
        result=result,
    )


async def _dispatch_email(
    db: AsyncSession,
    email_client: BaseEmailClient,
    parent: User,
    newsletters: list[AthleteMonthlyNewsletter],
    msg: OutboundEmail,
    template_ref: str,
    result: DispatchResult,
) -> list[int]:
    """Envía ``msg`` y, si tiene éxito, marca ``newsletters`` como enviados y
    registra un evento ``sent`` por destinatario en ``newsletter_delivery_events``
    (feature 038, contracts/api.md §Coach POST /{id}/send).

    El único contrato que le importa a esta función es "un
    ``OutboundEmail`` ya armado" + "la lista de newsletters que representa".
    """
    send_result: NotificationResult = await email_client.send(msg)

    if not send_result.success:
        # Sanitizar error del proveedor: puede incluir emails de padres o
        # subjects en respuestas de Resend/SMTP. Redactar emails antes de
        # loguear o propagar al response del API.
        import re
        raw_error = send_result.error or "unknown"
        safe_error = re.sub(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            "[email]",
            str(raw_error),
        )[:120]
        logger.error(
            "Error de email client | template_ref=%s error=%s",
            template_ref,
            safe_error,
        )
        result.errors.append(
            f"Error de envío para newsletters {[nl.id for nl in newsletters]}: {safe_error}"
        )
        return []

    # Marcar como sent (sin loguear emails)
    now = datetime.now(timezone.utc)
    # provider_message_id es el único dato PII-safe que el proveedor
    # devuelve, y SMTP no lo provee de verdad (retorna un id sintético
    # "smtp-<template>", no un id real del proveedor) — por eso solo se
    # persiste con Resend (contracts/api.md).
    provider_message_id = (
        send_result.message_id if isinstance(email_client, ResendEmailClient) else None
    )

    sent_ids = []
    for nl in newsletters:
        nl.status = NewsletterStatus.sent
        nl.sent_at = now
        # Guardar emails como referencia (PII — solo en DB, nunca en logs)
        nl.sent_to = [parent.email]
        db.add(
            NewsletterDeliveryEvent(
                newsletter_id=nl.id,
                parent_user_id=parent.id,
                event_type=DeliveryEventType.sent,
                provider_message_id=provider_message_id,
                occurred_at=now,
            )
        )
        await db.flush()
        result.newsletters_sent.append(nl.id)
        sent_ids.append(nl.id)
        logger.info(
            "Newsletter marcado como sent | newsletter_id=%d template_ref=%s",
            nl.id,
            template_ref,
        )

    return sent_ids


async def _check_sibling_newsletters(
    db: AsyncSession,
    parent_id: int,
    year: int,
    month: int,
    newsletters_to_send: list[AthleteMonthlyNewsletter],
) -> list[int]:
    """Verifica si hay hermanos del padre con newsletter del periodo en estado draft.

    Returns:
        Lista de IDs de newsletters de hermanos que están en draft/failed.
        Si está vacía, el envío puede proceder.
    """
    # Atletas del padre
    pa_result = await db.execute(
        select(ParentAthlete.athlete_id).where(
            ParentAthlete.parent_id == parent_id
        )
    )
    all_athlete_ids = [row for row in pa_result.scalars().all()]

    athletes_being_sent = {nl.athlete_id for nl in newsletters_to_send}
    other_athlete_ids = [aid for aid in all_athlete_ids if aid not in athletes_being_sent]

    if not other_athlete_ids:
        return []

    # Buscar newsletters del periodo para los otros atletas
    other_result = await db.execute(
        select(AthleteMonthlyNewsletter).where(
            AthleteMonthlyNewsletter.athlete_id.in_(other_athlete_ids),
            AthleteMonthlyNewsletter.year == year,
            AthleteMonthlyNewsletter.month == month,
            AthleteMonthlyNewsletter.status.in_([
                NewsletterStatus.draft,
                NewsletterStatus.failed,
            ]),
        )
    )
    blocked = other_result.scalars().all()
    return [nl.id for nl in blocked]


def _render_email_template(
    registry: TemplateRegistry,
    context: dict[str, Any],
    body_path: str = "email/athlete_stage_log.html",
) -> str:
    """Renderiza el template HTML del email en ``body_path`` (relativo a
    ``templates/``). ``registry`` no se usa hoy (la ruta ya viene resuelta
    en ``body_path``) — se conserva como primer parámetro posicional por
    compatibilidad con los tests existentes que ya llaman a esta función."""
    jinja_env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_ROOT)),
        autoescape=select_autoescape(["html"]),
    )
    template = jinja_env.get_template(body_path)
    return template.render(**context)


def _render_subject(
    registry: TemplateRegistry, template_id: str, context: dict[str, Any]
) -> str:
    """Renderiza el subject del email para ``template_id`` (ej.
    ``"athlete_monthly_newsletter"`` o ``"athlete_stage_log"``)."""
    from jinja2 import Template
    spec = registry.get_email_spec(template_id)
    template = Template(spec.subject_template)
    return template.render(**context)


def _month_label(year: int, month: int) -> str:
    months_es = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]
    return f"{months_es[month - 1]} {year}"
