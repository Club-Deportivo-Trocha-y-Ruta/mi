"""Tests F-UP2: ``RaceIngestor.ingest_event(dry_run=True)``.

Cubre:
- ``dry_run=True`` NO commitea (rollback al final) — store revierte a snapshot.
- ``IngestReport`` con conteos "como si" se hubiera insertado.
- Warnings prefijado con ``DRY_RUN: no se persistieron cambios``.
- Re-correr commit (mismo sha256) promueve pending → committed.
- Idempotencia sha256 con dry_run: detección sigue funcionando.
- Rollback automático si dry_run lanza excepción (no commit parcial).
- Status pending visible en query post-dry_run cuando el caller persistió
  previamente el RaceImport (escenario wizard /parse → /dry-run).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.race_event import SurfaceCondition
from app.models.race_import import RaceImport, RaceImportStatus
from app.schemas.race import EventMeta
from app.services.race.ingestor import RaceIngestor
from app.services.race.pdf_parser import (
    GeneralRow,
    ResultsRow,
    parse_general_pdf,
    parse_results_pdf,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _meta_v4() -> EventMeta:
    return EventMeta(
        season=2026,
        copa_code="copa_valle",
        valida_num=4,
        name="VALIDA IV CALI MAYO 17 DE 2026",
        event_date=date(2026, 5, 17),
        location="CALI",
        climate="soleado",
        temperature_c=Decimal("27.5"),
        surface_condition=SurfaceCondition.seca,
        altitude_msnm=1003,
        weather_notes="Pista en buen estado.",
        pdf_results_filename="valida_iv_2026_resultados.pdf",
        pdf_general_filename="valida_iv_2026_general.pdf",
    )


def _row(pos, bib, name, club, time_raw, points):
    return ResultsRow(
        position=pos, bib=bib, name=name, city="Yumbo",
        club=club, time_raw=time_raw, points=points,
    )


# ===========================================================================
# 1. dry_run=True no commitea
# ===========================================================================


class TestDryRunDoesNotCommit:
    @pytest.mark.asyncio
    async def test_dry_run_rolls_back_competitors_and_results(self, fake_session):
        """dry_run=True ejecuta el flujo pero rollback al final — store vacío."""
        results = {
            "TET_CP": [
                _row(1, "550", "Sebastian Yule Mendoza", "Club Caña y Trapiche", "0:03:38", 40),
                _row(2, "551", "Otro Niño", "Club X", "0:04:00", 36),
            ],
        }
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            ingested_by_user_id=1,
            dry_run=True,
        )

        # IngestReport refleja conteos "como si" hubiera insertado
        assert report.results_inserted == 2
        assert report.competitors_created == 2

        # Pero el store revertió: ningún competitor / result persistido
        assert len(fake_session.store.competitors) == 0
        assert len(fake_session.store.results) == 0
        # series y event también revertidos
        assert len(fake_session.store.series) == 0
        assert len(fake_session.store.events) == 0

    @pytest.mark.asyncio
    async def test_dry_run_report_includes_dry_run_warning(self, fake_session):
        """El IngestReport del dry_run incluye warning explícito."""
        results = {
            "TET_CP": [
                _row(1, "550", "Sebastian Yule Mendoza", "Club Caña y Trapiche", "0:03:38", 40),
            ],
        }
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            ingested_by_user_id=1,
            dry_run=True,
        )

        assert len(report.warnings) >= 1
        assert any("DRY_RUN" in w for w in report.warnings)
        assert any("no se persistieron cambios" in w for w in report.warnings)

    @pytest.mark.asyncio
    async def test_dry_run_with_general_pdf_no_competitors_persisted(
        self, fake_session
    ):
        """dry_run=True con GENERAL+RESULTADOS: ningún competitor del general
        queda persistido tampoco."""
        results = {
            "TET_CP": [
                _row(1, "550", "Sebastian Yule Mendoza", "Club Caña y Trapiche", "0:03:38", 40),
            ],
        }
        general = {
            "TET_CP": [
                GeneralRow(
                    overall_position=1, bib="550",
                    name="Sebastian Yule Mendoza", city="Yumbo",
                    club="Club Caña y Trapiche",
                    points_per_valida=[0, 0, 0, 40], total_points=40,
                ),
                GeneralRow(
                    overall_position=2, bib="1411",
                    name="Otro Tetero", city="Cali",
                    club="Club Y",
                    points_per_valida=[30, 25, 20, 0], total_points=75,
                ),
            ],
        }
        ingestor = RaceIngestor(fake_session)
        await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            general_by_category=general,
            ingested_by_user_id=1,
            dry_run=True,
        )

        assert len(fake_session.store.competitors) == 0


# ===========================================================================
# 2. Re-correr commit promueve pending → committed
# ===========================================================================


class TestPromotePendingToCommitted:
    @pytest.mark.asyncio
    async def test_commit_after_dry_run_with_same_sha_persists_normally(
        self, fake_session
    ):
        """Tras dry_run, un commit (dry_run=False) con mismo sha persiste OK.

        El dry_run no debe dejar artefactos que bloqueen un commit posterior.
        """
        results = {
            "TET_CP": [
                _row(1, "550", "Sebastian Yule Mendoza", "Club Caña y Trapiche", "0:03:38", 40),
            ],
        }
        ingestor = RaceIngestor(fake_session)
        sha = "deadbeef" * 8  # 64 hex chars

        # 1) dry_run primero
        await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            pdf_results_sha256=sha,
            ingested_by_user_id=1,
            dry_run=True,
        )
        assert len(fake_session.store.competitors) == 0
        assert len(fake_session.store.results) == 0
        assert len(fake_session.store.imports) == 0  # rollback descartó

        # 2) commit real
        report = await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            pdf_results_sha256=sha,
            ingested_by_user_id=1,
            dry_run=False,
        )
        assert report.results_inserted == 1
        assert len(fake_session.store.results) == 1
        # RaceImport quedó en committed
        imports = list(fake_session.store.imports.values())
        assert len(imports) == 1
        assert imports[0].status == RaceImportStatus.committed
        assert imports[0].sha256 == sha

    @pytest.mark.asyncio
    async def test_pending_race_import_preexists_then_commit_promotes(
        self, fake_session
    ):
        """Escenario wizard: ``/parse`` persiste RaceImport pending; ``/commit``
        lo reusa y promueve a committed sin duplicar fila."""
        sha = "abcd" * 16
        # Simular endpoint /parse: persiste un pending row PREVIAMENTE
        pending = RaceImport(
            filename="valida_iv_2026_resultados.pdf",
            sha256=sha,
            series_id=99,  # placeholder; se reseteará por _upsert_series
            status=RaceImportStatus.pending,
            stats_json={},
            imported_by_user_id=1,
        )
        fake_session.add(pending)
        await fake_session.commit()
        assert len(fake_session.store.imports) == 1

        # Ahora simular /commit: ingest_event(dry_run=False) con mismo sha
        results = {
            "TET_CP": [
                _row(1, "550", "Sebastian Yule Mendoza", "Club Caña y Trapiche", "0:03:38", 40),
            ],
        }
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            pdf_results_sha256=sha,
            ingested_by_user_id=1,
            dry_run=False,
        )
        assert report.results_inserted == 1

        # NO se duplicó el RaceImport — el pending se promovió en place
        imports = list(fake_session.store.imports.values())
        assert len(imports) == 1
        assert imports[0].status == RaceImportStatus.committed
        assert imports[0].sha256 == sha


# ===========================================================================
# 3. Idempotencia sha256 con dry_run
# ===========================================================================


class TestDryRunIdempotency:
    @pytest.mark.asyncio
    async def test_dry_run_detects_existing_committed_sha(self, fake_session):
        """dry_run sobre un SHA ya committed devuelve report con conteos=0
        y warning de duplicado — sin rollback parcial inconsistente."""
        sha = "feed" * 16
        results = {
            "TET_CP": [
                _row(1, "550", "Sebastian Yule Mendoza", "Club Caña y Trapiche", "0:03:38", 40),
            ],
        }
        ingestor = RaceIngestor(fake_session)

        # 1) commit real primero
        await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            pdf_results_sha256=sha,
            ingested_by_user_id=1,
            dry_run=False,
        )
        # snapshot del estado committed
        committed_count = len(fake_session.store.results)
        committed_imports = len(fake_session.store.imports)

        # 2) dry_run con mismo sha
        report = await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            pdf_results_sha256=sha,
            ingested_by_user_id=1,
            dry_run=True,
        )
        # Conteos == 0 (duplicado detectado, abort temprano)
        assert report.results_inserted == 0
        assert report.competitors_created == 0
        # Warning de duplicado presente
        assert any("ya commiteado" in w for w in report.warnings)
        # Warning DRY_RUN también presente
        assert any("DRY_RUN" in w for w in report.warnings)

        # Store no cambió (no rollback parcial)
        assert len(fake_session.store.results) == committed_count
        assert len(fake_session.store.imports) == committed_imports


# ===========================================================================
# 4. Rollback en excepción durante dry_run
# ===========================================================================


class TestDryRunExceptionRollback:
    @pytest.mark.asyncio
    async def test_dry_run_with_unknown_category_raises_and_rolls_back(
        self, fake_session
    ):
        """Si dry_run lanza ValueError (categoría desconocida), el rollback
        explícito en el except limpia cualquier estado pending."""
        results = {
            "XXX_UNKNOWN": [
                _row(1, "999", "Fake Rider", "Club Z", "0:30:00", 0),
            ],
        }
        ingestor = RaceIngestor(fake_session)
        with pytest.raises(ValueError, match="Categoría desconocida"):
            await ingestor.ingest_event(
                meta=_meta_v4(),
                results_by_category=results,
                ingested_by_user_id=1,
                dry_run=True,
            )

        # Store completamente limpio tras rollback
        assert len(fake_session.store.results) == 0
        assert len(fake_session.store.competitors) == 0
        assert len(fake_session.store.events) == 0
        assert len(fake_session.store.series) == 0


# ===========================================================================
# 5. Status pending query post-parse
# ===========================================================================


class TestPendingStatusQueryable:
    @pytest.mark.asyncio
    async def test_pending_import_visible_after_parse(self, fake_session):
        """Tras simular /parse (persiste RaceImport pending), una query por
        status=pending lo retorna — base para que /commit pueda promoverlo."""
        sha = "1234" * 16
        pending = RaceImport(
            filename="resultados.pdf",
            sha256=sha,
            series_id=1,
            status=RaceImportStatus.pending,
            stats_json={},
            imported_by_user_id=1,
        )
        fake_session.add(pending)
        await fake_session.commit()

        ingestor = RaceIngestor(fake_session)
        found = await ingestor._find_pending_import(sha)
        assert found is not None
        assert found.status == RaceImportStatus.pending
        assert found.sha256 == sha

    @pytest.mark.asyncio
    async def test_find_pending_returns_none_when_already_committed(
        self, fake_session
    ):
        """Una vez promovido a committed, ``_find_pending_import`` ya no lo
        encuentra — el helper es estricto sobre el status."""
        sha = "5678" * 16
        committed = RaceImport(
            filename="resultados.pdf",
            sha256=sha,
            series_id=1,
            status=RaceImportStatus.committed,
            stats_json={"results_inserted": 1},
            imported_by_user_id=1,
        )
        fake_session.add(committed)
        await fake_session.commit()

        ingestor = RaceIngestor(fake_session)
        found = await ingestor._find_pending_import(sha)
        assert found is None
