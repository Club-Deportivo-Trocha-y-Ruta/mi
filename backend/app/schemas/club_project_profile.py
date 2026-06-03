"""Schemas Pydantic para ClubProjectProfile (perfil de proyecto del club).

Usado en el "Informe Técnico Mensual" estilo financiador. Todos los campos
de contenido son opcionales para permitir PATCH parcial (upsert incremental).

Privacidad: este schema no contiene datos de menores — es metadata del club
(entidad ejecutora, responsable, objetivos, territorio). Sin restricciones de
rol en el schema; el router aplica RBAC (coach/admin del club).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ClubProjectProfileBase(BaseModel):
    """Campos comunes para create y update."""

    project_name: str | None = Field(default=None, max_length=200)
    executing_entity: str | None = Field(default=None, max_length=200)
    report_responsible: str | None = Field(default=None, max_length=200)
    purpose: str | None = Field(default=None, max_length=2000)
    general_objective: str | None = Field(default=None, max_length=2000)
    specific_objectives: list[str] | None = Field(
        default=None,
        description="Lista de objetivos específicos del proyecto (JSON array).",
    )
    territory_location: str | None = Field(default=None, max_length=200)
    territory_description: str | None = Field(default=None, max_length=2000)


class ClubProjectProfileCreate(ClubProjectProfileBase):
    """Payload para crear o reemplazar el perfil de proyecto del club (PUT)."""
    pass


class ClubProjectProfileUpdate(ClubProjectProfileBase):
    """Payload para actualización parcial (PATCH).

    Todos los campos heredados ya son Optional[...] = None desde la base,
    por lo que cumple la semántica de "solo actualiza lo que llega".
    Se usa ``model.model_dump(exclude_unset=True)`` en el servicio.
    """
    pass


class ClubProjectProfileRead(ClubProjectProfileBase):
    """Respuesta de lectura del perfil de proyecto del club."""

    id: int
    club_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
