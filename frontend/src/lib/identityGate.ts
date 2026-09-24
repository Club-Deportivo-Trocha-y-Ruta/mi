/**
 * Candado de identidad por carga (feature 045, `contracts/api.md`).
 *
 * `POST /imports/{id}/commit` y `…/commit-pending` responden `409` con un
 * cuerpo PLANO cuando esta carga tiene decisiones de identidad pendientes:
 *
 *   {"detail": "identity_pending", "pending_for_import": 3,
 *    "review_path": "/competitions/imports?seccion=identidades&import=<id>"}
 *
 * Reemplaza al viejo cuerpo anidado (`detail` como objeto con un `code` y un
 * conteo global de la cola), que ya no existe.
 * Este módulo es el único lugar que conoce esa forma: el wizard y el tablero
 * de cargas la consumen a través de `getIdentityPendingInfo`.
 */

export interface IdentityPendingInfo {
  /** Decisiones pendientes que involucran a ESTA carga. */
  pending: number;
  /** Ruta interna para resolverlas (conserva `import=<id>` para volver). */
  reviewPath: string;
}

/** Ruta de respaldo si el backend no manda un `review_path` interno válido. */
const FALLBACK_REVIEW_PATH = "/competitions/imports?seccion=identidades";

/**
 * Lee el `409 identity_pending` de un error de axios. Devuelve `null` para
 * cualquier otro error (incluido el viejo shape anidado, que ya no existe).
 */
export function getIdentityPendingInfo(err: unknown): IdentityPendingInfo | null {
  if (typeof err !== "object" || err === null) return null;
  const response = (err as { response?: { status?: number; data?: unknown } })
    .response;
  if (response?.status !== 409) return null;
  const data = response.data;
  if (typeof data !== "object" || data === null) return null;
  const body = data as {
    detail?: unknown;
    pending_for_import?: unknown;
    review_path?: unknown;
  };
  if (body.detail !== "identity_pending") return null;

  const pending =
    typeof body.pending_for_import === "number" ? body.pending_for_import : 0;
  // Solo rutas internas: un `review_path` externo o relativo al protocolo no
  // se enlaza (evita un redirect abierto si la respuesta fuera manipulada).
  const reviewPath =
    typeof body.review_path === "string" &&
    body.review_path.startsWith("/") &&
    !body.review_path.startsWith("//")
      ? body.review_path
      : FALLBACK_REVIEW_PATH;
  return { pending, reviewPath };
}

/** Copy del bloqueo (`contracts/ui-copy.md` §Identity gate). */
export function identityGateMessage(pending: number): string {
  const decisiones =
    pending === 1
      ? "1 decisión de identidad pendiente"
      : `${pending} decisiones de identidad pendientes`;
  return `Hay ${decisiones} para esta carga. Resuélvelas en «Cargas e identidades» y vuelve: tu carga queda guardada.`;
}
