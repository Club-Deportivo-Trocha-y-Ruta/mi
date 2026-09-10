/**
 * CoachActivityPage — "Actividad por entrenador" (feature 041 — gobernanza
 * multi-coach, US7, FR-013/FR-031/FR-032). Contrato:
 * specs/041-multi-coach-governance/contracts/coach-activity-report.md §6.
 *
 * Ruta `/training/reports/actividad-entrenadores`, coach + admin. Superficie
 * interna de gestión del club: nunca se renderiza bajo `routes/parents/`, no
 * viaja en ningún correo/PDF/boletín de familia y su query key no se agrega
 * a `PERSIST_ALLOWLIST_PREFIXES` (default-deny, `@/lib/persistAllowList`).
 *
 * Filtros clonados del panel de `ActivityReviewPage`
 * (`frontend/src/routes/activities/ActivityReviewPage.tsx:167-245`): mismo
 * token `inputSelectClass`, `<select>`/`<input type="date">` nativos con
 * `<label htmlFor>` visible. El selector de entrenador reutiliza
 * `useClubStaff` (`@/hooks/governance/useClubStaff`, ya existente — no se
 * duplica), que solo trae personal con `role=coach`, igual que
 * `coaches[]` del backend.
 *
 * Privacidad (Ley 1581): el payload de `useCoachActivity` es nombres de
 * personal adulto y enteros — nada de un deportista aparece en esta página.
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Users, X } from "lucide-react";

import { ActorChip } from "@/components/audit/ActorChip";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState, isColdStartError } from "@/components/shared/ErrorState";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatCard } from "@/components/shared/StatCard";
import { useClubStaff } from "@/hooks/governance/useClubStaff";
import { useCoachActivity } from "@/hooks/governance/useCoachActivity";
import { useAuthStore } from "@/store/auth.store";
import type {
  CoachActivityOut,
  CoachActivityParams,
  CoachActivityRow,
} from "@/types/coachActivity.types";

const inputSelectClass =
  "min-h-12 rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50 shadow-ring";

// ---------------------------------------------------------------------------
// Presets de periodo (§6.2) — aritmética simple en horario local, coherente
// con que `from`/`to` son fechas puras (`YYYY-MM-DD`) que el backend expande
// server-side (§1.1 del contrato). No se usa `toISOString` (desfasaría el
// día en UTC-5): se arma el string a partir de los componentes locales.
// ---------------------------------------------------------------------------

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function toISODate(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

interface DateRange {
  from: string;
  to: string;
}

function currentMonthRange(now = new Date()): DateRange {
  const first = new Date(now.getFullYear(), now.getMonth(), 1);
  const last = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  return { from: toISODate(first), to: toISODate(last) };
}

function previousMonthRange(now = new Date()): DateRange {
  const first = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const last = new Date(now.getFullYear(), now.getMonth(), 0);
  return { from: toISODate(first), to: toISODate(last) };
}

function last30DaysRange(now = new Date()): DateRange {
  const from = new Date(now);
  from.setDate(from.getDate() - 29);
  return { from: toISODate(from), to: toISODate(now) };
}

/** "Temporada" = desde el 1 de enero del año en curso hasta hoy. */
function seasonToDateRange(now = new Date()): DateRange {
  const first = new Date(now.getFullYear(), 0, 1);
  return { from: toISODate(first), to: toISODate(now) };
}

const PERIOD_PRESETS: { id: string; label: string; range: () => DateRange }[] = [
  { id: "current-month", label: "Mes actual", range: currentMonthRange },
  { id: "previous-month", label: "Mes anterior", range: previousMonthRange },
  { id: "last-30-days", label: "Últimos 30 días", range: last30DaysRange },
  { id: "season", label: "Temporada", range: seasonToDateRange },
];

// ---------------------------------------------------------------------------
// Derivados de copy (§6.4) — la forma exacta de la respuesta ya se confirmó
// leyendo `backend/app/schemas/coach_activity.py`; ninguno de los cuatro
// contadores de "Documentos" tiene un campo `total` propio (a diferencia de
// `results_operations.total`), así que el valor principal de esa tarjeta es
// la suma de sus cuatro contadores — decisión tomada acá, documentada en el
// informe de la tarea.
// ---------------------------------------------------------------------------

function documentsTotal(documents: CoachActivityOut["club_totals"]["documents"]): number {
  return (
    documents.reports_approved +
    documents.newsletters_approved +
    documents.newsletters_sent +
    documents.exports
  );
}

