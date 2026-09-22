"""race_history_backfill — congelado de categoría + identidad entre temporadas

Revision ID: 8efe1618cb83
Revises: c2314ccd7927
Create Date: 2026-09-18

Feature 044 (histórico Copa Valle 2024-2025). Ver
``specs/044-race-history-backfill/data-model.md`` §1-§4 y ``research.md``
R-04 / R-06.

Tres cambios, en un orden que **no es negociable** (ver ``upgrade()``):

1) ``race_results`` gana tres columnas *congeladas* — ``category_label_raw``,
   ``category_age_min_raw``, ``category_age_max_raw`` — y se backfillean
   desde el catálogo vigente. Se escriben una sola vez, al insertar, y nunca
   se actualizan: sin ellas, renombrar una categoría o corregir su rango de
   edad reescribiría el pasado (un resultado de 2024 mostraría la etiqueta de
   2026). Son nullable y van al final de la tabla → ``ALGORITHM=INSTANT`` en
   MySQL 8.4, sin bloqueo de tabla.

2) Nacen ``race_identity_candidates`` (cola de revisión + auditoría de
   decisiones) y ``race_competitor_signatures`` (las ternas
   ``(nombre, club, ciudad)`` observadas, una o varias por competidor).

3) Recién entonces se elimina ``uq_race_competitors_normalized_name``. Ese
   UNIQUE hacía dos cosas a la vez: definía la identidad de un competidor y
   protegía contra ingestas concurrentes del mismo corredor nuevo. La primera
   función era incorrecta (dos homónimos se fusionaban en silencio; una misma
   persona impresa con y sin segundo apellido eran dos personas) y la segunda
   la hereda ``uq_race_competitor_signatures_triple``.

**Por qué el orden importa.** Entre el paso 2 y el paso 3 el sistema sigue
teniendo una garantía de unicidad *en todo momento*: primero se crean y
pueblan las firmas — que mientras el UNIQUE viejo exista son
trivialmente únicas, una por competidor — y solo después se suelta el
constraint viejo. Si se soltara primero, habría una ventana en la que ni el
UNIQUE ni las firmas protegen nada, y una ingesta concurrente en esa ventana
duplicaría competidores. En MySQL el DDL no es transaccional, así que esa
ventana sería real, no teórica.

**Deuda conocida que esta revisión abre.** El código de ingesta todavía no
escribe ni consulta firmas (eso llega en la fase 6 de la 044). Entre esta
migración y esa fase, la protección de concurrencia existe en el esquema pero
nadie la usa: dos ingestas simultáneas del mismo corredor nuevo pueden crear
dos competidores. Es un intervalo aceptado a propósito — no se carga ningún
histórico antes de que la fase 6 esté lista — y está anotado en el runbook.

**Downgrade.** Simétrico, pero **falla ruidosamente** si para entonces
existen competidores homónimos: recrear el UNIQUE sobre ``normalized_name``
sería imposible y el error de MySQL no diría qué hacer. Ver ``downgrade()``.
"""
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from unidecode import unidecode

# revision identifiers, used by Alembic.
revision: str = "8efe1618cb83"
down_revision: Union[str, None] = "c2314ccd7927"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Copia congelada de `app.services.race.normalizer.normalize_club`
# ---------------------------------------------------------------------------
# Deliberadamente NO se importa el servicio. Una migración es un snapshot: si
# mañana cambia la normalización de clubes, este backfill debe seguir
# produciendo exactamente lo que produjo el día que corrió en producción.
# Importar el servicio también volvería `alembic upgrade head` desde cero
# (entrypoint.sh, CI) dependiente de que la función nunca se renombre.
_EMPTY_CLUB_TOKENS = frozenset({"0", "-", "n/a", "na", ""})


def _normalize_club(s: str | None) -> str:
    """``unidecode`` + lower + colapsa espacios; placeholders → ``''``."""
    if not s:
        return ""
    out = unidecode(s).lower()
    out = " ".join(out.split())
    if out in _EMPTY_CLUB_TOKENS:
        return ""
    return out


