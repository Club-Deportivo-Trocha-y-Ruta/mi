"""Construcción pura de ``StageLog`` a partir del snapshot de métricas.

Implementa ``specs/038-newsletter-bitacora-redesign/data-model.md`` §1 y las
funciones puras (`trail_waypoints`, `effort_profile`, `summit`,
`next_segment`, `stage_number`) que ``build_stage_log`` combina con:

  - ``snapshot``: el dict ``{"email_blocks": ..., "pdf_only_blocks": ...}``
    que produce ``newsletter_builder.build_newsletter_metrics`` (misma forma,
    reutilizada tal cual — no se reinventa).
  - ``narrative``: la salida IA v2 (``StageNarrative``, feature 038 Wave 2 —
    aún no implementada). Se referencia de forma estructural
    (:class:`StageNarrativeLike`) para no acoplar este módulo a
    ``app/services/ai/use_cases/athlete_monthly_newsletter_v2.py``, que se
    construye en paralelo en otra tarea.
  - ``family_input``: los campos deterministas de la lectura del analista
    (``valida_label``, ``source_insight_id``) que produce
    ``family_translation.select_insight`` (feature 038 Wave 1, otra tarea en
    paralelo) — aquí solo se consume su forma (``Mapping``), sin importar
    ese módulo.
  - ``overrides``: ``stage_overrides`` persistido por el coach (edición
    manual, ver ``AthleteNewsletterPatch``).
  - ``coach_note`` / ``hidden_blocks``: columnas propias de la fila del
    boletín.

Este módulo NO hace I/O: todo lo que necesita ya viaja en ``snapshot`` (más
los parámetros explícitos). Eso permite testear cada función con fixtures de
diccionario simples, sin base de datos ni mocks de sesión async.

Diseño no cubierto explícitamente por data-model.md, decidido aquí (ver
reporte de la tarea para el detalle completo):

  - ``stage_number`` necesita la fecha de la primera sesión histórica del
    atleta, que no cabe en un snapshot mensual. Se añadió
    ``email_blocks["athlete_first_session_date"]`` en
    ``newsletter_builder.build_newsletter_metrics`` (cambio aditivo) en vez
    de agregar un parámetro nuevo a ``build_stage_log`` — mantiene la firma
    exacta pedida y sigue siendo "puro" desde la perspectiva de este módulo.
  - El "mejor entrenamiento" del mes (waypoint ``best_session`` / cima de
    entrenamiento) usa el nuevo bloque ``pdf_only_blocks["weekly"]``
    (T104/T101 aditivo en ``newsletter_builder.py``), que trae rúbrica
    promedio y RPE por sesión — dato que no existía antes en el snapshot.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Protocol, runtime_checkable

from app.services.training.newsletter_static_copy import (
    static_family_compass,
    static_next_segment,
    static_observations,
    static_stage_title,
    static_summit_caption,
)
from app.services.training.stage_log import (
    AnalystReading,
    BadgeView,
    BlockState,
    EffortWeek,
    FamilyCompass,
    NextRace,
    NextSegment,
    Observation,
    PhotoView,
    StageLog,
    Summit,
    SummitKind,
    Waypoint,
    WaypointKind,
    badge_label_for,
)

__all__ = [
    "StageNarrativeLike",
    "AnalystReadingTextLike",
    "build_stage_log",
    "trail_waypoints",
    "effort_profile",
    "summit",
    "next_segment",
    "stage_number",
]


# ---------------------------------------------------------------------------
# Tipos estructurales (duck typing) para no importar la capa IA (Wave 2).
# ---------------------------------------------------------------------------


@runtime_checkable
class AnalystReadingTextLike(Protocol):
    headline_family: str
    action_family: str


@runtime_checkable
class StageNarrativeLike(Protocol):
    """Forma esperada de ``StageNarrative`` (use_cases/athlete_monthly_newsletter_v2.py).

    Protocol estructural: cualquier objeto (o el propio ``StageNarrative``
    real cuando exista) con estos atributos sirve, sin necesidad de un
    import cruzado entre Wave 1 y Wave 2.
    """

    stage_title: str
    summit_caption: str | None
    observations: list[Observation]
    next_segment_text: str | None
    family_compass: FamilyCompass | Any
    analyst_reading: AnalystReadingTextLike | None


# ---------------------------------------------------------------------------
# Constantes deterministas
# ---------------------------------------------------------------------------

_MONTH_ABBR_ES: tuple[str, ...] = (
    "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sep", "oct", "nov", "dic",
)

# Racha mínima (sesiones consecutivas asistidas) para aparecer como waypoint.
_STREAK_MILESTONE_THRESHOLD = 5

# Orden de prioridad al recortar la ruta al tope de 6 waypoints (next_race
# se agrega aparte y siempre queda al final por ser la única fecha futura).
_TRAIL_PRIORITY = ("race", "badge", "streak", "best_session", "first_session")

_TRAIL_CAP = 6


# ---------------------------------------------------------------------------
# Helpers de fecha / texto puros
# ---------------------------------------------------------------------------


def _parse_date(value: Any) -> date | None:
    """Parsea una fecha ISO (``date`` o ``str``); tolera ``None`` y ruido."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or text in ("None", "NaT", "nan"):
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _week_label(start: date, end: date) -> str:
    """Etiqueta legible de una semana ISO (``"1–7 jun"``), cruzando meses
    cuando corresponde (``"29 jun–5 jul"``)."""
    if start.month == end.month:
        return f"{start.day}–{end.day} {_MONTH_ABBR_ES[start.month - 1]}"
    return (
        f"{start.day} {_MONTH_ABBR_ES[start.month - 1]}–"
        f"{end.day} {_MONTH_ABBR_ES[end.month - 1]}"
    )


