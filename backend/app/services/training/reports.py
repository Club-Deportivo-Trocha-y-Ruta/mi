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
    from app.models.club_project_profile import ClubProjectProfile
    from app.models.training_session import SessionKind
    from app.services.ai.use_cases.monthly_report_blocks import MonthlyReportBlocksUseCase

logger = logging.getLogger(__name__)

# Evidencia fotográfica: tope de fotos y de bytes embebidos (guardia de RAM/peso
# en Render Free). Solo thumbnails (~15-40 KB c/u), nunca originales.
_REPORT_PHOTO_LIMIT = 6
_REPORT_PHOTO_MAX_TOTAL_BYTES = 2 * 1024 * 1024  # 2 MB de base64
# Pool de candidatas consultado en BD antes de aplicar el tope final: debe ser
# mayor que `_REPORT_PHOTO_LIMIT` para poder garantizar ≥1 foto por sección no
# vacía (spec 022, R6) sin escanear todas las fotos del período.
_REPORT_PHOTO_CANDIDATE_POOL = _REPORT_PHOTO_LIMIT * 5

# Secciones del registro fotográfico (spec 022, data-model.md §5). El orden no
# importa aquí: el template las agrupa por título.
_PHOTO_SECTION_ALTO_RENDIMIENTO = "Grupo de Alto Rendimiento"
_PHOTO_SECTION_ACTIVIDADES_CONJUNTAS = "Actividades Conjuntas"
_PHOTO_SECTION_COMPETENCIA = "Competencia"


def _validate_period(year: int, month: int) -> None:
    # TEMPORAL (revertir tras generar el informe de julio 2026 on-demand):
    # relaja el corte de "mes>=actual" a "mes>actual", en paridad con
    # MonthlyReportCreate._validate_period_not_future.
    today = date.today()
    if year > today.year or (year == today.year and month > today.month):
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


async def _resolve_race_dates(
    db: AsyncSession,
    club_id: int,
    month_start: date,
    month_end: date,
) -> set[date]:
    """Fechas del período en que algún atleta del club corrió una competencia.

    Usadas por la heurística de sección "Competencia" (spec 022, R6): no hay
    FK sesión↔evento, así que la coincidencia se hace por fecha. Cuenta la
    participación (no exige `position IS NOT NULL`: un DNF también corrió).
    Degrada limpio: ante cualquier error devuelve un set vacío (la foto cae
    a la regla por `session_kind`).
    """
    try:
        from app.models.athlete import Athlete
        from app.models.race_event import RaceEvent
        from app.models.race_result import RaceResult

        result = await db.execute(
            select(RaceEvent.event_date)
            .join(RaceResult, RaceResult.event_id == RaceEvent.id)
            .join(Athlete, Athlete.id == RaceResult.athlete_id)
            .where(
                Athlete.club_id == club_id,
                RaceEvent.event_date >= month_start,
                RaceEvent.event_date <= month_end,
                RaceResult.deleted_at.is_(None),
            )
            .distinct()
        )
        return {row[0] for row in result.all()}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Evidencia fotográfica: error resolviendo fechas de competencia (%s)",
            type(exc).__name__,
        )
        return set()


def _derive_photo_section(
    session_kind: "SessionKind",
    scheduled: date,
    race_dates: set[date],
) -> str:
    """Deriva la sección del registro fotográfico (spec 022, data-model.md §5).

    Prioridad: coincidencia de fecha con una competencia del club (heurística,
    no hay FK sesión↔evento) > `session_kind` > default seguro.
    """
    from app.models.training_session import SessionKind

    if scheduled in race_dates:
        return _PHOTO_SECTION_COMPETENCIA
    if session_kind in (SessionKind.ACTIVIDAD_CONJUNTA, SessionKind.SALIDA):
        return _PHOTO_SECTION_ACTIVIDADES_CONJUNTAS
    return _PHOTO_SECTION_ALTO_RENDIMIENTO


