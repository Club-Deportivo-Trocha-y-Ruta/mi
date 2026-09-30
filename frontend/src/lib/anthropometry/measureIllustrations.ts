/**
 * Ilustraciones por medida de la captura antropométrica (feature 048, FR-031).
 *
 * Los `.webp` viven en `src/assets/anthropometry/{medida}.webp` y se importan
 * de forma estática, una por medida: si un archivo falta, el build de Vite
 * falla en lugar de dejar un hueco silencioso en el asistente. No hay
 * ilustración de «Preparación» (`precheck.webp` no se produjo); el paso de
 * preparación simplemente no la muestra.
 *
 * Los textos («Dónde», «Cómo», alt accesible) viven en `measureGuides.ts`;
 * este archivo sólo aporta la imagen. Mismo patrón que
 * `lib/bodyComposition/siteIllustrations.ts`.
 */
import armSpanUrl from "@/assets/anthropometry/arm_span.webp";
import sittingHeightUrl from "@/assets/anthropometry/sitting_height.webp";
import standingHeightUrl from "@/assets/anthropometry/standing_height.webp";
import weightUrl from "@/assets/anthropometry/weight.webp";

import type { MeasureKey } from "./measureGuides";

const MEASURE_ILLUSTRATIONS: Record<MeasureKey, string> = {
  weight: weightUrl,
  standing_height: standingHeightUrl,
  sitting_height: sittingHeightUrl,
  arm_span: armSpanUrl,
};

/** URL de la ilustración de la medida. */
export function getMeasureIllustration(key: MeasureKey): string {
  return MEASURE_ILLUSTRATIONS[key];
}
