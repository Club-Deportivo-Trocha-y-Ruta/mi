/**
 * ClubHistoryPage — "Historial del club" (feature 041 — gobernanza
 * multi-coach, FR-006). Contratos:
 * specs/041-multi-coach-governance/contracts/coach-activity-report.md §8.2,
 * specs/041-multi-coach-governance/contracts/audit-log-api.md.
 *
 * Ruta `/club/historial`, visible a coach y admin (a diferencia de
 * `/admin/usuarios`, que es solo admin). Filtros de actor (entrenador),
 * período, tipo de registro y atleta, todos reflejados en la query string
 * para que el enlace "Ver historial de {nombre}" del informe de actividad
 * del coach (§6.2 de `coach-activity-report.md`) llegue pre-filtrado.
 *
 * Paginación del lado del servidor (`limit`/`offset`, R-28) sobre la lista
 * cruda que entrega `useClubAuditLog` — sin `@tanstack/react-table`.
 */
import { useState } from "react";
import { History } from "lucide-react";

import { AthleteCombobox } from "@/components/ai/AthleteCombobox";
import { AuditEntryRow } from "@/components/audit/AuditEntryRow";
import { CoachFilter } from "@/components/audit/CoachFilter";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState, isColdStartError } from "@/components/shared/ErrorState";
import { PageHeader } from "@/components/shared/PageHeader";
import { useClubAuditLog } from "@/hooks/governance/useAuditLog";
import { useClubStaff } from "@/hooks/governance/useClubStaff";
import { AUDIT_ENTITY_TYPE_LABELS } from "@/lib/auditLabels";
import { useAuthStore } from "@/store/auth.store";
import type { AuditEntityType, AuditLogFilters } from "@/types/audit.types";

const inputSelectClass =
  "min-h-[48px] rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50 shadow-ring";

const PAGE_SIZE = 20;

const ENTITY_TYPE_OPTIONS = Object.entries(AUDIT_ENTITY_TYPE_LABELS) as [
  AuditEntityType,
  string,
][];

export function ClubHistoryPage() {
  const clubId = useAuthStore((s) => s.user?.club_ids?.[0] ?? null);

  const [actorUserId, setActorUserId] = useState<number | null>(null);
  const [entityType, setEntityType] = useState<AuditEntityType | "">("");
  const [athleteId, setAthleteId] = useState<number | null>(null);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [offset, setOffset] = useState(0);

  const { coaches, isLoading: isStaffLoading } = useClubStaff();

  const filters: AuditLogFilters = {
    actor_user_id: actorUserId ?? undefined,
    entity_type: entityType || undefined,
    athlete_id: athleteId ?? undefined,
    from: from || undefined,
    to: to || undefined,
    limit: PAGE_SIZE,
    offset,
  };

  const auditQuery = useClubAuditLog(clubId, filters);

  const items = auditQuery.data?.items ?? [];
  const total = auditQuery.data?.total ?? 0;
  const hasActiveFilters =
    actorUserId !== null ||
    entityType !== "" ||
    athleteId !== null ||
    from !== "" ||
    to !== "";

  function resetFilters() {
    setActorUserId(null);
    setEntityType("");
    setAthleteId(null);
    setFrom("");
    setTo("");
    setOffset(0);
  }

  function updateAndResetPage<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value);
      setOffset(0);
    };
  }

  const canGoPrev = offset > 0;
  const canGoNext = offset + PAGE_SIZE < total;

  return (
    <section className="space-y-5" data-testid="club-history-page">
      <PageHeader
        title="Historial del club"
        subtitle="Quién hizo qué y cuándo. Visible solo para el equipo del club."
      />

      {/* Filtros */}
      <div
        className="rounded-xl bg-white p-4 shadow-card"
        data-testid="club-history-filters"
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:items-end lg:grid-cols-5">
          <CoachFilter
            coaches={coaches}
            value={actorUserId}
            onChange={updateAndResetPage(setActorUserId)}
            disabled={isStaffLoading}
          />

          <div className="flex flex-col gap-1">
            <label
              htmlFor="filter-entity-type"
              className="text-xs font-medium text-mid-gray"
            >
              Tipo de registro
            </label>
            <select
              id="filter-entity-type"
              value={entityType}
              onChange={(e) =>
                updateAndResetPage(setEntityType)(
                  e.target.value as AuditEntityType | "",
                )
              }
              className={inputSelectClass}
            >
              <option value="">Todos los tipos</option>
              {ENTITY_TYPE_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          <AthleteCombobox
            value={athleteId}
            onChange={updateAndResetPage(setAthleteId)}
            label="Atleta"
            allowAny
            anyLabel="Todos los atletas"
            id="filter-athlete"
          />

          <div className="flex flex-col gap-1">
            <label htmlFor="filter-from" className="text-xs font-medium text-mid-gray">
              Desde
            </label>
            <input
              id="filter-from"
              type="date"
              value={from}
              onChange={(e) => updateAndResetPage(setFrom)(e.target.value)}
              className={inputSelectClass}
            />
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="filter-to" className="text-xs font-medium text-mid-gray">
              Hasta
            </label>
            <input
              id="filter-to"
              type="date"
              value={to}
              onChange={(e) => updateAndResetPage(setTo)(e.target.value)}
              className={inputSelectClass}
            />
          </div>
        </div>

        {hasActiveFilters && (
          <div className="mt-3">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="min-h-[48px]"
              onClick={resetFilters}
            >
              Limpiar filtros
            </Button>
          </div>
        )}
      </div>

      {/* Loading */}
      {auditQuery.isLoading && (
        <div
          className="space-y-2 rounded-xl bg-white p-4 shadow-card"
          role="status"
          aria-live="polite"
        >
          <span className="sr-only">Cargando historial…</span>
          {Array.from({ length: 6 }).map((_, idx) => (
            <div key={idx} className="h-14 animate-pulse rounded-lg bg-light-gray" />
          ))}
        </div>
      )}

      {/* Error */}
      {auditQuery.isError && !auditQuery.isLoading && (
        <ErrorState
          message="No se pudo cargar el historial del club."
          onRetry={async () => {
            await auditQuery.refetch();
          }}
          isColdStart={isColdStartError(auditQuery.error)}
        />
      )}

      {/* Empty */}
      {!auditQuery.isLoading && !auditQuery.isError && items.length === 0 && (
        <EmptyState
          icon={History}
          title="No hay registros para los filtros seleccionados."
        />
      )}

      {/* Lista */}
      {!auditQuery.isLoading && !auditQuery.isError && items.length > 0 && (
        <>
          <div className="space-y-2">
            {items.map((entry) => (
              <div key={entry.id} data-testid="club-history-row">
                <AuditEntryRow entry={entry} />
              </div>
            ))}
          </div>

          <div
            className="flex items-center justify-between gap-3"
            data-testid="club-history-pagination"
          >
            <p className="text-xs text-mid-gray">
              {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} de {total}
            </p>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="min-h-[48px]"
                disabled={!canGoPrev}
                onClick={() => setOffset((prev) => Math.max(0, prev - PAGE_SIZE))}
              >
                Anterior
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="min-h-[48px]"
                disabled={!canGoNext}
                onClick={() => setOffset((prev) => prev + PAGE_SIZE)}
              >
                Siguiente
              </Button>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
