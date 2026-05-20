"""Pydantic v2 schemas para el módulo de resultados Copa Valle XCO.

Cubre los DTOs que cruzan la frontera servicio/CLI:
- ``EventMeta``    — metadata de evento capturada por el CLI (incluye condiciones
  no presentes en el PDF: clima, temperatura, superficie, altitud, notas).
- ``MatchDecision``— una decisión del coach: ``athlete_id`` confirmado o ``None``
  para "skip" / "new".
- ``IngestReport`` — resumen post-transacción de la ingesta de una válida.

Convenciones:
- Pydantic v2 (``model_config``, ``field_validator``).
- Ningún campo con dato sensible de menor — los warnings usan ``bib`` + ``code``.
- ``temperature_c`` es ``Decimal`` (decimal precision; consistente con
  ``RaceEvent.temperature_c`` que es ``Numeric(4,1)``).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.race_event import SurfaceCondition


# ---------------------------------------------------------------------------
# EventMeta — captura interactiva del CLI
# ---------------------------------------------------------------------------


class EventMeta(BaseModel):
    """Metadata de un evento (válida) para upsert en ``race_events``.

    Los campos derivados del PDF (``valida_num``, ``name``, ``event_date``,
    ``location``) los rellena el parser; el resto los rellena el CLI vía
    prompts al coach (workflow §6.2 paso 3).

    Validaciones:
    - ``valida_num`` ∈ [1..7] ∪ {99} (99 = Campeonato Departamental).
    - ``season`` ∈ [2020..2100] — rango defensivo razonable.
    - ``temperature_c`` ∈ [-10, 50] °C cuando se provee.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    season: int = Field(ge=2020, le=2100)
    copa_code: str = Field(default="copa_valle", max_length=40)
    valida_num: int = Field(ge=1, le=99)
    name: str = Field(max_length=200)
    event_date: date
    location: str = Field(max_length=150)
    climate: Optional[str] = Field(default=None, max_length=60)
    temperature_c: Optional[Decimal] = None
    surface_condition: Optional[SurfaceCondition] = None
    altitude_msnm: Optional[int] = Field(default=None, ge=0, le=6000)
    weather_notes: Optional[str] = None
    pdf_results_filename: Optional[str] = Field(default=None, max_length=255)
    pdf_general_filename: Optional[str] = Field(default=None, max_length=255)

    @field_validator("valida_num")
    @classmethod
    def _check_valida_num(cls, v: int) -> int:
        # Válidas regulares 1..7, CD = 99. Ningún otro valor admitido.
        if v == 99 or 1 <= v <= 7:
            return v
        raise ValueError(
            f"valida_num inválido: {v}. Debe ser 1..7 (regulares) o 99 (CD)."
        )

    @field_validator("temperature_c")
    @classmethod
    def _check_temp(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is None:
            return v
        if v < Decimal("-10") or v > Decimal("50"):
            raise ValueError(
                f"temperature_c fuera de rango razonable [-10, 50]: {v}"
            )
        return v


# ---------------------------------------------------------------------------
# MatchDecision — confirmación del coach
# ---------------------------------------------------------------------------


class MatchDecision(BaseModel):
    """Decisión del coach sobre un competidor TyR detectado por el ingestor.

    El flujo CLI muestra top-3 candidatos y el coach responde uno de:
    - ``"1"``/``"2"``/``"3"`` → confirmar match con candidato.athlete_id.
    - ``"skip"``             → no linkear (competidor queda con athlete_id=NULL).
    - ``"new"``              → atleta no existe en DB; queda en NULL pendiente de creación posterior.

    El ingestor mapea estas decisiones a ``athlete_id: Optional[int]``.
    """

    bib: str = Field(min_length=1, max_length=10)
    athlete_id: Optional[int] = None
    reason: str = Field(max_length=40)  # "coach_confirmed", "skipped", "new_athlete"

    @field_validator("reason")
    @classmethod
    def _check_reason(cls, v: str) -> str:
        allowed = {"coach_confirmed", "skipped", "new_athlete"}
        if v not in allowed:
            raise ValueError(f"reason inválido: {v!r}. Debe ser uno de {sorted(allowed)}")
        return v


# ---------------------------------------------------------------------------
# IngestReport — resumen post-ingest
# ---------------------------------------------------------------------------


class IngestReport(BaseModel):
    """Resumen de la ingesta de una válida (output de ``RaceIngestor.ingest_event``).

    No incluye nombres completos — los warnings usan ``bib`` + ``category_code``
    para preservar privacidad de menores (CLAUDE.md restricciones inviolables).

    Semántica de contadores:
    - ``results_inserted``: filas nuevas escritas en ``race_results``.
    - ``results_skipped``: filas ignoradas por colisión con UNIQUE
      ``(event_id, category_id, competitor_id)`` o por ingesta idempotente
      previa (mismo sha256 ya ``committed``).
    - ``competitors_created`` / ``competitors_updated``: efectos sobre
      ``race_competitors`` (UPSERT por ``normalized_name``).
    - ``tyr_count``: corredores detectados con ``is_trocha_y_ruta(club) is True``.
    - ``warnings``: lista de strings; **nunca** nombres completos. Ejemplos:
      ``"tiempo anómalo bib=424 cat=INF_A time_ms=273000"``,
      ``"bib=1411 en GENERAL pero no en RESULTADOS"``.
    """

    event_id: int
    series_id: int
    competitors_created: int = 0
    competitors_updated: int = 0
    results_inserted: int = 0
    results_skipped: int = 0
    tyr_count: int = 0
    warnings: list[str] = Field(default_factory=list)
