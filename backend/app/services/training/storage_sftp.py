"""Wrapper FTPS para subir/borrar media en Hostinger (Shared Hosting).

Hostinger Shared expone FTP/FTPS en el puerto 21 (no SFTP/SSH en el 22). Usa
`ftplib.FTP_TLS` para subir cifrado sobre TLS (AUTH TLS + PROT P). Las variables
de entorno conservan el prefijo `HOSTINGER_SFTP_*` por compatibilidad.

Si las credenciales no están configuradas (entorno local/tests), se usa un
fallback de filesystem local en `static/uploads/media` y se construye una URL
servida por el propio backend mediante el mount estático (configurado en
`main.py`).
"""

from __future__ import annotations

import asyncio
import io
import logging
import ssl
from contextlib import contextmanager
from ftplib import FTP, FTP_TLS, error_perm, error_temp
from pathlib import Path, PurePosixPath
from typing import Iterator

from app.config import settings

logger = logging.getLogger(__name__)


_LOCAL_FALLBACK_BASE = Path("static/uploads/media")
_LOCAL_FALLBACK_URL_PREFIX = "/static/uploads/media"

_FTP_TIMEOUT_SEC = 30


def _is_sftp_configured() -> bool:
    return bool(
        settings.hostinger_sftp_host
        and settings.hostinger_sftp_user
        and settings.hostinger_sftp_pass
        and settings.hostinger_sftp_remote_dir
        and settings.hostinger_public_base_url
    )


@contextmanager
def _ftp_client() -> Iterator[FTP]:
    """Abre una conexión FTPS (preferida) o FTP plano (fallback) a Hostinger.

    Hostinger Shared soporta FTPS explícito (AUTH TLS sobre el puerto 21). Si el
    servidor no acepta TLS, se cae a FTP plano emitiendo un warning.
    """
    host = settings.hostinger_sftp_host
    port = settings.hostinger_sftp_port or 21
    user = settings.hostinger_sftp_user
    password = settings.hostinger_sftp_pass

    ctx = ssl.create_default_context()
    ftp: FTP
    try:
        ftps = FTP_TLS(context=ctx, timeout=_FTP_TIMEOUT_SEC)
        ftps.connect(host, port)
        ftps.auth()
        ftps.login(user=user, passwd=password)
        ftps.prot_p()
        ftp = ftps
    except (ssl.SSLError, error_perm, error_temp, OSError) as exc:
        logger.warning(
            "FTPS no disponible (%s). Cayendo a FTP plano para Hostinger.",
            type(exc).__name__,
        )
        ftp = FTP(timeout=_FTP_TIMEOUT_SEC)
        ftp.connect(host, port)
        ftp.login(user=user, passwd=password)

    try:
        yield ftp
    finally:
        try:
            ftp.quit()
        except Exception:  # noqa: BLE001
            try:
                ftp.close()
            except Exception:  # noqa: BLE001
                pass


def _ensure_remote_dirs(ftp: FTP, remote_dir: PurePosixPath) -> None:
    """Crea recursivamente directorios remotos si no existen."""
    parts = remote_dir.parts
    current = PurePosixPath("/") if remote_dir.is_absolute() else PurePosixPath()
    for part in parts:
        if part in ("", "/"):
            continue
        current = current / part
        try:
            ftp.cwd(str(current))
        except error_perm:
            try:
                ftp.mkd(str(current))
            except error_perm as exc:
                # 550 puede aparecer si el directorio existe pero `cwd` falló por
                # permisos; intenta `cwd` de nuevo. Si vuelve a fallar, propaga.
                if not str(exc).startswith("550"):
                    raise
                ftp.cwd(str(current))


def _upload_sftp_sync(content: bytes, relative_path: str) -> tuple[str, str]:
    """Sube `content` a Hostinger por FTPS y retorna (storage_path, storage_url)."""
    remote_base = PurePosixPath(settings.hostinger_sftp_remote_dir)
    remote_path = remote_base / relative_path

    with _ftp_client() as ftp:
        _ensure_remote_dirs(ftp, remote_path.parent)
        buf = io.BytesIO(content)
        ftp.storbinary(f"STOR {remote_path}", buf)

    storage_url = f"{settings.hostinger_public_base_url}/{relative_path}"
    return str(remote_path), storage_url


def _delete_sftp_sync(storage_path: str) -> None:
    """Borra un archivo remoto por FTPS. Errores se loguean (best-effort)."""
    try:
        with _ftp_client() as ftp:
            ftp.delete(storage_path)
    except Exception:  # noqa: BLE001
        logger.warning("No se pudo borrar archivo FTPS (best-effort).")


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
