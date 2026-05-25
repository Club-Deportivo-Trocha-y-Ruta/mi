import { useEffect, useMemo, useRef, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link, useNavigate, useParams } from "react-router-dom";

import { AthletesMultiSelect } from "@/components/training/AthletesMultiSelect";
import { DurationPicker } from "@/components/training/DurationPicker";
import {
  NotifyParentsDialog,
  type NotifyVariant,
} from "@/components/training/NotifyParentsDialog";
import {
  bulkSetConvocatoria,
  useCreateTrainingSession,
  useSessionAttendance,
  useTrainingSession,
  useUpdateTrainingSession,
} from "@/api/trainingSessions";
import { useAthletes } from "@/hooks/athletes/useAthletes";
import { useQueryClient } from "@tanstack/react-query";
import {
  trainingSessionCreateSchema,
  type TrainingSessionFormValues,
} from "@/schemas/trainingSession.schema";
import type { TrainingSessionCreate } from "@/types/trainingSession.types";
import {
  diffAthleteIds,
  diffSessionValues,
  type AthleteEntry,
  type ChangeEntry,
} from "@/lib/sessionDiff";
interface SessionFormPageProps {
  mode: "create" | "edit";
}

// Clases compartidas — los inputs usan `shadow-ring` (utility de style.css)
// para el border 1px del design system. B5 romperá este formulario en
// sub-componentes; por ahora mantenemos las clases inline alineadas con shadcn.
const labelClass = "block text-sm font-medium text-charcoal";
const inputClass =
  "mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 shadow-ring";
const errorClass = "mt-1 text-xs text-red-600";

