"""Validación y persistencia de fotos/videos para sesiones de entrenamiento.

- Valida MIME real con magic bytes (no confía en Content-Type ni extensión).
- Strip EXIF en fotos para no exponer GPS de menores.
- Genera thumbnail JPG (max 400px) para fotos.
- Sube el original (y el thumbnail) al storage configurado (Hostinger SFTP
  o fallback local — ver `storage_sftp.py`).
"""

from __future__ import annotations

import io
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.config import settings
from app.models.session_media import MediaType
from app.services.training import storage_sftp

# Extensiones aceptadas por tipo
_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_VIDEO_EXTENSIONS = {".mp4", ".mov"}

# MIME esperado para guardar en DB (post-validación)
_MIME_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
}

_THUMBNAIL_MAX = 400  # px del lado mayor
_THUMBNAIL_QUALITY = 80


@dataclass
class StoredMedia:
    media_type: MediaType
    storage_url: str
    storage_path: str
    thumbnail_url: str | None
    mime_type: str
    size_bytes: int
    width: int | None
    height: int | None
    duration_sec: int | None


def _detect_media_type_from_ext(ext: str) -> MediaType:
    if ext in _PHOTO_EXTENSIONS:
        return MediaType.PHOTO
    if ext in _VIDEO_EXTENSIONS:
        return MediaType.VIDEO
    raise ValueError(
        f"Extensión '{ext}' no permitida. "
        f"Fotos: {sorted(_PHOTO_EXTENSIONS)}, Videos: {sorted(_VIDEO_EXTENSIONS)}."
    )


def _check_magic_bytes(content: bytes, ext: str) -> None:
    """Inspecciona los primeros bytes para asegurar que el tipo declarado es real."""
    if len(content) < 12:
        raise ValueError("El archivo es demasiado pequeño para ser válido.")

    head = content[:12]

    if ext in {".jpg", ".jpeg"}:
        if head[:3] != b"\xff\xd8\xff":
            raise ValueError("El archivo no parece un JPEG válido (magic bytes).")
    elif ext == ".png":
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("El archivo no parece un PNG válido (magic bytes).")
    elif ext == ".webp":
        if head[:4] != b"RIFF" or head[8:12] != b"WEBP":
            raise ValueError("El archivo no parece un WebP válido (magic bytes).")
    elif ext in {".mp4", ".mov"}:
        # MP4/MOV: tras el size (4 bytes) viene "ftyp" en posición 4..8
        if head[4:8] != b"ftyp":
            raise ValueError(
                "El archivo no parece un video MP4/MOV válido (falta 'ftyp')."
            )


def _validate_and_clean_image(content: bytes, ext: str) -> tuple[bytes, int, int, bytes | None]:
    """Decodifica con Pillow, hace strip EXIF y genera thumbnail.

    Returns:
        (clean_bytes, width, height, thumbnail_bytes_jpg)
    """
    from PIL import Image, ImageOps  # type: ignore

    try:
        img = Image.open(io.BytesIO(content))
        img.load()
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"La imagen no se puede decodificar: {exc}") from exc

    # Aplica orientación EXIF antes de strippear
    img = ImageOps.exif_transpose(img)
    width, height = img.size

    # Formato de salida según extensión original
    fmt_by_ext = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}
    fmt = fmt_by_ext[ext]

    # Re-encode sin EXIF (Pillow no incluye EXIF si no se pasa explícitamente)
    clean_buf = io.BytesIO()
    save_kwargs: dict = {"format": fmt}
    if fmt == "JPEG":
        # Conserva calidad alta pero descarta metadata
        save_kwargs.update({"quality": 90, "optimize": True})
        # JPEG no soporta alpha
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
    elif fmt == "PNG":
        save_kwargs.update({"optimize": True})
    elif fmt == "WEBP":
        save_kwargs.update({"quality": 85})

    img.save(clean_buf, **save_kwargs)
    clean_bytes = clean_buf.getvalue()

    # Thumbnail JPG
    thumb = img.copy()
    thumb.thumbnail((_THUMBNAIL_MAX, _THUMBNAIL_MAX))
    if thumb.mode in ("RGBA", "LA", "P"):
        thumb = thumb.convert("RGB")
    thumb_buf = io.BytesIO()
    thumb.save(thumb_buf, format="JPEG", quality=_THUMBNAIL_QUALITY, optimize=True)
    thumbnail_bytes = thumb_buf.getvalue()

    return clean_bytes, width, height, thumbnail_bytes


async def save_session_media(
    file: UploadFile,
    session_id: int,
) -> StoredMedia:
    """Valida y guarda una foto o video. No persiste DB (lo hace el router).

    Raises:
        ValueError: si la extensión/MIME/tamaño/contenido son inválidos.
    """
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    media_type = _detect_media_type_from_ext(ext)

    # Lee con cap defensivo
    max_mb = (
        settings.media_max_photo_mb
        if media_type is MediaType.PHOTO
        else settings.media_max_video_mb
    )
    max_bytes = max_mb * 1024 * 1024

    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError(
            f"El archivo supera el límite de {max_mb} MB para "
            f"{'fotos' if media_type is MediaType.PHOTO else 'videos'}."
        )
    if not content:
        raise ValueError("El archivo está vacío.")

    _check_magic_bytes(content, ext)

    width: int | None = None
    height: int | None = None
    thumb_bytes: bytes | None = None
    final_bytes: bytes = content

    if media_type is MediaType.PHOTO:
        final_bytes, width, height, thumb_bytes = _validate_and_clean_image(content, ext)

    base_name = f"{uuid.uuid4().hex}"
    relative_path = f"sessions/{session_id}/{base_name}{ext}"
    storage_path, storage_url = await storage_sftp.upload_bytes(final_bytes, relative_path)

    thumbnail_url: str | None = None
    if thumb_bytes is not None:
        thumb_relative = f"sessions/{session_id}/{base_name}.thumb.jpg"
        _, thumbnail_url = await storage_sftp.upload_bytes(thumb_bytes, thumb_relative)

    return StoredMedia(
        media_type=media_type,
        storage_url=storage_url,
        storage_path=storage_path,
        thumbnail_url=thumbnail_url,
        mime_type=_MIME_BY_EXT[ext],
        size_bytes=len(final_bytes),
        width=width,
        height=height,
        duration_sec=None,  # extracción precisa de duración video → fuera de MVP
    )


async def delete_session_media(storage_path: str, thumbnail_url: str | None = None) -> None:
    """Borra el archivo y su thumbnail (best-effort). Usado al hard-delete.

    Nota: el delete soft (deleted_at) NO toca el storage. El borrado físico
    queda para un job posterior si decidimos retención automática.
    """
    await storage_sftp.delete_object(storage_path)
