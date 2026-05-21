"""Tests F-UP4: integración storage SFTP para PDFs race-imports.

Cubre:
- ``upload_bytes`` con path race-imports/pending/{uuid}/{filename} usa wrapper
  existente (no se duplica el cliente FTPS).
- ``move_object`` promueve pending → committed (rename in-place sin re-upload).
- ``delete_object`` en rollback (best-effort, no raise).
- Fallback local cuando ``HOSTINGER_SFTP_*`` envs missing — escribe a
  ``static/uploads/media/`` (el wrapper actual usa el mismo bucket).
- Mock SFTP completo para evitar conexiones reales en CI.

Convención: NO se duplica el wrapper SFTP — todos los tests usan el cliente
unificado en ``app.services.training.storage_sftp``.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.training import storage_sftp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def disable_sftp_config(monkeypatch):
    """Fuerza el modo fallback local (envs SFTP vacías).

    El wrapper detecta el modo por _is_sftp_configured() que requiere host,
    user, pass, remote_dir y public_base_url. Vacíamos todas.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "hostinger_sftp_host", "")
    monkeypatch.setattr(settings, "hostinger_sftp_user", "")
    monkeypatch.setattr(settings, "hostinger_sftp_pass", "")
    monkeypatch.setattr(settings, "hostinger_sftp_remote_dir", "")
    monkeypatch.setattr(settings, "hostinger_public_base_url", "")
    yield


@pytest.fixture
def isolated_local_storage(monkeypatch, tmp_path):
    """Redirige el storage local fallback a tmp_path para no contaminar el repo."""
    fake_base = tmp_path / "uploads-race"
    monkeypatch.setattr(storage_sftp, "_LOCAL_FALLBACK_BASE", fake_base)
    monkeypatch.setattr(
        storage_sftp, "_LOCAL_FALLBACK_URL_PREFIX", "/static/uploads/race"
    )
    yield fake_base


# ---------------------------------------------------------------------------
# Tests fallback local — upload, move, delete
# ---------------------------------------------------------------------------


class TestLocalFallback:
    @pytest.mark.asyncio
    async def test_upload_bytes_falls_back_to_local_when_sftp_missing(
        self, disable_sftp_config, isolated_local_storage
    ):
        """Sin envs SFTP → upload escribe en filesystem local."""
        content = b"%PDF-1.4 fake pdf content for race import"
        relative = f"race-imports/pending/{uuid.uuid4().hex}/resultados.pdf"

        storage_path, storage_url = await storage_sftp.upload_bytes(content, relative)

        # storage_path es absoluto y existe
        assert Path(storage_path).exists()
        assert Path(storage_path).read_bytes() == content
        # URL bajo el prefix esperado
        assert storage_url.startswith("/static/uploads/race")
        assert storage_url.endswith("/resultados.pdf")

    @pytest.mark.asyncio
    async def test_move_object_local_renames_pending_to_committed(
        self, disable_sftp_config, isolated_local_storage
    ):
        """move_object en modo local renombra el archivo in-fs (atómico)."""
        content = b"%PDF-1.4 content"
        parse_uuid = uuid.uuid4().hex
        src_rel = f"race-imports/pending/{parse_uuid}/resultados.pdf"
        src_path, _ = await storage_sftp.upload_bytes(content, src_rel)
        assert Path(src_path).exists()

        # Mover pending → committed
        dst_rel = f"race-imports/committed/{parse_uuid}/resultados.pdf"
        new_path, new_url = await storage_sftp.move_object(src_path, dst_rel)

        # Origen ya no existe; destino sí, con mismo contenido
        assert not Path(src_path).exists()
        assert Path(new_path).exists()
        assert Path(new_path).read_bytes() == content
        # URL refleja la nueva ruta
        assert "committed" in new_url
        assert new_url.endswith("/resultados.pdf")

    @pytest.mark.asyncio
    async def test_delete_object_local_best_effort(
        self, disable_sftp_config, isolated_local_storage
    ):
        """delete_object en local elimina el archivo y no levanta si no existe."""
        content = b"%PDF-1.4 will be deleted"
        rel = f"race-imports/pending/{uuid.uuid4().hex}/r.pdf"
        path, _ = await storage_sftp.upload_bytes(content, rel)
        assert Path(path).exists()

        await storage_sftp.delete_object(path)
        assert not Path(path).exists()

        # Segunda llamada: no debe lanzar (best-effort)
        await storage_sftp.delete_object(path)
        assert not Path(path).exists()

    @pytest.mark.asyncio
    async def test_delete_object_ignores_empty_path(
        self, disable_sftp_config, isolated_local_storage
    ):
        """delete_object con storage_path vacío es no-op."""
        await storage_sftp.delete_object("")
        await storage_sftp.delete_object(None)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_move_object_validates_inputs(
        self, disable_sftp_config, isolated_local_storage
    ):
        """move_object con args inválidos lanza ValueError explícito."""
        with pytest.raises(ValueError, match="requeridos"):
            await storage_sftp.move_object("", "race-imports/committed/x/r.pdf")
        with pytest.raises(ValueError, match="requeridos"):
            await storage_sftp.move_object("/some/src.pdf", "")


