import { useState } from "react";

import { mapAnxietyError } from "@/api/anxiety";
import { useCreateAssessment } from "@/hooks/anxiety/useAnxietyAssessments";
import { useAthletes } from "@/hooks/athletes/useAthletes";
import type {
  AnxietyInstrumentType,
  AssessmentCreated,
} from "@/types/anxiety.types";

/**
 * Configuración de una evaluación (US1). El instrumento se elige por edad en
 * el backend; aquí sólo se ofrece un override opcional, que surface la
 * advertencia de menores de 13 (422) y exige confirmación explícita.
 */
export function AssessmentWizard() {
  const [athleteId, setAthleteId] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [eventId, setEventId] = useState("");
  const [instrument, setInstrument] = useState<AnxietyInstrumentType | "">("");
  const [override, setOverride] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<AssessmentCreated | null>(null);

  const mutation = useCreateAssessment();
  const athletesQuery = useAthletes();
  const athletes = athletesQuery.data?.items ?? [];

  function submit() {
    setError(null);
    setCreated(null);
    const id = Number(athleteId);
    if (!id || !scheduledAt) {
      setError("Indica el deportista y la fecha/hora.");
      return;
    }
    mutation.mutate(
      {
        athlete_id: id,
        scheduled_at: new Date(scheduledAt).toISOString(),
        event_id: eventId ? Number(eventId) : null,
        instrument_type: instrument || null,
        override,
      },
      {
        onSuccess: (data) => setCreated(data),
        onError: (err) => setError(mapAnxietyError(err).message),
      },
    );
  }

  return (
    <section
      className="rounded-xl border border-border-gray bg-white p-5"
      aria-label="Crear evaluación"
    >
      <h3 className="mb-4 text-base font-semibold text-charcoal">
        Nueva evaluación
      </h3>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="text-sm">
          <span className="mb-1 block font-medium text-charcoal">
            Deportista
          </span>
          <select
            value={athleteId}
            onChange={(e) => setAthleteId(e.target.value)}
            disabled={athletesQuery.isLoading}
            className="min-h-10 w-full rounded-lg border border-border-gray px-3 py-2 text-sm"
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
          <span className="mb-1 block font-medium text-charcoal">
            Fecha y hora
          </span>
          <input
            type="datetime-local"
            value={scheduledAt}
            onChange={(e) => setScheduledAt(e.target.value)}
            className="min-h-10 w-full rounded-lg border border-border-gray px-3 py-2 text-sm"
          />
        </label>

        <label className="text-sm">
          <span className="mb-1 block font-medium text-charcoal">
            Evento (ID, opcional)
          </span>
          <input
            type="number"
            inputMode="numeric"
            value={eventId}
            onChange={(e) => setEventId(e.target.value)}
            className="min-h-10 w-full rounded-lg border border-border-gray px-3 py-2 text-sm"
          />
        </label>

        <label className="text-sm">
          <span className="mb-1 block font-medium text-charcoal">
            Instrumento (opcional, por defecto según edad)
          </span>
          <select
            value={instrument}
            onChange={(e) =>
              setInstrument(e.target.value as AnxietyInstrumentType | "")
            }
            className="min-h-10 w-full rounded-lg border border-border-gray px-3 py-2 text-sm"
          >
            <option value="">Automático por edad</option>
            <option value="sas2">SAS-2 (10–12)</option>
            <option value="csai2r">CSAI-2R (13–15)</option>
          </select>
        </label>
      </div>

      {instrument === "csai2r" && (
        <label className="mt-3 flex items-start gap-2 text-xs text-mid-gray">
          <input
            type="checkbox"
            checked={override}
            onChange={(e) => setOverride(e.target.checked)}
            className="mt-0.5"
          />
          <span>
            Confirmo el uso de un instrumento por debajo de su rango validado
            para menores de 13 (solo con razón metodológica).
          </span>
        </label>
      )}

      <button
        type="button"
        onClick={submit}
        disabled={mutation.isPending}
        className="mt-4 min-h-10 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {mutation.isPending ? "Creando…" : "Crear y generar enlace"}
      </button>

      {error && (
        <p role="alert" className="mt-3 text-sm text-red-600">
          {error}
        </p>
      )}

      {created && (
        <div className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900">
          <p>
            Evaluación creada ({created.instrument_type.toUpperCase()}).
            {created.warning ? ` ${created.warning}` : ""}
          </p>
          {created.token && (
            <p className="mt-2 break-all">
              Enlace de respuesta:{" "}
              <code className="rounded bg-white px-1">
                /anxiety/responder/{created.token.token}
              </code>
            </p>
          )}
        </div>
      )}
    </section>
  );
}

export default AssessmentWizard;