def _select_balanced_candidates(candidates: list[dict], limit: int) -> list[dict]:
    """Elige hasta `limit` candidatas garantizando ≥1 por sección no vacía.

    `candidates` ya viene ordenada (fecha de sesión desc, subida desc). Paso 1:
    toma la primera candidata de cada sección distinta que aparezca (garantiza
    representación). Paso 2: completa los cupos restantes con las siguientes
    candidatas en el orden original. El resultado se devuelve reordenado según
    el índice original, así que en el caso común (una sola sección) el
    comportamiento es idéntico al de antes de esta feature (simple truncado a
    `limit`).
    """
    if limit <= 0 or not candidates:
        return []

    picked_indices: set[int] = set()
    seen_sections: set[str] = set()

    for idx, item in enumerate(candidates):
        section = item["section"]
        if section in seen_sections:
            continue
        seen_sections.add(section)
        picked_indices.add(idx)
        if len(picked_indices) >= limit:
            break

    if len(picked_indices) < limit:
        for idx in range(len(candidates)):
            if idx in picked_indices:
                continue
            picked_indices.add(idx)
            if len(picked_indices) >= limit:
                break

    return [candidates[idx] for idx in sorted(picked_indices)]


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
    la SESIÓN (no la de subida) y una `section` derivada (spec 022, R6):
    "Grupo de Alto Rendimiento" (`session_kind` entrenamiento|otro),
    "Actividades Conjuntas" (actividad_conjunta|salida), o "Competencia"
    (la fecha de la sesión coincide con un `RaceEvent.event_date` en el que
    corrió un atleta del club durante el período — prioridad sobre
    `session_kind`).

    El tope de `limit` fotos / `_REPORT_PHOTO_MAX_TOTAL_BYTES` bytes se aplica
    de forma consciente de las secciones: se intenta conservar al menos una
    foto por sección no vacía antes de completar cupos en orden cronológico
    (ver `_select_balanced_candidates`). En el caso común (una sola sección)
    el comportamiento es idéntico al truncado simple anterior.

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
            select(
                SessionMedia,
                TrainingSession.scheduled_date,
                TrainingSession.session_kind,
            )
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
            .limit(max(limit, _REPORT_PHOTO_CANDIDATE_POOL))
        )
        rows = result.all()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Evidencia fotográfica: error en query (%s)", type(exc).__name__)
        return []

    if not rows:
        return []

    race_dates = await _resolve_race_dates(db, club_id, month_start, month_end)

    candidates = [
        {
            "media": media,
            "scheduled": scheduled,
            "section": _derive_photo_section(session_kind, scheduled, race_dates),
        }
        for media, scheduled, session_kind in rows
    ]
    selected = _select_balanced_candidates(candidates, limit)

    from app.services.training import storage_sftp

    tmpdir = tempfile.gettempdir()
    items: list[dict] = []
    total_bytes = 0

    for candidate in selected:
        media = candidate["media"]
        scheduled = candidate["scheduled"]

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
            "section": candidate["section"],
        })

    return items


# ---------------------------------------------------------------------------
# Funciones del Informe Técnico Mensual
# ---------------------------------------------------------------------------

# Marcador de campo de encabezado ausente (perfil de proyecto incompleto).
_HEADER_FIELD_PLACEHOLDER = "—"

# Marcador de sección narrativa obligatoria sin contenido.
_PENDING_SECTION_PLACEHOLDER = "Pendiente de completar"

# Marcador de tabla derivada de metrics_snapshot sin datos (reporte antiguo
# generado antes de esta feature, o período sin actividad registrada).
_PENDING_TABLE_PLACEHOLDER = "Pendiente — regenerar informe"

# Orden aprobado de las secciones narrativas del Grupo de Alto Rendimiento
# (clave en narrative_blocks, título mostrado en el documento). Fuente:
# formato institucional aprobado — feature 022.
_APPROVED_NARRATIVE_SECTIONS: tuple[tuple[str, str], ...] = (
    ("objetivo", "Objetivo"),
    ("plan_entrenamiento", "Plan de entrenamiento"),
    ("desarrollo", "Desarrollo de actividades"),
    ("competencia", "Participación en competencia"),
    ("resultados", "Resultados obtenidos"),
    ("conclusiones", "Conclusiones"),
)


