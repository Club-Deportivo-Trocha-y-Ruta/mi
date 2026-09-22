"""T058 (feature 044, US5, research R-15) — la temporada 2026 no cambia.

``contracts/historical-load.md`` §"Current season untouched" (FR-029): todo
query del stack de carreras ya filtra por ``season_year`` — este test lo
prueba a nivel de servicio (no del pipeline LangGraph completo, que no corre
en esta suite offline): con dos temporadas históricas (2024, 2025) cargadas,
las consultas que alimentan ``GET /evolution`` y el contexto del analista IA
(``queries.fetch_results_for_athlete`` / ``fetch_all_results_for_season``) y
la clasificación (``standings.get_event_standings``) de la válida 2026 dan
exactamente el mismo resultado que sin ellas.

Usa el mismo arnés de ``tests/services/race/identity_support.py`` que
``test_identity_review.py`` — motor aiosqlite en memoria, nombres sintéticos
evidentemente ficticios.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.race_category import RaceCategory
from app.services.race import standings as standings_svc
from app.services.race.queries import (
    fetch_all_results_for_season,
    fetch_results_for_athlete,
)
from tests.services.race.identity_support import ingest, make_engine, row, session_factory

_ATHLETE_ID = 555


def _results_snapshot(results) -> list[tuple]:
    return sorted(
        (r.id, r.event_id, r.category_id, r.bib_number, r.position, r.points_awarded)
        for r in results
    )


@pytest.mark.asyncio
async def test_2026_queries_and_standings_unchanged_with_two_historical_seasons():
    engine = await make_engine()
    Session = session_factory(engine)

    async with Session() as db:
        report_2026 = await ingest(
            db, 2026, 4,
            {
                "INF_A": [
                    row("Atleta Enlazado Tyr", bib="10", position=1, points=40,
                        club="Club Trocha y Ruta"),
                    row("Rival Ajeno Uno", bib="11", position=2, points=36,
                        club="Club Sintetico Sur", city="Otra Ciudad"),
                ],
            },
            sha="sha-2026-v4",
            decisions={"10": _ATHLETE_ID},
        )
        await db.commit()
        event_id_2026 = report_2026.event_id

    async with Session() as db:
        cat = (
            await db.execute(select(RaceCategory).where(RaceCategory.code == "INF_A"))
        ).scalar_one()
        category_id = cat.id

        baseline_athlete = _results_snapshot(
            await fetch_results_for_athlete(db, _ATHLETE_ID, 2026)
        )
        baseline_season = _results_snapshot(
            await fetch_all_results_for_season(db, category_id, 2026)
        )
        baseline_standings = await standings_svc.get_event_standings(db, event_id_2026)
        baseline_standings_json = baseline_standings.model_dump_json()

    assert len(baseline_athlete) == 1
    assert len(baseline_season) == 2

    # --- Cargar dos temporadas históricas (2024, 2025) -------------------
    # Mismo code de categoría (INF_A) a propósito — es exactamente el caso
    # que probaría un filtro de temporada roto (mezclaría filas entre
    # season_year). Corredores sintéticos distintos, ningún nombre en común
    # con la válida 2026 (nada que resolver en identidad).
    async with Session() as db:
        await ingest(
            db, 2024, 3,
            {
                "INF_A": [
                    row("Historico Uno Ficticio", bib="20", position=1, points=40,
                        club="Club Historico A", city="Ciudad Historica"),
                    row("Historico Dos Ficticio", bib="21", position=2, points=36,
                        club="Club Historico B", city="Ciudad Historica"),
                ],
            },
            sha="sha-2024-v3",
        )
        await db.commit()

    async with Session() as db:
        await ingest(
            db, 2025, 7,
            {
                "INF_A": [
                    row("Historico Tres Ficticio", bib="30", position=1, points=40,
                        club="Club Historico C", city="Ciudad Historica"),
                ],
                "MAS_A": [
                    row("Historico Cuatro Ficticio", bib="31", position=1, points=40,
                        club="Club Historico D", city="Ciudad Historica"),
                ],
            },
            sha="sha-2025-v7",
        )
        await db.commit()

    # --- Re-verificar 2026: exactamente igual que antes -------------------
    async with Session() as db:
        after_athlete = _results_snapshot(
            await fetch_results_for_athlete(db, _ATHLETE_ID, 2026)
        )
        after_season = _results_snapshot(
            await fetch_all_results_for_season(db, category_id, 2026)
        )
        after_standings = await standings_svc.get_event_standings(db, event_id_2026)
        after_standings_json = after_standings.model_dump_json()

    assert after_athlete == baseline_athlete
    assert after_season == baseline_season, (
        "fetch_all_results_for_season mezcló filas de otra season_year — "
        "el filtro por temporada de la carga histórica está roto"
    )
    assert after_standings_json == baseline_standings_json
