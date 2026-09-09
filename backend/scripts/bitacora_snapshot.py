"""Extrae el snapshot de la bitácora de etapa de uno o varios atletas
directamente desde la base de datos (lectura, sin escribir) y lo deja en
disco para que la narrativa la escriba Claude Code (skill ``bitacora-pdf``).

Reutiliza ``build_newsletter_metrics`` (misma agregación que el boletín del
producto) y la enriquece con datos que el boletín actual no usa: feedback
individual por sesión, volumen Strava, calendario/roster reales de la
próxima válida y notas del coach por resultado.

Uso (desde ``backend/`` con el venv activo)::

    python scripts/bitacora_snapshot.py --year 2026 --month 8 --athlete-id 12
    python scripts/bitacora_snapshot.py --year 2026 --month 8 --all
    python scripts/bitacora_snapshot.py --year 2026 --month 8 --all --env-file .env.production

Salida: ``<out>/<YYYY-MM>/athlete-<id>/snapshot.json`` (datos completos, con
nombre — NUNCA versionar) y ``brief.md`` (resumen anonimizado que sirve de
único insumo para la narrativa y de fuente de grounding numérico).

Garantías:
- Solo lee las variables ``MYSQL_*`` del env-file; nunca imprime su valor.
- La sesión termina SIEMPRE en ``rollback()`` — ``build_newsletter_metrics``
  evalúa insignias con ``flush`` y esa escritura se descarta.
- No se llama a ningún proveedor de IA.
"""

from __future__ import annotations

import argparse
import asyncio
import calendar
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

_MYSQL_KEYS = ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASS", "MYSQL_DB")
_MONTHS_ES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


# ---------------------------------------------------------------------------
# Entorno (antes de importar ``app.*``)
# ---------------------------------------------------------------------------


def _load_env(env_file: Path) -> None:
    from dotenv import dotenv_values

    if not env_file.exists():
        sys.exit(
            f"No existe {env_file}. Crea el archivo con MYSQL_HOST, MYSQL_PORT, "
            "MYSQL_USER, MYSQL_PASS y MYSQL_DB (está en .gitignore)."
        )
    values = dotenv_values(env_file)
    missing = [k for k in _MYSQL_KEYS if not values.get(k)]
    if missing:
        sys.exit(f"Faltan variables en {env_file.name}: {', '.join(missing)}")
    for key in _MYSQL_KEYS:
        os.environ[key] = str(values[key])
    # Nada más del env-file: el snapshot no necesita IA, email ni Strava.
    os.environ["APP_ENV"] = "development"
    os.environ["AI_ENABLED"] = "false"
    os.environ["STRAVA_ENABLED"] = "false"
    os.environ["AI_LOG_PROMPTS"] = "false"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _decimal_age(birth_date: date, on: date) -> float:
    return round((on - birth_date).days / 365.25, 1)


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _redact(text: str | None, forbidden: frozenset[str]) -> str | None:
    if not text:
        return None
    from app.services.ai.use_cases.monthly_report import _redact_names

    return _redact_names(text.strip(), forbidden)


# ---------------------------------------------------------------------------
# Extras (datos que el boletín del producto no usa)
# ---------------------------------------------------------------------------


async def _session_feedback(db, athlete_id: int, start: date, end: date) -> list[dict]:
    from sqlalchemy import select

    from app.models.training_session import (
        AttendanceStatus,
        SessionAttendance,
        SessionStatus,
        TrainingSession,
    )

    stmt = (
        select(TrainingSession, SessionAttendance)
        .join(SessionAttendance, SessionAttendance.session_id == TrainingSession.id)
        .where(
            SessionAttendance.athlete_id == athlete_id,
            TrainingSession.status == SessionStatus.EXECUTED,
            TrainingSession.scheduled_date >= start,
            TrainingSession.scheduled_date <= end,
        )
        .order_by(TrainingSession.scheduled_date)
    )
    rows = (await db.execute(stmt)).all()
    out: list[dict] = []
    for session, att in rows:
        out.append(
            {
                "date": _iso(session.scheduled_date),
                "kind": _enum_value(session.session_kind),
                "duration_min": session.duration_min,
                "location": session.location,
                "technical_focus": session.technical_focus,
                "objectives": session.objectives,
                "session_coach_notes": session.coach_notes,
                "attendance_status": _enum_value(att.status),
                "attended": att.status in (AttendanceStatus.PRESENTE, AttendanceStatus.TARDE),
                "excuse_reason": att.excuse_reason,
                "rpe": att.rpe_omni,
                "rubric_effort": att.rubric_effort,
                "rubric_attitude": att.rubric_attitude,
                "rubric_technique": att.rubric_technique,
                "individual_feedback": att.individual_feedback,
            }
        )
    return out


