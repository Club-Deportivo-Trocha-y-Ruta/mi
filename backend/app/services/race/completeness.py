"""Verificación de completitud de una categoría y correcciones manuales.

Feature 044 (research R-05). Los archivos oficiales **sí traen defectos**: un
puesto repetido en una categoría infantil de los dos archivos de 2025 y un
puesto faltante en otra. Por eso el reconocimiento auditado
(``AcknowledgeReasonCode``) existe: no es un caso de esquina, es el camino
normal para un acta imperfecta que igual hay que cargar.

Módulo puro: sin DB, sin I/O, sin FastAPI.

Privacidad: ``apply_corrections`` recibe filas con nombre, ciudad y club de
menores de edad. **Nada de ese contenido se loggea ni se incluye en el texto
de una excepción** — los errores llevan un código y, a lo sumo, un ordinal.

Contrato de ``check_completeness`` (``contracts/reading-integrity.md``)
----------------------------------------------------------------------
``status == "inconsistent"`` **si y solo si** el multiset de ordinales es
distinto de ``{1…N}``, con ``N`` = cantidad de filas de la categoría.

**``status`` es lo único que bloquea el commit**, y sigue esa regla literal:
cualquier desviación del multiset ``{1…N}`` — un hueco, un duplicado, un
ordinal fuera de rango — deja la categoría en ``inconsistent`` y exige
corrección o reconocimiento auditado.

``missing`` y ``duplicated`` **no son la condición de bloqueo**: son pistas
para que el entrenador sepa dónde mirar en el acta. Esa separación es la que
hace segura la heurística del tope de ``missing`` descrita abajo — aunque en
un caso raro esa lista reporte de menos, ``status`` ya marcó la categoría y
ninguna categoría defectuosa pasa por estar la pista incompleta.

- ``duplicated``: ordinales impresos más de una vez.
- ``missing``: ordinales ausentes en ``1…min(N, max(ordinales))``. El tope se
  recorta al ordinal más alto realmente impreso para no reportar como
  "faltante" la cola que un duplicado desplaza: en ``[1, 2, 2, 3, 4]`` hay 5
  filas, pero el acta llega hasta el puesto 4 y el defecto real es el
  duplicado, no un "puesto 5 faltante" que nunca existió. Con ``[5]`` (una
  sola fila numerada 5) el tope es 1 y sí se reporta el puesto 1 faltante.

Ambas listas van **ordenadas ascendentemente**. Una categoría vacía es
``ok``: ``{1..0}`` es el conjunto vacío y coincide con el multiset vacío.
"""
from __future__ import annotations

import copy
import enum
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Sequence

from app.services.race.pdf_parser import ParsedCategory, ParsedResults, ResultsRow

# ---------------------------------------------------------------------------
# Estado de completitud
# ---------------------------------------------------------------------------

#: ``acknowledged`` no lo produce ``check_completeness``: lo escribe el
#: endpoint de reconocimiento sobre un reporte previamente ``inconsistent``.
CompletenessStatus = Literal["ok", "inconsistent", "acknowledged"]


@dataclass
class CompletenessReport:
    """Resultado de verificar los ordinales impresos de una categoría."""

    status: CompletenessStatus
    missing: list[int] = field(default_factory=list)
    duplicated: list[int] = field(default_factory=list)


def check_completeness(ordinals: Sequence[int]) -> CompletenessReport:
    """Verifica que los ordinales de una categoría sean exactamente ``1…N``.

    Función pura sobre **todos** los ordinales impresos de la categoría
    (incluidos los corredores doblados, que también llevan puesto).

    ``status`` es la condición de bloqueo y se calcula con la regla literal
    del contrato; ``missing``/``duplicated`` solo orientan al entrenador. Ver
    el docstring del módulo.
    """
    total = len(ordinals)
    if total == 0:
        return CompletenessReport(status="ok")

    counts = Counter(ordinals)
    duplicated = sorted(value for value, count in counts.items() if count > 1)

    limit = max(0, min(total, max(ordinals)))
    missing = [value for value in range(1, limit + 1) if value not in counts]

    consistent = sorted(ordinals) == list(range(1, total + 1))
    return CompletenessReport(
        status="ok" if consistent else "inconsistent",
        missing=missing,
        duplicated=duplicated,
    )


# ---------------------------------------------------------------------------
# Catálogo CERRADO de motivos de reconocimiento (research R-05)
# ---------------------------------------------------------------------------


class AcknowledgeReasonCode(str, enum.Enum):
    """Motivos permitidos para dar por buena una categoría inconsistente.

    Catálogo CERRADO, siguiendo el precedente de
    ``schemas.race_imports.RevisionReasonCode``: el texto libre sobre un acta
    de menores invita a escribir nombres, y estos motivos se persisten en
    ``race_imports.parse_meta_json`` y en la bitácora de auditoría.
    """

    #: El acta oficial repite un puesto (defecto real en los dos archivos 2025).
    source_duplicate_ordinal = "source_duplicate_ordinal"
    #: El acta oficial salta un puesto.
    source_missing_ordinal = "source_missing_ordinal"
    #: El salto corresponde a una descalificación retirada del acta.
    source_disqualification_gap = "source_disqualification_gap"
    #: El coach contrastó la categoría contra el acta impresa y coincide.
    verified_against_source = "verified_against_source"


