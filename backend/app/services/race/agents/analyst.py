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
import json
import logging
import re
import time
from dataclasses import dataclass, field as dc_field
from typing import Any, Callable, NamedTuple, Optional

from app.services.race.agents._llm import (
    LLMCallResult,
    build_chat_llm,
    call_llm,
    extract_text,
    extract_usage,
    resolve_configured_model,
)
from app.services.race.agents.pricing import (
    PROMPT_VERSION_ANALYST,
    compute_cost_usd,
)
from app.services.race.insight_v3 import (
    PRINCIPLE_LABELS,
    InsightV3,
    extract_numeric_tokens,
)
from app.services.race.prompts import render_prompt
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

# Regex: bullet con sufijo "(categoría=X, prioridad=Y[, horizonte=..][, catálogo=..])".
# Feature 037 (T101, spec §problem 6): el modelo a veces cierra el bullet con
# un punto o punto-y-coma final (tras el paréntesis o tras las citas) y la
# regex original exigía fin de línea inmediato → todo bullet así se
# descartaba silenciosamente ⇒ ``recommendations_json = []`` en producción.
# También tolera los campos opcionales "horizonte=…" y "catálogo=…" dentro
# del paréntesis (no capturados por separado — solo ablandan el match; el
# parseo estructurado de esos campos es tarea de T201/insight_v3).
_REC_BULLET_RE = re.compile(
    r"^[-*]\s+(?P<text>.+?)\s*\(\s*categor[ií]a\s*=\s*(?P<cat>[a-z_]+)\s*,\s*"
    r"prioridad\s*=\s*(?P<prio>low|med|high)\s*"
    r"(?:,\s*horizonte\s*=\s*[^,()]+?)?"
    r"(?:,\s*cat[aá]logo\s*=\s*[^,()]+?)?"
    r"\s*\)\s*(?P<cites>(?:\[\d+\]\s*)*)[.;]?\s*$",
    re.IGNORECASE,
)

# Regex: bullet con sufijo "(flag=X, severity=Y)".
_RISK_BULLET_RE = re.compile(
    r"^[-*]\s+(?P<text>.+?)\s*\(\s*flag\s*=\s*(?P<flag>[a-z_]+)\s*,\s*"
    r"severity\s*=\s*(?P<sev>low|med|high)\s*\)\s*(?P<cites>(?:\[\d+\]\s*)*)$",
    re.IGNORECASE,
)


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


def _word_count(text: str) -> int:
    """Conteo aproximado de palabras (compatibilidad ES/EN)."""
    return len([w for w in re.split(r"\s+", text.strip()) if w])


