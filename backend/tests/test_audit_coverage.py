"""Route-registry audit coverage (FR-009), T018.

`contracts/audit-recording.md` §7/§9 T4. Estado real del registro a hoy:
`AUDITED_ROUTES` tiene 111 claves, 99 de ellas `Audited` y el resto `Exempt`
(`app/services/audit.py`). Desde 2026-09-10 **todas** las exentas son
exenciones genuinas de §4.14 con su razón revisada: ya no queda ninguna con
el marcador "pending instrumentation". Lo que se comprueba aquí:

  T4.1 — registry completeness: every mutating route (POST/PUT/PATCH/DELETE)
         plus every `MUTATING_GETS` member (§4.13) has a registry entry.
  T4.2 — no stale entries: every registry key resolves to a mounted route
         (skipping strava-gated routes when `settings.strava_enabled` is
         off).
  T4.3 — exemptions are justified: every `Exempt` reason is >= 20 chars and
         the *exempt* subset of the registry equals the eleven §4.14 keys
         exactly, once instrumentation starts moving entries to `Audited`.
  T4.4a — mitad estática de FR-009: para cada ruta `Audited` montada, el
         grafo de llamadas de su handler alcanza `record_audit`. Es la red
         que evita que una ruta entre al registro como auditada sin que
         ningún camino escriba una fila.

La mitad **dinámica** de T4.4 (ejercitar la ruta y contar filas en
`audit_log`) sigue pendiente: necesita levantar la aplicación contra una base
real y un constructor de petición por ruta, y el contrato la limita a las
entradas "que declaren un factory", de las que todavía no hay ninguna. Esa
prueba recoge por eso cero casos — antes recogía las 81 rutas y las saltaba
una por una, que es lo que hacía parecer que la compuerta existía.

Aviso a quien edite este archivo: este docstring afirmó durante dos oleadas
que "every route is still `Exempt`" mucho después de dejar de ser cierto. Si
cambias el registro, cambia también lo que dice acá.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.main import app
from app.services.audit import (
    AUDITED_ROUTES,
    MUTATING_GETS,
    Audited,
    Exempt,
)
from tests.helpers.app_routes import iter_api_routes
from tests.helpers.audit_reachability import reaches_record_audit

#: The exact twelve §4.14 exemptions — every `Exempt` entry in the registry,
#: each with a genuine reviewed reason. The wave-1 placeholder
#: ("pending instrumentation") is gone: the last holder, the import dry-run,
#: became a settled exemption on 2026-09-10 because the route performs no
#: persistent write (see its reason in `app/services/audit.py`).
GENUINE_EXEMPTIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/refresh"),
        ("POST", "/api/auth/password-reset/request"),
        ("POST", "/api/profile/change-email/request"),
        ("POST", "/api/clubs/{club_id}/session-assistant/clarify"),
        ("POST", "/api/clubs/{club_id}/session-assistant/draft"),
        ("POST", "/api/race-analysis/chat"),
        ("POST", "/api/athletes/{athlete_id}/strava/connect"),
        ("POST", "/api/integrations/strava/webhook"),
        (
            "GET",
            "/api/athletes/{athlete_id}/monthly-newsletters/{newsletter_id}/render",
        ),
        ("GET", "/api/training-sessions/{session_id}/media"),
        ("POST", "/api/race-analysis/imports/{parse_id}/dry-run"),
    }
)

#: The two GETs of §4.14 that neither a POST/PUT/PATCH/DELETE walk nor
#: `MUTATING_GETS` reaches on their own (§4.14, penultimate paragraph). They
#: are excluded from T4.1's walk-derived `required` set on purpose.
_ADJUDICATED_READ_KEYS: frozenset[tuple[str, str]] = frozenset(
    {
        (
            "GET",
            "/api/athletes/{athlete_id}/monthly-newsletters/{newsletter_id}/render",
        ),
        ("GET", "/api/training-sessions/{session_id}/media"),
    }
)

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _mounted_mutating_routes() -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for route in iter_api_routes(app):
        methods = route.methods
        path = route.path
        if not methods or path is None:
            continue
        for method in methods:
            if method in _MUTATING_METHODS:
                routes.add((method, path))
    return routes


def _mounted_paths() -> set[tuple[str, str]]:
    """Every ``(method, path)`` FastAPI actually exposes, any method."""
    mounted: set[tuple[str, str]] = set()
    for route in iter_api_routes(app):
        methods = route.methods
        path = route.path
        if not methods or path is None:
            continue
        for method in methods:
            mounted.add((method, path))
    return mounted


def test_registry_completeness_covers_every_mutating_and_mutating_get_route() -> None:
    """T4.1 — a new mutating route merged without a decision fails here."""
    required = _mounted_mutating_routes() | MUTATING_GETS
    missing = required - set(AUDITED_ROUTES.keys())
    assert not missing, (
        "The following mutating/exporting routes have no AUDITED_ROUTES "
        f"entry — add an Audited(...) or Exempt(...) decision in "
        f"app/services/audit.py: {sorted(missing)}"
    )


def test_registry_has_no_stale_entries() -> None:
    """T4.2 — every registry key resolves to a mounted route.

    Strava-gated routes are skipped when `settings.strava_enabled` is off
    (§4.12), matching the app's own conditional mount in `app/main.py`.
    """
    mounted = _mounted_paths()

    stale: list[tuple[str, str]] = []
    for key in AUDITED_ROUTES:
        if key in _ADJUDICATED_READ_KEYS:
            # §4.14: these two are registry keys only, not reached by any
            # walk — see the module docstring in app/services/audit.py.
            continue
        if key in mounted:
            continue
        if not settings.strava_enabled and _is_strava_route(key):
            continue
        stale.append(key)

    assert not stale, (
        "The following AUDITED_ROUTES entries do not resolve to a mounted "
        f"route: {sorted(stale)}"
    )


_STRAVA_PATH_PREFIXES = (
    "/api/athletes/{athlete_id}/strava",
    "/api/integrations/strava",
    "/api/activities",
)


def _is_strava_route(key: tuple[str, str]) -> bool:
    _, path = key
    return path.startswith(_STRAVA_PATH_PREFIXES)


def test_exempt_reasons_are_at_least_twenty_characters() -> None:
    """T4.3 (part 1) — an `Exempt` with a placeholder-short reason is a
    registry entry nobody actually justified.
    """
    too_short = {
        key: policy.reason
        for key, policy in AUDITED_ROUTES.items()
        if isinstance(policy, Exempt) and len(policy.reason) < 20
    }
    assert not too_short, f"Exempt reason(s) shorter than 20 chars: {too_short}"


def test_genuine_exemption_set_matches_section_4_14_exactly() -> None:
    """T4.3 (part 2) — the *genuinely justified* exemptions (i.e. every
    `Exempt` whose reason is not the wave-1 placeholder) equal §4.14's
    twelve keys exactly. Any entry outside `GENUINE_EXEMPTIONS` with a real
    reason is undocumented; any `GENUINE_EXEMPTIONS` key without a real
    reason regressed to the placeholder.
    """
    genuinely_exempt = {
        key
        for key, policy in AUDITED_ROUTES.items()
        if isinstance(policy, Exempt) and policy.reason != "pending instrumentation"
    }
    assert genuinely_exempt == GENUINE_EXEMPTIONS


def test_no_route_is_both_audited_and_exempt() -> None:
    """Sanity: `AuditPolicy` is a union — a route is exactly one of the two,
    never listed twice under different keys.
    """
    for key, policy in AUDITED_ROUTES.items():
        assert isinstance(policy, (Audited, Exempt)), (key, policy)


def _audited_entries() -> list[tuple[tuple[str, str], Audited]]:
    return [
        (key, policy)
        for key, policy in AUDITED_ROUTES.items()
        if isinstance(policy, Audited)
    ]


def _audited_entries_with_a_mounted_route() -> list[tuple[tuple[str, str], Audited]]:
    """Las entradas `Audited` cuya ruta está montada en esta configuración.

    Las cuatro rutas de Strava desaparecen del router cuando
    `settings.strava_enabled` está en falso; T4.2 ya vigila que la clave del
    registro no quede huérfana, así que aquí simplemente no se recorren.
    """
    mounted = _mounted_route_endpoints()
    return [(key, policy) for key, policy in _audited_entries() if key in mounted]


def _mounted_route_endpoints() -> dict[tuple[str, str], object]:
    endpoints: dict[tuple[str, str], object] = {}
    for route in iter_api_routes(app):
        for method in route.methods or set():
            endpoints[(method, route.path)] = route.endpoint
    return endpoints


@pytest.mark.parametrize(
    "key,policy",
    _audited_entries_with_a_mounted_route(),
    ids=lambda value: f"{value[0]} {value[1]}" if isinstance(value, tuple) else "",
)
def test_audited_route_handler_reaches_record_audit(
    key: tuple[str, str], policy: Audited
) -> None:
    """FR-009, mitad estática: el handler declarado `Audited` sí audita.

    Recorre el grafo de llamadas del handler (por nombre, dentro del paquete
    `app`) y exige que alguna función alcanzable invoque `record_audit`. Es la
    red genérica que faltaba: sin ella, una ruta puede entrar al registro como
    `Audited` sin que ningún camino escriba una fila, y nadie se entera hasta
    que alguien confía en el historial.

    Lo que esta prueba **no** hace, dicho de frente: no ejercita la ruta, así
    que no comprueba ni el contenido de la fila ni que se escriba en tiempo de
    ejecución. Eso es el humo dinámico de `contracts/audit-recording.md` §9
    T4.4, que necesita levantar la aplicación contra una base real y sigue
    pendiente (ver `test_audited_route_writes_at_least_one_audit_log_row`).
    """
    endpoint = _mounted_route_endpoints()[key]
    assert reaches_record_audit(endpoint), (
        f"{key[0]} {key[1]} está en AUDITED_ROUTES como Audited"
        f"(entities={sorted(e.value for e in policy.entities)}) pero ningún "
        f"camino desde su handler `{getattr(endpoint, '__name__', endpoint)}` "
        f"llega a `record_audit`. O se instrumenta la ruta, o pasa a "
        f"`Exempt` con la razón de §4.14."
    )


#: Entradas `Audited` que declaran un constructor de petición para el humo
#: dinámico de §9 T4.4. Hoy `Audited` no tiene ese campo y ninguna entrada lo
#: declara, así que la parametrización de abajo recoge **cero** casos: es un
#: hueco reconocido, no una compuerta que pase en falso.
def _audited_entries_with_a_request_factory() -> list[tuple[tuple[str, str], Audited]]:
    return [
        (key, policy)
        for key, policy in _audited_entries()
        if getattr(policy, "request_factory", None) is not None
    ]


@pytest.mark.parametrize("key,policy", _audited_entries_with_a_request_factory())
def test_audited_route_writes_at_least_one_audit_log_row(
    key: tuple[str, str], policy: Audited
) -> None:
    """T4.4, humo dinámico — parametrizado sobre las entradas que declaran un
    constructor de petición, como pide el contrato (§9 T4.4: "parametrised
    over the `Audited` entries that declare a factory").

    Ninguna lo declara todavía, así que esta prueba recoge cero casos. Antes
    recogía las 81 rutas y las saltaba una por una, lo que hacía parecer que
    la compuerta existía. La mitad estática de FR-009 sí está cubierta, por
    `test_audited_route_handler_reaches_record_audit`.

    Para completarla hace falta una base real (el fixture `client` levanta la
    aplicación contra MySQL) y sintetizar una petición válida por ruta.
    """
    raise AssertionError(  # pragma: no cover - hoy no se recoge ningún caso
        f"{key}: llegó un caso con factory pero el humo dinámico no está "
        f"implementado (entities={sorted(e.value for e in policy.entities)})."
    )
