"""Modelo SQLAlchemy para ``athlete_ai_insights`` (insights agénticos
aprobados por el coach + histórico versionado).

Tabla creada en migración ``7a8b9c0d1e2f_race_agentic_module_tables.py``.
La migración BE-1 ``8c1d2e3f4a5b`` agrega:

- ``deprecated_at`` (DATETIME NULL): timestamp de deprecación. ``NULL``
  significa "vigente" (puede o no estar activo según ``is_active``).
- ``superseded_by_insight_id`` (INT NULL, FK self ON DELETE SET NULL):
  apunta al insight que reemplazó a éste. Permite reconstruir cadenas
  de versionado.
- ``is_active`` (SMALLINT NULL, sentinel): ``1`` = activo (publicable),
  ``NULL`` = no activo. Junto con el UNIQUE
  ``uq_insights_active_terna`` emula UNIQUE PARCIAL "solo UN activo por
  (athlete_id, season, valida_num)" — ver docstring de la migración.

Reglas de negocio (referidas por BE-2 / persist_insight node):
- Al insertar un insight aprobado nuevo para una terna que ya tiene uno
  activo: el viejo se marca con ``deprecated_at=now()``,
  ``superseded_by_insight_id=<new.id>``, ``is_active=NULL``; el nuevo
  queda con ``is_active=1``.
- ``valida_num=0`` se reserva para use_cases agregados a nivel temporada
  (ej. ``season_summary``). ``NULL`` significa "no aplica" (analíticas
  multi-temporada futuras).
- ``archived_at`` (preexistente) y ``deprecated_at`` (nuevo) son
  ortogonales: archived = lo borró el coach; deprecated = lo reemplazó
  otro insight.

Feature 036 (US4, T020) agrega:

- ``is_fallback`` (BOOLEAN NOT NULL, server_default FALSE): ``True`` ⇔
  la fila la escribió el *failure path* de
  ``services/race/ai/fallback.py`` (``deterministic_fallback``) porque
  el analyst LLM falló. El fallback N=1 (``deterministic_fallback_n1``)
  es un análisis legítimo bajo la regla N=1 y NUNCA marca esta columna.
  No es un campo derivado del contenido (no se infiere del markdown):
  lo asigna ``persist_insight`` a partir del discriminador expuesto por
  ``fallback.py``. Migración ``463c1f0ccb38`` agrega la columna y
  reclasifica filas históricas por texto exacto (backfill único).

Feature 037 (AI Insights v3 — causal, field-relative, prescriptive),
migración ``d1e2f3a4b5c6`` agrega:

- ``structured_json`` (JSON NULL): ``InsightV3.model_dump()`` (ver
  ``app/services/race/insight_v3.py``, T201). ``None`` para insights
  v1/v2 — el router sigue leyendo ``summary_text``/``recommendations_json``
  para esos.
- ``coach_answer_text`` (VARCHAR(1000) NULL): respuesta del coach a
  ``structured_json["coach_question"]``, escrubeada (nombres prohibidos
  del club) antes de persistir por
  ``routers/athlete_race_analysis.py::answer_insight``.
- ``coach_answer_at`` (DATETIME NULL): timestamp de la respuesta.
- ``coach_rating`` (SMALLINT NULL): ``1`` = útil, ``-1`` = no útil.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun
    from app.models.athlete import Athlete
    from app.models.race_competitor import RaceCompetitor
    from app.models.race_event import RaceEvent
    from app.models.user import User


class InsightConfidence(str, enum.Enum):
    """Nivel de confianza del insight (impacta cómo el UI lo presenta).

    Debe permanecer alineado con el enum DB ``insightconfidence`` creado
    en la migración ``7a8b9c0d1e2f``.
    """

    low = "low"
    medium = "medium"
    high = "high"


class AthleteAiInsight(Base):
    """Insight agéntico publicable sobre un atleta (con versionado BE-1).

    Un insight nace de un ``AgentRun`` y, una vez aprobado por el coach
    (``coach_approved=True``), puede mostrarse al atleta/padre. Las
    columnas de versionado (``deprecated_at``, ``superseded_by_insight_id``,
    ``is_active``) permiten mantener un histórico inmutable de qué se
    publicó cuándo, sin perder la capacidad de filtrar "solo el más
    reciente activo por terna".
    """

    __tablename__ = "athlete_ai_insights"
    __table_args__ = (
        CheckConstraint(
            "coach_edits_count >= 0",
            name="ck_insights_coach_edits_count_nonneg",
        ),
        # Versión relax (>= 0) — ver migración BE-1 ``8c1d2e3f4a5b``.
        # valida_num=0 reservado para use_cases agregados (season_summary).
        CheckConstraint(
            "valida_num IS NULL OR valida_num >= 0",
            name="ck_insights_valida_num_nonneg",
        ),
        # UNIQUE parcial emulado con sentinel NULL. Ver docstring migración.
        UniqueConstraint(
            "athlete_id",
            "season",
            "valida_num",
            "is_active",
            name="uq_insights_active_terna",
        ),
        Index(
            "ix_insights_athlete_season",
            "athlete_id",
            "season",
            "valida_num",
        ),
        Index("ix_insights_event", "event_id"),
        Index("ix_insights_use_case", "use_case", "generated_at"),
        Index("ix_insights_deprecated_at", "deprecated_at"),
    )

    # --- Identidad ---------------------------------------------------------
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- Foreign keys ------------------------------------------------------
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False
    )
    competitor_id: Mapped[int | None] = mapped_column(
        ForeignKey("race_competitors.id", ondelete="SET NULL"), nullable=True
    )
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("race_events.id", ondelete="SET NULL"), nullable=True
    )
    agent_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    generated_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # FK self (BE-1) para versionado.
    superseded_by_insight_id: Mapped[int | None] = mapped_column(
        ForeignKey("athlete_ai_insights.id", ondelete="SET NULL"),
        nullable=True,
    )

    # --- Contexto temporal -------------------------------------------------
    season: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    valida_num: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    # --- Contenido publicable ---------------------------------------------
    use_case: Mapped[str] = mapped_column(String(32), nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    recommendations_json: Mapped[list | dict] = mapped_column(JSON, nullable=False)
    metrics_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    principles_cited_json: Mapped[list | dict] = mapped_column(JSON, nullable=False)
    confidence: Mapped[InsightConfidence] = mapped_column(
        Enum(
            InsightConfidence,
            name="insightconfidence",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=InsightConfidence.medium,
    )
    # Feature 036 (US4): True ⇔ escrita por el failure path de
    # fallback.py (deterministic_fallback). NO cubre deterministic_fallback_n1
    # (análisis legítimo bajo la regla N=1). Bloquea el adjunto a boletines
    # (ver routers/athlete_monthly_newsletters.py:attach_insights).
    is_fallback: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    # --- Trazabilidad del modelo ------------------------------------------
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)

    # --- Flujo coach -------------------------------------------------------
    coach_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    coach_edits_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # --- Versionado BE-1 ---------------------------------------------------
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Sentinel: 1 = activo, NULL = no activo. Ver docstring de tabla.
    is_active: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    # Task #7: bandera idempotente del job de retención (180d post deprecated_at).
    # NULL = aún no scrubeado; NOT NULL = timestamp en que el job redactó PII.
    pii_scrubbed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # --- Feature 037: estructura v3 + diálogo coach -------------------------
    # ``InsightV3.model_dump()`` cuando el insight se generó con el prompt
    # v3 (analysis_kind valida|season). None para insights v1/v2.
    structured_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Respuesta del coach a ``structured_json["coach_question"]``. Escrita
    # ya escrubeada (nombres prohibidos del club, ``load_forbidden_names``)
    # por ``routers/athlete_race_analysis.py::answer_insight`` — nunca
    # texto crudo del coach.
    coach_answer_text: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    coach_answer_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 1 = útil, -1 = no útil. None = sin calificar.
    coach_rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    # --- Timestamps --------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # --- Relaciones --------------------------------------------------------
    athlete: Mapped["Athlete"] = relationship(
        "Athlete",
        back_populates="ai_insights",
        foreign_keys="[AthleteAiInsight.athlete_id]",
    )
    competitor: Mapped["RaceCompetitor | None"] = relationship(
        "RaceCompetitor",
        foreign_keys="[AthleteAiInsight.competitor_id]",
    )
    event: Mapped["RaceEvent | None"] = relationship(
        "RaceEvent",
        foreign_keys="[AthleteAiInsight.event_id]",
    )
    agent_run: Mapped["AgentRun | None"] = relationship(
        "AgentRun",
        back_populates="insights",
        foreign_keys="[AthleteAiInsight.agent_run_id]",
    )
    generated_by: Mapped["User"] = relationship(
        "User",
        foreign_keys="[AthleteAiInsight.generated_by_user_id]",
    )
    superseded_by: Mapped["AthleteAiInsight | None"] = relationship(
        "AthleteAiInsight",
        foreign_keys="[AthleteAiInsight.superseded_by_insight_id]",
        remote_side="AthleteAiInsight.id",
    )
