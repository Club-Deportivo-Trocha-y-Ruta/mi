"""T151 (feature 044, US5, amendment 2026-09-26) — la web app nunca sube un
archivo de resultados de carrera; solo revisa y comitea lo que el CLI/skill
ya dejó staged. ``contracts/staged-import.md`` § Structural guards.

Tres barridos estructurales, sin DB ni credenciales reales:

1. **Allow-list de archivos.** Se recorre el OpenAPI generado por
   ``app.main.app`` (más fiable que inspeccionar ``app.routes`` a mano — la
   representación interna de rutas de FastAPI puede cambiar de versión a
   versión, pero un endpoint con ``UploadFile``/``File(...)`` siempre se
   anuncia con ``requestBody.content["multipart/form-data"]`` en el schema).
   El conjunto de ``(method, path)`` así detectado debe ser EXACTAMENTE el de
   ``ALLOWED_UPLOAD_ENDPOINTS`` — ni uno más, ni uno menos. Si alguien vuelve
   a agregar un ``File(...)`` a un router de resultados, este test lo marca
   antes de que llegue a producción.
2. **Ruta denegada.** ``POST /api/race-analysis/imports/parse`` (el viejo
   endpoint de upload, retirado en T152) ya no existe — un POST multipart a
   esa ruta debe devolver 404 o 405 para admin, coach, parent y athlete
   (override de ``get_current_user``, sin necesidad de DB: el ruteo de
   FastAPI resuelve el 404 antes de evaluar cualquier dependencia de auth).
3. **Motor no importado por ningún router.** ``app.services.race
   .results_skill`` (el lector de PDF offline usado por el CLI/skill,
   feature 044 Amendment) no puede aparecer entre los imports de ningún
   módulo bajo ``app.routers`` — si un router alguna vez lo importa, se
   habilita sin querer un camino de upload por HTTP.
"""
from __future__ import annotations

import ast
import pkgutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

import app.routers as routers_pkg
from app.dependencies import get_current_user
from app.main import app
from app.models.user import UserRole

#: Los únicos cuatro endpoints de toda la plataforma autorizados a declarar
#: un parámetro ``UploadFile``/``File(...)`` (contracts/staged-import.md §
#: Structural guards). Un quinto entrante es una decisión que este test
#: obliga a tomar explícitamente, no un silencio.
ALLOWED_UPLOAD_ENDPOINTS: set[tuple[str, str]] = {
    ("POST", "/api/training-sessions/{session_id}/route-file"),
    ("POST", "/api/training-sessions/{session_id}/media"),
    ("POST", "/api/race-analysis/race-events/{race_event_id}/course/variants"),
    ("PUT", "/api/race-analysis/race-events/{race_event_id}/course/variants/{variant_id}/file"),
}

_RETIRED_PARSE_PATH = "/api/race-analysis/imports/parse"


def _multipart_upload_endpoints() -> set[tuple[str, str]]:
    """Recorre el OpenAPI generado y devuelve ``(METHOD, path)`` para cada
    operación cuyo ``requestBody`` declara ``multipart/form-data`` — la
    señal que FastAPI emite para cualquier parámetro ``UploadFile``/
    ``File(...)``, sin importar cómo esté armada la ruta internamente."""
    schema = app.openapi()
    found: set[tuple[str, str]] = set()
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            if method.upper() not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                continue
            request_body = operation.get("requestBody") or {}
            if "multipart/form-data" in request_body.get("content", {}):
                found.add((method.upper(), path))
    return found


def test_upload_allow_list_has_exactly_four_entries() -> None:
    """El único upload de resultados de carrera permitido es el de
    circuito (course profile, feature 043) — nunca uno de actas/resultados."""
    actual = _multipart_upload_endpoints()
    assert actual == ALLOWED_UPLOAD_ENDPOINTS, (
        f"La superficie de upload cambió sin actualizar este test.\n"
        f"Nuevos: {actual - ALLOWED_UPLOAD_ENDPOINTS}\n"
        f"Faltantes: {ALLOWED_UPLOAD_ENDPOINTS - actual}"
    )
    assert (
        "POST",
        _RETIRED_PARSE_PATH,
    ) not in actual, "POST /imports/parse debe estar retirado (T152)."


def _fake_user(role: UserRole) -> SimpleNamespace:
    return SimpleNamespace(
        id=999,
        first_name="Test",
        last_name="User",
        email=f"{role.value}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role", [UserRole.admin, UserRole.coach, UserRole.parent, UserRole.athlete]
)
async def test_post_to_retired_parse_endpoint_is_404_or_405(role: UserRole) -> None:
    """``POST /imports/parse`` ya no existe: el ruteo de FastAPI responde
    404 (o 405 si algún otro método sigue registrado en ese path) antes de
    evaluar ninguna dependencia de auth — así que esto no necesita DB."""
    app.dependency_overrides[get_current_user] = lambda: _fake_user(role)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            files = {"resultados_pdf": ("resultados.pdf", b"%PDF-1.4 fake", "application/pdf")}
            response = await client.post(_RETIRED_PARSE_PATH, files=files)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code in (404, 405), (
        f"role={role.value} obtuvo {response.status_code}, esperado 404/405: {response.text}"
    )


def _iter_router_module_files() -> list[Path]:
    """Todos los módulos ``.py`` de primer nivel bajo ``app.routers``.

    ``app.routers`` es un namespace package (sin ``__init__.py``), así que
    ``__file__`` es ``None`` — cada ``ModuleInfo.module_finder`` sí trae su
    propio ``path`` (uno por directorio en ``__path__``)."""
    files: list[Path] = []
    for module_info in pkgutil.iter_modules(routers_pkg.__path__):
        files.append(Path(module_info.module_finder.path) / f"{module_info.name}.py")
    return files


def test_no_router_imports_results_skill() -> None:
    """``app.services.race.results_skill`` es el motor de lectura offline del
    CLI/skill (Amendment 2026-09-26) — si algún router lo importara, un
    endpoint HTTP podría convertirse en un camino de upload sin que nadie lo
    haya decidido explícitamente. Se revisa el AST fuente (no
    ``sys.modules``, que puede tener el módulo cargado por otra razón —
    p.ej. un test en el mismo proceso) de cada router de primer nivel."""
    offenders: list[str] = []
    for module_path in _iter_router_module_files():
        if not module_path.is_file():
            continue
        tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [module] + [f"{module}.{alias.name}" for alias in node.names]
            else:
                continue
            if any("results_skill" in name for name in names):
                offenders.append(f"{module_path.name}: {names}")

    assert offenders == [], (
        "Ningún router puede importar app.services.race.results_skill "
        f"(motor offline del CLI/skill, nunca un camino HTTP): {offenders}"
    )
