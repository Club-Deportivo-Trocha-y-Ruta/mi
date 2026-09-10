from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import delete, select, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Annotated

from app.config import settings
from app.dependencies import (
    get_current_user,
    get_db,
    get_notification_service,
    get_task_dispatcher,
    require_role,
)
from app.models.athlete import Athlete, ParentAthlete
from app.models.audit_log import AuditLog
from app.models.club import Club, ClubMember, ClubRole
from app.models.parent_invite import ParentInvite
from app.models.parental_consent import ParentalConsent
from app.models.user import User, UserRole
from app.schemas.notification import (
    NotificationRecipient,
    NotificationRequest,
    NotificationTemplate,
)
from app.schemas.user import UserCreate, UserDeleteIn, UserListOut, UserOut, UserUpdate
from app.services import password_reset as password_reset_service
from app.services.audit import (
    AccountStateReasonCode,
    AuditAction,
    AuditEntityType,
    ParentRemovalReasonCode,
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

# Roles de "personal" (entrenador/administrador) — comparten las reglas de
# alta sin contraseña + club_id obligatorio + correo de fijar contraseña
# (contracts/staff-admin.md §1.2-§1.4).
_STAFF_ROLES: set[UserRole] = {UserRole.coach, UserRole.admin}

# Mapeo total rol de cuenta → rol en club (contracts/staff-admin.md §1.3).
# Debe cubrir los cuatro UserRole: un admin creado con club_id no puede caer
# silenciosamente en ClubRole.parent como hacía el `.get(..., ClubRole.parent)`
# anterior.
_ROLE_IN_CLUB: dict[UserRole, ClubRole] = {
    UserRole.admin: ClubRole.admin,
    UserRole.coach: ClubRole.coach,
    UserRole.parent: ClubRole.parent,
    UserRole.athlete: ClubRole.athlete,
}


def role_in_club_for(role: UserRole) -> ClubRole:
    """Único mapeo rol de cuenta → rol en club (FR-022)."""
    return _ROLE_IN_CLUB[role]


# Motivos válidos para PATCH /api/users/{user_id} (contracts/staff-admin.md
# §4.2): la unión del grupo de estado de cuenta y el de baja de padres, para
# que un coach que desactiva una cuenta de familia tenga un motivo veraz.
_VALID_ACCOUNT_UPDATE_REASONS: set[str] = {
    *AccountStateReasonCode.__members__.values(),
    *ParentRemovalReasonCode.__members__.values(),
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
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    notification_service=Depends(get_notification_service),
) -> User:
    # 1. Validar que el rol que se quiere crear esté permitido para el actor
    allowed = _ALLOWED_CREATIONS.get(current_user.role, set())
    if body.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No tienes permisos para crear usuarios con rol '{body.role}'",
        )

    # 2/3. Coach que crea: debe indicar uno de sus propios clubes.
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

    # 4. club_id obligatorio para el rol de la cuenta creada (personal), sin
    # importar quién la crea (contracts/staff-admin.md §1.2 fila 4) — esto
    # reemplaza, no extiende, la regla 2/3 acotada al llamador: un admin que
    # crea un coach también debe indicar club_id.
    if body.role in _STAFF_ROLES and body.club_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El club es obligatorio para las cuentas de entrenador y administrador",
        )

    # 5. correo obligatorio para personal
    if body.role in _STAFF_ROLES and not body.email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El correo electrónico es obligatorio para las cuentas de entrenador y administrador",
        )

    # 6. la contraseña de personal no se define aquí (FR-023): la persona la
    # fija desde el enlace que recibe por correo.
    if body.role in _STAFF_ROLES and body.password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La contraseña no se define aquí: la persona la crea desde el correo que recibirá",
        )

    # 7. club_id debe existir cuando se proporciona (antes solo se descubría
    # en el flush de la membresía y se reportaba con el mensaje equivocado
    # de "ya es miembro").
    if body.club_id is not None:
        club_result = await db.execute(select(Club).where(Club.id == body.club_id))
        if club_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Club no encontrado",
            )

    # Determinar can_login y hashed_password. Los roles de personal nunca
    # traen password (regla 6); parent/athlete tampoco lo requieren.
    can_login = body.role != UserRole.athlete
    hashed: str | None = None
    if body.password:
        hashed = hash_password(body.password)

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
        meta={"set_password_email": True} if body.role in _STAFF_ROLES else None,
    )

    # 6. Si se proporcionó club_id, crear membresía (role_in_club = rol de la
    # cuenta, mapeo total — contracts/staff-admin.md §1.3).
    if body.club_id is not None:
        membership = ClubMember(
            club_id=body.club_id,
            user_id=new_user.id,
            role_in_club=role_in_club_for(body.role),
            added_by_user_id=current_user.id,
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

    # Correo para fijar contraseña (FR-023, §1.4): solo para personal, vía el
    # flujo existente de password_reset — no se introduce un template nuevo.
    if body.role in _STAFF_ROLES and new_user.email:
        reset_result = await password_reset_service.request_reset(new_user.email, db)
        if reset_result is not None:
            _, reset_url = reset_result
            dispatcher = get_task_dispatcher(background_tasks)
            await notification_service.send(
                NotificationRequest(
                    recipient=NotificationRecipient(
                        email=new_user.email,
                        name=new_user.first_name,
                    ),
                    template=NotificationTemplate.PASSWORD_RESET,
                    context={
                        "reset_url": reset_url,
                        "club_name": settings.club_name,
                        "ttl_minutes": settings.password_reset_token_ttl_minutes,
                    },
                    send_async=True,
                ),
                dispatcher=dispatcher,
            )

    new_user.created_by_display_name = (
        current_user.display_name if current_user else None
    )
    return new_user


# ---------------------------------------------------------------------------
# GET /api/users
# ---------------------------------------------------------------------------
@router.get("", response_model=UserListOut)
async def list_users(
    role: Annotated[list[UserRole] | None, Query()] = None,
    club_id: int | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> UserListOut:
    # Los atletas se gestionan por /api/athletes
    # Construir filtros base
    base_filters = [User.role != UserRole.athlete]

    if role is not None:
        if UserRole.athlete in role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Los atletas se gestionan a través de /api/athletes",
            )
        base_filters.append(User.role.in_(role))

    if is_active is not None:
        base_filters.append(User.is_active == is_active)

    # Orden determinístico (contracts/staff-admin.md §3.3): por rol se evita
    # a propósito, porque UserRole es ENUM (orden de declaración) en MySQL
    # pero VARCHAR (alfabético) en la línea aiosqlite de pruebas.
    order_by = (User.is_active.desc(), User.last_name, User.first_name, User.id)

    if current_user.role == UserRole.admin:
        # Admin: ve todos los usuarios (con filtros opcionales)
        if club_id is not None:
            query = (
                select(User)
                .join(ClubMember, ClubMember.user_id == User.id)
                .where(ClubMember.club_id == club_id, *base_filters)
                .options(
                    selectinload(User.club_memberships),
                    selectinload(User.creator),
                )
                .order_by(*order_by)
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
                .options(
                    selectinload(User.club_memberships),
                    selectinload(User.creator),
                )
                .order_by(*order_by)
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
            .options(
                selectinload(User.club_memberships),
                selectinload(User.creator),
            )
            .distinct()
            .order_by(*order_by)
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

    # Hallazgo F1 (revisión de la fase 5, CWE-284/CWE-639): un coach recibía
    # correo, teléfono y quién creó la cuenta de todo el personal de su club.
    #
    # La corrección que proponía la revisión —negarle al coach la lista de
    # coaches y admins— no se puede aplicar tal cual: la propia feature 041 la
    # necesita. El filtro "Entrenador" del historial (US1,
    # `hooks/governance/useClubStaff.ts`) y el selector de entrenadores a cargo
    # de una sesión (US4, `hooks/training/useClubCoaches.ts`) piden
    # `GET /api/users?role=coach` **como coach**, y la atribución por nombre es
    # justamente de lo que trata la feature.
    #
    # Decisión (corrida nocturna 2, tomada sin supervisión): se conserva la
    # lista y se recorta la carga. Un coach ve de sus colegas lo que un
    # selector necesita —id, nombre, rol, estado— y nada de contacto. US3 AS5
    # habla de no poder crear, editar ni desactivar a otro coach o admin, y de
    # que la pantalla de gestión le sea negada; eso lo siguen garantizando
    # `update_user`, `delete_user` y el portón de `/admin/usuarios`.
    #
    # El recorte se limita a las filas de personal: sobre `role=parent` el
    # coach conserva el contacto completo, porque gestionar a las familias de
    # su club es parte de su trabajo (`api/parents.ts` consume este mismo
    # endpoint). Su propia fila tampoco se recorta.
    redact_staff_contact = current_user.role == UserRole.coach

    def _is_redacted(u: User) -> bool:
        return (
            redact_staff_contact
            and u.id != current_user.id
            and u.role in (UserRole.admin, UserRole.coach)
        )

    items = [
        UserOut(
            id=u.id,
            email=None if _is_redacted(u) else u.email,
            first_name=u.first_name,
            last_name=u.last_name,
            phone=None if _is_redacted(u) else u.phone,
            role=u.role,
            is_active=u.is_active,
            can_login=u.can_login,
            created_at=u.created_at,
            created_by_display_name=(
                None
                if _is_redacted(u)
                else (u.creator.display_name if u.creator else None)
            ),
        )
        for u in users
    ]

    return UserListOut(items=items, total=total)


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

    # Autodesactivación: incondicional para todo llamador
    # (contracts/staff-admin.md §4.2) — antes vivía solo dentro de la rama de
    # coach, así que un admin podía desactivarse a sí mismo y quedar fuera de
    # /admin/usuarios sin que nadie más pudiera reactivarlo.
    if target.id == current_user.id and body.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes desactivarte a ti mismo",
        )

    # Motivo de la acción (§4.2): obligatorio para desactivar, y si viene —
    # para desactivar o para reactivar — debe pertenecer al catálogo de
    # estado de cuenta o de baja de padre (un coach que desactiva una cuenta
    # de familia también necesita un motivo veraz).
    if body.is_active is False and body.reason_code is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Debes indicar el motivo de la desactivación",
        )

    if (
        body.reason_code is not None
        and body.reason_code.value not in _VALID_ACCOUNT_UPDATE_REASONS
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Motivo no válido",
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
        reason_code=body.reason_code,
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
        # Si el atleta ya está archivado, el mapeo cae al fallback
        # `primary_club_id` de la fila de auditoría del unlink — no hay
        # necesidad de resolver el club_id de un atleta archivado aquí.
        athletes_result = await db.execute(
            select(Athlete.id, Athlete.club_id).where(
                Athlete.id.in_(athlete_ids),
                Athlete.deleted_at.is_(None),
            )
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
