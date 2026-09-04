"""Exportador determinista de las tablas LMS de la OMS 2007 a CSV.

Feature 040 (T020) — lee la referencia OMS ya revisada y vendorizada en el
frontend (``frontend/src/data/growth-reference-who.json``) y produce los tres
CSV que consume el seed del backend (``app/seed_growth_data.py``):

    backend/app/data/who_lms/who_height_for_age.csv
    backend/app/data/who_lms/who_bmi_for_age.csv
    backend/app/data/who_lms/who_weight_for_age.csv

Uso (one-off; re-ejecutar solo si el JSON fuente cambia):

    cd backend
    .venv/bin/python scripts/export_who_lms_csv.py

Salida determinista: mismas filas, mismo orden (sexo M antes que F, edad
ascendente), mismo formato de número en cada corrida — re-ejecutar produce
un archivo byte-idéntico. Solo constantes de referencia poblacional; no hay
datos de atletas ni de menores en esta fuente ni en su salida.

Ver ``specs/040-growth-module-redesign/contracts/who-lms-seed.md``.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

_BACKEND_ROOT: Path = Path(__file__).resolve().parents[1]
_REPO_ROOT: Path = _BACKEND_ROOT.parent

SOURCE_JSON: Path = (
    _REPO_ROOT / "frontend" / "src" / "data" / "growth-reference-who.json"
)
OUTPUT_DIR: Path = _BACKEND_ROOT / "app" / "data" / "who_lms"

# (indicador JSON, nombre de archivo CSV de salida)
INDICATOR_FILES: list[tuple[str, str]] = [
    ("height_for_age", "who_height_for_age.csv"),
    ("bmi_for_age", "who_bmi_for_age.csv"),
    ("weight_for_age", "who_weight_for_age.csv"),
]

CSV_HEADER: list[str] = ["sex", "age_months", "L", "M", "S"]

# Sexos en orden fijo — determinismo del archivo generado.
_SEX_ORDER: list[str] = ["M", "F"]


def _format_number(value: float) -> str:
    """Formatea con hasta 6 decimales, sin ceros ni punto colgante.

    ``L``/``M``/``S`` en el JSON fuente ya vienen con la precisión de la
    tabla OMS (hasta 4-6 decimales); se preserva tal cual, sin redondeos
    adicionales, para que la paridad con el JSON sea exacta.
    """
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text else "0"


def build_rows(data: dict[str, Any], indicator: str) -> list[dict[str, str]]:
    """Extrae y ordena las filas ``sex,age_months,L,M,S`` de un indicador."""
    indicator_data = data["indicators"][indicator]
    rows: list[dict[str, str]] = []
    for sex in _SEX_ORDER:
        points = indicator_data.get(sex, [])
        # La fuente ya viene ordenada por edad, pero se ordena explícitamente
        # para que el exportador sea determinista aunque el JSON cambie de orden.
        for point in sorted(points, key=lambda p: float(p["age"])):
            rows.append(
                {
                    "sex": sex,
                    "age_months": _format_number(float(point["age"])),
                    "L": _format_number(float(point["L"])),
                    "M": _format_number(float(point["M"])),
                    "S": _format_number(float(point["S"])),
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def export_who_lms_csv(
    source_json: Path = SOURCE_JSON, output_dir: Path = OUTPUT_DIR
) -> dict[str, int]:
    """Lee ``source_json`` y escribe los tres CSV en ``output_dir``.

    Retorna el conteo de filas escritas por archivo (útil para pruebas).
    """
    data = json.loads(source_json.read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    for indicator, filename in INDICATOR_FILES:
        rows = build_rows(data, indicator)
        write_csv(output_dir / filename, rows)
        counts[filename] = len(rows)
    return counts


def main() -> None:
    counts = export_who_lms_csv()
    for filename, count in counts.items():
        print(f"{filename}: {count} filas")


if __name__ == "__main__":
    main()
