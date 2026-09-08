import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  Bike,
  ExternalLink,
  Info,
  Link2,
  Loader2,
  Mail,
  RefreshCw,
  Ruler,
  Sparkles,
  TrendingUp,
  Unlink,
  User,
} from "lucide-react";
import { useMutation } from "@tanstack/react-query";

import { ActivityCard } from "@/components/activities/ActivityCard";
import { ConnectionStatusBadge } from "@/components/activities/ConnectionStatusBadge";
import { AnthropometryForm } from "@/components/athletes/AnthropometryForm";
import { AnthropometryHistory } from "@/components/athletes/AnthropometryHistory";
import { AthleteInfoCard } from "@/components/athletes/AthleteInfoCard";
import { LinkedParentsCard } from "@/components/athletes/LinkedParentsCard";
import { AthleteNewslettersTabPanel } from "@/components/training/AthleteNewslettersTabPanel";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatCard } from "@/components/shared/StatCard";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { apiClient } from "@/api/client";
import { cn } from "@/lib/utils";
import { formatDateMedium } from "@/lib/datetime";
import { getMeasurementStatusMeta } from "@/lib/measurementStatus";
import { useAthlete } from "@/hooks/athletes/useAthlete";
import { useAnthropometry } from "@/hooks/athletes/useAnthropometry";
import { useGrowthSummary } from "@/hooks/athletes/useGrowthSummary";
import { useAthleteActivities } from "@/hooks/activities/useAthleteActivities";
import {
  useConnectStrava,
  useDisconnectStrava,
  useStravaConnection,
} from "@/hooks/activities/useStravaConnection";
import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";

// T096 (feature 036, US6): Insights IA — arrastra recharts (EvolutionChart,
// DistributionChart) al bundle sin importar si el tab se abre o no. Mismo
// patrón lazy-load usado en el resto de tabs pesados.
const AthleteAIAnalysisTab = lazy(() =>
  import("@/components/athletes/ai/AthleteAIAnalysisTab").then((m) => ({
    default: m.AthleteAIAnalysisTab,
  })),
);

// T042 (feature 040, US2): el tab Crecimiento arrastra `GrowthCharts`
// (recharts) — mismo patrón lazy-load que Insights IA, así el chunk de
// entrada deja de importar recharts de forma estática (research.md R-08).
const GrowthTab = lazy(() =>
  import("@/components/athletes/growth/GrowthTab").then((m) => ({
    default: m.GrowthTab,
  })),
);

type Tab =
  | "info"
  | "anthropometry"
  | "growth"
  | "ai_analysis"
  | "newsletters"
  | "activities";

const VALID_TABS: readonly Tab[] = [
  "info",
  "anthropometry",
  "growth",
  "ai_analysis",
  "newsletters",
  "activities",
] as const;

function parseTabParam(raw: string | null): Tab | null {
  if (raw && (VALID_TABS as readonly string[]).includes(raw)) {
    return raw as Tab;
  }
  return null;
}

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
 * StravaTabPanel — tarjeta de conexión Strava + listado de actividades
 * sincronizadas del atleta (feature 025, T025/T026).
 *
 * Se monta únicamente cuando el tab "Actividades" está activo, así las
 * queries de conexión/actividades no compiten con el resto de la página en
 * la carga inicial (mismo criterio que `AthleteNewslettersTabPanel`).
 *
 * Estados de conexión: none/active/broken/disconnected (ver
 * `ConnectionStatusBadge`). El CTA de conexión está disponible según el rol
 * (RBAC) — autorizar la conexión OAuth de Strava ES el consentimiento
 * afirmativo, sin checkbox de consentimiento aparte.
 *
 * Sin UI de mapa/ubicación en ningún estado — `ActivityCard` no expone esos
 * campos (ver su docstring).
 */
