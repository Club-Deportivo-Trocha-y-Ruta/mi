import { lazy, Suspense, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  Bike,
  Info,
  Sparkles,
  TrendingUp,
  User,
} from "lucide-react";

import { ActivityCard } from "@/components/activities/ActivityCard";
import { AthleteInfoCard } from "@/components/athletes/AthleteInfoCard";
import { StatCard } from "@/components/shared/StatCard";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { getMeasurementStatusMeta } from "@/lib/measurementStatus";
import { useAthlete } from "@/hooks/athletes/useAthlete";
import { useAnthropometry } from "@/hooks/athletes/useAnthropometry";
import { useGrowthSummary } from "@/hooks/athletes/useGrowthSummary";
import { useAthleteActivities } from "@/hooks/activities/useAthleteActivities";
import { MaturationStatus, Sex } from "@/types/enums";

// T096 (feature 036, US6): Insights IA — arrastra recharts (EvolutionChart,
// DistributionChart) al bundle sin importar si el tab se abre o no. Mismo
// patrón lazy-load que AthleteDetailPage.tsx (vista coach).
const AthleteAIAnalysisTab = lazy(() =>
  import("@/components/athletes/ai/AthleteAIAnalysisTab").then((m) => ({
    default: m.AthleteAIAnalysisTab,
  })),
);

// T062 (feature 040, US4): el tab Crecimiento pasa a ser el `GrowthTab`
// compartido con la vista coach (modo padre: tarjetas familiares narrativas
// + curva simplificada + IA de solo lectura) — mismo patrón lazy-load que
// `AthleteDetailPage.tsx` (T042), así el chunk de entrada tampoco arrastra
// recharts desde el lado padre.
const GrowthTab = lazy(() =>
  import("@/components/athletes/growth/GrowthTab").then((m) => ({
    default: m.GrowthTab,
  })),
);

type Tab = "info" | "growth" | "activities" | "ai-analysis";

const ACTIVITIES_PAGE_SIZE = 10;

const MONTHS_ES_SHORT = [
  "ene", "feb", "mar", "abr", "may", "jun",
  "jul", "ago", "sep", "oct", "nov", "dic",
];

/**
 * Fecha corta "12 dic 2026" a partir de un `YYYY-MM-DD` plano (sin hora) —
 * feature 040 (US5, T070). Se parte el string en vez de `new Date(...)`:
 * una fecha sin hora se interpreta como medianoche UTC y, formateada en
 * `America/Bogota` (UTC-5), puede retroceder un día — mismo criterio que
 * `AnthropometryHistory.tsx::formatDate` / `NextMeasurementCard.tsx::formatDueDate`.
 */
function formatSummaryDate(dateStr: string): string {
  const [year, month, day] = dateStr.split("-");
  const label = MONTHS_ES_SHORT[Number(month) - 1] ?? month;
  return `${Number(day)} ${label} ${year}`;
}

/**
 * Etapa de maduración en lenguaje familiar para la tarjeta superior
 * (feature 040, T073 sobre T070). Esta página es la vista familiar completa,
 * no sólo su tab Crecimiento: FR-016 prohíbe la sigla clínica ("Pre-PHV",
 * "Circa-PHV", "Post-PHV") en cualquier superficie que ve un padre, y estas
 * tarjetas quedan por encima de los tabs.
 *
 * Versión corta de la frase de `growth/FamilyStageCard.tsx::stageMessage`
 * (la tarjeta de dentro del tab, que sí tiene espacio para la frase
 * completa). Si cambia una, cambiar la otra.
 */
const FAMILY_STAGE_LABEL: Record<MaturationStatus, string> = {
  [MaturationStatus.PrePHV]: "Desarrollo temprano",
  [MaturationStatus.CircaPHV]: "Pico de crecimiento",
  [MaturationStatus.PostPHV]: "Crecimiento estabilizándose",
};

