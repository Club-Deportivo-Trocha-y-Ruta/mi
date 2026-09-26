"""``resolve_target`` — amendment 2026-09-26, T144.

contracts/results-skill-cli.md § Target rules. Todo corre sobre aiosqlite y
un ``.env.production`` sintético en ``tmp_path``; jamás toca una base MySQL
ni una red real.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.services.race.results_skill import target as target_module
from app.services.race.results_skill.target import (
    CONFIRM_WORD,
    LOCAL_HOSTS,
    TargetError,
    make_scrubber,
    resolve_target,
)

_PROD_ENV_BODY = (
    "MYSQL_HOST=produccion.hostinger.example\n"
    "MYSQL_PORT=3306\n"
    "MYSQL_USER=trocha_prod\n"
    "MYSQL_PASS=s3cr3t-prod-pass\n"
    "MYSQL_DB=trocha_ruta_prod\n"
    "HOSTINGER_SFTP_HOST=sftp.hostinger.example\n"
    "HOSTINGER_SFTP_USER=sftp_user\n"
    "HOSTINGER_SFTP_PASS=sftp-secret\n"
    "HOSTINGER_SFTP_REMOTE_DIR=/media\n"
    "HOSTINGER_PUBLIC_BASE_URL=https://media.example.com\n"
)


def _write_prod_env(tmp_path, body: str = _PROD_ENV_BODY):
    (tmp_path / ".env.production").write_text(body, encoding="utf-8")
    return tmp_path


@pytest.fixture(autouse=True)
def _restore_settings(monkeypatch):
    # Cada test parte del par local por defecto de la Settings activa.
    monkeypatch.setattr(settings, "app_env", "development", raising=False)
    monkeypatch.setattr(settings, "mysql_host", "localhost", raising=False)
    monkeypatch.setattr(settings, "mysql_db", "trocha_ruta_test_local", raising=False)
    monkeypatch.setattr(settings, "hostinger_sftp_host", "", raising=False)
    monkeypatch.setattr(settings, "hostinger_sftp_user", "", raising=False)
    monkeypatch.setattr(settings, "hostinger_sftp_pass", "", raising=False)
    monkeypatch.setattr(settings, "hostinger_sftp_remote_dir", "", raising=False)
    yield


# ---------------------------------------------------------------------------
# Local — allow-list de hosts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("host", sorted(LOCAL_HOSTS))
async def test_local_allow_list_hosts_accepted(tmp_path, monkeypatch, host):
    monkeypatch.setattr(settings, "mysql_host", host, raising=False)
    _write_prod_env(tmp_path)
    result = await resolve_target(None, None, tmp_path)
    assert result.name == "local"
    assert result.is_production is False


async def test_local_rejects_remote_host(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "mysql_host", "203.0.113.7", raising=False)
    _write_prod_env(tmp_path)
    with pytest.raises(TargetError):
        await resolve_target("local", None, tmp_path)


async def test_local_rejects_app_env_production(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production", raising=False)
    _write_prod_env(tmp_path)
    with pytest.raises(TargetError):
        await resolve_target("local", None, tmp_path)


async def test_local_rejects_pair_matching_production(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "mysql_host", "produccion.hostinger.example", raising=False)
    monkeypatch.setattr(settings, "mysql_db", "trocha_ruta_prod", raising=False)
    _write_prod_env(tmp_path)
    with pytest.raises(TargetError):
        await resolve_target("local", None, tmp_path)


async def test_local_default_target_is_local(tmp_path):
    _write_prod_env(tmp_path)
    result = await resolve_target(None, None, tmp_path)
    assert result.name == "local"


# ---------------------------------------------------------------------------
# Production — guardas
# ---------------------------------------------------------------------------


async def _seeded_sqlite_engine(db_version: str | None):
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, future=True)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        if db_version is not None:
            await conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                {"v": db_version},
            )
    return engine


async def test_production_requires_confirm(tmp_path):
    _write_prod_env(tmp_path)
    with pytest.raises(TargetError):
        await resolve_target("production", None, tmp_path)
    with pytest.raises(TargetError):
        await resolve_target("production", "no-es-la-palabra", tmp_path)


async def test_production_rejects_incomplete_sftp(tmp_path):
    body = _PROD_ENV_BODY.replace("HOSTINGER_SFTP_PASS=sftp-secret\n", "")
    _write_prod_env(tmp_path, body)
    with pytest.raises(TargetError):
        await resolve_target("production", CONFIRM_WORD, tmp_path)


async def test_production_rejects_missing_env_file(tmp_path):
    with pytest.raises(TargetError):
        await resolve_target("production", CONFIRM_WORD, tmp_path)


async def test_production_rejects_alembic_head_mismatch(tmp_path, monkeypatch):
    _write_prod_env(tmp_path)
    engine = await _seeded_sqlite_engine("old_revision_0001")
    monkeypatch.setattr(target_module, "create_target_engine", lambda url: engine)
    monkeypatch.setattr(target_module, "_repo_alembic_head", lambda env_dir: "current_head_9999")

    with pytest.raises(TargetError):
        await resolve_target("production", CONFIRM_WORD, tmp_path)


async def test_production_accepts_matching_head(tmp_path, monkeypatch):
    _write_prod_env(tmp_path)
    engine = await _seeded_sqlite_engine("current_head_9999")
    monkeypatch.setattr(target_module, "create_target_engine", lambda url: engine)
    monkeypatch.setattr(target_module, "_repo_alembic_head", lambda env_dir: "current_head_9999")

    result = await resolve_target("production", CONFIRM_WORD, tmp_path)
    assert result.name == "production"
    assert result.is_production is True
    assert result.sftp_configured is True


async def test_production_rejects_missing_alembic_table(tmp_path, monkeypatch):
    _write_prod_env(tmp_path)
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, future=True)
    monkeypatch.setattr(target_module, "create_target_engine", lambda url: engine)
    monkeypatch.setattr(target_module, "_repo_alembic_head", lambda env_dir: "current_head_9999")

    with pytest.raises(TargetError):
        await resolve_target("production", CONFIRM_WORD, tmp_path)


# ---------------------------------------------------------------------------
# scrub()
# ---------------------------------------------------------------------------


def test_scrub_replaces_every_loaded_value():
    values = {"MYSQL_PASS": "s3cr3t-prod-pass", "HOSTINGER_SFTP_PASS": "sftp-secret"}
    scrub = make_scrubber(values)
    text_with_secrets = (
        "conexión fallida a host con clave s3cr3t-prod-pass y sftp-secret adjunto"
    )
    scrubbed = scrub(text_with_secrets)
    assert "s3cr3t-prod-pass" not in scrubbed
    assert "sftp-secret" not in scrubbed
    assert "***" in scrubbed


async def test_production_error_message_is_scrubbed(tmp_path, monkeypatch):
    _write_prod_env(tmp_path)
    engine = await _seeded_sqlite_engine("old_revision_0001")
    monkeypatch.setattr(target_module, "create_target_engine", lambda url: engine)
    monkeypatch.setattr(target_module, "_repo_alembic_head", lambda env_dir: "current_head_9999")

    try:
        await resolve_target("production", CONFIRM_WORD, tmp_path)
    except TargetError as exc:
        assert "s3cr3t-prod-pass" not in str(exc)
        assert "sftp-secret" not in str(exc)
    else:
        pytest.fail("se esperaba TargetError")


async def test_unknown_target_rejected(tmp_path):
    _write_prod_env(tmp_path)
    with pytest.raises(TargetError):
        await resolve_target("staging", None, tmp_path)
