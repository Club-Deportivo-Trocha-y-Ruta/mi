"""Genera los golden de paridad (T122), con el parser retirado.

Correr **antes** de que T153 borre ``app.services.race.pdf_parser``:

    cd backend && . .venv/bin/activate
    python -m tests.fixtures.race.parity.generate_golden

Nunca se corre contra un archivo real — solo contra PDFs sintéticos de
``tests.helpers.results_pdf_builder`` (nombres/ciudades/clubes ficticios de
``FakeNameGenerator``, semilla por defecto).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.services.race import pdf_parser
from app.services.race.staged_document import document_to_json
from tests.helpers.results_pdf_builder import FakeNameGenerator, build_results_pdf
from tests.services.race.results_skill.golden_fixtures import build_parity_categories

_OUT_DIR = Path(__file__).resolve().parent


def _generate_one(layout: str) -> None:
    gen = FakeNameGenerator()
    categories = build_parity_categories()
    pdf_path = _OUT_DIR / f"_tmp_{layout}.pdf"
    build_results_pdf(
        pdf_path,
        valida_num=3,
        location="Ciudad Ficticia",
        event_date=date(2026, 3, 1),
        categories=categories,
        name_generator=gen,
        layout=layout,
    )
    parsed = pdf_parser.parse_results_document(pdf_path)
    payload = document_to_json(parsed)
    dest = _OUT_DIR / f"{layout}.json"
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pdf_path.unlink()
    print(f"wrote {dest}")


def main() -> None:
    for layout in ("historical", "2026"):
        _generate_one(layout)


if __name__ == "__main__":  # pragma: no cover — script manual, T122
    main()
