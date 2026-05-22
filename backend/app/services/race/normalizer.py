"""Normalización y parsing puro de campos PDF Copa Valle.

Funciones sin DB ni I/O. Toda la inteligencia de extracción textual está aquí:
- Nombres y clubes (`unidecode` + lower + collapse).
- Detección fuzzy del club Trocha y Ruta (`rapidfuzz.fuzz.partial_ratio`).
- Parseo de tiempos `H:MM:SS` → milisegundos (decisión Paso 2 ambigüedad #3).
- Parseo de status `DNF` / `DSQ` / `DNS` / `(-N VUELTA[S])`.
- Mapping `CAT: <NOMBRE>` → code interno del catálogo (`HEADER_TO_CODE`).

Origen: módulo F1.7 (CLI ingest_race). Decisiones de mapping y edge cases
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
#: 26 entradas correspondientes a las 26 categorías observadas en Válida IV
#: (edge-cases.md §2). Si una válida futura usa un texto distinto (ej.
#: ``INFANTIL A (FEMENINO)``), ampliar este dict — punto único de cambio.
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
}

# ---------------------------------------------------------------------------
# Regex para parse_time
# ---------------------------------------------------------------------------

#: Patrón ``(-N VUELTA[S])`` con N entero ≥1. Tolera mayúsculas/minúsculas y
#: espacio opcional. Ej: ``(-1 VUELTA)``, ``(-2 VUELTAS)``, ``(-12 VUELTAS)``.
_MINUS_LAPS_RE = re.compile(r"^\(-(\d+)\s*VUELTAS?\)$", re.IGNORECASE)

#: Patrón ``H:MM:SS`` (con H de 1+ dígito). El PDF usa formato 24h pero las
#: pruebas son XCO < 4h, así que rara vez excede ``2:30:00``.
_TIME_HMS_RE = re.compile(r"^(\d+):(\d{2}):(\d{2})$")

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
    - ``H:MM:SS``   → ``(FINISHED, <ms>, 0)``

    Lanza ``ValueError`` si el formato no coincide con ningún patrón conocido —
    el parser debe atrapar y emitir warning para que la ingesta no se rompa.
    """
    if raw is None:
        raise ValueError("parse_time recibió None")
    s = raw.strip()
    su = s.upper()

    if su == "DNF":
        return ResultStatus.DNF, None, 0
    if su == "DSQ":
        return ResultStatus.DSQ, None, 0
    if su == "DNS":
        return ResultStatus.DNS, None, 0

    m = _MINUS_LAPS_RE.match(su)
    if m:
        return ResultStatus.MINUS_LAPS, None, int(m.group(1))

    m = _TIME_HMS_RE.match(s)
    if m:
        h, mm, ss = (int(x) for x in m.groups())
        if mm >= 60 or ss >= 60:
            raise ValueError(f"Componentes de tiempo fuera de rango: {raw!r}")
        ms = (h * 3600 + mm * 60 + ss) * 1000
        return ResultStatus.FINISHED, ms, 0

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
