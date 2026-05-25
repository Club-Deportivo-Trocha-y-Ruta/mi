"""Rate-limit tests para ``/api/auth/*`` (A3).

slowapi por defecto usa ``get_remote_address`` con ``X-Forwarded-For``
o el peer IP. En tests httpx contra ASGI el ``request.client.host`` es
``127.0.0.1``, así que el rate-limit usa esa IP para todos.

El limiter se **deshabilita en development/test** (``app.main.py``) para
no romper otros tests. Este fixture lo habilita explícitamente, resetea
contadores y lo desactiva al terminar.
"""
from __future__ import annotations

import pytest

from app.main import limiter


@pytest.fixture
def rate_limiter_enabled():
    """Habilita el rate-limiter sólo durante este test, con contadores
    limpios. Restaura el estado al finalizar."""
    prev = limiter.enabled
    limiter.enabled = True
    limiter.reset()
    yield limiter
    limiter.reset()
    limiter.enabled = prev


@pytest.mark.asyncio
async def test_login_rate_limit_returns_429_after_threshold(
    client, rate_limiter_enabled
):
    """11 intentos /login en <1min con misma IP → al menos uno debe ser 429."""
    statuses: list[int] = []
    for _ in range(11):
        resp = await client.post(
            "/api/auth/login",
            json={"email": "nope@nowhere.com", "password": "wrong"},
        )
        statuses.append(resp.status_code)

    assert 429 in statuses, (
        f"Esperaba al menos un 429 entre 11 intentos; obtuvo {statuses}"
    )
    # El 11° intento debería ser 429 (por encima del threshold 10/min).
    assert statuses[-1] == 429, statuses
