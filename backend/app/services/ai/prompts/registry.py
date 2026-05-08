"""PromptRegistry — versionado, validación y render de plantillas Jinja2.

Mismo patrón que `app.services.notification.template_registry.TemplateRegistry`.
El system prompt único vive en `system_principles.md`, fuente única de verdad
para los principios no negociables. Cada use case tiene una plantilla
`<nombre>.j2` con sus `required_keys`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    select_autoescape,
)

logger = logging.getLogger(__name__)

_PROMPTS_ROOT = Path(__file__).parent
_SYSTEM_PROMPT_FILE = _PROMPTS_ROOT / "system_principles.md"


@dataclass(frozen=True)
class PromptSpec:
    """Especificación de una plantilla de prompt."""

    template_id: str
    template_path: str           # relativo a `prompts/`
    required_keys: frozenset[str] = field(default_factory=frozenset)
    version: int = 1
    description: str = ""


PROMPT_SPECS: dict[str, PromptSpec] = {
    "phv_explainer": PromptSpec(
        template_id="phv_explainer",
        template_path="phv_explainer.j2",
        required_keys=frozenset(
            {
                "age_group",
                "age_decimal",
                "sex",
                "category",
                "maturation_status",
                "phv_offset",
                "age_at_phv",
            }
        ),
        version=1,
        description="Explicación del resultado PHV para padres.",
    ),
    "monthly_report": PromptSpec(
        template_id="monthly_report",
        template_path="monthly_report.j2",
        required_keys=frozenset(
            {
                "club_name",
                "period_year",
                "period_month",
                "total_sessions_planned",
                "total_sessions_executed",
                "total_sessions_cancelled",
                "attendance_stats",
                "focos_técnicos",
                "avg_rpe",
                "avg_rubric_effort",
                "avg_rubric_attitude",
                "avg_rubric_technique",
                "coach_observations",
            }
        ),
        version=1,
        description="Resumen mensual agregado del club para el comité.",
    ),
}


class PromptRegistry:
    """Renderiza plantillas Jinja2 y carga el system prompt común."""

    def __init__(self, prompts_root: Path | None = None) -> None:
        self._root = prompts_root or _PROMPTS_ROOT
        self._env = Environment(
            loader=FileSystemLoader(str(self._root)),
            undefined=StrictUndefined,
            autoescape=select_autoescape(default_for_string=False),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._specs = PROMPT_SPECS

    # ------------------------------------------------------------------
    # System prompt (cargado una sola vez por proceso)
    # ------------------------------------------------------------------

    @lru_cache(maxsize=1)
    def system_prompt(self) -> str:
        path = self._root / "system_principles.md"
        return path.read_text(encoding="utf-8").strip()

    # ------------------------------------------------------------------
    # Specs
    # ------------------------------------------------------------------

    def get_spec(self, template_id: str) -> PromptSpec:
        try:
            return self._specs[template_id]
        except KeyError:
            registered = sorted(self._specs)
            raise ValueError(
                f"Prompt '{template_id}' no registrado. Disponibles: {registered}"
            ) from None

    def validate_context(self, template_id: str, context: dict) -> None:
        spec = self.get_spec(template_id)
        missing = spec.required_keys - context.keys()
        if missing:
            raise ValueError(
                f"Contexto incompleto para prompt '{template_id}'. "
                f"Claves faltantes: {sorted(missing)}"
            )

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def render(self, template_id: str, context: dict) -> str:
        spec = self.get_spec(template_id)
        self.validate_context(template_id, context)
        template = self._env.get_template(spec.template_path)
        return template.render(**context).strip()
