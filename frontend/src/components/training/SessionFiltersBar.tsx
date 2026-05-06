import { useTrainingFiltersStore } from "@/store/trainingFiltersStore";
import type { AgeGroup, SessionStatus } from "@/types/trainingSession.types";

const inputSelectClass =
  "rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50";
const inputSelectStyle = { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" };

export function SessionFiltersBar() {
  const {
    from_date,
    to_date,
    age_group,
    status,
    setFromDate,
    setToDate,
    setAgeGroup,
    setStatus,
    resetToCurrentMonth,
  } = useTrainingFiltersStore();

  return (
    <div
      className="flex flex-wrap items-end gap-3 rounded-xl bg-white p-4"
      style={{
        boxShadow:
          "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
      }}
    >
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-mid-gray">Desde</label>
        <input
          type="date"
          value={from_date}
          onChange={(e) => setFromDate(e.target.value)}
          className={inputSelectClass}
          style={inputSelectStyle}
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-mid-gray">Hasta</label>
        <input
          type="date"
          value={to_date}
          onChange={(e) => setToDate(e.target.value)}
          className={inputSelectClass}
          style={inputSelectStyle}
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-mid-gray">Grupo</label>
        <select
          value={age_group}
          onChange={(e) => setAgeGroup(e.target.value as AgeGroup | "")}
          className={inputSelectClass}
          style={inputSelectStyle}
        >
          <option value="">Todos</option>
          <option value="u12">U12 (10-12 años)</option>
          <option value="u15">U15 (13-15 años)</option>
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-mid-gray">Estado</label>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as SessionStatus | "")}
          className={inputSelectClass}
          style={inputSelectStyle}
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
        className="rounded-lg bg-white px-3 py-2 text-sm font-medium text-mid-gray transition-opacity hover:opacity-70"
        style={inputSelectStyle}
      >
        Mes actual
      </button>
    </div>
  );
}