def _header_field(value: str | None) -> str:
    """Devuelve ``value`` o el placeholder ``—`` si está vacío/ausente."""
    return value if value else _HEADER_FIELD_PLACEHOLDER


def _group_competition_results(items: list) -> list[dict]:
    """Agrupa ``competition_results`` por evento (jornada), en orden de fecha.

    Cada grupo resume el evento (``event_id``, ``event_name``, ``event_date``,
    ``series_kind``, ``awards_points``) y trae sus resultados (``results``).

    Tolera reportes generados antes de la feature 022, cuyos items no tienen
    ``event_id``/``series_kind``/``awards_points`` (usa valores por defecto
    seguros: ``event_id=0``, ``series_kind=None``, ``awards_points=True``,
    el comportamiento histórico donde todo resultado contaba para el
    ranking). Ignora items que no sean dict. Nunca lanza excepción.
    """
    groups: dict[int, dict] = {}
    order: list[int] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        event_id = item.get("event_id") or 0
        if event_id not in groups:
            groups[event_id] = {
                "event_id": event_id,
                "event_name": item.get("event_name"),
                "event_date": item.get("event_date"),
                "series_kind": item.get("series_kind"),
                "awards_points": item.get("awards_points", True),
                "results": [],
            }
            order.append(event_id)
        groups[event_id]["results"].append(item)

    ordered = [groups[event_id] for event_id in order]
    # event_date llega serializado como str ISO ("YYYY-MM-DD") desde el JSON
    # de la BD, que ordena cronológicamente igual que un date. Ausente → al
    # final (no rompe el orden de los eventos con fecha conocida).
    ordered.sort(key=lambda g: (g["event_date"] is None, g["event_date"] or ""))
    return ordered


