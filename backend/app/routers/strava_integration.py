"""Router for Strava OAuth connection + machine endpoints (feature 025).

Registered in ``app/main.py`` with prefix ``/api`` and tag
``strava-integration``, guarded so it is only included when
``settings.strava_enabled`` is true.

Route inventory (contract: specs/025-strava-activity-sync/contracts/api.md
§A/§B):

  GET    /api/athletes/{athlete_id}/strava/connection    — connection status
  POST   /api/athletes/{athlete_id}/strava/connect        — start OAuth
  GET    /api/integrations/strava/callback                 — OAuth callback (public)
  DELETE /api/athletes/{athlete_id}/strava/connection      — family disconnect
  GET    /api/integrations/strava/webhook                  — subscription validation (public)
  POST   /api/integrations/strava/webhook                  — event delivery (public)
  POST   /api/integrations/strava/reconcile                — daily catch-up (shared-secret)

RBAC (§A): ``GET``/``POST``/``DELETE`` on ``/athletes/{athlete_id}/strava/*``
reuse ``app.dependencies.verify_athlete_access`` (admin always; coach only
for the athlete's own club; parent only for their own linked child) — the
exact scope the contract specifies. The OAuth callback, webhook, and
reconcile endpoints are machine-facing and unauthenticated by nature; they
are protected instead by a signed ``state`` token, a webhook
``verify_token``, and a shared-secret header, respectively (never by JWT).

Privacy (Ley 1581, minors — FR-016): this module logs numeric identifiers
only (``athlete_id``, ``strava_activity_id``/``object_id``) — never athlete
names, activity titles, emails, or token contents. OAuth ``code``/token
values are never logged (see ``services/strava/oauth.py``/``token_store.py``
for the same rule applied deeper in the stack).
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Header, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.dependencies import get_current_user, get_db, get_task_dispatcher, verify_athlete_access
from app.models.athlete import Athlete
from app.models.strava_connection import StravaConnection, StravaConnectionStatus
from app.models.user import User
from app.schemas.strava import (
    AuthorizeUrlOut,
    ConnectionStatusOut,
    ReconcileResultOut,
    StravaWebhookEvent,
)
from app.services.notification.task_dispatcher import TaskDispatcher
from app.services.strava import oauth
from app.services.strava.client import StravaClient
from app.services.strava.ingest import process_webhook_event
from app.services.strava.reconcile import reconcile_all
from app.services.strava.token_store import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["strava-integration"])


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------


def _frontend_redirect(athlete_id: int, **params: str) -> RedirectResponse:
    """302 al perfil del atleta en el frontend con ``params`` como querystring.

    Nunca incluye tokens ni datos del atleta más allá del ``athlete_id``
    numérico ya presente en la ruta.
    """
    base = settings.frontend_base_url.rstrip("/")
    query = urlencode(params)
    url = f"{base}/athletes/{athlete_id}?{query}"
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


# ---------------------------------------------------------------------------
# A. Connection management
# ---------------------------------------------------------------------------


@router.get(
    "/athletes/{athlete_id}/strava/connection",
    response_model=ConnectionStatusOut,
)
async def get_strava_connection(
    athlete: Athlete = Depends(verify_athlete_access),
    db: AsyncSession = Depends(get_db),
) -> ConnectionStatusOut:
    """Estado actual de la conexión Strava del atleta (o ``none`` si nunca
    se conectó).
    """
    result = await db.execute(
        select(StravaConnection)
        .where(StravaConnection.athlete_id == athlete.id)
        .options(selectinload(StravaConnection.authorized_by))
    )
    connection = result.scalar_one_or_none()

    if connection is None:
        return ConnectionStatusOut(status="none")

    authorized_by = None
    if connection.authorized_by is not None:
        authorized_by = (
            f"{connection.authorized_by.first_name} {connection.authorized_by.last_name}".strip()
        )

    return ConnectionStatusOut(
        status=connection.status.value,
        connected_at=connection.connected_at,
        disconnected_at=connection.disconnected_at,
        authorized_by=authorized_by,
        last_sync_at=connection.last_sync_at,
    )


@router.post(
    "/athletes/{athlete_id}/strava/connect",
    response_model=AuthorizeUrlOut,
)
async def start_strava_connect(
    athlete: Athlete = Depends(verify_athlete_access),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuthorizeUrlOut:
    """Inicia el flujo OAuth: retorna la URL de autorización de Strava.

    El acto de autorizar la conexión OAuth de Strava ES el consentimiento
    afirmativo — no se exige una fila de consentimiento previa. El rastro de
    auditoría (quién autorizó + cuándo) queda registrado en
    ``strava_connections`` (``authorized_by_user_id`` + ``connected_at``).

    Guards (contracts/api.md §A): solo RBAC (admin, coach del club del atleta,
    o acudiente del atleta — vía ``verify_athlete_access``) e interruptor
    maestro deshabilitado → 503.
    """
    if not settings.strava_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La sincronización con Strava no está disponible en este momento.",
        )

    authorize_url = oauth.build_authorize_url(athlete.id, current_user.id)
    return AuthorizeUrlOut(authorize_url=authorize_url)


@router.delete(
    "/athletes/{athlete_id}/strava/connection",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def disconnect_strava(
    athlete: Athlete = Depends(verify_athlete_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Desconexión iniciada por la familia/coach/admin (FR-014).

    Revoca el acceso del lado de Strava como cortesía (``best-effort`` — un
    fallo se loggea y se ignora, ver ``StravaClient.deauthorize``); el
    estado local SIEMPRE pasa a ``disconnected`` sin importar el resultado
    upstream. Las actividades ya sincronizadas se conservan.
    """
    result = await db.execute(
        select(StravaConnection).where(StravaConnection.athlete_id == athlete.id)
    )
    connection = result.scalar_one_or_none()
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El atleta no tiene una conexión con Strava.",
        )

    if connection.status == StravaConnectionStatus.active:
        access_token = decrypt_token(connection.access_token_enc)
        async with StravaClient(connection, db) as client:
            await client.deauthorize(access_token)

    connection.status = StravaConnectionStatus.disconnected
    connection.disconnected_at = datetime.now(timezone.utc)
    await db.flush()

    logger.info(
        "strava_connection_disconnected",
        extra={"athlete_id": athlete.id},
    )


