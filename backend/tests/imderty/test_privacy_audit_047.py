"""Regression tests for the feature-047 privacy audit (T051, privacy-audit.md).

P-1: every free-text field of the IMDERTY write schemas carries a
``max_length`` equal to its column. Without it an over-long value reached
the database; on MySQL (strict mode) the flush fails with "Data too long"
and the unhandled-exception log prints the SQLAlchemy error, whose
``[parameters: ...]`` block holds the submitted value (a minor's document
number, address or phone). SQLite does not enforce ``String(n)``, so the
default lane can only prove the request is rejected *before* the database,
with a 422 that does not echo the value.

All values are fictitious (Ley 1581).
"""
from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.imderty import (
    AthleteImdertyProfile,
    ClubImdertySettings,
    ImdertyBarrio,
)
from app.schemas.imderty import (
    BarrioCreate,
    BarrioUpdate,
    ClubImdertySettingsUpdate,
    ImdertyProfileUpdate,
    ImdertySheetHeader,
)

from tests.imderty.conftest import _TABLES, CLUB_ID

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def imderty_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Conftest's engine plus the IMDERTY tables these tests read back."""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    names = (
        *_TABLES,
        "imderty_barrios",
        "athlete_imderty_profiles",
        "athlete_sensitive_authorizations",
        "athlete_sensitive_data",
        "club_imderty_settings",
    )
    tables = [Base.metadata.tables[t] for t in names]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()

_SCHEMA_TO_MODEL = (
    (ImdertyProfileUpdate, AthleteImdertyProfile),
    (BarrioCreate, ImdertyBarrio),
    (BarrioUpdate, ImdertyBarrio),
    (ClubImdertySettingsUpdate, ClubImdertySettings),
    (ImdertySheetHeader, ClubImdertySettings),
)


def _max_length(field_info) -> int | None:
    for meta in field_info.metadata:
        value = getattr(meta, "max_length", None)
        if value is not None:
            return value
    return None


@pytest.mark.parametrize(("schema", "model"), _SCHEMA_TO_MODEL)
async def test_every_string_field_is_capped_at_its_column_length(schema, model) -> None:
    columns = model.__table__.columns
    checked = 0
    for name, field_info in schema.model_fields.items():
        if name not in columns:
            continue
        column_type = columns[name].type
        length = getattr(column_type, "length", None)
        # Enum columns also carry a length; only free-text columns matter.
        if length is None or getattr(column_type, "enums", None):
            continue
        assert _max_length(field_info) == length, f"{schema.__name__}.{name}"
        checked += 1
    assert checked > 0, schema.__name__


_OVERLONG_FIELDS = {
    "document_number": "9" * 21,
    "phone": "3" * 21,
    "address": "CALLE FICTICIA " + "X" * 200,
    "eps": "EPS FICTICIA " + "Y" * 100,
    "school": "COLEGIO FICTICIO " + "Z" * 150,
    "first_surname": "FICTICIO" + "W" * 100,
}


@pytest.mark.parametrize(("field", "value"), sorted(_OVERLONG_FIELDS.items()))
async def test_overlong_profile_value_is_rejected_without_echo(
    coach_client, imderty_scenario, field, value
) -> None:
    athlete_id = imderty_scenario.parent_athlete_one_id
    response = await coach_client.put(
        f"/api/athletes/{athlete_id}/imderty-profile", json={field: value}
    )
    assert response.status_code == 422
    assert value not in response.text
    assert value[:12] not in response.text

    # Nothing was written: the profile stays empty for that field.
    read = await coach_client.get(f"/api/athletes/{athlete_id}/imderty-profile")
    assert read.status_code == 200
    assert read.json()[field] is None


async def test_overlong_settings_value_is_rejected_without_echo(coach_client) -> None:
    value = "CONTRATISTA FICTICIO " + "Q" * 200
    response = await coach_client.put(
        f"/api/clubs/{CLUB_ID}/imderty-settings", json={"contractor_name": value}
    )
    assert response.status_code == 422
    assert value[:25] not in response.text

    read = await coach_client.get(f"/api/clubs/{CLUB_ID}/imderty-settings")
    assert read.status_code == 200
    assert read.json()["contractor_name"] is None
