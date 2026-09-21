"""T032/T033 — candado de progresión de terceros (US3, FR-012..FR-015).

Contrato: ``specs/044-race-history-backfill/contracts/third-party-lock.md``
(ver también ``research.md`` R-07). El módulo bajo prueba,
``app/services/race/third_party_guard.py``, todavía NO existe — esto es
TDD (T034 lo crea, T035 lo aplica). Por eso el import de abajo falla hoy con
``ModuleNotFoundError`` y TODO este archivo aborta en collection. Verificado
corriendo ``pytest tests/privacy/test_third_party_lock.py -q`` (rojo por
código ausente, no por un typo).

T032 — parte estructural
-------------------------
``_discover_competitor_id_callables()`` recorre ``app.services.race`` (todos
los submódulos, incl. ``ai/``, ``course/``, ``agents/``, ``eval/``) vía
``pkgutil``/``importlib``/``inspect`` y recolecta todo callable público de
primer nivel cuya firma incluye un parámetro ``competitor_id``. El barrido
real, verificado contra un stub temporal del propio candado durante la
escritura de este archivo — ver más abajo) encontró exactamente 7
candidatos — fijados en ``EXPECTED_CANDIDATES`` para que un cambio en la
superficie sea una decisión explícita, no un silencio:

- ``analytics.athlete_progression``                      — GUARDADA (historial completo, N válidas)
- ``analytics.projection``                                — GUARDADA (regresión sobre histórico)
- ``field_metrics.compute_field_metrics``                 — ALLOWED_SINGLE_EVENT
- ``competitor_linking.suggest_athletes_for_competitor``  — ALLOWED_SINGLE_EVENT
- ``competitor_linking.link_competitor_to_athlete``       — ALLOWED_SINGLE_EVENT
- ``competitor_linking.unlink_competitor``                — ALLOWED_SINGLE_EVENT
- ``third_party_guard.require_club_competitor``           — ALLOWED_SINGLE_EVENT

El séptimo candidato es un hallazgo del propio barrido, no anticipado por
el contrato: ``third_party_guard.py`` vive DENTRO de ``app.services.race``,
así que su propia función ``require_club_competitor(db, competitor_id)``
—el primitivo de enforcement— también matchea el patrón "público +
parámetro competitor_id". No puede depender de sí misma (circular), y no
devuelve datos de progresión (sólo el ``athlete_id`` vinculado, o excepción)
— va a ``ALLOWED_SINGLE_EVENT`` con esa justificación. Confirmado corriendo
este archivo contra un stub temporal del candado (ver nota de verificación
al final del docstring).

Decisión de diseño (instrucción del team-lead: "si no hay forma robusta de
inferir 'devuelve datos de más de una válida', sé conservador"): el barrido
NO intenta inferir el rango de válidas cubierto por el valor de retorno —
eso es frágil (tipos de retorno heterogéneos: DataFrame, dict, list). En
cambio exige marca o allow-list para TODO callable público con
``competitor_id``, sin excepción. Los 4 casos de arriba que van a
``ALLOWED_SINGLE_EVENT`` no son realmente "de una sola válida" (dos de
ellos sí agregan varias válidas) — es el nombre que fija el contrato, se
mantiene tal cual para que T034 lo importe con ese nombre exacto.

Nota sobre ``compute_field_metrics``: es una función **síncrona y pura**
sobre colecciones ORM ya cargadas (no recibe ``db``), así que no puede
llamar/esperar ``require_club_competitor`` ni ser envuelta por el
decorador async ``@club_competitor_only`` tal como lo describe el
contrato. Sus dos únicos call sites de producción
(``app/services/race/ai/nodes/compute_metrics.py`` — donde corre DESPUÉS de
que ``athlete_progression`` ya validó el mismo ``competitor_id`` en la misma
función — y ``app/services/training/newsletter_builder.py`` — donde el
``competitor_id`` sale siempre de ``select(RaceCompetitor).where(athlete_id
== athlete_id)``, por construcción nunca un tercero) sólo pasan un
competitor ya vinculado. Ver la justificación exacta en
``ALLOWED_SINGLE_EVENT`` una vez T034 la escriba.

Discrepancia con la prosa del contrato: ``analytics.podium_gap`` aparece
mencionada en ``third-party-lock.md``/``research.md`` R-07 como una de las
funciones "at minimum" a guardar, pero su firma actual
(``podium_gap(db, category_id, season)``) NO tiene parámetro
``competitor_id`` — filtra internamente a ``athlete_id IS NOT NULL`` (sólo
TyR) antes de construir su grilla, así que nunca puede devolver la fila de
un tercero sin importar qué ``competitor_id`` exista en la tabla. El barrido
estructural, tal como está especificado ("callables con parámetro
competitor_id"), correctamente NO la marca como candidata. Se deja
documentado acá para que T034/T036 no lo lean como un descuido.

``projection`` no tiene ningún llamador de producción hoy (sólo aparece en
tests) — igual se guarda, por ser superficie pública exportada que podría
conectarse a un router en cualquier momento futuro.

Convención asumida con T034 (no está textual en el contrato, es el único
punto de enganche introspectable posible): ``club_competitor_only`` debe
setear ``fn.__club_competitor_guarded__ = True`` en el callable que
devuelve, y usar ``functools.wraps(fn)`` para conservar
``__module__``/``__qualname__``/la firma original (``inspect.signature``
sigue ``__wrapped__`` automáticamente) — si no usa ``functools.wraps``, la
función decorada "desaparece" de su módulo de origen para el barrido de
``pkgutil`` y este test dejaría de vigilarla en silencio.

T033 — parte de comportamiento
--------------------------------
Un competidor NO vinculado (tercero, nombre sintético evidentemente falso)
con resultados en tres temporadas es rechazado por ``require_club_competitor``
y por las funciones guardadas, sin importar el rol de quien termine
llamando (el candado es una función pura del estado de la DB — no recibe
rol — por diseño del propio contrato: ``require_club_competitor(db,
competitor_id) -> int``). Hoy no existe ningún router que exponga
``competitor_id`` crudo por rol (el único llamador de producción de
``athlete_progression`` resuelve ``competitor_id`` desde un ``athlete_id``
ya autorizado por ``_ensure_athlete_club_access``/``verify_athlete_access``)
— la parametrización por rol es, por tanto, una prueba de defensa en
profundidad a nivel de servicio: fija que ningún camino futuro condicione
el candado al rol de quien llama, no un test de RBAC de router (ese llega
con T035/T072).

Privacidad: nombre sintético evidentemente ficticio ("Tercero Ajeno
Ficticio"), nunca un dato real de un menor.
"""

