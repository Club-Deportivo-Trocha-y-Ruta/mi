"""Skinfold capture endpoints (feature 046).

Mounted in ``app/main.py`` under the same ``/api/athletes`` prefix as
``routers/anthropometry.py`` (same include pattern). Source of truth:
``specs/046-body-composition-skinfolds/contracts/skinfolds-api.md`` §1-§2.

Only ``PUT``/``DELETE`` live here; ``GET .../anthropometry`` (extended with
the ``skinfolds`` field) stays in ``routers/anthropometry.py`` — see
``skinfold_set_out`` below, imported from there to avoid duplicating the
ORM→schema mapping.

Privacy (Ley 1581 / CLAUDE.md): every ``HTTPException.detail`` below carries
only ids, dates and machine codes — never a reading value or an athlete/
parent name. Audit rows reuse the existing ``anthropometric_record`` entity
type (no new enum member) with ``meta={"event_type": "skinfolds.saved" |
"skinfolds.deleted", "site_count": ...}`` — ids and a count only, never a
value.
"""
from __future__ import annotations

import json
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.dependencies import (
    get_db,
    get_notification_service,
    require_role,
    verify_athlete_access,
)
from app.models.anthropometry import AnthropometricRecord
from app.models.athlete import Athlete
from app.models.audit_log import AuditAction
from app.models.skinfold_measurement import SkinfoldMeasurement
from app.models.user import User, UserRole
from app.schemas.body_composition import (
    BodyCompositionEstimates,
    BodyCompositionOut,
    BodyCompositionReference,
    BodyCompositionSeries,
    SeriesPoint,
    SkinfoldSetIn,
    SkinfoldSetOut,
    SkinfoldSiteOut,
    SkinfoldSitesOut,
)
from app.schemas.notification import DocumentFormat, DocumentRequest, DocumentTemplate
from app.services.audit import AuditEntityType, record_audit
from app.services.body_composition import (
    SITES,
    AthleteTooYoungError,
    SkinfoldIntervalTooShortError,
    apply_set,
    check_interval,
    check_min_age,
    needs_third_reading,
)
from app.services.body_composition import load_reading as load_body_composition_reading
from app.services.category import compute_age_decimal
from app.services.notification.service import NotificationService

router = APIRouter()

#: Separate `APIRouter` for `GET /api/body-composition/field-guide.pdf`
#: (feature 046, US5, T057). Not athlete-scoped — mounted in `app/main.py`
#: with its own `/api/body-composition` prefix, unlike `router` above
#: (mounted under `/api/athletes`).
field_guide_router = APIRouter()


def skinfold_set_out(measurement: SkinfoldMeasurement) -> SkinfoldSetOut:
    """Map the flat `SkinfoldMeasurement` columns to the nested wire shape.

    Shared with `routers/anthropometry.py::list_anthropometry` (T022) so the
    `PUT` response and the `GET .../anthropometry` item use the exact same
    serialisation — never hand-roll this dict twice.
    """
    site_kwargs: dict[str, SkinfoldSiteOut] = {}
    unconfirmed_sites: list[str] = []
    for site in SITES:
        declined = bool(getattr(measurement, f"{site}_declined"))
        readings_raw = getattr(measurement, f"{site}_readings")
        value_raw = getattr(measurement, f"{site}_mm")
        readings = [float(r) for r in readings_raw] if readings_raw is not None else None
        unconfirmed = (
            not declined
            and readings is not None
            and len(readings) == 2
            and needs_third_reading(readings[0], readings[1])
        )
        if unconfirmed:
            unconfirmed_sites.append(site)
        site_kwargs[site] = SkinfoldSiteOut(
            value_mm=float(value_raw) if value_raw is not None else None,
            readings=readings,
            declined=declined,
            unconfirmed=unconfirmed,
        )

    return SkinfoldSetOut(
        record_id=measurement.anthropometric_record_id,
        athlete_id=measurement.athlete_id,
        evaluation_date=measurement.record.evaluation_date,
        caliper_model=measurement.caliper_model,
        protocol_version=measurement.protocol_version,
        sites=SkinfoldSitesOut(**site_kwargs),
        sum4_mm=float(measurement.sum4_mm) if measurement.sum4_mm is not None else None,
        sum6_mm=float(measurement.sum6_mm) if measurement.sum6_mm is not None else None,
        body_fat_pct=(
            float(measurement.body_fat_pct) if measurement.body_fat_pct is not None else None
        ),
        fat_mass_kg=(
            float(measurement.fat_mass_kg) if measurement.fat_mass_kg is not None else None
        ),
        fat_free_mass_kg=(
            float(measurement.fat_free_mass_kg)
            if measurement.fat_free_mass_kg is not None
            else None
        ),
        equation_version=measurement.equation_version,
        needs_third_reading_unconfirmed=unconfirmed_sites,
        measured_by=measurement.measured_by,
        updated_at=measurement.updated_at,
    )


