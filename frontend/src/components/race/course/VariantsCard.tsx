/**
 * VariantsCard — lista de variantes de circuito de una válida (feature 043).
 *
 * `readOnly=true` (rol parent): solo la lista, sin ninguna acción.
 * Coach/admin (`readOnly` ausente/false): "Agregar variante", renombrar
 * inline, "Reemplazar archivo" y borrar (con confirmación — 409
 * `variant_in_use` se muestra inline en el propio diálogo de confirmación,
 * sin cerrarlo, nombrando las categorías que la usan).
 */
import { useState } from "react";
import { Loader2, Pencil, Plus, RefreshCw, Trash2, X as XIcon, Check } from "lucide-react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import {
  useDeleteCourseVariant,
  useRenameCourseVariant,
} from "@/hooks/race/useRaceCourse";
import { getCourseErrorMessage } from "@/lib/courseErrors";
import { cn } from "@/lib/utils";
import type { CourseVariant } from "@/types/raceCourse.types";

import { VariantUploadDialog } from "@/components/race/course/VariantUploadDialog";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface VariantsCardProps {
  raceEventId: number;
  variants: CourseVariant[];
  /** true para el rol parent — solo lectura, sin botones de acción. */
  readOnly?: boolean;
}

/** "Circuito completo" para la 1ra variante, "Recorrido reducido" para la
 * 2da, vacío para la 3ra en adelante (`ui-course.md` §2). */