from __future__ import annotations

import importlib
import inspect
import json
import logging
import pkgutil
import re
import unicodedata
from datetime import date
from typing import Any, Callable

import pytest

import app.services.race as race_pkg
from app.models.race_competitor import RaceCompetitor
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries
from app.models.user import UserRole
from app.services.ai.models import LLMMessage, LLMRequest
from app.services.ai.providers.fake import FakeLLMProvider
from app.services.race.analytics import athlete_progression, projection
from app.services.race.field_metrics import compute_field_metrics
from tests.services.race.conftest import FakeAsyncSession, _build_seeded_store

# El módulo bajo prueba no existe todavía (TDD, T034) — este import es el
# que hace fallar todo el archivo en collection hoy (ModuleNotFoundError).
from app.services.race.third_party_guard import (
    ALLOWED_SINGLE_EVENT,
    ThirdPartyProgressionForbidden,
    club_competitor_only,
    require_club_competitor,
)


# ---------------------------------------------------------------------------
# T032 — barrido estructural
# ---------------------------------------------------------------------------

_GUARD_MARKER_ATTR = "__club_competitor_guarded__"

EXPECTED_CANDIDATES: set[tuple[str, str]] = {
    ("app.services.race.analytics", "athlete_progression"),
    ("app.services.race.analytics", "projection"),
    ("app.services.race.competitor_linking", "link_competitor_to_athlete"),
    ("app.services.race.competitor_linking", "suggest_athletes_for_competitor"),
    ("app.services.race.competitor_linking", "unlink_competitor"),
    ("app.services.race.field_metrics", "compute_field_metrics"),
    ("app.services.race.third_party_guard", "require_club_competitor"),
}


def _is_marked(fn: Callable[..., Any]) -> bool:
    """True si *fn* fue decorada con ``@club_competitor_only``."""
    return getattr(fn, _GUARD_MARKER_ATTR, False) is True


