from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_current_user, get_db, require_role
from app.models.athlete import ParentAthlete
from app.models.club import ClubMember, ClubRole
from app.models.parent_invite import ParentInvite
from app.models.parental_consent import ParentalConsent
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserListOut, UserOut, UserUpdate
from app.services.auth import hash_password

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Roles que cada actor puede crear
_ALLOWED_CREATIONS: dict[UserRole, set[UserRole]] = {
    UserRole.admin: {UserRole.coach, UserRole.parent, UserRole.athlete},
    UserRole.coach: {UserRole.parent, UserRole.athlete},
}

# IDs de clubes donde el usuario es coach
def _coach_club_ids(user: User) -> set[int]:
    return {m.club_id for m in user.club_memberships if m.role_in_club == ClubRole.coach}


# ---------------------------------------------------------------------------
# POST /api/users
# ---------------------------------------------------------------------------
@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> User:
    # 1. Validar que el rol que se quiere crear esté permitido para el actor
    allowed = _ALLOWED_CREATIONS.get(current_user.role, set())
    if body.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No tienes permisos para crear usuarios con rol '{body.role}'",
        )

    # 2. Coach: validar email/password requeridos para coaches (aunque admin crea coaches,
    #    un coach nunca crea otro coach, así que esta regla aplica solo a admin).
    #    Para coaches que crean parent/athlete: deben proveer club_id.
    if current_user.role == UserRole.coach:
        if body.club_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Debes indicar el club (club_id) al que pertenece el nuevo usuario",
            )
        coach_clubs = _coach_club_ids(current_user)
        if body.club_id not in coach_clubs:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No perteneces al club indicado como coach",
            )

    # 3. Reglas específicas por rol a crear
    if body.role == UserRole.coach:
        # Email y password obligatorios para coaches
        if not body.email or not body.password:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Email y contraseña son requeridos para crear un coach",
            )

    # 4. Determinar can_login y hashed_password
    can_login = body.role != UserRole.athlete
    hashed: str | None = None
    if body.password:
        hashed = hash_password(body.password)
    elif body.role not in (UserRole.parent, UserRole.athlete):
        # Roles que sí necesitan login pero no trajeron password
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Se requiere contraseña para este rol",
        )

    # 5. Crear el usuario
    new_user = User(
        email=body.email or None,
        hashed_password=hashed,
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        role=body.role,
        can_login=can_login,
        created_by=current_user.id,
    )
    db.add(new_user)

    try:
        await db.flush()  # para obtener new_user.id y detectar duplicado de email
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un usuario con ese correo electrónico",
        )

    # 6. Si se proporcionó club_id, crear membresía
    if body.club_id is not None:
        # Mapear role → role_in_club
        role_in_club_map: dict[UserRole, ClubRole] = {
            UserRole.coach: ClubRole.coach,
            UserRole.parent: ClubRole.parent,
            UserRole.athlete: ClubRole.athlete,
        }
        role_in_club = role_in_club_map.get(body.role, ClubRole.parent)
        membership = ClubMember(
            club_id=body.club_id,
            user_id=new_user.id,
            role_in_club=role_in_club,
        )
        db.add(membership)

        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El usuario ya es miembro de ese club",
            )

    return new_user


