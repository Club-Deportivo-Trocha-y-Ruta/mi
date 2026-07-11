import { useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { getAthlete } from "@/api/athletes";
import { AthletesTable, type AthleteRow } from "@/components/athletes/AthletesTable";
import { ErrorState } from "@/components/shared/ErrorState";
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

const inputSelectClass =
  "rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50";
const inputSelectStyle = { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" };

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
    <section className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1
            className="text-2xl text-charcoal"
            style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
          >
            Atletas
          </h1>
          <p className="mt-0.5 text-sm text-mid-gray">Gestion de atletas del club.</p>
        </div>
        {isCoach && (
          <Link
            to="/athletes/new"
            className="rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70"
            style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
          >
            + Agregar atleta
          </Link>
        )}
      </div>

      {/* Filtros */}
      <div
        className="grid gap-3 rounded-xl bg-white p-4 md:grid-cols-3"
        style={{ boxShadow: "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px" }}
      >
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Buscar por nombre..."
          aria-label="Buscar por nombre"
          className={inputSelectClass}
          style={inputSelectStyle}
        />
        <select
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          aria-label="Categoría"
          className={inputSelectClass}
          style={inputSelectStyle}
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
          aria-label="Estado PHV"
          className={inputSelectClass}
          style={inputSelectStyle}
        >
          <option value="Todos">Todos los estados PHV</option>
          <option value={MaturationStatus.PrePHV}>Pre-PHV</option>
          <option value={MaturationStatus.CircaPHV}>Circa-PHV</option>
          <option value={MaturationStatus.PostPHV}>Post-PHV</option>
        </select>
      </div>

      {/* Skeleton */}
      {athletesQuery.isLoading ? (
        <div
          className="space-y-2 rounded-xl bg-white p-4"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
        >
          {Array.from({ length: 5 }).map((_, idx) => (
            <div key={idx} className="h-9 animate-pulse rounded-lg bg-light-gray" />
          ))}
        </div>
      ) : null}

      {/* Error */}
      {athletesQuery.isError ? (
        <ErrorState
          message="No se pudo cargar la lista de atletas."
          onRetry={() => void athletesQuery.refetch()}
        />
      ) : null}

      {/* Empty state */}
      {!athletesQuery.isLoading && !athletesQuery.isError && filteredRows.length === 0 ? (
        <div
          className="rounded-xl bg-white p-10 text-center"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px", borderStyle: "dashed" }}
        >
          <p className="text-sm text-mid-gray">No hay atletas registrados.</p>
          {isCoach ? (
            <Link
              to="/athletes/new"
              className="mt-3 inline-block text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
            >
              + Agregar atleta
            </Link>
          ) : null}
        </div>
      ) : null}

      {/* Table */}
      {!athletesQuery.isLoading && !athletesQuery.isError && filteredRows.length > 0 ? (
        <AthletesTable items={filteredRows} />
      ) : null}
    </section>
  );
}
