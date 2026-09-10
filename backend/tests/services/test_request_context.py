"""Tests for ``app.services.request_context`` (feature 041,
contracts/audit-recording.md §3.1-§3.3).

Covers: isolation of the ``request_id`` ContextVar between concurrent
requests, the middleware echoing/generating ``X-Request-Id``, and the
non-HTTP helper contexts (``system_context`` / ``webhook_context`` /
``cron_context``).
"""
from __future__ import annotations

import asyncio
import re

import pytest

from app.models.audit_log import AuditActorKind
from app.models.user import UserRole
from app.services.request_context import (
    AuditContext,
    cron_context,
    current_request_id,
    new_request_id,
    request_id_scope,
    system_context,
    webhook_context,
)

_HEX32 = re.compile(r"^[0-9a-f]{32}$")


def test_new_request_id_is_32_char_hex():
    request_id = new_request_id()
    assert _HEX32.match(request_id)


def test_current_request_id_is_none_outside_any_scope():
    assert current_request_id() is None


def test_request_id_scope_binds_and_resets():
    assert current_request_id() is None
    with request_id_scope() as bound:
        assert _HEX32.match(bound)
        assert current_request_id() == bound
    assert current_request_id() is None


def test_request_id_scope_accepts_an_explicit_value():
    with request_id_scope("a" * 32) as bound:
        assert bound == "a" * 32
        assert current_request_id() == "a" * 32


def test_request_id_scope_resets_on_exception():
    with pytest.raises(ValueError):
        with request_id_scope():
            raise ValueError("boom")
    assert current_request_id() is None


class _FakeUser:
    def __init__(self, role: UserRole = UserRole.coach) -> None:
        self.role = role


def test_audit_context_for_user_uses_bound_request_id():
    user = _FakeUser()
    with request_id_scope("b" * 32):
        ctx = AuditContext.for_user(user)
    assert ctx.request_id == "b" * 32
    assert ctx.actor is user
    assert ctx.actor_kind == AuditActorKind.user
    assert ctx.actor_role == UserRole.coach


def test_audit_context_for_user_generates_when_unbound():
    ctx = AuditContext.for_user(_FakeUser())
    assert _HEX32.match(ctx.request_id)


def test_audit_context_for_job_rejects_user_kind():
    with pytest.raises(ValueError):
        AuditContext.for_job(AuditActorKind.user, "some_job")


@pytest.mark.parametrize(
    ("helper", "expected_kind"),
    [
        (system_context, AuditActorKind.system),
        (webhook_context, AuditActorKind.webhook),
        (cron_context, AuditActorKind.cron),
    ],
)
def test_non_http_context_helpers(helper, expected_kind):
    ctx = helper(job="some_job")
    assert ctx.actor is None
    assert ctx.actor_role is None
    assert ctx.actor_kind == expected_kind
    assert _HEX32.match(ctx.request_id)


def test_isolation_between_concurrent_scopes():
    """Two concurrently-running coroutines must never see each other's
    bound ``request_id`` — the guarantee the middleware relies on to keep
    concurrent requests from bleeding their correlation id into each
    other's audit rows / log lines.
    """

    async def bind_and_read(value: str) -> tuple[str, str | None]:
        with request_id_scope(value):
            await asyncio.sleep(0)
            return value, current_request_id()

    async def run() -> list[tuple[str, str | None]]:
        return await asyncio.gather(
            bind_and_read("c" * 32),
            bind_and_read("d" * 32),
        )

    results = asyncio.run(run())
    assert dict(results) == {"c" * 32: "c" * 32, "d" * 32: "d" * 32}
    assert current_request_id() is None


# ---------------------------------------------------------------------------
# Middleware, through the real ASGI app
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_middleware_generates_request_id_when_absent(client):
    response = await client.get("/health")
    assert "x-request-id" in response.headers
    assert _HEX32.match(response.headers["x-request-id"])


@pytest.mark.asyncio
async def test_middleware_ignores_inbound_header_on_non_machine_endpoints(client):
    """Only the two machine endpoints (§3.1) may set their own correlation
    id — everywhere else a client-supplied ``X-Request-Id`` must be ignored
    so a browser cannot forge the id its own writes get attributed to.
    """
    response = await client.get("/health", headers={"X-Request-Id": "e" * 32})
    assert response.headers["x-request-id"] != "e" * 32
    assert _HEX32.match(response.headers["x-request-id"])


@pytest.mark.asyncio
async def test_middleware_two_requests_get_different_ids(client):
    first = await client.get("/health")
    second = await client.get("/health")
    assert first.headers["x-request-id"] != second.headers["x-request-id"]