#: Forma de parámetro que el barrido considera "ids de competidor". Desde la
#: nota de auditoría de T036 (feature 044, US4) no basta con ``competitor_id``
#: literal: ``competitor_ids: list[int]`` — la forma que necesitaría una
#: operación por lotes como la revisión de identidad — pasaba sin detectar.
#: El patrón cubre ``competitor_id``, ``competitor_ids`` y cualquier prefijo
#: (``other_competitor_id``, ``keep_competitor_ids``...).
_COMPETITOR_PARAM_RE = re.compile(r"(^|_)competitor_ids?$")


def _competitor_params(fn: Callable[..., Any]) -> list[str]:
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return []
    return [p for p in sig.parameters if _COMPETITOR_PARAM_RE.search(p)]


def _public_callables(module: Any, modname: str) -> list[tuple[str, Callable[..., Any]]]:
    """Funciones públicas de primer nivel y métodos públicos de clases
    públicas definidas en el módulo (``Clase.metodo``)."""
    out: list[tuple[str, Callable[..., Any]]] = []
    for name, obj in vars(module).items():
        if name.startswith("_") or getattr(obj, "__module__", None) != modname:
            continue
        if inspect.isfunction(obj):
            out.append((name, obj))
        elif inspect.isclass(obj):
            for mname, member in vars(obj).items():
                if mname.startswith("_"):
                    continue
                fn = member.__func__ if isinstance(member, (staticmethod, classmethod)) else member
                if inspect.isfunction(fn):
                    out.append((f"{name}.{mname}", fn))
    return out


def _discover_competitor_id_callables() -> list[tuple[str, str, Callable[..., Any]]]:
    """Recorre ``app.services.race`` y devuelve ``(module, name, fn)`` para
    todo callable público — función de primer nivel o método público de una
    clase pública — cuya firma incluye un parámetro de ids de competidor
    (``_COMPETITOR_PARAM_RE``: ``competitor_id``, ``competitor_ids``, …).

    Sólo cuenta objetos DEFINIDOS en el módulo que se está recorriendo
    (``__module__ == modname``) — evita contar dos veces un mismo
    callable reexportado bajo un alias en otro módulo (frecuente en este
    paquete: ``analytics.py`` reexporta varios ``_load_*`` de
    ``queries.py``, pero esos alias empiezan con ``_`` y ya quedan afuera
    por el filtro de "público").
    """
    found: list[tuple[str, str, Callable[..., Any]]] = []
    for _finder, modname, _ispkg in pkgutil.walk_packages(
        race_pkg.__path__, prefix=f"{race_pkg.__name__}."
    ):
        module = importlib.import_module(modname)
        for name, fn in _public_callables(module, modname):
            if _competitor_params(fn):
                found.append((modname, name, fn))
    return found


def test_scan_detects_list_of_competitor_ids_and_public_methods() -> None:
    """Autoprueba del barrido (nota de auditoría T036): la forma por lotes y
    los métodos públicos se detectan; los privados no."""
    import types

    fake = types.ModuleType("app.services.race._scan_probe")

    def batch(db: Any, competitor_ids: list[int]) -> None: ...

    def other(db: Any, keep_competitor_id: int) -> None: ...

    def _private(db: Any, competitor_ids: list[int]) -> None: ...

    class Service:
        def run(self, competitor_ids: list[int]) -> None: ...

        def _hidden(self, competitor_id: int) -> None: ...

    for obj in (batch, other, _private, Service):
        obj.__module__ = fake.__name__
        setattr(fake, obj.__name__, obj)
    for fn in (Service.run, Service._hidden):
        fn.__module__ = fake.__name__

    names = {n for n, fn in _public_callables(fake, fake.__name__) if _competitor_params(fn)}
    assert names == {"batch", "other", "Service.run"}


def test_discovered_surface_matches_reviewed_snapshot() -> None:
    """Fija la superficie actual (insumo para T034/T036). Un cambio en esta
    lista debe ser una decisión explícita del reviewer, no un accidente:
    si falla, decide si el nuevo callable necesita ``@club_competitor_only``
    o una entrada justificada en ``ALLOWED_SINGLE_EVENT``, y sólo entonces
    actualiza ``EXPECTED_CANDIDATES``."""
    discovered = {(m, n) for m, n, _fn in _discover_competitor_id_callables()}
    assert discovered == EXPECTED_CANDIDATES


