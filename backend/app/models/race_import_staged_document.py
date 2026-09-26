"""Modelo SQLAlchemy para ``race_import_staged_documents`` (amendment
2026-09-26, data-model.md §11.1).

Una fila 1:1 con una ``RaceImport`` en estado ``pending`` (o ``committed``
con ``pending_categories``): las filas que el CLI ``race-results-load``
extrajo del acta oficial, ya listas para que las rutas de revisión las
lean sin volver a tocar el archivo original (FR-048, FR-049 — "el servidor
nunca vuelve a leer el archivo almacenado", research R-20).

**Clase de privacidad**: igual que ``race_competitors`` y
``RaceImport.parse_meta_json["corrections"]``. ``document_json`` contiene
nombre, ciudad y club de cada corredor — de los cuales cerca del 90 % son
menores de edad (Ley 1581). Vive únicamente en la base de datos: ningún
schema Pydantic lo serializa completo hacia un endpoint, y ningún log,
traza o mensaje de excepción de ``app.services.race.staged_document``
incluye un valor de fila (solo ``import_id``/conteos) — ver ese módulo.

Sin relación declarada hacia ``RaceImport``: el loader (T116) siempre
selecciona por clave primaria (``import_id``), así que un
``relationship`` de carga perezosa nunca hace falta y solo agregaría un
riesgo de lazy-load asíncrono (``MissingGreenlet``) si algún día alguien
accede a ``import.staged_document`` fuera de un ``await``.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CHAR, DateTime, ForeignKey, Integer, JSON, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RaceImportStagedDocument(Base):
    """Documento en bruto (categorías + filas) de una ingesta en revisión.

    ``import_id`` es a la vez PK y FK: relación 1:1 estricta con
    ``race_imports``. ``ON DELETE CASCADE`` porque un documento huérfano
    (sin import) no tiene sentido ni uso — borrar el import se lleva su
    documento igual que borrar un import ya se lleva sus resultados.
    """

    __tablename__ = "race_import_staged_documents"

    import_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("race_imports.id", ondelete="CASCADE"),
        primary_key=True,
    )
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    #: Perfil de lectura aplicado (``race_reading_profiles/<profile_id>.json``).
    profile_id: Mapped[str] = mapped_column(String(64), nullable=False)
    #: SHA-256 del archivo de perfil tal como se aplicó — así una edición
    #: posterior del perfil no cambia en silencio lo que el coach revisó.
    profile_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Ver ``data-model.md`` §11.2 para la forma exacta:
    #: ``{"categories": [...], "unreadable_rows": [...]}``.
    document_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