# ---------------------------------------------------------------------------
# GET /api/users
# ---------------------------------------------------------------------------
@router.get("", response_model=UserListOut)
async def list_users(
    role: UserRole | None = Query(default=None),
    club_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> UserListOut:
    # Los atletas se gestionan por /api/athletes
    # Construir filtros base
    base_filters = [User.role != UserRole.athlete]

    if role is not None:
        if role == UserRole.athlete:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Los atletas se gestionan a través de /api/athletes",
            )
        base_filters.append(User.role == role)

    if current_user.role == UserRole.admin:
        # Admin: ve todos los usuarios (con filtros opcionales)
        if club_id is not None:
            query = (
                select(User)
                .join(ClubMember, ClubMember.user_id == User.id)
                .where(ClubMember.club_id == club_id, *base_filters)
                .options(selectinload(User.club_memberships))
            )
            count_query = (
                select(func.count())
                .select_from(User)
                .join(ClubMember, ClubMember.user_id == User.id)
                .where(ClubMember.club_id == club_id, *base_filters)
            )
        else:
            query = (
                select(User)
                .where(*base_filters)
                .options(selectinload(User.club_memberships))
            )
            count_query = select(func.count()).select_from(User).where(*base_filters)
    else:
        # Coach: solo usuarios de sus clubes
        coach_clubs = _coach_club_ids(current_user)
        if not coach_clubs:
            return UserListOut(items=[], total=0)

        if club_id is not None:
            if club_id not in coach_clubs:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No perteneces al club indicado como coach",
                )
            scope_clubs = {club_id}
        else:
            scope_clubs = coach_clubs

        query = (
            select(User)
            .join(ClubMember, ClubMember.user_id == User.id)
            .where(ClubMember.club_id.in_(scope_clubs), *base_filters)
            .options(selectinload(User.club_memberships))
            .distinct()
        )
        count_query = (
            select(func.count(User.id.distinct()))
            .select_from(User)
            .join(ClubMember, ClubMember.user_id == User.id)
            .where(ClubMember.club_id.in_(scope_clubs), *base_filters)
        )

    result = await db.execute(query)
    users = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar_one()

    return UserListOut(items=list(users), total=total)


# ---------------------------------------------------------------------------
# PATCH /api/users/{user_id}
# ---------------------------------------------------------------------------
@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> User:
    # Cargar el usuario objetivo
    result = await db.execute(
        select(User)
        .options(selectinload(User.club_memberships))
        .where(User.id == user_id)
    )
    target = result.scalar_one_or_none()

    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )

    # Autorización por rol
    if current_user.role == UserRole.coach:
        # Coach no puede editar admins ni otros coaches
        if target.role in (UserRole.admin, UserRole.coach):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para editar este usuario",
            )
        # El usuario debe pertenecer a uno de los clubes del coach
        coach_clubs = _coach_club_ids(current_user)
        target_clubs = {m.club_id for m in target.club_memberships}
        if not coach_clubs.intersection(target_clubs):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Este usuario no pertenece a ninguno de tus clubes",
            )
        # Coach no puede desactivarse a sí mismo (edge case: si intentara editar su propio usuario)
        if target.id == current_user.id and body.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No puedes desactivarte a ti mismo",
            )

    # Aplicar solo los campos provistos
    update_data = body.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(target, field, value)

    await db.flush()

    return target


# ---------------------------------------------------------------------------
# DELETE /api/users/{user_id} — eliminar padre/acudiente
# ---------------------------------------------------------------------------
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> None:
    """Elimina un padre/acudiente y limpia sus vínculos.

    Coach: solo puede borrar padres de sus clubes.
    No se permite borrar admin/coach por este endpoint, ni autoborrado.
    Atletas se gestionan vía DELETE /api/athletes/{id}.
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes eliminarte a ti mismo",
        )

    result = await db.execute(
        select(User)
        .options(selectinload(User.club_memberships))
        .where(User.id == user_id)
    )
    target = result.scalar_one_or_none()

    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )

    if target.role == UserRole.athlete:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los atletas se eliminan vía DELETE /api/athletes/{id}",
        )

    if target.role in (UserRole.admin, UserRole.coach):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes eliminar usuarios con rol admin o coach",
        )

    if current_user.role == UserRole.coach:
        coach_clubs = _coach_club_ids(current_user)
        target_clubs = {m.club_id for m in target.club_memberships}
        if not coach_clubs.intersection(target_clubs):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Este usuario no pertenece a ninguno de tus clubes",
            )

    # Cascada manual: limpiar referencias antes de eliminar el user.
    await db.execute(delete(ParentalConsent).where(ParentalConsent.parent_user_id == user_id))
    await db.execute(delete(ParentAthlete).where(ParentAthlete.parent_id == user_id))
    await db.execute(delete(ClubMember).where(ClubMember.user_id == user_id))
    await db.execute(
        update(ParentInvite).where(ParentInvite.used_by == user_id).values(used_by=None)
    )
    await db.execute(
        update(User).where(User.created_by == user_id).values(created_by=None)
    )
    await db.execute(delete(User).where(User.id == user_id))
    await db.flush()
