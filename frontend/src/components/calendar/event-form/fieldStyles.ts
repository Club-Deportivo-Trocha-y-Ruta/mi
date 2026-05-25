/**
 * Clases compartidas entre los sub-componentes `*Fields` del EventForm.
 * Mantener un único punto evita drift entre secciones.
 */
export const labelClass = "block text-sm font-medium text-charcoal";
export const inputClass =
  "mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 shadow-ring";
export const errorClass = "mt-1 text-xs text-red-600";

export const INTENSITY_OPTIONS = [
  { value: "low", label: "Baja" },
  { value: "medium", label: "Media" },
  { value: "high", label: "Alta" },
] as const;

export const COMPETITION_CATEGORIES = [
  { value: "A", label: "A — Tapering completo" },
  { value: "B", label: "B — Mini-tapering" },
  { value: "C", label: "C — Diagnóstica" },
] as const;