# ---------------------------------------------------------------------------
# Tests con mock SFTP — paths race-imports correctos
# ---------------------------------------------------------------------------


class TestSftpMockedUpload:
    @pytest.mark.asyncio
    async def test_upload_sftp_called_when_configured(self, monkeypatch):
        """Si envs SFTP configuradas, _upload_sftp_sync es invocado (no fallback)."""
        from app.config import settings

        monkeypatch.setattr(settings, "hostinger_sftp_host", "ftps.example.com")
        monkeypatch.setattr(settings, "hostinger_sftp_user", "user")
        monkeypatch.setattr(settings, "hostinger_sftp_pass", "pass")
        monkeypatch.setattr(settings, "hostinger_sftp_remote_dir", "/public_html")
        monkeypatch.setattr(
            settings, "hostinger_public_base_url", "https://cdn.example.com"
        )

        called = {}

        def fake_upload(content, relative_path):
            called["content_len"] = len(content)
            called["relative_path"] = relative_path
            return f"/public_html/{relative_path}", f"https://cdn.example.com/{relative_path}"

        monkeypatch.setattr(storage_sftp, "_upload_sftp_sync", fake_upload)

        content = b"%PDF-1.4 content"
        rel = f"race-imports/pending/{uuid.uuid4().hex}/resultados.pdf"
        path, url = await storage_sftp.upload_bytes(content, rel)

        assert called["content_len"] == len(content)
        assert called["relative_path"] == rel
        assert path.startswith("/public_html/race-imports/")
        assert url.startswith("https://cdn.example.com/race-imports/")

    @pytest.mark.asyncio
    async def test_move_object_sftp_called_when_configured(self, monkeypatch):
        """move_object delega a _move_sftp_sync cuando hay envs SFTP."""
        from app.config import settings

        monkeypatch.setattr(settings, "hostinger_sftp_host", "ftps.example.com")
        monkeypatch.setattr(settings, "hostinger_sftp_user", "user")
        monkeypatch.setattr(settings, "hostinger_sftp_pass", "pass")
        monkeypatch.setattr(settings, "hostinger_sftp_remote_dir", "/public_html")
        monkeypatch.setattr(
            settings, "hostinger_public_base_url", "https://cdn.example.com"
        )

        called = {}

        def fake_move(src, dst_rel):
            called["src"] = src
            called["dst_rel"] = dst_rel
            return f"/public_html/{dst_rel}", f"https://cdn.example.com/{dst_rel}"

        monkeypatch.setattr(storage_sftp, "_move_sftp_sync", fake_move)

        src = "/public_html/race-imports/pending/abc/r.pdf"
        dst_rel = "race-imports/committed/abc/r.pdf"
        new_path, new_url = await storage_sftp.move_object(src, dst_rel)

        assert called["src"] == src
        assert called["dst_rel"] == dst_rel
        assert new_path == "/public_html/race-imports/committed/abc/r.pdf"
        assert new_url == "https://cdn.example.com/race-imports/committed/abc/r.pdf"
