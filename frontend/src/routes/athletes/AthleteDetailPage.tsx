import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  Bike,
  ExternalLink,
  History,
  Info,
  Link2,
  Loader2,
  Mail,
  RefreshCw,
  Ruler,
  TrendingUp,
  Trophy,
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
import { skinfoldCapturePath } from "@/lib/bodyComposition/eligibility";
import { getMeasurementStatusMeta } from "@/lib/measurementStatus";
import { dropCarrerasParams, resolveLegacyAiTabAlias } from "@/lib/carrerasTabAlias";
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

// Feature 045 (T041, US1): pestaña única «Carreras» — reemplaza a «Insights
// IA» (T096, feature 036) y a la «Carreras» de la feature 044. Arrastra
// recharts (gráficas de progresión, distribución) al bundle sin importar si
// la pestaña se abre o no; cada una de sus vistas es además su propio chunk
// lazy (ver `CarrerasTab`). Mismo patrón lazy-load usado en el resto de tabs
// pesados.
const CarrerasTab = lazy(() =>
  import("@/components/athletes/races/CarrerasTab").then((m) => ({
    default: m.CarrerasTab,
  })),
);

// T042 (feature 040, US2): el tab Crecimiento arrastra `GrowthCharts`
// (recharts) — mismo patrón lazy-load que Carreras, así el chunk de
// entrada deja de importar recharts de forma estática (research.md R-08).
const GrowthTab = lazy(() =>
  import("@/components/athletes/growth/GrowthTab").then((m) => ({
    default: m.GrowthTab,
  })),
);

// T038 (feature 041, US7): tab "Historial" — no es la pestaña por defecto,
// mismo patrón lazy-load que Carreras / Crecimiento.
const AthleteHistoryPanel = lazy(() =>
  import("@/components/athletes/AthleteHistoryPanel").then((m) => ({
    default: m.AthleteHistoryPanel,
  })),
);

type Tab =
  | "info"
  | "anthropometry"
  | "growth"
  | "races"
  | "newsletters"
  | "activities"
  | "history";

const VALID_TABS: readonly Tab[] = [
  "info",
  "anthropometry",
  "growth",
  "races",
  "newsletters",
  "activities",
  "history",
] as const;

/** Tabs que un padre nunca puede ver — usado tanto para el botón (guardado
 * inline con `!isParent`) como para el fallback de deep-link por query
 * string. "races" (feature 045, FR-010) es la pestaña única «Carreras» para
 * coach Y familia: ya no es solo-coach (la audiencia se resuelve con
 * `isParent` al montar `CarrerasTab`). */
const COACH_ONLY_TABS: readonly Tab[] = ["newsletters", "history"];

