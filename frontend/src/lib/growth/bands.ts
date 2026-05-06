/**
 * Constantes de bandas de crecimiento OMS 2007.
 *
 * Cortes Z-score según Resolución MinSalud Colombia 2465/2016.
 * Cada banda tiene label, color Tailwind y frase narrativa para padre/atleta.
 */

import type { GrowthBand } from "@/hooks/athletes/useGrowthMetrics";
import type { GrowthIndicator } from "@/lib/growth/lms";

// ---------------------------------------------------------------------------
// Tipos públicos
// ---------------------------------------------------------------------------

export type BandColor = "green" | "yellow" | "orange" | "red" | "blue";

export interface BandSpec {
  /** Etiqueta corta de la banda (1-3 palabras). */
  label: string;
  /** Color asociado (Tailwind theme). */
  color: BandColor;
  /** Frase narrativa contextual para padre/atleta (1-2 frases). Sin placeholder. */
  narrative: string;
}

// ---------------------------------------------------------------------------
// Constantes
// ---------------------------------------------------------------------------

/**
 * Mapeo (indicador, banda) -> spec con label + color + frase.
 * Cumple cortes OMS 2007 (Resolución MinSalud 2465/2016).
 *
 * Bandas por Z-score:
 *   low        : z < -2
 *   watch_low  : -2 ≤ z < -1
 *   ok         : -1 ≤ z ≤ 1
 *   watch_high : 1 < z ≤ 2
 *   high       : z > 2
 */
export const GROWTH_BANDS_WHO: Record<GrowthIndicator, Record<GrowthBand, BandSpec>> = {
  height_for_age: {
    low: {
      label: "Talla baja",
      color: "orange",
      narrative:
        "La estatura está por debajo del rango esperado para su edad. Recomendamos consulta médica para descartar causas y dar seguimiento.",
    },
    watch_low: {
      label: "En vigilancia",
      color: "yellow",
      narrative:
        "La estatura está un poco por debajo del promedio para su edad, dentro del rango normal. Lo importante es que siga su propio canal de crecimiento.",
    },
    ok: {
      label: "Adecuada",
      color: "green",
      narrative:
        "La estatura está dentro del rango esperado para su edad. Sigue su canal de crecimiento normal.",
    },
    watch_high: {
      label: "Talla alta",
      color: "blue",
      narrative:
        "La estatura está por encima del promedio para su edad. No es un problema clínico; puede reflejar una maduración adelantada.",
    },
    high: {
      label: "Talla muy alta",
      color: "blue",
      narrative:
        "La estatura está significativamente por encima del promedio. No es patológico; útil considerar estado de maduración biológica.",
    },
  },

  bmi_for_age: {
    low: {
      label: "Delgadez",
      color: "red",
      narrative:
        "El IMC está por debajo del rango saludable. En atleta activo descartar disponibilidad energética insuficiente. Recomendamos evaluación nutricional.",
    },
    watch_low: {
      label: "Riesgo de delgadez",
      color: "yellow",
      narrative:
        "El IMC está un poco bajo. Vigilamos que la alimentación sea suficiente para el entrenamiento.",
    },
    ok: {
      label: "Adecuado",
      color: "green",
      narrative: "El IMC está dentro del rango saludable para su edad.",
    },
    watch_high: {
      label: "Sobrepeso",
      color: "yellow",
      narrative:
        "El IMC está en el límite superior. En ciclistas que entrenan con regularidad puede reflejar mayor masa muscular. Se monitorea la tendencia.",
    },
    high: {
      label: "Obesidad",
      color: "orange",
      narrative:
        "El IMC está por encima del rango saludable. Requiere evaluación; muy raro en atletas activos.",
    },
  },

  weight_for_age: {
    low: {
      label: "Peso bajo",
      color: "orange",
      narrative:
        "El peso está por debajo del rango esperado. Recomendamos evaluación nutricional y médica.",
    },
    watch_low: {
      label: "En vigilancia",
      color: "yellow",
      narrative:
        "El peso está un poco bajo, dentro del rango normal. Verificamos que la alimentación cubra la actividad.",
    },
    ok: {
      label: "Adecuado",
      color: "green",
      narrative: "El peso está dentro del rango esperado para su edad.",
    },
    watch_high: {
      label: "Peso alto",
      color: "yellow",
      narrative:
        "El peso está por encima del promedio. Considerar también talla e IMC para el cuadro completo.",
    },
    high: {
      label: "Peso muy alto",
      color: "orange",
      narrative:
        "El peso está significativamente por encima del promedio. Requiere evaluación con talla e IMC.",
    },
  },
};

// ---------------------------------------------------------------------------
// Helper público
// ---------------------------------------------------------------------------

/** Retorna el spec completo o un fallback seguro si la combinación no existe. */
export function getBandSpec(indicator: GrowthIndicator, band: GrowthBand): BandSpec {
  return (
    GROWTH_BANDS_WHO[indicator]?.[band] ?? {
      label: "Sin datos",
      color: "yellow",
      narrative: "No hay información suficiente para interpretar este indicador.",
    }
  );
}
