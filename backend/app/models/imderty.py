"""IMDERTY monthly attendance sheet (feature 047).

Source of truth: ``specs/047-imderty-attendance-sheet/data-model.md``.

Five tables:

- ``athlete_imderty_profiles``: 1:1 with ``athletes``, created lazily on the
  first save; the non-sensitive identification block of the sheet.
- ``athlete_sensitive_authorizations``: append-only log of the guardian's
  explicit authorization for the sensitive block. ``active_key`` equals
  ``athlete_id`` while active and NULL once withdrawn, so its UNIQUE index
  enforces at most one active authorization per athlete (NULLs never collide
  in MySQL or SQLite).
- ``athlete_sensitive_data``: 1:1 with ``athletes``; exists only while an
  active authorization exists (withdrawal deletes the row).
- ``imderty_barrios``: platform-wide Yumbo catalog (public geography).
- ``club_imderty_settings``: 1:1 with ``clubs``; saved header defaults.

Privacy (Ley 1581): the category excluded by FR-009 deliberately has no enum,
column or label here; its sheet column is always left blank. Values of these columns must never reach logs,
error messages, audit ``diff_json`` or AI context.
"""
from __future__ import annotations

import enum
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import UpdatedByMixin

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.club import Club
    from app.models.user import User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


# ---------------------------------------------------------------------------
# Enums (stored values → official sheet text via the *_LABELS maps)
# ---------------------------------------------------------------------------


class ImdertyDocumentType(str, enum.Enum):
    rc = "rc"
    ti = "ti"
    cc = "cc"
    ce = "ce"
    ppt = "ppt"
    pep = "pep"
    nes = "nes"


class ImdertyGrade(str, enum.Enum):
    prejardin = "prejardin"
    jardin = "jardin"
    transicion = "transicion"
    g1 = "g1"
    g2 = "g2"
    g3 = "g3"
    g4 = "g4"
    g5 = "g5"
    g6 = "g6"
    g7 = "g7"
    g8 = "g8"
    g9 = "g9"
    g10 = "g10"
    g11 = "g11"
    no_escolarizado = "no_escolarizado"
    otro = "otro"


class ImdertyEthnicity(str, enum.Enum):
    """The 9 official values; the stored value IS the sheet text."""

    AFROCOLOMBIANO = "AFROCOLOMBIANO"
    INDIGENA = "INDÍGENA"
    MESTIZO = "MESTIZO"
    MULATO = "MULATO"
    NO_SABE_NO_RESPONDE = "NO SABE NO RESPONDE"
    OTRO = "OTRO"
    PALENQUERO = "PALENQUERO"
    RAIZAL = "RAIZAL"
    ROM_GITANO = "ROM GITANO"


class ImdertyDisability(str, enum.Enum):
    """The 10 official values; the stored value IS the sheet text."""

    OLFATIVA_Y_TACTO = "OLFATIVA Y TACTO"
    MENTAL = "MENTAL"
    MOVILIDAD = "MOVILIDAD"
    MULTIPLE = "MULTIPLE"
    ORAL = "ORAL"
    PSICOSOCIAL = "PSICOSOCIAL"
    VISUAL = "VISUAL"
    VOZ_Y_HABLA = "VOZ Y HABLA"
    NO_SABE_NOMBRARLA = "NO SABE NOMBRARLA"
    NA = "N/A"


class ImdertyYesNo(str, enum.Enum):
    """Armed-conflict victim status."""

    si = "si"
    no = "no"


class ImdertyProgram(str, enum.Enum):
    masificacion = "masificacion"
    educacion_fisica_deporte_escolar = "educacion_fisica_deporte_escolar"
    primera_infancia = "primera_infancia"
    hevs = "hevs"
    recreacion = "recreacion"
    deporte_social_comunitario = "deporte_social_comunitario"
    lecyd_cda = "lecyd_cda"
    competencia = "competencia"
    conjunto = "conjunto"
    individual = "individual"
    adaptado = "adaptado"


