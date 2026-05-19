"""Wrapper SFTP para subir/borrar media en Hostinger.

Si las credenciales no están configuradas (entorno local/tests), se usa un
fallback de filesystem local en `static/uploads/media` y se construye una URL
servida por el propio backend mediante el mount estático (configurado en
`main.py`).
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Iterator

from app.config import settings

logger = logging.getLogger(__name__)


_LOCAL_FALLBACK_BASE = Path("static/uploads/media")
_LOCAL_FALLBACK_URL_PREFIX = "/static/uploads/media"


def _is_sftp_configured() -> bool:
    return bool(
        settings.hostinger_sftp_host
        and settings.hostinger_sftp_user
        and settings.hostinger_sftp_pass
        and settings.hostinger_sftp_remote_dir
        and settings.hostinger_public_base_url
    )


@contextmanager
def _sftp_client() -> Iterator["paramiko.SFTPClient"]:  # type: ignore[name-defined]
    """Context manager que abre y cierra una conexión SFTP a Hostinger."""
    import paramiko

    transport = paramiko.Transport(
        (settings.hostinger_sftp_host, settings.hostinger_sftp_port)
    )
    try:
        transport.connect(
            username=settings.hostinger_sftp_user,
            password=settings.hostinger_sftp_pass,
        )
        sftp = paramiko.SFTPClient.from_transport(transport)
        if sftp is None:
            raise RuntimeError("No se pudo abrir el cliente SFTP.")
        try:
            yield sftp
        finally:
            sftp.close()
    finally:
        transport.close()


def _ensure_remote_dirs(sftp, remote_dir: PurePosixPath) -> None:
    """Crea recursivamente directorios remotos si no existen."""
    parts = remote_dir.parts
    current = PurePosixPath("/") if remote_dir.is_absolute() else PurePosixPath()
    for part in parts:
        if part in ("", "/"):
            continue
        current = current / part
        try:
            sftp.stat(str(current))
        except IOError:
            sftp.mkdir(str(current))


def _upload_sftp_sync(content: bytes, relative_path: str) -> tuple[str, str]:
    """Sube `content` a Hostinger y retorna (storage_path, storage_url)."""
    remote_base = PurePosixPath(settings.hostinger_sftp_remote_dir)
    remote_path = remote_base / relative_path

    with _sftp_client() as sftp:
        _ensure_remote_dirs(sftp, remote_path.parent)
        with sftp.open(str(remote_path), "wb") as fh:
            fh.write(content)

    storage_url = f"{settings.hostinger_public_base_url}/{relative_path}"
    return str(remote_path), storage_url


def _delete_sftp_sync(storage_path: str) -> None:
    """Borra un archivo SFTP. Errores se loguean (best-effort)."""
    try:
        with _sftp_client() as sftp:
            sftp.remove(storage_path)
    except Exception:  # noqa: BLE001
        logger.warning("No se pudo borrar archivo SFTP (best-effort).")


def _upload_local_sync(content: bytes, relative_path: str) -> tuple[str, str]:
    dest = _LOCAL_FALLBACK_BASE / relative_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return str(dest), f"{_LOCAL_FALLBACK_URL_PREFIX}/{relative_path}"


def _delete_local_sync(storage_path: str) -> None:
    try:
        Path(storage_path).unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        logger.warning("No se pudo borrar archivo local (best-effort).")


async def upload_bytes(content: bytes, relative_path: str) -> tuple[str, str]:
    """Sube bytes al storage configurado.

    Returns:
        Tupla `(storage_path, storage_url)`.
    """
    if _is_sftp_configured():
        return await asyncio.to_thread(_upload_sftp_sync, content, relative_path)
    return await asyncio.to_thread(_upload_local_sync, content, relative_path)


async def delete_object(storage_path: str) -> None:
    """Borra un objeto del storage configurado. Best-effort, no levanta."""
    if not storage_path:
        return
    if _is_sftp_configured() and not storage_path.startswith(str(_LOCAL_FALLBACK_BASE)):
        await asyncio.to_thread(_delete_sftp_sync, storage_path)
    else:
        await asyncio.to_thread(_delete_local_sync, storage_path)
