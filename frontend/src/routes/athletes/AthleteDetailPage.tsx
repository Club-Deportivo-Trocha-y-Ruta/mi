import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  CalendarDays,
  Info,
  Loader2,
  Mail,
  Ruler,
  Sparkles,
  TrendingUp,
  User,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useMutation } from "@tanstack/react-query";

import { PHVExplanationCard } from "@/components/ai/PHVExplanationCard";
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
import { apiClient } from "@/api/client";
import { cn } from "@/lib/utils";
import { useAthlete } from "@/hooks/athletes/useAthlete";
import { useAnthropometry } from "@/hooks/athletes/useAnthropometry";
import { useAuthStore } from "@/store/auth.store";
import { MaturationStatus, UserRole } from "@/types/enums";

type Tab = "info" | "anthropometry" | "growth" | "ai_analysis";

const VALID_TABS: readonly Tab[] = [
  "info",
  "anthropometry",
  "growth",
  "ai_analysis",
] as const;

function parseTabParam(raw: string | null): Tab | null {
  if (raw && (VALID_TABS as readonly string[]).includes(raw)) {
    return raw as Tab;
  }
  return null;
}

/* shadow-card utility */
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
    <div className="rounded-xl bg-white p-4 shadow-card">
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
  const [searchParams, setSearchParams] = useSearchParams();
  const tabFromUrl = parseTabParam(searchParams.get("tab"));
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
  useEffect(() => {
    const urlTab = parseTabParam(searchParams.get("tab"));
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
          className="text-2xl text-charcoal font-heading"
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
            className="col-span-1 flex items-center justify-center rounded-xl bg-white p-4 text-sm text-mid-gray lg:col-span-3 shadow-ring border border-dashed border-transparent"
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
              className="mb-4 flex items-center gap-2 text-sm text-charcoal font-heading tracking-[0.2px]"
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
                  className="text-sm text-charcoal font-heading tracking-[0.2px]"
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
              className="text-lg text-charcoal font-heading"
            >
              Registro de mediciones
            </h3>
            <button
              type="button"
              onClick={() => setShowForm(!showForm)}
              className="rounded-lg bg-charcoal px-3 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70"
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

      {/* Tab content — Análisis IA */}
      {activeTab === "ai_analysis" && (
        <AthleteAIAnalysisTab
          athlete={athlete}
          mode={isParent ? "parent" : "coach"}
        />
      )}

      {/* Tab content — Crecimiento */}
      {activeTab === "growth" && records.length > 0 && (
        <div className="space-y-5">
          <NutritionalClassification
            record={latestRecord}
            sex={athlete.sex}
            birthDate={athlete.birth_date}
          />
          <div className="rounded-xl bg-white p-5 shadow-card">
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