# Nota sobre `batch_alter_table` en SQLite: recrea la tabla desde la reflexión,
# y de ahí la tentación de repasar constraints por `table_args`. No hace falta,
# y hacerlo sería un error:
#   - los CHECK declarados (`ck_race_results_*`) SÍ los devuelve la reflexión
#     (`get_check_constraints` del dialecto sqlite), así que declararlos otra
#     vez los DUPLICA en el DDL, y la duplicación se acumula en cada ciclo
#     upgrade → downgrade → upgrade;
#   - los CHECK "de enum" (`racecompetitorsex`, `raceresultstatus`) no existen:
#     desde SQLAlchemy 1.4 `Enum.create_constraint` es False por defecto, así
#     que en SQLite esas columnas son VARCHAR pelado sin CHECK.
# Ambas cosas verificadas leyendo el DDL de `sqlite_master` tras un ciclo
# completo.


# Backfill de las tres columnas congeladas desde el catálogo. Tres subconsultas
# correlacionadas en vez de `UPDATE ... JOIN`: esa sintaxis es exclusiva de
# MySQL y el carril por defecto de pytest corre sobre SQLite. Ninguna subquery
# referencia `race_results` en su propio FROM, que es lo único que MySQL
# rechazaría ("can't specify target table for update in FROM clause").
# El `WHERE ... IS NULL` lo hace idempotente y, sobre todo, garantiza que un
# re-run jamás pise un valor ya congelado.
BACKFILL_FROZEN_CATEGORY_SQL = """
    UPDATE race_results
    SET category_label_raw = (
            SELECT c.label FROM race_categories c
            WHERE c.id = race_results.category_id
        ),
        category_age_min_raw = (
            SELECT c.age_min FROM race_categories c
            WHERE c.id = race_results.category_id
        ),
        category_age_max_raw = (
            SELECT c.age_max FROM race_categories c
            WHERE c.id = race_results.category_id
        )
    WHERE race_results.category_label_raw IS NULL
"""

# Temporadas en que cada competidor tiene al menos un resultado. No se filtra
# `deleted_at`: un resultado con soft-delete sigue siendo evidencia de que esa
# persona fue impresa esa temporada, que es lo único que first/last_season
# afirman.
COMPETITOR_SEASONS_SQL = """
    SELECT rr.competitor_id AS competitor_id,
           MIN(rs.season_year) AS first_season,
           MAX(rs.season_year) AS last_season
    FROM race_results rr
    JOIN race_events re ON re.id = rr.event_id
    JOIN race_series rs ON rs.id = re.series_id
    GROUP BY rr.competitor_id
"""

