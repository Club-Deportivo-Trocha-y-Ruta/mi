"""``RaceAnalystAgent`` — produce el análisis cualitativo de carreras.

Flujo v1 (por defecto):

1. Renderiza ``race_analyst_v1.md`` con :class:`AnalysisInput`.
2. Invoca Gemini 2.5 Flash Lite.
3. Parsea el markdown de salida en secciones, recomendaciones y riesgos.
4. Captura ``RunMetrics`` (tokens, latency, cost).
5. Devuelve ``(AnalysisOutput, RunMetrics)``.

Flujo v2 (``prompt_version="race_analyst_v2"``):

- :meth:`invoke_per_valida`: recibe una lista de ``(valida_num, AnalysisInput)``
  y lanza las llamadas con ``asyncio.gather`` bajo cap de 4 válidas.
  Cada tarea tiene ``asyncio.wait_for`` individual con el timeout de
  ``Settings.ai_timeout_seconds``. Fallos individuales producen el
  fallback determinista para esa válida (sin romper las demás).
  Aplica guardrails v2 con ``forbidden_names`` tras cada generación.
  Retry 1 vez si veto duro rechaza; si segunda falla → fallback + log.
- :meth:`invoke_season_summary`: un único call v2 con datos aggregados
  de toda la temporada. Sección 4 "Resumen temporada" ≤200 palabras.

Decisiones:
- v1 ``invoke`` se mantiene intacto → cero impacto en tests/use_cases existentes.
- Heurística de prompt_version: si el agente se construye con
  ``prompt_version="race_analyst_v2"``, usa la lógica nueva; de lo contrario
  delega a la lógica v1 (retrocompat total).
"""

from __future__ import annotations

import asyncio
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

# Versión v2 del prompt.
PROMPT_VERSION_ANALYST_V2 = "race_analyst_v2"

# Cap máximo de válidas por llamada v2 (spec: 4 → max 12 LLM calls + 1 summary).
_V2_CAP = 4

# Headings esperados → key en AnalysisOutput.sections (v1)
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


# Headings v2 → key en AnalysisOutput.sections
_SECTION_KEYS_V2: dict[str, str] = {
    "qué pasó en esta válida": "what_happened",
    "que paso en esta valida": "what_happened",
    "recorrido hasta acá": "journey_so_far",
    "recorrido hasta aca": "journey_so_far",
    "hacia dónde va": "next_steps",
    "hacia donde va": "next_steps",
    # Sección 4 del resumen de temporada (solo en invoke_season_summary)
    "resumen temporada": "season_summary",
    "resumen de temporada": "season_summary",
}


