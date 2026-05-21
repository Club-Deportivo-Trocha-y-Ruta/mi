"""Pydantic v2 schemas para los endpoints `/api/race-analysis/imports/*`.

Cubre los DTOs del wizard upload UI (F-UP3, docs/10-race-results/upload-design.md §4):

- ``ImportParseResponse``    — output del paso 1 (parse).
- ``ImportDryRunResponse``   — output del paso 2 (dry-run preview).
- ``ImportCommitRequest``    — body del paso 3 (commit con resolved matches).
- ``ImportCommitResponse``   — output del paso 3 (post-ingest).
- ``ImportListResponse``     — output del histórico GET /.

Convenciones:
- Pydantic v2 (``model_config``, ``ConfigDict``).
- Ningún campo contiene datos PII de menores: matches usan
  ``competitor_normalized_name`` (slug normalizado) + ``athlete_id`` opcional.
- Nombres reales SÍ aparecen en ``MatchPreview.competitor_name`` (display) —
  estos son de PDFs ya públicos por la Federación, no datos privados de TyR.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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
    """Respuesta del endpoint POST /imports/parse (F-UP3 §4.1)."""

    model_config = ConfigDict(from_attributes=True)

    parse_id: int  # = RaceImport.id (status='pending')
    sha256: str  # SHA del PDF RESULTADOS (64 hex chars)
    header: ParseHeaderInfo
    n_rows_resultados: int
    n_rows_general: Optional[int] = None
    warnings: list[ParseWarning] = Field(default_factory=list)


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
    """Body del endpoint POST /imports/{parse_id}/commit (F-UP3 §4.3)."""

    model_config = ConfigDict(from_attributes=True)

    resolved_matches: list[ResolvedMatch] = Field(default_factory=list)


class ImportCommitResponse(BaseModel):
    """Respuesta del endpoint POST /imports/{parse_id}/commit (F-UP3 §4.3)."""

    model_config = ConfigDict(from_attributes=True)

    parse_id: int
    race_event_id: int
    n_results_inserted: int
    n_competitors_created: int
    n_competitors_linked: int


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
