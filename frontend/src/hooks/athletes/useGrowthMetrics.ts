/**
 * useGrowthMetrics
 *
 * Hook puro (sin side-effects) que calcula métricas LMS de crecimiento para un
 * registro antropométrico dado. Centraliza la lógica de percentiles/Z-score
 * para ser reutilizado en NutritionalClassification, PercentileCurves,
 * PercentileInterpretationBlock, etc.
 *
 * Fuente de referencia: WHO 2007 Growth Reference (5-19 anios).
 * Cumple Resolucion MinSalud Colombia 2465/2016.
 * Fórmula LMS: WHO Technical Report Series (Cole & Green, 1992).
 *
 * Prioridad Z/percentil (feature 040, T025 — un solo estándar de referencia):
 *   - El Z-score/percentil almacenado en el backend solo se usa cuando
 *     `record.growth_source === "WHO"` (la Resolución 2465/2016 usa OMS 2007;
 *     un registro `CDC`/`null` fue calculado contra otra población y NO debe
 *     mezclarse con las curvas OMS que dibuja este módulo).
 *   - En cualquier otro caso (registro legado sin recomputar, `growth_source`
 *     ausente o `CDC`) se recalcula localmente con la tabla OMS del cliente.
 *   - `source` en el resultado indica cuál de los dos caminos se tomó, para
 *     que los llamadores (p. ej. `NutritionalClassification`) muestren el
 *     aviso "Referencia anterior — pendiente de actualizar" cuando corresponda
 *     (`contracts/band-vocabulary.md`).
 */

import { useMemo } from "react";

import whoData from "@/data/growth-reference-who.json";
import { classifyBand } from "@/lib/growth/bands";
import type { NutritionalStatus } from "@/lib/growth/bands";
import {
  ageMonthsFromDates,
  interpolateReferenceRow,
  percentileFromZ,
  zScoreFromLMS,
} from "@/lib/growth/lms";
import type { GrowthIndicator, ReferenceRow } from "@/lib/growth/lms";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

// ---------------------------------------------------------------------------
// Tipos públicos
// ---------------------------------------------------------------------------

/**
 * Banda antigua de 5 niveles. Re-exportada únicamente por compatibilidad —
 * `PercentileCurves.tsx` todavía la importa desde este módulo para su propia
 * clasificación local (se refactoriza en una ola posterior). El resultado de
 * este hook usa el vocabulario nuevo (`NutritionalStatus`, ver `band` abajo).
 */
export type { GrowthBand } from "@/lib/growth/bands";

export interface GrowthMetrics {
  /** Valor del indicador: cm para talla, kg para peso, kg/m² para BMI. */
  value: number;
  /** Edad en meses decimales en el momento de la evaluación. */
  ageMonths: number;
  /** Z-score calculado por LMS o tomado del backend. */
  zScore: number;
  /** Percentil entero (1-99). */
  percentile: number;
  /** Clasificación OMS por Z-score, alineada 1:1 con el enum del backend. */
  band: NutritionalStatus;
  /** Referencia LMS interpolada usada en el cálculo (útil para tooltips/debug). */
  reference: { L: number; M: number; S: number };
  /**
   * Origen del Z-score/percentil/banda devueltos:
   *   - "stored": vienen del backend porque `record.growth_source === "WHO"`.
   *   - "computed": se calcularon en el cliente contra la tabla OMS (registro
   *     legado `CDC`/`null` o sin Z-score de backend para este indicador).
   * Opcional solo por compatibilidad con mocks/fixtures existentes que aún no
   * lo declaran — el hook siempre lo devuelve.
   */
  source?: "stored" | "computed";
}

export interface UseGrowthMetricsArgs {
  record: AnthropometricRecord;
  /** Sexo biológico: M = masculino, F = femenino. */
  sex: "M" | "F";
  /** Fecha de nacimiento en formato ISO yyyy-mm-dd. */
  birthDate: string;
  /** Indicador de crecimiento a calcular. */
  indicator: GrowthIndicator;
}

// ---------------------------------------------------------------------------
// Helpers internos
// ---------------------------------------------------------------------------

/** Estructura del JSON de referencia OMS. */
interface WhoData {
  indicators: Record<GrowthIndicator, Record<"M" | "F", ReferenceRow[]>>;
}

const who = whoData as WhoData;

/**
 * Extrae el valor del indicador desde el registro.
 * Retorna null si el valor es inválido o no computable.
 */
