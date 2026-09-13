/**
 * Copy pasiva compartida por las dos tarjetas de IA de solo lectura para
 * padres (`PHVExplanationCard`, `AnthropometricRecordExplanationCard`)
 * cuando el atleta todavía no tiene un análisis aprobado que mostrar
 * (feature 042, FR-033). Una sola constante evita que las dos copias del
 * mismo mensaje diverjan con el tiempo.
 *
 * Nunca debe insinuar la existencia de un análisis bloqueado (`flagged`,
 * `fallback` o `skipped`): esos veredictos ya quedan fuera de la respuesta
 * que recibe una familia, así que este mensaje es el único texto que un
 * padre puede ver en ese caso — indistinguible de "todavía no se generó
 * nada".
 */
export const AI_ANALYSIS_NOT_YET_AVAILABLE_MESSAGE =
  "Todavía no hay un análisis disponible. El entrenador lo generará pronto.";
