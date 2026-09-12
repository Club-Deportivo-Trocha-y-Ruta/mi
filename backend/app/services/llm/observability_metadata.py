"""Allow-list cerrado de metadata de trazas Langfuse + máscara del cliente.

**Por qué esta lista es tan corta y no "solo un poco más larga"**

Para un club de ~20 menores, ``sex × age_group`` ya da un tamaño medio de
clase de equivalencia de 5 — el umbral que el propio código ya trata como
inseguro (``monthly_report.py::MIN_ATHLETES_FOR_INDIVIDUAL_ROWS = 5``).
Sumar ``maturation_status`` baja ese tamaño medio de celda por debajo de 2.
**Ningún esquema de redondeo o bucketing rescata** ``sex``, ``age_group``,
``maturation_status``, ``category``, ``phv_offset``/``age_at_phv``/
``months_from_phv``, ``growth_velocity_cm_per_year`` ni ninguna magnitud de
delta como metadata o tag combinable a esta escala de club — la única
mitigación que funciona a nivel de campo es la exclusión total. Por eso
``ALLOWED_METADATA_KEYS`` tiene tantos campos ausentes que una primera
lectura del spec ("edad → bucket de 2 años", "deltas → redondeados") podría
sugerir que sí caben: la auditoría de privacidad de la feature 042 anula
explícitamente esa lectura literal (``contracts/trace-metadata-allowlist.md``
§0 y §2).

**NO agregues una clave nueva a ``ALLOWED_METADATA_KEYS`` sin releer ese
contrato completo** — en particular su regla de combinación (§2.1): incluso
si algún día se decide permitir uno de ``sex``/``age_group``/
``maturation_status``/``category`` de forma aislada, nunca deben viajar dos
de ellos en la misma llamada (la aritmética de tamaño de club de arriba no
cambia). ``StructuralMetadata`` aplica esa regla de forma independiente del
allow-list (``_QUASI_IDENTIFIER_KEYS`` más abajo) precisamente para que un
PR bien intencionado que "active" un segundo campo no la viole en silencio.

**El mask — tipo sentinela, no una heurística de forma**

El callback ``mask()`` de Langfuse (protocolo ``MaskFunction``) recibe
``data: Any`` sin decir qué campo (``input``/``output``/``metadata``) está
enmascarando. Una heurística por forma ("si es un dict, se deja pasar") es
insegura: el ``content`` de un mensaje LangChain puede ser ``list[dict]``
para input multimodal, así que un ``isinstance(data, dict)`` desenmascararía
parte de un prompt real. La solución es un tipo sentinela construido SOLO a
través de un constructor que valida — la decisión de allow-list ocurre al
construir el objeto, no al enmascararlo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

# Campos operacionales (modelo/costo/reglas/veredictos) y los identificadores
# ya transformados (hash con clave, nunca el id crudo) que sobreviven al
# mask cuando LANGFUSE_STRUCTURAL_METADATA=true. Exactamente las filas "yes"
# y "transformed" (bajo su nombre de clave YA transformado/bucketizado) de
# `contracts/trace-metadata-allowlist.md` §2 — ninguna fila "no" entra aquí
# bajo ningún alias.
ALLOWED_METADATA_KEYS: frozenset[str] = frozenset(
    {
        # Identificadores — SOLO transformados (HMAC con clave, nunca el id
        # crudo); ver keyed_session_id/athlete_id_hash en observability.py.
        "athlete_id_hash",
        "record_id_hash",
        "user_id_hash",
        "club_id",  # despliegue mono-club: no aporta entropía extra.
        # Señales booleanas sin magnitud.
        "delta_height_significant",
        "delta_weight_significant",
        # Bucketizados — el corte de bucket ya tiene significado de código
        # (MIN_WEEKS_FOR_VELOCITY / VELOCITY_RELIABLE_WEEKS).
        "weeks_since_prev_measurement_bucket",
        "num_previous_measurements_bucket",
        # Comportamiento del pipeline/LLM, no datos del atleta.
        "guardrail_rule_ids",
        "guardrail_scrub_count",
        "precheck_rule_ids",
        "precheck_violation_count",
        "critic_verdict",
        "cache_outcome",
        "use_case",
        "model",
        "provider",
        "prompt_version",
        "role",
        "tokens_in",
        "tokens_out",
        "tokens_total",
        "latency_ms",
        "cost_usd",
    }
)

# Cuasi-identificadores que, combinados de a dos o más, bajan el tamaño de
# clase de equivalencia por debajo de un k seguro en un club de este tamaño
# (ver docstring del módulo). Hoy los cuatro son "no" en ALLOWED_METADATA_KEYS
# — esta lista es una regla de combinación INDEPENDIENTE del allow-list,
# para que quede activa incluso si algún día uno de ellos se agrega al
# allow-list de forma aislada (contracts/trace-metadata-allowlist.md §2.1).
_QUASI_IDENTIFIER_KEYS: frozenset[str] = frozenset(
    {"sex", "age_group", "maturation_status", "category"}
)


@dataclass(frozen=True)
class StructuralMetadata:
    """Envoltorio marcador. Solo lo construido vía este constructor sobrevive
    al mask. Cualquier clave fuera de ``ALLOWED_METADATA_KEYS`` se rechaza al
    construir, no solo al exportar, para que una clave mal escrita nunca
    llegue a Langfuse aunque un call site olvide pasar por
    ``build_structural_metadata()``.
    """

    _data: Mapping[str, Any]

    def __init__(self, **fields: Any) -> None:
        unknown = set(fields) - ALLOWED_METADATA_KEYS
        if unknown:
            raise ValueError(f"Claves de metadata fuera del allow-list: {sorted(unknown)}")
        quasi_present = set(fields) & _QUASI_IDENTIFIER_KEYS
        if len(quasi_present) > 1:
            raise ValueError(
                "No pueden viajar dos o más cuasi-identificadores en la misma "
                f"llamada: {sorted(quasi_present)} (regla de combinación §2.1)"
            )
        object.__setattr__(self, "_data", dict(fields))

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)


def build_structural_metadata(**fields: Any) -> StructuralMetadata | None:
    """Único punto de entrada para adjuntar metadata a una observación Langfuse.

    Devuelve ``None`` (es decir, no adjuntar nada) cuando
    ``settings.langfuse_structural_metadata`` es falso — los call sites NUNCA
    deben ramificar sobre el flag ellos mismos, solo llamar esta función y
    pasar el resultado como ``metadata=`` (o nada, si es ``None``).
    """
    from app.config import settings

    if not settings.langfuse_structural_metadata:
        return None
    return StructuralMetadata(**fields)


def build_mask(sentinel: str) -> Callable[..., Any]:
    """Fábrica del callback ``mask()`` del cliente Langfuse.

    Cuatro reglas, no negociables (``contracts/trace-metadata-allowlist.md``
    §1):

    1. ``input``/``output`` se redactan SIEMPRE, sin importar
       ``LANGFUSE_STRUCTURAL_METADATA`` — nunca se envuelven en
       ``StructuralMetadata``, ese tipo existe solo para el canal ``metadata``.
    2. Una clave fuera de ``ALLOWED_METADATA_KEYS`` se rechaza en
       ``StructuralMetadata.__init__`` (falla ruidoso, no se descarta en
       silencio — a diferencia de los allow-lists del context builder, que sí
       descartan: una clave de prompt descartada degrada una generación, una
       clave de traza descartada-y-olvidada es una falsa sensación de
       seguridad sobre qué salió del proceso).
    3. Con el flag apagado (default, y el único valor legal en producción),
       ``build_structural_metadata()`` devuelve ``None`` y el argumento
       ``metadata`` de cada observación simplemente se omite — equivalente
       byte a byte al comportamiento redact-always de hoy.
    4. Un dict pelado — incluido cualquier ``metadata`` que el
       ``CallbackHandler`` de LangChain auto-popule (tags de corrida, índice
       de paso) — cae siempre a ``sentinel``: el default sigue siendo
       máximamente estricto, solo escapa de él la metadata explícita,
       envuelta y allow-listada.
    """

    def _mask(*, data: Any, **kwargs: Any) -> Any:
        if data is None:
            return None
        if isinstance(data, StructuralMetadata):
            return data.as_dict()
        return sentinel

    return _mask
