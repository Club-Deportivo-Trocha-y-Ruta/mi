import { useMemo, useState } from "react";

import { ParentFormDialog } from "@/components/parents/ParentFormDialog";
import { ParentsTable } from "@/components/parents/ParentsTable";
import { useParentUsers } from "@/hooks/parents/useParentUsers";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useAuthStore } from "@/store/auth.store";

const inputClass =
  "rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50 shadow-ring";

export function ParentsListPage() {
  const user = useAuthStore((state) => state.user);
  const [search, setSearch] = useState("");
  const [showDialog, setShowDialog] = useState(false);
  const debouncedSearch = useDebouncedValue(search, 300);

  const clubId = user?.club_ids?.[0];

  const parentsQuery = useParentUsers(clubId ? { club_id: clubId } : undefined);

  const filteredParents = useMemo(() => {
    const items = parentsQuery.data?.items ?? [];
    return items.filter((p) => {
      const name = `${p.first_name} ${p.last_name}`.toLowerCase();
      return name.includes(debouncedSearch.toLowerCase().trim());
    });
  }, [parentsQuery.data, debouncedSearch]);

  return (
    <section className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1
            className="font-display text-2xl text-charcoal"
          >
            Padres y Acudientes
          </h1>
          <p className="mt-0.5 text-sm text-mid-gray">Gestion de tutores del club.</p>
        </div>
        <button
          type="button"
          onClick={() => setShowDialog(true)}
          className="rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70 shadow-button-highlight"
        >
          + Nuevo padre
        </button>
      </div>

      {/* Search */}
      <div className="rounded-xl bg-white p-4 shadow-card">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Buscar por nombre..."
          className={inputClass}
        />
      </div>

      {/* Skeleton */}
      {parentsQuery.isLoading ? (
        <div className="space-y-2 rounded-xl bg-white p-4 shadow-ring">
          {Array.from({ length: 5 }).map((_, idx) => (
            <div key={idx} className="h-9 animate-pulse rounded-lg bg-light-gray" />
          ))}
        </div>
      ) : null}

      {/* Error */}
      {parentsQuery.isError ? (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          No se pudo cargar la lista de padres y acudientes.
        </p>
      ) : null}

      {/* Empty state */}
      {!parentsQuery.isLoading && !parentsQuery.isError && filteredParents.length === 0 ? (
        <div
          className="rounded-xl bg-white p-10 text-center shadow-ring"
          style={{ borderStyle: "dashed" }}
        >
          <p className="text-sm text-mid-gray">No hay padres o acudientes registrados.</p>
          <button
            type="button"
            onClick={() => setShowDialog(true)}
            className="mt-3 inline-block text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
          >
            + Nuevo padre
          </button>
        </div>
      ) : null}

      {/* Table */}
      {!parentsQuery.isLoading && !parentsQuery.isError && filteredParents.length > 0 ? (
        <ParentsTable items={filteredParents} />
      ) : null}

      {/* Dialog */}
      {clubId !== undefined ? (
        <ParentFormDialog
          clubId={clubId}
          open={showDialog}
          onClose={() => setShowDialog(false)}
        />
      ) : null}
    </section>
  );
}
