"""Recorrido de rutas de la aplicación tolerante a la versión de FastAPI.

Hasta FastAPI 0.11x, ``app.include_router(...)`` aplanaba las rutas del router
dentro de ``app.routes``, así que una prueba podía recorrer ``app.routes`` y ver
cada ``APIRoute`` con su ruta ya prefijada. Desde FastAPI 0.14x el montaje es
perezoso: ``app.routes`` guarda un objeto interno ``_IncludedRouter`` por cada
``include_router`` y las rutas efectivas solo se resuelven al atender la
petición (o al construir el OpenAPI).

Esto importa mucho aquí: la prueba de cobertura de auditoría (FR-009,
``tests/test_audit_coverage.py``) recorre las rutas para exigir que cada
endpoint de escritura esté en ``AUDITED_ROUTES`` o en ``EXEMPT_ROUTES``. Con la
versión nueva, recorrer ``app.routes`` a secas devuelve cero endpoints y la
compuerta **pasa en falso**, que es peor que fallar. Este ayudante normaliza
las dos formas para que la compuerta siga midiendo lo que dice medir.

Uso::

    from tests.helpers.app_routes import iter_api_routes

    for route in iter_api_routes(app):
        route.path      # ruta completa, ya prefijada ("/api/athletes/{athlete_id}")
        route.methods   # set[str]
        route.endpoint  # la función de la vista
        route.name
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(frozen=True)
class ResolvedRoute:
    """Una ruta efectiva de la aplicación, con su prefijo ya aplicado."""

    path: str
    methods: frozenset[str]
    endpoint: Any
    name: str | None = None


def _as_resolved(path: str, route: Any) -> ResolvedRoute:
    return ResolvedRoute(
        path=path,
        methods=frozenset(getattr(route, "methods", None) or ()),
        endpoint=getattr(route, "endpoint", None),
        name=getattr(route, "name", None),
    )


def iter_api_routes(app: Any) -> Iterator[ResolvedRoute]:
    """Devuelve cada endpoint de la aplicación con su ruta completa.

    Funciona tanto con el montaje aplanado (FastAPI <= 0.11x) como con el
    montaje perezoso vía ``_IncludedRouter`` (FastAPI >= 0.14x).
    """
    for entry in getattr(app, "routes", ()):
        # Montaje perezoso: expandir el router incluido a sus rutas efectivas.
        candidates = getattr(entry, "effective_candidates", None)
        if callable(candidates):
            for context in candidates():
                original = getattr(context, "original_route", None)
                if original is None or not hasattr(original, "endpoint"):
                    continue
                yield _as_resolved(getattr(context, "path", ""), original)
            continue

        # Montaje clásico: la propia entrada ya es la ruta final.
        if hasattr(entry, "endpoint") and hasattr(entry, "path"):
            yield _as_resolved(entry.path, entry)


def api_route_paths(app: Any) -> set[str]:
    """Conjunto de rutas completas de la aplicación."""
    return {route.path for route in iter_api_routes(app)}
