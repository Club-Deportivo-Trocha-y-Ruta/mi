/**
 * Copy compartida de "en progreso" para las dos tarjetas de IA
 * (`PHVExplanationCard`, `AnthropometricRecordExplanationCard`) mientras
 * corre una generación (feature 042, T059).
 *
 * El backend vive en el free tier de Render: un cold start ronda ~50 s y un
 * análisis del coach ya arrancado toma 20-40 s. Sin un mensaje que escale
 * con el tiempo transcurrido, una espera normal se ve como un cuelgue. Esta
 * función es pura (solo recibe milisegundos transcurridos, sin timers ni
 * efectos) para poder probarla con `it.each` sin `vi.useFakeTimers()`.
 */

/** Tarjeta que consume el mensaje — solo cambia la frase inicial (antes del
 *  primer umbral), que describe la acción en curso de cada una. */
export type PendingMessageKind = "phv" | "measurement";

/** A partir de acá el mensaje avisa que el proveedor de IA está trabajando
 *  (todavía no es cold start; una llamada normal cae en este rango). */
const SLOW_THRESHOLD_MS = 20_000;

/** A partir de acá se asume que Render está despertando el contenedor
 *  (cold start del free tier, ~50 s). */
const COLD_START_THRESHOLD_MS = 55_000;

/** Espera ya larga incluso para un cold start — el mensaje deja explícito
 *  que seguir esperando es normal y no un error, para que nadie recargue la
 *  página a mitad de una generación en curso. */
const EXTENDED_WAIT_THRESHOLD_MS = 90_000;

const STARTING_MESSAGE: Record<PendingMessageKind, string> = {
  phv: "Generando explicación…",
  measurement: "Analizando esta medición…",
};

/**
 * Mensaje a mostrar para `elapsedMs` transcurridos desde que arrancó la
 * generación. `kind` (default `"phv"`) solo afecta la frase antes del
 * primer umbral — de ahí en adelante el mensaje es el mismo para ambas
 * tarjetas, porque a esa altura la espera ya no depende de cuál tarjeta es.
 */
export function pendingMessage(
  elapsedMs: number,
  kind: PendingMessageKind = "phv",
): string {
  if (elapsedMs >= EXTENDED_WAIT_THRESHOLD_MS) {
    return "Sigue en proceso — puede tardar hasta un par de minutos, no es necesario recargar la página.";
  }
  if (elapsedMs >= COLD_START_THRESHOLD_MS) {
    return "El servidor está despertando, esto puede tardar un minuto…";
  }
  if (elapsedMs >= SLOW_THRESHOLD_MS) {
    return "Consultando modelo de IA (puede tardar hasta 30 s)…";
  }
  return STARTING_MESSAGE[kind];
}
