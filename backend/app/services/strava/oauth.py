"""Strava OAuth flow: authorize URL, signed ``state``, token exchange/refresh
(specs/025-strava-activity-sync T013).

Inputs: ``build_authorize_url``/``sign_state`` take the platform
``athlete_id`` and the ``user_id`` of whoever runs the connect flow
(parent/coach/admin, FR-001); ``verify_state`` takes the opaque ``state``
string returned by Strava on the OAuth callback; ``exchange_code`` takes the
one-time authorization ``code``; ``refresh_access_token`` takes a stored
(decrypted) refresh token.
Outputs: ``build_authorize_url`` returns the full Strava authorize URL;
``verify_state`` returns ``{"athlete_id": int, "user_id": int}``;
``exchange_code``/``refresh_access_token`` return Strava's raw token response
dict (``access_token``, ``refresh_token``, ``expires_at``, ``expires_in``,
``token_type``, and — only on ``exchange_code`` — an ``athlete`` summary).
Side effects: ``exchange_code``/``refresh_access_token`` perform outbound
HTTPS calls to ``settings.strava_oauth_base_url``; nothing is persisted here
(callers own encryption via ``token_store`` and DB writes).

Privacy (Ley 1581 minors): this module NEVER logs a ``code``, an access
token, or a refresh token — only outcomes (status codes) with no PII. State
tokens carry only numeric ids and a random nonce, never athlete names.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from app.config import settings

logger = logging.getLogger(__name__)

# Reuses the platform's existing JWT signing key/algorithm (services/auth.py)
# rather than introducing a second secret — see research.md §4. A dedicated
# "type" claim keeps this token from being accepted anywhere access/refresh
# tokens are, and vice versa.
_STATE_TOKEN_TYPE = "strava_oauth_state"
STATE_TTL_MINUTES = 15

# CLAUDE.md convention: never call httpx.AsyncClient() without an explicit
# timeout. Strava's OAuth token endpoint has no documented long-tail latency
# (unlike Gemini), so the default 30 s budget applies.
_REQUEST_TIMEOUT_S = 30.0

_SCOPE = "activity:read_all"


class StravaOAuthError(RuntimeError):
    """Raised when Strava rejects a token exchange/refresh, or is unreachable."""


class InvalidStateError(StravaOAuthError):
    """Raised when the OAuth ``state`` parameter fails verification.

    Covers a bad/forged signature, wrong token type, expiry, or a malformed
    payload. Callers (the OAuth callback router) MUST map this to HTTP 400
    per contracts/api.md §A.
    """


def sign_state(athlete_id: int, user_id: int) -> str:
    """Build a signed, short-lived ``state`` token for one connect attempt.

    Binds ``athlete_id`` and ``user_id`` (the initiating platform user) plus
    a random ``nonce`` into a JWT signed with ``settings.jwt_secret_key``,
    expiring after ``STATE_TTL_MINUTES`` minutes. The nonce guards against
    trivial replay; the short TTL bounds the window an intercepted state
    value could be reused in.
    """
    payload: dict[str, Any] = {
        "athlete_id": athlete_id,
        "user_id": user_id,
        "nonce": secrets.token_urlsafe(16),
        "type": _STATE_TOKEN_TYPE,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=STATE_TTL_MINUTES),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_state(state: str) -> dict[str, int]:
    """Verify and decode a ``state`` token produced by ``sign_state``.

    Returns ``{"athlete_id": ..., "user_id": ...}`` on success.

    Raises ``InvalidStateError`` on bad/forged signature, expiry, wrong
    token ``type``, or a payload missing/mistyped ``athlete_id``/``user_id``.
    Never logs the raw ``state`` value.
    """
    try:
        payload = jwt.decode(
            state, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise InvalidStateError("El enlace de conexión con Strava expiró o no es válido.") from exc

    if payload.get("type") != _STATE_TOKEN_TYPE:
        raise InvalidStateError("El enlace de conexión con Strava no es válido.")

    try:
        return {
            "athlete_id": int(payload["athlete_id"]),
            "user_id": int(payload["user_id"]),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidStateError("El enlace de conexión con Strava no es válido.") from exc


def build_authorize_url(athlete_id: int, user_id: int) -> str:
    """Build the Strava authorize URL to start connecting ``athlete_id``.

    ``user_id`` is the platform user running the connect flow (parent,
    coach, or admin — FR-001) and travels inside the signed ``state`` so the
    callback cannot be replayed to bind a different athlete or attributed to
    a different user. Scope is fixed to ``activity:read_all`` — plain
    ``activity:read`` cannot read private activities and would silently drop
    most rides (research.md §4; families are advised to keep activities
    private/followers-only on Strava, privacy is enforced on our side by
    never persisting GPS/location fields).
    """
    state = sign_state(athlete_id, user_id)
    params = {
        "client_id": settings.strava_client_id,
        "redirect_uri": settings.strava_redirect_uri,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": _SCOPE,
        "state": state,
    }
    return f"{settings.strava_oauth_base_url}/authorize?{urlencode(params)}"


async def _post_token_request(payload: dict[str, str], *, action: str) -> dict[str, Any]:
    """Shared POST to Strava's token endpoint for exchange/refresh.

    ``action`` is a log-safe label ("exchange" | "refresh") — never includes
    the code/token values themselves.
    """
    url = f"{settings.strava_oauth_base_url}/token"
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_S) as client:
            response = await client.post(url, data=payload)
    except httpx.HTTPError as exc:
        logger.warning("strava_oauth_%s_network_error", action)
        raise StravaOAuthError(
            "No se pudo contactar a Strava. Intenta de nuevo en unos minutos."
        ) from exc

    if response.status_code >= 400:
        logger.warning(
            "strava_oauth_%s_rejected",
            action,
            extra={"status_code": response.status_code},
        )
        raise StravaOAuthError(
            f"Strava rechazó la solicitud de {action} de token "
            f"(status {response.status_code})."
        )

    return response.json()


async def exchange_code(code: str) -> dict[str, Any]:
    """Exchange an OAuth authorization ``code`` for tokens.

    ``POST {strava_oauth_base_url}/token`` with
    ``grant_type=authorization_code``. Returns Strava's raw response dict —
    ``access_token``, ``refresh_token``, ``expires_at`` (epoch seconds),
    ``expires_in``, ``token_type``, and an ``athlete`` summary whose ``id``
    is the ``strava_athlete_id`` callers must store.

    Raises ``StravaOAuthError`` on a non-2xx response or network failure.
    Never logs ``code`` or any token value.
    """
    payload = {
        "client_id": settings.strava_client_id,
        "client_secret": settings.strava_client_secret,
        "code": code,
        "grant_type": "authorization_code",
    }
    return await _post_token_request(payload, action="exchange")


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    """Refresh an expired/expiring access token.

    ``POST {strava_oauth_base_url}/token`` with ``grant_type=refresh_token``.
    Strava **rotates refresh tokens on every use** — the response's
    ``refresh_token`` field is the newest valid one and callers MUST persist
    it in place of the old value (never assume the previous refresh token
    remains usable).

    Raises ``StravaOAuthError`` on a non-2xx response (e.g. a revoked or
    expired refresh token — callers should map this to marking the
    connection ``broken``, per data-model.md §1 state transitions) or
    network failure. Never logs the refresh token value.
    """
    payload = {
        "client_id": settings.strava_client_id,
        "client_secret": settings.strava_client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    return await _post_token_request(payload, action="refresh")