function documentsHint(documents: CoachActivityOut["club_totals"]["documents"]): string {
  return (
    `${documents.reports_approved} informes aprobados · ` +
    `${documents.newsletters_approved} boletines aprobados · ` +
    `${documents.newsletters_sent} enviados · ` +
    `${documents.exports} descargas`
  );
}

function hasNoActivity(data: CoachActivityOut): boolean {
  return data.club_totals.audit_entries_count === 0;
}

// ---------------------------------------------------------------------------
// CoachActivityCard
// ---------------------------------------------------------------------------

function CoachActivityCard({
  row,
  from,
  to,
}: {
  row: CoachActivityRow;
  from: string;
  to: string;
}) {
  const { coach, sessions, results_operations, documents } = row;
  const headingId = `coach-activity-heading-${coach.user_id}`;

  return (
    <section
      className="rounded-xl bg-white p-4 shadow-card"
      aria-labelledby={headingId}
      data-testid="coach-activity-card"
      data-coach-id={coach.user_id}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={headingId} className="font-display text-lg text-charcoal">
          <ActorChip
            userId={coach.user_id}
            displayName={coach.display_name}
            isActive={coach.is_active}
          />
        </h2>
        <Link
          to={`/club/historial?actor=${coach.user_id}&from=${from}&to=${to}`}
          className="text-sm font-medium text-link-blue hover:underline"
          data-testid="coach-activity-history-link"
        >
          Ver historial de {coach.display_name}
        </Link>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard
          label="Sesiones"
          value={sessions.total}
          hint={`${sessions.planned} planificadas · ${sessions.executed} ejecutadas · ${sessions.cancelled} canceladas`}
          badge={
            sessions.co_led > 0 ? (
              <p className="text-xs text-mid-gray">{sessions.co_led} en co-dirección</p>
            ) : undefined
          }
        />
        <StatCard label="Registros de asistencia" value={row.attendance_entries_recorded} />
        <StatCard label="Análisis de IA lanzados" value={row.ai_runs_launched} />
        <StatCard
          label="Operaciones de resultados"
          value={results_operations.total}
          hint={`${results_operations.imports} importaciones · ${results_operations.revisions} revisiones · ${results_operations.competitor_links} enlaces`}
        />
        <StatCard
          label="Documentos"
          value={documentsTotal(documents)}
          hint={documentsHint(documents)}
        />
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// CoachActivityPage
// ---------------------------------------------------------------------------

export function CoachActivityPage() {
  const clubId = useAuthStore((s) => s.user?.club_ids?.[0]);

  const [range, setRange] = useState<DateRange>(() => currentMonthRange());
  const [coachUserId, setCoachUserId] = useState<number | null>(null);

  const { coaches: coachOptions, isLoading: isStaffLoading } = useClubStaff();

  const filters: CoachActivityParams = useMemo(
    () => ({
      from: range.from,
      to: range.to,
      coach_user_id: coachUserId ?? undefined,
    }),
    [range.from, range.to, coachUserId],
  );

  const activityQuery = useCoachActivity(clubId, filters);
  const data = activityQuery.data;

  const hasActiveFilters =
    coachUserId !== null ||
    range.from !== currentMonthRange().from ||
    range.to !== currentMonthRange().to;

  function resetFilters() {
    setRange(currentMonthRange());
    setCoachUserId(null);
  }

  return (
    <section className="space-y-5" data-testid="coach-activity-page">
      <PageHeader
        title="Actividad por entrenador"
        subtitle="Resumen interno de gestión del club. No se comparte con las familias."
        backTo={{ to: "/training/reports", label: "Informes del club" }}
      />

      {/* Filtros */}
      <div
        className="rounded-xl bg-white p-4 shadow-card"
        data-testid="coach-activity-filters"
      >
        <div className="flex flex-col gap-3">
          <div role="group" aria-label="Periodo" className="flex flex-wrap gap-2">
            {PERIOD_PRESETS.map((preset) => (
              <button
                key={preset.id}
                type="button"
                onClick={() => setRange(preset.range())}
                className="min-h-12 rounded-lg bg-light-gray px-3 py-2 text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
              >
                {preset.label}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-end sm:gap-3">
            <div className="flex flex-col gap-1">
              <label htmlFor="coach-activity-from" className="text-xs font-medium text-mid-gray">
                Desde
              </label>
              <input
                id="coach-activity-from"
                type="date"
                value={range.from}
                onChange={(e) => setRange((r) => ({ ...r, from: e.target.value }))}
                className={inputSelectClass}
              />
            </div>

            <div className="flex flex-col gap-1">
              <label htmlFor="coach-activity-to" className="text-xs font-medium text-mid-gray">
                Hasta
              </label>
              <input
                id="coach-activity-to"
                type="date"
                value={range.to}
                onChange={(e) => setRange((r) => ({ ...r, to: e.target.value }))}
                className={inputSelectClass}
              />
            </div>

            <div className="flex flex-col gap-1">
              <label htmlFor="coach-activity-coach" className="text-xs font-medium text-mid-gray">
                Entrenador
              </label>
              <select
                id="coach-activity-coach"
                value={coachUserId ?? ""}
                onChange={(e) =>
                  setCoachUserId(e.target.value ? Number(e.target.value) : null)
                }
                disabled={isStaffLoading}
                className={inputSelectClass}
              >
                <option value="">Todos los entrenadores</option>
                {coachOptions.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.displayName}
                  </option>
                ))}
              </select>
            </div>

            {hasActiveFilters && (
              <button
                type="button"
                onClick={resetFilters}
                className="inline-flex min-h-12 items-center gap-1.5 self-end rounded-lg bg-white px-3 py-2 text-sm font-medium text-mid-gray transition-opacity hover:opacity-70 shadow-ring"
              >
                <X size={14} aria-hidden="true" />
                Limpiar filtros
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Error de página (§6.3 — un solo ErrorState, no uno por tarjeta) */}
      {activityQuery.isError && (
        <ErrorState
          message="No se pudo cargar la actividad por entrenador."
          onRetry={() => activityQuery.refetch()}
          isColdStart={isColdStartError(activityQuery.error)}
        />
      )}

      {!activityQuery.isError && (
        <>
          {/* Totales del club */}
          <div
            role="status"
            aria-live="polite"
            aria-busy={activityQuery.isLoading}
            data-testid="coach-activity-club-totals"
            className="space-y-2"
          >
            {activityQuery.isLoading && (
              <span className="sr-only">Cargando actividad por entrenador…</span>
            )}
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatCard
                label="Sesiones del club"
                value={data?.club_totals.sessions.total ?? 0}
                hint={
                  data
                    ? `${data.club_totals.sessions.planned} planificadas · ${data.club_totals.sessions.executed} ejecutadas · ${data.club_totals.sessions.cancelled} canceladas`
                    : undefined
                }
                isLoading={activityQuery.isLoading}
              />
              <StatCard
                label="Registros de asistencia"
                value={data?.club_totals.attendance_entries_recorded ?? 0}
                isLoading={activityQuery.isLoading}
              />
              <StatCard
                label="Análisis de IA"
                value={data?.club_totals.ai_runs_launched ?? 0}
                isLoading={activityQuery.isLoading}
              />
              <StatCard
                label="Documentos"
                value={data ? documentsTotal(data.club_totals.documents) : 0}
                hint={data ? documentsHint(data.club_totals.documents) : undefined}
                isLoading={activityQuery.isLoading}
              />
            </div>
            <p className="text-xs text-mid-gray">
              Cada sesión se cuenta una sola vez en el total del club. Una sesión con dos
              entrenadores cuenta para ambos en sus tarjetas.
            </p>
            {data && hasNoActivity(data) && (
              <p className="text-xs text-mid-gray">
                No hay actividad registrada en el periodo seleccionado. Prueba con otro
                rango de fechas.
              </p>
            )}
          </div>

          {/* Tarjetas por entrenador */}
          {activityQuery.isLoading && (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {[0, 1].map((i) => (
                <div key={i} className="h-40 animate-pulse rounded-xl bg-light-gray" />
              ))}
            </div>
          )}

          {!activityQuery.isLoading && data && data.coaches.length === 0 && (
            <EmptyState
              icon={Users}
              title="Este club todavía no tiene entrenadores registrados."
            />
          )}

          {!activityQuery.isLoading && data && data.coaches.length > 0 && (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {data.coaches.map((row) => (
                <CoachActivityCard
                  key={row.coach.user_id}
                  row={row}
                  from={data.from}
                  to={data.to}
                />
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
