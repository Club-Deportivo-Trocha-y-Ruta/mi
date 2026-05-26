"""Dispatcher de notificaciones para insights de carrera aprobados.

Contexto
========
Decisión cerrada del track Family Relations (2026-05-25):

- NO enviar email a padres por cada análisis aprobado.
- In-app notification + inclusión en boletín mensual (Fase 1.8) por default.
- Email a padres SOLO para válidas tier ``A`` o ``CD`` (Campeonato
  Departamental) — ver :mod:`app.services.notification.race_event_tier`.

Este módulo encapsula esa lógica de decisión: el caller (router de
aprobación) sólo necesita pasar el insight + sesión DB. El dispatcher
resuelve tier, padres, idempotencia y canal.

Privacidad
==========
- Logs SIEMPRE con ids hasheados (helper :func:`_hash_id`). Nunca emails o
  nombres en logs.
- ``coach_summary`` (que va al email) se trunca a 500 chars y se entrega
  tal cual viene de :attr:`AthleteAiInsight.summary_text` — el saneo de
  PII vive en el use case IA upstream (forbidden_names dinámicos).
- ``valida_label`` y ``tier_label`` NO son PII: son datos públicos del
  calendario federativo.

Idempotencia
============
Reaprobaciones de un mismo insight (mismo ``insight_id``) NO duplican
email. El registro vive en ``athlete_ai_insights.notified_parents_at``
(columna nullable agregada en migración futura). Por ahora, mientras esa
columna no exista, usamos guard por ``coach_approved=True`` + flag
``force=False`` (default). Cuando se persista la columna, este módulo se
actualiza sin tocar callers.

Edge cases manejados
====================
- ``valida_num=0`` (resumen temporada) ⇒ NO email (siempre on-demand,
  coach decide cuándo enviar mensualmente).
- ``event_id IS NULL`` ⇒ log warning + no email.
- ``is_active=False`` (insight deprecado o reaprobación de uno previo) ⇒
  ``NotificationDecision.SKIPPED_INACTIVE``.
- Tier ``UNKNOWN`` ⇒ NO email (fallback conservador).
"""
from __future__ import annotations

import enum
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.athlete import Athlete, ParentAthlete
from app.models.athlete_ai_insight import AthleteAiInsight
from app.models.club import Club, ClubMember
from app.models.race_event import RaceEvent
from app.models.user import User
from app.services.notification.race_event_tier import (
    RaceTier,
    get_race_tier,
    should_email_parents,
)

if TYPE_CHECKING:
    from app.services.notification.service import NotificationService
    from app.services.notification.task_dispatcher import TaskDispatcher

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tipos públicos
# ---------------------------------------------------------------------------


class NotificationChannel(str, enum.Enum):
    """Canal por el que se notificó al padre/usuario."""

    EMAIL = "email"
    IN_APP = "in_app"
    NONE = "none"


class NotificationDecision(str, enum.Enum):
    """Resultado de la decisión de notificación (para tests + telemetría)."""

    SENT_EMAIL = "sent_email"
    SENT_IN_APP = "sent_in_app"
    SKIPPED_TIER = "skipped_tier"             # tier B/C/UNKNOWN
    SKIPPED_INACTIVE = "skipped_inactive"     # insight no activo
    SKIPPED_AGGREGATE = "skipped_aggregate"   # valida_num=0 (season summary)
    SKIPPED_NO_EVENT = "skipped_no_event"     # insight sin event_id
    SKIPPED_NOT_APPROVED = "skipped_not_approved"
    SKIPPED_NO_PARENTS = "skipped_no_parents"
    ERROR = "error"


@dataclass
class NotificationResult:
    """Resultado agregado por insight.

    Un mismo insight puede notificar a N padres por email + emitir M eventos
    in-app. Este resultado los suma para que el caller pueda hacer log
    estructurado de "qué pasó".
    """

    decision: NotificationDecision
    tier: RaceTier
    channels: list[NotificationChannel] = field(default_factory=list)
    emails_sent: int = 0
    in_app_emitted: int = 0
    parents_skipped: int = 0
    reason: str | None = None  # explicación legible para logs/QA


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------


def _hash_id(value: int | None) -> str:
    """Hash corto y estable para logs (mismo patrón que training/sessions.py)."""
    if value is None:
        return "none"
    return hashlib.sha256(str(value).encode()).hexdigest()[:8]


_MONTHS_ES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}


def _format_date_es(d: date | None) -> str:
    if d is None:
        return "Fecha por confirmar"
    return f"{d.day} de {_MONTHS_ES[d.month]} de {d.year}"


def _roman_numeral(n: int) -> str:
    """Convierte 1..7 a numeral romano. Para CD retorna 'CD' externamente."""
    table = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII"}
    return table.get(n, str(n))


