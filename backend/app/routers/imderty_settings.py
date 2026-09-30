"""IMDERTY club settings routes.

``GET``/``PUT /api/clubs/{club_id}/imderty-settings`` — saved sheet-header
defaults for a club (``ClubImdertySettings``, 1:1 with ``clubs``).

Follows the get-or-create and audit pattern of ``routers/monthly_reports.py``
project-profile (``get_project_profile`` / ``upsert_project_profile``,
~L803-947), with two differences demanded by contracts/api.md §"Settings":

- ``GET`` never 404s — a club that has never saved settings gets 200 with
  nulls and an empty ``programs`` list (no row is created on read).
- ``PUT`` is the only write and is a full get-or-create upsert (there is no
  separate PATCH here, unlike the project-profile router).

None of the fields on this table are a minor's data (``contractor_name`` is
the adult contractor/coach; the rest are venue/schedule strings), so the
audit entry only records ``changed_fields`` — no value ever reaches
``diff_json`` (no entry for ``AuditEntityType.club_imderty_settings`` in
``VALUE_ALLOWLIST``, services/audit.py).
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.club import Club
from app.models.imderty import ClubImdertySettings
from app.models.user import User
from app.schemas.imderty import ClubImdertySettingsRead, ClubImdertySettingsUpdate
from app.services.audit import AuditAction, AuditEntityType, record_audit

router = APIRouter(tags=["imderty-settings"])


async def _require_club_staff(
    club_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Club:
    """Thin wrapper around ``app.routers.imderty.require_club_staff``.

    ``imderty.py`` imports this module (and every other IMDERTY sub-router)
    at the top, *before* defining its own RBAC dependencies further down the
    file — so a module-level ``from app.routers.imderty import
    require_club_staff`` here would be a circular import. Importing inside
    the function body defers the lookup until the first request, by which
    point ``app.routers.imderty`` has finished loading.
    """
    from app.routers.imderty import require_club_staff

    return await require_club_staff(club_id, current_user, db)


@router.get(
    "/clubs/{club_id}/imderty-settings",
    response_model=ClubImdertySettingsRead,
)
async def get_imderty_settings(
    club: Club = Depends(_require_club_staff),
    db: AsyncSession = Depends(get_db),
) -> ClubImdertySettingsRead:
    """Returns the club's saved header defaults, or an all-null default
    when the club has never saved them (no row is created on read)."""
    result = await db.execute(
        select(ClubImdertySettings).where(ClubImdertySettings.club_id == club.id)
    )
    settings = result.scalar_one_or_none()
    if settings is None:
        return ClubImdertySettingsRead()
    return ClubImdertySettingsRead.model_validate(settings)


@router.put(
    "/clubs/{club_id}/imderty-settings",
    response_model=ClubImdertySettingsRead,
    status_code=status.HTTP_200_OK,
)
async def upsert_imderty_settings(
    body: ClubImdertySettingsUpdate,
    club: Club = Depends(_require_club_staff),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClubImdertySettingsRead:
    """Get-or-create upsert. Records an audit entry with ``changed_fields``
    (no values, per ``VALUE_ALLOWLIST``)."""
    result = await db.execute(
        select(ClubImdertySettings).where(ClubImdertySettings.club_id == club.id)
    )
    settings = result.scalar_one_or_none()

    data = body.model_dump(mode="json")
    is_create = settings is None
    if settings is None:
        settings = ClubImdertySettings(club_id=club.id, **data)
        db.add(settings)
    else:
        for key, value in data.items():
            setattr(settings, key, value)

    await db.flush()
    await record_audit(
        db,
        action=AuditAction.create if is_create else AuditAction.update,
        entity_type=AuditEntityType.club_imderty_settings,
        entity_id=club.id,
        actor=current_user,
        club_id=club.id,
        changed_fields=sorted(data.keys()),
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(settings)
    return ClubImdertySettingsRead.model_validate(settings)
