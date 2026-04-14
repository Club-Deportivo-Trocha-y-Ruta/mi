import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { AnthropometryForm } from "@/components/athletes/AnthropometryForm";
import { AnthropometryHistory } from "@/components/athletes/AnthropometryHistory";
import { AthleteInfoCard } from "@/components/athletes/AthleteInfoCard";
import { GrowthCharts } from "@/components/athletes/GrowthCharts";
import { useAthlete } from "@/hooks/athletes/useAthlete";
import { useAnthropometry } from "@/hooks/athletes/useAnthropometry";

type Tab = "info" | "anthropometry";

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
      </div>

      {/* Tab content */}
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
              <p>Fecha nacimiento: {athlete.birth_date}</p>
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
            <GrowthCharts records={records} />
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <AnthropometryHistory
              records={records}
              isLoading={anthropometryQuery.isLoading}
            />
          </div>
        </div>
      )}
    </section>
  );
}
