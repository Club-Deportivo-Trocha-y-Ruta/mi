"""Block assembly + session-attachment service for the Strength Training
Library (feature 021, T021).

All functions are async and accept an ``AsyncSession``. Unlike the read-only
``catalog.py`` module, this module owns its transaction boundaries (mirrors
``services/technique/assembler.py``): each public write function issues its
own ``db.commit()`` after the block/entries/link rows are flushed, then
reloads with the eager-load chain the router needs to serialize the response
without a second round-trip.

Club scoping (data-model.md, contracts/strength-api.md):
    Every block is owned by exactly one club (``StrengthBlock.club_id``).
    Every read/write here takes an explicit ``club_id`` and filters on it —
    a block from another club is treated as not found (``None`` / 404), never
    as a permission error leaking existence. Session attachment additionally
    verifies the target ``TrainingSession`` belongs to the same club.

Age-band guardrail (FR-011, US3):
    Enforced in ``_validate_age_band_guardrail`` (called from both
    ``create_block`` and ``update_block`` before any row is written). For
    each submitted entry, when the exercise's ``age_bands`` do not include
    the block's ``target_age_band`` and the entry's ``is_age_override`` is
    not ``True``, the write is rejected with ``HTTPException(422)`` whose
    ``detail`` is a structured ``{"code": "AGE_BAND_GUARDRAIL", "detail":
    "<Spanish explanation>"}`` payload (no existing structured-error-code
    convention was found elsewhere in the codebase — every other
    ``HTTPException`` in this module uses a plain Spanish string ``detail``
    — so this shape is introduced here per contracts/strength-api.md's
    named ``AGE_BAND_GUARDRAIL`` error and may be reused by future routers
    that need a machine-readable code). When ``is_age_override=True`` the
    mismatch is allowed and persisted as-is (``is_age_override`` +
    ``override_note`` on the ``StrengthBlockEntry`` row) — this is the
    "warn-and-allow with a recorded override" behavior (FR-011).
"""
from __future__ import annotations

import logging
from typing import Sequence

from fastapi import HTTPException, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.strength import (
    StrengthBlock,
    StrengthBlockEntry,
    StrengthExercise,
    StrengthSessionBlock,
)
from app.models.technique_exercise import AgeBand
from app.models.training_session import TrainingSession
from app.schemas.strength import BlockEntryIn

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _block_select():  # type: ignore[return]
    """Base SELECT for ``StrengthBlock`` with the full read eager-load chain.

    Loads ``entries`` (ordered by ``position`` via the relationship's
    ``order_by`` — see ``models/strength.py``), each entry's ``exercise``,
    and each exercise's ``age_bands`` — everything ``BlockOut``/``EntryOut``/
    ``ExerciseOut`` need to serialize without triggering a lazy load
    (Constitution IV, no N+1).

    Returns:
        A SQLAlchemy ``Select`` ready to be extended with ``.where()``.
        No DB I/O is performed here.
    """
    return select(StrengthBlock).options(
        selectinload(StrengthBlock.entries)
        .selectinload(StrengthBlockEntry.exercise)
        .selectinload(StrengthExercise.age_bands)
    )


async def _load_exercises_by_ids(
    db: AsyncSession, exercise_ids: list[int]
) -> dict[int, StrengthExercise]:
    """Load non-hidden exercises keyed by id, with ``age_bands`` eager-loaded.

    Missing or hidden ids are simply absent from the returned mapping —
    callers detect the gap by diffing against the requested id set and raise
    404 (contract: "404 — unknown/hidden exercise_id"). ``age_bands`` is
    eager-loaded (selectinload) because ``_validate_age_band_guardrail``
    reads it after this coroutine returns — without it, that read would
    trigger an implicit lazy load outside the async context (Constitution
    IV, no N+1 / no implicit I/O).

    Args:
        db: Active async session. Caller owns commit/rollback.
        exercise_ids: Distinct exercise primary keys to look up (may contain
            duplicates; harmless for the IN clause).

    Returns:
        Mapping of ``exercise_id -> StrengthExercise`` for every id that
        exists and is not hidden, with ``age_bands`` eagerly loaded.

    Side-effects:
        Issues one SELECT + one selectinload IN-query. No writes.
    """
    if not exercise_ids:
        return {}
    result = await db.execute(
        select(StrengthExercise)
        .options(selectinload(StrengthExercise.age_bands))
        .where(
            StrengthExercise.id.in_(exercise_ids),
            StrengthExercise.is_hidden.is_(False),
        )
    )
    return {ex.id: ex for ex in result.scalars().all()}


