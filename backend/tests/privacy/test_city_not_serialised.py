"""T041 (feature 044, US4) — ``city`` no se cuela fuera de la revisión de
identidad.

``IdentityRecordRead`` (``app/schemas/race_identity.py``) es, por diseño
(``contracts/identity-review-api.md`` §Endpoints), el ÚNICO schema de toda la
plataforma que serializa la ciudad de un tercero. Ningún otro schema Pydantic
— ni ningún ``response_model`` montado en la app — puede declarar un campo
``city`` / ``city_text`` / ``city_norm``: la ciudad es el dato con el que
``homonym_suspect`` desambigua a dos personas del mismo nombre, y solo el
coach/admin revisando esa cola debe verla.

Dos barridos independientes, ambos estáticos (sin DB, sin cliente HTTP):

1. Recorre ``app.schemas`` completo (``pkgutil.walk_packages``, mismo patrón
   que ``tests/privacy/test_third_party_lock.py``) e inspecciona
   ``model_fields`` de toda subclase pública de ``pydantic.BaseModel``.
2. Recorre cada ruta montada en ``app.main.app`` y revisa el
   ``response_model`` declarado (cuando lo hay), recursivamente sobre los
   modelos anidados — la defensa de "ningún endpoint expone esto", no solo
   "ningún schema lo declara".

Ambos barridos EXCLUYEN explícitamente ``app.schemas.race_identity`` (barrido
1) y las rutas de ``/api/race-identity/*`` (barrido 2) — es justamente donde
``city`` debe seguir viviendo.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil

from pydantic import BaseModel

import app.schemas as schemas_pkg
from app.main import app

FORBIDDEN_FIELD_NAMES = {"city", "city_text", "city_norm"}

#: Único módulo autorizado a declarar estos campos.
ALLOWED_SCHEMA_MODULE = "app.schemas.race_identity"

#: Único prefijo de ruta autorizado a exponerlos en su respuesta.
ALLOWED_ROUTE_PREFIX = "/api/race-identity/"

#: Excepciones pre-existentes, revisadas y documentadas — ninguna es la
#: "ciudad de un competidor" que el contrato protege (``city_norm``/
#: ``city_text`` de ``RaceCompetitor``, usada para desambiguar homónimos).
#: Un campo nuevo NO entra aquí sin una razón igual de concreta; el barrido
#: sigue siendo estricto para cualquier otra clase.
KNOWN_LEGITIMATE_CITY_FIELDS: dict[str, str] = {
    "app.schemas.calendar.EventDataCompetition": (
        "`city` es la sede de la carrera en un evento de calendario "
        "(event_type=competition) — ubicación del evento, no la ciudad de "
        "un competidor."
    ),
    "app.schemas.race_imports.ParsedResultsRowRead": (
        "Espejo de una fila del acta que el coach acaba de subir — misma "
        "base de exposición que `MatchPreview.competitor_name` (docstring "
        "propio del schema): no expone nada que el coach no haya visto ya "
        "en el PDF/CSV."
    ),
    "app.schemas.race_imports.ResultsRowIn": (
        "Cuerpo de corrección de esa misma fila "
        "(`POST /{parse_id}/corrections`) — mismo origen y misma excepción "
        "que `ParsedResultsRowRead`."
    ),
}


# ---------------------------------------------------------------------------
# Barrido 1 — todo módulo de app.schemas
# ---------------------------------------------------------------------------


def _iter_schema_modules() -> list[str]:
    names = [
        name
        for _finder, name, _ispkg in pkgutil.walk_packages(
            schemas_pkg.__path__, prefix=f"{schemas_pkg.__name__}."
        )
    ]
    assert len(names) >= 20, "el barrido no encontró los módulos esperados de app.schemas"
    return names


def _iter_basemodel_classes(module) -> list[type[BaseModel]]:
    out = []
    for _name, obj in inspect.getmembers(module, inspect.isclass):
        if not issubclass(obj, BaseModel) or obj is BaseModel:
            continue
        # Solo clases DEFINIDAS en este módulo — evita contar dos veces un
        # reexport (p. ej. un schema importado por otro módulo para componer
        # una respuesta más grande).
        if obj.__module__ != module.__name__:
            continue
        out.append(obj)
    return out


def test_scan_finds_schema_modules_including_race_identity() -> None:
    """Autoprueba del barrido: el propio módulo que SÍ debe llevar ``city``
    aparece, así que su exclusión de abajo es deliberada, no un hueco."""
    names = _iter_schema_modules()
    assert ALLOWED_SCHEMA_MODULE in names


def test_no_schema_outside_race_identity_declares_city_fields() -> None:
    offenders: list[str] = []
    for modname in _iter_schema_modules():
        if modname == ALLOWED_SCHEMA_MODULE:
            continue
        module = importlib.import_module(modname)
        for cls in _iter_basemodel_classes(module):
            qualname = f"{modname}.{cls.__name__}"
            allowed = KNOWN_LEGITIMATE_CITY_FIELDS.get(qualname)
            hit = FORBIDDEN_FIELD_NAMES & set(cls.model_fields.keys())
            if allowed is not None:
                # La excepción solo cubre `city` — `city_text`/`city_norm`
                # (la representación interna de la revisión de identidad)
                # nunca están justificados fuera de race_identity.py.
                hit -= {"city"}
            if hit:
                offenders.append(f"{qualname}: {sorted(hit)}")
    assert not offenders, (
        "Campo(s) de ciudad fuera de app/schemas/race_identity.py:\n"
        + "\n".join(offenders)
    )


def test_known_legitimate_exceptions_still_exist_and_are_still_narrow() -> None:
    """Autoprueba del allowlist: cada entrada sigue siendo una clase real que
    declara exactamente `city` (no `city_text`/`city_norm`) — si alguna deja
    de existir o gana un campo prohibido nuevo, este test lo marca en vez de
    que la excepción quede huérfana o se ensanche en silencio."""
    for qualname in KNOWN_LEGITIMATE_CITY_FIELDS:
        modname, clsname = qualname.rsplit(".", 1)
        module = importlib.import_module(modname)
        cls = getattr(module, clsname)
        assert issubclass(cls, BaseModel)
        assert FORBIDDEN_FIELD_NAMES & set(cls.model_fields.keys()) == {"city"}


def test_race_identity_module_itself_still_declares_city() -> None:
    """Si esto deja de ser cierto, el contrato cambió y el resto de este
    archivo ya no prueba lo que dice probar."""
    module = importlib.import_module(ALLOWED_SCHEMA_MODULE)
    hit_somewhere = any(
        FORBIDDEN_FIELD_NAMES & set(cls.model_fields.keys())
        for cls in _iter_basemodel_classes(module)
    )
    assert hit_somewhere


# ---------------------------------------------------------------------------
# Barrido 2 — response_model de cada ruta montada
# ---------------------------------------------------------------------------


def _iter_route_response_models() -> list[tuple[str, type[BaseModel]]]:
    """``[(path, response_model), ...]`` para cada ``APIRoute`` con un
    ``response_model`` que sea (o contenga) un ``BaseModel``."""
    out: list[tuple[str, type[BaseModel]]] = []
    for route in app.routes:
        response_model = getattr(route, "response_model", None)
        path = getattr(route, "path", "")
        if response_model is None:
            continue
        for cls in _flatten_models(response_model):
            out.append((path, cls))
    return out


def _flatten_models(annotation, *, _seen: set | None = None) -> list[type[BaseModel]]:
    """Modelos ``BaseModel`` alcanzables desde ``annotation`` — entra en
    ``list[...]``/``Optional[...]``/uniones y en los campos anidados de cada
    modelo encontrado."""
    import typing

    if _seen is None:
        _seen = set()
    found: list[type[BaseModel]] = []
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation in _seen:
            return found
        _seen.add(annotation)
        found.append(annotation)
        for field in annotation.model_fields.values():
            found.extend(_flatten_models(field.annotation, _seen=_seen))
        return found
    origin = typing.get_origin(annotation)
    if origin is not None:
        for arg in typing.get_args(annotation):
            found.extend(_flatten_models(arg, _seen=_seen))
    return found


def test_no_mounted_route_outside_race_identity_responds_with_city_fields() -> None:
    offenders: list[str] = []
    for path, cls in _iter_route_response_models():
        if path.startswith(ALLOWED_ROUTE_PREFIX):
            continue
        qualname = f"{cls.__module__}.{cls.__name__}"
        hit = FORBIDDEN_FIELD_NAMES & set(cls.model_fields.keys())
        if qualname in KNOWN_LEGITIMATE_CITY_FIELDS:
            hit -= {"city"}
        if hit:
            offenders.append(f"{path} -> {qualname}: {sorted(hit)}")
    assert not offenders, (
        "Ruta fuera de /api/race-identity/* respondiendo con campo(s) de "
        "ciudad:\n" + "\n".join(offenders)
    )


def test_race_identity_routes_are_actually_mounted_and_reachable_by_the_scan() -> None:
    """Autoprueba: si el router de identidad dejara de montarse, el barrido
    de arriba pasaría en falso (cero rutas que revisar). Fija que existe al
    menos una ruta bajo el prefijo excluido con un ``response_model`` que sí
    lleva ``city``."""
    matches = [
        (path, cls)
        for path, cls in _iter_route_response_models()
        if path.startswith(ALLOWED_ROUTE_PREFIX)
        and FORBIDDEN_FIELD_NAMES & set(cls.model_fields.keys())
    ]
    assert matches, "ninguna ruta /api/race-identity/* expone city — ¿router montado?"
