import { useState } from "react";
import { AlertCircle, Clock, Loader2, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * ErrorState — bloque reutilizable para fallos de carga, con una variante
 * "cold start" (backend Render Free despertando) que usa tono calmado en vez
 * de tono de error. Reemplaza los bloques ad hoc (CatalogGrid, RosterError,
 * párrafos rojos sueltos) unificando copy, tono y el botón "Reintentar" con
 * spinner accesible.
 */
interface ErrorStateProps {
  /** Copy amigable en es-CO; los errores técnicos crudos nunca se renderizan. */
  message?: string;
  /** Si se pasa, renderiza el botón "Reintentar" (con spinner mientras corre). */
  onRetry?: () => void | Promise<void>;
  /** Renderiza la variante "el servidor está despertando" en vez de error. */
  isColdStart?: boolean;
}

const DEFAULT_ERROR_MESSAGE = "No se pudo cargar la información.";
const DEFAULT_COLD_START_MESSAGE =
  "La aplicación está iniciando, puede tardar unos segundos. Intenta de nuevo en un momento.";

export function ErrorState({ message, onRetry, isColdStart = false }: ErrorStateProps) {
  const [isRetrying, setIsRetrying] = useState(false);

  const displayMessage = message ?? (isColdStart ? DEFAULT_COLD_START_MESSAGE : DEFAULT_ERROR_MESSAGE);

  async function handleRetry() {
    if (!onRetry || isRetrying) return;
    setIsRetrying(true);
    try {
      await onRetry();
    } finally {
      setIsRetrying(false);
    }
  }

  return (
    <div
      role={isColdStart ? "status" : "alert"}
      aria-live={isColdStart ? "polite" : undefined}
      className={cn(
        "rounded-xl border px-6 py-10 text-center",
        isColdStart ? "border-warning/30 bg-warning/10" : "border-danger/30 bg-danger/10",
      )}
    >
      {isColdStart ? (
        <Clock size={40} className="mx-auto mb-3 text-warning" aria-hidden="true" />
      ) : (
        <AlertCircle size={40} className="mx-auto mb-3 text-danger" aria-hidden="true" />
      )}

      <p className="text-sm font-medium text-charcoal">{displayMessage}</p>

      {onRetry && (
        <div className="mt-4">
          <Button
            type="button"
            variant="outline"
            size="lg"
            onClick={() => void handleRetry()}
            disabled={isRetrying}
          >
            {isRetrying ? (
              <Loader2 size={16} className="animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCw size={16} aria-hidden="true" />
            )}
            Reintentar
          </Button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// isColdStartError
// ---------------------------------------------------------------------------

/**
 * Heurística centralizada de "cold start" (Render Free duerme tras ~15 min de
 * inactividad y tarda hasta ~60s en responder). Generaliza `resolveErrorMessage`
 * (frontend/src/components/strength/CatalogGrid.tsx), que solo miraba texto de
 * `Error.message`, sumando:
 *   1. La misma búsqueda por texto, pero tolerando cualquier `err` con un
 *      `message` legible (string plano, `Error`, o un objeto con `.message`),
 *      no solo instancias de `Error`.
 *   2. Una vía por forma: un error de axios/XHR que salió (`request`) pero
 *      nunca recibió respuesta (`response` ausente) — típico de un backend
 *      dormido o inalcanzable aunque el mensaje no contenga ninguna palabra
 *      clave (p. ej. mensajes de red traducidos por el navegador). No
 *      requiere importar axios: se detecta por duck-typing.
 * Las cancelaciones explícitas (`AbortController`, navegación fuera) nunca
 * cuentan como cold start.
 */
export function isColdStartError(err: unknown): boolean {
  const message = extractMessage(err).toLowerCase();
  if (
    message.includes("timeout") ||
    message.includes("network") ||
    message.includes("503") ||
    message.includes("502")
  ) {
    return true;
  }
  return looksLikeUnansweredRequest(err);
}

function extractMessage(err: unknown): string {
  if (typeof err === "string") return err;
  if (err instanceof Error) return err.message;
  if (err && typeof err === "object" && typeof (err as { message?: unknown }).message === "string") {
    return (err as { message: string }).message;
  }
  return "";
}

function looksLikeUnansweredRequest(err: unknown): boolean {
  if (!err || typeof err !== "object") return false;

  const candidate = err as {
    isAxiosError?: boolean;
    code?: string;
    name?: string;
    request?: unknown;
    response?: unknown;
  };

  // Cancelaciones (AbortController, navegación fuera de la vista) no son cold start.
  if (candidate.code === "ERR_CANCELED" || candidate.name === "CanceledError") {
    return false;
  }

  const looksLikeRequestError = candidate.isAxiosError === true || "request" in candidate;
  return looksLikeRequestError && !candidate.response;
}
