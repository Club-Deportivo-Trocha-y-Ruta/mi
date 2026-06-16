/**
 * raceOptionLabel.ts — Helpers de identidad/etiqueta para el picker de
 * distribución de resultados (feature 016).
 *
 * # Representación elegida para los valores de <select>
 *
 * Un `<select>` HTML maneja *siempre* valores de tipo `string`. Para evitar
 * colisiones entre el sentinela "toda la temporada" y cualquier `event_id`
 * real (enteros positivos >= 1), se usa el siguiente esquema:
 *
 *   - Opción agregada  → string literal `"season-aggregate"`
 *   - Opción por carrera → `String(eventId)`  (ej. `"21"`)
 *
 * `"season-aggregate"` no puede colidir con un `event_id` numérico porque
 * `Number("season-aggregate")` es `NaN` y ningún id de BD es NaN. Tampoco
 * coincide con `"0"`, `"-1"` ni con ningún número negativo que alguien pudiera
 * usar como sentinel alternativo, lo que hace la intención inequívoca.
 *
 * Módulo puro: sin React, sin I/O, sin efectos secundarios.
 */

// ---------------------------------------------------------------------------
// Sentinel
// ---------------------------------------------------------------------------

/**
 * Valor estable usado como `value` en la opción "Temporada (todas)" del picker.
 * No puede colisionar con ningún `event_id` real (enteros >= 1).
 */
export const SEASON_AGGREGATE = "season-aggregate" as const;

/** Tipo del valor de opción del picker (sentinel o id de evento serializado). */
export type RaceOptionValue = typeof SEASON_AGGREGATE | string;

// ---------------------------------------------------------------------------
// Guards y etiquetas
// ---------------------------------------------------------------------------

/**
 * Devuelve `true` si el valor dado corresponde a la opción agregada de
 * temporada, `false` si es un valor de carrera concreta.
 *
 * Rama 1 (aggregate): `value === SEASON_AGGREGATE`
 * Rama 2 (race):      cualquier otro string (incluye `"21"`, `"3"`, etc.)
 */
export function isAggregateOption(value: RaceOptionValue): boolean {
  return value === SEASON_AGGREGATE;
}

/**
 * Etiqueta en español neutro (Colombia) para la opción de temporada completa.
 */
export function aggregateLabel(): string {
  return "Temporada (todas)";
}

// ---------------------------------------------------------------------------
// Serialización / deserialización de event_id
// ---------------------------------------------------------------------------

/**
 * Devuelve la clave string estable para una opción de carrera concreta,
 * usando el `event_id` como base.
 *
 * Ejemplos:
 *   `raceOptionValue(21)`  → `"21"`
 *   `raceOptionValue(1)`   → `"1"`
 *
 * El valor resultante es idempotente al pasar por un `<select>` value y
 * nunca coincide con `SEASON_AGGREGATE`.
 */
export function raceOptionValue(eventId: number): string {
  return String(eventId);
}

/**
 * Convierte un valor de opción del picker de vuelta a su `event_id` numérico.
 *
 * - Si `value` es el sentinel agregado  → `null`
 * - Si `value` es un id serializado     → el número correspondiente
 *
 * Usado por el picker (T022) para decidir si debe lanzar una petición de
 * carrera específica o no.
 *
 * Rama 1 (aggregate): devuelve `null`
 * Rama 2 (race id):   parsea con `Number()`; devuelve el entero
 */
export function parseEventId(value: RaceOptionValue): number | null {
  if (isAggregateOption(value)) {
    return null;
  }
  return Number(value);
}