def _athlete_reference(athlete_sex: str | None) -> str:
    """Pronombre de referencia en español para el atleta.

    Mismo criterio que ``newsletter_builder._derive_athlete_reference`` /
    el use case de IA v1 — se duplica a propósito (convención ya establecida
    en este repo, ver comentario en ``newsletter_builder.py``) para no
    acoplar capas.
    """
    if athlete_sex == "M":
        return "su hijo"
    if athlete_sex == "F":
        return "su hija"
    return "su hijo/a"


def _race_position_gap_sublabel(result: Mapping[str, Any]) -> str | None:
    """Sublabel de un waypoint de carrera: SOLO el propio gap del atleta
    (data-model.md: ``sublabel`` documenta "own gap only")."""
    position = result.get("position")
    gap_pct = result.get("gap_to_winner_pct")
    if position == 1 or gap_pct is None:
        return None
    try:
        return f"+{float(gap_pct):.1f} % al P1"
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# stage_number
# ---------------------------------------------------------------------------


def stage_number(first_session_date: date | None, year: int, month: int) -> int:
    """Número de etapa: meses transcurridos desde la primera sesión de la
    temporada del atleta (1-based). Sin fecha de referencia, la etapa
    reportada es siempre la 1 (no se puede afirmar nada anterior)."""
    if first_session_date is None:
        return 1
    months = (year - first_session_date.year) * 12 + (month - first_session_date.month) + 1
    return max(months, 1)


# ---------------------------------------------------------------------------
# trail_waypoints
# ---------------------------------------------------------------------------


