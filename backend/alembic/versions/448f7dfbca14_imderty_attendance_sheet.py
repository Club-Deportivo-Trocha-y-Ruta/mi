"""IMDERTY monthly attendance sheet (feature 047, T005)

Revision ID: 448f7dfbca14
Revises: be4595de1ad2
Create Date: 2026-09-28

``specs/047-imderty-attendance-sheet/data-model.md``. Mirrors
``app/models/imderty.py`` and ``ParentAthlete.primary_contact_key`` in
``app/models/athlete.py``.

1. ``imderty_barrios`` — platform-wide Yumbo barrio → zone catalog (public
   geography). UNIQUE ``name``; CHECK ``zone`` in the 7 official values.
2. ``athlete_imderty_profiles`` — 1:1 ``athletes`` (PK = FK, ON DELETE
   CASCADE: the sheet profile has no meaning without the athlete).
   ``barrio_id`` → ``imderty_barrios`` ON DELETE RESTRICT (a referenced barrio
   is deactivated, never deleted). CHECK: ``other_municipality`` and
   ``barrio_id`` are mutually exclusive.
3. ``athlete_sensitive_authorizations`` — append-only guardian authorization
   log. ``active_key`` = ``athlete_id`` while active, NULL once withdrawn;
   its UNIQUE index allows at most one active row per athlete (NULLs never
   collide in MySQL or SQLite). ``athlete_id`` ON DELETE CASCADE;
   guardian/recorder/withdrawer FKs to ``users`` without ON DELETE (the audit
   trail must not silently lose its actors).
4. ``athlete_sensitive_data`` — 1:1 ``athletes`` (ON DELETE CASCADE); FK to
   the authorization without ON DELETE (the service deletes the data row
   before/with the withdrawal, never the authorization).
5. ``club_imderty_settings`` — 1:1 ``clubs`` (ON DELETE CASCADE).
6. ``parent_athlete.primary_contact_key`` INTEGER NULL + UNIQUE
   ``uq_parent_athlete_primary_contact_key`` (same nullable-unique trick).
   Added through ``batch_alter_table`` so SQLite can add the constraint; on
   MySQL it renders plain ``ALTER TABLE`` statements. ``parent_athlete`` is a
   small table (one row per guardian link), so the ALTER lock is negligible.
7. Seed of ``imderty_barrios`` from the SECTOR sheet. The list is copied
   literally below (frozen at migration time) instead of importing
   ``app/services/imderty/barrios_seed.py``: later edits to the seed module
   must not change what this revision inserts.

Every ``updated_by_user_id`` → ``users`` is ON DELETE SET NULL
(``UpdatedByMixin``). No enum, column or label for the category excluded by
FR-009 exists here.

Downgrade (reverse order): drop the ``parent_athlete`` constraint and column,
then the tables in reverse dependency order. Dropping ``imderty_barrios``
removes the seed with it. Data loss on downgrade is limited to the rows of
this feature's own tables (identification and sensitive blocks entered after
the upgrade), which is the intended rollback of the feature.
"""
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "448f7dfbca14"
down_revision: Union[str, None] = "be4595de1ad2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ZONES: tuple[str, ...] = (
    "1",
    "2",
    "3",
    "4",
    "ZONA NORTE",
    "ZONA CENTRO",
    "ZONA SUR",
)

DOCUMENT_TYPES = ("rc", "ti", "cc", "ce", "ppt", "pep", "nes")
GRADES = (
    "prejardin",
    "jardin",
    "transicion",
    *(f"g{n}" for n in range(1, 12)),
    "no_escolarizado",
    "otro",
)
ETHNICITIES = (
    "AFROCOLOMBIANO",
    "INDÍGENA",
    "MESTIZO",
    "MULATO",
    "NO SABE NO RESPONDE",
    "OTRO",
    "PALENQUERO",
    "RAIZAL",
    "ROM GITANO",
)
DISABILITIES = (
    "OLFATIVA Y TACTO",
    "MENTAL",
    "MOVILIDAD",
    "MULTIPLE",
    "ORAL",
    "PSICOSOCIAL",
    "VISUAL",
    "VOZ Y HABLA",
    "NO SABE NOMBRARLA",
    "N/A",
)
YES_NO = ("si", "no")