def _validate_entries_exercises(
    entries: Sequence[BlockEntryIn], exercises: dict[int, StrengthExercise]
) -> None:
    """Raise 404 when any submitted entry references an unknown/hidden exercise.

    Args:
        entries: Submitted block entries (``BlockEntryIn`` from the request
            body — ``BlockCreate.entries`` / ``BlockUpdate.entries``).
        exercises: Mapping returned by ``_load_exercises_by_ids`` for the
            same entries' ``exercise_id`` values.

    Raises:
        HTTPException 404: with the list of missing/hidden exercise ids in
            the (Spanish) detail message.
    """
    missing = sorted({entry.exercise_id for entry in entries} - exercises.keys())
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ejercicios no encontrados o inactivos: {missing}",
        )


def _validate_age_band_guardrail(
    entries: Sequence[BlockEntryIn],
    exercises: dict[int, StrengthExercise],
    target_age_band: AgeBand,
) -> None:
    """Enforce the age-band appropriateness guardrail (FR-011, US3).

    For each submitted entry, when the exercise's age bands do not include
    the block's ``target_age_band`` and the entry did not set
    ``is_age_override=True``, the whole write is rejected. This is a
    "warn-and-allow with a recorded override" guardrail — the coach may
    proceed by explicitly setting ``is_age_override=True`` (and, by
    convention, an ``override_note``), which is persisted as-is by the
    caller.

    Must run after ``_validate_entries_exercises`` — assumes every
    ``entry.exercise_id`` is present in ``exercises`` (unknown/hidden ids
    already raised 404 by that point).

    Args:
        entries: Submitted block entries (``BlockEntryIn``).
        exercises: Mapping of ``exercise_id -> StrengthExercise`` with
            ``age_bands`` eagerly loaded (from ``_load_exercises_by_ids``).
        target_age_band: The block's guardrail context
            (``BlockCreate.target_age_band`` / ``BlockUpdate.target_age_band``).

    Raises:
        HTTPException 422: ``detail={"code": "AGE_BAND_GUARDRAIL", "detail":
            "<Spanish explanation>"}`` for the first offending entry whose
            exercise is not appropriate for ``target_age_band`` and which
            did not set ``is_age_override=True``.
    """
    for entry in entries:
        if entry.is_age_override:
            continue
        exercise = exercises[entry.exercise_id]
        exercise_bands = {ab.age_band for ab in exercise.age_bands}
        if target_age_band not in exercise_bands:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "AGE_BAND_GUARDRAIL",
                    "detail": (
                        f"El ejercicio '{exercise.name}' no es apropiado "
                        f"para la banda de edad {target_age_band.value}: "
                        "está dirigido a "
                        f"{', '.join(sorted(b.value for b in exercise_bands)) or 'ninguna banda'}. "
                        "Confirma la excepción explícitamente "
                        "(is_age_override=true) para agregarlo de todas "
                        "formas; la excepción quedará registrada."
                    ),
                },
            )


async def _reload_block(db: AsyncSession, block_id: int) -> StrengthBlock:
    """Reload a block by id with the full read eager-load chain.

    Used after every write (create/update/archive) so the caller always
    serializes fresh, fully-loaded state. Assumes the id exists (callers
    only invoke this right after a successful write to that id).

    Args:
        db: Active async session.
        block_id: Primary key of a ``StrengthBlock`` known to exist.

    Returns:
        The reloaded ``StrengthBlock`` with ``entries.exercise.age_bands``
        eagerly loaded.

    Side-effects:
        Issues one primary SELECT + selectinload IN-queries. No writes.
    """
    result = await db.execute(_block_select().where(StrengthBlock.id == block_id))
    return result.unique().scalar_one()


