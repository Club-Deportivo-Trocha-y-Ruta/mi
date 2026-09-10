"""Esquemas Pydantic del informe de actividad por entrenador (feature 041).

Ver ``specs/041-multi-coach-governance/contracts/coach-activity-report.md``
§1.2. El contrato ubica estos modelos en ``app/schemas/audit.py``; viven en
un módulo propio porque ese archivo pertenece a otra tarea en paralelo. La
única consecuencia es la ruta del import: la forma serializada es
exactamente la del §1.2.

``ActorRef`` **no** se redeclara aquí — se importa de ``app.schemas.audit``,
que es su definición canónica (``{user_id, display_name}``). ``CoachRef``
la extiende con los dos campos que el informe necesita para pintar la
tarjeta del entrenador (``role``, ``is_active``).

Privacidad (Ley 1581, §5 del contrato): este payload contiene **nombres de
personal adulto y enteros**, nada más. Ningún ``athlete_id``, ningún nombre
de menor, ninguna fecha de nacimiento, ninguna medida, ningún texto libre y
ningún nombre de archivo. El conjunto de claves es cerrado y una prueba lo
fija (``tests/test_coach_activity.py``).
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.user import UserRole
from app.schemas.audit import ActorRef


class CoachRef(ActorRef):
    """Entrenador del informe: ``ActorRef`` + rol y estado de la cuenta.

    ``is_active=False`` es lo que permite que un entrenador desactivado siga
    apareciendo en los períodos que trabajó (FR-013) en vez de desaparecer
    del histórico.
    """

    role: UserRole
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ClubSessionCounters(BaseModel):
    """Sesiones del club, **deduplicadas**: una sesión cuenta una sola vez
    aunque la dirijan dos entrenadores (§2, regla de ``COUNT(DISTINCT)``)."""

    planned: int = 0
    executed: int = 0
    cancelled: int = 0
    total: int = 0


class CoachSessionCounters(ClubSessionCounters):
    """Sesiones de un entrenador. El fan-out es intencional: una sesión
    codirigida suma 1 a cada entrenador.

    ``co_led`` **no** es un cuarto estado disjunto — es el subconjunto de
    ``total`` cuyas sesiones tienen 2 o más entrenadores asignados. Se
    mantienen dos invariantes: ``planned + executed + cancelled == total`` y
    ``co_led <= total``.
    """

    co_led: int = 0


class ResultsOperationsCounters(BaseModel):
    """Operaciones sobre resultados de competencia (§3)."""

    imports: int = 0
    revisions: int = 0
    competitor_links: int = 0
    total: int = 0


class DocumentCounters(BaseModel):
    """Aprobaciones, envíos y exportaciones documentales leídas de
    ``audit_log`` (§3)."""

    reports_approved: int = 0
    newsletters_approved: int = 0
    newsletters_sent: int = 0
    exports: int = 0


class ClubTotals(BaseModel):
    """Totales del club. Incluyen lo hecho por administradores y por actores
    automáticos, así que la suma de las filas por entrenador **no** tiene por
    qué coincidir con estos números (§2, último párrafo)."""

    sessions: ClubSessionCounters
    attendance_entries_recorded: int = 0
    ai_runs_launched: int = 0
    results_operations: ResultsOperationsCounters
    documents: DocumentCounters
    audit_entries_count: int = 0


class CoachActivityRow(BaseModel):
    """Una fila del informe: un entrenador y sus contadores del período."""

    coach: CoachRef
    sessions: CoachSessionCounters
    attendance_entries_recorded: int = 0
    ai_runs_launched: int = 0
    results_operations: ResultsOperationsCounters
    documents: DocumentCounters
    audit_entries_count: int = 0


class CoachActivityOut(BaseModel):
    """Respuesta de ``GET /api/clubs/{club_id}/coach-activity`` (§1.2).

    ``period_from``/``period_to`` se serializan como ``from``/``to``: ``from``
    es palabra reservada de Python y no puede ser nombre de atributo.
    """

    club_id: int
    period_from: date = Field(alias="from")
    period_to: date = Field(alias="to")
    computed_at: datetime
    club_totals: ClubTotals
    coaches: list[CoachActivityRow]

    model_config = ConfigDict(populate_by_name=True)


__all__ = [
    "ClubSessionCounters",
    "ClubTotals",
    "CoachActivityOut",
    "CoachActivityRow",
    "CoachRef",
    "CoachSessionCounters",
    "DocumentCounters",
    "ResultsOperationsCounters",
]
