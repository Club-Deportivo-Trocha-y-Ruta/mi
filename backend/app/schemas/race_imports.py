"""Pydantic v2 schemas para los endpoints `/api/race-analysis/imports/*`.

Cubre los DTOs del wizard upload UI (F-UP3, docs/10-race-results/upload-design.md §4):

- ``ImportParseResponse``      — output del paso 1 (parse).
- ``ImportDryRunResponse``     — output del paso 2 (dry-run preview).
- ``ImportCommitRequest``      — body del paso 3 (commit con resolved matches).
- ``ImportCommitResponse``     — output del paso 3 (post-ingest).
- ``ImportListResponse``       — output del histórico GET /.
- ``ImportParseRequestFields`` — campos de condiciones de carrera para el wizard.
- ``RaceEventConditionsRead``  — respuesta del PATCH condiciones (B3).
- ``RaceEventConditionsUpdate``— body del PATCH condiciones (B3).

Convenciones:
- Pydantic v2 (``model_config``, ``ConfigDict``).
- Ningún campo contiene datos PII de menores: matches usan
  ``competitor_normalized_name`` (slug normalizado) + ``athlete_id`` opcional.
- Nombres reales SÍ aparecen en ``MatchPreview.competitor_name`` (display) —
  estos son de PDFs ya públicos por la Federación, no datos privados de TyR.
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.race_event import SurfaceCondition
from app.services.race.completeness import AcknowledgeReasonCode


# ---------------------------------------------------------------------------
# Catálogo CERRADO de motivos de revisión (PR4 unificación /competitions)
# ---------------------------------------------------------------------------


class RevisionReasonCode(str, enum.Enum):
    """Motivos permitidos para una re-ingesta (revisión).

    Catálogo CERRADO — reemplaza el texto libre previo. Privacidad menores:
    al ser un enum, el coach NO puede escribir nombres ni datos sensibles en
    el motivo (que se persiste en ``race_result_revisions.reason`` y
    ``race_imports.revision_reason``).
    """

    official_correction = "official_correction"  # Corrección oficial de la fed
    timing_fix = "timing_fix"  # Ajuste de tiempos
    position_fix = "position_fix"  # Reordenamiento de posiciones
    category_reclassification = "category_reclassification"  # Recategorización
    dsq_added = "dsq_added"  # Descalificación añadida
    result_removed = "result_removed"  # Resultado retirado del acta
    result_added = "result_added"  # Resultado añadido al acta
    data_entry_error = "data_entry_error"  # Error de digitación previo


#: Etiquetas legibles (es-CO) para la UI. El backend solo persiste el code.
REVISION_REASON_LABELS: dict[RevisionReasonCode, str] = {
    RevisionReasonCode.official_correction: "Corrección oficial de la Federación",
    RevisionReasonCode.timing_fix: "Ajuste de tiempos",
    RevisionReasonCode.position_fix: "Reordenamiento de posiciones",
    RevisionReasonCode.category_reclassification: "Recategorización de deportistas",
    RevisionReasonCode.dsq_added: "Descalificación añadida",
    RevisionReasonCode.result_removed: "Resultado retirado del acta",
    RevisionReasonCode.result_added: "Resultado añadido al acta",
    RevisionReasonCode.data_entry_error: "Error de digitación previo",
}


# ---------------------------------------------------------------------------
# Subtipos compartidos
# ---------------------------------------------------------------------------


class EventHeaderPreview(BaseModel):
    """Header detectado por el parser desde el PDF RESULTADOS.

    Cuando el parser no puede detectar el header (PDF atípico), todos los
    campos quedan None y el coach debe rellenarlos en el wizard step 2.
    """

    model_config = ConfigDict(from_attributes=True)

    valida_num: Optional[int] = None
    location: Optional[str] = None
    event_date: Optional[date] = None
    name: Optional[str] = None


class ParseWarning(BaseModel):
    """Warning no-bloqueante emitido durante parse o dry-run."""

    model_config = ConfigDict(from_attributes=True)

    code: str  # "category_unknown" | "time_anomaly" | "dorsal_mismatch" | ...
    message: str
    context: Optional[dict] = None  # ej. {"bib": "424", "cat": "INF_A"}


class TyrAthleteRef(BaseModel):
    """Referencia compacta a un atleta TyR (sin datos sensibles)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str  # nombre del atleta (uso interno coach — no se expone a padres aquí)


