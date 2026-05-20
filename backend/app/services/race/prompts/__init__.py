"""Loader/renderer de prompts Jinja2 versionados (Fase 3 race-results v2).

Los prompts viven como ``.md`` en este directorio (1 archivo por agente +
versión). Decisiones:

- **Versión en el nombre de archivo** (``race_analyst_v1.md``): el bump de
  versión obliga a crear un archivo nuevo → diff visible en code review,
  rollback es ``git revert``.
- **Jinja2 con ``StrictUndefined``** sólo si ``strict=True`` (default
  ``False``): los tests cargan prompts con dicts vacíos para validar
  sintaxis sin fallar por variables faltantes. En runtime, los agentes
  pasan ``strict=True``.
- **Sin auto-escape**: estos prompts NO se renderizan en HTML — escapar
  rompería citas con HTML accidental.

API pública:

    >>> from app.services.race.prompts import render_prompt
    >>> txt = render_prompt("race_analyst_v1", {"athlete_pseudonym": "X", ...})
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import (
    ChainableUndefined,
    Environment,
    FileSystemLoader,
    StrictUndefined,
    select_autoescape,
)

PROMPTS_DIR = Path(__file__).parent

__all__ = ["PROMPTS_DIR", "load_prompt_source", "render_prompt"]


def _build_env(strict: bool) -> Environment:
    """Construye un Environment Jinja2 con/ sin variables estrictas."""
    return Environment(
        loader=FileSystemLoader(str(PROMPTS_DIR)),
        autoescape=select_autoescape(disabled_extensions=("md",), default=False),
        keep_trailing_newline=True,
        undefined=StrictUndefined if strict else ChainableUndefined,
    )


@lru_cache(maxsize=8)
def _env_cached(strict: bool) -> Environment:
    return _build_env(strict)


def load_prompt_source(name: str) -> str:
    """Carga el contenido bruto del prompt ``name`` (sin renderizar).

    Útil para tests de sintaxis o introspección. ``name`` se busca como
    ``{name}.md`` en :data:`PROMPTS_DIR`.

    Raises:
        FileNotFoundError: si el archivo no existe.
    """
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' no encontrado en {PROMPTS_DIR}")
    return path.read_text(encoding="utf-8")


def render_prompt(name: str, context: dict[str, Any], strict: bool = False) -> str:
    """Renderiza el prompt ``name`` con ``context``.

    Args:
        name: nombre base del prompt (sin ``.md``). Ej.: ``race_analyst_v1``.
        context: variables Jinja2 a inyectar.
        strict: si ``True``, variables faltantes lanzan ``UndefinedError``.
            En tests cargamos con ``strict=False`` para validar sintaxis
            con dicts incompletos.

    Returns:
        Prompt renderizado como string.
    """
    env = _env_cached(strict)
    template = env.get_template(f"{name}.md")
    return template.render(**context)
