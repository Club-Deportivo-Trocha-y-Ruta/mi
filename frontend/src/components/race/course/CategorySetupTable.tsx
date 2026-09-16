/**
 * CategorySetupTable — tabla de vueltas por categoría de una válida
 * (feature 043).
 *
 * Una fila por categoría en la unión `resultCategoryIds ∪ setups ∪
 * suggested_setups` (`ui-course.md` §2). Cuando `setups` está vacío y hay
 * `suggested_setups`, se prellenan las filas desde la válida anterior de la
 * serie (R-14) y el botón de guardar cambia a "Confirmar vueltas".
 *
 * Validación: se usa `setupsSchema`/`setupRowSchema` de `@/schemas/raceCourse`
 * pero SOLO sobre las filas con vueltas indicadas — una fila en blanco no es
 * un error, es una categoría que simplemente no se envía (`ui-course.md`
 * §2: "blank rows are simply not included in the submitted array").
 */
import { useEffect, useState } from "react";
import { Controller, useFieldArray, useForm } from "react-hook-form";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { useReplaceCourseSetups } from "@/hooks/race/useRaceCourse";
import { getCourseErrorMessage } from "@/lib/courseErrors";
import { cn } from "@/lib/utils";
import { setupsSchema } from "@/schemas/raceCourse";
import type {
  CourseSetup,
  CourseVariant,
  SetupInput,
  SuggestedSetup,
} from "@/types/raceCourse.types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface CategorySetupTableProps {
  raceEventId: number;
  setups: CourseSetup[];
  suggestedSetups: SuggestedSetup[];
  variants: CourseVariant[];
  /** Ids de categoría presentes en los resultados de esta válida. */
  resultCategoryIds?: number[];
}

// ---------------------------------------------------------------------------
// Filas — unión de categorías + valores del formulario
// ---------------------------------------------------------------------------

interface CategoryRowMeta {
  category_id: number;
  label: string;
}

interface SetupRowDraft {
  category_id: number;
  /** Valor crudo del input — "" = fila en blanco (se omite al guardar). */
  laps: string;
  /** Valor crudo del select — "" = sin variante seleccionada. */
  variant_id: string;
}

interface SetupsFormDraft {
  rows: SetupRowDraft[];
}

/** Unión best-effort de categorías a mostrar. Para ids que solo vienen de
 * `resultCategoryIds` o `suggestedSetups` no hay label/code disponible en
 * estos props — se renderiza un rótulo genérico por id en ese caso. */
function buildCategoryRows(
  setups: CourseSetup[],
  suggestedSetups: SuggestedSetup[],
  resultCategoryIds: number[],
): CategoryRowMeta[] {
  const byId = new Map<number, CategoryRowMeta>();
  for (const s of setups) {
    byId.set(s.category_id, { category_id: s.category_id, label: s.category_label });
  }
  for (const s of suggestedSetups) {
    if (!byId.has(s.category_id)) {
      byId.set(s.category_id, {
        category_id: s.category_id,
        label: `Categoría #${s.category_id}`,
      });
    }
  }
  for (const id of resultCategoryIds) {
    if (!byId.has(id)) {
      byId.set(id, { category_id: id, label: `Categoría #${id}` });
    }
  }
  return Array.from(byId.values()).sort((a, b) => a.category_id - b.category_id);
}

