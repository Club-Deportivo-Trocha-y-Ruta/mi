"""merge ClubRole into UserRole

Revision ID: ba90896dc9aa
Revises: 50a1cdbb25d0
Create Date: 2026-05-25 00:24:21.410571

Fusiona el enum `ClubRole` en `UserRole` (C8). Los valores son idénticos
(admin/coach/parent/athlete) — la migración solo actualiza el nombre del
tipo enum subyacente en la columna `club_members.role_in_club`.

A nivel Python, `ClubRole` queda como alias de `UserRole` en
``app/models/club.py``.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ba90896dc9aa"
down_revision: Union[str, None] = "50a1cdbb25d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Los valores del enum no cambian; solo el nombre del tipo enum. MySQL
# representa enums ENUM('...','...') inline en la columna, así que
# emitimos un MODIFY COLUMN que re-declara los valores; la diferencia
# semántica es solo el nombre `userrole` vs `clubrole` que SQLAlchemy
# usará al reflejar la metadata.
_ENUM_DDL = "ENUM('admin','coach','parent','athlete') NOT NULL"


def upgrade() -> None:
    op.execute(f"ALTER TABLE club_members MODIFY COLUMN role_in_club {_ENUM_DDL}")


def downgrade() -> None:
    # No-op de DDL: el set de valores es idéntico. Mantener un MODIFY
    # explícito para que el upgrade/downgrade sea simétrico en logs.
    op.execute(f"ALTER TABLE club_members MODIFY COLUMN role_in_club {_ENUM_DDL}")
