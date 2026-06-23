"""Single-use, hashed, expiring answer tokens (FR-007, CL-002).

The raw token is returned to the coach exactly once at issue time; only its
SHA-256 hash is stored. A token is valid only while not consumed and not
expired; submitting answers consumes it.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anxiety_response_token import AnxietyResponseToken

DEFAULT_TTL = timedelta(days=2)


def hash_token(raw: str) -> str:
    """Return the SHA-256 hex digest stored for ``raw``."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def issue_token(
    db: AsyncSession,
    assessment_id: int,
    ttl: timedelta = DEFAULT_TTL,
    now: datetime | None = None,
) -> tuple[AnxietyResponseToken, str]:
    """Create a token row and return ``(row, raw_token)``.

    The raw token is never persisted — only its hash. Caller surfaces the raw
    value to the coach once.
    """
    now = now or datetime.now(timezone.utc)
    raw = secrets.token_urlsafe(32)
    row = AnxietyResponseToken(
        assessment_id=assessment_id,
        token_hash=hash_token(raw),
        expires_at=now + ttl,
        created_at=now,
    )
    db.add(row)
    await db.flush()
    return row, raw


async def resolve_active_token(
    db: AsyncSession,
    raw: str,
    now: datetime | None = None,
) -> AnxietyResponseToken | None:
    """Return the token row for ``raw`` if valid (not consumed, not expired)."""
    now = now or datetime.now(timezone.utc)
    result = await db.execute(
        select(AnxietyResponseToken).where(
            AnxietyResponseToken.token_hash == hash_token(raw)
        )
    )
    token = result.scalar_one_or_none()
    if token is None:
        return None
    if token.consumed_at is not None:
        return None
    expires = token.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= now:
        return None
    return token


def consume(token: AnxietyResponseToken, now: datetime | None = None) -> None:
    """Mark ``token`` consumed (single-use)."""
    token.consumed_at = now or datetime.now(timezone.utc)
