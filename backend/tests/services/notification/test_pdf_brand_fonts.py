"""Regresión: las fuentes de marca de los PDF cargan de verdad.

``templates/documents/pdf/base/layout.html`` (base de la bitácora, los
informes mensuales, la guía de pliegues, etc.) declaraba sus ``@font-face``
con ``url('../static/fonts/…')``. ``DocumentGenerator`` le pasa a WeasyPrint
``base_url = backend/templates``, así que esa ruta resolvía a
``backend/static/fonts/`` — inexistente. WeasyPrint solo avisaba
("Font-face … cannot be loaded") y caía a la fuente del sistema: Arial en
macOS, DejaVu Sans en Linux/Docker (producción). El resultado dependía de la
máquina: la paginación calibrada en macOS no se cumplía en el contenedor
(p. ej. la bitácora pasaba a 4 páginas, contra AC-5.2 de la spec 038).

Dos defensas:

1. Estática: toda ``url(...)`` de un ``@font-face`` en las plantillas PDF
   resuelve —con la misma regla de WeasyPrint— a un archivo que existe.
2. Renderizada: el PDF de la bitácora incrusta Inter y Plus Jakarta Sans.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import url2pathname

import pdfplumber
import pytest

from app.services.notification.document_generator import _TEMPLATES_ROOT

_PDF_TEMPLATES_DIR = _TEMPLATES_ROOT / "documents" / "pdf"

_FONT_FACE_RE = re.compile(r"@font-face\s*\{[^}]*?url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", re.S)


def _font_face_urls() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for template in sorted(_PDF_TEMPLATES_DIR.rglob("*.html")):
        for url in _FONT_FACE_RE.findall(template.read_text(encoding="utf-8")):
            found.append((str(template.relative_to(_TEMPLATES_ROOT)), url))
    return found


def test_scan_finds_the_shared_layout_font_faces() -> None:
    """Autoprueba: el barrido sí ve las fuentes de ``base/layout.html``; si
    el regex dejara de coincidir, el test de abajo pasaría en falso."""
    templates = {template for template, _url in _font_face_urls()}
    assert "documents/pdf/base/layout.html" in templates


@pytest.mark.parametrize(("template", "url"), _font_face_urls())
def test_every_pdf_font_face_url_resolves_to_a_bundled_file(template: str, url: str) -> None:
    # Misma resolución que WeasyPrint: ``base_url`` es el directorio de
    # templates (``path2url`` le agrega la barra final a un directorio).
    base = _TEMPLATES_ROOT.resolve().as_uri() + "/"
    resolved = urljoin(base, url)
    assert resolved.startswith("file://"), f"{template}: fuente remota {url!r}"
    path = Path(url2pathname(resolved.removeprefix("file://")))
    assert path.is_file(), f"{template}: {url!r} resuelve a {path}, que no existe"


async def test_stage_log_pdf_embeds_the_brand_fonts() -> None:
    from tests.services.notification.test_stage_log_pdf import (
        _full_month_stage_log,
        _render,
    )

    pdf_bytes = await _render(_full_month_stage_log())
    pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
    # Los nombres incrustados llevan un prefijo de subconjunto ("ABCDEF+").
    fonts = {char["fontname"].split("+", 1)[-1] for page in pdf.pages for char in page.chars}
    assert any(name.startswith("Inter-Variable") for name in fonts), sorted(fonts)
    assert any(name.startswith("Plus-Jakarta-Sans") for name in fonts), sorted(fonts)
