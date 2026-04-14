import { useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { getAthlete } from "@/api/athletes";
import { AthletesTable, type AthleteRow } from "@/components/athletes/AthletesTable";
import { useAthletes } from "@/hooks/athletes/useAthletes";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useAuthStore } from "@/store/auth.store";
import { MaturationStatus, UserRole } from "@/types/enums";

const CATEGORY_OPTIONS = [
  "Todas",
  "Pre-Infantil A",
  "Pre-Infantil A femenino",
  "Pre-Infantil B",
  "Pre-Infantil B femenino",
  "Infantil A",
  "Infantil A femenino",
  "Infantil B",
  "Infantil B femenino",
  "Pre-juvenil A",
  "Pre-juvenil A femenino",
  "Pre-juvenil B",
  "Pre-juvenil B femenino",
];

export function AthletesListPage() {
  const user = useAuthStore((state) => state.user);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("Todas");
  const [phv, setPhv] = useState<"Todos" | MaturationStatus>("Todos");
  const debouncedSearch = useDebouncedValue(search, 300);

  const athletesQuery = useAthletes();

  const detailQueries = useQueries({
    queries: (athletesQuery.data?.items ?? []).map((athlete) => ({
      queryKey: ["athlete", athlete.id],
      queryFn: () => getAthlete(athlete.id),
      staleTime: 30_000,
    })),
  });

  const rows = useMemo<AthleteRow[]>(() => {
    const items = athletesQuery.data?.items ?? [];
    return items.map((athlete, index) => ({
      ...athlete,
      latest_maturation_status: detailQueries[index]?.data?.latest_anthropometry?.maturation_status ?? null,
    }));
  }, [athletesQuery.data?.items, detailQueries]);

  const filteredRows = useMemo(() => {
    return rows.filter((row) => {
      const fullName = `${row.first_name} ${row.last_name}`.toLowerCase();
      const bySearch = fullName.includes(debouncedSearch.toLowerCase().trim());
      const byCategory = category === "Todas" || row.category === category;
      const byPhv = phv === "Todos" || row.latest_maturation_status === phv;
      return bySearch && byCategory && byPhv;
    });
  }, [rows, debouncedSearch, category, phv]);

  const isCoach = user?.role === UserRole.coach;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Atletas</h1>
          <p className="text-sm text-slate-600">Gestion de atletas del club.</p>
        </div>
        {isCoach && (
          <Link
            to="/athletes/new"
            className="rounded-md bg-slate-900 px-4 py-2 text-sm text-white hover:bg-slate-800"
          >
            + Agregar atleta
          </Link>
        )}
      </div>

      <div className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 md:grid-cols-3">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Buscar por nombre..."
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
        <select
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
        >
          {CATEGORY_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        <select
          value={phv}
          onChange={(event) => setPhv(event.target.value as "Todos" | MaturationStatus)}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="Todos">Todos los estados PHV</option>
          <option value={MaturationStatus.PrePHV}>Pre-PHV</option>
          <option value={MaturationStatus.CircaPHV}>Circa-PHV</option>
          <option value={MaturationStatus.PostPHV}>Post-PHV</option>
        </select>
      </div>

      {athletesQuery.isLoading ? (
        <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-4">
          {Array.from({ length: 5 }).map((_, idx) => (
            <div key={idx} className="h-9 animate-pulse rounded bg-slate-100" />
          ))}
        </div>
      ) : null}

      {athletesQuery.isError ? (
        <p className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          No se pudo cargar la lista de atletas.
        </p>
      ) : null}

      {!athletesQuery.isLoading && !athletesQuery.isError && filteredRows.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center">
          <p className="text-sm text-slate-600">No hay atletas registrados.</p>
          {isCoach ? (
            <Link to="/athletes/new" className="mt-3 inline-block text-sm font-medium text-slate-900">
              + Agregar atleta
            </Link>
          ) : null}
        </div>
      ) : null}

      {!athletesQuery.isLoading && !athletesQuery.isError && filteredRows.length > 0 ? (
        <AthletesTable items={filteredRows} />
      ) : null}
    </section>
  );
}
