"""checks indices updated_at bib_number rename collation

Revision ID: 50a1cdbb25d0
Revises: bb2231fb9f99
Create Date: 2026-05-25 00:06:57.924561

Cambios introducidos por el bloque C2 (db: checks + indices + updated_at +
bib_number + collation + ClubMember rename + race_series FK + relationship
rename):

- CHECK constraints (C4) en athletes, monthly_reports,
  anthropometric_records, race_categories, parental_consents, parent_invites.
- FK explícita race_series.points_scheme_code → race_points_schemes.code (C5).
- Índices (C6): drop ix_race_results_deleted_at; create
  ix_race_results_event_deleted; create ix_session_media_athlete_athlete;
  create ix_event_attendances_athlete; create ix_race_competitors_linked_by_user.
- updated_at en users y clubs (C7).
- ParentAthlete: renombra columna `relationship` → `relationship_type` (C9).
- race_results.bib_number SmallInteger → String(10) (C2).
- race_competitors.normalized_name collation utf8mb4_bin (C10).

Tablas no mapeadas en models (`agent_run_events`, `anonymization_mappings` y
columnas extras de `agent_runs`) se preservan: la autogen las quería borrar
pero el modelo intencionalmente mapea solo un subconjunto. Esta migración
no las toca.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# ---------------------------------------------------------------------------
# Helpers idempotentes: solo aplican el cambio si el estado lo requiere.
# Útil cuando una corrida previa de esta migración avanzó parcialmente.
# ---------------------------------------------------------------------------


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    res = bind.execute(
        sa.text(
            """
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :t
              AND COLUMN_NAME = :c
            """
        ),
        {"t": table, "c": column},
    )
    return res.scalar() > 0


def _index_exists(table: str, index: str) -> bool:
    bind = op.get_bind()
    res = bind.execute(
        sa.text(
            """
            SELECT COUNT(*) FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :t
              AND INDEX_NAME = :i
            """
        ),
        {"t": table, "i": index},
    )
    return res.scalar() > 0


def _constraint_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    res = bind.execute(
        sa.text(
            """
            SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :t
              AND CONSTRAINT_NAME = :n
            """
        ),
        {"t": table, "n": name},
    )
    return res.scalar() > 0


# revision identifiers, used by Alembic.
revision: str = "50a1cdbb25d0"
down_revision: Union[str, None] = "bb2231fb9f99"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1) Soft-touch columns: updated_at en users y clubs (C7)
    # ------------------------------------------------------------------
    if not _column_exists("users", "updated_at"):
        op.add_column(
            "users",
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
        )
        op.alter_column(
            "users",
            "updated_at",
            server_default=None,
            existing_type=sa.DateTime(),
            existing_nullable=False,
        )

    if not _column_exists("clubs", "updated_at"):
        op.add_column(
            "clubs",
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
        )
        op.alter_column(
            "clubs",
            "updated_at",
            server_default=None,
            existing_type=sa.DateTime(),
            existing_nullable=False,
        )

    # ------------------------------------------------------------------
    # 2) ParentAthlete: rename columna `relationship` → `relationship_type` (C9)
    # ------------------------------------------------------------------
    if _column_exists("parent_athlete", "relationship") and not _column_exists(
        "parent_athlete", "relationship_type"
    ):
        op.alter_column(
            "parent_athlete",
            "relationship",
            new_column_name="relationship_type",
            existing_type=mysql.ENUM("padre", "madre", "acudiente"),
            existing_nullable=False,
        )

    # ------------------------------------------------------------------
    # 3) race_results.bib_number SmallInteger → String(10) (C2)
    # ------------------------------------------------------------------
    bind = op.get_bind()
    bib_type = bind.execute(
        sa.text(
            """
            SELECT DATA_TYPE FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'race_results'
              AND COLUMN_NAME = 'bib_number'
            """
        )
    ).scalar()
    if bib_type and bib_type.lower() != "varchar":
        op.alter_column(
            "race_results",
            "bib_number",
            existing_type=mysql.SMALLINT(),
            type_=sa.String(length=10),
            existing_nullable=True,
        )

    # ------------------------------------------------------------------
    # 4) Índices C6 (idempotente: solo crea/drop si necesario)
    # ------------------------------------------------------------------
    if _index_exists("race_results", "ix_race_results_deleted_at"):
        op.drop_index("ix_race_results_deleted_at", table_name="race_results")
    if not _index_exists("race_results", "ix_race_results_event_deleted"):
        op.create_index(
            "ix_race_results_event_deleted",
            "race_results",
            ["event_id", "deleted_at"],
            unique=False,
        )

    if not _index_exists(
        "session_media_athlete", "ix_session_media_athlete_athlete"
    ):
        op.create_index(
            "ix_session_media_athlete_athlete",
            "session_media_athlete",
            ["athlete_id"],
            unique=False,
        )

    if not _index_exists("event_attendances", "ix_event_attendances_athlete"):
        op.create_index(
            "ix_event_attendances_athlete",
            "event_attendances",
            ["athlete_id"],
            unique=False,
        )

    if not _index_exists(
        "race_competitors", "ix_race_competitors_linked_by_user"
    ):
        op.create_index(
            "ix_race_competitors_linked_by_user",
            "race_competitors",
            ["linked_by_user_id"],
            unique=False,
        )

    # ------------------------------------------------------------------
    # 5) FK race_series.points_scheme_code → race_points_schemes.code (C5)
    # ------------------------------------------------------------------
    if not _constraint_exists("race_series", "fk_race_series_points_scheme_code"):
        op.create_foreign_key(
            "fk_race_series_points_scheme_code",
            "race_series",
            "race_points_schemes",
            ["points_scheme_code"],
            ["code"],
            onupdate="CASCADE",
            ondelete="RESTRICT",
        )

    # ------------------------------------------------------------------
    # 6) Collation race_competitors.normalized_name → utf8mb4_bin (C10)
    #
    # Hay un UNIQUE sobre normalized_name. MySQL no permite cambiar collation
    # con el índice en su lugar: dropeamos primero, alteramos, recreamos.
    # Verificamos collation actual para no aplicar dos veces.
    # ------------------------------------------------------------------
    bind = op.get_bind()
    current_collation = bind.execute(
        sa.text(
            """
            SELECT COLLATION_NAME FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'race_competitors'
              AND COLUMN_NAME = 'normalized_name'
            """
        )
    ).scalar()
    if current_collation != "utf8mb4_bin":
        if _constraint_exists(
            "race_competitors", "uq_race_competitors_normalized_name"
        ):
            op.drop_constraint(
                "uq_race_competitors_normalized_name",
                "race_competitors",
                type_="unique",
            )
        op.execute(
            "ALTER TABLE race_competitors "
            "MODIFY COLUMN normalized_name VARCHAR(160) "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL"
        )
        if not _constraint_exists(
            "race_competitors", "uq_race_competitors_normalized_name"
        ):
            op.create_unique_constraint(
                "uq_race_competitors_normalized_name",
                "race_competitors",
                ["normalized_name"],
            )

    # ------------------------------------------------------------------
    # 7) CHECK constraints (C4) — idempotente
    # ------------------------------------------------------------------
    _checks = [
        (
            "athletes",
            "ck_athletes_consent_obtained_date_consistent",
            "(parental_consent_obtained = 0 AND parental_consent_date IS NULL) "
            "OR (parental_consent_obtained = 1 AND parental_consent_date IS NOT NULL)",
        ),
        # MySQL no permite CURRENT_DATE en CHECK (no determinista).
        # Limitamos a rango plausible; validar "no futuro absoluto" en Pydantic.
        (
            "athletes",
            "ck_athletes_birth_date_range",
            "birth_date BETWEEN '1900-01-01' AND '2100-12-31'",
        ),
        ("monthly_reports", "ck_monthly_report_month_range", "month BETWEEN 1 AND 12"),
        (
            "monthly_reports",
            "ck_monthly_report_year_range",
            "year BETWEEN 2000 AND 2100",
        ),
        (
            "anthropometric_records",
            "ck_anthro_evaluation_date_range",
            "evaluation_date BETWEEN '1900-01-01' AND '2100-12-31'",
        ),
        (
            "anthropometric_records",
            "ck_anthro_weight_range",
            "weight_kg BETWEEN 10 AND 200",
        ),
        (
            "anthropometric_records",
            "ck_anthro_standing_height_range",
            "standing_height_cm BETWEEN 80 AND 230",
        ),
        (
            "race_categories",
            "ck_race_categories_age_max_gte_min",
            "age_max IS NULL OR age_min IS NULL OR age_max >= age_min",
        ),
        (
            "parental_consents",
            "ck_parental_consents_withdrawn_after_consent",
            "withdrawn_at IS NULL OR withdrawn_at >= consented_at",
        ),
        (
            "parent_invites",
            "ck_parent_invites_expires_after_created",
            "expires_at > created_at",
        ),
    ]
    for table, name, cond in _checks:
        if not _constraint_exists(table, name):
            op.create_check_constraint(name, table, cond)


def downgrade() -> None:
    # CHECK constraints (idempotente)
    _check_names = [
        ("parent_invites", "ck_parent_invites_expires_after_created"),
        ("parental_consents", "ck_parental_consents_withdrawn_after_consent"),
        ("race_categories", "ck_race_categories_age_max_gte_min"),
        ("anthropometric_records", "ck_anthro_standing_height_range"),
        ("anthropometric_records", "ck_anthro_weight_range"),
        ("anthropometric_records", "ck_anthro_evaluation_date_range"),
        ("monthly_reports", "ck_monthly_report_year_range"),
        ("monthly_reports", "ck_monthly_report_month_range"),
        ("athletes", "ck_athletes_birth_date_range"),
        ("athletes", "ck_athletes_consent_obtained_date_consistent"),
    ]
    for table, name in _check_names:
        if _constraint_exists(table, name):
            op.drop_constraint(name, table, type_="check")

    # Collation race_competitors.normalized_name → default
    bind = op.get_bind()
    current_collation = bind.execute(
        sa.text(
            """
            SELECT COLLATION_NAME FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'race_competitors'
              AND COLUMN_NAME = 'normalized_name'
            """
        )
    ).scalar()
    if current_collation == "utf8mb4_bin":
        if _constraint_exists(
            "race_competitors", "uq_race_competitors_normalized_name"
        ):
            op.drop_constraint(
                "uq_race_competitors_normalized_name",
                "race_competitors",
                type_="unique",
            )
        op.execute(
            "ALTER TABLE race_competitors "
            "MODIFY COLUMN normalized_name VARCHAR(160) "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL"
        )
        op.create_unique_constraint(
            "uq_race_competitors_normalized_name",
            "race_competitors",
            ["normalized_name"],
        )

    # FK race_series.points_scheme_code
    if _constraint_exists("race_series", "fk_race_series_points_scheme_code"):
        op.drop_constraint(
            "fk_race_series_points_scheme_code", "race_series", type_="foreignkey"
        )

    # Indices
    # NOTA: el índice ix_race_competitors_linked_by_user no se dropea: MySQL
    # lo necesita para sostener la FK fk_race_competitors_linked_by_user_id.
    # Dejarlo en su lugar es seguro (es solo un índice secundario más).
    # NOTA: ix_event_attendances_athlete tampoco se dropea — MySQL lo
    # necesita para la FK event_attendances.athlete_id → athletes.id.
    # NOTA: ix_session_media_athlete_athlete tampoco se dropea — MySQL lo
    # necesita para la FK session_media_athlete.athlete_id → athletes.id.
    if _index_exists("race_results", "ix_race_results_event_deleted"):
        op.drop_index("ix_race_results_event_deleted", table_name="race_results")
    if not _index_exists("race_results", "ix_race_results_deleted_at"):
        op.create_index(
            "ix_race_results_deleted_at",
            "race_results",
            ["deleted_at"],
            unique=False,
        )

    # bib_number → SmallInteger (los strings se intentan castear; si el
    # dataset tiene alfanuméricos, este downgrade fallaría — debe ejecutarse
    # con cuidado en data real). Para datasets numéricos típicos (Válida IV)
    # el cast es seguro.
    bib_type = bind.execute(
        sa.text(
            """
            SELECT DATA_TYPE FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'race_results'
              AND COLUMN_NAME = 'bib_number'
            """
        )
    ).scalar()
    if bib_type and bib_type.lower() == "varchar":
        op.alter_column(
            "race_results",
            "bib_number",
            existing_type=sa.String(length=10),
            type_=mysql.SMALLINT(),
            existing_nullable=True,
        )

    # ParentAthlete rename inverso
    if _column_exists("parent_athlete", "relationship_type") and not _column_exists(
        "parent_athlete", "relationship"
    ):
        op.alter_column(
            "parent_athlete",
            "relationship_type",
            new_column_name="relationship",
            existing_type=mysql.ENUM("padre", "madre", "acudiente"),
            existing_nullable=False,
        )

    # updated_at columns
    if _column_exists("clubs", "updated_at"):
        op.drop_column("clubs", "updated_at")
    if _column_exists("users", "updated_at"):
        op.drop_column("users", "updated_at")
