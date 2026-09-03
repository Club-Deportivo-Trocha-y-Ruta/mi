"""Plantillas reutilizables de intervalos: CRUD + ``attach_template()``
copy-on-attach (feature 026, T031).

Mirrors the transactional shape of ``services/strength/blocks.py`` (each
public write function owns its ``db.commit()`` and reloads with the
eager-load chain the router needs) and reuses **all** guardrail validation
from ``services/intervals/structures.py`` — this module never re-implements
cadence/repeat-group/age-gate checks (research.md D3, contracts/api.md).

Two distinct places call into ``structures.py``:

1. **Template save** (``create_template`` / ``update_template``) calls
   ``structures.validate_structure_blocks(blocks, target_age_band,
   age_gate_confirmed=True)``. Passing ``True`` unconditionally is
   deliberate, not a bypass of FR-007: ``TemplateCreate``/``TemplateUpdate``
   have **no** ``age_gate_confirmed`` field (contracts/api.md — a template
   is authored content, never executed directly), so the "all Z1-Z2 on
   10-12 needs explicit confirmation" branch of
   ``validate_structure_blocks`` would otherwise be permanently
   unsatisfiable for a legitimate 10-12 template. The **hard** Z3+ block
   (FR-006, no override) is independent of the ``age_gate_confirmed`` value
   and still runs unconditionally — "Z3+ on a 10-12 template is rejected at
   save, keeping the library clean at the source" (contracts/api.md). The
   real confirmation gate is deferred to attach time, where a human is
   attaching the plan to an actual session.
2. **Template attach** (``attach_template``) delegates the *entire* write —
   session lookup/club-scope, the 409 "session already has a structure"
   guard, the full ``validate_structure_blocks`` guardrail run (now with the
   caller-supplied ``age_gate_confirmed``), row construction and commit — to
   ``structures.create_structure()``. This module only clones the template's
   ``IntervalTemplateBlock`` rows into plain ``BlockIn`` values first; it
   never touches ``interval_structures``/``interval_structure_blocks`` rows
   directly. No FK is kept from the resulting structure back to the
   template (data-model.md §3/§4: "no FK link retained") — editing or
   deleting a template afterwards never touches sessions that used it, and
   mutating the cloned copy never touches the template.

Club scoping: ``IntervalTemplate.club_id`` is a direct column (unlike
``IntervalStructure``, which has none of its own and is scoped via its
session's club) — every read/write here takes an explicit ``club_id`` and
filters on it; a template from another club is treated as not found
(``None`` / 404), never as a permission error that leaks its existence.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence

from fastapi import HTTPException, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.interval_structure import (
    AgeBand,
    IntervalStructure,
    IntervalTemplate,
    IntervalTemplateBlock,
)
from app.schemas.intervals import BlockIn
from app.services.intervals import structures as structures_service

logger = logging.getLogger(__name__)

#: ``age_gate_confirmed`` passed to ``validate_structure_blocks`` when
#: saving a template (create/update) — see module docstring point 1. This is
#: **not** persisted anywhere; ``IntervalTemplate`` has no
#: ``age_gate_confirmed`` column (data-model.md §3) — the real confirmation
#: is recorded on the *structure* produced by ``attach_template``.
_TEMPLATE_SAVE_AGE_GATE_CONFIRMED = True


# ---------------------------------------------------------------------------
# Internos de persistencia
# ---------------------------------------------------------------------------


def _template_select():  # type: ignore[return]
    """Base SELECT de ``IntervalTemplate`` con el eager-load del read view.

    Carga ``blocks`` (ordenados por ``position`` vía el ``order_by`` de la
    relación) — todo lo que el router necesita para serializar
    ``TemplateOut`` sin disparar un lazy load (Constitution IV, sin N+1).
    Sin I/O acá.
    """
    return select(IntervalTemplate).options(selectinload(IntervalTemplate.blocks))


async def _reload_template(db: AsyncSession, template_id: int) -> IntervalTemplate:
    """Recarga una plantilla por id con el eager-load completo del read view.

    Se usa tras cada write (create/update/archive). Asume que el id existe
    (solo se invoca justo después de un write exitoso a ese id).

    Side-effects: un SELECT primario + IN-query de selectinload. Sin writes.
    """
    result = await db.execute(
        _template_select().where(IntervalTemplate.id == template_id)
    )
    return result.unique().scalar_one()


def _build_template_block_rows(
    template_id: int, blocks: Sequence[BlockIn]
) -> list[IntervalTemplateBlock]:
    """Materializa las filas ``IntervalTemplateBlock`` de una plantilla.

    Mismo criterio que ``structures._build_block_rows``: preserva la
    ``position`` enviada por el cliente (ya validada ≥ 1, única y contigua
    por grupo por ``validate_structure_blocks``).
    """
    return [
        IntervalTemplateBlock(
            template_id=template_id,
            position=block.position,
            block_type=block.block_type,
            duration_type=block.duration_type,
            duration_s=block.duration_s,
            target_zone=block.target_zone,
            target_cadence_rpm=block.target_cadence_rpm,
            repeat_group=block.repeat_group,
            repeat_count=block.repeat_count,
        )
        for block in blocks
    ]


def _clone_blocks_to_block_in(
    template_blocks: Sequence[IntervalTemplateBlock],
) -> list[BlockIn]:
    """Convierte los bloques ORM de una plantilla en ``BlockIn`` desconectados.

    Estos ``BlockIn`` son objetos Pydantic nuevos (sin ``id``, sin sesión
    ORM adjunta) — pasarlos a ``structures.create_structure`` produce filas
    ``IntervalStructureBlock`` **independientes**: mutar la estructura
    resultante nunca toca la plantilla de origen, y viceversa (copy-on-attach,
    FR-009, data-model.md §3/§4). ``duration_type``/``duration_s`` se
    preservan verbatim (feature 034) — un bloque ``open_lap`` de la
    plantilla sigue siendo ``open_lap`` en la estructura clonada.

    Args:
        template_blocks: bloques ORM de la plantilla (``template.blocks``,
            ya eager-loaded — no dispara I/O acá).

    Returns:
        Lista de ``BlockIn`` en el mismo orden de ``position``, listos para
        ``validate_structure_blocks``/``create_structure``.
    """
    return [
        BlockIn(
            position=block.position,
            block_type=block.block_type.value,
            duration_type=block.duration_type.value,
            duration_s=block.duration_s,
            target_zone=block.target_zone.value,
            target_cadence_rpm=block.target_cadence_rpm,
            repeat_group=block.repeat_group,
            repeat_count=block.repeat_count,
        )
        for block in sorted(template_blocks, key=lambda b: b.position)
    ]


# ---------------------------------------------------------------------------
# Público: CRUD de IntervalTemplate (US4)
# ---------------------------------------------------------------------------


async def create_template(
    db: AsyncSession,
    *,
    name: str,
    target_age_band: AgeBand,
    mesocycle_phase: str,
    competition_proximity: str,
    blocks: Sequence[BlockIn],
    club_id: int,
    created_by_user_id: int,
) -> IntervalTemplate:
    """Crea una plantilla reutilizable de intervalos (POST /templates).

    Corre el mismo guardarraíl que una estructura (``validate_structure_
    blocks``), con la salvedad documentada en el docstring del módulo: se
    pasa ``age_gate_confirmed=True`` siempre (la plantilla no tiene ese
    campo — la confirmación real ocurre en ``attach_template``), de modo
    que solo el bloqueo duro Z3+ en 10-12 (FR-006, sin override) puede
    rechazar el guardado.

    Args:
        db: sesión async activa. Esta función es dueña del commit.
        name: nombre visible de la plantilla.
        target_age_band: banda declarada — tag + contexto de gate al
            adjuntar (FR-008).
        mesocycle_phase: vocabulario controlado en el frontend (string).
        competition_proximity: vocabulario controlado en el frontend
            (string).
        blocks: bloques ordenados (``BlockIn`` del body).
        club_id: club del entrenador (resuelto en el router) — dueño de la
            plantilla.
        created_by_user_id: id del usuario coach/admin autenticado.

    Returns:
        La ``IntervalTemplate`` creada, recargada con ``blocks`` eager-loaded.

    Raises:
        HTTPException 422: guardarraíl violado — ``cadence_below_minimum``,
            ``invalid_repeat_group`` o ``age_gate_z3_blocked`` (ver
            ``structures.validate_structure_blocks``).

    Side-effects: SELECT/INSERT; un solo commit.
    """
    structures_service.validate_structure_blocks(
        blocks, target_age_band, _TEMPLATE_SAVE_AGE_GATE_CONFIRMED
    )

    template = IntervalTemplate(
        name=name,
        target_age_band=target_age_band,
        mesocycle_phase=mesocycle_phase,
        competition_proximity=competition_proximity,
        club_id=club_id,
        created_by_user_id=created_by_user_id,
        is_archived=False,
    )
    db.add(template)
    await db.flush()  # popula template.id para las FKs de los bloques

    db.add_all(_build_template_block_rows(template.id, blocks))
    await db.commit()

    reloaded = await _reload_template(db, template.id)
    logger.debug(
        "Plantilla de intervalos creada | template_id=%s club_id=%s blocks=%d",
        reloaded.id,
        club_id,
        len(blocks),
    )
    return reloaded


async def get_template(
    db: AsyncSession, *, template_id: int, club_id: int
) -> IntervalTemplate | None:
    """Devuelve una plantilla por id, club-scoped, o ``None`` si no existe.

    Una plantilla de otro club se trata como inexistente (``None`` — el
    router 404ea), sin filtrar su existencia.

    Side-effects: SELECT. Sin writes.
    """
    result = await db.execute(
        _template_select().where(
            IntervalTemplate.id == template_id, IntervalTemplate.club_id == club_id
        )
    )
    return result.unique().scalar_one_or_none()


async def list_templates(
    db: AsyncSession,
    *,
    club_id: int,
    age_band: AgeBand | None = None,
    mesocycle_phase: str | None = None,
    competition_proximity: str | None = None,
    include_archived: bool = False,
) -> tuple[list[IntervalTemplate], int]:
    """Lista las plantillas del club, filtrables por las 3 tags (US4-AC2).

    Args:
        db: sesión async activa. El caller es dueño del commit/rollback.
        club_id: filtro de club — solo se devuelven plantillas de este club.
        age_band: filtro opcional exacto por ``target_age_band``.
        mesocycle_phase: filtro opcional exacto por ``mesocycle_phase``.
        competition_proximity: filtro opcional exacto por
            ``competition_proximity``.
        include_archived: cuando ``False`` (default), excluye
            ``is_archived = true`` (contrato: default de ``GET /templates``).

    Returns:
        Tupla ``(items, total)`` — lista de ``IntervalTemplate`` con
        ``blocks`` eager-loaded (más recientes primero) y su conteo total.

    Side-effects: SELECT. Sin writes.
    """
    stmt = _template_select().where(IntervalTemplate.club_id == club_id)
    if not include_archived:
        stmt = stmt.where(IntervalTemplate.is_archived.is_(False))
    if age_band is not None:
        stmt = stmt.where(IntervalTemplate.target_age_band == age_band)
    if mesocycle_phase is not None:
        stmt = stmt.where(IntervalTemplate.mesocycle_phase == mesocycle_phase)
    if competition_proximity is not None:
        stmt = stmt.where(
            IntervalTemplate.competition_proximity == competition_proximity
        )
    stmt = stmt.order_by(IntervalTemplate.created_at.desc())

    result = await db.execute(stmt)
    items = list(result.unique().scalars().all())
    return items, len(items)


async def update_template(
    db: AsyncSession,
    *,
    template_id: int,
    club_id: int,
    name: str,
    target_age_band: AgeBand,
    mesocycle_phase: str,
    competition_proximity: str,
    blocks: Sequence[BlockIn],
) -> IntervalTemplate | None:
    """Reemplazo total de una plantilla (PUT /templates/{id}).

    Borra todas las filas de bloques y las reemplaza por el set enviado;
    corre el mismo guardarraíl (con la misma salvedad documentada en el
    módulo) que ``create_template``. Editar una plantilla **nunca** muta
    las sesiones que ya la adjuntaron — no hay FK de vuelta desde
    ``interval_structures`` (copy-on-attach).

    Args:
        db: sesión async activa. Dueña del commit.
        template_id: PK de la plantilla a reemplazar.
        club_id: filtro de club — otro club ⇒ ``None`` (404).
        name: nuevo nombre.
        target_age_band: nueva banda declarada.
        mesocycle_phase: nuevo valor de fase de mesociclo.
        competition_proximity: nuevo valor de proximidad a competencia.
        blocks: nuevo set completo de bloques (``BlockIn``).

    Returns:
        La ``IntervalTemplate`` actualizada con eager-load, o ``None`` si no
        existe / es de otro club (no ocurre write en ese caso).

    Raises:
        HTTPException 422: guardarraíl violado (ver ``create_template``).

    Side-effects: SELECT/DELETE/INSERT; un commit cuando la plantilla existe.
    """
    result = await db.execute(
        select(IntervalTemplate).where(
            IntervalTemplate.id == template_id, IntervalTemplate.club_id == club_id
        )
    )
    template = result.scalar_one_or_none()
    if template is None:
        return None

    structures_service.validate_structure_blocks(
        blocks, target_age_band, _TEMPLATE_SAVE_AGE_GATE_CONFIRMED
    )

    template.name = name
    template.target_age_band = target_age_band
    template.mesocycle_phase = mesocycle_phase
    template.competition_proximity = competition_proximity

    await db.execute(
        sa_delete(IntervalTemplateBlock).where(
            IntervalTemplateBlock.template_id == template_id
        )
    )
    await db.flush()

    db.add_all(_build_template_block_rows(template_id, blocks))
    await db.commit()

    reloaded = await _reload_template(db, template_id)
    logger.debug(
        "Plantilla de intervalos actualizada | template_id=%s club_id=%s blocks=%d",
        template_id,
        club_id,
        len(blocks),
    )
    return reloaded


async def archive_template(
    db: AsyncSession, *, template_id: int, club_id: int, is_archived: bool
) -> IntervalTemplate | None:
    """Archiva (o desarchiva) una plantilla (PATCH /templates/{id}/archive).

    Las plantillas archivadas se excluyen del ``list_templates`` por
    defecto pero siguen siendo legibles vía ``get_template`` y nunca se
    borran físicamente (data-model.md §Estados: "active → archived,
    never hard-deleted while referenced by nothing — copies live
    independently").

    Args:
        db: sesión async activa. Esta función es dueña del commit.
        template_id: PK de la plantilla a (des)archivar.
        club_id: filtro de club.
        is_archived: nuevo valor de ``IntervalTemplate.is_archived``.

    Returns:
        La ``IntervalTemplate`` actualizada con eager-load, o ``None`` si no
        existe / es de otro club (sin write en ese caso).

    Side-effects: SELECT; un commit cuando la plantilla existe.
    """
    result = await db.execute(
        select(IntervalTemplate).where(
            IntervalTemplate.id == template_id, IntervalTemplate.club_id == club_id
        )
    )
    template = result.scalar_one_or_none()
    if template is None:
        return None

    template.is_archived = is_archived
    await db.commit()

    reloaded = await _reload_template(db, template_id)
    logger.debug(
        "Plantilla de intervalos %s | template_id=%s club_id=%s",
        "archivada" if is_archived else "desarchivada",
        template_id,
        club_id,
    )
    return reloaded


# ---------------------------------------------------------------------------
# Público: copy-on-attach (US4, FR-009)
# ---------------------------------------------------------------------------


async def attach_template(
    db: AsyncSession,
    *,
    template_id: int,
    training_session_id: int,
    club_id: int,
    age_gate_confirmed: bool,
    attached_by_user_id: int,
) -> IntervalStructure:
    """Adjunta una plantilla a una sesión clonando sus bloques (POST /templates/{id}/attach).

    Copy-on-attach (FR-009, spec edge case): clona los bloques de la
    plantilla en filas ``IntervalStructureBlock`` **nuevas e independientes**
    (``_clone_blocks_to_block_in``) y delega el resto entero de la
    escritura — existencia/club de la sesión (404), 409 si la sesión ya
    tiene estructura, el guardarraíl completo con el
    ``age_gate_confirmed`` real del caller, la persistencia y el commit — a
    ``structures.create_structure``. No se retiene ningún FK hacia la
    plantilla (data-model.md §3/§4): editar o borrar la plantilla después
    nunca toca esta estructura, y mutarla nunca toca la plantilla.

    Args:
        db: sesión async activa. La escritura la comitea
            ``structures.create_structure`` — esta función no comitea nada
            por sí misma más allá de eso.
        template_id: PK de la plantilla a clonar.
        training_session_id: sesión destino.
        club_id: club del entrenador — tanto la plantilla como la sesión
            deben pertenecer a este club.
        age_gate_confirmed: confirmación explícita del caller para el caso
            10-12 con bloques Z1-Z2 (FR-007) — evaluada contra la banda y
            los bloques *de la plantilla* en este momento de attach (spec
            edge case: "attaching a Z3+ template to a 10-12 session →
            age_gate_z3_blocked; sub-Z3 onto 10-12 → age_gate_confirmation_
            required unless confirmed").
        attached_by_user_id: id del usuario coach/admin autenticado —
            registrado como ``created_by_user_id`` (y, si corresponde,
            confirmador) de la estructura resultante.

    Returns:
        La ``IntervalStructure`` nueva, recargada con ``blocks`` y
        ``age_gate_confirmed_by`` eager-loaded (mismo shape que
        ``structures.create_structure``).

    Raises:
        HTTPException 404: la plantilla no existe / es de otro club, o la
            sesión no existe / es de otro club.
        HTTPException 409: la sesión ya tiene una estructura de intervalos.
        HTTPException 422: guardarraíl violado contra la banda y los
            bloques de la plantilla (ver
            ``structures.validate_structure_blocks``).

    Side-effects: SELECT de la plantilla; el resto de SELECT/INSERT + commit
        ocurre dentro de ``structures.create_structure``.
    """
    template_result = await db.execute(
        select(IntervalTemplate)
        .options(selectinload(IntervalTemplate.blocks))
        .where(
            IntervalTemplate.id == template_id, IntervalTemplate.club_id == club_id
        )
    )
    template = template_result.unique().scalar_one_or_none()
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plantilla de intervalos {template_id} no encontrada.",
        )

    # Defensa en profundidad: validá los bloques ORM de la plantilla ANTES de
    # clonarlos a BlockIn. Una plantilla sembrada directamente en la BD (fuera
    # del path de create/update) podría tener cadencia < 60; construir BlockIn
    # levantaría un ValidationError crudo de Pydantic (500) en vez del 422 de
    # dominio. Validar el ORM primero garantiza el código de error limpio.
    structures_service.validate_structure_blocks(
        template.blocks,
        template.target_age_band,
        age_gate_confirmed,
    )

    cloned_blocks = _clone_blocks_to_block_in(template.blocks)

    structure = await structures_service.create_structure(
        db,
        training_session_id=training_session_id,
        target_age_band=template.target_age_band,
        age_gate_confirmed=age_gate_confirmed,
        blocks=cloned_blocks,
        club_id=club_id,
        created_by_user_id=attached_by_user_id,
    )

    logger.debug(
        "Plantilla adjuntada a sesión | template_id=%s structure_id=%s "
        "training_session_id=%s club_id=%s",
        template_id,
        structure.id,
        training_session_id,
        club_id,
    )
    return structure
