/**
 * piiGuard — client-side anti-PII heuristic for Phase B element labels.
 *
 * Mirrors the backend `_phase_b_label_is_pii` function in
 * backend/app/schemas/technique.py (FR-019 / O-6).
 *
 * Rejects:
 *  - Labels longer than MAX_PHASE_B_LABEL (40) characters.
 *  - Date-of-birth patterns: dd/mm/yyyy or yyyy-mm-dd.
 *  - Two or more "Capitalized Words" (first char uppercase, word ≥ 2 chars) —
 *    person-name heuristic ("Juan Carlos", "María Fernanda").
 *
 * Allows short circuit annotations: "Salida", "#1", "zona A", "Cono #3",
 * "Meta", "zona principal", "Estación 2".
 *
 * Privacy guarantee: this guard prevents accidental entry of minor PII
 * (athlete names / DOB) into diagram labels. It is NOT a comprehensive
 * content filter — it only catches the two most likely accidental patterns.
 */

const DATE_RE =
  /\b\d{1,2}\/\d{1,2}\/\d{4}\b|\b\d{4}-\d{2}-\d{2}\b/;

export const MAX_PHASE_B_LABEL = 40;

/**
 * Returns true when the label triggers the anti-PII heuristic.
 *
 * Call this before allowing a label to be stored in a ComposedElement.
 */
export function isPhaseBLabelPii(label: string): boolean {
  if (label.length > MAX_PHASE_B_LABEL) return true;
  if (DATE_RE.test(label)) return true;
  // Person-name heuristic: ≥ 2 words each starting with an uppercase letter
  // and having ≥ 2 characters total. Numbers/symbols whose char[0] is not a
  // cased letter are excluded via the isCasedUppercase check.
  const capWords = label.split(/\s+/).filter((w) => {
    if (w.length < 2) return false;
    const c = w[0];
    return c === c.toUpperCase() && c !== c.toLowerCase(); // truly uppercase letter
  });
  return capWords.length >= 2;
}

/**
 * Returns a Spanish error message if the label fails the anti-PII check,
 * or null if the label is safe.
 *
 * Suitable for inline field validation in the composer UI.
 */
export function validatePhaseBLabel(label: string): string | null {
  if (!label.trim()) return null; // empty is fine (label is optional)
  if (label.length > MAX_PHASE_B_LABEL) {
    return `La etiqueta no puede superar ${MAX_PHASE_B_LABEL} caracteres.`;
  }
  if (DATE_RE.test(label)) {
    return "La etiqueta no puede contener una fecha (protección de datos de menores).";
  }
  const capWords = label.split(/\s+/).filter((w) => {
    if (w.length < 2) return false;
    const c = w[0];
    return c === c.toUpperCase() && c !== c.toLowerCase();
  });
  if (capWords.length >= 2) {
    return "La etiqueta parece contener un nombre. No incluyas datos personales de deportistas.";
  }
  return null;
}