async def _load_record(db: AsyncSession, athlete_id: int, record_id: int) -> AnthropometricRecord:
    stmt = (
        select(AnthropometricRecord)
        .options(
            selectinload(AnthropometricRecord.athlete),
            selectinload(AnthropometricRecord.skinfolds),
        )
        .where(
            AnthropometricRecord.id == record_id,
            AnthropometricRecord.athlete_id == athlete_id,
        )
    )
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "anthropometric_record_not_found", "message": "Registro no encontrado"},
        )
    return record


@router.put(
    "/{athlete_id}/anthropometry/{record_id}/skinfolds",
    response_model=SkinfoldSetOut,
)
async def save_skinfolds(
    athlete_id: int,
    record_id: int,
    body: SkinfoldSetIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    athlete: Athlete = Depends(verify_athlete_access),
) -> SkinfoldSetOut:
    record = await _load_record(db, athlete.id, record_id)

    try:
        check_min_age(athlete, record, settings)
    except AthleteTooYoungError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "athlete_too_young", "message": str(exc)},
        ) from exc

    try:
        await check_interval(db, athlete.id, record, settings)
    except SkinfoldIntervalTooShortError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "skinfold_interval_too_short",
                "message": str(exc),
                "previous_set_date": exc.previous_set_date.isoformat(),
                "next_allowed_date": exc.next_allowed_date.isoformat(),
            },
        ) from exc

    measurement = apply_set(record, body, settings)
    measurement.measured_by = current_user.id
    db.add(measurement)
    await db.flush()
    await db.refresh(measurement)

    site_count = sum(
        1 for site in SITES if not getattr(measurement, f"{site}_declined")
    )
    await record_audit(
        db,
        action=AuditAction.update,
        entity_type=AuditEntityType.anthropometric_record,
        entity_id=record.id,
        actor=current_user,
        club_id=athlete.club_id,
        athlete_id=athlete.id,
        changed_fields=["skinfolds"],
        meta={"event_type": "skinfolds.saved", "site_count": site_count},
    )

    return skinfold_set_out(measurement)


@router.delete(
    "/{athlete_id}/anthropometry/{record_id}/skinfolds",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_skinfolds(
    athlete_id: int,
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    athlete: Athlete = Depends(verify_athlete_access),
) -> None:
    record = await _load_record(db, athlete.id, record_id)
    if record.skinfolds is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "no_skinfold_data", "message": "Este registro no tiene pliegues cutáneos"},
        )

    await db.delete(record.skinfolds)
    await db.flush()

    await record_audit(
        db,
        action=AuditAction.delete,
        entity_type=AuditEntityType.anthropometric_record,
        entity_id=record.id,
        actor=current_user,
        club_id=athlete.club_id,
        athlete_id=athlete.id,
        meta={"event_type": "skinfolds.deleted"},
    )


def _build_series(records: list[AnthropometricRecord]) -> BodyCompositionSeries:
    """`series.sum4`/`sum6`/`per_site` — one point per set, skipping
    incomplete points (contract §4)."""
    sum4: list[SeriesPoint] = []
    sum6: list[SeriesPoint] = []
    per_site: dict[str, list[SeriesPoint]] = {site: [] for site in SITES}
    for record in records:
        measurement = record.skinfolds
        if measurement.sum4_mm is not None:
            sum4.append(SeriesPoint(date=record.evaluation_date, value=float(measurement.sum4_mm)))
        if measurement.sum6_mm is not None:
            sum6.append(SeriesPoint(date=record.evaluation_date, value=float(measurement.sum6_mm)))
        for site in SITES:
            value = getattr(measurement, f"{site}_mm")
            if value is not None:
                per_site[site].append(
                    SeriesPoint(date=record.evaluation_date, value=float(value))
                )
    return BodyCompositionSeries(sum4=sum4, sum6=sum6, per_site=per_site)