class MatchPreview(BaseModel):
    """Match detectado por el matcher fuzzy para un competidor del PDF.

    Reglas:
    - ``tyr_athlete=None`` y ``confidence=0`` → no hubo match candidato.
    - ``is_ambiguous=True`` → hay 2+ candidatos con scores similares; el coach
      debe resolver manualmente en el paso commit.
    - ``confidence`` ∈ [0, 1].
    """

    model_config = ConfigDict(from_attributes=True)

    competitor_name: str
    competitor_normalized_name: str
    tyr_athlete: Optional[TyrAthleteRef] = None
    confidence: float = Field(ge=0.0, le=1.0)
    is_ambiguous: bool = False


class DryRunCounts(BaseModel):
    """Conteos agregados de matches en el preview dry-run."""

    model_config = ConfigDict(from_attributes=True)

    confirmed: int = 0
    ambiguous: int = 0
    no_match: int = 0
    total: int = 0


# ---------------------------------------------------------------------------
# Integridad de lectura (feature 044, US1) — contracts/reading-integrity.md
# ---------------------------------------------------------------------------


class ParsedResultsRowRead(BaseModel):
    """Una fila cruda del acta tal como la interpretó el parser.

    Espejo de ``pdf_parser.ResultsRow`` para el wizard de importación — el
    coach ya vio estos mismos datos en el PDF/CSV que acaba de subir, así
    que mostrarlos aquí no expone nada nuevo (misma base que
    ``MatchPreview.competitor_name``). ``time_raw == ""`` significa
    "clasificada sin tiempo" (research R-01 punto 4), no ``DNF``/``DSQ``.
    """

    model_config = ConfigDict(from_attributes=True)

    position: Optional[int] = None
    bib: str = ""
    name: str = ""
    city: str = ""
    club: str = ""
    time_raw: str = ""
    points: int = 0


class CompletenessRead(BaseModel):
    """Estado de completitud de una categoría (``completeness.CompletenessReport``)."""

    model_config = ConfigDict(from_attributes=True)

    status: Literal["ok", "inconsistent", "acknowledged"]
    missing: list[int] = Field(default_factory=list)
    duplicated: list[int] = Field(default_factory=list)


class ParsedCategoryRead(BaseModel):
    """Una categoría del acta tal como la vio el parser, con su completitud.

    ``code=None`` significa encabezado no reconocido: las filas se conservan
    igual (FR-002) y el commit de esa categoría queda bloqueado hasta que
    exista un mapeo. ``mapping_kind`` distingue exact/rename/season_specific
    /unknown (``normalizer.mapping_kind_for``).
    """

    model_config = ConfigDict(from_attributes=True)

    header_raw: str
    code: Optional[str] = None
    mapping_kind: str
    rows: list[ParsedResultsRowRead] = Field(default_factory=list)
    completeness: CompletenessRead


class UnreadableRowRead(BaseModel):
    """Banda de fila que el parser no pudo interpretar (FR-001).

    Solo ubicación — nunca contenido de la fila (privacidad menores).
    """

    model_config = ConfigDict(from_attributes=True)

    page: int
    ordinal: Optional[int] = None


class ResultsRowIn(BaseModel):
    """Cuerpo de una fila para ``POST /{parse_id}/corrections`` (add/edit).

    Espejo de los campos que ``completeness._build_row`` acepta
    (``_ROW_FIELDS``). ``extra="forbid"`` para que un campo inesperado se
    rechace en el borde HTTP en vez de perderse en silencio.
    """

    model_config = ConfigDict(extra="forbid")

    position: Optional[int] = None
    bib: str = ""
    name: str = ""
    city: str = ""
    club: str = ""
    time_raw: str = ""
    points: int = 0