# Frozen copy of ``app.services.imderty.barrios_seed.BARRIOS_YUMBO``
# (SECTOR sheet, public geography — no personal data).
BARRIOS: tuple[tuple[str, str], ...] = (
    ('ALTO DAPA', 'ZONA SUR'),
    ('ALTO SAN JORGE', '1'),
    ('ALTOS DE MENGA', 'ZONA SUR'),
    ('ARROYOHONDO', 'ZONA SUR'),
    ('ASOPROSAN', 'ZONA NORTE'),
    ('ASOVIVIR LAS COLINAS', '3'),
    ('BELALCAZAR', '2'),
    ('BELLAVISTA', '4'),
    ('BOLIVAR', '2'),
    ('BRISAS DE LA SULTANA', '4'),
    ('BUENOS AIRES', '3'),
    ('CACIQUE JACINTO', '4'),
    ('CAMPESTRE REAL', '4'),
    ('CANGREJO', 'ZONA NORTE'),
    ('CIUDADELA PORTALES DE COMFANDI', '2'),
    ('COLINAS DEL NORTE', '1'),
    ('CONQUISTADORES', '4'),
    ('CORVIVALLE', '3'),
    ('DAPA', 'ZONA SUR'),
    ('DIONISIO HERNÁN CALDERÓN', '4'),
    ('EL CHOCHO', 'ZONA CENTRO'),
    ('EL HIGUERON', 'ZONA NORTE'),
    ('EL PEDREGAL', 'ZONA SUR'),
    ('EL PLACER', 'ZONA CENTRO'),
    ('EL TABLAZO', 'ZONA SUR'),
    ('FINLANDIA', '3'),
    ('FLORAL', '4'),
    ('FRAY PEÑA', '2'),
    ('GUABINAS', '1'),
    ('GUACANDA', '4'),
    ('HACIENDA VERDE', '1'),
    ('INVIYUMBO SAN JORGE', '1'),
    ('JORGE ELIECER GAITAN', '4'),
    ('JUAN PABLO II', '1'),
    ('LA BUITRERA', 'ZONA CENTRO'),
    ('LA CEIBA', '4'),
    ('LA ESTANCIA', '1'),
    ('LA NUEVA ESTANCIA', '1'),
    ('LA OLGA', 'ZONA SUR'),
    ('LA SULTANA', '4'),
    ('LAGUNA SECA', 'ZONA SUR'),
    ('LAS AMÉRICAS', '1'),
    ('LAS CRUCES', '3'),
    ('LAS VEGAS', '4'),
    ('LLERAS', '4'),
    ('MADRIGAL', '4'),
    ('MANGA VIEJA', 'ZONA NORTE'),
    ('MENGA', 'ZONA SUR'),
    ('MIRAVALLE', 'ZONA SUR'),
    ('MIRAVALLE DAPA', 'ZONA SUR'),
    ('MIRAVALLE NORTE', 'ZONA NORTE'),
    ('MONTAÑITAS', 'ZONA CENTRO'),
    ('MULALÓ', 'ZONA NORTE'),
    ('MUNICIPAL', '4'),
    ('NUESTRA SEÑORA DE GUADALUPE', '4'),
    ('NUEVO HORIZONTE', '3'),
    ('PANORAMA', '1'),
    ('PARQUES DEL PINAR', '1'),
    ('PASO DE LA TORRE', 'ZONA NORTE'),
    ('PASOANCHO', '3'),
    ('PEDREGAL', '3'),
    ('PILAS DAPA', 'ZONA SUR'),
    ('PILES', 'ZONA CENTRO'),
    ('PLATANARES', 'ZONA NORTE'),
    ('PORTALES DE YUMBO', '4'),
    ('PUERTO ISAAC', '1'),
    ('PUERTO RICO', 'ZONA CENTRO'),
    ('RINCÓN DAPA', 'ZONA SUR'),
    ('RIVERAS DE YUMBO', '3'),
    ('SALAZAR', 'ZONA CENTRO'),
    ('SAN FERNANDO', '3'),
    ('SAN JORGE', '1'),
    ('SAN JOSÉ', 'ZONA CENTRO'),
    ('SAN MARCOS', 'ZONA NORTE'),
    ('SANTA INÉS', 'ZONA CENTRO'),
    ('TELECOM', 'ZONA CENTRO'),
    ('TRINIDAD', '3'),
    ('TRINIDAD I', '3'),
    ('URBANIZACIÓN CARLOS PIZARRO', '4'),
    ('URIBE URIBE', '2'),
    ('XIXAOLA', 'ZONA SUR'),
    ('YUMBILLO', 'ZONA CENTRO'),
)

