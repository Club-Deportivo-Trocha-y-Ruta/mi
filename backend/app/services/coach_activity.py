"""Informe de actividad por entrenador (feature 041, US7 — T081).

Contrato: ``specs/041-multi-coach-governance/contracts/coach-activity-report.md``
§1 a §4. Una sola función pública, ``compute_coach_activity``, que arma el
payload completo del período pedido.

Las dos reglas que gobiernan todo el módulo (§2)
------------------------------------------------

1. **Por entrenador el fan-out es intencional.** Una sesión dirigida por A y
   B suma 1 a A y 1 a B. ``co_led`` es el subconjunto de las sesiones de ese
   entrenador que tienen 2 o más filas en ``training_session_coaches``: no es
   un cuarto estado, así que se conserva
   ``planned + executed + cancelled == total`` y ``co_led <= total``.
2. **En el total del club la sesión cuenta una sola vez**, sin importar
   cuántos entrenadores tenga (``COUNT(DISTINCT training_sessions.id)``).

De ahí sale la aserción de SC-008:
``sum(coaches[].sessions.total) >= club_totals.sessions.total``, y el exceso
es exactamente el número de asignaciones extra de entrenador. El total del
club **nunca** se calcula sumando las filas por entrenador.

Dos familias de anclaje temporal, a propósito (§3, nota 1)
----------------------------------------------------------

- Sesiones y asistencias se anclan en ``training_sessions.scheduled_date``,
  para que "marzo" signifique lo mismo aquí y en el informe mensual y ambos
  reconcilien.
- Todo lo demás se ancla en la marca de tiempo del acto en sí (un informe
  aprobado el 2 de abril pertenece a abril). Las fechas del período se
  expanden a ``[desde 00:00:00, hasta+1día 00:00:00)``.

Consultas (§5): un número **constante** de sentencias, independiente de
cuántos entrenadores tenga el club. Nunca se itera consultando por
entrenador; se agrupa por actor y se reparte en memoria.

Privacidad (Ley 1581): el resultado son nombres de personal adulto y
enteros. Ningún ``athlete_id``, nombre de menor, fecha de nacimiento, medida
ni texto libre entra jamás en este payload; los deportistas solo participan
como criterio de alcance por club en ``agent_runs``.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun
from app.models.athlete import Athlete
from app.models.audit_log import AuditAction, AuditLog
from app.models.club import Club, ClubMember, ClubRole
from app.models.race_competitor_link_audit import (
    LinkAuditAction,
    RaceCompetitorLinkAudit,
)
from app.models.race_import import RaceImport, RaceImportStatus
from app.models.race_result_revision import RaceResultRevision
from app.models.training_session import (
    SessionAttendance,
    SessionStatus,
    TrainingSession,
    TrainingSessionCoach,
)
from app.models.user import User, UserRole
from app.schemas.coach_activity import (
    ClubSessionCounters,
    ClubTotals,
    CoachActivityOut,
    CoachActivityRow,
    CoachRef,
    CoachSessionCounters,
    DocumentCounters,
    ResultsOperationsCounters,
)
from app.services.audit import AuditEntityType

#: Ventana máxima admitida por el contrato (§1.1).
MAX_PERIOD_DAYS = 366


class CoachActivityError(Exception):
    """Base de los errores de dominio que el router traduce a HTTP."""


class ClubNotFoundError(CoachActivityError):
    """El ``club_id`` pedido no existe (§1.5, 404)."""


class CoachNotInClubError(CoachActivityError):
    """El ``coach_user_id`` pedido no es (ni fue) entrenador del club (404)."""


class InvalidPeriodError(CoachActivityError):
    """``from > to`` o ventana mayor a 366 días (§1.5, 422)."""


# ---------------------------------------------------------------------------
# Acumulador interno por actor
# ---------------------------------------------------------------------------


@dataclass
class _Bucket:
    """Contadores en bruto de un actor, antes de convertirse en esquema."""

    sessions_by_status: dict[SessionStatus, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    session_ids: set[int] = field(default_factory=set)
    co_led: int = 0
    attendance: int = 0
    ai_runs: int = 0
    imports: int = 0
    revisions: int = 0
    competitor_links: int = 0
    reports_approved: int = 0
    newsletters_approved: int = 0
    newsletters_sent: int = 0
    exports: int = 0
    audit_entries: int = 0


@dataclass(frozen=True)
class _Member:
    """Fila de ``club_members`` resuelta con los datos de la cuenta."""

    user_id: int
    first_name: str
    last_name: str
    role: UserRole
    is_active: bool
    role_in_club: ClubRole


# ---------------------------------------------------------------------------
# Validación del período
# ---------------------------------------------------------------------------


def validate_period(period_from: date, period_to: date) -> None:
    """Aplica las dos reglas del §1.1: orden y longitud máxima.

    Ambos extremos son obligatorios a propósito: un "mes actual" implícito
    ataría la prueba de reconciliación de SC-008 al reloj.
    """
    if period_from > period_to:
        raise InvalidPeriodError
    if (period_to - period_from).days > MAX_PERIOD_DAYS:
        raise InvalidPeriodError


def _timestamp_window(
    period_from: date, period_to: date
) -> tuple[datetime, datetime]:
    """Expande el período a ``[desde 00:00:00, hasta+1día 00:00:00)``.

    Naive a propósito: las columnas ``DateTime`` del modelo no llevan zona y
    guardan UTC, así que comparar contra un ``datetime`` con ``tzinfo``
    fallaría en MySQL y compararía mal en SQLite.
    """
    start = datetime.combine(period_from, time.min)
    end = datetime.combine(period_to + timedelta(days=1), time.min)
    return start, end


# ---------------------------------------------------------------------------
# Consultas por bloque (§3). Una por bloque, todas agrupadas por actor.
# ---------------------------------------------------------------------------


def _sessions_in_window(club_id: int, period_from: date, period_to: date) -> Select:
    """Sesiones del club ancladas en su propia fecha programada.

    No filtra por ``athletes.deleted_at`` ni por nada del deportista: un
    informe que reconstruye un período pasado debe seguir contando las
    sesiones de un atleta archivado (``data-model.md`` §8.1).
    """
    return select(TrainingSession.id, TrainingSession.status).where(
        TrainingSession.club_id == club_id,
        TrainingSession.scheduled_date >= period_from,
        TrainingSession.scheduled_date <= period_to,
    )


async def _load_members(db: AsyncSession, club_id: int) -> list[_Member]:
    """Personal del club con los datos de cuenta ya resueltos (1 consulta)."""
    rows = await db.execute(
        select(
            User.id,
            User.first_name,
            User.last_name,
            User.role,
            User.is_active,
            ClubMember.role_in_club,
        )
        .join(ClubMember, ClubMember.user_id == User.id)
        .where(ClubMember.club_id == club_id)
    )
    return [
        _Member(
            user_id=row.id,
            first_name=row.first_name,
            last_name=row.last_name,
            role=row.role,
            is_active=bool(row.is_active),
            role_in_club=row.role_in_club,
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Función pública
# ---------------------------------------------------------------------------


async def compute_coach_activity(
    db: AsyncSession,
    club_id: int,
    period_from: date,
    period_to: date,
    coach_user_id: int | None = None,
) -> CoachActivityOut:
    """Arma el informe de actividad por entrenador de un club y período.

    Args:
        db: sesión asíncrona.
        club_id: club cuyo informe se calcula; alcance de toda la respuesta.
        period_from: límite inferior inclusivo.
        period_to: límite superior inclusivo.
        coach_user_id: si viene, ``coaches`` se recorta a esa persona.
            ``club_totals`` **nunca** se recorta (§1.1).

    Returns:
        ``CoachActivityOut`` con los totales del club y una fila por
        entrenador, ordenada por ``(last_name, first_name, user_id)``.

    Raises:
        InvalidPeriodError: período inválido (§1.1).
        ClubNotFoundError: el club no existe.
        CoachNotInClubError: ``coach_user_id`` no es entrenador del club.
    """
    validate_period(period_from, period_to)

    exists = await db.execute(select(Club.id).where(Club.id == club_id))
    if exists.scalar_one_or_none() is None:
        raise ClubNotFoundError

    members = await _load_members(db, club_id)
    coaches = [m for m in members if m.role_in_club == ClubRole.coach]
    coach_ids = {m.user_id for m in coaches}
    member_ids = {m.user_id for m in members}

    if coach_user_id is not None and coach_user_id not in coach_ids:
        raise CoachNotInClubError

    start, end = _timestamp_window(period_from, period_to)

    buckets: dict[int, _Bucket] = defaultdict(_Bucket)
    club_sessions = ClubSessionCounters()
    club_attendance = 0
    club_ai_runs = 0
    club_imports = 0
    club_revisions = 0
    club_links = 0
    club_documents = DocumentCounters()
    club_audit_entries = 0

    # --- Bloque 1: sesiones del club, deduplicadas (§2) --------------------
    session_rows = (await db.execute(_sessions_in_window(club_id, period_from, period_to))).all()
    club_session_ids: set[int] = set()
    for session_id, status in session_rows:
        if session_id in club_session_ids:
            continue
        club_session_ids.add(session_id)
        if status == SessionStatus.PLANNED:
            club_sessions.planned += 1
        elif status == SessionStatus.EXECUTED:
            club_sessions.executed += 1
        elif status == SessionStatus.CANCELLED:
            club_sessions.cancelled += 1
    club_sessions.total = len(club_session_ids)

    # --- Bloque 2: sesiones por entrenador, con fan-out (§2) ---------------
    # Se traen las asignaciones crudas (una fila por par sesión-entrenador)
    # y se reparten en memoria: así el mismo recorrido resuelve los tres
    # estados y ``co_led`` sin una segunda consulta con subselect.
    assignment_rows = (
        await db.execute(
            select(
                TrainingSessionCoach.coach_user_id,
                TrainingSession.id,
                TrainingSession.status,
            )
            .join(
                TrainingSession,
                TrainingSession.id == TrainingSessionCoach.session_id,
            )
            .where(
                TrainingSession.club_id == club_id,
                TrainingSession.scheduled_date >= period_from,
                TrainingSession.scheduled_date <= period_to,
            )
        )
    ).all()

    coaches_per_session: dict[int, int] = defaultdict(int)
    for _, session_id, _status in assignment_rows:
        coaches_per_session[session_id] += 1

    for actor_id, session_id, status in assignment_rows:
        bucket = buckets[actor_id]
        bucket.sessions_by_status[status] += 1
        bucket.session_ids.add(session_id)
        if coaches_per_session[session_id] > 1:
            bucket.co_led += 1

    # --- Bloque 3: asistencias registradas (§3) ----------------------------
    # ``archived_at IS NULL``: el conteo debe coincidir con lo que muestran
    # el informe mensual y el detalle de sesión. El archivado en sí queda
    # visible en el historial, no aquí.
    attendance_rows = (
        await db.execute(
            select(
                SessionAttendance.recorded_by_user_id,
                func.count(SessionAttendance.id),
            )
            .join(
                TrainingSession,
                TrainingSession.id == SessionAttendance.session_id,
            )
            .where(
                TrainingSession.club_id == club_id,
                TrainingSession.scheduled_date >= period_from,
                TrainingSession.scheduled_date <= period_to,
                SessionAttendance.archived_at.is_(None),
            )
            .group_by(SessionAttendance.recorded_by_user_id)
        )
    ).all()
    for actor_id, count in attendance_rows:
        club_attendance += count
        if actor_id is not None:
            buckets[actor_id].attendance += count

    # --- Bloque 4: runs agénticos lanzados (§3, nota 4) --------------------
    # Alcance por club vía el atleta; los runs sin atleta se atribuyen al
    # club cuando quien los lanzó es entrenador de ese club.
    #
    # A propósito SIN ``Athlete.deleted_at.is_(None)``: este informe
    # reconstruye un período cerrado y §1.4 del contrato lo pone por escrito
    # ("a report reconstructing a past period must not filter
    # athletes.deleted_at", ``data-model.md`` §8.1). Archivar a un menor no
    # puede borrar el trabajo que un adulto hizo ese mes. La exención está
    # registrada, con esa razón, en ``ARCHIVE_SCOPE_EXEMPT``
    # (``tests/test_archive_scope_gate.py``). El atleta solo se usa como
    # criterio de alcance: ni su id ni su nombre salen en el payload.
    ai_scope = [Athlete.club_id == club_id]
    if coach_ids:
        ai_scope.append(
            AgentRun.athlete_id.is_(None)
            & AgentRun.requested_by_user_id.in_(coach_ids)
        )
    ai_rows = (
        await db.execute(
            select(AgentRun.requested_by_user_id, func.count(AgentRun.id))
            .outerjoin(Athlete, Athlete.id == AgentRun.athlete_id)
            .where(
                AgentRun.started_at >= start,
                AgentRun.started_at < end,
                or_(*ai_scope),
            )
            .group_by(AgentRun.requested_by_user_id)
        )
    ).all()
    for actor_id, count in ai_rows:
        club_ai_runs += count
        if actor_id is not None:
            buckets[actor_id].ai_runs += count

    # --- Bloque 5: operaciones sobre resultados (§3, nota 5) ---------------
    # Las tablas de carreras no llevan ``club_id`` (verificado): el alcance
    # es "el actor es miembro de este club". Exacto mientras haya un solo
    # club en producción; al incorporar un segundo hay que cambiarlo.
    if member_ids:
        # Solo cuentan las ingestas ``committed``: un ``pending``/``dry_run``
        # es trabajo en curso, no una operación de resultados. La atribución
        # cae a ``imported_by_user_id``/``imported_at`` en filas antiguas sin
        # ``committed_by_user_id`` (§1.4).
        import_actor = func.coalesce(
            RaceImport.committed_by_user_id, RaceImport.imported_by_user_id
        )
        import_anchor = func.coalesce(RaceImport.committed_at, RaceImport.imported_at)
        import_rows = (
            await db.execute(
                select(import_actor, func.count(RaceImport.id))
                .where(
                    RaceImport.status == RaceImportStatus.committed,
                    import_actor.in_(member_ids),
                    import_anchor >= start,
                    import_anchor < end,
                )
                .group_by(import_actor)
            )
        ).all()
        for actor_id, count in import_rows:
            club_imports += count
            if actor_id is not None:
                buckets[actor_id].imports += count

        revision_rows = (
            await db.execute(
                select(
                    RaceResultRevision.changed_by_user_id,
                    func.count(RaceResultRevision.id),
                )
                .where(
                    RaceResultRevision.changed_by_user_id.in_(member_ids),
                    RaceResultRevision.changed_at >= start,
                    RaceResultRevision.changed_at < end,
                )
                .group_by(RaceResultRevision.changed_by_user_id)
            )
        ).all()
        for actor_id, count in revision_rows:
            club_revisions += count
            if actor_id is not None:
                buckets[actor_id].revisions += count

        link_rows = (
            await db.execute(
                select(
                    RaceCompetitorLinkAudit.user_id,
                    func.count(RaceCompetitorLinkAudit.id),
                )
                .where(
                    RaceCompetitorLinkAudit.user_id.in_(member_ids),
                    RaceCompetitorLinkAudit.action.in_(
                        [LinkAuditAction.link, LinkAuditAction.unlink]
                    ),
                    RaceCompetitorLinkAudit.created_at >= start,
                    RaceCompetitorLinkAudit.created_at < end,
                )
                .group_by(RaceCompetitorLinkAudit.user_id)
            )
        ).all()
        for actor_id, count in link_rows:
            club_links += count
            if actor_id is not None:
                buckets[actor_id].competitor_links += count

    # --- Bloque 6: documentos y volumen de historial (§3) ------------------
    # Una sola consulta agrupada por (actor, acción, entidad) sirve los
    # cuatro contadores documentales y ``audit_entries_count``.
    audit_rows = (
        await db.execute(
            select(
                AuditLog.actor_user_id,
                AuditLog.action,
                AuditLog.entity_type,
                func.count(AuditLog.id),
            )
            .where(
                AuditLog.club_id == club_id,
                AuditLog.occurred_at >= start,
                AuditLog.occurred_at < end,
            )
            .group_by(AuditLog.actor_user_id, AuditLog.action, AuditLog.entity_type)
        )
    ).all()
    for actor_id, action, entity_type, count in audit_rows:
        club_audit_entries += count
        bucket = buckets[actor_id] if actor_id is not None else None
        if bucket is not None:
            bucket.audit_entries += count
        if action == AuditAction.approve and entity_type == AuditEntityType.monthly_report:
            club_documents.reports_approved += count
            if bucket is not None:
                bucket.reports_approved += count
        elif (
            action == AuditAction.approve
            and entity_type == AuditEntityType.athlete_monthly_newsletter
        ):
            club_documents.newsletters_approved += count
            if bucket is not None:
                bucket.newsletters_approved += count
        elif (
            action == AuditAction.send
            and entity_type == AuditEntityType.athlete_monthly_newsletter
        ):
            club_documents.newsletters_sent += count
            if bucket is not None:
                bucket.newsletters_sent += count
        elif action == AuditAction.export:
            club_documents.exports += count
            if bucket is not None:
                bucket.exports += count

    # --- Armado de las filas -----------------------------------------------
    # Membresía de ``coaches[]`` (§1.3): todo entrenador activo del club, más
    # todo entrenador (aunque esté desactivado) con algún contador distinto
    # de cero en la ventana. Los ceros se devuelven explícitos para que el
    # lector vea "0" y no una ausencia.
    rows: list[CoachActivityRow] = []
    for member in coaches:
        if coach_user_id is not None and member.user_id != coach_user_id:
            continue
        bucket = buckets.get(member.user_id, _Bucket())
        if member.is_active or _has_activity(bucket):
            rows.append(_build_row(member, bucket))

    # Orden estable ``(last_name, first_name, user_id)`` — se arma con los
    # campos del miembro, no con el nombre ya compuesto, para no depender de
    # la intercalación local (§1.2).
    order = {m.user_id: (m.last_name, m.first_name, m.user_id) for m in coaches}
    rows.sort(key=lambda r: order[r.coach.user_id])

    club_totals = ClubTotals(
        sessions=club_sessions,
        attendance_entries_recorded=club_attendance,
        ai_runs_launched=club_ai_runs,
        results_operations=ResultsOperationsCounters(
            imports=club_imports,
            revisions=club_revisions,
            competitor_links=club_links,
            total=club_imports + club_revisions + club_links,
        ),
        documents=club_documents,
        audit_entries_count=club_audit_entries,
    )

    return CoachActivityOut(
        club_id=club_id,
        period_from=period_from,
        period_to=period_to,
        computed_at=datetime.now(timezone.utc).replace(tzinfo=None),
        club_totals=club_totals,
        coaches=rows,
    )


def _has_activity(bucket: _Bucket) -> bool:
    """``True`` si el entrenador movió algo en la ventana (§1.3, punto 2)."""
    return bool(
        bucket.session_ids
        or bucket.attendance
        or bucket.ai_runs
        or bucket.imports
        or bucket.revisions
        or bucket.competitor_links
        or bucket.audit_entries
    )


def _build_row(member: _Member, bucket: _Bucket) -> CoachActivityRow:
    """Convierte el acumulador en la fila serializable del contrato."""
    planned = bucket.sessions_by_status.get(SessionStatus.PLANNED, 0)
    executed = bucket.sessions_by_status.get(SessionStatus.EXECUTED, 0)
    cancelled = bucket.sessions_by_status.get(SessionStatus.CANCELLED, 0)
    return CoachActivityRow(
        coach=CoachRef(
            user_id=member.user_id,
            display_name=f"{member.first_name} {member.last_name}".strip(),
            role=member.role,
            is_active=member.is_active,
        ),
        sessions=CoachSessionCounters(
            planned=planned,
            executed=executed,
            cancelled=cancelled,
            total=planned + executed + cancelled,
            co_led=bucket.co_led,
        ),
        attendance_entries_recorded=bucket.attendance,
        ai_runs_launched=bucket.ai_runs,
        results_operations=ResultsOperationsCounters(
            imports=bucket.imports,
            revisions=bucket.revisions,
            competitor_links=bucket.competitor_links,
            total=bucket.imports + bucket.revisions + bucket.competitor_links,
        ),
        documents=DocumentCounters(
            reports_approved=bucket.reports_approved,
            newsletters_approved=bucket.newsletters_approved,
            newsletters_sent=bucket.newsletters_sent,
            exports=bucket.exports,
        ),
        audit_entries_count=bucket.audit_entries,
    )


__all__ = [
    "MAX_PERIOD_DAYS",
    "ClubNotFoundError",
    "CoachActivityError",
    "CoachNotInClubError",
    "InvalidPeriodError",
    "compute_coach_activity",
    "validate_period",
]
