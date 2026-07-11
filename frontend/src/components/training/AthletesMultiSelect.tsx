import { useMemo, useState } from "react";
import { X } from "lucide-react";

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
  const athletesQuery = useAthletes({ sort: "recent_attendance" });

  const allAthletes = athletesQuery.data?.items ?? [];

  const nameById = useMemo(() => {
    const map = new Map<number, string>();
    for (const a of allAthletes) {
      map.set(a.id, `${a.first_name} ${a.last_name}`.trim());
    }
    return map;
  }, [allAthletes]);

  const filtered = allAthletes.filter((a) => {
    const fullName = `${a.first_name} ${a.last_name}`.toLowerCase();
    return fullName.includes(search.toLowerCase().trim());
  });

  // Seleccionados primero, luego no seleccionados — orden de servidor preservado en ambos (asistencia reciente).
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
          <div key={i} className="h-12 animate-pulse rounded-lg bg-light-gray" />
        ))}
      </div>
    );
  }

  return (
    <fieldset className="space-y-2">
      <legend className="sr-only">Atletas convocados</legend>

      {/* Chips de seleccionados (removibles) */}
      {value.length > 0 && (
        <ul
          className="flex flex-wrap gap-1.5"
          aria-label="Atletas seleccionados"
          data-testid="selected-athlete-chips"
        >
          {value.map((id) => (
            <li key={id}>
              <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 py-1 pl-3 pr-1 text-xs font-medium text-blue-800">
                {nameById.get(id) ?? `Atleta #${id}`}
                <button
                  type="button"
                  onClick={() => toggle(id)}
                  className="flex h-5 w-5 items-center justify-center rounded-full text-blue-700 hover:bg-blue-100"
                  aria-label={`Quitar a ${nameById.get(id) ?? `atleta ${id}`}`}
                >
                  <X size={12} aria-hidden="true" />
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}

      <div className="flex items-center gap-2">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar atleta..."
          className="min-h-[48px] flex-1 rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 shadow-ring"
          aria-label="Buscar atleta"
        />
        <button
          type="button"
          onClick={selectAll}
          className="min-h-[48px] rounded-lg px-3 py-2 text-xs font-medium text-charcoal transition-opacity hover:opacity-70 shadow-ring"
        >
          Todos
        </button>
        <button
          type="button"
          onClick={clearAll}
          className="min-h-[48px] rounded-lg px-3 py-2 text-xs font-medium text-mid-gray transition-opacity hover:opacity-70 shadow-ring"
        >
          Limpiar
        </button>
      </div>

      <div className="max-h-72 overflow-y-auto rounded-lg bg-white shadow-ring">
        {sortedFiltered.length === 0 ? (
          <p className="px-4 py-3 text-sm text-mid-gray">No hay atletas.</p>
        ) : (
          <ul role="list">
            {sortedFiltered.map((athlete) => {
              const checked = value.includes(athlete.id);
              return (
                <li key={athlete.id}>
                  <label className="flex min-h-[48px] cursor-pointer items-center gap-3 px-4 py-2.5 transition-colors hover:bg-light-gray">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggle(athlete.id)}
                      className="h-5 w-5 rounded border-mid-gray text-charcoal"
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

      {/* Conteo pegajoso: visible al hacer scroll de la lista. */}
      <p
        className="sticky bottom-0 bg-white/90 py-1 text-xs font-medium text-charcoal backdrop-blur"
        data-testid="selected-count"
        aria-live="polite"
      >
        {value.length} atleta{value.length !== 1 ? "s" : ""} seleccionado
        {value.length !== 1 ? "s" : ""}
      </p>

      {error && (
        <p className="text-xs text-red-600" role="alert">
          {error}
        </p>
      )}
    </fieldset>
  );
}
