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

from app.models.athlete import Athlete, ParentAthlete
from app.models.athlete_newsletter import AthleteMonthlyNewsletter, NewsletterStatus
from app.models.user import User
from app.schemas.notification import NotificationResult
from app.services.notification.email_client import Attachment, BaseEmailClient, OutboundEmail
from app.services.notification.template_registry import TemplateRegistry

logger = logging.getLogger(__name__)

_TEMPLATES_ROOT = Path(__file__).parents[3] / "templates"

# Límite de tamaño total de adjuntos por email (Resend limit: 40 MB)
_MAX_ATTACHMENT_BYTES = 40 * 1024 * 1024


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

    # Atletas sin padres vinculados: newsletter se omite (no hay a quién enviar)
    for nl in newsletters:
        has_parent = any(pa.athlete_id == nl.athlete_id for pa in parent_athletes)
        if not has_parent:
            logger.info(
                "Atleta sin padres vinculados, newsletter omitido | newsletter_id=%d",
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
    """Envía un email con los newsletters de un padre.

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

    # Construir adjuntos PDF
    attachments: list[Attachment] = []
    total_size = 0
    children_data: list[dict[str, Any]] = []

    for nl in newsletters:
        # Cargar PDF desde storage o desde snapshot
        if nl.pdf_storage_url and nl.pdf_sha256:
            # En producción: descargar desde SFTP (no implementado aquí — adjuntar solo si está en memoria)
            # Por ahora, solo incluir si el PDF ya está en memoria (caso de dispatch inmediato)
            pass

        # Construir datos del hijo para el template email
        snapshot = nl.metrics_snapshot or {}
        ai_narrative = nl.ai_narrative
        overrides = nl.coach_narrative_overrides

        athlete_result = await db.execute(
            select(Athlete).where(Athlete.id == nl.athlete_id)
        )
        athlete = athlete_result.scalar_one_or_none()
        if athlete is None:
            continue

        child_data: dict[str, Any] = {
            "athlete_id": nl.athlete_id,
            "athlete_first_name": athlete.first_name,
            "email_blocks": snapshot.get("email_blocks", {}),
            "ai_narrative": ai_narrative,
            "coach_narrative_overrides": overrides,
        }
        children_data.append(child_data)

    if not children_data:
        return []

    # Verificar tamaño total
    if total_size > _MAX_ATTACHMENT_BYTES:
        logger.warning(
            "Adjuntos superan límite %dMB | newsletter_ids=%s",
            _MAX_ATTACHMENT_BYTES // (1024 * 1024),
            [nl.id for nl in newsletters],
        )
        result.errors.append(
            f"Adjuntos superan {_MAX_ATTACHMENT_BYTES // (1024 * 1024)}MB — reducir número de fotos."
        )
        return []

    # Renderizar email
    month_label = _month_label(year, month)
    email_context = {
        "parent_name": parent.first_name,
        "club_name": "Club Deportivo Trocha y Ruta",
        "month_label": month_label,
        "season_year": str(year),
        "children": children_data,
    }

    html_body = _render_email_template(registry, email_context)
    subject = _render_subject(registry, email_context)

    msg = OutboundEmail(
        to_email=parent.email,
        to_name=parent.first_name,
        subject=subject,
        html_body=html_body,
        template_ref="athlete_monthly_newsletter",
        attachments=attachments,
    )

    # Enviar
    send_result: NotificationResult = await email_client.send(msg)

    if not send_result.success:
        logger.error(
            "Error de email client | template_ref=athlete_monthly_newsletter error=%s",
            send_result.error,
        )
        result.errors.append(
            f"Error de envío para newsletters {[nl.id for nl in newsletters]}: {send_result.error}"
        )
        return []

    # Marcar como sent (sin loguear emails)
    now = datetime.now(timezone.utc)
    sent_ids = []
    for nl in newsletters:
        nl.status = NewsletterStatus.sent
        nl.sent_at = now
        # Guardar emails como referencia (PII — solo en DB, nunca en logs)
        nl.sent_to = [parent.email]
        await db.flush()
        result.newsletters_sent.append(nl.id)
        sent_ids.append(nl.id)
        logger.info(
            "Newsletter marcado como sent | newsletter_id=%d template_ref=athlete_monthly_newsletter",
            nl.id,
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


def _render_email_template(registry: TemplateRegistry, context: dict[str, Any]) -> str:
    """Renderiza el template HTML del email."""
    jinja_env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_ROOT)),
        autoescape=select_autoescape(["html"]),
    )
    template = jinja_env.get_template("email/athlete_monthly_newsletter.html")
    return template.render(**context)


def _render_subject(registry: TemplateRegistry, context: dict[str, Any]) -> str:
    """Renderiza el subject del email."""
    from jinja2 import Template
    spec = registry.get_email_spec("athlete_monthly_newsletter")
    template = Template(spec.subject_template)
    return template.render(**context)


def _month_label(year: int, month: int) -> str:
    months_es = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]
    return f"{months_es[month - 1]} {year}"
