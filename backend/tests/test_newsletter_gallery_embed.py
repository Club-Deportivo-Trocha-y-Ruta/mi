"""Tests R3 (specs/024-newsletter-audit-fixes) — gate de 3 estados de la
galería del boletín mensual individual (`Bloque 5: Fotos del mes`).

`build_photos_render` (`app.services.notification.media_embedding`) descarga
cada thumbnail vía SFTP en render-time y lo codifica a data-URI base64; el
template `athlete_monthly_newsletter.html` decide qué mostrar según el
resultado:

  1. 0 fotos elegibles           -> sección "Galería del Mes" ausente.
  2. elegibles > 0, 0 embebibles -> placeholder "disponibles en la plataforma",
     sin ningún `data:image` en el HTML.
  3. >= 1 foto embebible         -> `<img src="data:image/jpeg;base64,...">`.

Estrategia: SQLite async in-memory real solo con la tabla `session_media`
(mismo patrón que `tests/test_report_photo_evidence_sections.py` — SQLite no
enforza FKs sin `PRAGMA foreign_keys=ON`, así que no hace falta poblar
`training_sessions`/`users`). Se parchea únicamente
`app.services.training.storage_sftp.download_to_tempfile` (la llamada SFTP
real) para no requerir un servidor SFTP en los tests. El HTML se obtiene
renderizando el template Jinja directamente (mismo patrón que
`tests/test_document_generator.py::_render_monthly_report`) — no se invoca
WeasyPrint, evitando el costo/no-determinismo de generar un PDF real.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.session_media import MediaType, SessionMedia
from app.services.notification.document_generator import DocumentGenerator
from app.services.notification.media_embedding import build_photos_render
from app.services.notification.template_registry import TemplateRegistry
from app.schemas.notification import DocumentTemplate


# ---------------------------------------------------------------------------
# Engine / sesión SQLite in-memory (solo tabla session_media)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    table = Base.metadata.tables["session_media"]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[table]))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session


async def _seed_media(
    session: AsyncSession, media_ids: list[int], *, fail_ids: frozenset[int] = frozenset()
) -> None:
    """Inserta filas de `session_media`. `fail_ids` marca cuáles deben tener
    un `storage_path` bajo el prefijo "unreachable/" — usado por el mock del
    download SFTP para decidir qué falla, sin depender de substrings del
    `media_id` (ej. "202" es substring de "2026" en un path con fecha)."""
    for media_id in media_ids:
        prefix = "unreachable" if media_id in fail_ids else "club"
        session.add(
            SessionMedia(
                id=media_id,
                session_id=1,
                media_type=MediaType.PHOTO,
                storage_url=f"https://storage.example.com/{media_id}.jpg",
                storage_path=f"{prefix}/photos/{media_id}.jpg",
                filename_original=f"{media_id}.jpg",
                mime_type="image/jpeg",
                size_bytes=1024,
                consent_ack=True,
                uploaded_by_user_id=1,
            )
        )
    await session.commit()


def _make_thumb_tempfile(content: bytes = b"fake-jpeg-bytes") -> Path:
    """Crea un archivo temporal real, simulando el download SFTP exitoso."""
    _fd, name = tempfile.mkstemp(suffix=".jpg")
    path = Path(name)
    path.write_bytes(content)
    return path


def _render_gallery_section(photos_render: dict) -> str:
    """Renderiza el template completo del boletín con un contexto mínimo,
    variando únicamente `photos_render` (contexto render-time, R3)."""
    registry = TemplateRegistry()
    generator = DocumentGenerator(registry)
    spec = registry.get_document_spec(DocumentTemplate.ATHLETE_MONTHLY_NEWSLETTER.value)
    template = generator._jinja.get_template(spec.template_path)
    return template.render(
        athlete_first_name="Mateo",
        athlete_last_name="Ficticio",
        club_name="Trocha y Ruta",
        month_label="Abril 2026",
        season_year="2026",
        generated_at="2026-05-01",
        email_blocks={"photos": {"count": photos_render.get("eligible_count", 0), "items": []}},
        pdf_only_blocks={},
        ai_narrative=None,
        coach_narrative_overrides=None,
        photos_render=photos_render,
    )


# ---------------------------------------------------------------------------
# Estado 1: 0 fotos elegibles -> sección ausente
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zero_eligible_photos_section_absent(db_session: AsyncSession):
    photos_render = await build_photos_render(db_session, [], eligible_count=0)

    assert photos_render == {"eligible_count": 0, "embeddable_count": 0, "items": []}

    html = _render_gallery_section(photos_render)
    assert "Galería del Mes" not in html
    assert "data:image" not in html


# ---------------------------------------------------------------------------
# Estado 2: elegibles > 0, 0 embebibles -> placeholder con conteo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eligible_but_none_embeddable_shows_placeholder(db_session: AsyncSession):
    await _seed_media(db_session, [101, 102, 103])
    photo_items = [{"media_id": mid, "caption": None} for mid in (101, 102, 103)]

    with patch(
        "app.services.training.storage_sftp.download_to_tempfile",
        new=AsyncMock(side_effect=RuntimeError("sftp unreachable")),
    ):
        photos_render = await build_photos_render(db_session, photo_items, eligible_count=3)

    assert photos_render["eligible_count"] == 3
    assert photos_render["embeddable_count"] == 0
    assert photos_render["items"] == []

    html = _render_gallery_section(photos_render)
    assert "Galería del Mes" in html
    assert "3 fotos del mes disponibles en la plataforma" in html
    assert "data:image" not in html
    assert "<img" not in html


# ---------------------------------------------------------------------------
# Estado 3: >= 1 foto embebible -> <img src="data:image/jpeg;base64,...">
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_at_least_one_embeddable_renders_data_uri_img(db_session: AsyncSession):
    await _seed_media(db_session, [201, 202], fail_ids=frozenset({202}))
    photo_items = [
        {"media_id": 201, "caption": "Circuito técnico"},
        {"media_id": 202, "caption": None},
    ]

    created_tempfiles: list[Path] = []

    async def _download_side_effect(storage_path: str, suffix: str = "") -> Path:
        if "unreachable" in storage_path:
            raise RuntimeError("sftp timeout for this one")
        tmp = _make_thumb_tempfile()
        created_tempfiles.append(tmp)
        return tmp

    with patch(
        "app.services.training.storage_sftp.download_to_tempfile",
        new=AsyncMock(side_effect=_download_side_effect),
    ):
        photos_render = await build_photos_render(db_session, photo_items, eligible_count=2)

    assert photos_render["eligible_count"] == 2
    assert photos_render["embeddable_count"] == 1
    assert photos_render["items"][0]["caption"] == "Circuito técnico"

    html = _render_gallery_section(photos_render)
    assert "Galería del Mes" in html
    assert '<img src="data:image/jpeg;base64,' in html
    assert "disponibles en la plataforma" not in html
    assert "Circuito técnico" in html

    # Sanity: los tempfiles simulados fueron consumidos/borrados por el
    # servicio (degradación limpia, no deja basura en /tmp).
    for tmp in created_tempfiles:
        assert not tmp.exists()


# ---------------------------------------------------------------------------
# Privacidad (R3): photos_render nunca debe filtrarse a bloques persistidos.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_photos_render_never_written_to_email_blocks_or_snapshot():
    """`build_photos_render` es puramente render-time: su output no debe
    mezclarse con `email_blocks`/`metrics_snapshot` — se pasa por separado
    al contexto del generador (ver `athlete_newsletter_pdf.generate_newsletter_pdf`)."""
    import inspect

    from app.services.notification import athlete_newsletter_pdf

    source = inspect.getsource(athlete_newsletter_pdf)
    assert '"photos_render": photos_render' in source or "photos_render=photos_render" in source or "photos_render\": photos_render" in source
    # email_blocks pasado al contexto es el original, no mutado con photos_render.
    assert '"email_blocks": email_blocks' in source
