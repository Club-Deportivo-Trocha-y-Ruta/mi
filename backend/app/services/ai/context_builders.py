"""Builders de contexto para los prompts.

Función pura: recibe instancias de SQLAlchemy y devuelve un dict con
**allowlist explícita** de claves seguras. Nada que pueda identificar al
menor sale de aquí: ni nombre, ni apellido, ni fecha de nacimiento exacta,
ni email, ni id.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from app.services.category import compute_age_decimal, get_category
from app.services.measurement_alerts import DEFAULT_INTERVAL, MEASUREMENT_INTERVALS

if TYPE_CHECKING:
    from app.models.anthropometry import AnthropometricRecord
    from app.models.athlete import Athlete


# Umbrales para distinguir señal de ruido en deltas (Mirwald, error de medición).
# Por debajo de estos valores el cambio es indistinguible del error instrumental.
DELTA_HEIGHT_SIGNIFICANT_CM = 0.7
DELTA_WEIGHT_SIGNIFICANT_KG = 1.5
# Mínimo de semanas entre mediciones para calcular velocidad de crecimiento confiable.
MIN_WEEKS_FOR_VELOCITY = 8

# --- Feature 042 (traceable-growth-ai) ---------------------------------------
# Umbral de semanas a partir del cual una velocidad ya computada (>= 8 semanas,
# MIN_WEEKS_FOR_VELOCITY arriba, sin cambios) se etiqueta "reliable" en vez de
# "early_signal". El piso de cómputo NO cambia — solo la etiqueta de confianza
# que acompaña al mismo número (FR-004, contracts/analysis-context.md §1).
# Precedente de monitoreo clínico documentado en docs/01-marco-teorico.md §1.
VELOCITY_RELIABLE_WEEKS = 26

# Por encima de este número de mediciones, las más antiguas se compactan en
# checkpoints anuales en vez de descartarse (Edge Case spec.md:126). Es una
# válvula de presupuesto de tokens, no un recorte de alcance: la historia
# completa sigue representada, solo que agregada más allá de este punto.
HISTORY_MAX_POINTS = 16

# Máximo permitido para `training_implications` antes de inyectarlo al ctx.
# Si excede, truncamos con elipsis para limitar superficie de PII libre escrita
# por el coach.
TRAINING_IMPLICATIONS_MAX_CHARS = 300


# Patrones anti-diagnóstico para sanitizar `training_implications` antes de
# pasarlo al LLM. Replican (con replacement vacío para simplificar) las reglas
# `_RECORD_ANALYSIS_RULES` de `guardrails.py`. Se duplican aquí porque el
# guardrail opera sobre el OUTPUT del LLM, mientras que aquí hay que sanitizar
# el INPUT (texto libre escrito por el coach en la BD). Si los patrones de
# `guardrails.py` cambian, actualizar también esta lista.
_TRAINING_IMPLICATIONS_DIAGNOSTIC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bdiagn[óo]stic[oa]s?\b", re.IGNORECASE),
    re.compile(r"\bpatolog[ií]a(s|o|os|cas?)?\b", re.IGNORECASE),
    re.compile(r"\banormal(idad(es)?)?\b", re.IGNORECASE),
    re.compile(
        r"\b(RED-?S|s[íi]ndrome de deficiencia energ[ée]tica( relativa)?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(d[ée]ficit energ[ée]tico|desnutrici[óo]n|anemia)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bretraso pub(eral|ertal)\b", re.IGNORECASE),
)

# Patrón conservador para detectar nombres propios en español: dos palabras
# consecutivas que empiezan con mayúscula y tienen al menos 3 letras. Usa
# letras latinas con acentos (À-ſ). Conscientemente conservador:
# prefiere falsos positivos a fugas de nombres ("Recordar Trabajar" se
# eliminaría, pero el operador no escribe así en notas clínicas).
_NAME_LIKE_PATTERN = re.compile(
    r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñÀ-ſ]{2,}"
    r"\s+"
    r"[A-ZÁÉÍÓÚÑ][a-záéíóúñÀ-ſ]{2,}\b"
)


def _sanitize_training_implications(text: str | None) -> str | None:
    """Sanea texto libre del coach antes de inyectarlo al LLM.

    Pasos (en orden):
      1. Si es ``None`` o queda vacío tras strip, devuelve ``None``.
      2. Elimina secuencias que parezcan nombres propios (regex conservadora).
      3. Aplica patrones anti-diagnóstico (replacement vacío).
      4. Trunca a ``TRAINING_IMPLICATIONS_MAX_CHARS`` caracteres con elipsis.
      5. Si tras todo lo anterior queda vacío o solo whitespace, devuelve
         ``None`` para que el caller pueda omitir la clave del contexto.
    """
    if text is None:
        return None
    cleaned = text.strip()
    if not cleaned:
        return None

    # Eliminar nombres propios antes que los patrones diagnósticos para no
    # dejar restos parciales si un nombre aparecía junto a un término clínico.
    cleaned = _NAME_LIKE_PATTERN.sub("", cleaned)

    for pattern in _TRAINING_IMPLICATIONS_DIAGNOSTIC_PATTERNS:
        cleaned = pattern.sub("", cleaned)

    # Normalizar whitespace que pueda haber quedado tras las sustituciones.
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

    # Si solo quedó puntuación residual (".", ",", "—", etc.) tras eliminar
    # nombres y términos clínicos, consideramos el contenido vacío. Sin esto
    # quedarían restos sin significado como "." que solo confunden al LLM.
    if not cleaned or not re.search(r"\w", cleaned):
        return None

    if len(cleaned) > TRAINING_IMPLICATIONS_MAX_CHARS:
        cleaned = cleaned[:TRAINING_IMPLICATIONS_MAX_CHARS].rstrip() + "…"

    return cleaned


# Claves permitidas en el contexto que se entrega al LLM.
# Cualquier clave fuera de esta lista es un bug de privacidad.
ATHLETE_CONTEXT_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "age_decimal",
        "age_group",          # "10-12" | "13-15" | "16+"
        "sex",                # "M" | "F"
        "category",           # categoría FCC
        "phv_offset",
        "age_at_phv",
        "months_from_phv",     # |phv_offset| en meses, entero (feature 040, coach)
        "maturation_status",  # "Pre-PHV" | "Circa-PHV" | "Post-PHV"
        # Privacidad: z-scores eliminados a propósito de la allowlist. En bases
        # pequeñas un par (z-altura, z-peso, edad, sexo) puede re-identificar al
        # menor. La plantilla `phv_explainer.j2` v2 ya no los renderiza; al
        # excluirlos también de la allowlist y de `build()` garantizamos que
        # nunca lleguen al LLM aunque un template futuro intente referenciarlos.
        "nutritional_status",
        "evaluation_age_decimal",
        "trend",              # dict con deltas de últimas mediciones
        "training_implications",
        "arm_span_cm",
        # Análisis particular por medición:
        "delta_height_cm",
        "delta_weight_kg",
        "delta_height_significant",
        "delta_weight_significant",
        "growth_velocity_cm_per_year",
        "weeks_since_prev_measurement",
        "num_previous_measurements",
        "crossed_phv_phase",
        "prev_maturation_status",
    }
)


@dataclass(frozen=True)
class TrendPoint:
    """Delta entre dos mediciones consecutivas (sin fechas exactas)."""

    weeks_ago: int
    delta_height_cm: float
    delta_weight_kg: float


def _to_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _age_group(age_decimal: float) -> str:
    if age_decimal < 13:
        return "10-12"
    if age_decimal < 16:
        return "13-15"
    return "16+"


def _build_trend(records: list["AnthropometricRecord"]) -> list[dict] | None:
    """Tendencia derivada de las últimas 3 mediciones (más reciente primero).

    Devuelve solo deltas y semanas relativas; nunca fechas absolutas.
    """
    if len(records) < 2:
        return None
    sorted_records = sorted(records, key=lambda r: r.evaluation_date, reverse=True)
    selected = sorted_records[:3]
    out: list[dict] = []
    for current, previous in zip(selected, selected[1:]):
        weeks = max(
            int((current.evaluation_date - previous.evaluation_date).days / 7), 0
        )
        out.append(
            {
                "weeks_ago": weeks,
                "delta_height_cm": round(
                    float(current.standing_height_cm - previous.standing_height_cm), 1
                ),
                "delta_weight_kg": round(
                    float(current.weight_kg - previous.weight_kg), 1
                ),
            }
        )
    return out


def _maturation_value(record: "AnthropometricRecord") -> str:
    status = record.maturation_status
    return status.value if hasattr(status, "value") else str(status)


def age_group_for(age_decimal: float) -> str:
    """Envoltorio público de :func:`_age_group` (feature 042, `anthro/context.py`).

    Mismo cómputo que usa `AthleteAIContextBuilder`; se expone con nombre
    público porque un módulo fuera de esta clase (el pipeline antropométrico)
    también necesita el bucket de edad sin duplicar la regla de corte.
    """
    return _age_group(age_decimal)


# ---------------------------------------------------------------------------
# Feature 042 (traceable-growth-ai): helpers del pipeline antropométrico
# ---------------------------------------------------------------------------
#
# Estas funciones alimentan `app/services/ai/anthro/context.py` (T028, paso 1
# del pipeline). Viven aquí, junto a `ATHLETE_CONTEXT_ALLOWED_KEYS` y sus
# umbrales hermanos, por la misma razón que el resto del archivo: son la
# única vía aprobada por la que datos derivados del atleta llegan a un
# prompt, así que su lógica de privacidad debe revisarse en un solo lugar.


def velocity_confidence(weeks_between: int | None) -> str | None:
    """Etiqueta de confianza para una velocidad de crecimiento ya computada.

    FR-004: el PISO de cómputo (8 semanas, `MIN_WEEKS_FOR_VELOCITY`) no
    cambia — por debajo de él no existe ninguna cifra de velocidad, y esta
    función refleja eso devolviendo `None`. Entre 8 y 26 semanas la cifra
    existe pero es apenas una señal temprana; a partir de 26 semanas
    (`VELOCITY_RELIABLE_WEEKS`) se considera confiable.

    `weeks_between=None` (sin medición previa) también retorna `None`.
    """
    if weeks_between is None or weeks_between < MIN_WEEKS_FOR_VELOCITY:
        return None
    if weeks_between >= VELOCITY_RELIABLE_WEEKS:
        return "reliable"
    return "early_signal"


def phase_crossing_corroborated(
    previous_status: str,
    previous_evaluation_date: date,
    older_status: str | None,
    older_evaluation_date: date | None,
) -> bool:
    """FR-005: ¿el cruce de fase (target vs. `previous`) está corroborado?

    Un cruce se considera confirmado solo cuando la lectura ANTERIOR a
    `previous` ("older") muestra la misma fase que `previous` (es decir, la
    fase previa era estable, no ruido de una sola lectura) Y el intervalo
    entre `older` y `previous` cubre el intervalo de re-medición de esa
    etapa (`MEASUREMENT_INTERVALS`, `app/services/measurement_alerts.py` —
    90/30/120 días según Pre/Circa/Post-PHV).

    Sin una lectura "older" disponible (menos de dos mediciones antes del
    target), el cruce NUNCA se marca como corroborado — es un dato, no un
    juicio del LLM (data-model.md §2.2).
    """
    if older_status is None or older_evaluation_date is None:
        return False
    if older_status != previous_status:
        return False
    interval_days = MEASUREMENT_INTERVALS.get(older_status, DEFAULT_INTERVAL)
    span_days = (previous_evaluation_date - older_evaluation_date).days
    return span_days >= interval_days


def _compact_into_yearly_checkpoints(
    records: list["AnthropometricRecord"], latest_date: date
) -> list[dict]:
    """Agrupa mediciones antiguas por año calendario en checkpoints sintéticos.

    Cada checkpoint promedia talla/peso del año y toma el estado de
    maduración más representado ese año (empate → el primero encontrado,
    orden estable). Nunca lleva una fecha absoluta: solo
    `weeks_offset_from_latest`, derivado de la fecha más reciente del grupo.
    """
    by_year: dict[int, list["AnthropometricRecord"]] = {}
    for record in records:
        by_year.setdefault(record.evaluation_date.year, []).append(record)

    checkpoints: list[dict] = []
    for year in sorted(by_year.keys(), reverse=True):
        year_records = by_year[year]
        avg_height = sum(float(r.standing_height_cm) for r in year_records) / len(year_records)
        avg_weight = sum(float(r.weight_kg) for r in year_records) / len(year_records)
        status_counts: dict[str, int] = {}
        for r in year_records:
            status = _maturation_value(r)
            status_counts[status] = status_counts.get(status, 0) + 1
        most_common_status = max(status_counts.items(), key=lambda kv: kv[1])[0]
        representative_date = max(r.evaluation_date for r in year_records)
        weeks_offset = max(int((latest_date - representative_date).days / 7), 0)
        checkpoints.append(
            {
                "weeks_offset_from_latest": weeks_offset,
                "height_cm": round(avg_height, 1),
                "weight_kg": round(avg_weight, 1),
                "maturation_status_at_point": most_common_status,
            }
        )
    return checkpoints


def build_longitudinal_series(
    records: list["AnthropometricRecord"],
    *,
    reference_date: date | None = None,
) -> list[dict]:
    """Serie longitudinal compactada para el pipeline antropométrico (FR-003).

    `records` es el historial completo del atleta (target incluido), en
    cualquier orden. El resultado está ordenado del punto más reciente al
    más antiguo:

    - Cada punto lleva `weeks_offset_from_latest` (jamás una fecha absoluta).
    - Nunca incluye `sitting_height_cm` ni `arm_span_cm` por punto — solo el
      `arm_span_cm` de la medición más reciente se expone, como clave aparte
      fuera de esta serie (mismo patrón de `AthleteAIContextBuilder.build`).
    - Con más de `HISTORY_MAX_POINTS` (16) registros, los 15 más recientes
      quedan punto a punto y el resto se compacta en checkpoints anuales
      (`_compact_into_yearly_checkpoints`) — nunca se descarta historia.
    - `delta_height_cm_from_prior_point` es `None` en el punto más antiguo de
      la serie (compactada o no); en el resto, es la diferencia de talla
      contra el punto cronológicamente anterior.
    """
    if not records:
        return []

    sorted_desc = sorted(records, key=lambda r: r.evaluation_date, reverse=True)
    latest_date = reference_date or sorted_desc[0].evaluation_date

    keep_per_point = HISTORY_MAX_POINTS - 1
    if len(sorted_desc) > HISTORY_MAX_POINTS:
        recent, older = sorted_desc[:keep_per_point], sorted_desc[keep_per_point:]
    else:
        recent, older = sorted_desc, []

    points: list[dict] = []
    for record in recent:
        weeks_offset = max(int((latest_date - record.evaluation_date).days / 7), 0)
        points.append(
            {
                "weeks_offset_from_latest": weeks_offset,
                "height_cm": round(float(record.standing_height_cm), 1),
                "weight_kg": round(float(record.weight_kg), 1),
                "maturation_status_at_point": _maturation_value(record),
            }
        )

    if older:
        points.extend(_compact_into_yearly_checkpoints(older, latest_date))

    for idx, point in enumerate(points):
        if idx + 1 < len(points):
            point["delta_height_cm_from_prior_point"] = round(
                point["height_cm"] - points[idx + 1]["height_cm"], 1
            )
        else:
            point["delta_height_cm_from_prior_point"] = None

    return points


# Claves permitidas en el `AnalysisContext` del pipeline antropométrico
# (feature 042, `contracts/analysis-context.md` §2). Deliberadamente
# independiente de `ATHLETE_CONTEXT_ALLOWED_KEYS`: es un frozenset CERRADO y
# propio para que una futura poda de la allowlist legada nunca angoste, sin
# querer, lo que puede ver este pipeline. Es plana (no anidada) porque valida
# claves "hoja" — se aplica por separado a cada dict hoja del
# `AnalysisContext` (identity, measurement_deltas, cada punto de
# longitudinal_series, growth_summary, training_load_window,
# previous_analysis) vía `sanitize_insight_context()`, nunca al contenedor
# completo (cuyas claves — "identity", "measurement_deltas", etc. — son
# estructurales, no datos).
ANTHROPOMETRY_INSIGHT_CONTEXT_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        # 2.1 identidad
        "age_decimal",
        "age_group",
        "sex",
        "category",
        "audience",
        "arm_span_cm",
        # 2.2 measurement_deltas
        "weeks_since_prev_measurement",
        "delta_height_cm",
        "delta_weight_kg",
        "delta_height_significant",
        "delta_weight_significant",
        "growth_velocity_cm_per_year",
        "velocity_confidence",
        "crossed_phv_phase",
        "prev_maturation_status",
        "phase_crossing_corroborated",
        # 2.3 longitudinal_series (por punto)
        "weeks_offset_from_latest",
        "height_cm",
        "weight_kg",
        "maturation_status_at_point",
        "delta_height_cm_from_prior_point",
        # 2.4 growth_summary — códigos cualitativos únicamente, nunca z-score/
        # percentil/valor crudo de banda (defensa en profundidad, §3 del
        # contrato: eso se filtra aquí incluso si algo aguas arriba lo cuela).
        "stage",
        "maturity_offset",
        "age_at_phv",
        "months_from_phv",
        "expected_velocity_range_cm_year",
        "height_band",
        "weight_band",
        "nutritional_status",
        "alerts",
        "measurement_due_status",
        # 2.5 training_load_window (28 días, tres campos solamente)
        "sessions_count_28d",
        "avg_rpe_28d",
        "hours_28d",
        # 2.6 previous_analysis (última estructurada propia, si existe)
        "insight_schema_version",
        "summary_line",
        "confidence_level",
        "weeks_since",
    }
)


def sanitize_insight_context(ctx: dict) -> dict:
    """Defensa en profundidad para el contexto del pipeline antropométrico.

    Misma lógica de recorte silencioso que `AthleteAIContextBuilder._sanitize`
    pero contra `ANTHROPOMETRY_INSIGHT_CONTEXT_ALLOWED_KEYS`. Se aplica a
    cada dict "hoja" del `AnalysisContext` — nunca al contenedor completo,
    ver la nota junto a la allowlist arriba.
    """
    return {key: value for key, value in ctx.items() if key in ANTHROPOMETRY_INSIGHT_CONTEXT_ALLOWED_KEYS}


class AthleteAIContextBuilder:
    """Construye el contexto seguro para alimentar prompts.

    No depende de la sesión DB: recibe instancias ya cargadas. Es una función
    pura, fácil de testear, y la **única** vía aprobada por la que datos del
    atleta llegan a un LLM.
    """

    def build(
        self,
        athlete: "Athlete",
        latest_record: "AnthropometricRecord | None",
        history: list["AnthropometricRecord"] | None = None,
        *,
        reference_date: date | None = None,
    ) -> dict:
        ref = reference_date or date.today()
        age_decimal = compute_age_decimal(athlete.birth_date, ref)
        ctx: dict = {
            "age_decimal": round(age_decimal, 1),
            "age_group": _age_group(age_decimal),
            "sex": athlete.sex.value,
            "category": get_category(athlete.birth_date.year, athlete.sex.value),
        }

        if latest_record is not None:
            # Privacidad: phv_offset y age_at_phv se redondean a 1 decimal
            # antes de inyectarse. La precisión a 2-3 decimales combinada con
            # (sexo, age_group) en clubes pequeños (n<10) facilita
            # re-identificación. Un decimal preserva la utilidad clínica
            # (Mirwald reporta ±1 año de error) sin entregar firmas únicas.
            phv_offset_raw = _to_float(latest_record.maturity_offset)
            age_at_phv_raw = _to_float(latest_record.age_at_phv)
            ctx.update(
                {
                    "phv_offset": (
                        round(phv_offset_raw, 1)
                        if phv_offset_raw is not None
                        else None
                    ),
                    "age_at_phv": (
                        round(age_at_phv_raw, 1)
                        if age_at_phv_raw is not None
                        else None
                    ),
                    # Magnitud en meses de `phv_offset` (feature 040, prompt
                    # para entrenador): se deriva del mismo valor crudo, así
                    # que no añade precisión nueva sobre el ya redondeado a
                    # 1 decimal en años — solo cambia la unidad de lectura.
                    # El signo (antes/después del pico) lo decide el propio
                    # template a partir de `phv_offset`.
                    "months_from_phv": (
                        round(abs(phv_offset_raw) * 12)
                        if phv_offset_raw is not None
                        else None
                    ),
                    "maturation_status": _maturation_value(latest_record),
                    "evaluation_age_decimal": round(
                        compute_age_decimal(
                            athlete.birth_date, latest_record.evaluation_date
                        ),
                        1,
                    ),
                }
            )
            # `training_implications` es texto libre escrito por el coach.
            # Se sanea (truncado + anti-diagnóstico + anti-nombre propio)
            # antes de inyectarlo. Si tras saneo queda vacío, omitimos la
            # clave para no contaminar el prompt con un string nulo.
            sanitized_implications = _sanitize_training_implications(
                latest_record.training_implications
            )
            if sanitized_implications is not None:
                ctx["training_implications"] = sanitized_implications
            # NOTA privacidad: NO se inyectan height_z_score ni weight_z_score
            # al contexto del LLM. Quedan disponibles en el modelo SQL para uso
            # interno (clasificación, reporting), pero la capa IA solo recibe
            # la categoría cualitativa `nutritional_status`.
            if latest_record.nutritional_status is not None:
                ns = latest_record.nutritional_status
                ctx["nutritional_status"] = (
                    ns.value if hasattr(ns, "value") else str(ns)
                )
            # Envergadura: dato del PROPIO atleta, útil como referencia
            # interna (relación talla/envergadura). Se inyecta solo si está
            # disponible y se redondea a 1 decimal para mantener la
            # consistencia con phv_offset/age_at_phv. Sigue dentro de la
            # allowlist (ATHLETE_CONTEXT_ALLOWED_KEYS).
            if latest_record.arm_span_cm is not None:
                arm_span_raw = _to_float(latest_record.arm_span_cm)
                if arm_span_raw is not None:
                    ctx["arm_span_cm"] = round(arm_span_raw, 1)

        if history:
            trend = _build_trend(history)
            if trend:
                ctx["trend"] = trend
                # Velocidad de crecimiento reciente (talla), derivada del
                # primer punto de la tendencia (medición más reciente vs la
                # inmediatamente anterior). Mismo umbral/fórmula que
                # `build_record_delta` (feature 040, prompt para entrenador);
                # se omite si el intervalo es demasiado corto para ser
                # confiable (ruido de medición).
                most_recent_delta = trend[0]
                weeks_ago = most_recent_delta["weeks_ago"]
                if weeks_ago >= MIN_WEEKS_FOR_VELOCITY:
                    years = weeks_ago / 52.18
                    if years > 0:
                        ctx["growth_velocity_cm_per_year"] = round(
                            most_recent_delta["delta_height_cm"] / years, 1
                        )

        return self._sanitize(ctx)

    def build_record_delta(
        self,
        athlete: "Athlete",
        target_record: "AnthropometricRecord",
        prior_records: list["AnthropometricRecord"],
        *,
        reference_date: date | None = None,
    ) -> dict:
        """Contexto para análisis particular: target vs medición inmediata anterior.

        `prior_records` son las mediciones ESTRICTAMENTE previas a `target_record`,
        en cualquier orden. Si la lista está vacía, el contexto omite los campos
        delta y la plantilla debe tomar la rama "primera medición".
        """
        ctx = self.build(athlete, target_record, history=None, reference_date=reference_date)
        ctx.pop("trend", None)

        prior_sorted = sorted(
            [r for r in prior_records if r.evaluation_date < target_record.evaluation_date],
            key=lambda r: r.evaluation_date,
            reverse=True,
        )
        ctx["num_previous_measurements"] = len(prior_sorted)

        if not prior_sorted:
            return self._sanitize(ctx)

        previous = prior_sorted[0]
        weeks = max(
            int((target_record.evaluation_date - previous.evaluation_date).days / 7),
            0,
        )
        delta_h = round(
            float(target_record.standing_height_cm - previous.standing_height_cm), 1
        )
        delta_w = round(
            float(target_record.weight_kg - previous.weight_kg), 1
        )

        ctx["weeks_since_prev_measurement"] = weeks
        ctx["delta_height_cm"] = delta_h
        ctx["delta_weight_kg"] = delta_w
        ctx["delta_height_significant"] = abs(delta_h) >= DELTA_HEIGHT_SIGNIFICANT_CM
        ctx["delta_weight_significant"] = abs(delta_w) >= DELTA_WEIGHT_SIGNIFICANT_KG

        if weeks >= MIN_WEEKS_FOR_VELOCITY:
            years = weeks / 52.18
            if years > 0:
                ctx["growth_velocity_cm_per_year"] = round(delta_h / years, 1)

        prev_status = _maturation_value(previous)
        ctx["prev_maturation_status"] = prev_status
        ctx["crossed_phv_phase"] = prev_status != ctx.get("maturation_status", "")

        return self._sanitize(ctx)

    @staticmethod
    def _sanitize(ctx: dict) -> dict:
        # Defensa en profundidad: si alguna vez se cuela una clave fuera de la
        # allowlist, recortamos en silencio (mejor que filtrar PII).
        for key in list(ctx.keys() - ATHLETE_CONTEXT_ALLOWED_KEYS):
            ctx.pop(key, None)
        return ctx