// T096 (feature 036, US6) — fallback mientras se descarga el chunk lazy de
// AthleteAIAnalysisTab. Sólo cubre la carga del chunk en sí (una vez, por
// visita) — el propio tab ya tiene sus estados de carga de datos (Skeleton
// del header, etc.) para cuando el chunk ya está montado.
function AiTabSkeleton() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Cargando análisis de IA…"
      className="space-y-4"
    >
      <Skeleton className="h-24 w-full rounded-xl" />
      <div className="flex flex-wrap gap-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-24 rounded-lg" />
        ))}
      </div>
      <Skeleton className="h-64 w-full rounded-xl" />
    </div>
  );
}

// T062 (feature 040, US4) — fallback mientras se descarga el chunk lazy de
// GrowthTab. Mismo criterio que AiTabSkeleton/GrowthTabSkeleton de
// `AthleteDetailPage.tsx` (vista coach): sólo cubre la carga del chunk en
// sí, el propio GrowthTab gestiona sus estados de carga de datos.
function GrowthTabSkeleton() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Cargando crecimiento…"
      className="space-y-4"
    >
      <Skeleton className="h-24 w-full rounded-xl" />
      <div className="grid gap-3 sm:grid-cols-2">
        <Skeleton className="h-28 w-full rounded-xl" />
        <Skeleton className="h-28 w-full rounded-xl" />
      </div>
      <Skeleton className="h-64 w-full rounded-xl" />
    </div>
  );
}

