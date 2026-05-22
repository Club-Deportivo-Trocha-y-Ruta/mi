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
  // Subido de bg-blue-50/text-blue-800 (~4.18:1) a bg-{color}-100/text-{color}-900
  // (>7:1) — supera WCAG AA con holgura para badge en blanco.
  //
  // Iniciando y Desarrollando son ambas "etapas tempranas" — se mantienen en la
  // familia azul (no rojo/ámbar, para no leer como "mal"), pero usan tonos
  // distintos (blue vs sky) para que no se vean idénticas. Sports-science:
  // ambas etapas son neutras-positivas en LTAD; el contraste de tono solo
  // permite al padre identificar la posición en la rúbrica, no la "calidad".
  Iniciando: "bg-blue-100 text-blue-900",
  Desarrollando: "bg-sky-100 text-sky-900",
  Avanzando: "bg-amber-100 text-amber-900",
  Consolidando: "bg-green-100 text-green-900",
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
