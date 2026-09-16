"""multicopa: insight_scope_key, race_events.priority, race_series.short_name

Revision ID: c2314ccd7927
Revises: 2c0097aa48b8
Create Date: 2026-09-16 15:14:02.172446

Hotfix "identidad de válida" — ver
``~/.claude/plans/multicopa-identidad-valida.md`` (bug real: la AI mezcló
Copa Let's Go V4 con Copa Valle V4/V5 del mismo atleta porque `valida_num`
sin la copa no identifica una carrera sin ambigüedad).

1) ``race_series.short_name`` (VARCHAR(40) NULL): nombre corto para labels
   (ej. "Let's Go" en vez de "Copa Let's Go Interdepartamental XCO"). Sin
   backfill — NULL cae a `name` completo en `race_labels.series_display_name`.

2) ``race_events.priority`` (ENUM('A','B','C','CD') NULL, MySQL nativo /
   VARCHAR en SQLite): reemplaza el dict hardcodeado `_CALENDAR_TIERS` de
   `services/notification/race_event_tier.py`, que solo conocía Copa Valle
   2026 y colisionaba con cualquier otra copa reutilizando `sequence_number`.
   Backfill idempotente SOLO para Copa Valle 2026
   (`race_series.season_year=2026 AND race_series.name LIKE 'Copa Valle%'`):
   sequence_number 3→C, 4→A, 5→B, 6→A, 7→B, 99→CD. 1 y 2 (ya corridas, sin
   necesidad de tapering) quedan NULL a propósito. Cualquier otra copa
   (Let's Go, etc.) queda NULL → tier UNKNOWN → sin email a padres, hasta
   que el coach la priorice manualmente vía `PATCH /race-events/{id}`.

3) ``athlete_ai_insights.event_id`` (backfill, NO columna nueva — la
   columna ya existía y es nullable): filas legadas (pre-hotfix) con
   ``event_id IS NULL AND valida_num > 0`` se resuelven a la válida
   correspondiente SOLO cuando ``(season, valida_num)`` mapea a EXACTAMENTE
   un ``race_event`` en esa temporada (``race_series.season_year = season``,
   ``race_event.sequence_number = valida_num``). Si hay más de una copa
   corriendo ese ``valida_num`` en esa temporada (el caso ambiguo real:
   Copa Valle V4 + Copa Let's Go V4 en 2026), la fila se deja con
   ``event_id`` en ``NULL`` — no hay forma segura de adivinar cuál era.
   Filas con ``valida_num IN (0, NULL)`` nunca se tocan (agregados de
   temporada / analíticas futuras no tienen un evento único que resolver).
   Idempotente: una fila ya backfilleada tiene ``event_id`` no NULL y el
   ``WHERE`` no vuelve a tocarla.

4) ``athlete_ai_insights.insight_scope_key`` (VARCHAR(40) NOT NULL): la
   terna real de agrupación de un insight — ver
   ``app.models.athlete_ai_insight.compute_insight_scope_key``. Corre
   DESPUÉS del backfill de ``event_id`` de (3) para que las filas legadas
   ahora resueltas obtengan la clave ``event:{id}`` en vez de
   ``valida:{season}:{n}``. Backfill con el mismo CASE que el helper
   Python, luego NOT NULL. Reemplaza el UNIQUE parcial
   ``uq_insights_active_terna (athlete_id, season, valida_num, is_active)``
   — que colisionaba entre dos copas con el mismo ``valida_num`` en la
   misma temporada — por ``uq_insights_active_scope (athlete_id,
   insight_scope_key, is_active)``. ``ix_insights_athlete_season`` se
   conserva sin cambios (sigue sirviendo al filtro por season/valida_num de
   ``list_athlete_insights``).

Downgrade: revierte las 3 columnas y restaura ``uq_insights_active_terna``.
ADVERTENCIA — el downgrade de la constraint FALLARÁ si para entonces existen
dos filas activas con el mismo ``(athlete_id, season, valida_num)`` pero
distinto ``event_id`` (exactamente el estado que este hotfix hace posible a
propósito, ej. Copa Valle V4 y Copa Let's Go V4 ambas activas para el mismo
atleta). Es el comportamiento esperado: revertir el fix también debe
revertir la posibilidad de tener ambas activas — requiere resolver
manualmente cuál de las dos deprecar antes de poder downgradear.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c2314ccd7927"
down_revision: Union[str, None] = "2c0097aa48b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_PRIORITY_ENUM_NAME = "raceeventpriority"

# (sequence_number -> priority) para Copa Valle 2026 únicamente. Mismos
# valores que `_CALENDAR_TIERS` en `race_event_tier.py` (pre-hotfix), menos
# 1 y 2 (ya corridas sin tapering, se dejan NULL a propósito).
_COPA_VALLE_2026_PRIORITY = {
    3: "C",
    4: "A",
    5: "B",
    6: "A",
    7: "B",
    99: "CD",
}

# Backfill de filas legadas: resuelve `event_id` desde `(season, valida_num)`
# SOLO cuando esa combinación mapea a exactamente UN race_event en esa
# temporada (subquery de conteo en el WHERE). Portable MySQL/SQLite — es una
# subquery correlacionada estándar, ninguna de las dos referencia
# `athlete_ai_insights` en su propio FROM (eso es lo único que MySQL
# rechazaría con "can't specify target table for update in FROM clause").
# Exportado como constante a nivel de módulo para que
# `tests/models/test_athlete_ai_insight_scope_key_migration.py` la ejecute
# directamente contra un esquema mínimo y verifique el caso ambiguo vs. el
# caso resuelto sin re-implementar la lógica.
BACKFILL_LEGACY_EVENT_ID_SQL = """
    UPDATE athlete_ai_insights
    SET event_id = (
        SELECT re.id
        FROM race_events re
        JOIN race_series rs ON rs.id = re.series_id
        WHERE rs.season_year = athlete_ai_insights.season
          AND re.sequence_number = athlete_ai_insights.valida_num
    )
    WHERE athlete_ai_insights.event_id IS NULL
      AND athlete_ai_insights.valida_num > 0
      AND (
          SELECT COUNT(*)
          FROM race_events re2
          JOIN race_series rs2 ON rs2.id = re2.series_id
          WHERE rs2.season_year = athlete_ai_insights.season
            AND re2.sequence_number = athlete_ai_insights.valida_num
      ) = 1
