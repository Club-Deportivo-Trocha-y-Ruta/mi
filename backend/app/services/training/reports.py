"""Service layer: generación y envío de reportes mensuales del club."""

from __future__ import annotations

import base64
import calendar
import logging
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.club import Club
from app.models.training_session import MonthlyReport, MonthlyReportStatus, TrainingSession
from app.models.user import User
from app.schemas.training_session import (
    ALLOWED_BLOCK_KEYS,
    CompetitionResultItem,
    NarrativeBlock,
    ParentMonthlySummary,
)
from app.services.permissions import parent_athlete_ids
from app.services.training.metrics import compute_monthly_metrics

if TYPE_CHECKING:
    from app.services.ai.use_cases.monthly_report_blocks import MonthlyReportBlocksUseCase

logger = logging.getLogger(__name__)

# Evidencia fotográfica: tope de fotos y de bytes embebidos (guardia de RAM/peso
# en Render Free). Solo thumbnails (~15-40 KB c/u), nunca originales.
_REPORT_PHOTO_LIMIT = 6
_REPORT_PHOTO_MAX_TOTAL_BYTES = 2 * 1024 * 1024  # 2 MB de base64


def _validate_period(year: int, month: int) -> None:
    today = date.today()
    if year > today.year or (year == today.year and month >= today.month):
        raise ValueError(
            f"El período {year}-{month:02d} no está cerrado todavía. "
            "Solo se pueden generar reportes de meses anteriores."
        )


