import { useState } from "react";

import { useAthletes } from "@/hooks/athletes/useAthletes";

interface AthletesMultiSelectProps {
  value: number[];
  onChange: (ids: number[]) => void;
  error?: string;
}

export function AthletesMultiSelect({
  value,
  onChange,
  error,
}: AthletesMultiSelectProps) {
  const [search, setSearch] = useState("");
  const athletesQuery = useAthletes();

  const allAthletes = athletesQuery.data?.items ?? [];

  const filtered = allAthletes.filter((a) => {
    const fullName = `${a.first_name} ${a.last_name}`.toLowerCase();
    return fullName.includes(search.toLowerCase().trim());
  });

  // Selected athletes first, then unselected — both groups sorted by name
  const sortedFiltered = [
    ...filtered.filter((a) => value.includes(a.id)),
    ...filtered.filter((a) => !value.includes(a.id)),
  ];

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
    <fieldset className="space-y-2">
      <legend className="sr-only">Atletas convocados</legend>
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

      <div
        className="max-h-72 overflow-y-auto rounded-lg bg-white"
        style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
      >
        {sortedFiltered.length === 0 ? (
          <p className="px-4 py-3 text-sm text-mid-gray">No hay atletas.</p>
        ) : (
          <ul role="list">
            {sortedFiltered.map((athlete) => {
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
                      {athlete.age_decimal != null && (
                        <span className="ml-2 text-xs text-mid-gray">
                          {athlete.age_decimal.toFixed(1)} años
                        </span>
                      )}
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
    </fieldset>
  );
}
