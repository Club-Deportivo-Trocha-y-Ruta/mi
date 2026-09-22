"""Genera los dos PDFs sintéticos que usa ``frontend/e2e/race-history.spec.ts``
(feature 044, T087).

Playwright no puede llamar a ``tests/helpers/results_pdf_builder.py``
directamente (es Python + WeasyPrint): este script es el puente — se invoca
una vez, antes de la corrida, vía ``child_process`` desde el spec, y escribe
los dos archivos en el directorio que reciba por argumento (un temp dir del
sistema operativo, nunca dentro del repo).

Uso::

    cd backend && source .venv/bin/activate
    DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib \\
        python scripts/generate_e2e_race_history_fixtures.py <output_dir>

(la variable ``DYLD_FALLBACK_LIBRARY_PATH`` sólo hace falta en macOS con
Homebrew — mismo requisito que correr ``pytest`` localmente, ver
``docs/technical-notes.md``).

Qué reproduce cada archivo (nombres, clubes y ciudades enteramente
ficticios — ningún corredor, club ni municipio real):

- ``e2e_race_history_2024.pdf`` (Válida III, categoría INFANTIL A, temporada
  2024): fila 1 = "Mateo Ejemplar Ficticio"; fila 2 = "Sofia Demostrativa"
  (club "Ficticio FC", ciudad "Ciudad Ficticia Uno"); fila 3 = corredor
  genérico. Sin huecos — archivo "limpio".
- ``e2e_race_history_2025.pdf`` (Válida IV, categoría INFANTIL B — un
  escalón arriba, progresión de edad normal, temporada 2025): fila 1 =
  "Mateo Ejemplar" (mismo corredor, perdió el segundo apellido impreso —
  dispara ``same_person_suspect``, ``token_set_ratio`` alto); fila 2 =
  "Sofia Demostrativa" con club "Modelo FC" y ciudad "Municipio Ejemplo"
  (mismo nombre, club Y ciudad distintos — dispara ``homonym_suspect`` vía
  la señal ``club_and_city_differ``; ver el docstring de
  ``app/services/race/identity_review.py``); el puesto 3 se borra a
  propósito después de generar las filas secuenciales — hueco de
  completitud que el spec corrige/reconoce en el wizard antes de continuar.

Privacidad: mismo criterio que ``tests/helpers/results_pdf_builder.py`` —
nombres, clubes y ciudades salen de listas ficticias o están escritos aquí
mismo como literales sintéticos, nunca de un dato real.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

# tests/ no es un paquete instalado — se agrega backend/ al path para poder
# importar tests.helpers.results_pdf_builder fuera de una corrida pytest.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.helpers.results_pdf_builder import (  # noqa: E402
    build_results_pdf,
    sequential_category,
)


def _build_2024(out_dir: Path) -> Path:
    category = sequential_category("INFANTIL A", 3, start_points=50, base_minutes=38)
    category.rows[0].name = "Mateo Ejemplar Ficticio"
    category.rows[1].name = "Sofia Demostrativa"
    category.rows[1].club = "Ficticio FC"
    category.rows[1].city = "Ciudad Ficticia Uno"
    return build_results_pdf(
        out_dir / "e2e_race_history_2024.pdf",
        valida_num=3,
        location="Sede E2E Ficticia",
        event_date=date(2024, 6, 15),
        categories=[category],
    )


def _build_2025(out_dir: Path) -> Path:
    # n=4 para poder borrar la fila del puesto 3 (el hueco) sin tocar las
    # dos filas con nombre fijo (Mateo, Sofia) que necesitan sobrevivir.
    category = sequential_category("INFANTIL B", 4, start_points=50, base_minutes=38)
    category.rows[0].name = "Mateo Ejemplar"
    category.rows[1].name = "Sofia Demostrativa"
    category.rows[1].club = "Modelo FC"
    category.rows[1].city = "Municipio Ejemplo"
    assert category.rows[2].position == 3
    del category.rows[2]  # hueco de completitud a propósito (puesto 3 ausente)
    return build_results_pdf(
        out_dir / "e2e_race_history_2025.pdf",
        valida_num=4,
        location="Sede E2E Ficticia",
        event_date=date(2025, 6, 21),
        categories=[category],
    )


def main() -> None:
    if len(sys.argv) != 2:
        print(
            "uso: generate_e2e_race_history_fixtures.py <output_dir>",
            file=sys.stderr,
        )
        raise SystemExit(2)
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    path_2024 = _build_2024(out_dir)
    path_2025 = _build_2025(out_dir)
    # Contrato con el spec de Playwright: imprime las dos rutas, una por
    # línea, en orden temporada 2024 luego 2025 — el spec las lee de stdout.
    print(path_2024)
    print(path_2025)


if __name__ == "__main__":
    main()