def _estimates_latest(measurement: SkinfoldMeasurement) -> BodyCompositionEstimates:
    return BodyCompositionEstimates(
        body_fat_pct=(
            float(measurement.body_fat_pct) if measurement.body_fat_pct is not None else None
        ),
        fat_mass_kg=(
            float(measurement.fat_mass_kg) if measurement.fat_mass_kg is not None else None
        ),
        fat_free_mass_kg=(
            float(measurement.fat_free_mass_kg)
            if measurement.fat_free_mass_kg is not None
            else None
        ),
        equation_version=measurement.equation_version,
    )


@router.get(
    "/{athlete_id}/body-composition",
    response_model=BodyCompositionOut,
)
async def get_body_composition(
    athlete_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    athlete: Athlete = Depends(verify_athlete_access),
) -> BodyCompositionOut:
    """`GET .../body-composition` — coach/admin only (`skinfolds-api.md` §4).

    Loads the athlete's whole anthropometric history in one query
    (``selectinload`` of ``skinfolds``) for the sets and series; the reading
    comes from the shared ``services.body_composition.load_reading`` (T080)
    over those same records, so it matches the growth-summary card, the
    newsletter annex and the AI leaf input for input.
    """
    stmt = (
        select(AnthropometricRecord)
        .options(selectinload(AnthropometricRecord.skinfolds))
        .where(AnthropometricRecord.athlete_id == athlete.id)
        .order_by(AnthropometricRecord.evaluation_date.asc())
    )
    result = await db.execute(stmt)
    all_records = list(result.scalars().all())
    skinfold_records = [r for r in all_records if r.skinfolds is not None]

    if not skinfold_records:
        return BodyCompositionOut(athlete_id=athlete.id)

    sets_out = [skinfold_set_out(r.skinfolds) for r in skinfold_records]
    series = _build_series(skinfold_records)

    # Shared loader (T080, privacy-audit F6): the same inputs — velocity and
    # previous velocity against each set's preceding record, FUPRECOL
    # reference, latest attempt — as the growth summary, the newsletter
    # annex and the AI leaf. Reuses the records already loaded above.
    loaded = await load_body_composition_reading(db, athlete, records=all_records)
    reading = loaded.reading
    next_due_date = reading.next_due_date if reading is not None else None

    return BodyCompositionOut(
        athlete_id=athlete.id,
        sets=sets_out,
        series=series,
        reading=reading,
        estimates_latest=_estimates_latest(skinfold_records[-1].skinfolds),
        reference=BodyCompositionReference(),
        next_due_date=next_due_date,
    )


# ---------------------------------------------------------------------------
# GET /{athlete_id}/body-composition/referral-note.pdf (T045)
# ---------------------------------------------------------------------------

#: Spanish leg names for the neutral `legs_missing_note` sentence — never a
#: number, always the qualitative name of the leg that was unavailable
#: (contracts/skinfolds-api.md §6).
_LEG_LABELS_ES: dict[str, str] = {
    "previous_set": "una toma anterior comparable",
    "weight": "el cambio de peso",
    "height": "el cambio de talla",
    "velocity": "la velocidad de crecimiento",
    "bmi_z": "el índice de masa corporal para la edad",
    "reference": "la referencia poblacional",
}


