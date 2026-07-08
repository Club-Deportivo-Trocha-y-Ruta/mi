/**
 * raceSeriesLabels.ts — Etiquetas derivadas para el nivel de un campeonato
 * (feature 023 — Campeonato Nacional).
 *
 * Los labels NUNCA se persisten: se derivan en tiempo de render a partir de
 * `RaceSeriesLevel` (ver `data-model.md` de la spec 023, sección "Label
 * derivation"). Solo aplican a series de tipo `championship`; las copas
 * (`kind = "cup"`) siempre guardan `level = "departmental"` pero no exponen
 * el nivel en la UI.
 *
 * Módulo puro: sin React, sin I/O, sin efectos secundarios.
 */
import type { RaceSeriesLevel } from "../types/raceSeries.types";

/**
 * Etiqueta larga en español neutro (Colombia) para el nivel de un campeonato.
 *
 * - `national`     → "Campeonato Nacional"
 * - `departmental` → "Campeonato Departamental"
 */
export function championshipLabel(level: RaceSeriesLevel): string {
  return level === "national" ? "Campeonato Nacional" : "Campeonato Departamental";
}

/**
 * Etiqueta corta en español neutro (Colombia) para el nivel de un campeonato,
 * usada en chips/labels de gráficas donde el espacio es limitado.
 *
 * - `national`     → "Cto. Nal."
 * - `departmental` → "Cto. Dep."
 */
export function championshipShortLabel(level: RaceSeriesLevel): string {
  return level === "national" ? "Cto. Nal." : "Cto. Dep.";
}
