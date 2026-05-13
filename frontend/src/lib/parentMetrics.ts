/**
 * Helpers de presentación para métricas mostradas al padre.
 *
 * Las rúbricas 1-5 se exponen al padre con etiquetas cualitativas (no número
 * crudo) para evitar interpretación como calificación escolar. Diferenciación
 * por edad LTAD: <13 (Aprender a Entrenar) oculta rúbrica numérica; ≥13
 * (Entrenar para Entrenar) la muestra con la etiqueta.
 */

export type RubricLabel = "Iniciando" | "Desarrollando" | "Avanzando" | "Consolidando" | "Dominando";

export function rubricToLabel(value: number | null | undefined): RubricLabel | null {
  if (value == null) return null;
  const rounded = Math.round(value);
  switch (rounded) {
    case 1:
      return "Iniciando";
    case 2:
      return "Desarrollando";
    case 3:
      return "Avanzando";
    case 4:
      return "Consolidando";
    case 5:
      return "Dominando";
    default:
      return null;
  }
}

export const RUBRIC_TONE: Record<RubricLabel, string> = {
  Iniciando: "bg-blue-50 text-blue-800",
  Desarrollando: "bg-blue-100 text-blue-800",
  Avanzando: "bg-amber-100 text-amber-800",
  Consolidando: "bg-green-100 text-green-800",
  Dominando: "bg-green-200 text-green-900",
};

/**
 * Umbral LTAD: por debajo se considera "Aprender a Entrenar" (10-12)
 * y se oculta la rúbrica numérica al padre. age_decimal puede ser null si
 * no hay antropometría reciente; en ese caso devolvemos `false` (conservador).
 */
export function showsRubricToParent(ageDecimal: number | null | undefined): boolean {
  if (ageDecimal == null) return false;
  return ageDecimal >= 13;
}
