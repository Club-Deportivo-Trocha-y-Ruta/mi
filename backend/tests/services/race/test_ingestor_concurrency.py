"""Concurrencia, idempotencia y validación por tier — Paso 7 §7.2.

Workflow §7.2 exige:
- Tests de **concurrencia**: 2 ingests simultáneos del mismo PDF (lock SHA256).
- Tests de **idempotencia con UPDATE**: cambiar ``points`` y re-ingest.
  Decisión data-analyst Paso 1 (edge-cases §8 punto 3): el comportamiento
  actual del ingestor es **PRESERVE** (no UPDATE):
  el ``RaceImport`` ``committed`` por sha256 hace abort idempotente, y el
  loop interno detecta colisión via ``existing_pairs`` → ``results_skipped``.
  Para soportar UPDATE explícito se requiere migración futura (issue Paso 9).
  Este test **documenta el contrato actual**: re-ingest del mismo PDF
  con datos modificados preserva los originales.
- Tests de **rango de tiempo por tier**: Teteros 0-2min anómalo, INF<25min
  anómalo, Junior<25min anómalo. ELITE/MAS no chequeados.

Concurrencia técnica: ``asyncio.gather(ingest1, ingest2)`` con misma sha →
el segundo debe detectar el RaceImport committed y abortar limpio (no doble
escritura). Como el ``FakeAsyncSession`` no tiene locks de DB reales,
simulamos el orden secuencial encadenando los gathers y verificamos que el
segundo no duplica filas. Esto valida la lógica del lock por sha256, no la
concurrencia de la DB real (que es responsabilidad de MySQL + UNIQUE).
"""
from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal

import pytest

from app.models.race_event import SurfaceCondition
from app.models.race_import import RaceImportStatus
from app.schemas.race import EventMeta
from app.services.race.ingestor import (
    RaceIngestor,
    _anomaly_threshold_for,
    _derive_sex_from_code,
)
from app.services.race.pdf_parser import ResultsRow


def _meta(valida: int = 4) -> EventMeta:
    return EventMeta(
        season=2026,
        valida_num=valida,
        name=f"V-{valida}",
        event_date=date(2026, 5, 17),
        location="X",
        climate=None,
        temperature_c=Decimal("25.0"),
        surface_condition=SurfaceCondition.seca,
    )


def _row(pos: int, bib: str, name: str, club: str, time_raw: str, points: int) -> ResultsRow:
    return ResultsRow(
        position=pos, bib=bib, name=name, city="X", club=club,
        time_raw=time_raw, points=points,
    )


# ===========================================================================
# 1. Concurrencia: 2 ingests simultáneos del mismo PDF (lock SHA256)
# ===========================================================================


