import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  CalendarDays,
  Info,
  Ruler,
  TrendingUp,
  User,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { AnthropometryForm } from "@/components/athletes/AnthropometryForm";
import { AnthropometryHistory } from "@/components/athletes/AnthropometryHistory";
import { AthleteInfoCard } from "@/components/athletes/AthleteInfoCard";
import { GrowthCharts } from "@/components/athletes/GrowthCharts";
import { NutritionalClassification } from "@/components/athletes/NutritionalClassification";
import { PercentileCurves } from "@/components/athletes/PercentileCurves";
import { ResearchReferences } from "@/components/athletes/ResearchReferences";
import { TrainingReadiness } from "@/components/athletes/TrainingReadiness";
import { cn } from "@/lib/utils";
import { useAthlete } from "@/hooks/athletes/useAthlete";
import { useAnthropometry } from "@/hooks/athletes/useAnthropometry";
import { MaturationStatus } from "@/types/enums";

type Tab = "info" | "anthropometry" | "growth";

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
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2 text-slate-500">
        <Icon size={16} />
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <p className={cn("mt-1 text-2xl font-bold", colorClass ?? "text-slate-900")}>{value}</p>
      {subtitle && <p className="mt-0.5 text-xs text-slate-400">{subtitle}</p>}
    </div>
  );
}

function phvColor(status: string | undefined | null): string {
  if (status === MaturationStatus.PrePHV) return "text-blue-700";
  if (status === MaturationStatus.CircaPHV) return "text-amber-700";
  if (status === MaturationStatus.PostPHV) return "text-green-700";
  return "text-slate-900";
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

  const [activeTab, setActiveTab] = useState<Tab>("info");
  const [showForm, setShowForm] = useState(false);
  const [hasSetInitialTab, setHasSetInitialTab] = useState(false);

  const records = anthropometryQuery.data ?? [];

  // Cambiar a tab "growth" cuando se cargan records por primera vez
  useEffect(() => {
    if (!hasSetInitialTab && records.length > 0) {
      setActiveTab("growth");
      setHasSetInitialTab(true);
    }
  }, [records.length, hasSetInitialTab]);

  if (athleteQuery.isLoading) {
    return (
      <section className="space-y-4">
        <div className="h-36 animate-pulse rounded-xl bg-slate-100" />
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-slate-100" />
          ))}
        </div>
        <div className="flex gap-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-10 w-32 animate-pulse rounded-lg bg-slate-100" />
          ))}
        </div>
      </section>
    );
  }

  if (athleteQuery.isError) {
    return (
      <section className="space-y-3">
        <h1 className="text-2xl font-bold">Atleta no encontrado</h1>
        <p className="text-sm text-slate-600">
          No existe un atleta con ese ID o no tienes permisos para verlo.
        </p>
        <Link to="/athletes" className="text-sm font-medium text-slate-900 hover:underline">
          Volver a la lista
        </Link>
      </section>
    );
  }

  if (!athleteQuery.data) return null;

  const athlete = athleteQuery.data;
  const latest = athlete.latest_anthropometry;

  // Edad en meses cuando ocurrio/ocurrira el PHV
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
        ? "bg-slate-900 text-white shadow-sm"
        : "text-slate-600 hover:bg-slate-100",
    );

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
              label="Últ. medición"
              value={latest.evaluation_date}
              subtitle={formatRelativeDate(latest.evaluation_date)}
            />
          </>
        ) : (
          <div className="col-span-1 flex items-center justify-center rounded-xl border border-dashed border-slate-300 p-4 text-sm text-slate-400 lg:col-span-3">
            Sin mediciones antropométricas registradas
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-2">
        <button type="button" className={tabClasses("info")} onClick={() => setActiveTab("info")}>
          <User size={14} />
          Info general
        </button>
        <button
          type="button"
          className={tabClasses("anthropometry")}
          onClick={() => setActiveTab("anthropometry")}
        >
          <Ruler size={14} />
          Antropometría
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
      </div>

      {/* Tab content — Info general */}
      {activeTab === "info" && (
        <div className="space-y-4">
          <div className="rounded-xl border border-slate-200 bg-white p-5">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-700">
              <Info size={16} />
              Datos del atleta
            </h3>
            <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-slate-400">Sexo</dt>
                <dd className="font-medium text-slate-700">
                  {athlete.sex === "M" ? "Masculino" : "Femenino"}
                </dd>
              </div>
              <div>
                <dt className="text-slate-400">Categoría</dt>
                <dd className="font-medium text-slate-700">
                  {athlete.category ?? "Sin categoría"}
                </dd>
              </div>
              <div>
                <dt className="text-slate-400">Ingreso al club</dt>
                <dd className="font-medium text-slate-700">
                  {athlete.club_join_date ?? "—"}
                </dd>
              </div>
              <div>
                <dt className="text-slate-400">Tiempo en club</dt>
                <dd className="font-medium text-slate-700">
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
                "rounded-xl border p-5",
                latest.maturation_status === "Circa-PHV"
                  ? "border-amber-200 bg-amber-50"
                  : "border-slate-200 bg-white",
              )}
            >
              <div className="mb-2 flex items-center gap-2">
                {latest.maturation_status === "Circa-PHV" && (
                  <AlertTriangle size={16} className="text-amber-500" />
                )}
                <span className="text-sm font-semibold text-slate-700">
                  Implicaciones PHV
                </span>
                <span className="ml-auto text-xs text-slate-400">
                  Evaluado: {latest.evaluation_date}
                </span>
              </div>
              <p className="text-sm text-slate-600">{latest.training_implications}</p>
            </div>
          )}
        </div>
      )}

      {/* Tab content — Antropometria */}
      {activeTab === "anthropometry" && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold">Mediciones antropométricas</h3>
            <button
              type="button"
              onClick={() => setShowForm(!showForm)}
              className="rounded-lg bg-slate-900 px-3 py-2 text-sm text-white shadow-sm hover:bg-slate-800"
            >
              {showForm ? "Cancelar" : "+ Nueva medición"}
            </button>
          </div>

          {showForm && (
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <AnthropometryForm
                athleteId={athlete.id}
                athleteSex={athlete.sex}
                athleteBirthDate={athlete.birth_date}
                onSuccess={() => setShowForm(false)}
              />
            </div>
          )}

          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <GrowthCharts
              records={records}
              sex={athlete.sex}
              birthDate={athlete.birth_date}
              phvAgeMonths={phvAgeMonths}
            />
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <AnthropometryHistory
              records={records}
              isLoading={anthropometryQuery.isLoading}
            />
          </div>
        </div>
      )}

      {/* Tab content — Crecimiento */}
      {activeTab === "growth" && records.length > 0 && (
        <div className="space-y-6">
          <NutritionalClassification
            record={records[records.length - 1]}
            sex={athlete.sex}
            birthDate={athlete.birth_date}
          />
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <h4 className="mb-3 text-sm font-semibold text-slate-700">
              Curvas de crecimiento — Talla/Edad
            </h4>
            <PercentileCurves
              sex={athlete.sex}
              birthDate={athlete.birth_date}
              records={records}
              indicator="height_for_age"
              phvAgeMonths={phvAgeMonths}
            />
          </div>
          <TrainingReadiness
            athlete={athlete}
            latestRecord={records[records.length - 1]}
          />
          <ResearchReferences />
        </div>
      )}
    </section>
  );
}