def trail_waypoints(
    snapshot: dict[str, Any],
    *,
    month_start: date,
    month_end: date,
    first_session_date: date | None,
) -> list[Waypoint]:
    """Ruta del mes: hasta 6 waypoints, ``next_race`` siempre al final.

    Prioridad al recortar cuando hay más candidatos que espacio disponible:
    ``race > badge > streak > best_session > first_session``. Como todos los
    waypoints "del mes" caen dentro de ``[month_start, month_end]`` y
    ``next_race`` es, por definición, una fecha futura, ordenar el resultado
    final por fecha ascendente ya deja ``next_race`` al final sin lógica
    especial adicional.
    """
    email_blocks = snapshot.get("email_blocks") or {}
    pdf_only_blocks = snapshot.get("pdf_only_blocks") or {}

    candidates_by_kind: dict[str, list[Waypoint]] = {
        "race": [],
        "badge": [],
        "streak": [],
        "best_session": [],
        "first_session": [],
    }

    # --- race ---------------------------------------------------------
    race_results = ((email_blocks.get("race_results") or {}).get("results")) or []
    for result in sorted(race_results, key=lambda r: r.get("event_date") or ""):
        event_date = _parse_date(result.get("event_date"))
        if event_date is None:
            continue
        position = result.get("position")
        label = result.get("label") or "Carrera"
        display_label = f"{label} · P{position}" if position else label
        candidates_by_kind["race"].append(
            Waypoint(
                kind=WaypointKind.RACE,
                date=event_date,
                label=display_label,
                sublabel=_race_position_gap_sublabel(result),
                icon="map-pin",
            )
        )

    # --- badge ----------------------------------------------------------
    badge_items = ((email_blocks.get("badges") or {}).get("items")) or []
    for badge in sorted(badge_items, key=lambda b: b.get("earned_at") or ""):
        earned_at = _parse_date(badge.get("earned_at")) or month_end
        code = badge.get("badge_type", "")
        candidates_by_kind["badge"].append(
            Waypoint(
                kind=WaypointKind.BADGE,
                date=earned_at,
                label=badge_label_for(code),
                sublabel=None,
                icon="award",
            )
        )

    # --- streak -----------------------------------------------------------
    streak_sessions = (email_blocks.get("attendance") or {}).get("streak_sessions") or 0
    if streak_sessions >= _STREAK_MILESTONE_THRESHOLD:
        candidates_by_kind["streak"].append(
            Waypoint(
                kind=WaypointKind.STREAK,
                date=month_end,
                label=f"Racha de {streak_sessions}",
                sublabel=None,
                icon="flame",
            )
        )

    # --- best_session -------------------------------------------------
    weekly = pdf_only_blocks.get("weekly") or []
    attended_weekly = [w for w in weekly if w.get("attended")]

    def _session_score(entry: Mapping[str, Any]) -> float:
        rubric_avg = entry.get("rubric_avg")
        if rubric_avg is not None:
            return float(rubric_avg)
        return float(entry.get("rpe") or 0)

    if attended_weekly:
        best = max(attended_weekly, key=_session_score)
        if _session_score(best) > 0:
            best_date = _parse_date(best.get("date"))
            if best_date is not None:
                rubric_avg = best.get("rubric_avg")
                label = (
                    f"Mejor sesión · técnica {rubric_avg}/5"
                    if rubric_avg is not None
                    else f"Mejor sesión · RPE {best.get('rpe')}"
                )
                candidates_by_kind["best_session"].append(
                    Waypoint(
                        kind=WaypointKind.BEST_SESSION,
                        date=best_date,
                        label=label,
                        sublabel=None,
                        icon="star",
                    )
                )

    # --- first_session -----------------------------------------------
    if first_session_date is not None and month_start <= first_session_date <= month_end:
        candidates_by_kind["first_session"].append(
            Waypoint(
                kind=WaypointKind.FIRST_SESSION,
                date=first_session_date,
                label="Primera sesión de la temporada",
                sublabel=None,
                icon="flag",
            )
        )

    # --- next_race (siempre al final, fuera del recorte por prioridad) --
    next_race_events = (email_blocks.get("calendar") or {}).get("next_race_events") or []
    next_race_waypoint: Waypoint | None = None
    if next_race_events:
        event = next_race_events[0]
        event_date = _parse_date(event.get("date"))
        if event_date is not None:
            valida = event.get("valida") or ""
            label_map = {"CD": "Campeonato Departamental", "CN": "Campeonato Nacional"}
            label = label_map.get(valida, f"Próxima: Válida {valida}" if valida else "Próxima carrera")
            next_race_waypoint = Waypoint(
                kind=WaypointKind.NEXT_RACE,
                date=event_date,
                label=label,
                sublabel=event.get("location"),
                icon="compass",
                is_future=True,
            )

    remaining_cap = _TRAIL_CAP - (1 if next_race_waypoint is not None else 0)
    selected: list[Waypoint] = []
    for kind in _TRAIL_PRIORITY:
        for candidate in candidates_by_kind[kind]:
            if len(selected) >= remaining_cap:
                break
            selected.append(candidate)

    selected.sort(key=lambda w: w.date)
    if next_race_waypoint is not None:
        selected.append(next_race_waypoint)

    return selected[:_TRAIL_CAP]