#: Etiquetas legibles (es-CO) para la UI. El backend solo persiste el code.
ACKNOWLEDGE_REASON_LABELS: dict[AcknowledgeReasonCode, str] = {
    AcknowledgeReasonCode.source_duplicate_ordinal: (
        "El acta oficial repite un puesto"
    ),
    AcknowledgeReasonCode.source_missing_ordinal: (
        "El acta oficial salta un puesto"
    ),
    AcknowledgeReasonCode.source_disqualification_gap: (
        "El salto corresponde a una descalificación"
    ),
    AcknowledgeReasonCode.verified_against_source: (
        "Verificado contra el acta oficial"
    ),
}


# ---------------------------------------------------------------------------
# Correcciones manuales
# ---------------------------------------------------------------------------

#: Operaciones admitidas en un parche de fila.
CorrectionOp = Literal["add", "edit", "remove"]

_ROW_FIELDS: tuple[str, ...] = (
    "position", "bib", "name", "city", "club", "time_raw", "points",
)


class CorrectionError(ValueError):
    """Corrección inválida. El router la traduce a ``422``.

    Lleva un ``code`` estable y, como máximo, el ordinal afectado — nunca el
    contenido de la fila.
    """

    def __init__(self, code: str, *, ordinal: int | None = None) -> None:
        self.code = code
        self.ordinal = ordinal
        super().__init__(code if ordinal is None else f"{code} (ordinal={ordinal})")


def _build_row(payload: Mapping[str, Any] | None, *, ordinal: int) -> ResultsRow:
    """Construye un ``ResultsRow`` desde el cuerpo de un parche."""
    if not isinstance(payload, Mapping):
        raise CorrectionError("malformed_row", ordinal=ordinal)

    unknown = set(payload) - set(_ROW_FIELDS)
    if unknown:
        raise CorrectionError("malformed_row", ordinal=ordinal)

    try:
        position = payload.get("position", ordinal)
        return ResultsRow(
            position=None if position is None else int(position),
            bib=str(payload.get("bib", "")),
            name=str(payload.get("name", "")),
            city=str(payload.get("city", "")),
            club=str(payload.get("club", "")),
            time_raw=str(payload.get("time_raw", "")),
            points=int(payload.get("points", 0)),
        )
    except (TypeError, ValueError) as exc:
        raise CorrectionError("malformed_row", ordinal=ordinal) from exc


def _find_category(parsed: ParsedResults, header: str) -> ParsedCategory:
    for category in parsed.categories:
        if category.header_raw == header:
            return category
    raise CorrectionError("unknown_category")


def _insert_ordered(rows: list[ResultsRow], row: ResultsRow) -> None:
    """Inserta manteniendo el orden ascendente de posición del acta."""
    if row.position is None:
        rows.append(row)
        return
    for index, existing in enumerate(rows):
        if existing.position is not None and existing.position > row.position:
            rows.insert(index, row)
            return
    rows.append(row)


def apply_corrections(
    parsed: ParsedResults, corrections: Sequence[Mapping[str, Any]]
) -> ParsedResults:
    """Aplica parches de fila sobre un parseo, en orden, y devuelve uno nuevo.

    Cada parche es ``{op, category_header, ordinal, row?}``; ``ordinal``
    identifica la fila destino por su posición **actual** (``edit``/``remove``)
    o la posición que se agrega (``add``).

    No muta ``parsed``: el router re-parsea el archivo almacenado en cada
    dry-run y commit y vuelve a aplicar las correcciones guardadas, así que
    acumular estado aquí corrompería la segunda pasada (research R-05,
    ``_reload_parsed_from_storage``).
    """
    result = copy.deepcopy(parsed)

    for correction in corrections:
        op = correction.get("op")
        header = correction.get("category_header")
        raw_ordinal = correction.get("ordinal")

        if op not in ("add", "edit", "remove"):
            raise CorrectionError("unknown_op")
        if not isinstance(header, str):
            raise CorrectionError("unknown_category")
        try:
            ordinal = int(raw_ordinal)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise CorrectionError("malformed_ordinal") from exc

        category = _find_category(result, header)

        if op == "add":
            _insert_ordered(category.rows, _build_row(correction.get("row"), ordinal=ordinal))
            continue

        index = next(
            (i for i, row in enumerate(category.rows) if row.position == ordinal),
            None,
        )
        if index is None:
            raise CorrectionError("ordinal_not_found", ordinal=ordinal)

        if op == "remove":
            category.rows.pop(index)
        else:  # edit
            category.rows[index] = _build_row(correction.get("row"), ordinal=ordinal)

    return result


def check_category(category: ParsedCategory) -> CompletenessReport:
    """Atajo: verifica los ordinales impresos de una categoría ya parseada.

    Las filas sin ordinal legible no participan de la verificación — se
    reportan aparte como ``UnreadableRow``.
    """
    return check_completeness(
        [row.position for row in category.rows if row.position is not None]
    )
