/**
 * CatalogPage — página principal del catálogo de técnica y gymkhana (US1).
 *
 * Compone:
 *   - FilterBar          → controla los filtros (estado local)
 *   - CatalogGrid         → consume useTechniqueCatalog con los filtros activos
 *   - ExerciseFormDialog  → abre en modo "crear" desde el botón "Nuevo ejercicio"
 *                           o en modo "editar" desde el affordance en la tarjeta
 *   - SessionPickerDialog → "Adjuntar a una sesión" (feature 032, T017): el
 *                           punto de entrada #2 iniciado desde la biblioteca
 *                           (contracts/unified-attach-flow.md). Adjunta el
 *                           ejercicio elegido directamente — nunca navega ni
 *                           crea una sesión — y ofrece un enlace "Ver en la
 *                           sesión" al terminar.
 *
 * Coach/admin only (gating en App.tsx via ProtectedRoute).
 * La URL no codifica los filtros (no es necesario para v1); los filtros
 * se reinician al navegar fuera y volver.
 */
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, Plus } from "lucide-react";

import { CatalogGrid } from "@/components/technique/CatalogGrid";
import { ExerciseFormDialog } from "@/components/technique/ExerciseFormDialog";
import { FilterBar } from "@/components/technique/FilterBar";
import { SessionPickerDialog } from "@/components/training/session-plan/SessionPickerDialog";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/store/auth.store";
import { mapTechniqueError } from "@/api/technique";
import {
  useAttachTechniqueItems,
  useTechniqueCatalog,
} from "@/hooks/technique/useTechnique";
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

  // -------------------------------------------------------------------------
  // "Adjuntar a una sesión" — entry point #2, feature 032, T017.
  // -------------------------------------------------------------------------

  const [attachPickerOpen, setAttachPickerOpen] = useState(false);
  const [attachTarget, setAttachTarget] = useState<ExerciseListItem | null>(
    null,
  );
  // Set once a session is chosen — carries the exact sessionId the mutation
  // hook (T014) below must be built against for this attach attempt.
  const [pendingAttach, setPendingAttach] = useState<{
    sessionId: number;
    exercise: ExerciseListItem;
  } | null>(null);
  const [attachError, setAttachError] = useState<string | null>(null);
  const [attachedTo, setAttachedTo] = useState<{
    sessionId: number;
    exerciseName: string;
  } | null>(null);

  const attachMutation = useAttachTechniqueItems(pendingAttach?.sessionId ?? 0);

  function handleAttachClick(exercise: ExerciseListItem) {
    setAttachTarget(exercise);
    setAttachError(null);
    setAttachedTo(null);
    setAttachPickerOpen(true);
  }

  function handleSessionSelect(sessionId: number) {
    if (!attachTarget) return;
    setPendingAttach({ sessionId, exercise: attachTarget });
  }

  // pendingAttach only settles into a fully re-rendered attachMutation (bound
  // to the correct sessionId) the render after it is set — an effect keyed on
  // it, rather than an inline call inside handleSessionSelect, is what lets
  // the mutation hook's closure catch up before firing (feature 032, T017).
  useEffect(() => {
    if (!pendingAttach) return;
    const { sessionId, exercise } = pendingAttach;
    attachMutation.mutate(
      [{ exercise_id: exercise.id, segment: "principal", position: 0 }],
      {
        onSuccess: () => {
          setAttachedTo({ sessionId, exerciseName: exercise.name });
          setAttachTarget(null);
          setPendingAttach(null);
        },
        onError: (err) => {
          setAttachError(mapTechniqueError(err).message);
          setPendingAttach(null);
        },
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingAttach]);

  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      {/* Page header */}
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold text-charcoal">
            Biblioteca de técnica y gymkhana
          </h1>
          <p className="mt-1 text-sm text-mid-gray">
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

      {/* Aviso de adjunto — error o enlace "Ver en la sesión" (T017) */}
      {attachError ? (
        <p
          role="alert"
          className="mb-4 flex items-center gap-1.5 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          {attachError}
        </p>
      ) : null}
      {attachedTo ? (
        <div
          role="status"
          className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-green-200 bg-green-50 p-4 text-sm text-green-800"
        >
          <span>
            &ldquo;{attachedTo.exerciseName}&rdquo; fue adjuntado a la sesión.
          </span>
          <Link
            to={`/training/sessions/${attachedTo.sessionId}?section=plan`}
            className="min-h-12 flex items-center font-medium text-primary underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            Ver en la sesión
          </Link>
        </div>
      ) : null}

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
        onAttach={canCurate ? handleAttachClick : undefined}
        attachingExerciseId={
          pendingAttach && attachMutation.isPending
            ? pendingAttach.exercise.id
            : null
        }
      />

      {/* Selector "¿A qué sesión?" — entry point #2 (T017) */}
      {canCurate && (
        <SessionPickerDialog
          open={attachPickerOpen}
          onOpenChange={setAttachPickerOpen}
          onSelect={handleSessionSelect}
          title="¿A qué sesión?"
          description={
            attachTarget
              ? `Elegí la sesión donde adjuntar "${attachTarget.name}".`
              : undefined
          }
        />
      )}

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
