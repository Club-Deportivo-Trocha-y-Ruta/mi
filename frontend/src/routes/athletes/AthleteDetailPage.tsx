import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  Bike,
  CalendarDays,
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
import type { LucideIcon } from "lucide-react";
import { useMutation } from "@tanstack/react-query";

import { PHVExplanationCard } from "@/components/ai/PHVExplanationCard";
import { ActivityCard } from "@/components/activities/ActivityCard";
import { ConnectionStatusBadge } from "@/components/activities/ConnectionStatusBadge";
import { AthleteAIAnalysisTab } from "@/components/athletes/ai/AthleteAIAnalysisTab";
import { AnthropometryForm } from "@/components/athletes/AnthropometryForm";
import { AnthropometryHistory } from "@/components/athletes/AnthropometryHistory";
import { AthleteInfoCard } from "@/components/athletes/AthleteInfoCard";
import { GrowthCharts } from "@/components/athletes/GrowthCharts";
import { LinkedParentsCard } from "@/components/athletes/LinkedParentsCard";
import { MorphologyCard } from "@/components/athletes/MorphologyCard";
import { NutritionalClassification } from "@/components/athletes/NutritionalClassification";
import { ResearchReferences } from "@/components/athletes/ResearchReferences";
import { TrainingReadiness } from "@/components/athletes/TrainingReadiness";
import { AthleteNewslettersTabPanel } from "@/components/training/AthleteNewslettersTabPanel";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/api/client";
import { cn } from "@/lib/utils";
import { formatDateMedium } from "@/lib/datetime";
import { useAthlete } from "@/hooks/athletes/useAthlete";
import { useAnthropometry } from "@/hooks/athletes/useAnthropometry";
import { useAthleteActivities } from "@/hooks/activities/useAthleteActivities";
import {
  useConnectStrava,
  useDisconnectStrava,
  useStravaConnection,
} from "@/hooks/activities/useStravaConnection";
import { useAuthStore } from "@/store/auth.store";
import { MaturationStatus, UserRole } from "@/types/enums";

type Tab = "info" | "anthropometry" | "growth" | "ai_analysis" | "newsletters" | "activities";

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

const cardShadow =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

function StatCard({
  icon: Icon,
  label,
  value,
  subtitle,
  colorClass,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  subtitle?: string;
  colorClass?: string;
}) {
  return (
    <div className="rounded-xl bg-white p-4" style={{ boxShadow: cardShadow }}>
      <div className="flex items-center gap-2 text-mid-gray">
        <Icon size={16} />
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <p className={cn("mt-1.5 text-2xl font-bold", colorClass ?? "text-charcoal")}>{value}</p>
      {subtitle && <p className="mt-0.5 text-xs text-mid-gray">{subtitle}</p>}
    </div>
  );
}

function phvColor(status: string | undefined | null): string {
  if (status === MaturationStatus.PrePHV) return "text-blue-700";
  if (status === MaturationStatus.CircaPHV) return "text-amber-700";
  if (status === MaturationStatus.PostPHV) return "text-green-700";
  return "text-charcoal";
}

function formatRelativeDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return "hoy";
  if (diffDays === 1) return "hace 1 día";
  if (diffDays < 30) return `hace ${diffDays} días`;
  const diffMonths = Math.floor(diffDays / 30);
  if (diffMonths === 1) return "hace 1 mes";
  return `hace ${diffMonths} meses`;
}

const ACTIVITIES_PAGE_SIZE = 10;

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
      <div className="rounded-xl bg-white p-5" style={{ boxShadow: cardShadow }}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3
            className="flex items-center gap-2 text-sm text-charcoal"
            style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600, letterSpacing: "0.2px" }}
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
      <div className="rounded-xl bg-white p-5" style={{ boxShadow: cardShadow }}>
        <h3
          className="mb-4 flex items-center gap-2 text-sm text-charcoal"
          style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600, letterSpacing: "0.2px" }}
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

