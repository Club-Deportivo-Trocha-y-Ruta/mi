"""Route-registry audit coverage (FR-009), T018.

`contracts/audit-recording.md` §7/§9 T4. This wave (T017/T018) instruments
no route yet — `AUDITED_ROUTES` is 110 keys, every one of them `Exempt`
(`app/services/audit.py`). This test file therefore only carries the static
tests that must hold from day one:

  T4.1 — registry completeness: every mutating route (POST/PUT/PATCH/DELETE)
         plus every `MUTATING_GETS` member (§4.13) has a registry entry.
  T4.2 — no stale entries: every registry key resolves to a mounted route
         (skipping strava-gated routes when `settings.strava_enabled` is
         off).
  T4.3 — exemptions are justified: every `Exempt` reason is >= 20 chars and
         the *exempt* subset of the registry equals the eleven §4.14 keys
         exactly, once instrumentation starts moving entries to `Audited`.

The dynamic smoke test (T4.4) is parametrised over `Audited` entries that
declare a factory; there are none yet, so it collects zero cases and is a
no-op until Phase 3 lands the first `Audited(...)` entry.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.main import app
from tests.helpers.app_routes import iter_api_routes
from app.services.audit import (
    AUDITED_ROUTES,
    MUTATING_GETS,
    Audited,
    Exempt,
)

#: The exact eleven §4.14 exemptions — the only ones with a genuine,
#: reviewed reason. Every other `Exempt` entry in the registry today carries
#: the wave-1 placeholder ("pending instrumentation") and is expected to
#: disappear from this set, one entry at a time, as Phase 3 instruments it.
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
    eleven keys exactly. Any entry outside `GENUINE_EXEMPTIONS` with a real
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


@pytest.mark.parametrize("key,policy", _audited_entries())
def test_audited_route_writes_at_least_one_audit_log_row(
    key: tuple[str, str], policy: Audited
) -> None:
    """T4.4 dynamic smoke, parametrised over `Audited` entries.

    ATENCIÓN — este gancho **no comprueba nada todavía**: hace `skip` para
    todas las rutas, así que la mitad de FR-009 que exige "toda ruta auditada
    que la suite ejercita escribió al menos una fila" (contracts/audit-recording.md
    §9) no está implementada. Su docstring anterior decía "zero `Audited`
    entries — every route is still `Exempt`", lo cual dejó de ser cierto: hoy
    el registro tiene 91 rutas `Audited` y las 81 que llegan aquí se saltan
    una por una.

    Cada ruta instrumentada sí tiene su prueba de integración dedicada junto a
    su handler; lo que falta es esta red genérica, que es la que evitaría que
    una ruta futura se quede sin fila sin que nadie se entere. Ver la brecha
    correspondiente en checklists/integration-review.md.
    """
    pytest.skip(
        f"{key}: dynamic smoke test not yet wired for this route "
        f"(entities={sorted(e.value for e in policy.entities)})"
    )
