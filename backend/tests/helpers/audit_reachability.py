"""¿El handler de una ruta llega de verdad a ``record_audit``?

Feature 041, brecha A2 de `checklists/integration-review.md`. La mitad
dinámica de FR-009 (`contracts/audit-recording.md` §9 T4.4) exige que "toda
ruta auditada que la suite ejercita escribió al menos una fila". Esa versión
dinámica necesita levantar la aplicación contra una base real y sintetizar una
petición válida por ruta; hoy no hay MySQL en el entorno de las corridas y el
contrato mismo la limita a las entradas "que declaren un factory", de las que
todavía no hay ninguna.

Este módulo implementa la red que sí se puede sostener sin base de datos: un
recorrido **estático** del grafo de llamadas del handler, buscando si alguna
función alcanzable desde él invoca ``record_audit``. No reemplaza al humo
dinámico —no prueba que la fila se escriba en tiempo de ejecución, ni con qué
contenido— pero sí atrapa el modo de falla que hoy no vigila nadie: una ruta
declarada ``Audited`` en el registro cuyo handler no toca la auditoría por
ningún camino.

Alcance y límites, dichos de frente:

- El grafo se resuelve por **nombre**, no por tipo. Dos funciones distintas con
  el mismo nombre se confunden a propósito: preferimos un falso negativo
  (dejar pasar una ruta) antes que un falso positivo que obligue a marcar
  excepciones a mano.
- La profundidad está acotada (`_MAX_DEPTH`): un handler que necesite más de
  cuatro saltos para llegar a la auditoría es, de por sí, algo que conviene
  mirar.
- Solo se indexa el paquete ``app``; una llamada a una dependencia externa
  corta la rama.
"""
from __future__ import annotations

import ast
import functools
import pathlib
from collections.abc import Callable, Iterator

#: Nombre de la única puerta de escritura de la auditoría
#: (`contracts/audit-recording.md` §1).
_AUDIT_ENTRY_POINT = "record_audit"

#: Saltos máximos desde el handler. Seis cubren la cadena más larga que hoy
#: existe en el repo: `send_newsletter` → `dispatch_newsletters` →
#: `_send_for_parent` → `_send_v2_email` → `_dispatch_email` → `record_audit`
#: (`app/services/notification/newsletter_dispatcher.py`), que son cinco.
_MAX_DEPTH = 6


def _app_package_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2] / "app"


def _iter_function_nodes(
    tree: ast.AST,
) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _called_names(node: ast.AST) -> set[str]:
    """Nombres invocados dentro de ``node``, sin distinguir módulo.

    De ``servicio.hacer_algo(...)`` se queda con ``hacer_algo``; de
    ``hacer_algo(...)``, con ``hacer_algo``. También recoge los nombres usados
    como valor (``partial(hacer_algo)``, un decorador, un callback), porque el
    repo pasa funciones por parámetro en varios sitios.
    """
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
        elif isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
    return names


@functools.lru_cache(maxsize=1)
def _index() -> tuple[dict[str, tuple[frozenset[str], ...]], frozenset[str]]:
    """Indexa el paquete ``app``.

    Devuelve ``(por_nombre, auditoras)``:

    - ``por_nombre`` mapea el nombre de una función a la tupla de conjuntos de
      nombres que invoca (una entrada por cada definición homónima).
    - ``auditoras`` es el conjunto de nombres de funciones que invocan
      ``record_audit`` directamente.
    """
    por_nombre: dict[str, list[frozenset[str]]] = {}
    auditoras: set[str] = set()

    for path in sorted(_app_package_root().rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - defensivo
            continue
        for func in _iter_function_nodes(tree):
            llamadas = _called_names(func)
            por_nombre.setdefault(func.name, []).append(frozenset(llamadas))
            if _AUDIT_ENTRY_POINT in llamadas:
                auditoras.add(func.name)

    return (
        {nombre: tuple(cuerpos) for nombre, cuerpos in por_nombre.items()},
        frozenset(auditoras),
    )


def reaches_record_audit(endpoint: Callable[..., object]) -> bool:
    """¿Alguna función alcanzable desde ``endpoint`` llama a ``record_audit``?

    Recorre en anchura el grafo de llamadas resuelto por nombre, hasta
    ``_MAX_DEPTH`` saltos.
    """
    por_nombre, auditoras = _index()

    nombre = getattr(endpoint, "__name__", None)
    if nombre is None:  # pragma: no cover - defensivo
        return False
    if nombre == _AUDIT_ENTRY_POINT or nombre in auditoras:
        return True

    vistos = {nombre}
    frontera = {nombre}
    for _ in range(_MAX_DEPTH):
        siguiente: set[str] = set()
        for actual in frontera:
            for llamadas in por_nombre.get(actual, ()):
                if _AUDIT_ENTRY_POINT in llamadas:
                    return True
                siguiente |= llamadas - vistos
        if not siguiente:
            return False
        vistos |= siguiente
        frontera = siguiente
    return False