def build_report_document_context(
    report: MonthlyReport,
    profile: "ClubProjectProfile | None",
) -> dict:
    """Construye el contexto de renderizado del Informe Técnico Mensual.

    Fuente única de verdad compartida por el renderer de PDF y el (futuro)
    renderer de DOCX: ambos deben consumir el dict devuelto aquí en lugar de
    leer ``report``/``profile`` directamente, para garantizar paridad de
    contenido entre los dos formatos (contrato: ``monthly-report-api.md``).

    No hace consultas a BD: toda la información ya vive en las columnas JSON
    del ``report`` (``metrics_snapshot``, ``narrative_blocks``,
    ``competition_results``) y en el ``profile`` (``ClubProjectProfile``).
    La evidencia fotográfica (``build_report_photo_evidence``) y las
    actividades conjuntas (``get_conjoint_sessions``) se resuelven aparte
    (requieren BD) y se fusionan en el contexto por quien invoque esta
    función (router).

    Degrada limpio ante reportes generados antes de esta feature (FR-012):
    ninguna clave ausente en las columnas JSON lanza excepción; las tablas
    sin datos y las secciones narrativas sin contenido se marcan como
    pendientes en lugar de fallar.

    Returns:
        dict con las claves:

        - ``header``: dict con ``project_name``, ``executing_entity``,
          ``report_responsible`` (``"—"`` si el perfil no los define) y
          ``period_label`` (ej. ``"Julio 2026"``).
        - ``status`` / ``is_draft``: estado persistido del reporte y su
          equivalente booleano (``True`` salvo ``approved``).
        - ``sections``: lista ordenada (formato aprobado) de dicts
          ``{key, title, text, is_missing}``. ``text`` es siempre el
          ``final_text`` aprobado por el coach (el ``ai_draft`` NUNCA se
          expone en el documento); ``is_missing`` es ``True`` cuando el
          bloque no existe o no tiene ``final_text`` NI ``ai_draft``.
        - ``missing_sections``: títulos de las secciones con ``is_missing``
          (para el banner de borrador).
        - ``session_detail``: dict ``{rows, is_empty, placeholder}`` con las
          filas de ``metrics_snapshot.session_detail``.
        - ``attendance_table``: dict ``{rows, is_empty, placeholder}`` con
          una fila por atleta (asistencia + promedios de rúbrica);
          ``athlete_id`` en cada fila tal como quedó serializado (str, id).
        - ``competition_results``: lista cruda (para consumidores que no
          necesiten agrupar).
        - ``competition_groups``: la misma lista agrupada por evento
          (``_group_competition_results``), ordenada por fecha.
        - ``has_competition_results``: bool de conveniencia.
    """
    header = {
        "project_name": _header_field(getattr(profile, "project_name", None)),
        "executing_entity": _header_field(getattr(profile, "executing_entity", None)),
        "report_responsible": _header_field(getattr(profile, "report_responsible", None)),
        "period_label": _month_label(report.year, report.month),
    }

    status = report.status
    is_draft = not (
        isinstance(status, MonthlyReportStatus) and status == MonthlyReportStatus.APPROVED
    )

    raw_narrative = report.narrative_blocks
    narrative_blocks: dict = raw_narrative if isinstance(raw_narrative, dict) else {}

    sections: list[dict] = []
    missing_sections: list[str] = []
    for key, title in _APPROVED_NARRATIVE_SECTIONS:
        block = narrative_blocks.get(key)
        final_text = block.get("final_text") if isinstance(block, dict) else None
        ai_draft = block.get("ai_draft") if isinstance(block, dict) else None
        is_missing = not final_text and not ai_draft
        if is_missing:
            missing_sections.append(title)
        sections.append({
            "key": key,
            "title": title,
            "text": final_text if final_text else _PENDING_SECTION_PLACEHOLDER,
            "is_missing": is_missing,
        })

    raw_metrics = report.metrics_snapshot
    metrics: dict = raw_metrics if isinstance(raw_metrics, dict) else {}

    session_detail_rows = metrics.get("session_detail") or []
    session_detail = {
        "rows": session_detail_rows,
        "is_empty": not session_detail_rows,
        "placeholder": _PENDING_TABLE_PLACEHOLDER,
    }

    raw_attendance = metrics.get("attendance_by_athlete") or {}
    attendance_rows: list[dict] = []
    if isinstance(raw_attendance, dict):
        for athlete_id, stats in raw_attendance.items():
            if not isinstance(stats, dict):
                continue
            attendance_rows.append({
                "athlete_id": athlete_id,
                "count_present": stats.get("count_present", 0),
                "count_absent": stats.get("count_absent", 0),
                "count_justified": stats.get("count_justified", 0),
                "count_late": stats.get("count_late", 0),
                "count_injured": stats.get("count_injured", 0),
                "total_sessions": stats.get("total_sessions", 0),
                "attendance_pct": stats.get("attendance_pct", 0.0),
                "avg_rubric_effort": stats.get("avg_rubric_effort"),
                "avg_rubric_attitude": stats.get("avg_rubric_attitude"),
                "avg_rubric_technique": stats.get("avg_rubric_technique"),
            })
    attendance_table = {
        "rows": attendance_rows,
        "is_empty": not attendance_rows,
        "placeholder": _PENDING_TABLE_PLACEHOLDER,
    }

    raw_competition = report.competition_results
    competition_results: list = raw_competition if isinstance(raw_competition, list) else []
    competition_groups = _group_competition_results(competition_results)

    return {
        "header": header,
        "status": status.value if isinstance(status, MonthlyReportStatus) else str(status),
        "is_draft": is_draft,
        "sections": sections,
        "missing_sections": missing_sections,
        "session_detail": session_detail,
        "attendance_table": attendance_table,
        "competition_results": competition_results,
        "competition_groups": competition_groups,
        "has_competition_results": bool(competition_results),
    }


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
