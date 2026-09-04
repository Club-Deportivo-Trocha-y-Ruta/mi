/**
 * Test de paridad — `zScoreFromLMS` (cliente) vs `calculate_z_score` (backend).
 *
 * Feature 040 (T019): garantiza que el cálculo LMS del cliente reproduce
 * exactamente el del backend (`backend/app/services/growth.py::calculate_z_score`)
 * para el mismo trío L/M/S y el mismo valor medido — ambos implementan la
 * fórmula de Cole & Green (1992). Datos 100% sintéticos (no hay atletas ni
 * medidas reales de menores involucradas).
 *
 * Los 6 puntos cubren los tres indicadores × ambos sexos, con L/M/S leídos
 * directamente de `frontend/src/data/growth-reference-who.json` en edades que
 * coinciden exactamente con una fila del dataset (sin interpolación, para
 * aislar la fórmula LMS de `interpolateReferenceRow`).
 *
 * Los valores de Z esperados se generaron ejecutando, contra el mismo L/M/S:
 *
 *   cd backend && .venv/bin/python -c "
 *   from app.services.growth import calculate_z_score
 *   print(calculate_z_score(140.0, 1.0, 143.1126, 0.04703))
 *   "
 *
 * (y análogamente para los 5 puntos restantes) y se fijan aquí como
 * constantes — si `calculate_z_score` cambia de fórmula, este test debe
 * volver a ejecutarse contra el backend y actualizarse a mano.
 */

import { describe, expect, it } from "vitest";

import { zScoreFromLMS } from "./lms";

interface ParityFixture {
  label: string;
  /** Parámetro de potencia Box-Cox (λ), leído de growth-reference-who.json. */
  L: number;
  /** Mediana (μ), leída de growth-reference-who.json. */
  M: number;
  /** Coeficiente de variación generalizado (σ), leído de growth-reference-who.json. */
  S: number;
  /** Valor sintético del indicador (cm, kg o kg/m² según el caso). */
  value: number;
  /** Z-score calculado por `calculate_z_score` (backend) para el mismo L/M/S/value. */
  expectedZ: number;
}

// ---------------------------------------------------------------------------
// Fixtures — 6 puntos sintéticos (indicador × sexo), L/M/S de growth-reference-who.json
// ---------------------------------------------------------------------------

const PARITY_FIXTURES: ParityFixture[] = [
  {
    // indicators.height_for_age.M, age=132.5
    label: "height_for_age M @132.5m, valor=140.0cm",
    L: 1.0,
    M: 143.1126,
    S: 0.04703,
    value: 140.0,
    expectedZ: -0.462456,
  },
  {
    // indicators.height_for_age.F, age=108.5
    label: "height_for_age F @108.5m, valor=135.0cm",
    L: 1.0,
    M: 132.4944,
    S: 0.04612,
    value: 135.0,
    expectedZ: 0.410039,
  },
  {
    // indicators.bmi_for_age.M, age=150.5
    label: "bmi_for_age M @150.5m, valor=19.0kg/m²",
    L: -1.7511,
    M: 17.8704,
    S: 0.1172,
    value: 19.0,
    expectedZ: 0.495892,
  },
  {
    // indicators.bmi_for_age.F, age=90.5
    label: "bmi_for_age F @90.5m, valor=14.0kg/m²",
    L: -1.3287,
    M: 15.524,
    S: 0.1102,
    value: 14.0,
    expectedZ: -1.005075,
  },
  {
    // indicators.weight_for_age.M, age=100.5
    label: "weight_for_age M @100.5m, valor=28.0kg",
    L: -0.5799,
    M: 26.2911,
    S: 0.14608,
    value: 28.0,
    expectedZ: 0.423316,
  },
  {
    // indicators.weight_for_age.F, age=72.5
    label: "weight_for_age F @72.5m, valor=18.0kg",
    L: -0.5013,
    M: 20.1639,
    S: 0.149,
    value: 18.0,
    expectedZ: -0.78399,
  },
];

describe("zScoreFromLMS — paridad con calculate_z_score (backend)", () => {
  it.each(PARITY_FIXTURES)(
    "$label → Z ≈ $expectedZ (backend)",
    ({ L, M, S, value, expectedZ }) => {
      const z = zScoreFromLMS(value, L, M, S);
      expect(z).toBeCloseTo(expectedZ, 5);
    },
  );
});
