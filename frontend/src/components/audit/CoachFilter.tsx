/**
 * CoachFilter — selector "Entrenador" del historial de auditoría (feature
 * 041 — gobernanza multi-coach). Clona la barra de filtros de
 * `ActivityReviewPage` (mismos tokens: `inputSelectClass`, opción "Todos",
 * botón "Limpiar filtros" solo visible con filtro activo).
 *
 * Componente controlado y sin fetch propio: la lista de personal del club
 * (staff) llega por props desde la página contenedora, que ya la tiene
 * cargada (p. ej. desde el listado de `/admin/usuarios` o del roster del
 * club) — este componente no declara una nueva llamada a la API.
 */
import { X } from "lucide-react";

const inputSelectClass =
  "min-h-[40px] rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50 shadow-ring";

export interface CoachFilterOption {
  id: number;
  displayName: string;
}

export interface CoachFilterProps {
  coaches: CoachFilterOption[];
  value: number | null;
  onChange: (coachId: number | null) => void;
  /** Deshabilita el select mientras la lista de personal está cargando. */
  disabled?: boolean;
  /** Muestra "Limpiar filtros" cuando hay algún filtro activo (no solo este). */
  showClear?: boolean;
  onClear?: () => void;
}

export function CoachFilter({
  coaches,
  value,
  onChange,
  disabled,
  showClear,
  onClear,
}: CoachFilterProps) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor="filter-coach" className="text-xs font-medium text-mid-gray">
        Entrenador
      </label>
      <div className="flex items-end gap-2">
        <select
          id="filter-coach"
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
          disabled={disabled}
          className={inputSelectClass}
        >
          <option value="">Todos los entrenadores</option>
          {coaches.map((coach) => (
            <option key={coach.id} value={coach.id}>
              {coach.displayName}
            </option>
          ))}
        </select>

        {showClear && onClear && (
          <button
            type="button"
            onClick={onClear}
            className="inline-flex min-h-[40px] items-center gap-1.5 rounded-lg bg-white px-3 py-2 text-sm font-medium text-mid-gray transition-opacity hover:opacity-70 shadow-ring"
          >
            <X size={14} aria-hidden="true" />
            Limpiar filtros
          </button>
        )}
      </div>
    </div>
  );
}
