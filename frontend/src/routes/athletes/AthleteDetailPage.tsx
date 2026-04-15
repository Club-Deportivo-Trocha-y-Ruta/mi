import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { AnthropometryForm } from "@/components/athletes/AnthropometryForm";
import { AnthropometryHistory } from "@/components/athletes/AnthropometryHistory";
import { AthleteInfoCard } from "@/components/athletes/AthleteInfoCard";
import { GrowthCharts } from "@/components/athletes/GrowthCharts";
import { NutritionalClassification } from "@/components/athletes/NutritionalClassification";
import { PercentileCurves } from "@/components/athletes/PercentileCurves";
import { ResearchReferences } from "@/components/athletes/ResearchReferences";
import { TrainingReadiness } from "@/components/athletes/TrainingReadiness";
import { useAthlete } from "@/hooks/athletes/useAthlete";
import { useAnthropometry } from "@/hooks/athletes/useAnthropometry";

type Tab = "info" | "anthropometry" | "growth";

export function AthleteDetailPage() {
  const { id } = useParams();
  const athleteId = Number(id);
  const athleteQuery = useAthlete(athleteId, Number.isFinite(athleteId));
  const anthropometryQuery = useAnthropometry(athleteId);

  const [activeTab, setActiveTab] = useState<Tab>("info");
  const [showForm, setShowForm] = useState(false);

  if (athleteQuery.isLoading) {
    return (
      <section className="space-y-3">
        <div className="h-6 w-48 animate-pulse rounded bg-slate-200" />
        <div className="h-40 animate-pulse rounded-lg bg-slate-100" />
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
  const records = anthropometryQuery.data ?? [];

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
    `px-4 py-2 text-sm font-medium border-b-2 ${
      activeTab === tab
        ? "border-slate-900 text-slate-900"
        : "border-transparent text-slate-500 hover:text-slate-700"
    }`;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link to="/athletes" className="text-sm text-slate-600 hover:text-slate-900">
          ← Volver a lista
        </Link>
        <Link
          to={`/athletes/${athlete.id}/edit`}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm hover:bg-slate-100"
        >
          Editar atleta
        </Link>
      </div>

      <AthleteInfoCard athlete={athlete} />

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-200">
        <button type="button" className={tabClasses("info")} onClick={() => setActiveTab("info")}>
          Info general
        </button>
        <button
          type="button"
          className={tabClasses("anthropometry")}
          onClick={() => setActiveTab("anthropometry")}
        >
          Antropometria
        </button>
        {records.length > 0 && (
          <button
            type="button"
            className={tabClasses("growth")}
            onClick={() => setActiveTab("growth")}
          >
            Crecimiento y Decision
          </button>
        )}
      </div>

      {/* Tab content — Info general */}
      {activeTab === "info" && (
        <div className="space-y-4">
          <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700">
            <div className="grid gap-3 md:grid-cols-2">
              <p>Nombre: {athlete.first_name} {athlete.last_name}</p>
              <p>Sexo: {athlete.sex}</p>
              <p>Edad: {athlete.age_decimal?.toFixed(1) ?? "-"} anos</p>
              <p>Categoria: {athlete.category ?? "Sin categoria"}</p>
              <p>En club: {athlete.years_in_club != null ? `${athlete.years_in_club.toFixed(1)} años` : "—"}</p>
              <p>Ingreso al club: {athlete.club_join_date ?? "—"}</p>
              {/* birth_date no se expone — solo se muestra la edad calculada */}
            </div>
          </div>

          {athlete.latest_anthropometry && (
            <div
              className={`rounded-lg border p-4 text-sm ${
                athlete.latest_anthropometry.maturation_status === "Circa-PHV"
                  ? "border-amber-300 bg-amber-50"
                  : "border-slate-200 bg-white"
              }`}
            >
              <div className="mb-2 flex items-center gap-2">
                {athlete.latest_anthropometry.maturation_status === "Circa-PHV" && (
                  <span className="text-amber-600">⚠</span>
                )}
                <span className="font-medium text-slate-700">
                  Ultima evaluacion PHV: {athlete.latest_anthropometry.evaluation_date}
                </span>
              </div>
              <p className="text-slate-600">
                {athlete.latest_anthropometry.training_implications}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Tab content — Antropometria */}
      {activeTab === "anthropometry" && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold">Mediciones antropometricas</h3>
            <button
              type="button"
              onClick={() => setShowForm(!showForm)}
              className="rounded-md bg-slate-900 px-3 py-2 text-sm text-white hover:bg-slate-800"
            >
              {showForm ? "Cancelar" : "+ Nueva medicion"}
            </button>
          </div>

          {showForm && (
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <AnthropometryForm
                athleteId={athlete.id}
                athleteSex={athlete.sex}
                athleteBirthDate={athlete.birth_date}
                onSuccess={() => setShowForm(false)}
              />
            </div>
          )}

          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <GrowthCharts
              records={records}
              sex={athlete.sex}
              birthDate={athlete.birth_date}
              phvAgeMonths={phvAgeMonths}
            />
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <AnthropometryHistory
              records={records}
              isLoading={anthropometryQuery.isLoading}
            />
          </div>
        </div>
      )}

      {/* Tab content — Crecimiento y Decision */}
      {activeTab === "growth" && records.length > 0 && (
        <div className="space-y-6">
          <NutritionalClassification
            record={records[records.length - 1]}
            sex={athlete.sex}
            birthDate={athlete.birth_date}
          />
          <div className="rounded-lg border border-slate-200 bg-white p-4">
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
