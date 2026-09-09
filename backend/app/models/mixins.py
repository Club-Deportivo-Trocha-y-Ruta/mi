"""Reusable attribution mixins for models touched by feature 041.

Two mixins, one public entry point each (data-model.md §5):

- ``UpdatedByMixin`` — actor only. For tables that already declare their own
  ``updated_at`` column.
- ``ActorTimestampMixin`` — actor + timestamp. For tables that declare
  neither.

``@declared_attr`` is required for ``updated_by_user_id``: a plain
class-level ``mapped_column(ForeignKey(...))`` would be a single shared
``Column`` object aliased across every mapped class, which SQLAlchemy
explicitly forbids. ``updated_at`` carries no ``ForeignKey`` and would work
as a plain attribute, but is declared the same way so the two read
identically.

``Base`` (``app/models/base.py``) is not touched — these mixins are applied
per-model, not globally.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class UpdatedByMixin:
    """Actor-only. For tables that already declare their own ``updated_at``."""

    @declared_attr
    def updated_by_user_id(cls) -> Mapped[int | None]:
        return mapped_column(
            ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        )


class ActorTimestampMixin(UpdatedByMixin):
    """Actor + time. For tables that have neither."""

    @declared_attr
    def updated_at(cls) -> Mapped[datetime | None]:
        return mapped_column(
            DateTime,
            default=lambda: datetime.now(timezone.utc),
            onupdate=lambda: datetime.now(timezone.utc),
            nullable=True,
        )
