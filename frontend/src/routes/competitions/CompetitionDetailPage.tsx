/**
 * CompetitionDetailPage — detalle de una competencia (válida Copa Valle).
 *
 * Layout:
 *   - Header: "← Competencias", título (nombre), badges, subtitle (sede · fecha)
 *   - Action bar: "Editar metadata", "Eliminar" (admin)
 *   - Acción primaria contextual (importar / ver insights)
 *   - Tabs URL-driven: info | results | conditions | athletes | insights
 *
 * Acceso: coach + admin. Configurado en App.tsx.
 *
 * URL: /competitions/:id?tab=info|results|conditions|athletes|insights
 */
import { lazy, Suspense, useEffect, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import {
  AlertCircle,
  ArrowLeft,
  ChevronDown,
  Edit2,
  Link2,
  Loader2,
  RefreshCw,
  Trophy,
  Upload,
} from "lucide-react";
import { toast } from "sonner";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { PageHeader } from "@/components/shared/PageHeader";
import { buttonVariants } from "@/components/ui/button";
import {
  getRaceEventErrorMessage,
  useCreateCalendarEventForRaceEvent,
  useDeleteRaceEvent,
  useRaceEvent,
} from "@/hooks/race/useRaceEvents";
import { useRaceSeriesList } from "@/hooks/race/useRaceSeries";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";
import type { RaceEventStatus } from "@/types/raceEvents.types";

// ---------------------------------------------------------------------------
// Lazy-load de tabs pesados
// ---------------------------------------------------------------------------

const AthletesTab = lazy(() =>
  import("@/components/competitions/tabs/AthletesTab").then((m) => ({
    default: m.AthletesTab,
  })),
);
const InsightsTab = lazy(() =>
  import("@/components/competitions/tabs/InsightsTab").then((m) => ({
    default: m.InsightsTab,
  })),
);
const StandingsTab = lazy(() =>
  import("@/components/competitions/tabs/StandingsTab").then((m) => ({
    default: m.StandingsTab,
  })),
);

// Tabs livianos — importados directamente (no lazy)
import { InfoTab } from "@/components/competitions/tabs/InfoTab";
import { ConditionsTab } from "@/components/competitions/tabs/ConditionsTab";
import { ResultsTab } from "@/components/competitions/tabs/ResultsTab";

// ---------------------------------------------------------------------------
// Constantes
// ---------------------------------------------------------------------------

type TabValue =
  | "info"
  | "results"
  | "standings"
  | "conditions"
  | "athletes"
  | "insights";

const TAB_VALUES: TabValue[] = [
  "info",
  "results",
  "standings",
  "conditions",
  "athletes",
  "insights",
];

const TAB_LABELS: Record<TabValue, string> = {
  info: "Información",
  results: "Resultados",
  standings: "Clasificación",
  conditions: "Condiciones",
  athletes: "Atletas",
  insights: "Insights IA",
};

const STATUS_LABELS: Record<RaceEventStatus, string> = {
  scheduled: "Planificada",
  completed: "Completada",
  cancelled: "Cancelada",
};

// ---------------------------------------------------------------------------
// Helpers de formato
// ---------------------------------------------------------------------------

function formatDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  if (!year || !month || !day) return iso;
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  return date.toLocaleDateString("es-CO", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

/**
 * US2 (feature 008 Phase 4) — "Editar detalles primero".
 *
 * Construye la URL del formulario de calendario pre-rellenado con los datos de
 * la válida. T014 deberá añadir un split button / dropdown que dispare
 * `navigate(getCalendarNewUrl(raceEventId))` junto a la acción primaria.
 *
 * @param raceEventId — ID de la válida a pre-rellenar en el formulario.
 */
export function getCalendarNewUrl(raceEventId: number): string {
  return `/calendar/events/new?race_event_id=${raceEventId}`;
}

function isBeforeToday(iso: string): boolean {
  const eventDate = new Date(iso + "T00:00:00");
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  return eventDate < now;
}

// ---------------------------------------------------------------------------
// Sub-componente: Tab trigger individual
// ---------------------------------------------------------------------------

function TabTrigger({
  value,
  label,
}: {
  value: TabValue;
  label: string;
}) {
  return (
    <TabsPrimitive.Trigger
      value={value}
      className="flex flex-1 items-center justify-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium text-mid-gray transition-colors data-[state=active]:bg-white data-[state=active]:text-charcoal data-[state=active]:shadow-sm"
    >
      {label}
    </TabsPrimitive.Trigger>
  );
}

// ---------------------------------------------------------------------------
// Sub-componente: Skeleton de header + tabs
// ---------------------------------------------------------------------------

function DetailPageSkeleton() {
  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-6">
      <div className="h-4 w-32 animate-pulse rounded-lg bg-light-gray" />
      <div className="space-y-2">
        <div className="h-7 w-64 animate-pulse rounded-lg bg-light-gray" />
        <div className="h-4 w-48 animate-pulse rounded-lg bg-light-gray" />
      </div>
      <div className="h-12 w-full animate-pulse rounded-xl bg-light-gray" />
      <div className="h-40 w-full animate-pulse rounded-xl bg-light-gray" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-componente: Suspense fallback para tabs lazy
// ---------------------------------------------------------------------------

function TabFallback() {
  return (
    <div
      className="rounded-xl bg-light-gray/40 p-6 text-center text-sm text-mid-gray"
      role="status"
      aria-live="polite"
    >
      Cargando…
    </div>
  );
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export function CompetitionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === UserRole.admin;
  const isCoach = user?.role === UserRole.coach;

  const raceEventId = Number(id);

  // Tab activo — sincronizado con URL
  const tabParam = searchParams.get("tab") as TabValue | null;
  const activeTab: TabValue =
    tabParam && TAB_VALUES.includes(tabParam) ? tabParam : "info";

  function handleTabChange(value: string) {
    setSearchParams({ tab: value }, { replace: true });
  }

  // Datos del evento
  const { data: event, isLoading, isError, refetch, isFetching, error } =
    useRaceEvent(Number.isNaN(raceEventId) ? null : raceEventId);

  // Nivel de la serie (feature 023 — Campeonato Nacional). Solo se necesita
  // para campeonatos (InfoTab usa el fallback "Departamental" en el resto de
  // casos) — evita disparar el fetch en cada válida regular de copa.
  // No existe GET /race-series/{id}; se resuelve filtrando la lista, igual
  // que `useImportPrefill` (feature 015).
  const seriesQuery = useRaceSeriesList(
    {},
    { enabled: event?.is_championship ?? false },
  );
  const seriesLevel = seriesQuery.data?.items.find(
    (s) => s.id === event?.series_id,
  )?.level;

  // 404 → redirect en efecto (evita setState durante render en React 19)
  const is404 =
    isError &&
    typeof error === "object" &&
    error !== null &&
    (error as { response?: { status?: number } }).response?.status === 404;

  useEffect(() => {
    if (is404) {
      navigate("/competitions", { replace: true });
    }
  }, [is404, navigate]);

  // Delete
  const deleteMutation = useDeleteRaceEvent();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Associate to calendar (US1 — one-click)
  const associateMutation = useCreateCalendarEventForRaceEvent();

  function handleAssociateCalendar() {
    associateMutation.mutate(
      { raceEventId },
      {
        onSuccess: () => {
          toast.success("Competencia asociada al calendario.");
        },
        onError: (err) => {
          toast.error(
            getRaceEventErrorMessage(
              err,
              "No se pudo asociar al calendario. Intenta de nuevo.",
            ),
          );
        },
      },
    );
  }

  function handleDeleteConfirm() {
    setDeleteError(null);
    deleteMutation.mutate(
      { id: raceEventId },
      {
        onSuccess: () => {
          navigate("/competitions", { replace: true });
        },
        onError: (err) => setDeleteError(getRaceEventErrorMessage(err)),
      },
    );
  }

  // ── ID inválido ────────────────────────────────────────────────────────────
  if (Number.isNaN(raceEventId)) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-6">
        <div
          className="flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-4"
          role="alert"
        >
          <AlertCircle className="h-5 w-5 shrink-0 text-red-500" aria-hidden="true" />
          <p className="text-sm text-red-700">ID de competencia inválido.</p>
          <Link
            to="/competitions"
            className="ml-auto text-sm font-medium text-charcoal underline hover:no-underline"
          >
            Volver a la lista
          </Link>
        </div>
      </div>
    );
  }

  // ── Loading ────────────────────────────────────────────────────────────────
  if (isLoading) {
    return <DetailPageSkeleton />;
  }

  // ── Error / 404 ────────────────────────────────────────────────────────────
  if (isError || !event) {
    if (is404) {
      // Redirect ya disparado en useEffect — no renderizar nada
      return null;
    }

    return (
      <div className="mx-auto max-w-5xl space-y-4 px-4 py-6">
        <Link
          to="/competitions"
          className="inline-flex items-center gap-1.5 text-sm text-mid-gray hover:text-charcoal"
        >
          <ArrowLeft size={14} aria-hidden="true" />
          Competencias
        </Link>
        <div
          className="flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-4"
          role="alert"
        >
          <AlertCircle className="h-5 w-5 shrink-0 text-red-500" aria-hidden="true" />
          <p className="flex-1 text-sm text-red-700">
            No se pudo cargar la competencia.
          </p>
          <button
            type="button"
            onClick={() => void refetch()}
            disabled={isFetching}
            className="flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-charcoal shadow-ring transition-opacity hover:opacity-70 disabled:opacity-50"
          >
            {isFetching ? (
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCw size={14} aria-hidden="true" />
            )}
            Reintentar
          </button>
        </div>
      </div>
    );
  }

  // ── Acción primaria contextual ─────────────────────────────────────────────
  // `has_results` no está en RaceEventRead — inferimos desde climate+status:
  // Si hay resultados, el status tiende a ser "completed". Lo determinamos
  // verificando si la fecha ya pasó y el status es completed.
  // La acción más útil en cada estado:
  const eventDatePassed = isBeforeToday(event.event_date);
  const isCompleted = event.status === "completed";
  const isCancelled = event.status === "cancelled";

  // Si es scheduled y la fecha ya pasó → probablemente tiene resultados
  // pendientes de importar. Si es completed → ya tiene resultados.
  // Usamos lógica conservadora: solo mostramos "importar" si aún no hay
  // análisis (la CompetitionsListPage tiene `has_results` pero la DetailPage
  // trabaja con RaceEventRead que no lo incluye).
  const showImportCTA = !isCompleted && !isCancelled && eventDatePassed;
  const showInsightsCTA = isCompleted;

  // CF6: botón "Asociar a calendario" — visible solo cuando el backend confirma
  // que NO hay calendar_event asociado (has_calendar_event === false).
  // Si el campo no viene del backend (undefined), no mostramos el botón
  // (comportamiento conservador: evitar duplicados).
  // Solo coach (FR-008: el endpoint es coach-only; no mostramos un botón que
  // daría 403 a admin). Se oculta tras un éxito —aunque el refetch de
  // `has_calendar_event` aún esté en vuelo— para evitar un segundo click que
  // chocaría con el 409 de "ya vinculada".
  const showCalendarCTA =
    isCoach &&
    event.has_calendar_event === false &&
    !isCancelled &&
    !associateMutation.isSuccess;

  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-6">
      {/* ── Header ───────────────────────────────────────────────────── */}
      <header>
        <PageHeader
          title={event.name}
          subtitle={`${event.location ? `${event.location} · ` : ""}${formatDate(event.event_date)} · ${STATUS_LABELS[event.status]}`}
          backTo={{ to: "/competitions", label: "Competencias" }}
          actions={
            <>
              {/* Badge campeonato */}
              {event.is_championship && (
                <span
                  className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800"
                  data-testid="badge-championship"
                >
                  <Trophy size={10} aria-hidden="true" />
                  CD
                </span>
              )}

              {/* Badge cancelada */}
              {isCancelled && (
                <span
                  className="inline-flex items-center rounded-full bg-[rgba(34,42,53,0.08)] px-2 py-0.5 text-xs font-medium text-mid-gray line-through"
                  data-testid="badge-cancelled"
                >
                  Cancelada
                </span>
              )}

              <Link
                to={`/competitions/${raceEventId}/edit`}
                className={buttonVariants({ variant: "outline", size: "sm" })}
                data-testid="btn-edit"
              >
                <Edit2 size={14} aria-hidden="true" />
                Editar metadata
              </Link>

              {/* CF6: badge "En calendario" cuando ya tiene calendar_event */}
              {event.has_calendar_event === true && (
                <span
                  className="inline-flex min-h-9 items-center gap-1.5 rounded-lg bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-700 shadow-ring"
                  data-testid="badge-in-calendar"
                >
                  <Link2 size={14} aria-hidden="true" />
                  En calendario
                </span>
              )}

              {/* CF6 / US1+US2: split button "Asociar a calendario".
                  - Acción primaria (izquierda): one-click, cero re-entrada.
                  - Acción secundaria (chevron dropdown): "Editar detalles primero"
                    navega a /calendar/events/new?race_event_id=N pre-rellenado.
                  Oculto cuando ya está en calendario o la competencia está cancelada. */}
              {showCalendarCTA && (
                <div className="flex" role="group" aria-label="Opciones de calendario">
                  {/* Botón principal — one-click associate */}
                  <button
                    type="button"
                    onClick={handleAssociateCalendar}
                    disabled={associateMutation.isPending}
                    aria-label="Asociar competencia al calendario del club"
                    className={cn(
                      buttonVariants({ variant: "default", size: "sm" }),
                      "min-h-12 min-w-12 rounded-r-none border-r border-r-white/20",
                      associateMutation.isPending && "opacity-70",
                    )}
                    data-testid="btn-associate-calendar"
                  >
                    {associateMutation.isPending ? (
                      <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                    ) : (
                      <Link2 size={14} aria-hidden="true" />
                    )}
                    Asociar a calendario
                  </button>

                  {/* Chevron — abre el dropdown con la acción secundaria */}
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button
                        type="button"
                        aria-label="Más opciones de calendario"
                        disabled={associateMutation.isPending}
                        className={cn(
                          buttonVariants({ variant: "default", size: "sm" }),
                          "min-h-12 w-9 rounded-l-none px-0",
                          associateMutation.isPending && "opacity-70",
                        )}
                        data-testid="btn-associate-calendar-chevron"
                      >
                        <ChevronDown size={14} aria-hidden="true" />
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem
                        onSelect={() => navigate(getCalendarNewUrl(raceEventId))}
                        data-testid="btn-edit-details-first"
                      >
                        <Edit2 size={14} aria-hidden="true" className="mr-2" />
                        Editar detalles primero
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              )}

              {isAdmin && (
                <button
                  type="button"
                  onClick={() => {
                    setDeleteError(null);
                    setDeleteOpen(true);
                  }}
                  className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-1.5 text-sm font-medium text-red-600 transition-colors hover:bg-red-50"
                  data-testid="btn-delete"
                >
                  Eliminar
                </button>
              )}
            </>
          }
        />

        {/* ── Acción primaria contextual ───────────────────────────── */}
        {(showImportCTA || showInsightsCTA) && (
          <div className="mt-4">
            {showImportCTA && (
              <Link
                to={`/competitions/${raceEventId}/import`}
                className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-charcoal px-5 py-2.5 text-sm font-semibold text-white shadow-button-highlight transition-opacity hover:opacity-90"
                data-testid="cta-import"
              >
                <Upload size={16} aria-hidden="true" />
                Importar resultados
              </Link>
            )}
            {showInsightsCTA && !showImportCTA && (
              <button
                type="button"
                onClick={() => handleTabChange("insights")}
                className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-charcoal px-5 py-2.5 text-sm font-semibold text-white shadow-button-highlight transition-opacity hover:opacity-90"
                data-testid="cta-insights"
              >
                <BarChart2Icon size={16} aria-hidden="true" />
                Ver análisis
              </button>
            )}
          </div>
        )}
      </header>

      {/* ── Tabs ─────────────────────────────────────────────────────── */}
      {/* Spec 014: championships have no season ranking — hide standings tab. */}
      <TabsPrimitive.Root
        value={
          // If URL has ?tab=standings on a championship, fall back to info
          activeTab === "standings" && event.is_championship ? "info" : activeTab
        }
        onValueChange={handleTabChange}
        data-testid="competition-tabs"
      >
        <TabsPrimitive.List
          className="flex gap-1 overflow-x-auto rounded-xl bg-light-gray p-1 scrollbar-none"
          aria-label="Secciones de la competencia"
        >
          {TAB_VALUES.filter(
            // Spec 014: campeonatos no tienen ranking de temporada
            (tab) => !(tab === "standings" && event.is_championship),
          ).map((tab) => (
            <TabTrigger key={tab} value={tab} label={TAB_LABELS[tab]} />
          ))}
        </TabsPrimitive.List>

        {/* ── Tab: Información ─────────────────────────────────────── */}
        <TabsPrimitive.Content value="info" className="mt-4">
          <InfoTab event={event} seriesLevel={seriesLevel} />
        </TabsPrimitive.Content>

        {/* ── Tab: Resultados ──────────────────────────────────────── */}
        <TabsPrimitive.Content value="results" className="mt-4">
          <ResultsTab
            raceEventId={raceEventId}
            hasResults={isCompleted}
            onNavigateToInsights={() => handleTabChange("insights")}
          />
        </TabsPrimitive.Content>

        {/* ── Tab: Clasificación general — solo copas (spec 014) ───── */}
        {!event.is_championship && (
          <TabsPrimitive.Content value="standings" className="mt-4">
            <Suspense fallback={<TabFallback />}>
              <StandingsTab raceEventId={raceEventId} />
            </Suspense>
          </TabsPrimitive.Content>
        )}

        {/* ── Tab: Condiciones ─────────────────────────────────────── */}
        <TabsPrimitive.Content value="conditions" className="mt-4">
          <ConditionsTab raceEventId={raceEventId} event={event} />
        </TabsPrimitive.Content>

        {/* ── Tab: Atletas ─────────────────────────────────────────── */}
        <TabsPrimitive.Content value="athletes" className="mt-4">
          <Suspense fallback={<TabFallback />}>
            <AthletesTab raceEventId={raceEventId} />
          </Suspense>
        </TabsPrimitive.Content>

        {/* ── Tab: Insights ────────────────────────────────────────── */}
        <TabsPrimitive.Content value="insights" className="mt-4">
          <Suspense fallback={<TabFallback />}>
            <InsightsTab
              raceEventId={raceEventId}
              hasResults={isCompleted}
              isCoachOrAdmin={isCoach || isAdmin}
              season={parseInt(event.event_date.slice(0, 4), 10)}
              validaNum={event.sequence_number}
            />
          </Suspense>
        </TabsPrimitive.Content>
      </TabsPrimitive.Root>

      {/* ── Dialog de confirmación de eliminación ─────────────────── */}
      <ConfirmDialog
        open={deleteOpen}
        title="Eliminar competencia"
        description={
          <>
            <span className="font-medium text-charcoal">{event.name}</span>
            <br />
            Esta acción es irreversible. La válida se eliminará permanentemente del sistema. Los datos históricos no podrán recuperarse.
          </>
        }
        confirmLabel="Eliminar válida"
        tone="danger"
        isPending={deleteMutation.isPending}
        errorMessage={deleteError ?? undefined}
        onCancel={() => {
          if (!deleteMutation.isPending) {
            setDeleteOpen(false);
            setDeleteError(null);
          }
        }}
        onConfirm={handleDeleteConfirm}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pequeño wrapper para el icono BarChart2 (lucide no tiene BarChart2Icon)
// ---------------------------------------------------------------------------
function BarChart2Icon({ size, ...rest }: { size?: number; "aria-hidden"?: "true" }) {
  return <svg
    xmlns="http://www.w3.org/2000/svg"
    width={size ?? 16}
    height={size ?? 16}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    {...rest}
  >
    <line x1="18" y1="20" x2="18" y2="10" />
    <line x1="12" y1="20" x2="12" y2="4" />
    <line x1="6" y1="20" x2="6" y2="14" />
  </svg>;
}
