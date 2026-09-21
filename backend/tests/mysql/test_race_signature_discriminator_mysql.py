"""Revisión a7c3e5d91f20 — UNIQUE de ``race_competitor_signatures`` sobre
``(normalized_name, club_norm, city_norm, discriminator)`` en MySQL real
(feature 044, decisión del dueño 2026-09-21 "separar por categoría").

Por qué MySQL real: la garantía depende de que ``discriminator`` sea
``NOT NULL DEFAULT ''``. En MySQL dos ``NULL`` son distintos dentro de una
clave única, así que el caso crítico es la cuaterna con cadenas vacías, que
sqlite no reproduce con la misma semántica de motor.

Sin ``TEST_DATABASE_URL`` (mysql+aiomysql://…, base terminada en ``_test``)
el módulo se salta solo vía ``mysql_session``. Correr con::

    TEST_DATABASE_URL="mysql+aiomysql://root:testroot@127.0.0.1:3306/trocha_ruta_test" \\
        pytest -m mysql -q tests/mysql/test_race_signature_discriminator_mysql.py

Nombres sintéticos. Rango de ids 944_000+ para no chocar con otros módulos
``mysql`` que comparten la sesión.
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.race_competitor import RaceCompetitor
from app.models.race_competitor_signature import RaceCompetitorSignature

pytestmark = pytest.mark.mysql

_PARENT_ID = 944_001
_CHILD_ID = 944_002
_EMPTY_ID = 944_003


def _sig(competitor_id: int, name: str, discriminator: str, club: str = "club andino",
         city: str = "cali") -> RaceCompetitorSignature:
    return RaceCompetitorSignature(
        competitor_id=competitor_id,
        normalized_name=name,
        club_norm=club,
        city_norm=city,
        discriminator=discriminator,
        first_season=2025,
        last_season=2025,
    )


async def test_distinct_discriminators_coexist_and_duplicates_collide(
    mysql_session: AsyncSession,
) -> None:
    name = "mateo ficticio igual 944"
    mysql_session.add_all(
        [
            RaceCompetitor(id=_PARENT_ID, normalized_name=name, display_name="Mateo Ficticio Igual"),
            RaceCompetitor(id=_CHILD_ID, normalized_name=name, display_name="Mateo Ficticio Igual"),
        ]
    )
    await mysql_session.commit()
    mysql_session.add_all(
        [_sig(_PARENT_ID, name, "M:30-39@2025"), _sig(_CHILD_ID, name, "M:9-10@2025")]
    )
    await mysql_session.commit()

    mysql_session.add(_sig(_CHILD_ID, name, "M:9-10@2025"))
    with pytest.raises(IntegrityError):
        await mysql_session.commit()
    await mysql_session.rollback()


async def test_all_empty_quadruple_collides(mysql_session: AsyncSession) -> None:
    """Caso crítico: club, ciudad y discriminador vacíos — con NULL el
    UNIQUE no protegería; con '' sí."""
    name = "sin club ficticio 944"
    mysql_session.add(RaceCompetitor(id=_EMPTY_ID, normalized_name=name, display_name="Sin Club"))
    await mysql_session.commit()
    mysql_session.add(_sig(_EMPTY_ID, name, "", club="", city=""))
    await mysql_session.commit()

    mysql_session.add(_sig(_EMPTY_ID, name, "", club="", city=""))
    with pytest.raises(IntegrityError):
        await mysql_session.commit()
    await mysql_session.rollback()
