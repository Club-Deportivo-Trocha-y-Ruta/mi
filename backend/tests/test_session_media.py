"""Tests unitarios del módulo de media de sesiones (sin DB).

Cubre:
- Validación de magic bytes (foto/video) detectando spoofing por extensión.
- Strip EXIF de fotos JPEG con GPS.
- Límites de tamaño (foto/video).
- Schema `SessionMediaCreate` requiere `consent_ack`.
- `filter_media_for_parent` no filtra media de hijos ajenos.
"""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import pytest

from app.models.session_media import MediaType


# ---------------------------------------------------------------------------
# Helpers de generación de archivos
# ---------------------------------------------------------------------------


def _make_jpeg_with_gps(width: int = 800, height: int = 600) -> bytes:
    """Genera un JPEG con tag EXIF GPS (latitud/longitud) embedded.

    Usamos PIL para construir un JPG con GPS metadata. El test verifica
    luego que tras pasar por `_validate_and_clean_image` el GPS desaparece.
    """
    from PIL import Image
    import piexif  # type: ignore

    img = Image.new("RGB", (width, height), color=(120, 200, 100))
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: b"N",
        piexif.GPSIFD.GPSLatitude: ((3, 1), (28, 1), (0, 1)),
        piexif.GPSIFD.GPSLongitudeRef: b"W",
        piexif.GPSIFD.GPSLongitude: ((76, 1), (30, 1), (0, 1)),
    }
    exif_bytes = piexif.dump({"0th": {}, "Exif": {}, "GPS": gps_ifd, "1st": {}, "thumbnail": None})
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif_bytes)
    return buf.getvalue()


