"""Historical CSV import: item-by-item, scored + baselined retroactively (US6).

CSV layout (CL-001 / research R8): one column per item (``i1``..``iN``) plus
metadata columns ``athlete_ref`` (athlete id), ``instrument`` (csai2r|sas2|csai2),
``date`` (ISO), optional ``event_ref`` (race_event id). Each row is parsed,
scored with the same ``scoring.py`` as the live path, and seeds baselines where
data permits. Bad rows are reported, never crash the whole import.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anxiety_assessment import AnxietyAssessment, AssessmentStatus
from app.models.anxiety_instrument import AnxietyInstrument, InstrumentType
from app.models.athlete import Athlete
from app.services.anxiety.consent_gate import has_psychological_consent
from app.services.anxiety.instrument_keys import VALID_TYPES, load_key
from app.services.anxiety.submit import apply_answers

_ITEM_RE = re.compile(r"^i(\d+)$", re.IGNORECASE)

# item count → instrument type (fallback when `instrument` column missing)
_COUNT_TO_TYPE = {17: "csai2r", 15: "sas2", 27: "csai2"}


@dataclass
class ImportRowError:
    row: int
    error: str


@dataclass
class ImportOutcome:
    imported: int = 0
    skipped: int = 0
    errors: list[ImportRowError] = field(default_factory=list)


def _parse_answers(row: dict[str, str]) -> dict[int, int]:
    answers: dict[int, int] = {}
    for col, raw in row.items():
        if col is None:
            continue
        m = _ITEM_RE.match(col.strip())
        if not m:
            continue
        value = (raw or "").strip()
        if value == "":
            continue  # missing item → partial
        answers[int(m.group(1))] = int(value)
    return answers


def _infer_instrument(row: dict[str, str], answers: dict[int, int]) -> str:
    explicit = (row.get("instrument") or "").strip().lower()
    if explicit:
        if explicit not in VALID_TYPES:
            raise ValueError(f"Instrumento desconocido: '{explicit}'.")
        return explicit
    inferred = _COUNT_TO_TYPE.get(max(answers) if answers else 0)
    if inferred is None:
        raise ValueError(
            "No se pudo inferir el instrumento (sin columna 'instrument' ni "
            "conteo de ítems reconocible)."
        )
    return inferred


async def _active_instrument(
    db: AsyncSession, instrument_type: str
) -> AnxietyInstrument | None:
    result = await db.execute(
        select(AnxietyInstrument)
        .where(
            AnxietyInstrument.type == InstrumentType(instrument_type),
            AnxietyInstrument.is_active.is_(True),
        )
        .order_by(AnxietyInstrument.id.desc())
    )
    return result.scalars().first()


async def import_csv(
    db: AsyncSession,
    content: str | bytes,
    created_by_user_id: int,
    now: datetime | None = None,
) -> ImportOutcome:
    """Import assessments from CSV ``content``. Returns an :class:`ImportOutcome`."""
    now = now or datetime.now(timezone.utc)
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig")

    outcome = ImportOutcome()
    reader = csv.DictReader(io.StringIO(content))

    for idx, row in enumerate(reader, start=2):  # row 1 = header
        try:
            athlete_ref = (row.get("athlete_ref") or "").strip()
            if not athlete_ref:
                raise ValueError("Falta 'athlete_ref'.")
            athlete_id = int(athlete_ref)

            athlete = await db.get(Athlete, athlete_id)
            if athlete is None:
                raise ValueError(f"Atleta {athlete_id} no existe.")

            if not await has_psychological_consent(db, athlete_id):
                raise ValueError(
                    f"Atleta {athlete_id} sin consentimiento de evaluación "
                    "psicológica vigente."
                )

            answers = _parse_answers(row)
            if not answers:
                raise ValueError("Fila sin respuestas de ítems (i1..iN).")

            instrument_type = _infer_instrument(row, answers)
            load_key(instrument_type)  # validates type / key presence

            instrument = await _active_instrument(db, instrument_type)
            if instrument is None:
                raise ValueError(
                    f"No hay instrumento activo configurado para "
                    f"'{instrument_type}'."
                )

            date_raw = (row.get("date") or "").strip()
            scheduled_at = (
                datetime.fromisoformat(date_raw) if date_raw else now
            )

            event_ref = (row.get("event_ref") or "").strip()
            event_id = int(event_ref) if event_ref else None

            assessment = AnxietyAssessment(
                athlete_id=athlete_id,
                instrument_id=instrument.id,
                event_id=event_id,
                scheduled_at=scheduled_at,
                status=AssessmentStatus.pending,
                created_by_user_id=created_by_user_id,
                created_at=now,
                updated_at=now,
            )
            db.add(assessment)
            await db.flush()

            await apply_answers(
                db, assessment, instrument_type, answers, now=now
            )
            outcome.imported += 1
        except Exception as exc:  # noqa: BLE001 — per-row isolation
            outcome.skipped += 1
            outcome.errors.append(ImportRowError(row=idx, error=str(exc)))

    return outcome