def test_every_competitor_id_callable_is_guarded_or_allowlisted() -> None:
    """El test cuya gracia es que una función nueva sin candado rompa CI."""
    allowed = {(mod, name) for mod, name, _just in ALLOWED_SINGLE_EVENT}
    offenders = [
        f"{modname}.{name}"
        for modname, name, fn in _discover_competitor_id_callables()
        if not _is_marked(fn) and (modname, name) not in allowed
    ]
    assert not offenders, (
        "Callable(s) público(s) con competitor_id sin @club_competitor_only "
        "ni entrada en ALLOWED_SINGLE_EVENT: " + ", ".join(sorted(offenders))
    )


def test_allowed_single_event_entries_are_short_and_justified() -> None:
    """"Tupla corta y revisada, cada entrada con su justificación de una
    línea" (contrato)."""
    assert len(ALLOWED_SINGLE_EVENT) <= 8, (
        f"ALLOWED_SINGLE_EVENT tiene {len(ALLOWED_SINGLE_EVENT)} entradas — "
        "revisa si de verdad todas necesitan estar exentas del candado."
    )
    for entry in ALLOWED_SINGLE_EVENT:
        assert len(entry) == 3, f"Entrada mal formada en ALLOWED_SINGLE_EVENT: {entry!r}"
        modname, name, justification = entry
        assert isinstance(modname, str) and modname.startswith("app.services.race")
        assert isinstance(name, str) and name
        assert isinstance(justification, str) and len(justification.strip()) >= 10, (
            f"{modname}.{name}: falta justificación (o es demasiado corta)"
        )


def test_guarded_functions_are_not_also_allowlisted() -> None:
    """Un callable no debería depender de dos mecanismos de protección a la
    vez — sería ambiguo cuál lo protege realmente."""
    allowed = {(mod, name) for mod, name, _just in ALLOWED_SINGLE_EVENT}
    for modname, name, fn in _discover_competitor_id_callables():
        if _is_marked(fn):
            assert (modname, name) not in allowed, (
                f"{modname}.{name} está marcada Y en ALLOWED_SINGLE_EVENT"
            )


# ---------------------------------------------------------------------------
# T033 — escenario común de comportamiento
# ---------------------------------------------------------------------------

_THIRD_PARTY_FULL_NAME = "Tercero Ajeno Ficticio"
_CLUB_COMPETITOR_NAME = "Deportista Club Ficticio"
_CLUB_ATHLETE_ID = 4242
_CATEGORY_CODE = "INF_A"
_SEASONS = (2024, 2025, 2026)


def _normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def _name_in_text(name: str, haystack: str) -> bool:
    """True si *name* (o algún token de ≥4 letras) aparece en *haystack*,
    insensible a mayúsculas/tildes. Mismo patrón que
    ``tests/services/race/ai/test_race_ai_privacy_invariants.py``."""
    norm_haystack = _normalize(haystack)
    for token in name.split():
        if len(token) >= 4 and _normalize(token) in norm_haystack:
            return True
    return _normalize(name) in norm_haystack


