"""Tests del servicio de audiencias de calendario.

Cubre: resolve_athletes para cada AudienceType, visibilidad por padre,
privacidad (padre A no ve eventos del hijo de padre B).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.calendar_event import AudienceType, EventAudience, EventType
from app.services.calendar.audiences import (
    any_athlete_in_audience,
    event_visible_to_athlete,
    resolve_athletes,
    set_audiences,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(audiences=None, club_id: int = 1):
    ev = MagicMock()
    ev.id = 10
    ev.club_id = club_id
    ev.event_type = EventType.CLUB_EVENT
    ev.audiences = audiences or []
    return ev


def _make_audience(atype: AudienceType, avalue: dict | None = None):
    a = MagicMock(spec=EventAudience)
    a.audience_type = atype
    a.audience_value = avalue or {}
    return a


def _make_athlete(athlete_id: int, club_id: int = 1, birth_year: int = 2012, sex: str = "M"):
    ath = MagicMock()
    ath.id = athlete_id
    ath.club_id = club_id
    birth_date = MagicMock()
    birth_date.year = birth_year
    ath.birth_date = birth_date
    sex_m = MagicMock()
    sex_m.value = sex
    ath.sex = sex_m
    return ath


def _make_db_returning(rows):
    """Crea un db AsyncMock que retorna 'rows' al ejecutar select."""
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    db.execute = AsyncMock(return_value=result)
    db.delete = AsyncMock()
    db.add = MagicMock()
    return db


# ---------------------------------------------------------------------------
# set_audiences
# ---------------------------------------------------------------------------


class TestSetAudiences:
    async def test_set_audiences_borra_y_reinserta(self):
        old_audience = MagicMock()
        event = _make_event(audiences=[old_audience])
        db = AsyncMock()
        db.delete = AsyncMock()
        db.add = MagicMock()

        from app.schemas.calendar import AudienceCreate

        specs = [
            AudienceCreate(
                audience_type=AudienceType.ALL_CLUB,
                audience_value={},
            )
        ]
        await set_audiences(db, event, specs)

        db.delete.assert_awaited_once_with(old_audience)
        db.add.assert_called_once()

    async def test_set_audiences_lista_vacia(self):
        event = _make_event(audiences=[])
        db = AsyncMock()
        db.delete = AsyncMock()
        db.add = MagicMock()

        await set_audiences(db, event, [])

        db.delete.assert_not_awaited()
        db.add.assert_not_called()


# ---------------------------------------------------------------------------
# resolve_athletes — ALL_CLUB
# ---------------------------------------------------------------------------


class TestResolveAthletesAllClub:
    async def test_all_club_retorna_todos_del_club(self):
        ath1 = _make_athlete(1)
        ath2 = _make_athlete(2)
        audience = _make_audience(AudienceType.ALL_CLUB, {})
        event = _make_event(audiences=[audience], club_id=1)
        db = _make_db_returning([ath1, ath2])

        result = await resolve_athletes(db, event)

        assert len(result) == 2
        assert {a.id for a in result} == {1, 2}

    async def test_all_club_club_vacio(self):
        audience = _make_audience(AudienceType.ALL_CLUB, {})
        event = _make_event(audiences=[audience], club_id=99)
        db = _make_db_returning([])

        result = await resolve_athletes(db, event)

        assert result == []


# ---------------------------------------------------------------------------
# resolve_athletes — CATEGORY
# ---------------------------------------------------------------------------


class TestResolveAthletesCategory:
    async def test_category_filtra_por_categoria_fcc(self):
        # Atleta nacido en 2012, masculino → categoría "Pre-juvenil A" aprox
        ath_target = _make_athlete(1, birth_year=2012, sex="M")
        ath_other = _make_athlete(2, birth_year=2015, sex="M")

        audience = _make_audience(
            AudienceType.CATEGORY,
            {"category": "Pre-juvenil A"},
        )
        event = _make_event(audiences=[audience], club_id=1)

        with patch(
            "app.services.calendar.audiences.get_category",
            side_effect=lambda year, sex: "Pre-juvenil A" if year == 2012 else "Juvenil B",
        ):
            db = _make_db_returning([ath_target, ath_other])
            result = await resolve_athletes(db, event)

        assert len(result) == 1
        assert result[0].id == 1

    async def test_category_sin_matches(self):
        ath = _make_athlete(1, birth_year=2012, sex="M")
        audience = _make_audience(AudienceType.CATEGORY, {"category": "Veteranos"})
        event = _make_event(audiences=[audience], club_id=1)

        with patch(
            "app.services.calendar.audiences.get_category",
            return_value="Pre-juvenil A",
        ):
            db = _make_db_returning([ath])
            result = await resolve_athletes(db, event)

        assert result == []


# ---------------------------------------------------------------------------
# resolve_athletes — ATHLETE_LIST
# ---------------------------------------------------------------------------


class TestResolveAthletesAthleteList:
    async def test_athlete_list_retorna_ids_correctos(self):
        ath1 = _make_athlete(10)
        ath2 = _make_athlete(20)
        audience = _make_audience(
            AudienceType.ATHLETE_LIST, {"athlete_ids": [10, 20]}
        )
        event = _make_event(audiences=[audience], club_id=1)
        db = _make_db_returning([ath1, ath2])

        result = await resolve_athletes(db, event)

        assert {a.id for a in result} == {10, 20}

    async def test_athlete_list_ids_vacios(self):
        audience = _make_audience(AudienceType.ATHLETE_LIST, {"athlete_ids": []})
        event = _make_event(audiences=[audience], club_id=1)
        db = AsyncMock()

        result = await resolve_athletes(db, event)

        assert result == []
        db.execute.assert_not_awaited()


# ---------------------------------------------------------------------------
# resolve_athletes — INDIVIDUAL
# ---------------------------------------------------------------------------


class TestResolveAthletesIndividual:
    async def test_individual_retorna_un_atleta(self):
        ath = _make_athlete(5)
        audience = _make_audience(AudienceType.INDIVIDUAL, {"athlete_id": 5})
        event = _make_event(audiences=[audience], club_id=1)

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = ath
        db.execute = AsyncMock(return_value=result_mock)

        result = await resolve_athletes(db, event)

        assert len(result) == 1
        assert result[0].id == 5

    async def test_individual_sin_athlete_id(self):
        audience = _make_audience(AudienceType.INDIVIDUAL, {})
        event = _make_event(audiences=[audience], club_id=1)
        db = AsyncMock()

        result = await resolve_athletes(db, event)

        assert result == []

    async def test_individual_no_encontrado(self):
        audience = _make_audience(AudienceType.INDIVIDUAL, {"athlete_id": 999})
        event = _make_event(audiences=[audience], club_id=1)

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        result = await resolve_athletes(db, event)

        assert result == []


# ---------------------------------------------------------------------------
# resolve_athletes — Unión de múltiples audiencias (deduplicada)
# ---------------------------------------------------------------------------


class TestResolveAthletesDeduplication:
    async def test_union_deduplicada(self):
        ath1 = _make_athlete(1)
        ath2 = _make_athlete(2)

        audience_list = _make_audience(
            AudienceType.ATHLETE_LIST, {"athlete_ids": [1, 2]}
        )
        audience_individual = _make_audience(
            AudienceType.INDIVIDUAL, {"athlete_id": 1}
        )
        event = _make_event(audiences=[audience_list, audience_individual], club_id=1)

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalars.return_value.all.return_value = [ath1, ath2]
            else:
                result.scalar_one_or_none.return_value = ath1
            return result

        db = AsyncMock()
        db.execute = mock_execute

        result = await resolve_athletes(db, event)

        ids = [a.id for a in result]
        assert len(ids) == len(set(ids)), "No deben haber duplicados"
        assert set(ids) == {1, 2}


# ---------------------------------------------------------------------------
# event_visible_to_athlete
# ---------------------------------------------------------------------------


class TestEventVisibleToAthlete:
    async def test_visible_si_atleta_en_audiencia(self):
        ath = _make_athlete(7)
        audience = _make_audience(AudienceType.INDIVIDUAL, {"athlete_id": 7})
        event = _make_event(audiences=[audience], club_id=1)

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = ath
        db.execute = AsyncMock(return_value=result_mock)

        visible = await event_visible_to_athlete(db, event, 7)
        assert visible is True

    async def test_no_visible_si_atleta_fuera_de_audiencia(self):
        ath = _make_athlete(7)
        audience = _make_audience(AudienceType.INDIVIDUAL, {"athlete_id": 7})
        event = _make_event(audiences=[audience], club_id=1)

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = ath
        db.execute = AsyncMock(return_value=result_mock)

        visible = await event_visible_to_athlete(db, event, 99)
        assert visible is False


# ---------------------------------------------------------------------------
# any_athlete_in_audience — privacidad padre A vs padre B
# ---------------------------------------------------------------------------


class TestAnyAthleteInAudience:
    async def test_padre_con_hijo_en_audiencia(self):
        ath = _make_athlete(3)
        audience = _make_audience(AudienceType.ATHLETE_LIST, {"athlete_ids": [3]})
        event = _make_event(audiences=[audience], club_id=1)
        db = _make_db_returning([ath])

        result = await any_athlete_in_audience(db, event, athlete_ids=[3])
        assert result is True

    async def test_padre_b_sin_hijo_en_audiencia(self):
        """Privacidad: padre B (hijo_id=5) no ve evento de padre A (hijo_id=3)."""
        ath_a = _make_athlete(3)
        audience = _make_audience(AudienceType.ATHLETE_LIST, {"athlete_ids": [3]})
        event = _make_event(audiences=[audience], club_id=1)
        db = _make_db_returning([ath_a])

        # Padre B tiene hijo_id=5, que NO está en la audiencia
        result = await any_athlete_in_audience(db, event, athlete_ids=[5])
        assert result is False

    async def test_lista_vacia_retorna_false(self):
        audience = _make_audience(AudienceType.ALL_CLUB, {})
        event = _make_event(audiences=[audience], club_id=1)
        db = AsyncMock()

        result = await any_athlete_in_audience(db, event, athlete_ids=[])
        assert result is False