function parseTabParam(raw: string | null): Tab | null {
  // Alias legado de «Insights IA» (feature 045): hoy es «Carreras». La URL se
  // normaliza en el render (ver `resolveLegacyAiTabAlias`); esto solo evita
  // un cuadro con la pestaña «Info» mientras el redireccionamiento aterriza.
  if (raw === "ai_analysis" || raw === "ai-analysis") return "races";
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
      <div className="rounded-card bg-surface-raised p-5 shadow-card ring-1 ring-hairline">
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
      <div className="rounded-card bg-surface-raised p-5 shadow-card ring-1 ring-hairline">
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
// Skeletons de suspense mientras cargan los chunks lazy (Carreras, Crecimiento)
// ---------------------------------------------------------------------------

// Feature 045 (T041) — fallback mientras se descarga el chunk lazy de
// CarrerasTab (antes T096/feature 036 para AthleteAIAnalysisTab y T075/
// feature 044 para HistoryProgressionCard). Sólo cubre la carga del chunk en
// sí (una vez, por visita) — la pestaña ya tiene su propio esqueleto por
// vista y sus estados de carga de datos para cuando el chunk ya está montado.
function CarrerasTabSkeleton() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Cargando carreras…"
      className="space-y-4"
    >
      <Skeleton className="h-24 w-full rounded-xl" />
      <div className="flex flex-wrap gap-2">
        {Array.from({ length: 3 }).map((_, i) => (
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
  // Feature 046 (T031): salidas hacia el asistente de pliegues cutáneos.
  const navigate = useNavigate();
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

  // FE-2: el tab inicial puede venir del query string (?tab=races).
  // Si el rol es parent y la URL pide un tab solo-coach → fallback silencioso a "info".
  // Feature 045 (T041): «Carreras» (?tab=races[&view=…][&insight=<id>]) es la
  // pestaña única para coach y familia. El alias legado `?tab=ai_analysis`
  // (y `ai-analysis`) se traduce más abajo, ANTES de pintar contenido, a
  // `?tab=races&view=analisis[&insight=<id>]`.
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTabFromUrl = parseTabParam(searchParams.get("tab"));
  const tabFromUrl =
    isParent && rawTabFromUrl && COACH_ONLY_TABS.includes(rawTabFromUrl)
      ? null
      : rawTabFromUrl;
  const [activeTab, setActiveTab] = useState<Tab>(tabFromUrl ?? "info");
  const [showForm, setShowForm] = useState(false);
  const [reportSent, setReportSent] = useState(false);
  const reportSentTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Mantener el URL en sync con la pestaña activa para que recargar la
  // página preserve el contexto del deportista + tab elegido.
  const updateTab = (tab: Tab) => {
    // Volver a tocar la pestaña activa no debe reiniciar su vista (`view`).
    if (tab === activeTab) return;
    setActiveTab(tab);
    const next = new URLSearchParams(searchParams);
    if (tab === "info") {
      next.delete("tab");
    } else {
      next.set("tab", tab);
    }
    // `view` e `insight` son de «Carreras»: no deben viajar a otra pestaña.
    dropCarrerasParams(next);
    setSearchParams(next, { replace: true });
  };

  // Reaccionar a cambios externos del query string (back/forward del navegador).
  // Si el rol es parent y pide un tab solo-coach → fallback silencioso a "info".
  useEffect(() => {
    const rawUrlTab = parseTabParam(searchParams.get("tab"));
    const urlTab =
      isParent && rawUrlTab && COACH_ONLY_TABS.includes(rawUrlTab)
        ? null
        : rawUrlTab;
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

  // Feature 045 (T041): alias legado `?tab=ai_analysis` → Carreras › Análisis
  // IA. Se resuelve ANTES de pintar contenido para que `CarrerasTab` nunca
  // lea la URL sin normalizar (sin destello de «Progresión»).
  const canonicalCarrerasParams = resolveLegacyAiTabAlias(searchParams);
  if (canonicalCarrerasParams) {
    return <Navigate to={{ search: `?${canonicalCarrerasParams}` }} replace />;
  }

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
      "flex min-h-12 items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
      activeTab === tab
        ? "bg-charcoal text-surface"
        : "bg-surface-raised text-mid-gray shadow-ring hover:text-charcoal",
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
        {/* Feature 045 (T041, FR-010) — pestaña ÚNICA «Carreras»: reemplaza
            a «Insights IA» y a la «Carreras» de la feature 044. Progresión,
            Análisis IA y Comparar son vistas dentro de ella (`?view=`). */}
        <button
          type="button"
          className={tabClasses("races")}
          onClick={() => updateTab("races")}
          data-testid="athlete-tab-races"
        >
          <Trophy size={14} />
          Carreras
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

        {!isParent && (
          <button
            type="button"
            className={tabClasses("history")}
            onClick={() => updateTab("history")}
            data-testid="athlete-tab-history"
          >
            <History size={14} />
            Historial
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
        <div className="ml-auto flex scroll-mb-24 flex-col items-end gap-1">
          <button
            type="button"
            disabled={sendReportMutation.isPending || reportSent}
            onClick={() => sendReportMutation.mutate()}
            className={cn(
              "scroll-mb-24 flex min-h-12 items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium shadow-button-highlight transition-opacity",
              reportSent
                ? "bg-green-600 text-white"
                : "bg-charcoal text-surface hover:opacity-70",
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
          <div className="rounded-card bg-surface-raised p-5 shadow-card ring-1 ring-hairline">
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
                "rounded-card p-5",
                latest.maturation_status === "Circa-PHV"
                  ? "border border-amber-200 bg-amber-50"
                  : "bg-surface-raised shadow-card ring-1 ring-hairline",
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
              className="rounded-lg bg-charcoal px-3 py-2 text-sm font-medium text-surface shadow-button-highlight transition-opacity hover:opacity-70"
            >
              {showForm ? "Cancelar" : "+ Nueva medición"}
            </button>
          </div>

          {showForm && (
            <div className="rounded-card bg-surface-raised p-5 shadow-card ring-1 ring-hairline">
              <AnthropometryForm
                athleteId={athlete.id}
                athleteSex={athlete.sex}
                athleteBirthDate={athlete.birth_date}
                onSuccess={() => setShowForm(false)}
                onAddSkinfolds={(recordId) =>
                  navigate(skinfoldCapturePath(athlete.id, recordId))
                }
              />
            </div>
          )}

          <div className="rounded-card bg-surface-raised p-5 shadow-card ring-1 ring-hairline">
            <AnthropometryHistory
              records={records}
              isLoading={anthropometryQuery.isLoading}
              athleteId={athleteId}
              mode="coach"
              onSkinfoldsAction={(record) =>
                navigate(skinfoldCapturePath(athleteId, record.id))
              }
            />
          </div>
        </div>
      )}

      {/* Tab content — Carreras (feature 045, T041). Reemplaza a los
          contenidos «Insights IA» y «Carreras» anteriores. Lazy: recharts
          solo entra al bundle si esta pestaña se abre. key={athlete.id}
          fuerza un remount limpio al cambiar de atleta (T010, feature 036,
          US3): sin ella, la selección de análisis, el run activo y el
          estado HITL de un atleta se filtran al siguiente al navegar sin
          desmontar la ruta. `view`/`insight` los sincroniza la propia
          pestaña con la URL. */}
      {activeTab === "races" && (
        <Suspense fallback={<CarrerasTabSkeleton />}>
          <CarrerasTab
            key={athlete.id}
            athlete={athlete}
            audience={isParent ? "family" : "coach"}
          />
        </Suspense>
      )}

      {/* Tab content — Boletines (solo coach/admin) */}
      {activeTab === "newsletters" && !isParent && (
        <AthleteNewslettersTabPanel athleteId={athleteId} />
      )}

      {/* Tab content — Historial (solo coach/admin) */}
      {activeTab === "history" && !isParent && role && (
        <Suspense
          fallback={
            <div
              className="h-14 animate-pulse rounded-lg bg-light-gray"
              role="status"
              aria-live="polite"
            >
              <span className="sr-only">Cargando historial…</span>
            </div>
          }
        >
          <AthleteHistoryPanel athleteId={athleteId} role={role} />
        </Suspense>
      )}

      {/* Tab content — Actividades (Strava) */}
      {activeTab === "activities" && <StravaTabPanel athleteId={athleteId} />}

      {/* Tab content — Crecimiento */}
      {activeTab === "growth" && records.length > 0 && (
        // T042 (feature 040, US2): key={athlete.id} fuerza un remount
        // limpio al cambiar de atleta (mismo criterio que
        // CarrerasTab, ver comentario de su Suspense más arriba).
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
