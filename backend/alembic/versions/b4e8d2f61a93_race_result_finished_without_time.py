"""race_result_finished_without_time — clasificado sin tiempo (feature 044, T024b)

Revision ID: b4e8d2f61a93
Revises: a7c3e5d91f20
Create Date: 2026-09-22

Las actas históricas 2024–2025 traen filas con posición y puntos pero la
celda ``Tiempo`` vacía (research R-01 punto 4, R-05). El ingestor las perdía;
desde T024b las guarda como ``status='finished'`` con ``race_time_ms`` nulo,
el mismo criterio con el que ``history.py`` y ``field_metrics`` ya las tratan
(cuentan en el campo, no en las cifras de tiempo).

El CHECK ``ck_race_results_time_consistent_with_status`` lo impedía: un
``finished`` exigía tiempo o ``laps_behind``. La regla nueva conserva la mitad
que protege algo — un estado que no es ``finished`` nunca tiene tiempo — y
deja de exigir tiempo a ``finished``.

**Downgrade.** Falla ruidosamente si existe alguna fila ``finished`` sin
tiempo ni ``laps_behind``: el CHECK viejo no se podría recrear. El mensaje
solo cuenta filas, no nombra a nadie.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4e8d2f61a93"
down_revision: Union[str, None] = "a7c3e5d91f20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "race_results"
_CK = "ck_race_results_time_consistent_with_status"

OLD_RULE = (
    "(status = 'finished' AND race_time_ms IS NOT NULL) "
    "OR (status != 'finished' AND race_time_ms IS NULL) "
    "OR (status = 'finished' AND laps_behind IS NOT NULL)"
)
NEW_RULE = "(status = 'finished') OR (status != 'finished' AND race_time_ms IS NULL)"

FINISHED_WITHOUT_TIME_SQL = (
    "SELECT COUNT(*) FROM race_results "
    "WHERE status = 'finished' AND race_time_ms IS NULL AND laps_behind IS NULL"
)


def _replace_check(rule: str) -> None:
    if op.get_bind().dialect.name == "sqlite":
        # Ver la nota de ``8efe1618cb83``: batch recrea la tabla desde la
        # reflexión, que sí trae los CHECK con nombre.
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.drop_constraint(_CK, type_="check")
            batch_op.create_check_constraint(_CK, rule)
        return
    op.drop_constraint(_CK, _TABLE, type_="check")
    op.create_check_constraint(_CK, _TABLE, rule)


def upgrade() -> None:
    _replace_check(NEW_RULE)


def downgrade() -> None:
    blocking = op.get_bind().execute(sa.text(FINISHED_WITHOUT_TIME_SQL)).scalar() or 0
    if blocking:
        raise RuntimeError(
            f"No se puede revertir b4e8d2f61a93: hay {blocking} resultado(s) "
            "'finished' sin tiempo ni laps_behind (clasificados sin tiempo de "
            f"las actas históricas) y el CHECK anterior de {_CK} los prohíbe.\n"
            "Qué hacer antes de reintentar: decidir con el coach si esas filas "
            "se borran o se corrigen a mano desde el acta, y reintentar con "
            "cero filas en esa condición."
        )
    _replace_check(OLD_RULE)
