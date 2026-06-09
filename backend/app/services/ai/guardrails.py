"""Guardrails post-procesamiento.

Aplica reglas regex sobre la salida del LLM para enforce los principios
no negociables del CLAUDE.md. Estas reglas son de defensa en profundidad:
el system prompt ya pide cumplirlos, pero el guardrail garantiza que
nunca se entregue al usuario un texto que los contradiga.

Principios cubiertos:
  - Cero suplementos para menores.
  - Máx 5 días/semana de entrenamiento.
  - Cadencia ≥60 rpm.
  - Sin potenciómetros para <13 años.
  - Sin conteo calórico hablando con atletas.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Si se exceden estas violaciones la respuesta se considera no recuperable.
MAX_VIOLATIONS_BEFORE_REJECT = 3


@dataclass(frozen=True)
class _Rule:
    name: str
    pattern: re.Pattern[str]
    replacement: str | None  # None → eliminar la frase entera
    description: str


_SUPPLEMENT_KEYWORDS = (
    r"creatina|proteína en polvo|proteinas en polvo|"
    r"suplementos?|batidos? proteicos?|aminoácidos?"
)

# Palabras clave que confirman contexto de entrenamiento. Se usan para
# desambiguar frases como "todos los días" — solo deben disparar el guardrail
# cuando aparecen junto a vocabulario de entrenamiento (no en "todos los días
# tomar agua").
_TRAINING_CONTEXT = (
    r"entren\w+|bicicleta|ciclismo|sesi\w+|pedal\w+|rodar|montar|"
    r"plan(?:es)?\s+de\s+entrenamiento|salida\w*"
)

# Patrón compuesto para detectar exceso diario de entrenamiento:
# - Rama A: cuantificador explícito (7 o "siete") + sesiones/días + semana(les)
#   o por/a la semana. El propio sustantivo aporta contexto de entrenamiento,
#   así que no exige co-ocurrencia con _TRAINING_CONTEXT.
# - Rama B: expresiones genéricas ("todos los días", "diariamente", "cada día")
#   que exigen contexto de entrenamiento en una ventana de hasta ~40 caracteres
#   antes o después, para evitar falsos positivos en frases legítimas como
#   "recordar todos los días tomar agua".
_DAILY_TRAINING_PATTERN = re.compile(
    r"(?:"
    # Rama A: número/palabra + sesiones|días + qualifier semanal
    r"\b(?:7|siete)\s+(?:sesion\w*|d[ií]as?)"
    r"\s+(?:a\s+la\s+semana|por\s+semana|semanales)"
    r"|"
    # Rama B1: contexto de entrenamiento ANTES (hasta ~40 caracteres) de la
    # expresión diaria.
    r"(?:" + _TRAINING_CONTEXT + r")[\s\S]{0,40}?"
    r"\b(?:todos\s+los\s+d[ií]as|diariamente|cada\s+d[ií]a)\b"
    r"|"
    # Rama B2: expresión diaria seguida (hasta ~40 caracteres) por contexto
    # de entrenamiento.
    r"\b(?:todos\s+los\s+d[ií]as|diariamente|cada\s+d[ií]a)\b"
    r"[\s\S]{0,40}?(?:" + _TRAINING_CONTEXT + r")"
    r")",
    re.IGNORECASE,
)

# Reglas anti-comparación poblacional / cuasi-diagnóstica.
#
# Aunque el sistema entrega métricas categóricas (Pre/Circa/Post-PHV, estado
# nutricional cualitativo), el LLM puede reintroducir comparaciones del tipo
# "por encima del promedio para su edad" o "en el percentil 75 de peso". Bajo
# el Código de Infancia y Adolescencia (Ley 1098/2006 Art. 27) solo personal
# de salud autorizado puede emitir afirmaciones diagnósticas o comparativas
# poblacionales sobre menores. Por eso aplicamos estas reglas GLOBALMENTE
# (cualquier use case que escriba a padres) y no solo en record_analysis.
#
# Diseño del regex `_COMPARATIVE_NORM_PATTERN`:
#   - Cubrimos las construcciones más comunes que sirven de bypass a la
#     restricción: "por encima/debajo del promedio", "sobre/bajo la media",
#     "más alto/bajo que la mayoría/otros niños/etc", "en el percentil N",
#     "comparado con otros niños", "respecto a la norma poblacional".
#   - Aceptamos opcionalmente "para su edad" como sufijo (común en los textos
#     a redactar) sin exigirlo, para no perder el match cuando el LLM lo omite.
#   - Limitamos la frase con un terminador de puntuación o fin de línea para
#     evitar tragarnos contexto útil cuando coincide con un fragmento corto.
#   - No exigimos vocabulario clínico previo (a diferencia de daily_training)
#     porque la propia frase comparativa es la violación.
#
# Falsos positivos conscientemente evitados: frases como "estuvo por encima
# del nivel del mar" no contienen "promedio|media|percentil|norma|mayoría|
# otros niños", por lo que no disparan.
_COMPARATIVE_NORM_PATTERN = re.compile(
    r"("
    # Variante A: "por encima/debajo de(l|la|...) ... promedio|media|esperado"
    # Aceptamos artículos opcionales (el|la|los|las|lo) además del contraído
    # "del", para cubrir construcciones como "sobre la media" o "bajo el
    # promedio".
    r"(?:muy\s+|bastante\s+|ligeramente\s+)?"
    r"(?:por\s+(?:encima|debajo)|sobre|bajo|encima|debajo|fuera)"
    r"(?:\s+(?:del?|de\s+(?:el|la|los|las|lo)|el|la|los|las|lo))?\s+"
    r"(?:promedio|media|norma(?:l)?(?:\s+poblacional)?|esperado)"
    r"(?:\s+para\s+su\s+edad)?"
    r"|"
    # Variante B: "más/menos {adj} que la mayoría|otros niños|sus pares"
    r"(?:m[aá]s|menos)\s+\w+\s+que\s+"
    r"(?:la\s+mayor[ií]a|otros\s+ni[ñn]os|sus\s+pares|el\s+promedio|la\s+media)"
    r"|"
    # Variante C: "en el percentil N" (con o sin número específico)
    r"en\s+el\s+percentil(?:\s+\d{1,3})?"
    r"|"
    # Variante D: "comparado con otros niños|el promedio|sus pares|la norma"
    r"comparado\s+con\s+"
    r"(?:otros\s+ni[ñn]os|el\s+promedio|sus\s+pares|la\s+norma|la\s+media|la\s+poblaci[óo]n)"
    r"|"
    # Variante E: "respecto a la norma poblacional|al promedio"
    r"respecto\s+a\s+(?:la\s+norma(?:\s+poblacional)?|el\s+promedio|la\s+media)"
    r")"
    # Permitimos un sufijo corto opcional ("...de peso", "...de talla") para
    # tragarnos también la coletilla aclaratoria si la hay.
    r"(?:\s+(?:de|en)\s+(?:peso|talla|estatura|altura|IMC))?",
    re.IGNORECASE,
)


# Reglas anti-métricas clínicas numéricas inventadas.
#
# El LLM puede inventar valores numéricos clínicos pese a que la allowlist del
# context_builder no entrega esos campos. Detectamos términos clínicos
# (IMC, z-score, percentil) seguidos de un número en una ventana corta.
#
# Patrón explicado:
#   - `\b(IMC|índice de masa corporal|z[-\s]?scores?|puntajes? z|percentiles?)\b`
#     identifica el término clínico.
#   - `[^.,;\n]{0,30}` permite hasta 30 caracteres sin separadores fuertes
#     entre el término y el número (cubre conectores como "alrededor de",
#     "cerca de", "de aproximadamente").
#   - `\d[\d.,]*` captura el número con punto o coma decimal y separadores.
#
# Reemplazo: cadena vacía. Quitamos toda la frase desde el término hasta el
# final del fragmento numérico para evitar dejar restos sin sentido.
_NUMERIC_CLINICAL_METRICS_PATTERN = re.compile(
    r"\b(?:IMC|[ií]ndice de masa corporal|z[-\s]?scores?|puntajes? z|percentiles?)\b"
    r"[^.,;\n]{0,30}\d[\d.,]*",
    re.IGNORECASE,
)


_RULES: tuple[_Rule, ...] = (
    _Rule(
        name="suplements",
        pattern=re.compile(rf"\b({_SUPPLEMENT_KEYWORDS})\b", re.IGNORECASE),
        replacement="alimentación basada en comida real",
        description="Cero suplementos para menores de 18.",
    ),
    _Rule(
        name="comparative_norm",
        pattern=_COMPARATIVE_NORM_PATTERN,
        replacement="",
        description=(
            "Comparaciones poblacionales o cuasi-diagnósticas: 'por encima "
            "del promedio para su edad', 'en el percentil 75', 'comparado "
            "con otros niños', 'respecto a la norma poblacional'. Bajo la "
            "Ley 1098/2006 Art. 27 (Colombia) solo personal de salud "
            "autorizado puede emitirlas sobre menores."
        ),
    ),
    _Rule(
        name="numeric_clinical_metrics",
        pattern=_NUMERIC_CLINICAL_METRICS_PATTERN,
        replacement="",
        description=(
            "Métricas clínicas numéricas posiblemente inventadas: 'IMC "
            "alrededor de 22', 'z-score de talla cerca de +1', 'percentil "
            "75 de peso'. El context_builder no entrega estos valores al "
            "LLM, así que cualquier número con término clínico es "
            "alucinación; lo eliminamos."
        ),
    ),
    _Rule(
        name="days_per_week_excess",
        pattern=re.compile(
            r"\b([67])\s*d[ií]as?\s*(por|a la|/)\s*semana", re.IGNORECASE
        ),
        replacement="máximo 5 días por semana",
        description="Máximo 5 días de entrenamiento por semana.",
    ),
    _Rule(
        name="daily_training",
        pattern=_DAILY_TRAINING_PATTERN,
        replacement="máximo 5 días por semana",
        description=(
            "Bypass común al límite de 5 días/semana: expresiones como "
            "'todos los días', 'diariamente', 'cada día', '7 sesiones por "
            "semana' o 'siete días semanales'. Las expresiones genéricas "
            "exigen co-ocurrencia con vocabulario de entrenamiento "
            "(entrenar/bicicleta/ciclismo/sesión/pedaleo/rodar/montar) "
            "en ±40 caracteres para evitar falsos positivos en frases "
            "legítimas no deportivas."
        ),
    ),
    _Rule(
        name="low_cadence",
        pattern=re.compile(
            r"\b([1-5]?\d)\s*rpm\b", re.IGNORECASE
        ),
        replacement="≥60 rpm",
        description="Cadencia mínima 60 rpm.",
    ),
    _Rule(
        name="calorie_counting_with_athlete",
        pattern=re.compile(
            r"\b(cont(ar|eo)|registr[ao]) (de )?calor[ií]as?\b", re.IGNORECASE
        ),
        replacement="enfoque en variedad y calidad de la comida",
        description="Sin conteo calórico con atletas menores.",
    ),
)

# Patrones que ameritan reemplazo solo en texto dirigido a 10-12.
_AGE_DEPENDENT_RULES: tuple[_Rule, ...] = (
    _Rule(
        name="powermeter_under_13",
        pattern=re.compile(r"\b(potenci[óo]metro|powermeter|vatios|watt(s)?)\b", re.IGNORECASE),
        replacement="RPE (percepción de esfuerzo)",
        description="No usar potenciómetro para <13 años.",
    ),
)

# Patrones anti-diagnóstico médico: aplican al análisis particular por medición
# para evitar sugerencias clínicas implícitas (RED-S, patología, retraso puberal).
# Bajo el Código de Infancia y Adolescencia (Ley 1098/2006 Art. 27) solo personal
# de salud autorizado puede emitir diagnósticos sobre menores.
_RECORD_ANALYSIS_RULES: tuple[_Rule, ...] = (
    _Rule(
        name="diagnostic_language",
        pattern=re.compile(r"\bdiagn[óo]stic[oa]s?\b", re.IGNORECASE),
        replacement="observación",
        description="Evitar lenguaje diagnóstico sobre menores.",
    ),
    _Rule(
        name="pathology_language",
        pattern=re.compile(r"\bpatolog[ií]a(s|o|os|cas?)?\b", re.IGNORECASE),
        replacement="situación a revisar",
        description="Evitar etiqueta de patología.",
    ),
    _Rule(
        name="abnormal_language",
        pattern=re.compile(r"\banormal(idad(es)?)?\b", re.IGNORECASE),
        replacement="fuera del rango esperado",
        description="Evitar etiqueta clínica de anormalidad.",
    ),
    _Rule(
        name="reds_term",
        pattern=re.compile(
            r"\b(RED-?S|s[íi]ndrome de deficiencia energ[ée]tica( relativa)?)\b",
            re.IGNORECASE,
        ),
        replacement="",
        description="Sin etiquetas de RED-S/SDE en outputs a padres.",
    ),
    _Rule(
        name="energy_deficit",
        pattern=re.compile(
            r"\b(d[ée]ficit energ[ée]tico|desnutrici[óo]n|anemia)\b",
            re.IGNORECASE,
        ),
        replacement="",
        description="Sin sugerencias diagnósticas nutricionales.",
    ),
    _Rule(
        name="puberty_delay",
        pattern=re.compile(r"\bretraso pub(eral|ertal)\b", re.IGNORECASE),
        replacement="",
        description="Sin diagnóstico de retraso puberal.",
    ),
)


# ---------------------------------------------------------------------------
# Reglas race analyst v2
# ---------------------------------------------------------------------------
#
# Grupo _RACE_V2_RULES: aplicado cuando use_case="race_analyst_v2".
#
# 1. max_words_section_*: los guardrails NO verifican word count aquí —
#    esa validación la hace _enforce_v2_word_limits() (separada) porque
#    requiere parsear el markdown por secciones, no reemplazos regex.
#
# 2. forbidden_real_names: se construye dinámicamente con
#    build_race_v2_forbidden_names_rules(names). No está en este tuple
#    constante — se inyecta por instancia en Guardrails.scrub_with_report.
#
# 3. no_pseudonym_in_what_happened: la sección "Qué pasó" NUNCA debe tener
#    pseudónimos AtletaXXX (el v2 usa "la deportista" / pronombres).
#
# 4. Frases de veto duro (5 frases exactas del spec).

_NO_PSEUDONYM_IN_WHAT_HAPPENED_PATTERN = re.compile(
    r"Atleta[-\s]?\w{1,10}[-\s]?\d{1,6}",
    re.IGNORECASE,
)

_VETO_DURO_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bdebe\s+ganar\b", re.IGNORECASE),
    re.compile(r"\btiene\s+que\s+llegar\s+al\s+podio\b", re.IGNORECASE),
    re.compile(r"\bnecesita\s+m[aá]s\s+horas\b", re.IGNORECASE),
    re.compile(r"\bm[aá]s\s+intensidad\b", re.IGNORECASE),
    re.compile(r"\btrabajo\s+de\s+potencia\s+para\s+superar\s+a\b", re.IGNORECASE),
)

# Secciones v2 y sus límites en palabras (spec: 120/120/120).
_V2_SECTIONS_MAX_WORDS: dict[str, int] = {
    "qué pasó en esta válida": 120,
    "que paso en esta valida": 120,
    "recorrido hasta acá": 120,
    "recorrido hasta aca": 120,
    "hacia dónde va": 120,
    "hacia donde va": 120,
}

# Margen de tolerancia: +10% sobre el límite antes de rechazar (spec).
_V2_WORDS_TOLERANCE_FACTOR = 1.10

# ---------------------------------------------------------------------------
# Veto duro N=1 — verbos prohibidos cuando solo hay una válida en el set
# ---------------------------------------------------------------------------
#
# Se activan únicamente cuando ``Guardrails(is_first_in_season=True)``.
# Rechazo automático ante cualquier match (sin contar hacia MAX_VIOLATIONS).

_VETO_N1_VERBS: tuple[str, ...] = (
    # Solo formas verbales conjugadas (no sustantivos puros como
    # "tendencia"/"progresión"/"evolución" — la frase canónica CA-6
    # las usa NEGADAS: "no es posible establecer una tendencia de
    # progresión"). El prompt v2 prohíbe afirmarlas vía DO/DON'T.
    "evolucionó",
    "evoluciono",
    "mejoró",
    "mejoro",
    "empeoró",
    "empeoro",
    "empeora",
    "subió",
    "subio",
    "bajó",
    "ascendió",
    "ascendio",
    "descendió",
    "descendio",
    "progresó",
    "progreso",
    "regresó",
    "regreso",
    "consolidó",
    "consolido",
    "confirmó",
    "confirmo",
    "venía",
    "venia",
    "viene mostrando",
    "sigue mejorando",
    "proyecta",
    "proyectado",
    "apunta a",
    "alcanzará",
    "alcanzara",
    "debería llegar",
    "deberia llegar",
    "se perfila",
)


def _build_n1_veto_patterns() -> list[tuple[str, re.Pattern[str]]]:
    """Compila un patrón ``\\b{verb}\\b`` case-insensitive por cada verbo N=1.

    Returns:
        Lista de ``(verb, compiled_pattern)`` lista para ``check_v2_veto_n1``.
    """
    patterns: list[tuple[str, re.Pattern[str]]] = []
    for verb in _VETO_N1_VERBS:
        escaped = re.escape(verb)
        # Verbos multi-palabra no necesitan \\b en el espacio interior.
        patterns.append((verb, re.compile(rf"\b{escaped}\b", re.IGNORECASE)))
    return patterns


_N1_VETO_PATTERNS: list[tuple[str, re.Pattern[str]]] = _build_n1_veto_patterns()


def check_v2_veto_n1(text: str) -> list[str]:
    """Verifica verbos de veto duro N=1 en el texto generado.

    Solo debe llamarse cuando ``is_first_in_season=True``.

    Returns:
        Lista de verbos detectados. Vacía si el texto es conforme.
    """
    found: list[str] = []
    for verb, pattern in _N1_VETO_PATTERNS:
        if pattern.search(text):
            found.append(verb)
    return found


_RACE_V2_BASE_RULES: tuple[_Rule, ...] = (
    _Rule(
        name="no_pseudonym_what_happened",
        pattern=_NO_PSEUDONYM_IN_WHAT_HAPPENED_PATTERN,
        replacement="la deportista",
        description=(
            "v2: la sección 'Qué pasó' no debe contener pseudónimos "
            "del tipo AtletaXXX-NNN. Reemplazar por 'la deportista'."
        ),
    ),
)


def build_race_v2_forbidden_names_rules(names: list[str]) -> tuple[_Rule, ...]:
    """Construye reglas dinámicas de nombres prohibidos para v2.

    Se llama una vez por análisis con la lista de nombres reales del atleta
    (full_name, nickname, padres) cargada desde DB por el nodo analyst_agent.
    Cada nombre genera una _Rule que lo reemplaza por 'la deportista'.

    Args:
        names: lista de nombres reales a prohibir (case-insensitive).

    Returns:
        Tuple de ``_Rule`` lista para añadir a un ``Guardrails`` de use_case
        ``"race_analyst_v2"``.
    """
    rules: list[_Rule] = []
    for name in names:
        name = name.strip()
        if not name:
            continue
        # Escapar caracteres especiales de regex para nombres con puntuación.
        escaped = re.escape(name)
        rules.append(
            _Rule(
                name=f"forbidden_name_{escaped[:20]}",
                pattern=re.compile(rf"\b{escaped}\b", re.IGNORECASE),
                replacement="la deportista",
                description=(
                    f"v2: nombre real prohibido detectado en output LLM. "
                    f"Privacidad Ley 1581 Art. 3 (Colombia)."
                ),
            )
        )
    return tuple(rules)


# ---------------------------------------------------------------------------
# Veto de fabricación de condiciones de carrera (feature 011)
# ---------------------------------------------------------------------------
#
# Se activa SOLO cuando ``use_case="race_analyst_v2"`` y la válida analizada NO
# tiene condiciones registradas (``has_recorded_conditions=False``). En ese caso
# el modelo NO debe mencionar clima/pista/terreno: el prompt ya lo prohíbe, y
# este guardrail es la defensa determinista. Términos detectados → se marcan
# como violation ``conditions_fabricated`` y se eliminan del texto.

_RACE_CONDITIONS_TERMS_PATTERN = re.compile(
    r"("
    r"\bclim\w*|\bclimátic\w*|"
    r"\bsolead\w*|\bnublad\w*|\bdespejad\w*|"
    r"\blluvi\w*|\bllov\w*|\bgaruga?\w*|"
    r"\bterreno\s+\w+|"
    r"\bpista\s+(?:seca|h[úu]meda|mojada|mixta|embarrada|resbaladiza|polvorienta)|"
    r"\bsuperficie\s+(?:seca|h[úu]meda|mojada|mixta|embarrada)|"
    r"\bbarro\b|\blodo\b|\bpolvo\b|"
    r"\b\d{1,2}\s*°\s*c\b|\b\d{1,2}\s*grados\b|"
    r"\baltitud\b|\bmsnm\b|"
    r"\bviento\w*|"
    r"\bcalor\b|\bcaluros\w*|\bfr[íi]o\b|\btemperatur\w*"
    r")",
    re.IGNORECASE,
)


def check_conditions_fabrication(text: str) -> list[str]:
    """Detecta menciones de clima/pista/terreno cuando NO hay condiciones.

    Solo debe llamarse cuando la válida no tiene condiciones registradas.

    Returns:
        Lista de términos detectados (uno por match). Vacía si el texto es
        conforme (no inventa condiciones).
    """
    return [m.group(0) for m in _RACE_CONDITIONS_TERMS_PATTERN.finditer(text)]


def check_v2_veto_duro(text: str) -> list[str]:
    """Verifica las 5 frases de veto duro del spec v2.

    Returns:
        Lista de nombres de frases vetadas encontradas. Vacía si OK.
    """
    found: list[str] = []
    names = [
        "debe_ganar",
        "tiene_que_llegar_al_podio",
        "necesita_mas_horas",
        "mas_intensidad",
        "trabajo_de_potencia_para_superar_a",
    ]
    for pattern, name in zip(_VETO_DURO_PATTERNS, names):
        if pattern.search(text):
            found.append(name)
    return found


def check_v2_section_word_limits(markdown: str) -> list[str]:
    """Verifica que cada sección v2 no exceda su límite de palabras (+10%).

    Parsea headings ``## ...`` para delimitar secciones. Solo verifica las
    secciones conocidas en ``_V2_SECTIONS_MAX_WORDS``.

    Returns:
        Lista de nombres de secciones que exceden el límite. Vacía si OK.
    """
    violations: list[str] = []
    current_key: str | None = None
    buf: list[str] = []

    def _check_buf(key: str, lines: list[str]) -> None:
        body = "\n".join(lines).strip()
        word_count = len([w for w in re.split(r"\s+", body) if w])
        limit = _V2_SECTIONS_MAX_WORDS.get(key, 999)
        if word_count > int(limit * _V2_WORDS_TOLERANCE_FACTOR):
            violations.append(key)

    for line in markdown.splitlines():
        m = re.match(r"^##\s+(?P<title>.+?)\s*$", line)
        if m:
            if current_key is not None:
                _check_buf(current_key, buf)
            title_lower = m.group("title").lower().strip()
            # Normalizar acentos para match flexible.
            import unicodedata
            normalized = "".join(
                c for c in unicodedata.normalize("NFD", title_lower)
                if unicodedata.category(c) != "Mn"
            )
            current_key = next(
                (k for k in _V2_SECTIONS_MAX_WORDS if normalized in k or k in normalized),
                None,
            )
            buf = []
        else:
            if current_key is not None:
                buf.append(line)

    if current_key is not None:
        _check_buf(current_key, buf)

    return violations


@dataclass(frozen=True)
class GuardrailReport:
    """Resultado del scrub para que el caller pueda auditar."""

    text: str
    violations: tuple[str, ...]
    rejected: bool


_AGE_MENTION_PATTERN = re.compile(
    r"\b(?:tiene\s+|de\s+)(\d{1,2})\s*años\b",
    re.IGNORECASE,
)

# Tolerancia en años para la comprobación de edad: si la diferencia entre
# la edad mencionada y la real supera este umbral se marca violation.
_AGE_MISMATCH_TOLERANCE = 0.6


class Guardrails:
    """Sanea texto generado por el LLM.

    Args:
        age_group: Grupo de edad del destinatario (`"10-12"` activa reglas
            extra como bloqueo de potenciómetro).
        use_case: Identificador del use case. Cuando vale
            `"anthropometric_record_analysis"` se aplican reglas anti-diagnóstico
            además de las globales. Cuando vale `"race_analyst_v2"` se aplican
            las reglas RACE_V2_BASE y las de nombres prohibidos.
        forbidden_names: Lista de nombres reales a prohibir. Solo se usa
            cuando ``use_case="race_analyst_v2"``. Se construyen como reglas
            regex dinámicas via :func:`build_race_v2_forbidden_names_rules`.
        is_first_in_season: True si el atleta tiene exactamente 1 válida con
            participación real en toda la temporada (no solo en el set lanzado).
            Cuando vale ``True`` y ``use_case="race_analyst_v2"``, activa el
            veto duro N=1 que rechaza automáticamente si aparece cualquier
            verbo de tendencia/progresión. No aplica a resúmenes de temporada.
        athlete_age: Edad real del atleta en años enteros. Solo aplica en
            ``use_case="race_analyst_v2"``. Si el LLM menciona una edad numérica
            con `|mencionada - athlete_age| > 0.6`, se registra violation
            ``age_mismatch`` y el output se rechaza (force reject).
    """

    def __init__(
        self,
        *,
        age_group: str | None = None,
        use_case: str | None = None,
        forbidden_names: list[str] | None = None,
        is_first_in_season: bool = False,
        athlete_age: int | None = None,
        has_recorded_conditions: bool = True,
    ) -> None:
        self._age_group = age_group
        self._use_case = use_case
        self._forbidden_names: list[str] = forbidden_names or []
        self._is_first_in_season = is_first_in_season
        self._athlete_age = athlete_age
        # Feature 011: cuando la válida NO tiene condiciones registradas,
        # activamos el veto determinista anti-fabricación de clima/pista. Default
        # True → no escanea (retrocompat con season_summary y otros use cases).
        self._has_recorded_conditions = has_recorded_conditions

    def scrub(self, text: str) -> str:
        """Devuelve `text` saneado. Si hubo demasiadas violaciones, lanza."""
        report = self.scrub_with_report(text)
        if report.rejected:
            from app.services.ai.errors import LLMSchemaError

            raise LLMSchemaError(
                f"Respuesta rechazada por guardrails: {report.violations}"
            )
        return report.text

    def scrub_with_report(self, text: str) -> GuardrailReport:
        sanitized = text
        violations: list[str] = []

        rules = list(_RULES)
        if self._age_group == "10-12":
            rules.extend(_AGE_DEPENDENT_RULES)
        if self._use_case == "anthropometric_record_analysis":
            rules.extend(_RECORD_ANALYSIS_RULES)

        if self._use_case == "race_analyst_v2":
            rules.extend(_RACE_V2_BASE_RULES)
            if self._forbidden_names:
                rules.extend(build_race_v2_forbidden_names_rules(self._forbidden_names))

        for rule in rules:
            new_text, count = rule.pattern.subn(
                rule.replacement or "", sanitized
            )
            if count:
                violations.extend([rule.name] * count)
                logger.warning(
                    "ai.guardrail.violation rule=%s count=%d", rule.name, count
                )
                sanitized = new_text

        # --- Verificaciones extra para v2 (no regex-replace, sino validación) ---
        has_age_mismatch = False
        if self._use_case == "race_analyst_v2":
            # Veto duro: frases explícitamente prohibidas por el Head Coach.
            veto_hits = check_v2_veto_duro(sanitized)
            if veto_hits:
                for v in veto_hits:
                    violations.append(f"veto_duro_{v}")
                    logger.warning("ai.guardrail.veto_duro phrase=%s", v)

            # Veto duro N=1: verbos de tendencia/progresión prohibidos cuando
            # el atleta tiene una sola válida en toda la temporada.
            if self._is_first_in_season:
                n1_hits = check_v2_veto_n1(sanitized)
                if n1_hits:
                    for v in n1_hits:
                        violations.append(f"veto_n1_{v}")
                        logger.warning("ai.guardrail.veto_n1 verb=%s", v)

            # Veto fabricación de condiciones: si la válida no tiene condiciones
            # registradas y el modelo menciona clima/pista/terreno, lo marcamos
            # y eliminamos el término (defensa determinista del FR-003).
            if not self._has_recorded_conditions:
                cond_hits = check_conditions_fabrication(sanitized)
                if cond_hits:
                    for _ in cond_hits:
                        violations.append("conditions_fabricated")
                    logger.warning(
                        "ai.guardrail.conditions_fabricated count=%d", len(cond_hits)
                    )
                    sanitized = _RACE_CONDITIONS_TERMS_PATTERN.sub("", sanitized)

            # Word limits por sección (+10% tolerancia).
            section_violations = check_v2_section_word_limits(sanitized)
            for sv in section_violations:
                violations.append(f"word_limit_{sv[:30]}")
                logger.warning("ai.guardrail.word_limit section=%s", sv)

            # Guardrail edad (Head Coach regla 1): si el LLM menciona una edad
            # numérica que difiere >0.6 años de la real → force reject.
            if self._athlete_age is not None:
                age_mentions = _AGE_MENTION_PATTERN.findall(sanitized)
                for mention in age_mentions:
                    try:
                        mentioned_age = int(mention)
                    except (ValueError, TypeError):
                        continue
                    if abs(mentioned_age - self._athlete_age) > _AGE_MISMATCH_TOLERANCE:
                        violations.append("age_mismatch")
                        has_age_mismatch = True
                        logger.warning(
                            "ai.guardrail.age_mismatch mentioned=%d real=%d",
                            mentioned_age,
                            self._athlete_age,
                        )

        has_n1_veto = any(v.startswith("veto_n1_") for v in violations)
        rejected = (
            len(violations) >= MAX_VIOLATIONS_BEFORE_REJECT
            or has_n1_veto
            or has_age_mismatch
        )
        return GuardrailReport(
            text=sanitized.strip(),
            violations=tuple(violations),
            rejected=rejected,
        )
