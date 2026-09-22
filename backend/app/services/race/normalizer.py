"""Normalización y parsing puro de campos PDF Copa Valle.

Funciones sin DB ni I/O. Toda la inteligencia de extracción textual está aquí:
- Nombres y clubes (`unidecode` + lower + collapse).
- Detección fuzzy del club Trocha y Ruta (`rapidfuzz.fuzz.partial_ratio`).
- Parseo de tiempos `H:MM:SS` → milisegundos (decisión Paso 2 ambigüedad #3).
- Parseo de status `DNF` / `DSQ` / `DNS` / `(-N VUELTA[S])`.
- Mapping `CAT: <NOMBRE>` → code interno del catálogo (`HEADER_TO_CODE`).

Origen: módulo F1.7 (race results). Decisiones de mapping y edge cases
documentadas históricamente; consultar `git log -- backend/app/services/race/`
para audit trail.
"""
from __future__ import annotations

import re
from typing import Optional

from rapidfuzz import fuzz
from unidecode import unidecode

from app.models.race_result import ResultStatus

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Variantes literales del club TyR observadas en PDFs reales (Válida IV).
#: La comparación se hace contra el club normalizado del corredor con
#: ``fuzz.partial_ratio`` (NO ``fuzz.ratio``) — ver edge-cases.md §7.4 para
#: la justificación: ``ratio("club trocha y ruta", "trocha y ruta") = 76``
#: pero ``partial_ratio = 100`` porque la subcadena coincide. Esto importa
#: porque algunos riders aparecen con club `"TROCHA Y RUTA"` (sin "Club").
TYR_VARIANTS: tuple[str, ...] = (
    "trocha y ruta",
    "club trocha y ruta",
    "trochy ruta",
    "trochayruta",
)

#: Default threshold para ``is_trocha_y_ruta`` (paridad con design.md §4.2).
DEFAULT_TYR_THRESHOLD: int = 85

#: Mapping ``CAT: <NOMBRE>`` (normalizado) → code interno del catálogo de
#: ``race_categories``. Igualdad exacta sobre header normalizado para evitar
#: la colisión ``"INFANTIL A" ⊂ "INFANTIL A FEMENINO"`` (edge-cases.md §4.4).
#:
#: 38 entradas: las 26 categorías observadas en Válida IV (edge-cases.md §2)
#: más 12 alias históricos Copa Valle 2024/2025 (feature 044, ver
#: ``contracts/category-mapping.md`` y ``HEADER_ALIASES``). Si una válida
#: futura usa un texto distinto (ej. ``INFANTIL A (FEMENINO)``), ampliar
#: este dict — punto único de cambio.
HEADER_TO_CODE: dict[str, str] = {
    "teteros sin pedales": "TET_SP",
    "teteros con pedales": "TET_CP",
    "preinfantil a": "PRE_A",
    "preinfantil a femenino": "PRE_A_F",
    "preinfantil b": "PRE_B",
    "preinfantil b femenino": "PRE_B_F",
    "infantil a": "INF_A",
    "infantil a femenino": "INF_A_F",
    "infantil b": "INF_B",
    "infantil b femenino": "INF_B_F",
    "prejuvenil a": "PJUV_A",
    "prejuvenil a femenino": "PJUV_A_F",
    "prejuvenil b": "PJUV_B",
    "prejuvenil b femenino": "PJUV_B_F",
    "junior": "JUN_M",
    "junior femenino": "JUN_F",
    "elite": "ELITE_M",
    "elite femenino": "ELITE_F",
    "promocional": "PROMO",
    "master a": "MAS_A",
    "master b1": "MAS_B1",
    "master b2": "MAS_B2",
    "master c1": "MAS_C1",
    "master c2": "MAS_C2",
    "master d": "MAS_D",
    "master femenino": "MAS_F",
    # ------------------------------------------------------------------
    # Alias históricos (feature 044, carga histórica Copa Valle 2024/2025).
    # Ver contracts/category-mapping.md y research.md R-03. Amplían el
    # MISMO dict (no uno paralelo) — 26 originales + 12 alias = 38 entradas.
    # ------------------------------------------------------------------
    # --- Renombres puros: header histórico distinto, misma categoría 2026 --
    "elite hombres": "ELITE_M",
    "elite damas": "ELITE_F",
    "junior damas": "JUN_F",
    "master damas": "MAS_F",
    "infantil a ninas": "INF_A_F",
    "infantil b ninas": "INF_B_F",
    "prejuvenil a damas": "PJUV_A_F",
    "prejuvenil b damas": "PJUV_B_F",
    # --- Propios de temporada: sin equivalente activo, resuelven a codes --
    # --- inactivos del catálogo (nunca ofrecidos para datos 2026+) --------
    "master b": "MAS_B_2025",
    "master c": "MAS_C_2025",
    "preinfantil ninas": "PRE_F_U",
    "preinfantil femenino": "PRE_F_U",
}

