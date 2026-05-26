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
import os
import ssl
import tempfile
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


def _cwd_into(ftp: FTP, abs_dir: PurePosixPath) -> None:
    """Navega a `abs_dir` (path absoluto), creando subdirectorios si faltan.

    Arranca siempre desde `/` para no depender del PWD post-login (Hostinger
    deja al usuario en `/public_html` por defecto, lo que duplicaría el path si
    `REMOTE_DIR` también incluye `public_html`).
    """
    try:
        ftp.cwd("/")
    except error_perm:
        # Si el servidor jaílea al usuario y rechaza `/`, navegar relativo.
        pass

    for part in _split_path(abs_dir):
        try:
            ftp.cwd(part)
        except error_perm:
            ftp.mkd(part)
            ftp.cwd(part)


def _split_path(p: PurePosixPath) -> list[str]:
    """Componentes no vacíos del path (sin `/` raíz)."""
    return [part for part in p.parts if part and part != "/"]


def _absolute_remote_dir() -> PurePosixPath:
    """`HOSTINGER_SFTP_REMOTE_DIR` interpretado como path absoluto.

    Acepta valores con o sin `/` inicial — siempre devuelve un path absoluto
    para evitar ambigüedad con el PWD post-login.
    """
    raw = settings.hostinger_sftp_remote_dir or ""
    if not raw.startswith("/"):
        raw = "/" + raw
    return PurePosixPath(raw)


def _upload_sftp_sync(content: bytes, relative_path: str) -> tuple[str, str]:
    """Sube `content` a Hostinger por FTPS y retorna (storage_path, storage_url).

    `storage_path` es el path absoluto (base + relativo) para uso al borrar.
    """
    remote_base = _absolute_remote_dir()
    remote_path = remote_base / relative_path

    with _ftp_client() as ftp:
        _cwd_into(ftp, remote_path.parent)
        buf = io.BytesIO(content)
        ftp.storbinary(f"STOR {remote_path.name}", buf)

    storage_url = f"{settings.hostinger_public_base_url}/{relative_path}"
    return str(remote_path), storage_url


def _delete_sftp_sync(storage_path: str) -> None:
    """Borra un archivo remoto por FTPS. Errores se loguean (best-effort)."""
    try:
        path = PurePosixPath(storage_path)
        with _ftp_client() as ftp:
            _cwd_into(ftp, path.parent)
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


# ---------------------------------------------------------------------------
# F-UP4: move_object — promueve archivos pending → committed sin re-upload
# ---------------------------------------------------------------------------


def _move_sftp_sync(src_storage_path: str, dst_relative_path: str) -> tuple[str, str]:
    """Renombra/mueve un archivo FTPS de ``src_storage_path`` a un path relativo
    nuevo bajo el remote_dir base.

    Estrategia: usar el comando RNFR/RNTO de FTP (soportado por Hostinger), que
    es atómico server-side y evita re-upload. Si falla (ej. servidor sin
    soporte), caemos a download+upload+delete como fallback robusto.

    Returns:
        Tupla `(new_storage_path, new_storage_url)`.
    """
    from ftplib import error_perm as _err

    remote_base = _absolute_remote_dir()
    dst_remote_path = remote_base / dst_relative_path

    with _ftp_client() as ftp:
        # Crear directorio destino si no existe (mkdir -p).
        _cwd_into(ftp, dst_remote_path.parent)
        try:
            ftp.rename(src_storage_path, str(dst_remote_path))
        except _err:
            # Fallback: download src → upload dst → delete src
            buf = io.BytesIO()
            ftp.retrbinary(f"RETR {src_storage_path}", buf.write)
            buf.seek(0)
            ftp.storbinary(f"STOR {dst_remote_path.name}", buf)
            try:
                ftp.delete(src_storage_path)
            except _err:
                logger.warning(
                    "move_object: STOR ok pero DELE de %s falló (huérfano).",
                    src_storage_path,
                )

    storage_url = f"{settings.hostinger_public_base_url}/{dst_relative_path}"
    return str(dst_remote_path), storage_url


def _move_local_sync(
    src_storage_path: str, dst_relative_path: str
) -> tuple[str, str]:
    src = Path(src_storage_path)
    dst = _LOCAL_FALLBACK_BASE / dst_relative_path
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        src.replace(dst)  # rename atómico in-fs
    else:
        # Si no existe el origen, tratamos como no-op (best-effort).
        logger.warning("move_object local: src %s no existe", src_storage_path)
    return str(dst), f"{_LOCAL_FALLBACK_URL_PREFIX}/{dst_relative_path}"


def _download_sftp_sync(storage_path: str, suffix: str = "") -> Path:
    """Descarga un archivo remoto FTPS a un archivo temporal y retorna su Path.

    Raises:
        FileNotFoundError: Si el archivo remoto no existe (error_perm / error_temp).
    """
    path = PurePosixPath(storage_path)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        with _ftp_client() as ftp:
            try:
                ftp.cwd("/")
            except error_perm:
                pass
            try:
                ftp.retrbinary(f"RETR {storage_path}", tmp.write)
            except (error_perm, error_temp) as exc:
                raise FileNotFoundError(storage_path) from exc
    except FileNotFoundError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "download_to_tempfile: error descargando %s: %s", path.name, type(exc).__name__
        )
        raise FileNotFoundError(storage_path) from exc
    finally:
        tmp.close()

    logger.debug("download_to_tempfile: descargado %s → %s", path.name, tmp.name)
    return Path(tmp.name)


async def download_to_tempfile(storage_path: str, suffix: str = "") -> Path:
    """Descarga ``storage_path`` a un NamedTemporaryFile y retorna su Path local.

    - Si SFTP está configurado Y el path NO es del fallback local: descarga
      vía FTPS usando ``asyncio.to_thread`` (operación bloqueante).
    - Si SFTP no está configurado o el path es local: verifica existencia y
      retorna el Path directamente (sin copiar).

    El caller es responsable de borrar el archivo temporal tras usarlo.

    Raises:
        FileNotFoundError: Si el archivo no se puede encontrar en ninguna
            de las dos rutas.
    """
    if _is_sftp_configured() and not storage_path.startswith(
        str(_LOCAL_FALLBACK_BASE)
    ):
        logger.debug("download_to_tempfile: modo SFTP para %s", storage_path)
        return await asyncio.to_thread(_download_sftp_sync, storage_path, suffix)

    # Fallback local
    p = Path(storage_path)
    if not p.exists():
        raise FileNotFoundError(storage_path)
    return p


async def move_object(
    src_storage_path: str, dst_relative_path: str
) -> tuple[str, str]:
    """Mueve un objeto a un nuevo path relativo en el storage configurado.

    Caso de uso (F-UP4): tras `parse` los PDFs viven en
    `race-imports/pending/{uuid}/...`; al `commit` se mueven a
    `race-imports/committed/{uuid}/...` sin re-upload.

    Returns:
        Tupla `(new_storage_path, new_storage_url)` análoga a `upload_bytes`.
    """
    if not src_storage_path or not dst_relative_path:
        raise ValueError("move_object: src_storage_path y dst_relative_path requeridos")
    # Si el src es local (fallback) usamos move local; idem para SFTP.
    if _is_sftp_configured() and not src_storage_path.startswith(
        str(_LOCAL_FALLBACK_BASE)
    ):
        return await asyncio.to_thread(_move_sftp_sync, src_storage_path, dst_relative_path)
    return await asyncio.to_thread(_move_local_sync, src_storage_path, dst_relative_path)