#: Neutral, observational description of the pattern for the referral note,
#: one per `band_reason_code` (T069 privacy audit, finding F1). It continues
#: the template sentence "El club ha observado …", so it is a lowercase noun
#: phrase without a final period. Deliberately NOT `COACH_REASON_COPY`: that
#: copy instructs the coach ("conversa…", "considera remitir…") and carries a
#: clinical label ("baja disponibilidad energética") and percentile cut-offs
#: ("≤ P5 o ≥ P95"), none of which may appear in a document a family hands to
#: a health professional (contracts/skinfolds-api.md §6: no percentage, no
#: millimetre value, no label; research-safeguards-referral.md §4: "no
#: clinical or diagnostic terms").
_REFERRAL_PATTERN_ES: dict[str, str] = {
    "energy_availability_pattern": (
        "una disminución en la suma de pliegues cutáneos mayor que nuestro margen "
        "de medición, junto con un peso estable o a la baja y una talla que sigue "
        "aumentando, entre las dos últimas tomas"
    ),
    "sum_down_unexplained": (
        "una disminución en la suma de pliegues cutáneos mayor que nuestro margen "
        "de medición, con un peso estable o a la baja, entre las dos últimas tomas"
    ),
    "sum_up_unexplained": (
        "un aumento en la suma de pliegues cutáneos mayor que nuestro margen de "
        "medición entre las dos últimas tomas, sin un cambio de peso o de talla "
        "que lo acompañe"
    ),
    "sum_up_velocity_low": (
        "un aumento en la suma de pliegues cutáneos mayor que nuestro margen de "
        "medición, con un crecimiento en talla más lento de lo esperado para su "
        "etapa de desarrollo"
    ),
    "reference_extreme": (
        "un pliegue cutáneo alejado de lo habitual en la referencia poblacional "
        "colombiana para su edad y sexo, sin un cambio en el tiempo que lo acompañe"
    ),
    "bmi_z_drop": (
        "una disminución marcada del índice de masa corporal para la edad respecto "
        "a la medición anterior"
    ),
    "velocity_low_persistent": (
        "un crecimiento en talla más lento de lo esperado para su etapa de "
        "desarrollo en dos ciclos de medición seguidos"
    ),
    "no_real_change": (
        "una suma de pliegues cutáneos sin cambio real entre las dos últimas tomas "
        "(dentro de nuestro margen de medición)"
    ),
    "expected_pubertal_gain": (
        "un aumento en la suma de pliegues cutáneos acompañado de aumento de peso y "
        "de talla dentro de lo esperado para su etapa de desarrollo"
    ),
    "pre_spurt_accumulation": (
        "un aumento en la suma de pliegues cutáneos con la talla creciendo al ritmo "
        "esperado para su etapa de desarrollo"
    ),
    "post_phv_lean_gain": (
        "un aumento de peso con la suma de pliegues cutáneos estable o a la baja, "
        "después del pico de crecimiento"
    ),
    "first_set": (
        "una primera toma de pliegues cutáneos, todavía sin una toma anterior con "
        "la cual comparar"
    ),
    "stable": "una composición corporal estable respecto a la toma anterior",
}
_REFERRAL_PATTERN_FALLBACK = "un cambio en la composición corporal del/de la deportista"


def _referral_observed_pattern(band_reason_code: str) -> str:
    """Neutral pattern phrase for the referral note (never the coach copy)."""
    return _REFERRAL_PATTERN_ES.get(band_reason_code, _REFERRAL_PATTERN_FALLBACK)


def _referral_legs_missing_note(legs_missing: list[str]) -> str | None:
    """A short neutral clause for legs the reading could not evaluate.

    Never a number — only the qualitative names of §2's leg codes, per
    `docs/21-body-composition/research-safeguards-referral.md` §4.
    """
    labels = [_LEG_LABELS_ES[leg] for leg in legs_missing if leg in _LEG_LABELS_ES]
    if not labels:
        return None
    if len(labels) == 1:
        joined = labels[0]
    else:
        joined = ", ".join(labels[:-1]) + " y " + labels[-1]
    return f"(no fue posible evaluar {joined} en esta lectura)"


def _referral_initials(athlete: Athlete) -> str:
    """Initials only — never the athlete's full name (Ley 1581)."""
    first = (athlete.first_name or "").strip()[:1].upper()
    last = (athlete.last_name or "").strip()[:1].upper()
    return f"{first}.{last}."


def _referral_age_band(age_years: float) -> str:
    floor_years = int(age_years)
    return f"{floor_years}-{floor_years + 1} años"


def _referral_sex_label(sex: object) -> str:
    value = sex.value if hasattr(sex, "value") else str(sex)
    return "Femenino" if value == "F" else "Masculino"


