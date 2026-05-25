"""lookup tables for event_type and race_import_status

Revision ID: 7b85747392d2
Revises: ba90896dc9aa
Create Date: 2026-05-25 00:29:50.158001

Reemplaza dos enums DDL (`ENUM('...', '...')`) por tablas lookup
referenciables vía FK (C3):

- ``calendar_events.event_type`` antes era un ``ENUM(7 valores)`` →
  ahora ``VARCHAR(50)`` con FK a ``calendar_event_types.code``.
- ``race_imports.status`` antes era ``ENUM(4 valores)`` → ahora
  ``VARCHAR(50)`` con FK a ``race_import_statuses.code``.

Las tablas lookup llevan ``code`` PK + ``label_es`` legible + columnas
extra de invariantes (``sort_order``, ``is_terminal``). El seed inicial
inserta los valores actuales para mantener compatibilidad con datos
existentes.

A nivel Python los enums (``EventType``, ``RaceImportStatus``) se
mantienen; SQLAlchemy persiste el ``.value`` como string con
``native_enum=False``. Schemas Pydantic siguen exponiendo strings.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7b85747392d2"
down_revision: Union[str, None] = "ba90896dc9aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    res = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :n"
        ),
        {"n": name},
    )
    return res.scalar() > 0


def _constraint_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    res = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t "
            "AND CONSTRAINT_NAME = :n"
        ),
        {"t": table, "n": name},
    )
    return res.scalar() > 0


def _column_type(table: str, column: str) -> str | None:
    bind = op.get_bind()
    res = bind.execute(
        sa.text(
            "SELECT DATA_TYPE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t "
            "AND COLUMN_NAME = :c"
        ),
        {"t": table, "c": column},
    )
    return res.scalar()


# ---------------------------------------------------------------------------
# Seed data: valores que ya existen en producción y deben preservarse.
# ---------------------------------------------------------------------------
_EVENT_TYPES = [
    ("training_session", "Entrenamiento", 10),
    ("competition", "Competencia", 20),
    ("club_event", "Evento del club", 30),
    ("personal_training", "Entrenamiento personal", 40),
    ("group_training", "Entrenamiento grupal", 50),
    ("rest_day", "Día de descanso", 60),
    ("birthday", "Cumpleaños", 70),
]

_IMPORT_STATUSES = [
    ("pending", "Pendiente", False),
    ("dry_run", "Validación previa", False),
    ("committed", "Confirmado", True),
    ("failed", "Fallido", True),
]


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1) Crear tablas lookup (idempotente)
    # ------------------------------------------------------------------
    if not _table_exists("calendar_event_types"):
        op.create_table(
            "calendar_event_types",
            sa.Column("code", sa.String(length=50), nullable=False),
            sa.Column("label_es", sa.String(length=100), nullable=False),
            sa.Column(
                "sort_order", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.PrimaryKeyConstraint("code"),
        )
        op.bulk_insert(
            sa.table(
                "calendar_event_types",
                sa.column("code", sa.String),
                sa.column("label_es", sa.String),
                sa.column("sort_order", sa.Integer),
            ),
            [
                {"code": code, "label_es": label, "sort_order": order}
                for code, label, order in _EVENT_TYPES
            ],
        )

    if not _table_exists("race_import_statuses"):
        op.create_table(
            "race_import_statuses",
            sa.Column("code", sa.String(length=50), nullable=False),
            sa.Column("label_es", sa.String(length=100), nullable=False),
            sa.Column(
                "is_terminal",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.PrimaryKeyConstraint("code"),
        )
        op.bulk_insert(
            sa.table(
                "race_import_statuses",
                sa.column("code", sa.String),
                sa.column("label_es", sa.String),
                sa.column("is_terminal", sa.Boolean),
            ),
            [
                {"code": code, "label_es": label, "is_terminal": is_term}
                for code, label, is_term in _IMPORT_STATUSES
            ],
        )

    # ------------------------------------------------------------------
    # 2) Convertir columnas: ENUM(...) → VARCHAR(50) y crear la FK
    # ------------------------------------------------------------------
    # calendar_events.event_type
    # MySQL no permite que una columna esté en un CHECK y simultáneamente
    # sea destino de FK con ON UPDATE CASCADE. Dropeamos el CHECK
    # ck_calendar_competition_race_event temporalmente, modificamos la
    # columna + creamos FK, y recreamos el CHECK al final.
    if _column_type("calendar_events", "event_type") not in ("varchar",):
        if _constraint_exists(
            "calendar_events", "ck_calendar_competition_race_event"
        ):
            op.drop_constraint(
                "ck_calendar_competition_race_event",
                "calendar_events",
                type_="check",
            )
        op.execute(
            "ALTER TABLE calendar_events "
            "MODIFY COLUMN event_type VARCHAR(50) NOT NULL"
        )

    if not _constraint_exists("calendar_events", "fk_calendar_events_event_type"):
        op.create_foreign_key(
            "fk_calendar_events_event_type",
            "calendar_events",
            "calendar_event_types",
            ["event_type"],
            ["code"],
            # Sin CASCADE update porque MySQL no permite combinar FK con
            # CASCADE y CHECK en la misma columna. RESTRICT es suficiente
            # (los codes no se renombran en runtime).
            ondelete="RESTRICT",
        )

    if not _constraint_exists(
        "calendar_events", "ck_calendar_competition_race_event"
    ):
        op.create_check_constraint(
            "ck_calendar_competition_race_event",
            "calendar_events",
            "event_type != 'competition' OR race_event_id IS NOT NULL",
        )

    # race_imports.status
    if _column_type("race_imports", "status") not in ("varchar",):
        op.execute(
            "ALTER TABLE race_imports "
            "MODIFY COLUMN status VARCHAR(50) NOT NULL"
        )

    if not _constraint_exists("race_imports", "fk_race_imports_status"):
        op.create_foreign_key(
            "fk_race_imports_status",
            "race_imports",
            "race_import_statuses",
            ["status"],
            ["code"],
            onupdate="CASCADE",
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    # Restaura los ENUMs DDL originales (con los mismos valores).
    op.drop_constraint(
        "fk_race_imports_status", "race_imports", type_="foreignkey"
    )
    op.execute(
        "ALTER TABLE race_imports "
        "MODIFY COLUMN status "
        "ENUM('pending','dry_run','committed','failed') NOT NULL"
    )

    op.drop_constraint(
        "fk_calendar_events_event_type", "calendar_events", type_="foreignkey"
    )
    # El CHECK debe dropearse antes del MODIFY COLUMN porque la conversión
    # de VARCHAR → ENUM la afecta.
    op.drop_constraint(
        "ck_calendar_competition_race_event", "calendar_events", type_="check"
    )
    op.execute(
        "ALTER TABLE calendar_events "
        "MODIFY COLUMN event_type "
        "ENUM('training_session','competition','club_event','personal_training',"
        "'group_training','rest_day','birthday') NOT NULL"
    )
    op.create_check_constraint(
        "ck_calendar_competition_race_event",
        "calendar_events",
        "event_type != 'competition' OR race_event_id IS NOT NULL",
    )

    op.drop_table("race_import_statuses")
    op.drop_table("calendar_event_types")