class RowCorrectionIn(BaseModel):
    """Body de ``POST /{parse_id}/corrections`` (research R-05).

    ``row`` es obligatorio para ``add``/``edit`` (``remove`` no lo necesita);
    esa regla la aplica ``completeness.apply_corrections`` porque depende del
    ``op`` — aquí solo se valida la forma del payload, no la combinación.
    """

    model_config = ConfigDict(extra="forbid")

    op: Literal["add", "edit", "remove"]
    category_header: str = Field(min_length=1, max_length=200)
    ordinal: int
    row: Optional[ResultsRowIn] = None

    @model_validator(mode="after")
    def _row_position_required_for_add_or_edit(self) -> "RowCorrectionIn":
        """``check_completeness``/``check_category`` solo miran filas con
        ``position`` — una fila ``add``/``edit`` sin ``row.position`` entraría
        en el acta y desaparecería en silencio de la verificación de
        completitud (una categoría podría quedar reportada ``ok`` mientras la
        fila corregida no cuenta para nada). ``remove`` no necesita ``row``.
        """
        if self.op in ("add", "edit") and (
            self.row is None or self.row.position is None
        ):
            raise ValueError(
                "row.position es obligatorio para 'add'/'edit': sin él, la "
                "fila corregida queda fuera de la verificación de "
                "completitud de la categoría (el ordinal por sí solo no la "
                "reemplaza)."
            )
        return self


class CategoryCompletenessResponse(BaseModel):
    """Respuesta común de ``/corrections`` y ``/acknowledge``: la
    completitud recalculada de la categoría afectada."""

    model_config = ConfigDict(from_attributes=True)

    category_header: str
    completeness: CompletenessRead


class AcknowledgeIn(BaseModel):
    """Body de ``POST /{parse_id}/acknowledge`` (research R-05).

    ``reason`` es un code del catálogo CERRADO ``AcknowledgeReasonCode`` —
    Pydantic rechaza cualquier valor fuera del enum con 422, igual que
    ``RevisionReasonCode`` en el commit.
    """

    model_config = ConfigDict(extra="forbid")

    category_header: str = Field(min_length=1, max_length=200)
    reason: AcknowledgeReasonCode


class AcknowledgeReasonOption(BaseModel):
    """Opción del catálogo de motivos de reconocimiento (dropdown UI)."""

    model_config = ConfigDict(extra="forbid")

    code: str
    label: str


class AcknowledgeReasonsResponse(BaseModel):
    """Catálogo cerrado de motivos de reconocimiento de completitud."""

    model_config = ConfigDict(extra="forbid")

    options: list[AcknowledgeReasonOption]


# ---------------------------------------------------------------------------
# Parse response
# ---------------------------------------------------------------------------


class ParseHeaderInfo(BaseModel):
    """Header expuesto al cliente (combina series + event)."""

    model_config = ConfigDict(from_attributes=True)

    series_name: str
    season: int
    valida_num: int
    event_name: str


class ImportParseResponse(BaseModel):
    """Respuesta del endpoint POST /imports/parse (F-UP3 §4.1 + F-UP-REV2).

    F-UP-REV2: campos opcionales ``will_be_revision`` y metadatos del parent
    cuando el sistema detecta que la `(series, valida)` ya está committed
    (revision-design.md §1.3). Todos los campos extra son opcionales para
    preservar backward compat con clientes F-UP.
    """

    model_config = ConfigDict(from_attributes=True)

    parse_id: int  # = RaceImport.id (status='pending')
    sha256: str  # SHA del PDF RESULTADOS (64 hex chars)
    header: ParseHeaderInfo
    n_rows_resultados: int
    n_rows_general: Optional[int] = None
    warnings: list[ParseWarning] = Field(default_factory=list)

    # Feature 044 (US1): integridad de lectura — contracts/reading-integrity.md.
    # Aditivo: default vacío, un cliente previo sigue deserializando igual.
    categories: list[ParsedCategoryRead] = Field(default_factory=list)
    unreadable_rows: list[UnreadableRowRead] = Field(default_factory=list)

    # F-UP-REV2: detección de revisión post-parse
    will_be_revision: bool = False
    parent_event_id: Optional[int] = None
    parent_import_id: Optional[int] = None
    parent_committed_at: Optional[datetime] = None
    parent_n_results: Optional[int] = None


# ---------------------------------------------------------------------------
# Dry-run response
# ---------------------------------------------------------------------------