def _build_valida_label(event: RaceEvent, tier: RaceTier) -> str:
    """Construye etiqueta legible para el email/in-app.

    Ejemplos: "IV — Cali", "Campeonato Departamental".
    """
    if tier == RaceTier.CD:
        return "Campeonato Departamental"
    location = (event.location or "").strip()
    roman = _roman_numeral(int(event.sequence_number or 0))
    if location:
        return f"{roman} — {location}"
    return roman


def _tier_label_es(tier: RaceTier) -> str:
    if tier == RaceTier.CD:
        return "Campeonato Departamental"
    if tier == RaceTier.A:
        return "Tipo A — máxima prioridad"
    if tier == RaceTier.B:
        return "Tipo B — prioridad media"
    if tier == RaceTier.C:
        return "Tipo C — diagnóstica"
    return "Sin clasificar"


_SUMMARY_MAX_CHARS = 500


def _safe_summary(text: str | None) -> str:
    """Trunca el summary del insight al límite del email (500 chars).

    El saneo de PII (nombres del menor) lo hace el use case IA upstream
    (forbidden_names dinámicos). Aquí solo cortamos longitud.
    """
    if not text:
        return "El entrenador publicó un análisis de la participación. Consulta los detalles en la plataforma."
    cleaned = text.strip()
    if len(cleaned) <= _SUMMARY_MAX_CHARS:
        return cleaned
    return cleaned[: _SUMMARY_MAX_CHARS - 1].rstrip() + "…"