# Official text written to the sheet cells.
DOCUMENT_TYPE_LABELS: dict[ImdertyDocumentType, str] = {
    ImdertyDocumentType.rc: "R.C",
    ImdertyDocumentType.ti: "T.I",
    ImdertyDocumentType.cc: "C.C",
    ImdertyDocumentType.ce: "C.E",
    ImdertyDocumentType.ppt: "PPT",
    ImdertyDocumentType.pep: "PEP",
    ImdertyDocumentType.nes: "NES",
}

GRADE_LABELS: dict[ImdertyGrade, str] = {
    ImdertyGrade.prejardin: "PREJARDIN",
    ImdertyGrade.jardin: "JARDIN",
    ImdertyGrade.transicion: "TRANSICION",
    **{ImdertyGrade(f"g{n}"): str(n) for n in range(1, 12)},
    ImdertyGrade.no_escolarizado: "NO ESCOLARIZADO",
    ImdertyGrade.otro: "OTRO",
}

ETHNICITY_LABELS: dict[ImdertyEthnicity, str] = {m: m.value for m in ImdertyEthnicity}

DISABILITY_LABELS: dict[ImdertyDisability, str] = {m: m.value for m in ImdertyDisability}

YES_NO_LABELS: dict[ImdertyYesNo, str] = {
    ImdertyYesNo.si: "SI",
    ImdertyYesNo.no: "NO",
}

# Program names as printed in the sheet header (spec "Header block").
PROGRAM_LABELS: dict[ImdertyProgram, str] = {
    ImdertyProgram.masificacion: "Masificación",
    ImdertyProgram.educacion_fisica_deporte_escolar: "Educación física / deporte escolar",
    ImdertyProgram.primera_infancia: "Primera infancia",
    ImdertyProgram.hevs: "HEVS",
    ImdertyProgram.recreacion: "Recreación",
    ImdertyProgram.deporte_social_comunitario: "Deporte social comunitario",
    ImdertyProgram.lecyd_cda: "LECYD-CDA",
    ImdertyProgram.competencia: "Competencia",
    ImdertyProgram.conjunto: "Conjunto",
    ImdertyProgram.individual: "Individual",
    ImdertyProgram.adaptado: "Adaptado",
}

# Allowed ``imderty_barrios.zone`` values (enforced by a CHECK constraint).
IMDERTY_ZONES: tuple[str, ...] = (
    "1",
    "2",
    "3",
    "4",
    "ZONA NORTE",
    "ZONA CENTRO",
    "ZONA SUR",
)

# Text written in the barrio cell when the athlete lives outside Yumbo.
OTHER_MUNICIPALITY_LABEL = "OTRO MUNICIPIO"

_ZONE_CHECK_SQL = "zone IN ({})".format(", ".join(f"'{z}'" for z in IMDERTY_ZONES))


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


class ImdertyBarrio(UpdatedByMixin, Base):
    """Yumbo barrio → comuna/zone catalog (platform-wide, admin-maintained)."""

    __tablename__ = "imderty_barrios"
    __table_args__ = (
        UniqueConstraint("name", name="uq_imderty_barrios_name"),
        CheckConstraint(_ZONE_CHECK_SQL, name="ck_imderty_barrios_zone"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    zone: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )


class AthleteImdertyProfile(UpdatedByMixin, Base):
    """Non-sensitive identification block of the sheet (1:1 athlete)."""

    __tablename__ = "athlete_imderty_profiles"
    __table_args__ = (
        CheckConstraint(
            "NOT (other_municipality = 1 AND barrio_id IS NOT NULL)",
            name="ck_athlete_imderty_profiles_barrio_xor_other",
        ),
        Index("ix_athlete_imderty_profiles_barrio_id", "barrio_id"),
    )

    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), primary_key=True
    )
    first_surname: Mapped[str | None] = mapped_column(String(100), nullable=True)
    second_surname: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Cleared when athletes.last_name changes (research R7).
    surname_split_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    surname_split_confirmed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    document_type: Mapped[ImdertyDocumentType | None] = mapped_column(
        Enum(
            ImdertyDocumentType,
            name="imdertydocumenttype",
            values_callable=_values,
        ),
        nullable=True,
    )
    document_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # RESTRICT: a barrio referenced by a profile is deactivated, never deleted.
    barrio_id: Mapped[int | None] = mapped_column(
        ForeignKey("imderty_barrios.id", ondelete="RESTRICT"), nullable=True
    )
    other_municipality: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    school: Mapped[str | None] = mapped_column(String(150), nullable=True)
    grade: Mapped[ImdertyGrade | None] = mapped_column(
        Enum(ImdertyGrade, name="imdertygrade", values_callable=_values),
        nullable=True,
    )
    eps: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )

    athlete: Mapped[Athlete] = relationship(
        "Athlete",
        back_populates="imderty_profile",
        foreign_keys="[AthleteImdertyProfile.athlete_id]",
    )
    barrio: Mapped[ImdertyBarrio | None] = relationship(
        "ImdertyBarrio",
        foreign_keys="[AthleteImdertyProfile.barrio_id]",
    )


