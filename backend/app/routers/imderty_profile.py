"""IMDERTY athlete profile, "contacto principal" and sensitive-data routes.

Source of truth: ``specs/047-imderty-attendance-sheet/contracts/api.md``
("Athlete IMDERTY profile" and "Sensitive data" sections). Business logic
lives in ``app.services.imderty.profile``; this module only wires HTTP:
RBAC via ``_require_athlete_staff``, request-body parsing that never echoes
a submitted value back on a 422 (Ley 1581 — the default FastAPI validation
handler includes the raw ``input`` in every error), and a 1:1 mapping from
``ImdertyProfileError`` to ``HTTPException``.

``_require_athlete_staff`` is deliberately a local copy of
``app.routers.imderty.require_athlete_staff`` (same shape as
``imderty_barrios.py``'s ``_require_admin``): that module imports this
router to mount it, so importing back would be circular.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.athlete import Athlete
from app.models.user import User, UserRole
from app.schemas.imderty import (
    ImdertyGuardianSummary,
    ImdertyProfileRead,
    ImdertyProfileUpdate,
    ImdertyProfileUpdateResult,
    PrimaryContactUpdate,
    SensitiveAuthorizationCreate,
    SensitiveAuthorizationRead,
    SensitiveDataRead,
    SensitiveDataUpdate,
)
from app.services.imderty import profile as svc
from app.services.permissions import coach_club_ids as _coach_club_ids

router = APIRouter(tags=["imderty-profile"])


async def _require_athlete_staff(
    athlete_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Athlete:
    """Admin, or a coach whose club owns the athlete; 403/404 otherwise.

    Kept in sync with ``app.routers.imderty.require_athlete_staff`` by hand
    — duplicated only to avoid the circular import described above.
    """
    result = await db.execute(
        select(Athlete).where(Athlete.id == athlete_id, Athlete.deleted_at.is_(None))
    )
    athlete = result.scalar_one_or_none()
    if athlete is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Atleta no encontrado"
        )

    if current_user.role == UserRole.admin:
        return athlete

    if current_user.role == UserRole.coach and athlete.club_id in _coach_club_ids(
        current_user
    ):
        return athlete

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permisos para esta acción"
    )


def _parse_body(model: type[BaseModel], payload: dict[str, Any]) -> Any:
    """Validate ``payload`` against ``model``; 422 without ever echoing a
    submitted value (unlike FastAPI's default handler, whose error items
    carry ``input``)."""
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        detail = [
            {"type": error["type"], "loc": list(error["loc"]), "msg": error["msg"]}
            for error in exc.errors()
        ]
        raise HTTPException(status_code=422, detail=detail) from exc


def _raise_for(exc: svc.ImdertyProfileError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


@router.get(
    "/athletes/{athlete_id}/imderty-profile", response_model=ImdertyProfileRead
)
async def get_imderty_profile(
    athlete: Athlete = Depends(_require_athlete_staff),
    db: AsyncSession = Depends(get_db),
) -> ImdertyProfileRead:
    return await svc.get_or_empty_profile(db, athlete)


@router.put(
    "/athletes/{athlete_id}/imderty-profile", response_model=ImdertyProfileUpdateResult
)
async def put_imderty_profile(
    payload: dict[str, Any] = Body(default_factory=dict),
    athlete: Athlete = Depends(_require_athlete_staff),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImdertyProfileUpdateResult:
    body = _parse_body(ImdertyProfileUpdate, payload)
    try:
        return await svc.upsert_profile(db, athlete, body, current_user)
    except svc.ImdertyProfileError as exc:
        _raise_for(exc)


@router.put(
    "/athletes/{athlete_id}/primary-contact",
    response_model=list[ImdertyGuardianSummary],
)
async def put_primary_contact(
    payload: dict[str, Any] = Body(default_factory=dict),
    athlete: Athlete = Depends(_require_athlete_staff),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ImdertyGuardianSummary]:
    body = _parse_body(PrimaryContactUpdate, payload)
    try:
        return await svc.set_primary_contact(
            db, athlete, body.guardian_user_id, current_user
        )
    except svc.ImdertyProfileError as exc:
        _raise_for(exc)


# ---------------------------------------------------------------------------
# Sensitive data
# ---------------------------------------------------------------------------


@router.post(
    "/athletes/{athlete_id}/sensitive-authorizations",
    response_model=SensitiveAuthorizationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_sensitive_authorization(
    payload: dict[str, Any] = Body(default_factory=dict),
    athlete: Athlete = Depends(_require_athlete_staff),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SensitiveAuthorizationRead:
    body = _parse_body(SensitiveAuthorizationCreate, payload)
    try:
        return await svc.create_authorization(db, athlete, body, current_user)
    except svc.ImdertyProfileError as exc:
        _raise_for(exc)


@router.post(
    "/athletes/{athlete_id}/sensitive-authorizations/withdraw",
    response_model=SensitiveAuthorizationRead,
)
async def withdraw_sensitive_authorization(
    athlete: Athlete = Depends(_require_athlete_staff),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SensitiveAuthorizationRead:
    try:
        return await svc.withdraw_authorization(db, athlete, current_user)
    except svc.ImdertyProfileError as exc:
        _raise_for(exc)


@router.get(
    "/athletes/{athlete_id}/sensitive-data", response_model=SensitiveDataRead
)
async def get_sensitive_data(
    athlete: Athlete = Depends(_require_athlete_staff),
    db: AsyncSession = Depends(get_db),
) -> SensitiveDataRead:
    try:
        return await svc.get_sensitive_data(db, athlete)
    except svc.ImdertyProfileError as exc:
        _raise_for(exc)


@router.put(
    "/athletes/{athlete_id}/sensitive-data", response_model=SensitiveDataRead
)
async def put_sensitive_data(
    payload: dict[str, Any] = Body(default_factory=dict),
    athlete: Athlete = Depends(_require_athlete_staff),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SensitiveDataRead:
    body = _parse_body(SensitiveDataUpdate, payload)
    try:
        return await svc.update_sensitive_data(db, athlete, body, current_user)
    except svc.ImdertyProfileError as exc:
        _raise_for(exc)