def _split_sections_v2(markdown: str) -> dict[str, str]:
    """Divide markdown v2 por headings ``## ...`` → dict.

    Usa ``_SECTION_KEYS_V2``. Igual lógica defensiva que ``_split_sections``.
    """
    import unicodedata

    sections: dict[str, str] = {}
    current_key: Optional[str] = None
    buf: list[str] = []

    def _norm(s: str) -> str:
        return "".join(
            c for c in unicodedata.normalize("NFD", s.lower().strip())
            if unicodedata.category(c) != "Mn"
        )

    for line in markdown.splitlines():
        m = re.match(r"^##\s+(?P<title>.+?)\s*$", line)
        if m:
            if current_key is not None:
                sections[current_key] = "\n".join(buf).strip()
            title_norm = _norm(m.group("title"))
            current_key = next(
                (v for k, v in _SECTION_KEYS_V2.items() if _norm(k) == title_norm),
                None,
            )
            buf = []
        else:
            if current_key is not None:
                buf.append(line)

    if current_key is not None:
        sections[current_key] = "\n".join(buf).strip()

    return sections


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

        agent = RaceAnalystAgent()                         # v1 por defecto
        out, metrics = await agent.invoke(input_)

        agent_v2 = RaceAnalystAgent(prompt_version="race_analyst_v2")
        results = await agent_v2.invoke_per_valida(pairs, forbidden_names=[...])

    Para tests, inyecta el LLM (``llm=FakeLLM(...)``).

    La heurística de ``prompt_version`` determina qué lógica de parseo y
    qué guardrails se usan. El método :meth:`invoke` (v1) es siempre
    seguro de llamar independientemente del prompt_version configurado.
    """

    def __init__(
        self,
        llm: Any | None = None,
        *,
        prompt_version: str = PROMPT_VERSION_ANALYST,
    ) -> None:
        """Inicializa el agente.

        Args:
            llm: instancia de un LangChain chat model con método
                ``ainvoke``. Si ``None``, se construye lazy — esto
                permite importar el agente sin ``AI_API_KEY``.
            prompt_version: versión del prompt a usar. Default
                ``"race_analyst_v1"`` (compat). Pasar
                ``"race_analyst_v2"`` activa flujo por-válida.
        """
        self._llm = llm
        self._prompt_version = prompt_version

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

    # -----------------------------------------------------------------------
    # v2: análisis por válida + resumen de temporada
    # -----------------------------------------------------------------------

    async def _invoke_single_v2(
        self,
        valida_num: int,
        input_: AnalysisInput,
        forbidden_names: list[str],
        timeout_seconds: float,
        is_first_in_season: bool = False,
        season_progression: list[dict] | None = None,
        athlete_age: int | None = None,
    ) -> tuple[int, AnalysisOutput, RunMetrics]:
        """Invoca el análisis v2 para una sola válida con retry + guardrails.

        Retry 1 vez si veto duro rechaza. Si segunda falla → fallback
        determinista + log warning (spec §Cap implementación).

        Args:
            is_first_in_season: True si el atleta tiene 1 sola válida en toda
                la temporada (no solo en el set lanzado). Activa bloque N=1
                en el prompt y veto duro N=1 en los guardrails.
            season_progression: Records compactos de toda la temporada para
                la sección "Recorrido hasta acá". Solo se usa si
                ``not is_first_in_season``.
            athlete_age: Edad real del atleta en años enteros. Se propaga al
                guardrail ``age_mismatch`` que rechaza el output si el LLM
                menciona una edad incorrecta.
        """
        from app.services.ai.guardrails import Guardrails, check_v2_veto_duro
        from app.services.race.ai.fallback import deterministic_fallback

        llm = self._llm or build_chat_llm()
        principles_ids = [c.chunk_id for c in input_.principles_citations]
        context = self._build_v2_context(
            input_,
            valida_num=valida_num,
            is_first_in_season=is_first_in_season,
            season_progression=season_progression,
        )

        async def _one_attempt() -> tuple[AnalysisOutput, RunMetrics]:
            prompt = render_prompt("race_analyst_v2", context, strict=False)
            call: LLMCallResult = await asyncio.wait_for(
                call_llm(llm, prompt),
                timeout=timeout_seconds,
            )
            guardrails = Guardrails(
                use_case="race_analyst_v2",
                forbidden_names=forbidden_names,
                is_first_in_season=is_first_in_season,
                athlete_age=athlete_age,
            )
            report = guardrails.scrub_with_report(call.text)
            vetos = check_v2_veto_duro(report.text)
            if vetos:
                raise _VetoDuroError(f"veto_duro: {vetos}")

            scrubbed_text = report.text
            sections = _split_sections_v2(scrubbed_text)
            recs = _parse_recommendations(sections.get("next_steps", ""))
            cites = _extract_citations(scrubbed_text, principles_ids)

            out = AnalysisOutput(
                pseudonym=input_.athlete_pseudonym,
                sections=sections,
                citations_used=cites,
                recommendations=recs,
                risk_flags=[],
                raw_markdown=scrubbed_text or "_(modelo no devolvió contenido)_",
                word_count=_word_count(scrubbed_text),
            )
            met = RunMetrics(
                tokens_in=call.tokens_in,
                tokens_out=call.tokens_out,
                latency_ms=call.latency_ms,
                cost_usd=call.cost_usd,
                prompt_version=PROMPT_VERSION_ANALYST_V2,
            )
            return out, met

        # Intento 1.
        try:
            output, metrics = await _one_attempt()
            return valida_num, output, metrics
        except _VetoDuroError:
            logger.warning(
                "analyst_v2: veto duro en válida %d — reintentando (1/1)", valida_num
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "analyst_v2: fallo en válida %d — activando fallback",
                valida_num,
                exc_info=True,
            )
            return valida_num, deterministic_fallback(input_.athlete_pseudonym), RunMetrics(
                tokens_in=0, tokens_out=0, latency_ms=0,
                cost_usd=0.0, prompt_version=PROMPT_VERSION_ANALYST_V2,
            )

        # Intento 2 (retry tras veto duro).
        try:
            output, metrics = await _one_attempt()
            return valida_num, output, metrics
        except Exception:  # noqa: BLE001
            logger.warning(
                "analyst_v2: segundo fallo en válida %d — activando fallback",
                valida_num,
                exc_info=True,
            )
            return valida_num, deterministic_fallback(input_.athlete_pseudonym), RunMetrics(
                tokens_in=0, tokens_out=0, latency_ms=0,
                cost_usd=0.0, prompt_version=PROMPT_VERSION_ANALYST_V2,
            )

    async def invoke_per_valida(
        self,
        pairs: list[tuple[int, AnalysisInput]],
        *,
        forbidden_names: list[str] | None = None,
        timeout_seconds: float | None = None,
        is_first_in_season: bool = False,
        full_season_records: list[dict] | None = None,
        athlete_age: int | None = None,
    ) -> dict[int, tuple[AnalysisOutput, RunMetrics]]:
        """Analiza varias válidas en paralelo (asyncio.gather, cap=4).

        Args:
            pairs: lista de ``(valida_num, AnalysisInput)``. Máx 4 elementos.
            forbidden_names: nombres reales a prohibir en guardrails v2.
            timeout_seconds: timeout por llamada. Default: ``Settings.ai_timeout_seconds``.
            is_first_in_season: True si el atleta tiene 1 sola válida válida
                en toda la temporada (no solo en el set lanzado). Activa la
                regla N=1 en el prompt y los guardrails de cada válida.
            full_season_records: Records compactos de TODA la temporada para
                la sección "Recorrido hasta acá". Solo se usa cuando
                ``not is_first_in_season``.
            athlete_age: Edad real del atleta en años enteros. Se propaga al
                guardrail ``age_mismatch`` de cada llamada individual.

        Returns:
            Dict ``{valida_num: (AnalysisOutput, RunMetrics)}``.

        Raises:
            ValueError: si ``len(pairs) > 4`` (cap v2 hard).
        """
        from app.config import settings

        if len(pairs) > _V2_CAP:
            raise ValueError(
                f"Cap v2: máximo {_V2_CAP} válidas por análisis. "
                "Genera resumen temporada para visión global."
            )
        timeout = timeout_seconds or float(settings.ai_timeout_seconds)
        _forbidden = forbidden_names or []
        _season_prog = full_season_records if not is_first_in_season else None

        tasks = [
            self._invoke_single_v2(
                vn,
                inp,
                _forbidden,
                timeout,
                is_first_in_season=is_first_in_season,
                season_progression=_season_prog,
                athlete_age=athlete_age,
            )
            for vn, inp in pairs
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        from app.services.race.ai.fallback import deterministic_fallback
        out: dict[int, tuple[AnalysisOutput, RunMetrics]] = {}
        for i, res in enumerate(raw_results):
            vn = pairs[i][0]
            pseudonym = pairs[i][1].athlete_pseudonym
            if isinstance(res, Exception):
                logger.error(
                    "analyst_v2: gather exception para válida %d: %s",
                    vn, type(res).__name__,
                )
                out[vn] = (
                    deterministic_fallback(pseudonym),
                    RunMetrics(
                        tokens_in=0, tokens_out=0, latency_ms=0,
                        cost_usd=0.0, prompt_version=PROMPT_VERSION_ANALYST_V2,
                    ),
                )
            else:
                _, analysis_out, run_metrics = res  # type: ignore[misc]
                out[vn] = (analysis_out, run_metrics)
        return out

    async def invoke_season_summary(
        self,
        input_: AnalysisInput,
        *,
        forbidden_names: list[str] | None = None,
        timeout_seconds: float | None = None,
    ) -> tuple[AnalysisOutput, RunMetrics]:
        """Genera el resumen de temporada (sección 4) en v2.

        Usa contexto agregado de toda la temporada. La sección
        "Resumen temporada" tiene límite de 200 palabras (guardrail post-gen).

        Args:
            input_: AnalysisInput con ``progression_df_records`` de toda
                la temporada.
            forbidden_names: nombres reales a prohibir en guardrails.
            timeout_seconds: timeout para la llamada.

        Returns:
            Tupla ``(AnalysisOutput, RunMetrics)``.
        """
        from app.config import settings
        from app.services.ai.guardrails import Guardrails
        from app.services.race.ai.fallback import deterministic_fallback

        timeout = timeout_seconds or float(settings.ai_timeout_seconds)
        _forbidden = forbidden_names or []
        llm = self._llm or build_chat_llm()
        principles_ids = [c.chunk_id for c in input_.principles_citations]

        context = self._build_v2_context(input_, valida_num=0, is_season_summary=True)
        prompt = render_prompt("race_analyst_v2", context, strict=False)

        try:
            call: LLMCallResult = await asyncio.wait_for(
                call_llm(llm, prompt),
                timeout=timeout,
            )
        except Exception:  # noqa: BLE001
            logger.error("analyst_v2: invoke_season_summary falló", exc_info=True)
            return deterministic_fallback(input_.athlete_pseudonym), RunMetrics(
                tokens_in=0, tokens_out=0, latency_ms=0,
                cost_usd=0.0, prompt_version=PROMPT_VERSION_ANALYST_V2,
            )

        guardrails = Guardrails(
            use_case="race_analyst_v2",
            forbidden_names=_forbidden,
        )
        scrubbed = guardrails.scrub_with_report(call.text).text
        sections = _split_sections_v2(scrubbed)
        recs = _parse_recommendations(sections.get("next_steps", ""))
        cites = _extract_citations(scrubbed, principles_ids)

        output = AnalysisOutput(
            pseudonym=input_.athlete_pseudonym,
            sections=sections,
            citations_used=cites,
            recommendations=recs,
            risk_flags=[],
            raw_markdown=scrubbed or "_(modelo no devolvió contenido)_",
            word_count=_word_count(scrubbed),
        )
        metrics = RunMetrics(
            tokens_in=call.tokens_in,
            tokens_out=call.tokens_out,
            latency_ms=call.latency_ms,
            cost_usd=call.cost_usd,
            prompt_version=PROMPT_VERSION_ANALYST_V2,
        )
        return output, metrics

    def _build_v2_context(
        self,
        input_: AnalysisInput,
        *,
        valida_num: int,
        is_season_summary: bool = False,
        is_first_in_season: bool = False,
        season_progression: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Construye el contexto Jinja2 para el prompt v2.

        ``forbidden_names`` NO se inyecta en el prompt — solo va a guardrails
        post-generación para no filtrar información sensible al LLM.

        Args:
            is_first_in_season: True si el atleta tiene 1 sola válida en toda
                la temporada. Activa el bloque N=1 del prompt
                (``{% if is_first_in_season %}``).
            season_progression: Records compactos [{valida_num, position,
                race_time_ms, gap_to_winner_ms}] de TODA la temporada.
                Solo se pasa cuando ``not is_first_in_season`` y hay ≥2
                entradas. Disponible en el prompt para sección "Recorrido".
        """
        progression_md = _progression_to_md(input_.progression_df_records)
        podium_md = _podium_to_md(input_.podium_context)
        principles_block = format_citations(input_.principles_citations)

        # Compactar season_progression para el prompt (solo campos relevantes).
        compact_season: list[dict[str, Any]] = []
        if season_progression and not is_first_in_season:
            for r in season_progression:
                compact_season.append({
                    "valida_num": r.get("valida_num"),
                    "position": r.get("position"),
                    "race_time_ms": r.get("race_time_ms"),
                    "gap_to_winner_ms": r.get("gap_to_winner_ms"),
                    "gap_pct": r.get("gap_pct"),
                })

        return {
            "athlete_pseudonym": input_.athlete_pseudonym,
            "age": input_.age,
            "ltad_group": input_.ltad_group.value,
            "valida_num": valida_num,
            "is_first_in_season": is_first_in_season,
            "season_progression": compact_season,
            "maturation_status": input_.podium_context.get("maturation_status", "Pre-PHV"),
            "progression_table": progression_md,
            "podium_context": podium_md,
            "race_meta": input_.podium_context.get("race_meta", ""),
            "memory_recent_insights": input_.memory_recent_insights,
            "principles": principles_block,
            "explain_mode": input_.explain_mode,
            "is_season_summary": is_season_summary,
        }


class _VetoDuroError(Exception):
    """Señal interna: el output del LLM contiene una frase de veto duro."""
