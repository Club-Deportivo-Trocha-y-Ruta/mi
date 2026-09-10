"""Request/job correlation context (feature 041, contracts/audit-recording.md §3).

Owns the process-wide ``request_id`` ``ContextVar``, the ``AuditContext``
dataclass threaded through service signatures as the audit actor, and the
helpers non-HTTP callers (CLI scripts, cron jobs, webhooks) use to bind a
``request_id`` for the duration of their unit of work.

The actor itself is **never** read back out of the ContextVar — only the
``request_id`` is contextual. ``AuditContext.actor`` travels explicitly as a
parameter so misattribution (Acceptance Scenario 4, spec.md:26) is impossible
even when a background task runs after the request that triggered it has
already returned.
"""
from __future__ import annotations

import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterator

from fastapi import Depends
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.dependencies import get_current_user
from app.models.audit_log import AuditActorKind

if TYPE_CHECKING:
    from app.models.user import User, UserRole

_REQUEST_ID_RE = re.compile(r"^[0-9a-f]{32}$")

_request_id: ContextVar[str | None] = ContextVar("audit_request_id", default=None)


def new_request_id() -> str:
    """A fresh 32-char hex correlation id (``data-model.md`` §1)."""
    return uuid.uuid4().hex


def current_request_id() -> str | None:
    """The bound ``request_id``, or ``None`` outside any scope."""
    return _request_id.get()


@contextmanager
def request_id_scope(value: str | None = None) -> Iterator[str]:
    """Bind a ``request_id`` for a non-HTTP unit of work.

    Used by the CLI, cron jobs, webhooks and detached callbacks (§3.3) that
    have no ``RequestIdMiddleware`` binding one for them. Always resets the
    ContextVar token on exit, including on exception.
    """
    request_id = value or new_request_id()
    token: Token[str | None] = _request_id.set(request_id)
    try:
        yield request_id
    finally:
        _request_id.reset(token)


class RequestIdMiddleware:
    """Pure ASGI middleware (Starlette) — not ``BaseHTTPMiddleware``.

    ``BaseHTTPMiddleware`` re-wraps every response in a ``StreamingResponse``,
    which this feature must not do to byte responses from WeasyPrint/docxtpl
    (§4.13, research R-05). Registered as the **outermost** middleware in
    ``app.main`` (after ``CORSMiddleware``) so the id exists even for
    CORS-rejected and 500 responses.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        inbound = _inbound_request_id(scope)
        request_id = inbound or new_request_id()
        token = _request_id.set(request_id)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _request_id.reset(token)


_MACHINE_ENDPOINT_PATHS = {
    "/api/webhooks/resend",
    "/api/integrations/strava/reconcile",
}


def _inbound_request_id(scope: Scope) -> str | None:
    """Honour an inbound ``X-Request-Id`` only for the two machine endpoints
    (§3.1) and only when it matches the 32-char hex shape — a browser must
    not be able to choose its own correlation id.
    """
    path = scope.get("path", "")
    if path not in _MACHINE_ENDPOINT_PATHS:
        return None

    raw_headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
    for name, value in raw_headers:
        if name.lower() == b"x-request-id":
            candidate = value.decode("latin-1")
            if _REQUEST_ID_RE.match(candidate):
                return candidate
            return None
    return None


@dataclass(frozen=True, slots=True)
class AuditContext:
    """The audit actor for one unit of work, threaded through service calls
    as an explicit parameter (§3.2) — never resolved from the ContextVar.
    """

    request_id: str
    actor: "User | None"
    actor_kind: AuditActorKind
    actor_role: "UserRole | None"

    @classmethod
    def for_user(cls, user: "User", request_id: str | None = None) -> "AuditContext":
        return cls(
            request_id=request_id or current_request_id() or new_request_id(),
            actor=user,
            actor_kind=AuditActorKind.user,
            actor_role=user.role,
        )

    @classmethod
    def for_job(
        cls,
        kind: AuditActorKind,
        job: str,
        request_id: str | None = None,
    ) -> "AuditContext":
        if kind == AuditActorKind.user:
            raise ValueError("AuditContext.for_job requires system/webhook/cron, got 'user'")
        return cls(
            request_id=request_id or current_request_id() or new_request_id(),
            actor=None,
            actor_kind=kind,
            actor_role=None,
        )


def system_context(*, job: str, request_id: str | None = None) -> AuditContext:
    """Convenience wrapper for ``actor_kind=system`` non-HTTP callers
    (start-up reconciliation, LangGraph completion callbacks, seed/backfill
    scripts, run-by-hand retention purge — §3.3).
    """
    return AuditContext.for_job(AuditActorKind.system, job, request_id=request_id)


def webhook_context(*, job: str, request_id: str | None = None) -> AuditContext:
    """Convenience wrapper for ``actor_kind=webhook`` callers (Resend
    delivery webhook, Strava webhook deferred worker — §3.3).
    """
    return AuditContext.for_job(AuditActorKind.webhook, job, request_id=request_id)


def cron_context(*, job: str, request_id: str | None = None) -> AuditContext:
    """Convenience wrapper for ``actor_kind=cron`` callers (daily Strava
    reconcile, scheduled retention purge — §3.3).
    """
    return AuditContext.for_job(AuditActorKind.cron, job, request_id=request_id)


async def get_request_context(
    current_user: "User" = Depends(get_current_user),
) -> AuditContext:
    """Dependency for every authenticated mutating endpoint (§3.2).

    The ``request_id`` is bound by ``RequestIdMiddleware`` for every real
    request; the ``current_request_id() or new_request_id()`` fallback only
    matters for a router-level unit test that mounts the app without the
    middleware.
    """
    return AuditContext.for_user(
        current_user,
        request_id=current_request_id() or new_request_id(),
    )


async def get_public_request_context() -> AuditContext:
    """For the two unauthenticated writers (parent self-register,
    password-reset confirm): the handler resolves the actor itself once it
    has loaded/created the ``User`` row; ``actor_kind`` stays ``user``.
    """
    return AuditContext(
        request_id=current_request_id() or new_request_id(),
        actor=None,
        actor_kind=AuditActorKind.user,
        actor_role=None,
    )
