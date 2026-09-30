import type { PlausibilityCode, PlausibilityMeasure } from "@/types/anthropometry.types";

/** Textos de las advertencias de plausibilidad (contracts/ui.md, feature 048). */
export const PLAUSIBILITY_COPY: Record<PlausibilityCode, string> = {
  height_decreased:
    "La talla de pie es más de 1 cm menor que en la medición anterior. Revisa la postura y vuelve a medir.",
  height_velocity_implausible:
    "El aumento de talla desde la medición anterior es inusualmente alto. Revisa que el dato esté bien escrito.",
  weight_change_large:
    "El peso cambió más de un 10 % desde la medición anterior. Confirma la lectura de la báscula.",
  sitting_ratio_atypical:
    "La talla sentado no guarda la proporción habitual con la talla de pie. ¿Restaste la altura del banco?",
  arm_span_ratio_atypical:
    "La envergadura no guarda la proporción habitual con la talla. Revisa que el dato esté bien escrito.",
};

export const PLAUSIBILITY_MEASURE_LABELS: Record<PlausibilityMeasure, string> = {
  weight: "Peso",
  standing_height: "Talla de pie",
  sitting_height: "Talla sentado",
  arm_span: "Envergadura",
};
