"""
Script para generar el JSON estático de datos LMS del CDC para el frontend.

Uso:
    cd backend
    python generate_frontend_json.py

Salida:
    ../frontend/src/data/growth-reference-cdc.json
"""
from __future__ import annotations

import csv
import io
import json
import math
import urllib.request
from pathlib import Path
from datetime import date

# Percentiles estándar y sus Z-scores (norm.ppf)
PERCENTILE_Z = {
    "P3": -1.8808,
    "P10": -1.2816,
    "P25": -0.6745,
    "P50": 0.0,
    "P75": 0.6745,
    "P90": 1.2816,
    "P97": 1.8808,
}

CDC_SOURCES = [
    {
        "url": "https://www.cdc.gov/growthcharts/data/zscore/statage.csv",
        "indicator": "height_for_age",
    },
    {
        "url": "https://www.cdc.gov/growthcharts/data/zscore/bmiagerev.csv",
        "indicator": "bmi_for_age",
    },
    {
        "url": "https://www.cdc.gov/growthcharts/data/zscore/wtage.csv",
        "indicator": "weight_for_age",
    },
]

# Rango de edad para atletas 10-19 años (en meses)
AGE_MIN = 120.0
AGE_MAX = 228.5


def lms_to_value(L: float, M: float, S: float, z: float) -> float:
    """Convierte parámetros LMS + Z-score a valor de medida."""
    if abs(L) < 1e-8:
        return M * math.exp(S * z)
    return M * (1 + L * S * z) ** (1 / L)


def download_and_parse(url: str, indicator: str) -> list[dict]:
    """Descarga CSV del CDC y retorna filas LMS filtradas al rango 10-19 años."""
    print(f"  Descargando {indicator}...")
    with urllib.request.urlopen(url, timeout=30) as response:
        raw = response.read()

    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("latin-1")

    reader = csv.DictReader(io.StringIO(content))
    rows = []

    for row in reader:
        sex_raw = row.get("Sex", "").strip()
        age_raw = row.get("Agemos", "").strip()
        l_raw = row.get("L", "").strip()
        m_raw = row.get("M", "").strip()
        s_raw = row.get("S", "").strip()

        if not all([sex_raw, age_raw, l_raw, m_raw, s_raw]):
            continue

        try:
            sex_code = int(sex_raw)
            age = float(age_raw)
            L = float(l_raw)
            M = float(m_raw)
            S = float(s_raw)
        except ValueError:
            continue

        if age < AGE_MIN or age > AGE_MAX:
            continue

        if sex_code == 1:
            sex = "M"
        elif sex_code == 2:
            sex = "F"
        else:
            continue

        # Calcular percentiles
        entry = {
            "age": round(age, 1),
            "L": round(L, 6),
            "M": round(M, 4),
            "S": round(S, 6),
        }
        for pname, z in PERCENTILE_Z.items():
            val = lms_to_value(L, M, S, z)
            entry[pname] = round(val, 2)

        rows.append({"sex": sex, "data": entry})

    return rows


def main() -> None:
    output = {
        "source": "CDC",
        "generated": str(date.today()),
        "age_unit": "months",
        "age_range": f"{AGE_MIN}-{AGE_MAX}",
        "percentiles": ["P3", "P10", "P25", "P50", "P75", "P90", "P97"],
        "indicators": {},
    }

    for source_info in CDC_SOURCES:
        indicator = source_info["indicator"]
        rows = download_and_parse(source_info["url"], indicator)

        m_rows = sorted(
            [r["data"] for r in rows if r["sex"] == "M"],
            key=lambda x: x["age"],
        )
        f_rows = sorted(
            [r["data"] for r in rows if r["sex"] == "F"],
            key=lambda x: x["age"],
        )

        output["indicators"][indicator] = {"M": m_rows, "F": f_rows}
        print(f"  {indicator}: {len(m_rows)} M + {len(f_rows)} F = {len(m_rows)+len(f_rows)} puntos")

    out_path = Path(__file__).parent.parent / "frontend" / "src" / "data" / "growth-reference-cdc.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    json_str = json.dumps(output, ensure_ascii=False, separators=(",", ":"))
    out_path.write_text(json_str, encoding="utf-8")

    size_kb = out_path.stat().st_size / 1024
    print(f"\nArchivo generado: {out_path}")
    print(f"Tamaño: {size_kb:.1f} KB")


if __name__ == "__main__":
    main()
