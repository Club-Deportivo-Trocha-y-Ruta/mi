/**
 * Formateo compartido de valores de `EvolutionPoint` (FE-1 / feature 039).
 *
 * Vive en `lib/` (no en `EvolutionChart.tsx`) a propósito: `EvolutionChart`
 * y `ChampionshipReadingCard` lo importan ambos, y varios tests mockean el
 * módulo `EvolutionChart` completo (`vi.mock("@/components/athletes/ai/
 * EvolutionChart", ...)`) — si `formatValue` viviera ahí, esa mockeada
 * dejaría el export indefinido para cualquier otro archivo que lo
 * importe, incluida la instancia "real" cargada vía `vi.importActual` en
 * los tests de a11y (el mock global de Vitest reemplaza el módulo para
 * TODOS los importadores del specifier, no solo para el import mockeado).
 */

export function formatMs(ms: number, unit: string): string {
  if (unit === "ms") {
    if (ms >= 60_000) {
      const totalSec = ms / 1000;
      const min = Math.floor(totalSec / 60);
      const sec = (totalSec - min * 60).toFixed(1);
      return `${min}:${sec.padStart(4, "0")}`;
    }
    return `${(ms / 1000).toFixed(2)} s`;
  }
  if (unit === "rank") return `P${Math.round(ms)}`;
  if (unit === "pct") return `${Math.round(ms)}`;
  return `${ms} ${unit}`;
}

export function formatValue(value: number | null, unit: string): string {
  if (value === null) return "—";
  return formatMs(value, unit);
}
