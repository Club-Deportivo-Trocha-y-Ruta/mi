import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { AssessmentWizard } from "@/components/anxiety/AssessmentWizard";
import { GroupPanel } from "@/components/anxiety/GroupPanel";
import { ImportDialog } from "@/components/anxiety/ImportDialog";
import { IndividualPanel } from "@/components/anxiety/IndividualPanel";
import {
  useAthleteSeries,
  useGroupByEvent,
} from "@/hooks/anxiety/useAnxietyDashboards";
import { useAthletes } from "@/hooks/athletes/useAthletes";
import type { AnxietyInstrumentType } from "@/types/anxiety.types";

type Tab = "crear" | "individual" | "grupo" | "importar";

const TABS: { id: Tab; label: string }[] = [
  { id: "crear", label: "Crear" },
  { id: "individual", label: "Individual" },
  { id: "grupo", label: "Grupo" },
  { id: "importar", label: "Importar" },
];

/** Dashboard del módulo de ansiedad competitiva (coach/admin). */
export function AnxietyDashboardPage() {
  const [searchParams] = useSearchParams();
  const athleteFromUrl = Number(searchParams.get("athlete")) || 0;
  const [tab, setTab] = useState<Tab>(athleteFromUrl > 0 ? "individual" : "crear");

  return (
    <div className="mx-auto max-w-3xl px-4 py-6">
      <h1 className="mb-1 text-2xl font-semibold text-slate-900">
        Ansiedad competitiva
      </h1>
      <p className="mb-5 text-sm text-slate-500">
        Evalúa, puntúa e interpreta el estado de ansiedad previo a la
        competencia, anclado a la línea base de cada deportista.
      </p>

      <div
        role="tablist"
        aria-label="Secciones del módulo de ansiedad"
        className="mb-5 flex flex-wrap gap-2"
      >
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={[
              "min-h-10 rounded-lg px-4 py-2 text-sm",
              tab === t.id
                ? "bg-slate-900 text-white"
                : "border border-slate-300 text-slate-700",
            ].join(" ")}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "crear" && <AssessmentWizard />}
      {tab === "individual" && <IndividualTab initialAthleteId={athleteFromUrl} />}
      {tab === "grupo" && <GroupTab />}
      {tab === "importar" && <ImportDialog />}
    </div>
  );
}

function IndividualTab({ initialAthleteId = 0 }: { initialAthleteId?: number }) {
  const [athleteId, setAthleteId] = useState(
    initialAthleteId > 0 ? String(initialAthleteId) : "",
  );
  const [instrument, setInstrument] = useState<AnxietyInstrumentType>("csai2r");
  const [submittedId, setSubmittedId] = useState(initialAthleteId);
  const series = useAthleteSeries(submittedId, instrument, submittedId > 0);
  const athletesQuery = useAthletes();
  const athletes = athletesQuery.data?.items ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="mb-1 block font-medium text-slate-700">
            Deportista
          </span>
          <select
            value={athleteId}
            onChange={(e) => setAthleteId(e.target.value)}
            disabled={athletesQuery.isLoading}
            className="min-h-10 w-56 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">
              {athletesQuery.isLoading
                ? "Cargando deportistas…"
                : "Selecciona un deportista"}
            </option>
            {athletes.map((a) => (
              <option key={a.id} value={a.id}>
                {a.first_name} {a.last_name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="mb-1 block font-medium text-slate-700">Instrumento</span>
          <select
            value={instrument}
            onChange={(e) =>
              setInstrument(e.target.value as AnxietyInstrumentType)
            }
            className="min-h-10 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="csai2r">CSAI-2R</option>
            <option value="sas2">SAS-2</option>
            <option value="csai2">CSAI-2</option>
          </select>
        </label>
        <button
          type="button"
          onClick={() => setSubmittedId(Number(athleteId) || 0)}
          className="min-h-10 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white"
        >
          Ver
        </button>
      </div>

      {series.isLoading && (
        <p className="text-sm text-slate-500">Cargando…</p>
      )}
      {series.data && <IndividualPanel series={series.data} />}
    </div>
  );
}

function GroupTab() {
  const [eventId, setEventId] = useState("");
  const [submittedId, setSubmittedId] = useState(0);
  const triage = useGroupByEvent(submittedId, submittedId > 0);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="mb-1 block font-medium text-slate-700">
            Evento (ID)
          </span>
          <input
            type="number"
            value={eventId}
            onChange={(e) => setEventId(e.target.value)}
            className="min-h-10 w-40 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
        </label>
        <button
          type="button"
          onClick={() => setSubmittedId(Number(eventId) || 0)}
          className="min-h-10 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white"
        >
          Ver
        </button>
      </div>

      {triage.isLoading && <p className="text-sm text-slate-500">Cargando…</p>}
      {triage.data && <GroupPanel triage={triage.data} />}
    </div>
  );
}

export default AnxietyDashboardPage;
