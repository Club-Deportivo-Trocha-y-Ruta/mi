"""Almacenamiento y validación de archivos de recorrido (.gpx / .fit)."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import UploadFile

_MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
_ALLOWED_EXTENSIONS = {".gpx", ".fit"}
_UPLOAD_BASE = Path("static/uploads/routes")


def _validate_fit_content(content: bytes) -> None:
    """Valida magic byte del formato FIT (.fit).

    El primer byte de un archivo FIT válido debe ser 0x0e (longitud del header)
    y la longitud mínima del header es 14 bytes.

    Raises:
        ValueError: si el archivo no es un FIT válido.
    """
    if len(content) < 14:
        raise ValueError("El archivo .fit es demasiado pequeño para ser un FIT válido.")
    if content[0] != 0x0E:
        raise ValueError(
            "El archivo .fit no tiene la firma de cabecera FIT esperada (magic byte 0x0e)."
        )


def _validate_gpx_content(content: bytes) -> None:
    """
    Parsea el contenido GPX usando defusedxml + gpxpy para detectar
    entidades XML externas (XXE) y estructuras inválidas.
    Lanza ValueError si el archivo es malicioso o inválido.
    """
    import io

    import defusedxml.ElementTree as dET
    import gpxpy

    # defusedxml rechaza DOCTYPE con entidades externas (XXE)
    try:
        dET.fromstring(content)
    except dET.DTDForbidden:
        raise ValueError("El archivo GPX contiene una DTD prohibida (posible XXE)")
    except dET.EntitiesForbidden:
        raise ValueError("El archivo GPX contiene entidades externas prohibidas (XXE)")
    except Exception as exc:
        raise ValueError(f"El archivo GPX no es XML válido: {exc}") from exc

    # gpxpy valida la estructura GPX
    try:
        gpxpy.parse(io.BytesIO(content))
    except Exception as exc:
        raise ValueError(f"El archivo GPX no tiene estructura GPX válida: {exc}") from exc


async def save_route_file(
    file: UploadFile,
    session_id: int,
) -> str:
    """
    Valida y guarda un archivo de recorrido (.gpx o .fit).

    Returns:
        Ruta relativa al archivo guardado (desde la raíz del backend).

    Raises:
        ValueError: si la extensión, tamaño o contenido son inválidos.
    """
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()

    if ext not in _ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Extensión '{ext}' no permitida. "
            f"Solo se aceptan: {', '.join(_ALLOWED_EXTENSIONS)}"
        )

    content = await file.read()

    if len(content) > _MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"El archivo supera el límite de {_MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB"
        )

    if ext == ".gpx":
        _validate_gpx_content(content)
    elif ext == ".fit":
        _validate_fit_content(content)

    # Generar ruta de destino
    dest_dir = _UPLOAD_BASE / str(session_id)
    await asyncio.to_thread(dest_dir.mkdir, parents=True, exist_ok=True)

    unique_name = f"{uuid.uuid4()}{ext}"
    dest_path = dest_dir / unique_name

    await asyncio.to_thread(dest_path.write_bytes, content)

    return str(dest_dir / unique_name)