class AthleteSensitiveAuthorization(Base):
    """Append-only guardian authorization for the sensitive block.

    State: active (``withdrawn_at`` NULL, ``active_key`` = ``athlete_id``) →
    withdrawn (``withdrawn_at`` set, ``active_key`` NULL). A new authorization
    after a withdrawal is a new row.
    """

    __tablename__ = "athlete_sensitive_authorizations"
    __table_args__ = (
        UniqueConstraint(
            "active_key", name="uq_athlete_sensitive_authorizations_active_key"
        ),
        Index("ix_athlete_sensitive_authorizations_athlete_id", "athlete_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False
    )
    guardian_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    authorized_on: Mapped[date] = mapped_column(Date, nullable=False)
    recorded_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    withdrawn_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    # = athlete_id while active, NULL once withdrawn (at most one active row).
    active_key: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )

    athlete: Mapped[Athlete] = relationship(
        "Athlete",
        foreign_keys="[AthleteSensitiveAuthorization.athlete_id]",
    )
    guardian: Mapped[User] = relationship(
        "User",
        foreign_keys="[AthleteSensitiveAuthorization.guardian_user_id]",
    )

    @property
    def is_active(self) -> bool:
        return self.withdrawn_at is None and self.active_key is not None


class AthleteSensitiveData(UpdatedByMixin, Base):
    """Ethnicity / disability / armed-conflict victim (1:1 athlete).

    Exists only while an active authorization exists; withdrawal deletes the
    row in the same transaction (FR-007).
    """

    __tablename__ = "athlete_sensitive_data"
    __table_args__ = (
        Index("ix_athlete_sensitive_data_authorization_id", "authorization_id"),
    )

    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), primary_key=True
    )
    authorization_id: Mapped[int] = mapped_column(
        ForeignKey("athlete_sensitive_authorizations.id"), nullable=False
    )
    ethnicity: Mapped[ImdertyEthnicity] = mapped_column(
        Enum(ImdertyEthnicity, name="imdertyethnicity", values_callable=_values),
        nullable=False,
        default=ImdertyEthnicity.NO_SABE_NO_RESPONDE,
    )
    disability: Mapped[ImdertyDisability] = mapped_column(
        Enum(ImdertyDisability, name="imdertydisability", values_callable=_values),
        nullable=False,
        default=ImdertyDisability.NA,
    )
    # No default: must be chosen explicitly.
    conflict_victim: Mapped[ImdertyYesNo | None] = mapped_column(
        Enum(ImdertyYesNo, name="imdertyyesno", values_callable=_values),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )

    athlete: Mapped[Athlete] = relationship(
        "Athlete",
        foreign_keys="[AthleteSensitiveData.athlete_id]",
    )
    authorization: Mapped[AthleteSensitiveAuthorization] = relationship(
        "AthleteSensitiveAuthorization",
        foreign_keys="[AthleteSensitiveData.authorization_id]",
    )


class ClubImdertySettings(UpdatedByMixin, Base):
    """Saved sheet-header defaults per club (1:1 club)."""

    __tablename__ = "club_imderty_settings"

    club_id: Mapped[int] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), primary_key=True
    )
    contractor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    venue: Mapped[str | None] = mapped_column(String(200), nullable=True)
    training_days: Mapped[str | None] = mapped_column(String(120), nullable=True)
    schedule: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # List of ImdertyProgram values; may be empty.
    programs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )

    club: Mapped[Club] = relationship(
        "Club",
        foreign_keys="[ClubImdertySettings.club_id]",
    )