# ---------------------------------------------------------------------------
# A. OAuth callback (público — destino de redirect de Strava)
# ---------------------------------------------------------------------------


@router.get("/integrations/strava/callback", include_in_schema=False)
async def strava_oauth_callback(
    state: str = Query(...),
    code: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Destino de retorno de Strava tras la autorización (público).

    Orden de validación (contracts/api.md §A): ``state`` (firma + TTL) → 400
    si inválido; denegación/errores de Strava y de scope → redirect con
    ``error=...``; éxito → 302 a ``/athletes/{id}?strava=conectado``.
    Nunca loggea ``code``, tokens, ni el valor crudo de ``state``.
    """
    try:
        claims = oauth.verify_state(state)
    except oauth.InvalidStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    athlete_id = claims["athlete_id"]
    user_id = claims["user_id"]

    if error:
        logger.info(
            "strava_oauth_callback_denied",
            extra={"athlete_id": athlete_id},
        )
        return _frontend_redirect(athlete_id, error="denegado")

    if not code:
        logger.warning(
            "strava_oauth_callback_missing_code",
            extra={"athlete_id": athlete_id},
        )
        return _frontend_redirect(athlete_id, error="codigo_faltante")

    granted_scopes = {s.strip() for s in (scope or "").split(",") if s.strip()}
    if "activity:read_all" not in granted_scopes:
        logger.info(
            "strava_oauth_callback_scope_downgrade",
            extra={"athlete_id": athlete_id},
        )
        return _frontend_redirect(athlete_id, error="scope")

    try:
        token_response = await oauth.exchange_code(code)
    except oauth.StravaOAuthError:
        logger.warning(
            "strava_oauth_callback_exchange_failed",
            extra={"athlete_id": athlete_id},
        )
        return _frontend_redirect(athlete_id, error="intercambio")

    strava_athlete_id = (token_response.get("athlete") or {}).get("id")
    expires_at_epoch = token_response.get("expires_at")
    access_token = token_response.get("access_token")
    refresh_token = token_response.get("refresh_token")
    if strava_athlete_id is None or not access_token or not refresh_token:
        logger.warning(
            "strava_oauth_callback_malformed_token_response",
            extra={"athlete_id": athlete_id},
        )
        return _frontend_redirect(athlete_id, error="intercambio")

    # Conflicto: esa cuenta de Strava ya está enlazada a OTRO atleta
    # (data-model.md §1 — primer bind gana).
    existing_by_strava_id = await db.scalar(
        select(StravaConnection).where(
            StravaConnection.strava_athlete_id == strava_athlete_id
        )
    )
    if existing_by_strava_id is not None and existing_by_strava_id.athlete_id != athlete_id:
        logger.warning(
            "strava_oauth_callback_account_conflict",
            extra={"athlete_id": athlete_id},
        )
        return _frontend_redirect(athlete_id, error="cuenta_en_uso")

    existing_by_athlete = await db.scalar(
        select(StravaConnection).where(StravaConnection.athlete_id == athlete_id)
    )
    connection = existing_by_athlete or existing_by_strava_id
    if connection is None:
        connection = StravaConnection(athlete_id=athlete_id)
        db.add(connection)

    now = datetime.now(timezone.utc)
    token_expires_at = (
        datetime.fromtimestamp(expires_at_epoch, tz=timezone.utc)
        if expires_at_epoch is not None
        else now
    )

    connection.athlete_id = athlete_id
    connection.strava_athlete_id = strava_athlete_id
    connection.status = StravaConnectionStatus.active
    connection.access_token_enc = encrypt_token(access_token)
    connection.refresh_token_enc = encrypt_token(refresh_token)
    connection.token_expires_at = token_expires_at
    connection.scope_granted = scope or ""
    connection.authorized_by_user_id = user_id
    connection.connected_at = now
    connection.disconnected_at = None
    connection.last_error = None

    await db.flush()
    logger.info(
        "strava_connection_established",
        extra={"athlete_id": athlete_id},
    )

    return _frontend_redirect(athlete_id, strava="conectado")


# ---------------------------------------------------------------------------
# B. Machine endpoints — webhook (público) + reconcile (secreto compartido)
# ---------------------------------------------------------------------------


@router.get("/integrations/strava/webhook", include_in_schema=False)
async def validate_strava_webhook(
    hub_challenge: str = Query(alias="hub.challenge"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
) -> dict[str, str]:
    """Validación de suscripción del webhook de Strava.

    Comparación constant-time del ``verify_token``; SIN trabajo de DB para
    cumplir el límite de 2 segundos de Strava. ``hub_mode`` se recibe pero
    no se valida (Strava solo envía ``"subscribe"`` en este flujo).
    """
    del hub_mode
    # Fail-closed: un verify_token sin configurar ("") jamás debe autorizar por
    # coincidencia "" == "" si el header/query llega vacío (no depende de que
    # APP_ENV sea exactamente "production").
    if not settings.strava_webhook_verify_token or not secrets.compare_digest(
        hub_verify_token, settings.strava_webhook_verify_token
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token de verificación de webhook inválido.",
        )
    return {"hub.challenge": hub_challenge}


async def _process_webhook_event_deferred(event: StravaWebhookEvent) -> None:
    """Procesamiento diferido de un evento de webhook (ejecuta DESPUÉS del
    ACK ``200 {}``).

    Abre su propia ``AsyncSessionLocal`` — la sesión de la request ya no es
    segura de reutilizar una vez que corren las ``BackgroundTasks`` (mismo
    patrón que ``routers/athlete_race_analysis.py::_on_complete``). Cualquier
    excepción se loggea y se traga: un evento problemático nunca debe
    escalar hacia Strava (que ya recibió su 200).
    """
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            await process_webhook_event(event, session)
            await session.commit()
        except Exception:  # noqa: BLE001
            await session.rollback()
            logger.exception(
                "strava_webhook_deferred_processing_failed",
                extra={
                    "object_type": event.object_type,
                    "aspect_type": event.aspect_type,
                    "object_id": event.object_id,
                    "owner_id": event.owner_id,
                },
            )


@router.post(
    "/integrations/strava/webhook",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def receive_strava_webhook_event(
    event: StravaWebhookEvent,
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),
) -> dict:
    """Entrega de eventos del webhook de Strava.

    Responde ``200 {}`` de inmediato (regla de 2 segundos de Strava) y
    difiere TODO el procesamiento (fetch de actividad, upsert, cambios de
    estado de conexión) a ``BackgroundTasks`` vía ``TaskDispatcher``.
    Entregas duplicadas/repetidas son un no-op (idempotencia en
    ``services/strava/ingest.py``).
    """
    # Defensa en profundidad contra eventos falsificados: Strava no firma el body,
    # así que si conocemos el subscription_id real, descartamos (no-op, pero igual
    # ACK 200) cualquier evento cuyo subscription_id no coincida. Evita que un
    # tercero que adivine un `owner_id` fuerce desconexiones o queme el rate-limit
    # compartido de la app. Vacío en config = suscripción aún no creada → no validar.
    expected_sub = settings.strava_subscription_id
    if expected_sub and str(event.subscription_id) != str(expected_sub):
        logger.warning(
            "strava_webhook_subscription_mismatch",
            extra={"subscription_id": event.subscription_id},
        )
        return {}
    dispatcher.dispatch(_process_webhook_event_deferred, event)
    return {}


@router.post(
    "/integrations/strava/reconcile",
    response_model=ReconcileResultOut,
)
async def run_strava_reconcile(
    x_reconcile_token: str = Header(default="", alias="X-Reconcile-Token"),
    db: AsyncSession = Depends(get_db),
) -> ReconcileResultOut:
    """Catch-up diario disparado por el workflow de GitHub Actions
    (contracts/api.md §E). Protegido por secreto compartido comparado en
    tiempo constante — nunca por JWT (llamador es una máquina, no un
    usuario logueado).
    """
    # Fail-closed: un reconcile_token sin configurar ("") jamás debe autorizar por
    # coincidencia "" == "" con un header ausente.
    if not settings.strava_reconcile_token or not secrets.compare_digest(
        x_reconcile_token, settings.strava_reconcile_token
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token de reconciliación inválido.",
        )

    result = await reconcile_all(db)
    return ReconcileResultOut(**result)
