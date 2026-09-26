"""Helper de test: stagea un documento sintético sin pasar por HTTP ``/parse``
(feature 044, amendment 2026-09-26, T132 — contracts/staged-import.md § Tests).

``stage_extracted_results`` no reparsea nada — recibe el ``ParsedResults`` ya
extraído — así que este helper puede construir uno sintético en memoria
(``ParsedCategory``/``ResultsRow``, sin PDF ni WeasyPrint) y llamar el
servicio directamente. Reemplaza el patrón viejo de subir un PDF por HTTP
``POST /parse`` solo para obtener un ``RaceImport`` en staging: el archivo
en bytes (``file_bytes``) es evidencia opaca — el servicio la sube a storage
y la hashea, nunca la vuelve a leer.

Privacidad: los nombres/ciudades/clubes por defecto vienen de
``FakeNameGenerator`` — nunca datos reales.
"""
from __future__ import annotations

import hashlib
from datetime import date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.race_series import RaceSeriesKind, RaceSeriesLevel
from app.models.user import User
from app.services.race.import_staging import (
    StageHeader,
    StageResult,
    stage_extracted_results,
)
from app.services.race.staged_document import (
    ParsedCategory,
    ParsedResults,
    ResultsRow,
    StagedProfileMeta,
)
from app.services.request_context import AuditContext
from tests.helpers.results_pdf_builder import FakeNameGenerator

#: Perfil de lectura sintético — no corresponde a un archivo real en
#: ``race_reading_profiles/``; basta para satisfacer las columnas NOT NULL
#: de ``race_import_staged_documents`` en un test.
DEFAULT_TEST_PROFILE = StagedProfileMeta(
    profile_id="test-synthetic-v1",
    profile_sha256="0" * 64,
    engine_version="test-helper",
)


def default_test_document(*, n_rows: int = 3, header: str = "INFANTIL A", code: str = "INF_A") -> ParsedResults:
    """Documento sintético mínimo: una categoría con ``n_rows`` filas sanas."""
    gen = FakeNameGenerator()
    rows: list[ResultsRow] = []
    for i in range(1, n_rows + 1):
        given, surname = gen.next_name_parts()
        rows.append(
            ResultsRow(
                position=i,
                bib=str(700 + i),
                name=f"{given} {surname}",
                city=gen.next_city(),
                club=gen.next_club(),
                time_raw=f"0:{40 + i:02d}:00",
                points=max(1, 50 - (i - 1)),
            )
        )
    return ParsedResults(
        categories=[ParsedCategory(header_raw=header, code=code, rows=rows)],
        unreadable_rows=[],
    )


def default_test_header(*, season: int = 2026, valida_num: int = 4) -> StageHeader:
    return StageHeader(
        series_name="Copa Valle de Ciclomontañismo",
        series_kind=RaceSeriesKind.cup,
        series_level=RaceSeriesLevel.departmental,
        season=season,
        valida_num=valida_num,
        event_name=f"VALIDA {valida_num} SINTETICA",
        event_date=date(season, 5, 17),
        location="Cali",
    )


async def stage_for_test(
    db: AsyncSession,
    document: Optional[ParsedResults] = None,
    header: Optional[StageHeader] = None,
    actor: Optional[User] = None,
    *,
    file_bytes: Optional[bytes] = None,
    results_ext: str = "pdf",
    profile: Optional[StagedProfileMeta] = None,
    dry: bool = False,
) -> StageResult:
    """Llama ``stage_extracted_results`` con un documento sintético cuando no
    se da uno, sobre el storage con el que el test ya esté configurado
    (típicamente el fallback local vía la fixture ``override_storage`` de
    cada archivo de test — este helper no lo reconfigura).

    ``actor`` es obligatorio (un ``User`` ya persistido en la sesión) — sin
    él no hay ``imported_by_user_id``/auditoría posibles.
    """
    if actor is None:
        raise ValueError("stage_for_test requiere `actor` (User ya persistido)")
    doc = document if document is not None else default_test_document()
    hdr = header if header is not None else default_test_header()
    fb = file_bytes
    if fb is None:
        # Evidencia opaca — el servicio nunca la reparsea, solo la hashea y
        # la sube. Se deriva de una representación estable del documento +
        # el header para que dos llamadas con el mismo documento produzcan
        # el mismo sha256 (dedupe, contracts/staged-import.md).
        fingerprint = repr((hdr.season, hdr.valida_num, doc)).encode("utf-8")
        fb = hashlib.sha256(fingerprint).digest()

    return await stage_extracted_results(
        db,
        document=doc,
        profile=profile or DEFAULT_TEST_PROFILE,
        file_bytes=fb,
        original_filename=f"sintetico_valida_{hdr.valida_num}.{results_ext}",
        results_ext=results_ext,
        header=hdr,
        actor=actor,
        ctx=AuditContext.for_user(actor, request_id="test-stage-for-test"),
        dry=dry,
    )
