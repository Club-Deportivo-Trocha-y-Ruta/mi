from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_current_user, get_db, require_role
from app.models.athlete import Athlete, ParentAthlete
from app.models.audit_log import AuditLog
from app.models.club import ClubMember, ClubRole
from app.models.parent_invite import ParentInvite
from app.models.parental_consent import ParentalConsent
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserDeleteIn, UserListOut, UserOut, UserUpdate
from app.services.audit import (
    AuditAction,
    AuditEntityType,
    VALUE_ALLOWLIST,
    compute_changed_fields,
    record_audit,
    snapshot,
)
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


async def _has_recorded_activity(db: AsyncSession, user_id: int) -> bool:
    """Sondas de actividad de una cuenta (feature 041, T046, §8.1).

    Regla 6 de `DELETE /api/users/{user_id}`: role-agnóstica — protege tanto
    cuentas de personal como de padres. Tres existencias indexadas, no un
    escaneo cruzado:

    1. `audit_log.actor_user_id` — cualquier acción registrada post-041.
    2. `users.created_by` — atribución pre-041 (columna legada corta).
    3. `parental_consents.parent_user_id` — evidencia de consentimiento
       Ley 1581 pre-041.
    """
    audit_probe = await db.execute(
        select(AuditLog.id).where(AuditLog.actor_user_id == user_id).limit(1)
    )
    if audit_probe.first() is not None:
        return True

    created_probe = await db.execute(
        select(User.id).where(User.created_by == user_id).limit(1)
    )
    if created_probe.first() is not None:
        return True

    consent_probe = await db.execute(
        select(ParentalConsent.id)
        .where(ParentalConsent.parent_user_id == user_id)
        .limit(1)
    )
    return consent_probe.first() is not None


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

    # Auditoría (feature 041, contracts/audit-recording.md §4.2): una fila
    # `user`·`create` por cada alta, compartiendo `request_id` con la fila de
    # `club_member`·`create` que sigue si hubo club_id.
    await record_audit(
        db,
        action=AuditAction.create,
        entity_type=AuditEntityType.user,
        entity_id=new_user.id,
        actor=current_user,
        club_id=body.club_id,
        changed_fields=["email", "first_name", "last_name", "phone", "role", "can_login"],
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

        await record_audit(
            db,
            action=AuditAction.create,
            entity_type=AuditEntityType.club_member,
            entity_id=membership.id,
            actor=current_user,
            club_id=body.club_id,
            changed_fields=["club_id", "user_id", "role_in_club"],
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

    # Auditoría (feature 041, contracts/audit-recording.md §4.2): snapshot
    # ANTES de mutar — solo los campos allow-listados para diff_json llegan
    # a `diff`, `changed_fields` lista todos los que de verdad cambiaron.
    audit_fields = ("first_name", "last_name", "phone", "is_active")
    before = snapshot(target, *audit_fields)

    # Aplicar solo los campos provistos. `reason_code` nunca es un atributo
    # de `User` — viaja solo hacia `record_audit` (contracts/audit-recording.md
    # §4.2 / contracts/staff-admin.md §4.1).
    update_data = body.model_dump(exclude_none=True, exclude={"reason_code"})
    for field, value in update_data.items():
        setattr(target, field, value)

    after = snapshot(target, *audit_fields)
    changed_fields, diff = compute_changed_fields(
        before, after, VALUE_ALLOWLIST.get(AuditEntityType.user, frozenset())
    )

    action = AuditAction.update
    if "is_active" in changed_fields:
        if before["is_active"] is True and after["is_active"] is False:
            action = AuditAction.deactivate
        elif before["is_active"] is False and after["is_active"] is True:
            action = AuditAction.activate

    if action == AuditAction.deactivate and body.reason_code is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Debes seleccionar un motivo para esta acción.",
        )

    target_club_id = (
        target.club_memberships[0].club_id if target.club_memberships else None
    )

    await record_audit(
        db,
        action=action,
        entity_type=AuditEntityType.user,
        entity_id=target.id,
        actor=current_user,
        club_id=target_club_id,
        changed_fields=changed_fields,
        diff=diff,
        reason_code=body.reason_code if action == AuditAction.deactivate else None,
    )

    await db.flush()

    return target


# ---------------------------------------------------------------------------
# DELETE /api/users/{user_id} — eliminar padre/acudiente
# ---------------------------------------------------------------------------
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    body: UserDeleteIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> None:
    """Elimina un padre/acudiente y limpia sus vínculos.

    Coach: solo puede borrar padres de sus clubes.
    No se permite borrar admin/coach por este endpoint, ni autoborrado.
    Atletas se gestionan vía DELETE /api/athletes/{id}.

    Se rechaza (409) cuando la cuenta tiene actividad registrada (feature 041,
    T046, contracts/athlete-archive.md §8): desactivar en su lugar preserva la
    atribución (`users.created_by`) y la evidencia de consentimiento
    (Ley 1581) en vez de destruirlas.
    """
    reason_code = body.reason_code

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

    # Regla 4 (§8, evaluada antes que la regla 5): un coach no puede ni
    # siquiera sondear actividad de un usuario fuera de sus clubes.
    if current_user.role == UserRole.coach:
        coach_clubs = _coach_club_ids(current_user)
        target_clubs = {m.club_id for m in target.club_memberships}
        if not coach_clubs.intersection(target_clubs):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Este usuario no pertenece a ninguno de tus clubes",
            )

    # Regla 5 (§8, contracts/staff-admin.md §5): incondicional para todo
    # llamador, no solo para coach.
    if target.role in (UserRole.admin, UserRole.coach):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes eliminar usuarios con rol admin o coach",
        )

    # Regla 6 (§8.1): la cuenta con actividad registrada no se elimina, se
    # desactiva. Rol-agnóstica — protege también a un padre con consentimiento
    # otorgado, RSVP o lectura de bitácora.
    if await _has_recorded_activity(db, user_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Este usuario tiene actividad registrada y no se puede eliminar. "
                "Desactívalo para impedir que inicie sesión; su nombre seguirá "
                "visible en el historial."
            ),
        )

    # Capturar, ANTES de borrar, lo que la cascada va a eliminar — se necesita
    # para escribir una fila de auditoría por cada registro removido
    # (contracts/audit-recording.md §4.2). Las sondas de §8.1 ya descartaron
    # que existan `parental_consents` para este usuario (regla 7, §8.2): esa
    # tabla ya no participa en esta cascada.
    links_result = await db.execute(
        select(ParentAthlete).where(ParentAthlete.parent_id == user_id)
    )
    links = list(links_result.scalars().all())

    members_result = await db.execute(
        select(ClubMember).where(ClubMember.user_id == user_id)
    )
    club_members = list(members_result.scalars().all())

    # club_id del usuario eliminado, para la fila `user`·`delete` (primera
    # membresía, o None si es un usuario club-less).
    primary_club_id = club_members[0].club_id if club_members else None

    # club_id de cada atleta involucrado, para las filas `parent_athlete`
    # (escalera de resolución §1.6 paso 2).
    athlete_ids = {link.athlete_id for link in links}
    athlete_club_map: dict[int, int] = {}
    if athlete_ids:
        athletes_result = await db.execute(
            select(Athlete.id, Athlete.club_id).where(Athlete.id.in_(athlete_ids))
        )
        athlete_club_map = dict(athletes_result.all())

    # Cascada manual: limpiar referencias antes de eliminar el user.
    await db.execute(delete(ParentAthlete).where(ParentAthlete.parent_id == user_id))
    await db.execute(delete(ClubMember).where(ClubMember.user_id == user_id))
    await db.execute(
        update(ParentInvite).where(ParentInvite.used_by == user_id).values(used_by=None)
    )
    # parent_user_id apunta al padre pre-creado que aún no aceptó la invitación
    await db.execute(
        update(ParentInvite).where(ParentInvite.parent_user_id == user_id).values(parent_user_id=None)
    )
    # NOTA (feature 041, contracts/audit-recording.md §10, defecto preexistente
    # corregido): NO se anula `created_by` de lo que este usuario creó —
    # borrar un padre no debe borrar la autoría de sus registros. La regla 6
    # ya refuerza esto: un usuario que sí creó algo tiene actividad registrada
    # (probe 2, §8.1) y este punto del código es inalcanzable para él.
    try:
        await db.execute(delete(User).where(User.id == user_id))
        await db.flush()
    except IntegrityError:
        # RESTRICT FK preexistente (`training_sessions.created_by_user_id`,
        # `race_results.created_by_user_id`, §8.1) para actividad anterior a
        # 041 que ninguna de las tres sondas cubre.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Este usuario tiene actividad registrada y no se puede eliminar. "
                "Desactívalo para impedir que inicie sesión; su nombre seguirá "
                "visible en el historial."
            ),
        )

    for link in links:
        await record_audit(
            db,
            action=AuditAction.unlink,
            entity_type=AuditEntityType.parent_athlete,
            entity_id=link.id,
            actor=current_user,
            club_id=athlete_club_map.get(link.athlete_id, primary_club_id),
            athlete_id=link.athlete_id,
            changed_fields=["parent_id", "athlete_id"],
        )

    for member in club_members:
        await record_audit(
            db,
            action=AuditAction.delete,
            entity_type=AuditEntityType.club_member,
            entity_id=member.id,
            actor=current_user,
            club_id=member.club_id,
            changed_fields=["club_id", "user_id", "role_in_club"],
        )

    await record_audit(
        db,
        action=AuditAction.delete,
        entity_type=AuditEntityType.user,
        entity_id=user_id,
        actor=current_user,
        club_id=primary_club_id,
        changed_fields=["role", "is_active"],
        reason_code=reason_code,
    )