async def _strava_block(db, athlete_id: int, start: date, end: date) -> dict:
    from sqlalchemy import select

    from app.models.strava_activity import StravaActivity, StravaUpstreamState
    from app.models.strava_activity_lap import IntervalMatchResult

    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end + timedelta(days=1), datetime.min.time())
    stmt = (
        select(StravaActivity)
        .where(
            StravaActivity.athlete_id == athlete_id,
            StravaActivity.upstream_state == StravaUpstreamState.present,
            StravaActivity.start_date_local >= start_dt,
            StravaActivity.start_date_local < end_dt,
        )
        .order_by(StravaActivity.start_date_local)
    )
    activities = (await db.execute(stmt)).scalars().all()
    if not activities:
        return {"available": False, "activities": 0}

    distance_km = sum((a.distance_m or 0) for a in activities) / 1000
    elevation_m = sum((a.total_elevation_gain_m or 0) for a in activities)
    moving_s = sum((a.moving_time_s or a.elapsed_time_s or 0) for a in activities)
    hr_values = [a.average_heartrate for a in activities if a.average_heartrate]
    max_hr = [a.max_heartrate for a in activities if a.max_heartrate]
    linked = [a for a in activities if a.training_session_id is not None]

    match_stmt = select(IntervalMatchResult).where(
        IntervalMatchResult.strava_activity_id.in_([a.id for a in activities])
    )
    matches = (await db.execute(match_stmt)).scalars().all()
    interval_summaries = [
        {
            "strava_activity_id": m.strava_activity_id,
            "summary": (m.result_json or {}).get("summary"),
            "tolerance_pct": (m.result_json or {}).get("tolerance_pct"),
        }
        for m in matches
    ]

    return {
        "available": True,
        "activities": len(activities),
        "linked_to_club_sessions": len(linked),
        "outside_club_sessions": len(activities) - len(linked),
        "indoor_trainer": sum(1 for a in activities if a.is_trainer),
        "distance_km": round(distance_km, 1),
        "elevation_gain_m": round(elevation_m),
        "moving_hours": round(moving_s / 3600, 1),
        "avg_heartrate": round(sum(hr_values) / len(hr_values)) if hr_values else None,
        "max_heartrate": round(max(max_hr)) if max_hr else None,
        "sport_types": sorted({a.sport_type for a in activities}),
        "per_activity": [
            {
                "date": _iso(a.start_date_local.date()),
                "sport_type": a.sport_type,
                "distance_km": round((a.distance_m or 0) / 1000, 1),
                "elevation_gain_m": round(a.total_elevation_gain_m or 0),
                "moving_min": round((a.moving_time_s or a.elapsed_time_s or 0) / 60),
                "avg_heartrate": round(a.average_heartrate) if a.average_heartrate else None,
                "linked_to_club_session": a.training_session_id is not None,
            }
            for a in activities
        ],
        "interval_matches": interval_summaries,
    }


