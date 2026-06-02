/**
 * InsightsHubPage — índice slim de análisis IA de carreras.
 *
 * Ruta: /competitions/insights
 * Acceso: coach + admin (parents → redirect por ProtectedRoute).
 *
 * Vista read-only: no lanza análisis, no monta chat, no muestra import.
 * Únicamente enlaza a las dos vistas cross-válida disponibles:
 *   - Panorama de temporada (/competitions/insights/season/:year)
 *   - Análisis por válida   (/competitions/insights/club)
 *
 * Privacidad: no expone datos de atletas; las subpáginas aplican RBAC.
 */
import { Link } from "react-router-dom";
import { BarChart2, Calendar } from "lucide-react";

// Año de temporada activa. Si en el futuro la temporada cambia, actualizar aquí.
const CURRENT_SEASON = 2026;

// ---------------------------------------------------------------------------
// Constante de estilo (alineada con CompetitionsListPage y SeasonInsightsPage)
// ---------------------------------------------------------------------------

const cardStyle = {
  boxShadow:
    "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
};

// ---------------------------------------------------------------------------
// Componente
// ---------------------------------------------------------------------------

export function InsightsHubPage() {
  return (
    <section className="space-y-6">
      {/* Header */}
      <div>
        <h1
          className="text-2xl text-charcoal"
          style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
        >
          Análisis IA carreras
        </h1>
        <p className="mt-0.5 text-sm text-mid-gray">
          Vistas agregadas de rendimiento por temporada y por válida.
        </p>
      </div>

      {/* Grid de accesos */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {/* Card: Panorama de temporada */}
        <Link
          to={`/competitions/insights/season/${CURRENT_SEASON}`}
          className="group flex flex-col gap-3 rounded-xl bg-white p-6 transition-colors hover:ring-2 hover:ring-charcoal/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-charcoal"
          style={cardStyle}
          aria-label="Ir a Panorama de temporada"
          data-testid="hub-card-season"
        >
          <div
            className="flex h-10 w-10 items-center justify-center rounded-lg bg-charcoal/8"
            aria-hidden="true"
          >
            <Calendar size={20} className="text-charcoal" />
          </div>
          <div>
            <p
              className="text-base font-semibold text-charcoal"
              style={{ fontFamily: "'Cal Sans', system-ui, sans-serif" }}
            >
              Panorama de temporada
            </p>
            <p className="mt-1 text-sm text-mid-gray">
              Tabla longitudinal de resultados por deportista en la temporada{" "}
              {CURRENT_SEASON}: válidas corridas, podios, puntos acumulados y
              mejor posición.
            </p>
          </div>
          <span
            className="mt-auto text-xs font-medium text-charcoal transition-opacity group-hover:opacity-70"
            aria-hidden="true"
          >
            Ver temporada {CURRENT_SEASON} →
          </span>
        </Link>

        {/* Card: Análisis por válida */}
        <Link
          to="/competitions/insights/club"
          className="group flex flex-col gap-3 rounded-xl bg-white p-6 transition-colors hover:ring-2 hover:ring-charcoal/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-charcoal"
          style={cardStyle}
          aria-label="Ir a Análisis por válida"
          data-testid="hub-card-club"
        >
          <div
            className="flex h-10 w-10 items-center justify-center rounded-lg bg-charcoal/8"
            aria-hidden="true"
          >
            <BarChart2 size={20} className="text-charcoal" />
          </div>
          <div>
            <p
              className="text-base font-semibold text-charcoal"
              style={{ fontFamily: "'Cal Sans', system-ui, sans-serif" }}
            >
              Análisis por válida
            </p>
            <p className="mt-1 text-sm text-mid-gray">
              Grid de insights IA por deportista para una válida específica.
              Selecciona la válida y consulta el análisis generado.
            </p>
          </div>
          <span
            className="mt-auto text-xs font-medium text-charcoal transition-opacity group-hover:opacity-70"
            aria-hidden="true"
          >
            Seleccionar válida →
          </span>
        </Link>
      </div>
    </section>
  );
}