# ---------------------------------------------------------------------------
# effort_profile
# ---------------------------------------------------------------------------


def effort_profile(snapshot: dict[str, Any]) -> list[EffortWeek]:
    """Perfil de esfuerzo semanal (altimetría), agrupado por semana ISO.

    Cruza límites de mes correctamente: una semana ISO que empieza en un mes
    y termina en el siguiente se agrupa una sola vez (por ``isocalendar()``),
    con una etiqueta que muestra ambos meses (ver :func:`_week_label`).
    """
    weekly = (snapshot.get("pdf_only_blocks") or {}).get("weekly") or []

    buckets: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for entry in weekly:
        entry_date = _parse_date(entry.get("date"))
        if entry_date is None:
            continue
        iso_year, iso_week, _ = entry_date.isocalendar()
        buckets.setdefault((iso_year, iso_week), []).append({**entry, "_date": entry_date})

    weeks: list[EffortWeek] = []
    for (iso_year, iso_week), entries in sorted(buckets.items()):
        start = date.fromisocalendar(iso_year, iso_week, 1)
        end = date.fromisocalendar(iso_year, iso_week, 7)
        attended = sum(1 for e in entries if e.get("attended"))
        rpes = [e["rpe"] for e in entries if e.get("rpe") is not None]
        mean_rpe = round(sum(rpes) / len(rpes), 1) if rpes else None
        weeks.append(
            EffortWeek(
                week_label=_week_label(start, end),
                sessions_planned=len(entries),
                sessions_attended=attended,
                mean_rpe=mean_rpe,
            )
        )
    return weeks


# ---------------------------------------------------------------------------
# summit
# ---------------------------------------------------------------------------


def summit(snapshot: dict[str, Any]) -> Summit | None:
    """La cima del mes: mejor resultado de carrera, o la mejor sesión de
    entrenamiento cuando no hubo carreras (edge case: mes sin carrera).

    Sin datos (mes de cero asistencia y sin carreras) retorna ``None`` — la
    bitácora omite el bloque en vez de mostrar un placeholder (principio 024:
    sin copy de reproche)."""
    email_blocks = snapshot.get("email_blocks") or {}
    race_block = email_blocks.get("race_results") or {}
    results = race_block.get("results") or []
    ranked = [r for r in results if r.get("position") is not None]

    if ranked:
        best = min(ranked, key=lambda r: r["position"])
        position = best["position"]
        label = best.get("label") or "la carrera"
        title = f"P{position} en la {label}"
        gap_pct = best.get("gap_to_winner_pct")
        detail_parts = [best.get("category_label")]
        if position != 1 and gap_pct is not None:
            detail_parts.append(f"+{float(gap_pct):.1f} % al P1")
        detail = " · ".join(p for p in detail_parts if p) or None
        return Summit(
            kind=SummitKind.RACE,
            title=title,
            detail=detail,
            caption=None,
            date=_parse_date(best.get("event_date")),
        )

    weekly = (snapshot.get("pdf_only_blocks") or {}).get("weekly") or []
    attended = [w for w in weekly if w.get("attended")]
    if not attended:
        return None

    def _score(entry: Mapping[str, Any]) -> float:
        rubric_avg = entry.get("rubric_avg")
        if rubric_avg is not None:
            return float(rubric_avg)
        return float(entry.get("rpe") or 0)

    best_session = max(attended, key=_score)
    if _score(best_session) <= 0:
        return None

    return Summit(
        kind=SummitKind.TRAINING,
        title="Mejor sesión de entrenamiento del mes",
        detail=None,
        caption=None,
        date=_parse_date(best_session.get("date")),
    )


