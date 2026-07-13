/**
 * PendingInbox — Row 2 ("Pending-work inbox") del Inicio rediseñado del
 * coach (feature 031, US2, `contracts/home-tiles.md` §"Row 2 — Pending-work
 * inbox").
 *
 * Shell únicamente (T032): fija el orden de las 5 filas (resultados por
 * importar → actividades sin enlazar → boletines pendientes →
 * consentimientos pendientes → insights IA desactualizados) y el manejo
 * genérico de `RowState` (`data-model.md` §2):
 *   - `undefined` → la fuente todavía está cargando → fila-esqueleto.
 *   - `null`      → la fuente no está disponible → la fila se **omite**
 *     por completo (nunca como línea vacía, spinner eterno ni error —
 *     FR-004, US2 acceptance #2).
 *   - `{count, href}` → fila resuelta → ícono + conteo + etiqueta corta +
 *     chevron, en un único `Link` de ≥48px de alto (Constitution III).
 *
 * T033–T036 (este archivo) conectan cada fila a su fuente real, per
 * `data-model.md` §2 / `contracts/home-tiles.md`:
 *   - T033 "Resultados por importar" — MISMO `useRaceEventsList` que
 *     `NextRaceTile` (mismo queryKey → sin request adicional, research.md
 *     R2), filtrado client-side `!has_results && event_date < today`.
 *   - T034 "Actividades sin enlazar" — `useActivityReview({linked:"false",
 *     page:1, page_size:1}).total`.
 *   - T035 "Boletines pendientes del mes" — 028's
 *     `useNewsletterStatusSummary(currentYear, currentMonth)`, contando
 *     ítems con `status !== "sent"`.
 *   - T036 "Consentimientos pendientes" / "Insights IA desactualizados" —
 *     `useCoachSummary().consents_pending` / `.insights_stale`.
 * T037 (este archivo) agrega el estado positivo "todo al día": se muestra
 * únicamente cuando toda fila que **ya resolvió** (no `undefined`) reporta
 * `count === 0` y al menos una fila resolvió de verdad — nunca mientras
 * cualquier fila sigue en `undefined`/cargando (esa es la fila-esqueleto,
 * no un all-clear real; `contracts/home-tiles.md` §"All-clear state",
 * `data-model.md` §2). Las filas `null` (fuente no disponible) no cuentan
 * como "resolvió" para este cálculo — se siguen omitiendo, tal como en el
 * listado normal. Las pruebas (T038+) llegan en tareas posteriores.
 */
import { useMemo } from "react";
import { Link } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import {
  CheckCircle2,
  ChevronRight,
  FileClock,
  Link2Off,
  Mail,
  ShieldAlert,
  Sparkles,
} from "lucide-react";

import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { useRaceEventsList } from "@/hooks/race/useRaceEvents";
import { useActivityReview } from "@/hooks/activities/useActivityReview";
import { useNewsletterStatusSummary } from "@/hooks/training/useNewsletterStatusSummary";
import { useCoachSummary } from "@/hooks/dashboard/useCoachSummary";
import { CLUB_TIMEZONE, currentSeason, diffDaysFromToday } from "@/lib/datetime";
import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";

/**
 * `/athletes` (lista) está restringida a `UserRole.coach` (ver `src/App.tsx`)
 * — admin NO tiene acceso y `ProtectedRoute` lo redirige en silencio al
 * dashboard. `research.md` R11 sólo había contemplado `/athletes/:id`
 * (cubierto por `AthleteLink`, specs/028) al concluir "no admin-specific
 * branching is needed"; la fila "Consentimientos pendientes" (T036) apunta
 * a `/athletes` (la lista, no un detalle) y quedó fuera de ese análisis.
 * T049 (US4) lo confirmó como dead-end real para admin; este gate —mismo
 * patrón que `AthleteLink`— es el fix de contingencia T050. Mantener
 * sincronizado con el `allowedRoles` de esa ruta.
 */
const ATHLETES_LIST_ALLOWED_ROLES: readonly UserRole[] = [UserRole.coach];

