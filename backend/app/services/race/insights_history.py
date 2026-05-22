"""Servicio de histórico de ``athlete_ai_insights`` (BE-2).

Funciones puras async que orquestan SELECT/UPDATE sobre la tabla con
versionado introducido en BE-1 (``8c1d2e3f4a5b``):

- :func:`list_athlete_insights` — paginado con filtros (use_case, valida_num,
  include_deprecated, latest_only).
- :func:`get_athlete_insight` — single + defensiva cross-tenant.
- :func:`get_insight_supersedes_chain` — recorre ``superseded_by_insight_id``
  para reconstruir versiones anteriores.
- :func:`deprecate_previous_active` — marca el insight activo anterior como
  deprecado (``is_active=NULL`` + ``deprecated_at=now``). TX-safe con
  ``SELECT ... FOR UPDATE`` en MySQL para evitar carrera con otro coach
  publicando simultáneamente la misma terna ``(athlete_id, season, valida_num)``.

Privacidad
==========
Las listas/details exponen sólo lo que ``AthleteInsightOut`` permite —
mapear a ese schema antes de devolver al cliente. Aquí trabajamos con el
ORM puro porque el ``persist_insight`` del grafo necesita acceso completo.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete_ai_insight import AthleteAiInsight

logger = logging.getLogger(__name__)

# Profundidad máxima para la cadena recursiva — protege contra ciclos
# accidentales (no deberían existir por la lógica del hook, pero un bug
# de migración podría introducirlos).
_MAX_CHAIN_DEPTH = 20


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_mysql(db: AsyncSession) -> bool:
    """True si el engine subyacente habla MySQL.

    SQLite (usado en tests) no soporta ``SELECT ... FOR UPDATE`` — el lock
    se hace implícito por la sesión async. En MySQL sí necesitamos el
    lock explícito para evitar dos coaches deprecando la misma fila.
    """
    bind = db.get_bind() if hasattr(db, "get_bind") else None
    if bind is None:
        return False
    name = getattr(bind, "name", "") or getattr(getattr(bind, "dialect", None), "name", "")
    return str(name).lower().startswith("mysql")


# ---------------------------------------------------------------------------
# Listado paginado
# ---------------------------------------------------------------------------


async def list_athlete_insights(
    db: AsyncSession,
    *,
    athlete_id: int,
    season: Optional[int] = None,
    use_case: Optional[str] = None,
    valida_num: Optional[int] = None,
    include_deprecated: bool = False,
    latest_only: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[AthleteAiInsight], int]:
    """Lista insights del atleta paginados.

    Args:
        athlete_id: PK del atleta. Filtro obligatorio (defensivo cross-tenant).
        season: Año de temporada. Si None, no filtra por temporada.
        use_case: ej. ``"race_progression"``, ``"season_summary"``. None = todos.
        valida_num: Filtro estricto. Si se necesita "agregados de temporada"
            pasar ``0``. ``None`` = no filtra.
        include_deprecated: Si True, levanta el filtro ``deprecated_at IS NULL``.
            Sólo debe usarse desde rutas admin/coach.
        latest_only: Si True, fuerza ``is_active=1`` (solo el activo aprobado).
        limit: 1..100 — el caller debería validar el rango antes de llamar.
        offset: cero-based.

    Returns:
        ``(items, total)`` — total ignora ``limit/offset`` para paginación.

    Notas:
        El default público (``include_deprecated=False`` +
        ``coach_approved=True`` aplicado siempre) garantiza que un padre
        nunca vea drafts internos del coach.
    """
    base_filters = [
        AthleteAiInsight.athlete_id == athlete_id,
        AthleteAiInsight.coach_approved.is_(True),
    ]
    if season is not None:
        base_filters.append(AthleteAiInsight.season == season)
    if use_case is not None:
        base_filters.append(AthleteAiInsight.use_case == use_case)
    if valida_num is not None:
        base_filters.append(AthleteAiInsight.valida_num == valida_num)
    if latest_only:
        base_filters.append(AthleteAiInsight.is_active == 1)
    elif not include_deprecated:
        base_filters.append(AthleteAiInsight.deprecated_at.is_(None))

    # Total (sin orderby ni limit).
    total_stmt = select(func.count(AthleteAiInsight.id)).where(*base_filters)
    total_result = await db.execute(total_stmt)
    total = int(total_result.scalar_one() or 0)

    items_stmt = (
        select(AthleteAiInsight)
        .where(*base_filters)
        .order_by(
            AthleteAiInsight.generated_at.desc(),
            AthleteAiInsight.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    items_result = await db.execute(items_stmt)
    items = list(items_result.scalars().all())
    return items, total


# ---------------------------------------------------------------------------
# Single get con check cross-tenant
# ---------------------------------------------------------------------------


async def get_athlete_insight(
    db: AsyncSession,
    *,
    athlete_id: int,
    insight_id: int,
) -> Optional[AthleteAiInsight]:
    """Carga un insight verificando que pertenezca al atleta indicado.

    Devuelve None si el insight no existe O pertenece a otro atleta
    (no se distingue para no filtrar pks). El router debe convertirlo a 404.
    """
    stmt = select(AthleteAiInsight).where(
        AthleteAiInsight.id == insight_id,
        AthleteAiInsight.athlete_id == athlete_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Cadena de versionado
# ---------------------------------------------------------------------------


async def get_insight_supersedes_chain(
    db: AsyncSession,
    *,
    insight_id: int,
) -> list[AthleteAiInsight]:
    """Recorre hacia atrás la cadena ``superseded_by_insight_id``.

    Devuelve la lista de insights *anteriores* a ``insight_id`` ordenados
    desde el más reciente (el inmediatamente anterior a ``insight_id``)
    hasta el más viejo. NO incluye al propio ``insight_id``.

    Para construir la cadena recorremos en sentido inverso al de la FK:
    buscamos filas que apuntan a ``insight_id`` con
    ``superseded_by_insight_id=insight_id``, luego el predecesor de aquel,
    etc. Limita a ``_MAX_CHAIN_DEPTH`` saltos para evitar bucles.
    """
    chain: list[AthleteAiInsight] = []
    current_id = insight_id
    visited: set[int] = {insight_id}
    for _ in range(_MAX_CHAIN_DEPTH):
        stmt = select(AthleteAiInsight).where(
            AthleteAiInsight.superseded_by_insight_id == current_id
        )
        result = await db.execute(stmt)
        prev = result.scalar_one_or_none()
        if prev is None:
            break
        if prev.id in visited:
            logger.warning(
                "Ciclo detectado en supersedes chain de insight_id=%s; corto.",
                insight_id,
            )
            break
        visited.add(prev.id)
        chain.append(prev)
        current_id = prev.id
    return chain


# ---------------------------------------------------------------------------
# Hook de deprecación HITL
# ---------------------------------------------------------------------------


async def deprecate_previous_active(
    db: AsyncSession,
    *,
    athlete_id: int,
    season: int,
    valida_num: Optional[int],
    new_insight_id: Optional[int],
) -> Optional[int]:
    """Marca el insight activo de la terna como deprecado y lo enlaza al nuevo.

    Idempotente: si no hay activo previo devuelve ``None``. Si lo hay,
    aplica:

    - ``is_active = NULL`` (libera el slot del UNIQUE parcial).
    - ``deprecated_at = now()``.
    - ``superseded_by_insight_id = new_insight_id``.

    En MySQL adquiere un ``SELECT ... FOR UPDATE`` sobre la fila previa
    para evitar carrera con otro coach publicando la misma terna. En
    SQLite (tests) la sesión async ya serializa.

    Args:
        athlete_id: Atleta dueño del insight.
        season: Temporada.
        valida_num: ``None`` = filtra estrictamente por ``IS NULL`` (el
            UNIQUE parcial usa el sentinel). ``0`` = agregado de temporada.
        new_insight_id: PK del nuevo insight que reemplaza al previo. Puede
            ser ``None`` si aún no fue INSERTado (el caller debe hacer un
            segundo UPDATE post-flush para enlazar).

    Returns:
        ID del insight deprecado, o ``None`` si no había activo previo.

    Notas:
        El campo ``valida_num`` ``IS NULL`` se respeta literalmente: la
        comparación ``column == None`` en SQLAlchemy se traduce a
        ``IS NULL`` automáticamente.
    """
    base_filters = [
        AthleteAiInsight.athlete_id == athlete_id,
        AthleteAiInsight.season == season,
        AthleteAiInsight.is_active == 1,
    ]
    # SQLAlchemy traduce ``== None`` a ``IS NULL`` automáticamente.
    if valida_num is None:
        base_filters.append(AthleteAiInsight.valida_num.is_(None))
    else:
        base_filters.append(AthleteAiInsight.valida_num == valida_num)

    select_stmt = select(AthleteAiInsight).where(*base_filters)
    if _is_mysql(db):
        # Lock explícito sólo en MySQL. SQLite ignora el atributo
        # gracefully pero no hace falta.
        select_stmt = select_stmt.with_for_update()

    result = await db.execute(select_stmt)
    previous = result.scalar_one_or_none()
    if previous is None:
        return None

    update_stmt = (
        update(AthleteAiInsight)
        .where(AthleteAiInsight.id == previous.id)
        .values(
            is_active=None,
            deprecated_at=_utc_now(),
            superseded_by_insight_id=new_insight_id,
            updated_at=_utc_now(),
        )
    )
    await db.execute(update_stmt)
    return int(previous.id)


__all__ = [
    "list_athlete_insights",
    "get_athlete_insight",
    "get_insight_supersedes_chain",
    "deprecate_previous_active",
]