def _seed_third_party_scenario() -> tuple[FakeAsyncSession, RaceCompetitor, RaceCompetitor]:
    """Un competidor de club (vinculado, ``athlete_id`` fijo) y un tercero
    (sin vincular), ambos con resultados en tres temporadas de la MISMA
    categoría/válida — para que el "pelotón" de ``compute_field_metrics``
    sea realista (el tercero aporta denominador, nunca identidad).

    Devuelve ``(session, club_competitor, third_party_competitor)``.
    """
    store = _build_seeded_store()
    category = next(c for c in store.categories.values() if c.code == _CATEGORY_CODE)

    club_cid = store.next_id("competitors")
    club_competitor = RaceCompetitor(
        id=club_cid,
        normalized_name=_CLUB_COMPETITOR_NAME.lower(),
        display_name=_CLUB_COMPETITOR_NAME,
        club_text="Club Trocha y Ruta",
        athlete_id=_CLUB_ATHLETE_ID,
    )
    store.competitors[club_cid] = club_competitor

    third_cid = store.next_id("competitors")
    third_party = RaceCompetitor(
        id=third_cid,
        normalized_name=_THIRD_PARTY_FULL_NAME.lower(),
        display_name=_THIRD_PARTY_FULL_NAME,
        club_text="Club Externo Ficticio",
        athlete_id=None,
    )
    store.competitors[third_cid] = third_party

    for season in _SEASONS:
        sid = store.next_id("series")
        store.series[sid] = RaceSeries(
            id=sid,
            name="Copa Valle de Ciclomontañismo",
            season_year=season,
            organizer="Liga",
            points_scheme_code=f"copa_valle_{season}",
        )

        eid = store.next_id("events")
        store.events[eid] = RaceEvent(
            id=eid,
            series_id=sid,
            sequence_number=1,
            name=f"VALIDA I {season}",
            event_date=date(season, 3, 15),
            location="Cali",
            is_championship=False,
            status=RaceEventStatus.COMPLETED,
            created_by_user_id=1,
        )

        for comp, pos, t_ms, pts in (
            (club_competitor, 2, 1_700_000, 30),
            (third_party, 5, 1_900_000, 10),
        ):
            rid = store.next_id("results")
            store.results[rid] = RaceResult(
                id=rid,
                event_id=eid,
                category_id=category.id,
                competitor_id=comp.id,
                athlete_id=comp.athlete_id,
                position=pos,
                status=ResultStatus.FINISHED,
                race_time_ms=t_ms,
                points_awarded=pts,
                created_by_user_id=1,
            )

    return FakeAsyncSession(store=store), club_competitor, third_party


# ---------------------------------------------------------------------------
# require_club_competitor — contrato central, en aislamiento
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_club_competitor_raises_for_unlinked_third_party() -> None:
    db, _club, third_party = _seed_third_party_scenario()
    with pytest.raises(ThirdPartyProgressionForbidden):
        await require_club_competitor(db, third_party.id)


@pytest.mark.asyncio
async def test_require_club_competitor_returns_athlete_id_for_linked() -> None:
    db, club_competitor, _third = _seed_third_party_scenario()
    athlete_id = await require_club_competitor(db, club_competitor.id)
    assert athlete_id == _CLUB_ATHLETE_ID


@pytest.mark.asyncio
async def test_require_club_competitor_raises_for_unknown_competitor_id() -> None:
    """Un ``competitor_id`` que no existe se rechaza igual que un tercero.

    Añadido en T035 (a pedido del lead) para fijar la decisión de diseño de
    ``require_club_competitor``: no puede ser un competidor del club, y
    responder distinto —devolver un DataFrame vacío, o un error de "no
    encontrado"— convertiría la función en un oráculo de existencia:
    alguien que pruebe ids uno por uno sabría cuáles corresponden a una
    persona real en ``race_competitors``. Con varios cientos de menores
    ajenos cargados por la 044, esa distinción es información sobre ellos.
    """
    db, _club, _third = _seed_third_party_scenario()
    unknown_id = max(db.store.competitors) + 1_000

    with pytest.raises(ThirdPartyProgressionForbidden):
        await require_club_competitor(db, unknown_id)


@pytest.mark.asyncio
async def test_unknown_and_unlinked_are_indistinguishable_from_outside() -> None:
    """El id inexistente y el tercero sin vincular son indistinguibles.

    Misma excepción y mismo ``code`` público: lo único que los diferencia es
    ``reason``, que viaja al log del servidor y NUNCA al cuerpo de la
    respuesta HTTP (el borde del router sólo serializa ``exc.code``). Si
    alguna vez ``reason`` empezara a salir en la respuesta, este test seguiría
    pasando pero el canal lateral volvería — por eso el handler de
    ``app/main.py`` es parte del contrato, no un detalle de presentación.
    """
    db, _club, third_party = _seed_third_party_scenario()
    unknown_id = max(db.store.competitors) + 1_000

    with pytest.raises(ThirdPartyProgressionForbidden) as unlinked_exc:
        await require_club_competitor(db, third_party.id)
    with pytest.raises(ThirdPartyProgressionForbidden) as unknown_exc:
        await require_club_competitor(db, unknown_id)

    assert type(unlinked_exc.value) is type(unknown_exc.value)
    assert unlinked_exc.value.code == unknown_exc.value.code
    # El motivo interno sí distingue — es lo que el operador necesita en el log.
    assert unlinked_exc.value.reason == "not_linked"
    assert unknown_exc.value.reason == "unknown_competitor"


