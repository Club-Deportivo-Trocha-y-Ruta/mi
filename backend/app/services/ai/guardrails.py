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


@dataclass(frozen=True)
class GuardrailReport:
    """Resultado del scrub para que el caller pueda auditar."""

    text: str
    violations: tuple[str, ...]
    rejected: bool


class Guardrails:
    """Sanea texto generado por el LLM.

    Args:
        age_group: Grupo de edad del destinatario (`"10-12"` activa reglas
            extra como bloqueo de potenciómetro).
        use_case: Identificador del use case. Cuando vale
            `"anthropometric_record_analysis"` se aplican reglas anti-diagnóstico
            además de las globales.
    """

    def __init__(
        self,
        *,
        age_group: str | None = None,
        use_case: str | None = None,
    ) -> None:
        self._age_group = age_group
        self._use_case = use_case

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

        rejected = len(violations) >= MAX_VIOLATIONS_BEFORE_REJECT
        return GuardrailReport(
            text=sanitized.strip(),
            violations=tuple(violations),
            rejected=rejected,
        )
