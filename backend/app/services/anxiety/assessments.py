"""Assessment-creation service (US1, FR-002/003/006/023).

Resolves the age-driven instrument (with the under-13 safeguard), enforces the
guardian-consent gate, copies the event priority for history, persists the
assessment, and issues a single-use answer token. Designed to be called both
for a single create and per-athlete inside a batch (errors are returned as
structured results so one bad athlete never fails the whole group).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anxiety_assessment import (
    AnxietyAssessment,
    AssessmentStatus,
    EventPriority,
)
from app.models.anxiety_instrument import AnxietyInstrument, InstrumentType
from app.models.anxiety_response_token import AnxietyResponseToken
from app.models.athlete import Athlete
from app.services.anxiety import tokens
from app.services.anxiety.consent_gate import has_psychological_consent
from app.services.anxiety.selection import select_instrument


class AssessmentCreationError(Exception):
    """Base for recoverable, per-athlete creation problems."""


class ConsentMissingError(AssessmentCreationError):
    """Athlete lacks an active psychological-assessment guardian consent."""

    def __init__(self) -> None:
        super().__init__(
            "El atleta no tiene consentimiento parental vigente para "
            "evaluación psicológica. Solicítalo antes de crear la evaluación."
        )


class OverrideRequiredError(AssessmentCreationError):
    """Age-inappropriate instrument selected without acknowledging the warning."""

    def __init__(self, warning: str) -> None:
        self.warning = warning
        super().__init__(warning)


@dataclass
class CreatedAssessment:
    assessment: AnxietyAssessment
    token: AnxietyResponseToken
    raw_token: str
    instrument_type: str
    warning: str | None


def age_in_years(birth_date: date, at: datetime) -> float:
    return (at.date() - birth_date).days / 365.25


async def _active_instrument(
    db: AsyncSession, instrument_type: str
) -> AnxietyInstrument:
    result = await db.execute(
        select(AnxietyInstrument)
        .where(
            AnxietyInstrument.type == InstrumentType(instrument_type),
            AnxietyInstrument.is_active.is_(True),
        )
        .order_by(AnxietyInstrument.id.desc())
    )
    instrument = result.scalars().first()
    if instrument is None:
        raise AssessmentCreationError(
            f"No hay un instrumento activo configurado para '{instrument_type}'."
        )
    return instrument


def _event_priority(event: object | None) -> EventPriority | None:
    raw = getattr(event, "priority", None)
    if raw is None:
        return None
    try:
        return EventPriority(str(raw))
    except ValueError:
        return None


async def create_assessment(
    db: AsyncSession,
    *,
    athlete: Athlete,
    scheduled_at: datetime,
    created_by_user_id: int,
    event: object | None = None,
    instrument_override: str | None = None,
    override_confirmed: bool = False,
    now: datetime | None = None,
) -> CreatedAssessment:
    """Create one assessment + token. Raises ``AssessmentCreationError`` subtypes.

    ``event`` is an optional ``RaceEvent``-like object (its ``id`` and optional
    ``priority`` are read). ``instrument_override`` forces a specific
    instrument; for an under-13 athlete an anxiety-adult instrument requires
    ``override_confirmed=True``.
    """
    now = now or datetime.now(timezone.utc)

    if not await has_psychological_consent(db, athlete.id):
        raise ConsentMissingError()

    age = age_in_years(athlete.birth_date, scheduled_at)
    selection = select_instrument(age, override=instrument_override)
    if selection.warning is not None and not override_confirmed:
        raise OverrideRequiredError(selection.warning)

    instrument = await _active_instrument(db, selection.instrument)

    assessment = AnxietyAssessment(
        athlete_id=athlete.id,
        instrument_id=instrument.id,
        event_id=getattr(event, "id", None),
        priority=_event_priority(event),
        scheduled_at=scheduled_at,
        status=AssessmentStatus.pending,
        instrument_override=selection.override_used,
        override_ack_at=now if selection.warning is not None else None,
        created_by_user_id=created_by_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(assessment)
    await db.flush()

    token, raw = await tokens.issue_token(db, assessment.id, now=now)
    return CreatedAssessment(
        assessment=assessment,
        token=token,
        raw_token=raw,
        instrument_type=selection.instrument,
        warning=selection.warning,
    )
