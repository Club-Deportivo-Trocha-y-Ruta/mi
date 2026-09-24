"""race_import_discarded — ``race_imports.status`` gana ``discarded`` (feature 045, T024)

Revision ID: a76c264449a5
Revises: b4e8d2f61a93
Create Date: 2026-09-23

Hasta hoy una carga (``race_imports``) que el coach abandona en el wizard
quedaba ``pending``/``dry_run`` hasta que la limpieza nocturna la barría, y una
carga que ya no se quiere no tenía un estado propio: reusar ``failed`` la
mostraría como un error en el buzón (research R-09). ``discarded`` es el estado
que fija ``POST /api/race-analysis/imports/{id}/discard``, solo desde
``pending`` o ``dry_run``.

**MySQL.** ``status`` es un ENUM nativo: agregar el valor al final exige
``MODIFY COLUMN`` (mismo patrón que ``a1b2c3d4e5fa`` con ``'outdated'``). Añadir
un miembro al final de la lista no reordena los valores existentes, así que no
reescribe filas. **SQLite** (tests): la columna es VARCHAR sin CHECK — el
modelo declara el ``Enum`` sin ``create_constraint`` —, no hace falta acción.

**Downgrade.** Antes de quitar el valor las filas ``discarded`` pasan a
``failed`` (una carga descartada es, para la versión anterior, una que no
prosperó); si no, el ``MODIFY`` fallaría en modo estricto. Solo cuenta filas, no
nombra a nadie.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a76c264449a5"
down_revision: Union[str, None] = "b4e8d2f61a93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "race_imports"
STATUS_VALUES_WITHOUT_DISCARDED = ("pending", "dry_run", "committed", "failed")
STATUS_VALUES_WITH_DISCARDED = (*STATUS_VALUES_WITHOUT_DISCARDED, "discarded")


def _enum_sql(values: Sequence[str]) -> str:
    return "ENUM(" + ",".join(f"'{v}'" for v in values) + ")"


def _is_mysql() -> bool:
    return op.get_bind().dialect.name in ("mysql", "mariadb")


def upgrade() -> None:
    if _is_mysql():
        op.execute(
            f"ALTER TABLE {_TABLE} "
            f"MODIFY COLUMN status {_enum_sql(STATUS_VALUES_WITH_DISCARDED)} NOT NULL"
        )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(f"UPDATE {_TABLE} SET status = 'failed' WHERE status = 'discarded'")
    )
    if _is_mysql():
        op.execute(
            f"ALTER TABLE {_TABLE} "
            f"MODIFY COLUMN status {_enum_sql(STATUS_VALUES_WITHOUT_DISCARDED)} NOT NULL"
        )