class TestConcurrentIngestSameSha:
    @pytest.mark.asyncio
    async def test_two_ingests_same_sha_only_first_writes(self, fake_session):
        """``asyncio.gather`` de 2 ingests con la misma sha:

        - El primero crea el ``RaceImport`` ``committed`` + 1 race_result.
        - El segundo encuentra el committed → abort sin duplicar.
        - Total: 1 race_result, 1 import committed.

        El ``FakeAsyncSession`` no es thread-safe pero asyncio en single-thread
        es secuencial dentro de cada coroutine — el orden está determinado
        por cuándo cada ingestor llega a ``await self.db.commit()``.
        """
        results = {
            "TET_CP": [_row(1, "550", "Sebastian Yule", "Club X", "0:03:38", 40)],
        }
        sha = "c" * 64
        ingestor1 = RaceIngestor(fake_session)
        ingestor2 = RaceIngestor(fake_session)

        results_tuple = await asyncio.gather(
            ingestor1.ingest_event(
                meta=_meta(),
                results_by_category=results,
                pdf_results_sha256=sha,
                ingested_by_user_id=1,
            ),
            ingestor2.ingest_event(
                meta=_meta(),
                results_by_category=results,
                pdf_results_sha256=sha,
                ingested_by_user_id=1,
            ),
        )

        # Total inserts a lo largo de ambos = 1 (el segundo no duplica)
        total_inserted = sum(r.results_inserted for r in results_tuple)
        assert total_inserted == 1, (
            f"Esperado 1 inserción, total={total_inserted} "
            f"({results_tuple[0].results_inserted}+{results_tuple[1].results_inserted})"
        )
        # Solo un RaceResult físicamente en el store
        assert len(fake_session.store.results) == 1
        # Solo un RaceImport committed (los otros podrían quedar pending sin commit del flush)
        committed = [
            i for i in fake_session.store.imports.values()
            if i.status == RaceImportStatus.committed
        ]
        assert len(committed) == 1

    @pytest.mark.asyncio
    async def test_sequential_ingest_with_different_shas_writes_both(self, fake_session):
        """Si los SHAs son distintos (PDF modificado entre ingests), ambos
        ingests producen ``RaceImport`` separados. Pero al ser el MISMO
        ``(event_id, category_id, competitor_id)``, el segundo detecta
        colisión vía ``existing_pairs`` y skip los duplicados.
        """
        results = {
            "TET_CP": [_row(1, "550", "Sebastian Yule", "Club X", "0:03:38", 40)],
        }
        ingestor1 = RaceIngestor(fake_session)
        r1 = await ingestor1.ingest_event(
            meta=_meta(),
            results_by_category=results,
            pdf_results_sha256="a" * 64,
            ingested_by_user_id=1,
        )
        assert r1.results_inserted == 1

        ingestor2 = RaceIngestor(fake_session)
        r2 = await ingestor2.ingest_event(
            meta=_meta(),
            results_by_category=results,
            pdf_results_sha256="b" * 64,  # sha distinto
            ingested_by_user_id=1,
        )
        # Segundo crea otro RaceImport pero las filas chocan con UNIQUE
        # — el ingestor las detecta vía existing_pairs y skip.
        assert r2.results_inserted == 0
        assert r2.results_skipped == 1
        # Dos RaceImport committed (los SHAs son distintos)
        committed = [
            i for i in fake_session.store.imports.values()
            if i.status == RaceImportStatus.committed
        ]
        assert len(committed) == 2


# ===========================================================================
# 2. Idempotencia con cambio de points — contrato: PRESERVE (no UPDATE)
# ===========================================================================


class TestIdempotencyPointsChange:
    @pytest.mark.asyncio
    async def test_re_ingest_with_modified_points_preserves_original(self, fake_session):
        """Re-ingest del mismo PDF con ``points`` modificado NO actualiza el
        ``race_result`` existente — el contrato actual es PRESERVE.

        Esto se debe a que el ingestor detecta la colisión vía
        ``existing_pairs`` y skip la inserción, sin tocar la fila previa.

        Si en el futuro se requiere UPDATE explícito (federación publica
        corrección oficial), se debe agregar un flag ``--force-update`` al
        CLI y la lógica correspondiente en ``ingestor.py``. Este test
        documenta el comportamiento actual para evitar regresión silenciosa.
        """
        # 1) Primer ingest: points=30
        ingestor = RaceIngestor(fake_session)
        await ingestor.ingest_event(
            meta=_meta(),
            results_by_category={
                "TET_CP": [_row(1, "550", "Niño", "Club X", "0:03:38", 30)],
            },
            ingested_by_user_id=1,
        )
        assert len(fake_session.store.results) == 1
        original_points = list(fake_session.store.results.values())[0].points_awarded
        assert original_points == 30

        # 2) Re-ingest con points=40 → PRESERVE (skip), no UPDATE
        report = await ingestor.ingest_event(
            meta=_meta(),
            results_by_category={
                "TET_CP": [_row(1, "550", "Niño", "Club X", "0:03:38", 40)],
            },
            ingested_by_user_id=1,
        )
        assert report.results_inserted == 0
        assert report.results_skipped == 1
        # La fila original NO cambió
        final = list(fake_session.store.results.values())[0]
        assert final.points_awarded == 30, (
            "Contrato actual: re-ingest PRESERVA puntos originales. "
            "Si se cambia a UPDATE, modificar este test y documentar."
        )

    @pytest.mark.asyncio
    async def test_re_ingest_with_modified_time_preserves_original(self, fake_session):
        """Igual que el de points — el ``race_time_ms`` queda intacto."""
        ingestor = RaceIngestor(fake_session)
        await ingestor.ingest_event(
            meta=_meta(),
            results_by_category={
                "TET_CP": [_row(1, "550", "Niño", "Club X", "0:03:38", 40)],
            },
            ingested_by_user_id=1,
        )
        original_time = list(fake_session.store.results.values())[0].race_time_ms

        await ingestor.ingest_event(
            meta=_meta(),
            results_by_category={
                "TET_CP": [_row(1, "550", "Niño", "Club X", "0:04:00", 40)],  # +22s
            },
            ingested_by_user_id=1,
        )
        final_time = list(fake_session.store.results.values())[0].race_time_ms
        assert final_time == original_time, "PRESERVE contract"