DUPLICATE_NAMES_SQL = """
    SELECT COUNT(*) FROM (
        SELECT normalized_name
        FROM race_competitors
        GROUP BY normalized_name
        HAVING COUNT(*) > 1
    ) dupes
"""


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # =========================================================================
    # 1) race_results: tres columnas congeladas + backfill desde el catálogo
    # =========================================================================
    # `op.add_column` plano (no batch): agregar una columna nullable al final
    # lo soportan nativamente MySQL y SQLite, y en MySQL 8.4 es INSTANT.
    op.add_column(
        "race_results", sa.Column("category_label_raw", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "race_results", sa.Column("category_age_min_raw", sa.SmallInteger(), nullable=True)
    )
    op.add_column(
        "race_results", sa.Column("category_age_max_raw", sa.SmallInteger(), nullable=True)
    )
    op.execute(BACKFILL_FROZEN_CATEGORY_SQL)

    # =========================================================================
    # 2) Tablas nuevas — candidatos PRIMERO (las firmas le apuntan con una FK)
    # =========================================================================
    op.create_table(
        "race_identity_candidates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "same_person_suspect",
                "homonym_suspect",
                name="raceidentitycandidatekind",
            ),
            nullable=False,
        ),
        sa.Column("pair_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("left_record", sa.JSON(), nullable=False),
        sa.Column("right_record", sa.JSON(), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("signals", sa.JSON(), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "pending",
                "same_person",
                "different_people",
                name="raceidentitycandidatestate",
            ),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "linked_athlete_involved",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("decided_by_user_id", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("reversed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("reversed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"],
            ["users.id"],
            name="fk_race_identity_candidates_decided_by_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reversed_by_user_id"],
            ["users.id"],
            name="fk_race_identity_candidates_reversed_by_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        # Idempotencia del rebuild: el mismo par vuelve a dar el mismo hash y
        # choca aquí en vez de re-preguntarle al coach algo ya decidido.
        sa.UniqueConstraint("pair_hash", name="uq_race_identity_candidates_pair_hash"),
    )
    op.create_index(
        "ix_race_identity_candidates_state",
        "race_identity_candidates",
        ["state"],
        unique=False,
    )

    op.create_table(
        "race_competitor_signatures",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("competitor_id", sa.Integer(), nullable=False),
        sa.Column("normalized_name", sa.String(length=160), nullable=False),
        # NOT NULL DEFAULT '' a propósito: MySQL considera dos NULL como
        # valores distintos dentro de una clave única, de modo que con columnas
        # nullable la terna (nombre, NULL, NULL) se podría insertar infinitas
        # veces y el UNIQUE de abajo no protegería absolutamente nada.
        sa.Column(
            "club_norm",
            sa.String(length=150),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column(
            "city_norm",
            sa.String(length=100),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column("first_season", sa.SmallInteger(), nullable=False),
        sa.Column("last_season", sa.SmallInteger(), nullable=False),
        sa.Column("source_candidate_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["competitor_id"],
            ["race_competitors.id"],
            name="fk_race_competitor_signatures_competitor_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_candidate_id"],
            ["race_identity_candidates.id"],
            name="fk_race_competitor_signatures_source_candidate_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalized_name",
            "club_norm",
            "city_norm",
            name="uq_race_competitor_signatures_triple",
        ),
    )
    # Sin índice propio sobre `normalized_name`: el UNIQUE de la terna ya lo
    # cubre como prefijo izquierdo.
    op.create_index(
        "ix_race_competitor_signatures_competitor_id",
        "race_competitor_signatures",
        ["competitor_id"],
        unique=False,
    )

    # =========================================================================
    # 3) Backfill: una firma por competidor existente
    # =========================================================================
    # Corre CON el UNIQUE viejo todavía puesto, así que `normalized_name` es
    # único y las ternas resultantes no pueden colisionar entre sí. La ciudad
    # va vacía porque hasta ahora no se persistía (research R-06).
    _backfill_signatures(bind)

    # =========================================================================
    # 4) Recién ahora: soltar el UNIQUE viejo, índice simple, city_text
    # =========================================================================
    if dialect == "sqlite":
        # SQLite no sabe hacer ALTER TABLE DROP CONSTRAINT — batch recrea la
        # tabla (ver la nota sobre reflexión más arriba).
        with op.batch_alter_table("race_competitors") as batch_op:
            batch_op.drop_constraint(
                "uq_race_competitors_normalized_name", type_="unique"
            )
    else:
        op.drop_constraint(
            "uq_race_competitors_normalized_name", "race_competitors", type_="unique"
        )

    op.create_index(
        "ix_race_competitors_normalized_name",
        "race_competitors",
        ["normalized_name"],
        unique=False,
    )
    op.add_column(
        "race_competitors", sa.Column("city_text", sa.String(length=100), nullable=True)
    )


def _backfill_signatures(bind: sa.engine.Connection) -> None:
    """Inserta una firma por competidor existente (data-model §3).

    Terna ``(normalized_name, normalize_club(club_text), '')``. Las temporadas
    salen de los resultados del competidor vía
    ``race_results → race_events → race_series.season_year``; un competidor sin
    resultados (posible: el linking puede crear uno antes de su primera
    válida) cae al año en curso.
    """
    competitors = bind.execute(
        sa.text("SELECT id, normalized_name, club_text FROM race_competitors")
    ).fetchall()
    if not competitors:
        return

    seasons = {
        row.competitor_id: (row.first_season, row.last_season)
        for row in bind.execute(sa.text(COMPETITOR_SEASONS_SQL)).fetchall()
    }
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    fallback_season = now.year

    rows = []
    # Red de seguridad: con el UNIQUE viejo puesto dos competidores no pueden
    # compartir `normalized_name`, así que dos ternas no pueden colisionar. Se
    # deduplica igual por si esta revisión llegara a correr sobre una base que
    # ya perdió el constraint por otro camino — mejor omitir una firma que
    # abortar la migración entera.
    seen: set[tuple[str, str, str]] = set()
    for competitor in competitors:
        club_norm = _normalize_club(competitor.club_text)
        triple = (competitor.normalized_name, club_norm, "")
        if triple in seen:
            continue
        seen.add(triple)
        first_season, last_season = seasons.get(
            competitor.id, (fallback_season, fallback_season)
        )
        rows.append(
            {
                "competitor_id": competitor.id,
                "normalized_name": competitor.normalized_name,
                "club_norm": club_norm,
                "city_norm": "",
                "first_season": first_season,
                "last_season": last_season,
                "created_at": now,
            }
        )

    if rows:
        bind.execute(
            sa.text(
                """
                INSERT INTO race_competitor_signatures (
                    competitor_id, normalized_name, club_norm, city_norm,
                    first_season, last_season, created_at
                ) VALUES (
                    :competitor_id, :normalized_name, :club_norm, :city_norm,
                    :first_season, :last_season, :created_at
                )
                """
            ),
            rows,
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # =========================================================================
    # 4') Restituir uq_race_competitors_normalized_name — puede ser imposible
    # =========================================================================
    # Todo el punto de esta feature es que dos personas puedan llamarse igual.
    # Si ya se cargó histórico con homónimos, el UNIQUE no se puede recrear y
    # revertir exige decidir a mano qué hacer con cada par. El mensaje no
    # nombra a nadie: solo cuenta (privacidad de terceros / menores).
    duplicates = bind.execute(sa.text(DUPLICATE_NAMES_SQL)).scalar() or 0
    if duplicates:
        raise RuntimeError(
            f"No se puede revertir 8efe1618cb83: hay {duplicates} nombre(s) "
            "normalizado(s) compartido(s) por más de un competidor, y el "
            "downgrade tiene que restituir "
            "uq_race_competitors_normalized_name (UNIQUE sobre "
            "race_competitors.normalized_name).\n"
            "Qué hacer antes de reintentar:\n"
            "  1. Listar los grupos: SELECT normalized_name, COUNT(*) FROM "
            "race_competitors GROUP BY normalized_name HAVING COUNT(*) > 1;\n"
            "  2. Por cada grupo, decidir en la revisión de identidad si son "
            "la misma persona (fusionar: mover race_results y "
            "race_competitor_signatures al competidor más antiguo y borrar el "
            "otro) o personas distintas (entonces NO se puede revertir sin "
            "perder esa distinción — restaurar desde backup).\n"
            "  3. Reintentar el downgrade con cero duplicados."
        )

    op.drop_column("race_competitors", "city_text")
    op.drop_index("ix_race_competitors_normalized_name", table_name="race_competitors")
    if dialect == "sqlite":
        with op.batch_alter_table("race_competitors") as batch_op:
            batch_op.create_unique_constraint(
                "uq_race_competitors_normalized_name", ["normalized_name"]
            )
    else:
        op.create_unique_constraint(
            "uq_race_competitors_normalized_name", "race_competitors", ["normalized_name"]
        )

    # =========================================================================
    # 3') / 2') Tablas nuevas — firmas primero (FK hacia candidatos)
    # =========================================================================
    # Destrucción de datos justificada: las firmas y los candidatos nacen en
    # esta revisión, no existía nada que preservar antes de ella. Las
    # decisiones de identidad ya tomadas SÍ se pierden — ese es el costo
    # documentado de revertir, y por eso el runbook exige backup previo.
    # Sin `drop_index` previo: `DROP TABLE` se lleva sus índices en ambos
    # dialectos, y en MySQL un índice que respalda una FK no se puede borrar
    # suelto (error 1553) — así falló la primera verificación en MySQL 8.4.
    op.drop_table("race_competitor_signatures")
    op.drop_table("race_identity_candidates")
    if dialect != "sqlite":
        # No-op en MySQL (el ENUM es inline en la columna, no un tipo con
        # nombre); se deja por simetría con el resto de las migraciones y por
        # si algún día el dialecto de destino tuviera tipos nombrados.
        sa.Enum(name="raceidentitycandidatestate").drop(bind, checkfirst=True)
        sa.Enum(name="raceidentitycandidatekind").drop(bind, checkfirst=True)

    # =========================================================================
    # 1') race_results: quitar las tres columnas congeladas
    # =========================================================================
    # Destrucción de datos justificada y acotada: las tres columnas son copias
    # del catálogo en el momento del insert. Al revertir se pierde la foto
    # histórica (si el catálogo cambió entretanto, no se puede reconstruir) —
    # pero ninguna lectura anterior a la 044 las usa.
    # `op.drop_column` plano, sin batch: SQLite soporta ALTER TABLE DROP COLUMN
    # nativamente desde 3.35 mientras la columna no participe de un índice, un
    # CHECK, una FK ni una columna generada — ninguna de las tres lo hace. Es
    # además lo deseable: `batch_alter_table` recrearía `race_results` entera
    # (4 CHECK + 1 UNIQUE + 4 índices) sin necesidad.
    op.drop_column("race_results", "category_age_max_raw")
    op.drop_column("race_results", "category_age_min_raw")
    op.drop_column("race_results", "category_label_raw")