"""


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # =========================================================================
    # 1) race_series.short_name
    # =========================================================================
    with op.batch_alter_table("race_series") as batch_op:
        batch_op.add_column(sa.Column("short_name", sa.String(length=40), nullable=True))

    # =========================================================================
    # 2) race_events.priority (+ backfill Copa Valle 2026)
    # =========================================================================
    with op.batch_alter_table("race_events") as batch_op:
        batch_op.add_column(
            sa.Column(
                "priority",
                sa.Enum("A", "B", "C", "CD", name=_PRIORITY_ENUM_NAME),
                nullable=True,
            )
        )

    # Backfill idempotente: solo Copa Valle 2026, solo por sequence_number
    # explícitamente mapeado arriba. Un re-run no cambia nada (mismo WHERE,
    # mismos valores) — no-op cuando la serie/eventos no existen (ej. entorno
    # de test sin datos sembrados).
    for seq, priority in _COPA_VALLE_2026_PRIORITY.items():
        op.execute(
            sa.text(
                """
                UPDATE race_events
                SET priority = :priority
                WHERE sequence_number = :seq
                  AND series_id IN (
                      SELECT id FROM race_series
                      WHERE season_year = 2026 AND name LIKE 'Copa Valle%'
                  )
                """
            ).bindparams(priority=priority, seq=seq)
        )

    # =========================================================================
    # 3) athlete_ai_insights.insight_scope_key + swap del UNIQUE parcial
    # =========================================================================
    with op.batch_alter_table("athlete_ai_insights") as batch_op:
        batch_op.add_column(
            sa.Column("insight_scope_key", sa.String(length=40), nullable=True)
        )

    # 3a) Backfill de event_id en filas legadas (ver docstring del módulo,
    # punto 3) — DEBE correr antes del backfill de insight_scope_key para
    # que las filas resueltas obtengan la clave event:{id} en vez de la
    # legada valida:{season}:{n}.
    op.execute(BACKFILL_LEGACY_EVENT_ID_SQL)

    # 3b) Backfill de insight_scope_key — mismo CASE que
    # compute_insight_scope_key en Python. CONCAT funciona igual en MySQL y
    # SQLite (ambos lo soportan con esta firma variádica; SQLite además
    # soporta `||` pero usamos CONCAT por portabilidad con el dialecto real
    # de prod).
    # NOTA: ningún literal de la CASE puede contener el token crudo `:none`
    # — `op.execute(str)` envuelve el string en `sa.text(...)`, y su parser
    # de bind params matchea `:identificador` en TODO el texto sin
    # entender comillas SQL, así que `':none'` se interpretaría como un
    # bind param llamado `none` (`InvalidRequestError: A value is required
    # for bind parameter 'none'`) en vez de como el literal
    # "dos puntos + none". Por eso el sentinel se concatena en dos pedazos
    # (`':' || 'none'` / `CONCAT(..., ':', 'none')`) — mismo string final,
    # sin ningún `:palabra` literal en el texto.
    if dialect == "sqlite":
        # SQLite no tiene CONCAT() variádico — usamos concatenación `||`.
        op.execute(
            """
            UPDATE athlete_ai_insights
            SET insight_scope_key = CASE
                WHEN valida_num = 0 THEN 'season:' || season
                WHEN event_id IS NOT NULL THEN 'event:' || event_id
                WHEN valida_num IS NULL THEN 'valida:' || season || ':' || 'none'
                ELSE 'valida:' || season || ':' || valida_num
            END
            """
        )
    else:
        op.execute(
            """
            UPDATE athlete_ai_insights
            SET insight_scope_key = CASE
                WHEN valida_num = 0 THEN CONCAT('season:', season)
                WHEN event_id IS NOT NULL THEN CONCAT('event:', event_id)
                WHEN valida_num IS NULL THEN CONCAT('valida:', season, ':', 'none')
                ELSE CONCAT('valida:', season, ':', valida_num)
            END
            """
        )

    if dialect == "sqlite":
        # SQLite: batch_alter_table recrea la tabla — hay que declarar el
        # UNIQUE nuevo explícitamente en table_args porque el recreate no
        # conoce el constraint viejo por nombre (usa el metadata actual del
        # modelo, que YA declara uq_insights_active_scope tras el cambio en
        # athlete_ai_insight.py). Alcanza con NOT NULL + el nuevo UNIQUE.
        with op.batch_alter_table(
            "athlete_ai_insights",
            table_args=(
                sa.CheckConstraint(
                    "coach_edits_count >= 0",
                    name="ck_insights_coach_edits_count_nonneg",
                ),
                sa.CheckConstraint(
                    "valida_num IS NULL OR valida_num >= 0",
                    name="ck_insights_valida_num_nonneg",
                ),
                sa.UniqueConstraint(
                    "athlete_id",
                    "insight_scope_key",
                    "is_active",
                    name="uq_insights_active_scope",
                ),
            ),
        ) as batch_op:
            batch_op.alter_column(
                "insight_scope_key", existing_type=sa.String(length=40), nullable=False
            )
    else:
        op.alter_column(
            "athlete_ai_insights",
            "insight_scope_key",
            existing_type=sa.String(length=40),
            nullable=False,
        )
        op.drop_constraint(
            "uq_insights_active_terna", "athlete_ai_insights", type_="unique"
        )
        op.create_unique_constraint(
            "uq_insights_active_scope",
            "athlete_ai_insights",
            ["athlete_id", "insight_scope_key", "is_active"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # =========================================================================
    # 3'. athlete_ai_insights: restaura uq_insights_active_terna
    # =========================================================================
    # Ver docstring del módulo: falla si hay 2 filas activas con la misma
    # (athlete_id, season, valida_num) y distinto event_id — resolver
    # manualmente antes de downgradear.
    if dialect == "sqlite":
        with op.batch_alter_table(
            "athlete_ai_insights",
            table_args=(
                sa.CheckConstraint(
                    "coach_edits_count >= 0",
                    name="ck_insights_coach_edits_count_nonneg",
                ),
                sa.CheckConstraint(
                    "valida_num IS NULL OR valida_num >= 0",
                    name="ck_insights_valida_num_nonneg",
                ),
                sa.UniqueConstraint(
                    "athlete_id",
                    "season",
                    "valida_num",
                    "is_active",
                    name="uq_insights_active_terna",
                ),
            ),
        ) as batch_op:
            batch_op.drop_column("insight_scope_key")
    else:
        op.drop_constraint(
            "uq_insights_active_scope", "athlete_ai_insights", type_="unique"
        )
        op.create_unique_constraint(
            "uq_insights_active_terna",
            "athlete_ai_insights",
            ["athlete_id", "season", "valida_num", "is_active"],
        )
        op.drop_column("athlete_ai_insights", "insight_scope_key")

    # =========================================================================
    # 2'. race_events.priority
    # =========================================================================
    with op.batch_alter_table("race_events") as batch_op:
        batch_op.drop_column("priority")
    if dialect != "sqlite":
        sa.Enum(name=_PRIORITY_ENUM_NAME).drop(bind, checkfirst=True)

    # =========================================================================
    # 1'. race_series.short_name
    # =========================================================================
    with op.batch_alter_table("race_series") as batch_op:
        batch_op.drop_column("short_name")