# ---------------------------------------------------------------------------
# Public: running total (FR-009 / FR-010)
# ---------------------------------------------------------------------------


def total_duration_min(entries: Sequence[StrengthBlockEntry]) -> int:
    """Return the block's running total in minutes — Σ ``duration_min``.

    Pure computation, no I/O. Echoed on ``BlockOut.total_duration_min`` so
    the frontend does not have to recompute it (data-model.md validation
    rule 1: within/at/over-target indicator thresholds are derived from this
    value client-side).

    Args:
        entries: The block's entries (ORM ``StrengthBlockEntry`` rows).

    Returns:
        Sum of every entry's ``duration_min``; ``0`` for an empty sequence.
    """
    return sum(entry.duration_min for entry in entries)


# ---------------------------------------------------------------------------
# Public: block CRUD
# ---------------------------------------------------------------------------


async def create_block(
    db: AsyncSession,
    *,
    name: str,
    target_age_band: AgeBand,
    duration_target_min: int,
    entries: Sequence[BlockEntryIn],
    club_id: int,
    created_by_user_id: int,
) -> StrengthBlock:
    """Create a strength block with its entries, positioned 0..n-1.

    Entries are re-positioned in submission (payload) order regardless of
    whatever ``position`` value the caller sent per entry — mirrors the
    ``PUT`` re-positioning rule (data-model.md validation rule 1) so create
    and update share the same invariant from the start.

    Age-band guardrail (FR-011, US3): each entry whose exercise is not
    appropriate for ``target_age_band`` must set ``is_age_override=True`` or
    the whole write is rejected with 422 ``AGE_BAND_GUARDRAIL`` before any
    row is inserted. Overriding entries persist their ``is_age_override``/
    ``override_note`` fields as submitted.

    Args:
        db: Active async session. This function owns the commit.
        name: Block display name.
        target_age_band: Guardrail context for the block (FR-011).
        duration_target_min: Configurable target used by the running-total
            indicator (default handled by the schema layer, not here).
        entries: Ordered ``BlockEntryIn`` list from the request body.
        club_id: Club that owns the block (router-resolved from the coach).
        created_by_user_id: Authenticated coach/admin user id.

    Returns:
        The newly created ``StrengthBlock``, reloaded with
        ``entries.exercise.age_bands`` eagerly loaded.

    Raises:
        HTTPException 404: an entry references an unknown/hidden exercise_id.
        HTTPException 422: an entry's exercise is not appropriate for
            ``target_age_band`` and did not set ``is_age_override=True``
            (``AGE_BAND_GUARDRAIL``).

    Side-effects:
        Issues SELECT/INSERT statements; commits once.
    """
    exercise_ids = [entry.exercise_id for entry in entries]
    exercises = await _load_exercises_by_ids(db, exercise_ids)
    _validate_entries_exercises(entries, exercises)
    _validate_age_band_guardrail(entries, exercises, target_age_band)

    block = StrengthBlock(
        name=name,
        target_age_band=target_age_band,
        duration_target_min=duration_target_min,
        club_id=club_id,
        created_by_user_id=created_by_user_id,
        is_archived=False,
    )
    db.add(block)
    await db.flush()  # populate block.id for the entry FKs below

    for position, entry in enumerate(entries):
        db.add(
            StrengthBlockEntry(
                block_id=block.id,
                exercise_id=entry.exercise_id,
                position=position,
                duration_min=entry.duration_min,
                reps=entry.reps,
                is_age_override=entry.is_age_override,
                override_note=entry.override_note,
            )
        )

    await db.commit()

    reloaded = await _reload_block(db, block.id)
    logger.debug(
        "Bloque de fuerza creado | block_id=%s club_id=%s entries=%d",
        reloaded.id,
        club_id,
        len(entries),
    )
    return reloaded


