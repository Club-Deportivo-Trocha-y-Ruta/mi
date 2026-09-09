"""Esquemas Pydantic para el historial de auditoría (feature 041).

Ver ``specs/041-multi-coach-governance/contracts/audit-log-api.md`` §5 y
§14.3. Los enums se importan de ``app.models.audit_log`` y
``app.services.audit`` — nunca se redeclaran aquí.

Privacidad (Ley 1581, FR-003): el único nombre propio que puede viajar en
estos esquemas es el del actor (un adulto: entrenador o administrador). El
deportista siempre viaja como ``athlete_id``, nunca por nombre.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.audit_log import AuditAction, AuditActorKind
from app.models.user import UserRole
from app.services.audit import AuditEntityType, AuditReasonGroup

#: Tipos admitidos dentro de `diff` — garantizados por VALUE_ALLOWLIST
#: (data-model §2.5): enums/estados, banderas, fechas de evento, FKs,
#: contadores, y la única lista permitida (`hidden_blocks`).
DiffScalar = str | int | float | bool | list[str] | None


class AuditDiffValue(BaseModel):
    """Valor antes/después de un campo permitido por la allow-list."""

    before: DiffScalar = None
    after: DiffScalar = None


class AuditEntryDetail(BaseModel):
    """Detalle expandible ("Ver detalle"). FR-008: los nombres crudos de
    columna y los identificadores viven aquí, nunca en `sentence_es`.
    """

    changed_fields: list[str] = Field(default_factory=list)
    changed_field_labels: list[str] = Field(default_factory=list)  # 1:1 con changed_fields
    diff: dict[str, AuditDiffValue] | None = None
    meta: dict[str, Any] | None = None


class AuditEntryOut(BaseModel):
    """Una entrada del historial, lista para renderizar.

    Privacidad (Ley 1581, FR-003): el único nombre propio que puede aparecer
    es el del actor (adulto: coach o administrador). Ningún campo lleva el
    nombre, la fecha de nacimiento ni datos del deportista; el atleta viaja
    solo como `athlete_id`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime           # UTC naive, ISO 8601 con microsegundos
    actor_user_id: int | None = None
    actor_kind: AuditActorKind
    actor_role: UserRole | None = None
    actor_display_name: str         # resuelto por JOIN o etiqueta de actor automático
    action: AuditAction
    entity_type: AuditEntityType
    entity_id: int
    entity_label: str               # etiqueta es-CO del tipo de registro
    club_id: int | None = None
    athlete_id: int | None = None
    reason_code: str | None = None
    reason_label: str | None = None  # AUDIT_REASON_LABELS[reason_code]
    sentence_es: str                # frase FR-008, siempre presente
    request_id: str
    detail: AuditEntryDetail


class AuditListOut(BaseModel):
    """Página del historial, más reciente primero."""

    items: list[AuditEntryOut]
    total: int
    limit: int
    offset: int


class AuditReasonCodeOut(BaseModel):
    """Una opción del catálogo cerrado de motivos (data-model §2.4)."""

    code: str                 # valor de AuditReasonCode
    label: str                # AUDIT_REASON_LABELS[code], es-CO con tildes
    group: AuditReasonGroup


class AuditReasonCodeListOut(BaseModel):
    """Catálogo completo o filtrado por grupo. Nunca paginado."""

    items: list[AuditReasonCodeOut]
