"""Servicio para enlace retroactivo competidor↔atleta.

Resuelve el caso "coach crea atleta DESPUÉS de ingestar PDFs":

- El wizard de ingesta (``ingestor.py``) solo aplica linkage si el coach
  decide on-import. Si el ``Athlete`` aún no existía en DB durante la ingesta,
  los ``RaceResult`` correspondientes quedan con ``athlete_id IS NULL``.
- El gate ``validate_input`` del grafo race-AI (``ai/nodes/validate_input.py``)
  y las queries analíticas (``queries.py``) filtran por
  ``race_results.athlete_id == X`` → 0 rows → "Sin carreras registradas
  para temporada".
- Este servicio permite:
  1. Listar competidores con ``athlete_id IS NULL`` (con filtros opcionales).
  2. Enlazar un competidor a un atleta + **propagar el athlete_id a todos
     los race_results pendientes del competidor** (deleted_at IS NULL).
  3. Deshacer el enlace (set NULL en competitor + race_results).
  4. Sugerir top-N atletas por similitud fuzzy de nombre.

Reglas:
- Transaccional: link/unlink se hacen en una sola operación; cualquier
  excepción dispara rollback (delegado al middleware ``get_db``).
- Audit: ``linked_at`` y ``linked_by_user_id`` se setean en cada link.
- Privacidad: logs nunca incluyen nombres (CLAUDE.md restricciones inviolables).
- Idempotencia: re-linkar al mismo athlete_id retorna ``already_linked=True``
  sin escribir; intentar linkar a un athlete_id distinto retorna 409 vía
  excepción ``CompetitorAlreadyLinkedError``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from rapidfuzz import fuzz
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete import Athlete
from app.models.race_competitor import RaceCompetitor
from app.models.race_competitor_link_audit import (
    LinkAuditAction,
    RaceCompetitorLinkAudit,
)
from app.models.race_event import RaceEvent
from app.models.race_result import RaceResult
from app.models.race_series import RaceSeries
from app.services.race.matcher import MatchCandidate, _SCORE_CAP, match_athletes
from app.services.race.normalizer import is_trocha_y_ruta, normalize_club, normalize_name

logger = logging.getLogger(__name__)


# Cap defensivo para protección DoS en endpoints de sugerencias inversas
# (R3-M3). El matcher walks toda la población de competitors huérfanos y
# computa ``fuzz.token_set_ratio`` por cada uno; con 10k filas eso son
# decenas de segundos en CPU y bloquea el event loop. 1000 es 10x la
# población esperada en producción (Copa Valle suele tener ~300 huérfanos
# acumulados por temporada).
MAX_UNLINKED_COMPETITORS_TO_SCORE: int = 1000


# ---------------------------------------------------------------------------
# Excepciones de dominio
# ---------------------------------------------------------------------------


class CompetitorNotFoundError(LookupError):
    """El competitor_id no existe en race_competitors."""

    def __init__(self, competitor_id: int) -> None:
        super().__init__(f"competitor_id={competitor_id} no existe")
        self.competitor_id = competitor_id


class AthleteNotFoundError(LookupError):
    """El athlete_id no existe en athletes."""

    def __init__(self, athlete_id: int) -> None:
        super().__init__(f"athlete_id={athlete_id} no existe")
        self.athlete_id = athlete_id


class CompetitorAlreadyLinkedError(RuntimeError):
    """El competitor ya está enlazado a un athlete_id DISTINTO al solicitado.

    El caller debe responder 409 Conflict. Re-link al mismo athlete_id NO
    dispara esta excepción (es idempotente).
    """

    def __init__(self, competitor_id: int, current_athlete_id: int, requested_athlete_id: int) -> None:
        super().__init__(
            f"competitor_id={competitor_id} ya está enlazado a "
            f"athlete_id={current_athlete_id}; rechazado link a "
            f"athlete_id={requested_athlete_id}"
        )
        self.competitor_id = competitor_id
        self.current_athlete_id = current_athlete_id
        self.requested_athlete_id = requested_athlete_id


# ---------------------------------------------------------------------------
# Dataclasses de resultado
# ---------------------------------------------------------------------------


@dataclass
class LinkResult:
    competitor_id: int
    athlete_id: int
    linked_at: datetime
    linked_by_user_id: int
    results_propagated: int
    already_linked: bool


@dataclass
class UnlinkResult:
    competitor_id: int
    results_propagated: int
    was_linked: bool


@dataclass
class SuggestionView:
    """Vista UI de un candidato del matcher.

    Score expuesto en escala [0, 1] para el frontend.
    """

    athlete_id: int
    full_name: str
    score: float  # [0, 1]
    reason: str


@dataclass
class UnlinkedCompetitorRow:
    id: int
    display_name: str
    normalized_name: str
    club_text: Optional[str]
    sex: Optional[str]
    results_count: int
    seasons: list[int]
    suggestions: list[SuggestionView]


@dataclass
class CompetitorSuggestionView:
    """Vista inversa: un ``RaceCompetitor`` huérfano sugerido para un
    athlete que está siendo creado.

    Score expuesto en escala [0, 1] para el frontend. El reason incluye
    una pista textual del boost aplicado (``"+ same club"``) para que el
    coach decida con contexto.
    """

    competitor_id: int
    display_name: str
    club_text: Optional[str]
    score: float  # [0, 1]
    reason: str
    results_count: int
    seasons: list[int]


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


async def _load_competitor(db: AsyncSession, competitor_id: int) -> RaceCompetitor:
    result = await db.execute(
        select(RaceCompetitor).where(RaceCompetitor.id == competitor_id)
    )
    competitor = result.scalar_one_or_none()
    if competitor is None:
        raise CompetitorNotFoundError(competitor_id)
    return competitor


async def _load_athlete(db: AsyncSession, athlete_id: int) -> Athlete:
    result = await db.execute(select(Athlete).where(Athlete.id == athlete_id))
    athlete = result.scalar_one_or_none()
    if athlete is None:
        raise AthleteNotFoundError(athlete_id)
    return athlete


def _candidate_to_view(c: MatchCandidate) -> SuggestionView:
    """Normaliza score 0..100 → 0..1 + traduce ``reason`` a texto humano."""
    score_norm = round(c.score / 100.0, 4)
    if c.score >= 99.5:
        reason = "exact name match"
    elif c.reason == "name+age_compat":
        reason = f"fuzzy {score_norm:.2f} + edad compatible"
    elif c.reason == "name+age_incompat":
        reason = f"fuzzy {score_norm:.2f} (edad fuera de rango)"
    else:
        reason = f"fuzzy {score_norm:.2f}"
    return SuggestionView(
        athlete_id=c.athlete_id,
        full_name=c.full_name,
        score=score_norm,
        reason=reason,
    )


async def _athletes_for_suggestions(
    db: AsyncSession, club_id: Optional[int] = None
) -> list[Athlete]:
    """Carga lista de athletes candidatos para el matcher.

    Si ``club_id`` se provee, filtra. Si no, devuelve todos los athletes
    activos (el matcher se encarga del threshold).
    """
    stmt = select(Athlete)
    if club_id is not None:
        stmt = stmt.where(Athlete.club_id == club_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# API pública del servicio
# ---------------------------------------------------------------------------


async def suggest_athletes_for_competitor(
    db: AsyncSession,
    competitor_id: int,
    *,
    limit: int = 5,
    threshold: float = 70.0,
    club_id: Optional[int] = None,
) -> list[SuggestionView]:
    """Top-N candidatos para enlazar este competitor.

    Reusa ``services.race.matcher.match_athletes`` (fuzzy rapidfuzz). El
    threshold default es 70 (más permisivo que el matcher on-import = 90)
    porque aquí el coach decide manualmente — preferimos sobre-mostrar.

    Args:
        db: Sesión async.
        competitor_id: PK del ``RaceCompetitor``.
        limit: Máximo de sugerencias devueltas. Si > 3, se complementan
            candidatos por debajo del top-3 estándar del matcher.
        threshold: Score mínimo (0..100). Default 70.
        club_id: Si se provee, filtra athletes por club. Default None
            (todos los athletes).

    Returns:
        Lista ordenada descendente por score. Vacía si no hay matches.

    Raises:
        CompetitorNotFoundError: si ``competitor_id`` no existe.
    """
    competitor = await _load_competitor(db, competitor_id)
    athletes = await _athletes_for_suggestions(db, club_id=club_id)
    candidates = match_athletes(
        competitor_name=competitor.display_name,
        competitor_club=competitor.club_text or "",
        competitor_category=None,
        athletes=athletes,
        threshold=threshold,
    )
    # ``match_athletes`` retorna top-3; si pedimos limit > 3 hacemos un
    # segundo paso con threshold más bajo. Para el MVP, limitamos al top-3
    # estándar y dejamos el complemento para iteración futura.
    return [_candidate_to_view(c) for c in candidates[:limit]]


async def list_unlinked_competitors(
    db: AsyncSession,
    *,
    club_filter: Optional[str] = None,
    season: Optional[int] = None,
    include_suggestions: bool = True,
    suggestions_limit: int = 3,
    suggestions_club_id: Optional[int] = None,
    suggestions_threshold: float = 70.0,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[UnlinkedCompetitorRow], int]:
    """Lista competidores con ``athlete_id IS NULL``.

    Args:
        db: Sesión async.
        club_filter: Si ``"trocha"`` (case-insensitive), filtra por
            ``is_trocha_y_ruta(club_text) is True``. Cualquier otro valor
            se ignora silenciosamente (el match exacto por club_text no
            tiene caso de uso conocido aún).
        season: Si se provee, restringe a competidores que tienen
            ``race_results`` (no eliminados) en eventos cuya
            ``series.season_year == season``.
        include_suggestions: Si True, calcula top-N por competitor.
            Default True. Setear False para listados grandes en frontend.
        suggestions_limit: Cuántas sugerencias por competitor.
        suggestions_club_id: Filtra athletes candidatos por club_id.
        suggestions_threshold: Score mínimo del matcher (0..100).
        limit: Cap de items devueltos.
        offset: Paginación.

    Returns:
        Tupla ``(items, total)``. ``total`` es el conteo ANTES de paginar.
    """
    base_stmt = select(RaceCompetitor).where(RaceCompetitor.athlete_id.is_(None))

    # Filtro por temporada vía join transitivo
    if season is not None:
        # Competidores que tienen ≥1 race_result no eliminado en algún evento
        # de la temporada solicitada.
        subq = (
            select(RaceResult.competitor_id)
            .join(RaceEvent, RaceEvent.id == RaceResult.event_id)
            .join(RaceSeries, RaceSeries.id == RaceEvent.series_id)
            .where(
                RaceResult.deleted_at.is_(None),
                RaceSeries.season_year == season,
            )
            .distinct()
            .subquery()
        )
        base_stmt = base_stmt.where(RaceCompetitor.id.in_(select(subq.c.competitor_id)))

    if club_filter and club_filter.strip().lower() == "trocha":
        # Prefiltro SQL grueso (LIKE '%trocha%') + refinamiento fuzzy en Python.
        # El filtro fuzzy debe correr ANTES de paginar para que `total` cuente
        # solo Trocha y Ruta y la paginación no quede limitada a los primeros
        # `limit` ids globales (que pueden no incluir TyR).
        rough_stmt = base_stmt.where(
            func.lower(RaceCompetitor.club_text).like("%trocha%")
        ).order_by(RaceCompetitor.id)
        rough_result = await db.execute(rough_stmt)
        rough_competitors = list(rough_result.scalars().all())
        filtered = [c for c in rough_competitors if is_trocha_y_ruta(c.club_text)]
        total = len(filtered)
        competitors = filtered[offset : offset + limit]
    else:
        total_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_result = await db.execute(total_stmt)
        total = int(total_result.scalar() or 0)
        page_stmt = (
            base_stmt.order_by(RaceCompetitor.id).offset(offset).limit(limit)
        )
        page_result = await db.execute(page_stmt)
        competitors = list(page_result.scalars().all())

    if not competitors:
        return [], total

    competitor_ids = [c.id for c in competitors]

    # Conteo de race_results por competitor (deleted_at IS NULL)
    counts_stmt = (
        select(RaceResult.competitor_id, func.count(RaceResult.id))
        .where(
            RaceResult.competitor_id.in_(competitor_ids),
            RaceResult.deleted_at.is_(None),
        )
        .group_by(RaceResult.competitor_id)
    )
    counts_result = await db.execute(counts_stmt)
    counts_by_id: dict[int, int] = {row[0]: int(row[1]) for row in counts_result.all()}

    # Seasons por competitor (DISTINCT season_year)
    seasons_stmt = (
        select(RaceResult.competitor_id, RaceSeries.season_year)
        .join(RaceEvent, RaceEvent.id == RaceResult.event_id)
        .join(RaceSeries, RaceSeries.id == RaceEvent.series_id)
        .where(
            RaceResult.competitor_id.in_(competitor_ids),
            RaceResult.deleted_at.is_(None),
        )
        .distinct()
    )
    seasons_result = await db.execute(seasons_stmt)
    seasons_by_id: dict[int, set[int]] = {}
    for cid, year in seasons_result.all():
        seasons_by_id.setdefault(int(cid), set()).add(int(year))

    # Sugerencias por competitor
    suggestions_by_id: dict[int, list[SuggestionView]] = {}
    if include_suggestions:
        # Cap defensivo (R3-M3): la página de competitors ya está acotada por
        # ``limit`` (max 200 vía router), pero ``_athletes_for_suggestions``
        # carga TODOS los athletes — si esa población crece sin control el
        # producto cartesiano (competitors × athletes) puede degradar el
        # endpoint. La población actual es < 50 athletes; mantenemos el cap
        # de competitors visible aunque hoy no se aplique.
        athletes = await _athletes_for_suggestions(db, club_id=suggestions_club_id)
        if len(competitors) > MAX_UNLINKED_COMPETITORS_TO_SCORE:
            logger.warning(
                "list_unlinked_competitors_suggestions_cap_hit page_size=%d cap=%d",
                len(competitors),
                MAX_UNLINKED_COMPETITORS_TO_SCORE,
            )
            # En la práctica ``competitors`` ya está acotado por ``limit``
            # del router (max 200) — esta rama es defensiva.
            competitors_to_score = competitors[:MAX_UNLINKED_COMPETITORS_TO_SCORE]
        else:
            competitors_to_score = competitors
        for c in competitors_to_score:
            candidates = match_athletes(
                competitor_name=c.display_name,
                competitor_club=c.club_text or "",
                competitor_category=None,
                athletes=athletes,
                threshold=suggestions_threshold,
            )
            suggestions_by_id[c.id] = [
                _candidate_to_view(cand) for cand in candidates[:suggestions_limit]
            ]

    items: list[UnlinkedCompetitorRow] = []
    for c in competitors:
        items.append(
            UnlinkedCompetitorRow(
                id=c.id,
                display_name=c.display_name,
                normalized_name=c.normalized_name,
                club_text=c.club_text,
                sex=(c.sex.value if c.sex else None),
                results_count=counts_by_id.get(c.id, 0),
                seasons=sorted(seasons_by_id.get(c.id, set())),
                suggestions=suggestions_by_id.get(c.id, []),
            )
        )
    return items, total


async def link_competitor_to_athlete(
    db: AsyncSession,
    competitor_id: int,
    athlete_id: int,
    user_id: int,
) -> LinkResult:
    """Enlaza un competitor a un athlete y propaga el athlete_id a sus race_results.

    Reglas:
    - Si el competitor ya está enlazado al MISMO athlete_id → idempotente,
      ``already_linked=True``, sin escrituras (excepto la propagación a
      race_results que aún tengan athlete_id NULL — defensa contra
      inconsistencia previa).
    - Si el competitor está enlazado a otro athlete_id → ``CompetitorAlreadyLinkedError``.
    - Si ``athlete_id`` no existe → ``AthleteNotFoundError``.
    - Si ``competitor_id`` no existe → ``CompetitorNotFoundError``.

    La propagación actualiza ``race_results.athlete_id`` para TODOS los
    ``race_results`` del competitor con ``deleted_at IS NULL``. Filas
    soft-deleted NO se tocan (preservar historial inmutable).

    El método NO hace ``db.commit()`` — eso lo hace el middleware ``get_db``
    del FastAPI dependency tree (convención del proyecto).

    Args:
        db: Sesión async.
        competitor_id: PK ``RaceCompetitor``.
        athlete_id: PK ``Athlete``.
        user_id: PK ``User`` que ejecuta la acción (audit).

    Returns:
        ``LinkResult`` con conteos.

    Raises:
        CompetitorNotFoundError, AthleteNotFoundError, CompetitorAlreadyLinkedError.

    Race condition (R3-A1):
        El método usa una UPDATE atómica con guard ``athlete_id IS NULL`` para
        ganar la carrera contra otro escritor concurrente. El segundo
        escritor obtiene ``rowcount=0`` y re-lee el estado para distinguir
        entre "no existe" (404), "ya está enlazado al mismo athlete"
        (idempotente) y "enlazado a otro" (409).
    """
    # Cheap pre-check para detectar competitor inexistente con un error
    # claro antes de gastar la UPDATE. Si entre este SELECT y el UPDATE
    # otro proceso enlaza el competitor, el UPDATE atómico abajo lo
    # detecta y responde con 409 (rowcount=0 + re-read).
    competitor = await _load_competitor(db, competitor_id)
    # Verificar atleta existe (athlete_id != 0 ya validado por schema)
    await _load_athlete(db, athlete_id)

    # Idempotencia detectada en pre-check. Esto NO es vulnerable a la race
    # condition: si el competitor ya tiene athlete_id == requested, no hay
    # transición que registrar y el comportamiento esperado es retornar
    # already_linked=True sin escribir audit. (Si otro escritor unlinkea
    # entre este check y el flush final, la propagación defensiva lo
    # devolverá a estado consistente, pero NO se genera audit duplicado.)
    if competitor.athlete_id == athlete_id:
        propagated = await _propagate_athlete_id(
            db, competitor_id=competitor_id, athlete_id=athlete_id
        )
        if competitor.linked_at is None:
            # Estado raro: linkeado pero sin audit. Lo dejamos como está
            # (no sobrescribimos audit), pero advertimos en log.
            logger.warning(
                "competitor_link_idempotent_missing_audit competitor_id=%s "
                "athlete_id=%s user_id=%s",
                competitor_id,
                athlete_id,
                user_id,
            )
        logger.info(
            "competitor_link_idempotent competitor_id=%s athlete_id=%s "
            "user_id=%s results_propagated=%d",
            competitor_id,
            athlete_id,
            user_id,
            propagated,
        )
        return LinkResult(
            competitor_id=competitor_id,
            athlete_id=athlete_id,
            linked_at=competitor.linked_at or datetime.now(timezone.utc),
            linked_by_user_id=competitor.linked_by_user_id or user_id,
            results_propagated=propagated,
            already_linked=True,
        )

    # Conflicto detectado en pre-check (otro athlete). 409 sin tocar DB.
    if competitor.athlete_id is not None:
        raise CompetitorAlreadyLinkedError(
            competitor_id=competitor_id,
            current_athlete_id=competitor.athlete_id,
            requested_athlete_id=athlete_id,
        )

    # ---- UPDATE atómica (R3-A1) ----
    # Sólo escribe si el competitor sigue con athlete_id IS NULL. Si otro
    # proceso lo enlazó entre el SELECT de arriba y este UPDATE, rowcount
    # será 0 y re-leemos para distinguir idempotente vs conflicto.
    now = datetime.now(timezone.utc)
    update_stmt = (
        update(RaceCompetitor)
        .where(
            RaceCompetitor.id == competitor_id,
            RaceCompetitor.athlete_id.is_(None),
        )
        .values(
            athlete_id=athlete_id,
            linked_at=now,
            linked_by_user_id=user_id,
        )
        .execution_options(synchronize_session=False)
    )
    update_result = await db.execute(update_stmt)
    if int(update_result.rowcount or 0) == 0:
        # Otro escritor ganó la carrera. Re-leer el state actual desde DB
        # con un SELECT fresco (no usamos ``db.refresh(competitor)`` porque
        # el pre-check puede haber leído desde caché stale y queremos un
        # ground-truth desde el storage).
        fresh = (
            await db.execute(
                select(RaceCompetitor).where(RaceCompetitor.id == competitor_id)
            )
        ).scalar_one_or_none()
        if fresh is None:
            # Competitor fue hard-deleted entre nuestro pre-check y el
            # UPDATE — devolvemos 404.
            raise CompetitorNotFoundError(competitor_id)
        if fresh.athlete_id == athlete_id:
            # El otro escritor pidió el mismo athlete → degradamos a
            # idempotente. Propagamos defensivamente.
            propagated = await _propagate_athlete_id(
                db, competitor_id=competitor_id, athlete_id=athlete_id
            )
            logger.info(
                "competitor_link_race_won_by_other_same_athlete competitor_id=%s "
                "athlete_id=%s user_id=%s results_propagated=%d",
                competitor_id,
                athlete_id,
                user_id,
                propagated,
            )
            return LinkResult(
                competitor_id=competitor_id,
                athlete_id=athlete_id,
                linked_at=fresh.linked_at or now,
                linked_by_user_id=fresh.linked_by_user_id or user_id,
                results_propagated=propagated,
                already_linked=True,
            )
        if fresh.athlete_id is not None:
            # El otro escritor enlazó a un athlete DISTINTO → 409.
            logger.info(
                "competitor_link_race_lost_to_other_athlete competitor_id=%s "
                "requested_athlete_id=%s current_athlete_id=%s user_id=%s",
                competitor_id,
                athlete_id,
                fresh.athlete_id,
                user_id,
            )
            raise CompetitorAlreadyLinkedError(
                competitor_id=competitor_id,
                current_athlete_id=fresh.athlete_id,
                requested_athlete_id=athlete_id,
            )
        # rowcount=0 PERO fresh.athlete_id sigue NULL: caso muy raro
        # (el WHERE habría matcheado). Defensivo: indicamos conflict
        # genérico re-intentando podría ayudar. Re-raise como NotFound
        # mantiene contrato simple.
        raise CompetitorNotFoundError(competitor_id)

    propagated = await _propagate_athlete_id(
        db, competitor_id=competitor_id, athlete_id=athlete_id
    )

    # Audit append-only (R3-M1). Insert ANTES del flush final para que
    # ambos cambios (mutation + audit) viajen en la misma transacción y
    # el rollback del middleware get_db los revierta juntos en error path.
    audit_row = RaceCompetitorLinkAudit(
        competitor_id=competitor_id,
        action=LinkAuditAction.link,
        previous_athlete_id=None,
        new_athlete_id=athlete_id,
        results_propagated=propagated,
        user_id=user_id,
        created_at=now,
    )
    db.add(audit_row)

    await db.flush()

    logger.info(
        "competitor_link_ok competitor_id=%s athlete_id=%s user_id=%s "
        "results_propagated=%d",
        competitor_id,
        athlete_id,
        user_id,
        propagated,
    )

    return LinkResult(
        competitor_id=competitor_id,
        athlete_id=athlete_id,
        linked_at=now,
        linked_by_user_id=user_id,
        results_propagated=propagated,
        already_linked=False,
    )


async def unlink_competitor(
    db: AsyncSession,
    competitor_id: int,
    user_id: int,
) -> UnlinkResult:
    """Deshace el enlace competitor↔athlete y limpia race_results.

    Si el competitor ya estaba en NULL, retorna ``was_linked=False`` sin
    cambios (idempotente).

    Args:
        db: Sesión async.
        competitor_id: PK ``RaceCompetitor``.
        user_id: PK ``User`` que ejecuta la acción (audit en logs).

    Returns:
        ``UnlinkResult``.

    Raises:
        CompetitorNotFoundError: si ``competitor_id`` no existe.
    """
    competitor = await _load_competitor(db, competitor_id)

    if competitor.athlete_id is None:
        # Defensa: aunque competitor esté en NULL, race_results podrían
        # tener athlete_id != NULL (state inconsistente). Limpiamos.
        # NO emitimos audit row aquí: no hay transición real (was_linked=False).
        propagated = await _propagate_athlete_id(
            db, competitor_id=competitor_id, athlete_id=None
        )
        logger.info(
            "competitor_unlink_noop competitor_id=%s user_id=%s "
            "results_propagated=%d",
            competitor_id,
            user_id,
            propagated,
        )
        return UnlinkResult(
            competitor_id=competitor_id,
            results_propagated=propagated,
            was_linked=False,
        )

    # Capturamos previous_athlete_id ANTES de mutarlo — el audit registra
    # quién era el athlete enlazado al momento del unlink (R3-M1).
    previous_athlete_id = competitor.athlete_id

    competitor.athlete_id = None
    competitor.linked_at = None
    competitor.linked_by_user_id = None

    propagated = await _propagate_athlete_id(
        db, competitor_id=competitor_id, athlete_id=None
    )

    # Audit append-only (R3-M1).
    audit_row = RaceCompetitorLinkAudit(
        competitor_id=competitor_id,
        action=LinkAuditAction.unlink,
        previous_athlete_id=previous_athlete_id,
        new_athlete_id=None,
        results_propagated=propagated,
        user_id=user_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(audit_row)

    await db.flush()

    logger.info(
        "competitor_unlink_ok competitor_id=%s user_id=%s results_propagated=%d",
        competitor_id,
        user_id,
        propagated,
    )

    return UnlinkResult(
        competitor_id=competitor_id,
        results_propagated=propagated,
        was_linked=True,
    )


#: Boost agregado al score base cuando el ``club`` provisto matchea el
#: ``club_text`` del competitor por ``partial_ratio >= 80``. Calibrado para
#: empatar el orden cuando dos candidatos comparten score base pero uno
#: pertenece al mismo club que el athlete a crear.
_CLUB_BOOST: float = 5.0

#: Threshold de ``partial_ratio`` para considerar que dos clubs "matchean".
#: Conservador: evita boosts espurios entre clubs con substrings cortos.
_CLUB_MATCH_THRESHOLD: float = 80.0


def _build_full_name(first_name: str, last_name: str) -> str:
    """Concatena ``first_name`` + ``last_name`` colapsando whitespace."""
    parts = [p for p in (first_name or "", last_name or "") if p and p.strip()]
    return " ".join(parts).strip()


async def suggest_competitors_for_new_athlete(
    db: AsyncSession,
    *,
    first_name: str,
    last_name: str,
    club: Optional[str] = None,
    limit: int = 5,
    threshold: float = 70.0,
) -> list[CompetitorSuggestionView]:
    """Top-N competitors huérfanos sugeridos para un athlete a crear.

    Búsqueda INVERSA al matcher on-import:
    - Aquí se conoce el athlete (a crear) y se buscan ``RaceCompetitor``
      con ``athlete_id IS NULL`` cuyos nombres matcheen.
    - Reusa ``rapidfuzz.fuzz.token_set_ratio`` sobre ``normalize_name``
      (misma normalización que el ingestor — coherencia end-to-end).
    - Boost ``+_CLUB_BOOST`` si el ``club`` provisto matchea el
      ``club_text`` del competitor por ``partial_ratio >= _CLUB_MATCH_THRESHOLD``.
    - Filtra por score base >= ``threshold`` (en escala 0..100). El boost
      no contribuye al filtrado — un candidato con score base 65 + club
      no entra aunque el total quede en 70.
    - Score expuesto al frontend en [0, 1] (normalizado /100).
    - ``results_count`` y ``seasons`` se agregan para que el frontend pueda
      mostrar contexto ("4 resultados pendientes en 2025-2026").

    Args:
        db: Sesión async.
        first_name: Primer nombre del athlete a crear. Obligatorio.
        last_name: Apellido(s). Obligatorio.
        club: Club textual opcional (ej. "Trocha y Ruta"). Si se provee
            y matchea ``club_text`` del competitor → boost al score.
        limit: Máximo de sugerencias retornadas. Default 5.
        threshold: Score base mínimo (0..100) para incluir candidato.
            Default 70.

    Returns:
        Lista ordenada descendente por score (con boost), tie-break por
        ``competitor_id`` para determinismo. Vacía si no hay matches.

    Notas privacidad:
    - El log no incluye nombres — solo cardinalidad y score.
    - El método no muta nada en DB (solo lectura).
    """
    full_name = _build_full_name(first_name, last_name)
    if not full_name:
        logger.debug(
            "suggest_competitors_for_new_athlete | empty_full_name → []"
        )
        return []

    normalized_query = normalize_name(full_name)
    if not normalized_query:
        return []

    normalized_club_query = normalize_club(club) if club else ""

    # Cargamos solo competitors huérfanos. Población esperada baja (decenas
    # a centenas para una temporada activa), filtrar en Python es trivial
    # y mantiene la lógica de scoring centralizada con el matcher.
    #
    # Cap defensivo (R3-M3): si la población crece anormalmente (e.g.
    # backfill masivo de temporadas pasadas, bug que multiplica filas),
    # limitamos a MAX_UNLINKED_COMPETITORS_TO_SCORE para no degradar el
    # endpoint a DoS. Sin LIMIT, walks N filas + fuzz por cada una bloquea
    # el event loop con N=10k. ORDER BY id para que el subset sea
    # determinístico (no aleatorio entre invocaciones).
    stmt = (
        select(RaceCompetitor)
        .where(RaceCompetitor.athlete_id.is_(None))
        .order_by(RaceCompetitor.id)
        .limit(MAX_UNLINKED_COMPETITORS_TO_SCORE + 1)
    )
    result = await db.execute(stmt)
    competitors = list(result.scalars().all())

    if len(competitors) > MAX_UNLINKED_COMPETITORS_TO_SCORE:
        # +1 para detectar overflow. Truncamos y loggeamos sin nombres.
        logger.warning(
            "suggest_competitors_for_new_athlete_cap_hit cap=%d "
            "(considerar backfill manual o aumentar cap)",
            MAX_UNLINKED_COMPETITORS_TO_SCORE,
        )
        competitors = competitors[:MAX_UNLINKED_COMPETITORS_TO_SCORE]

    if not competitors:
        return []

    # Pre-calcular ratios y boosts
    scored: list[tuple[float, float, RaceCompetitor]] = []
    # (base_score [0..100], final_score con cap [0..100], competitor)

    for c in competitors:
        # ``normalized_name`` se guarda en DB ya normalizado por ingestor;
        # lo re-normalizamos defensivamente por si fue cargado externamente.
        target = c.normalized_name or normalize_name(c.display_name or "")
        if not target:
            continue
        base_score = float(fuzz.token_set_ratio(normalized_query, target))
        if base_score < threshold:
            continue

        final_score = base_score
        club_matched = False
        if normalized_club_query:
            target_club_norm = normalize_club(c.club_text or "")
            if target_club_norm:
                club_ratio = float(
                    fuzz.partial_ratio(normalized_club_query, target_club_norm)
                )
                if club_ratio >= _CLUB_MATCH_THRESHOLD:
                    final_score = min(base_score + _CLUB_BOOST, _SCORE_CAP)
                    club_matched = True

        scored.append((base_score, final_score, c))
        # Stash temporal para el reason; lo necesitamos en orden estable.
        c.__dict__["_club_matched"] = club_matched  # type: ignore[attr-defined]

    if not scored:
        return []

    # Orden descendente por final_score, tie-break por competitor_id asc
    scored.sort(key=lambda t: (-t[1], t[2].id))
    top = scored[: max(limit, 0)]

    if not top:
        return []

    competitor_ids = [c.id for _, _, c in top]

    # Conteo de race_results activos por competitor
    counts_stmt = (
        select(RaceResult.competitor_id, func.count(RaceResult.id))
        .where(
            RaceResult.competitor_id.in_(competitor_ids),
            RaceResult.deleted_at.is_(None),
        )
        .group_by(RaceResult.competitor_id)
    )
    counts_result = await db.execute(counts_stmt)
    counts_by_id: dict[int, int] = {
        int(row[0]): int(row[1]) for row in counts_result.all()
    }

    # Seasons distintas por competitor
    seasons_stmt = (
        select(RaceResult.competitor_id, RaceSeries.season_year)
        .join(RaceEvent, RaceEvent.id == RaceResult.event_id)
        .join(RaceSeries, RaceSeries.id == RaceEvent.series_id)
        .where(
            RaceResult.competitor_id.in_(competitor_ids),
            RaceResult.deleted_at.is_(None),
        )
        .distinct()
    )
    seasons_result = await db.execute(seasons_stmt)
    seasons_by_id: dict[int, set[int]] = {}
    for cid, year in seasons_result.all():
        seasons_by_id.setdefault(int(cid), set()).add(int(year))

    views: list[CompetitorSuggestionView] = []
    for _base, final_score, c in top:
        score_norm = round(final_score / 100.0, 4)
        club_matched = bool(c.__dict__.get("_club_matched", False))
        if final_score >= 99.5:
            reason = (
                "exact name match + same club"
                if club_matched
                else "exact name match"
            )
        else:
            base_reason = f"fuzzy {score_norm:.2f}"
            reason = f"{base_reason} + same club" if club_matched else base_reason

        views.append(
            CompetitorSuggestionView(
                competitor_id=c.id,
                display_name=c.display_name,
                club_text=c.club_text,
                score=score_norm,
                reason=reason,
                results_count=counts_by_id.get(c.id, 0),
                seasons=sorted(seasons_by_id.get(c.id, set())),
            )
        )

    logger.info(
        "suggest_competitors_for_new_athlete | candidates_total=%d top=%d "
        "threshold=%.1f has_club=%s",
        len(scored),
        len(views),
        threshold,
        bool(normalized_club_query),
    )
    return views


# ---------------------------------------------------------------------------
# Helpers privados — propagación
# ---------------------------------------------------------------------------


async def _propagate_athlete_id(
    db: AsyncSession, *, competitor_id: int, athlete_id: Optional[int]
) -> int:
    """Setea ``race_results.athlete_id = athlete_id`` para todos los results
    del competitor con ``deleted_at IS NULL`` cuyo athlete_id actual difiera.

    Soft-deleted results NO se tocan (inmutables por convención de auditoría).

    Retorna el número de filas actualizadas.
    """
    stmt = (
        update(RaceResult)
        .where(
            RaceResult.competitor_id == competitor_id,
            RaceResult.deleted_at.is_(None),
            # Si ya tiene el valor objetivo, no contamos como propagación.
            # Esto importa para el idempotency case: queremos propagated=0
            # cuando todo ya está sincronizado.
            (
                RaceResult.athlete_id.is_not(athlete_id)
                if athlete_id is None
                else (
                    (RaceResult.athlete_id != athlete_id)
                    | RaceResult.athlete_id.is_(None)
                )
            ),
        )
        .values(athlete_id=athlete_id)
        .execution_options(synchronize_session=False)
    )
    result = await db.execute(stmt)
    return int(result.rowcount or 0)
