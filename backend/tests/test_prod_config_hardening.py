"""Tests de endurecimiento de configuración de producción.

Verifica: (1) JWT default rechazado en prod, (2) JWT default advierte en dev,
(3) CORS wildcard advierte en prod, (4) CORS wildcard silencioso en dev.
"""

from __future__ import annotations

import warnings

import pytest
from pydantic import ValidationError

from app.config import Settings


def _prod_kwargs(**overrides):
    """Defaults que pasan los validators previos en `app_env=production`."""
    base = dict(
        app_env="production",
        jwt_secret_key="0" * 64,
        email_provider="resend",
        resend_api_key="re_xxx",
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# JWT secret por defecto
# ---------------------------------------------------------------------------


def test_default_jwt_secret_rejected_in_prod(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(_env_file=None, **_prod_kwargs(jwt_secret_key="cambiar-en-produccion"))


def test_default_jwt_secret_allowed_in_dev(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    with pytest.warns(UserWarning, match="JWT_SECRET_KEY"):
        s = Settings(_env_file=None, app_env="development", jwt_secret_key="cambiar-en-produccion")
    assert s.app_env == "development"


# ---------------------------------------------------------------------------
# CORS wildcard
# ---------------------------------------------------------------------------


def test_cors_wildcard_warns_in_prod(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    with pytest.warns(UserWarning, match="CORS"):
        Settings(_env_file=None, **_prod_kwargs(cors_origins="*"))


def test_cors_wildcard_silent_in_dev(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        Settings(_env_file=None, app_env="development", cors_origins="*")
    cors_warns = [w for w in caught if "CORS" in str(w.message)]
    assert not cors_warns, f"Unexpected CORS warning in dev: {cors_warns}"
