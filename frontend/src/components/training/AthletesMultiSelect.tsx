import { useState } from "react";

import { useAthletes } from "@/hooks/athletes/useAthletes";
import type { AgeGroup } from "@/types/trainingSession.types";

interface AthletesMultiSelectProps {
  ageGroup: AgeGroup | "";
  value: number[];
  onChange: (ids: number[]) => void;
  error?: string;
}

const AGE_GROUP_CATEGORY_MAP: Record<AgeGroup, string[]> = {
  u12: [
    "Pre-Infantil A",
    "Pre-Infantil A femenino",
    "Pre-Infantil B",
    "Pre-Infantil B femenino",
    "Infantil A",
    "Infantil A femenino",
    "Infantil B",
    "Infantil B femenino",
  ],
  u15: [
    "Pre-juvenil A",
    "Pre-juvenil A femenino",
    "Pre-juvenil B",
    "Pre-juvenil B femenino",
  ],
};

export function AthletesMultiSelect({
  ageGroup,
  value,
  onChange,
  error,
}: AthletesMultiSelectProps) {
  const [search, setSearch] = useState("");
  const athletesQuery = useAthletes();

  const allAthletes = athletesQuery.data?.items ?? [];

  const filtered = allAthletes.filter((a) => {
    const fullName = `${a.first_name} ${a.last_name}`.toLowerCase();
    const matchesSearch = fullName.includes(search.toLowerCase().trim());
    if (!ageGroup) return matchesSearch;
    const categories = AGE_GROUP_CATEGORY_MAP[ageGroup] ?? [];
    return matchesSearch && categories.includes(a.category ?? "");
  });

  function toggle(id: number) {
    if (value.includes(id)) {
      onChange(value.filter((v) => v !== id));
    } else {
      onChange([...value, id]);
    }
  }

  function selectAll() {
    onChange(filtered.map((a) => a.id));
  }

  function clearAll() {
    onChange([]);
  }

  if (athletesQuery.isLoading) {
    return (
      <div className="space-y-1">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-8 animate-pulse rounded-lg bg-light-gray" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar atleta..."
          className="flex-1 rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
        />
        <button
          type="button"
          onClick={selectAll}
          className="rounded-lg px-2.5 py-2 text-xs font-medium text-charcoal transition-opacity hover:opacity-70"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
        >
          Todos
        </button>
        <button
          type="button"
          onClick={clearAll}
          className="rounded-lg px-2.5 py-2 text-xs font-medium text-mid-gray transition-opacity hover:opacity-70"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
        >
          Limpiar
        </button>
      </div>

      {!ageGroup && (
        <p className="text-xs text-mid-gray">
          Selecciona un grupo de edad para filtrar los atletas.
        </p>
      )}

      <div
        className="max-h-48 overflow-y-auto rounded-lg bg-white"
        style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
      >
        {filtered.length === 0 ? (
          <p className="px-4 py-3 text-sm text-mid-gray">
            {ageGroup ? "No hay atletas en este grupo de edad." : "No hay atletas."}
          </p>
        ) : (
          <ul role="list">
            {filtered.map((athlete) => {
              const checked = value.includes(athlete.id);
              return (
                <li key={athlete.id}>
                  <label className="flex cursor-pointer items-center gap-3 px-4 py-2.5 transition-colors hover:bg-light-gray">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggle(athlete.id)}
                      className="h-4 w-4 rounded border-mid-gray text-charcoal"
                      aria-label={`Convocar a ${athlete.first_name} ${athlete.last_name}`}
                    />
                    <span className="flex-1 text-sm text-charcoal">
                      {athlete.first_name} {athlete.last_name}
                    </span>
                    {athlete.category && (
                      <span className="text-xs text-mid-gray">{athlete.category}</span>
                    )}
                  </label>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {value.length > 0 && (
        <p className="text-xs font-medium text-charcoal">
          {value.length} atleta{value.length !== 1 ? "s" : ""} seleccionado{value.length !== 1 ? "s" : ""}
        </p>
      )}

      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
