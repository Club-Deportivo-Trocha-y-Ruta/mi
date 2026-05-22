"""Ingestor transaccional de resultados Copa Valle XCO.

Orquesta el flujo completo de persistencia tras parser + matcher:

1. **Upsert ``RaceSeries``** por ``(name, season_year)``.
2. **Upsert ``RaceEvent``** por ``(series_id, sequence_number)``.
3. **Idempotencia por SHA256**: si ``RaceImport`` ya está ``committed`` con
   el mismo sha256 del PDF RESULTADOS, abortamos retornando un IngestReport
   informativo sin escribir filas.
4. **GENERAL primero**: upsert de ``RaceCompetitor`` para todos los corredores
   del acumulado de temporada (esto pre-llena el catálogo TyR aunque no hayan
   corrido la válida actual — edge-cases.md §4.12).
5. **RESULTADOS**: upsert de cada corredor + insert de ``RaceResult`` con
   manejo de UNIQUE ``(event_id, category_id, competitor_id)``.
6. **Match decisions**: solo si ``is_trocha_y_ruta(row.club)``, aplicamos
   el ``athlete_id`` confirmado por el coach (no auto-asignación).
7. **Commit único** al final; cualquier excepción → rollback completo.

Restricciones inviolables (CLAUDE.md + workflow §4):
- Privacidad menores: warnings usan ``bib`` + ``category_code``, nunca nombres.
- Nunca auto-asigna ``athlete_id``: solo aplica decisiones del coach.
- Tiempo anómalo (< 25 min en tiers menores/juvenil) genera warning, NO bloquea.

Convenciones de schema (Paso 2):
- ``RaceResult.race_time_ms`` en milisegundos (NO segundos).
- ``RaceCompetitor.normalized_name`` es UNIQUE — el upsert se hace por allí.
- ``RaceImport`` usa enum ``RaceImportStatus.{pending, dry_run, committed, failed}``.
- ``RaceResult.created_by_user_id`` es NOT NULL → debe pasarse ``ingested_by_user_id``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.race_category import RaceCategory
from app.models.race_competitor import CompetitorSex, RaceCompetitor
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_import import RaceImport, RaceImportStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries
from app.schemas.race import EventMeta, IngestReport
from app.services.race.normalizer import (
    is_trocha_y_ruta,
    normalize_name,
    parse_time,
)

if TYPE_CHECKING:
    from app.services.race.pdf_parser import GeneralRow, ResultsRow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Nombre canónico de la serie Copa Valle — usado en upsert ``RaceSeries``.
_SERIES_NAME = "Copa Valle de Ciclomontañismo"

#: Code default del esquema de puntos. Si no existe, se crea ``RaceSeries``
#: con este code y queda como FK lógica al ``race_points_schemes.code``.
_DEFAULT_POINTS_SCHEME_CODE = "copa_valle_2026"

#: Threshold ms POR CODE PREFIX para detectar tiempo anómalo. Teteros y
#: Preinfantil corren legítimamente < 25 min, así que el threshold genérico
#: del workflow §4 (25 min) sólo aplica a Infantil/Prejuvenil/Junior.
#: Para Teteros y Preinfantil, threshold mucho más bajo (sub-2 min) sólo
#: dispara warning sobre tiempos físicamente imposibles.
#:
#: Referencia edge-cases.md §4.2: el caso Matias Sabogal (bib 424 INF_A
#: con 0:04:33) cae bajo el bracket "INF" → < 25 min anómalo.
_ANOMALY_THRESHOLDS_MS_BY_CODE_PREFIX: dict[str, int] = {
    # Categorías "carrera larga" — < 25 min indica error de digitación.
    "INF_":  1_500_000,   # 25 min
    "PJUV_": 1_500_000,   # 25 min
    "JUN_":  1_500_000,   # 25 min
    # Categorías cortas — sólo sub-2 min son físicamente imposibles.
    "TET_":  120_000,     # 2 min
    "PRE_":  300_000,     # 5 min
}


def _anomaly_threshold_for(code: str) -> Optional[int]:
    """Threshold ms para considerar tiempo anómalo según prefijo de code.

    Retorna ``None`` si el code no aplica al warning (ej. ELITE, MAS_*, PROMO).
    """
    if not code:
        return None
    for prefix, ms in _ANOMALY_THRESHOLDS_MS_BY_CODE_PREFIX.items():
        if code.startswith(prefix):
            return ms
    return None


# ---------------------------------------------------------------------------
# Helpers — derivación de sexo desde category code
# ---------------------------------------------------------------------------


def _derive_sex_from_code(code: str) -> Optional[CompetitorSex]:
    """Infiere ``CompetitorSex`` a partir del category code observado.

    Reglas (consistentes con el seed `seed_race_categories.py`):
    - Termina en ``_F`` → ``F``.
    - Empieza con ``JUN_`` / ``ELITE_`` / ``MAS_`` y termina en ``_F`` → cubierto arriba.
    - ``MAS_F`` → ``F``.
    - ``JUN_F`` → ``F``, ``ELITE_F`` → ``F`` (cubierto por sufijo).
    - ``PROMO``, ``TET_*`` → MIXED en categoría, pero a nivel competidor
      individual no lo sabemos — devolvemos ``None`` (campo nullable en DB).
    - Resto (PRE_A, INF_B, JUN_M, ELITE_M, MAS_A..D) → ``M``.

    Si el code no se reconoce, retorna ``None``.
    """
    if not code:
        return None
    upper = code.upper()
    if upper.endswith("_F"):
        return CompetitorSex.F
    if upper.startswith("TET_") or upper == "PROMO":
        return None
    # Resto de codes son masculinos por construcción del seed
    if upper.startswith(("PRE_", "INF_", "PJUV_", "JUN_", "ELITE_", "MAS_")):
        return CompetitorSex.M
    return None


# ---------------------------------------------------------------------------
# RaceIngestor
# ---------------------------------------------------------------------------


class RaceIngestor:
    """Servicio transaccional para ingestar una válida completa.

    Uso típico (Paso 6 CLI):

    ```python
    ingestor = RaceIngestor(db)
    report = await ingestor.ingest_event(
        meta=event_meta,
        results_by_category=parsed_results,
        general_by_category=parsed_general,
        match_decisions={"553": athlete_id_thiago, "10": athlete_id_juan},
        pdf_results_sha256="abc...",
        ingested_by_user_id=coach_user.id,
    )
    print(report.model_dump_json(indent=2))
    ```

    No mantiene estado entre invocaciones — cada llamada a ``ingest_event``
    abre su propia transacción.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -------------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------------

    async def ingest_event(
        self,
        meta: EventMeta,
        results_by_category: dict[str, list["ResultsRow"]],
        general_by_category: Optional[dict[str, list["GeneralRow"]]] = None,
        match_decisions: Optional[dict[str, Optional[int]]] = None,
        *,
        pdf_results_sha256: Optional[str] = None,
        pdf_general_sha256: Optional[str] = None,
        ingested_by_user_id: int,
        dry_run: bool = False,
    ) -> IngestReport:
        """Ingest atómico de una válida completa.

        Args:
            meta: Metadata del evento (capturada CLI). Se aplica vía upsert.
            results_by_category: Output de ``parse_results_pdf``.
            general_by_category: Output de ``parse_general_pdf``. Opcional —
                si se provee, pre-llena competidores del catálogo histórico.
            match_decisions: ``{bib: athlete_id|None}`` — solo se aplican
                cuando ``is_trocha_y_ruta(row.club)``. ``None`` significa
                "skip" / "new_athlete" → ``athlete_id`` queda NULL.
            pdf_results_sha256: Si se pasa y ya existe un ``RaceImport``
                ``committed`` con el mismo hash, la ingesta aborta idempotente
                (retorna IngestReport con ``results_inserted=0``).
            pdf_general_sha256: Igual lógica para el GENERAL (solo se loggea,
                no aborta porque GENERAL no genera ``race_results``).
            ingested_by_user_id: FK NOT NULL en ``RaceResult.created_by_user_id``
                y ``RaceImport.imported_by_user_id``.
            dry_run: (F-UP2) Si True, ejecuta todo el flujo en una transacción
                que se hace **rollback al final** — no persiste resultados ni
                competidores. El ``IngestReport`` retornado contiene los conteos
                "como si" se hubiera ejecutado, con ``warnings`` enriquecido con
                un prefijo ``"DRY_RUN: no se persistieron cambios"``. El
                ``RaceImport`` previo se preserva en status ``pending`` (no
                avanza a ``committed``) para que un ``ingest_event`` posterior
                con ``dry_run=False`` y el mismo ``pdf_results_sha256`` pueda
                promoverlo. Default ``False`` (backward compat con CLI F1.7).

        Returns:
            ``IngestReport`` con conteos y warnings (sin nombres completos).
            En dry_run, los conteos reflejan lo que SE HABRÍA insertado.

        Raises:
            Cualquier excepción de DB se propaga tras rollback explícito.
            Categoría desconocida (no en seed) → ``ValueError``.
        """
        decisions: dict[str, Optional[int]] = match_decisions or {}
        warnings: list[str] = []
        competitors_created = 0
        competitors_updated = 0
        results_inserted = 0
        results_skipped = 0
        tyr_count = 0

        try:
            # --- 1. Upsert RaceSeries por (name, season_year) ----------
            series = await self._upsert_series(meta.season)

            # --- 2. Upsert RaceEvent por (series_id, sequence_number) -
            event = await self._upsert_event(series.id, meta, ingested_by_user_id)

            # --- 3. Idempotencia por SHA256 (RESULTADOS) ----------------
            race_import: Optional[RaceImport] = None
            if pdf_results_sha256:
                existing = await self._find_committed_import(pdf_results_sha256)
                if existing is not None:
                    # Abortar idempotente: no escribimos filas
                    warnings.append(
                        f"sha256 ya commiteado import_id={existing.id} "
                        f"sequence_number={meta.valida_num}"
                    )
                    if dry_run:
                        # En dry_run no commiteamos el upsert series/event tampoco.
                        warnings.insert(0, "DRY_RUN: no se persistieron cambios")
                        await self.db.rollback()
                    else:
                        await self.db.commit()  # mantener el upsert de series/event
                    return IngestReport(
                        event_id=event.id,
                        series_id=series.id,
                        competitors_created=0,
                        competitors_updated=0,
                        results_inserted=0,
                        results_skipped=0,
                        tyr_count=0,
                        warnings=warnings,
                    )

                # F-UP2: en dry_run buscamos un RaceImport pending previo (creado
                # por el endpoint /parse). Si existe, lo reusamos sin promoverlo.
                # En commit (dry_run=False), también lo reusamos pero lo promovemos
                # a committed al final. Si no existe, lo creamos (compat CLI F1.7).
                race_import = await self._find_pending_import(pdf_results_sha256)
                if race_import is None:
                    race_import = RaceImport(
                        filename=meta.pdf_results_filename or f"valida_{meta.valida_num}_resultados.pdf",
                        sha256=pdf_results_sha256,
                        series_id=series.id,
                        status=RaceImportStatus.pending,
                        stats_json={},
                        imported_by_user_id=ingested_by_user_id,
                    )
                    self.db.add(race_import)
                    await self.db.flush()

            # --- 4. Catálogo de categorías cacheado (un lookup por code) -
            category_cache: dict[str, RaceCategory] = await self._load_category_cache()

            # --- 5. GENERAL primero — upsert competidores acumulados ----
            if general_by_category:
                for code, rows in general_by_category.items():
                    category = category_cache.get(code)
                    if category is None:
                        # Code desconocido (no en seed). No bloqueamos GENERAL pero loggeamos.
                        warnings.append(
                            f"categoria_desconocida_general code={code} rows={len(rows)}"
                        )
                        continue
                    for row in rows:
                        created = await self._upsert_competitor_from_general(
                            row, category
                        )
                        if created:
                            competitors_created += 1
                        else:
                            competitors_updated += 1

            # --- 6. RESULTADOS — upsert competidor + insert race_result -
            for code, rows in results_by_category.items():
                category = category_cache.get(code)
                if category is None:
                    raise ValueError(
                        f"Categoría desconocida en RESULTADOS: code={code!r}. "
                        f"Verificar seed `race_categories`."
                    )

                # Index de race_results existentes para idempotencia por UNIQUE
                # (no consultamos en el loop por performance; un solo select por categoría)
                existing_pairs = await self._existing_competitor_ids_for(
                    event_id=event.id, category_id=category.id
                )

                for row in rows:
                    # Upsert competitor
                    competitor, was_created = await self._upsert_competitor_from_results(
                        row, category
                    )
                    if was_created:
                        competitors_created += 1
                    else:
                        competitors_updated += 1

                    is_tyr = is_trocha_y_ruta(row.club)
                    if is_tyr:
                        tyr_count += 1
                        # Aplicar decisión del coach solo si la dio
                        decided_athlete_id = decisions.get(str(row.bib))
                        if decided_athlete_id is not None:
                            # Setear linkage en el competitor (idempotente: si ya
                            # estaba linkeado a otro athlete, lo respetamos a
                            # menos que decisión nueva diga otra cosa).
                            if competitor.athlete_id != decided_athlete_id:
                                competitor.athlete_id = decided_athlete_id
                                competitor.linked_at = datetime.now(timezone.utc)
                                competitor.linked_by_user_id = ingested_by_user_id

                    # ¿Ya existe race_result (event, category, competitor)?
                    if competitor.id in existing_pairs:
                        results_skipped += 1
                        continue

                    # Parsear tiempo / status
                    try:
                        status, race_time_ms, laps_behind = parse_time(row.time_raw)
                    except ValueError as exc:
                        warnings.append(
                            f"tiempo_no_parseable bib={row.bib} cat={code} "
                            f"raw={row.time_raw!r} err={type(exc).__name__}"
                        )
                        continue

                    # Warning tiempo anómalo (sin nombre, solo bib + code)
                    threshold_ms = _anomaly_threshold_for(code)
                    if (
                        status == ResultStatus.FINISHED
                        and race_time_ms is not None
                        and threshold_ms is not None
                        and race_time_ms < threshold_ms
                    ):
                        tier_val = category.tier.value if category.tier else "none"
                        warnings.append(
                            f"tiempo_anomalo bib={row.bib} cat={code} "
                            f"time_ms={race_time_ms} tier={tier_val}"
                        )

                    # Construir RaceResult
                    bib_int = self._parse_bib_safe(row.bib)
                    athlete_id_to_persist = competitor.athlete_id if is_tyr else None
                    laps_behind_val = laps_behind if laps_behind > 0 else None

                    race_result = RaceResult(
                        event_id=event.id,
                        category_id=category.id,
                        competitor_id=competitor.id,
                        athlete_id=athlete_id_to_persist,
                        bib_number=bib_int,
                        position=row.position,
                        status=status,
                        race_time_ms=race_time_ms,
                        laps_behind=laps_behind_val,
                        points_awarded=row.points,
                        imported_from_id=(race_import.id if race_import else None),
                        created_by_user_id=ingested_by_user_id,
                    )
                    self.db.add(race_result)
                    # Memorizar para evitar doble insert dentro del mismo loop
                    # si el PDF tuviera duplicados (defensa profundidad).
                    existing_pairs.add(competitor.id)
                    results_inserted += 1

            # --- 7. Cierre del RaceImport como committed ---------------
            # Solo promovemos a committed cuando NO es dry_run. En dry_run
            # dejamos race_import.status en `pending` para que un commit
            # posterior (mismo sha256) lo pueda promover (F-UP2/F-UP3 wizard).
            if race_import is not None and not dry_run:
                race_import.status = RaceImportStatus.committed
                race_import.stats_json = {
                    "competitors_created": competitors_created,
                    "competitors_updated": competitors_updated,
                    "results_inserted": results_inserted,
                    "results_skipped": results_skipped,
                    "tyr_count": tyr_count,
                    "warnings": len(warnings),
                }

            # FIX F-UP-REV6 BUG-1: capturar IDs SIEMPRE antes de rollback/commit
            # para evitar MissingGreenlet en el return final (lazy-load sync
            # sobre aiomysql post-rollback). El log usa los mismos locales.
            event_id_snapshot = event.id
            series_id_snapshot = series.id

            if dry_run:
                # F-UP2: rollback al final para no persistir competitors,
                # results, ni el avance de status del RaceImport. El upsert
                # de series/event tampoco persiste — pero los IDs in-memory
                # del IngestReport reflejan lo que SE HABRÍA insertado.
                warnings.insert(0, "DRY_RUN: no se persistieron cambios")
                await self.db.rollback()
                logger.info(
                    "race_ingest_dry_run event_id_preview=%s series_id_preview=%s "
                    "results_would_insert=%d tyr_count=%d warnings=%d",
                    event_id_snapshot,
                    series_id_snapshot,
                    results_inserted,
                    tyr_count,
                    len(warnings),
                )
            else:
                await self.db.commit()
                logger.info(
                    "race_ingest_ok event_id=%s series_id=%s results_inserted=%d "
                    "results_skipped=%d tyr_count=%d warnings=%d",
                    event_id_snapshot,
                    series_id_snapshot,
                    results_inserted,
                    results_skipped,
                    tyr_count,
                    len(warnings),
                )
            return IngestReport(
                event_id=event_id_snapshot,
                series_id=series_id_snapshot,
                competitors_created=competitors_created,
                competitors_updated=competitors_updated,
                results_inserted=results_inserted,
                results_skipped=results_skipped,
                tyr_count=tyr_count,
                warnings=warnings,
            )

        except Exception:
            await self.db.rollback()
            raise

    # -------------------------------------------------------------------
    # Helpers internos — series / event / import
    # -------------------------------------------------------------------

    async def _upsert_series(self, season: int) -> RaceSeries:
        """Upsert ``RaceSeries`` por ``(name=_SERIES_NAME, season_year=season)``."""
        result = await self.db.execute(
            select(RaceSeries).where(
                RaceSeries.name == _SERIES_NAME,
                RaceSeries.season_year == season,
            )
        )
        series = result.scalar_one_or_none()
        if series is not None:
            return series
        series = RaceSeries(
            name=_SERIES_NAME,
            season_year=season,
            organizer="Liga Vallecaucana de Ciclismo",
            points_scheme_code=_DEFAULT_POINTS_SCHEME_CODE,
        )
        self.db.add(series)
        await self.db.flush()
        return series

    async def _upsert_event(
        self, series_id: int, meta: EventMeta, user_id: int
    ) -> RaceEvent:
        """Upsert ``RaceEvent`` por ``(series_id, sequence_number=valida_num)``.

        Actualiza todos los campos de ``meta`` si el evento ya existía — la
        idea es que el coach pueda corregir clima/superficie y reingestar el
        PDF sin tener que tocar SQL.
        """
        result = await self.db.execute(
            select(RaceEvent).where(
                RaceEvent.series_id == series_id,
                RaceEvent.sequence_number == meta.valida_num,
            )
        )
        event = result.scalar_one_or_none()
        if event is None:
            event = RaceEvent(
                series_id=series_id,
                sequence_number=meta.valida_num,
                name=meta.name,
                event_date=meta.event_date,
                location=meta.location,
                is_championship=(meta.valida_num == 99),
                status=RaceEventStatus.COMPLETED,
                created_by_user_id=user_id,
                climate=meta.climate,
                temperature_c=meta.temperature_c,
                surface_condition=meta.surface_condition,
                altitude_msnm=meta.altitude_msnm,
                weather_notes=meta.weather_notes,
                pdf_results_filename=meta.pdf_results_filename,
                pdf_general_filename=meta.pdf_general_filename,
            )
            self.db.add(event)
            await self.db.flush()
            return event

        # Update in place
        event.name = meta.name
        event.event_date = meta.event_date
        event.location = meta.location
        event.is_championship = (meta.valida_num == 99)
        event.status = RaceEventStatus.COMPLETED
        if meta.climate is not None:
            event.climate = meta.climate
        if meta.temperature_c is not None:
            event.temperature_c = meta.temperature_c
        if meta.surface_condition is not None:
            event.surface_condition = meta.surface_condition
        if meta.altitude_msnm is not None:
            event.altitude_msnm = meta.altitude_msnm
        if meta.weather_notes is not None:
            event.weather_notes = meta.weather_notes
        if meta.pdf_results_filename is not None:
            event.pdf_results_filename = meta.pdf_results_filename
        if meta.pdf_general_filename is not None:
            event.pdf_general_filename = meta.pdf_general_filename
        await self.db.flush()
        return event

    async def _find_committed_import(self, sha256: str) -> Optional[RaceImport]:
        """Busca un ``RaceImport`` con ``status=committed`` y sha256 dado."""
        result = await self.db.execute(
            select(RaceImport).where(
                RaceImport.sha256 == sha256,
                RaceImport.status == RaceImportStatus.committed,
            )
        )
        return result.scalar_one_or_none()

    async def _find_pending_import(self, sha256: str) -> Optional[RaceImport]:
        """Busca un ``RaceImport`` con ``status=pending`` y sha256 dado (F-UP2).

        Usado por el flow upload UI: el endpoint ``/parse`` crea un pending row
        en su propia transacción; luego ``/dry-run`` y ``/commit`` reusan el
        mismo row (sin duplicar). Si el row existe pero está en otro estado
        (dry_run / committed / failed), devolvemos None y el ingestor decidirá
        crear uno nuevo o abortar idempotente.
        """
        # FIX F-UP-REV6 BUG-2: order_by id DESC + limit 1 evita
        # MultipleResultsFound si por race condition existen 2 pending
        # con mismo SHA (no hay UNIQUE constraint sha256+status).
        result = await self.db.execute(
            select(RaceImport)
            .where(
                RaceImport.sha256 == sha256,
                RaceImport.status == RaceImportStatus.pending,
            )
            .order_by(RaceImport.id.desc())
            .limit(1)
        )
        return result.scalars().first()

    # -------------------------------------------------------------------
    # Helpers internos — categorías + competidores
    # -------------------------------------------------------------------

    async def _load_category_cache(self) -> dict[str, RaceCategory]:
        """Carga las 26 categorías en un dict ``{code: RaceCategory}``."""
        result = await self.db.execute(select(RaceCategory))
        return {c.code: c for c in result.scalars().all()}

    async def _existing_competitor_ids_for(
        self, *, event_id: int, category_id: int
    ) -> set[int]:
        """Devuelve los ``competitor_id`` que ya tienen ``race_result`` para
        este ``(event_id, category_id)`` — usado para detectar colisión
        UNIQUE sin esperar a IntegrityError.
        """
        result = await self.db.execute(
            select(RaceResult.competitor_id).where(
                RaceResult.event_id == event_id,
                RaceResult.category_id == category_id,
            )
        )
        return set(result.scalars().all())

    async def _upsert_competitor_from_results(
        self, row: "ResultsRow", category: RaceCategory
    ) -> tuple[RaceCompetitor, bool]:
        """Upsert por ``normalized_name`` desde una ``ResultsRow``.

        Retorna ``(competitor, was_created)``. ``was_created=True`` si insertamos
        fila nueva; ``False`` si reusamos existente (y posiblemente actualizamos
        club_text/sex).
        """
        normalized = normalize_name(row.name)
        if not normalized:
            # Nombre vacío post-normalización: no debería ocurrir, defensivo.
            raise ValueError(
                f"Nombre vacío post-normalización bib={row.bib} cat={category.code}"
            )

        result = await self.db.execute(
            select(RaceCompetitor).where(RaceCompetitor.normalized_name == normalized)
        )
        competitor = result.scalar_one_or_none()
        sex_from_code = _derive_sex_from_code(category.code)

        if competitor is not None:
            # Update suave: preferimos club_text reciente si no es vacío
            from app.services.race.normalizer import normalize_club

            club_norm = normalize_club(row.club)
            if club_norm and competitor.club_text != row.club:
                competitor.club_text = row.club
            if competitor.sex is None and sex_from_code is not None:
                competitor.sex = sex_from_code
            return competitor, False

        # Nuevo competidor
        competitor = RaceCompetitor(
            normalized_name=normalized,
            display_name=row.name.strip(),
            club_text=row.club or None,
            sex=sex_from_code,
        )
        self.db.add(competitor)
        await self.db.flush()
        return competitor, True

    async def _upsert_competitor_from_general(
        self, row: "GeneralRow", category: RaceCategory
    ) -> bool:
        """Upsert desde GENERAL. No retorna el objeto — solo informa si creó.

        Razón: el GENERAL no genera ``race_results``; solo nos interesa
        pre-llenar el catálogo histórico de competidores (edge-cases §4.12).
        """
        normalized = normalize_name(row.name)
        if not normalized:
            return False

        result = await self.db.execute(
            select(RaceCompetitor).where(RaceCompetitor.normalized_name == normalized)
        )
        competitor = result.scalar_one_or_none()
        sex_from_code = _derive_sex_from_code(category.code)

        if competitor is not None:
            from app.services.race.normalizer import normalize_club

            club_norm = normalize_club(row.club)
            if club_norm and competitor.club_text != row.club:
                competitor.club_text = row.club
            if competitor.sex is None and sex_from_code is not None:
                competitor.sex = sex_from_code
            return False

        competitor = RaceCompetitor(
            normalized_name=normalized,
            display_name=row.name.strip(),
            club_text=row.club or None,
            sex=sex_from_code,
        )
        self.db.add(competitor)
        await self.db.flush()
        return True

    # -------------------------------------------------------------------
    # Helpers internos — parsing defensivo
    # -------------------------------------------------------------------

    @staticmethod
    def _parse_bib_safe(bib_raw: str) -> Optional[int]:
        """Convierte ``bib`` (str del PDF) a ``int`` o ``None`` si no es numérico.

        El schema actual usa ``SmallInteger`` para ``bib_number`` (edge-cases
        §4.8 confirma todos numéricos en V-IV). Si una válida futura usa
        dorsales alfanuméricos, este método debe migrarse junto con la columna.
        """
        if bib_raw is None:
            return None
        s = str(bib_raw).strip()
        if not s.isdigit():
            return None
        try:
            return int(s)
        except (TypeError, ValueError):
            return None
