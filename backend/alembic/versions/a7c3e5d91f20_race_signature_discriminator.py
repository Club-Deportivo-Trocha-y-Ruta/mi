"""race_signature_discriminator — homónimos con la misma terna (feature 044)

Revision ID: a7c3e5d91f20
Revises: 8efe1618cb83
Create Date: 2026-09-21

Decisión del dueño (2026-09-21, "separar por categoría"): dos personas
distintas con el mismo nombre, club y ciudad — el caso realista es padre e
hijo del mismo club — no pueden colapsar en un solo competidor. Hasta esta
revisión la terna ``(normalized_name, club_norm, city_norm)`` era UNIQUE, así
que era imposible representarlas por separado.

``race_competitor_signatures`` gana ``discriminator VARCHAR(32) NOT NULL
DEFAULT ''`` y el UNIQUE pasa a la cuaterna. ``''`` es el valor de toda firma
que no necesita desempate (el caso normal); solo una decisión
``different_people`` de la revisión de identidad escribe un discriminador no
vacío, derivado de la categoría (regla en ``research.md`` R-06 y en
``app/services/race/identity_resolver.py::category_discriminator``).

``NOT NULL DEFAULT ''`` por la misma razón que ``club_norm``/``city_norm``: en
MySQL dos ``NULL`` son distintos dentro de una clave única y el UNIQUE no
protegería nada.

**Orden.** Primero la columna y el UNIQUE nuevo, después se suelta el viejo:
mientras ambos existen, el nuevo es trivialmente satisfecho (todas las filas
tienen ``''``) y en ningún momento queda la tabla sin protección de
concurrencia.

**Downgrade.** Falla ruidosamente si alguna terna tiene más de una firma
(homónimos ya separados): recrear el UNIQUE de la terna sería imposible. El
mensaje solo cuenta, no nombra a nadie.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3e5d91f20"
down_revision: Union[str, None] = "8efe1618cb83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "race_competitor_signatures"
_OLD_UQ = "uq_race_competitor_signatures_triple"
_NEW_UQ = "uq_race_competitor_signatures_identity"
_TRIPLE = ["normalized_name", "club_norm", "city_norm"]

DUPLICATE_TRIPLES_SQL = """
    SELECT COUNT(*) FROM (
        SELECT normalized_name, club_norm, city_norm
        FROM race_competitor_signatures
        GROUP BY normalized_name, club_norm, city_norm
        HAVING COUNT(*) > 1
    ) AS d
"""


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    column = sa.Column(
        "discriminator",
        sa.String(length=32),
        nullable=False,
        server_default=sa.text("''"),
    )
    if dialect == "sqlite":
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.add_column(column)
            batch_op.create_unique_constraint(_NEW_UQ, [*_TRIPLE, "discriminator"])
            batch_op.drop_constraint(_OLD_UQ, type_="unique")
        return
    op.add_column(_TABLE, column)
    op.create_unique_constraint(_NEW_UQ, _TABLE, [*_TRIPLE, "discriminator"])
    op.drop_constraint(_OLD_UQ, _TABLE, type_="unique")


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    duplicates = bind.execute(sa.text(DUPLICATE_TRIPLES_SQL)).scalar() or 0
    if duplicates:
        raise RuntimeError(
            f"No se puede revertir a7c3e5d91f20: hay {duplicates} terna(s) "
            "(nombre, club, ciudad) con más de una firma — homónimos que la "
            "revisión de identidad separó por categoría — y el downgrade tiene "
            f"que restituir {_OLD_UQ} (UNIQUE sobre la terna).\n"
            "Qué hacer antes de reintentar:\n"
            "  1. Listar los grupos: SELECT normalized_name, club_norm, "
            "city_norm, COUNT(*) FROM race_competitor_signatures GROUP BY "
            "normalized_name, club_norm, city_norm HAVING COUNT(*) > 1;\n"
            "  2. No hay forma de revertir sin perder la separación de esas "
            "personas: restaurar desde backup.\n"
            "  3. Reintentar el downgrade con cero duplicados."
        )
    if dialect == "sqlite":
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.create_unique_constraint(_OLD_UQ, _TRIPLE)
            batch_op.drop_constraint(_NEW_UQ, type_="unique")
            batch_op.drop_column("discriminator")
        return
    op.create_unique_constraint(_OLD_UQ, _TABLE, _TRIPLE)
    op.drop_constraint(_NEW_UQ, _TABLE, type_="unique")
    op.drop_column(_TABLE, "discriminator")