async def _upcoming_races(db, athlete_id: int, club_id: int, month_end: date) -> dict:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.calendar_event import CalendarEvent, EventAttendance, EventStatus, EventType
    from app.models.race_event import RaceEvent, RaceEventStatus
    from app.models.race_event_roster import RaceEventRoster

    horizon = month_end + timedelta(days=75)
    stmt = (
        select(RaceEvent)
        .where(
            RaceEvent.event_date > month_end,
            RaceEvent.event_date <= horizon,
            RaceEvent.status != RaceEventStatus.CANCELLED,
        )
        .options(selectinload(RaceEvent.series))
        .order_by(RaceEvent.event_date)
        .limit(3)
    )
    events = (await db.execute(stmt)).scalars().all()
    roster_rows = (
        await db.execute(
            select(RaceEventRoster).where(
                RaceEventRoster.athlete_id == athlete_id,
                RaceEventRoster.race_event_id.in_([e.id for e in events] or [0]),
            )
        )
    ).scalars().all()
    roster_by_event = {r.race_event_id: r for r in roster_rows}

    races = []
    for e in events:
        roster = roster_by_event.get(e.id)
        races.append(
            {
                "race_event_id": e.id,
                "name": e.name,
                "series": e.series.name if e.series else None,
                "series_kind": _enum_value(e.series.kind) if e.series else None,
                "sequence_number": e.sequence_number,
                "date": _iso(e.event_date),
                "location": e.location,
                "is_championship": e.is_championship,
                "roster_status": _enum_value(roster.status) if roster else None,
                # roster.note es texto libre del coach: se omite a propósito;
                # si algún día se expone en brief.md debe pasar por _redact().
            }
        )

    cal_stmt = (
        select(CalendarEvent)
        .where(
            CalendarEvent.club_id == club_id,
            CalendarEvent.event_type.in_([EventType.COMPETITION, EventType.CLUB_EVENT, EventType.GROUP_TRAINING]),
            CalendarEvent.status != EventStatus.CANCELLED,
            CalendarEvent.start_at > datetime.combine(month_end, datetime.max.time()),
            CalendarEvent.start_at <= datetime.combine(horizon, datetime.max.time()),
        )
        .order_by(CalendarEvent.start_at)
        .limit(5)
    )
    cal_events = (await db.execute(cal_stmt)).scalars().all()
    rsvp_rows = (
        await db.execute(
            select(EventAttendance).where(
                EventAttendance.athlete_id == athlete_id,
                EventAttendance.event_id.in_([c.id for c in cal_events] or [0]),
            )
        )
    ).scalars().all()
    rsvp_by_event = {r.event_id: r for r in rsvp_rows}
    calendar_items = [
        {
            "title": c.title,
            "event_type": _enum_value(c.event_type),
            "start_at": _iso(c.start_at),
            "location": c.location,
            "race_event_id": c.race_event_id,
            "rsvp_status": _enum_value(rsvp_by_event[c.id].rsvp_status) if c.id in rsvp_by_event else None,
        }
        for c in cal_events
    ]
    return {"race_events": races, "calendar_events": calendar_items}


async def _race_notes(db, athlete_id: int, start: date, end: date) -> list[dict]:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.race_event import RaceEvent
    from app.models.race_result import RaceResult

    stmt = (
        select(RaceResult)
        .join(RaceEvent, RaceEvent.id == RaceResult.event_id)
        .where(
            RaceResult.athlete_id == athlete_id,
            RaceResult.deleted_at.is_(None),
            RaceEvent.event_date >= start,
            RaceEvent.event_date <= end,
        )
        .options(selectinload(RaceResult.event))
        .order_by(RaceEvent.event_date)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "event_name": r.event.name if r.event else None,
            "date": _iso(r.event.event_date) if r.event else None,
            "location": r.event.location if r.event else None,
            "status": _enum_value(r.status),
            "position": r.position,
            "laps_behind": r.laps_behind,
            "points_awarded": r.points_awarded,
            "coach_note": r.coach_note,
            "conditions": {
                "climate": r.event.climate if r.event else None,
                "temperature_c": float(r.event.temperature_c) if r.event and r.event.temperature_c is not None else None,
                "surface": _enum_value(r.event.surface_condition) if r.event else None,
                "altitude_msnm": r.event.altitude_msnm if r.event else None,
                "weather_notes": r.event.weather_notes if r.event else None,
            },
        }
        for r in rows
    ]


