from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.anthropometry import AnthropometricRecord
    from app.models.athlete import Athlete
    from app.models.user import User


class AthleteAIExplanation(Base):
    """Caché de outputs de IA por (atleta, medición, use case).

    El texto persistido ya está saneado por `Guardrails` y `_scrub` en el
    use case, así que es seguro de leer por cualquier rol con acceso al
    atleta. La cache key incluye `anthropometric_record_id`: cuando se
    crea una medición nueva, el ID cambia y el cache se invalida
    implícitamente sin necesidad de DELETE.
    """

    __tablename__ = "athlete_ai_explanations"
    __table_args__ = (
        UniqueConstraint(
            "athlete_id",
            "anthropometric_record_id",
            "use_case",
            name="uq_ai_expl_athlete_record_usecase",
        ),
        Index("ix_ai_expl_athlete_id", "athlete_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False
    )
    anthropometric_record_id: Mapped[int] = mapped_column(
        ForeignKey("anthropometric_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Discriminador para futuros use cases (training_plan_explainer, etc.)
    use_case: Mapped[str] = mapped_column(
        String(64), nullable=False, default="phv_explainer"
    )

    # Payload — refleja PHVExplanationResponse
    text: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    age_group: Mapped[str] = mapped_column(String(16), nullable=False)
    maturation_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=""
    )

    # --- Trazabilidad (feature 042) — nueve columnas nullable, sin
    # server_default y sin índice nuevo (data-model.md §1: nada consulta
    # todavía por ellas). Todas aditivas; las filas existentes (033) quedan
    # con estas nueve en NULL para siempre.
    #
    # `schema_version` distingue el *formato de la fila*, no el formato del
    # payload interno de `structured_json` (que trae su propio
    # `AnthropometryInsightV1.schema_version`, hoy siempre "v1" — ver
    # data-model.md §0, la nota de colisión de nombres). Nunca vale "v1" en
    # esta columna: una fila con prosa libre (033) se expresa como NULL, no
    # como el string "v1", así que `schema_version IS NOT NULL` es la única
    # comprobación de una sola columna para "¿esta fila es de la feature 042?".
    schema_version: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # `AnthropometryInsightV1.model_dump(mode="json")`. NULL cuando
    # `schema_version` es NULL; siempre poblado cuando `schema_version="v2"`,
    # incluso para filas `critic_verdict="fallback"` (la plantilla
    # determinística también es un `AnthropometryInsightV1` válido).
    structured_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Uno de approved | revised | flagged | fallback | skipped (data-model.md
    # §3). NULL para filas legado. No es el mismo vocabulario que la
    # respuesta cruda del crítico LLM (approve|revise|reject) — el pipeline
    # los convierte según la máquina de estados de §3.
    critic_verdict: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Valor de AI_ANTHRO_PROMPT_VERSION vigente al generar esta fila, para
    # que un rollback posterior de la variable no reetiquete filas viejas.
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Suma de tokens de entrada/salida entre la llamada del analista y,
    # cuando corrió, la del crítico.
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Seis decimales, igual que el redondeo de compute_cost_usd. Suma
    # analista + crítico.
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    # Tiempo de reloj del pipeline completo (contexto → persistencia), no
    # solo las llamadas al LLM.
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Trace id determinístico de Langfuse. NULL siempre que
    # LANGFUSE_ENABLED=false (el caso siempre-verdadero en producción) — por
    # diseño, no un bug a corregir.
    langfuse_trace_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )

    # Auditoría: ¿quién pidió la generación?
    generated_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    athlete: Mapped[Athlete] = relationship(
        "Athlete",
        foreign_keys="[AthleteAIExplanation.athlete_id]",
    )
    record: Mapped[AnthropometricRecord] = relationship(
        "AnthropometricRecord",
        foreign_keys="[AthleteAIExplanation.anthropometric_record_id]",
    )
    generated_by: Mapped[User] = relationship(
        "User",
        foreign_keys="[AthleteAIExplanation.generated_by_user_id]",
    )
