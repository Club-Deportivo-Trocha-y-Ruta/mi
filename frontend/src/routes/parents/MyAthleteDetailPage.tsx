import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  Bike,
  CalendarDays,
  Info,
  Ruler,
  Sparkles,
  TrendingUp,
  User,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { PHVExplanationCard } from "@/components/ai/PHVExplanationCard";
import { ActivityCard } from "@/components/activities/ActivityCard";
import { AnthropometryHistory } from "@/components/athletes/AnthropometryHistory";
import { AthleteAIAnalysisTab } from "@/components/athletes/ai/AthleteAIAnalysisTab";
import { AthleteInfoCard } from "@/components/athletes/AthleteInfoCard";
import { GrowthCharts } from "@/components/athletes/GrowthCharts";
import { NutritionalClassification } from "@/components/athletes/NutritionalClassification";
import { ResearchReferences } from "@/components/athletes/ResearchReferences";
import { cn } from "@/lib/utils";
import { useAthlete } from "@/hooks/athletes/useAthlete";
import { useAnthropometry } from "@/hooks/athletes/useAnthropometry";
import { useAthleteActivities } from "@/hooks/activities/useAthleteActivities";
import { MaturationStatus, Sex } from "@/types/enums";

type Tab = "info" | "growth" | "activities" | "ai-analysis";

const ACTIVITIES_PAGE_SIZE = 10;

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

function phvParentMessage(status: string | undefined | null, sex: Sex): string {
  const pronoun = sex === Sex.F ? "hija" : "hijo";
  if (status === MaturationStatus.PrePHV)
    return `Tu ${pronoun} está en etapa de desarrollo temprano`;
  if (status === MaturationStatus.CircaPHV)
    return `Tu ${pronoun} está en su pico de crecimiento — etapa clave`;
  if (status === MaturationStatus.PostPHV)
    return `El crecimiento de tu ${pronoun} se está estabilizando`;
  return "";
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

export function MyAthleteDetailPage() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const athleteId = Number(id);
  const athleteQuery = useAthlete(athleteId, Number.isFinite(athleteId));
  const anthropometryQuery = useAnthropometry(athleteId);
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
        <div className="rounded-xl bg-white p-5" style={{ boxShadow: cardShadow }}>
          <p className="text-sm text-mid-gray">
            No se pudo cargar la información del atleta.
          </p>
        </div>
      </section>
    );
  }

  if (!athleteQuery.data) return null;

  const athlete = athleteQuery.data;
  const latest = athlete.latest_anthropometry;

  const phvAgeMonths =
    records.length > 0
      ? (() => {
          const lastRecord = records[records.length - 1];
          if (!lastRecord.age_at_phv) return undefined;
          return lastRecord.age_at_phv * 12;
        })()
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

      {/* Stat Cards Row — 3 cards: Edad, Talla, Ultima medicion */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatCard
          icon={Activity}
          label="Edad"
          value={athlete.age_decimal?.toFixed(1) ?? "—"}
          subtitle={athlete.category ?? undefined}
        />
        {latest ? (
          <>
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
            className="col-span-1 flex items-center justify-center rounded-xl bg-white p-4 text-sm text-mid-gray sm:col-span-2"
            style={{
              boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px",
              borderStyle: "dashed",
            }}
          >
            Sin mediciones registradas
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={tabClasses("info")}
          style={tabStyle("info")}
          onClick={() => setActiveTab("info")}
        >
          <User size={14} />
          Datos
        </button>
        {records.length > 0 && (
          <button
            type="button"
            className={tabClasses("growth")}
            style={tabStyle("growth")}
            onClick={() => setActiveTab("growth")}
          >
            <TrendingUp size={14} />
            Crecimiento
          </button>
        )}
        <button
          type="button"
          className={tabClasses("activities")}
          style={tabStyle("activities")}
          onClick={() => setActiveTab("activities")}
          data-testid="parent-tab-activities"
        >
          <Bike size={14} />
          Actividades
        </button>
        <button
          type="button"
          className={tabClasses("ai-analysis")}
          style={tabStyle("ai-analysis")}
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
          <div className="rounded-xl bg-white p-5" style={{ boxShadow: cardShadow }}>
            <h3
              className="mb-4 flex items-center gap-2 text-sm text-charcoal"
              style={{
                fontFamily: "'Cal Sans', system-ui, sans-serif",
                fontWeight: 600,
                letterSpacing: "0.2px",
              }}
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

          {/* Estado PHV con lenguaje para padres */}
          {latest && latest.maturation_status && (
            <div
              className={cn(
                "rounded-xl p-5",
                latest.maturation_status === MaturationStatus.CircaPHV
                  ? "border border-amber-200 bg-amber-50"
                  : "bg-white",
              )}
              style={
                latest.maturation_status !== MaturationStatus.CircaPHV
                  ? { boxShadow: cardShadow }
                  : undefined
              }
            >
              <div className="mb-3 flex items-center gap-2">
                {latest.maturation_status === MaturationStatus.CircaPHV && (
                  <AlertTriangle size={16} className="text-amber-500" />
                )}
                <span
                  className="text-sm text-charcoal"
                  style={{
                    fontFamily: "'Cal Sans', system-ui, sans-serif",
                    fontWeight: 600,
                    letterSpacing: "0.2px",
                  }}
                >
                  Etapa de desarrollo
                </span>
                <span className="ml-auto text-xs text-mid-gray">
                  Evaluado: {latest.evaluation_date}
                </span>
              </div>
              <p
                className={cn(
                  "text-sm font-medium",
                  phvColor(latest.maturation_status),
                )}
              >
                {phvParentMessage(latest.maturation_status, athlete.sex)}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Tab content — Análisis IA (parent) */}
      {activeTab === "ai-analysis" && (
        <AthleteAIAnalysisTab athlete={athlete} mode="parent" />
      )}

      {/* Tab content — Crecimiento */}
      {activeTab === "growth" && records.length > 0 && (
        <div className="space-y-5">
          <NutritionalClassification
            record={records[records.length - 1]}
            sex={athlete.sex}
            birthDate={athlete.birth_date}
          />
          <div className="rounded-xl bg-white p-5" style={{ boxShadow: cardShadow }}>
            <AnthropometryHistory
              records={records}
              isLoading={anthropometryQuery.isLoading}
              athleteId={athleteId}
              mode="parent"
            />
          </div>
          <div className="rounded-xl bg-white p-5" style={{ boxShadow: cardShadow }}>
            <GrowthCharts
              records={records}
              sex={athlete.sex}
              birthDate={athlete.birth_date}
              phvAgeMonths={phvAgeMonths}
              ageDecimal={athlete.age_decimal ?? undefined}
            />
          </div>
          <PHVExplanationCard
            athleteId={athleteId}
            hasRecords={records.length > 0}
            readOnly
          />
          <ResearchReferences />
        </div>
      )}

      {/* Tab content — Actividades (feature 025, T036). Solo lectura: sin
          controles de conexión ni de enlace a sesión (esos son exclusivos
          del coach/admin, ver FR-007). RBAC de "solo mi hijo" lo aplica el
          backend — acá solo se consume la respuesta ya filtrada. */}
      {activeTab === "activities" && (
        <div className="rounded-xl bg-white p-5" style={{ boxShadow: cardShadow }}>
          <h3
            className="mb-4 flex items-center gap-2 text-sm text-charcoal"
            style={{
              fontFamily: "'Cal Sans', system-ui, sans-serif",
              fontWeight: 600,
              letterSpacing: "0.2px",
            }}
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
