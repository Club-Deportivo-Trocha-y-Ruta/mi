/**
 * Alias de URL de la pestaña única «Carreras» (feature 045, T041/T045).
 *
 * Antes existían dos pestañas — «Insights IA» (`ai_analysis` en la vista
 * coach, `ai-analysis` en la familiar) y «Carreras» (`races`). Ahora hay UNA
 * sola (`tab=races`) con tres vistas (`view=progresion|analisis|comparar`) y
 * un análisis expandible (`insight=<id>`). Los enlaces viejos (correos ya
 * enviados, marcadores, notificaciones) siguen llegando con el `tab`
 * anterior: estas utilidades los traducen a la URL canónica.
 *
 * Contrato: `specs/045-competitions-one-place/contracts/ui-routes.md`.
 *
 * Las dos páginas (`AthleteDetailPage`, `MyAthleteDetailPage`) aceptan AMBAS
 * grafías en ambos roles: es inofensivo y evita un 404 silencioso si un
 * enlace de un rol cruza al otro.
 */

/** Claves de pestaña legadas que hoy equivalen a «Carreras › Análisis IA». */
const LEGACY_AI_TAB_KEYS: readonly string[] = ["ai_analysis", "ai-analysis"];

/** Clave canónica de la pestaña «Carreras» en la URL (`?tab=races`). */
export const CARRERAS_TAB_KEY = "races";

/**
 * Si `tab` es un alias legado de «Insights IA», devuelve los parámetros
 * canónicos `tab=races&view=analisis[&insight=<id>]` (conservando cualquier
 * otro parámetro); si no, `null` (la URL ya es canónica o no aplica).
 *
 * El orden es determinista (`tab`, `view`, `insight`, resto) para que la URL
 * resultante sea igual a la del contrato y a la de los correos nuevos.
 */
export function resolveLegacyAiTabAlias(
  params: URLSearchParams,
): URLSearchParams | null {
  const tab = params.get("tab");
  if (tab === null || !LEGACY_AI_TAB_KEYS.includes(tab)) return null;

  const next = new URLSearchParams();
  next.set("tab", CARRERAS_TAB_KEY);
  next.set("view", "analisis");
  const insight = params.get("insight");
  if (insight) next.set("insight", insight);
  params.forEach((value, key) => {
    if (key !== "tab" && key !== "view" && key !== "insight") {
      next.append(key, value);
    }
  });
  return next;
}

/** Parámetros propios de «Carreras»: solo tienen sentido con `tab=races`. */
export function dropCarrerasParams(params: URLSearchParams): void {
  params.delete("view");
  params.delete("insight");
}
