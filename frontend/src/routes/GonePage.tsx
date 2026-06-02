import { Link } from "react-router-dom";

/**
 * GonePage — equivalente SPA de un HTTP 410 Gone (PR7, D7).
 *
 * Las rutas legacy del módulo IA (`/coach/race-analysis`,
 * `/training/races/:id/club-insights`) estuvieron activas con redirect 301
 * durante un ciclo completo (PR1-PR7). En PR7 se deprecan definitivamente:
 * en vez de redirigir, mostramos esta página con un enlace al nuevo hub.
 *
 * Props opcionales para personalizar el destino sugerido.
 */
export function GonePage({
  to = "/competitions/insights",
  toLabel = "Ir a Análisis IA",
}: {
  to?: string;
  toLabel?: string;
}) {
  return (
    <div className="flex min-h-[60vh] items-center justify-center bg-white p-4">
      <div
        className="max-w-md rounded-xl bg-white p-8 text-center"
        style={{
          boxShadow:
            "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
        }}
        data-testid="gone-page"
      >
        <h1
          className="text-4xl text-charcoal"
          style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
        >
          Esta sección se movió
        </h1>
        <p className="mt-3 text-sm text-mid-gray">
          El módulo de análisis de carreras ahora vive dentro de Competencias.
          Esta dirección ya no está disponible.
        </p>
        <Link
          to={to}
          className="mt-6 inline-block rounded-lg bg-charcoal px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-70"
          style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
        >
          {toLabel}
        </Link>
      </div>
    </div>
  );
}

export default GonePage;
