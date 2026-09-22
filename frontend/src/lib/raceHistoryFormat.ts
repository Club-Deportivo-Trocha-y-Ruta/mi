/**
 * Formateo compartido de valores de `RaceHistoryPoint` (feature 044, US6).
 *
 * Vive en `lib/` — igual que `evolutionFormat.ts` — porque tanto
 * `HistoryChart` como `HistoryTable` (y su tooltip) necesitan el mismo
 * formato exacto para "sin dato" y para el signo de la brecha.
 */

/** "sin dato" es el texto fijo del proyecto para cualquier campo `null` de
 * una métrica derivada — nunca "—" ni "N/A" (convención establecida en
 * `course/derived.py` / `CourseSummary.tsx`). */
export const SIN_DATO = "sin dato";

/** `-4.2` → "-4.2 %"; `11.8` → "+11.8 %". El signo explícito en positivos
 * evita ambigüedad: negativo = más rápido que la referencia. */
export function formatGapPct(value: number | null): string {
  if (value === null) return SIN_DATO;
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)} %`;
}

export function formatPercentile(value: number | null): string {
  if (value === null) return SIN_DATO;
  return `P${Math.round(value)}`;
}

export function formatPosition(value: number | null): string {
  if (value === null) return SIN_DATO;
  return `${value}°`;
}

export function formatFieldSize(value: number | null): string {
  if (value === null) return SIN_DATO;
  return String(value);
}

/** "2025-02-09" → "9 feb 2025" — mismo parseo por substring (sin `Date`)
 * que `AthleteAIAnalysisTab#formatRaceDateShort`, para no depender del
 * corrimiento de zona horaria de una fecha-only pasada por `new Date(iso)`. */
const MONTH_ABBR = [
  "ene", "feb", "mar", "abr", "may", "jun",
  "jul", "ago", "sep", "oct", "nov", "dic",
];

export function formatRaceDateShort(isoDate: string): string {
  const year = isoDate.slice(0, 4);
  const month = Number(isoDate.slice(5, 7));
  const day = Number(isoDate.slice(8, 10));
  const abbr = MONTH_ABBR[month - 1];
  return abbr && Number.isFinite(day) ? `${day} ${abbr} ${year}` : isoDate;
}