export function MyAthleteDetailPage() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const athleteId = Number(id);
  const athleteQuery = useAthlete(athleteId, Number.isFinite(athleteId));
  const anthropometryQuery = useAnthropometry(athleteId);
  // T070 (feature 040, US5): las tarjetas superiores (etapa, talla + P,
  // velocidad, próxima medición) leen del resumen calculado en el servidor,
  // no de `athlete.latest_anthropometry` — mismo criterio que
  // `AthleteDetailPage.tsx` (vista coach).
  const growthSummaryQuery = useGrowthSummary(athleteId, Number.isFinite(athleteId));
  // RBAC (padre solo ve actividades de su propio hijo) se aplica en backend —
  // ver docstring de useAthleteActivities. Query no habilitada hasta tener
  // un athleteId válido, mismo criterio que el resto de la página.
  const activitiesQuery = useAthleteActivities(
    athleteId,
    { page: 1, page_size: ACTIVITIES_PAGE_SIZE },
    Number.isFinite(athleteId),
  );

  // Soportar deep-link desde email: ?tab=ai-analysis&insight=<id>
  const tabParam = searchParams.get("tab") as Tab | null;
  const [activeTab, setActiveTab] = useState<Tab>(
    tabParam === "ai-analysis" ? "ai-analysis" : "info",
  );

  // Si el parámetro cambia (ej: navegación interna), sincronizar.
  useEffect(() => {
    if (tabParam === "ai-analysis") {
      setActiveTab("ai-analysis");
    }
  }, [tabParam]);

  const records = anthropometryQuery.data ?? [];

  if (athleteQuery.isLoading) {
    return (
      <section className="space-y-4">
        <div className="h-5 w-28 animate-pulse rounded bg-light-gray" />
        <div className="h-36 animate-pulse rounded-xl bg-light-gray" />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-light-gray" />
          ))}
        </div>
        <div className="flex gap-2">
          {[...Array(2)].map((_, i) => (
            <div key={i} className="h-10 w-32 animate-pulse rounded-lg bg-light-gray" />
          ))}
        </div>
      </section>
    );
  }

  if (athleteQuery.isError) {
    return (
      <section className="space-y-4">
        <Link
          to="/my-athletes"
          className="flex items-center gap-1 text-sm font-medium text-mid-gray transition-colors hover:text-charcoal"
        >
          <span>←</span>
          <span>Mis Atletas</span>
        </Link>
        <div className="rounded-xl bg-white p-5 shadow-card">
          <p className="text-sm text-mid-gray">
            No se pudo cargar la información del atleta.
          </p>
        </div>
      </section>
    );
  }

  if (!athleteQuery.data) return null;

  const athlete = athleteQuery.data;

  const tabClasses = (tab: Tab) =>
    cn(
      "flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
      activeTab === tab
        ? "bg-charcoal text-white"
        : "bg-white text-mid-gray hover:text-charcoal shadow-ring",
    );

  return (
    <section className="space-y-4">
      {/* Breadcrumb */}
      <Link
        to="/my-athletes"
        className="flex w-fit items-center gap-1 text-sm font-medium text-mid-gray transition-colors hover:text-charcoal"
      >
        <span>←</span>
        <span>Mis Atletas</span>
      </Link>

      {/* Hero Card */}
      <AthleteInfoCard athlete={athlete} backUrl={null} editUrl={null} />

      {/* Stat Cards Row — feature 040 (US5, T070): etapa, talla, velocidad y
          estado de próxima medición, todo desde el resumen de crecimiento
          calculado en el servidor — mismo criterio que `AthleteDetailPage.tsx`
          (vista coach), salvo que aquí la etapa va en lenguaje familiar y la
          talla no lleva percentil (FR-016, vista familiar). */}
      {(() => {
        const summary = growthSummaryQuery.data;
        const isLoading = growthSummaryQuery.isLoading;
        const height = summary?.latest?.height ?? null;
        const velocity = summary?.velocity ?? null;
        const measurement = summary?.measurement;
        const measurementMeta = measurement ? getMeasurementStatusMeta(measurement.status) : null;

        return (
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard
              label="Etapa"
              value={summary?.stage ? FAMILY_STAGE_LABEL[summary.stage] : "—"}
              isLoading={isLoading}
            />
            <StatCard
              label="Talla"
              value={height ? `${height.value} cm` : "—"}
              hint={height ? undefined : "Sin medición registrada"}
              isLoading={isLoading}
            />
            <StatCard
              label="Velocidad de talla"
              value={velocity ? `${velocity.cm_per_year} cm/año` : "—"}
              hint={velocity ? undefined : "Se necesitan 2 mediciones"}
              isLoading={isLoading}
            />
            <StatCard
              label="Próxima medición"
              value={
                measurement?.next_due_date
                  ? formatSummaryDate(measurement.next_due_date)
                  : "Sin medición"
              }
              isLoading={isLoading}
              badge={
                measurementMeta && (
                  <StatusBadge status={measurementMeta.tone} label={measurementMeta.rowLabel} />
                )
              }
            />
          </div>
        );
      })()}

      {/* Tabs */}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={tabClasses("info")}
          onClick={() => setActiveTab("info")}
        >
          <User size={14} />
          Datos
        </button>
        {records.length > 0 && (
          <button
            type="button"
            className={tabClasses("growth")}
            onClick={() => setActiveTab("growth")}
          >
            <TrendingUp size={14} />
            Crecimiento
          </button>
        )}
        <button
          type="button"
          className={tabClasses("activities")}
          onClick={() => setActiveTab("activities")}
          data-testid="parent-tab-activities"
        >
          <Bike size={14} />
          Actividades
        </button>
        <button
          type="button"
          className={tabClasses("ai-analysis")}
          onClick={() => setActiveTab("ai-analysis")}
          data-testid="parent-tab-ai-analysis"
        >
          <Sparkles size={14} />
          Análisis IA
        </button>
      </div>

      {/* Tab content — Datos */}
      {activeTab === "info" && (
        <div className="space-y-4">
          {/* Datos basicos */}
          <div className="rounded-xl bg-white p-5 shadow-card">
            <h3
              className="font-display mb-4 flex items-center gap-2 text-sm text-charcoal"
              style={{ letterSpacing: "0.2px" }}
            >
              <Info size={16} />
              Datos del atleta
            </h3>
            <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-mid-gray">Sexo</dt>
                <dd className="mt-0.5 font-medium text-charcoal">
                  {athlete.sex === Sex.M ? "Masculino" : "Femenino"}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-mid-gray">
                  Categoría
                </dt>
                <dd className="mt-0.5 font-medium text-charcoal">
                  {athlete.category ?? "Sin categoría"}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-mid-gray">
                  Ingreso al club
                </dt>
                <dd className="mt-0.5 font-medium text-charcoal">
                  {athlete.club_join_date ?? "—"}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-mid-gray">
                  Tiempo en club
                </dt>
                <dd className="mt-0.5 font-medium text-charcoal">
                  {athlete.years_in_club != null
                    ? `${athlete.years_in_club.toFixed(1)} años`
                    : "—"}
                </dd>
              </div>
            </dl>
          </div>
          {/* La etapa de desarrollo ("Estado PHV con lenguaje para padres")
              vivía acá duplicada del tab Crecimiento — T062 (feature 040,
              US4) la retira: el tab Crecimiento ya la muestra vía
              `FamilyStageCard`, con la fecha de evaluación ofuscada a
              "mes año" (esta versión mostraba el día exacto). */}
        </div>
      )}

      {/* Tab content — Análisis IA (parent) */}
      {activeTab === "ai-analysis" && (
        // T096 (feature 036, US6): lazy-load — recharts (EvolutionChart,
        // DistributionChart) ya no entra al bundle si este tab nunca se abre.
        // T010 (feature 036, US3, aplicado también en el lado parent al
        // cerrar la feature): key={athlete.id} fuerza un remount limpio si
        // esta página alguna vez se navega de un hijo a otro sin pasar por
        // /my-athletes (ver AthleteDetailPage.tsx, mismo patrón del lado coach).
        <Suspense fallback={<AiTabSkeleton />}>
          <AthleteAIAnalysisTab key={athlete.id} athlete={athlete} mode="parent" />
        </Suspense>
      )}

      {/* Tab content — Crecimiento (feature 040, US4, T062): `GrowthTab`
          compartido con la vista coach en modo padre (tarjetas familiares
          narrativas → curva simplificada → IA de solo lectura → historial).
          key={athlete.id} fuerza un remount limpio al cambiar de atleta,
          mismo criterio que AthleteAIAnalysisTab arriba y que
          AthleteDetailPage.tsx (vista coach). */}
      {activeTab === "growth" && records.length > 0 && (
        <Suspense fallback={<GrowthTabSkeleton />}>
          <GrowthTab key={athlete.id} athlete={athlete} mode="parent" />
        </Suspense>
      )}

      {/* Tab content — Actividades (feature 025, T036). Solo lectura: sin
          controles de conexión ni de enlace a sesión (esos son exclusivos
          del coach/admin, ver FR-007). RBAC de "solo mi hijo" lo aplica el
          backend — acá solo se consume la respuesta ya filtrada. */}
      {activeTab === "activities" && (
        <div className="rounded-xl bg-white p-5 shadow-card">
          <h3
            className="font-display mb-4 flex items-center gap-2 text-sm text-charcoal"
            style={{ letterSpacing: "0.2px" }}
          >
            <Bike size={16} />
            Actividades sincronizadas
          </h3>

          {activitiesQuery.isLoading && (
            <div className="space-y-3">
              {[...Array(2)].map((_, i) => (
                <div key={i} className="h-24 animate-pulse rounded-xl bg-light-gray" />
              ))}
            </div>
          )}

          {activitiesQuery.isError && !activitiesQuery.isLoading && (
            <p className="text-sm text-mid-gray">
              No se pudieron cargar las actividades.{" "}
              <button
                type="button"
                onClick={() => activitiesQuery.refetch()}
                className="font-medium text-charcoal underline underline-offset-2 transition-opacity hover:opacity-70"
              >
                Reintentar
              </button>
            </p>
          )}

          {!activitiesQuery.isLoading &&
            !activitiesQuery.isError &&
            (activitiesQuery.data?.items.length ?? 0) === 0 && (
              <p className="text-sm text-mid-gray">
                Todavía no hay actividades sincronizadas de Strava para tu
                atleta. Aparecerán aquí automáticamente cuando suba una rodada.
              </p>
            )}

          {!activitiesQuery.isLoading &&
            !activitiesQuery.isError &&
            (activitiesQuery.data?.items.length ?? 0) > 0 && (
              <div className="space-y-3">
                {activitiesQuery.data!.items.map((activity) => (
                  <ActivityCard key={activity.id} activity={activity} />
                ))}
                {activitiesQuery.data!.total > activitiesQuery.data!.items.length && (
                  <p className="pt-1 text-xs text-mid-gray">
                    Mostrando las {activitiesQuery.data!.items.length} actividades más
                    recientes de {activitiesQuery.data!.total}.
                  </p>
                )}
              </div>
            )}
        </div>
      )}
    </section>
  );
}
