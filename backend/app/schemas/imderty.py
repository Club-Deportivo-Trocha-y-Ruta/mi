"""Esquemas Pydantic v2 de la planilla mensual de asistencia IMDERTY (feature 047).

Fuente de verdad: ``specs/047-imderty-attendance-sheet/contracts/api.md``.

Privacidad (Ley 1581): ningún mensaje de error de los validadores de este
módulo debe incluir el valor recibido — solo el nombre del problema — para
evitar que un documento, nombre o dato sensible de un menor termine en un
log de validación.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.imderty import (
    ImdertyDisability,
    ImdertyDocumentType,
    ImdertyEthnicity,
    ImdertyGrade,
    ImdertyProgram,
    ImdertyYesNo,
)

_DIGIT_ONLY_DOCUMENT_TYPES = {
    ImdertyDocumentType.rc,
    ImdertyDocumentType.ti,
    ImdertyDocumentType.cc,
}


#: Strict ``YYYY-MM``: four-digit year, zero-padded month 01–12. ``strptime``
#: alone would also accept ``2026-9`` or `` 2026-09``, which then leak into
#: the file name and the audit meta in a non-canonical form.
_YEAR_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$", re.ASCII)  # ASCII: no fullwidth digits


def _parse_year_month(value: str) -> tuple[int, int]:
    if not isinstance(value, str) or not _YEAR_MONTH_RE.fullmatch(value):
        raise ValueError("El mes debe tener el formato AAAA-MM")
    parsed = datetime.strptime(value, "%Y-%m")
    return parsed.year, parsed.month


# ---------------------------------------------------------------------------
# Perfil IMDERTY del deportista
# ---------------------------------------------------------------------------


class ImdertySurnameSplit(BaseModel):
    confirmed: bool
    proposed_first: str | None = None
    proposed_second: str | None = None


class ImdertyBarrioSummary(BaseModel):
    id: int
    name: str
    zone: str

    model_config = ConfigDict(from_attributes=True)


class ImdertyGuardianSummary(BaseModel):
    user_id: int
    display_name: str
    has_phone: bool
    is_primary_contact: bool


class ImdertySensitiveAuthorizationSummary(BaseModel):
    id: int
    guardian_user_id: int
    authorized_on: date
    active: bool

    model_config = ConfigDict(from_attributes=True)


class ImdertyProfileSensitiveOut(BaseModel):
    authorization: ImdertySensitiveAuthorizationSummary | None = None


class ImdertyProfileRead(BaseModel):
    athlete_id: int
    first_surname: str | None = None
    second_surname: str | None = None
    surname_split: ImdertySurnameSplit
    document_type: ImdertyDocumentType | None = None
    document_number: str | None = None
    address: str | None = None
    barrio: ImdertyBarrioSummary | None = None
    other_municipality: bool
    school: str | None = None
    grade: ImdertyGrade | None = None
    eps: str | None = None
    phone: str | None = None
    guardians: list[ImdertyGuardianSummary] = Field(default_factory=list)
    effective_phone_source: str | None = None
    sensitive: ImdertyProfileSensitiveOut

    model_config = ConfigDict(from_attributes=True)


class ImdertyProfileUpdate(BaseModel):
    # ``max_length`` mirrors each column (data-model.md). Without it a longer
    # value reaches MySQL, fails with "Data too long" (strict mode) and the
    # unhandled-exception log would carry the SQLAlchemy error text, whose
    # ``[parameters: ...]`` holds the submitted document number, address or
    # phone of a minor (privacy-audit.md, P-1). The 422 never echoes the value.
    first_surname: str | None = Field(default=None, max_length=100)
    second_surname: str | None = Field(default=None, max_length=100)
    document_type: ImdertyDocumentType | None = None
    document_number: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=200)
    barrio_id: int | None = None
    other_municipality: bool = False
    school: str | None = Field(default=None, max_length=150)
    grade: ImdertyGrade | None = None
    eps: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    confirm_surname_split: bool = False

    @field_validator("document_number")
    @classmethod
    def strip_document_number(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return v.strip()

    @model_validator(mode="after")
    def validate_document_number_digits(self) -> "ImdertyProfileUpdate":
        if (
            self.document_type in _DIGIT_ONLY_DOCUMENT_TYPES
            and self.document_number is not None
            and not self.document_number.isdigit()
        ):
            raise ValueError(
                "El número de documento debe contener solo dígitos para este tipo de documento"
            )
        return self

    @model_validator(mode="after")
    def validate_barrio_exclusive(self) -> "ImdertyProfileUpdate":
        if self.other_municipality and self.barrio_id is not None:
            raise ValueError(
                "No se puede indicar un barrio y marcar 'otro municipio' al mismo tiempo"
            )
        return self


class ImdertyProfileUpdateResult(ImdertyProfileRead):
    warnings: list[str] = Field(default_factory=list)


class PrimaryContactUpdate(BaseModel):
    guardian_user_id: int | None = None


# ---------------------------------------------------------------------------
# Datos sensibles
# ---------------------------------------------------------------------------


class SensitiveAuthorizationCreate(BaseModel):
    guardian_user_id: int
    authorized_on: date

    @field_validator("authorized_on")
    @classmethod
    def authorized_on_not_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("La fecha de autorización no puede ser futura")
        return v


class SensitiveAuthorizationRead(BaseModel):
    id: int
    guardian_user_id: int
    authorized_on: date
    active: bool

    model_config = ConfigDict(from_attributes=True)


class SensitiveDataRead(BaseModel):
    ethnicity: ImdertyEthnicity
    disability: ImdertyDisability
    conflict_victim: ImdertyYesNo | None = None

    model_config = ConfigDict(from_attributes=True)


class SensitiveDataUpdate(BaseModel):
    ethnicity: ImdertyEthnicity
    disability: ImdertyDisability
    conflict_victim: ImdertyYesNo | None = None


# ---------------------------------------------------------------------------
# Catálogo de barrios
# ---------------------------------------------------------------------------


class BarrioRead(BaseModel):
    id: int
    name: str
    zone: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class BarrioCreate(BaseModel):
    name: str = Field(max_length=120)
    zone: str = Field(max_length=20)
    is_active: bool = True


class BarrioUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    zone: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Configuración IMDERTY del club
# ---------------------------------------------------------------------------


class ClubImdertySettingsRead(BaseModel):
    contractor_name: str | None = None
    venue: str | None = None
    training_days: str | None = None
    schedule: str | None = None
    programs: list[ImdertyProgram] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ClubImdertySettingsUpdate(BaseModel):
    contractor_name: str | None = Field(default=None, max_length=200)
    venue: str | None = Field(default=None, max_length=200)
    training_days: str | None = Field(default=None, max_length=120)
    schedule: str | None = Field(default=None, max_length=120)
    programs: list[ImdertyProgram] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Planilla mensual
# ---------------------------------------------------------------------------


class ImdertySheetHeader(BaseModel):
    contractor_name: str | None = Field(default=None, max_length=200)
    venue: str | None = Field(default=None, max_length=200)
    training_days: str | None = Field(default=None, max_length=120)
    schedule: str | None = Field(default=None, max_length=120)
    programs: list[ImdertyProgram] = Field(default_factory=list)


class SheetRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_month: str = Field(alias="from")
    to_month: str = Field(alias="to")
    header: ImdertySheetHeader | None = None
    save_header_as_default: bool = False

    @field_validator("from_month", "to_month")
    @classmethod
    def validate_month_format(cls, v: str) -> str:
        _parse_year_month(v)
        return v

    @model_validator(mode="after")
    def validate_month_range(self) -> "SheetRequest":
        from_year, from_month_num = _parse_year_month(self.from_month)
        to_year, to_month_num = _parse_year_month(self.to_month)
        from_ordinal = from_year * 12 + from_month_num
        to_ordinal = to_year * 12 + to_month_num
        if to_ordinal < from_ordinal:
            raise ValueError("El mes final debe ser igual o posterior al mes inicial")
        if (to_ordinal - from_ordinal + 1) > 12:
            raise ValueError("El rango de meses no puede superar 12 meses")
        return self


class ReadinessGap(BaseModel):
    athlete_id: int
    display_name: str
    codes: list[str]
    activity_dates: list[date] = Field(default_factory=list)


class ReadinessRead(BaseModel):
    months: list[str]
    month_in_progress: bool
    months_without_activity: list[str]
    athlete_count: int
    gaps: list[ReadinessGap] = Field(default_factory=list)