async def update_block(
    db: AsyncSession,
    *,
    block_id: int,
    club_id: int,
    name: str,
    target_age_band: AgeBand,
    duration_target_min: int,
    entries: Sequence[BlockEntryIn],
) -> StrengthBlock | None:
    """Full replace of a block's fields and entries (contract: ``PUT``).

    All existing ``StrengthBlockEntry`` rows for the block are deleted and
    replaced with the submitted set, re-positioned 0..n-1 in payload order —
    the same rule as ``create_block``. Shrinking the entry count simply drops
    the removed rows entirely (no soft-delete on entries).

    Args:
        db: Active async session. This function owns the commit.
        block_id: Primary key of the block to replace.
        club_id: Club-scope filter — a block from another club is treated as
            not found (returns ``None``, router 404s).
        name: New block display name.
        target_age_band: New guardrail context.
        duration_target_min: New running-total target.
        entries: Ordered ``BlockEntryIn`` list — the full new entry set.

    Returns:
        The updated ``StrengthBlock`` reloaded with eager-loaded relations,
        or ``None`` when ``block_id`` does not exist (or belongs to another
        club).

    Raises:
        HTTPException 404: an entry references an unknown/hidden exercise_id.
        HTTPException 422: an entry's exercise is not appropriate for
            ``target_age_band`` and did not set ``is_age_override=True``
            (``AGE_BAND_GUARDRAIL``).

    Side-effects:
        Issues SELECT/DELETE/INSERT statements; commits once when the block
        is found (no write occurs when it is not found).
    """
    result = await db.execute(
        select(StrengthBlock).where(
            StrengthBlock.id == block_id, StrengthBlock.club_id == club_id
        )
    )
    block = result.scalar_one_or_none()
    if block is None:
        return None

    exercise_ids = [entry.exercise_id for entry in entries]
    exercises = await _load_exercises_by_ids(db, exercise_ids)
    _validate_entries_exercises(entries, exercises)
    _validate_age_band_guardrail(entries, exercises, target_age_band)

    block.name = name
    block.target_age_band = target_age_band
    block.duration_target_min = duration_target_min

    await db.execute(
        sa_delete(StrengthBlockEntry).where(StrengthBlockEntry.block_id == block_id)
    )
    await db.flush()

    for position, entry in enumerate(entries):
        db.add(
            StrengthBlockEntry(
                block_id=block_id,
                exercise_id=entry.exercise_id,
                position=position,
                duration_min=entry.duration_min,
                reps=entry.reps,
                is_age_override=entry.is_age_override,
                override_note=entry.override_note,
            )
        )

    await db.commit()

    reloaded = await _reload_block(db, block_id)
    logger.debug(
        "Bloque de fuerza actualizado | block_id=%s club_id=%s entries=%d",
        block_id,
        club_id,
        len(entries),
    )
    return reloaded


async def get_block(
    db: AsyncSession, *, block_id: int, club_id: int
) -> StrengthBlock | None:
    """Return a single club-scoped block by id, or ``None`` when not found.

    A block belonging to a different club is treated identically to a
    non-existent block (returns ``None`` — router 404s either way), so club
    membership is never leaked through response-code differences.

    Args:
        db: Active async session. Caller owns commit/rollback.
        block_id: Primary key of the ``StrengthBlock`` row.
        club_id: Club-scope filter.

    Returns:
        ``StrengthBlock`` with ``entries.exercise.age_bands`` eagerly
        loaded, or ``None``.

    Side-effects:
        Issues SELECT statements. No writes.
    """
    result = await db.execute(
        _block_select().where(
            StrengthBlock.id == block_id, StrengthBlock.club_id == club_id
        )
    )
    return result.unique().scalar_one_or_none()


