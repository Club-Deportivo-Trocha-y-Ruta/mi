"""Estructura de intervalos: helpers puros (flattening + validaciones de
guardarraíl) y CRUD transaccional de ``IntervalStructure`` (feature 026, T011).

Este módulo tiene dos capas bien separadas:

1. **Puro / sin I/O** (reusado por ``matching.py`` y por el instructivo PDF):
   - ``flatten_blocks(blocks) -> list[FlattenedStep]`` — expande cada grupo de
     repetición ``repeat_count`` veces en orden de ``position`` (los bloques no
     agrupados corren una vez). El ``FlattenedStep`` resultante satisface
     estructuralmente el ``FlattenedBlockLike`` que consume el motor de matching
     (mismos atributos: ``block_id``/``block_type``/``repeat_iteration``/
     ``planned_duration_s``/``target_zone``/``target_cadence_rpm``).
   - ``total_planned_duration_s(blocks) -> int`` — suma de las duraciones ya
     aplanadas (las repeticiones cuentan las veces que corren). Ecoado en
     ``StructureOut.total_planned_duration_s``.
   - ``validate_structure_blocks(blocks, band, age_gate_confirmed)`` — aplica los
     guardarraíles D2/D3 (research.md) con los códigos de error de
     ``contracts/api.md``. Se reusa idéntico en create/update de estructuras,
     create/update de plantillas y en el attach de plantilla (misma regla de la
     feature 021 con ``_validate_age_band_guardrail``).

2. **Transaccional** (dueño de su ``commit``, patrón de ``services/strength/
   blocks.py``): ``create_structure`` / ``get_structure_by_session`` /
   ``update_structure`` / ``delete_structure``. Cada write valida ANTES de
   escribir cualquier fila y recarga con el eager-load que el router necesita
   para serializar ``StructureOut`` sin un segundo round-trip.

Alcance de club (data-model.md §Access control):
    ``IntervalStructure`` no tiene ``club_id`` propio — pertenece a un club a
    través de su ``TrainingSession``. Toda lectura/escritura toma un ``club_id``
    explícito y filtra por ``TrainingSession.club_id`` (join): una estructura de
    otro club se trata como inexistente (``None`` / 404), nunca como error de
    permisos que filtre su existencia.

PRIVACIDAD / no-negociables (Ley 1581, menores):
    Los bloques solo declaran zona de FC y cadencia — no hay potencia (FR-005).
    La cadencia objetivo siempre es ≥ 60 rpm, cualquier banda, sin excepción
    (FR-004) — validado acá aun para rutas que clonan bloques ORM (attach de
    plantilla) donde el schema Pydantic no vuelve a correr.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.interval_structure import IntervalStructure, IntervalStructureBlock
from app.models.technique_exercise import AgeBand
from app.models.training_session import TrainingSession
from app.schemas.intervals import MIN_CADENCE_RPM, BlockIn

logger = logging.getLogger(__name__)

#: Zonas bloqueadas para la banda 10-12 (age gate duro, FR-006, sin override).
BLOCKED_ZONES_10_12: frozenset[str] = frozenset({"Z3", "Z4", "Z5"})

#: Valor de banda que dispara el age gate (FR-006/FR-007).
_GATED_BAND = "10-12"


# ---------------------------------------------------------------------------
# Salida del flattening (compatible estructuralmente con FlattenedBlockLike)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FlattenedStep:
    """Un paso real del plan tras expandir las repeticiones.

    Sus atributos coinciden con el ``FlattenedBlockLike`` que consume
    ``matching.compute_match`` (tipado estructural — no se acopla a ese módulo).
    El instructivo PDF (US3) también itera esta lista para su tabla de pasos.

    Attributes:
        block_id: id del bloque de origen (``None`` si el bloque no viene de la
            base — p. ej. ``BlockIn`` sin persistir).
        block_type: ``warmup`` | ``work`` | ``recovery`` | ``cooldown`` (string).
        repeat_iteration: iteración 1-based dentro de un grupo de repetición;
            ``None`` para bloques no agrupados.
        duration_type: ``fixed`` | ``open_lap`` (string, feature 034).
        planned_duration_s: duración planificada del paso (segundos, > 0)
            cuando ``duration_type == "fixed"``; ``None`` cuando
            ``"open_lap"`` (bloque libre, sin duración planificada —
            nunca entra a la matemática de tolerancia del matching).
        target_zone: ``Z1``..``Z5`` (string).
        target_cadence_rpm: cadencia objetivo (rpm, siempre ≥ 60).
        position: ``position`` de autoría del bloque de origen (los pasos de un
            mismo grupo comparten ``position``). Útil para reportar errores de
            validación con la posición original.
    """

    block_id: int | None
    block_type: str
    repeat_iteration: int | None
    duration_type: str
    planned_duration_s: int | None
    target_zone: str
    target_cadence_rpm: int
    position: int


# ---------------------------------------------------------------------------
# Normalización enum ↔ str (los bloques de entrada pueden ser BlockIn o ORM)
# ---------------------------------------------------------------------------


def _as_str(value: Any) -> str:
    """Devuelve el ``.value`` si es un enum, o el string tal cual.

    Los helpers reciben tanto ``BlockIn`` (Pydantic, campos ya string) como
    filas ORM (``IntervalStructureBlock`` / ``IntervalTemplateBlock``, campos
    enum). Se normaliza a string en ambos casos.
    """
    return value.value if hasattr(value, "value") else str(value)


def _band_str(band: Any) -> str:
    """Normaliza la banda de edad (``AgeBand`` enum o string) a su valor."""
    return band.value if isinstance(band, AgeBand) else str(band)


# ---------------------------------------------------------------------------
# Puro: flattening (reusado por matching e instructivo)
# ---------------------------------------------------------------------------


def flatten_blocks(blocks: Sequence[Any]) -> list[FlattenedStep]:
    """Expande los grupos de repetición en la secuencia real de pasos.

    Regla (data-model.md §Flattening, api.md ejemplo): recorriendo los bloques
    en orden de ``position``, cada corrida consecutiva de bloques que comparten
    un mismo ``repeat_group`` se emite ``repeat_count`` veces (todos los bloques
    del grupo en orden, y recién ahí se repite el grupo completo); los bloques
    sin grupo se emiten una sola vez. Ej.: ``warmup, work(g1), recovery(g1)×2,
    cooldown`` ⇢ ``warmup, work#1, recovery#1, work#2, recovery#2, cooldown``.

    Función **pura y determinística**: no lee ni escribe nada; ordena por
    ``position`` de forma defensiva (no muta la secuencia de entrada). Asume que
    los grupos ya están validados (``validate_structure_blocks`` garantiza
    ``repeat_count`` presente y ≥ 2, consistente y contiguo por grupo); si se la
    llama sin validar, un ``repeat_count`` ausente se trata como 1.

    Args:
        blocks: bloques de una estructura o plantilla (``BlockIn`` o filas ORM);
            cada uno con ``position``, ``block_type``, ``duration_s``,
            ``target_zone``, ``target_cadence_rpm``, ``repeat_group``,
            ``repeat_count`` (y opcionalmente ``id``).

    Returns:
        Lista de ``FlattenedStep`` en el orden real de ejecución.
    """
    ordered = sorted(blocks, key=lambda b: b.position)
    steps: list[FlattenedStep] = []
    i = 0
    n = len(ordered)
    while i < n:
        block = ordered[i]
        group = block.repeat_group
        if group is None:
            steps.append(_to_step(block, repeat_iteration=None))
            i += 1
            continue
        # Reúne la corrida consecutiva de bloques del mismo grupo.
        j = i
        run: list[Any] = []
        while j < n and ordered[j].repeat_group == group:
            run.append(ordered[j])
            j += 1
        count = block.repeat_count if block.repeat_count is not None else 1
        for iteration in range(1, count + 1):
            for run_block in run:
                steps.append(_to_step(run_block, repeat_iteration=iteration))
        i = j
    return steps


def _to_step(block: Any, *, repeat_iteration: int | None) -> FlattenedStep:
    """Construye un ``FlattenedStep`` a partir de un bloque de entrada."""
    return FlattenedStep(
        block_id=getattr(block, "id", None),
        block_type=_as_str(block.block_type),
        repeat_iteration=repeat_iteration,
        duration_type=_as_str(block.duration_type),
        # ``duration_s`` ya es None en el bloque de origen para un paso
        # open_lap (invariante validada por ``validate_structure_blocks``) —
        # se propaga tal cual, sin transformación (feature 034).
        planned_duration_s=block.duration_s,
        target_zone=_as_str(block.target_zone),
        target_cadence_rpm=block.target_cadence_rpm,
        position=block.position,
    )


def total_planned_duration_s(blocks: Sequence[Any]) -> int:
    """Suma la duración planificada de la estructura, ya aplanada.

    Pura, sin I/O. Las repeticiones se cuentan las veces que corren (usa
    ``flatten_blocks``), de modo que el total coincide con lo que el atleta
    ejecuta. Ecoado en ``StructureOut.total_planned_duration_s`` /
    ``TemplateOut.total_planned_duration_s``.

    Feature 034: los pasos ``open_lap`` tienen ``planned_duration_s = None``
    y **no** contribuyen a la suma (documentado en contracts/api-delta.md
    como "fixed-blocks-only sum, repeat-expanded") — el frontend deriva el
    sufijo "+ calentamiento libre" / "+ bloques libres" a partir de los
    bloques, no de un campo nuevo en la respuesta.

    Args:
        blocks: bloques de la estructura/plantilla (``BlockIn`` o filas ORM).

    Returns:
        Suma de ``planned_duration_s`` sobre los pasos aplanados de tipo
        ``fixed``; ``0`` si vacío o si todos los pasos son ``open_lap``.
    """
    return sum(
        step.planned_duration_s
        for step in flatten_blocks(blocks)
        if step.planned_duration_s is not None
    )


# ---------------------------------------------------------------------------
# Puro: validaciones de guardarraíl (D2/D3 research.md · códigos api.md)
# ---------------------------------------------------------------------------


def _raise_422(code: str, message: str, positions: list[int] | None = None) -> None:
    """Levanta un 422 con el envelope machine-readable de ``contracts/api.md``.

    ``detail`` es ``{"code": ..., "message": ...}`` (+ ``"positions"`` cuando el
    error apunta a bloques concretos). Español neutro en ``message``.
    """
    detail: dict[str, Any] = {"code": code, "message": message}
    if positions is not None:
        detail["positions"] = positions
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def _validate_repeat_groups(blocks: Sequence[Any]) -> None:
    """Valida el modelado de grupos de repetición → 422 ``invalid_repeat_group``.

    Reglas (data-model.md §2 + api.md):
    - ``repeat_group`` y ``repeat_count`` van juntos: ambos seteados o ambos
      ``NULL`` (uno sin el otro es inválido).
    - ``repeat_count`` ≥ 2 cuando está seteado.
    - Todas las filas de un grupo deben compartir el mismo ``repeat_count``.
    - Las filas de un grupo deben ser contiguas en orden de ``position`` (si no,
      el flattening sería ambiguo).
    """
    for block in blocks:
        has_group = block.repeat_group is not None
        has_count = block.repeat_count is not None
        if has_group != has_count:
            _raise_422(
                "invalid_repeat_group",
                "Un grupo de repetición requiere definir tanto el grupo como la "
                "cantidad de repeticiones.",
                positions=[block.position],
            )
        if has_count and block.repeat_count < 2:
            _raise_422(
                "invalid_repeat_group",
                "La cantidad de repeticiones de un grupo debe ser al menos 2.",
                positions=[block.position],
            )

    # Consistencia de conteo por grupo.
    counts_by_group: dict[int, set[int]] = {}
    for block in blocks:
        if block.repeat_group is not None:
            counts_by_group.setdefault(block.repeat_group, set()).add(
                block.repeat_count
            )
    for group, counts in counts_by_group.items():
        if len(counts) > 1:
            positions = sorted(
                b.position for b in blocks if b.repeat_group == group
            )
            _raise_422(
                "invalid_repeat_group",
                "Todos los bloques de un mismo grupo de repetición deben tener la "
                "misma cantidad de repeticiones.",
                positions=positions,
            )

    # Contigüidad por grupo (en orden de position).
    ordered = sorted(blocks, key=lambda b: b.position)
    seen_groups: set[int] = set()
    previous_group: int | None = None
    for block in ordered:
        group = block.repeat_group
        if group is not None and group != previous_group:
            if group in seen_groups:
                positions = sorted(
                    b.position for b in blocks if b.repeat_group == group
                )
                _raise_422(
                    "invalid_repeat_group",
                    "Los bloques de un grupo de repetición deben estar juntos "
                    "(posiciones contiguas).",
                    positions=positions,
                )
            seen_groups.add(group)
        previous_group = group


#: Tipos de bloque que pueden ser ``open_lap`` (feature 034 — nunca
#: ``work``/``recovery``, ver contracts/api-delta.md).
_OPEN_LAP_ALLOWED_BLOCK_TYPES: frozenset[str] = frozenset({"warmup", "cooldown"})


def _validate_duration_types(blocks: Sequence[Any]) -> None:
    """Guardarraíles de duración de bloque (feature 034, data-model.md §Invariants).

    Función **pura** (solo levanta ``HTTPException``, sin I/O). Reglas, en
    orden de chequeo (mensajes español-neutro exactos de
    ``contracts/api-delta.md``):

      1. ``open_lap_invalid_block_type`` (422) — un bloque ``open_lap`` con
         ``block_type`` distinto de ``warmup``/``cooldown``.
      2. ``open_lap_repeat_group_not_allowed`` (422) — un bloque ``open_lap``
         con ``repeat_group`` seteado (nunca dentro de un grupo repetido,
         sin importar el orden en que el cliente setee ambos campos —
         edge case de la spec).
      3. ``open_lap_duration_not_allowed`` (422) — un bloque ``open_lap``
         con ``duration_s`` presente (un bloque libre no lleva duración).
      4. ``fixed_duration_required`` (422) — un bloque ``fixed`` (el
         default cuando se omite ``duration_type``) con ``duration_s``
         ausente o ≤ 0. Reemplaza la constraint ``Field(gt=0)`` que
         ``BlockIn.duration_s`` tenía antes de esta feature — ahora es una
         regla CRUZADA (depende de ``duration_type``), por eso vive acá y
         no en el schema.

    Args:
        blocks: bloques a validar (``BlockIn`` o filas ORM).

    Raises:
        HTTPException 422: con ``detail={"code", "message", "positions"}``
            para el primer guardarraíl violado, en el orden documentado
            arriba.
    """
    invalid_block_type = sorted(
        b.position
        for b in blocks
        if _as_str(b.duration_type) == "open_lap"
        and _as_str(b.block_type) not in _OPEN_LAP_ALLOWED_BLOCK_TYPES
    )
    if invalid_block_type:
        _raise_422(
            "open_lap_invalid_block_type",
            "Solo el calentamiento y el enfriamiento pueden ser libres "
            "(hasta botón de vuelta).",
            positions=invalid_block_type,
        )

    invalid_repeat_group = sorted(
        b.position
        for b in blocks
        if _as_str(b.duration_type) == "open_lap" and b.repeat_group is not None
    )
    if invalid_repeat_group:
        _raise_422(
            "open_lap_repeat_group_not_allowed",
            "Un bloque libre no puede pertenecer a un grupo repetido.",
            positions=invalid_repeat_group,
        )

    invalid_duration_present = sorted(
        b.position
        for b in blocks
        if _as_str(b.duration_type) == "open_lap" and b.duration_s is not None
    )
    if invalid_duration_present:
        _raise_422(
            "open_lap_duration_not_allowed",
            "Un bloque libre no lleva duración.",
            positions=invalid_duration_present,
        )

    invalid_duration_missing = sorted(
        b.position
        for b in blocks
        if _as_str(b.duration_type) != "open_lap"
        and (b.duration_s is None or b.duration_s <= 0)
    )
    if invalid_duration_missing:
        _raise_422(
            "fixed_duration_required",
            "La duración debe ser mayor que cero.",
            positions=invalid_duration_missing,
        )


def validate_structure_blocks(
    blocks: Sequence[Any],
    target_age_band: Any,
    age_gate_confirmed: bool,
) -> None:
    """Aplica todos los guardarraíles de una estructura/plantilla antes de escribir.

    Función **pura** (solo levanta ``HTTPException``, sin I/O). Se corre idéntica
    en create/update de estructura, create/update de plantilla y attach de
    plantilla (mismo patrón que ``services/strength/blocks.py``).

    Orden de chequeos y códigos (``contracts/api.md`` + ``contracts/api-delta.md``
    para feature 034):
      1. ``cadence_below_minimum`` (422) — algún bloque con
         ``target_cadence_rpm`` < 60 (FR-004, cualquier banda). ``positions``
         lista las ``position`` infractoras.
      2. Guardarraíles de duración de bloque (feature 034, ver
         ``_validate_duration_types``): ``open_lap_invalid_block_type``,
         ``open_lap_repeat_group_not_allowed``, ``open_lap_duration_not_allowed``,
         ``fixed_duration_required``.
      3. ``invalid_repeat_group`` (422) — modelado de repeticiones inválido
         (ver ``_validate_repeat_groups``).
      4. Solo si la banda es ``10-12`` (D3):
         - ``age_gate_z3_blocked`` (422, duro, sin override) — algún bloque con
           zona Z3/Z4/Z5 (FR-006). ``positions`` lista las ``position``.
         - ``age_gate_confirmation_required`` (422) — todos los bloques Z1–Z2
           pero ``age_gate_confirmed`` es falso (FR-007). El cliente reintenta
           con ``age_gate_confirmed: true`` tras el diálogo de confirmación.

    Args:
        blocks: bloques a validar (``BlockIn`` o filas ORM). El schema Pydantic
            ya fuerza ``target_cadence_rpm`` ≥ 60 en las rutas API, pero el
            chequeo se repite acá (defensa en profundidad) porque el attach de
            plantilla valida bloques ORM clonados sin pasar por el schema.
        target_age_band: banda declarada de la estructura (``AgeBand`` o string
            ``"10-12"``/``"13-15"``).
        age_gate_confirmed: confirmación explícita enviada por el cliente
            (relevante solo para banda ``10-12`` con bloques Z1–Z2).

    Raises:
        HTTPException 422: con ``detail={"code", "message"[, "positions"]}`` para
            el primer guardarraíl violado, en el orden documentado arriba.
    """
    # 1) Cadencia mínima (FR-004) — cualquier banda.
    below = sorted(
        b.position for b in blocks if b.target_cadence_rpm < MIN_CADENCE_RPM
    )
    if below:
        _raise_422(
            "cadence_below_minimum",
            "La cadencia mínima es 60 rpm para todas las categorías.",
            positions=below,
        )

    # 2) Duración de bloque (feature 034) — open_lap vs. fixed.
    _validate_duration_types(blocks)

    # 3) Grupos de repetición.
    _validate_repeat_groups(blocks)

    # 4) Age gate — solo banda 10-12 (D3).
    if _band_str(target_age_band) != _GATED_BAND:
        return

    z3_positions = sorted(
        b.position for b in blocks if _as_str(b.target_zone) in BLOCKED_ZONES_10_12
    )
    if z3_positions:
        _raise_422(
            "age_gate_z3_blocked",
            "Intensidad Z3 o superior no está disponible para la categoría 10-12.",
            positions=z3_positions,
        )

    if not age_gate_confirmed:
        _raise_422(
            "age_gate_confirmation_required",
            "Confirmá explícitamente la estructura para la categoría 10-12 antes "
            "de guardar.",
        )


# ---------------------------------------------------------------------------
# Internos de persistencia
# ---------------------------------------------------------------------------


def _structure_select():  # type: ignore[return]
    """Base SELECT de ``IntervalStructure`` con el eager-load del read view.

    Carga ``blocks`` (ordenados por ``position`` vía el ``order_by`` de la
    relación) y ``age_gate_confirmed_by`` (para el nombre del confirmador en
    ``StructureOut.age_gate_confirmed_by``) — todo lo que el router serializa
    sin disparar un lazy load (Constitution IV, sin N+1). Sin I/O acá.
    """
    return select(IntervalStructure).options(
        selectinload(IntervalStructure.blocks),
        selectinload(IntervalStructure.age_gate_confirmed_by),
    )


async def _reload_structure(
    db: AsyncSession, structure_id: int
) -> IntervalStructure:
    """Recarga una estructura por id con el eager-load completo del read view.

    Se usa tras cada write (create/update). Asume que el id existe (solo se
    invoca justo después de un write exitoso a ese id).

    Side-effects: un SELECT primario + IN-queries de selectinload. Sin writes.
    """
    result = await db.execute(
        _structure_select().where(IntervalStructure.id == structure_id)
    )
    return result.unique().scalar_one()


def _now_utc() -> datetime:
    """Instante UTC actual (mismo patrón de defaults de los modelos)."""
    return datetime.now(timezone.utc)


def _build_block_rows(
    structure_id: int, blocks: Sequence[BlockIn]
) -> list[IntervalStructureBlock]:
    """Materializa las filas ``IntervalStructureBlock`` de una estructura.

    Preserva la ``position`` enviada por el cliente (a diferencia de strength,
    acá ``position`` es semántica — define el orden de autoría y la contigüidad
    de los grupos de repetición; ya viene validada ≥ 1 y única por el schema +
    ``_validate_repeat_groups``).
    """
    return [
        IntervalStructureBlock(
            structure_id=structure_id,
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


# ---------------------------------------------------------------------------
# Público: CRUD de IntervalStructure (US1)
# ---------------------------------------------------------------------------


async def create_structure(
    db: AsyncSession,
    *,
    training_session_id: int,
    target_age_band: AgeBand,
    age_gate_confirmed: bool,
    blocks: Sequence[BlockIn],
    club_id: int,
    created_by_user_id: int,
) -> IntervalStructure:
    """Crea la estructura de intervalos 1:1 de una sesión (POST /structures).

    Valida la sesión (existencia + club), rechaza si ya tiene estructura (409),
    corre todos los guardarraíles (``validate_structure_blocks``) y recién ahí
    persiste la estructura y sus bloques. Cuando ``age_gate_confirmed`` es True
    se registra el confirmador y el timestamp (FR-007).

    Args:
        db: sesión async activa. Esta función es dueña del commit.
        training_session_id: sesión a la que se adjunta la estructura.
        target_age_band: banda declarada por el entrenador (dirige el age gate).
        age_gate_confirmed: confirmación explícita para 10-12 (FR-007).
        blocks: bloques ordenados (``BlockIn`` del body).
        club_id: club del entrenador (resuelto en el router) — la sesión debe
            pertenecer a este club.
        created_by_user_id: id del usuario coach/admin autenticado.

    Returns:
        La ``IntervalStructure`` creada, recargada con ``blocks`` y
        ``age_gate_confirmed_by`` eager-loaded.

    Raises:
        HTTPException 404: la sesión no existe o es de otro club.
        HTTPException 409: la sesión ya tiene una estructura (usar PUT).
        HTTPException 422: guardarraíl violado (ver ``validate_structure_blocks``).

    Side-effects: SELECT/INSERT; un solo commit.
    """
    session_result = await db.execute(
        select(TrainingSession.id).where(
            TrainingSession.id == training_session_id,
            TrainingSession.club_id == club_id,
        )
    )
    if session_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sesión de entrenamiento {training_session_id} no encontrada.",
        )

    existing_result = await db.execute(
        select(IntervalStructure.id).where(
            IntervalStructure.training_session_id == training_session_id
        )
    )
    if existing_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta sesión ya tiene una estructura de intervalos.",
        )

    validate_structure_blocks(blocks, target_age_band, age_gate_confirmed)

    structure = IntervalStructure(
        training_session_id=training_session_id,
        target_age_band=target_age_band,
        age_gate_confirmed=age_gate_confirmed,
        age_gate_confirmed_by_user_id=created_by_user_id if age_gate_confirmed else None,
        age_gate_confirmed_at=_now_utc() if age_gate_confirmed else None,
        created_by_user_id=created_by_user_id,
    )
    db.add(structure)
    await db.flush()  # popula structure.id para las FKs de los bloques

    db.add_all(_build_block_rows(structure.id, blocks))
    await db.commit()

    reloaded = await _reload_structure(db, structure.id)
    logger.debug(
        "Estructura de intervalos creada | structure_id=%s session_id=%s "
        "club_id=%s blocks=%d",
        reloaded.id,
        training_session_id,
        club_id,
        len(blocks),
    )
    return reloaded


async def get_structure_by_session(
    db: AsyncSession, *, training_session_id: int, club_id: int
) -> IntervalStructure | None:
    """Devuelve la estructura de una sesión, o ``None`` si no tiene / otro club.

    Club-scoped por join a ``TrainingSession.club_id``: una sesión de otro club
    se trata como sin estructura (``None`` → el router 404ea el estado vacío),
    sin filtrar su existencia.

    Args:
        db: sesión async activa. El caller es dueño del commit/rollback.
        training_session_id: sesión objetivo.
        club_id: filtro de club.

    Returns:
        ``IntervalStructure`` con ``blocks``/``age_gate_confirmed_by`` eager, o
        ``None``.

    Side-effects: SELECTs. Sin writes.
    """
    result = await db.execute(
        _structure_select()
        .join(
            TrainingSession,
            TrainingSession.id == IntervalStructure.training_session_id,
        )
        .where(
            IntervalStructure.training_session_id == training_session_id,
            TrainingSession.club_id == club_id,
        )
    )
    return result.unique().scalar_one_or_none()


async def get_structure(
    db: AsyncSession, *, structure_id: int, club_id: int
) -> IntervalStructure | None:
    """Devuelve una estructura por id, club-scoped, o ``None`` si no existe.

    Igual criterio de club que ``get_structure_by_session`` (join a
    ``TrainingSession.club_id``). Útil para el router de recalculate / borrado.

    Side-effects: SELECTs. Sin writes.
    """
    result = await db.execute(
        _structure_select()
        .join(
            TrainingSession,
            TrainingSession.id == IntervalStructure.training_session_id,
        )
        .where(
            IntervalStructure.id == structure_id,
            TrainingSession.club_id == club_id,
        )
    )
    return result.unique().scalar_one_or_none()


async def update_structure(
    db: AsyncSession,
    *,
    structure_id: int,
    club_id: int,
    target_age_band: AgeBand,
    age_gate_confirmed: bool,
    blocks: Sequence[BlockIn],
) -> IntervalStructure | None:
    """Reemplazo total de banda + bloques de una estructura (PUT /structures/{id}).

    Borra todas las filas de bloques y las reemplaza por el set enviado; corre
    los mismos guardarraíles y códigos 422 que ``create_structure``. Actualiza
    los campos de age gate (registra confirmador + timestamp cuando se confirma;
    los limpia cuando ``age_gate_confirmed`` pasa a falso).

    El disparo del recálculo diferido cuando la sesión tiene actividad vinculada
    (``triggered_by=structure_change``, api.md) es responsabilidad del router —
    esta función solo persiste la estructura.

    Args:
        db: sesión async activa. Dueña del commit.
        structure_id: PK de la estructura a reemplazar.
        club_id: filtro de club (join a la sesión) — otra club ⇒ ``None`` (404).
        target_age_band: nueva banda declarada.
        age_gate_confirmed: nueva confirmación explícita.
        blocks: nuevo set completo de bloques (``BlockIn``).

    Returns:
        La ``IntervalStructure`` actualizada con eager-load, o ``None`` si no
        existe / es de otro club (no ocurre write en ese caso).

    Raises:
        HTTPException 422: guardarraíl violado (ver ``validate_structure_blocks``).

    Side-effects: SELECT/DELETE/INSERT; un commit cuando la estructura existe.
    """
    result = await db.execute(
        select(IntervalStructure)
        .join(
            TrainingSession,
            TrainingSession.id == IntervalStructure.training_session_id,
        )
        .where(
            IntervalStructure.id == structure_id,
            TrainingSession.club_id == club_id,
        )
    )
    structure = result.scalar_one_or_none()
    if structure is None:
        return None

    validate_structure_blocks(blocks, target_age_band, age_gate_confirmed)

    structure.target_age_band = target_age_band
    structure.age_gate_confirmed = age_gate_confirmed
    if age_gate_confirmed:
        structure.age_gate_confirmed_by_user_id = structure.created_by_user_id
        structure.age_gate_confirmed_at = _now_utc()
    else:
        structure.age_gate_confirmed_by_user_id = None
        structure.age_gate_confirmed_at = None

    await db.execute(
        sa_delete(IntervalStructureBlock).where(
            IntervalStructureBlock.structure_id == structure_id
        )
    )
    await db.flush()

    db.add_all(_build_block_rows(structure_id, blocks))
    await db.commit()

    reloaded = await _reload_structure(db, structure_id)
    logger.debug(
        "Estructura de intervalos actualizada | structure_id=%s club_id=%s "
        "blocks=%d",
        structure_id,
        club_id,
        len(blocks),
    )
    return reloaded


async def delete_structure(
    db: AsyncSession, *, structure_id: int, club_id: int
) -> bool:
    """Borra una estructura (DELETE /structures/{id}).

    Cascada (definida en el modelo): borra sus ``blocks`` y sus
    ``match_results``. Las vueltas (``strava_activity_laps``) son propiedad de la
    actividad y **no** se tocan (D7).

    Args:
        db: sesión async activa. Dueña del commit.
        structure_id: PK de la estructura a borrar.
        club_id: filtro de club (join a la sesión).

    Returns:
        ``True`` si se borró; ``False`` si no existe / es de otro club (sin
        write en ese caso).

    Side-effects: SELECT + DELETE; un commit cuando se borra.
    """
    result = await db.execute(
        select(IntervalStructure)
        .join(
            TrainingSession,
            TrainingSession.id == IntervalStructure.training_session_id,
        )
        .where(
            IntervalStructure.id == structure_id,
            TrainingSession.club_id == club_id,
        )
    )
    structure = result.scalar_one_or_none()
    if structure is None:
        return False

    await db.delete(structure)
    await db.commit()

    logger.debug(
        "Estructura de intervalos borrada | structure_id=%s club_id=%s",
        structure_id,
        club_id,
    )
    return True
