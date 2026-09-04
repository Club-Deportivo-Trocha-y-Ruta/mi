/**
 * Vocabulario de bandas de crecimiento OMS 2007.
 *
 * Cortes Z-score según Resolución MinSalud Colombia 2465/2016 — replican
 * exactamente `backend/app/services/growth.py::classify_nutritional_status_height`
 * y `::classify_nutritional_status_bmi` (contrato `contracts/band-vocabulary.md`).
 *
 * Estructura (feature 040, D2 — alineación de banda):
 *   - `NutritionalStatus` es la clave canónica (enum del backend). Cada valor
 *     trae `coachLabel`, `familyLabel`, `narrative`, `tone` y `referral`.
 *   - `classifyBand(indicator, z)` es ahora *indicator-aware*: para talla,
 *     `1 < z ≤ 2` cae en `talla_adecuada` (antes era una banda "watch_high"
 *     separada); `talla_alta` sólo aplica por encima de +2.
 *   - `getBandSpec(indicator, band)` se mantiene como capa de compatibilidad
 *     para los llamadores existentes (`NutritionalClassification.tsx`,
 *     `PercentileInterpretationBlock.tsx`, `PercentileCurves.tsx`), que aún
 *     esperan la forma antigua `{ label, color, narrative }` y, en el caso de
 *     `PercentileCurves.tsx`, siguen produciendo las claves antiguas
 *     (`GrowthBand`) con su propia clasificación local.
 */

import type { GrowthIndicator } from "@/lib/growth/lms";

// ---------------------------------------------------------------------------
// Tipos públicos — vocabulario nuevo (NutritionalStatus-keyed)
// ---------------------------------------------------------------------------

/** Enum de banda nutricional del backend (`app.models.enums.NutritionalStatus`). */
export type NutritionalStatus =
  | "retraso_talla"
  | "riesgo_retraso_talla"
  | "talla_adecuada"
  | "talla_alta"
  | "delgadez_severa"
  | "delgadez"
  | "adecuado"
  | "sobrepeso"
  | "obesidad";

/** Tono visual — coincide 1:1 con `Status` de `components/shared/StatusBadge`. */
export type BandTone = "success" | "warning" | "danger" | "neutral";

export interface BandVocabularyEntry {
  /** Etiqueta técnica para el coach (1-3 palabras). */
  coachLabel: string;
  /** Etiqueta sin jerga clínica para familias. */
  familyLabel: string;
  /** Frase narrativa contextual (1-2 frases), sin placeholders. */
  narrative: string;
  /** Tono de estado — nunca es el único canal (ícono + label siempre). */
  tone: BandTone;
  /** true cuando la banda amerita sugerir consulta profesional (solo coach). */
  referral: boolean;
}

/**
 * Vocabulario único por `NutritionalStatus`. Las narrativas y `coachLabel`
 * corresponden a talla/IMC; `getBandSpec` aplica un ajuste de texto para
 * `weight_for_age` (ver `WEIGHT_LABEL_OVERRIDES`) porque el peso reutiliza
 * las claves de la familia "talla" (mismo corte, sin enum propio — contrato
 * `data-model.md` §4).
 */