#: Subconjunto de keys de ``HEADER_TO_CODE`` que son alias históricos (feature
#: 044) — es decir, NO están entre las 26 originales de Válida IV 2026.
#: Usado por ``mapping_kind_for`` para distinguir ``exact`` de
#: ``rename``/``season_specific``. Disjunto de las 26 keys originales por
#: construcción (contracts/category-mapping.md).
HEADER_ALIASES: frozenset[str] = frozenset(
    {
        "elite hombres",
        "elite damas",
        "junior damas",
        "master damas",
        "infantil a ninas",
        "infantil b ninas",
        "prejuvenil a damas",
        "prejuvenil b damas",
        "master b",
        "master c",
        "preinfantil ninas",
        "preinfantil femenino",
    }
)

# ---------------------------------------------------------------------------
# Regex para parse_time
# ---------------------------------------------------------------------------

#: Patrón ``(-N VUELTA[S])`` con N entero ≥1. Tolera mayúsculas/minúsculas y
#: espacio opcional. Ej: ``(-1 VUELTA)``, ``(-2 VUELTAS)``, ``(-12 VUELTAS)``.
_MINUS_LAPS_RE = re.compile(r"^\(-(\d+)\s*VUELTAS?\)$", re.IGNORECASE)

#: Palabra "vuelta(s)" tal como la escriben las actas, erratas medidas
#: incluidas (``VUELTA``, ``VUELTAS``, ``VULETAS``, ``VIELTAS``). Deliberadamente
#: estrecha: una ``V`` seguida de ``EL``/``LE`` y ``TA[S]`` no se confunde con
#: un club ni con un nombre propio que empiece por ``V``.
LAP_WORD_PATTERN = r"V[UÚI]?(?:EL|LE)TAS?"

#: Déficit de vueltas en cualquiera de las formas medidas en 2024–2025
#: (feature 044, T024b): ``-1 vuelta``, ``(1- VUELTA``, ``(- 1 VUELTA)``,
#: ``(2 VUELTAS)``, ``(-3 VUELTAS=``, ``()-1 VUELTA)``, ``-2 vueltas (lap)``
#: o un ``-N`` desnudo. Se acepta solo si trae la palabra de vuelta o un
#: signo menos — un número suelto no es un déficit (ver ``parse_time``).
_LAP_DEFICIT_RE = re.compile(
    r"^\(?\s*\)?\s*(?P<pre>-)?\s*(?P<n>\d{1,2})\s*(?P<post>-)?\s*"
    r"(?P<word>" + LAP_WORD_PATTERN + r")?"
    r"\s*[)=\-]?\s*(?:\(\w+\))?$",
    re.IGNORECASE,
)

#: Patrón ``H:MM:SS``. El apóstrofo opcional antes de los segundos es una
#: errata medida en un acta de 2025 (``0:16:'08``).
_TIME_HMS_RE = re.compile(r"^(\d+):(\d{2}):'?(\d{2})$")

#: Patrón ``MM:SS`` (categorías cortas que imprimen el tiempo sin horas).
_TIME_MS_RE = re.compile(r"^(\d{1,2}):(\d{2})$")