function StravaTabPanel({ athleteId }: { athleteId: number }) {
  const connectionQuery = useStravaConnection(athleteId);
  const activitiesQuery = useAthleteActivities(athleteId, {
    page: 1,
    page_size: ACTIVITIES_PAGE_SIZE,
  });
  const connectMutation = useConnectStrava(athleteId);
  const disconnectMutation = useDisconnectStrava(athleteId);
  const [showDisconnectConfirm, setShowDisconnectConfirm] = useState(false);

  const connection = connectionQuery.data;
  const status = connection?.status ?? "none";

  const handleConnect = () => {
    connectMutation.mutate(undefined, {
      onSuccess: (data) => {
        // Redirección real de navegador — no es una ruta SPA, es la página
        // de autorización de Strava (contracts/api.md §A POST /connect).
        window.location.href = data.authorize_url;
      },
    });
  };

  const handleDisconnect = () => {
    disconnectMutation.mutate(undefined, {
      onSuccess: () => setShowDisconnectConfirm(false),
    });
  };

  const activities = activitiesQuery.data?.items ?? [];
  const total = activitiesQuery.data?.total ?? 0;

  return (
    <div className="space-y-4">
      {/* Connection card */}
      <div className="rounded-xl bg-white p-5 shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3
            className="font-display flex items-center gap-2 text-sm text-charcoal"
            style={{ letterSpacing: "0.2px" }}
          >
            <Bike size={16} />
            Conexión con Strava
          </h3>

          {connectionQuery.isLoading ? (
            <div className="h-6 w-24 animate-pulse rounded-full bg-light-gray" />
          ) : (
            <ConnectionStatusBadge status={status} />
          )}
        </div>

        {/* Loading */}
        {connectionQuery.isLoading && (
          <div className="mt-4 space-y-2">
            <div className="h-4 w-64 animate-pulse rounded bg-light-gray" />
            <div className="h-9 w-40 animate-pulse rounded-lg bg-light-gray" />
          </div>
        )}

        {/* Error */}
        {connectionQuery.isError && !connectionQuery.isLoading && (
          <p className="mt-4 text-sm text-mid-gray">
            No se pudo cargar el estado de la conexión.{" "}
            <button
              type="button"
              onClick={() => connectionQuery.refetch()}
              className="font-medium text-charcoal underline underline-offset-2 transition-opacity hover:opacity-70"
            >
              Reintentar
            </button>
          </p>
        )}

        {/* Loaded */}
        {connection && !connectionQuery.isLoading && !connectionQuery.isError && (
          <div className="mt-4 space-y-3">
            {status === "active" && (
              <p className="text-sm text-mid-gray">
                Cuenta autorizada por{" "}
                <span className="font-medium text-charcoal">
                  {connection.authorized_by ?? "—"}
                </span>
                {connection.last_sync_at && (
                  <> · Última sincronización: {formatDateMedium(connection.last_sync_at)}</>
                )}
              </p>
            )}
            {status === "broken" && (
              <p className="text-sm text-amber-700">
                La conexión con Strava dejó de funcionar (autorización revocada o
                expirada). Vuelve a conectar la cuenta para reanudar la
                sincronización.
              </p>
            )}
            {status === "disconnected" && (
              <p className="text-sm text-mid-gray">
                La sincronización está detenida
                {connection.disconnected_at && (
                  <> desde el {formatDateMedium(connection.disconnected_at)}</>
                )}
                . Las actividades ya sincronizadas se conservan.
              </p>
            )}
            {status === "none" && (
              <p className="text-sm text-mid-gray">
                Conecta la cuenta de Strava del atleta para que sus actividades
                (duración, distancia, frecuencia cardiaca) aparezcan aquí
                automáticamente.
              </p>
            )}

            <div className="flex flex-wrap items-center gap-2">
              {(status === "none" || status === "disconnected" || status === "broken") && (
                <Button
                  type="button"
                  size="default"
                  onClick={handleConnect}
                  disabled={connectMutation.isPending}
                  className="gap-2"
                >
                  {connectMutation.isPending ? (
                    <Loader2 size={16} className="animate-spin" aria-hidden="true" />
                  ) : status === "none" ? (
                    <Link2 size={16} aria-hidden="true" />
                  ) : (
                    <RefreshCw size={16} aria-hidden="true" />
                  )}
                  {status === "none" ? "Conectar con Strava" : "Reconectar"}
                </Button>
              )}

              {status === "active" && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setShowDisconnectConfirm(true)}
                  disabled={disconnectMutation.isPending}
                  className="gap-2"
                >
                  <Unlink size={16} aria-hidden="true" />
                  Desconectar
                </Button>
              )}

              <a
                href="https://www.strava.com"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-xs font-medium text-link-blue transition-opacity hover:opacity-70"
              >
                Strava <ExternalLink size={12} aria-hidden="true" />
              </a>
            </div>

            {connectMutation.isError && (
              <p className="text-xs text-red-600" role="alert">
                No se pudo iniciar la conexión con Strava. Intenta de nuevo.
              </p>
            )}
            {disconnectMutation.isError && (
              <p className="text-xs text-red-600" role="alert">
                No se pudo desconectar. Intenta de nuevo.
              </p>
            )}
          </div>
        )}
      </div>

      {/* Activities list */}
      <div className="rounded-xl bg-white p-5 shadow-card">
        <h3
          className="font-display mb-4 flex items-center gap-2 text-sm text-charcoal"
          style={{ letterSpacing: "0.2px" }}
        >
          <Activity size={16} />
          Actividades sincronizadas
        </h3>

        {/* Loading */}
        {activitiesQuery.isLoading && (
          <div className="space-y-3">
            {[...Array(2)].map((_, i) => (
              <div key={i} className="h-24 animate-pulse rounded-xl bg-light-gray" />
            ))}
          </div>
        )}

        {/* Error */}
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

        {/* Empty */}
        {!activitiesQuery.isLoading && !activitiesQuery.isError && activities.length === 0 && (
          <p className="text-sm text-mid-gray">
            {status === "active"
              ? "Todavía no ha llegado ninguna actividad sincronizada. Aparecerán aquí automáticamente cuando el atleta suba una rodada a Strava."
              : "Sin actividades sincronizadas."}
          </p>
        )}

        {/* List */}
        {!activitiesQuery.isLoading && !activitiesQuery.isError && activities.length > 0 && (
          <div className="space-y-3">
            {activities.map((activity) => (
              <ActivityCard key={activity.id} activity={activity} canLink />
            ))}
            {total > activities.length && (
              <p className="pt-1 text-xs text-mid-gray">
                Mostrando las {activities.length} actividades más recientes de {total}.
              </p>
            )}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={showDisconnectConfirm}
        title="Desconectar Strava"
        description={
          <>
            <span className="font-medium text-charcoal">
              Se detendrá la sincronización de actividades de este atleta
            </span>
            <br />
            Las actividades ya sincronizadas se conservan. Podrás volver a conectar la cuenta cuando quieras.
          </>
        }
        confirmLabel="Desconectar"
        tone="danger"
        isPending={disconnectMutation.isPending}
        errorMessage={disconnectMutation.isError ? "No se pudo desconectar. Intenta de nuevo." : undefined}
        onCancel={() => setShowDisconnectConfirm(false)}
        onConfirm={handleDisconnect}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Skeletons de suspense mientras cargan los chunks lazy (Insights IA)
// ---------------------------------------------------------------------------

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

// T042 (feature 040, US2) — fallback mientras se descarga el chunk lazy de
// GrowthTab. Sólo cubre la carga del chunk en sí (una vez, por visita); el
// propio GrowthTab ya tiene sus estados de carga de datos (skeleton del
// resumen, etc.) para cuando el chunk ya está montado.
function GrowthTabSkeleton() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Cargando crecimiento…"
      className="space-y-4"
    >
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[...Array(4)].map((_, i) => (
          <Skeleton key={i} className="h-24 w-full rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-64 w-full rounded-xl" />
    </div>
  );
}

export function AthleteDetailPage() {
  const { id } = useParams();
  const athleteId = Number(id);
  const athleteQuery = useAthlete(athleteId, Number.isFinite(athleteId));
  const anthropometryQuery = useAnthropometry(athleteId);
  // T070 (feature 040, US5): las tarjetas superiores (etapa, talla + P,
  // velocidad, próxima medición) leen del resumen calculado en el servidor,
  // no de `athlete.latest_anthropometry` (FR-020) — se piden siempre, no
  // sólo cuando el tab Crecimiento está activo.
  const growthSummaryQuery = useGrowthSummary(athleteId, Number.isFinite(athleteId));
  const role = useAuthStore((s) => s.user?.role);
  const isParent = role === UserRole.parent;

  // FE-2: el tab inicial puede venir del query string (?tab=ai_analysis).
  // Permite que el combobox del tab "Insights históricos" en
  // RaceAnalysisPage enrute directo al histórico del deportista.
  // Si el rol es parent y la URL pide "newsletters" → fallback silencioso a "info".
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTabFromUrl = parseTabParam(searchParams.get("tab"));
  const tabFromUrl =
    rawTabFromUrl === "newsletters" && isParent ? null : rawTabFromUrl;
  const [activeTab, setActiveTab] = useState<Tab>(tabFromUrl ?? "info");
  const [showForm, setShowForm] = useState(false);
  const [reportSent, setReportSent] = useState(false);
  const reportSentTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Mantener el URL en sync con la pestaña activa para que recargar la
  // página preserve el contexto del deportista + tab elegido.
  const updateTab = (tab: Tab) => {
    setActiveTab(tab);
    const next = new URLSearchParams(searchParams);
    if (tab === "info") {
      next.delete("tab");
    } else {
      next.set("tab", tab);
    }
    setSearchParams(next, { replace: true });
  };

  // Reaccionar a cambios externos del query string (back/forward del navegador).
  // Si el rol es parent y pide "newsletters" → fallback silencioso a "info".
  useEffect(() => {
    const rawUrlTab = parseTabParam(searchParams.get("tab"));
    const urlTab = rawUrlTab === "newsletters" && isParent ? null : rawUrlTab;
    if (urlTab && urlTab !== activeTab) {
      setActiveTab(urlTab);
    }
    // No incluimos activeTab para no entrar en loop al setear desde updateTab.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // TODO: Este botón será eliminado cuando se implemente el cron job mensual automático.
  //       Ver: backend/app/routers/reports.py - POST /athletes/{id}/report/email
  const sendReportMutation = useMutation({
    mutationFn: () =>
      apiClient.post<{ queued: boolean; template: string }>(
        `/api/athletes/${athleteId}/report/email`,
      ),
    onSuccess: () => {
      setReportSent(true);
      reportSentTimerRef.current = setTimeout(() => setReportSent(false), 3000);
    },
  });

  const records = anthropometryQuery.data ?? [];

  // FR-020 (feature 040, US5): la página YA NO salta sola al tab Crecimiento
  // en cuanto detecta registros — abre siempre en "Info general" salvo que
  // la URL pida otro tab explícitamente (ver `tabFromUrl` arriba).

  useEffect(() => {
    return () => {
      if (reportSentTimerRef.current) clearTimeout(reportSentTimerRef.current);
    };
  }, []);

  if (athleteQuery.isLoading) {
    return (
      <section className="space-y-4">
        <div className="h-36 animate-pulse rounded-xl bg-light-gray" />
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-light-gray" />
          ))}
        </div>
        <div className="flex gap-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-10 w-32 animate-pulse rounded-lg bg-light-gray" />
          ))}
        </div>
      </section>
    );
  }

  if (athleteQuery.isError) {
    return (
      <section className="space-y-3">
        <PageHeader
          title="Atleta no encontrado"
          subtitle="No existe un atleta con ese ID o no tienes permisos para verlo."
          backTo={{ to: "/athletes", label: "Volver a la lista" }}
        />
      </section>
    );
  }

  if (!athleteQuery.data) return null;

  const athlete = athleteQuery.data;
  const latest = athlete.latest_anthropometry;

  const tabClasses = (tab: Tab) =>
    cn(
      "flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
      activeTab === tab
        ? "bg-charcoal text-white"
        : "bg-white text-mid-gray shadow-ring hover:text-charcoal",
    );

  return (
    <section className="space-y-4">
      {/* Hero Card */}
      <AthleteInfoCard athlete={athlete} />

      {/* Stat Cards Row — feature 040 (US5, T070): etapa, talla + percentil,
          velocidad y estado de próxima medición, todo desde el resumen de
          crecimiento calculado en el servidor (FR-020), no de
          `athlete.latest_anthropometry`. */}
      {(() => {
        const summary = growthSummaryQuery.data;
        const isLoading = growthSummaryQuery.isLoading;
        const height = summary?.latest?.height ?? null;
        const velocity = summary?.velocity ?? null;
        const measurement = summary?.measurement;
        const measurementMeta = measurement ? getMeasurementStatusMeta(measurement.status) : null;

        return (
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard label="Etapa" value={summary?.stage ?? "—"} isLoading={isLoading} />
            <StatCard
              label="Talla"
              value={height ? `${height.value} cm` : "—"}
              hint={height ? `P${Math.round(height.percentile)}` : "Sin referencia para la edad"}
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

      {/* Parents */}
      <LinkedParentsCard athleteId={athlete.id} />

      {/* Tabs */}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={tabClasses("info")}
          onClick={() => updateTab("info")}
        >
          <User size={14} />
          Info general
        </button>
        <button
          type="button"
          className={tabClasses("anthropometry")}
          onClick={() => updateTab("anthropometry")}
        >
          <Ruler size={14} />
          Antropometría
        </button>
        {records.length > 0 && (
          <button
            type="button"
            className={tabClasses("growth")}
            onClick={() => updateTab("growth")}
          >
            <TrendingUp size={14} />
            Crecimiento
          </button>
        )}
        <button
          type="button"
          className={tabClasses("ai_analysis")}
          onClick={() => updateTab("ai_analysis")}
          data-testid="athlete-tab-ai-analysis"
        >
          <Sparkles size={14} />
          Insights IA
        </button>

        {!isParent && (
          <button
            type="button"
            className={tabClasses("newsletters")}
            onClick={() => updateTab("newsletters")}
            data-testid="athlete-tab-newsletters"
          >
            <Mail size={14} />
            Boletines
          </button>
        )}

        <button
          type="button"
          className={tabClasses("activities")}
          onClick={() => updateTab("activities")}
          data-testid="athlete-tab-activities"
        >
          <Bike size={14} />
          Actividades
        </button>

        {/* TODO: Este botón será eliminado cuando se implemente el cron job mensual automático.
            Ver: backend/app/routers/reports.py - POST /athletes/{id}/report/email */}
        <div className="ml-auto flex flex-col items-end gap-1">
          <button
            type="button"
            disabled={sendReportMutation.isPending || reportSent}
            onClick={() => sendReportMutation.mutate()}
            className={cn(
              "flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium shadow-button-highlight transition-opacity",
              reportSent
                ? "bg-green-600 text-white"
                : "bg-charcoal text-white hover:opacity-70",
              (sendReportMutation.isPending || reportSent) && "cursor-not-allowed opacity-70",
            )}
          >
            {sendReportMutation.isPending ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                Enviando...
              </>
            ) : reportSent ? (
              <>
                <Mail size={14} />
                ¡Enviado!
              </>
            ) : (
              <>
                <Mail size={14} />
                Enviar informe
              </>
            )}
          </button>
          {sendReportMutation.isError && !sendReportMutation.isPending && (
            <p className="text-xs text-red-600">
              Error al enviar. Intenta de nuevo.
            </p>
          )}
        </div>
      </div>

      {/* Tab content — Info general */}
      {activeTab === "info" && (
        <div className="space-y-4">
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
                  {athlete.sex === "M" ? "Masculino" : "Femenino"}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-mid-gray">Categoría</dt>
                <dd className="mt-0.5 font-medium text-charcoal">
                  {athlete.category ?? "Sin categoría"}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-mid-gray">Ingreso al club</dt>
                <dd className="mt-0.5 font-medium text-charcoal">
                  {athlete.club_join_date ?? "—"}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-mid-gray">Tiempo en club</dt>
                <dd className="mt-0.5 font-medium text-charcoal">
                  {athlete.years_in_club != null
                    ? `${athlete.years_in_club.toFixed(1)} años`
                    : "—"}
                </dd>
              </div>
            </dl>
          </div>

          {latest && (
            <div
              className={cn(
                "rounded-xl p-5",
                latest.maturation_status === "Circa-PHV"
                  ? "border border-amber-200 bg-amber-50"
                  : "bg-white shadow-card",
              )}
            >
              <div className="mb-3 flex items-center gap-2">
                {latest.maturation_status === "Circa-PHV" && (
                  <AlertTriangle size={16} className="text-amber-500" />
                )}
                <span
                  className="font-display text-sm text-charcoal"
                  style={{ letterSpacing: "0.2px" }}
                >
                  Implicaciones PHV
                </span>
                <span className="ml-auto text-xs text-mid-gray">
                  Evaluado: {latest.evaluation_date}
                </span>
              </div>
              <p className="text-sm text-mid-gray">{latest.training_implications}</p>
            </div>
          )}
        </div>
      )}

      {/* Tab content — Antropometria */}
      {activeTab === "anthropometry" && (
        <div className="space-y-5">
          <div className="flex items-center justify-between">
            <h3
              className="font-display text-lg text-charcoal"
            >
              Registro de mediciones
            </h3>
            <button
              type="button"
              onClick={() => setShowForm(!showForm)}
              className="rounded-lg bg-charcoal px-3 py-2 text-sm font-medium text-white shadow-button-highlight transition-opacity hover:opacity-70"
            >
              {showForm ? "Cancelar" : "+ Nueva medición"}
            </button>
          </div>

          {showForm && (
            <div className="rounded-xl bg-white p-5 shadow-card">
              <AnthropometryForm
                athleteId={athlete.id}
                athleteSex={athlete.sex}
                athleteBirthDate={athlete.birth_date}
                onSuccess={() => setShowForm(false)}
              />
            </div>
          )}

          <div className="rounded-xl bg-white p-5 shadow-card">
            <AnthropometryHistory
              records={records}
              isLoading={anthropometryQuery.isLoading}
              athleteId={athleteId}
              mode="coach"
            />
          </div>
        </div>
      )}

      {/* Tab content — Insights IA */}
      {activeTab === "ai_analysis" && (
        // T096 (feature 036, US6): lazy-load — recharts (EvolutionChart,
        // DistributionChart) ya no entra al bundle si este tab nunca se
        // abre. T010 (feature 036, US3): key={athlete.id} fuerza un
        // remount limpio al cambiar de atleta. Sin esta key,
        // AthleteAIAnalysisTab es la misma instancia de React entre dos
        // atletas — selección de insight, run activo y estado HITL de uno
        // se filtran al otro.
        <Suspense fallback={<AiTabSkeleton />}>
          <AthleteAIAnalysisTab
            key={athlete.id}
            athlete={athlete}
            mode={isParent ? "parent" : "coach"}
          />
        </Suspense>
      )}

      {/* Tab content — Boletines (solo coach/admin) */}
      {activeTab === "newsletters" && !isParent && (
        <AthleteNewslettersTabPanel athleteId={athleteId} />
      )}

      {/* Tab content — Actividades (Strava) */}
      {activeTab === "activities" && <StravaTabPanel athleteId={athleteId} />}

      {/* Tab content — Crecimiento */}
      {activeTab === "growth" && records.length > 0 && (
        // T042 (feature 040, US2): key={athlete.id} fuerza un remount
        // limpio al cambiar de atleta (mismo criterio que
        // AthleteAIAnalysisTab, ver comentario de su Suspense más abajo).
        <Suspense fallback={<GrowthTabSkeleton />}>
          <GrowthTab
            key={athlete.id}
            athlete={athlete}
            mode="coach"
            onRecordMeasurement={() => updateTab("anthropometry")}
          />
        </Suspense>
      )}
    </section>
  );
}