# ---------------------------------------------------------------------------
# next_segment
# ---------------------------------------------------------------------------


def next_segment(snapshot: dict[str, Any]) -> NextSegment | None:
    """El próximo tramo: focos técnicos planificados (024) + próxima carrera.

    ``None`` cuando no hay ni focos planificados ni carrera próxima (nada
    que anticipar todavía)."""
    pdf_only_blocks = snapshot.get("pdf_only_blocks") or {}
    email_blocks = snapshot.get("email_blocks") or {}

    focus_groups_raw = pdf_only_blocks.get("next_focus_groups") or []
    focus_group_names = [g["name"] for g in focus_groups_raw[:4] if g.get("name")]

    next_race_events = (email_blocks.get("calendar") or {}).get("next_race_events") or []
    next_race: NextRace | None = None
    if next_race_events:
        event = next_race_events[0]
        event_date = _parse_date(event.get("date"))
        if event_date is not None:
            valida = event.get("valida") or ""
            label_map = {"CD": "Campeonato Departamental", "CN": "Campeonato Nacional"}
            label = label_map.get(valida, f"Válida {valida}" if valida else "Próxima carrera")
            priority = event.get("priority")
            priority_label = f"Prioridad {priority}" if priority in ("A", "B") else None
            next_race = NextRace(
                label=label,
                date=event_date,
                venue=event.get("location"),
                priority_label=priority_label,
            )

    if not focus_group_names and next_race is None:
        return None

    return NextSegment(focus_groups=focus_group_names, next_race=next_race, text=None)


# ---------------------------------------------------------------------------
# build_stage_log
# ---------------------------------------------------------------------------


def _get_field(obj: Any, key: str) -> Any:
    """Lee ``key`` de ``obj`` sin asumir su forma exacta.

    El router (otra tarea, en paralelo) persiste ``narrative`` como el JSON
    crudo de ``athlete_monthly_newsletters.ai_narrative`` — un ``dict`` plano
    al leerlo de la columna JSON — mientras que las pruebas y un eventual
    ``StageNarrative`` real (Wave 2) lo pasan como objeto con atributos. Esta
    función acepta ambas formas (``Mapping`` u objeto) para que
    ``build_stage_log`` no le importe cuál llegó. Igual aplica a
    ``family_input`` (``FamilyInsightInput`` + id, o el dict equivalente).
    """
    if obj is None:
        return None
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


def _narrative_field(narrative: Any, key: str) -> Any:
    return _get_field(narrative, key)


def _coerce_observations(raw: Any) -> list[Observation]:
    return [o if isinstance(o, Observation) else Observation(**o) for o in (raw or [])]


def _coerce_family_compass(raw: Any) -> FamilyCompass:
    if isinstance(raw, FamilyCompass):
        return raw
    if hasattr(raw, "model_dump"):
        return FamilyCompass(**raw.model_dump())
    return FamilyCompass(**raw)


def _badges_from_snapshot(email_blocks: dict[str, Any]) -> list[BadgeView]:
    items = ((email_blocks.get("badges") or {}).get("items")) or []
    out: list[BadgeView] = []
    for item in items:
        code = item.get("badge_type", "")
        out.append(
            BadgeView(
                code=code,
                label=badge_label_for(code),
                icon="award",
                earned_at=_parse_date(item.get("earned_at")),
            )
        )
    return out


def _photos_from_snapshot(email_blocks: dict[str, Any]) -> list[PhotoView]:
    items = ((email_blocks.get("photos") or {}).get("items")) or []
    out: list[PhotoView] = []
    for item in items:
        thumbnail = item.get("thumbnail_url") or item.get("storage_url")
        if not thumbnail:
            continue
        out.append(PhotoView(thumbnail_url=thumbnail, caption=item.get("caption")))
    return out


