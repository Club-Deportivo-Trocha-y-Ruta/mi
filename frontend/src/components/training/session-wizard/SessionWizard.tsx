import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowLeft, ArrowRight, CheckCircle2, Loader2, RotateCcw } from "lucide-react";

import {
  bulkSetConvocatoria,
  fetchTrainingSession,
  uploadRouteFile,
  useCreateTrainingSession,
  useUpdateTrainingSession,
} from "@/api/trainingSessions";
import { useAuthStore } from "@/store/auth.store";
import { useFormDraft } from "@/hooks/useFormDraft";
import {
  STEP_ATHLETES_FIELDS,
  STEP_GENERAL_FIELDS,
  STEP_ROUTE_NOTES_FIELDS,
  trainingSessionCreateSchema,
  type TrainingSessionFormValues,
} from "@/schemas/trainingSession.schema";
import type {
  TrainingSession,
  TrainingSessionCreate,
  TrainingSessionUpdate,
} from "@/types/trainingSession.types";

import { SessionStepper, type WizardStep } from "./SessionStepper";
import { SessionErrorSummary, type ErrorSummaryItem } from "./SessionErrorSummary";
import { StepGeneral } from "./StepGeneral";
import { StepAthletes } from "./StepAthletes";
import { StepRouteNotes } from "./StepRouteNotes";
import { StepReview } from "./StepReview";

const STEPS: WizardStep[] = [
  { idx: 1, label: "General" },
  { idx: 2, label: "Atletas" },
  { idx: 3, label: "Ruta y notas" },
  { idx: 4, label: "Revisar" },
];

const FIELDS_BY_STEP: Record<number, readonly (keyof TrainingSessionFormValues)[]> = {
  1: STEP_GENERAL_FIELDS,
  2: STEP_ATHLETES_FIELDS,
  3: STEP_ROUTE_NOTES_FIELDS,
};

const ERROR_TARGET_ID: Record<string, string> = {
  scheduled_date: "scheduled_date-input",
  scheduled_start_time: "scheduled_start_time-input",
  duration_min: "duration-group-label",
  location: "location-input",
  technical_focus: "technical_focus-input",
  description: "description-input",
  objectives: "objectives-input",
  convocados_athlete_ids: "session-step-athletes",
  route_text: "route_text-input",
  strava_url: "strava_url-input",
  coach_notes: "coach_notes-input",
};

export interface SessionWizardProps {
  mode: "create" | "edit";
  defaultValues: TrainingSessionFormValues;
  /** Solo en edición. */
  sessionId?: number;
  /** Solo en edición: `updated_at` cargado, para detectar edición concurrente. */
  loadedUpdatedAt?: string;
  /** Solo en edición: ids convocados al cargar (para diff de convocatoria). */
  initialAthleteIds?: number[];
}

type SubmitOutcome =
  | { kind: "idle" }
  | { kind: "success"; sessionId: number; notified: boolean }
  | { kind: "route-upload-failed"; sessionId: number };

function buildCreatePayload(
  v: TrainingSessionFormValues,
  notify: boolean,
): TrainingSessionCreate {
  return {
    scheduled_date: v.scheduled_date,
    scheduled_start_time: v.scheduled_start_time,
    duration_min: v.duration_min,
    location: v.location,
    technical_focus: v.technical_focus,
    description: v.description,
    session_kind: v.session_kind ?? "entrenamiento",
    objectives: v.objectives || null,
    route_text: v.route_text || null,
    strava_url: v.strava_url || null,
    coach_notes: v.coach_notes || null,
    convocados_athlete_ids: v.convocados_athlete_ids,
    send_notification: notify,
  };
}

