"""Servicio de perfil de circuito (feature 043, T018).

Persiste variantes de recorrido (GPX ya procesado por ``gpx_processing.py``),
la tabla de vueltas por categoría (``race_course_category_setups``) y compone
la lectura agregada (``GET /course``) que consume el router.

Rama coach/admin únicamente — la rama parent de ``get_course``
(``allowed_athlete_ids is not None``) es ``T055`` y hoy no la llama nadie
(el router no le da acceso al padre todavía).

Presupuesto de consultas de ``get_course``: **<= 3 sentencias** (event+variantes
vía LEFT JOIN, setups+categoría+variante propios, y — solo cuando la válida no
tiene setups propios — la sugerencia de la válida anterior de la serie). Nunca
se hace lazy-load de una relación fuera de las eager-loads explícitas de abajo.
"""
from __future__ import annotations

import hashlib
import logging

from fastapi import HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager

from app.models.race_category import RaceCategory
from app.models.race_course_category_setup import RaceCourseCategorySetup
from app.models.race_course_variant import RaceCourseVariant
from app.models.race_event import RaceEvent
from app.schemas.race_course import (
    CourseDescriptionRead,
    CourseRead,
    LapDetectionRead,
    SetupIn,
    SetupRead,
    SuggestedSetupRead,
    VariantRead,
)
from app.services.race.course.gpx_processing import ProcessedLap, process_gpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers puros (no I/O)
# ---------------------------------------------------------------------------


def has_course_data(event: RaceEvent) -> bool:
    """``True`` si la válida tiene alguna variante o algún campo de descripción.

    Requiere que ``event.course_variants`` ya esté eager-loaded — no dispara
    ninguna consulta por sí misma. Este NO es el helper que usa T020 para el
    listado / los tres sitios de construcción de ``RaceEventRead`` — ese vive
    en ``app.services.race_events.event_has_course_data`` y sí consulta la BD
    porque en esos sitios ``course_variants`` no está cargado.
    """
    return bool(event.course_variants) or any(
        [
            event.terrain_type,
            event.technical_difficulty,
            event.key_sectors,
            event.course_notes,
        ]
    )


def _variant_read(variant: RaceCourseVariant) -> VariantRead:
    """``ProcessedLap.detection.total_distance_m`` no se persiste (§4.1 del
    data-model — el archivo original se descarta tras procesar), así que se
    reconstruye de forma determinista a partir de las columnas guardadas:
    ``lap_distance_m`` ya es la vuelta medida sin simplificar y
    ``recorded_laps`` es lo que la plataforma cree que contenía la grabación
    completa (R-04). Es una aproximación (redondeo de la división original),
    nunca usada para nada distinto de mostrarla en la ficha de detección.
    """
    total_distance_m = round(variant.lap_distance_m * variant.recorded_laps)
    return VariantRead(
        id=variant.id,
        label=variant.label,
        lap_distance_km=round(variant.lap_distance_m / 1000, 1),
        lap_distance_m=variant.lap_distance_m,
        elevation_gain_m=variant.elevation_gain_m,
        has_elevation=variant.has_elevation,
        point_count=variant.point_count,
        geometry=variant.geometry,
        detection=LapDetectionRead(
            method=variant.detection_method,
            laps_detected=variant.recorded_laps,
            total_distance_m=total_distance_m,
        ),
        created_at=variant.created_at,
        updated_at=variant.updated_at,
    )


def _description_read(event: RaceEvent) -> CourseDescriptionRead:
    return CourseDescriptionRead(
        terrain_type=event.terrain_type,
        technical_difficulty=event.technical_difficulty,
        key_sectors=event.key_sectors or [],
        course_notes=event.course_notes,
    )


# ---------------------------------------------------------------------------
# Guards internos (404/409) — compartidos por las mutaciones
# ---------------------------------------------------------------------------


async def _assert_event_exists(db: AsyncSession, race_event_id: int) -> None:
    result = await db.execute(select(exists().where(RaceEvent.id == race_event_id)))
    if not result.scalar():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "race_event_not_found",
                "message": f"Evento de carrera con id={race_event_id} no existe.",
            },
        )