async def _auto_family_input(db, athlete, year: int, month: int, has_ai_consent: bool) -> dict | None:
    """Lectura del analista: usa los insights adjuntos por el coach si ya hay
    boletín; si no, elige automáticamente los insights v3 activos de carreras
    del mes (misma elegibilidad que el producto)."""
    from sqlalchemy import select

    from app.models.athlete_ai_insight import AthleteAiInsight
    from app.models.athlete_newsletter import AthleteMonthlyNewsletter
    from app.models.race_event import RaceEvent
    from app.routers.athlete_monthly_newsletters import _resolve_family_insight

    existing = (
        await db.execute(
            select(AthleteMonthlyNewsletter).where(
                AthleteMonthlyNewsletter.athlete_id == athlete.id,
                AthleteMonthlyNewsletter.year == year,
                AthleteMonthlyNewsletter.month == month,
            )
        )
    ).scalar_one_or_none()
    if existing is not None and existing.selected_race_insight_ids:
        nl = existing
    else:
        start, end = _month_bounds(year, month)
        ids = (
            await db.execute(
                select(AthleteAiInsight.id)
                .join(RaceEvent, RaceEvent.id == AthleteAiInsight.event_id)
                .where(
                    AthleteAiInsight.athlete_id == athlete.id,
                    AthleteAiInsight.is_active == 1,
                    AthleteAiInsight.structured_json.is_not(None),
                    RaceEvent.event_date >= start,
                    RaceEvent.event_date <= end,
                )
                .order_by(AthleteAiInsight.coach_approved.desc(), AthleteAiInsight.generated_at.desc())
            )
        ).scalars().all()
        nl = AthleteMonthlyNewsletter(
            athlete_id=athlete.id, year=year, month=month, selected_race_insight_ids=list(ids) or None
        )
    return await _resolve_family_insight(db, nl, athlete, has_ai_consent)


# ---------------------------------------------------------------------------
# Brief anonimizado (insumo de la narrativa + fuente de grounding numérico)
# ---------------------------------------------------------------------------


def _fmt(value: Any, suffix: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.1f}{suffix}"
    return f"{value}{suffix}"


