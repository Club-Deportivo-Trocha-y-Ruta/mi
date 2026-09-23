"""Dispatcher de notificaciones para insights de carrera aprobados.

Contexto
========
Decisión cerrada (2026-09-23, reestructura Competencias): aprobar un
insight de carrera NUNCA envía correo automático a los padres — sin
importar la prioridad/tier de la válida. La aprobación solo publica el
insight en la app; la familia lo ve en su panorama o en la bitácora
mensual (Fase 1.8). Esta decisión reemplaza la anterior (Family Relations
track, 2026-05-25) que enviaba email para válidas tier A/CD.

Este módulo encapsula esa lógica: el caller (nodo ``notify_coach``) solo
necesita pasar el insight + sesión DB. El dispatcher resuelve el tier
(hoy solo para telemetría — ya no gatilla ninguna rama de envío) y emite
la notificación in-app a cada padre/acudiente del atleta.

Privacidad
==========
Logs SIEMPRE con ids hasheados (helper :func:`_hash_id`). Nunca emails o
nombres en logs.

Edge cases manejados
====================
- ``valida_num=0`` (resumen temporada) ⇒ sin notificación (siempre
  on-demand, coach decide cuándo compartir mensualmente).
- ``event_id IS NULL`` ⇒ log warning + no notificación.
- ``is_active=False`` (insight deprecado o reaprobación de uno previo) ⇒
  ``NotificationDecision.SKIPPED_INACTIVE``.
- Atleta archivado entre aprobación y despacho ⇒
  ``NotificationDecision.SKIPPED_ARCHIVED_ATHLETE`` (FR-014, feature 041).
"""
from __future__ import annotations

import enum
import hashlib
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.athlete import ParentAthlete
from app.models.athlete_ai_insight import AthleteAiInsight
from app.models.race_event import RaceEvent
from app.models.user import User
from app.services.notification.race_event_tier import RaceTier, get_race_tier

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tipos públicos
# ---------------------------------------------------------------------------


class NotificationChannel(str, enum.Enum):
    """Canal por el que se notificó al padre/usuario."""

    IN_APP = "in_app"
    NONE = "none"


class NotificationDecision(str, enum.Enum):
    """Resultado de la decisión de notificación (para tests + telemetría)."""

    SENT_IN_APP = "sent_in_app"
    SKIPPED_INACTIVE = "skipped_inactive"     # insight no activo
    SKIPPED_AGGREGATE = "skipped_aggregate"   # valida_num=0 (season summary)
    SKIPPED_NO_EVENT = "skipped_no_event"     # insight sin event_id
    SKIPPED_NOT_APPROVED = "skipped_not_approved"
    SKIPPED_NO_PARENTS = "skipped_no_parents"
    # FR-014 (feature 041): el atleta fue archivado entre la aprobación del
    # insight y el despacho — ningún correo ni notificación in-app debe salir.
    SKIPPED_ARCHIVED_ATHLETE = "skipped_archived_athlete"
    ERROR = "error"


@dataclass
class NotificationResult:
    """Resultado agregado por insight.

    Un mismo insight puede emitir N eventos in-app (uno por padre/acudiente).
    Este resultado los suma para que el caller pueda hacer log estructurado
    de "qué pasó".
    """

    decision: NotificationDecision
    tier: RaceTier
    channels: list[NotificationChannel] = field(default_factory=list)
    in_app_emitted: int = 0
    reason: str | None = None  # explicación legible para logs/QA


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------


def _hash_id(value: int | None) -> str:
    """Hash corto y estable para logs (mismo patrón que training/sessions.py)."""
    if value is None:
        return "none"
    return hashlib.sha256(str(value).encode()).hexdigest()[:8]


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
# Entry point público
# ---------------------------------------------------------------------------


async def dispatch_insight_notification(
    insight: AthleteAiInsight,
    db: AsyncSession,
) -> NotificationResult:
    """Publica un insight de carrera aprobado (siempre in-app, nunca email).

    Ver docstring del módulo para el contexto completo de la decisión
    (2026-09-23): aprobar NUNCA dispara email a padres, sin importar el
    tier de la válida. Este dispatcher resuelve el tier solo para
    telemetría/futuras vistas y emite la notificación in-app a cada
    padre/acudiente del atleta.

    +-----------------------------+----------------------+
    | Condición                   | Decisión              |
    +=============================+========================+
    | ``coach_approved=False``    | SKIPPED_NOT_APPROVED |
    | ``is_active != 1``          | SKIPPED_INACTIVE     |
    | ``valida_num == 0``         | SKIPPED_AGGREGATE    |
    | ``event_id IS NULL``        | SKIPPED_NO_EVENT     |
    | atleta archivado            | SKIPPED_ARCHIVED_ATHLETE |
    | sin padres con email        | SKIPPED_NO_PARENTS   |
    | cualquier otro caso         | SENT_IN_APP           |
    +-----------------------------+----------------------+

    Args:
        insight: ORM instance (puede venir "frío" — re-cargamos relaciones).
        db: sesión async para queries de soporte.

    Returns:
        :class:`NotificationResult` con decisión + tier + métricas in-app.
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
            "(valida_num=%s) — skip notificación (entrega mensual on-demand)",
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

    # 2.b Compuerta de archivado (FR-014, contract athlete-archive.md §5.2).
    # Un insight aprobado puede despacharse minutos u horas después; si el
    # atleta se archivó en ese intervalo, ni el correo ni la notificación
    # in-app deben salir. Se evalúa antes de cargar padres para no tocar
    # siquiera la lista de destinatarios.
    # ``getattr`` con default: el resto del módulo ya tolera atletas "stub"
    # (sin el atributo) en pruebas y en objetos cargados parcialmente; un
    # ORM real siempre trae ``deleted_at``.
    archived_athlete = fresh.athlete
    if archived_athlete is None or getattr(archived_athlete, "deleted_at", None) is not None:
        logger.info(
            "race_insight_dispatcher: insight_id=%s con atleta archivado o "
            "inexistente — skip notificación (athlete_hash=%s)",
            insight.id,
            _hash_id(fresh.athlete_id),
        )
        return NotificationResult(
            decision=NotificationDecision.SKIPPED_ARCHIVED_ATHLETE,
            tier=tier,
            reason="athlete archived (deleted_at IS NOT NULL)",
        )

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

    # 4. In-app — única rama de notificación. Aprobar un insight nunca
    #    dispara email, sin importar el tier de la válida (2026-09-23).
    in_app_count = await _emit_in_app_notification(
        insight=fresh, tier=tier, parents=parents
    )

    return NotificationResult(
        decision=NotificationDecision.SENT_IN_APP,
        tier=tier,
        channels=[NotificationChannel.IN_APP],
        in_app_emitted=in_app_count,
        reason=f"tier={tier.value} (in-app únicamente; aprobar nunca envía correo)",
    )


__all__ = [
    "NotificationChannel",
    "NotificationDecision",
    "NotificationResult",
    "dispatch_insight_notification",
]
