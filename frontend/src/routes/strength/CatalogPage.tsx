/**
 * CatalogPage — página principal del catálogo de Fuerza y Acondicionamiento
 * (feature 021 / T017, US1).
 *
 * Compone:
 *   - FilterBar    → controla los filtros (estado local)
 *   - CatalogGrid  → consume useStrengthCatalog con los filtros activos y
 *                    resuelve loading/empty/error internamente
 *
 * Coach/admin only (gating en App.tsx via ProtectedRoute). Catálogo estático
 * curado — no hay creación/edición desde la UI en v1 (FR-018, mirror 018).
 * La URL no codifica los filtros; se reinician al navegar fuera y volver.
 *
 * "Armar bloque" (feature 030 / T022, US2, FR-007) — nueva entrada directa
 * al armador de bloques de fuerza (`/strength/blocks/new`), antes solo
 * alcanzable desde el detalle de una sesión de entrenamiento.
 */
import { useCallback, useState } from "react";
import { Plus } from "lucide-react";
import { Link } from "react-router-dom";

import { CatalogGrid } from "@/components/strength/CatalogGrid";
import { FilterBar } from "@/components/strength/FilterBar";
import type { StrengthCatalogFilters } from "@/components/strength/FilterBar";
import { useStrengthCatalog } from "@/hooks/strength/useStrength";

// ---------------------------------------------------------------------------
// Helper — at least one filter is active
// ---------------------------------------------------------------------------

function hasFilters(f: StrengthCatalogFilters): boolean {
  return !!(f.q || f.equipment || f.age_band || f.movement_category);
}

/**
 * The club's dosing rules keep gym-equipment work out of the 10-12 band
 * (see data-model.md), so this combination is a known-sparse/empty result
 * — not a bug. Used to swap the empty-state copy in CatalogGrid.
 */
function isSparseKnownCombo(f: StrengthCatalogFilters): boolean {
  return f.equipment === "equipo_gym" && f.age_band === "10-12";
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function CatalogPage() {
  const [filters, setFilters] = useState<StrengthCatalogFilters>({});

  const { data, isLoading, isFetching, isError, error } =
    useStrengthCatalog(filters);

  const handleFiltersChange = useCallback((next: StrengthCatalogFilters) => {
    setFilters(next);
  }, []);

  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      {/* Page header */}
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold text-slate-900">
            Biblioteca de fuerza y acondicionamiento
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Explora y filtra ejercicios de fortalecimiento ilustrados, con y sin
            equipo, para armar bloques adaptados a cada grupo de edad.
          </p>
        </div>

        {/* Entrada directa al armador de bloques (feature 030, FR-007) */}
        <Link
          to="/strength/blocks/new"
          className="inline-flex min-h-12 shrink-0 items-center gap-2 rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70 shadow-button-highlight"
        >
          <Plus size={16} aria-hidden="true" />
          Armar bloque
        </Link>
      </div>

      {/* Filter controls */}
      <div className="mb-5">
        <FilterBar onChange={handleFiltersChange} />
      </div>

      {/* Catalog grid — all async states handled inside */}
      <CatalogGrid
        items={data?.items}
        total={data?.total}
        isLoading={isLoading}
        isFetching={isFetching}
        isError={isError}
        error={error}
        hasActiveFilters={hasFilters(filters)}
        isSparseKnownCombo={isSparseKnownCombo(filters)}
      />
    </div>
  );
}

export default CatalogPage;