def render_brief(snap: dict) -> str:
    from app.services.training.stage_log import badge_label_for
    from app.services.training.stage_log_builder import effort_profile, next_segment

    forbidden = frozenset(snap["forbidden_names"])
    ref = snap["athlete_reference"]
    metrics = snap["metrics_snapshot"]
    eb = metrics.get("email_blocks", {})
    att = eb.get("attendance", {})
    tech = eb.get("technical", {})
    races = eb.get("race_results", {})
    badges = eb.get("badges", {}).get("items") or []
    extras = snap["extras"]
    meta = snap["athlete"]

    lines: list[str] = []
    a = lines.append
    a(f"# Brief de bitácora — {snap['period']['label']}")
    a("")
    a(f"Referencia al atleta: **{ref}** (nunca uses un nombre propio). "
      f"Edad: {meta['age_years']} años · banda {meta['age_band']} · "
      f"{'primera etapa registrada' if snap.get('previous_stage_title') is None else 'etapa con historial'}.")
    a(f"Consentimiento IA: {'sí' if meta['has_ai_consent'] else 'NO (la narrativa debe quedar en null; solo copy estático)'}.")
    a(f"Confianza de datos: {snap['confidence']}.")
    a("")
    a("## Asistencia y compromiso")
    a(f"- Sesiones asistidas: {att.get('sessions_present', 0)}/{att.get('sessions_total', 0)}")
    a(f"- Porcentaje: {_fmt(att.get('attendance_pct'), '%')}")
    if att.get("attendance_pct_prev_month") is not None:
        a(f"- Mes anterior: {_fmt(att.get('attendance_pct_prev_month'), '%')}")
    a(f"- Racha actual: {att.get('streak_sessions', 0)} sesiones consecutivas")
    a("")
    a("## Perfil semanal")
    weeks = [w.model_dump() for w in effort_profile(metrics)]
    if weeks:
        for w in weeks:
            rpe = f", RPE promedio {w['mean_rpe']}" if w.get("mean_rpe") is not None else ""
            a(f"- {w['week_label']}: {w['sessions_attended']}/{w['sessions_planned']} sesiones{rpe}")
    else:
        a("(sin sesiones registradas)")
    a("")
    a("## Técnica del mes")
    a(f"- Focos técnicos: {', '.join(tech.get('focos_tecnicos') or []) or 'no registrados'}")
    a(f"- RPE promedio: {_fmt(tech.get('avg_rpe'))}")
    a(f"- Rúbrica esfuerzo / actitud / técnica (1-5): {_fmt(tech.get('avg_rubric_effort'))} / "
      f"{_fmt(tech.get('avg_rubric_attitude'))} / {_fmt(tech.get('avg_rubric_technique'))}")
    a(f"- Horas de entrenamiento con el club: {_fmt(tech.get('total_training_hours'))} "
      f"(promedio semanal {_fmt(tech.get('weekly_hours_avg'))})")
    a("")
    a("## Sesión por sesión (feedback del entrenador)")
    a("Sintetiza patrones; no cites frases literales ni fechas una por una.")
    fb = extras.get("session_feedback") or []
    if not fb:
        a("(sin sesiones)")
    for s in fb:
        status = "asistió" if s["attended"] else f"no asistió ({s['attendance_status']})"
        detail = []
        if s.get("rpe") is not None:
            detail.append(f"RPE {s['rpe']}")
        if s.get("rubric_technique") is not None:
            detail.append(f"técnica {s['rubric_technique']}/5")
        if s.get("rubric_attitude") is not None:
            detail.append(f"actitud {s['rubric_attitude']}/5")
        feedback = _redact(s.get("individual_feedback"), forbidden)
        line = f"- {s['date']} · {_redact(s['technical_focus'], forbidden)} · {status}"
        if detail:
            line += " · " + ", ".join(detail)
        if feedback:
            line += f' · feedback: "{feedback}"'
        a(line)
        if s.get("objectives"):
            a(f"  - objetivo de la sesión: {_redact(s['objectives'], forbidden)}")
    a("")
    a("## Strava (actividad fuera y dentro del club)")
    st = extras.get("strava") or {}
    if not st.get("available"):
        a("(sin cuenta Strava conectada o sin actividades este mes — no lo menciones)")
    else:
        a(f"- Actividades: {st['activities']} ({st['linked_to_club_sessions']} vinculadas a sesiones del club, "
          f"{st['outside_club_sessions']} por su cuenta, {st['indoor_trainer']} en rodillo)")
        a(f"- Distancia total: {st['distance_km']} km · desnivel acumulado: {st['elevation_gain_m']} m · "
          f"tiempo en movimiento: {st['moving_hours']} h")
        if st.get("avg_heartrate"):
            a(f"- FC promedio: {st['avg_heartrate']} · FC máxima del mes: {st.get('max_heartrate') or '—'}")
        if st.get("interval_matches"):
            a("- Cumplimiento de intervalos (sesiones estructuradas):")
            for m in st["interval_matches"]:
                a(f"  - {json.dumps(m.get('summary'), ensure_ascii=False)}")
    a("")
    a("## Carreras del mes")
    results = races.get("results") or []
    notes_by_date = {n["date"]: n for n in (extras.get("race_notes") or [])}
    if not results:
        a("(sin participación en carreras este mes)")
    for r in results:
        pos = r.get("position") if r.get("position") else "DNF/DSQ"
        gap = f" (+{r['gap_to_winner_pct']:.1f}% respecto al P1 — solo su propia brecha)" if r.get("gap_to_winner_pct") is not None else ""
        a(f"- {r.get('label')}: posición {pos}{gap} — {r.get('event_date')}")
        note = notes_by_date.get(r.get("event_date"))
        if note:
            if note.get("status") and note["status"] != "finished":
                a(f"  - estado oficial: {note['status']}" + (f", {note['laps_behind']} vuelta(s) menos" if note.get("laps_behind") else ""))
            if note.get("coach_note"):
                a(f'  - nota del entrenador sobre esa carrera: "{_redact(note["coach_note"], forbidden)}"')
            cond = note.get("conditions") or {}
            cond_bits = [f"{k}: {v}" for k, v in cond.items() if v not in (None, "")]
            if cond_bits:
                a(f"  - condiciones: {', '.join(cond_bits)}")
    # Progresión de temporada separada por grupo de comparación (feature 039):
    # una copa NUNCA se compara con otra copa ni con un campeonato. Los
    # campeonatos van sueltos, cada uno con el tamaño real de su parrilla.
    cups = races.get("cups")
    championships = races.get("championships") or []
    if cups is not None:
        for cup in cups:
            hist = [
                f"{h.get('label') or 'V?'} P{h.get('position') or 'DNF'}"
                for h in (cup.get("history") or [])
            ]
            if hist:
                a(f"- Progresión en {cup.get('label')} (solo contexto, no la enumeres): {', '.join(hist)}")
        for ch in championships:
            field = f" de {ch['field_size']} corredores" if ch.get("field_size") else ""
            a(f"- {ch.get('label')}: puesto {ch.get('position')}{field} — carrera aparte, con otra "
              f"parrilla y otro nivel: NO la compares con las válidas de la copa ni la pongas "
              f"en la misma línea de progreso")
    elif races.get("progression_history"):
        hist = [
            f"V{h.get('valida_num')} P{h.get('position') or 'DNF'}"
            for h in races["progression_history"]
        ]
        a(f"- Progresión de la temporada (solo contexto, no la enumeres): {', '.join(hist)}")
    a("")
    a("## Insignias ganadas")
    if badges:
        for b in badges:
            a(f"- {badge_label_for(b.get('badge_type'))}")
    else:
        a("(sin insignias nuevas)")
    a("")
    a("## Próximo tramo")
    nxt = next_segment(metrics)
    focus_groups = list(nxt.focus_groups) if nxt is not None else []
    a(f"- Focos planificados: {', '.join(focus_groups) or 'aún sin definir'}")
    up = extras.get("upcoming") or {}
    if up.get("race_events"):
        for e in up["race_events"]:
            roster = {
                "confirmed": "inscripción confirmada",
                "called_up": "convocado/a, pendiente de confirmar",
                "withdrawn": "retirado/a de la convocatoria",
                None: "sin convocatoria registrada",
            }.get(e.get("roster_status"), e.get("roster_status"))
            a(f"- Próxima carrera: {e['name']} ({e.get('series') or ''}) — {e['date']}"
              + (f" — {e['location']}" if e.get("location") else "") + f" — {roster}")
    else:
        fallback = (eb.get("calendar") or {}).get("next_race_events") or []
        if fallback:
            for e in fallback[:2]:
                prio = f" (prioridad {e['priority']})" if e.get("priority") else ""
                a(f"- Próxima carrera (calendario Copa Valle del club, sin convocatoria registrada aún): "
                  f"Válida {e.get('valida')} — {e.get('date')} — {e.get('location')}{prio}")
        else:
            a("- Próxima carrera: ninguna programada en los próximos 75 días")
    for c in up.get("calendar_events") or []:
        rsvp = f" (RSVP: {c['rsvp_status']})" if c.get("rsvp_status") else ""
        a(f"- Evento del club: {_redact(c['title'], forbidden)} — {c['start_at'][:10]}{rsvp}")
    a("")
    a("## Lectura del análisis de carrera")
    fi = snap.get("family_input")
    if fi:
        a(f"Aprobada por el entrenador para {fi.get('valida_label') or 'la carrera del mes'}. Tradúcela, no la copies:")
        a(f"- Titular técnico: {fi.get('headline')}")
        a(f"- Acción recomendada ({fi.get('action_category')}): {fi.get('action_text')}")
    else:
        a("(sin análisis disponible — omite analyst_reading)")
    a("")
    a("## Título del mes anterior (no lo repitas ni lo parafrasees)")
    a(f'"{snap["previous_stage_title"]}"' if snap.get("previous_stage_title") else "(primera etapa registrada)")
    a("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------


async def _collect(db, athlete, year: int, month: int) -> dict:
    from app.routers.athlete_monthly_newsletters import (
        _athlete_sex_value,
        _build_forbidden_names,
        _previous_stage_texts,
    )
    from app.services.ai.use_cases.athlete_monthly_newsletter_v2 import (
        _compute_confidence,
        _derive_athlete_reference,
    )
    from app.services.privacy import athlete_has_ai_processing_consent
    from app.services.training.newsletter_builder import build_newsletter_metrics

    start, end = _month_bounds(year, month)
    has_ai_consent = await athlete_has_ai_processing_consent(athlete.id, db)
    metrics = await build_newsletter_metrics(db, athlete.id, year, month)
    forbidden = await _build_forbidden_names(db, athlete.club_id)
    prev_title, prev_text = await _previous_stage_texts(db, athlete.id, year, month)
    family_input = await _auto_family_input(db, athlete, year, month, has_ai_consent)
    sex = _athlete_sex_value(athlete)

    extras = {
        "session_feedback": await _session_feedback(db, athlete.id, start, end),
        "strava": await _strava_block(db, athlete.id, start, end),
        "upcoming": await _upcoming_races(db, athlete.id, athlete.club_id, end),
        "race_notes": await _race_notes(db, athlete.id, start, end),
    }
    age = _decimal_age(athlete.birth_date, end)
    sessions_total = metrics.get("email_blocks", {}).get("attendance", {}).get("sessions_total", 0)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "period": {"year": year, "month": month, "label": f"{_MONTHS_ES[month].capitalize()} {year}"},
        "athlete": {
            "id": athlete.id,
            "first_name": athlete.first_name,
            "last_name": athlete.last_name,
            "sex": sex,
            "age_years": age,
            "age_band": "10-12" if age < 13 else "13-15",
            "club_join_date": _iso(athlete.club_join_date),
            "has_ai_consent": has_ai_consent,
        },
        "athlete_reference": _derive_athlete_reference(sex),
        "confidence": _compute_confidence(sessions_total, 0),
        "forbidden_names": sorted(forbidden),
        "previous_stage_title": prev_title,
        "previous_stage_text": prev_text,
        "family_input": family_input,
        "metrics_snapshot": metrics,
        "extras": extras,
    }


