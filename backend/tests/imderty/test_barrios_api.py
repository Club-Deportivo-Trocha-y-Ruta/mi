"""Pruebas de las rutas del catálogo de barrios IMDERTY (feature 047, T026).

Estas pruebas redefinen ``imderty_engine`` para incluir la tabla
``imderty_barrios`` (ausente de ``tests/imderty/conftest.py::_TABLES``,
compartida entre las historias) — las demás fixtures (escenario, fábrica de
cliente) se heredan sin cambios.

Cada test abre un ``async with imderty_client_factory(user_id)`` por actor,
en lugar de combinar las fixtures ``admin_client``/``coach_client`` en los
parámetros de un mismo test: ambas comparten ``app.dependency_overrides``
(un diccionario a nivel de módulo), así que instanciarlas juntas hace que la
segunda pise el override de la primera antes de que el cuerpo del test
llegue a usarla.
"""
from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base
from tests.imderty.conftest import _TABLES

pytestmark = pytest.mark.asyncio

_BARRIOS_TABLES = (*_TABLES, "imderty_barrios")


@pytest_asyncio.fixture
async def imderty_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Igual que la fixture de ``conftest.py``, más ``imderty_barrios``."""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _BARRIOS_TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


async def _create_barrio(
    imderty_client_factory,
    admin_user_id: int,
    *,
    name: str = "SAN FERNANDO",
    zone: str = "1",
    is_active: bool = True,
):
    async with imderty_client_factory(admin_user_id) as client:
        return await client.post(
            "/api/imderty/barrios",
            json={"name": name, "zone": zone, "is_active": is_active},
        )


async def test_coach_can_list_barrios(imderty_client_factory, imderty_scenario):
    async with imderty_client_factory(imderty_scenario.coach_user_id) as client:
        resp = await client.get("/api/imderty/barrios")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_coach_gets_403_on_create(imderty_client_factory, imderty_scenario):
    async with imderty_client_factory(imderty_scenario.coach_user_id) as client:
        resp = await client.post(
            "/api/imderty/barrios",
            json={"name": "SAN FERNANDO", "zone": "1", "is_active": True},
        )
    assert resp.status_code == 403


async def test_coach_gets_403_on_patch(imderty_client_factory, imderty_scenario):
    created = await _create_barrio(imderty_client_factory, imderty_scenario.admin_user_id)
    assert created.status_code == 201, created.text
    barrio_id = created.json()["id"]

    async with imderty_client_factory(imderty_scenario.coach_user_id) as client:
        resp = await client.patch(f"/api/imderty/barrios/{barrio_id}", json={"zone": "2"})
    assert resp.status_code == 403


async def test_admin_can_create_rename_remap_and_deactivate(
    imderty_client_factory, imderty_scenario
):
    admin_id = imderty_scenario.admin_user_id
    created = await _create_barrio(imderty_client_factory, admin_id)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "SAN FERNANDO"
    assert body["zone"] == "1"
    assert body["is_active"] is True
    barrio_id = body["id"]

    async with imderty_client_factory(admin_id) as client:
        renamed = await client.patch(
            f"/api/imderty/barrios/{barrio_id}", json={"name": "SAN FERNANDO ALTO"}
        )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "SAN FERNANDO ALTO"

    async with imderty_client_factory(admin_id) as client:
        remapped = await client.patch(
            f"/api/imderty/barrios/{barrio_id}", json={"zone": "ZONA NORTE"}
        )
    assert remapped.status_code == 200
    assert remapped.json()["zone"] == "ZONA NORTE"

    async with imderty_client_factory(admin_id) as client:
        deactivated = await client.patch(
            f"/api/imderty/barrios/{barrio_id}", json={"is_active": False}
        )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False


async def test_duplicate_name_returns_409(imderty_client_factory, imderty_scenario):
    admin_id = imderty_scenario.admin_user_id
    first = await _create_barrio(imderty_client_factory, admin_id)
    assert first.status_code == 201, first.text

    second = await _create_barrio(imderty_client_factory, admin_id, zone="2")
    assert second.status_code == 409


async def test_rename_to_duplicate_name_returns_409(
    imderty_client_factory, imderty_scenario
):
    admin_id = imderty_scenario.admin_user_id
    await _create_barrio(imderty_client_factory, admin_id)
    second = await _create_barrio(imderty_client_factory, admin_id, name="ACOPI", zone="2")
    barrio_id = second.json()["id"]

    async with imderty_client_factory(admin_id) as client:
        resp = await client.patch(
            f"/api/imderty/barrios/{barrio_id}", json={"name": "SAN FERNANDO"}
        )
    assert resp.status_code == 409


async def test_inactive_entries_hidden_by_default(
    imderty_client_factory, imderty_scenario
):
    admin_id = imderty_scenario.admin_user_id
    created = await _create_barrio(imderty_client_factory, admin_id)
    barrio_id = created.json()["id"]

    async with imderty_client_factory(admin_id) as client:
        await client.patch(f"/api/imderty/barrios/{barrio_id}", json={"is_active": False})

    async with imderty_client_factory(admin_id) as client:
        default_listing = await client.get("/api/imderty/barrios")
    assert default_listing.json() == []

    async with imderty_client_factory(admin_id) as client:
        full_listing = await client.get(
            "/api/imderty/barrios", params={"include_inactive": True}
        )
    names = [b["name"] for b in full_listing.json()]
    assert "SAN FERNANDO" in names


async def test_parent_gets_403(imderty_client_factory, imderty_scenario):
    async with imderty_client_factory(imderty_scenario.parent_user_id) as client:
        get_resp = await client.get("/api/imderty/barrios")
        post_resp = await client.post(
            "/api/imderty/barrios",
            json={"name": "SAN FERNANDO", "zone": "1", "is_active": True},
        )
    assert get_resp.status_code == 403
    assert post_resp.status_code == 403