export const BAND_VOCABULARY: Record<NutritionalStatus, BandVocabularyEntry> = {
  retraso_talla: {
    coachLabel: "Talla baja",
    familyLabel: "Por debajo del rango esperado",
    narrative:
      "La estatura está por debajo del rango esperado para su edad. Recomendamos consulta médica para descartar causas y dar seguimiento.",
    tone: "danger",
    referral: true,
  },
  riesgo_retraso_talla: {
    coachLabel: "En vigilancia",
    familyLabel: "Un poco por debajo del promedio",
    narrative:
      "La estatura está un poco por debajo del promedio para su edad, dentro del rango normal. Lo importante es que siga su propio canal de crecimiento.",
    tone: "warning",
    referral: false,
  },
  talla_adecuada: {
    coachLabel: "Adecuada",
    familyLabel: "Dentro del rango esperado",
    narrative:
      "La estatura está dentro del rango esperado para su edad. Sigue su canal de crecimiento normal.",
    tone: "success",
    referral: false,
  },
  talla_alta: {
    coachLabel: "Talla alta",
    familyLabel: "Por encima del promedio",
    narrative:
      "La estatura está significativamente por encima del promedio. No es patológico; útil considerar estado de maduración biológica.",
    tone: "neutral",
    referral: false,
  },
  delgadez_severa: {
    coachLabel: "Delgadez",
    familyLabel: "Por debajo del rango esperado",
    narrative:
      "El IMC está por debajo del rango saludable. En atleta activo descartar disponibilidad energética insuficiente. Recomendamos evaluación nutricional.",
    tone: "danger",
    referral: true,
  },
  delgadez: {
    coachLabel: "Riesgo de delgadez",
    familyLabel: "Un poco por debajo del rango",
    narrative: "El IMC está un poco bajo. Vigilamos que la alimentación sea suficiente para el entrenamiento.",
    tone: "warning",
    referral: false,
  },
  adecuado: {
    coachLabel: "Adecuado",
    familyLabel: "Dentro del rango esperado",
    narrative: "El IMC está dentro del rango saludable para su edad.",
    tone: "success",
    referral: false,
  },
  sobrepeso: {
    coachLabel: "Sobrepeso",
    familyLabel: "Por encima del rango esperado",
    narrative:
      "El IMC está en el límite superior. En ciclistas que entrenan con regularidad puede reflejar mayor masa muscular. Se monitorea la tendencia.",
    tone: "warning",
    referral: false,
  },
  obesidad: {
    coachLabel: "Obesidad",
    familyLabel: "Por encima del rango esperado",
    narrative: "El IMC está por encima del rango saludable. Requiere evaluación; muy raro en atletas activos.",
    tone: "danger",
    referral: true,
  },
};

/**
 * Ajuste de texto (coachLabel + narrative) cuando el indicador es
 * `weight_for_age`: reutiliza las claves de estado de talla (mismo corte
 * Z-score) pero con vocabulario propio de peso — frases existentes de la
 * tabla anterior, re-keyed sin inventar texto nuevo (`data-model.md` §4).
 */
const WEIGHT_LABEL_OVERRIDES: Partial<
  Record<NutritionalStatus, Pick<BandVocabularyEntry, "coachLabel" | "narrative">>
> = {
  retraso_talla: {
    coachLabel: "Peso bajo",
    narrative: "El peso está por debajo del rango esperado. Recomendamos evaluación nutricional y médica.",
  },
  riesgo_retraso_talla: {
    coachLabel: "En vigilancia",
    narrative:
      "El peso está un poco bajo, dentro del rango normal. Verificamos que la alimentación cubra la actividad.",
  },
  talla_adecuada: {
    coachLabel: "Adecuado",
    narrative: "El peso está dentro del rango esperado para su edad.",
  },
  talla_alta: {
    coachLabel: "Peso muy alto",
    narrative:
      "El peso está significativamente por encima del promedio. Requiere evaluación con talla e IMC.",
  },
};

/** Retorna la entrada del vocabulario ajustada al indicador (coachLabel/narrative de peso). */
export function getBandVocabulary(
  indicator: GrowthIndicator,
  status: NutritionalStatus,
): BandVocabularyEntry {
  const base = BAND_VOCABULARY[status];
  if (indicator !== "weight_for_age") return base;
  const override = WEIGHT_LABEL_OVERRIDES[status];
  return override ? { ...base, ...override } : base;
}

// ---------------------------------------------------------------------------
// classifyBand — indicator-aware, réplica exacta de los cortes del backend
// ---------------------------------------------------------------------------

/**
 * Clasifica un Z-score en su `NutritionalStatus`, según el indicador.
 *
 * - `bmi_for_age`: z<-2 delgadez_severa · -2..-1 delgadez · -1..1 adecuado ·
 *   1..2 sobrepeso · >2 obesidad (sin cambios respecto al corte anterior).
 * - `height_for_age` / `weight_for_age`: comparten forma (el peso no tiene
 *   enum propio — usa las claves de talla). z<-2 retraso_talla · -2..-1
 *   riesgo_retraso_talla · **-1..2 talla_adecuada** (D2: antes el tramo
 *   1..2 se clasificaba aparte) · >2 talla_alta.
 */
