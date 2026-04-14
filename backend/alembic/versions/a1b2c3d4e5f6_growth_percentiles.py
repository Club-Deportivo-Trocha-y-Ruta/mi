"""growth_percentiles: tabla growth_reference_lms y campos percentiles en anthropometric_records

Revision ID: a1b2c3d4e5f6
Revises: 3a1f8c9d4e72
Create Date: 2026-04-14 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "3a1f8c9d4e72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Crear tabla growth_reference_lms
    # ------------------------------------------------------------------
    op.create_table(
        "growth_reference_lms",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "source",
            sa.Enum("WHO", "CDC", name="growthsource"),
            nullable=False,
        ),
        sa.Column(
            "indicator",
            sa.Enum(
                "height_for_age",
                "weight_for_age",
                "bmi_for_age",
                name="growthindicator",
            ),
            nullable=False,
        ),
        sa.Column(
            "sex",
            sa.Enum("M", "F", name="sex_enum"),
            nullable=False,
        ),
        sa.Column("age_months", sa.DECIMAL(5, 1), nullable=False),
        sa.Column("L", sa.DECIMAL(15, 12), nullable=False),
        sa.Column("M", sa.DECIMAL(10, 6), nullable=False),
        sa.Column("S", sa.DECIMAL(15, 12), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source", "indicator", "sex", "age_months",
            name="uq_lms_source_indicator_sex_age",
        ),
    )
    op.create_index(
        "ix_lms_source_indicator_sex",
        "growth_reference_lms",
        ["source", "indicator", "sex"],
    )

    # ------------------------------------------------------------------
    # 2. Agregar columnas de percentiles a anthropometric_records
    # ------------------------------------------------------------------
    op.add_column(
        "anthropometric_records",
        sa.Column("height_z_score", sa.DECIMAL(6, 3), nullable=True),
    )
    op.add_column(
        "anthropometric_records",
        sa.Column("height_percentile", sa.DECIMAL(5, 1), nullable=True),
    )
    op.add_column(
        "anthropometric_records",
        sa.Column("bmi", sa.DECIMAL(5, 2), nullable=True),
    )
    op.add_column(
        "anthropometric_records",
        sa.Column("bmi_z_score", sa.DECIMAL(6, 3), nullable=True),
    )
    op.add_column(
        "anthropometric_records",
        sa.Column("bmi_percentile", sa.DECIMAL(5, 1), nullable=True),
    )
    op.add_column(
        "anthropometric_records",
        sa.Column("weight_z_score", sa.DECIMAL(6, 3), nullable=True),
    )
    op.add_column(
        "anthropometric_records",
        sa.Column("weight_percentile", sa.DECIMAL(5, 1), nullable=True),
    )
    op.add_column(
        "anthropometric_records",
        sa.Column(
            "nutritional_status",
            sa.Enum(
                "retraso_talla",
                "riesgo_retraso_talla",
                "talla_adecuada",
                "talla_alta",
                "delgadez_severa",
                "delgadez",
                "adecuado",
                "sobrepeso",
                "obesidad",
                name="nutritionalstatus",
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Eliminar columnas de percentiles de anthropometric_records
    # ------------------------------------------------------------------
    op.drop_column("anthropometric_records", "nutritional_status")
    op.drop_column("anthropometric_records", "weight_percentile")
    op.drop_column("anthropometric_records", "weight_z_score")
    op.drop_column("anthropometric_records", "bmi_percentile")
    op.drop_column("anthropometric_records", "bmi_z_score")
    op.drop_column("anthropometric_records", "bmi")
    op.drop_column("anthropometric_records", "height_percentile")
    op.drop_column("anthropometric_records", "height_z_score")

    # ------------------------------------------------------------------
    # 2. Eliminar tabla growth_reference_lms
    # ------------------------------------------------------------------
    op.drop_index("ix_lms_source_indicator_sex", table_name="growth_reference_lms")
    op.drop_table("growth_reference_lms")
