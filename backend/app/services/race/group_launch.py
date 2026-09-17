"""Service layer for group analysis launch (Feature 010).

Implements the business logic for ``POST /race-events/{id}/runs`` and
``GET /race-events/{id}/runs`` without touching any router — the router
is wired in a later task.

Key design decisions
--------------------
- **No per-athlete budget check**: ``check_budget`` is a single up-front
  check owned by the router. This service never calls it.
- **Identical run submission path**: uses the same ``submit_run`` +
  ``_on_complete`` + ``_finalize_run`` mechanism as the existing
  ``POST /runs`` endpoint. Behavior (HITL gate, events, persistence,
  staleness, usage metrics) is identical for single and group launches
  (FR-003, FR-009, FR-014).
- **Active run detection via input_json**: mirrors the JSON-matching
  approach documented in ``data-model.md`` — a run belongs to event E
  iff ``input_json.season == series.season_year`` AND
  ``E.sequence_number ∈ input_json.valida_nums`` AND the athlete has a
  result in E. ``find_active_run`` applies this principle to the
  ``agent_runs`` table using MySQL ``JSON_EXTRACT`` / ``JSON_CONTAINS``
  (same DB as production) with a Python-side fallback for SQLite tests.
- **Display name convention**: ``"{first_name} {last_name}"`` — same as
  ``season_panorama`` and ``club_race_insights``. Group launch is a
  coach-only endpoint so no masking is applied here; the router enforces
  RBAC before calling this service.
- **Stale detection**: ``stale = (stale_since IS NOT NULL)`` — direct
  column read, no extra computation.

Privacy: athlete names appear in logs ONLY at DEBUG level and are not
included in any ERROR/WARNING log entry (CLAUDE.md §Privacy).
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete import Athlete
from app.models.race_event import RaceEvent
from app.models.race_result import RaceResult
from app.models.race_series import RaceSeries
from app.models.user import User
from app.schemas.race_ai import (
    GroupRunItem,
    GroupRunLaunchResponse,
    GroupRunOutcome,
    RaceEventRunItem,
    RaceEventRunsResponse,
    RunState,
)
from app.services.audit import AuditAction, AuditEntityType, record_audit
from app.services.race.ai.runner import RunBackpressureError, submit_run

logger = logging.getLogger(__name__)

# Mapping from DB status string to RunState schema enum.
_DB_STATUS_TO_RUN_STATE: dict[str, RunState] = {
    "running": RunState.RUNNING,
    "awaiting_hitl": RunState.HITL_WAITING,
    "completed": RunState.DONE,
    "rejected": RunState.DONE,
    "failed": RunState.FAILED,
    "cancelled": RunState.CANCELLED,
}

# Active statuses used for "already running" detection and list filtering.
_ACTIVE_STATUSES = {"running", "awaiting_hitl"}

# Terminal statuses included in the "last 7 days" window for active_only=False.
_TERMINAL_STATUSES = {"completed", "rejected", "failed", "cancelled"}


# ---------------------------------------------------------------------------
# Module-level errors
# ---------------------------------------------------------------------------


class RaceEventNotFoundError(LookupError):
    """The requested race_event_id does not exist in the database."""

    def __init__(self, race_event_id: int) -> None:
        super().__init__(f"race_event not found: id={race_event_id}")
        self.race_event_id = race_event_id


class EventNotAnalyzableError(ValueError):
    """The race event has a NULL sequence_number and cannot be analyzed."""

    def __init__(self, race_event_id: int) -> None:
        super().__init__(
            f"race_event id={race_event_id} has NULL sequence_number — "
            "cannot derive valida_num for analysis"
        )
        self.race_event_id = race_event_id


class EventHasNoResultsError(ValueError):
    """The race event has no committed results for any club athlete."""

    def __init__(self, race_event_id: int) -> None:
        super().__init__(
            f"race_event id={race_event_id} has no committed athlete results"
        )
        self.race_event_id = race_event_id


# ---------------------------------------------------------------------------
# Internal dataclass for resolved group members
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Member:
    """Resolved athlete member for a group launch."""

    athlete_id: int
    display_name: str


@dataclass(frozen=True)
class AthleteAiContext:
    """Contexto compartido para poblar el ``initial_state`` de un run IA.

    Hotfix "identidad de válida" (2026-09-16, ver
    ``~/.claude/plans/multicopa-identidad-valida.md``, Bug #2): centraliza
    la resolución de edad, sexo, grupo LTAD, fase madurativa y nombres
    prohibidos — histéricamente duplicada, casi idéntica, en
    ``routers/race_analysis.py::start_run`` y en
    ``routers/athlete_race_analysis.py`` (``start_athlete_run`` /
    ``create_season_summary``). ``launch_group`` nunca poblaba estos campos:
    sin ``forbidden_names`` el scrub de ``coach_note`` en ``anonymize.py``
    no tenía nada que scrubear en un lanzamiento grupal — un vacío real de
    privacidad, no solo de datos faltantes.
    """

    athlete_age: Optional[int]
    athlete_sex: Optional[str]
    ltad_group: Optional[str]
    maturation_status: Optional[str]
    forbidden_names: list[str]


async def resolve_athlete_ai_context(db: AsyncSession, athlete: Athlete) -> AthleteAiContext:
    """Resuelve el contexto IA de un atleta para inyectar en ``initial_state``.

    Réplica exacta de la lógica usada por ``race_analysis.py::start_run``
    (features 011/037): ``athlete_sex`` se resuelve siempre (no depende de
    ``birth_date``); ``athlete_age``/``ltad_group``/``maturation_status``
    solo cuando hay ``birth_date``. ``forbidden_names`` es best-effort (ver
    :func:`app.services.race.ai.grounding.load_forbidden_names`) y siempre
    devuelve una lista, nunca ``None``.
    """
    from app.services.race.ai.grounding import (
        load_forbidden_names,
        ltad_group_from_age,
        resolve_maturation_status,
    )

    athlete_sex_val: Optional[str] = None
    if getattr(athlete, "sex", None) is not None:
        athlete_sex_val = getattr(athlete.sex, "value", None) or str(athlete.sex)

    athlete_age: Optional[int] = None
    ltad_group_val: Optional[str] = None
    maturation_status: Optional[str] = None
    forbidden_names: list[str] = []

    if getattr(athlete, "birth_date", None) is not None:
        age_decimal = (date.today() - athlete.birth_date).days / 365.25
        athlete_age = int(age_decimal)
        ltad_group_val = ltad_group_from_age(age_decimal).value
        # Adulto (≥18) → None sin consultar la BD: PHV no aplica (ver
        # resolve_maturation_status).
        maturation_status = await resolve_maturation_status(db, athlete.id, athlete_age)
        forbidden_names = await load_forbidden_names(
            db, athlete.id, nickname=getattr(athlete, "nickname", None)
        )
    else:
        logger.warning(
            "resolve_athlete_ai_context: athlete_id=%s sin birth_date; "
            "athlete_age/ltad_group/maturation_status no resueltos",
            athlete.id,
        )

    return AthleteAiContext(
        athlete_age=athlete_age,
        athlete_sex=athlete_sex_val,
        ltad_group=ltad_group_val,
        maturation_status=maturation_status,
        forbidden_names=forbidden_names,
    )


async def resolve_events_for_season_valida(
    db: AsyncSession, season: int, valida_num: int
) -> list[int]:
    """PKs de ``race_events`` cuya serie es de ``season`` con ese ``sequence_number``.

    Longitud > 1 ⇒ el número de válida es AMBIGUO en la temporada (dos copas,
    o una copa y un campeonato, comparten ``sequence_number`` — hotfix
    "identidad de válida"). Usado por :func:`find_active_run` (para no
    adoptar un run legado que podría pertenecer a otra copa) y por
    ``routers/race_analysis.py::start_run`` (para exigir desambiguación con
    409 en vez de adivinar).
    """
    result = await db.execute(
        select(RaceEvent.id)
        .join(RaceSeries, RaceEvent.series_id == RaceSeries.id)
        .where(
            RaceSeries.season_year == season,
            RaceEvent.sequence_number == valida_num,
        )
    )
    return [int(x) for x in result.scalars().all()]


# ---------------------------------------------------------------------------
# Helper: UTC now
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 1. resolve_event_scope
# ---------------------------------------------------------------------------


async def resolve_event_scope(
    db: AsyncSession,
    race_event_id: int,
) -> tuple[int, int]:
    """Return ``(season, valida_num)`` for the given race event.

    Loads ``race_events`` joined to ``race_series`` to extract
    ``season_year`` and ``sequence_number``.

    Args:
        db: Active async DB session.
        race_event_id: PK of the ``race_events`` row.

    Returns:
        Tuple ``(season_year, sequence_number)``.

    Raises:
        RaceEventNotFoundError: if no row exists for ``race_event_id``.
        EventNotAnalyzableError: if ``sequence_number`` is NULL.
    """
    result = await db.execute(
        select(RaceEvent, RaceSeries)
        .join(RaceSeries, RaceEvent.series_id == RaceSeries.id)
        .where(RaceEvent.id == race_event_id)
    )
    row = result.first()
    if row is None:
        raise RaceEventNotFoundError(race_event_id)

    event: RaceEvent
    series: RaceSeries
    event, series = row

    if event.sequence_number is None:
        raise EventNotAnalyzableError(race_event_id)

    return int(series.season_year), int(event.sequence_number)


# ---------------------------------------------------------------------------
# 2. resolve_group_members
# ---------------------------------------------------------------------------


async def resolve_group_members(
    db: AsyncSession,
    race_event_id: int,
    athlete_ids: Optional[list[int]],
    club_ids: Optional[set[int]] = None,
) -> list[Member]:
    """Return distinct club athletes with results in the given event.

    Performs a single JOIN query (no N+1) between ``race_results`` and
    ``athletes`` to get the athlete display name. Filters:
    - ``race_results.event_id = race_event_id``
    - ``race_results.athlete_id IS NOT NULL``
    - ``race_results.deleted_at IS NULL``
    - When ``athlete_ids`` is not None: ``athlete_id IN athlete_ids``
    - When ``club_ids`` is not None: ``athletes.club_id IN club_ids``

    ``club_ids`` acota el resultado a los clubes de quien pregunta y es el
    arreglo de los hallazgos H1 y H2 de la revisión de seguridad de US6
    (T080): una carrera es de un tercero y en ella corren menores de varios
    clubes, así que sin este filtro el listado de corridas de un evento le
    entregaba a un entrenador de otro club el **nombre completo** de una menor
    ajena junto con un ``run_id`` válido, y el lanzamiento grupal abría una
    corrida por cada una de esas menores. ``None`` = sin filtro, que es lo que
    pasa el administrador.

    Display name convention: ``"{first_name} {last_name}"`` — identical to
    ``season_panorama`` (``race_analysis.py`` line 1438) and
    ``club_race_insights``.

    Args:
        db: Active async DB session.
        race_event_id: PK of the ``race_events`` row.
        athlete_ids: Optional subset filter. None = all athletes.

    Returns:
        List of :class:`Member` instances, deduplicated by athlete_id,
        ordered by last_name then first_name.
    """
    stmt = (
        select(Athlete.id, Athlete.first_name, Athlete.last_name)
        .join(RaceResult, RaceResult.athlete_id == Athlete.id)
        .where(
            RaceResult.event_id == race_event_id,
            RaceResult.athlete_id.is_not(None),
            RaceResult.deleted_at.is_(None),
            Athlete.deleted_at.is_(None),
        )
        .distinct()
        .order_by(Athlete.last_name, Athlete.first_name)
    )

    if athlete_ids is not None:
        stmt = stmt.where(Athlete.id.in_(athlete_ids))

    if club_ids is not None:
        # Conjunto vacío → ningún miembro. Es lo correcto: un coach sin club
        # no tiene deportistas que analizar, y `in_(())` no devuelve filas.
        stmt = stmt.where(Athlete.club_id.in_(club_ids))

    result = await db.execute(stmt)
    rows = result.all()

    members: list[Member] = []
    seen: set[int] = set()
    for row in rows:
        if hasattr(row, "_mapping"):
            aid = int(row._mapping["id"])
            first = str(row._mapping["first_name"] or "")
            last = str(row._mapping["last_name"] or "")
        else:
            aid = int(row[0])
            first = str(row[1] or "")
            last = str(row[2] or "")

        if aid not in seen:
            seen.add(aid)
            members.append(
                Member(
                    athlete_id=aid,
                    display_name=f"{first} {last}".strip(),
                )
            )

    return members


# ---------------------------------------------------------------------------
# 3. find_active_run
# ---------------------------------------------------------------------------


async def find_active_run(
    db: AsyncSession,
    athlete_id: int,
    season: int,
    valida_num: int,
    *,
    event_id: Optional[int] = None,
) -> Optional[str]:
    """Return the ``external_run_id`` of an active run for the given scope.

    An "active" run has status ``running`` or ``awaiting_hitl`` and its
    ``input_json`` matches:
    - ``athlete_id == athlete_id``
    - ``season == season``
    - ``valida_num ∈ valida_nums``

    Resolution mirrors the event-linkage logic documented in
    ``data-model.md`` and used by ``run_staleness.invalidate_runs_for_event``.

    Uses ``JSON_EXTRACT`` / ``JSON_CONTAINS`` for MySQL (production).  For
    SQLite (tests) the query falls back to a Python-side filter because
    SQLite's JSON support differs.

    Args:
        db: Active async DB session.
        athlete_id: Athlete PK.
        season: Season year (e.g. 2026).
        valida_num: Sequence number of the event (e.g. 3).
        event_id: Hotfix "identidad de válida" (2026-09-16). When given, a
            candidate run's ``input_json.event_id`` must match it exactly.
            A LEGACY run (persisted before this hotfix, so its payload has
            no ``event_id`` key) is only adopted when ``(season,
            valida_num)`` resolves to exactly one event in the season — if
            it's ambiguous (two cups sharing the same ``sequence_number``)
            we can't tell which cup the legacy run belongs to, so it is
            NEVER adopted as a match. ``None`` (default) reproduces the
            legacy behaviour for callers that don't resolve an anchor event.

    Returns:
        ``external_run_id`` string if an active run exists, else ``None``.
    """
    # Fetch all active runs for this athlete (small result set — at most
    # MAX_CONCURRENT_RUNS=10 rows total across all athletes). Python-side
    # JSON filtering avoids dialect-specific syntax while remaining correct.
    result = await db.execute(
        text(
            """
            SELECT external_run_id, input_json
            FROM agent_runs
            WHERE status IN ('running', 'awaiting_hitl')
              AND input_json IS NOT NULL
            """
        )
    )
    rows = result.fetchall() if hasattr(result, "fetchall") else []

    for row in rows:
        if hasattr(row, "_mapping"):
            run_id = str(row._mapping["external_run_id"])
            raw = row._mapping["input_json"]
        else:
            run_id = str(row[0])
            raw = row[1]

        # Deserialize input_json (stored as JSON string in MySQL).
        if isinstance(raw, str):
            try:
                payload = json.loads(raw)
            except (ValueError, TypeError):
                continue
        elif isinstance(raw, dict):
            payload = raw
        else:
            continue

        if not isinstance(payload, dict):
            continue

        # Match: athlete_id, season, valida_num ∈ valida_nums.
        if payload.get("athlete_id") != athlete_id:
            continue
        if payload.get("season") != season:
            continue
        valida_nums = payload.get("valida_nums")
        # valida_nums=None means "all válidas" — treat as a match for any
        # specific valida_num to be conservative (avoids double-launching).
        if valida_nums is not None and valida_num not in valida_nums:
            continue

        if event_id is not None:
            payload_event_id = payload.get("event_id")
            if payload_event_id is not None:
                if payload_event_id != event_id:
                    # Same (season, valida_num) but a DIFFERENT cup's event —
                    # never a match (hotfix "identidad de válida").
                    continue
            else:
                # Legacy row (pre-hotfix): no event_id of its own. Only
                # adopt it if (season, valida_num) is unambiguous — else it
                # could belong to another cup and we'd double-launch or
                # silently skip the wrong athlete's run.
                candidates = await resolve_events_for_season_valida(
                    db, season, valida_num
                )
                if len(candidates) != 1:
                    continue

        return run_id

    return None


# ---------------------------------------------------------------------------
# Internal: _on_complete callback factory (mirrors router's pattern)
# ---------------------------------------------------------------------------


def _make_on_complete(
    run_id: str,
) -> Callable[[str, Optional[BaseException], Optional[dict[str, Any]]], Awaitable[None]]:
    """Build the ``on_complete`` callback for a run launched by this service.

    Reuses ``_finalize_run`` from the router module (same code path as
    single-athlete launch) to guarantee identical persistence behavior
    (FR-003, FR-009, FR-014).
    """

    async def _on_complete(
        rid: str,
        exc: Optional[BaseException],
        result_state: Optional[dict[str, Any]],
    ) -> None:
        # Import lazily to mirror the router pattern and avoid circular deps.
        from app.database import AsyncSessionLocal
        from app.routers.race_analysis import _finalize_run

        async with AsyncSessionLocal() as session:
            try:
                await _finalize_run(session, rid, exc, result_state)
                await session.commit()
            except Exception:  # noqa: BLE001
                logger.exception(
                    "group_launch _on_complete: finalize_run falló para run=%s",
                    rid,
                )

    return _on_complete


# ---------------------------------------------------------------------------
# Internal: _insert_agent_run (same INSERT as router's start_run)
# ---------------------------------------------------------------------------


async def _insert_agent_run(
    db: AsyncSession,
    run_id: str,
    athlete_id: int,
    season: int,
    valida_nums: list[int],
    explain_mode: bool,
    started_at: datetime,
    requested_by_user_id: int,
    event_id: Optional[int] = None,
) -> None:
    """Insert a new ``agent_runs`` row with status=running.

    Mirrors the INSERT in ``race_analysis.start_run`` (lines 596-624).

    ``event_id`` (hotfix "identidad de válida", Bug #2): the anchor event of
    a group launch is ALWAYS known — a group launch starts FROM one specific
    ``race_event_id`` — so it is always persisted in ``input_json``. Without
    it, :func:`find_active_run` can't tell two cups sharing the same
    ``valida_num`` apart for runs started by this path.
    """
    from app.services.race.agents.pricing import PROMPT_VERSION_ANALYST_V2

    input_payload = {
        "athlete_id": athlete_id,
        "season": season,
        "valida_nums": valida_nums,
        "explain_mode": explain_mode,
        "event_id": event_id,
    }

    await db.execute(
        text(
            """
            INSERT INTO agent_runs (
                external_run_id, graph_name, prompt_version, started_at,
                status, input_json, requested_by_user_id,
                checkpoint_thread_id, explain_mode, athlete_id
            ) VALUES (
                :rid, :gn, :pv, :sa, 'running', :inp, :uid, :tid, :em, :aid
            )
            """
        ),
        {
            "rid": run_id,
            "gn": "race-analyst",
            "pv": PROMPT_VERSION_ANALYST_V2,
            "sa": started_at,
            "inp": json.dumps(input_payload, ensure_ascii=False, default=str),
            "uid": requested_by_user_id,
            "tid": run_id,
            "em": 1 if explain_mode else 0,
            # §1.3: la columna es la fuente preferida para resolver el club
            # del run; sin ella, cada run de grupo nacía con ``athlete_id``
            # en NULL.
            "aid": athlete_id,
        },
    )


# ---------------------------------------------------------------------------
# 4. launch_group
# ---------------------------------------------------------------------------


async def launch_group(
    db: AsyncSession,
    race_event_id: int,
    athlete_ids: Optional[list[int]],
    explain_mode: bool,
    requested_by_user_id: int,
    club_ids: Optional[set[int]] = None,
) -> GroupRunLaunchResponse:
    """Launch group analysis for all (or a subset of) athletes in an event.

    This is the canonical service function for
    ``POST /api/race-analysis/race-events/{id}/runs``.

    Steps (per contract in ``race-event-runs.md``):
    1. Resolve ``(season, valida_num)`` from the event (404/422 on error).
    2. Resolve group members. If empty and ``athlete_ids`` is None → 422
       (EventHasNoResultsError). If empty and ``athlete_ids`` was given →
       return 200 with zero started (callers asked for an empty subset).
    3. For each member:
       - Skip with ``already_running`` if ``find_active_run`` returns a hit.
       - Otherwise, insert ``agent_runs`` row and call ``submit_run``.
       - Catch ``RunBackpressureError`` → ``backpressure`` item.
       - Catch unexpected exceptions → ``error`` item (log, no PII).
    4. Compute ``started_count`` / ``skipped_count`` from items.

    Budget check is the CALLER's responsibility (router checks once
    up-front before calling this function).

    Args:
        db: Active async DB session (will be flushed but NOT committed
            here — caller commits).
        race_event_id: PK of the ``race_events`` row.
        athlete_ids: Optional subset; None = all athletes with results.
        explain_mode: Forwarded to each run's ``input_json``.
        requested_by_user_id: PK of the user triggering the launch.

    Returns:
        :class:`GroupRunLaunchResponse` with per-athlete outcomes.

    Raises:
        RaceEventNotFoundError: event does not exist.
        EventNotAnalyzableError: sequence_number is NULL.
        EventHasNoResultsError: no results in event AND athlete_ids is None.
    """
    season, valida_num = await resolve_event_scope(db, race_event_id)
    members = await resolve_group_members(db, race_event_id, athlete_ids, club_ids)

    if not members and athlete_ids is None:
        raise EventHasNoResultsError(race_event_id)

    items: list[GroupRunItem] = []

    for member in members:
        # 1. Check for existing active run. ``event_id=race_event_id``
        #    (hotfix "identidad de válida"): sin esto, dos copas con el
        #    mismo valida_num "veían" el run activo de la otra.
        active_run_id = await find_active_run(
            db, member.athlete_id, season, valida_num, event_id=race_event_id
        )
        if active_run_id is not None:
            items.append(
                GroupRunItem(
                    athlete_id=member.athlete_id,
                    athlete_display_name=member.display_name,
                    run_id=active_run_id,
                    outcome=GroupRunOutcome.already_running,
                    detail="Ya hay un análisis en curso para este deportista.",
                )
            )
            continue

        # 2. Generate run_id + prepare initial state (mirrors start_run).
        run_id = uuid.uuid4().hex
        started_at = _utc_now()

        # Resolve full AI context (age, sex, LTAD group, maturation status,
        # forbidden_names) for the initial state — same helper used by
        # ``race_analysis.py::start_run`` (best-effort, same pattern as that
        # router). Bug #2 (hotfix "identidad de válida"): before this,
        # ``launch_group`` only resolved ``athlete_age`` and NEVER set
        # ``forbidden_names`` — a real privacy gap, since coach-note
        # scrubbing in ``anonymize.py`` depends on it.
        _ath: Optional[Athlete] = None
        ai_context = AthleteAiContext(
            athlete_age=None,
            athlete_sex=None,
            ltad_group=None,
            maturation_status=None,
            forbidden_names=[],
        )
        try:
            # FR-014: ``_load_members`` ya excluye archivados; el filtro se
            # repite aquí (defensa en profundidad) para que un atleta
            # archivado entre la selección y el lanzamiento no aporte
            # contexto al estado inicial del run.
            _ath_result = await db.execute(
                select(Athlete).where(
                    Athlete.id == member.athlete_id,
                    Athlete.deleted_at.is_(None),
                )
            )
            _ath = _ath_result.scalar_one_or_none()
            if _ath is not None:
                ai_context = await resolve_athlete_ai_context(db, _ath)
        except Exception:  # noqa: BLE001
            logger.debug(
                "group_launch: could not resolve AI context for athlete_id=%s",
                member.athlete_id,
            )

        initial_state: dict[str, Any] = {
            "athlete_id": member.athlete_id,
            "season": season,
            "valida_nums": [valida_num],
            "coach_id": requested_by_user_id,
            "explain_mode": explain_mode,
            "run_id": run_id,
            # Hotfix "identidad de válida" (Bug #2): el ancla del run — un
            # lanzamiento grupal SIEMPRE nace desde un evento concreto.
            "event_id": race_event_id,
            "forbidden_names": ai_context.forbidden_names,
            "athlete_sex": ai_context.athlete_sex,
        }
        if ai_context.athlete_age is not None:
            initial_state["athlete_age"] = ai_context.athlete_age
        if ai_context.ltad_group is not None:
            initial_state["ltad_group"] = ai_context.ltad_group
        if _ath is not None:
            initial_state["maturation_status"] = ai_context.maturation_status

        # 3. Persist the agent_runs row before spawning the task.
        try:
            await _insert_agent_run(
                db,
                run_id=run_id,
                athlete_id=member.athlete_id,
                season=season,
                valida_nums=[valida_num],
                explain_mode=explain_mode,
                started_at=started_at,
                requested_by_user_id=requested_by_user_id,
                event_id=race_event_id,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "group_launch: insert agent_runs failed for athlete_id=%s",
                member.athlete_id,
            )
            items.append(
                GroupRunItem(
                    athlete_id=member.athlete_id,
                    athlete_display_name=member.display_name,
                    run_id=None,
                    outcome=GroupRunOutcome.error,
                    detail="Error interno al registrar el análisis. Intenta de nuevo.",
                )
            )
            continue

        # 3b. Fila de auditoría del lanzamiento (§4.9 audit-recording.md),
        # mismo patrón que ``routers/race_analysis.py::start_run`` /
        # ``routers/athlete_race_analysis.py::start_athlete_run``: un run
        # NUEVO es siempre ``create``, sea cual sea el punto de entrada.
        _new_run_id_result = await db.execute(
            text("SELECT id FROM agent_runs WHERE external_run_id = :rid LIMIT 1"),
            {"rid": run_id},
        )
        _new_run_row = _new_run_id_result.first()
        if _new_run_row is not None:
            _requested_by_user = await db.get(User, requested_by_user_id)
            await record_audit(
                db,
                action=AuditAction.create,
                entity_type=AuditEntityType.agent_run,
                entity_id=int(_new_run_row[0]),
                actor=_requested_by_user,
                club_id=_ath.club_id if _ath is not None else None,
                athlete_id=member.athlete_id,
            )

        # 4. Submit to the runner (backpressure → skip, other errors → error).
        try:
            await submit_run(
                run_id,
                initial_state,
                on_complete=_make_on_complete(run_id),
            )
        except RunBackpressureError:
            # Mark the already-inserted row as cancelled so it doesn't linger.
            try:
                from app.routers.race_analysis import _update_run_status

                await _update_run_status(
                    db, run_id, "cancelled", error_message="backpressure: no slots"
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "group_launch: failed to cancel run=%s after backpressure",
                    run_id,
                )
            items.append(
                GroupRunItem(
                    athlete_id=member.athlete_id,
                    athlete_display_name=member.display_name,
                    run_id=None,
                    outcome=GroupRunOutcome.backpressure,
                    detail=(
                        "Límite de análisis simultáneos alcanzado. "
                        "Intenta de nuevo en unos minutos."
                    ),
                )
            )
            continue
        except Exception:  # noqa: BLE001
            logger.exception(
                "group_launch: submit_run raised unexpected error for run=%s",
                run_id,
            )
            items.append(
                GroupRunItem(
                    athlete_id=member.athlete_id,
                    athlete_display_name=member.display_name,
                    run_id=None,
                    outcome=GroupRunOutcome.error,
                    detail="Error inesperado al iniciar el análisis.",
                )
            )
            continue

        items.append(
            GroupRunItem(
                athlete_id=member.athlete_id,
                athlete_display_name=member.display_name,
                run_id=run_id,
                outcome=GroupRunOutcome.started,
                detail=None,
            )
        )

    started_count = sum(1 for i in items if i.outcome == GroupRunOutcome.started)
    skipped_count = len(items) - started_count

    return GroupRunLaunchResponse(
        race_event_id=race_event_id,
        season=season,
        valida_num=valida_num,
        started_count=started_count,
        skipped_count=skipped_count,
        items=items,
    )


# ---------------------------------------------------------------------------
# 5. list_event_runs
# ---------------------------------------------------------------------------


async def list_event_runs(
    db: AsyncSession,
    race_event_id: int,
    active_only: bool = True,
    club_ids: Optional[set[int]] = None,
) -> RaceEventRunsResponse:
    """List analysis runs associated with the given race event.

    Resolution mirrors ``run_staleness.invalidate_runs_for_event``:
    a run belongs to event E iff:
    - ``input_json.season == series.season_year``
    - ``E.sequence_number ∈ input_json.valida_nums``
    - The athlete has a result in E (athlete_id IS NOT NULL, deleted_at IS NULL).

    Args:
        db: Active async DB session.
        race_event_id: PK of the ``race_events`` row.
        active_only: If True (default), return only runs in status
            ``running`` or ``awaiting_hitl``. If False, also include
            terminal runs with ``started_at >= now - 7 days``.

    Returns:
        :class:`RaceEventRunsResponse` with the matching runs.

    Raises:
        RaceEventNotFoundError: if the event does not exist.
        EventNotAnalyzableError: if sequence_number is NULL.
    """
    season, valida_num = await resolve_event_scope(db, race_event_id)

    # Resolve athlete_ids with results in the event (for final filtering).
    members = await resolve_group_members(
        db, race_event_id, athlete_ids=None, club_ids=club_ids
    )
    athlete_id_to_name: dict[int, str] = {m.athlete_id: m.display_name for m in members}
    if not athlete_id_to_name:
        # No results in event → return empty list (not an error for list endpoint).
        return RaceEventRunsResponse(race_event_id=race_event_id, runs=[])

    # Fetch candidate runs. We load all non-cancelled rows and filter
    # by input_json in Python (same approach as find_active_run).
    if active_only:
        status_clause = "status IN ('running', 'awaiting_hitl')"
        params: dict[str, Any] = {}
    else:
        cutoff = _utc_now() - timedelta(days=7)
        status_clause = (
            "("
            "  status IN ('running', 'awaiting_hitl')"
            "  OR (status IN ('completed', 'rejected', 'failed', 'cancelled')"
            "      AND started_at >= :cutoff)"
            ")"
        )
        params = {"cutoff": cutoff}

    result = await db.execute(
        text(
            f"""
            SELECT external_run_id, status, started_at,
                   input_json, stale_since
            FROM agent_runs
            WHERE {status_clause}
              AND input_json IS NOT NULL
            ORDER BY started_at DESC
            """  # noqa: S608  — status_clause is a literal, not user input
        ),
        params,
    )
    rows = result.fetchall() if hasattr(result, "fetchall") else []

    run_items: list[RaceEventRunItem] = []
    seen_run_ids: set[str] = set()

    for row in rows:
        if hasattr(row, "_mapping"):
            m = row._mapping
            ext_run_id = str(m["external_run_id"])
            db_status = str(m["status"])
            started_at_raw = m["started_at"]
            raw_json = m["input_json"]
            stale_since = m["stale_since"]
        else:
            ext_run_id = str(row[0])
            db_status = str(row[1])
            started_at_raw = row[2]
            raw_json = row[3]
            stale_since = row[4]

        if ext_run_id in seen_run_ids:
            continue

        # Deserialize input_json.
        if isinstance(raw_json, str):
            try:
                payload = json.loads(raw_json)
            except (ValueError, TypeError):
                continue
        elif isinstance(raw_json, dict):
            payload = raw_json
        else:
            continue

        if not isinstance(payload, dict):
            continue

        # Validate season + valida_num membership.
        if payload.get("season") != season:
            continue
        vns = payload.get("valida_nums")
        if vns is not None and valida_num not in vns:
            continue
        # vns=None means "all válidas" — include.

        run_athlete_id = payload.get("athlete_id")
        if run_athlete_id is None or int(run_athlete_id) not in athlete_id_to_name:
            continue

        # Normalize started_at to tz-aware datetime.
        if isinstance(started_at_raw, datetime):
            if started_at_raw.tzinfo is None:
                started_at_aware = started_at_raw.replace(tzinfo=timezone.utc)
            else:
                started_at_aware = started_at_raw
        else:
            started_at_aware = _utc_now()

        state = _DB_STATUS_TO_RUN_STATE.get(db_status, RunState.RUNNING)
        stale = stale_since is not None

        run_items.append(
            RaceEventRunItem(
                run_id=ext_run_id,
                athlete_id=int(run_athlete_id),
                athlete_display_name=athlete_id_to_name[int(run_athlete_id)],
                state=state,
                started_at=started_at_aware,
                stale=stale,
            )
        )
        seen_run_ids.add(ext_run_id)

    return RaceEventRunsResponse(race_event_id=race_event_id, runs=run_items)


__all__ = [
    "RaceEventNotFoundError",
    "EventNotAnalyzableError",
    "EventHasNoResultsError",
    "Member",
    "AthleteAiContext",
    "resolve_athlete_ai_context",
    "resolve_events_for_season_valida",
    "resolve_event_scope",
    "resolve_group_members",
    "find_active_run",
    "launch_group",
    "list_event_runs",
]
