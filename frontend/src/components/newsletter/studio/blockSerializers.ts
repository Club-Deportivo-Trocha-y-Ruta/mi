/**
 * blockSerializers — convierte los bloques narrativos compuestos de la
 * bitácora (`observations`, `analyst_reading`, `family_compass`) hacia y
 * desde texto plano editable en un único `<textarea>` de `BlockCard`
 * (feature 038, T302).
 *
 * `BlockCard` no conoce la forma de cada bloque — solo edita texto. Estas
 * funciones son el puente puro (sin estado, sin I/O) entre esa forma común
 * y los tipos estructurados de `StageOverrides`. Se testean de forma
 * aislada de cualquier componente.
 */
import type {
  AnalystReadingText,
  FamilyCompass,
  Observation,
} from "@/types/stageLog.types";

/** Cuenta de palabras — mismo criterio que los guardrails backend (split por espacios). */
export function countWords(text: string | null | undefined): number {
  if (!text) return 0;
  const trimmed = text.trim();
  if (!trimmed) return 0;
  return trimmed.split(/\s+/).length;
}

// ---------------------------------------------------------------------------
// observations (3 pares claim/evidence — block_ref se preserva del original)
// ---------------------------------------------------------------------------

export function serializeObservations(observations: Observation[]): string {
  return observations
    .map((obs) => `${obs.claim}\n${obs.evidence}`)
    .join("\n\n");
}

/**
 * Reconstruye `Observation[]` a partir del texto editado. Cada bloque
 * separado por línea en blanco es una observación; la primera línea es el
 * `claim`, el resto (unidas) es la `evidence`. `block_ref` no es editable
 * por el coach — se preserva por índice del arreglo original (o
 * `"attendance"` si el coach agregó una observación de más).
 */
export function parseObservations(
  text: string,
  original: Observation[],
): Observation[] {
  const chunks = text
    .split(/\n\s*\n/)
    .map((chunk) => chunk.trim())
    .filter(Boolean);

  return chunks.map((chunk, index) => {
    const [claim, ...rest] = chunk.split("\n");
    const evidence = rest.join(" ").trim();
    return {
      claim: (claim ?? "").trim(),
      evidence,
      block_ref: original[index]?.block_ref ?? "attendance",
    };
  });
}

// ---------------------------------------------------------------------------
// analyst_reading (headline_family + action_family)
// ---------------------------------------------------------------------------

const ANALYST_HEADLINE_PREFIX = "Titular: ";
const ANALYST_ACTION_PREFIX = "Acción: ";

export function serializeAnalystReading(
  reading: AnalystReadingText | { headline_family: string; action_family: string } | null,
): string {
  if (!reading) return "";
  return `${ANALYST_HEADLINE_PREFIX}${reading.headline_family}\n${ANALYST_ACTION_PREFIX}${reading.action_family}`;
}

export function parseAnalystReading(text: string): AnalystReadingText {
  const lines = text.split("\n");
  const headlineLine = lines.find((l) => l.startsWith(ANALYST_HEADLINE_PREFIX));
  const actionLine = lines.find((l) => l.startsWith(ANALYST_ACTION_PREFIX));
  return {
    headline_family: (headlineLine ?? "").replace(ANALYST_HEADLINE_PREFIX, "").trim(),
    action_family: (actionLine ?? "").replace(ANALYST_ACTION_PREFIX, "").trim(),
  };
}

// ---------------------------------------------------------------------------
// family_compass (conversation_question + monthly_challenge + what_to_watch)
// ---------------------------------------------------------------------------

const COMPASS_QUESTION_PREFIX = "Pregunta: ";
const COMPASS_CHALLENGE_PREFIX = "Reto del mes: ";
const COMPASS_WATCH_PREFIX = "Qué observar: ";

export function serializeFamilyCompass(compass: FamilyCompass | null): string {
  if (!compass) return "";
  return [
    `${COMPASS_QUESTION_PREFIX}${compass.conversation_question}`,
    `${COMPASS_CHALLENGE_PREFIX}${compass.monthly_challenge}`,
    `${COMPASS_WATCH_PREFIX}${compass.what_to_watch}`,
  ].join("\n");
}

export function parseFamilyCompass(text: string): FamilyCompass {
  const lines = text.split("\n");
  const find = (prefix: string) =>
    (lines.find((l) => l.startsWith(prefix)) ?? "").replace(prefix, "").trim();
  return {
    conversation_question: find(COMPASS_QUESTION_PREFIX),
    monthly_challenge: find(COMPASS_CHALLENGE_PREFIX),
    what_to_watch: find(COMPASS_WATCH_PREFIX),
  };
}
