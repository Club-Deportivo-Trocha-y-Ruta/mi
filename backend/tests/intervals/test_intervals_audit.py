"""T030 — auditoría de las siete rutas mutantes de `/api/intervals`.

Contrato: ``specs/041-multi-coach-governance/contracts/audit-recording.md``
§4.11 (fila de intervalos de la matriz de instrumentación), §1.4 (reglas R1/R4/
R7), §1.6 (resolución de ``club_id``) y §1.7 (``META_ALLOWLIST``).

Rutas cubiertas:

  POST   /api/intervals/structures                    → interval_structure·create
  PUT    /api/intervals/structures/{id}               → interval_structure·update
  DELETE /api/intervals/structures/{id}               → interval_structure·delete
  POST   /api/intervals/templates                     → interval_template·create
  PUT    /api/intervals/templates/{id}                → interval_template·update
  PATCH  /api/intervals/templates/{id}/archive        → interval_template·archive
  POST   /api/intervals/templates/{id}/attach         → interval_template·link

Corre en la vía offline aiosqlite del arnés de ``tests/intervals/conftest.py``
(subconjunto de tablas + ``app.dependency_overrides``): no toca el fixture
``client`` de ``tests/conftest.py``, que exige MySQL real.

Privacidad (Ley 1581): el escenario usa club, entrenador y sesión ficticios;
las aserciones verifican explícitamente que ninguna fila lleve ``diff_json``
ni el valor del nombre de una plantilla.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditAction, AuditActorKind, AuditLog
from app.models.user import UserRole
from app.services.audit import AuditEntityType

from tests.intervals.conftest import (
    make_client,
    seed_club,
    seed_coach,
    seed_training_session,
)

BASE = "/api/intervals"
CLUB_ID = 1
COACH_ID = 10


# ---------------------------------------------------------------------------
# Helpers de escenario y de lectura del historial
# ---------------------------------------------------------------------------


async def _setup(session) -> int:
    """Club + entrenador + una sesión de entrenamiento; devuelve su id."""
    await seed_club(session, club_id=CLUB_ID)
    await seed_coach(session, user_id=COACH_ID, club_id=CLUB_ID)
    ts = await seed_training_session(
        session, club_id=CLUB_ID, created_by_user_id=COACH_ID
    )
    await session.commit()
    return ts.id


async def _audit_rows(session, entity_type: AuditEntityType | None = None):
    """Filas de ``audit_log``, opcionalmente filtradas por tipo de entidad."""
    stmt = select(AuditLog).order_by(AuditLog.id)
    if entity_type is not None:
        stmt = stmt.where(AuditLog.entity_type == entity_type.value)
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _block(
    *,
    position: int,
    block_type: str = "work",
    duration_s: int = 120,
    target_zone: str = "Z2",
    target_cadence_rpm: int = 80,
) -> dict:
    return {
        "position": position,
        "block_type": block_type,
        "duration_type": "fixed",
        "duration_s": duration_s,
        "target_zone": target_zone,
        "target_cadence_rpm": target_cadence_rpm,
        "repeat_group": None,
        "repeat_count": None,
    }


def _blocks(*, work_duration_s: int = 120) -> list[dict]:
    """Trío benigno calentamiento/trabajo/vuelta a la calma (Z1-Z2)."""
    return [
        _block(position=1, block_type="warmup", duration_s=300, target_zone="Z1",
               target_cadence_rpm=70),
        _block(position=2, block_type="work", duration_s=work_duration_s),
        _block(position=3, block_type="cooldown", duration_s=300, target_zone="Z1",
               target_cadence_rpm=65),
    ]


def _structure_payload(training_session_id: int, *, work_duration_s: int = 120) -> dict:
    return {
        "training_session_id": training_session_id,
        "target_age_band": "13-15",
        "age_gate_confirmed": False,
        "blocks": _blocks(work_duration_s=work_duration_s),
    }


def _structure_put_payload(*, work_duration_s: int = 120, band: str = "13-15") -> dict:
    return {
        "target_age_band": band,
        "age_gate_confirmed": False,
        "blocks": _blocks(work_duration_s=work_duration_s),
    }


def _template_payload(*, name: str = "Plantilla ficticia de intervalos") -> dict:
    return {
        "name": name,
        "target_age_band": "13-15",
        "mesocycle_phase": "base",
        "competition_proximity": "general",
        "blocks": _blocks(),
    }


# ===========================================================================
# Estructuras — create / update / delete
# ===========================================================================


@pytest.mark.asyncio
async def test_create_structure_registra_fila_create(session):
    ts_id = await _setup(session)

    async with make_client(session) as client:
        resp = await client.post(
            f"{BASE}/structures", json=_structure_payload(ts_id)
        )
    assert resp.status_code == 201, resp.text
    structure_id = resp.json()["id"]

    rows = await _audit_rows(session, AuditEntityType.interval_structure)
    assert len(rows) == 1
    row = rows[0]
    assert row.action == AuditAction.create
    assert row.entity_id == structure_id
    assert row.club_id == CLUB_ID
    # Acción de club, no de un atleta concreto (§1.6, cuarta columna de §4.11).
    assert row.athlete_id is None
    assert row.actor_user_id == COACH_ID
    assert row.actor_kind == AuditActorKind.user
    assert row.actor_role == UserRole.coach
    assert row.meta_json == {"related_entity_id": ts_id}
    # `interval_structure` no está en VALUE_ALLOWLIST: nunca hay valores.
    assert row.diff_json is None
    assert row.request_id


@pytest.mark.asyncio
async def test_update_structure_registra_update_con_nombres_de_campo(session):
    ts_id = await _setup(session)

    async with make_client(session) as client:
        created = await client.post(
            f"{BASE}/structures", json=_structure_payload(ts_id)
        )
        structure_id = created.json()["id"]
        resp = await client.put(
            f"{BASE}/structures/{structure_id}",
            json=_structure_put_payload(work_duration_s=240),
        )
    assert resp.status_code == 200, resp.text

    rows = await _audit_rows(session, AuditEntityType.interval_structure)
    assert [r.action for r in rows] == [AuditAction.create, AuditAction.update]
    update_row = rows[-1]
    assert update_row.entity_id == structure_id
    assert update_row.changed_fields == ["blocks"]
    assert update_row.diff_json is None
    # Una sola operación de negocio ⇒ una sola fila (R1).
    assert len([r for r in rows if r.action == AuditAction.update]) == 1


@pytest.mark.asyncio
async def test_update_structure_sin_cambios_no_escribe_fila(session):
    """Regla R7 (§1.4): un `update` sin cambios no fabrica historia."""
    ts_id = await _setup(session)

    async with make_client(session) as client:
        created = await client.post(
            f"{BASE}/structures", json=_structure_payload(ts_id)
        )
        structure_id = created.json()["id"]
        resp = await client.put(
            f"{BASE}/structures/{structure_id}", json=_structure_put_payload()
        )
    assert resp.status_code == 200, resp.text

    rows = await _audit_rows(session, AuditEntityType.interval_structure)
    assert [r.action for r in rows] == [AuditAction.create]


@pytest.mark.asyncio
async def test_update_structure_cambia_banda_registra_ese_nombre(session):
    ts_id = await _setup(session)

    async with make_client(session) as client:
        created = await client.post(
            f"{BASE}/structures", json=_structure_payload(ts_id)
        )
        structure_id = created.json()["id"]
        resp = await client.put(
            f"{BASE}/structures/{structure_id}",
            json={
                "target_age_band": "10-12",
                # La banda 10-12 exige confirmación explícita del age gate
                # (FR-007), así que también cambia ese campo.
                "age_gate_confirmed": True,
                "blocks": _blocks(),
            },
        )
    assert resp.status_code == 200, resp.text

    rows = await _audit_rows(session, AuditEntityType.interval_structure)
    update_row = rows[-1]
    assert update_row.action == AuditAction.update
    assert update_row.changed_fields == ["age_gate_confirmed", "target_age_band"]
    assert update_row.diff_json is None


@pytest.mark.asyncio
async def test_delete_structure_registra_fila_delete(session):
    ts_id = await _setup(session)

    async with make_client(session) as client:
        created = await client.post(
            f"{BASE}/structures", json=_structure_payload(ts_id)
        )
        structure_id = created.json()["id"]
        resp = await client.delete(f"{BASE}/structures/{structure_id}")
    assert resp.status_code == 204, resp.text

    rows = await _audit_rows(session, AuditEntityType.interval_structure)
    assert [r.action for r in rows] == [AuditAction.create, AuditAction.delete]
    delete_row = rows[-1]
    assert delete_row.entity_id == structure_id
    assert delete_row.club_id == CLUB_ID
    assert delete_row.meta_json == {"related_entity_id": ts_id}


@pytest.mark.asyncio
async def test_delete_structure_inexistente_no_escribe_fila(session):
    await _setup(session)

    async with make_client(session) as client:
        resp = await client.delete(f"{BASE}/structures/9999")
    assert resp.status_code == 404

    assert await _audit_rows(session) == []


# ===========================================================================
# Plantillas — create / update / archive / attach
# ===========================================================================


@pytest.mark.asyncio
async def test_create_template_registra_fila_create(session):
    await _setup(session)

    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/templates", json=_template_payload())
    assert resp.status_code == 201, resp.text
    template_id = resp.json()["id"]

    rows = await _audit_rows(session, AuditEntityType.interval_template)
    assert len(rows) == 1
    row = rows[0]
    assert row.action == AuditAction.create
    assert row.entity_id == template_id
    assert row.club_id == CLUB_ID
    assert row.athlete_id is None
    assert row.actor_user_id == COACH_ID
    assert row.meta_json is None
    assert row.diff_json is None


@pytest.mark.asyncio
async def test_update_template_registra_nombre_de_campo_sin_su_valor(session):
    """El NOMBRE `name` viaja en `changed_fields`; su valor, en ningún lado."""
    await _setup(session)
    secreto = "Plantilla renombrada ficticia"

    async with make_client(session) as client:
        created = await client.post(f"{BASE}/templates", json=_template_payload())
        template_id = created.json()["id"]
        resp = await client.put(
            f"{BASE}/templates/{template_id}",
            json=_template_payload(name=secreto),
        )
    assert resp.status_code == 200, resp.text

    rows = await _audit_rows(session, AuditEntityType.interval_template)
    assert [r.action for r in rows] == [AuditAction.create, AuditAction.update]
    update_row = rows[-1]
    assert update_row.changed_fields == ["name"]
    assert update_row.diff_json is None
    serializada = json.dumps(
        {
            "changed_fields": update_row.changed_fields,
            "diff_json": update_row.diff_json,
            "meta_json": update_row.meta_json,
        },
        ensure_ascii=False,
    )
    assert secreto not in serializada


@pytest.mark.asyncio
async def test_update_template_sin_cambios_no_escribe_fila(session):
    await _setup(session)

    async with make_client(session) as client:
        created = await client.post(f"{BASE}/templates", json=_template_payload())
        template_id = created.json()["id"]
        resp = await client.put(
            f"{BASE}/templates/{template_id}", json=_template_payload()
        )
    assert resp.status_code == 200, resp.text

    rows = await _audit_rows(session, AuditEntityType.interval_template)
    assert [r.action for r in rows] == [AuditAction.create]


@pytest.mark.asyncio
async def test_archive_y_desarchive_registran_estado_en_meta(session):
    """Ambas direcciones son `archive` (§4.11); `new_status` las distingue."""
    await _setup(session)

    async with make_client(session) as client:
        created = await client.post(f"{BASE}/templates", json=_template_payload())
        template_id = created.json()["id"]
        archivada = await client.patch(
            f"{BASE}/templates/{template_id}/archive", json={"is_archived": True}
        )
        desarchivada = await client.patch(
            f"{BASE}/templates/{template_id}/archive", json={"is_archived": False}
        )
    assert archivada.status_code == 200, archivada.text
    assert desarchivada.status_code == 200, desarchivada.text

    rows = await _audit_rows(session, AuditEntityType.interval_template)
    assert [r.action for r in rows] == [
        AuditAction.create,
        AuditAction.archive,
        AuditAction.archive,
    ]
    assert rows[1].meta_json == {"previous_status": "active", "new_status": "archived"}
    assert rows[2].meta_json == {"previous_status": "archived", "new_status": "active"}
    assert rows[1].changed_fields == ["is_archived"]
    assert rows[1].entity_id == template_id
    assert rows[1].club_id == CLUB_ID


@pytest.mark.asyncio
async def test_attach_template_registra_link_sobre_la_plantilla(session):
    ts_id = await _setup(session)

    async with make_client(session) as client:
        created = await client.post(f"{BASE}/templates", json=_template_payload())
        template_id = created.json()["id"]
        resp = await client.post(
            f"{BASE}/templates/{template_id}/attach",
            json={"training_session_id": ts_id, "age_gate_confirmed": False},
        )
    assert resp.status_code == 201, resp.text

    template_rows = await _audit_rows(session, AuditEntityType.interval_template)
    assert [r.action for r in template_rows] == [AuditAction.create, AuditAction.link]
    link_row = template_rows[-1]
    # La fila apunta a la PLANTILLA, con la sesión destino en el meta.
    assert link_row.entity_id == template_id
    assert link_row.meta_json == {"related_entity_id": ts_id}
    assert link_row.club_id == CLUB_ID
    assert link_row.diff_json is None

    # La matriz §4.11 pide UNA fila para esta ruta: `interval_template`·`link`.
    # `attach` delega en `structures.create_structure`, pero la instrumentación
    # de `interval_structure`·`create` vive en el handler de POST /structures,
    # así que adjuntar no duplica una fila de creación de estructura.
    structure_rows = await _audit_rows(session, AuditEntityType.interval_structure)
    assert structure_rows == []


# ===========================================================================
# Privacidad transversal
# ===========================================================================


@pytest.mark.asyncio
async def test_ninguna_fila_de_intervalos_almacena_valores(session):
    """FR-003: ni estructuras ni plantillas están en `VALUE_ALLOWLIST`."""
    ts_id = await _setup(session)

    async with make_client(session) as client:
        created = await client.post(
            f"{BASE}/structures", json=_structure_payload(ts_id)
        )
        structure_id = created.json()["id"]
        await client.put(
            f"{BASE}/structures/{structure_id}",
            json=_structure_put_payload(work_duration_s=600),
        )
        tpl = await client.post(f"{BASE}/templates", json=_template_payload())
        await client.patch(
            f"{BASE}/templates/{tpl.json()['id']}/archive",
            json={"is_archived": True},
        )

    rows = await _audit_rows(session)
    assert rows, "el escenario debe producir filas"
    for row in rows:
        assert row.diff_json is None, row.entity_type
        assert row.reason_code is None
        for key in (row.meta_json or {}):
            assert key in {"related_entity_id", "previous_status", "new_status"}
