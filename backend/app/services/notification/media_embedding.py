"""Servicio: embebido de fotos como data-URI base64 en render-time.

WeasyPrint (`document_generator.py`) no configura un `url_fetcher` propio, así
que `<img src="https://.../thumb.jpg">` apuntando al storage de Hostinger
nunca se resuelve al renderizar desde Render (sin acceso a esa red) — el tag
queda vacío sin error visible. Reutiliza el patrón de
`app.services.training.reports.build_report_photo_evidence` (spec-022):
descarga cada thumbnail vía SFTP, lo codifica a base64 y aplica un
presupuesto total de bytes, degradando de forma silenciosa foto por foto.

Privacidad: el resultado (`data_uri`) es SOLO para el contexto de render del
PDF. Nunca debe escribirse en `metrics_snapshot` ni en ningún bloque de email.
"""

from __future__ import annotations

import base64
import logging
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Presupuesto total de bytes embebidos por documento (paridad con spec-022).
_PHOTO_EMBED_MAX_TOTAL_BYTES = 2 * 1024 * 1024


async def _fetch_storage_paths(
    db: AsyncSession, media_ids: Sequence[int]
) -> dict[int, str]:
    """Resuelve `storage_path` real (no la URL pública) por `media_id`.

    Los items de `photos_block` sólo traen `thumbnail_url`/`storage_url`
    (no reconstruibles de forma confiable a un `storage_path` de SFTP), así
    que se consulta el modelo una sola vez por lote.
    """
    if not media_ids:
        return {}

    from app.models.session_media import SessionMedia

    result = await db.execute(
        select(SessionMedia.id, SessionMedia.storage_path).where(
            SessionMedia.id.in_(media_ids)
        )
    )
    return {media_id: storage_path for media_id, storage_path in result.all()}


async def _download_thumb_as_data_uri(storage_path: str) -> tuple[str, int] | None:
    """Descarga el thumbnail derivado de `storage_path` y lo codifica base64.

    Retorna `(data_uri, bytes)` o `None` si la descarga falla (degradación
    limpia: nunca rompe el render del PDF por una foto individual).
    """
    from app.services.training import storage_sftp

    # Deriva el path del thumbnail desde el del original, igual que en
    # `reports.build_report_photo_evidence` (ver `media_files.save_session_media`).
    orig = PurePosixPath(storage_path)
    thumb_path = str(orig.with_name(f"{orig.stem}.thumb.jpg"))

    tmpdir = tempfile.gettempdir()
    local_path: Path | None = None
    try:
        resolved = await storage_sftp.download_to_tempfile(thumb_path, suffix=".jpg")
        local_path = Path(resolved)
        data = local_path.read_bytes()
    except Exception:  # noqa: BLE001
        return None
    finally:
        # Borra SOLO si es un temporal (modo SFTP); en modo local es el
        # archivo real del storage y no debe eliminarse.
        if local_path is not None and str(local_path).startswith(tmpdir):
            local_path.unlink(missing_ok=True)

    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/jpeg;base64,{b64}", len(data)


async def build_photos_render(
    db: AsyncSession | None,
    photo_items: Sequence[Mapping[str, Any]],
    eligible_count: int,
    max_total_bytes: int = _PHOTO_EMBED_MAX_TOTAL_BYTES,
) -> dict[str, Any]:
    """Construye el contexto `photos_render` (render-time, nunca persistido).

    Args:
        db: sesión async para resolver `storage_path` por `media_id`. Si es
            `None` (caller sin sesión disponible), degrada a `embeddable_count
            = 0` sin intentar descargas.
        photo_items: items del bloque `photos` del snapshot (`media_id`,
            `thumbnail_url`, `storage_url`, `caption`, ...).
        eligible_count: total de fotos elegibles reportado por el snapshot
            (`photos.count`), independiente de cuántas se logren embeber.
        max_total_bytes: presupuesto acumulado de bytes base64 embebidos.

    Returns:
        `{"eligible_count": int, "embeddable_count": int, "items": [...]}`
        con `items[].data_uri` y `items[].caption`. Nunca lanza.
    """
    if db is None or not photo_items:
        return {"eligible_count": eligible_count, "embeddable_count": 0, "items": []}

    try:
        media_ids = [
            item["media_id"] for item in photo_items if item.get("media_id") is not None
        ]
        storage_paths = await _fetch_storage_paths(db, media_ids)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "photos_render: error resolviendo storage_path (%s)", type(exc).__name__
        )
        return {"eligible_count": eligible_count, "embeddable_count": 0, "items": []}

    items: list[dict[str, Any]] = []
    total_bytes = 0

    for item in photo_items:
        storage_path = storage_paths.get(item.get("media_id"))
        if not storage_path:
            continue

        embedded = await _download_thumb_as_data_uri(storage_path)
        if embedded is None:
            continue
        data_uri, size = embedded

        total_bytes += size
        if total_bytes > max_total_bytes:
            break

        items.append({"data_uri": data_uri, "caption": item.get("caption")})

    return {
        "eligible_count": eligible_count,
        "embeddable_count": len(items),
        "items": items,
    }
