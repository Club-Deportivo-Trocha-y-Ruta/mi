/**
 * Constantes compartidas entre `RubricSliders`, `RpeScale` y `AttendanceTable`.
 * Viven en un módulo neutral (sin componentes) para evitar un ciclo de
 * import en tiempo de ejecución: `RubricSliders` usa `RpeScale`, y `RpeScale`
 * necesita estas mismas etiquetas/caritas — si vivieran en `RubricSliders.tsx`
 * (como antes de este rediseño) se formaría un ciclo real (no solo de tipos).
 */

// OMNI 0-10 (Robertson et al.): even indices map validated adult-OMNI anchors;
// odd indices are documented interpolations so every integer shows one word.
// "Moderado" sits at the midpoint (5) per the scientific reference.
export const RPE_LABELS = [
  "Reposo",      // 0
  "Muy fácil",   // 1
  "Fácil",       // 2
  "Ligero",      // 3
  "Algo fácil",  // 4
  "Moderado",    // 5 ← midpoint
  "Algo duro",   // 6
  "Duro",        // 7
  "Muy duro",    // 8
  "Muy muy duro", // 9
  "Máximo",      // 10
];
// Faces aligned: calm/rested (0) → neutral midpoint (5, 😐) → exhausted (10)
export const RPE_FACES = ["😴", "😌", "🙂", "😊", "😀", "😐", "🫤", "😮‍💨", "😤", "😩", "🥵"];

export const RUBRIC_LABELS: Record<number, string> = {
  1: "Muy bajo",
  2: "Bajo",
  3: "Regular",
  4: "Bueno",
  5: "Excelente",
};

// Discrete steps rendered as ToggleGroup options.
export const RPE_VALUES = Array.from({ length: 11 }, (_, i) => i); // 0..10
export const RUBRIC_VALUES = [1, 2, 3, 4, 5];

/**
 * Rampa secuencial de UN solo tono de marca (0 → `--color-primary-light`
 * claro, 10 → `--color-tier-a` oscuro) para la escala de RPE estilo Garmin
 * Connect. Nunca verde-ámbar-rojo: la constitución (`docs/05-design-system`
 * §2) reserva esos tres colores para el vocabulario de ESTADOS, y el RPE es
 * una magnitud de esfuerzo, no un semáforo de éxito/fallo. `color-mix` deja
 * que el navegador interpole entre los dos tokens existentes sin declarar
 * 11 hex nuevos.
 */
export function rpeSegmentColor(n: number): string {
  const pct = Math.round((n / 10) * 100);
  return `color-mix(in oklch, var(--color-tier-a) ${pct}%, var(--color-primary-light))`;
}
