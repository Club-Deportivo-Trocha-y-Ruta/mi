/**
 * CatalogPage — página principal del catálogo de técnica y gymkhana (US1).
 *
 * Compone:
 *   - FilterBar         → controla los filtros (estado local)
 *   - CatalogGrid       → consume useTechniqueCatalog con los filtros activos
 *   - ExerciseFormDialog → abre en modo "crear" desde el botón "Nuevo ejercicio"
 *                          o en modo "editar" desde el affordance en la tarjeta
 *
 * Coach/admin only (gating en App.tsx via ProtectedRoute).
 * La URL no codifica los filtros (no es necesario para v1); los filtros
 * se reinician al navegar fuera y volver.
 */
import { useCallback, useState } from "react";
import { Plus } from "lucide-react";

import { CatalogGrid } from "@/components/technique/CatalogGrid";
import { ExerciseFormDialog } from "@/components/technique/ExerciseFormDialog";
import { FilterBar } from "@/components/technique/FilterBar";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/store/auth.store";
import { useTechniqueCatalog } from "@/hooks/technique/useTechnique";
import type { CatalogFilters, ExerciseListItem } from "@/types/technique.types";
import { UserRole } from "@/types/enums";

// ---------------------------------------------------------------------------
// Helper — at least one filter is active
// ---------------------------------------------------------------------------

function hasFilters(f: CatalogFilters): boolean {
  return !!(
    f.skill ||
    f.age_band ||
    f.difficulty ||
    f.materials
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function CatalogPage() {
  const user = useAuthStore((s) => s.user);
  const canCurate =
    user?.role === UserRole.coach || user?.role === UserRole.admin;

  const [filters, setFilters] = useState<CatalogFilters>({});

  const { data, isLoading, isFetching, isError, error } =
    useTechniqueCatalog(filters);

  // Dialog state — null = closed; undefined exerciseId = create mode;
  // non-null exerciseId = edit mode.
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<ExerciseListItem | null>(null);

  const handleFiltersChange = useCallback((next: CatalogFilters) => {
    setFilters(next);
  }, []);

  function openCreate() {
    setEditTarget(null);
    setDialogOpen(true);
  }

  const handleEdit = useCallback((exercise: ExerciseListItem) => {
    setEditTarget(exercise);
    setDialogOpen(true);
  }, []);

  function handleDialogClose(open: boolean) {
    setDialogOpen(open);
    if (!open) setEditTarget(null);
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      {/* Page header */}
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold text-slate-900">
            Biblioteca de técnica y gymkhana
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Explora y filtra los ejercicios técnicos para planificar sesiones de
            entrenamiento adaptadas a cada grupo de edad.
          </p>
        </div>

        {/* Curation CTA — coach/admin only */}
        {canCurate && (
          <Button
            onClick={openCreate}
            className="min-h-12 shrink-0 gap-2"
            aria-label="Crear nuevo ejercicio en el catálogo"
          >
            <Plus size={16} aria-hidden="true" />
            Nuevo ejercicio
          </Button>
        )}
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
        onEdit={canCurate ? handleEdit : undefined}
      />

      {/* Exercise form dialog (create / edit) */}
      {canCurate && (
        <ExerciseFormDialog
          open={dialogOpen}
          onOpenChange={handleDialogClose}
          exerciseId={editTarget?.id}
          defaultValues={editTarget ?? undefined}
        />
      )}
    </div>
  );
}

export default CatalogPage;