async def list_blocks(
    db: AsyncSession, *, club_id: int, include_archived: bool = False
) -> tuple[list[StrengthBlock], int]:
    """Return every block owned by a club, most-recently-created first.

    Args:
        db: Active async session. Caller owns commit/rollback.
        club_id: Club-scope filter — only this club's blocks are returned.
        include_archived: When ``False`` (default), excludes
            ``is_archived = true`` rows (contract: ``GET /blocks`` default).
            Pass ``True`` for ``?include_archived=true``.

    Returns:
        Tuple of (list of ``StrengthBlock`` with eager-loaded relations,
        total count of matching rows).

    Side-effects:
        Issues SELECT statements. No writes.
    """
    stmt = _block_select().where(StrengthBlock.club_id == club_id)
    if not include_archived:
        stmt = stmt.where(StrengthBlock.is_archived.is_(False))
    stmt = stmt.order_by(StrengthBlock.created_at.desc())

    result = await db.execute(stmt)
    items = list(result.unique().scalars().all())
    return items, len(items)


async def archive_block(
    db: AsyncSession, *, block_id: int, club_id: int, is_archived: bool
) -> StrengthBlock | None:
    """Soft-archive (or un-archive) a block (contract: ``PATCH .../archive``).

    Archived blocks are excluded from the default ``list_blocks`` result but
    remain fully readable via ``get_block`` and stay attached to any
    sessions they were already attached to (data-model.md: "Archived blocks
    stay attached to sessions, read-only there").

    Args:
        db: Active async session. This function owns the commit.
        block_id: Primary key of the block to (un)archive.
        club_id: Club-scope filter.
        is_archived: New value for ``StrengthBlock.is_archived``.

    Returns:
        The updated ``StrengthBlock`` reloaded with eager-loaded relations,
        or ``None`` when ``block_id`` does not exist (or belongs to another
        club) — no write occurs in that case.

    Side-effects:
        Issues SELECT statements; commits once when the block is found.
    """
    result = await db.execute(
        select(StrengthBlock).where(
            StrengthBlock.id == block_id, StrengthBlock.club_id == club_id
        )
    )
    block = result.scalar_one_or_none()
    if block is None:
        return None

    block.is_archived = is_archived
    await db.commit()

    return await _reload_block(db, block_id)


# ---------------------------------------------------------------------------
# Public: session attachment (FR-012 / FR-013)
# ---------------------------------------------------------------------------


async def attach_block_to_session(
    db: AsyncSession,
    *,
    block_id: int,
    training_session_id: int,
    club_id: int,
    attached_by_user_id: int,
) -> StrengthSessionBlock:
    """Attach a reusable block to a training session (contract: ``POST .../attach``).

    A block is reusable across sessions (no copy-on-attach, per data-model.md
    assumption) — the same ``block_id`` may be attached to many sessions, but
    never twice to the *same* session (unique ``(training_session_id,
    block_id)`` pair — enforced here at the application layer ahead of the DB
    unique constraint so the error is a clean 409 with a Spanish detail).

    Args:
        db: Active async session. This function owns the commit.
        block_id: Primary key of the block to attach.
        training_session_id: Primary key of the target training session.
        club_id: Club-scope filter — both the block and the session must
            belong to this club.
        attached_by_user_id: Authenticated coach/admin user id.

    Returns:
        The newly created ``StrengthSessionBlock`` link row (refreshed so
        ``id``/``attached_at`` are populated).

    Raises:
        HTTPException 404: unknown block_id, or unknown/foreign-club
            training_session_id.
        HTTPException 409: the pair is already attached.

    Side-effects:
        Issues SELECT statements; commits once on success.
    """
    block_result = await db.execute(
        select(StrengthBlock.id).where(
            StrengthBlock.id == block_id, StrengthBlock.club_id == club_id
        )
    )
    if block_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bloque de fuerza {block_id} no encontrado.",
        )

    session_result = await db.execute(
        select(TrainingSession.id).where(
            TrainingSession.id == training_session_id,
            TrainingSession.club_id == club_id,
        )
    )
    if session_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sesión de entrenamiento {training_session_id} no encontrada.",
        )

    existing_result = await db.execute(
        select(StrengthSessionBlock.id).where(
            StrengthSessionBlock.training_session_id == training_session_id,
            StrengthSessionBlock.block_id == block_id,
        )
    )
    if existing_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este bloque ya está adjunto a esta sesión.",
        )

    link = StrengthSessionBlock(
        training_session_id=training_session_id,
        block_id=block_id,
        position=0,
        attached_by_user_id=attached_by_user_id,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)

    logger.debug(
        "Bloque adjuntado a sesión | block_id=%s training_session_id=%s club_id=%s",
        block_id,
        training_session_id,
        club_id,
    )
    return link


