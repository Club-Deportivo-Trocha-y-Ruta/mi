/**
 * AppErrorFallback — fallback de top-level ErrorBoundary.
 *
 * Visible solo cuando una excepción no atrapada burbujea hasta la raíz
 * de la app (errores de render, hooks, etc.). Errores de red de TanStack
 * Query se manejan en cada hook/componente y NO disparan este fallback.
 *
 * Diseño:
 *  - Mensaje en español, neutral (no técnico).
 *  - Botón primario "Reintentar" → resetErrorBoundary() vuelve a renderizar
 *    el árbol descendiente; si la causa era un transitorio, se recupera.
 *  - Link secundario "Reportar" abre un `mailto:` (placeholder) — el equipo
 *    puede sustituirlo por un endpoint real cuando exista.
 */
import type { FallbackProps } from "react-error-boundary";

import { Button } from "@/components/ui/button";

const REPORT_EMAIL = "soporte@trochyruta.com";

export function AppErrorFallback({
  error,
  resetErrorBoundary,
}: FallbackProps) {
  const subject = encodeURIComponent("Reporte de error en la app");
  const body = encodeURIComponent(
    `Hola equipo,\n\nOcurrió un error inesperado.\n\nDetalle técnico (no editar):\n${
      error instanceof Error ? error.message : String(error)
    }\n\nGracias.`,
  );

  return (
    <div
      role="alert"
      aria-live="assertive"
      className="flex min-h-[60vh] flex-col items-center justify-center gap-6 px-4 text-center"
    >
      <div className="max-w-md space-y-3">
        <h1 className="text-2xl font-semibold text-charcoal">
          Ha ocurrido un error inesperado
        </h1>
        <p className="text-sm text-mid-gray">
          La aplicación encontró un problema. Puedes reintentar o reportar
          lo sucedido al equipo de soporte para ayudarnos a corregirlo.
        </p>
      </div>

      <div className="flex flex-col items-center gap-3">
        <Button onClick={resetErrorBoundary}>Reintentar</Button>
        <a
          href={`mailto:${REPORT_EMAIL}?subject=${subject}&body=${body}`}
          className="text-sm text-link-blue underline-offset-4 hover:underline"
        >
          Reportar al equipo
        </a>
      </div>
    </div>
  );
}