async def _referral_weekly_hours_label(
    db: AsyncSession, athlete: Athlete, window_end
) -> str:
    """Approximate weekly training hours over the 28 days up to `window_end`.

    Same present/tarde-attendance-based hour computation as
    `training/newsletter_builder.py::_build_technical_block`, over a fixed
    28-day window instead of a calendar month — never a mm/% figure, this is
    training context only (contracts/skinfolds-api.md §6).
    """
    from app.models.training_session import (
        AttendanceStatus,
        SessionAttendance,
        SessionStatus,
        TrainingSession,
    )

    window_start = window_end - timedelta(days=28)
    fallback = "sin datos suficientes de entrenamiento en el último mes"

    sessions_result = await db.execute(
        select(TrainingSession).where(
            TrainingSession.club_id == athlete.club_id,
            TrainingSession.scheduled_date >= window_start,
            TrainingSession.scheduled_date <= window_end,
            TrainingSession.status == SessionStatus.EXECUTED,
        )
    )
    sessions = list(sessions_result.scalars().all())
    if not sessions:
        return fallback

    session_ids = [s.id for s in sessions]
    att_result = await db.execute(
        select(SessionAttendance).where(
            SessionAttendance.session_id.in_(session_ids),
            SessionAttendance.athlete_id == athlete.id,
            SessionAttendance.archived_at.is_(None),
        )
    )
    attendances = list(att_result.scalars().all())
    present_session_ids = {
        a.session_id
        for a in attendances
        if a.status in {AttendanceStatus.PRESENTE, AttendanceStatus.TARDE}
    }
    if not present_session_ids:
        return fallback

    by_id = {s.id: s for s in sessions}
    total_hours = sum(
        (by_id[sid].duration_min or 0) / 60.0 for sid in present_session_ids
    )
    weekly_hours = round(total_hours / 4.0, 1)  # 28 days == 4 weeks
    if weekly_hours <= 0:
        return fallback
    return f"aprox. {weekly_hours:g} horas por semana"


@router.get(
    "/{athlete_id}/body-composition/referral-note.pdf",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "Archivo PDF"},
        403: {"description": "Sin acceso al atleta"},
        409: {"description": "El atleta no tiene pliegues cutáneos registrados"},
    },
)
async def get_referral_note(
    athlete_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    athlete: Athlete = Depends(verify_athlete_access),
    notification_service: NotificationService = Depends(get_notification_service),
) -> Response:
    """`GET .../body-composition/referral-note.pdf` — coach/admin only.

    Contract: `contracts/skinfolds-api.md` §6. Builds the same
    `BodyCompositionReading` as `GET .../body-composition` from the latest
    counted set, then renders a neutral, generic referral note (no diagnosis,
    no label, no percentage/mm figure, no professional/institution name —
    the club has no named referral partner, owner decision C6). 409
    `no_skinfold_data` when the athlete has no counted skinfold set.
    """
    loaded = await load_body_composition_reading(db, athlete)
    reading = loaded.reading
    latest_record = loaded.latest_set_record
    if reading is None or latest_record is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "no_skinfold_data",
                "message": "Este atleta no tiene pliegues cutáneos registrados",
            },
        )
    age_years = compute_age_decimal(athlete.birth_date, latest_record.evaluation_date)

    observed_pattern = _referral_observed_pattern(reading.band_reason_code)
    weekly_hours_label = await _referral_weekly_hours_label(
        db, athlete, latest_record.evaluation_date
    )

    doc_request = DocumentRequest(
        template=DocumentTemplate.BODY_COMPOSITION_REFERRAL_NOTE,
        format=DocumentFormat.PDF,
        filename_hint="nota-remision",
        context={
            "athlete_initials": _referral_initials(athlete),
            "age_band": _referral_age_band(age_years),
            "sex_label": _referral_sex_label(athlete.sex),
            "observed_pattern": observed_pattern,
            "legs_missing_note": _referral_legs_missing_note(reading.legs_missing),
            "weekly_hours_label": weekly_hours_label,
        },
    )
    generated = await notification_service.generate_document_only(doc_request)

    await record_audit(
        db,
        action=AuditAction.export,
        entity_type=AuditEntityType.anthropometric_record,
        entity_id=latest_record.id,
        actor=current_user,
        club_id=athlete.club_id,
        athlete_id=athlete.id,
        meta={"event_type": "skinfolds.referral_note_generated"},
    )

    return Response(
        content=generated.data,
        media_type=generated.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{generated.filename}"',
            "Content-Length": str(len(generated.data)),
        },
    )


