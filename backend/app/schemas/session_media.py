from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.session_media import MediaType


class SessionMediaCreate(BaseModel):
    """Payload (multipart side-channel) para subir una media.

    El archivo viene en `UploadFile`; estos campos vienen como Form fields.
    """

    media_type: MediaType
    caption: str | None = Field(default=None, max_length=280)
    athlete_ids: list[int] = Field(min_length=1)
    consent_ack: bool = Field(
        ...,
        description="El coach declara que cuenta con consentimiento parental para los atletas etiquetados.",
    )

    @model_validator(mode="after")
    def _require_consent(self) -> "SessionMediaCreate":
        if not self.consent_ack:
            raise ValueError(
                "Debe marcar la casilla de consentimiento parental (Ley 1581) "
                "antes de subir media de menores."
            )
        return self


class SessionMediaUpdate(BaseModel):
    """Actualización parcial de caption y atletas etiquetados."""

    caption: str | None = Field(default=None, max_length=280)
    athlete_ids: list[int] | None = Field(default=None, min_length=1)


class SessionMediaAthleteTag(BaseModel):
    athlete_id: int

    model_config = {"from_attributes": True}


class SessionMediaRead(BaseModel):
    """Respuesta para coach/admin: incluye storage_path y uploader."""

    id: int
    session_id: int
    media_type: MediaType
    storage_url: str
    thumbnail_url: str | None
    filename_original: str
    mime_type: str
    size_bytes: int
    width: int | None
    height: int | None
    duration_sec: int | None
    caption: str | None
    consent_ack: bool
    uploaded_by_user_id: int
    uploaded_at: datetime
    athlete_ids: list[int] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class SessionMediaReadParent(BaseModel):
    """Respuesta para padres: omite uploader, storage_path y consent flag."""

    id: int
    session_id: int
    media_type: MediaType
    storage_url: str
    thumbnail_url: str | None
    mime_type: str
    width: int | None
    height: int | None
    duration_sec: int | None
    caption: str | None
    uploaded_at: datetime

    model_config = {"from_attributes": True}