async def _get_variant_or_404(
    db: AsyncSession, race_event_id: int, variant_id: int
) -> RaceCourseVariant:
    result = await db.execute(
        select(RaceCourseVariant).where(
            RaceCourseVariant.id == variant_id,
            RaceCourseVariant.race_event_id == race_event_id,
        )
    )
    variant = result.scalar_one_or_none()
    if variant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "variant_not_found",
                "message": f"La variante id={variant_id} no existe en esta válida.",
            },
        )
    return variant


async def _assert_no_duplicate_recording(
    db: AsyncSession,
    race_event_id: int,
    sha256: str,
    *,
    exclude_variant_id: int | None = None,
) -> None:
    stmt = select(RaceCourseVariant).where(
        RaceCourseVariant.race_event_id == race_event_id,
        RaceCourseVariant.source_sha256 == sha256,
    )
    if exclude_variant_id is not None:
        stmt = stmt.where(RaceCourseVariant.id != exclude_variant_id)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "duplicate_recording",
                "message": f'Ya subiste esta misma grabación como "{existing.label}".',
            },
        )


async def _assert_label_unique(
    db: AsyncSession,
    race_event_id: int,
    label: str,
    *,
    exclude_variant_id: int | None = None,
) -> None:
    stmt = select(RaceCourseVariant.id).where(
        RaceCourseVariant.race_event_id == race_event_id,
        RaceCourseVariant.label == label,
    )
    if exclude_variant_id is not None:
        stmt = stmt.where(RaceCourseVariant.id != exclude_variant_id)
    conflict = (await db.execute(stmt)).scalar_one_or_none()
    if conflict is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "variant_label_taken",
                "message": "Ya existe una variante con ese nombre en esta válida.",
            },
        )


async def _rebuild_course(db: AsyncSession, race_event_id: int) -> CourseRead:
    """Recarga el ``CourseRead`` completo tras una mutación exitosa."""
    result = await get_course(db, race_event_id)
    if result is None:  # pragma: no cover - defensivo, ya se validó arriba
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "race_event_not_found",
                "message": f"Evento de carrera con id={race_event_id} no existe.",
            },
        )
    return result


# ---------------------------------------------------------------------------
# GET /course — lectura agregada (coach/admin)
# ---------------------------------------------------------------------------


async def _load_setups(db: AsyncSession, race_event_id: int) -> list[SetupRead]:
    stmt = (
        select(RaceCourseCategorySetup, RaceCategory, RaceCourseVariant)
        .join(RaceCategory, RaceCategory.id == RaceCourseCategorySetup.category_id)
        .join(RaceCourseVariant, RaceCourseVariant.id == RaceCourseCategorySetup.variant_id)
        .where(RaceCourseCategorySetup.race_event_id == race_event_id)
        .order_by(RaceCategory.sort_order)
    )
    rows = (await db.execute(stmt)).all()
    return [
        SetupRead(
            category_id=category.id,
            category_code=category.code,
            category_label=category.label,
            laps=setup.laps,
            variant_id=variant.id,
        )
        for setup, category, variant in rows
    ]