export function AthleteDetailPage() {
  const { id } = useParams();
  const athleteId = Number(id);
  const athleteQuery = useAthlete(athleteId, Number.isFinite(athleteId));
  const anthropometryQuery = useAnthropometry(athleteId);
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
  // Si el tab vino por URL, ya consideramos el "tab inicial" decidido —
  // no queremos que el efecto de records lo sobrescriba a "growth".
  const [hasSetInitialTab, setHasSetInitialTab] = useState(tabFromUrl !== null);
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
      setHasSetInitialTab(true);
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
  // API devuelve registros ordenados desc (más reciente primero).
  const latestRecord = records[0];

  useEffect(() => {
    if (!hasSetInitialTab && records.length > 0) {
      setActiveTab("growth");
      setHasSetInitialTab(true);
    }
  }, [records.length, hasSetInitialTab]);

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
        <h1
          className="text-2xl text-charcoal"
          style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
        >
          Atleta no encontrado
        </h1>
        <p className="text-sm text-mid-gray">
          No existe un atleta con ese ID o no tienes permisos para verlo.
        </p>
        <Link to="/athletes" className="text-sm font-medium text-charcoal transition-opacity hover:opacity-70">
          Volver a la lista
        </Link>
      </section>
    );
  }

  if (!athleteQuery.data) return null;

  const athlete = athleteQuery.data;
  const latest = athlete.latest_anthropometry;

  const phvAgeMonths = latestRecord?.age_at_phv
    ? latestRecord.age_at_phv * 12
    : undefined;

  const tabClasses = (tab: Tab) =>
    cn(
      "flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
      activeTab === tab
        ? "bg-charcoal text-white"
        : "bg-white text-mid-gray hover:text-charcoal",
    );

  const tabStyle = (tab: Tab) =>
    activeTab !== tab
      ? { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }
      : undefined;

  return (
    <section className="space-y-4">
      {/* Hero Card */}
      <AthleteInfoCard athlete={athlete} />

      {/* Stat Cards Row */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          icon={Activity}
          label="Edad"
          value={athlete.age_decimal?.toFixed(1) ?? "—"}
          subtitle={athlete.category ?? undefined}
        />
        {latest ? (
          <>
            <StatCard
              icon={TrendingUp}
              label="Offset PHV"
              value={`${latest.maturity_offset >= 0 ? "+" : ""}${latest.maturity_offset.toFixed(1)}`}
              subtitle={latest.maturation_status}
              colorClass={phvColor(latest.maturation_status)}
            />
            <StatCard
              icon={Ruler}
              label="Talla"
              value={`${latest.standing_height_cm} cm`}
              subtitle={
                latest.height_percentile != null
                  ? `P${Math.round(latest.height_percentile)}`
                  : undefined
              }
            />
            <StatCard
              icon={CalendarDays}
              label="Ult. medición"
              value={latest.evaluation_date}
              subtitle={formatRelativeDate(latest.evaluation_date)}
            />
          </>
        ) : (
          <div
            className="col-span-1 flex items-center justify-center rounded-xl bg-white p-4 text-sm text-mid-gray lg:col-span-3"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px", borderStyle: "dashed" }}
          >
            Sin mediciones antropométricas registradas
          </div>
        )}
      </div>

      {/* Parents */}
      <LinkedParentsCard athleteId={athlete.id} />

      {/* Tabs */}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={tabClasses("info")}
          style={tabStyle("info")}
          onClick={() => updateTab("info")}
        >
          <User size={14} />
          Info general
        </button>
        <button
          type="button"
          className={tabClasses("anthropometry")}
          style={tabStyle("anthropometry")}
          onClick={() => updateTab("anthropometry")}
        >
          <Ruler size={14} />
          Antropometría
        </button>
        {records.length > 0 && (
          <button
            type="button"
            className={tabClasses("growth")}
            style={tabStyle("growth")}
            onClick={() => updateTab("growth")}
          >
            <TrendingUp size={14} />
            Crecimiento
          </button>
        )}
        <button
          type="button"
          className={tabClasses("ai_analysis")}
          style={tabStyle("ai_analysis")}
          onClick={() => updateTab("ai_analysis")}
          data-testid="athlete-tab-ai-analysis"
        >
          <Sparkles size={14} />
          Análisis IA
        </button>

        {!isParent && (
          <button
            type="button"
            className={tabClasses("newsletters")}
            style={tabStyle("newsletters")}
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
          style={tabStyle("activities")}
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
              "flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-opacity",
              reportSent
                ? "bg-green-600 text-white"
                : "bg-charcoal text-white hover:opacity-70",
              (sendReportMutation.isPending || reportSent) && "cursor-not-allowed opacity-70",
            )}
            style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
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
          <div className="rounded-xl bg-white p-5" style={{ boxShadow: cardShadow }}>
            <h3
              className="mb-4 flex items-center gap-2 text-sm text-charcoal"
              style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600, letterSpacing: "0.2px" }}
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
                  : "bg-white",
              )}
              style={latest.maturation_status !== "Circa-PHV" ? { boxShadow: cardShadow } : undefined}
            >
              <div className="mb-3 flex items-center gap-2">
                {latest.maturation_status === "Circa-PHV" && (
                  <AlertTriangle size={16} className="text-amber-500" />
                )}
                <span
                  className="text-sm text-charcoal"
                  style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600, letterSpacing: "0.2px" }}
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
              className="text-lg text-charcoal"
              style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
            >
              Registro de mediciones
            </h3>
            <button
              type="button"
              onClick={() => setShowForm(!showForm)}
              className="rounded-lg bg-charcoal px-3 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70"
              style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
            >
              {showForm ? "Cancelar" : "+ Nueva medición"}
            </button>
          </div>

          {showForm && (
            <div className="rounded-xl bg-white p-5" style={{ boxShadow: cardShadow }}>
              <AnthropometryForm
                athleteId={athlete.id}
                athleteSex={athlete.sex}
                athleteBirthDate={athlete.birth_date}
                onSuccess={() => setShowForm(false)}
              />
            </div>
          )}

          <div className="rounded-xl bg-white p-5" style={{ boxShadow: cardShadow }}>
            <AnthropometryHistory
              records={records}
              isLoading={anthropometryQuery.isLoading}
              athleteId={athleteId}
              mode="coach"
            />
          </div>
        </div>
      )}

      {/* Tab content — Análisis IA */}
      {activeTab === "ai_analysis" && (
        <AthleteAIAnalysisTab
          athlete={athlete}
          mode={isParent ? "parent" : "coach"}
        />
      )}

      {/* Tab content — Boletines (solo coach/admin) */}
      {activeTab === "newsletters" && !isParent && (
        <AthleteNewslettersTabPanel athleteId={athleteId} />
      )}

      {/* Tab content — Actividades (Strava) */}
      {activeTab === "activities" && <StravaTabPanel athleteId={athleteId} />}

      {/* Tab content — Crecimiento */}
      {activeTab === "growth" && records.length > 0 && (
        <div className="space-y-5">
          <NutritionalClassification
            record={latestRecord}
            sex={athlete.sex}
            birthDate={athlete.birth_date}
          />
          <div className="rounded-xl bg-white p-5" style={{ boxShadow: cardShadow }}>
            <GrowthCharts
              records={records}
              sex={athlete.sex}
              birthDate={athlete.birth_date}
              phvAgeMonths={phvAgeMonths}
              ageDecimal={athlete.age_decimal ?? undefined}
            />
          </div>
          <TrainingReadiness
            athlete={athlete}
            latestRecord={latestRecord}
          />
          <MorphologyCard latestRecord={latestRecord} />
          <PHVExplanationCard
            athleteId={athlete.id}
            hasRecords={records.length > 0}
            onMeasurementCTA={() => updateTab("anthropometry")}
          />
          <ResearchReferences />
        </div>
      )}
    </section>
  );
}