async def _run(args: argparse.Namespace) -> int:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.athlete import Athlete

    out_root = Path(args.out) / f"{args.year}-{args.month:02d}"
    out_root.mkdir(parents=True, exist_ok=True)

    async with AsyncSessionLocal() as db:
        try:
            if args.all:
                stmt = select(Athlete).order_by(Athlete.id)
                if args.club_id:
                    stmt = stmt.where(Athlete.club_id == args.club_id)
                athletes = (await db.execute(stmt)).scalars().all()
            else:
                athletes = (
                    await db.execute(select(Athlete).where(Athlete.id.in_(args.athlete_id)))
                ).scalars().all()
                missing = set(args.athlete_id) - {a.id for a in athletes}
                if missing:
                    print(f"Atletas no encontrados: {sorted(missing)}", file=sys.stderr)

            summary = []
            for athlete in athletes:
                snap = await _collect(db, athlete, args.year, args.month)
                folder = out_root / f"athlete-{athlete.id}"
                folder.mkdir(exist_ok=True)
                (folder / "snapshot.json").write_text(
                    json.dumps(snap, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
                )
                (folder / "brief.md").write_text(render_brief(snap), encoding="utf-8")
                att = snap["metrics_snapshot"]["email_blocks"]["attendance"]
                summary.append(
                    {
                        "athlete_id": athlete.id,
                        "initials": f"{athlete.first_name[:1]}{athlete.last_name[:1]}".upper(),
                        "sessions": f"{att.get('sessions_present', 0)}/{att.get('sessions_total', 0)}",
                        "races": len(snap["metrics_snapshot"]["email_blocks"].get("race_results", {}).get("results") or []),
                        "strava": snap["extras"]["strava"].get("activities", 0),
                        "feedback_notes": sum(1 for s in snap["extras"]["session_feedback"] if s.get("individual_feedback")),
                        "ai_consent": snap["athlete"]["has_ai_consent"],
                        "analyst_reading": snap["family_input"] is not None,
                        "folder": str(folder),
                    }
                )
        finally:
            # Nunca persistimos nada desde este script (insignias evaluadas
            # por build_newsletter_metrics incluidas).
            await db.rollback()

    (out_root / "index.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Snapshots: {len(summary)} atleta(s) → {out_root}")
    for row in summary:
        print(
            f"  athlete-{row['athlete_id']} ({row['initials']}): sesiones {row['sessions']}, "
            f"carreras {row['races']}, strava {row['strava']}, feedback {row['feedback_notes']}, "
            f"IA {'sí' if row['ai_consent'] else 'no'}, analista {'sí' if row['analyst_reading'] else 'no'}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True, choices=range(1, 13))
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--athlete-id", type=int, action="append", help="repetible")
    group.add_argument("--all", action="store_true", help="todos los atletas (filtra con --club-id)")
    parser.add_argument("--club-id", type=int, default=None)
    parser.add_argument("--env-file", default=".env.production", help="archivo con MYSQL_* (default .env.production)")
    parser.add_argument("--out", default="../output/bitacora", help="carpeta raíz de salida (gitignored)")
    args = parser.parse_args()

    _load_env(Path(args.env_file))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        return asyncio.run(_run(args))
    except Exception as exc:  # noqa: BLE001 — nunca imprimir la traza (puede traer el DSN)
        detail = str(exc)
        for key in _MYSQL_KEYS:
            value = os.environ.get(key)
            if value:
                detail = detail.replace(value, f"<{key}>")
        print(f"Error ({type(exc).__name__}): {detail[:400]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
