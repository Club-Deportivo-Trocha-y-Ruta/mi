"""T085 — cobertura MySQL real del cambio de identidad de la feature 044
(histórico Copa Valle 2024-2025): defaults de la firma de identidad, el
UNIQUE eliminado de ``race_competitors.normalized_name``, las tres columnas
congeladas de ``race_results`` y los dos enums de revisión de identidad.

Por qué esto necesita MySQL real y no basta con la vía offline (aiosqlite):

- ``club_norm``/``city_norm``/``discriminator`` de ``race_competitor_signatures``
  son ``NOT NULL DEFAULT ''``; el caso interesante es qué pasa cuando el
  INSERT los omite del todo y depende del ``server_default`` del motor — un
  INSERT vía ORM (que siempre manda el default de Python) no lo ejerce.
  sqlite además trata ``server_default=text("''")`` de forma menos estricta.
- El UNIQUE de ``race_competitors.normalized_name`` se eliminó a propósito
  (dos homónimos ya no se fusionan). Confirmar que el motor de verdad no
  tiene ese UNIQUE — y que sí quedó el índice simple — es una pregunta sobre
  el DDL real, no sobre el ORM.
- ``raceidentitycandidatekind`` / ``raceidentitycandidatestate`` son ENUM
  nativos de MySQL; sqlite los trata como texto libre y no valida los
  valores permitidos.

Este archivo NO duplica ``test_race_signature_discriminator_mysql.py``: ese
cubre la colisión del UNIQUE de 4 columnas (incluida la cuaterna
"todo vacío") vía ORM. Aquí se cubre el camino que ese archivo no ejerce
— el ``server_default`` cuando el INSERT omite las columnas — más los otros
tres puntos de T085 que ningún archivo mysql existente cubre todavía.

Sin ``TEST_DATABASE_URL`` (mysql+aiomysql://…, base terminada en ``_test``)
este módulo se salta solo vía la fixture ``mysql_session`` de
``tests/conftest.py``. Correr con::

    TEST_DATABASE_URL="mysql+aiomysql://root:testroot@127.0.0.1:3306/trocha_ruta_test" \\
        pytest -m mysql -q tests/mysql/test_race_history_models.py

Nombres sintéticos, ninguno real. Rango de ids 945_000+ (feature 044,
distinto del 943_000+ de la 043 y del 944_000+ de
``test_race_signature_discriminator_mysql.py``) para no colisionar con otra
fila de ``users``/``race_series``/``race_categories``/``race_events``/
``race_competitors`` de otro módulo marcado ``mysql`` dentro de la misma
corrida (``mysql_session`` es de alcance de sesión de pytest).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.race_competitor import RaceCompetitor
from app.models.race_competitor_signature import RaceCompetitorSignature
from app.models.race_identity_candidate import (
    IdentityCandidateKind,
    IdentityCandidateState,
    RaceIdentityCandidate,
)
from app.models.race_result import RaceResult, ResultStatus
from app.models.user import UserRole
from tests.fixtures.race_history_fixtures import (
    create_race_category,
    create_race_competitor,
    create_race_event,
    create_race_series,
    create_user,
)

pytestmark = pytest.mark.mysql

_COACH_ID = 945_001
_SERIES_ID = 945_000
_CATEGORY_ID = 945_000


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def scenario(mysql_session: AsyncSession) -> dict[str, int]:
    """Un entrenador + una serie + una categoría, sembrados una sola vez para
    todo el módulo (``mysql_session`` es de alcance de sesión de pytest)."""
    await create_user(
        mysql_session,
        user_id=_COACH_ID,
        role=UserRole.coach,
        first_name="Entrenador",
        last_name="Prueba044Models",
    )
    await create_race_series(
        mysql_session,
        series_id=_SERIES_ID,
        season_year=2024,
        name="Serie Prueba Histórico 044",
    )
    await create_race_category(
        mysql_session,
        category_id=_CATEGORY_ID,
        code="INF_B_945_HIST",
        label="Infantil B Prueba Histórico",
    )
    await mysql_session.commit()
    return {"coach_id": _COACH_ID, "series_id": _SERIES_ID, "category_id": _CATEGORY_ID}


# ---------------------------------------------------------------------------
# 1. server_default de la firma cuando el INSERT omite las tres columnas
# ---------------------------------------------------------------------------


async def test_signature_server_default_lands_as_empty_string_not_null(
    mysql_session: AsyncSession, scenario: dict[str, int]
) -> None:
    """INSERT crudo que omite ``club_norm``/``city_norm``/``discriminator``
    del todo — depende exclusivamente del ``server_default=text("''")`` del
    motor, no del default de Python que un INSERT vía ORM habría mandado de
    todas formas.

    ``created_at``/``updated_at`` de ``race_competitors`` y ``created_at`` de
    ``race_competitor_signatures`` sólo tienen default de Python
    (``default=lambda: ...``, sin ``server_default``) — un INSERT crudo que
    los omite choca contra NOT NULL (error 1364 en MySQL real), a diferencia
    de club_norm/city_norm/discriminator que sí declaran
    ``server_default=text("''")``. Se mandan explícitos con
    ``UTC_TIMESTAMP()`` para no reintroducir esa dependencia del ORM."""
    competitor_id = 945_101
    await mysql_session.execute(
        sa_text(
            "INSERT INTO race_competitors "
            "(id, normalized_name, display_name, created_at, updated_at) "
            "VALUES (:id, :name, :display, UTC_TIMESTAMP(), UTC_TIMESTAMP())"
        ),
        {"id": competitor_id, "name": "firma default 945", "display": "Firma Default"},
    )
    await mysql_session.execute(
        sa_text(
            "INSERT INTO race_competitor_signatures "
            "(competitor_id, normalized_name, first_season, last_season, created_at) "
            "VALUES (:competitor_id, :name, :first_season, :last_season, UTC_TIMESTAMP())"
        ),
        {
            "competitor_id": competitor_id,
            "name": "firma default 945",
            "first_season": 2024,
            "last_season": 2024,
        },
    )
    await mysql_session.commit()

    row = (
        await mysql_session.execute(
            select(RaceCompetitorSignature)
            .where(RaceCompetitorSignature.competitor_id == competitor_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()

    assert row.club_norm == ""
    assert row.city_norm == ""
    assert row.discriminator == ""
    assert row.club_norm is not None
    assert row.city_norm is not None
    assert row.discriminator is not None


# ---------------------------------------------------------------------------
# 2. UNIQUE eliminado de race_competitors.normalized_name + índice simple
# ---------------------------------------------------------------------------


async def test_competitors_normalized_name_not_unique_but_indexed(
    mysql_session: AsyncSession, scenario: dict[str, int]
) -> None:
    """Dos homónimos: el INSERT no debe chocar contra ningún UNIQUE (se
    eliminó a propósito en la feature 044). El índice simple debe seguir
    existiendo para que la búsqueda del resolver de identidad no haga table
    scan."""
    homonym_name = "homonimo prueba 945"
    await create_race_competitor(
        mysql_session,
        competitor_id=945_201,
        normalized_name=homonym_name,
        display_name="Homónimo Uno Prueba",
    )
    await create_race_competitor(
        mysql_session,
        competitor_id=945_202,
        normalized_name=homonym_name,
        display_name="Homónimo Dos Prueba",
    )
    await mysql_session.commit()

    rows = (
        await mysql_session.execute(
            select(RaceCompetitor).where(RaceCompetitor.normalized_name == homonym_name)
        )
    ).scalars().all()
    assert {r.id for r in rows} == {945_201, 945_202}

    index_rows = (
        await mysql_session.execute(sa_text("SHOW INDEX FROM race_competitors"))
    ).fetchall()
    by_name = {row[2]: row for row in index_rows}  # Key_name -> row
    assert "ix_race_competitors_normalized_name" in by_name
    # Non_unique column (index 1 en SHOW INDEX) debe ser 1 (no-único).
    assert by_name["ix_race_competitors_normalized_name"][1] == 1
    assert "PRIMARY" not in {
        row[2] for row in index_rows if row[4] == "normalized_name" and row[2] != "ix_race_competitors_normalized_name"
    }


# ---------------------------------------------------------------------------
# 3. Columnas congeladas de race_results — ida y vuelta
# ---------------------------------------------------------------------------


async def test_race_result_frozen_columns_round_trip(
    mysql_session: AsyncSession, scenario: dict[str, int]
) -> None:
    event_id = 945_301
    competitor_id = 945_301
    await create_race_event(
        mysql_session,
        event_id=event_id,
        series_id=scenario["series_id"],
        sequence_number=1,
        name="Válida Prueba Congeladas 945",
        created_by_user_id=scenario["coach_id"],
    )
    await create_race_competitor(
        mysql_session,
        competitor_id=competitor_id,
        normalized_name="corredor congeladas 945",
        display_name="Corredor Congeladas Prueba",
    )
    mysql_session.add(
        RaceResult(
            id=945_301,
            event_id=event_id,
            category_id=scenario["category_id"],
            competitor_id=competitor_id,
            position=1,
            status=ResultStatus.FINISHED,
            race_time_ms=1_800_000,
            points_awarded=40,
            category_label_raw="Infantil B (como se imprimió en 2024)",
            category_age_min_raw=11,
            category_age_max_raw=12,
            created_by_user_id=scenario["coach_id"],
        )
    )
    await mysql_session.commit()

    row = (
        await mysql_session.execute(
            select(RaceResult)
            .where(RaceResult.id == 945_301)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()

    assert row.category_label_raw == "Infantil B (como se imprimió en 2024)"
    assert row.category_age_min_raw == 11
    assert row.category_age_max_raw == 12

    # Editar el catálogo vigente NO debe tocar lo ya congelado — round trip
    # tras un cambio ajeno confirma que no hay trigger ni columna calculada
    # escondiendo una relectura del catálogo.
    await create_race_category(
        mysql_session,
        category_id=scenario["category_id"] + 1,
        code="INF_B_945_HIST_EDITADA",
        label="Infantil B Renombrada 2026",
    )
    await mysql_session.commit()
    row_after = (
        await mysql_session.execute(
            select(RaceResult)
            .where(RaceResult.id == 945_301)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert row_after.category_label_raw == "Infantil B (como se imprimió en 2024)"
    assert row_after.category_age_min_raw == 11
    assert row_after.category_age_max_raw == 12


# ---------------------------------------------------------------------------
# 4. Los dos enums nativos de revisión de identidad — todos los valores
# ---------------------------------------------------------------------------


async def test_identity_candidate_enums_store_all_values(
    mysql_session: AsyncSession, scenario: dict[str, int]
) -> None:
    kinds = list(IdentityCandidateKind)
    states = list(IdentityCandidateState)
    assert {k.value for k in kinds} == {"same_person_suspect", "homonym_suspect"}
    assert {s.value for s in states} == {"pending", "same_person", "different_people"}

    created_ids: list[int] = []
    base_id = 945_401
    for offset, (kind, state) in enumerate(
        [(k, s) for k in kinds for s in states]
    ):
        candidate_id = base_id + offset
        created_ids.append(candidate_id)
        mysql_session.add(
            RaceIdentityCandidate(
                id=candidate_id,
                kind=kind,
                pair_hash=f"{candidate_id:064d}",
                left_record={"normalized_name": "izquierda prueba 945", "club": ""},
                right_record={"normalized_name": "derecha prueba 945", "club": ""},
                score=90,
                signals=["token_set_ratio"],
                state=state,
                decided_by_user_id=scenario["coach_id"] if state != IdentityCandidateState.pending else None,
                decided_at=datetime.now(timezone.utc) if state != IdentityCandidateState.pending else None,
                linked_athlete_involved=False,
            )
        )
    await mysql_session.commit()

    rows = (
        await mysql_session.execute(
            select(RaceIdentityCandidate).where(RaceIdentityCandidate.id.in_(created_ids))
        )
    ).scalars().all()
    assert len(rows) == len(created_ids)
    stored_pairs = {(row.kind.value, row.state.value) for row in rows}
    expected_pairs = {(k.value, s.value) for k in kinds for s in states}
    assert stored_pairs == expected_pairs
