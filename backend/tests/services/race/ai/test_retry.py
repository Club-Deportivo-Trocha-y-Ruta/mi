"""Tests del decorador :func:`with_retry`."""
from __future__ import annotations

import asyncio

import httpx
import pytest

from app.services.race.ai.retry import with_retry


@pytest.mark.asyncio
async def test_retry_succeeds_first_attempt():
    calls = {"n": 0}

    @with_retry(max_attempts=3, backoff=0)
    async def fn():
        calls["n"] += 1
        return "ok"

    assert await fn() == "ok"
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_retry_retries_on_transient_error_then_succeeds():
    calls = {"n": 0}

    @with_retry(max_attempts=3, backoff=0)
    async def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.HTTPError("boom")
        return "recovered"

    assert await fn() == "recovered"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retry_exhausts_attempts_and_reraises():
    calls = {"n": 0}

    @with_retry(max_attempts=3, backoff=0)
    async def fn():
        calls["n"] += 1
        raise TimeoutError("always down")

    with pytest.raises(TimeoutError):
        await fn()
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retry_does_not_retry_value_error():
    calls = {"n": 0}

    @with_retry(max_attempts=3, backoff=0)
    async def fn():
        calls["n"] += 1
        raise ValueError("bug")

    with pytest.raises(ValueError):
        await fn()
    assert calls["n"] == 1  # no retries para bugs


@pytest.mark.asyncio
async def test_retry_does_not_retry_key_error():
    calls = {"n": 0}

    @with_retry(max_attempts=3, backoff=0)
    async def fn():
        calls["n"] += 1
        raise KeyError("missing")

    with pytest.raises(KeyError):
        await fn()
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_retry_backoff_does_not_hang_when_zero():
    """Con backoff=0 no debe sleep."""

    @with_retry(max_attempts=3, backoff=0)
    async def fn():
        raise OSError("net down")

    # Asegura completes en <1s a pesar de 3 retries.
    await asyncio.wait_for(_safe_call(fn), timeout=1.0)


async def _safe_call(fn):
    try:
        await fn()
    except Exception:
        pass