_ZONE_CHECK_SQL = "zone IN ({})".format(", ".join(f"'{z}'" for z in ZONES))


def _timestamps(*, updated_by: str | None) -> list:
    cols: list = [
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    ]
    if updated_by is not None:
        cols += [
            sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(
                ["updated_by_user_id"],
                ["users.id"],
                name=f"fk_{updated_by}_updated_by",
                ondelete="SET NULL",
            ),
        ]
    return cols


def upgrade() -> None:
    # 1. Barrio catalog ------------------------------------------------------
    barrios = op.create_table(
        "imderty_barrios",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("zone", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        *_timestamps(updated_by="imderty_barrios"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_imderty_barrios_name"),
        sa.CheckConstraint(_ZONE_CHECK_SQL, name="ck_imderty_barrios_zone"),
    )

    # 2. Identification block (1:1 athlete) ----------------------------------
    op.create_table(
        "athlete_imderty_profiles",
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("first_surname", sa.String(100), nullable=True),
        sa.Column("second_surname", sa.String(100), nullable=True),
        sa.Column("surname_split_confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("surname_split_confirmed_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "document_type",
            sa.Enum(*DOCUMENT_TYPES, name="imdertydocumenttype"),
            nullable=True,
        ),
        sa.Column("document_number", sa.String(20), nullable=True),
        sa.Column("address", sa.String(200), nullable=True),
        sa.Column("barrio_id", sa.Integer(), nullable=True),
        sa.Column(
            "other_municipality", sa.Boolean(), nullable=False, server_default="0"
        ),
        sa.Column("school", sa.String(150), nullable=True),
        sa.Column("grade", sa.Enum(*GRADES, name="imdertygrade"), nullable=True),
        sa.Column("eps", sa.String(100), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        *_timestamps(updated_by="athlete_imderty_profiles"),
        sa.PrimaryKeyConstraint("athlete_id"),
        sa.ForeignKeyConstraint(
            ["athlete_id"],
            ["athletes.id"],
            name="fk_athlete_imderty_profiles_athlete",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["surname_split_confirmed_by_user_id"],
            ["users.id"],
            name="fk_athlete_imderty_profiles_surname_confirmed_by",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["barrio_id"],
            ["imderty_barrios.id"],
            name="fk_athlete_imderty_profiles_barrio",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "NOT (other_municipality = 1 AND barrio_id IS NOT NULL)",
            name="ck_athlete_imderty_profiles_barrio_xor_other",
        ),
    )
    op.create_index(
        "ix_athlete_imderty_profiles_barrio_id",
        "athlete_imderty_profiles",
        ["barrio_id"],
    )

    # 3. Guardian authorization log (append-only) ----------------------------
    op.create_table(
        "athlete_sensitive_authorizations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("guardian_user_id", sa.Integer(), nullable=False),
        sa.Column("authorized_on", sa.Date(), nullable=False),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(), nullable=True),
        sa.Column("withdrawn_by_user_id", sa.Integer(), nullable=True),
        sa.Column("active_key", sa.Integer(), nullable=True),
        *_timestamps(updated_by=None),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["athlete_id"],
            ["athletes.id"],
            name="fk_athlete_sensitive_authorizations_athlete",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["guardian_user_id"],
            ["users.id"],
            name="fk_athlete_sensitive_authorizations_guardian",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"],
            ["users.id"],
            name="fk_athlete_sensitive_authorizations_recorded_by",
        ),
        sa.ForeignKeyConstraint(
            ["withdrawn_by_user_id"],
            ["users.id"],
            name="fk_athlete_sensitive_authorizations_withdrawn_by",
        ),
        sa.UniqueConstraint(
            "active_key", name="uq_athlete_sensitive_authorizations_active_key"
        ),
    )
    op.create_index(
        "ix_athlete_sensitive_authorizations_athlete_id",
        "athlete_sensitive_authorizations",
        ["athlete_id"],
    )

    # 4. Sensitive block (1:1 athlete, only while authorized) ----------------
    op.create_table(
        "athlete_sensitive_data",
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("authorization_id", sa.Integer(), nullable=False),
        sa.Column(
            "ethnicity",
            sa.Enum(*ETHNICITIES, name="imdertyethnicity"),
            nullable=False,
        ),
        sa.Column(
            "disability",
            sa.Enum(*DISABILITIES, name="imdertydisability"),
            nullable=False,
        ),
        sa.Column(
            "conflict_victim", sa.Enum(*YES_NO, name="imdertyyesno"), nullable=True
        ),
        *_timestamps(updated_by="athlete_sensitive_data"),
        sa.PrimaryKeyConstraint("athlete_id"),
        sa.ForeignKeyConstraint(
            ["athlete_id"],
            ["athletes.id"],
            name="fk_athlete_sensitive_data_athlete",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["authorization_id"],
            ["athlete_sensitive_authorizations.id"],
            name="fk_athlete_sensitive_data_authorization",
        ),
    )
    op.create_index(
        "ix_athlete_sensitive_data_authorization_id",
        "athlete_sensitive_data",
        ["authorization_id"],
    )

    # 5. Saved header defaults (1:1 club) ------------------------------------
    op.create_table(
        "club_imderty_settings",
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("contractor_name", sa.String(200), nullable=True),
        sa.Column("venue", sa.String(200), nullable=True),
        sa.Column("training_days", sa.String(120), nullable=True),
        sa.Column("schedule", sa.String(120), nullable=True),
        # MySQL forbids a literal DEFAULT on JSON; the ORM supplies ``[]``.
        sa.Column("programs", sa.JSON(), nullable=False),
        *_timestamps(updated_by="club_imderty_settings"),
        sa.PrimaryKeyConstraint("club_id"),
        sa.ForeignKeyConstraint(
            ["club_id"],
            ["clubs.id"],
            name="fk_club_imderty_settings_club",
            ondelete="CASCADE",
        ),
    )

    # 6. Primary contact mark on the guardian link ---------------------------
    with op.batch_alter_table("parent_athlete") as batch_op:
        batch_op.add_column(
            sa.Column("primary_contact_key", sa.Integer(), nullable=True)
        )
        batch_op.create_unique_constraint(
            "uq_parent_athlete_primary_contact_key", ["primary_contact_key"]
        )

    # 7. Seed the barrio catalog (bound parameters via bulk_insert) ----------
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    op.bulk_insert(
        barrios,
        [
            {
                "name": name,
                "zone": zone,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
            for name, zone in BARRIOS
        ],
    )


def downgrade() -> None:
    with op.batch_alter_table("parent_athlete") as batch_op:
        batch_op.drop_constraint(
            "uq_parent_athlete_primary_contact_key", type_="unique"
        )
        batch_op.drop_column("primary_contact_key")

    op.drop_table("club_imderty_settings")
    # DROP TABLE takes its indexes along; dropping an FK-backing index first
    # would fail on MySQL.
    op.drop_table("athlete_sensitive_data")
    op.drop_table("athlete_sensitive_authorizations")
    op.drop_table("athlete_imderty_profiles")
    # Dropping the catalog removes the seeded rows with it.
    op.drop_table("imderty_barrios")
