"""Loader/renderer de prompts Jinja2 del pipeline de antropometría (feature 042).

Los prompts viven como ``.md`` en este mismo directorio (``anthropometry_analyst_v1.md``,
``anthropometry_critic_v1.md``, T031/T032), uno por rol + versión. Espejo deliberado del
loader del stack de carreras (``app/services/race/prompts/__init__.py``): misma
configuración de ``Environment``, mismo nombre de archivo ``{name}.md``, mismo
``keep_trailing_newline`` y ``autoescape`` deshabilitado (estos prompts no se
renderizan como HTML).

Única diferencia intencional frente al loader de carreras: aquí **no** existe un
modo no estricto. El loader de carreras acepta ``strict=False`` para que sus tests
de sintaxis rendericen con dicts incompletos; este loader siempre usa
``StrictUndefined`` — una variable faltante es un error de programación (un campo
que ``context.py`` (T028) olvidó pasar), nunca una cadena vacía silenciosa que
podría filtrarse a un prompt y, de ahí, a un texto que lee un coach o una familia.
Los tests de sintaxis de este stack deben pasar un contexto completo, no uno vacío.

API pública:

    >>> from app.services.ai.anthro.prompts.loader import render_prompt
    >>> texto = render_prompt("anthropometry_analyst_v1", {"audience": "family", ...})
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

PROMPTS_DIR = Path(__file__).parent

__all__ = ["PROMPTS_DIR", "load_prompt_source", "render_prompt"]


@lru_cache(maxsize=1)
def _env() -> Environment:
    """Construye (una sola vez) el ``Environment`` Jinja2 con variables estrictas."""

    return Environment(
        loader=FileSystemLoader(str(PROMPTS_DIR)),
        autoescape=select_autoescape(disabled_extensions=("md",), default=False),
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )


def load_prompt_source(name: str) -> str:
    """Carga el contenido bruto del prompt ``name`` (sin renderizar).

    ``name`` se busca como ``{name}.md`` dentro de :data:`PROMPTS_DIR`.

    Raises:
        FileNotFoundError: si el archivo no existe.
    """

    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' no encontrado en {PROMPTS_DIR}")
    return path.read_text(encoding="utf-8")


def render_prompt(name: str, context: dict[str, Any]) -> str:
    """Renderiza el prompt ``name`` con ``context``.

    Args:
        name: nombre base del prompt (sin ``.md``). Ej.: ``anthropometry_analyst_v1``.
        context: variables Jinja2 a inyectar. Debe ser completo: cualquier
            variable referenciada en la plantilla que falte aquí levanta
            ``jinja2.UndefinedError`` (``StrictUndefined``), nunca se
            sustituye por una cadena vacía.

    Returns:
        Prompt renderizado como string.

    Raises:
        FileNotFoundError: si el prompt no existe.
        jinja2.UndefinedError: si falta una variable que la plantilla usa.
    """

    template = _env().get_template(f"{name}.md")
    return template.render(**context)