function extractValue(
  record: AnthropometricRecord,
  indicator: GrowthIndicator,
): number | null {
  switch (indicator) {
    case "height_for_age": {
      const h = Number(record.standing_height_cm);
      return h > 0 ? h : null;
    }
    case "weight_for_age": {
      const w = Number(record.weight_kg);
      return w > 0 ? w : null;
    }
    case "bmi_for_age": {
      // Preferencia: BMI calculado por el backend
      if (record.bmi != null) {
        const bmi = Number(record.bmi);
        return bmi > 0 ? bmi : null;
      }
      // Fallback: calcular desde peso y talla
      const h = Number(record.standing_height_cm);
      const w = Number(record.weight_kg);
      if (h <= 0 || w <= 0) return null;
      return w / Math.pow(h / 100, 2);
    }
  }
}

/**
 * Determina si hay un Z-score de backend que corresponda exactamente al
 * indicador solicitado. Evita usar `height_z_score` para `bmi_for_age`, etc.
 */
function extractBackendZ(
  record: AnthropometricRecord,
  indicator: GrowthIndicator,
): { zScore: number; percentile: number | null } | null {
  switch (indicator) {
    case "height_for_age":
      if (record.height_z_score != null) {
        return {
          zScore: record.height_z_score,
          percentile: record.height_percentile ?? null,
        };
      }
      return null;
    case "bmi_for_age":
      if (record.bmi_z_score != null) {
        return {
          zScore: record.bmi_z_score,
          percentile: record.bmi_percentile ?? null,
        };
      }
      return null;
    case "weight_for_age":
      if (record.weight_z_score != null) {
        return {
          zScore: record.weight_z_score,
          percentile: record.weight_percentile ?? null,
        };
      }
      return null;
  }
}

// ---------------------------------------------------------------------------
// Hook público
// ---------------------------------------------------------------------------

/**
 * Calcula métricas de crecimiento LMS para un registro antropométrico.
 *
 * - Prioriza el Z-score del backend cuando existe para el indicador correcto
 *   Y `record.growth_source === "WHO"` (ver `source` en el resultado).
 * - En cualquier otro caso interpola la tabla OMS del cliente y aplica la
 *   fórmula LMS.
 * - Retorna `null` si el valor es inválido, la edad está fuera de rango o no
 *   hay filas de referencia disponibles.
 */
export function useGrowthMetrics(args: UseGrowthMetricsArgs): GrowthMetrics | null {
  const { record, sex, birthDate, indicator } = args;

  return useMemo<GrowthMetrics | null>(() => {
    // 1. Extraer el valor del indicador
    const value = extractValue(record, indicator);
    if (value === null) return null;

    // 2. Calcular edad en meses
    const ageMonths = ageMonthsFromDates(birthDate, record.evaluation_date);

    // 3. Cargar filas de referencia OMS para (indicador, sexo)
    const rows: ReferenceRow[] | undefined = who.indicators[indicator]?.[sex];
    if (!rows || rows.length === 0) return null;

    // 4. Verificar que la edad esté dentro del rango del dataset
    const minAge = rows[0].age;
    const maxAge = rows[rows.length - 1].age;
    if (ageMonths < minAge || ageMonths > maxAge) return null;

    // 5. Interpolación de referencia (siempre necesaria para el campo `reference`)
    const refRow = interpolateReferenceRow(rows, ageMonths);
    if (refRow === null) return null;

    const reference = { L: refRow.L, M: refRow.M, S: refRow.S };

    // 6. Priorizar Z-score del backend SOLO si el registro fue calculado con
    //    la misma referencia (OMS 2007) que dibuja este módulo. Un registro
    //    `growth_source === "CDC"` (o `null`, legado sin recomputar) tiene un
    //    Z-score de otra población — usarlo aquí produciría un número
    //    inconsistente con las curvas OMS que se muestran junto a él.
    const backendZ = extractBackendZ(record, indicator);
    const canUseStored = backendZ !== null && record.growth_source === "WHO";

    if (canUseStored && backendZ !== null) {
      const zScore = backendZ.zScore;
      const percentile =
        backendZ.percentile != null
          ? backendZ.percentile
          : percentileFromZ(zScore);
      return {
        value,
        ageMonths,
        zScore,
        percentile,
        band: classifyBand(indicator, zScore),
        reference,
        source: "stored",
      };
    }

    // 7. Calcular Z-score por LMS (registro sin Z de backend, o Z de backend
    //    que no es OMS-conformante todavía).
    const zScore = zScoreFromLMS(value, refRow.L, refRow.M, refRow.S);
    const percentile = percentileFromZ(zScore);

    return {
      value,
      ageMonths,
      zScore,
      percentile,
      band: classifyBand(indicator, zScore),
      reference,
      source: "computed",
    };
  }, [record, sex, birthDate, indicator]);
}
