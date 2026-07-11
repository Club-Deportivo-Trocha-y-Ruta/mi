import { useTrainingFiltersStore } from "@/store/trainingFiltersStore";
import type { SessionStatus } from "@/types/trainingSession.types";

const inputSelectClass =
  "rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50 shadow-ring";

export function SessionFiltersBar() {
  const {
    from_date,
    to_date,
    status,
    setFromDate,
    setToDate,
    setStatus,
    resetToCurrentMonth,
  } = useTrainingFiltersStore();

  return (
    <div className="rounded-xl bg-white p-4 shadow-card">
      {/* Mobile: 2-col grid; sm+: single inline row */}
      <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-end sm:gap-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="filter-from-date" className="text-xs font-medium text-mid-gray">Desde</label>
          <input
            id="filter-from-date"
            type="date"
            value={from_date}
            onChange={(e) => setFromDate(e.target.value)}
            className={inputSelectClass}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="filter-to-date" className="text-xs font-medium text-mid-gray">Hasta</label>
          <input
            id="filter-to-date"
            type="date"
            value={to_date}
            onChange={(e) => setToDate(e.target.value)}
            className={inputSelectClass}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="filter-status" className="text-xs font-medium text-mid-gray">Estado</label>
          <select
            id="filter-status"
            value={status}
            onChange={(e) => setStatus(e.target.value as SessionStatus | "")}
            className={inputSelectClass}
          >
            <option value="">Todos</option>
            <option value="planned">Planificada</option>
            <option value="executed">Ejecutada</option>
            <option value="cancelled">Cancelada</option>
          </select>
        </div>
        <button
          type="button"
          onClick={resetToCurrentMonth}
          className="self-end rounded-lg bg-white px-3 py-2 text-sm font-medium text-mid-gray transition-opacity hover:opacity-70 shadow-ring"
        >
          Mes actual
        </button>
      </div>
    </div>
  );
}
