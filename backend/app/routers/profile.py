"""Router de perfil / ajustes de cuenta (specs/004-user-profile).

Todas las operaciones actúan sobre el usuario autenticado (``get_current_user``):
no existe parámetro ``{user_id}``, por lo que el acceso a otra cuenta es
estructuralmente imposible. La confirmación de cambio de correo es pública (el
token del enlace es el secreto), como en el flujo de restablecimiento.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import (
    get_current_user,
    get_db,
    get_notification_service,
    get_task_dispatcher,
)
from app.models.user import User
from app.schemas.notification import (
    NotificationRecipient,
    NotificationRequest,
    NotificationTemplate,
)
from app.schemas.profile import (
    EmailChangeConfirm,
    EmailChangeRequestBody,
    PasswordChangeRequest,
    ProfileBasicUpdate,
    ProfileMessage,
    ProfileOut,
)
from app.services import profile as profile_service
from app.services.audit import (
    VALUE_ALLOWLIST,
    AuditAction,
    AuditEntityType,
    compute_changed_fields,
    record_audit,
    snapshot,
)

router = APIRouter()

# Mensaje neutral compartido del cambio de correo (anti-enumeración): idéntico
# exista o no la dirección destino.
_EMAIL_CHANGE_REQUEST_MESSAGE = (
    "Si el correo es válido y está disponible, te enviamos un enlace de "
    "confirmación a la nueva dirección."
)


@router.get("/me", response_model=ProfileOut)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
) -> User:
    """Devuelve el perfil del usuario autenticado."""
    return current_user


@router.patch("/basic", response_model=ProfileOut)
async def update_basic(
    body: ProfileBasicUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    """Actualiza la información básica (nombre, apellido, teléfono).

    Auditoría (feature 041, contracts/audit-recording.md §4.1): fila
    ``user``·``update`` con ``club_id=None`` — permitido por ``CLUB_OPTIONAL``
    (§1.7) por tratarse de una autoedición de perfil. Solo llegan NOMBRES de
    columna: ni ``first_name``, ni ``last_name``, ni ``phone`` están en
    ``VALUE_ALLOWLIST[user]``, así que ``diff_json`` queda vacío. Una edición
    que no cambia nada no escribe fila (regla R7 de §1.4).

    La instantánea previa se toma aquí, en el router, porque
    ``services/profile.py`` pertenece a otro agente en esta oleada; el objeto
    ``current_user`` es el mismo que muta el servicio, de modo que la
    comparación antes/después es exacta.
    """
    audit_fields = ("first_name", "last_name", "phone")
    before = snapshot(current_user, *audit_fields)

    user = await profile_service.update_basic_info(current_user, body, db)

    changed_fields, diff = compute_changed_fields(
        before,
        snapshot(user, *audit_fields),
        VALUE_ALLOWLIST.get(AuditEntityType.user, frozenset()),
    )
    await record_audit(
        db,
        action=AuditAction.update,
        entity_type=AuditEntityType.user,
        entity_id=user.id,
        actor=current_user,
        club_id=None,
        changed_fields=changed_fields,
        diff=diff,
    )
    return user


@router.post("/change-password", response_model=ProfileMessage)
async def change_password(
    body: PasswordChangeRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    notification_service=Depends(get_notification_service),
) -> ProfileMessage:
    """Cambia la contraseña tras re-autenticación; envía correo de confirmación."""
    user = await profile_service.change_password(
        current_user, body.current_password, body.new_password, db
    )

    # Auditoría (feature 041, §4.1): `user`·`update` con `club_id=None`
    # (`CLUB_OPTIONAL`, §1.7). Ni la contraseña actual ni la nueva —ni su
    # hash— entran a la fila: solo el nombre de la columna.
    await record_audit(
        db,
        action=AuditAction.update,
        entity_type=AuditEntityType.user,
        entity_id=user.id,
        actor=current_user,
        club_id=None,
        changed_fields=["hashed_password"],
    )

    if user.email:
        dispatcher = get_task_dispatcher(background_tasks)
        await notification_service.send(
            NotificationRequest(
                recipient=NotificationRecipient(
                    email=user.email,
                    name=user.first_name or "Usuario",
                ),
                template=NotificationTemplate.PASSWORD_CHANGED,
                context={"club_name": settings.club_name},
                send_async=True,
            ),
            dispatcher=dispatcher,
        )

    return ProfileMessage(message="Tu contraseña fue actualizada.")


@router.post("/change-email/request", response_model=ProfileMessage)
async def request_email_change(
    body: EmailChangeRequestBody,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    notification_service=Depends(get_notification_service),
) -> ProfileMessage:
    """Solicita un cambio de correo (verify-new-email-before-apply).

    Responde siempre con el mismo mensaje neutral. El correo de verificación se
    despacha en background a la NUEVA dirección, por lo que el tiempo de
    respuesta no revela si la dirección ya existe (anti-enumeración + timing).
    """
    client_ip = request.client.host if request.client else None
    result = await profile_service.request_email_change(
        current_user, body.current_password, str(body.new_email), db, client_ip
    )

    if result is not None:
        new_email, confirm_url = result
        dispatcher = get_task_dispatcher(background_tasks)
        await notification_service.send(
            NotificationRequest(
                recipient=NotificationRecipient(
                    email=new_email,
                    name=current_user.first_name or "Usuario",
                ),
                template=NotificationTemplate.EMAIL_CHANGE_VERIFY,
                context={
                    "confirm_url": confirm_url,
                    "club_name": settings.club_name,
                    "ttl_minutes": settings.email_change_token_ttl_minutes,
                },
                send_async=True,
            ),
            dispatcher=dispatcher,
        )

    return ProfileMessage(message=_EMAIL_CHANGE_REQUEST_MESSAGE)


@router.post("/change-email/confirm", response_model=ProfileMessage)
async def confirm_email_change(
    body: EmailChangeConfirm,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    notification_service=Depends(get_notification_service),
) -> ProfileMessage:
    """Aplica el cambio de correo con el token del enlace (endpoint público).

    Avisa a la dirección ANTERIOR en background. No emite JWT (sin auto-login).
    """
    user, old_email = await profile_service.confirm_email_change(body.token, db)

    # Auditoría (feature 041, §4.1): `user`·`update` con `changed_fields=
    # ["email"]` — NUNCA la dirección, ni la anterior ni la nueva, ni el token
    # del enlace. `email` no está en `VALUE_ALLOWLIST[user]`, así que aunque
    # se pasara un `diff` el valor se descartaría antes de existir la fila
    # (§1.2, paso 6). Ruta pública: el actor es el propio interesado, resuelto
    # por el handler tras cargar el `User` (§3.2, contexto público).
    await record_audit(
        db,
        action=AuditAction.update,
        entity_type=AuditEntityType.user,
        entity_id=user.id,
        actor=user,
        club_id=None,
        changed_fields=["email"],
    )

    if old_email:
        dispatcher = get_task_dispatcher(background_tasks)
        await notification_service.send(
            NotificationRequest(
                recipient=NotificationRecipient(
                    email=old_email,
                    name=user.first_name or "Usuario",
                ),
                template=NotificationTemplate.EMAIL_CHANGED_NOTICE,
                context={"club_name": settings.club_name},
                send_async=True,
            ),
            dispatcher=dispatcher,
        )

    return ProfileMessage(
        message="Tu correo fue actualizado. Inicia sesión con tu nueva dirección."
    )
