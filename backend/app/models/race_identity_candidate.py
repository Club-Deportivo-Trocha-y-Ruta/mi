"""Modelo SQLAlchemy para ``race_identity_candidates`` (feature 044).

Cola de revisión y auditoría de decisiones **en una sola tabla**
(data-model §4, research R-06). Una fila = un par de registros que el
generador de candidatos considera sospechoso, más la decisión del coach
sobre ese par y, si la hubo, su reversión.

Dos tipos de sospecha:

- ``same_person_suspect``: nombres normalizados distintos que probablemente
  son la misma persona (``token_set_ratio >= 90``, sexo compatible, ruta de
  categorías que nunca retrocede a un grupo de edad menor). El caso típico
  es el segundo apellido que un año aparece impreso y el siguiente no.
- ``homonym_suspect``: nombre normalizado idéntico con alguna señal de que
  son dos personas (``same_valida_two_categories``, ``sex_conflict``,
  ``age_path_backwards``, ``club_and_city_differ``). Un cambio de club por
  sí solo **no** es señal — los niños cambian de club constantemente; solo
  agrega una firma.

``pair_hash`` (SHA-256 de las dos claves de registro, ordenadas) es lo que
hace que el "no volver a preguntar" sea estructural y no una convención: un
rebuild posterior recalcula el mismo hash, choca contra el UNIQUE y no crea
una fila nueva ni pisa la decisión existente. Sin él, cada reconstrucción de
la cola le devolvería al coach preguntas que ya respondió.

No hay borrado: un candidato que desaparece de un rebuild posterior (porque
los datos cambiaron) permanece como historia. La reversión de una decisión
devuelve ``state`` a ``pending`` y **conserva** los sellos ``decided_*``
junto con los ``reversed_*``; la secuencia completa vive en ``record_audit``.

Los snapshots ``left_record`` / ``right_record`` contienen nombre impreso,
club y ciudad de terceros: esta tabla es de la misma clase de sensibilidad
que ``race_competitors`` y su contenido solo se serializa a través de
``IdentityRecordRead`` (coach/admin). Nunca va a un log, una traza ni un
mensaje de excepción.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    CHAR,
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class IdentityCandidateKind(str, enum.Enum):
    """Qué sospecha el generador sobre el par.

    - ``same_person_suspect``: dos registros con nombres distintos que
      podrían ser la misma persona.
    - ``homonym_suspect``: dos registros con el mismo nombre que podrían ser
      personas distintas.
    """

    same_person_suspect = "same_person_suspect"
    homonym_suspect = "homonym_suspect"


class IdentityCandidateState(str, enum.Enum):
    """Estado de la revisión.

    Transiciones: ``pending -> same_person | different_people`` (decisión) y
    ``same_person | different_people -> pending`` (reversión auditada). No
    existe un estado ``reversed``: la reversión devuelve el par a la cola.
    """

    pending = "pending"
    same_person = "same_person"
    different_people = "different_people"


class RaceIdentityCandidate(Base):
    """Par sospechoso + decisión + reversión.

    Mientras exista al menos una fila en ``pending``, el commit de cualquier
    import histórico responde ``409 identity_review_pending``: cargar
    resultados con la identidad sin resolver produciría fusiones silenciosas
    que después hay que deshacer a mano.
    """

    __tablename__ = "race_identity_candidates"
    __table_args__ = (
        UniqueConstraint("pair_hash", name="uq_race_identity_candidates_pair_hash"),
        Index("ix_race_identity_candidates_state", "state"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[IdentityCandidateKind] = mapped_column(
        Enum(
            IdentityCandidateKind,
            name="raceidentitycandidatekind",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    # SHA-256 de las dos claves de registro ordenadas — idempotencia del rebuild.
    pair_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    left_record: Mapped[dict] = mapped_column(JSON, nullable=False)
    right_record: Mapped[dict] = mapped_column(JSON, nullable=False)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    signals: Mapped[list] = mapped_column(JSON, nullable=False)
    state: Mapped[IdentityCandidateState] = mapped_column(
        Enum(
            IdentityCandidateState,
            name="raceidentitycandidatestate",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=IdentityCandidateState.pending,
        server_default=text("'pending'"),
    )
    # FR-022: si cualquiera de los dos registros es un competidor ya vinculado
    # a un atleta del club, la decisión toca datos de un menor identificado y
    # la UI lo marca como tal.
    linked_athlete_involved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    decided_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reversed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relaciones — SET NULL en ambas FKs: borrar un usuario no puede borrar
    # ni invalidar la auditoría de la decisión que tomó.
    decided_by: Mapped["User | None"] = relationship(
        "User",
        foreign_keys="[RaceIdentityCandidate.decided_by_user_id]",
    )
    reversed_by: Mapped["User | None"] = relationship(
        "User",
        foreign_keys="[RaceIdentityCandidate.reversed_by_user_id]",
    )