# ---------------------------------------------------------------------------
# GET /api/body-composition/field-guide.pdf (T057)
# ---------------------------------------------------------------------------

#: Spanish display label per site key — same words as `SITE_LABELS` in
#: `frontend/src/components/athletes/body-composition/
#: BodyCompositionDetailDialog.tsx` (kept in sync by hand, both are short
#: fixed lists tied to `SITES`/`skinfold_sites.json`'s six entries).
_SITE_LABELS_ES: dict[str, str] = {
    "triceps": "Tríceps",
    "biceps": "Bíceps",
    "subscapular": "Subescapular",
    "medial_calf": "Pantorrilla",
    "iliac_crest": "Cresta ilíaca",
    "supraspinale": "Supraespinal",
}

#: `backend/app/data/skinfold_sites.json` — source of the per-site texts
#: (`donde`/`como`/`alt`) rendered in the field-guide PDF and of the site
#: order shared with `frontend/src/lib/bodyComposition/siteDiagrams.ts`.
#: The PDF illustrations are the static PNGs under
#: `templates/documents/pdf/diagrams/img/skinfold_<key>.png` (required,
#: no fallback). Loaded once per process; the file is static app data,
#: never edited at runtime.
_SKINFOLD_SITES_PATH = Path(__file__).resolve().parents[1] / "data" / "skinfold_sites.json"


@lru_cache(maxsize=1)
def _load_skinfold_sites_data() -> dict:
    with _SKINFOLD_SITES_PATH.open(encoding="utf-8") as f:
        return json.load(f)


#: Static PNG illustrations for the field-guide PDF, relative to the
#: templates root (`DocumentGenerator` passes it as WeasyPrint's `base_url`).
_FIELD_GUIDE_IMG_REL = "documents/pdf/diagrams/img"


def _field_guide_illustration(site_key: str) -> str:
    """Template-relative path of the site's PNG (required; no fallback)."""
    return f"{_FIELD_GUIDE_IMG_REL}/skinfold_{site_key}.png"


def _build_field_guide_sites() -> list[dict]:
    """`sites` context for `documents/pdf/skinfold_field_guide.html`: the six
    entries of `skinfold_sites.json`, in `site_order`, each with its
    `key`/Spanish `label` added — never any athlete data (US5)."""
    data = _load_skinfold_sites_data()
    sites_by_key = data["sites"]
    return [
        {
            "key": key,
            "label": _SITE_LABELS_ES[key],
            "illustration": _field_guide_illustration(key),
            **sites_by_key[key],
        }
        for key in data["site_order"]
    ]


@field_guide_router.get(
    "/field-guide.pdf",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "Archivo PDF"},
        403: {"description": "Sin acceso (rol parent)"},
    },
)
async def get_field_guide(
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    notification_service: NotificationService = Depends(get_notification_service),
) -> Response:
    """`GET /api/body-composition/field-guide.pdf` — coach/admin only.

    Contract: `contracts/skinfolds-api.md` §7. Static, generic content — no
    `athlete_id` in the path, no athlete data in the response. Cached
    per-client for a day (`Cache-Control: private, max-age=86400`); `private`
    keeps a shared/CDN cache from serving it to a different club.
    """
    doc_request = DocumentRequest(
        template=DocumentTemplate.BODY_COMPOSITION_FIELD_GUIDE,
        format=DocumentFormat.PDF,
        filename_hint="instructivo-pliegues",
        context={"sites": _build_field_guide_sites()},
    )
    generated = await notification_service.generate_document_only(doc_request)

    return Response(
        content=generated.data,
        media_type=generated.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{generated.filename}"',
            "Content-Length": str(len(generated.data)),
            "Cache-Control": "private, max-age=86400",
        },
    )
