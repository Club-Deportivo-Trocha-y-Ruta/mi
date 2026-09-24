"""skinfold_measurements + FUPRECOL LMS enum values (feature 046, T005)

Revision ID: be4595de1ad2
Revises: a76c264449a5
Create Date: 2026-09-23

Body composition by skinfolds — ``specs/046-body-composition-skinfolds/``
(``data-model.md`` §1, §3, §8). Mirrors ``app/models/skinfold_measurement.py``.

1. ``skinfold_measurements`` — one row per ``anthropometric_records`` row that
   has a skinfold set (1:1, UNIQUE on ``anthropometric_record_id``, FK
   ON DELETE CASCADE). Six sites × (``{site}_mm`` NUMERIC(4,1),
   ``{site}_declined`` BOOLEAN NOT NULL default false, ``{site}_readings``
   JSON), sums, Slaughter estimate, protocol/caliper metadata, ``measured_by``
   and the ``ActorTimestampMixin`` columns. INDEX on ``athlete_id``.

2. ``growth_reference_lms`` (MySQL only): the native ENUM columns ``source``
   and ``indicator`` gain ``FUPRECOL`` and the three skinfold indicators
   (appended at the end — existing values keep their ordinal, no row
   rewrite). SQLite (tests) renders both as VARCHAR without CHECK, so nothing
   to alter there. ``anthropometric_records.growth_source`` shares the Python
   enum but is deliberately NOT widened: a record's z-scores are never
   computed from FUPRECOL.

Downgrade: delete ``FUPRECOL`` rows and rows of the three skinfold indicators
first (otherwise the shrinking ``MODIFY`` fails in strict mode), shrink both
enums (MySQL only), then drop the table. Counts rows only; no minor data.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "be4595de1ad2"
down_revision: Union[str, None] = "a76c264449a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "skinfold_measurements"
_LMS = "growth_reference_lms"
_SITES = (
    "triceps",
    "biceps",
    "subscapular",
    "medial_calf",
    "iliac_crest",
    "supraspinale",
)

SOURCE_OLD = ("WHO", "CDC")
SOURCE_NEW = (*SOURCE_OLD, "FUPRECOL")
INDICATOR_OLD = ("height_for_age", "weight_for_age", "bmi_for_age")
SKINFOLD_INDICATORS = (
    "triceps_skinfold_for_age",
    "subscapular_skinfold_for_age",
    "triceps_subscapular_sum_for_age",
)
INDICATOR_NEW = (*INDICATOR_OLD, *SKINFOLD_INDICATORS)


def _is_mysql() -> bool:
    # Same guard as ``op.get_bind().dialect.name``, but also valid in offline
    # (``alembic upgrade --sql``) mode, where there is no bind.
    return op.get_context().dialect.name in ("mysql", "mariadb")


def _alter_lms_enums(
    source_from: Sequence[str],
    source_to: Sequence[str],
    indicator_from: Sequence[str],
    indicator_to: Sequence[str],
) -> None:
    op.alter_column(
        _LMS,
        "source",
        type_=sa.Enum(*source_to, name="growthsource"),
        existing_type=sa.Enum(*source_from, name="growthsource"),
        existing_nullable=False,
    )
    op.alter_column(
        _LMS,
        "indicator",
        type_=sa.Enum(*indicator_to, name="growthindicator"),
        existing_type=sa.Enum(*indicator_from, name="growthindicator"),
        existing_nullable=False,
    )


def upgrade() -> None:
    site_columns: list[sa.Column] = []
    for site in _SITES:
        site_columns.append(sa.Column(f"{site}_mm", sa.Numeric(4, 1), nullable=True))
    for site in _SITES:
        site_columns.append(
            sa.Column(
                f"{site}_declined",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
    for site in _SITES:
        site_columns.append(sa.Column(f"{site}_readings", sa.JSON(), nullable=True))

    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("anthropometric_record_id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        *site_columns,
        sa.Column("sum4_mm", sa.Numeric(5, 1), nullable=True),
        sa.Column("sum6_mm", sa.Numeric(5, 1), nullable=True),
        sa.Column("body_fat_pct", sa.Numeric(4, 1), nullable=True),
        sa.Column("fat_mass_kg", sa.Numeric(5, 2), nullable=True),
        sa.Column("fat_free_mass_kg", sa.Numeric(5, 2), nullable=True),
        sa.Column("equation_version", sa.String(32), nullable=True),
        sa.Column(
            "protocol_version", sa.String(16), nullable=False, server_default="v1"
        ),
        sa.Column(
            "caliper_model",
            sa.String(32),
            nullable=False,
            server_default="slim_guide",
        ),
        sa.Column("measured_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["anthropometric_record_id"],
            ["anthropometric_records.id"],
            name="fk_skinfold_measurements_record",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["athlete_id"], ["athletes.id"], name="fk_skinfold_measurements_athlete"
        ),
        sa.ForeignKeyConstraint(
            ["measured_by"], ["users.id"], name="fk_skinfold_measurements_measured_by"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name="fk_skinfold_measurements_updated_by",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "anthropometric_record_id", name="uq_skinfold_measurements_record"
        ),
    )
    op.create_index("ix_skinfold_measurements_athlete", _TABLE, ["athlete_id"])

    if _is_mysql():
        _alter_lms_enums(SOURCE_OLD, SOURCE_NEW, INDICATOR_OLD, INDICATOR_NEW)


def downgrade() -> None:
    indicator_list = ", ".join(f"'{v}'" for v in SKINFOLD_INDICATORS)
    op.execute(
        f"DELETE FROM {_LMS} WHERE source = 'FUPRECOL' "
        f"OR indicator IN ({indicator_list})"
    )
    if _is_mysql():
        _alter_lms_enums(SOURCE_NEW, SOURCE_OLD, INDICATOR_NEW, INDICATOR_OLD)

    # DROP TABLE takes its indexes with it; dropping the athlete index first
    # could fail on MySQL if the FK were relying on it.
    op.drop_table(_TABLE)
