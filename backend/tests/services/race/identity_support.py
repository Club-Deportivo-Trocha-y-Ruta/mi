"""Soporte compartido de las pruebas de identidad (feature 044, US4).

Motor aiosqlite en memoria con el subconjunto de tablas que tocan el
resolver, la revisión de identidad y el ingestor, más helpers para sembrar
categorías, ingestar filas sintéticas y crear imports en staging.

Todos los nombres son sintéticos y evidentemente ficticios ("Ana Prueba
Uno"); ninguno corresponde a un menor real (Ley 1581).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.race_category import RaceCategory
from app.models.race_event import SurfaceCondition
from app.models.race_import import RaceImport, RaceImportKind, RaceImportStatus
from app.models.race_series import RaceSeries
from app.models.user import UserRole
from app.schemas.race import EventMeta
from app.services.race.ingestor import RaceIngestor
from app.services.race.pdf_parser import ResultsRow
from tests.helpers.audit_tables import AUDIT_TABLES
from tests.services.race.conftest import _SEED_CATEGORIES

IDENTITY_TABLES = [
    "users",
    "race_series",
    "race_events",
    "race_categories",
    "race_competitors",
    "race_identity_candidates",
    "race_competitor_signatures",
    "race_results",
    "race_imports",
    "race_competitor_link_audit",
    *AUDIT_TABLES,
]


async def make_engine(path: str = ":memory:") -> AsyncEngine:
    """Motor aiosqlite con las tablas de identidad. ``path`` distinto de
    ``:memory:`` crea un archivo (para sesiones realmente independientes)."""
    if path == ":memory:":
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
    else:
        engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    tables = [Base.metadata.tables[t] for t in IDENTITY_TABLES]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        for code, label, sex, age_min, age_max, tier, sort_order in _SEED_CATEGORIES:
            db.add(
                RaceCategory(
                    code=code, label=label, sex=sex, age_min=age_min, age_max=age_max,
                    tier=tier, sort_order=sort_order, is_active=True,
                )
            )
        await db.commit()
    return engine


def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def actor(user_id: int = 7) -> SimpleNamespace:
    """Actor mínimo para ``record_audit`` (solo lee ``id`` y ``role``)."""
    return SimpleNamespace(id=user_id, role=UserRole.coach)


def row(
    name: str,
    *,
    club: str = "Club Sintetico Norte",
    city: str = "Ciudad Uno",
    bib: str = "101",
    position: int = 1,
    time_raw: str = "0:40:00",
    points: int = 40,
) -> ResultsRow:
    return ResultsRow(
        position=position, bib=bib, name=name, city=city, club=club,
        time_raw=time_raw, points=points,
    )


def meta(season: int, valida: int) -> EventMeta:
    return EventMeta(
        season=season,
        valida_num=valida,
        name=f"Valida {valida}",
        event_date=date(season, 3, valida),
        location="Pista sintetica",
        climate=None,
        temperature_c=Decimal("24.0"),
        surface_condition=SurfaceCondition.seca,
    )


async def ingest(
    db: AsyncSession,
    season: int,
    valida: int,
    rows_by_code: dict[str, list[ResultsRow]],
    *,
    sha: Optional[str] = None,
    decisions: Optional[dict[str, Optional[int]]] = None,
    dry_run: bool = False,
):
    return await RaceIngestor(db).ingest_event(
        meta=meta(season, valida),
        results_by_category=rows_by_code,
        match_decisions=decisions,
        pdf_results_sha256=sha,
        ingested_by_user_id=1,
        dry_run=dry_run,
    )


async def series_for(db: AsyncSession, season: int) -> RaceSeries:
    """La serie Copa Valle de la temporada (la crea como el ingestor)."""
    from sqlalchemy import select

    found = (
        await db.execute(select(RaceSeries).where(RaceSeries.season_year == season))
    ).scalars().first()
    if found is not None:
        return found
    series = RaceSeries(
        name="Copa Valle de Ciclomontañismo",
        season_year=season,
        points_scheme_code="copa_valle_2026",
    )
    db.add(series)
    await db.flush()
    return series


async def stage_import(
    db: AsyncSession, season: int, valida: int, *, sha: str
) -> RaceImport:
    """Import en staging (``pending``), como lo deja ``/parse``."""
    series = await series_for(db, season)
    imp = RaceImport(
        filename=f"valida_{valida}.pdf",
        sha256=sha,
        series_id=series.id,
        status=RaceImportStatus.pending,
        kind=RaceImportKind.resultados,
        stats_json={},
        imported_by_user_id=1,
        parse_meta_json={"header": {"season": season, "valida_num": valida}},
    )
    db.add(imp)
    await db.flush()
    return imp


def loader_for(rows_by_import: dict[int, dict[str, list[ResultsRow]]]):
    """``rows_loader`` de prueba: filas por id de import; ``KeyError`` →
    import ilegible."""

    async def _load(imp: RaceImport):
        return rows_by_import[imp.id]

    return _load
