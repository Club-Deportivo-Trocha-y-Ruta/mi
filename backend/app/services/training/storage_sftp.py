"""Wrapper FTPS para subir/borrar media en Hostinger (Shared Hosting).

Hostinger Shared expone FTP/FTPS en el puerto 21 (no SFTP/SSH en el 22). Usa
`ftplib.FTP_TLS` para subir cifrado sobre TLS (AUTH TLS + PROT P). Las variables
de entorno conservan el prefijo `HOSTINGER_SFTP_*` por compatibilidad.

El servidor FTP de Hostinger Shared usa un certificado auto-firmado/genérico
sin SAN que matchee el dominio del usuario. Por eso `check_hostname` y
`verify_mode` están deshabilitados — TLS sigue cifrando la sesión y las
credenciales, pero no se valida la identidad del peer.

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


def _build_ssl_context() -> ssl.SSLContext:
    """Contexto TLS que cifra pero no verifica identidad del peer.

    Hostinger Shared presenta un certificado genérico/auto-firmado que no
    coincide con el dominio del usuario, por lo que verify falla siempre. Aun
    así, la sesión queda cifrada — usable para datos no extremadamente
    sensibles. Si se necesita verificación estricta, migrar a Cloudflare R2.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


@contextmanager
def _ftp_client() -> Iterator[FTP]:
    """Abre una conexión FTPS (preferida) o FTP plano (fallback) a Hostinger."""
    host = settings.hostinger_sftp_host
    port = settings.hostinger_sftp_port or 21
    user = settings.hostinger_sftp_user
    password = settings.hostinger_sftp_pass

    ftp: FTP
    try:
        ftps = FTP_TLS(context=_build_ssl_context(), timeout=_FTP_TIMEOUT_SEC)
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


def _cwd_into(ftp: FTP, parts: list[str]) -> None:
    """Entra a cada subdirectorio en `parts`, creándolo si no existe.

    Usa nombres simples relativos al cwd actual — nunca paths acumulados,
    porque `ftp.cwd('a/b')` desde dentro de `a` busca `a/a/b`.
    """
    for part in parts:
        if not part or part == "/":
            continue
        try:
            ftp.cwd(part)
        except error_perm:
            ftp.mkd(part)
            ftp.cwd(part)


def _split_path(p: PurePosixPath) -> list[str]:
    """Componentes no vacíos del path (sin `/` raíz)."""
    return [part for part in p.parts if part and part != "/"]


def _upload_sftp_sync(content: bytes, relative_path: str) -> tuple[str, str]:
    """Sube `content` a Hostinger por FTPS y retorna (storage_path, storage_url).

    `storage_path` es el path completo (base + relativo) para uso al borrar.
    """
    remote_base = PurePosixPath(settings.hostinger_sftp_remote_dir)
    remote_path = remote_base / relative_path

    with _ftp_client() as ftp:
        _cwd_into(ftp, _split_path(remote_path.parent))
        buf = io.BytesIO(content)
        ftp.storbinary(f"STOR {remote_path.name}", buf)

    storage_url = f"{settings.hostinger_public_base_url}/{relative_path}"
    return str(remote_path), storage_url


def _delete_sftp_sync(storage_path: str) -> None:
    """Borra un archivo remoto por FTPS. Errores se loguean (best-effort)."""
    try:
        path = PurePosixPath(storage_path)
        with _ftp_client() as ftp:
            for part in _split_path(path.parent):
                ftp.cwd(part)
            ftp.delete(path.name)
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