class ImportDryRunResponse(BaseModel):
    """Respuesta del endpoint POST /imports/{parse_id}/dry-run (F-UP3 §4.2)."""

    model_config = ConfigDict(from_attributes=True)

    parse_id: int
    matches: list[MatchPreview]
    counts: DryRunCounts
    warnings: list[ParseWarning] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Commit request / response
# ---------------------------------------------------------------------------


class ResolvedMatch(BaseModel):
    """Decisión del coach para un competidor del PDF.

    - ``athlete_id=None`` significa "no es atleta TyR" o "crear atleta después".
    - El service valida que TODOS los `MatchPreview.is_ambiguous=True` tengan
      resolved match aquí; si falta alguno, 422.
    """

    model_config = ConfigDict(from_attributes=True)

    competitor_normalized_name: str = Field(min_length=1, max_length=200)
    athlete_id: Optional[int] = None


class ImportCommitRequest(BaseModel):
    """Body del endpoint POST /imports/{parse_id}/commit (F-UP3 §4.3).

    PR4: ``revision_reason`` ahora es un code del catálogo CERRADO
    (``RevisionReasonCode``), no texto libre. Privacidad menores: el coach no
    puede escribir nombres/datos sensibles en el motivo. Pydantic rechaza
    cualquier valor fuera del enum con 422.
    """

    model_config = ConfigDict(from_attributes=True)

    resolved_matches: list[ResolvedMatch] = Field(default_factory=list)
    revision_reason: Optional[RevisionReasonCode] = Field(
        default=None,
        description=(
            "Motivo de la revisión (catálogo cerrado). Obligatorio si el diff "
            "incluye eliminaciones (validado en el flujo de revisión)."
        ),
    )


class RevisionReasonOption(BaseModel):
    """Opción del catálogo de motivos de revisión (para poblar el dropdown UI)."""

    model_config = ConfigDict(extra="forbid")

    code: str
    label: str


class RevisionReasonsResponse(BaseModel):
    """Catálogo cerrado de motivos de revisión."""

    model_config = ConfigDict(extra="forbid")

    options: list[RevisionReasonOption]


class ImportCommitResponse(BaseModel):
    """Respuesta del endpoint POST /imports/{parse_id}/commit (F-UP3 §4.3)."""

    model_config = ConfigDict(from_attributes=True)

    parse_id: int
    race_event_id: int
    n_results_inserted: int
    n_competitors_created: int
    n_competitors_linked: int
    # Feature 044 (US1/US5): headers de categorías cuyo commit quedó fuera
    # (inconsistentes sin reconocer, o de encabezado no reconocido). El
    # backfill real de esta lista es de T060/T061 (commit-pending);
    # aditivo con default vacío para no romper clientes previos.
    pending_categories: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Diff read-only de la última revisión (PR4 unificación /competitions)
# GET /api/race-analysis/imports/{race_event_id}/diff
# ---------------------------------------------------------------------------


class RevisionDiffItem(BaseModel):
    """Un cambio individual de la última revisión, agrupable en la UI.

    Privacidad: ``competitor_display_name`` proviene de PDFs públicos de la
    Federación (no datos privados de TyR). NO se exponen ``athlete_id`` ni IDs
    internos de usuario.
    """

    model_config = ConfigDict(extra="forbid")

    action: str = Field(..., description="create | update | delete")
    group: str = Field(
        ...,
        description=(
            "Grupo UI: position | time | gap_gc | category_reclassified | "
            "added_removed"
        ),
    )
    competitor_display_name: str
    category_code: str | None = None
    field_before: str | None = Field(
        default=None, description="Valor previo (display) del campo cambiado."
    )
    field_after: str | None = Field(
        default=None, description="Valor nuevo (display) del campo cambiado."
    )


class RevisionDiffGroupCounts(BaseModel):
    """Conteos por grupo para los encabezados de la UI."""

    model_config = ConfigDict(extra="forbid")

    position: int = 0
    time: int = 0
    gap_gc: int = 0
    category_reclassified: int = 0
    added_removed: int = 0


