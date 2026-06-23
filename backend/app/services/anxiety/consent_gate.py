"""Guardian-consent gate for the anxiety module (FR-023).

An assessment may be created only when the athlete has an active (not
withdrawn) ``parental_consents`` row with ``psychological_assessment=True``.
Reuses the existing consent model rather than a new table (research R6).
Coach/admin RBAC is enforced at the router layer.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.parental_consent import ParentalConsent


async def has_psychological_consent(db: AsyncSession, athlete_id: int) -> bool:
    """True if ``athlete_id`` has an active psychological-assessment consent."""
    result = await db.execute(
        select(ParentalConsent.id).where(
            ParentalConsent.athlete_id == athlete_id,
            ParentalConsent.psychological_assessment.is_(True),
            ParentalConsent.withdrawn_at.is_(None),
        )
    )
    return result.first() is not None