# ===========================================================================
# 3. Validación rango de tiempo por tier — `_anomaly_threshold_for`
# ===========================================================================


class TestAnomalyThresholds:
    """Valida la tabla ``_ANOMALY_THRESHOLDS_MS_BY_CODE_PREFIX``.

    Workflow §7.2 declara: ``Teteros 2-10min, Preinfantil 5-15min, Infantil
    25-50min, Prejuvenil 25-60min, Junior/Elite 80-120min``.

    El umbral implementado en ``ingestor._anomaly_threshold_for`` es más
    conservador (sólo dispara warning si el tiempo es **físicamente
    imposible**, no si está en rango sospechoso pero plausible):

    | code prefix | threshold ms | en minutos |
    |-------------|-------------|------------|
    | TET_        |     120_000 |    2 min   |
    | PRE_        |     300_000 |    5 min   |
    | INF_        |   1_500_000 |   25 min   |
    | PJUV_       |   1_500_000 |   25 min   |
    | JUN_        |   1_500_000 |   25 min   |

    Estos cubren las anomalías documentadas en edge-cases §4.2 (Matias
    Sabogal INF_A con 4:33). ELITE/MAS/PROMO no tienen threshold porque
    son categorías adultas con grandes rangos legítimos.
    """

    @pytest.mark.parametrize(
        "code,expected_ms",
        [
            ("TET_SP", 120_000),
            ("TET_CP", 120_000),
            ("PRE_A", 300_000),
            ("PRE_B_F", 300_000),
            ("INF_A", 1_500_000),
            ("INF_B_F", 1_500_000),
            ("PJUV_A", 1_500_000),
            ("PJUV_B_F", 1_500_000),
            ("JUN_M", 1_500_000),
            ("JUN_F", 1_500_000),
        ],
    )
    def test_thresholds_match_workflow_spec(self, code: str, expected_ms: int):
        assert _anomaly_threshold_for(code) == expected_ms

    @pytest.mark.parametrize("code", ["ELITE_M", "ELITE_F", "MAS_A", "MAS_F", "PROMO"])
    def test_adult_codes_have_no_threshold(self, code: str):
        """ELITE/MAS/PROMO no disparan warning de tiempo (categorías adultas)."""
        assert _anomaly_threshold_for(code) is None

    def test_unknown_code_returns_none(self):
        assert _anomaly_threshold_for("FOOBAR") is None
        assert _anomaly_threshold_for("") is None
        assert _anomaly_threshold_for(None) is None  # type: ignore[arg-type]


# ===========================================================================
# 4. Warnings de tiempo anómalo por tier — emisión en `ingest_event`
# ===========================================================================