export function SessionFormPage({ mode }: SessionFormPageProps) {
  const navigate = useNavigate();
  const { id } = useParams();
  const sessionId = Number(id);
  const isEdit = mode === "edit";

  const sessionQuery = useTrainingSession(sessionId, isEdit);
  const attendanceQuery = useSessionAttendance(sessionId, isEdit);
  const createMutation = useCreateTrainingSession();
  const updateMutation = useUpdateTrainingSession();
  const queryClient = useQueryClient();

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<TrainingSessionFormValues>({
    resolver: zodResolver(trainingSessionCreateSchema),
    shouldFocusError: true,
    defaultValues: {
      scheduled_date: "",
      scheduled_start_time: "",
      duration_min: 60,
      location: "",
      technical_focus: "",
      description: "",
      route_text: "",
      strava_url: "",
      convocados_athlete_ids: [],
    },
  });

  const initialValuesRef = useRef<TrainingSessionFormValues | null>(null);
  const athletesQuery = useAthletes();

  useEffect(() => {
    if (isEdit && sessionQuery.data && attendanceQuery.data) {
      const s = sessionQuery.data;
      const snapshot: TrainingSessionFormValues = {
        scheduled_date: s.scheduled_date,
        scheduled_start_time: s.scheduled_start_time.slice(0, 5),
        duration_min: s.duration_min,
        location: s.location,
        technical_focus: s.technical_focus,
        description: s.description,
        route_text: s.route_text ?? "",
        strava_url: s.strava_url ?? "",
        convocados_athlete_ids: attendanceQuery.data.map((a) => a.athlete_id),
      };
      reset(snapshot);
      initialValuesRef.current = snapshot;
    }
  }, [isEdit, sessionQuery.data, attendanceQuery.data, reset]);

  const allAthletes = athletesQuery.data?.items ?? [];
  const athleteNameById = useMemo(() => {
    const map = new Map<number, string>();
    for (const a of allAthletes) {
      map.set(a.id, `${a.first_name} ${a.last_name}`.trim());
    }
    return map;
  }, [allAthletes]);

  interface PendingSave {
    payload: TrainingSessionCreate;
    variant: NotifyVariant;
    changes: ChangeEntry[];
    addedAthletes: AthleteEntry[];
    removedAthletes: AthleteEntry[];
    convocadosChanged: boolean;
  }

  const [pending, setPending] = useState<PendingSave | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [dialogPending, setDialogPending] = useState(false);

  function buildPayload(values: TrainingSessionFormValues): TrainingSessionCreate {
    return {
      ...values,
      route_text: values.route_text || null,
      strava_url: values.strava_url || null,
    };
  }

  function nameFor(id: number): AthleteEntry {
    return { id, name: athleteNameById.get(id) ?? `Atleta #${id}` };
  }

  async function onSubmit(values: TrainingSessionFormValues) {
    const payload = buildPayload(values);

    if (!isEdit) {
      setPending({
        payload,
        variant: "create",
        changes: [],
        addedAthletes: values.convocados_athlete_ids.map(nameFor),
        removedAthletes: [],
        convocadosChanged: false,
      });
      return;
    }

    const initial = initialValuesRef.current;
    if (!initial) return; // datos aún no cargados

    const changes = diffSessionValues(
      initial as unknown as Record<string, unknown>,
      values as unknown as Record<string, unknown>,
    );
    const attendanceDiff = diffAthleteIds(
      initial.convocados_athlete_ids,
      values.convocados_athlete_ids,
    );

    // Si no hay cambio alguno, atajo: salir sin diálogo ni mutaciones.
    if (changes.length === 0 && !attendanceDiff.changed) {
      navigate(`/training/sessions/${sessionId}`);
      return;
    }

    const variant: NotifyVariant =
      changes.length > 0 ? "update" : "attendance";

    setPending({
      payload,
      variant,
      changes,
      addedAthletes: attendanceDiff.added.map(nameFor),
      removedAthletes: attendanceDiff.removed.map(nameFor),
      convocadosChanged: attendanceDiff.changed,
    });
  }

  async function persistPending(sendNotification: boolean) {
    if (!pending) return;
    setDialogPending(true);
    setDialogError(null);
    try {
      if (isEdit) {
        await updateMutation.mutateAsync({
          id: sessionId,
          payload: { ...pending.payload, send_notification: sendNotification },
        });

        if (pending.convocadosChanged) {
          await bulkSetConvocatoria(
            sessionId,
            pending.payload.convocados_athlete_ids,
            sendNotification,
          );
          // Invalidación por namespace para alcanzar las variantes con
          // userId en el key (privacy R2: cache aislado por cuenta).
          await queryClient.invalidateQueries({
            queryKey: ["training-session-attendance"],
          });
          await queryClient.invalidateQueries({
            queryKey: ["training-session"],
          });
        }

        setPending(null);
        navigate(`/training/sessions/${sessionId}`);
      } else {
        const created = await createMutation.mutateAsync({
          ...pending.payload,
          send_notification: sendNotification,
        });
        setPending(null);
        navigate(`/training/sessions/${created.id}`);
      }
    } catch {
      setDialogError("No se pudo guardar la sesión. Intenta de nuevo.");
    } finally {
      setDialogPending(false);
    }
  }

  function handleDialogCancel() {
    if (dialogPending) return;
    setPending(null);
    setDialogError(null);
  }

  function handleCancel() {
    if (isDirty) {
      const ok = window.confirm("Tienes cambios sin guardar. ¿Salir sin guardar?");
      if (!ok) return;
    }
    navigate("/training/sessions");
  }

  function onError() {
    document
      .querySelector('[aria-invalid="true"]')
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  if (isEdit && (sessionQuery.isLoading || attendanceQuery.isLoading)) {
    return (
      <section className="space-y-3">
        <div className="h-6 w-52 animate-pulse rounded bg-light-gray" />
        <div className="h-80 animate-pulse rounded-xl bg-light-gray" />
      </section>
    );
  }

  if (isEdit && sessionQuery.isError) {
    return (
      <section className="space-y-3">
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

  const mutationError =
    createMutation.isError || updateMutation.isError
      ? "No se pudo guardar la sesión. Intenta de nuevo."
      : null;

  return (
    <section className="max-w-3xl mx-auto space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1
            className="text-2xl text-charcoal"
            style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
          >
            {isEdit ? "Editar sesión" : "Nueva sesión"}
          </h1>
          <p className="mt-0.5 text-sm text-mid-gray">
            {isEdit
              ? "Actualiza los datos de la sesión."
              : "Planifica una nueva sesión de entrenamiento."}
          </p>
        </div>
        <button
          type="button"
          onClick={handleCancel}
          className="rounded-lg bg-white px-3 py-2 text-sm font-medium text-mid-gray transition-opacity hover:opacity-70"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
        >
          Cancelar
        </button>
      </div>

      <form
        onSubmit={(e) => {
          void handleSubmit(onSubmit, onError)(e);
        }}
        className="space-y-6"
        noValidate
      >
        {/* Sección 1: Básicos */}
        <div
          className="rounded-xl bg-white p-5 space-y-4"
          style={{
            boxShadow:
              "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
          }}
        >
          <h2 className="text-base font-semibold text-charcoal">Información general</h2>

          {/* Fecha y hora */}
          <div className="grid gap-4 sm:grid-cols-[180px_180px] justify-start">
            <div>
              <label htmlFor="scheduled_date-input" className={labelClass}>Fecha</label>
              <input
                id="scheduled_date-input"
                type="date"
                {...register("scheduled_date")}
                className={inputClass}

                aria-describedby={errors.scheduled_date ? "scheduled_date-error" : undefined}
                aria-invalid={!!errors.scheduled_date}
              />
              {errors.scheduled_date && (
                <p id="scheduled_date-error" className={errorClass}>{errors.scheduled_date.message}</p>
              )}
            </div>
            <div>
              <label htmlFor="scheduled_start_time-input" className={labelClass}>Hora de inicio</label>
              <input
                id="scheduled_start_time-input"
                type="time"
                {...register("scheduled_start_time")}
                className={inputClass}

                aria-describedby={errors.scheduled_start_time ? "scheduled_start_time-error" : undefined}
                aria-invalid={!!errors.scheduled_start_time}
              />
              {errors.scheduled_start_time && (
                <p id="scheduled_start_time-error" className={errorClass}>{errors.scheduled_start_time.message}</p>
              )}
            </div>
          </div>

          {/* Duración y lugar */}
          <div className="grid gap-4 sm:grid-cols-[auto_1fr] sm:items-start">
            <div className="sm:max-w-[260px]">
              <Controller
                name="duration_min"
                control={control}
                render={({ field }) => (
                  <DurationPicker
                    value={field.value}
                    onChange={field.onChange}
                    error={errors.duration_min?.message}
                  />
                )}
              />
            </div>
            <div>
              <label htmlFor="location-input" className={labelClass}>Lugar</label>
              <input
                id="location-input"
                type="text"
                placeholder="Ej: Pista XCO La Buitrera"
                {...register("location")}
                className={inputClass}

                aria-describedby={errors.location ? "location-error" : undefined}
                aria-invalid={!!errors.location}
              />
              {errors.location && (
                <p id="location-error" className={errorClass}>{errors.location.message}</p>
              )}
            </div>
          </div>

          {/* Foco técnico */}
          <div>
            <label htmlFor="technical_focus-input" className={labelClass}>Foco técnico</label>
            <input
              id="technical_focus-input"
              type="text"
              placeholder="Ej: Técnica de frenada en descenso"
              {...register("technical_focus")}
              className={inputClass}

              aria-describedby={errors.technical_focus ? "technical_focus-error" : undefined}
              aria-invalid={!!errors.technical_focus}
            />
            {errors.technical_focus && (
              <p id="technical_focus-error" className={errorClass}>{errors.technical_focus.message}</p>
            )}
          </div>

          {/* Descripción */}
          <div>
            <label htmlFor="description-input" className={labelClass}>Descripción</label>
            <textarea
              id="description-input"
              rows={4}
              placeholder="Describe el plan de la sesión, objetivos, metodología..."
              {...register("description")}
              className={`${inputClass} resize-none`}

              aria-describedby={errors.description ? "description-error" : undefined}
              aria-invalid={!!errors.description}
            />
            {errors.description && (
              <p id="description-error" className={errorClass}>{errors.description.message}</p>
            )}
          </div>
        </div>

        {/* Sección 2: Recorrido (opcional) */}
        <div
          className="rounded-xl bg-white p-5 space-y-4"
          style={{
            boxShadow:
              "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
          }}
        >
          <div>
            <h2 className="text-base font-semibold text-charcoal">
              Recorrido{" "}
              <span className="text-sm font-normal text-mid-gray">(opcional)</span>
            </h2>
          </div>

          <div>
            <label htmlFor="route-description" className={labelClass}>Descripción del recorrido</label>
            <textarea
              id="route-description"
              rows={3}
              placeholder="Describe el recorrido en texto libre (máx. 500 caracteres)..."
              {...register("route_text")}
              className={`${inputClass} resize-none`}

              aria-describedby={errors.route_text ? "route_text-error" : undefined}
              aria-invalid={!!errors.route_text}
            />
            {errors.route_text && (
              <p id="route_text-error" className={errorClass}>{errors.route_text.message}</p>
            )}
          </div>

          <div>
            <label htmlFor="strava-url" className={labelClass}>Link Strava (actividad del entrenador)</label>
            <input
              id="strava-url"
              type="url"
              placeholder="https://www.strava.com/activities/..."
              {...register("strava_url")}
              className={inputClass}

              aria-describedby={errors.strava_url ? "strava_url-error" : undefined}
              aria-invalid={!!errors.strava_url}
            />
            {errors.strava_url && (
              <p id="strava_url-error" className={errorClass}>{errors.strava_url.message}</p>
            )}
          </div>
        </div>

        {/* Sección 3: Atletas convocados */}
        <div
          className="rounded-xl bg-white p-5 space-y-4"
          style={{
            boxShadow:
              "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
          }}
        >
          <h2 className="text-base font-semibold text-charcoal">Atletas convocados</h2>
          <Controller
            name="convocados_athlete_ids"
            control={control}
            render={({ field }) => (
              <AthletesMultiSelect
                value={field.value}
                onChange={field.onChange}
                error={errors.convocados_athlete_ids?.message}
              />
            )}
          />
        </div>

        {mutationError && (
          <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {mutationError}
          </p>
        )}

        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={handleCancel}
            className="rounded-lg bg-white px-4 py-2 text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={isSubmitting}
            className="rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70 disabled:opacity-50"
            style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
          >
            {isSubmitting
              ? "Guardando..."
              : isEdit
                ? "Guardar cambios"
                : "Crear sesión"}
          </button>
        </div>
      </form>

      <NotifyParentsDialog
        open={pending !== null}
        variant={pending?.variant ?? "create"}
        parentCount={
          pending?.variant === "attendance"
            ? pending.addedAthletes.length
            : (pending?.payload.convocados_athlete_ids.length ?? 0)
        }
        changes={pending?.changes ?? []}
        addedAthletes={pending?.addedAthletes ?? []}
        removedAthletes={pending?.removedAthletes ?? []}
        isPending={dialogPending}
        errorMessage={dialogError}
        onSend={() => void persistPending(true)}
        onSkip={() => void persistPending(false)}
        onCancel={handleDialogCancel}
      />
    </section>
  );
}
