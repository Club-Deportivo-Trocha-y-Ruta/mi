"""Modelo SQLAlchemy para ``race_competitor_signatures`` (feature 044).

Una fila por **forma observada** en que un competidor viene impreso en los
resultados oficiales: la terna ``(normalized_name, club_norm, city_norm)``.
Cada firma pertenece a exactamente un ``RaceCompetitor``.

Por qué existe (research R-06, data-model §3). Hasta la 044 la identidad de
un competidor era ``race_competitors.normalized_name UNIQUE``, y eso falla en
las dos direcciones al cargar el histórico completo de una copa:

- dos personas distintas con el mismo nombre se fusionaban en silencio;
- una misma persona impresa con y sin segundo apellido eran dos personas.

La firma es la **persistencia de lo ya resuelto**: una vez que el coach
decidió (o que la ingesta resolvió sin ambigüedad) que cierta terna es
determinada persona, la siguiente carga que traiga esa misma terna la
reconoce por acierto exacto y no vuelve a preguntar. No es una función de
alias editable por el usuario: no hay pantalla para crear ni borrar firmas
fuera del flujo de revisión de identidad.

``UNIQUE(normalized_name, club_norm, city_norm, discriminator)`` cumple además el segundo
papel del constraint que se eliminó: es la **protección de concurrencia**.
Dos ingestas simultáneas del mismo corredor nuevo compiten por insertar la
misma terna (con discriminador ``''``) y solo una gana; la otra recibe el error de integridad y reusa
el competidor ya creado.

``club_norm`` y ``city_norm`` son ``NOT NULL DEFAULT ''`` a propósito. MySQL
trata dos ``NULL`` como valores *distintos* dentro de una clave única, de
modo que con columnas nullable la terna ``(juan perez, NULL, NULL)`` se
podría insertar infinitas veces y el UNIQUE no protegería absolutamente
nada. La cadena vacía es el valor canónico de "no se conoce / placeholder"
que ya produce ``normalizer.normalize_club`` para ``"0"``, ``"-"``, ``"n/a"``.

``city_norm`` — como ``race_competitors.city_text`` — es señal de
desambiguación y nunca se serializa fuera de los schemas de revisión de
identidad (coach/admin).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.race_competitor import RaceCompetitor
    from app.models.race_identity_candidate import RaceIdentityCandidate


class RaceCompetitorSignature(Base):
    """Terna observada ``(nombre normalizado, club normalizado, ciudad normalizada)``.

    ``first_season`` / ``last_season`` se ensanchan en cada avistamiento: son
    el rango de temporadas en que esa forma impresa apareció. La reversión de
    una decisión ``same_person`` los usa junto con ``source_candidate_id``
    para saber **exactamente** qué firma y qué resultados volver a separar.
    """

    __tablename__ = "race_competitor_signatures"
    __table_args__ = (
        # Revisión a7c3e5d91f20 (decisión del dueño 2026-09-21): el UNIQUE
        # incluye `discriminator` para que padre e hijo homónimos del mismo
        # club y ciudad puedan ser dos personas.
        UniqueConstraint(
            "normalized_name",
            "club_norm",
            "city_norm",
            "discriminator",
            name="uq_race_competitor_signatures_identity",
        ),
        Index("ix_race_competitor_signatures_competitor_id", "competitor_id"),
        # No hay índice propio sobre `normalized_name`: el UNIQUE de arriba ya
        # lo cubre como prefijo izquierdo, que es exactamente la búsqueda del
        # resolver ("¿qué firmas existen con este nombre?"). Un índice aparte
        # solo costaría escrituras y espacio.
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # CASCADE: una firma huérfana no identifica a nadie. Es lo contrario del
    # RESTRICT de `race_results.competitor_id`, que protege el resultado
    # histórico; aquí no hay nada que proteger.
    competitor_id: Mapped[int] = mapped_column(
        ForeignKey("race_competitors.id", ondelete="CASCADE"), nullable=False
    )
    normalized_name: Mapped[str] = mapped_column(String(160), nullable=False)
    club_norm: Mapped[str] = mapped_column(
        String(150), nullable=False, default="", server_default=text("''")
    )
    city_norm: Mapped[str] = mapped_column(
        String(100), nullable=False, default="", server_default=text("''")
    )
    # Desempate de dos personas con la misma terna, derivado de la categoría
    # (``identity_resolver.category_discriminator``: ``"<sexo>:<min>-<max>@<temporada>"``).
    # ``''`` en toda firma que no lo necesita — el caso normal. NOT NULL por
    # la misma razón que `club_norm`: con NULL el UNIQUE no protegería.
    discriminator: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", server_default=text("''")
    )
    first_season: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    last_season: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # Candidato cuya decisión `same_person` adjuntó esta firma a este
    # competidor. SET NULL y no CASCADE: el candidato es historia auditada y
    # no se borra, pero si algún día desapareciera la firma debe sobrevivir
    # (el borrado del candidato no puede desidentificar resultados).
    source_candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("race_identity_candidates.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relaciones
    competitor: Mapped["RaceCompetitor"] = relationship(
        "RaceCompetitor",
        back_populates="signatures",
        foreign_keys="[RaceCompetitorSignature.competitor_id]",
    )
    source_candidate: Mapped["RaceIdentityCandidate | None"] = relationship(
        "RaceIdentityCandidate",
        foreign_keys="[RaceCompetitorSignature.source_candidate_id]",
    )