function nextDefaultLabel(count: number): string {
  if (count === 0) return "Circuito completo";
  if (count === 1) return "Recorrido reducido";
  return "";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function VariantsCard({
  raceEventId,
  variants,
  readOnly = false,
}: VariantsCardProps) {
  const [addOpen, setAddOpen] = useState(false);
  const [replacingVariant, setReplacingVariant] = useState<CourseVariant | null>(
    null,
  );
  const [deletingVariant, setDeletingVariant] = useState<CourseVariant | null>(
    null,
  );
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameError, setRenameError] = useState<string | null>(null);

  const renameMutation = useRenameCourseVariant();
  const deleteMutation = useDeleteCourseVariant();

  function startRename(variant: CourseVariant) {
    setRenamingId(variant.id);
    setRenameValue(variant.label);
    setRenameError(null);
    renameMutation.reset();
  }

  function cancelRename() {
    setRenamingId(null);
    setRenameValue("");
    setRenameError(null);
  }

  function confirmRename(variantId: number) {
    const trimmed = renameValue.trim();
    if (trimmed.length < 1 || trimmed.length > 60) {
      setRenameError("El nombre debe tener entre 1 y 60 caracteres.");
      return;
    }
    setRenameError(null);
    renameMutation.mutate(
      { raceEventId, variantId, body: { label: trimmed } },
      {
        onSuccess: () => {
          setRenamingId(null);
          setRenameValue("");
        },
        onError: (err) => setRenameError(getCourseErrorMessage(err)),
      },
    );
  }

  function confirmDelete() {
    if (!deletingVariant) return;
    deleteMutation.mutate(
      { raceEventId, variantId: deletingVariant.id },
      {
        onSuccess: () => {
          toast.success("Variante eliminada.");
          setDeletingVariant(null);
          deleteMutation.reset();
        },
      },
    );
  }

  return (
    <div
      className="rounded-xl bg-white p-4 ring-1 ring-[rgba(34,42,53,0.08)]"
      data-testid="course-variants-card"
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-charcoal">
          Variantes de circuito
        </h2>
        {!readOnly && (
          <button
            type="button"
            onClick={() => setAddOpen(true)}
            className="inline-flex min-h-12 items-center gap-1.5 rounded-lg bg-charcoal px-4 text-sm font-semibold text-white transition-opacity hover:opacity-90"
            data-testid="course-variants-add-btn"
          >
            <Plus size={14} aria-hidden="true" />
            Agregar variante
          </button>
        )}
      </div>

      {variants.length === 0 ? (
        <p
          className="text-sm text-mid-gray"
          data-testid="course-variants-empty"
        >
          Aún no hay variantes de circuito registradas.
        </p>
      ) : (
        <ul className="space-y-3">
          {variants.map((variant) => (
            <li
              key={variant.id}
              className="rounded-lg border border-[rgba(34,42,53,0.08)] p-3"
              data-testid={`course-variant-row-${variant.id}`}
            >
              <div className="flex items-center justify-between gap-2">
                {renamingId === variant.id ? (
                  <div className="flex flex-1 items-center gap-2">
                    <input
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      maxLength={60}
                      autoFocus
                      className="min-h-12 flex-1 rounded-lg border border-[rgba(34,42,53,0.12)] px-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40"
                      aria-label={`Nuevo nombre para ${variant.label}`}
                      data-testid={`course-variant-rename-input-${variant.id}`}
                    />
                    <button
                      type="button"
                      aria-label="Confirmar nombre"
                      onClick={() => confirmRename(variant.id)}
                      disabled={renameMutation.isPending}
                      className="flex min-h-12 min-w-12 items-center justify-center rounded-lg text-charcoal hover:bg-light-gray disabled:opacity-50"
                      data-testid={`course-variant-rename-confirm-${variant.id}`}
                    >
                      {renameMutation.isPending ? (
                        <Loader2 size={16} className="animate-spin" aria-hidden="true" />
                      ) : (
                        <Check size={16} aria-hidden="true" />
                      )}
                    </button>
                    <button
                      type="button"
                      aria-label="Cancelar renombrar"
                      onClick={cancelRename}
                      disabled={renameMutation.isPending}
                      className="flex min-h-12 min-w-12 items-center justify-center rounded-lg text-mid-gray hover:bg-light-gray disabled:opacity-50"
                    >
                      <XIcon size={16} aria-hidden="true" />
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm font-medium text-charcoal">
                      {variant.label}
                    </span>
                    {!readOnly && (
                      <button
                        type="button"
                        aria-label={`Renombrar ${variant.label}`}
                        onClick={() => startRename(variant)}
                        className="flex min-h-12 min-w-12 items-center justify-center rounded-lg text-mid-gray hover:bg-light-gray hover:text-charcoal"
                        data-testid={`course-variant-rename-btn-${variant.id}`}
                      >
                        <Pencil size={14} aria-hidden="true" />
                      </button>
                    )}
                  </div>
                )}

                {!readOnly && renamingId !== variant.id && (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      aria-label={`Reemplazar archivo de ${variant.label}`}
                      onClick={() => setReplacingVariant(variant)}
                      className="flex min-h-12 min-w-12 items-center justify-center rounded-lg text-mid-gray hover:bg-light-gray hover:text-charcoal"
                      data-testid={`course-variant-replace-btn-${variant.id}`}
                    >
                      <RefreshCw size={14} aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      aria-label={`Eliminar ${variant.label}`}
                      onClick={() => setDeletingVariant(variant)}
                      className="flex min-h-12 min-w-12 items-center justify-center rounded-lg text-mid-gray hover:bg-light-gray hover:text-red-700"
                      data-testid={`course-variant-delete-btn-${variant.id}`}
                    >
                      <Trash2 size={14} aria-hidden="true" />
                    </button>
                  </div>
                )}
              </div>

              {renameError && renamingId === variant.id && (
                <p className="mt-1 text-xs text-red-600" role="alert">
                  {renameError}
                </p>
              )}

              <p
                className={cn(
                  "mt-1 text-xs text-mid-gray",
                  renamingId === variant.id && "sr-only",
                )}
              >
                {variant.lap_distance_km} km ·{" "}
                {variant.elevation_gain_m != null
                  ? `${variant.elevation_gain_m} m D+`
                  : "D+ sin dato"}{" "}
                · {variant.point_count} puntos
              </p>
            </li>
          ))}
        </ul>
      )}

      {!readOnly && (
        <VariantUploadDialog
          raceEventId={raceEventId}
          open={addOpen}
          onOpenChange={setAddOpen}
          defaultLabel={nextDefaultLabel(variants.length)}
        />
      )}

      {!readOnly && replacingVariant && (
        <VariantUploadDialog
          raceEventId={raceEventId}
          open={replacingVariant != null}
          onOpenChange={(next) => {
            if (!next) setReplacingVariant(null);
          }}
          variantId={replacingVariant.id}
          defaultLabel={replacingVariant.label}
        />
      )}

      {!readOnly && (
        <ConfirmDialog
          open={deletingVariant != null}
          title={
            deletingVariant
              ? `¿Eliminar "${deletingVariant.label}"?`
              : "¿Eliminar variante?"
          }
          description="Esta acción no se puede deshacer."
          confirmLabel="Eliminar"
          tone="danger"
          isPending={deleteMutation.isPending}
          errorMessage={
            deleteMutation.isError
              ? getCourseErrorMessage(deleteMutation.error)
              : undefined
          }
          onConfirm={confirmDelete}
          onCancel={() => {
            setDeletingVariant(null);
            deleteMutation.reset();
          }}
        />
      )}
    </div>
  );
}
