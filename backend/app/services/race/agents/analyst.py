"""``RaceAnalystAgent`` — produce el análisis cualitativo de carreras.

Flujo:

1. Renderiza ``race_analyst_v1.md`` con :class:`AnalysisInput`.
2. Invoca Gemini 2.5 Flash Lite.
3. Parsea el markdown de salida en secciones, recomendaciones y riesgos.
4. Captura ``RunMetrics`` (tokens, latency, cost).
5. Devuelve ``(AnalysisOutput, RunMetrics)``.

Decisiones de diseño:
- **Output markdown, no JSON tools.** Más natural para Gemini y el coach
  ya ve markdown nativo en la UI (workflow §"Decisiones cerradas").
- **Parseo defensivo.** Heurísticas regex sobre headings ``##`` + bullets
  con sufijos paréntesis ``(categoría=X, prioridad=Y)``. Si una sección
  falta, el campo queda como string vacío en ``sections`` pero
  ``raw_markdown`` se preserva entero → el coach siempre tiene la
  versión "como vino del modelo".
- **Citations extraídas** del texto vía regex ``\\[(\\d+)\\]`` cruzado
  contra ``input.principles_citations``: el modelo cita por número, el
  agente resuelve a ``chunk_id`` real (lo que persiste auditoría).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from app.services.race.agents._llm import LLMCallResult, build_chat_llm, call_llm
from app.services.race.agents.pricing import PROMPT_VERSION_ANALYST
from app.services.race.prompts import render_prompt
from app.services.race.rag.tools import format_citations
from app.services.race.schemas import (
    AnalysisInput,
    AnalysisOutput,
    Priority,
    Recommendation,
    RecommendationCategory,
    RiskFlag,
    RiskFlagType,
    RunMetrics,
    Severity,
)

logger = logging.getLogger(__name__)

# Headings esperados → key en AnalysisOutput.sections
_SECTION_KEYS: dict[str, str] = {
    "evolución": "evolution",
    "evolucion": "evolution",
    "análisis técnico": "technical",
    "analisis tecnico": "technical",
    "recomendaciones ltad": "recommendations",
    "recomendaciones": "recommendations",
    "riesgos": "risks",
    "próximos pasos": "next_steps",
    "proximos pasos": "next_steps",
}

# Regex: bullet con sufijo "(categoría=X, prioridad=Y)" — case-insensitive.
_REC_BULLET_RE = re.compile(
    r"^[-*]\s+(?P<text>.+?)\s*\(\s*categor[ií]a\s*=\s*(?P<cat>[a-z_]+)\s*,\s*"
    r"prioridad\s*=\s*(?P<prio>low|med|high)\s*\)\s*(?P<cites>(?:\[\d+\]\s*)*)$",
    re.IGNORECASE,
)

# Regex: bullet con sufijo "(flag=X, severity=Y)".
_RISK_BULLET_RE = re.compile(
    r"^[-*]\s+(?P<text>.+?)\s*\(\s*flag\s*=\s*(?P<flag>[a-z_]+)\s*,\s*"
    r"severity\s*=\s*(?P<sev>low|med|high)\s*\)\s*(?P<cites>(?:\[\d+\]\s*)*)$",
    re.IGNORECASE,
)

# Regex: cualquier [n] citado en el texto.
_CITE_RE = re.compile(r"\[(\d+)\]")


def _split_sections(markdown: str) -> dict[str, str]:
    """Divide el markdown por headings ``## Heading`` → dict.

    Devuelve dict ``{key: section_body}`` donde ``key`` está en
    :data:`_SECTION_KEYS`. Contenido antes del primer heading se ignora.
    Headings no reconocidos se ignoran (defensa: el modelo a veces
    inventa "## Resumen Ejecutivo").
    """
    sections: dict[str, str] = {}
    current_key: Optional[str] = None
    buf: list[str] = []

    for line in markdown.splitlines():
        m = re.match(r"^##\s+(?P<title>.+?)\s*$", line)
        if m:
            # Cerrar sección previa.
            if current_key is not None:
                sections[current_key] = "\n".join(buf).strip()
            title = m.group("title").lower().strip()
            current_key = _SECTION_KEYS.get(title)
            buf = []
        else:
            if current_key is not None:
                buf.append(line)

    if current_key is not None:
        sections[current_key] = "\n".join(buf).strip()

    return sections


def _parse_recommendations(section_text: str) -> list[Recommendation]:
    """Extrae bullets con sufijo (categoría=X, prioridad=Y)."""
    out: list[Recommendation] = []
    if not section_text:
        return out
    valid_cats = {c.value for c in RecommendationCategory}
    valid_prios = {p.value for p in Priority}
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        m = _REC_BULLET_RE.match(line)
        if not m:
            continue
        cat = m.group("cat").lower()
        prio = m.group("prio").lower()
        if cat not in valid_cats or prio not in valid_prios:
            logger.debug("Recomendación con cat/prio inválida descartada: %s", line)
            continue
        text = m.group("text").strip()
        # Enforce schema bounds defensively.
        text = text[:500]
        out.append(
            Recommendation(
                text=text,
                category=RecommendationCategory(cat),
                priority=Priority(prio),
            )
        )
    return out


def _parse_risks(section_text: str) -> list[RiskFlag]:
    """Extrae bullets con sufijo (flag=X, severity=Y)."""
    out: list[RiskFlag] = []
    if not section_text:
        return out
    valid_flags = {f.value for f in RiskFlagType}
    valid_sevs = {s.value for s in Severity}
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        m = _RISK_BULLET_RE.match(line)
        if not m:
            continue
        flag = m.group("flag").lower()
        sev = m.group("sev").lower()
        if flag not in valid_flags or sev not in valid_sevs:
            logger.debug("Riesgo con flag/sev inválido descartado: %s", line)
            continue
        evidence = m.group("text").strip()[:500]
        out.append(
            RiskFlag(
                flag=RiskFlagType(flag),
                severity=Severity(sev),
                evidence=evidence,
            )
        )
    return out


def _extract_citations(markdown: str, principles_chunk_ids: list[str]) -> list[str]:
    """Mapea ``[n]`` en el texto a ``chunk_id`` reales.

    ``principles_chunk_ids`` viene en orden (1-indexed). Si el modelo
    cita ``[5]`` pero solo hay 3 chunks → ignoramos la cita (el critic
    la marcará).
    """
    used: list[str] = []
    seen: set[str] = set()
    for match in _CITE_RE.finditer(markdown):
        idx = int(match.group(1))
        if 1 <= idx <= len(principles_chunk_ids):
            cid = principles_chunk_ids[idx - 1]
            if cid not in seen:
                seen.add(cid)
                used.append(cid)
    return used


def _word_count(text: str) -> int:
    """Conteo aproximado de palabras (compatibilidad ES/EN)."""
    return len([w for w in re.split(r"\s+", text.strip()) if w])


def _build_prompt_context(input_: AnalysisInput) -> dict[str, Any]:
    """Mapea ``AnalysisInput`` → variables Jinja2 del prompt."""
    progression_md = _progression_to_md(input_.progression_df_records)
    podium_md = _podium_to_md(input_.podium_context)
    principles_block = format_citations(input_.principles_citations)

    return {
        "athlete_pseudonym": input_.athlete_pseudonym,
        "age": input_.age,
        "ltad_group": input_.ltad_group.value,
        "progression_table": progression_md,
        "podium_context": podium_md,
        "memory_recent_insights": input_.memory_recent_insights,
        "principles": principles_block,
        "explain_mode": input_.explain_mode,
    }


def _progression_to_md(records: list[dict[str, Any]]) -> str:
    """Convierte records de progresión a tabla markdown corta."""
    if not records:
        return "_(sin resultados previos en esta temporada)_"
    headers = ["valida_num", "event_date", "position", "race_time_ms", "points_awarded"]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for r in records:
        row = [str(r.get(h, "")) for h in headers]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _podium_to_md(podium: dict[str, Any]) -> str:
    """Bloque markdown corto con el podio."""
    if not podium or not podium.get("podium"):
        return "_(sin datos de podio para el evento foco)_"
    finishers = podium.get("finishers_count", 0)
    out = [f"**Finalizaron:** {finishers}", "", "| Posición | competitor_id | race_time_ms |", "| --- | --- | --- |"]
    for row in podium["podium"]:
        out.append(
            f"| {row['position']} | {row['competitor_id']} | {row.get('race_time_ms', '—')} |"
        )
    return "\n".join(out)


class RaceAnalystAgent:
    """Agente analyst (sin estado interno — todas las invocaciones son puras).

    Uso típico::

        agent = RaceAnalystAgent()                # usa Settings.ai_*
        out, metrics = await agent.invoke(input_)

    Para tests, inyecta el LLM (``llm=FakeLLM(...)``).
    """

    def __init__(self, llm: Any | None = None) -> None:
        """Inicializa el agente.

        Args:
            llm: instancia de un LangChain chat model con método
                ``ainvoke``. Si ``None``, se construye lazy en
                :meth:`invoke` con :func:`build_chat_llm` — esto
                permite importar el agente sin ``AI_API_KEY``.
        """
        self._llm = llm
        self._prompt_version = PROMPT_VERSION_ANALYST

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    async def invoke(self, input_: AnalysisInput) -> tuple[AnalysisOutput, RunMetrics]:
        """Genera análisis para un atleta.

        Returns:
            Tupla ``(AnalysisOutput, RunMetrics)`` lista para persistir
            en ``athlete_ai_insights``.
        """
        llm = self._llm or build_chat_llm()
        context = _build_prompt_context(input_)
        prompt = render_prompt("race_analyst_v1", context, strict=False)

        call: LLMCallResult = await call_llm(llm, prompt)

        principles_ids = [c.chunk_id for c in input_.principles_citations]
        sections = _split_sections(call.text)
        recs = _parse_recommendations(sections.get("recommendations", ""))
        risks = _parse_risks(sections.get("risks", ""))
        cites = _extract_citations(call.text, principles_ids)

        output = AnalysisOutput(
            pseudonym=input_.athlete_pseudonym,
            sections=sections,
            citations_used=cites,
            recommendations=recs,
            risk_flags=risks,
            raw_markdown=call.text if call.text else "_(modelo no devolvió contenido)_",
            word_count=_word_count(call.text),
        )

        metrics = RunMetrics(
            tokens_in=call.tokens_in,
            tokens_out=call.tokens_out,
            latency_ms=call.latency_ms,
            cost_usd=call.cost_usd,
            prompt_version=self._prompt_version,
        )

        return output, metrics
