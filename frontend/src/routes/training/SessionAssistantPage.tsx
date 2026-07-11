/**
 * SessionAssistantPage — pre-wizard launch page for the AI session assistant.
 *
 * Hosts `SessionAssistantPanel` (lazy-loaded by the route).  On draft ready,
 * navigates to `/training/sessions/new` passing the mapped form values and
 * AI-seeded field set via React Router location state.
 *
 * On "continuar manualmente" the same route is opened without state (blank form).
 */
import { lazy, Suspense } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";

import { useAuthStore } from "@/store/auth.store";
import { useAthletes } from "@/hooks/athletes/useAthletes";

import type { DraftReadyPayload } from "@/components/training/session-wizard/ai-assistant/SessionAssistantPanel";
import type { TrainingSessionFormValues } from "@/schemas/trainingSession.schema";
import type { SeededFieldName } from "@/components/training/session-wizard/ai-assistant/aiSeededFields";

// Lazy-load the heavy panel component
const SessionAssistantPanel = lazy(() =>
  import(
    "@/components/training/session-wizard/ai-assistant/SessionAssistantPanel"
  ).then((m) => ({ default: m.SessionAssistantPanel })),
);

// Empty defaults (same as SessionFormPage)
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

/** Router state passed to /training/sessions/new when a draft is ready. */
export interface AssistantDraftState {
  fromAssistant: true;
  draftValues: TrainingSessionFormValues;
  seededFields: string[]; // Set serialised to array for router state
  draftNotes: string | null;
}

export function SessionAssistantPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const clubId = user?.club_ids?.[0] ?? 1;

  const athletesQuery = useAthletes({ club_id: clubId });
  const roster = athletesQuery.data?.items ?? [];

  function handleDraftReady({ values, seededFields, draftNotes }: DraftReadyPayload) {
    const state: AssistantDraftState = {
      fromAssistant: true,
      draftValues: values,
      seededFields: [...seededFields] as string[],
      draftNotes,
    };
    void navigate("/training/sessions/new", { state });
  }

  function handleContinueManually() {
    void navigate("/training/sessions/new");
  }

  return (
    <section className="mx-auto max-w-2xl space-y-5">
      <div>
        <div className="flex items-center gap-2">
          <Link
            to="/training/sessions"
            className="text-sm text-mid-gray hover:text-charcoal transition-colors"
          >
            Sesiones
          </Link>
          <span className="text-mid-gray">/</span>
          <span className="text-sm text-charcoal">Asistente IA</span>
        </div>
        <h1
          className="font-display mt-2 text-2xl text-charcoal"
        >
          Asistente IA
        </h1>
        <p className="mt-0.5 text-sm text-mid-gray">
          Planifica una sesión con ayuda de la inteligencia artificial.
        </p>
      </div>

      <div
        className="rounded-xl bg-white p-5 shadow-card"
      >
        <Suspense
          fallback={
            <div className="flex min-h-[200px] items-center justify-center gap-2 text-sm text-mid-gray">
              <Loader2 size={16} className="animate-spin" aria-hidden="true" />
              Cargando asistente…
            </div>
          }
        >
          <SessionAssistantPanel
            clubId={clubId}
            roster={roster}
            currentFormValues={EMPTY_DEFAULTS}
            onDraftReady={handleDraftReady}
            onContinueManually={handleContinueManually}
          />
        </Suspense>
      </div>
    </section>
  );
}

// Re-export the state type helper for use in SessionFormPage
export type { SeededFieldName };
