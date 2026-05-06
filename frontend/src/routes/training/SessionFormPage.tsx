import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link, useNavigate, useParams } from "react-router-dom";

import { AthletesMultiSelect } from "@/components/training/AthletesMultiSelect";
import {
  useCreateTrainingSession,
  useTrainingSession,
  useUpdateTrainingSession,
} from "@/api/trainingSessions";
import {
  trainingSessionCreateSchema,
  type TrainingSessionFormValues,
} from "@/schemas/trainingSession.schema";
import type { AgeGroup } from "@/types/trainingSession.types";

interface SessionFormPageProps {
  mode: "create" | "edit";
}

const labelClass = "block text-sm font-medium text-charcoal";
const inputClass =
  "mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40";
const inputStyle = { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" };
const errorClass = "mt-1 text-xs text-red-600";

export function SessionFormPage({ mode }: SessionFormPageProps) {
  const navigate = useNavigate();
  const { id } = useParams();
  const sessionId = Number(id);
  const isEdit = mode === "edit";

  const sessionQuery = useTrainingSession(sessionId, isEdit);
  const createMutation = useCreateTrainingSession();
  const updateMutation = useUpdateTrainingSession();

  const {
    register,
    handleSubmit,
    control,
    watch,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<TrainingSessionFormValues>({
    resolver: zodResolver(trainingSessionCreateSchema),
    defaultValues: {
      age_group: "u12",
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

  const selectedAgeGroup = watch("age_group") as AgeGroup;

  useEffect(() => {
    if (isEdit && sessionQuery.data) {
      const s = sessionQuery.data;
      reset({
        age_group: s.age_group,
        scheduled_date: s.scheduled_date,
        scheduled_start_time: s.scheduled_start_time.slice(0, 5),
        duration_min: s.duration_min,
        location: s.location,
        technical_focus: s.technical_focus,
        description: s.description,
        route_text: s.route_text ?? "",
        strava_url: s.strava_url ?? "",
        convocados_athlete_ids: [],
      });
    }
  }, [isEdit, sessionQuery.data, reset]);

  async function onSubmit(values: TrainingSessionFormValues) {
    const payload = {
      ...values,
      route_text: values.route_text || null,
      strava_url: values.strava_url || null,
    };

    if (isEdit) {
      await updateMutation.mutateAsync({ id: sessionId, payload });
      navigate(`/training/sessions/${sessionId}`);
    } else {
      const created = await createMutation.mutateAsync(payload);
      navigate(`/training/sessions/${created.id}`);
    }
  }

  if (isEdit && sessionQuery.isLoading) {
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
    <section className="space-y-5">
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
        <Link
          to="/training/sessions"
          className="rounded-lg bg-white px-3 py-2 text-sm font-medium text-mid-gray transition-opacity hover:opacity-70"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
        >
          Cancelar
        </Link>
      </div>

      <form
        onSubmit={(e) => {
          void handleSubmit(onSubmit)(e);
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

          {/* Grupo de edad */}
          <div>
            <span className={labelClass}>Grupo de edad</span>
            <div className="mt-2 flex gap-4">
              {(["u12", "u15"] as const).map((g) => (
                <label key={g} className="flex cursor-pointer items-center gap-2">
                  <input
                    type="radio"
                    value={g}
                    {...register("age_group")}
                    className="h-4 w-4 text-charcoal"
                  />
                  <span className="text-sm font-medium text-charcoal">
                    {g === "u12" ? "U12 — 10 a 12 años" : "U15 — 13 a 15 años"}
                  </span>
                </label>
              ))}
            </div>
            {errors.age_group && (
              <p className={errorClass}>{errors.age_group.message}</p>
            )}
          </div>

          {/* Fecha y hora */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="scheduled_date" className={labelClass}>Fecha</label>
              <input
                id="scheduled_date"
                type="date"
                {...register("scheduled_date")}
                className={inputClass}
                style={inputStyle}
              />
              {errors.scheduled_date && (
                <p className={errorClass}>{errors.scheduled_date.message}</p>
              )}
            </div>
            <div>
              <label htmlFor="scheduled_start_time" className={labelClass}>Hora de inicio</label>
              <input
                id="scheduled_start_time"
                type="time"
                {...register("scheduled_start_time")}
                className={inputClass}
                style={inputStyle}
              />
              {errors.scheduled_start_time && (
                <p className={errorClass}>{errors.scheduled_start_time.message}</p>
              )}
            </div>
          </div>

          {/* Duración y lugar */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="duration_min" className={labelClass}>Duración (minutos)</label>
              <input
                id="duration_min"
                type="number"
                min={15}
                max={240}
                {...register("duration_min", { valueAsNumber: true })}
                className={inputClass}
                style={inputStyle}
              />
              {errors.duration_min && (
                <p className={errorClass}>{errors.duration_min.message}</p>
              )}
            </div>
            <div>
              <label htmlFor="location" className={labelClass}>Lugar</label>
              <input
                id="location"
                type="text"
                placeholder="Ej: Pista XCO La Buitrera"
                {...register("location")}
                className={inputClass}
                style={inputStyle}
              />
              {errors.location && (
                <p className={errorClass}>{errors.location.message}</p>
              )}
            </div>
          </div>

          {/* Foco técnico */}
          <div>
            <label htmlFor="technical_focus" className={labelClass}>Foco técnico</label>
            <input
              id="technical_focus"
              type="text"
              placeholder="Ej: Técnica de frenada en descenso"
              {...register("technical_focus")}
              className={inputClass}
              style={inputStyle}
            />
            {errors.technical_focus && (
              <p className={errorClass}>{errors.technical_focus.message}</p>
            )}
          </div>

          {/* Descripción */}
          <div>
            <label htmlFor="description" className={labelClass}>Descripción</label>
            <textarea
              id="description"
              rows={4}
              placeholder="Describe el plan de la sesión, objetivos, metodología..."
              {...register("description")}
              className={`${inputClass} resize-none`}
              style={inputStyle}
            />
            {errors.description && (
              <p className={errorClass}>{errors.description.message}</p>
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
            <label className={labelClass}>Descripción del recorrido</label>
            <textarea
              rows={3}
              placeholder="Describe el recorrido en texto libre (máx. 500 caracteres)..."
              {...register("route_text")}
              className={`${inputClass} resize-none`}
              style={inputStyle}
            />
            {errors.route_text && (
              <p className={errorClass}>{errors.route_text.message}</p>
            )}
          </div>

          <div>
            <label className={labelClass}>Link Strava (actividad del entrenador)</label>
            <input
              type="url"
              placeholder="https://www.strava.com/activities/..."
              {...register("strava_url")}
              className={inputClass}
              style={inputStyle}
            />
            {errors.strava_url && (
              <p className={errorClass}>{errors.strava_url.message}</p>
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
                ageGroup={selectedAgeGroup}
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
          <Link
            to="/training/sessions"
            className="rounded-lg bg-white px-4 py-2 text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
          >
            Cancelar
          </Link>
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
    </section>
  );
}
