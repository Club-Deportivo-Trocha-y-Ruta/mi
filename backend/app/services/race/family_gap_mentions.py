"""Aviso de brecha al podio en el texto para familias (feature 045, T030, FR-022).

Decisión del dueño (2026-09-23): la familia nunca ve brecha a la ganadora ni
al podio, en ninguna parte. Las cifras estructuradas ya se omiten server-side
(``athlete_race_analysis._structured_for_response``); esto cubre el **texto
libre** que redacta la IA. Cuando el coach abre un borrador para aprobarlo, el
backend escanea lo que verá la familia y devuelve fragmentos que mencionan al
líder, la ganadora, P1/P3, el primer o tercer lugar o el podio. La tarjeta de
aprobación muestra un aviso; la decisión sigue siendo del coach (no se
reescribe la salida de la IA después del crítico — research R-06).

Módulo puro: sin BD, sin I/O y **sin logging**. El texto de un borrador puede
referirse a un menor, así que nunca se registra ni se guarda.

Coincidencias
=============
Se busca sobre el texto plegado (minúsculas, sin tildes; el pliegue es 1:1 por
carácter, así que los snippets salen del texto original con sus tildes) y con
límites de palabra. Las reglas viven en :data:`MENTION_PATTERNS`; agregar una
mención nueva es agregar una fila (abierto/cerrado).

Compromisos deliberados (precisión vs. cobertura). Es un aviso, no un bloqueo,
así que se prefiere avisar de más antes que dejar pasar una brecha, salvo en
las palabras muy comunes:

- ``primer``/``tercer`` cuentan **sólo** junto a un sustantivo de puesto
  (lugar, puesto, posición, plaza, clasificado). «Primera vuelta», «primer
  intento», «tercera válida» o «los primeros 5 minutos» no avisan.
- «Primero»/«tercero» sueltos cuentan sólo como referente de un jinete
  («al primero», «del tercero», «con el primero») y no si siguen con «a/al»
  («del primero al segundo»). «A la primera» (modismo) nunca cuenta. Costo
  conocido: «al primero de los bloques» sí avisa.
- «En primer/tercer lugar» como conector («En primer lugar, ...») no avisa;
  «terminó en primer lugar» sí.
- «Líder»/«ganador»/«vencedor»/«campeón» (con sus géneros y plurales) cuentan;
  «liderazgo», «lidera» y «campeonato» no (los verbos como «ganó»/«lidera» son
  demasiado ambiguos: «ganó 3 posiciones»).
- P1/P3 y «puesto/posición 1|3» avisan aunque describan el resultado propio
  del atleta («terminó en P3»): el coach lo descarta en un vistazo.
- Cifras sin marca ordinal («3 posiciones») nunca cuentan.

Campos que ve la familia
========================
Una aprobación publica el borrador tal como lo ve el padre: el detalle del
insight con las omisiones de ``_structured_for_response(for_parent=True)`` y la
tarjeta ``InsightV3Card`` en ``mode="parent"``. Se escanean sólo esos campos
del ``InsightV3`` (:func:`family_visible_texts`):

- ``headline``
- ``field_reading.summary`` y ``field_reading.series_label``
- ``observations[].claim`` (todas) y ``observations[].evidence[]`` de las
  observaciones que no son de dominio ``training`` — la API le quita la
  evidencia a las de ``training`` y la tarjeta familiar oculta esas
  observaciones; el ``claim`` se escanea igual porque la API sí lo envía.
- ``actions[].text``
- ``watch_signals[]``, ``data_gaps[]`` y ``principles_cited[]``

Quedan fuera lo que la familia no recibe: ``coach_question``,
``field_reading.gap_to_p3_hhmmss`` / ``expected_position`` /
``delta_vs_expected``, el bloque ``critic``, el pseudónimo, y el
``draft_markdown`` de los borradores v3 (es la proyección de la vista del
coach: incluye «gap a P3» y «Pregunta para el coach», y avisaría siempre).
Un borrador **sin** estructura (v1/v2) sólo existe como markdown, y ese
markdown es lo que se publica: entonces sí se escanea entero. En runs
multi-válida se recorren todos los borradores de ``structured_drafts``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Pattern

__all__ = [
    "FAMILY_GAP_MENTIONS_KEY",
    "MAX_SNIPPETS",
    "MAX_SNIPPET_CHARS",
    "MENTION_PATTERNS",
    "MentionPattern",
    "family_visible_texts",
    "find_family_gap_mentions",
    "with_family_gap_mentions",
]

FAMILY_GAP_MENTIONS_KEY = "family_gap_mentions"
MAX_SNIPPETS = 3
MAX_SNIPPET_CHARS = 80
_ELLIPSIS = "…"
_TRAINING_DOMAIN = "training"


# ---------------------------------------------------------------------------
# Tabla de patrones (abierto/cerrado: agregar una fila = agregar una mención)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MentionPattern:
    """Una regla de detección sobre texto plegado (minúsculas, sin tildes)."""

    name: str
    regex: Pattern[str]


def _rule(name: str, pattern: str) -> MentionPattern:
    return MentionPattern(name=name, regex=re.compile(pattern))


# Sustantivos de puesto. Aceptan plural («primeros lugares»).
_PLACE_NOUN = r"(?:lugar(?:es)?|puestos?|posicion(?:es)?|plazas?|clasificad[oa]s?)"
# Marca ordinal tras un dígito: 1.º, 1º, 3er, 3.er, 3ro, 1.°
_DIGIT_ORDINAL = r"\s?(?:\.\s?)?(?:er|ro|ra|º|°)"


def _ordinal_place_rules(name: str, word: str, digit: str) -> tuple[MentionPattern, ...]:
    """«primer lugar», «tercera posición», «1.º puesto», «puesto 3», ...

    ``word`` es la raíz del ordinal en letras; ``digit`` el dígito. El conector
    «en primer lugar, ...» se excluye con dos reglas: la ordinal sin ``en``
    delante, y la ordinal con ``en`` sólo si no la sigue una coma/dos puntos.
    """
    ordinal = rf"(?:{word}(?:er|era|ero|eros|eras)|{digit}{_DIGIT_ORDINAL})"
    core = rf"{ordinal}\s+{_PLACE_NOUN}\b"
    return (
        _rule(name, rf"(?<!\ben )\b{core}"),
        _rule(name, rf"\ben\s+{core}(?!\s*[,;:])"),
        # «puesto 3», «posición nº 1», «lugar 3».
        _rule(name, rf"\b(?:lugar|puesto|posicion)\s+(?:n[o°º]?\.?\s*)?{digit}\b"),
    )


MENTION_PATTERNS: tuple[MentionPattern, ...] = (
    # Líder: «líder», «líderes», «lideresa»; no «liderazgo» ni «lidera».
    _rule("leader", r"\blider(?:es|esa|esas)?\b"),
    _rule("leader", r"\bpunter[oa]s?\b"),
    _rule("leader", r"\b(?:cabeza|punta)\s+de\s+(?:la\s+)?carrera\b"),
    # Ganador/a: no el verbo «ganó».
    _rule("winner", r"\b(?:ganador|vencedor|campeon)(?:a|es|as)?\b"),
    _rule("winner", r"\bprimer[oa]s?\s+en\s+(?:cruzar|terminar|finalizar|llegar\s+a\s+(?:la\s+)?meta)\b"),
    # Podio.
    _rule("podium", r"\b(?:podios?|podium)\b"),
    _rule("podium", r"\btop[\s-]?(?:3|tres)\b"),
    _rule("podium", r"\b(?:los|las)\s+(?:3|tres)\s+primer[oa]s\b"),
    # P1 / P3.
    _rule("p1_p3", r"\bp-?[13]\b"),
    # Primer / tercer lugar.
    *_ordinal_place_rules("first_place", "prim", "1"),
    *_ordinal_place_rules("third_place", "terc", "3"),
    # «al primero», «del tercero», «con el primero» (referente de un jinete).
    _rule(
        "rider_reference",
        r"\b(?:(?:al|del)|(?:con|contra|sobre)\s+el)\s+(?:primero|tercero)\b(?!\s+(?:al|a)\b)",
    ),
)


# ---------------------------------------------------------------------------
# Detección
# ---------------------------------------------------------------------------


def _fold(text: str) -> str:
    """Minúsculas y sin tildes, **1:1 por carácter** (los índices se conservan).

    Recibe texto ya en NFC: cada carácter compuesto (``í``) se reduce a su base
    (``i``) sin cambiar el largo, así los índices del texto plegado sirven para
    recortar el original.
    """
    out: list[str] = []
    for ch in text:
        if ch.isascii():
            out.append(ch.lower())
            continue
        base = unicodedata.normalize("NFD", ch)[0]
        lowered = base.lower()
        out.append(lowered[0] if lowered else base)
    return "".join(out)


def _prepare(raw: str) -> str:
    """NFC + espacios colapsados (los snippets no llevan saltos ni tabs)."""
    return " ".join(unicodedata.normalize("NFC", raw).split())


def _spans(folded: str) -> list[tuple[int, int]]:
    """Coincidencias de todas las reglas, ordenadas y sin solapes."""
    raw = sorted(
        (m.start(), m.end())
        for rule in MENTION_PATTERNS
        for m in rule.regex.finditer(folded)
    )
    merged: list[tuple[int, int]] = []
    for start, end in raw:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _window(text: str, start: int, end: int) -> tuple[int, int]:
    """Ventana [ws, we) de ≤80 caracteres centrada en la coincidencia.

    Reserva 2 caracteres para «…» a cada lado y ajusta los bordes a un espacio
    cuando puede, para no partir palabras.
    """
    if len(text) <= MAX_SNIPPET_CHARS:
        return 0, len(text)
    inner = MAX_SNIPPET_CHARS - 2 * len(_ELLIPSIS)
    match_len = end - start
    if match_len >= inner:
        return start, start + inner
    ws = max(0, start - (inner - match_len) // 2)
    we = min(len(text), ws + inner)
    ws = max(0, we - inner)
    if ws > 0:
        space = text.find(" ", ws, start)
        if space != -1:
            ws = space + 1
    if we < len(text):
        space = text.rfind(" ", end, we)
        if space != -1:
            we = space
    return ws, we


def _render(text: str, ws: int, we: int) -> str:
    body = text[ws:we].strip()
    return f"{_ELLIPSIS if ws > 0 else ''}{body}{_ELLIPSIS if we < len(text) else ''}"


def find_family_gap_mentions(
    text_fields: Iterable[str | None] | str | None,
) -> list[str]:
    """Fragmentos que mencionan líder, ganador, P1/P3, primer/tercer lugar o podio.

    Args:
        text_fields: textos que ve la familia (ver el docstring del módulo).
            Un ``str`` suelto se trata como un único campo.

    Returns:
        Hasta :data:`MAX_SNIPPETS` fragmentos de ≤ :data:`MAX_SNIPPET_CHARS`
        caracteres tomados del texto original, en el orden de los campos y de
        aparición. Menciones cercanas dentro de un campo se agrupan en un solo
        fragmento y los fragmentos repetidos se descartan. ``[]`` si no hay
        menciones.
    """
    if text_fields is None:
        return []
    fields: Iterable[str | None] = (
        (text_fields,) if isinstance(text_fields, str) else text_fields
    )

    snippets: list[str] = []
    seen: set[str] = set()
    for raw in fields:
        if not isinstance(raw, str) or not raw.strip():
            continue
        text = _prepare(raw)
        emitted: list[tuple[int, int]] = []
        for start, end in _spans(_fold(text)):
            if any(ws <= start and end <= we for ws, we in emitted):
                continue  # ya cubierta por un fragmento de este campo
            ws, we = _window(text, start, end)
            emitted.append((ws, we))
            snippet = _render(text, ws, we)
            key = _fold(snippet)
            if key in seen:
                continue
            seen.add(key)
            snippets.append(snippet)
            if len(snippets) >= MAX_SNIPPETS:
                return snippets
    return snippets


# ---------------------------------------------------------------------------
# Campos del borrador que ve la familia
# ---------------------------------------------------------------------------


def _add(texts: list[str], value: Any) -> None:
    if isinstance(value, str) and value.strip():
        texts.append(value)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _structured_family_texts(structured: Mapping[str, Any]) -> list[str]:
    """Campos de un ``InsightV3`` serializado que llegan al padre."""
    texts: list[str] = []
    _add(texts, structured.get("headline"))

    field_reading = structured.get("field_reading")
    if isinstance(field_reading, Mapping):
        _add(texts, field_reading.get("summary"))
        _add(texts, field_reading.get("series_label"))

    for obs in _as_list(structured.get("observations")):
        if not isinstance(obs, Mapping):
            continue
        _add(texts, obs.get("claim"))
        if obs.get("domain") != _TRAINING_DOMAIN:
            for evidence in _as_list(obs.get("evidence")):
                _add(texts, evidence)

    for action in _as_list(structured.get("actions")):
        if isinstance(action, Mapping):
            _add(texts, action.get("text"))

    for key in ("watch_signals", "data_gaps", "principles_cited"):
        for item in _as_list(structured.get(key)):
            _add(texts, item)
    return texts


def _draft_sort_key(key: Any) -> tuple[int, Any]:
    try:
        return (0, int(key))
    except (TypeError, ValueError):
        return (1, str(key))


def _structured_drafts(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Borradores estructurados del payload HITL (todos los de un run multi-válida)."""
    many = payload.get("structured_drafts")
    if isinstance(many, Mapping):
        drafts = [
            many[k] for k in sorted(many, key=_draft_sort_key) if isinstance(many[k], Mapping)
        ]
        if drafts:
            return drafts
    single = payload.get("structured_draft")
    return [single] if isinstance(single, Mapping) else []


def family_visible_texts(payload: Mapping[str, Any]) -> list[str]:
    """Textos del payload ``hitl_request`` que verá la familia al aprobarse.

    Con borrador estructurado (v3) se toman sólo los campos de la lista del
    docstring del módulo. Sin él (v1/v2) el markdown es lo que se publica y se
    devuelve entero.
    """
    drafts = _structured_drafts(payload)
    if drafts:
        return [text for draft in drafts for text in _structured_family_texts(draft)]
    markdown = payload.get("draft_markdown")
    return [markdown] if isinstance(markdown, str) and markdown.strip() else []


def with_family_gap_mentions(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Copia del payload ``hitl_request`` con ``family_gap_mentions`` calculado.

    Sólo para coach/admin, y se calcula al leer: nada se persiste ni se muta
    el payload almacenado. Devuelve siempre la clave (``[]`` si no hay
    menciones).
    """
    enriched = dict(payload)
    enriched[FAMILY_GAP_MENTIONS_KEY] = find_family_gap_mentions(
        family_visible_texts(payload)
    )
    return enriched
