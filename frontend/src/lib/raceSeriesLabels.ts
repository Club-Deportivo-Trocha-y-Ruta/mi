/**
 * raceSeriesLabels.ts — Etiquetas derivadas para series de competencias:
 * nivel de un campeonato (feature 023) y nombre de chip de una copa (hotfix
 * multicopa — identidad de válida, 2026-09-16).
 *
 * Los labels NUNCA se persisten: se derivan en tiempo de render. El nivel se
 * deriva de `RaceSeriesLevel` (ver `data-model.md` de la spec 023, sección
 * "Label derivation"). Solo aplican a series de tipo `championship`; las
 * copas (`kind = "cup"`) siempre guardan `level = "departmental"` pero no
 * exponen el nivel en la UI.
 *
 * Módulo puro: sin React, sin I/O, sin efectos secundarios. Sin calendario
 * de copas hardcodeado — la etiqueta siempre viene de los datos de la serie.
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

// ---------------------------------------------------------------------------
// Nombre de chip de una serie (hotfix multicopa — identidad de válida)
// ---------------------------------------------------------------------------

/**
 * Nombre compacto de una serie para chips/etiquetas donde el espacio es
 * limitado — prefiere `short_name` (ej. "Let's GO") y cae al `name`
 * completo cuando no hay nombre corto configurado.
 *
 * Contrato compartido: mirror del `series_display_name` del backend
 * (`race_labels.py`, owner W1-C) — misma prioridad short_name > name.
 */
export function seriesChipLabel(
  name: string,
  shortName: string | null | undefined,
): string {
  const trimmed = shortName?.trim();
  return trimmed && trimmed.length > 0 ? trimmed : name;
}