function buildUpdatePayload(
  v: TrainingSessionFormValues,
  notify: boolean,
): TrainingSessionUpdate {
  return {
    scheduled_date: v.scheduled_date,
    scheduled_start_time: v.scheduled_start_time,
    duration_min: v.duration_min,
    location: v.location,
    technical_focus: v.technical_focus,
    description: v.description,
    session_kind: v.session_kind ?? "entrenamiento",
    objectives: v.objectives || null,
    route_text: v.route_text || null,
    strava_url: v.strava_url || null,
    coach_notes: v.coach_notes || null,
    send_notification: notify,
  };
}

export function SessionWizard({
  mode,
  defaultValues,
  sessionId,
  loadedUpdatedAt,
  initialAthleteIds = [],
}: SessionWizardProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const userId = useAuthStore((s) => s.user?.id ?? null);
  const isEdit = mode === "edit";

  const createMutation = useCreateTrainingSession();
  const updateMutation = useUpdateTrainingSession();

  const {
    register,
    control,
    handleSubmit,
    trigger,
    getValues,
    watch,
    reset,
    formState: { errors },
  } = useForm<TrainingSessionFormValues>({
    resolver: zodResolver(trainingSessionCreateSchema),
    mode: "onTouched",
    defaultValues,
  });

  const [step, setStep] = useState(1);
  const [routeFile, setRouteFile] = useState<File | null>(null);
  const [routeFileError, setRouteFileError] = useState<string | null>(null);
  const [notify, setNotify] = useState(false);
  // Mostramos el resumen de errores tras intentar avanzar/guardar; los ítems se
  // derivan en render de `errors` (proxy reactivo) para no leer estado obsoleto.
  const [showSummary, setShowSummary] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<SubmitOutcome>({ kind: "idle" });
  const [submitting, setSubmitting] = useState(false);

  // --- Borrador local (autoguardado + restauración)
  const draftTarget = isEdit && sessionId ? String(sessionId) : "new";
  const { restoreCandidate, saveDraft, clearDraft } = useFormDraft<TrainingSessionFormValues>({
    userId,
    target: draftTarget,
  });
  const [draftDismissed, setDraftDismissed] = useState(false);

  // Autoguardado: nos suscribimos a cambios del formulario (debounced en el hook).
  const watched = watch();
  const lastSerialized = useRef<string>("");
  useEffect(() => {
    const serialized = JSON.stringify(watched);
    if (serialized !== lastSerialized.current) {
      lastSerialized.current = serialized;
      saveDraft(watched, step);
    }
  }, [watched, step, saveDraft]);

  function restoreDraft() {
    if (restoreCandidate) {
      reset(restoreCandidate.values);
      setStep(Math.min(Math.max(restoreCandidate.step, 1), 4));
    }
    setDraftDismissed(true);
  }

  function discardDraft() {
    clearDraft();
    setDraftDismissed(true);
  }

  const summaryItems: ErrorSummaryItem[] = Object.entries(errors)
    .filter(([, e]) => e && (e as { message?: string }).message)
    .map(([field, e]) => ({
      field,
      message: (e as { message?: string }).message ?? "Campo inválido",
      targetId: ERROR_TARGET_ID[field] ?? field,
    }));

  async function goNext() {
    const fields = FIELDS_BY_STEP[step];
    const valid = fields ? await trigger(fields as never, { shouldFocus: true }) : true;
    if (!valid) {
      setShowSummary(true);
      return;
    }
    setShowSummary(false);
    setStep((s) => Math.min(s + 1, 4));
  }

  function goBack() {
    setShowSummary(false);
    setStep((s) => Math.max(s - 1, 1));
  }

  async function onValid(values: TrainingSessionFormValues) {
    setSubmitError(null);
    setShowSummary(false);
    setSubmitting(true);
    try {
      let saved: TrainingSession;
      if (isEdit && sessionId) {
        // Detección de edición concurrente (FR-019): si la sesión cambió en el
        // servidor desde que se cargó, avisar antes de sobrescribir.
        if (loadedUpdatedAt) {
          try {
            const current = await fetchTrainingSession(sessionId);
            if (current.updated_at && current.updated_at !== loadedUpdatedAt) {
              setSubmitError(
                "Esta sesión fue modificada en otro dispositivo. Recarga la página " +
                  "para ver los cambios antes de guardar.",
              );
              setSubmitting(false);
              return;
            }
          } catch {
            // Si la verificación falla (red), continuamos con el guardado normal.
          }
        }
        saved = await updateMutation.mutateAsync({
          id: sessionId,
          payload: buildUpdatePayload(values, notify),
        });
        const currentIds = values.convocados_athlete_ids;
        const changed =
          currentIds.length !== initialAthleteIds.length ||
          currentIds.some((id) => !initialAthleteIds.includes(id));
        if (changed) {
          await bulkSetConvocatoria(sessionId, currentIds, notify);
          await queryClient.invalidateQueries({
            queryKey: ["training-session-attendance"],
          });
        }
      } else {
        saved = await createMutation.mutateAsync(buildCreatePayload(values, notify));
      }

      // Subida del archivo de ruta tras guardar (no bloquea la sesión ya creada).
      if (routeFile) {
        try {
          await uploadRouteFile(saved.id, routeFile);
        } catch {
          clearDraft();
          setRouteFileError(
            "La sesión se guardó, pero el archivo de recorrido no se pudo subir.",
          );
          setOutcome({ kind: "route-upload-failed", sessionId: saved.id });
          setSubmitting(false);
          return;
        }
      }

      clearDraft();
      setOutcome({ kind: "success", sessionId: saved.id, notified: notify });
      setSubmitting(false);
    } catch {
      setSubmitError(
        isEdit
          ? "No se pudo guardar los cambios. Revisa tu conexión e intenta de nuevo."
          : "No se pudo crear la sesión. Revisa tu conexión e intenta de nuevo.",
      );
      setSubmitting(false);
    }
  }

  function onInvalid() {
    setShowSummary(true);
  }

  // --- Pantalla de resultado (éxito o fallo de subida de ruta)
  if (outcome.kind === "success") {
    return (
      <div
        role="status"
        className="rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-5 text-sm text-emerald-900"
        data-testid="session-wizard-success"
      >
        <div className="mb-2 flex items-center gap-2">
          <CheckCircle2 size={18} aria-hidden="true" />
          <span className="font-semibold">
            {isEdit ? "Sesión actualizada" : "Sesión creada"}
          </span>
        </div>
        <p className="text-xs">
          {outcome.notified
            ? "Se envió la notificación a las familias de los atletas convocados."
            : "No se enviaron notificaciones a las familias."}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => navigate(`/training/sessions/${outcome.sessionId}`)}
            className="rounded-lg bg-charcoal px-3 py-2 text-xs font-semibold text-white hover:opacity-90"
          >
            Ver la sesión
          </button>
          <button
            type="button"
            onClick={() => navigate("/training/sessions")}
            className="rounded-lg bg-white px-3 py-2 text-xs font-medium text-charcoal ring-1 ring-light-gray hover:bg-light-gray"
          >
            Volver a la lista
          </button>
        </div>
      </div>
    );
  }

  if (outcome.kind === "route-upload-failed") {
    return (
      <div
        role="alert"
        className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-5 text-sm text-amber-900"
        data-testid="session-wizard-route-failed"
      >
        <div className="mb-2 flex items-center gap-2">
          <AlertCircle size={18} aria-hidden="true" />
          <span className="font-semibold">Sesión guardada, archivo pendiente</span>
        </div>
        <p className="text-xs">
          La sesión se guardó correctamente, pero el archivo de recorrido no se subió.
          Puedes reintentar la subida o continuar y adjuntarlo más tarde desde el detalle.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={async () => {
              if (!routeFile) return;
              setRouteFileError(null);
              try {
                await uploadRouteFile(outcome.sessionId, routeFile);
                setOutcome({ kind: "success", sessionId: outcome.sessionId, notified: notify });
              } catch {
                setRouteFileError("La subida volvió a fallar. Intenta más tarde.");
              }
            }}
            className="inline-flex items-center gap-1 rounded-lg bg-charcoal px-3 py-2 text-xs font-semibold text-white hover:opacity-90"
          >
            <RotateCcw size={12} aria-hidden="true" />
            Reintentar subida
          </button>
          <button
            type="button"
            onClick={() => navigate(`/training/sessions/${outcome.sessionId}`)}
            className="rounded-lg bg-white px-3 py-2 text-xs font-medium text-charcoal ring-1 ring-light-gray hover:bg-light-gray"
          >
            Continuar sin archivo
          </button>
        </div>
        {routeFileError && (
          <p className="mt-2 text-xs text-red-700" role="alert">
            {routeFileError}
          </p>
        )}
      </div>
    );
  }

  const showRestoreBanner =
    !!restoreCandidate && !draftDismissed && !isEdit;

  return (
    <section data-testid="session-wizard">
      <SessionStepper
        steps={STEPS}
        active={step}
        onStepClick={(idx) => setStep(idx)}
      />

      {showRestoreBanner && (
        <div
          className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900"
          role="status"
          data-testid="session-draft-banner"
        >
          <span>Tienes un borrador sin guardar de una sesión anterior.</span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={restoreDraft}
              className="rounded-lg bg-charcoal px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90"
            >
              Restaurar
            </button>
            <button
              type="button"
              onClick={discardDraft}
              className="rounded-lg bg-white px-3 py-1.5 text-xs font-medium text-charcoal ring-1 ring-blue-200 hover:bg-blue-100"
            >
              Descartar
            </button>
          </div>
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (step === 4) void handleSubmit(onValid, onInvalid)(e);
        }}
        noValidate
        className="space-y-5"
      >
        <div
          className="rounded-xl bg-white p-5"
          style={{
            boxShadow:
              "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
          }}
        >
          {step === 1 && (
            <StepGeneral register={register} control={control} errors={errors} />
          )}
          {step === 2 && <StepAthletes control={control} errors={errors} />}
          {step === 3 && (
            <StepRouteNotes
              register={register}
              errors={errors}
              routeFile={routeFile}
              onRouteFileChange={(f) => {
                setRouteFile(f);
                setRouteFileError(null);
              }}
              routeFileError={routeFileError}
            />
          )}
          {step === 4 && (
            <StepReview
              values={getValues()}
              athleteCount={getValues("convocados_athlete_ids")?.length ?? 0}
              routeFileName={routeFile?.name ?? null}
              notify={notify}
              onNotifyChange={setNotify}
            />
          )}
        </div>

        {showSummary && summaryItems.length > 0 && (
          <SessionErrorSummary items={summaryItems} />
        )}

        {submitError && (
          <p
            className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
            role="alert"
          >
            {submitError}
          </p>
        )}

        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={goBack}
            disabled={step === 1}
            className="inline-flex min-h-[48px] items-center gap-1 rounded-lg px-3 py-2 text-sm text-mid-gray hover:text-charcoal disabled:opacity-40"
          >
            <ArrowLeft size={16} aria-hidden="true" />
            Atrás
          </button>

          {step < 4 ? (
            <button
              type="button"
              onClick={() => void goNext()}
              className="inline-flex min-h-[48px] items-center gap-2 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-white hover:opacity-90"
            >
              Siguiente
              <ArrowRight size={16} aria-hidden="true" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={submitting}
              className="inline-flex min-h-[48px] items-center gap-2 rounded-lg bg-charcoal px-5 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
              data-testid="session-wizard-submit"
            >
              {submitting && <Loader2 size={16} className="animate-spin" aria-hidden="true" />}
              {isEdit ? "Guardar cambios" : "Crear sesión"}
            </button>
          )}
        </div>
      </form>
    </section>
  );
}
