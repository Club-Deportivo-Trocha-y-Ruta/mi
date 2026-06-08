import { useMemo } from "react";
import { Link, useParams, useLocation } from "react-router-dom";

import { SessionWizard } from "@/components/training/session-wizard/SessionWizard";
import {
  useSessionAttendance,
  useTrainingSession,
} from "@/api/trainingSessions";
import type { TrainingSessionFormValues } from "@/schemas/trainingSession.schema";
import type { AssistantDraftState } from "@/routes/training/SessionAssistantPage";

interface SessionFormPageProps {
  mode: "create" | "edit";
}

const EMPTY_DEFAULTS: TrainingSessionFormValues = {
  scheduled_date: "",
  scheduled_start_time: "",
  duration_min: 60,
  location: "",
  technical_focus: "",
  description: "",
  session_kind: "entrenamiento",
  objectives: "",
  route_text: "",
  strava_url: "",
  coach_notes: "",
  convocados_athlete_ids: [],
};

export function SessionFormPage({ mode }: SessionFormPageProps) {
  const { id } = useParams();
  const location = useLocation();
  const sessionId = Number(id);
  const isEdit = mode === "edit";

  // AI assistant draft handoff via router state
  const assistantState =
    !isEdit && (location.state as AssistantDraftState | null)?.fromAssistant
      ? (location.state as AssistantDraftState)
      : null;

  const sessionQuery = useTrainingSession(sessionId, isEdit);
  const attendanceQuery = useSessionAttendance(sessionId, isEdit);

  const editReady =
    !isEdit || (!!sessionQuery.data && !!attendanceQuery.data);

  const defaults = useMemo<TrainingSessionFormValues>(() => {
    // AI assistant draft takes priority for create mode
    if (assistantState) return assistantState.draftValues;
    if (!isEdit || !sessionQuery.data) return EMPTY_DEFAULTS;
    const s = sessionQuery.data;
    return {
      scheduled_date: s.scheduled_date,
      scheduled_start_time: s.scheduled_start_time.slice(0, 5),
      duration_min: s.duration_min,
      location: s.location,
      technical_focus: s.technical_focus,
      description: s.description ?? "",
      session_kind: s.session_kind ?? "entrenamiento",
      objectives: s.objectives ?? "",
      route_text: s.route_text ?? "",
      strava_url: s.strava_url ?? "",
      coach_notes: s.coach_notes ?? "",
      convocados_athlete_ids: (attendanceQuery.data ?? []).map((a) => a.athlete_id),
    };
  }, [isEdit, sessionQuery.data, attendanceQuery.data, assistantState]);

  if (isEdit && (sessionQuery.isLoading || attendanceQuery.isLoading)) {
    return (
      <section className="mx-auto max-w-3xl space-y-3">
        <div className="h-6 w-52 animate-pulse rounded bg-light-gray" />
        <div className="h-80 animate-pulse rounded-xl bg-light-gray" />
      </section>
    );
  }

  if (isEdit && sessionQuery.isError) {
    return (
      <section className="mx-auto max-w-3xl space-y-3">
        <h1
          className="text-2xl text-charcoal"
          style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
        >
          Editar sesión
        </h1>
        <p className="text-sm text-red-700">No se pudo cargar la sesión.</p>
        <Link
          to="/training/sessions"
          className="text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
        >
          Volver a la lista
        </Link>
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-3xl space-y-5">
      <div>
        <h1
          className="text-2xl text-charcoal"
          style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
        >
          {isEdit ? "Editar sesión" : "Nueva sesión"}
        </h1>
        <p className="mt-0.5 text-sm text-mid-gray">
          {isEdit
            ? "Actualiza los datos de la sesión paso a paso."
            : "Planifica una nueva sesión de entrenamiento paso a paso."}
        </p>
      </div>

      {editReady && (
        <SessionWizard
          key={isEdit ? `edit-${sessionId}` : "create"}
          mode={mode}
          defaultValues={defaults}
          sessionId={isEdit ? sessionId : undefined}
          loadedUpdatedAt={isEdit ? sessionQuery.data?.updated_at : undefined}
          initialAthleteIds={defaults.convocados_athlete_ids}
          aiSeededFields={
            assistantState
              ? new Set(assistantState.seededFields)
              : undefined
          }
          draftNotes={assistantState?.draftNotes ?? undefined}
        />
      )}
    </section>
  );
}
