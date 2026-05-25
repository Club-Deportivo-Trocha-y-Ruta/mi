/**
 * usePercentileChartData — memoiza buildChartData + dominio Y para
 * <PercentileCurves>. Aísla el cálculo y permite reuso/test sin recharts.
 *
 * Extraído en B5.
 */
import { useMemo } from "react";

import {
  buildChartData,
  getReferenceData,
  type ChartRow,
  type GrowthIndicator,
} from "@/lib/growth/percentileChart";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

export interface UsePercentileChartDataResult {
  rows: ChartRow[];
  domain: [number, number];
  referenceLoaded: boolean;
}

export function usePercentileChartData(
  records: AnthropometricRecord[],
  sex: "M" | "F",
  indicator: GrowthIndicator,
  birthDate: string,
): UsePercentileChartDataResult {
  const referenceRows = useMemo(
    () => getReferenceData(sex, indicator),
    [sex, indicator],
  );

  const { rows, domain } = useMemo(
    () => buildChartData(referenceRows, records, birthDate, indicator),
    // referenceRows es estable (JSON), sex+indicator+birthDate+records
    // cubren toda la dependencia útil.
    [referenceRows, records, birthDate, indicator],
  );

  return {
    rows,
    domain,
    referenceLoaded: referenceRows.length > 0,
  };
}
