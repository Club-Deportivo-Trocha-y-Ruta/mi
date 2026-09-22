"""T034 — candado de progresión de terceros (US3, FR-012…FR-015).

Contrato: ``specs/044-race-history-backfill/contracts/third-party-lock.md``
(ver también ``research.md`` R-07). Test ejecutable:
``backend/tests/privacy/test_third_party_lock.py``.

Por qué existe
--------------
La carga histórica de la Copa Valle 2024-2025 mete en ``race_competitors``
la parrilla COMPLETA de 15 válidas — varios cientos de menores ajenos al
club. Su dato existe **sólo como denominador** (tamaño de parrilla, mediana
de la categoría, tiempo del ganador) para poder situar a los ~20 deportistas
propios. Debe ser estructuralmente imposible obtener la progresión
longitudinal de un competidor no vinculado a un ``Athlete`` del club.

Antes de esta feature, ``analytics.athlete_progression`` / ``projection``
aceptaban cualquier ``competitor_id``: lo único que las mantenía sobre
atletas del club era la convención de llamado (los routers resuelven el
``competitor_id`` desde un ``athlete_id`` ya autorizado). Con cientos de
terceros en la tabla, "convención de llamado" dejó de ser suficiente.

Modelo de enforcement
---------------------
(Nota de la auditoría T090, 2026-09-22: no existe un primitivo por lotes
— ``require_club_competitors`` — para listas de ``competitor_ids``. El test
estructural ya detecta parámetros ``competitor_ids``, pero ninguna función
pública los recibe hoy. Si alguna vez hace falta, créalo aquí y protégelo con
el mismo marcador; no asumas que existe.)

1. :func:`require_club_competitor` — el primitivo. Lee el estado de vínculo
   **en cada llamada** (no cachea), así una desvinculación surte efecto
   inmediato. Devuelve el ``athlete_id`` vinculado o lanza
   :class:`ThirdPartyProgressionForbidden`.
2. :func:`club_competitor_only` — decorador marcador. Valida ANTES de
   ejecutar el cuerpo decorado y marca el callable con
   ``__club_competitor_guarded__ = True``.
3. :data:`ALLOWED_SINGLE_EVENT` — la lista corta y revisada de excepciones,
   cada una con su justificación de una línea.

El test estructural recorre todo ``app.services.race`` y falla si aparece un
callable público con parámetro ``competitor_id`` que no esté marcado ni en la
allow-list: una función nueva sin candado rompe CI.

Nota sobre ``analytics.podium_gap``
-----------------------------------
La prosa del contrato y ``research.md`` R-07 la listan como una de las
funciones "at minimum" a guardar. **No se marca**, y es correcto: su firma
actual es ``podium_gap(db, category_id, season)`` — no recibe
``competitor_id``, y filtra internamente a ``athlete_id IS NOT NULL`` (sólo
corredores TyR con match confirmado) antes de construir su grilla, así que
nunca puede devolver la fila de un tercero. El barrido estructural, tal como
está especificado ("callables con parámetro ``competitor_id``"), no la
reporta como candidata. Queda constando acá para que una revisión futura no
lo lea como un descuido. Si algún día ``podium_gap`` recibiera un
``competitor_id``, el barrido la marcaría automáticamente como ofensora.

Nota sobre los cargadores detrás de ``compute_field_metrics``
--------------------------------------------------------------
``compute_field_metrics`` es síncrona y pura sobre colecciones ORM ya
cargadas (no recibe ``db``), así que no puede esperar al candado async. Sus
dos llamadores de producción reciben el ``competitor_id`` ya validado:

- ``ai/nodes/compute_metrics.py`` llama primero, y sin condición, a
  ``athlete_progression(db, competitor_id)`` — que sí está guardada — sobre
  el mismo ``competitor_id``; si es un tercero, el nodo aborta antes de
  llegar a ``compute_field_metrics``.
- ``training/newsletter_builder.py`` obtiene sus competidores con
  ``select(RaceCompetitor).where(athlete_id == athlete_id)``: por
  construcción nunca un tercero.

Los ``load_*`` de ``queries.py`` que alimentan a ambos no reciben
``competitor_id`` (cargan la temporada completa), así que no hay un punto
intermedio más temprano donde poner el candado.
"""
from __future__ import annotations

