"""Construye el brief JSON de un/a deportista para redactar su informe de temporada.

Extrae de la base de datos (solo lectura) todo lo que el informe personal usa:
identidad, carreras con GAP/percentil calculados contra el/la ganador/a de su
categoría, puntos de Copa Valle, asistencia, antropometría (PHV) e insights IA
aprobados. Opcionalmente cruza la entrevista del formulario (CSV exportado de
Google Forms) buscando una subcadena en la columna "Nombre completo".

Uso:
    cd backend
    MYSQL_HOST=127.0.0.1 python -m scripts.build_report_brief --athlete-id 3 \\
        --interview-csv ~/Downloads/entrevista.csv --interview-match apellido_deportista \\
        --output data/reports/<atleta>/brief.json

Privacidad: la salida contiene datos reales de un menor — SIEMPRE bajo
`backend/data/` (ignorado por git).
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.anthropometry import AnthropometricRecord
from app.models.athlete import Athlete
from app.models.athlete_ai_insight import AthleteAiInsight
from app.models.race_category import RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_event import RaceEvent
from app.models.race_result import RaceResult
from app.models.race_series import RaceSeries
from app.models.training_session import SessionAttendance, TrainingSession

COPA_VALLE = "Copa Valle de Ciclomontañismo"


def _hms(ms: int | None) -> str | None:
    if ms is None:
        return None
    total = round(ms / 1000)
    m, s = divmod(total, 60)
    return f"{m}:{s:02d}"


def _age_on(birth: date, on: date) -> int:
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))


async def _races(db: AsyncSession, athlete_id: int) -> list[dict]:
    rows = (
        await db.execute(
            select(RaceResult, RaceEvent, RaceSeries, RaceCategory)
            .join(RaceEvent, RaceEvent.id == RaceResult.event_id)
            .join(RaceSeries, RaceSeries.id == RaceEvent.series_id)
            .join(RaceCategory, RaceCategory.id == RaceResult.category_id)
            .where(RaceResult.athlete_id == athlete_id, RaceResult.deleted_at.is_(None))
            .order_by(RaceEvent.event_date)
        )
    ).all()

    out: list[dict] = []
    for result, event, series, category in rows:
        field_size = (
            await db.execute(
                select(func.count(RaceResult.id)).where(
                    RaceResult.event_id == event.id,
                    RaceResult.category_id == category.id,
                    RaceResult.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        winner = (
            await db.execute(
                select(RaceCompetitor.display_name, RaceCompetitor.club_text, RaceResult.race_time_ms)
                .join(RaceCompetitor, RaceCompetitor.id == RaceResult.competitor_id)
                .where(
                    RaceResult.event_id == event.id,
                    RaceResult.category_id == category.id,
                    RaceResult.position == 1,
                    RaceResult.deleted_at.is_(None),
                )
            )
        ).first()
        winner_name, winner_club, winner_ms = winner if winner else (None, None, None)

        gap_ms = gap_pct = None
        if result.race_time_ms is not None and winner_ms:
            gap_ms = result.race_time_ms - winner_ms
            gap_pct = round(gap_ms / winner_ms * 100, 1)
        percentile = (
            round(result.position / field_size * 100) if result.position and field_size else None
        )

        out.append(
            {
                "date": event.event_date.isoformat(),
                "series": series.name,
                "sequence_number": event.sequence_number,
                "event_name": event.name,
                "location": event.location,
                "category": category.label,
                "status": result.status.value if hasattr(result.status, "value") else str(result.status),
                "position": result.position,
                "field_size": field_size,
                "time": _hms(result.race_time_ms),
                "time_ms": result.race_time_ms,
                "points_awarded": result.points_awarded,
                "laps_behind": result.laps_behind,
                "winner_name": winner_name,
                "winner_club": winner_club,
                "winner_time": _hms(winner_ms),
                "winner_time_ms": winner_ms,
                "gap_time": _hms(gap_ms) if gap_ms is not None else None,
                "gap_ms": gap_ms,
                "gap_pct": gap_pct,
                "position_percentile": percentile,
                "coach_note": result.coach_note,
                "is_copa_valle": series.name == COPA_VALLE,
            }
        )
    return out


async def _attendance(db: AsyncSession, athlete_id: int) -> dict:
    rows = (
        await db.execute(
            select(TrainingSession.session_kind, SessionAttendance.status, func.count())
            .join(TrainingSession, TrainingSession.id == SessionAttendance.session_id)
            .where(SessionAttendance.athlete_id == athlete_id, SessionAttendance.archived_at.is_(None))
            .group_by(TrainingSession.session_kind, SessionAttendance.status)
        )
    ).all()
    by_kind: dict[str, dict[str, int]] = {}
    total: dict[str, int] = {}
    for kind, status, n in rows:
        k = kind.value if hasattr(kind, "value") else str(kind)
        s = status.value if hasattr(status, "value") else str(status)
        by_kind.setdefault(k, {})[s] = n
        total[s] = total.get(s, 0) + n
    registered = sum(total.values())
    present = total.get("presente", 0) + total.get("tarde", 0)
    return {
        "by_session_kind": by_kind,
        "totals": total,
        "sessions_registered": registered,
        "present_incl_late": present,
        "present_pct": round(present / registered * 100) if registered else None,
    }


async def _anthropometry(db: AsyncSession, athlete_id: int) -> list[dict]:
    rows = (
        await db.execute(
            select(AnthropometricRecord)
            .where(AnthropometricRecord.athlete_id == athlete_id)
            .order_by(AnthropometricRecord.evaluation_date)
        )
    ).scalars().all()
    return [
        {
            "date": r.evaluation_date.isoformat(),
            "height_cm": float(r.standing_height_cm),
            "weight_kg": float(r.weight_kg),
            "maturity_offset_years": float(r.maturity_offset),
            "age_at_phv": float(r.age_at_phv),
            "maturation_status": r.maturation_status.value
            if hasattr(r.maturation_status, "value")
            else str(r.maturation_status),
            "height_percentile": float(r.height_percentile) if r.height_percentile is not None else None,
            "bmi_percentile": float(r.bmi_percentile) if r.bmi_percentile is not None else None,
            "training_implications": r.training_implications,
        }
        for r in rows
    ]


async def _insights(db: AsyncSession, athlete_id: int) -> list[dict]:
    rows = (
        await db.execute(
            select(AthleteAiInsight)
            .where(
                AthleteAiInsight.athlete_id == athlete_id,
                AthleteAiInsight.coach_approved.is_(True),
                AthleteAiInsight.is_active == 1,
                AthleteAiInsight.archived_at.is_(None),
            )
            .order_by(AthleteAiInsight.generated_at)
        )
    ).scalars().all()
    return [
        {
            "use_case": r.use_case,
            "valida_num": r.valida_num,
            "summary_text": r.summary_text[:2000],
            "recommendations": r.recommendations_json,
        }
        for r in rows
    ]


def _interview(csv_path: Path, match: str) -> dict | None:
    with csv_path.open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    header = rows[0]
    needle = match.lower()
    for row in rows[1:]:
        if needle in row[1].lower():
            return {
                header[i]: row[i].strip()
                for i in range(len(header))
                if i not in (0, 1) and row[i].strip()
            } | {"form_timestamp": row[0]}
    return None


async def run(athlete_id: int, output: Path, csv_path: Path | None, match: str | None) -> None:
    async with AsyncSessionLocal() as db:
        athlete = await db.get(Athlete, athlete_id)
        if athlete is None:
            raise SystemExit(f"Athlete id={athlete_id} no encontrado")
        races = await _races(db, athlete_id)
        attendance = await _attendance(db, athlete_id)
        anthro = await _anthropometry(db, athlete_id)
        insights = await _insights(db, athlete_id)

    copa = [r for r in races if r["is_copa_valle"]]
    today = date.today()
    brief = {
        "athlete": {
            "id": athlete.id,
            "first_name": athlete.first_name,
            "last_name": athlete.last_name,
            "sex": athlete.sex.value if hasattr(athlete.sex, "value") else str(athlete.sex),
            "age_today": _age_on(athlete.birth_date, today),
            "category_label": races[-1]["category"] if races else None,
        },
        "generated_on": today.isoformat(),
        "races": races,
        "copa_valle": {
            "validas_run": [r["sequence_number"] for r in copa],
            "points_total": sum(r["points_awarded"] for r in copa),
            "points_by_valida": {r["sequence_number"]: r["points_awarded"] for r in copa},
            "validas_remaining": ["VI — Yumbo", "VII — Roldanillo"],
        },
        "attendance": attendance,
        "anthropometry": anthro,
        "ai_insights_approved": insights,
        "interview": _interview(csv_path, match) if csv_path and match else None,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Brief generado: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--athlete-id", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--interview-csv", type=Path)
    parser.add_argument("--interview-match")
    args = parser.parse_args()
    asyncio.run(run(args.athlete_id, args.output, args.interview_csv, args.interview_match))


if __name__ == "__main__":
    main()