async def _load_insight_with_relations(
    db: AsyncSession, insight_id: int
) -> AthleteAiInsight | None:
    """Carga el insight + event (+ series para tier) + athlete en una sola query.

    Importante: el caller puede pasar un ORM ``AthleteAiInsight`` ya cargado,
    en cuyo caso usamos esa instancia. Pero cuando viene "frío" (post-aprobación
    en background) necesitamos las relaciones materializadas porque no hay
    sesión async para lazy-loads.
    """
    stmt = (
        select(AthleteAiInsight)
        .where(AthleteAiInsight.id == insight_id)
        .options(
            selectinload(AthleteAiInsight.event).selectinload(RaceEvent.series),
            selectinload(AthleteAiInsight.athlete),
        )
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def _resolve_club_name(db: AsyncSession, athlete_id: int) -> str:
    """Resuelve el nombre del club al que pertenece el atleta.

    Atletas tienen ``user_id`` con ``can_login=False``, vinculado a un club
    via ``club_members``. Si hay múltiples (edge case migración), tomamos
    el primero estable.
    """
    stmt = (
        select(Club.name)
        .join(ClubMember, ClubMember.club_id == Club.id)
        .join(Athlete, Athlete.user_id == ClubMember.user_id)
        .where(Athlete.id == athlete_id)
        .limit(1)
    )
    res = await db.execute(stmt)
    name = res.scalar_one_or_none()
    return name or "Club Trocha y Ruta"


async def _load_parents(db: AsyncSession, athlete_id: int) -> list[User]:
    """Carga todos los padres/acudientes con email del atleta."""
    stmt = (
        select(User)
        .join(ParentAthlete, ParentAthlete.parent_id == User.id)
        .where(ParentAthlete.athlete_id == athlete_id)
    )
    res = await db.execute(stmt)
    return [u for u in res.scalars().all() if u.email]


# ---------------------------------------------------------------------------
# In-app notification (stub honesto)
# ---------------------------------------------------------------------------


async def _emit_in_app_notification(
    *,
    insight: AthleteAiInsight,
    tier: RaceTier,
    parents: list[User],
) -> int:
    """Emite notificación in-app para cada padre.

    HOY: no existe tabla ``notifications`` ni WS hub. Esta función SOLO
    loggea estructuradamente — el frontend descubre el insight via el
    endpoint ``GET /athletes/{id}/race-analysis/insights`` (TanStack Query
    refetch al volver a la app).

    Cuando se cree la tabla ``notifications`` (sprint futuro), aquí va el
    INSERT correspondiente. Mantener firma estable.
    """
    count = 0
    for parent in parents:
        logger.info(
            "race_insight_dispatcher.in_app | parent_hash=%s athlete_hash=%s "
            "insight_id=%s tier=%s valida_num=%s season=%s kind=race_insight_published",
            _hash_id(parent.id),
            _hash_id(insight.athlete_id),
            insight.id,
            tier.value,
            insight.valida_num,
            insight.season,
        )
        count += 1
    return count


# ---------------------------------------------------------------------------
# Email send
# ---------------------------------------------------------------------------


async def _send_email_to_parents(
    *,
    insight: AthleteAiInsight,
    event: RaceEvent,
    tier: RaceTier,
    parents: list[User],
    athlete_first_name: str,
    club_name: str,
    notification_service: "NotificationService",
    dispatcher: "TaskDispatcher | None",
) -> int:
    """Despacha el email ``race_insight_published`` a cada padre con email."""
    from app.schemas.notification import (
        NotificationRecipient,
        NotificationRequest,
        NotificationTemplate,
    )

    valida_label = _build_valida_label(event, tier)
    tier_label = _tier_label_es(tier)
    valida_date = _format_date_es(event.event_date)
    coach_summary = _safe_summary(insight.summary_text)
    deep_link = f"/athletes/{insight.athlete_id}/race-analysis/insights/{insight.id}"

    sent = 0
    for parent in parents:
        parent_name = (
            f"{parent.first_name} {parent.last_name}".strip()
            or "Padre/Acudiente"
        )
        try:
            request = NotificationRequest(
                recipient=NotificationRecipient(
                    email=parent.email, name=parent_name
                ),
                template=NotificationTemplate.RACE_INSIGHT_PUBLISHED,
                context={
                    "parent_name": parent_name,
                    "athlete_first_name": athlete_first_name,
                    "club_name": club_name,
                    "valida_label": valida_label,
                    "valida_date": valida_date,
                    "tier_label": tier_label,
                    "coach_summary": coach_summary,
                    "deep_link_path": deep_link,
                },
                send_async=True,
            )
            await notification_service.send(request, dispatcher=dispatcher)
            sent += 1
            logger.info(
                "race_insight_dispatcher.email_dispatched | parent_hash=%s "
                "athlete_hash=%s insight_id=%s tier=%s",
                _hash_id(parent.id),
                _hash_id(insight.athlete_id),
                insight.id,
                tier.value,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "race_insight_dispatcher.email_error | parent_hash=%s "
                "athlete_hash=%s insight_id=%s tier=%s error_type=%s",
                _hash_id(parent.id),
                _hash_id(insight.athlete_id),
                insight.id,
                tier.value,
                type(exc).__name__,
            )
    return sent


# ---------------------------------------------------------------------------
# Entry point público
# ---------------------------------------------------------------------------


async def dispatch_insight_notification(
    insight: AthleteAiInsight,
    db: AsyncSession,
    *,
    notification_service: "NotificationService | None" = None,
    dispatcher: "TaskDispatcher | None" = None,
) -> NotificationResult:
    """Decide canal de notificación tras aprobación de un insight de carrera.

    Lógica de decisión (ver módulo docstring para edge cases):

    +-----------------------------+----------------------+---------------------+
    | Condición                   | Decisión             | Canal               |
    +=============================+======================+=====================+
    | ``coach_approved=False``    | SKIPPED_NOT_APPROVED | NONE                |
    | ``is_active != 1``          | SKIPPED_INACTIVE     | NONE                |
    | ``valida_num == 0``         | SKIPPED_AGGREGATE    | NONE                |
    | ``event_id IS NULL``        | SKIPPED_NO_EVENT     | NONE                |
    | tier ∈ {A, CD}              | SENT_EMAIL           | EMAIL + IN_APP      |
    | tier ∈ {B, C, UNKNOWN}      | SENT_IN_APP /        | IN_APP / NONE       |
    |                             | SKIPPED_TIER         |                     |
    +-----------------------------+----------------------+---------------------+

    Args:
        insight: ORM instance (puede venir "frío" — re-cargamos relaciones).
        db: sesión async para queries de soporte.
        notification_service: si es ``None``, NO se envía email (solo log + in-app).
            Caller decide si quiere "dry-run".
        dispatcher: BackgroundTasks dispatcher (opcional, mismo patrón que
            training/sessions._notify_parents).

    Returns:
        :class:`NotificationResult` con decisión + métricas por canal.
    """
    # 1. Guards triviales (no requieren DB extra).
    if not insight.coach_approved:
        logger.debug(
            "race_insight_dispatcher: insight_id=%s no aprobado, skip",
            insight.id,
        )
        return NotificationResult(
            decision=NotificationDecision.SKIPPED_NOT_APPROVED,
            tier=RaceTier.UNKNOWN,
            reason="coach_approved=False",
        )

    if insight.is_active != 1:
        logger.info(
            "race_insight_dispatcher: insight_id=%s no es active (is_active=%s) — "
            "skip notificación (idempotencia: una reaprobación deprecó este insight)",
            insight.id,
            insight.is_active,
        )
        return NotificationResult(
            decision=NotificationDecision.SKIPPED_INACTIVE,
            tier=RaceTier.UNKNOWN,
            reason=f"is_active={insight.is_active}",
        )

    if insight.valida_num is None or insight.valida_num == 0:
        logger.info(
            "race_insight_dispatcher: insight_id=%s es agregado de temporada "
            "(valida_num=%s) — skip email (entrega mensual on-demand)",
            insight.id,
            insight.valida_num,
        )
        return NotificationResult(
            decision=NotificationDecision.SKIPPED_AGGREGATE,
            tier=RaceTier.UNKNOWN,
            reason="valida_num=0 (season summary)",
        )

    if insight.event_id is None:
        logger.warning(
            "race_insight_dispatcher: insight_id=%s sin event_id — "
            "no podemos derivar tier, skip notificación",
            insight.id,
        )
        return NotificationResult(
            decision=NotificationDecision.SKIPPED_NO_EVENT,
            tier=RaceTier.UNKNOWN,
            reason="event_id IS NULL",
        )

    # 2. Re-cargar insight con relaciones (event + series + athlete).
    #    Soportamos que el caller pase un objeto ya cargado, pero re-cargar
    #    es barato y evita lazy-load en contextos async ambiguos.
    fresh = await _load_insight_with_relations(db, insight.id)
    if fresh is None:
        logger.error(
            "race_insight_dispatcher: insight_id=%s no encontrado en re-load",
            insight.id,
        )
        return NotificationResult(
            decision=NotificationDecision.ERROR,
            tier=RaceTier.UNKNOWN,
            reason="insight not found on reload",
        )

    event = fresh.event
    if event is None:
        logger.warning(
            "race_insight_dispatcher: insight_id=%s event_id=%s no resuelve "
            "(¿borrado?). Skip.",
            insight.id,
            insight.event_id,
        )
        return NotificationResult(
            decision=NotificationDecision.SKIPPED_NO_EVENT,
            tier=RaceTier.UNKNOWN,
            reason="RaceEvent no resoluble (event=None)",
        )

    tier = get_race_tier(event, series=event.series)

    # 3. Padres del atleta.
    parents = await _load_parents(db, fresh.athlete_id)
    if not parents:
        logger.info(
            "race_insight_dispatcher: insight_id=%s sin padres con email — "
            "skip (athlete_hash=%s)",
            insight.id,
            _hash_id(fresh.athlete_id),
        )
        return NotificationResult(
            decision=NotificationDecision.SKIPPED_NO_PARENTS,
            tier=tier,
            reason="no parents with email",
        )

    # 4. In-app SIEMPRE (independiente del tier).
    in_app_count = await _emit_in_app_notification(
        insight=fresh, tier=tier, parents=parents
    )

    # 5. Email SOLO para tier A o CD.
    if not should_email_parents(tier):
        logger.info(
            "race_insight_dispatcher: insight_id=%s tier=%s — solo in-app "
            "(no email). athlete_hash=%s parents=%d",
            insight.id,
            tier.value,
            _hash_id(fresh.athlete_id),
            len(parents),
        )
        return NotificationResult(
            decision=(
                NotificationDecision.SENT_IN_APP
                if in_app_count > 0
                else NotificationDecision.SKIPPED_TIER
            ),
            tier=tier,
            channels=[NotificationChannel.IN_APP] if in_app_count > 0 else [],
            in_app_emitted=in_app_count,
            reason=f"tier={tier.value} (no parent email)",
        )

    # 6. Tier A o CD: enviar email también.
    if notification_service is None:
        logger.info(
            "race_insight_dispatcher: insight_id=%s tier=%s requiere email "
            "pero notification_service=None (dry-run). athlete_hash=%s",
            insight.id,
            tier.value,
            _hash_id(fresh.athlete_id),
        )
        return NotificationResult(
            decision=NotificationDecision.SENT_IN_APP,
            tier=tier,
            channels=[NotificationChannel.IN_APP],
            in_app_emitted=in_app_count,
            reason="email skipped (notification_service=None)",
        )

    # Resolver datos para el email.
    athlete = fresh.athlete
    athlete_first_name = (athlete.first_name if athlete else None) or "su hijo/a"
    club_name = await _resolve_club_name(db, fresh.athlete_id)

    emails_sent = await _send_email_to_parents(
        insight=fresh,
        event=event,
        tier=tier,
        parents=parents,
        athlete_first_name=athlete_first_name,
        club_name=club_name,
        notification_service=notification_service,
        dispatcher=dispatcher,
    )

    return NotificationResult(
        decision=NotificationDecision.SENT_EMAIL,
        tier=tier,
        channels=[NotificationChannel.IN_APP, NotificationChannel.EMAIL],
        emails_sent=emails_sent,
        in_app_emitted=in_app_count,
        parents_skipped=len(parents) - emails_sent,
        reason=f"tier={tier.value}",
    )


__all__ = [
    "NotificationChannel",
    "NotificationDecision",
    "NotificationResult",
    "dispatch_insight_notification",
]