@pytest.mark.asyncio
async def test_guarded_function_refuses_unknown_competitor_id() -> None:
    """El id inexistente también corta en una función guardada, no sólo en el
    primitivo: antes de la 044, ``athlete_progression`` con un id cualquiera
    devolvía un DataFrame vacío sin preguntar nada."""
    db, _club, _third = _seed_third_party_scenario()
    unknown_id = max(db.store.competitors) + 1_000

    with pytest.raises(ThirdPartyProgressionForbidden):
        await athlete_progression(db, unknown_id)


@pytest.mark.asyncio
async def test_require_club_competitor_reads_current_state_after_unlink() -> None:
    """"Lee estado actual, así que una desvinculación aplica de inmediato"
    (contrato). Se simula la desvinculación mutando ``athlete_id`` en el
    mismo objeto que ``unlink_competitor`` mutaría en producción — no se
    invoca el servicio de linking completo (fuera de alcance de este
    archivo, tiene su propia cobertura en ``test_race_competitors.py``)."""
    db, club_competitor, _third = _seed_third_party_scenario()

    assert await require_club_competitor(db, club_competitor.id) == _CLUB_ATHLETE_ID

    club_competitor.athlete_id = None

    with pytest.raises(ThirdPartyProgressionForbidden):
        await require_club_competitor(db, club_competitor.id)


@pytest.mark.asyncio
async def test_club_competitor_only_marks_and_enforces_before_body_runs() -> None:
    """Contrato de ``club_competitor_only`` en aislamiento: (1) marca el
    callable que devuelve para que el barrido estructural lo reconozca, y
    (2) valida ``competitor_id`` ANTES de ejecutar el cuerpo decorado — el
    cuerpo nunca corre para un tercero."""

    calls: list[int] = []

    @club_competitor_only
    async def _dummy(db: Any, competitor_id: int) -> str:
        calls.append(competitor_id)
        return "ok"

    assert _is_marked(_dummy)

    db, club_competitor, third_party = _seed_third_party_scenario()

    with pytest.raises(ThirdPartyProgressionForbidden):
        await _dummy(db, third_party.id)
    assert calls == []

    result = await _dummy(db, club_competitor.id)
    assert result == "ok"
    assert calls == [club_competitor.id]


# ---------------------------------------------------------------------------
# Funciones guardadas — rechazo/servicio, sin importar el rol de quien llama
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", list(UserRole))
class TestGuardedFunctionsIgnoreCallerRole:
    """``require_club_competitor(db, competitor_id)`` no recibe rol — es
    puramente función del estado de la DB. Parametrizar por los 4 roles del
    proyecto (admin/coach/parent/athlete) fija, como regresión, que ningún
    camino futuro condicione el candado al rol de quien llama: sea cual sea
    el rol autenticado que termine invocando ``athlete_progression``/
    ``projection``, un ``competitor_id`` no vinculado se rechaza igual, y
    uno vinculado se sirve igual. Ver docstring del módulo para por qué esto
    se prueba a nivel de servicio y no de router."""

    @pytest.mark.asyncio
    async def test_athlete_progression_refused_for_unlinked(self, role: UserRole) -> None:
        db, _club, third_party = _seed_third_party_scenario()
        with pytest.raises(ThirdPartyProgressionForbidden):
            await athlete_progression(db, third_party.id)

    @pytest.mark.asyncio
    async def test_projection_refused_for_unlinked(self, role: UserRole) -> None:
        db, _club, third_party = _seed_third_party_scenario()
        with pytest.raises(ThirdPartyProgressionForbidden):
            await projection(db, third_party.id, next_event_id=999_999)

    @pytest.mark.asyncio
    async def test_athlete_progression_served_for_linked(self, role: UserRole) -> None:
        db, club_competitor, _third = _seed_third_party_scenario()
        df = await athlete_progression(db, club_competitor.id)
        assert len(df) == len(_SEASONS)

    @pytest.mark.asyncio
    async def test_projection_served_for_linked(self, role: UserRole) -> None:
        db, club_competitor, _third = _seed_third_party_scenario()
        result = await projection(db, club_competitor.id, next_event_id=999_999)
        assert result["n_samples"] == len(_SEASONS)

    @pytest.mark.asyncio
    async def test_refused_again_immediately_after_unlink(self, role: UserRole) -> None:
        db, club_competitor, _third = _seed_third_party_scenario()

        df = await athlete_progression(db, club_competitor.id)
        assert len(df) == len(_SEASONS)

        club_competitor.athlete_id = None

        with pytest.raises(ThirdPartyProgressionForbidden):
            await athlete_progression(db, club_competitor.id)


