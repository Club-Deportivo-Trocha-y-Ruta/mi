"""Tests del ``RaceIngestor``.

Estrategia: ``FakeAsyncSession`` (conftest local) emula in-memory el subset
de ``AsyncSession`` que usa el ingestor — select, add, flush, commit, rollback.
No requiere aiosqlite ni MySQL.

Cobertura mínima (≥5 casos, workflow §4.4):
- Ingest V-IV completo (dataset sintético multi-categoría): conteos,
  velocidad, metadata del evento (T153 — ver nota de amendment más abajo).
- Re-ingest sin SHA: idempotente por UNIQUE (results_skipped sube).
- Re-ingest con SHA committed: abort idempotente (results_inserted=0).
- Match decision aplicada: bib 553 queda con athlete_id confirmado.
- Warning tiempo anómalo: bib 424 (0:04:33 en INF_A) genera warning con
  ``bib`` + ``cat`` pero NO el nombre.
- Sex inferido por code de categoría.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.models.race_competitor import CompetitorSex
from app.models.race_event import RaceEventStatus, SurfaceCondition
from app.models.race_import import RaceImportStatus
from app.models.race_result import ResultStatus
from app.schemas.race import EventMeta
from app.services.race.ingestor import RaceIngestor, _derive_sex_from_code
from app.services.race.staged_document import ResultsRow
from tests.helpers.results_pdf_builder import FakeNameGenerator


# ---------------------------------------------------------------------------
# Helpers de construcción de filas
# ---------------------------------------------------------------------------


def _meta_v4() -> EventMeta:
    """Metadata canónica de la Válida IV (CALI, 2026-05-17)."""
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
        pdf_results_filename="resultados_sintetico_v4.pdf",
        pdf_general_filename="general_sintetico_v4.pdf",
    )


def _row(
    pos: int,
    bib: str,
    name: str,
    club: str,
    time_raw: str,
    points: int,
) -> ResultsRow:
    return ResultsRow(
        position=pos,
        bib=bib,
        name=name,
        city="Yumbo",
        club=club,
        time_raw=time_raw,
        points=points,
    )


# ---------------------------------------------------------------------------
# Amendment 2026-09-26 (T153): ``pdf_parser.py``/``parse_results_pdf`` se
# retiraron — las 4 pruebas que leían los PDFs reales de la Válida IV
# (los PDFs reales de válida IV, T155 los borra)
# staguean ahora un dataset 100% sintético (``FakeNameGenerator``, nunca
# datos reales de menores) en vez de parsear un archivo. Se pierde la cifra
# exacta "229 filas/26 categorías/10 TyR" del acta real — lo que estas
# pruebas verifican no es esa cifra en sí, sino que el ingestor cuenta,
# inserta y reporta correctamente sobre un dataset multi-categoría con TyR
# mezclados con externos; las cifras nuevas son las que el propio dataset
# sintético declara (ver ``_N_CATEGORIES``/``_ROWS_PER_CATEGORY``/``_N_TYR``).
# ---------------------------------------------------------------------------

_SYNTHETIC_CATEGORY_CODES = ["TET_CP", "PRE_A", "INF_A_F", "JUN_M", "MAS_B1"]
_N_CATEGORIES = len(_SYNTHETIC_CATEGORY_CODES)
_ROWS_PER_CATEGORY = 4
_TOTAL_ROWS = _N_CATEGORIES * _ROWS_PER_CATEGORY
#: De cada categoría, la primera fila es TyR (club Trocha y Ruta); el resto
#: son clubes externos ficticios.
_N_TYR = _N_CATEGORIES


def _build_synthetic_v4_results() -> dict[str, list[ResultsRow]]:
    gen = FakeNameGenerator()
    results: dict[str, list[ResultsRow]] = {}
    for code in _SYNTHETIC_CATEGORY_CODES:
        rows = []
        for pos in range(1, _ROWS_PER_CATEGORY + 1):
            club = "Club Trocha y Ruta" if pos == 1 else gen.next_club()
            rows.append(
                _row(
                    pos, str(100 * len(results) + pos), gen.next_name(), club,
                    f"0:{30 + pos:02d}:00", max(1, 40 - pos),
                )
            )
        results[code] = rows
    return results


# ===========================================================================
# 1. Ingest V-IV completo (dataset sintético multi-categoría)
# ===========================================================================


class TestIngestFromFullPdf:
    @pytest.mark.asyncio
    async def test_ingest_valida_iv_creates_expected_counts(self, fake_session):
        """Ingestar V-IV completo (dataset sintético) — verificar conteos."""
        results = _build_synthetic_v4_results()

        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            ingested_by_user_id=999,
        )

        assert len(results) == _N_CATEGORIES

        total_rows = sum(len(rs) for rs in results.values())
        assert total_rows == _TOTAL_ROWS
        assert report.results_inserted == _TOTAL_ROWS
        assert report.results_skipped == 0

        assert report.tyr_count == _N_TYR

        # Por default, ningún athlete_id se asigna automáticamente
        race_results = list(fake_session.store.results.values())
        tyr_results = [
            r for r in race_results
            if fake_session.store.competitors[r.competitor_id].club_text
            and "trocha" in (fake_session.store.competitors[r.competitor_id].club_text.lower())
        ]
        assert len(tyr_results) == _N_TYR
        assert all(r.athlete_id is None for r in tyr_results)

    @pytest.mark.asyncio
    async def test_ingest_speed_under_5s(self, fake_session):
        """Workflow §4 criterio: ingest V-IV < 5s."""
        import time as _time

        results = _build_synthetic_v4_results()

        ingestor = RaceIngestor(fake_session)
        t0 = _time.monotonic()
        await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            ingested_by_user_id=999,
        )
        elapsed = _time.monotonic() - t0
        assert elapsed < 5.0, f"Ingest tardó {elapsed:.2f}s (debe ser <5s)"

    @pytest.mark.asyncio
    async def test_ingest_creates_event_with_meta(self, fake_session):
        """``RaceEvent`` se persiste con todos los campos de ``EventMeta``."""
        results = _build_synthetic_v4_results()

        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            ingested_by_user_id=999,
        )

        event = fake_session.store.events[report.event_id]
        assert event.sequence_number == 4
        assert event.event_date == date(2026, 5, 17)
        assert event.location == "CALI"
        assert event.status == RaceEventStatus.COMPLETED
        assert event.climate == "soleado"
        assert event.temperature_c == Decimal("27.5")
        assert event.surface_condition == SurfaceCondition.seca
        assert event.altitude_msnm == 1003
        assert event.pdf_results_filename == "resultados_sintetico_v4.pdf"


# ===========================================================================
# 2. Idempotencia
# ===========================================================================


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_re_ingest_without_sha_skips_duplicates(self, fake_session):
        """Re-ingest del mismo evento sin SHA: UNIQUE atrapa los duplicados
        vía la consulta previa del ingestor (``_existing_competitor_ids_for``)."""
        results = {
            "TET_CP": [
                _row(1, "550", "Sebastian Yule Mendoza", "Club Caña y Trapiche", "0:03:38", 40),
                _row(2, "551", "Otro Niño", "Club X", "0:04:00", 36),
            ],
        }
        ingestor = RaceIngestor(fake_session)

        r1 = await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            ingested_by_user_id=1,
        )
        assert r1.results_inserted == 2
        assert r1.results_skipped == 0

        # Re-ingest sin sha → segunda pasada detecta colisión via existing_pairs
        r2 = await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            ingested_by_user_id=1,
        )
        assert r2.event_id == r1.event_id
        assert r2.results_inserted == 0
        assert r2.results_skipped == 2

    @pytest.mark.asyncio
    async def test_re_ingest_with_committed_sha_aborts(self, fake_session):
        """Si ``RaceImport`` ya está committed con el mismo sha256, el
        segundo ingest aborta retornando IngestReport con warning informativo."""
        results = {
            "INF_A": [_row(1, "401", "Niño Test", "Club X", "0:33:00", 40)],
        }
        ingestor = RaceIngestor(fake_session)
        sha = "a" * 64

        r1 = await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            pdf_results_sha256=sha,
            ingested_by_user_id=1,
        )
        assert r1.results_inserted == 1

        # Verificar que el RaceImport quedó committed
        committed = [
            i for i in fake_session.store.imports.values()
            if i.status == RaceImportStatus.committed
        ]
        assert len(committed) == 1
        assert committed[0].sha256 == sha

        # Segundo intento con mismo sha → abort
        r2 = await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            pdf_results_sha256=sha,
            ingested_by_user_id=1,
        )
        assert r2.results_inserted == 0
        assert r2.results_skipped == 0
        assert any("sha256 ya commiteado" in w for w in r2.warnings)


# ===========================================================================
# 3. Match decisions del coach
# ===========================================================================


class TestMatchDecisions:
    @pytest.mark.asyncio
    async def test_decision_applied_to_tyr_competitor(self, fake_session):
        """``match_decisions={"553": 42}`` → competitor de bib 553 (TyR)
        queda con ``athlete_id=42`` y el race_result también."""
        results = {
            "TET_CP": [
                _row(4, "553", "Thiago Duque Cardona", "Club Trocha y Ruta", "0:04:49", 30),
            ],
        }
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            match_decisions={"553": 42},
            ingested_by_user_id=1,
        )

        assert report.tyr_count == 1
        assert report.results_inserted == 1
        # Competitor linkeado
        comp = next(iter(fake_session.store.competitors.values()))
        assert comp.athlete_id == 42
        assert comp.linked_by_user_id == 1
        # RaceResult también con athlete_id
        rr = next(iter(fake_session.store.results.values()))
        assert rr.athlete_id == 42

    @pytest.mark.asyncio
    async def test_decision_none_keeps_athlete_null(self, fake_session):
        """``match_decisions={"553": None}`` (skip/new) → athlete_id NULL."""
        results = {
            "TET_CP": [
                _row(4, "553", "Thiago Duque Cardona", "Club Trocha y Ruta", "0:04:49", 30),
            ],
        }
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            match_decisions={"553": None},
            ingested_by_user_id=1,
        )
        comp = next(iter(fake_session.store.competitors.values()))
        assert comp.athlete_id is None
        rr = next(iter(fake_session.store.results.values()))
        assert rr.athlete_id is None
        assert report.tyr_count == 1

    @pytest.mark.asyncio
    async def test_decision_ignored_for_non_tyr(self, fake_session):
        """Si el club NO es TyR, las match_decisions se ignoran — no se
        debe linkear athlete_id a un competidor de otro club.

        Usamos un club textual con baja similitud a "trocha y ruta" para
        evitar falso positivo del fuzzy partial_ratio (edge-cases §7.4)."""
        results = {
            "TET_CP": [
                _row(2, "551", "Otro Niño", "Club Caña y Trapiche", "0:04:00", 36),
            ],
        }
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            match_decisions={"551": 99},  # incorrecto: no es TyR
            ingested_by_user_id=1,
        )
        comp = next(iter(fake_session.store.competitors.values()))
        assert comp.athlete_id is None
        assert report.tyr_count == 0


# ===========================================================================
# 4. Warning de tiempo anómalo
# ===========================================================================


class TestTimeAnomalyWarning:
    @pytest.mark.asyncio
    async def test_anomalous_time_in_menores_tier_warns(self, fake_session):
        """Bib 424 INF_A con time=0:04:33 → warning con bib+cat, sin nombre."""
        results = {
            "INF_A": [
                _row(1, "401", "Niño Normal", "Club X", "0:38:00", 40),
                _row(9, "424", "Matias Sabogal", "Fundacion Acti-Vida", "0:04:33", 19),
            ],
        }
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            ingested_by_user_id=1,
        )

        # 1 warning de tiempo anómalo
        anom_warnings = [w for w in report.warnings if "tiempo_anomalo" in w]
        assert len(anom_warnings) == 1
        w = anom_warnings[0]
        assert "bib=424" in w
        assert "cat=INF_A" in w
        # Privacidad: NUNCA el nombre completo en warnings
        assert "Matias" not in w
        assert "Sabogal" not in w

    @pytest.mark.asyncio
    async def test_anomalous_time_in_master_tier_no_warning(self, fake_session):
        """Tier master con tiempo bajo NO debe generar warning (categoría adulta)."""
        results = {
            "MAS_A": [
                _row(1, "101", "Master Test", "Club X", "0:20:00", 40),
            ],
        }
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            ingested_by_user_id=1,
        )
        anom = [w for w in report.warnings if "tiempo_anomalo" in w]
        assert len(anom) == 0


# ===========================================================================
# 4b. Filas sin tiempo reconocible (feature 044, T024b)
# ===========================================================================


class TestRowsWithoutRecognisableTime:
    """Una fila leída nunca se pierde en silencio: se guarda o se salta con
    warning, y la cuenta por categoría cuadra (SC-001 a nivel de ingesta)."""

    @pytest.mark.asyncio
    async def test_every_row_is_stored_with_the_right_status(self, fake_session):
        results = {
            "INF_A": [
                _row(1, "501", "Ficticio Uno", "Club X", "0:38:00", 50),
                _row(2, "502", "Ficticio Dos", "Club X", "13:07", 45),
                _row(3, "503", "Ficticio Tres", "Club X", "-1 vuelta", 40),
                _row(4, "504", "Ficticio Cuatro", "Club X", "-2", 35),
                _row(5, "505", "Ficticio Cinco", "Club X", "", 30),
                _row(6, "506", "Ficticio Seis", "Club X", "12:02:00", 25),
            ],
        }
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta_v4(), results_by_category=results, ingested_by_user_id=1,
        )

        assert report.results_inserted == 6
        assert report.results_skipped == 0
        by_bib = {r.bib_number: r for r in fake_session.store.results.values()}
        assert by_bib[502].status == ResultStatus.FINISHED
        assert by_bib[502].race_time_ms == 787_000
        assert (by_bib[503].status, by_bib[503].laps_behind) == (ResultStatus.MINUS_LAPS, 1)
        assert (by_bib[504].status, by_bib[504].laps_behind) == (ResultStatus.MINUS_LAPS, 2)
        # Clasificado sin tiempo: FINISHED, sin tiempo ni vueltas, puntos tal cual.
        assert by_bib[505].status == ResultStatus.FINISHED
        assert by_bib[505].race_time_ms is None
        assert by_bib[505].laps_behind is None
        assert by_bib[505].position == 5
        assert by_bib[505].points_awarded == 30
        # Hora fuera de rango XCO: warning y fila conservada sin tiempo.
        assert by_bib[506].race_time_ms is None
        assert by_bib[506].points_awarded == 25
        unparse = [w for w in report.warnings if "tiempo_no_parseable" in w]
        assert len(unparse) == 1 and "bib=506" in unparse[0]
        assert "Ficticio" not in unparse[0]

    @pytest.mark.asyncio
    async def test_row_without_position_nor_time_is_an_explicit_skip(self, fake_session):
        row = _row(1, "511", "Ficticio Once", "Club X", "", 0)
        row.position = None
        results = {"INF_A": [_row(1, "510", "Ficticio Diez", "Club X", "0:38:00", 50), row]}
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta_v4(), results_by_category=results, ingested_by_user_id=1,
        )

        assert report.results_inserted == 1
        assert report.results_skipped == 1
        skips = [w for w in report.warnings if "fila_sin_posicion_ni_tiempo" in w]
        assert skips == ["fila_sin_posicion_ni_tiempo bib=511 cat=INF_A"]
        # Una fila que no se guarda no deja un competidor huérfano.
        assert "ficticio once" not in {
            c.normalized_name for c in fake_session.store.competitors.values()
        }

    @pytest.mark.asyncio
    async def test_per_category_accounting_is_enforced(self, fake_session):
        """Si una rama futura se saltara una fila sin contarla, la ingesta
        aborta en vez de confirmar una categoría incompleta. Se simula con una
        categoría que declara una fila más de las que itera."""
        rows = [_row(1, "520", "Ficticio Veinte", "Club X", "0:38:00", 50)]

        class _ShortList(list):
            def __len__(self):  # la categoría "declara" una fila más de las que itera
                return super().__len__() + 1

        ingestor = RaceIngestor(fake_session)
        with pytest.raises(RuntimeError, match="ingest_incompleto cat=INF_A leidas=2"):
            await ingestor.ingest_event(
                meta=_meta_v4(),
                results_by_category={"INF_A": _ShortList(rows)},
                ingested_by_user_id=1,
            )


# ===========================================================================
# 5. (retirada — GENERAL retirement, amendment 2026-09-26, R-25):
# ``TestGeneralFirst`` probaba el paso "GENERAL primero"
# (``_upsert_competitor_from_general``) que ``ingest_event`` ya no tiene —
# GENERAL no se stagea ni se ingesta más (contracts/staged-import.md).
# ===========================================================================


# ===========================================================================
# 6. Derivación de sexo desde code
# ===========================================================================


class TestSexDerivation:
    def test_male_code(self):
        assert _derive_sex_from_code("INF_A") == CompetitorSex.M
        assert _derive_sex_from_code("ELITE_M") == CompetitorSex.M
        assert _derive_sex_from_code("MAS_A") == CompetitorSex.M

    def test_female_code(self):
        assert _derive_sex_from_code("INF_A_F") == CompetitorSex.F
        assert _derive_sex_from_code("ELITE_F") == CompetitorSex.F
        assert _derive_sex_from_code("MAS_F") == CompetitorSex.F
        assert _derive_sex_from_code("JUN_F") == CompetitorSex.F

    def test_mixed_codes_return_none(self):
        # Teteros y Promo no son binarios a nivel competidor
        assert _derive_sex_from_code("TET_SP") is None
        assert _derive_sex_from_code("TET_CP") is None
        assert _derive_sex_from_code("PROMO") is None

    def test_unknown_code(self):
        assert _derive_sex_from_code("") is None
        assert _derive_sex_from_code("FOOBAR") is None


# ===========================================================================
# 7. Idempotencia con sha = re-ingest desde fixtures completos
# ===========================================================================


class TestFullIdempotency:
    @pytest.mark.asyncio
    async def test_re_ingest_pdf_committed_aborts_clean(self, fake_session):
        """Ingest V-IV completo (dataset sintético) + re-ingest con mismo sha = abort."""
        results = _build_synthetic_v4_results()
        sha = "f" * 64
        ingestor = RaceIngestor(fake_session)

        r1 = await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            pdf_results_sha256=sha,
            ingested_by_user_id=1,
        )
        assert r1.results_inserted == _TOTAL_ROWS

        # Re-ingest con mismo sha → no escribe results
        snapshot_results_count = len(fake_session.store.results)
        r2 = await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            pdf_results_sha256=sha,
            ingested_by_user_id=1,
        )
        assert r2.results_inserted == 0
        # No agregamos ni quitamos race_results
        assert len(fake_session.store.results) == snapshot_results_count
        # Sigue habiendo solo un import committed (el primero)
        committed = [
            i for i in fake_session.store.imports.values()
            if i.status == RaceImportStatus.committed
        ]
        assert len(committed) == 1


# ===========================================================================
# 8. Privacidad: warnings nunca tienen nombres
# ===========================================================================


class TestPrivacyInWarnings:
    @pytest.mark.asyncio
    async def test_warnings_do_not_leak_names(self, fake_session):
        """Múltiples casos con bibs distintos: todos los warnings deben
        contener identificadores estructurales (bib/cat), nunca nombres."""
        sensitive_names = [
            "Matias Sabogal",
            "Dulce Maria Herrera",
            "Thiago Duque Cardona",
        ]
        results = {
            "INF_A": [
                _row(1, "424", "Matias Sabogal", "Fundacion Acti-Vida", "0:04:33", 19),
            ],
            "TET_CP": [
                _row(4, "553", "Thiago Duque Cardona", "Club Trocha y Ruta", "0:04:49", 30),
            ],
        }
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta_v4(),
            results_by_category=results,
            ingested_by_user_id=1,
        )

        combined = " | ".join(report.warnings)
        for name in sensitive_names:
            # Tampoco apellidos sueltos
            for fragment in name.split():
                if len(fragment) <= 3:
                    continue
                assert fragment not in combined, (
                    f"Posible fuga de nombre {fragment!r} en warnings: {combined}"
                )