export function classifyBand(indicator: GrowthIndicator, z: number): NutritionalStatus {
  if (indicator === "bmi_for_age") {
    if (z < -2) return "delgadez_severa";
    if (z < -1) return "delgadez";
    if (z <= 1) return "adecuado";
    if (z <= 2) return "sobrepeso";
    return "obesidad";
  }
  // height_for_age y weight_for_age comparten la misma forma de corte.
  if (z < -2) return "retraso_talla";
  if (z < -1) return "riesgo_retraso_talla";
  if (z <= 2) return "talla_adecuada";
  return "talla_alta";
}

// ---------------------------------------------------------------------------
// Capa de compatibilidad — callers existentes (5 bandas antiguas)
// ---------------------------------------------------------------------------

/**
 * Banda antigua de 5 niveles, previa al vocabulario `NutritionalStatus`.
 * Se conserva únicamente porque `PercentileCurves.tsx` mantiene su propia
 * clasificación local (duplicada, indicator-agnostic) y un
 * `Record<GrowthBand, string>` de colores de punto — ese componente se
 * refactoriza en una ola posterior (T026+). No usar en código nuevo.
 */
export type GrowthBand = "low" | "watch_low" | "ok" | "watch_high" | "high";

/** Color legado de 5 valores usado por los componentes aún no migrados. */
export type BandColor = "green" | "yellow" | "orange" | "red" | "blue";

/** Forma antigua devuelta por `getBandSpec` — sólo para compatibilidad. */
export interface BandSpec {
  label: string;
  color: BandColor;
  narrative: string;
}

const TONE_TO_LEGACY_COLOR: Record<BandTone, BandColor> = {
  success: "green",
  warning: "yellow",
  danger: "red",
  neutral: "blue",
};

/**
 * Mapa legado (banda de 5 niveles → `NutritionalStatus`) para la familia
 * "talla" (height_for_age y weight_for_age). `watch_high` colapsa a
 * `talla_adecuada` — es exactamente el fix D2: el tramo 1 < z ≤ 2 deja de
 * mostrarse como una banda separada.
 */
const LEGACY_HEIGHT_FAMILY: Record<GrowthBand, NutritionalStatus> = {
  low: "retraso_talla",
  watch_low: "riesgo_retraso_talla",
  ok: "talla_adecuada",
  watch_high: "talla_adecuada",
  high: "talla_alta",
};

/** Mapa legado para la familia IMC — cortes sin cambios, 1:1. */
const LEGACY_BMI_FAMILY: Record<GrowthBand, NutritionalStatus> = {
  low: "delgadez_severa",
  watch_low: "delgadez",
  ok: "adecuado",
  watch_high: "sobrepeso",
  high: "obesidad",
};

function isNutritionalStatus(value: string): value is NutritionalStatus {
  return Object.prototype.hasOwnProperty.call(BAND_VOCABULARY, value);
}

/** Fallback seguro cuando la combinación (indicador, banda) es inválida en runtime. */
const UNKNOWN_BAND_SPEC: BandSpec = {
  label: "Sin datos",
  color: "yellow",
  narrative: "No hay información suficiente para interpretar este indicador.",
};

function resolveStatus(
  indicator: GrowthIndicator,
  band: GrowthBand | NutritionalStatus,
): NutritionalStatus | null {
  if (isNutritionalStatus(band)) return band;
  const family = indicator === "bmi_for_age" ? LEGACY_BMI_FAMILY : LEGACY_HEIGHT_FAMILY;
  return family[band as GrowthBand] ?? null;
}

/**
 * Retorna el spec en la forma antigua `{ label, color, narrative }` para los
 * llamadores que aún no migraron a `getBandVocabulary`. Acepta tanto la
 * banda antigua de 5 niveles (`GrowthBand`, usada por `PercentileCurves.tsx`)
 * como el `NutritionalStatus` nuevo (usado por `useGrowthMetrics`) — ambos se
 * resuelven al mismo vocabulario único. Fallback seguro si la combinación no
 * existe en runtime (p. ej. datos corruptos o un cast forzado en tests).
 */
export function getBandSpec(
  indicator: GrowthIndicator,
  band: GrowthBand | NutritionalStatus,
): BandSpec {
  const status = resolveStatus(indicator, band);
  if (status === null) return UNKNOWN_BAND_SPEC;
  const entry = getBandVocabulary(indicator, status);
  return {
    label: entry.coachLabel,
    color: TONE_TO_LEGACY_COLOR[entry.tone],
    narrative: entry.narrative,
  };
}