class TestAnomalousTimeWarnings:
    """Verifica que los warnings se emiten cuando un tiempo está bajo umbral."""

    @pytest.mark.asyncio
    async def test_teteros_sub_2min_anomalous(self, fake_session):
        """TET_SP con 1:00 → warning (umbral 2 min)."""
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta(),
            results_by_category={
                "TET_SP": [_row(1, "1400", "X", "Club X", "0:00:55", 40)],
            },
            ingested_by_user_id=1,
        )
        anom = [w for w in report.warnings if "tiempo_anomalo" in w]
        assert len(anom) == 1
        assert "bib=1400" in anom[0]
        assert "cat=TET_SP" in anom[0]

    @pytest.mark.asyncio
    async def test_preinfantil_sub_5min_anomalous(self, fake_session):
        """PRE_A con 4 min → warning (umbral 5 min)."""
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta(),
            results_by_category={
                "PRE_A": [_row(1, "800", "X", "Club X", "0:04:00", 40)],
            },
            ingested_by_user_id=1,
        )
        anom = [w for w in report.warnings if "tiempo_anomalo" in w]
        assert len(anom) == 1
        assert "cat=PRE_A" in anom[0]

    @pytest.mark.asyncio
    async def test_prejuvenil_sub_25min_anomalous(self, fake_session):
        """PJUV_A con 20 min → warning (umbral 25 min)."""
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta(),
            results_by_category={
                "PJUV_A": [_row(1, "600", "X", "Club X", "0:20:00", 40)],
            },
            ingested_by_user_id=1,
        )
        anom = [w for w in report.warnings if "tiempo_anomalo" in w]
        assert len(anom) == 1
        assert "cat=PJUV_A" in anom[0]

    @pytest.mark.asyncio
    async def test_junior_sub_25min_anomalous(self, fake_session):
        """JUN_M con 24 min → warning."""
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta(),
            results_by_category={
                "JUN_M": [_row(1, "100", "X", "Club X", "0:24:00", 40)],
            },
            ingested_by_user_id=1,
        )
        anom = [w for w in report.warnings if "tiempo_anomalo" in w]
        assert len(anom) == 1

    @pytest.mark.asyncio
    async def test_elite_no_warning_at_low_time(self, fake_session):
        """ELITE_M con 10 min — sin warning (ELITE no tiene umbral)."""
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta(),
            results_by_category={
                "ELITE_M": [_row(1, "1", "X", "Club X", "0:10:00", 40)],
            },
            ingested_by_user_id=1,
        )
        anom = [w for w in report.warnings if "tiempo_anomalo" in w]
        assert len(anom) == 0

    @pytest.mark.asyncio
    async def test_promo_no_warning_at_low_time(self, fake_session):
        """PROMO con 5 min — sin warning."""
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta(),
            results_by_category={
                "PROMO": [_row(1, "1300", "X", "Club X", "0:05:00", 40)],
            },
            ingested_by_user_id=1,
        )
        anom = [w for w in report.warnings if "tiempo_anomalo" in w]
        assert len(anom) == 0

    @pytest.mark.asyncio
    async def test_dnf_does_not_trigger_warning(self, fake_session):
        """Un DNF (status != FINISHED) no debe disparar warning de tiempo."""
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta(),
            results_by_category={
                "INF_A": [_row(1, "401", "X", "Club X", "DNF", 1)],
            },
            ingested_by_user_id=1,
        )
        anom = [w for w in report.warnings if "tiempo_anomalo" in w]
        assert len(anom) == 0

    @pytest.mark.asyncio
    async def test_invalid_time_emits_unparseable_warning(self, fake_session):
        """Tiempo no-parseable (ej. ``BADFORMAT``) → warning + fila no inserta."""
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta(),
            results_by_category={
                "INF_A": [_row(1, "401", "X", "Club X", "BADFORMAT", 5)],
            },
            ingested_by_user_id=1,
        )
        unparse = [w for w in report.warnings if "tiempo_no_parseable" in w]
        assert len(unparse) == 1
        assert "bib=401" in unparse[0]
        assert "cat=INF_A" in unparse[0]
        # Y el race_result NO se insertó
        assert len(fake_session.store.results) == 0


# ===========================================================================
# 5. Sex derivation — casos no cubiertos
# ===========================================================================


class TestDeriveSexAdditional:
    """Cubre las ramas restantes de ``_derive_sex_from_code``."""

    def test_jun_m_is_male(self):
        from app.models.race_competitor import CompetitorSex
        assert _derive_sex_from_code("JUN_M") == CompetitorSex.M

    def test_elite_m_is_male(self):
        from app.models.race_competitor import CompetitorSex
        assert _derive_sex_from_code("ELITE_M") == CompetitorSex.M

    def test_pjuv_a_is_male(self):
        from app.models.race_competitor import CompetitorSex
        assert _derive_sex_from_code("PJUV_A") == CompetitorSex.M

    def test_pjuv_a_f_is_female(self):
        from app.models.race_competitor import CompetitorSex
        assert _derive_sex_from_code("PJUV_A_F") == CompetitorSex.F

    def test_mas_d_is_male(self):
        from app.models.race_competitor import CompetitorSex
        assert _derive_sex_from_code("MAS_D") == CompetitorSex.M

    def test_random_prefix_returns_none(self):
        assert _derive_sex_from_code("XYZ_M") is None