class RaceEventDiffResponse(BaseModel):
    """Diff read-only de la última revisión commiteada de una válida.

    Si la válida no tiene revisiones (primer import o sin re-ingesta), retorna
    ``has_revision=false`` y listas vacías.
    """

    model_config = ConfigDict(extra="forbid")

    race_event_id: int
    has_revision: bool
    last_revision_at: datetime | None = None
    reason_code: str | None = Field(
        default=None,
        description="Code del catálogo cerrado (o legacy text si es previo a PR4).",
    )
    counts: RevisionDiffGroupCounts = Field(default_factory=RevisionDiffGroupCounts)
    items: list[RevisionDiffItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# List histórico
# ---------------------------------------------------------------------------


class UploadUserRef(BaseModel):
    """Referencia compacta al usuario que subió el import (auditoría)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str


class ImportListItem(BaseModel):
    """Item del listado de imports (F-UP3 §4.4)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str  # 'resultados' | 'general' | 'both'
    status: str  # 'pending' | 'committed' | 'failed' | 'dry_run'
    created_at: datetime
    event_id: Optional[int] = None
    original_filename: Optional[str] = None
    uploaded_by: UploadUserRef
    n_results: int = 0  # extraído de stats_json.results_inserted


class ImportListResponse(BaseModel):
    """Respuesta paginada del histórico de imports."""

    model_config = ConfigDict(from_attributes=True)

    items: list[ImportListItem]
    total: int


# ---------------------------------------------------------------------------
# Campos de condiciones de carrera — wizard upload (B1)
# ---------------------------------------------------------------------------


class ImportParseRequestFields(BaseModel):
    """Campos opcionales de condiciones de carrera para el wizard de ingesta.

    Se validan dentro del handler POST /parse después de extraer los valores
    de los ``Form()`` params (FastAPI no aplica Pydantic automáticamente a
    campos multipart individuales). La construcción explícita del modelo
    en el handler garantiza que la validación sea idéntica a la del PATCH B3.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    climate: Optional[str] = Field(
        default=None,
        max_length=60,
        description="Descripción libre del clima (ej: 'Soleado con viento moderado').",
    )
    temperature_c: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=50,
        decimal_places=1,
        description="Temperatura en grados Celsius (0-50). Un decimal.",
    )
    surface_condition: Optional[SurfaceCondition] = Field(
        default=None,
        description="Condición del trazado: seca | humeda | barro | lluvia | mixta.",
    )
    altitude_msnm: Optional[int] = Field(
        default=None,
        ge=0,
        le=5000,
        description="Altitud en metros sobre el nivel del mar (0-5000).",
    )
    weather_notes: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Notas adicionales de condiciones climatológicas.",
    )


# ---------------------------------------------------------------------------
# DTOs para PATCH /api/race-analysis/race-events/{id}/conditions (B3)
# ---------------------------------------------------------------------------


class RaceEventConditionsUpdate(BaseModel):
    """Body del PATCH — actualización parcial de condiciones de carrera.

    Solo los campos enviados (exclude_unset=True) se aplican al evento.
    Campos extra son rechazados (extra='forbid') para evitar inyecciones
    accidentales de atributos no esperados.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    climate: Optional[str] = Field(
        default=None,
        max_length=60,
        description="Descripción libre del clima.",
    )
    temperature_c: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=50,
        decimal_places=1,
        description="Temperatura en grados Celsius (0-50). Un decimal.",
    )
    surface_condition: Optional[SurfaceCondition] = Field(
        default=None,
        description="Condición del trazado: seca | humeda | barro | lluvia | mixta.",
    )
    altitude_msnm: Optional[int] = Field(
        default=None,
        ge=0,
        le=5000,
        description="Altitud sobre el nivel del mar en metros.",
    )
    weather_notes: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Notas adicionales de condiciones climatológicas.",
    )


class RaceEventConditionsRead(BaseModel):
    """Respuesta del PATCH — condiciones actuales del evento tras el update.

    ``from_attributes=True`` permite construir directamente desde el ORM
    ``RaceEvent`` tras el flush.
    """

    model_config = ConfigDict(from_attributes=True)

    race_event_id: int
    climate: Optional[str] = None
    temperature_c: Optional[Decimal] = None
    surface_condition: Optional[SurfaceCondition] = None
    altitude_msnm: Optional[int] = None
    weather_notes: Optional[str] = None
    updated_at: datetime
