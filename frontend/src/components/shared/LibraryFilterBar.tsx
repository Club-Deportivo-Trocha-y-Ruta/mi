/**
 * LibraryFilterBar — shell de filtros config-driven para catálogos tipo
 * biblioteca (feature 033 / T040).
 *
 * Extraído de `components/technique/FilterBar.tsx` y
 * `components/strength/FilterBar.tsx` (259/259 líneas, misma estructura RHF
 * `watch`+`reset`, solo cambian los campos). En vez de dos copias casi
 * idénticas, este componente recibe la forma de los filtros como config
 * (`fields`) y expone un único `onChange(filters)` con los valores activos
 * ya serializados — el dominio (técnica: habilidad/edad/dificultad/
 * materiales; fuerza: búsqueda/equipo/edad/categoría) se pasa por props, sin
 * lógica de dominio dentro del componente compartido.
 *
 * Tipos de campo soportados:
 *   - "text"        → input libre (p. ej. búsqueda de fuerza)
 *   - "select"       → <select> nativo con opción "Todos/as" al inicio
 *   - "multiSelect"  → grupo de pills toggle (p. ej. materiales de técnica)
 *
 * RHF-driven, sin useEffect: los valores se sincronizan via watch + onChange
 * hacia el padre, igual que las dos implementaciones originales. El botón
 * "Limpiar filtros" llama a reset() y notifica al padre con {} (sin filtros).
 */
import { useCallback } from "react";
import { useForm } from "react-hook-form";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Field config
// ---------------------------------------------------------------------------

export interface LibraryFilterOption {
  value: string;
  label: string;
}

interface LibraryFilterTextField {
  type: "text";
  name: string;
  label: string;
  placeholder?: string;
}

interface LibraryFilterSelectField {
  type: "select";
  name: string;
  label: string;
  /** Label of the "no filter" option, e.g. "Todas las habilidades". */
  placeholder: string;
  options: LibraryFilterOption[];
  isLoading?: boolean;
}

interface LibraryFilterMultiSelectField {
  type: "multiSelect";
  name: string;
  label: string;
  options: LibraryFilterOption[];
  isLoading?: boolean;
  /** Skeleton pill count while options load. Default 5. */
  loadingSkeletonCount?: number;
}