async def detach_block_from_session(
    db: AsyncSession, *, block_id: int, training_session_id: int, club_id: int
) -> bool:
    """Detach a block from a session (contract: ``DELETE .../attach/{sid}``).

    Only removes the link row — the block itself is untouched (RESTRICT on
    ``StrengthSessionBlock.block_id`` means the block always survives even
    when the *session* is deleted; this function is the inverse operation,
    explicitly requested by the coach).

    Args:
        db: Active async session. This function owns the commit.
        block_id: Primary key of the block. Club-scoped: raises 404 when the
            block does not belong to ``club_id``.
        training_session_id: Primary key of the session to detach from.
        club_id: Club-scope filter for the block lookup.

    Returns:
        ``True`` when a link row was found and removed; ``False`` when no
        such attachment existed (idempotent no-op — the router may choose to
        surface this as 204 either way, or 404; contract does not mandate a
        specific behavior for the missing-link case).

    Raises:
        HTTPException 404: ``block_id`` does not exist (or belongs to
            another club).

    Side-effects:
        Issues SELECT statements; commits once when a link row is deleted.
    """
    block_result = await db.execute(
        select(StrengthBlock.id).where(
            StrengthBlock.id == block_id, StrengthBlock.club_id == club_id
        )
    )
    if block_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bloque de fuerza {block_id} no encontrado.",
        )

    result = await db.execute(
        select(StrengthSessionBlock).where(
            StrengthSessionBlock.training_session_id == training_session_id,
            StrengthSessionBlock.block_id == block_id,
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        return False

    await db.delete(link)
    await db.commit()

    logger.debug(
        "Bloque desadjuntado de sesión | block_id=%s training_session_id=%s club_id=%s",
        block_id,
        training_session_id,
        club_id,
    )
    return True


async def list_session_blocks(
    db: AsyncSession, *, training_session_id: int, club_id: int
) -> list[StrengthBlock]:
    """Return the blocks attached to a session, in attach order (contract: ``GET /sessions/{sid}/blocks``).

    Used to render the strength portion of a session's plan (FR-012/FR-013).
    Club-scoped defensively: attachment already guarantees the block and the
    session share a club, but the filter is repeated here so this function
    never returns cross-club data even if called with a stale/foreign
    ``club_id``.

    Args:
        db: Active async session. Caller owns commit/rollback.
        training_session_id: Primary key of the training session.
        club_id: Club-scope filter applied to the returned blocks.

    Returns:
        List of attached ``StrengthBlock`` rows (eager-loaded relations),
        ordered by ``(position, attached_at)``. Empty list when nothing is
        attached — never raises for an unknown session (mirrors the
        empty-catalog convention; the router may 404 first if it separately
        validates the session belongs to the club).

    Side-effects:
        Issues SELECT statements (join + selectinload IN-queries). No writes.
    """
    stmt = (
        _block_select()
        .join(
            StrengthSessionBlock,
            StrengthSessionBlock.block_id == StrengthBlock.id,
        )
        .where(
            StrengthSessionBlock.training_session_id == training_session_id,
            StrengthBlock.club_id == club_id,
        )
        .order_by(StrengthSessionBlock.position, StrengthSessionBlock.attached_at)
    )
    result = await db.execute(stmt)
    return list(result.unique().scalars().all())
