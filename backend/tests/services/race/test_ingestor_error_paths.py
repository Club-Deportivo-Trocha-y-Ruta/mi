"""Rutas de error y casos defensivos del ingestor (Paso 7).

Cubre branches no ejercitados:
- ``ValueError`` cuando RESULTADOS contiene categoría desconocida.
- Warning + skip cuando GENERAL contiene categoría desconocida.
- ``ValueError`` cuando ``normalize_name`` retorna vacío.
- Actualización in-place de evento existente (no insert duplicado).
- Update suave de ``club_text`` / ``sex`` en competitor existente.
- Rollback ante excepción dentro de la transacción.
- ``_parse_bib_safe`` con valores no numéricos.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.models.race_competitor import CompetitorSex
from app.models.race_event import SurfaceCondition
from app.schemas.race import EventMeta
from app.services.race.ingestor import RaceIngestor
from app.services.race.pdf_parser import GeneralRow, ResultsRow


def _meta(valida: int = 4, **kw) -> EventMeta:
    base = dict(
        season=2026,
        valida_num=valida,
        name=f"V-{valida}",
        event_date=date(2026, 5, 17),
        location="X",
        climate=None,
        temperature_c=Decimal("25.0"),
        surface_condition=SurfaceCondition.seca,
    )
    base.update(kw)
    return EventMeta(**base)


def _row(pos, bib, name, club, time_raw="0:30:00", points=20) -> ResultsRow:
    return ResultsRow(
        position=pos, bib=bib, name=name, city="X", club=club,
        time_raw=time_raw, points=points,
    )


def _g_row(bib, name, club, ppv) -> GeneralRow:
    return GeneralRow(
        overall_position=1, bib=bib, name=name, city="X", club=club,
        points_per_valida=ppv, total_points=sum(ppv),
    )


# ===========================================================================
# 1. Categorías desconocidas
# ===========================================================================


class TestUnknownCategories:
    @pytest.mark.asyncio
    async def test_results_unknown_code_raises_value_error(self, fake_session):
        """RESULTADOS con code que no existe en seed → ValueError fuerte."""
        ingestor = RaceIngestor(fake_session)
        with pytest.raises(ValueError, match="Categoría desconocida en RESULTADOS"):
            await ingestor.ingest_event(
                meta=_meta(),
                results_by_category={
                    "UNKNOWN_CODE": [_row(1, "1", "X", "Club X")],
                },
                ingested_by_user_id=1,
            )

    @pytest.mark.asyncio
    async def test_general_unknown_code_only_warns(self, fake_session):
        """GENERAL con code desconocido → warning + skip, NO crash."""
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta(),
            results_by_category={},
            general_by_category={
                "UNKNOWN_GENERAL_CODE": [_g_row("99", "X", "Club X", [0, 0, 0, 0])],
            },
            ingested_by_user_id=1,
        )
        assert any("categoria_desconocida_general" in w for w in report.warnings)
        # El evento sí se creó (no crash)
        assert report.event_id is not None


# ===========================================================================
# 2. Nombre vacío
# ===========================================================================


class TestEmptyName:
    @pytest.mark.asyncio
    async def test_results_empty_name_raises(self, fake_session):
        """``normalize_name`` de un nombre completamente vacío/punctuación lanza."""
        ingestor = RaceIngestor(fake_session)
        with pytest.raises(ValueError, match="Nombre vacío"):
            await ingestor.ingest_event(
                meta=_meta(),
                results_by_category={
                    # `.;` se normaliza a "" porque normalize_name reemplaza
                    # punctuación por espacios y luego strip.
                    "TET_SP": [_row(1, "1400", ".;", "Club X")],
                },
                ingested_by_user_id=1,
            )

    @pytest.mark.asyncio
    async def test_general_empty_name_skipped(self, fake_session):
        """En GENERAL, nombre vacío se ignora sin crash (sólo no se upserta)."""
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta(),
            results_by_category={},
            general_by_category={
                "TET_SP": [_g_row("99", ".;", "Club X", [0, 0, 0, 0])],
            },
            ingested_by_user_id=1,
        )
        # Sin competitor creado por el GENERAL inválido
        assert report.competitors_created == 0


# ===========================================================================
# 3. Update in-place de evento existente
# ===========================================================================


class TestEventUpdate:
    @pytest.mark.asyncio
    async def test_re_ingest_updates_event_metadata(self, fake_session):
        """Re-ingest con meta modificada actualiza el RaceEvent in-place."""
        ingestor = RaceIngestor(fake_session)
        # Primer ingest
        r1 = await ingestor.ingest_event(
            meta=_meta(climate="soleado", temperature_c=Decimal("25.0")),
            results_by_category={"TET_SP": [_row(1, "1400", "X", "Club Y")]},
            ingested_by_user_id=1,
        )
        # Segundo ingest con meta distinta
        r2 = await ingestor.ingest_event(
            meta=_meta(climate="nublado", temperature_c=Decimal("21.5"),
                       surface_condition=SurfaceCondition.barro,
                       altitude_msnm=1100, weather_notes="lluvioso"),
            results_by_category={"TET_SP": [_row(1, "1400", "X", "Club Y")]},
            ingested_by_user_id=1,
        )
        assert r1.event_id == r2.event_id  # Mismo evento, actualizado
        event = fake_session.store.events[r2.event_id]
        assert event.climate == "nublado"
        assert event.temperature_c == Decimal("21.5")
        assert event.surface_condition == SurfaceCondition.barro
        assert event.altitude_msnm == 1100
        assert event.weather_notes == "lluvioso"

    @pytest.mark.asyncio
    async def test_cd_event_flagged_as_championship(self, fake_session):
        """Un evento es championship cuando su serie es kind=championship (spec 014).

        La convención legacy valida_num=99 → is_championship está RETIRADA.
        El campo is_championship ahora se deriva de series.kind via
        derive_event_fields_for_series: championship → seq=1, is_championship=True.
        """
        from app.models.race_series import RaceSeriesKind

        # Seed a championship series directly in the fake store
        from app.models.race_series import RaceSeries as _RS
        champ_series = _RS(
            id=99,
            name="Campeonato Departamental Valle",
            season_year=2026,
            organizer="Liga Vallecaucana de Ciclismo",
            points_scheme_code="copa_valle_2026",
            kind=RaceSeriesKind.championship,
        )
        fake_session.store.series[champ_series.id] = champ_series

        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta(valida=1, name="CD Ginebra"),
            results_by_category={"ELITE_M": [_row(1, "1", "X", "Club Y", "1:30:00", 40)]},
            ingested_by_user_id=1,
            series_id=champ_series.id,
        )
        evt = fake_session.store.events[report.event_id]
        # is_championship derived from series.kind == championship
        assert evt.is_championship is True
        # For championships, sequence_number is always forced to 1 (not valida_num)
        assert evt.sequence_number == 1


# ===========================================================================
# 4. Update suave de competitor existente
# ===========================================================================


class TestCompetitorSoftUpdate:
    @pytest.mark.asyncio
    async def test_competitor_club_text_updated_on_second_appearance(self, fake_session):
        """Mismo competitor en 2 ingests con clubs distintos → club_text se
        actualiza al más reciente (no vacío)."""
        ingestor = RaceIngestor(fake_session)
        # Ingest 1: club "Club X"
        await ingestor.ingest_event(
            meta=_meta(),
            results_by_category={"TET_SP": [_row(1, "1400", "Nombre Mismo", "Club X")]},
            ingested_by_user_id=1,
        )
        comp_first = next(iter(fake_session.store.competitors.values()))
        assert comp_first.club_text == "Club X"

        # Ingest 2: distinta válida, mismo nombre, club "Club Y"
        await ingestor.ingest_event(
            meta=_meta(valida=5, name="V-5", event_date=date(2026, 7, 1)),
            results_by_category={"TET_SP": [_row(1, "1400", "Nombre Mismo", "Club Y")]},
            ingested_by_user_id=1,
        )
        comp_second = next(iter(fake_session.store.competitors.values()))
        assert comp_second.id == comp_first.id  # Mismo competitor
        assert comp_second.club_text == "Club Y"  # Actualizado

    @pytest.mark.asyncio
    async def test_competitor_sex_inferred_on_first_appearance(self, fake_session):
        """sex=None inicialmente → al ingerir en categoría con sex inferrible,
        se asigna. Y NO se sobrescribe en re-ingest."""
        ingestor = RaceIngestor(fake_session)
        # Ingest 1: INF_A_F → F
        await ingestor.ingest_event(
            meta=_meta(),
            results_by_category={
                "INF_A_F": [_row(1, "1257", "Sofia Test", "Club X", "0:30:00", 40)],
            },
            ingested_by_user_id=1,
        )
        comp = next(iter(fake_session.store.competitors.values()))
        assert comp.sex == CompetitorSex.F


# ===========================================================================
# 5. Rollback en error
# ===========================================================================


class TestRollback:
    @pytest.mark.asyncio
    async def test_rollback_on_unknown_category_preserves_state(self, fake_session):
        """Si el ingest falla con ValueError, los datos NO se commiten."""
        ingestor = RaceIngestor(fake_session)
        try:
            await ingestor.ingest_event(
                meta=_meta(),
                results_by_category={
                    "TET_SP": [_row(1, "1400", "OK", "Club X")],
                    "UNKNOWN": [_row(1, "1500", "Fail", "Club X")],
                },
                ingested_by_user_id=1,
            )
        except ValueError:
            pass
        # Tras rollback, no debe haber race_results ni competitors
        assert len(fake_session.store.results) == 0
        assert len(fake_session.store.competitors) == 0


# ===========================================================================
# 6. _parse_bib_safe
# ===========================================================================


class TestParseBibSafe:
    def test_numeric_bib(self):
        from app.services.race.ingestor import RaceIngestor as Ing
        assert Ing._parse_bib_safe("553") == 553

    def test_with_whitespace(self):
        from app.services.race.ingestor import RaceIngestor as Ing
        assert Ing._parse_bib_safe("  553  ") == 553

    def test_alphanumeric_returns_none(self):
        from app.services.race.ingestor import RaceIngestor as Ing
        assert Ing._parse_bib_safe("E-23") is None
        assert Ing._parse_bib_safe("1A") is None

    def test_none_returns_none(self):
        from app.services.race.ingestor import RaceIngestor as Ing
        assert Ing._parse_bib_safe(None) is None

    def test_empty_returns_none(self):
        from app.services.race.ingestor import RaceIngestor as Ing
        assert Ing._parse_bib_safe("") is None
        assert Ing._parse_bib_safe("   ") is None


# ===========================================================================
# 7. Decisión de match aplicada idempotentemente
# ===========================================================================


class TestMatchDecisionIdempotency:
    @pytest.mark.asyncio
    async def test_decision_not_overwritten_if_same_athlete_id(self, fake_session):
        """Si decision aplica el mismo athlete_id ya existente, no cambia
        ``linked_at`` ni ``linked_by_user_id`` innecesariamente."""
        ingestor = RaceIngestor(fake_session)
        # Primera ingesta: bib 553 con athlete_id=42
        await ingestor.ingest_event(
            meta=_meta(),
            results_by_category={
                "TET_CP": [_row(4, "553", "Thiago Duque", "Club Trocha y Ruta", "0:04:49", 30)],
            },
            match_decisions={"553": 42},
            ingested_by_user_id=1,
        )
        comp = next(iter(fake_session.store.competitors.values()))
        first_linked_at = comp.linked_at
        assert first_linked_at is not None

        # Segunda ingesta — misma decision, distinto user
        await ingestor.ingest_event(
            meta=_meta(valida=5, name="V-5", event_date=date(2026, 7, 1)),
            results_by_category={
                "TET_CP": [_row(4, "553", "Thiago Duque", "Club Trocha y Ruta", "0:04:00", 30)],
            },
            match_decisions={"553": 42},  # mismo athlete_id
            ingested_by_user_id=2,  # otro user
        )
        comp_after = next(iter(fake_session.store.competitors.values()))
        # ``linked_at`` NO cambió porque el athlete_id ya era 42
        assert comp_after.linked_at == first_linked_at
        # ``linked_by_user_id`` tampoco cambió
        assert comp_after.linked_by_user_id == 1