async def generate_monthly_report(
    db: AsyncSession,
    club_id: int,
    year: int,
    month: int,
    generator_user: User,
    coach_observations: str | None = None,
    force_regenerate: bool = False,
    ai_use_case=None,
    blocks_use_case: "MonthlyReportBlocksUseCase | None" = None,
) -> MonthlyReport:
    """Genera (o regenera) el reporte mensual de un club.

    Cuando ``blocks_use_case`` se provee, genera borradores de narrativa por
    bloque (objetivo, desarrollo, resultados, conclusiones, apoyos_materiales,
    analisis_grupo) y los persiste en ``narrative_blocks``.

    Comportamiento de regeneración (``force_regenerate=True``):
    - ``ai_draft`` se regenera siempre con la IA (si el use case está disponible).
    - ``final_text``: si el coach YA lo había editado (final_text != ai_draft
      anterior o ai_draft anterior era None), se PRESERVA. Si final_text era
      igual al ai_draft anterior (nunca editado), se actualiza con el nuevo
      ai_draft. Esto garantiza que el trabajo del coach no se pierde.
    - ``status`` se resetea a DRAFT en regeneración completa.

    Los resultados de competencia se reconstruyen siempre (son datos estructurados,
    no editados por el coach).

    Raises:
        ValueError: período no cerrado, mes futuro, o ya existe sin force_regenerate.
    """
    _validate_period(year, month)

    existing_result = await db.execute(
        select(MonthlyReport).where(
            MonthlyReport.club_id == club_id,
            MonthlyReport.year == year,
            MonthlyReport.month == month,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing is not None and not force_regenerate:
        raise ValueError(
            f"Ya existe un reporte para {year}-{month:02d}. "
            "Usa force_regenerate=true para regenerarlo."
        )

    club_result = await db.execute(select(Club).where(Club.id == club_id))
    club = club_result.scalar_one_or_none()
    if club is None:
        raise ValueError(f"Club {club_id} no encontrado.")

    metrics = await compute_monthly_metrics(db, club_id, year, month)

    # --- Nombres reales: solo para construir forbidden_names del guardrail ---
    # Nunca se pasan a la IA directamente.
    from app.models.athlete import Athlete
    athletes_result = await db.execute(
        select(Athlete).where(Athlete.club_id == club_id)
    )
    athletes = athletes_result.scalars().all()
    real_names: set[str] = {f"{a.first_name} {a.last_name}" for a in athletes}

    # --- Narrativa IA (resumen legacy, ai_summary) ---
    ai_summary: str | None = None
    if ai_use_case is not None:
        ctx = ai_use_case.build_context_from_metrics(
            club_id=club.id,
            club_name=club.name,
            year=year,
            month=month,
            metrics=metrics,
            coach_observations=coach_observations,
            real_names=real_names,
        )
        result = await ai_use_case.run(ctx)
        ai_summary = result.text

    # --- Bloques de narrativa técnica por sección ---
    new_narrative_blocks: dict[str, dict] | None = None
    if blocks_use_case is not None:
        ctx_blocks = blocks_use_case.build_context_from_metrics(
            club_id=club.id,
            club_name=club.name,
            year=year,
            month=month,
            metrics=metrics,
            coach_observations=coach_observations,
            real_names=real_names,
        )
        drafts = await blocks_use_case.run_all_blocks(ctx_blocks)

        # Construir dict[str, dict] para persistir como JSON en narrative_blocks.
        # Preservar final_text editado por el coach si ya existía y difería del
        # ai_draft previo (indica edición manual).
        prev_blocks: dict[str, dict] = (
            (existing.narrative_blocks or {}) if existing is not None else {}
        )
        merged: dict[str, dict] = {}
        for draft in drafts:
            key = draft.block_key
            prev = prev_blocks.get(key, {})
            prev_ai_draft = prev.get("ai_draft")
            prev_final_text = prev.get("final_text")

            # "No editado" cuando final_text == ai_draft previo o final_text era None
            coach_edited = (
                prev_final_text is not None
                and prev_ai_draft is not None
                and prev_final_text != prev_ai_draft
            )
            final_text = prev_final_text if coach_edited else draft.ai_draft

            merged[key] = NarrativeBlock(
                ai_draft=draft.ai_draft,
                final_text=final_text,
                ai_model=draft.ai_model,
                ai_generated_at=draft.generated_at,
            ).model_dump(mode="json")

        new_narrative_blocks = merged

    # --- Resultados de competencia ---
    from app.services.training.competition_results import build_competition_results
    comp_results = await build_competition_results(db, club_id, year, month)
    competition_results_json = (
        [item.model_dump(mode="json") for item in comp_results]
        if comp_results else None
    )

    metrics_dict = metrics.model_dump(mode="json")
    now = datetime.now(timezone.utc)

    if existing is not None and force_regenerate:
        existing.ai_summary = ai_summary
        existing.metrics_snapshot = metrics_dict
        existing.coach_observations = coach_observations
        existing.generated_by_user_id = generator_user.id
        existing.generated_at = now
        existing.status = MonthlyReportStatus.DRAFT
        if new_narrative_blocks is not None:
            existing.narrative_blocks = new_narrative_blocks
        existing.competition_results = competition_results_json
        await db.flush()
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return existing

    report = MonthlyReport(
        club_id=club_id,
        year=year,
        month=month,
        ai_summary=ai_summary,
        metrics_snapshot=metrics_dict,
        coach_observations=coach_observations,
        generated_by_user_id=generator_user.id,
        generated_at=now,
        status=MonthlyReportStatus.DRAFT,
        narrative_blocks=new_narrative_blocks,
        competition_results=competition_results_json,
    )
    db.add(report)
    await db.flush()
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return report


async def parent_monthly_summary(
    db: AsyncSession,
    parent_user_id: int,
    athlete_id: int,
    year: int,
    month: int,
) -> ParentMonthlySummary:
    """Retorna el resumen mensual de un atleta para su padre.

    Raises:
        PermissionError: si el atleta no pertenece al padre.
        ValueError: si no hay datos del atleta en ese mes.
    """
    ids = await parent_athlete_ids(db, parent_user_id)
    if athlete_id not in ids:
        raise PermissionError(
            "No tienes permiso para ver el resumen de este atleta."
        )

    from app.models.athlete import Athlete
    from app.models.training_session import SessionAttendance, SessionStatus

    athlete_result = await db.execute(
        select(Athlete).where(Athlete.id == athlete_id)
    )
    athlete = athlete_result.scalar_one_or_none()
    if athlete is None:
        raise ValueError(f"Atleta {athlete_id} no encontrado.")

    month_start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    month_end = date(year, month, last_day)

    sessions_result = await db.execute(
        select(TrainingSession).where(
            TrainingSession.club_id == athlete.club_id,
            TrainingSession.scheduled_date >= month_start,
            TrainingSession.scheduled_date <= month_end,
            TrainingSession.status == SessionStatus.EXECUTED,
        )
    )
    sessions = sessions_result.scalars().all()
    session_ids = [s.id for s in sessions]
    focos = list({s.technical_focus for s in sessions if s.technical_focus})

    count_present = 0
    count_total = len(session_ids)
    avg_rpe: float | None = None
    avg_effort: float | None = None
    avg_attitude: float | None = None
    avg_technique: float | None = None

    if session_ids:
        from app.models.training_session import AttendanceStatus
        att_result = await db.execute(
            select(SessionAttendance).where(
                SessionAttendance.session_id.in_(session_ids),
                SessionAttendance.athlete_id == athlete_id,
            )
        )
        attendances = att_result.scalars().all()
        count_present = sum(
            1 for a in attendances
            if a.status in {AttendanceStatus.PRESENTE, AttendanceStatus.TARDE}
        )

        def _avg(values: list[int | None]) -> float | None:
            clean = [v for v in values if v is not None]
            return round(sum(clean) / len(clean), 1) if clean else None

        avg_rpe = _avg([a.rpe_omni for a in attendances])
        avg_effort = _avg([a.rubric_effort for a in attendances])
        avg_attitude = _avg([a.rubric_attitude for a in attendances])
        avg_technique = _avg([a.rubric_technique for a in attendances])

    pct = round(count_present / count_total * 100, 1) if count_total > 0 else 0.0

    return ParentMonthlySummary(
        athlete_id=athlete_id,
        athlete_name=f"{athlete.first_name} {athlete.last_name}",
        count_present=count_present,
        count_total=count_total,
        percentage=pct,
        focos_técnicos=focos,
        avg_rpe=avg_rpe,
        avg_rubric_effort=avg_effort,
        avg_rubric_attitude=avg_attitude,
        avg_rubric_technique=avg_technique,
    )


def _month_label(year: int, month: int) -> str:
    months_es = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]
    return f"{months_es[month - 1]} {year}"


async def build_report_photo_evidence(
    db: AsyncSession,
    club_id: int,
    year: int,
    month: int,
    limit: int = _REPORT_PHOTO_LIMIT,
) -> list[dict]:
    """Evidencia fotográfica del mes para el PDF del reporte de club.

    Trae hasta `limit` fotos CONSENTIDAS de las sesiones del club en el mes y
    embebe su thumbnail como data-URI base64 (independiente del storage en
    render-time: robusto en dev local y en SFTP). Cada item lleva la fecha de
    la SESIÓN (no la de subida).

    Degrada limpio: si una foto no se puede leer, se omite; ante cualquier
    error retorna lo acumulado (o lista vacía). Nunca rompe el PDF.

    Privacidad: filtra `consent_ack=True` y `deleted_at IS NULL`. Solo fotos
    (no videos). Documento interno del club (endpoint coach/admin).
    """
    from app.models.session_media import MediaType, SessionMedia

    month_start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    month_end = date(year, month, last_day)

    try:
        result = await db.execute(
            select(SessionMedia, TrainingSession.scheduled_date)
            .join(TrainingSession, TrainingSession.id == SessionMedia.session_id)
            .where(
                TrainingSession.club_id == club_id,
                TrainingSession.scheduled_date >= month_start,
                TrainingSession.scheduled_date <= month_end,
                SessionMedia.media_type == MediaType.PHOTO,
                SessionMedia.consent_ack.is_(True),
                SessionMedia.deleted_at.is_(None),
                SessionMedia.thumbnail_url.is_not(None),
            )
            .order_by(
                TrainingSession.scheduled_date.desc(),
                SessionMedia.uploaded_at.desc(),
            )
            .limit(limit)
        )
        rows = result.all()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Evidencia fotográfica: error en query (%s)", type(exc).__name__)
        return []

    from app.services.training import storage_sftp

    tmpdir = tempfile.gettempdir()
    items: list[dict] = []
    total_bytes = 0

    for media, scheduled in rows:
        # Deriva el path del thumbnail desde el del original:
        # .../{uuid}{ext} → .../{uuid}.thumb.jpg (ver media_files.save_session_media).
        orig = PurePosixPath(media.storage_path)
        thumb_path = str(orig.with_name(f"{orig.stem}.thumb.jpg"))

        local_path: Path | None = None
        try:
            resolved = await storage_sftp.download_to_tempfile(thumb_path, suffix=".jpg")
            local_path = Path(resolved)
            data = local_path.read_bytes()
        except Exception:  # noqa: BLE001
            continue
        finally:
            # Borra SOLO si es un temporal (modo SFTP). En modo local el path es
            # el archivo real del storage y NO debe borrarse.
            if local_path is not None and str(local_path).startswith(tmpdir):
                local_path.unlink(missing_ok=True)

        total_bytes += len(data)
        if total_bytes > _REPORT_PHOTO_MAX_TOTAL_BYTES:
            break

        b64 = base64.b64encode(data).decode("ascii")
        items.append({
            "data_uri": f"data:image/jpeg;base64,{b64}",
            "session_date": scheduled.strftime("%d/%m/%Y"),
            "caption": media.caption,
        })

    return items


# ---------------------------------------------------------------------------
# Funciones del Informe Técnico Mensual
# ---------------------------------------------------------------------------


async def update_report_blocks(
    db: AsyncSession,
    club_id: int,
    year: int,
    month: int,
    blocks: dict[str, str],
    new_status: MonthlyReportStatus | None = None,
    editor_user: User | None = None,
) -> MonthlyReport:
    """Actualiza ``final_text`` de los bloques indicados y opcionalmente aprueba.

    Solo acepta claves dentro de ``ALLOWED_BLOCK_KEYS``. Valida la transición
    de estado: solo ``draft -> approved`` (no reversión).

    Args:
        db: sesión async.
        club_id: ID del club.
        year, month: período del reporte.
        blocks: dict clave → final_text. Solo las claves presentes se actualizan.
        new_status: si vale ``MonthlyReportStatus.APPROVED``, aprueba el reporte.
        editor_user: usuario que realiza la edición (solo para trazabilidad en log).

    Raises:
        ValueError: reporte no existe, claves inválidas, transición de estado no permitida.
    """
    invalid = set(blocks.keys()) - ALLOWED_BLOCK_KEYS
    if invalid:
        raise ValueError(
            f"Claves de bloque no permitidas: {sorted(invalid)}. "
            f"Permitidas: {sorted(ALLOWED_BLOCK_KEYS)}"
        )

    result = await db.execute(
        select(MonthlyReport).where(
            MonthlyReport.club_id == club_id,
            MonthlyReport.year == year,
            MonthlyReport.month == month,
        )
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise ValueError(
            f"No existe reporte para {year}-{month:02d} en el club {club_id}."
        )

    if new_status == MonthlyReportStatus.DRAFT and report.status == MonthlyReportStatus.APPROVED:
        raise ValueError(
            "No se puede revertir un reporte aprobado a borrador desde este endpoint. "
            "Usa force_regenerate=true para regenerarlo."
        )

    # Actualizar final_text por clave
    if blocks:
        current_blocks: dict = dict(report.narrative_blocks or {})
        for key, final_text in blocks.items():
            entry = dict(current_blocks.get(key) or {})
            entry["final_text"] = final_text
            current_blocks[key] = entry
        report.narrative_blocks = current_blocks

    if new_status is not None:
        report.status = new_status

    await db.flush()
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "update_report_blocks: club=%d %d-%02d keys=%s status=%s editor=%s",
        club_id, year, month,
        sorted(blocks.keys()),
        new_status.value if new_status else "unchanged",
        editor_user.id if editor_user else "?",
    )
    return report


async def regenerate_block(
    db: AsyncSession,
    club_id: int,
    year: int,
    month: int,
    block_key: str,
    blocks_use_case: "MonthlyReportBlocksUseCase",
) -> MonthlyReport:
    """Regenera el ``ai_draft`` de un único bloque con la IA.

    Preserva el ``final_text`` editado por el coach (si difiere del ai_draft previo).
    El reporte NO cambia de estado (sigue draft o aprobado).

    Raises:
        ValueError: reporte no existe, clave inválida.
    """
    if block_key not in ALLOWED_BLOCK_KEYS:
        raise ValueError(
            f"Clave de bloque no permitida: '{block_key}'. "
            f"Permitidas: {sorted(ALLOWED_BLOCK_KEYS)}"
        )

    result = await db.execute(
        select(MonthlyReport).where(
            MonthlyReport.club_id == club_id,
            MonthlyReport.year == year,
            MonthlyReport.month == month,
        )
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise ValueError(
            f"No existe reporte para {year}-{month:02d} en el club {club_id}."
        )

    # Reconstruir contexto para el bloque
    club_result = await db.execute(select(Club).where(Club.id == club_id))
    club = club_result.scalar_one_or_none()
    if club is None:
        raise ValueError(f"Club {club_id} no encontrado.")

    metrics = await compute_monthly_metrics(db, club_id, year, month)

    from app.models.athlete import Athlete
    athletes_result = await db.execute(
        select(Athlete).where(Athlete.club_id == club_id)
    )
    real_names: set[str] = {
        f"{a.first_name} {a.last_name}" for a in athletes_result.scalars().all()
    }

    coach_obs = report.coach_observations
    ctx = blocks_use_case.build_context_from_metrics(
        club_id=club.id,
        club_name=club.name,
        year=year,
        month=month,
        metrics=metrics,
        coach_observations=coach_obs,
        real_names=real_names,
    )
    draft = await blocks_use_case.run_block(ctx, block_key)

    current_blocks: dict = dict(report.narrative_blocks or {})
    prev = current_blocks.get(block_key) or {}

    prev_ai_draft = prev.get("ai_draft")
    prev_final_text = prev.get("final_text")
    coach_edited = (
        prev_final_text is not None
        and prev_ai_draft is not None
        and prev_final_text != prev_ai_draft
    )
    new_final_text = prev_final_text if coach_edited else draft.ai_draft

    current_blocks[block_key] = NarrativeBlock(
        ai_draft=draft.ai_draft,
        final_text=new_final_text,
        ai_model=draft.ai_model,
        ai_generated_at=draft.generated_at,
    ).model_dump(mode="json")
    report.narrative_blocks = current_blocks

    await db.flush()
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return report


async def get_conjoint_sessions(
    db: AsyncSession,
    club_id: int,
    year: int,
    month: int,
) -> list[dict]:
    """Lista sesiones del mes con session_kind=actividad_conjunta o salida.

    Usada por el PDF para el apartado "Actividades Conjuntas". Retorna
    dicts con date, kind, objectives, technical_focus, location, duration_min.
    Degrada limpio ante errores.
    """
    from app.models.training_session import SessionKind, SessionStatus

    month_start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    month_end = date(year, month, last_day)

    try:
        result = await db.execute(
            select(TrainingSession).where(
                TrainingSession.club_id == club_id,
                TrainingSession.scheduled_date >= month_start,
                TrainingSession.scheduled_date <= month_end,
                TrainingSession.session_kind.in_([
                    SessionKind.ACTIVIDAD_CONJUNTA,
                    SessionKind.SALIDA,
                ]),
                TrainingSession.status != SessionStatus.CANCELLED,
            ).order_by(TrainingSession.scheduled_date.asc())
        )
        sessions = result.scalars().all()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "get_conjoint_sessions: error club=%d %d-%02d: %s",
            club_id, year, month, exc,
        )
        return []

    return [
        {
            "date": s.scheduled_date.strftime("%d/%m/%Y"),
            "kind": s.session_kind.value,
            "technical_focus": s.technical_focus or "",
            "objectives": s.objectives or "",
            "location": s.location or "",
            "duration_min": s.duration_min,
        }
        for s in sessions
    ]