export type LibraryFilterField =
  | LibraryFilterTextField
  | LibraryFilterSelectField
  | LibraryFilterMultiSelectField;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface LibraryFilterBarProps {
  /** Accessible name for the enclosing <section>, e.g. "Filtros del catálogo". */
  ariaLabel: string;
  /** Field definitions, in render order (text/select fields render in a grid, multiSelect below). */
  fields: LibraryFilterField[];
  /**
   * Called whenever any field changes, with only the active (non-empty)
   * values. multiSelect values are joined with "," under their field name —
   * same serialization `technique/FilterBar.tsx` used for `materials`.
   */
  onChange: (filters: Record<string, string>) => void;
  /** Tailwind grid-cols classes for the text/select row. Defaults by field count. */
  gridClassName?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type FormValues = Record<string, string | string[]>;

function buildEmptyValues(fields: LibraryFilterField[]): FormValues {
  const empty: FormValues = {};
  for (const field of fields) {
    empty[field.name] = field.type === "multiSelect" ? [] : "";
  }
  return empty;
}

function toActiveFilters(fields: LibraryFilterField[], values: FormValues): Record<string, string> {
  const filters: Record<string, string> = {};
  for (const field of fields) {
    const raw = values[field.name];
    if (field.type === "multiSelect") {
      const selected = Array.isArray(raw) ? raw : [];
      if (selected.length > 0) filters[field.name] = selected.join(",");
      continue;
    }
    const text = typeof raw === "string" ? raw.trim() : "";
    if (text) filters[field.name] = text;
  }
  return filters;
}

function defaultGridClassName(fieldCount: number): string {
  if (fieldCount <= 2) return "sm:grid-cols-2";
  if (fieldCount === 3) return "sm:grid-cols-3";
  return "sm:grid-cols-2 lg:grid-cols-4";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function LibraryFilterBar({ ariaLabel, fields, onChange, gridClassName }: LibraryFilterBarProps) {
  const gridFields = fields.filter((f): f is LibraryFilterTextField | LibraryFilterSelectField => f.type !== "multiSelect");
  const multiSelectFields = fields.filter((f): f is LibraryFilterMultiSelectField => f.type === "multiSelect");

  const emptyValues = buildEmptyValues(fields);
  const { register, watch, reset, setValue, getValues } = useForm<FormValues>({
    defaultValues: emptyValues,
  });

  const notify = useCallback(
    (values: FormValues) => {
      onChange(toActiveFilters(fields, values));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `fields` is caller-stable config, not per-render state
    [onChange],
  );

  function handleFieldChange() {
    // getValues is synchronous — safe to call immediately after RHF field change
    notify(getValues());
  }

  function handleMultiSelectToggle(name: string, value: string) {
    const current = (getValues(name) as string[] | undefined) ?? [];
    const next = current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
    setValue(name, next);
    notify({ ...getValues(), [name]: next });
  }

  function handleClear() {
    reset(emptyValues);
    onChange({});
  }

  const values = watch();
  const activeCount = fields.reduce((count, field) => {
    const raw = values[field.name];
    if (field.type === "multiSelect") {
      return count + (Array.isArray(raw) ? raw.length : 0);
    }
    return count + (typeof raw === "string" && raw.trim() ? 1 : 0);
  }, 0);

  return (
    <section aria-label={ariaLabel} className="rounded-xl border border-border-gray bg-white p-4">
      {gridFields.length > 0 && (
        <div className={cn("grid gap-3", gridClassName ?? defaultGridClassName(gridFields.length))}>
          {gridFields.map((field) => {
            const inputId = `filter-${field.name}`;
            return (
              <div key={field.name}>
                <label htmlFor={inputId} className="mb-1 block text-xs font-medium text-mid-gray">
                  {field.label}
                </label>
                {field.type === "select" && field.isLoading ? (
                  <Skeleton className="h-10 w-full" />
                ) : field.type === "select" ? (
                  <select
                    id={inputId}
                    {...register(field.name, { onChange: handleFieldChange })}
                    className="min-h-12 w-full rounded-lg border border-border-gray bg-white px-3 py-2 text-sm text-charcoal focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    <option value="">{field.placeholder}</option>
                    {field.options.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    id={inputId}
                    type="text"
                    placeholder={field.placeholder}
                    {...register(field.name, { onChange: handleFieldChange })}
                    className="min-h-12 w-full rounded-lg border border-border-gray bg-white px-3 py-2 text-sm text-charcoal focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                )}
              </div>
            );
          })}
        </div>
      )}

      {multiSelectFields.map((field) => {
        const selected = (values[field.name] as string[] | undefined) ?? [];
        return (
          <div key={field.name} className="mt-3">
            <p className="mb-2 text-xs font-medium text-mid-gray">{field.label}</p>
            {field.isLoading ? (
              <div className="flex flex-wrap gap-2" role="status" aria-label={`Cargando ${field.label.toLowerCase()}…`}>
                {Array.from({ length: field.loadingSkeletonCount ?? 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-7 w-20 rounded-full" />
                ))}
              </div>
            ) : (
              <div className="flex flex-wrap gap-2" role="group" aria-label={field.label}>
                {field.options.map((o) => {
                  const active = selected.includes(o.value);
                  return (
                    <button
                      key={o.value}
                      type="button"
                      aria-pressed={active}
                      onClick={() => handleMultiSelectToggle(field.name, o.value)}
                      className={cn(
                        "min-h-7 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                        active
                          ? "border-primary bg-primary text-white"
                          : "border-border-gray bg-white text-mid-gray hover:border-mid-gray/50",
                      )}
                    >
                      {o.label}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}

      {activeCount > 0 && (
        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            onClick={handleClear}
            className="min-h-9 rounded-lg border border-border-gray px-3 py-1.5 text-xs font-medium text-mid-gray hover:border-mid-gray/50 hover:text-charcoal focus:outline-none focus:ring-2 focus:ring-primary"
          >
            Limpiar filtros
          </button>
          <Badge variant="secondary" className="text-xs">
            {activeCount} {activeCount === 1 ? "filtro activo" : "filtros activos"}
          </Badge>
        </div>
      )}
    </section>
  );
}

export default LibraryFilterBar;