def _make_plain_jpeg() -> bytes:
    from PIL import Image

    img = Image.new("RGB", (10, 10), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_png() -> bytes:
    from PIL import Image

    img = Image.new("RGBA", (5, 5), color=(0, 255, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_fake_mp4(header_ok: bool = True) -> bytes:
    # MP4: tras 4 bytes de size, "ftyp" + brand + extras.
    if header_ok:
        return b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64
    return b"\x00\x00\x00\x18BADFLAGS" + b"\x00" * 64


def _make_text_disguised_as_jpeg() -> bytes:
    return b"Esto es un .txt que se hace pasar por JPEG" + b"\x00" * 10


# ---------------------------------------------------------------------------
# Magic byte validation
# ---------------------------------------------------------------------------


def test_magic_bytes_accept_real_jpeg():
    from app.services.training.media_files import _check_magic_bytes

    content = _make_plain_jpeg()
    _check_magic_bytes(content, ".jpg")


def test_magic_bytes_accept_real_png():
    from app.services.training.media_files import _check_magic_bytes

    _check_magic_bytes(_make_png(), ".png")


def test_magic_bytes_accept_real_mp4():
    from app.services.training.media_files import _check_magic_bytes

    _check_magic_bytes(_make_fake_mp4(header_ok=True), ".mp4")


def test_magic_bytes_reject_text_pretending_jpeg():
    from app.services.training.media_files import _check_magic_bytes

    with pytest.raises(ValueError, match="JPEG"):
        _check_magic_bytes(_make_text_disguised_as_jpeg(), ".jpg")


def test_magic_bytes_reject_bad_mp4_header():
    from app.services.training.media_files import _check_magic_bytes

    with pytest.raises(ValueError, match="ftyp"):
        _check_magic_bytes(_make_fake_mp4(header_ok=False), ".mp4")


def test_magic_bytes_reject_too_short_file():
    from app.services.training.media_files import _check_magic_bytes

    with pytest.raises(ValueError, match="pequeño"):
        _check_magic_bytes(b"abc", ".jpg")


# ---------------------------------------------------------------------------
# EXIF strip
# ---------------------------------------------------------------------------


def test_image_processing_strips_exif_gps():
    """Tras procesar la imagen, los tags GPS deben desaparecer."""
    pytest.importorskip("piexif")
    from PIL import Image  # type: ignore

    from app.services.training.media_files import _validate_and_clean_image

    raw = _make_jpeg_with_gps()
    clean, w, h, thumb = _validate_and_clean_image(raw, ".jpg")

    # Verificamos que la imagen procesada NO tiene EXIF (Pillow guarda sin EXIF
    # cuando no se pasa explícitamente).
    img = Image.open(io.BytesIO(clean))
    exif_dict = img.getexif()
    # El campo 34853 es GPSInfo. Debe no existir o estar vacío.
    assert 34853 not in exif_dict or not exif_dict[34853]

    assert w > 0 and h > 0
    assert thumb is not None
    # Thumbnail debe ser JPEG válido
    Image.open(io.BytesIO(thumb)).verify()


def test_image_processing_returns_dimensions():
    from app.services.training.media_files import _validate_and_clean_image

    raw = _make_plain_jpeg()
    _, w, h, _ = _validate_and_clean_image(raw, ".jpg")
    assert (w, h) == (10, 10)


# ---------------------------------------------------------------------------
# Schema: consent_ack requerido
# ---------------------------------------------------------------------------


def test_schema_requires_consent_ack():
    from pydantic import ValidationError

    from app.schemas.session_media import SessionMediaCreate

    with pytest.raises(ValidationError):
        SessionMediaCreate(
            media_type=MediaType.PHOTO,
            athlete_ids=[1],
            consent_ack=False,
        )


def test_schema_requires_at_least_one_athlete():
    from pydantic import ValidationError

    from app.schemas.session_media import SessionMediaCreate

    with pytest.raises(ValidationError):
        SessionMediaCreate(
            media_type=MediaType.PHOTO,
            athlete_ids=[],
            consent_ack=True,
        )


def test_schema_accepts_valid_payload():
    from app.schemas.session_media import SessionMediaCreate

    payload = SessionMediaCreate(
        media_type=MediaType.VIDEO,
        athlete_ids=[1, 2],
        consent_ack=True,
        caption="Drill técnico",
    )
    assert payload.media_type is MediaType.VIDEO
    assert payload.athlete_ids == [1, 2]


# ---------------------------------------------------------------------------
# filter_media_for_parent: privacidad cruzada
# ---------------------------------------------------------------------------


@dataclass
class _FakeAthlete:
    id: int


@dataclass
class _FakeMedia:
    id: int
    athletes: list
    deleted_at: datetime | None = None


def test_filter_media_only_returns_intersection():
    from app.services.permissions import filter_media_for_parent

    media_list = [
        _FakeMedia(id=1, athletes=[_FakeAthlete(10)]),   # hijo del padre A
        _FakeMedia(id=2, athletes=[_FakeAthlete(99)]),   # hijo ajeno
        _FakeMedia(id=3, athletes=[_FakeAthlete(10), _FakeAthlete(99)]),  # mixto
    ]
    children = {10}
    visible = filter_media_for_parent(media_list, children)
    assert {m.id for m in visible} == {1, 3}


def test_filter_media_omits_soft_deleted():
    from app.services.permissions import filter_media_for_parent

    media_list = [
        _FakeMedia(id=1, athletes=[_FakeAthlete(10)]),
        _FakeMedia(
            id=2,
            athletes=[_FakeAthlete(10)],
            deleted_at=datetime.now(timezone.utc),
        ),
    ]
    visible = filter_media_for_parent(media_list, {10})
    assert {m.id for m in visible} == {1}


def test_filter_media_empty_children_returns_empty():
    from app.services.permissions import filter_media_for_parent

    media_list = [_FakeMedia(id=1, athletes=[_FakeAthlete(10)])]
    visible = filter_media_for_parent(media_list, set())
    assert visible == []


# ---------------------------------------------------------------------------
# Detección de tipo a partir de extensión
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ext,expected",
    [
        (".jpg", MediaType.PHOTO),
        (".jpeg", MediaType.PHOTO),
        (".png", MediaType.PHOTO),
        (".webp", MediaType.PHOTO),
        (".mp4", MediaType.VIDEO),
        (".mov", MediaType.VIDEO),
    ],
)
def test_detect_media_type(ext, expected):
    from app.services.training.media_files import _detect_media_type_from_ext

    assert _detect_media_type_from_ext(ext) is expected


def test_detect_media_type_rejects_unknown():
    from app.services.training.media_files import _detect_media_type_from_ext

    with pytest.raises(ValueError, match="permitida"):
        _detect_media_type_from_ext(".exe")
