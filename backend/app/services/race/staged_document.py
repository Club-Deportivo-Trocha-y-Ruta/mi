"""Documento en bruto de una ingesta en revisión (amendment 2026-09-26).

Dos responsabilidades:

1. **Tipos neutros** — ``ResultsRow``, ``ParsedCategory``, ``ParsedResults``
   y ``UnreadableRow``, movidos aquí sin cambios desde ``pdf_parser.py``
   (T113). Antes de esta migración solo el parser oficial de PDFs los
   producía; ahora también los produce ``results_skill.apply_profile``
   (el motor de lectura offline de la fase 13), así que el nombre del
   módulo deja de sugerir "solo viene de un PDF". ``pdf_parser.py``
   mantiene un re-export temporal para no romper a sus importadores
   existentes; ``T153`` lo retira junto con el parser fijo.

2. **Persistencia** — ``save``/``load``/``delete`` sobre
   ``race_import_staged_documents`` (data-model.md §11.1): la fila 1:1 con
   una ``RaceImport`` en revisión que reemplaza la relectura del archivo
   original en cada ruta de revisión (FR-048, FR-049, research R-20).

**Privacidad**: las filas de ``ParsedResults``/``document_json`` llevan
nombre, ciudad y club de cada corredor — en su mayoría menores de edad
(Ley 1581). Ninguna función de este módulo registra un valor de fila en un
log, una traza o un mensaje de excepción; ``load``/``save``/``delete``
solo registran ``import_id`` y conteos (nunca el contenido).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.race_import_staged_document import RaceImportStagedDocument

if TYPE_CHECKING:
    from app.models.race_import import RaceImport

logger = logging.getLogger(__name__)

#: Versión del esquema de ``document_json`` (data-model.md §11.2). Sube solo
#: si la forma del documento cambia de manera incompatible.
SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Tipos neutros (movidos desde pdf_parser.py, T113 — sin cambios)
# ---------------------------------------------------------------------------


@dataclass
class ResultsRow:
    """Una fila del acta RESULTADOS (un corredor en una válida).

    ``time_raw == ""`` significa **clasificado sin tiempo**: la banda trae
    posición, dorsal y puntos pero la celda ``Tiempo`` vino vacía en el acta
    (research R-01 punto 4). No es lo mismo que ``DNF``/``DSQ``/``DNS``, que
    sí se conservan como texto.
    """

    position: Optional[int]
    bib: str
    name: str
    city: str  #: capturado para resolución de homónimos, no se persiste en `RaceCompetitor`.
    club: str
    time_raw: str
    points: int


@dataclass
class UnreadableRow:
    """Banda de fila que no pudo interpretarse (FR-001).

    Se reporta al coach en la previsualización en vez de descartarse en
    silencio. Solo lleva ubicación — ``page`` y el ordinal impreso cuando la
    celda 0 de la tabla es numérica — nunca texto de la fila.
    """

    page: int
    ordinal: Optional[int]


@dataclass
class ParsedCategory:
    """Una categoría del acta, en el orden en que aparece en el documento.

    ``code is None`` significa encabezado no reconocido: las filas **se
    conservan** igual (FR-002) y el commit queda bloqueado hasta que exista
    un mapeo en ``normalizer.HEADER_TO_CODE``.
    """

    header_raw: str  #: tal como se imprime, p. ej. "PREJUVENIL A DAMAS".
    code: Optional[str]
    rows: list[ResultsRow] = field(default_factory=list)


@dataclass
class ParsedResults:
    """Documento completo: categorías (en orden) + filas ilegibles."""

    categories: list[ParsedCategory] = field(default_factory=list)
    unreadable_rows: list[UnreadableRow] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------


@dataclass
class StagedProfileMeta:
    """Metadatos del perfil de lectura aplicado, tal como los pide
    ``save`` (contracts/staged-import.md)."""

    profile_id: str
    profile_sha256: str
    engine_version: str


class StagedDocumentMissing(Exception):
    """No existe fila de ``race_import_staged_documents`` para este import.

    El caso normal es un import "legado" (cargado por el flujo de subida
    antiguo, retirado en esta misma amendment): tiene ``RaceImport`` pero
    nunca tuvo documento. Los routers lo traducen a
    ``409 {"detail": "restage_required"}`` (contracts/staged-import.md).
    """

    def __init__(self, import_id: int) -> None:
        self.import_id = import_id
        super().__init__(f"import_id={import_id} sin race_import_staged_documents")


def document_to_json(document: ParsedResults) -> dict[str, Any]:
    """``ParsedResults`` -> ``dict`` serializable, forma de data-model.md §11.2."""
    return {
        "categories": [
            {
                "header_raw": category.header_raw,
                "code": category.code,
                "rows": [
                    {
                        "position": row.position,
                        "bib": row.bib,
                        "name": row.name,
                        "city": row.city,
                        "club": row.club,
                        "time_raw": row.time_raw,
                        "points": row.points,
                    }
                    for row in category.rows
                ],
            }
            for category in document.categories
        ],
        "unreadable_rows": [
            {"page": row.page, "ordinal": row.ordinal}
            for row in document.unreadable_rows
        ],
    }


def document_from_json(payload: dict[str, Any]) -> ParsedResults:
    """Inverso de ``document_to_json``. No valida — ``save`` es el único
    escritor de esta columna y siempre la produce con ``document_to_json``."""
    categories = [
        ParsedCategory(
            header_raw=raw_category["header_raw"],
            code=raw_category["code"],
            rows=[
                ResultsRow(
                    position=raw_row["position"],
                    bib=raw_row["bib"],
                    name=raw_row["name"],
                    city=raw_row["city"],
                    club=raw_row["club"],
                    time_raw=raw_row["time_raw"],
                    points=raw_row["points"],
                )
                for raw_row in raw_category["rows"]
            ],
        )
        for raw_category in payload.get("categories", [])
    ]
    unreadable_rows = [
        UnreadableRow(page=raw_row["page"], ordinal=raw_row["ordinal"])
        for raw_row in payload.get("unreadable_rows", [])
    ]
    return ParsedResults(categories=categories, unreadable_rows=unreadable_rows)


async def save(
    db: AsyncSession,
    import_id: int,
    document: ParsedResults,
    profile_meta: StagedProfileMeta,
) -> RaceImportStagedDocument:
    """Inserta la fila ``race_import_staged_documents`` de un import recién
    creado (paso 5 de ``stage_extracted_results``, contracts/staged-import.md).

    No hace ``commit`` — el caller decide la transacción (típicamente junto
    con el ``INSERT`` de ``RaceImport`` y el registro de auditoría, en una
    sola transacción, como pide el contrato).
    """
    row = RaceImportStagedDocument(
        import_id=import_id,
        schema_version=SCHEMA_VERSION,
        profile_id=profile_meta.profile_id,
        profile_sha256=profile_meta.profile_sha256,
        engine_version=profile_meta.engine_version,
        document_json=document_to_json(document),
    )
    db.add(row)
    await db.flush()
    n_categories = len(document.categories)
    n_rows = sum(len(category.rows) for category in document.categories)
    logger.info(
        "staged_document.save import_id=%s categories=%d rows=%d unreadable=%d",
        import_id,
        n_categories,
        n_rows,
        len(document.unreadable_rows),
    )
    return row


async def load(db: AsyncSession, imp: "RaceImport") -> ParsedResults:
    """Lee y deserializa el documento de un import.

    ``imp`` es la ``RaceImport`` ya cargada (evita un segundo round-trip
    solo para conocer ``imp.id``, que el caller casi siempre ya tiene).
    Lanza ``StagedDocumentMissing`` si no hay fila — el import es legado o
    ya se le borró el documento (commit completo, discard).
    """
    row = await db.get(RaceImportStagedDocument, imp.id)
    if row is None:
        raise StagedDocumentMissing(imp.id)
    return document_from_json(row.document_json)


async def delete(db: AsyncSession, import_id: int) -> None:
    """Borra la fila del documento, si existe. Idempotente: borrar dos
    veces (o borrar un import que nunca tuvo documento) no es un error —
    el commit completo, el commit-pending que termina lo pendiente y el
    discard todos llaman esto sin comprobar antes si ya se había borrado."""
    await db.execute(
        sa_delete(RaceImportStagedDocument).where(
            RaceImportStagedDocument.import_id == import_id
        )
    )
    logger.info("staged_document.delete import_id=%s", import_id)