def _is_current_month(year: int, month: int) -> bool:
    today = date.today()
    return today.year == year and today.month == month


def build_stage_log(
    snapshot: dict[str, Any],
    narrative: StageNarrativeLike | Mapping[str, Any] | None,
    family_input: Mapping[str, Any] | Any | None,
    overrides: Mapping[str, Any] | None,
    coach_note: str | None,
    hidden_blocks: list[str] | None,
    athlete_sex: str | None,
    athlete_first_name: str,
) -> StageLog:
    """Combina el snapshot determinista + la narrativa IA (opcional) + los
    overrides del coach en un ``StageLog`` completo.

    Precedencia por bloque: ``overrides`` (edición manual) > ``narrative``
    (IA) > copia estática determinista (``newsletter_static_copy`` v2). Sin
    IA y sin override, cada bloque narrativo cae a su función estática
    correspondiente (AC-2.5: la bitácora siempre se genera, con o sin
    consentimiento IA).

    ``hidden_blocks`` NO vacía los datos aquí (eso lo hace
    :func:`stage_log.to_parent_dto` al derivar el DTO del padre): aquí solo
    marca el ``block_states`` correspondiente como ``hidden`` para que el
    studio del coach pueda mostrar/ocultar sin perder el contenido.
    """
    email_blocks = snapshot.get("email_blocks") or {}
    overrides = dict(overrides or {})
    hidden = set(hidden_blocks or [])

    period = email_blocks.get("period") or {}
    year = int(period.get("year"))
    month = int(period.get("month"))
    period_label = period.get("label", "")

    import calendar as _calendar_mod

    month_start = date(year, month, 1)
    month_end = date(year, month, _calendar_mod.monthrange(year, month)[1])

    first_session_date = _parse_date(email_blocks.get("athlete_first_session_date"))
    athlete_reference = _athlete_reference(athlete_sex)

    trail = trail_waypoints(
        snapshot,
        month_start=month_start,
        month_end=month_end,
        first_session_date=first_session_date,
    )
    summit_obj = summit(snapshot)
    effort = effort_profile(snapshot)
    segment = next_segment(snapshot)

    block_states: dict[str, BlockState] = {}

    # --- stage_title --------------------------------------------------
    if "stage_title" in overrides:
        stage_title = overrides["stage_title"]
        block_states["stage_title"] = BlockState.EDITED
    elif _narrative_field(narrative, "stage_title"):
        stage_title = _narrative_field(narrative, "stage_title")
        block_states["stage_title"] = BlockState.AI
    else:
        stage_title = static_stage_title(email_blocks, athlete_reference)
        block_states["stage_title"] = BlockState.STATIC

    # --- observations ---------------------------------------------------
    if "observations" in overrides:
        observations = _coerce_observations(overrides["observations"])
        block_states["observations"] = BlockState.EDITED
    elif _narrative_field(narrative, "observations"):
        observations = _coerce_observations(_narrative_field(narrative, "observations"))
        block_states["observations"] = BlockState.AI
    else:
        observations = static_observations(email_blocks, athlete_reference)
        block_states["observations"] = BlockState.STATIC if observations else BlockState.EMPTY

    # --- summit caption -------------------------------------------------
    if summit_obj is not None:
        if "summit_caption" in overrides:
            summit_obj = summit_obj.model_copy(update={"caption": overrides["summit_caption"]})
            block_states["summit_caption"] = BlockState.EDITED
        elif _narrative_field(narrative, "summit_caption"):
            summit_obj = summit_obj.model_copy(update={"caption": _narrative_field(narrative, "summit_caption")})
            block_states["summit_caption"] = BlockState.AI
        else:
            caption = static_summit_caption(summit_obj, email_blocks, athlete_reference)
            summit_obj = summit_obj.model_copy(update={"caption": caption})
            block_states["summit_caption"] = BlockState.STATIC
    else:
        block_states["summit_caption"] = BlockState.EMPTY

    # --- analyst_reading --------------------------------------------
    # ``family_input`` en teoría siempre trae ``valida_label`` +
    # ``source_insight_id`` (data-model.md §1: FamilyInsightInput + el id del
    # insight elegido en select_insight) — pero se accede de forma tolerante
    # (dict o objeto) porque el llamador real (router, otra tarea en
    # paralelo) todavía compone ese valor de forma provisional.
    analyst_reading: AnalystReading | None = None
    ai_reading = _narrative_field(narrative, "analyst_reading")
    if family_input and ai_reading is not None:
        headline_family = _get_field(ai_reading, "headline_family")
        action_family = _get_field(ai_reading, "action_family")
        valida_label = _get_field(family_input, "valida_label") or ""
        source_insight_id = _get_field(family_input, "source_insight_id")
        if headline_family and action_family and source_insight_id is not None:
            analyst_reading = AnalystReading(
                headline_family=headline_family,
                action_family=action_family,
                valida_label=valida_label,
                source_insight_id=int(source_insight_id),
            )
            block_states["analyst_reading"] = BlockState.AI
        else:
            block_states["analyst_reading"] = BlockState.EMPTY
    else:
        block_states["analyst_reading"] = BlockState.EMPTY
    if "analyst_reading" in hidden:
        block_states["analyst_reading"] = BlockState.HIDDEN

    # --- next_segment.text ------------------------------------------
    if segment is not None:
        if "next_segment_text" in overrides:
            segment = segment.model_copy(update={"text": overrides["next_segment_text"]})
            block_states["next_segment_text"] = BlockState.EDITED
        elif _narrative_field(narrative, "next_segment_text"):
            segment = segment.model_copy(update={"text": _narrative_field(narrative, "next_segment_text")})
            block_states["next_segment_text"] = BlockState.AI
        else:
            text = static_next_segment(segment, athlete_reference)
            segment = segment.model_copy(update={"text": text})
            block_states["next_segment_text"] = BlockState.STATIC
    else:
        block_states["next_segment_text"] = BlockState.EMPTY

    # --- family_compass -------------------------------------------------
    if "family_compass" in overrides:
        family_compass = _coerce_family_compass(overrides["family_compass"])
        block_states["family_compass"] = BlockState.EDITED
    elif _narrative_field(narrative, "family_compass") is not None:
        family_compass = _coerce_family_compass(_narrative_field(narrative, "family_compass"))
        block_states["family_compass"] = BlockState.AI
    else:
        family_compass = static_family_compass(email_blocks, segment, athlete_reference)
        block_states["family_compass"] = BlockState.STATIC

    # --- badges / photos / coach_note ------------------------------------
    badges_list = _badges_from_snapshot(email_blocks)
    if "badges" in hidden:
        block_states["badges"] = BlockState.HIDDEN
    else:
        block_states["badges"] = BlockState.STATIC if badges_list else BlockState.EMPTY

    photos_list = _photos_from_snapshot(email_blocks)
    if "photos" in hidden:
        block_states["photos"] = BlockState.HIDDEN
    else:
        block_states["photos"] = BlockState.STATIC if photos_list else BlockState.EMPTY

    if not coach_note:
        block_states["coach_note"] = BlockState.EMPTY
    elif "coach_note" in hidden:
        block_states["coach_note"] = BlockState.HIDDEN
    else:
        block_states["coach_note"] = BlockState.EDITED

    return StageLog(
        stage_number=stage_number(first_session_date, year, month),
        period_label=period_label,
        is_current_month=_is_current_month(year, month),
        athlete_first_name=athlete_first_name,
        athlete_reference=athlete_reference,
        stage_title=stage_title,
        trail=trail,
        summit=summit_obj,
        observations=observations,
        analyst_reading=analyst_reading,
        effort_profile=effort,
        next_segment=segment,
        family_compass=family_compass,
        badges=badges_list,
        photos=photos_list,
        coach_note=coach_note,
        block_states=block_states,
        grounding_violations=[],
    )