async def _suggested_setups(db: AsyncSession, event: RaceEvent) -> list[SuggestedSetupRead]:
    """R-14: sugerencia de prefill de la válida anterior de la misma serie que
    SÍ tenga setups propios (el ``JOIN`` con ``RaceCourseCategorySetup``
    descarta de raíz las válidas anteriores sin configurar). Solo se llama
    cuando la válida actual no tiene setups propios (ver ``get_course``).
    """
    stmt = (
        select(
            RaceEvent.id,
            RaceEvent.sequence_number,
            RaceCourseCategorySetup.category_id,
            RaceCourseCategorySetup.laps,
            RaceCourseVariant.label,
        )
        .join(RaceCourseCategorySetup, RaceCourseCategorySetup.race_event_id == RaceEvent.id)
        .join(RaceCourseVariant, RaceCourseVariant.id == RaceCourseCategorySetup.variant_id)
        .where(
            RaceEvent.series_id == event.series_id,
            RaceEvent.sequence_number < event.sequence_number,
        )
        .order_by(RaceEvent.sequence_number.desc())
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        return []
    top_sequence = rows[0][1]
    return [
        SuggestedSetupRead(
            category_id=category_id,
            laps=laps,
            variant_label=label,
            source_event_id=event_id,
        )
        for event_id, sequence_number, category_id, laps, label in rows
        if sequence_number == top_sequence
    ]


async def get_course(
    db: AsyncSession,
    race_event_id: int,
    *,
    allowed_athlete_ids: list[int] | None = None,
) -> CourseRead | None:
    """``None`` cuando ``race_event_id`` no existe (el router responde 404).

    Rama parent (``allowed_athlete_ids is not None``): ``T055`` — nada la usa
    todavía porque el router no le da esta ruta al padre.
    """
    if allowed_athlete_ids is not None:
        raise NotImplementedError("parent branch of get_course — see T055")

    stmt = (
        select(RaceEvent)
        .outerjoin(RaceCourseVariant, RaceCourseVariant.race_event_id == RaceEvent.id)
        .options(contains_eager(RaceEvent.course_variants))
        .where(RaceEvent.id == race_event_id)
        .order_by(RaceCourseVariant.id)
    )
    result = await db.execute(stmt)
    event = result.unique().scalar_one_or_none()
    if event is None:
        return None

    setups = await _load_setups(db, race_event_id)
    suggested = await _suggested_setups(db, event) if not setups else []

    return CourseRead(
        race_event_id=event.id,
        has_course_data=has_course_data(event),
        variants=[_variant_read(variant) for variant in event.course_variants],
        setups=setups,
        suggested_setups=suggested,
        description=_description_read(event),
        my_categories=[],
    )


# ---------------------------------------------------------------------------
# Mutaciones de variantes (coach/admin)
# ---------------------------------------------------------------------------


async def create_variant(
    db: AsyncSession,
    race_event_id: int,
    *,
    label: str,
    recorded_laps: int | None,
    content: bytes,
    filename: str,
    user_id: int,
) -> CourseRead:
    """``filename`` solo llega por paridad de interfaz con el router — nunca
    se persiste ni se registra en logs (Ley 1581, FR-003).
    """
    del filename  # nunca se persiste ni se loguea — ver docstring.

    await _assert_event_exists(db, race_event_id)

    # process_gpx puede lanzar CourseProcessingError — se deja propagar sin
    # capturar, el router la traduce a 422 con el código+mensaje del contrato.
    processed: ProcessedLap = process_gpx(content, recorded_laps=recorded_laps)
    sha256 = hashlib.sha256(content).hexdigest()

    await _assert_no_duplicate_recording(db, race_event_id, sha256)
    await _assert_label_unique(db, race_event_id, label)

    variant = RaceCourseVariant(
        race_event_id=race_event_id,
        label=label,
        lap_distance_m=processed.lap_distance_m,
        elevation_gain_m=processed.elevation_gain_m,
        has_elevation=processed.has_elevation,
        point_count=processed.point_count,
        geometry=processed.geometry,
        detection_method=processed.detection.method,
        recorded_laps=processed.detection.laps_detected,
        source_sha256=sha256,
        created_by_user_id=user_id,
    )
    db.add(variant)
    await db.flush()

    logger.info(
        "race_course_variant_processed race_event_id=%s variant_id=%s "
        "point_count=%s lap_distance_m=%s detection_method=%s",
        race_event_id,
        variant.id,
        variant.point_count,
        variant.lap_distance_m,
        variant.detection_method,
    )

    return await _rebuild_course(db, race_event_id)


async def replace_variant_file(
    db: AsyncSession,
    race_event_id: int,
    variant_id: int,
    *,
    recorded_laps: int | None,
    content: bytes,
    filename: str,
    user_id: int,
) -> CourseRead:
    """Reprocesa el GPX y sobrescribe geometría/figuras/detección en el
    mismo ``id`` (FR-009) — el ``label`` no se toca (ignorado por el router).
    """
    del filename  # nunca se persiste ni se loguea — ver create_variant.

    variant = await _get_variant_or_404(db, race_event_id, variant_id)

    processed = process_gpx(content, recorded_laps=recorded_laps)
    sha256 = hashlib.sha256(content).hexdigest()

    await _assert_no_duplicate_recording(
        db, race_event_id, sha256, exclude_variant_id=variant_id
    )
    await _assert_label_unique(
        db, race_event_id, variant.label, exclude_variant_id=variant_id
    )

    variant.lap_distance_m = processed.lap_distance_m
    variant.elevation_gain_m = processed.elevation_gain_m
    variant.has_elevation = processed.has_elevation
    variant.point_count = processed.point_count
    variant.geometry = processed.geometry
    variant.detection_method = processed.detection.method
    variant.recorded_laps = processed.detection.laps_detected
    variant.source_sha256 = sha256
    variant.updated_by_user_id = user_id

    await db.flush()

    logger.info(
        "race_course_variant_processed race_event_id=%s variant_id=%s "
        "point_count=%s lap_distance_m=%s detection_method=%s",
        race_event_id,
        variant.id,
        variant.point_count,
        variant.lap_distance_m,
        variant.detection_method,
    )

    return await _rebuild_course(db, race_event_id)


async def rename_variant(
    db: AsyncSession,
    race_event_id: int,
    variant_id: int,
    *,
    label: str,
    user_id: int,
) -> CourseRead:
    variant = await _get_variant_or_404(db, race_event_id, variant_id)
    await _assert_label_unique(db, race_event_id, label, exclude_variant_id=variant_id)

    variant.label = label
    variant.updated_by_user_id = user_id
    await db.flush()

    return await _rebuild_course(db, race_event_id)


async def delete_variant(
    db: AsyncSession,
    race_event_id: int,
    variant_id: int,
) -> CourseRead:
    variant = await _get_variant_or_404(db, race_event_id, variant_id)

    stmt = (
        select(RaceCategory.label)
        .join(
            RaceCourseCategorySetup,
            RaceCourseCategorySetup.category_id == RaceCategory.id,
        )
        .where(RaceCourseCategorySetup.variant_id == variant_id)
        .order_by(RaceCourseCategorySetup.id)
    )
    labels = list((await db.execute(stmt)).scalars().all())
    if labels:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "variant_in_use",
                "message": f"No se puede eliminar: la usan {', '.join(labels)}.",
            },
        )

    await db.delete(variant)
    await db.flush()

    return await _rebuild_course(db, race_event_id)