#: Una prueba XCO dura menos de 10 h; una hora ≥ 10 es una errata del acta
#: (``12:02:00`` entre tiempos de 1:2x) y no se inventa un tiempo con ella.
_MAX_XCO_HOURS = 9

#: Patrón inicio "CAT: <texto>" (PDF Federación) o "CATEGORÍA: <texto>" /
#: "CATEGORIA: <texto>" (CSV/XLSX Federación V-I Sevilla 2026). Texto puede
#: tener cualquier combinación de mayúsculas/tildes/espacios.
_CAT_HEADER_RE = re.compile(
    r"^\s*(?:CAT|CATEGOR(?:I|Í)A)\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)

#: Patrones del club que el PDF a veces escribe con valor placeholder ``0``
#: u otro marcador equivalente a "no club declarado" (edge-cases.md §4.3).
_EMPTY_CLUB_TOKENS: frozenset[str] = frozenset({"0", "-", "n/a", "na", ""})


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _strip_diacritics_lower(s: str) -> str:
    """Aplica ``unidecode`` + lower + colapsa espacios. Sin punctuation strip.

    Útil para comparación interna; ``normalize_name`` además quita puntuación
    leve para que ``"García, Pedro"`` y ``"Garcia Pedro"`` matcheen.
    """
    if not s:
        return ""
    out = unidecode(s).lower()
    out = re.sub(r"\s+", " ", out).strip()
    return out


# ---------------------------------------------------------------------------
# API pública — normalización de texto
# ---------------------------------------------------------------------------


def normalize_name(s: str) -> str:
    """Normaliza nombre completo: ``unidecode`` + lower + colapsa espacios.

    Quita puntuación leve (``.,;:``) que aparece en PDFs (ej. ``"García."``).
    No quita guiones (``-``) ni apóstrofes (``'``) — son parte de apellidos
    compuestos (``"Saint-Étienne"``, ``"D'Alessandro"``).

    Devuelve cadena vacía si la entrada es vacía/None.
    """
    if not s:
        return ""
    out = unidecode(s).lower()
    out = re.sub(r"[.,;:]", " ", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def normalize_club(s: str) -> str:
    """Normaliza nombre de club.

    - ``unidecode`` + lower + colapsa espacios.
    - Mapea placeholders observados (``"0"``, ``"-"``, ``"n/a"``, ``""``) a ``""``
      vacío para que ``is_trocha_y_ruta`` los descarte sin riesgo de falso
      positivo y para que el ingestor pueda guardar ``NULL`` en lugar del
      placeholder textual.

    Referencia: edge-cases.md §4.3 (rider 1305 con city/club ``0``).
    """
    if not s:
        return ""
    out = unidecode(s).lower()
    out = re.sub(r"\s+", " ", out).strip()
    if out in _EMPTY_CLUB_TOKENS:
        return ""
    return out


#: Longitud mínima del club normalizado para usar ``partial_ratio``. Por
#: debajo de esto, ``partial_ratio`` produce falsos positivos masivos sobre
#: clubes cortos (ej. ``"Otro"`` da ``partial_ratio=85.7`` contra
#: ``"trocha y ruta"`` porque "otro" comparte 4 letras con "tr**o**cha…r**o**…"
#: en posiciones cercanas). Para clubs cortos exigimos ``ratio`` exacta.
#:
#: Calibración: ``"trochy ruta"`` (11 chars) y ``"trocha y ruta"`` (13 chars)
#: son las variantes más cortas. Umbral 9 es conservador: rechaza ``"Otro"``
#: (4), ``"Sin club"`` (8) y conserva los positivos legítimos.
_PARTIAL_MIN_LEN: int = 9


def is_trocha_y_ruta(club: str, threshold: int = DEFAULT_TYR_THRESHOLD) -> bool:
    """¿Este club textual corresponde a Trocha y Ruta?

    Estrategia híbrida:
    - Si el club normalizado tiene **>= 9 caracteres** → usa
      ``rapidfuzz.fuzz.partial_ratio`` contra ``TYR_VARIANTS`` (decisión
      edge-cases.md §7.4 — captura ``"TROCHA Y RUTA"`` vs ``"Club Trocha y Ruta"``).
    - Si el club normalizado es **corto** (< 9 chars) → exige ``ratio``
      exacta. Esto evita falsos positivos sobre ``"Otro"`` (4 chars,
      partial_ratio=85.7) y ``"Sin club"`` (8 chars, partial_ratio=66).

    El edge-cases.md §4.15 afirmaba ``partial_ratio("otro", "trocha y ruta")≈25``
    pero la medición real es 85.7 — el guard de longitud lo corrige sin alterar
    los 10 oracle TyR de Válida IV.

    - Pasa el club original; ``normalize_club`` se aplica internamente.
    - Si el club normalizado queda vacío (placeholder ``0``/``-``/etc), retorna
      ``False`` sin invocar al fuzzy.
    - ``threshold`` default 85: validado contra los 10 corredores TyR del PDF
      Válida IV — todos dan score 100.

    No lanza excepciones; ``""`` y ``None`` → ``False``.
    """
    if not club:
        return False
    normalized = normalize_club(club)
    if not normalized:
        return False
    if len(normalized) < _PARTIAL_MIN_LEN:
        best = max(fuzz.ratio(normalized, v) for v in TYR_VARIANTS)
    else:
        best = max(fuzz.partial_ratio(normalized, v) for v in TYR_VARIANTS)
    return best >= threshold


# ---------------------------------------------------------------------------
# API pública — parsing de tiempos y status
# ---------------------------------------------------------------------------


def parse_time(raw: str) -> tuple[ResultStatus, Optional[int], int]:
    """Convierte un campo "tiempo" del PDF a ``(status, race_time_ms, laps_behind)``.

    Decisión Paso 2 (ambigüedad #3): el modelo persiste ``race_time_ms`` en
    **milisegundos**, no segundos. Para ``H:MM:SS`` retornamos
    ``(h*3600 + m*60 + s) * 1000``.

    Reglas:
    - ``DNF``       → ``(ResultStatus.DNF, None, 0)``
    - ``DSQ``       → ``(ResultStatus.DSQ, None, 0)``
    - ``DNS``       → ``(ResultStatus.DNS, None, 0)`` (heredado del enum aunque
      no observado en V-IV — la federación lo usa en otras válidas).
    - ``(-1 VUELTA)`` → ``(MINUS_LAPS, None, 1)``
    - ``(-N VUELTAS)`` → ``(MINUS_LAPS, None, N)``
    - variantes del déficit de vueltas medidas en 2024–2025 (``-1 vuelta``,
      ``(1- VUELTA``, ``(2 VUELTAS)``, ``-N`` desnudo…) → ``(MINUS_LAPS, None, N)``
    - ``H:MM:SS``   → ``(FINISHED, <ms>, 0)`` (H ≤ 9)
    - ``MM:SS``     → ``(FINISHED, <ms>, 0)``
    - ``""``        → ``(FINISHED, None, 0)``: **clasificado sin tiempo** —
      la fila trae posición y puntos pero la celda Tiempo vino vacía
      (research R-01 punto 4, R-05). Quien llama decide qué hacer si además
      falta la posición.

    Lanza ``ValueError`` si el formato no coincide con ningún patrón conocido —
    el ingestor atrapa, emite warning y conserva la fila con tiempo nulo.
    """
    if raw is None:
        raise ValueError("parse_time recibió None")
    s = raw.strip()
    su = s.upper()

    if not s:
        return ResultStatus.FINISHED, None, 0

    if su == "DNF":
        return ResultStatus.DNF, None, 0
    if su == "DSQ":
        return ResultStatus.DSQ, None, 0
    if su == "DNS":
        return ResultStatus.DNS, None, 0

    m = _MINUS_LAPS_RE.match(su)
    if m:
        return ResultStatus.MINUS_LAPS, None, int(m.group(1))

    m = _LAP_DEFICIT_RE.match(s)
    if m and (m.group("word") or m.group("pre") or m.group("post")):
        laps = int(m.group("n"))
        if laps >= 1:
            return ResultStatus.MINUS_LAPS, None, laps

    m = _TIME_HMS_RE.match(s)
    if m:
        h, mm, ss = (int(x) for x in m.groups())
        if mm >= 60 or ss >= 60 or h > _MAX_XCO_HOURS:
            raise ValueError(f"Componentes de tiempo fuera de rango: {raw!r}")
        ms = (h * 3600 + mm * 60 + ss) * 1000
        return ResultStatus.FINISHED, ms, 0

    m = _TIME_MS_RE.match(s)
    if m:
        mm, ss = (int(x) for x in m.groups())
        if ss >= 60:
            raise ValueError(f"Componentes de tiempo fuera de rango: {raw!r}")
        return ResultStatus.FINISHED, (mm * 60 + ss) * 1000, 0

    raise ValueError(f"Tiempo no parseable: {raw!r}")


def parse_category_header(s: str) -> Optional[str]:
    """De ``"CAT: INFANTIL A FEMENINO"`` a ``"INF_A_F"``.

    Reglas (edge-cases.md §2.1):
    - Match case-insensitive sobre ``CAT:\\s*<texto>``.
    - Normaliza: ``unidecode`` + lower + colapsa espacios.
    - Lookup exacto en ``HEADER_TO_CODE`` (NO substring, para evitar la
      colisión "INFANTIL A" ⊂ "INFANTIL A FEMENINO").
    - Retorna ``None`` si no matchea el prefijo ``CAT:`` o si el header
      normalizado no está en el dict (categoría desconocida — el parser
      debe loggear warning con el texto raw).
    """
    if not s:
        return None
    m = _CAT_HEADER_RE.match(s)
    if not m:
        return None
    header = _strip_diacritics_lower(m.group(1))
    # Strip guión interno: CSV usa "PRE-INFANTIL"/"PRE-JUVENIL", PDF usa
    # "PREINFANTIL"/"PREJUVENIL". HEADER_TO_CODE almacena la forma sin guión.
    header = header.replace("-", "")
    header = re.sub(r"\s+", " ", header).strip()
    return HEADER_TO_CODE.get(header)


def mapping_kind_for(raw_header: str, category: Optional[object]) -> str:
    """Clasifica cómo resolvió un header de categoría (feature 044, US2).

    Recibe el header CRUDO (con prefijo ``CAT:``/``CATEGORIA:``), igual que
    ``parse_category_header`` — no un header ya normalizado — para poder
    aplicar la misma normalización aquí adentro.

    Contrato (``contracts/category-mapping.md``):
    - ``category is None`` → ``"unknown"`` (el header no resolvió a ningún
      code — desconocido para el catálogo).
    - Header normalizado en ``HEADER_ALIASES`` y ``category.is_active`` →
      ``"rename"`` (alias histórico que resuelve a una categoría activa
      2026 — ej. ``ELITE HOMBRES`` → ``ELITE_M``).
    - Header normalizado en ``HEADER_ALIASES`` y NO ``category.is_active``
      → ``"season_specific"`` (alias que resuelve a un code propio de
      temporada, ej. ``MASTER B`` → ``MAS_B_2025``).
    - Cualquier otro header resuelto (una de las 26 keys originales) →
      ``"exact"``.

    ``category`` solo necesita exponer ``.is_active`` (duck typing) — los
    tests lo ejercitan con ``SimpleNamespace`` sin tocar la DB.
    """
    if category is None:
        return "unknown"
    if not raw_header:
        return "exact"
    m = _CAT_HEADER_RE.match(raw_header)
    if not m:
        return "exact"
    header = _strip_diacritics_lower(m.group(1))
    header = header.replace("-", "")
    header = re.sub(r"\s+", " ", header).strip()
    if header in HEADER_ALIASES:
        return "rename" if category.is_active else "season_specific"
    return "exact"
