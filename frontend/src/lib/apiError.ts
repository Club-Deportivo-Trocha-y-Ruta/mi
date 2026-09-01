/**
 * apiError — extracción centralizada del detalle humano de un error de API.
 *
 * Feature 036 (T045): unifica dos implementaciones duplicadas del mismo
 * cálculo (`SeasonSummaryButton.tsx` lo tenía correcto; `LaunchAnalysisForm.tsx`
 * solo hacía `err instanceof Error ? err.message : …`). Como `AxiosError`
 * extiende `Error`, esa rama SIEMPRE gana y esconde el `detail` en español
 * que el backend arma con cuidado (ej. los 409 de run activo / dedup de
 * resumen de temporada) detrás del genérico "Request failed with status
 * code 409".
 *
 * Prioridad de resolución:
 *   1. Cold start (Render Free despertando) — un timeout/502/503/petición
 *      sin respuesta no trae `response.data`, así que se resuelve ANTES
 *      que el detail y devuelve la copy calmada (mismo tono que
 *      `ErrorState` isColdStart) en vez de un mensaje técnico de red.
 *   2. `response.data.detail` como string — el caso feliz: detail en
 *      español armado por el backend (`HTTPException(detail=...)`).
 *   3. `response.data.detail` como array — error de validación Pydantic
 *      (`[{msg, loc, type}, …]`); se usa el primer `msg`.
 *   4. `err.message` no vacío — network errors sin `isAxiosError` (fetch
 *      nativo, etc.) o cualquier otro `Error`.
 *   5. `fallback` provisto por el caller.
 */
import { isColdStartError } from "@/components/shared/ErrorState";

const DEFAULT_FALLBACK = "Ocurrió un error. Intenta de nuevo.";

const COLD_START_MESSAGE =
  "La aplicación está iniciando, puede tardar unos segundos. Intenta de nuevo en un momento.";

export function extractErrorDetail(
  err: unknown,
  fallback: string = DEFAULT_FALLBACK,
): string {
  if (isColdStartError(err)) return COLD_START_MESSAGE;

  if (err && typeof err === "object") {
    const anyErr = err as {
      response?: { data?: { detail?: unknown } };
      message?: string;
    };
    const detail = anyErr.response?.data?.detail;
    if (typeof detail === "string" && detail.trim().length > 0) return detail;
    // FastAPI/Pydantic validation: detail es array de {msg, loc, type}.
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: unknown };
      if (typeof first?.msg === "string" && first.msg.trim().length > 0) {
        return `Datos inválidos: ${first.msg}`;
      }
    }
    if (typeof anyErr.message === "string" && anyErr.message.trim().length > 0) {
      return anyErr.message;
    }
  }

  if (typeof err === "string" && err.trim().length > 0) return err;

  return fallback;
}