# ---------------------------------------------------------------------------
# PUT /course/setups — reemplazo total (coach/admin)
# ---------------------------------------------------------------------------


async def replace_setups(
    db: AsyncSession,
    race_event_id: int,
    *,
    setups: list[SetupIn],
    user_id: int,
) -> CourseRead:
    category_ids = [setup.category_id for setup in setups]
    if len(category_ids) != len(set(category_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "duplicate_category",
                "message": "Hay una categoría repetida en la tabla de vueltas.",
            },
        )

    variant_ids = {setup.variant_id for setup in setups}
    if variant_ids:
        valid_variant_ids = set(
            (
                await db.execute(
                    select(RaceCourseVariant.id).where(
                        RaceCourseVariant.id.in_(variant_ids),
                        RaceCourseVariant.race_event_id == race_event_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        if variant_ids - valid_variant_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "variant_not_in_event",
                    "message": "La variante no pertenece a esta válida.",
                },
            )

    if category_ids:
        valid_category_ids = set(
            (
                await db.execute(
                    select(RaceCategory.id).where(
                        RaceCategory.id.in_(category_ids),
                        RaceCategory.is_active.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        if set(category_ids) - valid_category_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "unknown_category",
                    "message": "La categoría no existe.",
                },
            )

    existing_rows = list(
        (
            await db.execute(
                select(RaceCourseCategorySetup).where(
                    RaceCourseCategorySetup.race_event_id == race_event_id
                )
            )
        )
        .scalars()
        .all()
    )
    existing_by_category = {row.category_id: row for row in existing_rows}
    incoming_category_ids = set(category_ids)

    for row in existing_rows:
        if row.category_id not in incoming_category_ids:
            await db.delete(row)

    for setup in setups:
        row = existing_by_category.get(setup.category_id)
        if row is not None:
            row.laps = setup.laps
            row.variant_id = setup.variant_id
            row.updated_by_user_id = user_id
        else:
            db.add(
                RaceCourseCategorySetup(
                    race_event_id=race_event_id,
                    category_id=setup.category_id,
                    variant_id=setup.variant_id,
                    laps=setup.laps,
                    updated_by_user_id=user_id,
                )
            )

    await db.flush()

    return await _rebuild_course(db, race_event_id)