import functools
import inspect
import logging
from typing import Any, Awaitable, Callable, NoReturn, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.race_competitor import RaceCompetitor

logger = logging.getLogger(__name__)

__all__ = [
    "ALLOWED_SINGLE_EVENT",
    "ThirdPartyProgressionForbidden",
    "club_competitor_only",
    "require_club_competitor",
]


#: Atributo con el que ``club_competitor_only`` marca el callable que
#: devuelve. Es el único punto de enganche introspectable del barrido
#: estructural — cambiarlo rompe ``tests/privacy/test_third_party_lock.py``.
GUARD_MARKER_ATTR = "__club_competitor_guarded__"

#: Nombre del evento estructurado que se emite en cada rechazo. Sólo lleva
#: ids y un motivo enumerado — nunca nombre, club ni ciudad (Ley 1581).
REFUSAL_EVENT = "third_party_progression_refused"

#: Nombres de parámetro que el decorador reconoce como "la sesión". Si la
#: función no usa ninguno, cae al primer parámetro posicional.
_DB_PARAM_NAMES: tuple[str, ...] = ("db", "session", "db_session")


#: Código público del error, reproducido tal cual en la respuesta 403 del
#: borde del router (``contracts/third-party-lock.md``).
ERROR_CODE = "third_party_progression_forbidden"


class ThirdPartyProgressionForbidden(PermissionError):
    """Se pidió data longitudinal de un competidor no vinculado al club.

    El ``str()`` lleva sólo ids y un motivo enumerado — nunca nombre, club ni
    ciudad — y está pensado para el log del servidor.

    ``event_safe_message`` es la versión que SÍ puede publicarse: el
    decorador ``with_events`` del grafo persiste el mensaje de la excepción
    en ``agent_run_events``, y ese stream se sirve por
    ``GET /race-analysis/runs/{run_id}/status``. El id del competidor no
    tiene por qué viajar hasta ahí: identifica una fila de
    ``race_competitors`` que, en el caso que este candado existe para cubrir,
    es una persona ajena al club. El texto sustituto conserva el código para
    que el operador sepa qué pasó, sin el id. Convención genérica declarada
    en ``ai/events.py::EVENT_SAFE_MESSAGE_ATTR``: ese módulo no importa nada
    de acá, es la excepción la que se declara.
    """

    #: Ver ``app/services/race/ai/events.py::EVENT_SAFE_MESSAGE_ATTR``.
    event_safe_message = (
        f"{ERROR_CODE}: acceso denegado a un competidor no vinculado al club"
    )

    def __init__(self, competitor_id: int | None, *, reason: str = "not_linked") -> None:
        self.competitor_id = competitor_id
        self.reason = reason
        self.code = ERROR_CODE
        super().__init__(
            f"{ERROR_CODE} (competitor_id={competitor_id}, reason={reason})"
        )


#: Callables públicos con parámetro ``competitor_id`` que NO llevan candado,
#: cada uno con su justificación de una línea (revisado en T034/T036).
#:
#: Formato: ``(módulo, nombre, justificación)``.
ALLOWED_SINGLE_EVENT: tuple[tuple[str, str, str], ...] = (
    (
        "app.services.race.field_metrics",
        "compute_field_metrics",
        "Síncrona y pura sobre colecciones ya cargadas (no recibe db): no puede "
        "esperar al candado async. Sus dos llamadores de producción sólo pasan "
        "competidores ya vinculados — ver la nota del módulo.",
    ),
    (
        "app.services.race.competitor_linking",
        "suggest_athletes_for_competitor",
        "Sugiere candidatos de vinculación para un competidor todavía sin "
        "vincular; no devuelve progresión ni resultados, sólo scores de match.",
    ),
    (
        "app.services.race.competitor_linking",
        "link_competitor_to_athlete",
        "Es la acción misma de vincular: exigir vínculo previo sería "
        "contradictorio (ningún competidor podría vincularse nunca).",
    ),
    (
        "app.services.race.competitor_linking",
        "unlink_competitor",
        "Es la acción misma de desvincular: correrla detrás del candado "
        "impediría revertir un match equivocado del coach.",
    ),
    (
        "app.services.race.third_party_guard",
        "require_club_competitor",
        "Es el primitivo de enforcement y vive dentro del paquete barrido; no "
        "puede depender de sí mismo, y sólo devuelve el athlete_id vinculado.",
    ),
)


