"""SQLAlchemy model for ``audit_log`` (feature 041, data-model.md §1-2).

Club-wide, append-only, privacy-minimised audit trail: one row per recorded
action (FR-001/FR-004). Never stores a minor's name, birth date, measurement
or narrative text — only identifiers, column names and catalogue codes
(CLAUDE.md privacy rule; enforced downstream by ``VALUE_ALLOWLIST`` and
``META_ALLOWLIST`` in ``app/services/audit.py``).

This module owns only the model and the two DB enums (``AuditAction``,
``AuditActorKind``) plus the reason-code sub-enums that are typed on request
schemas (data-model.md §2, contracts/audit-recording.md §3.1 — same module as
``AuditReasonCode`` itself per plan.md:87). The Python-only closed catalogues
(``AuditEntityType``, ``AuditReasonCode``, ``AuditReasonGroup``,
``AuditDocumentKind``, ``VALUE_ALLOWLIST``, ``CLUB_OPTIONAL``,
``META_ALLOWLIST``) live in ``app/services/audit.py``. ``record_audit`` itself
is implemented on top of this module in a later task (T010) — not here.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    JSON,
    String,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.dialects.sqlite import INTEGER as SQLITE_INTEGER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.user import UserRole

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.club import Club
    from app.models.user import User


class AuditAction(str, enum.Enum):
    """Closed catalogue mirroring FR-001's verb list one-for-one."""

    create = "create"
    update = "update"
    archive = "archive"
    delete = "delete"
    restore = "restore"
    approve = "approve"
    unapprove = "unapprove"
    send = "send"
    export = "export"
    cancel = "cancel"
    execute = "execute"
    link = "link"
    unlink = "unlink"
    role_change = "role_change"
    activate = "activate"
    deactivate = "deactivate"
    purge = "purge"


class AuditActorKind(str, enum.Enum):
    """Who performed the action. Never defaults to ``user``."""

    user = "user"
    system = "system"
    webhook = "webhook"
    cron = "cron"


class AuditLog(Base):
    """One row per recorded action. Append-only — see data-model.md §1.2.

    No ``updated_at`` / ``updated_by`` column, by construction. All ORM
    relationships are declared ``viewonly=True`` so no cascade can ever write
    through them. The application MUST NOT issue ``update(AuditLog)``,
    ``delete(AuditLog)`` or ``session.delete(<AuditLog>)`` anywhere; the
    single exception is ``app/services/retention.py`` (FR-030), which
    appends a ``purge`` row rather than mutating existing ones.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_club_time", "club_id", "occurred_at"),
        Index("ix_audit_actor_time", "actor_user_id", "occurred_at"),
        Index("ix_audit_entity_time", "entity_type", "entity_id", "occurred_at"),
        Index("ix_audit_athlete_time", "athlete_id", "occurred_at"),
        Index("ix_audit_request_id", "request_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(SQLITE_INTEGER(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_kind: Mapped[AuditActorKind] = mapped_column(
        Enum(
            AuditActorKind,
            name="audit_actor_kind",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    actor_role: Mapped[UserRole | None] = mapped_column(
        Enum(
            UserRole,
            name="audit_actor_role",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=True,
    )
    club_id: Mapped[int | None] = mapped_column(
        ForeignKey("clubs.id", ondelete="SET NULL"), nullable=True
    )
    athlete_id: Mapped[int | None] = mapped_column(
        ForeignKey("athletes.id", ondelete="SET NULL"), nullable=True
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[AuditAction] = mapped_column(
        Enum(
            AuditAction,
            name="audit_action",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    changed_fields: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    diff_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    request_id: Mapped[str] = mapped_column(String(32), nullable=False)
    meta_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Read-only relationships — never write through these (append-only).
    actor: Mapped["User | None"] = relationship(
        "User", foreign_keys=[actor_user_id], viewonly=True
    )
    club: Mapped["Club | None"] = relationship(
        "Club", foreign_keys=[club_id], viewonly=True
    )
    athlete: Mapped["Athlete | None"] = relationship(
        "Athlete", foreign_keys=[athlete_id], viewonly=True
    )