# ---------------------------------------------------------------------------
# Barrido de PII — logs, prompt de IA, "contexto de boletín"/familia
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_third_party_name_leaks_into_logs_or_ai_prompt(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Durante los intentos de acceso al tercero (rechazados, para los 4
    roles) y al club (permitido), ni los logs ni el prompt que llegaría al
    LLM contienen su nombre.

    "Contexto del boletín" y "respuestas a familias" se cubren acá a través
    de las DOS funciones de producción que efectivamente los alimentan:

    - ``athlete_progression`` — lo que ``newsletter_builder._build_race_block``
      vuelca casi verbatim en ``results[]``, que es lo que ve la familia
      (y lo que usa el nodo de IA ``compute_metrics``).
    - ``compute_field_metrics`` — alimenta ``championships[]`` del boletín
      Y el bloque de pelotón del analista de IA (feature 037/039); se
      construye aquí con AMBOS competidores compartiendo válida/categoría
      para probar que el agregado nunca expone al tercero aunque comparta
      "pelotón" con el atleta del club.

    No se reconstruye el pipeline completo de boletín/IA (LangGraph, DB
    real, plantillas Jinja) — eso es infraestructura pesada fuera de
    alcance de este archivo de privacidad; en cambio se prueba, con datos
    reales de ambos competidores, que las funciones que PRODUCEN esos
    contextos jamás emiten el nombre del tercero.
    """
    caplog.set_level(logging.DEBUG)
    db, club_competitor, third_party = _seed_third_party_scenario()

    # 1) Intentos rechazados contra el tercero — uno por rol.
    for _role in UserRole:
        with pytest.raises(ThirdPartyProgressionForbidden):
            await require_club_competitor(db, third_party.id)
        with pytest.raises(ThirdPartyProgressionForbidden):
            await athlete_progression(db, third_party.id)

    # 2) Camino permitido: el propio deportista del club.
    progression_df = await athlete_progression(db, club_competitor.id)
    progression_dump = progression_df.to_json()
    assert not _name_in_text(_THIRD_PARTY_FULL_NAME, progression_dump)

    # 3) field_metrics — pelotón compartido con el tercero.
    field_ctx = compute_field_metrics(
        results=list(db.store.results.values()),
        events=list(db.store.events.values()),
        series=list(db.store.series.values()),
        categories=list(db.store.categories.values()),
        competitor_id=club_competitor.id,
        season=_SEASONS[-1],
    )
    field_dump = json.dumps(field_ctx, default=str)
    assert not _name_in_text(_THIRD_PARTY_FULL_NAME, field_dump)

    # 4) Ese mismo dump es, en los hechos, lo que agents/analyst.py
    #    convierte en texto de prompt — se envía a un FakeLLMProvider
    #    (mismo patrón que tests/test_ai_monthly_report_privacy.py) y se
    #    barre last_request.
    provider = FakeLLMProvider(canned="ok")
    request = LLMRequest(
        system="Eres un analista de rendimiento deportivo juvenil.",
        messages=(LLMMessage(role="user", content=field_dump),),
        use_case="test_third_party_lock",
    )
    await provider.complete(request)
    assert provider.last_request is not None
    sent_text = provider.last_request.system + "\n" + "\n".join(
        m.content for m in provider.last_request.messages
    )
    assert not _name_in_text(_THIRD_PARTY_FULL_NAME, sent_text)

    # 5) Barrido final de logs — nada de lo anterior debió loguear el
    #    nombre del tercero (ni siquiera el mensaje de rechazo del
    #    candado, que T035 documenta como "third_party_progression_refused
    #    con ids únicamente").
    assert not _name_in_text(_THIRD_PARTY_FULL_NAME, caplog.text)