def _refuse(competitor_id: int | None, reason: str) -> NoReturn:
    """Emite el evento estructurado (sólo ids) y lanza la excepción."""
    logger.warning(
        "%s | competitor_id=%s reason=%s",
        REFUSAL_EVENT,
        competitor_id,
        reason,
    )
    raise ThirdPartyProgressionForbidden(competitor_id, reason=reason)


async def require_club_competitor(db: AsyncSession, competitor_id: int) -> int:
    """Devuelve el ``athlete_id`` vinculado a *competitor_id*, o lanza.

    Lee el estado actual de ``race_competitors`` en CADA llamada (sin caché
    de proceso): una desvinculación hecha por el coach surte efecto en la
    llamada siguiente, sin reiniciar la app.

    Args:
        db: Sesión async (``AsyncSession`` real o el ``FakeAsyncSession`` de
            los tests — sólo se usa ``execute(select(...))``).
        competitor_id: PK del ``RaceCompetitor`` consultado.

    Returns:
        El ``athlete_id`` del ``Athlete`` del club al que está vinculado.

    Raises:
        ThirdPartyProgressionForbidden: si el competidor no existe
            (``unknown_competitor``), si no se pasó id
            (``missing_competitor_id``) o si existe pero no está vinculado a
            ningún atleta del club (``not_linked``, el caso del tercero).

    Un ``competitor_id`` inexistente se rechaza igual que un tercero: no
    puede ser un competidor del club, y responder distinto filtraría por
    canal lateral qué ids existen en la tabla.
    """
    if competitor_id is None:
        _refuse(None, "missing_competitor_id")

    result = await db.execute(
        select(RaceCompetitor).where(RaceCompetitor.id == competitor_id)
    )
    competitor = result.scalar_one_or_none()
    if competitor is None:
        _refuse(competitor_id, "unknown_competitor")

    athlete_id = competitor.athlete_id
    if athlete_id is None:
        _refuse(competitor_id, "not_linked")

    return int(athlete_id)


_F = TypeVar("_F", bound=Callable[..., Awaitable[Any]])


def club_competitor_only(fn: _F) -> _F:
    """Decorador marcador: exige competidor vinculado antes del cuerpo.

    Resuelve la sesión y el ``competitor_id`` desde los argumentos reales de
    la llamada (posicionales o keyword) con ``inspect.signature.bind_partial``
    y llama a :func:`require_club_competitor`. **El cuerpo decorado no se
    ejecuta si el candado rechaza** — no hay ventana en la que se cargue
    data del tercero "y luego se filtre".

    Usa ``functools.wraps``, así que la función decorada conserva
    ``__module__``/``__qualname__`` y su firma original: el barrido
    estructural la sigue viendo en su módulo de origen. Marca el resultado
    con ``__club_competitor_guarded__ = True``.

    Raises:
        TypeError: en tiempo de import, si se aplica a una función sin
            parámetro ``competitor_id`` o a una función síncrona (el candado
            necesita hacer I/O).
    """
    sig = inspect.signature(fn)

    if "competitor_id" not in sig.parameters:
        raise TypeError(
            f"club_competitor_only: {fn.__qualname__} no tiene parámetro "
            "'competitor_id'; el candado no tendría qué validar."
        )
    if not inspect.iscoroutinefunction(fn):
        raise TypeError(
            f"club_competitor_only: {fn.__qualname__} es síncrona; el candado "
            "consulta la DB y sólo puede envolver corutinas."
        )

    db_param = next((name for name in _DB_PARAM_NAMES if name in sig.parameters), None)
    if db_param is None:
        db_param = next(iter(sig.parameters), None)
    if db_param is None:
        raise TypeError(
            f"club_competitor_only: {fn.__qualname__} no expone una sesión de DB."
        )

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        bound = sig.bind_partial(*args, **kwargs)
        bound.apply_defaults()
        db = bound.arguments.get(db_param)
        competitor_id = bound.arguments.get("competitor_id")
        if db is None:
            raise TypeError(
                f"club_competitor_only: {fn.__qualname__} se llamó sin sesión "
                f"de DB en '{db_param}'; el candado no puede validar."
            )
        await require_club_competitor(db, competitor_id)
        return await fn(*args, **kwargs)

    setattr(wrapper, GUARD_MARKER_ATTR, True)
    return wrapper  # type: ignore[return-value]