function buildInitialRows(
  categoryRows: CategoryRowMeta[],
  setups: CourseSetup[],
  suggestedSetups: SuggestedSetup[],
  variants: CourseVariant[],
  useSuggestions: boolean,
): SetupRowDraft[] {
  const setupByCategory = new Map(setups.map((s) => [s.category_id, s]));
  const suggestionByCategory = new Map(
    suggestedSetups.map((s) => [s.category_id, s]),
  );
  const variantByLabel = new Map(variants.map((v) => [v.label, v]));

  return categoryRows.map((row) => {
    const existing = setupByCategory.get(row.category_id);
    if (existing) {
      return {
        category_id: row.category_id,
        laps: String(existing.laps),
        variant_id: String(existing.variant_id),
      };
    }
    if (useSuggestions) {
      const suggestion = suggestionByCategory.get(row.category_id);
      if (suggestion) {
        const matched = variantByLabel.get(suggestion.variant_label);
        return {
          category_id: row.category_id,
          laps: String(suggestion.laps),
          variant_id: matched ? String(matched.id) : "",
        };
      }
    }
    return { category_id: row.category_id, laps: "", variant_id: "" };
  });
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CategorySetupTable({
  raceEventId,
  setups,
  suggestedSetups,
  variants,
  resultCategoryIds = [],
}: CategorySetupTableProps) {
  const categoryRows = buildCategoryRows(
    setups,
    suggestedSetups,
    resultCategoryIds,
  );
  const labelById = new Map(categoryRows.map((r) => [r.category_id, r.label]));
  const useSuggestions = setups.length === 0 && suggestedSetups.length > 0;

  const [submitError, setSubmitError] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<number, string>>({});

  const replaceMutation = useReplaceCourseSetups();

  const { control, handleSubmit, reset } = useForm<SetupsFormDraft>({
    defaultValues: {
      rows: buildInitialRows(
        categoryRows,
        setups,
        suggestedSetups,
        variants,
        useSuggestions,
      ),
    },
  });

  const { fields } = useFieldArray({ control, name: "rows" });

  // Re-sincroniza las filas cuando cambian los datos del servidor (por
  // ejemplo tras guardar, al recibir la respuesta inicial, o cuando
  // `resultCategoryIds` llega en una query separada y aporta una categoría
  // que no estaba en `setups`/`suggestedSetups`).
  const resultCategoryIdsKey = resultCategoryIds.join(",");
  useEffect(() => {
    reset({
      rows: buildInitialRows(
        categoryRows,
        setups,
        suggestedSetups,
        variants,
        useSuggestions,
      ),
    });
    setSubmitError(null);
    setRowErrors({});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setups, suggestedSetups, variants, resultCategoryIdsKey]);

  const onSubmit = handleSubmit((values) => {
    setSubmitError(null);
    const errs: Record<number, string> = {};
    const candidates: Array<{
      category_id: number;
      laps: number | string;
      variant_id: number;
    }> = [];

    for (const row of values.rows) {
      if (row.laps.trim() === "") continue; // fila en blanco → se omite
      if (row.variant_id === "") {
        errs[row.category_id] = "Selecciona una variante para esta categoría.";
        continue;
      }
      candidates.push({
        category_id: row.category_id,
        laps: row.laps,
        variant_id: Number(row.variant_id),
      });
    }

    if (Object.keys(errs).length > 0) {
      setRowErrors(errs);
      return;
    }

    const parsed = setupsSchema.safeParse(candidates);
    if (!parsed.success) {
      const zodErrs: Record<number, string> = {};
      for (const issue of parsed.error.issues) {
        const idx = issue.path[0];
        if (typeof idx === "number" && candidates[idx]) {
          zodErrs[candidates[idx].category_id] = issue.message;
        }
      }
      setRowErrors(zodErrs);
      return;
    }

    setRowErrors({});
    const body: { setups: SetupInput[] } = { setups: parsed.data };
    replaceMutation.mutate(
      { raceEventId, body },
      {
        onSuccess: () => toast.success("Vueltas guardadas."),
        onError: (err) => setSubmitError(getCourseErrorMessage(err)),
      },
    );
  });

  const saveLabel = useSuggestions ? "Confirmar vueltas" : "Guardar";

  return (
    <div
      className="rounded-xl bg-white p-4 ring-1 ring-[rgba(34,42,53,0.08)]"
      data-testid="course-setup-table"
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-charcoal">
          Vueltas por categoría
        </h2>
      </div>

      {useSuggestions && (
        <div
          className="mb-3 rounded-lg bg-light-gray/40 px-3 py-2 text-xs text-mid-gray ring-1 ring-[rgba(34,42,53,0.08)]"
          role="status"
          data-testid="course-setup-suggested-banner"
        >
          Sugerido desde la válida anterior
        </div>
      )}

      {fields.length === 0 ? (
        <p className="text-sm text-mid-gray" data-testid="course-setup-empty">
          No hay categorías disponibles para configurar todavía.
        </p>
      ) : (
        <form onSubmit={onSubmit} className="space-y-3" noValidate>
          <div className="space-y-3">
            {fields.map((field, index) => (
              <div
                key={field.id}
                className="grid grid-cols-1 gap-2 rounded-lg border border-[rgba(34,42,53,0.08)] p-3 sm:grid-cols-[1fr_100px_1fr]"
                data-testid={`course-setup-row-${field.category_id}`}
              >
                <span className="flex items-center text-sm font-medium text-charcoal">
                  {labelById.get(field.category_id) ??
                    `Categoría #${field.category_id}`}
                </span>

                <div>
                  <label
                    htmlFor={`setup-laps-${field.category_id}`}
                    className="sr-only"
                  >
                    Vueltas — {labelById.get(field.category_id)}
                  </label>
                  <Controller
                    control={control}
                    name={`rows.${index}.laps`}
                    render={({ field: f }) => (
                      <input
                        id={`setup-laps-${field.category_id}`}
                        type="number"
                        inputMode="numeric"
                        min={1}
                        max={20}
                        placeholder="Vueltas"
                        value={f.value}
                        onChange={f.onChange}
                        onBlur={f.onBlur}
                        className={cn(
                          "min-h-12 w-full rounded-lg bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-blue-500/40",
                          "shadow-ring",
                        )}
                        data-testid={`course-setup-laps-${field.category_id}`}
                      />
                    )}
                  />
                </div>

                <div>
                  <label
                    htmlFor={`setup-variant-${field.category_id}`}
                    className="sr-only"
                  >
                    Variante — {labelById.get(field.category_id)}
                  </label>
                  <Controller
                    control={control}
                    name={`rows.${index}.variant_id`}
                    render={({ field: f }) => (
                      <select
                        id={`setup-variant-${field.category_id}`}
                        value={f.value}
                        onChange={f.onChange}
                        onBlur={f.onBlur}
                        className={cn(
                          "min-h-12 w-full rounded-lg bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-blue-500/40",
                          "shadow-ring",
                        )}
                        data-testid={`course-setup-variant-${field.category_id}`}
                      >
                        <option value="">Selecciona una variante…</option>
                        {variants.map((v) => (
                          <option key={v.id} value={v.id}>
                            {v.label}
                          </option>
                        ))}
                      </select>
                    )}
                  />
                </div>

                {rowErrors[field.category_id] && (
                  <p
                    className="text-xs text-red-600 sm:col-span-3"
                    role="alert"
                    data-testid={`course-setup-row-error-${field.category_id}`}
                  >
                    {rowErrors[field.category_id]}
                  </p>
                )}
              </div>
            ))}
          </div>

          {submitError && (
            <p
              className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
              role="alert"
              data-testid="course-setup-error"
            >
              {submitError}
            </p>
          )}

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={replaceMutation.isPending}
              className="inline-flex min-h-12 items-center gap-2 rounded-lg bg-charcoal px-4 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              data-testid="course-setup-save"
            >
              {replaceMutation.isPending && (
                <Loader2 size={14} className="animate-spin" aria-hidden="true" />
              )}
              {saveLabel}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