def _build_prompt_context(input_: AnalysisInput) -> dict[str, Any]:
    """Mapea ``AnalysisInput`` → variables Jinja2 del prompt."""
    progression_md = _progression_to_md(input_.progression_df_records)
    podium_md = _podium_to_md(input_.podium_context)

    return {
        "athlete_pseudonym": input_.athlete_pseudonym,
        "age": input_.age,
        "ltad_group": input_.ltad_group.value,
        "progression_table": progression_md,
        "podium_context": podium_md,
        "memory_recent_insights": input_.memory_recent_insights,
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


def _format_ms_hhmmss(ms: Any) -> str:
    """Convierte milisegundos a ``hh:mm:ss`` (o ``—`` si vacío/no numérico).

    Preserva el signo en vez de dejar que ``divmod`` trunque hacia
    -infinito: un total negativo se separa en signo + magnitud absoluta
    ANTES de descomponer en horas/min/seg, para no producir una hora
    corrida (p. ej. ``-30_000`` ms → ``-0:00:30``, no ``-1:59:30``). El
    único caller real que pasa valores negativos es ``delta_time_ms`` de
    ``season_comparative`` (T014) cuando el atleta mejora su tiempo entre
    válidas — ``race_time_ms``/``gap_to_winner_ms`` nunca lo son.
    """
    if ms is None or ms == "" or str(ms) == "<NA>":
        return "—"
    try:
        total_sec = int(round(int(ms) / 1000))
    except (TypeError, ValueError):
        return "—"
    sign = "-" if total_sec < 0 else ""
    h, rem = divmod(abs(total_sec), 3600)
    m, s = divmod(rem, 60)
    return f"{sign}{h:d}:{m:02d}:{s:02d}"


def _progression_series_label(record: dict[str, Any]) -> str:
    """Etiqueta de serie de una fila de progresión (feature 039, T034).

    Mismos textos que :func:`series_label_v3` — ``"Válida N · Copa"``,
    ``"Cto. Departamental"``, ``"Cto. Nacional"`` — pero derivados de
    ``series_kind``/``series_level`` de la fila en vez de ``FieldMetrics``.

    Sin esta columna el modelo ve un ``valida_num`` ambiguo: desde spec 014
    un campeonato lleva ``sequence_number=1`` igual que la Válida I, así que
    la tabla "Recorrido hasta acá" mostraba dos filas "1" indistinguibles e
    invitaba a compararlas puesto a puesto. Las filas previas a la feature
    039 no traen ``series_kind`` y caen a copa, que es lo que eran.
    """
    kind = getattr(record.get("series_kind"), "value", record.get("series_kind"))
    if str(kind or "cup").lower() == "championship":
        level = getattr(record.get("series_level"), "value", record.get("series_level"))
        return "Cto. Nacional" if str(level or "").lower() == "national" else "Cto. Departamental"
    valida_num = record.get("valida_num")
    return f"Válida {valida_num} · Copa" if valida_num is not None else "Copa"


def _row_kind(record: dict[str, Any]) -> str:
    """Normaliza ``series_kind`` de una fila de temporada → ``"cup"``/``"championship"``.

    Cae a ``"cup"`` cuando la clave falta o es desconocida: filas previas a
    la feature 039 (o ``field_metrics`` sin ``series_id``) siguen siendo
    tratadas como copa, igual que :func:`_progression_series_label` y
    :func:`series_label_v3`.
    """
    kind = getattr(record.get("series_kind"), "value", record.get("series_kind"))
    return "championship" if str(kind or "cup").lower() == "championship" else "cup"


def _split_rows_by_kind(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separa filas de temporada en ``(copa, campeonato)`` por ``series_kind``."""
    cup_rows: list[dict[str, Any]] = []
    championship_rows: list[dict[str, Any]] = []
    for r in rows:
        (championship_rows if _row_kind(r) == "championship" else cup_rows).append(r)
    return cup_rows, championship_rows


def _group_cup_rows_by_series(
    cup_rows: list[dict[str, Any]],
) -> list[tuple[str | None, list[dict[str, Any]]]]:
    """Agrupa filas de copa por ``series_id`` cuando el dato está disponible.

    ``field_metrics`` (consumido por ``_v3_season_block``) no trae
    ``series_id`` — en ese caso devuelve un único grupo sin rótulo, igual
    que el comportamiento previo a la feature 039. Las filas de
    ``athlete_progression`` (consumidas por ``_progression_to_md``) sí lo
    traen, así que ahí sí se abre una sub-tabla por copa.
    """
    if not any(r.get("series_id") is not None for r in cup_rows):
        return [(None, cup_rows)]
    order: list[Any] = []
    groups: dict[Any, list[dict[str, Any]]] = {}
    for r in cup_rows:
        key = r.get("series_id")
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)
    return [(groups[key][0].get("series_name") or "Copa", groups[key]) for key in order]


_SEASON_SPLIT_HEADING_CUPS = "**Válidas de copa**"
_SEASON_SPLIT_HEADING_CHAMPIONSHIPS = (
    "**Campeonatos (pelotón propio, no comparable con la copa)**"
)


def _render_split_tables(
    rows: list[dict[str, Any]],
    render_table: Callable[[list[dict[str, Any]]], str],
    *,
    group_cups: bool,
) -> str:
    """Arma el markdown de temporada, separando copa vs. campeonato (F-4).

    Con ambos tipos presentes: dos tablas rotuladas — nunca una sola donde
    el modelo pueda leer puestos consecutivos de series distintas como
    comparables (regla 10 del prompt v3). Con un solo tipo presente,
    mantiene el formato de una única tabla sin encabezado (compatibilidad
    con los casos golden y fixtures previos a esta separación).
    """
    cup_rows, championship_rows = _split_rows_by_kind(rows)

    def _cup_block() -> str:
        if not group_cups:
            return render_table(cup_rows)
        groups = _group_cup_rows_by_series(cup_rows)
        if len(groups) == 1 and groups[0][0] is None:
            return render_table(cup_rows)
        return "\n\n".join(f"*{name}*\n\n{render_table(g_rows)}" for name, g_rows in groups)

    if cup_rows and championship_rows:
        return "\n\n".join(
            [
                _SEASON_SPLIT_HEADING_CUPS,
                _cup_block(),
                _SEASON_SPLIT_HEADING_CHAMPIONSHIPS,
                render_table(championship_rows),
            ]
        )
    if cup_rows:
        return _cup_block()
    return render_table(championship_rows)


def _render_progression_table(records: list[dict[str, Any]]) -> str:
    """Tabla markdown corta de records de progresión (una sola serie/kind)."""
    headers = [
        "valida_num",
        "serie",
        "event_date",
        "position",
        "race_time",
        "points_awarded",
    ]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for r in records:
        race_time_fmt = _format_ms_hhmmss(r.get("race_time_ms"))
        # DNF/DNS/DSQ dejan position=None (clave presente, valor vacío) —
        # dict.get(key, default) NO aplica el default en ese caso, así que
        # sin esta guarda se imprime el literal "None" en la tabla que el
        # LLM recibe como contexto.
        position = r.get("position")
        position_fmt = str(position) if position is not None else "—"
        row = [
            str(r.get("valida_num", "")),
            _progression_series_label(r),
            str(r.get("event_date", "")),
            position_fmt,
            race_time_fmt,
            str(r.get("points_awarded", "")),
        ]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _progression_to_md(records: list[dict[str, Any]]) -> str:
    """Convierte records de progresión a tabla(s) markdown corta(s).

    Feature 039 (F-4): cuando la temporada mezcla válidas de copa y
    campeonatos, separa en dos tablas rotuladas (agrupando las copas por
    ``series_id`` cuando el dato está presente — una sub-tabla por copa
    con su nombre). Con un solo tipo de fila mantiene la tabla única de
    siempre.
    """
    if not records:
        return "_(sin resultados previos en esta temporada)_"
    return _render_split_tables(records, _render_progression_table, group_cups=True)


# Etiquetas de display para SurfaceCondition (valores enum en minúscula).
_SURFACE_LABELS: dict[str, str] = {
    "seca": "Seca",
    "humeda": "Húmeda",
    "barro": "Barro",
    "lluvia": "Lluvia",
    "mixta": "Mixta",
}


def format_race_meta(conditions: dict[str, Any] | None) -> str | None:
    """Formatea las condiciones registradas de una válida → bloque markdown.

    Feature 011: la fuente de verdad son las condiciones realmente registradas
    en ``race_events``. Reglas:

    - Devuelve ``None`` cuando NO hay ningún campo registrado (todos None/vacío).
      La ausencia se propaga como ``None`` — NUNCA un string vacío — para que el
      prompt active el veto anti-fabricación (no inventar clima/pista).
    - Solo lista los campos efectivamente registrados (no rellena con "—").
    """
    if not conditions:
        return None

    climate = conditions.get("climate")
    temperature_c = conditions.get("temperature_c")
    surface = conditions.get("surface_condition")
    altitude = conditions.get("altitude_msnm")
    notes = conditions.get("weather_notes")

    lines: list[str] = []
    if climate and str(climate).strip():
        lines.append(f"- Clima: {str(climate).strip()}")
    if temperature_c is not None:
        temp_str = f"{float(temperature_c):.1f}".rstrip("0").rstrip(".")
        lines.append(f"- Temperatura: {temp_str} °C")
    if surface and str(surface).strip():
        label = _SURFACE_LABELS.get(str(surface).lower(), str(surface))
        lines.append(f"- Superficie de la pista: {label}")
    if altitude is not None:
        lines.append(f"- Altitud: {altitude} msnm")
    if notes and str(notes).strip():
        lines.append(f"- Notas: {str(notes).strip()}")

    if not lines:
        return None
    return "\n".join(lines)


def _podium_to_md(podium: dict[str, Any]) -> str:
    """Bloque markdown corto con el podio."""
    if not podium or not podium.get("podium"):
        return "_(sin datos de podio para el evento foco)_"
    finishers = podium.get("finishers_count", 0)
    out = [f"**Finalizaron:** {finishers}", "", "| Posición | competitor_id | race_time |", "| --- | --- | --- |"]
    for row in podium["podium"]:
        out.append(
            f"| {row['position']} | {row['competitor_id']} | {_format_ms_hhmmss(row.get('race_time_ms'))} |"
        )
    return "\n".join(out)


# ---------------------------------------------------------------------------
# v3: análisis estructurado (feature 037, T201)
# ---------------------------------------------------------------------------

# Versiones v3 del prompt (una por tipo de análisis).
PROMPT_VERSION_ANALYST_V3 = "race_analyst_v3"
PROMPT_VERSION_SEASON_SUMMARY_V3 = "race_season_summary_v3"

# Cap de llamadas simultáneas al proveedor. El free tier de Gemini ronda 15
# RPM y un run puede lanzar 4 válidas × (analyst + critic): con 2 en vuelo el
# 429 deja de ser el caso común (plan.md §Risks & mitigations).
_V3_CONCURRENCY = 2

# El analista v3 devuelve JSON con 2-4 observaciones y 2-3 acciones: 1024
# tokens (default histórico) trunca el objeto a mitad y rompe el parseo.
_V3_MAX_OUTPUT_TOKENS = 4096

# Topes de tokens del bloque de catálogo — el club puede tener decenas de
# bloques/plantillas y el prompt no necesita el inventario completo.
_V3_CATALOG_CAP = 8

# Cuánto texto del intento fallido se le devuelve al modelo en el reintento
# de reparación (suficiente para que vea su propio error sin duplicar costo).
_V3_REPAIR_EXCERPT_CHARS = 1500


class V3CallResult(NamedTuple):
    """Resultado de una llamada v3.

    ``grounding_numbers`` son los tokens numéricos del **prompt renderizado**
    (no del output): el precheck determinista del critic (T202) los usa como
    verdad de referencia para detectar cifras inventadas.
    """

    insight: InsightV3
    metrics: RunMetrics
    grounding_numbers: list[str]


@dataclass(frozen=True)
class AnalystV3Input:
    """Input de :meth:`RaceAnalystAgent.invoke_v3` para UNA válida (o temporada).

    Todos los campos llegan ya anonimizados/derivados desde el grafo. No
    incluye pseudónimo: el prompt v3 se refiere al sujeto solo con
    ``athlete_ref``, así que el modelo no tiene ningún identificador que
    pueda re-emitir.
    """

    valida_num: int
    analysis_kind: str = "valida"  # "valida" | "season"
    athlete_ref: str = "la deportista"
    age: int | None = None
    ltad_group: str = "bambino"
    season: int | None = None
    validas_count: int = 0
    valida_label: str | None = None
    race_row: dict[str, Any] | None = None
    field_metrics: dict[str, Any] | None = None
    season_rows: list[dict[str, Any]] = dc_field(default_factory=list)
    race_meta: str | None = None
    anthro_context: dict[str, Any] | None = None
    training_window: dict[str, Any] | None = None
    coach_dialogue: list[dict[str, Any]] = dc_field(default_factory=list)
    catalog_context: dict[str, Any] = dc_field(default_factory=dict)
    memory_recent_insights: list[str] = dc_field(default_factory=list)


class _InsightV3Error(Exception):
    """El modelo no produjo un ``InsightV3`` válido tras el reintento."""


def _fmt_number(value: Any, suffix: str = "") -> str:
    """Formatea un número para los bloques del prompt (``—`` si no hay dato).

    Usa ``%g`` para no imprimir decimales espurios: el grounding compara
    tokens literales, así que ``58.3`` debe verse igual en el prompt y en la
    evidencia que el modelo copie.
    """
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "sí" if value else "no"
    if isinstance(value, (int,)):
        return f"{value}{suffix}"
    try:
        return f"{float(value):g}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def series_label_v3(field_metrics: dict[str, Any] | None) -> str:
    """Etiqueta de serie legible a partir de ``FieldMetrics``.

    Campeonatos se rotulan como tales (AC-2.3: nunca se comparan puesto a
    puesto contra válidas de copa).
    """
    if not field_metrics:
        return ""
    if field_metrics.get("is_championship"):
        level = str(field_metrics.get("series_level") or "").lower()
        return "Cto. Nacional" if level == "national" else "Cto. Departamental"
    valida_num = field_metrics.get("valida_num")
    return f"Válida {valida_num} · Copa" if valida_num else "Copa"


def _v3_race_block(row: dict[str, Any] | None) -> str | None:
    """Fila de la carrera analizada → bullets markdown (``None`` si no hay)."""
    if not row:
        return None
    lines = [
        f"- Fecha: {row.get('event_date') or '—'}",
        f"- Categoría: {row.get('category_code') or '—'}",
        f"- Posición: {_fmt_number(row.get('position'))}",
        f"- Tiempo: {_format_ms_hhmmss(row.get('race_time_ms'))}",
        f"- Gap al líder: {_format_ms_hhmmss(row.get('gap_to_winner_ms'))}"
        f" ({_fmt_number(row.get('gap_to_winner_pct'), '%')})",
    ]
    return "\n".join(lines)


def _v3_field_block(field_metrics: dict[str, Any] | None) -> str | None:
    """``FieldMetrics`` → bullets markdown (``None`` si no hay métricas)."""
    if not field_metrics:
        return None
    fm = field_metrics
    lines = [
        f"- Serie: {series_label_v3(fm) or '—'}",
        f"- Tamaño del pelotón: {_fmt_number(fm.get('field_size'))}",
        f"- Percentil: {_fmt_number(fm.get('percentile'))}",
        f"- Gap al líder: {_format_ms_hhmmss(fm.get('gap_to_p1_ms'))}"
        f" ({_fmt_number(fm.get('gap_pct'), '%')})",
        f"- Gap a P3: {_format_ms_hhmmss(fm.get('gap_to_p3_ms'))}",
        f"- Gap a la mediana de categoría: {_fmt_number(fm.get('gap_to_median_pct'), '%')}",
        f"- Vueltas abajo: {_fmt_number(fm.get('laps_behind'))}",
    ]
    if fm.get("expected_position") is not None:
        lines.append(
            f"- Posición esperada: {_fmt_number(fm.get('expected_position'))} "
            f"(real {_fmt_number(fm.get('position'))}, "
            f"delta {_fmt_number(fm.get('delta_vs_expected'))})"
        )
        lines.append(f"- Fuerza del pelotón: {_fmt_number(fm.get('field_strength'))}")
    else:
        # AC-2.2: con <50 % de finishers con índice previo la expectativa no
        # se calcula. Decirlo explícitamente evita que el modelo la invente.
        lines.append(
            "- Posición esperada: no calculable (menos de la mitad del pelotón "
            "tiene historial previo en la temporada)"
        )
    return "\n".join(lines)


def _render_season_table(rows: list[dict[str, Any]]) -> str:
    """Tabla markdown de métricas de pelotón por válida (una sola serie/kind)."""
    header = (
        "| válida | fecha | serie | posición | pelotón | percentil | gap % | "
        "gap a P3 | esperada | Δ esperada |"
    )
    sep = "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    lines = [header, sep]
    for r in rows:
        lines.append(
            "| {vn} | {date} | {serie} | {pos} | {size} | {pct} | {gap} | "
            "{p3} | {exp} | {delta} |".format(
                vn=_fmt_number(r.get("valida_num")),
                date=r.get("event_date") or "—",
                serie=series_label_v3(r) or "—",
                pos=_fmt_number(r.get("position")),
                size=_fmt_number(r.get("field_size")),
                pct=_fmt_number(r.get("percentile")),
                gap=_fmt_number(r.get("gap_pct"), "%"),
                p3=_format_ms_hhmmss(r.get("gap_to_p3_ms")),
                exp=_fmt_number(r.get("expected_position")),
                delta=_fmt_number(r.get("delta_vs_expected")),
            )
        )
    return "\n".join(lines)


def _v3_season_block(rows: list[dict[str, Any]] | None) -> str | None:
    """Tabla de temporada con métricas de pelotón (``None`` si está vacía).

    Feature 039 (F-4): mismo criterio de separación que
    :func:`_progression_to_md` — copa y campeonato nunca comparten tabla
    cuando ambos aparecen en la temporada. ``field_metrics`` no trae
    ``series_id``, así que las copas nunca se sub-agrupan aquí (queda para
    cuando ese dato exista en este bloque).
    """
    if not rows:
        return None
    return _render_split_tables(rows, _render_season_table, group_cups=True)


def _v3_measurement_timing(days_before_event: Any) -> str:
    """Texto de la distancia temporal entre la medición y la carrera.

    ``days_before_event`` negativo significa que la medición más cercana es
    POSTERIOR a la carrera (feature 037: se usa como mejor aproximación de la
    fase madurativa cuando no hay registro previo, y se declara explícitamente
    para que ni el analista ni el critic lo tomen por un dato del día).
    """
    try:
        days = int(days_before_event)
    except (TypeError, ValueError):
        return "(fecha de medición desconocida)"
    if days < 0:
        return f"(medida {abs(days)} días DESPUÉS de la carrera — aproximación)"
    return f"({days} días antes de la carrera)"


def _v3_anthro_block(anthro: dict[str, Any] | None) -> str | None:
    """``AnthroContext`` → bullets markdown.

    Privacidad (AC-1.3): solo maduración y estatura. Nunca peso, IMC,
    z-scores ni estado nutricional — esas claves ni siquiera existen en el
    dict que produce ``athlete_context.load_anthro_context``.
    """
    if not anthro:
        return None
    latest = anthro.get("latest") or {}
    lines = [
        f"- Última evaluación: {latest.get('evaluation_date') or '—'} "
        f"{_v3_measurement_timing(latest.get('days_before_event'))}",
        f"- Fase madurativa: {latest.get('maturation_status') or '—'}",
        f"- Offset de maduración: {_fmt_number(latest.get('maturity_offset_years'))} años "
        f"({_fmt_number(anthro.get('months_from_phv'))} meses respecto del PHV)",
        f"- Velocidad de crecimiento: "
        f"{_fmt_number(anthro.get('growth_velocity_cm_per_year'), ' cm/año')}",
        f"- Percentil de estatura: {_fmt_number(latest.get('height_percentile'))}",
    ]
    flags = anthro.get("flags") or []
    if flags:
        lines.append(f"- Alertas: {', '.join(str(f) for f in flags)}")
    return "\n".join(lines)


def _v3_training_block(window: dict[str, Any] | None) -> str | None:
    """``TrainingWindow`` → bullets markdown (``None`` si no hay ventana)."""
    if not window:
        return None
    tw = window
    lines = [
        f"- Ventana: {tw.get('date_from') or '—'} a {tw.get('date_to') or '—'} "
        f"({_fmt_number(tw.get('window_days'))} días)",
        f"- Sesiones con registro: {_fmt_number(tw.get('sessions_in_window'))} "
        f"(asistió {_fmt_number(tw.get('attended'))}, "
        f"faltó {_fmt_number(tw.get('absent'))}, "
        f"excusas {_fmt_number(tw.get('excused'))})",
        f"- Asistencia: {_fmt_number(tw.get('attendance_pct'), '%')}",
        f"- Horas entrenadas: {_fmt_number(tw.get('training_hours'))}",
        f"- RPE medio: {_fmt_number(tw.get('rpe_mean'))} "
        f"(últimos 7 días {_fmt_number(tw.get('rpe_last7_mean'))}, "
        f"previos {_fmt_number(tw.get('rpe_prev21_mean'))})",
        f"- Rúbricas — esfuerzo {_fmt_number(tw.get('rubric_effort_mean'))}, "
        f"actitud {_fmt_number(tw.get('rubric_attitude_mean'))}, "
        f"técnica {_fmt_number(tw.get('rubric_technique_mean'))}",
        f"- Sesiones de fuerza: {_fmt_number(tw.get('strength_sessions'))} · "
        f"con intervalos: {_fmt_number(tw.get('interval_sessions'))}",
        f"- Días desde la última sesión: {_fmt_number(tw.get('days_since_last_session'))}",
    ]
    foci = tw.get("technical_foci") or []
    if foci:
        lines.append(f"- Foco técnico trabajado: {', '.join(str(f) for f in foci)}")
    skills = tw.get("skill_codes_worked") or []
    if skills:
        lines.append(f"- Skills del catálogo trabajadas: {', '.join(str(s) for s in skills)}")
    feedback = tw.get("coach_feedback") or []
    if feedback:
        lines.append("- Notas del coach en sesiones (ya anonimizadas):")
        lines.extend(f"  - {str(f)}" for f in feedback[:3])
    return "\n".join(lines)


def _v3_dialogue_block(dialogue: list[dict[str, Any]] | None) -> str | None:
    """Diálogo coach ↔ analista de insights previos (US4) → markdown."""
    if not dialogue:
        return None
    lines: list[str] = []
    for item in dialogue[:3]:
        label = item.get("valida_label") or item.get("generated_at") or "análisis previo"
        lines.append(f"- {label}")
        headline = item.get("headline")
        if headline:
            lines.append(f"  - Hallazgo: {headline}")
        question = item.get("coach_question")
        if question:
            lines.append(f"  - Pregunté: {question}")
        answer = item.get("coach_answer") or item.get("coach_answer_text")
        if answer:
            lines.append(f"  - El coach respondió: {answer}")
        rating = item.get("coach_rating")
        if rating is not None:
            lines.append(
                f"  - Valoración del coach: {'útil' if int(rating) > 0 else 'no útil'}"
            )
    return "\n".join(lines) if lines else None


def _v3_catalog_block(catalog: dict[str, Any] | None) -> str | None:
    """Catálogo del club → markdown acotado (``None`` si está vacío)."""
    if not catalog:
        return None
    templates = catalog.get("interval_templates") or []
    if not templates:
        return None

    lines: list[str] = []
    if templates:
        lines.append("")
        lines.append("**Plantillas de intervalos** (`interval_template`, usa el id):")
        for t in templates[:_V3_CATALOG_CAP]:
            phase = t.get("mesocycle_phase")
            phase_txt = f", {phase}" if phase else ""
            lines.append(
                f"- `{t.get('id')}` {t.get('name')} ({t.get('age_band') or '—'}{phase_txt})"
            )
    return "\n".join(lines)


def _strip_json_fence(text: str) -> str:
    """Quita el ```json ... ``` que algunos modelos agregan pese al prompt."""
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def parse_insight_v3(text: str) -> InsightV3:
    """Parsea el JSON de un modelo a :class:`InsightV3`.

    Tolera el code fence y texto alrededor del objeto (recorta al primer
    ``{`` y al último ``}``). Cualquier fallo se propaga como
    ``ValueError``/``ValidationError`` para que el caller dispare el
    reintento de reparación.
    """
    candidate = _strip_json_fence(text)
    if not candidate:
        raise ValueError("respuesta vacía")
    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("la respuesta no contiene un objeto JSON")
        candidate = candidate[start : end + 1]
    return InsightV3.model_validate(json.loads(candidate))


def _forbidden_name_patterns(names: list[str]) -> list[re.Pattern[str]]:
    """Regex de nombres reales prohibidos (equivalente v3 de guardrails v2).

    ``guardrails.build_race_v2_forbidden_names_rules`` reemplaza siempre por
    el literal "la deportista"; acá el reemplazo lo decide el caller
    (``athlete_ref``), por eso se construyen los patrones aparte en vez de
    reusar aquellas reglas.
    """
    patterns: list[re.Pattern[str]] = []
    for raw in names or []:
        name = (raw or "").strip()
        if len(name) < 3:
            continue
        patterns.append(re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE))
    return patterns


def scrub_insight_v3(draft: InsightV3, forbidden_names: list[str], athlete_ref: str) -> InsightV3:
    """Reemplaza nombres reales por ``athlete_ref`` en todo campo de texto.

    Defensa en profundidad: el prompt ya prohíbe nombres propios y el
    precheck del critic (T202) los detecta, pero una fila persistida con un
    nombre real de menor es una violación de la Ley 1581 que no puede
    depender de que el critic corra. Si no hay nombres que prohibir, el
    draft se devuelve tal cual (sin copia).
    """
    patterns = _forbidden_name_patterns(forbidden_names)
    if not patterns:
        return draft

    hits = 0

    def _clean(value: str) -> str:
        nonlocal hits
        out = value
        for pattern in patterns:
            out, count = pattern.subn(athlete_ref, out)
            hits += count
        return out

    data = draft.model_dump()
    data["headline"] = _clean(data["headline"])
    data["coach_question"] = _clean(data["coach_question"])
    data["watch_signals"] = [_clean(s) for s in data.get("watch_signals") or []]
    data["data_gaps"] = [_clean(s) for s in data.get("data_gaps") or []]
    for obs in data.get("observations") or []:
        obs["claim"] = _clean(obs["claim"])
        obs["evidence"] = [_clean(e) for e in obs.get("evidence") or []]
    for action in data.get("actions") or []:
        action["text"] = _clean(action["text"])
    reading = data.get("field_reading")
    if reading:
        reading["summary"] = _clean(reading.get("summary") or "")

    if hits:
        # NUNCA logueamos el nombre detectado (sería el leak que estamos
        # evitando) — solo el conteo.
        logger.warning("analyst_v3: %d nombre(s) real(es) escrubeado(s) del draft", hits)
    return InsightV3.model_validate(data)


# Heading que abre el ejemplo resuelto (few-shot) en los prompts v3. Sus cifras
# son ficticias y NO deben contar como evidencia válida para el grounding.
_V3_FEW_SHOT_HEADING = "# Ejemplo resuelto"


def grounding_source_text(prompt: str) -> str:
    """Recorta el prompt v3 a la parte que contiene datos reales.

    ``grounding_numbers`` alimenta el precheck de grounding del critic: cada
    número del draft debe existir en este texto. Si se calculara sobre el
    prompt completo, las cifras del ejemplo resuelto (few-shot) pasarían por
    evidencia legítima y un draft que las copiara no sería detectado. Se
    devuelve todo lo anterior al heading del ejemplo; si el prompt no lo
    trae, se devuelve íntegro.
    """
    idx = prompt.find(_V3_FEW_SHOT_HEADING)
    return prompt if idx < 0 else prompt[:idx]


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

        sections = _split_sections(call.text)
        recs = _parse_recommendations(sections.get("recommendations", ""))
        risks = _parse_risks(sections.get("risks", ""))

        output = AnalysisOutput(
            pseudonym=input_.athlete_pseudonym,
            sections=sections,
            citations_used=[],
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
                has_recorded_conditions=bool(context.get("race_meta")),
            )
            report = guardrails.scrub_with_report(call.text)
            vetos = check_v2_veto_duro(report.text)
            if vetos:
                raise _VetoDuroError(f"veto_duro: {vetos}")

            scrubbed_text = report.text
            sections = _split_sections_v2(scrubbed_text)
            recs = _parse_recommendations(sections.get("next_steps", ""))

            out = AnalysisOutput(
                pseudonym=input_.athlete_pseudonym,
                sections=sections,
                citations_used=[],
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

        output = AnalysisOutput(
            pseudonym=input_.athlete_pseudonym,
            sections=sections,
            citations_used=[],
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

        # Compactar season_progression para el prompt (solo campos relevantes).
        compact_season: list[dict[str, Any]] = []
        if season_progression and not is_first_in_season:
            for r in season_progression:
                compact_season.append({
                    "valida_num": r.get("valida_num"),
                    "position": r.get("position"),
                    "race_time": _format_ms_hhmmss(r.get("race_time_ms")),
                    "gap_to_winner": _format_ms_hhmmss(r.get("gap_to_winner_ms")),
                    "gap_pct": r.get("gap_pct"),
                })

        # Season context (T014): build the comparative table for the prompt.
        # Format race_time_ms values for human readability.
        season_comparative_prompt: list[dict[str, Any]] = []
        for entry in input_.season_comparative:
            season_comparative_prompt.append({
                "valida_num": entry.get("valida_num"),
                "event_label": entry.get("event_label"),
                "position": entry.get("position"),
                "race_time": _format_ms_hhmmss(entry.get("race_time_ms")),
                "field_size": entry.get("field_size"),
                "delta_position": entry.get("delta_position"),
                "delta_time": _format_ms_hhmmss(entry.get("delta_time_ms")),
            })

        return {
            "athlete_pseudonym": input_.athlete_pseudonym,
            # Feature 037 (T101): "el deportista"/"la deportista" en vez del
            # "la deportista" hardcodeado en el prompt v2 anterior.
            "athlete_ref": input_.athlete_ref,
            "age": input_.age,
            "ltad_group": input_.ltad_group.value,
            "valida_num": valida_num,
            "is_first_in_season": is_first_in_season,
            "season_progression": compact_season,
            # Feature 011: valores reales por válida desde AnalysisInput.
            # `maturation_status=None` → el prompt no afirma fase madurativa
            # (ya no se usa el default "Pre-PHV" del dead read en podium_context).
            "maturation_status": input_.maturation_status,
            "progression_table": progression_md,
            "podium_context": podium_md,
            # `race_meta=None` → el prompt omite las condiciones y activa el veto
            # anti-fabricación (ya no se lee el dead key podium_context["race_meta"]).
            "race_meta": input_.race_meta,
            "memory_recent_insights": input_.memory_recent_insights,
            "explain_mode": input_.explain_mode,
            "is_season_summary": is_season_summary,
            # Season context (T014 — feature 010):
            "season_comparative": season_comparative_prompt,
            "progression_assessment": input_.progression_assessment,
        }


    # -----------------------------------------------------------------------
    # v3: análisis estructurado (JSON) por válida / temporada
    # -----------------------------------------------------------------------

    def _build_v3_context(self, input_: AnalystV3Input) -> dict[str, Any]:
        """Construye el contexto Jinja2 de ``race_analyst_v3`` / ``…_summary_v3``.

        Ambos prompts se renderizan con ``strict=True``, así que este dict
        SIEMPRE define todas las claves: un bloque sin datos viaja como
        ``None`` (el template lo convierte en un aviso "SIN DATO" explícito)
        y nunca como clave ausente.

        ``forbidden_names`` NO se inyecta — igual que en v2, los nombres
        reales solo alimentan el scrubbing post-generación.
        """
        return {
            "athlete_ref": input_.athlete_ref,
            "age": input_.age,
            "ltad_group": input_.ltad_group,
            "season": input_.season,
            "validas_count": input_.validas_count,
            "valida_label": (
                input_.valida_label or series_label_v3(input_.field_metrics) or None
            ),
            "race_block": _v3_race_block(input_.race_row),
            "field_block": _v3_field_block(input_.field_metrics),
            "season_block": _v3_season_block(input_.season_rows),
            "conditions_block": input_.race_meta,
            "anthro_block": _v3_anthro_block(input_.anthro_context),
            "training_block": _v3_training_block(input_.training_window),
            "dialogue_block": _v3_dialogue_block(input_.coach_dialogue),
            "catalog_block": _v3_catalog_block(input_.catalog_context),
            "memory_recent_insights": list(input_.memory_recent_insights or [])[:3],
            "principle_labels": list(PRINCIPLE_LABELS),
        }

    async def _generate_v3(
        self, llm: Any, prompt: str, prompt_version: str, timeout: float
    ) -> tuple[InsightV3, RunMetrics]:
        """Obtiene un ``InsightV3`` válido del modelo (structured → texto).

        Orden de intentos:

        1. ``llm.with_structured_output(InsightV3)`` — el proveedor fuerza el
           esquema. Es el camino barato: no hay parseo que pueda fallar.
        2. JSON en texto (proveedor sin structured output, o structured que
           falló) + un **único** reintento de reparación en el que se le
           devuelve al modelo su propio output y el error de validación.

        Raises:
            _InsightV3Error: ningún intento produjo un objeto válido.
        """
        from app.config import settings

        model_id = resolve_configured_model(role="analyst")
        provider = (settings.race_ai_provider or "anthropic").lower()

        tokens_in = tokens_out = latency_ms = 0
        cost_usd = 0.0

        def _metrics() -> RunMetrics:
            return RunMetrics(
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
                cost_usd=round(cost_usd, 6),
                prompt_version=prompt_version,
            )

        structured, include_raw = _build_structured_llm(llm)
        if structured is not None:
            start = time.monotonic()
            try:
                insight, raw = await asyncio.wait_for(
                    _call_structured_v3(structured, prompt, include_raw),
                    timeout=timeout,
                )
                latency_ms += int((time.monotonic() - start) * 1000)
                text_for_usage = insight.model_dump_json()
                ti, to = extract_usage(raw, prompt, text_for_usage)
                tokens_in += ti
                tokens_out += to
                cost_usd += compute_cost_usd(ti, to, provider=provider, model=model_id)
                return insight, _metrics()
            except Exception as exc:  # noqa: BLE001
                latency_ms += int((time.monotonic() - start) * 1000)
                logger.info(
                    "analyst_v3: structured output no disponible o inválido (%s); "
                    "reintentando con JSON en texto",
                    type(exc).__name__,
                )

        call: LLMCallResult = await asyncio.wait_for(
            call_llm(llm, prompt, model=model_id), timeout=timeout
        )
        tokens_in += call.tokens_in
        tokens_out += call.tokens_out
        latency_ms += call.latency_ms
        cost_usd += call.cost_usd
        try:
            return parse_insight_v3(call.text), _metrics()
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "analyst_v3: JSON inválido (%s); intento de reparación (1/1)",
                type(exc).__name__,
            )
            first_error = exc
            first_text = call.text

        repair = await asyncio.wait_for(
            call_llm(llm, _v3_repair_prompt(prompt, first_text, first_error), model=model_id),
            timeout=timeout,
        )
        tokens_in += repair.tokens_in
        tokens_out += repair.tokens_out
        latency_ms += repair.latency_ms
        cost_usd += repair.cost_usd
        try:
            return parse_insight_v3(repair.text), _metrics()
        except Exception as exc:  # noqa: BLE001
            raise _InsightV3Error(
                f"InsightV3 inválido tras reparación: {type(exc).__name__}"
            ) from exc

    async def _invoke_single_v3(
        self,
        input_: AnalystV3Input,
        forbidden_names: list[str],
        timeout: float,
        semaphore: asyncio.Semaphore,
    ) -> V3CallResult:
        """Renderiza el prompt, llama al modelo y escrubea el resultado."""
        prompt_version = v3_prompt_version(input_.analysis_kind)
        context = self._build_v3_context(input_)
        prompt = render_prompt(prompt_version, context, strict=True)
        grounding_numbers = sorted(
            extract_numeric_tokens(grounding_source_text(prompt))
        )

        llm = self._llm or build_chat_llm(
            role="analyst", max_output_tokens=_V3_MAX_OUTPUT_TOKENS
        )

        async with semaphore:
            insight, metrics = await self._generate_v3(
                llm, prompt, prompt_version, timeout
            )

        insight = scrub_insight_v3(insight, forbidden_names, input_.athlete_ref)
        return V3CallResult(
            insight=insight, metrics=metrics, grounding_numbers=grounding_numbers
        )

    async def invoke_v3(
        self,
        inputs: list[AnalystV3Input],
        *,
        forbidden_names: list[str] | None = None,
        timeout_seconds: float | None = None,
        concurrency: int = _V3_CONCURRENCY,
    ) -> dict[int, V3CallResult]:
        """Genera un :class:`InsightV3` por cada entrada, con cap de concurrencia.

        A diferencia de :meth:`invoke_per_valida`, esta llamada **nunca
        propaga** una excepción por entrada: una válida que falla recibe el
        fallback determinista v3 y las demás siguen su curso. El caller
        distingue el fallback con
        :func:`app.services.race.ai.fallback.is_fallback_output`.

        Args:
            inputs: una entrada por válida (``analysis_kind="valida"``) o una
                sola con ``analysis_kind="season"``.
            forbidden_names: nombres reales a escrubear del output. NUNCA
                viajan al prompt.
            timeout_seconds: timeout por llamada al proveedor. Default:
                ``Settings.race_ai_v3_timeout_seconds`` (120 s).
            concurrency: llamadas simultáneas al proveedor (default 2).

        Returns:
            ``{valida_num: V3CallResult}`` (``valida_num=0`` para temporada).
        """
        from app.config import settings
        from app.services.race.ai.fallback import deterministic_fallback_v3

        timeout = timeout_seconds or float(settings.race_ai_v3_timeout_seconds)
        semaphore = asyncio.Semaphore(max(1, int(concurrency)))
        names = list(forbidden_names or [])

        async def _one(input_: AnalystV3Input) -> tuple[int, V3CallResult]:
            prompt_version = v3_prompt_version(input_.analysis_kind)
            try:
                result = await self._invoke_single_v3(input_, names, timeout, semaphore)
                return input_.valida_num, result
            except Exception:  # noqa: BLE001
                logger.warning(
                    "analyst_v3: fallo en válida %d — activando fallback v3",
                    input_.valida_num,
                    exc_info=True,
                )
                return input_.valida_num, V3CallResult(
                    insight=deterministic_fallback_v3(
                        analysis_kind=input_.analysis_kind
                    ),
                    metrics=RunMetrics(
                        tokens_in=0,
                        tokens_out=0,
                        latency_ms=0,
                        cost_usd=0.0,
                        prompt_version=prompt_version,
                    ),
                    grounding_numbers=[],
                )

        gathered = await asyncio.gather(
            *(_one(i) for i in inputs), return_exceptions=True
        )

        out: dict[int, V3CallResult] = {}
        for i, item in enumerate(gathered):
            if isinstance(item, BaseException):  # pragma: no cover - _one no lanza
                input_ = inputs[i]
                logger.error(
                    "analyst_v3: gather exception para válida %d: %s",
                    input_.valida_num,
                    type(item).__name__,
                )
                out[input_.valida_num] = V3CallResult(
                    insight=deterministic_fallback_v3(
                        analysis_kind=input_.analysis_kind
                    ),
                    metrics=RunMetrics(
                        tokens_in=0,
                        tokens_out=0,
                        latency_ms=0,
                        cost_usd=0.0,
                        prompt_version=v3_prompt_version(input_.analysis_kind),
                    ),
                    grounding_numbers=[],
                )
            else:
                valida_num, result = item
                out[valida_num] = result
        return out


def v3_prompt_version(analysis_kind: str | None) -> str:
    """``"season"`` → prompt de temporada; cualquier otro → prompt por válida."""
    return (
        PROMPT_VERSION_SEASON_SUMMARY_V3
        if (analysis_kind or "valida") == "season"
        else PROMPT_VERSION_ANALYST_V3
    )


def _build_structured_llm(llm: Any) -> tuple[Any | None, bool]:
    """Devuelve ``(structured_llm, include_raw)`` o ``(None, False)``.

    ``include_raw=True`` conserva el ``AIMessage`` original y con él el
    ``usage_metadata`` real; si el binding del proveedor no soporta ese
    kwarg se cae a la variante simple (tokens estimados por caracteres).
    """
    factory = getattr(llm, "with_structured_output", None)
    if factory is None:
        return None, False
    try:
        return factory(InsightV3, include_raw=True), True
    except TypeError:
        pass
    except Exception:  # noqa: BLE001
        return None, False
    try:
        return factory(InsightV3), False
    except Exception:  # noqa: BLE001
        return None, False


async def _call_structured_v3(
    structured: Any, prompt: str, include_raw: bool
) -> tuple[InsightV3, Any]:
    """Invoca el binding structured y normaliza sus tres formas de respuesta."""
    from langchain_core.messages import HumanMessage

    response = await structured.ainvoke([HumanMessage(content=prompt)])

    raw: Any = None
    parsed: Any = response
    if include_raw and isinstance(response, dict):
        raw = response.get("raw")
        error = response.get("parsing_error")
        if error:
            raise ValueError(f"parsing_error: {type(error).__name__}")
        parsed = response.get("parsed")

    if parsed is None:
        raise ValueError("structured output devolvió parsed=None")
    if isinstance(parsed, InsightV3):
        return parsed, raw
    if isinstance(parsed, dict):
        return InsightV3.model_validate(parsed), raw
    return parse_insight_v3(extract_text(parsed)), raw


def _v3_repair_prompt(prompt: str, previous_text: str, error: Exception) -> str:
    """Prompt de reparación: el original + el error + el intento fallido."""
    excerpt = _strip_json_fence(previous_text or "")[:_V3_REPAIR_EXCERPT_CHARS]
    return (
        f"{prompt}\n\n"
        "# Corrección obligatoria\n\n"
        "Tu respuesta anterior no fue un objeto JSON válido para el esquema pedido.\n"
        f"Error del validador: {type(error).__name__}: {str(error)[:300]}\n\n"
        "Respuesta anterior (recortada):\n\n"
        f"```\n{excerpt}\n```\n\n"
        "Devuelve ÚNICAMENTE el objeto JSON corregido, sin texto alrededor, "
        "sin ```json y respetando las cardinalidades "
        "(observations 2-4, actions 2-3)."
    )


class _VetoDuroError(Exception):
    """Señal interna: el output del LLM contiene una frase de veto duro."""
