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


def _split_path(p: PurePosixPath) -> list[str]:
    """Componentes no vacíos del path (sin `/` raíz)."""
    return [part for part in p.parts if part and part != "/"]


def _normalized_remote_parts() -> list[str]:
    """Componentes de ``HOSTINGER_SFTP_REMOTE_DIR`` relativos a la PWD post-login.

    Hostinger Shared deja al usuario FTP dentro de ``/public_html`` tras login.
    Si ``REMOTE_DIR`` incluye ``public_html`` (caso común cuando el usuario lo
    configura mirando la ruta absoluta del file manager), se elimina ese
    prefijo redundante para evitar crear ``/public_html/public_html/...``.
    """
    raw = (settings.hostinger_sftp_remote_dir or "").strip("/")
    parts = [p for p in raw.split("/") if p]
    if parts and parts[0] == "public_html":
        parts = parts[1:]
    return parts


def _cwd_into(ftp: FTP, parts: list[str]) -> None:
    """Navega RELATIVO desde la PWD actual, creando subdirectorios si faltan.

    No se usa ``cwd('/')`` previo: Hostinger Shared coloca al usuario en
    ``/public_html`` después del login y un ``cwd('/')`` exitoso escaparía
    ese chroot lógico, dejando los uploads en ``/mi/media/...`` (fuera del
    webroot servido por el subdominio).
    """
    for part in parts:
        if not part or part == "/":
            continue
        try:
            ftp.cwd(part)
        except error_perm:
            ftp.mkd(part)
            ftp.cwd(part)


def _upload_sftp_sync(content: bytes, relative_path: str) -> tuple[str, str]:
    """Sube ``content`` a Hostinger por FTPS y retorna (storage_path, storage_url).

    ``storage_path`` es el path absoluto reportado por el servidor FTP tras
    ``pwd()`` (chroot-relativo) — uso confiable para RETR/DELE/RNFR posteriores.
    """
    rel = PurePosixPath(relative_path)
    rel_parts = _split_path(rel)
    if not rel_parts:
        raise ValueError("relative_path inválido")
    parent_parts = _normalized_remote_parts() + rel_parts[:-1]
    filename = rel_parts[-1]

    with _ftp_client() as ftp:
        _cwd_into(ftp, parent_parts)
        buf = io.BytesIO(content)
        ftp.storbinary(f"STOR {filename}", buf)
        abs_dir = ftp.pwd().rstrip("/")
        storage_path = f"{abs_dir}/{filename}"

    storage_url = f"{settings.hostinger_public_base_url}/{relative_path}"
    return storage_path, storage_url


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

    dst_rel = PurePosixPath(dst_relative_path)
    dst_rel_parts = _split_path(dst_rel)
    if not dst_rel_parts:
        raise ValueError("dst_relative_path inválido")
    parent_parts = _normalized_remote_parts() + dst_rel_parts[:-1]
    filename = dst_rel_parts[-1]

    with _ftp_client() as ftp:
        _cwd_into(ftp, parent_parts)
        abs_dst_dir = ftp.pwd().rstrip("/")
        dst_full = f"{abs_dst_dir}/{filename}"
        try:
            ftp.rename(src_storage_path, dst_full)
        except _err:
            # Fallback: download src → upload dst → delete src
            buf = io.BytesIO()
            ftp.retrbinary(f"RETR {src_storage_path}", buf.write)
            buf.seek(0)
            ftp.storbinary(f"STOR {filename}", buf)
            try:
                ftp.delete(src_storage_path)
            except _err:
                logger.warning(
                    "move_object: STOR ok pero DELE de %s falló (huérfano).",
                    src_storage_path,
                )

    storage_url = f"{settings.hostinger_public_base_url}/{dst_relative_path}"
    return dst_full, storage_url


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

    Intenta RETR con el ``storage_path`` tal como está y, si falla, reintenta
    con un prefijo legado ``/public_html`` strippeado — backward-compat para
    archivos persistidos antes del fix de chroot.

    Raises:
        FileNotFoundError: Si el archivo remoto no existe en ninguna variante.
    """
    path = PurePosixPath(storage_path)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        with _ftp_client() as ftp:
            candidates = [storage_path]
            # Backward-compat: archivos viejos subidos antes del fix quedaron
            # en ``/mi/...`` (sin prefijo ``/public_html``). Si tras mover
            # manualmente a ``/public_html/mi/...`` el storage_path en DB
            # sigue apuntando al path viejo, reintentamos con el prefijo.
            if not storage_path.startswith("/public_html/"):
                candidates.append("/public_html" + storage_path)
            last_exc: Exception | None = None
            for candidate in candidates:
                try:
                    ftp.retrbinary(f"RETR {candidate}", tmp.write)
                    last_exc = None
                    break
                except (error_perm, error_temp) as exc:
                    last_exc = exc
                    tmp.seek(0)
                    tmp.truncate()
            if last_exc is not None:
                raise FileNotFoundError(storage_path) from last_exc
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