/**
 * `RowState`, `data-model.md` §2 — tres estados independientes por fila:
 * cargando (`undefined`), no disponible (`null`, la fila se omite) o
 * resuelta (`{count, href}`).
 */
export type RowState = { count: number; href: string } | null | undefined;

interface PendingRowSpec {
  id: string;
  icon: LucideIcon;
  /** Etiqueta corta en español, tal como aparece en `contracts/home-tiles.md`. */
  label: string;
  state: RowState;
}

/** "Hoy" en `CLUB_TIMEZONE`, para `useNewsletterStatusSummary(year, month)` (T035). */
function useCurrentYearMonth(): { year: number; month: number } {
  return useMemo(() => {
    const [year, month] = new Intl.DateTimeFormat("en-CA", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      timeZone: CLUB_TIMEZONE,
    })
      .format(new Date())
      .split("-")
      .map(Number);
    return { year, month };
  }, []);
}

export function PendingInbox() {
  // T050 — rol actual, para gatear la fila "consents-pending" (única fila
  // de esta sección que apunta a `/athletes`, coach-only).
  const role = useAuthStore((state) => state.user?.role);
  const canOpenAthletesList = role !== undefined && ATHLETES_LIST_ALLOWED_ROLES.includes(role);

  // T033 — misma queryKey que `NextRaceTile` (["raceEvents","list",{season}]):
  // reutiliza el cache de TanStack Query, no dispara un request adicional.
  const raceQuery = useRaceEventsList({ season: currentSeason() });
  const resultsToImportState: RowState = raceQuery.isLoading
    ? undefined
    : raceQuery.isError
      ? null
      : {
          count: (raceQuery.data?.items ?? []).filter((item) => {
            const days = diffDaysFromToday(item.event_date);
            return !item.has_results && days !== null && days < 0;
          }).length,
          href: "/competitions?filter=needs-results",
        };

  // T034 — conteo de actividades Strava sin enlazar, club-wide.
  const activitiesQuery = useActivityReview({ linked: "false", page: 1, page_size: 1 });
  const activitiesUnlinkedState: RowState = activitiesQuery.isLoading
    ? undefined
    : activitiesQuery.isError
      ? null
      : { count: activitiesQuery.data?.total ?? 0, href: "/activities?linked=false" };

  // T035 — boletines mensuales del mes en curso (028's endpoint de resumen).
  const { year: currentYear, month: currentMonth } = useCurrentYearMonth();
  const newslettersQuery = useNewsletterStatusSummary(currentYear, currentMonth);
  const newslettersDueState: RowState = newslettersQuery.isLoading
    ? undefined
    : newslettersQuery.isError
      ? null
      : {
          count: (newslettersQuery.data?.items ?? []).filter((item) => item.status !== "sent")
            .length,
          href: "/training/athlete-newsletters",
        };

  // T036 — agregados nuevos de `useCoachSummary()`. Un campo `null` (falla
  // parcial del backend, 200 con ese sub-agregado en `null`) se trata igual
  // que la fila "no disponible": se omite, nunca como error ni como cero.
  const coachSummaryQuery = useCoachSummary();
  const consentsPendingState: RowState = coachSummaryQuery.isLoading
    ? undefined
    : coachSummaryQuery.isError || coachSummaryQuery.data?.consents_pending == null
      ? null
      : { count: coachSummaryQuery.data.consents_pending, href: "/athletes" };
  const insightsStaleState: RowState = coachSummaryQuery.isLoading
    ? undefined
    : coachSummaryQuery.isError || coachSummaryQuery.data?.insights_stale == null
      ? null
      : {
          count: coachSummaryQuery.data.insights_stale,
          href: `/competitions/insights/season/${currentSeason()}`,
        };

  // Orden fijo (contracts/home-tiles.md "Row 2").
  const rows: PendingRowSpec[] = [
    {
      id: "results-to-import",
      icon: FileClock,
      label: "Resultados por importar",
      state: resultsToImportState,
    },
    {
      id: "activities-unlinked",
      icon: Link2Off,
      label: "Actividades sin enlazar",
      state: activitiesUnlinkedState,
    },
    {
      id: "newsletters-due",
      icon: Mail,
      label: "Boletines pendientes del mes",
      state: newslettersDueState,
    },
    {
      id: "consents-pending",
      icon: ShieldAlert,
      label: "Consentimientos pendientes",
      state: consentsPendingState,
    },
    {
      id: "insights-stale",
      icon: Sparkles,
      label: "Insights IA desactualizados",
      state: insightsStaleState,
    },
  ];

  // Una fila `null` (fuente no disponible) se omite por completo del
  // listado — nunca se renderiza como línea vacía, spinner infinito ni
  // banner de error (FR-004, US2 acceptance #2).
  const visibleRows = rows.filter(
    (row): row is PendingRowSpec & { state: Exclude<RowState, null> } => row.state !== null,
  );

  if (visibleRows.length === 0) return null;

  // T037 — all-clear (`contracts/home-tiles.md` §"All-clear state",
  // `data-model.md` §2): sólo cuando NINGUNA fila sigue en `undefined`
  // (todas ya resolvieron a `null` u objeto) y, entre las que resolvieron
  // a un objeto real (`{count, href}`, es decir no `null`), todas reportan
  // `count === 0` — y hay al menos una de esas. Una fila `undefined`
  // bloquea el all-clear (es la fila-esqueleto, no un estado positivo
  // confirmado); una fila `null` simplemente no participa del cálculo.
  const noRowStillLoading = rows.every((row) => row.state !== undefined);
  const resolvedRows = rows.filter(
    (row): row is PendingRowSpec & { state: { count: number; href: string } } =>
      row.state != null,
  );
  const isAllClear =
    noRowStillLoading &&
    resolvedRows.length > 0 &&
    resolvedRows.every((row) => row.state.count === 0);

  return (
    <section className="mt-6 space-y-3">
      <h2 className="font-display text-lg text-charcoal">Pendientes de esta semana</h2>
      {isAllClear ? (
        <EmptyState icon={CheckCircle2} title="Todo al día — sin pendientes esta semana" />
      ) : (
        <div className="rounded-xl bg-white shadow-card">
          <ul>
            {visibleRows.map((row, idx) => (
              <li
                key={row.id}
                style={idx > 0 ? { borderTop: "1px solid rgba(34, 42, 53, 0.06)" } : undefined}
              >
                <PendingRow
                  spec={row}
                  restricted={row.id === "consents-pending" && !canOpenAthletesList}
                />
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function PendingRow({
  spec,
  restricted,
}: {
  spec: PendingRowSpec & { state: Exclude<RowState, null> };
  /**
   * T050 (US4) — `true` cuando el rol actual no puede abrir `state.href`
   * (mismo criterio que `AthleteLink`, specs/028): se renderiza el mismo
   * contenido en un `<div>` en vez de un `Link` que nunca debería seguirse.
   */
  restricted: boolean;
}) {
  const { icon: Icon, label, state } = spec;

  if (state === undefined) {
    return (
      <div className="flex min-h-12 items-center gap-3 px-4 py-3" aria-hidden="true">
        <Skeleton className="h-5 w-5 shrink-0 rounded-full" />
        <Skeleton className="h-4 w-6 shrink-0" />
        <Skeleton className="h-4 flex-1" />
      </div>
    );
  }

  const content = (
    <>
      <Icon size={18} className="shrink-0 text-mid-gray" aria-hidden="true" />
      <span className="shrink-0 text-sm font-semibold text-charcoal">{state.count}</span>
      <span className="min-w-0 flex-1 truncate text-sm text-charcoal">{label}</span>
      <ChevronRight size={18} className="shrink-0 text-mid-gray" aria-hidden="true" />
    </>
  );

  if (restricted) {
    return <div className="flex min-h-12 items-center gap-3 px-4 py-3">{content}</div>;
  }

  return (
    <Link
      to={state.href}
      className="flex min-h-12 items-center gap-3 px-4 py-3 transition-opacity hover:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:ring-offset-2"
    >
      {content}
    </Link>
  );
}
