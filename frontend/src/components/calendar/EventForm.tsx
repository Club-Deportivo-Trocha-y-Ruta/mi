import { useEffect } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import { AudienceSelector } from "./AudienceSelector";
import {
  calendarEventSchema,
  buildEventPayload,
  type CalendarEventFormValues,
} from "@/schemas/calendar.schema";
import {
  useCreateCalendarEvent,
  useUpdateCalendarEvent,
} from "@/api/calendar";
import type { CalendarEventRead, EventType } from "@/types/calendar.types";
import { labelForEventType } from "./colors";

import * as TabsPrimitive from "@radix-ui/react-tabs";

interface EventFormProps {
  mode: "create" | "edit";
  initialData?: CalendarEventRead;
  prefillDate?: string; // YYYY-MM-DD
  onSuccess: () => void;
  onCancel: () => void;
}

const ALL_EVENT_TYPES: EventType[] = [
  "training_session",
  "competition",
  "club_event",
  "personal_training",
  "group_training",
  "rest_day",
];

const INTENSITY_OPTIONS = [
  { value: "low", label: "Baja" },
  { value: "medium", label: "Media" },
  { value: "high", label: "Alta" },
] as const;

const COMPETITION_CATEGORIES = [
  { value: "A", label: "A — Tapering completo" },
  { value: "B", label: "B — Mini-tapering" },
  { value: "C", label: "C — Diagnóstica" },
] as const;

const labelClass = "block text-sm font-medium text-charcoal";
const inputClass =
  "mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40";
const inputStyle = { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" };
const errorClass = "mt-1 text-xs text-red-600";
const sectionClass =
  "rounded-xl bg-white p-5 space-y-4";
const sectionStyle = {
  boxShadow:
    "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
};

function buildDefaultValues(
  initialData?: CalendarEventRead,
  prefillDate?: string,
): CalendarEventFormValues {
  if (initialData) {
    const start = new Date(initialData.start);
    const end = new Date(initialData.end);
    const durationMin = Math.round((end.getTime() - start.getTime()) / 60_000);
    const startDate = start.toISOString().slice(0, 10);
    const startTime = start.toISOString().slice(11, 16);

    return {
      event_type: initialData.event_type,
      title: initialData.title,
      description: initialData.description ?? "",
      location: initialData.location ?? "",
      start_date: startDate,
      start_time: startTime,
      duration_min: durationMin,
      all_day: initialData.allDay,
      color_hex: initialData.color_hex ?? "",
      audiences: initialData.audiences ?? [],
    };
  }

  const now = new Date();
  const defaultDate =
    prefillDate ??
    now.toLocaleDateString("en-CA", { timeZone: "America/Bogota" });
  const hours = String(now.getHours()).padStart(2, "0");
  const mins = String(now.getMinutes()).padStart(2, "0");

  return {
    event_type: "training_session",
    title: "",
    description: "",
    location: "",
    start_date: defaultDate,
    start_time: `${hours}:${mins}`,
    duration_min: 90,
    all_day: false,
    color_hex: "",
    audiences: [{ audience_type: "all_club", audience_value: {} as Record<string, never> }],
  };
}

export function EventForm({
  mode,
  initialData,
  prefillDate,
  onSuccess,
  onCancel,
}: EventFormProps) {
  const createMutation = useCreateCalendarEvent();
  const updateMutation = useUpdateCalendarEvent();

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<
    z.input<typeof calendarEventSchema>,
    unknown,
    CalendarEventFormValues
  >({
    resolver: zodResolver(calendarEventSchema),
    defaultValues: buildDefaultValues(initialData, prefillDate) as z.input<typeof calendarEventSchema>,
  });

  const selectedType = useWatch({ control, name: "event_type" });

  useEffect(() => {
    if (initialData) {
      reset(buildDefaultValues(initialData));
    }
  }, [initialData, reset]);

  async function onSubmit(values: CalendarEventFormValues) {
    const payload = buildEventPayload(values);

    if (mode === "edit" && initialData) {
      await updateMutation.mutateAsync({
        id: initialData.id,
        payload,
      });
    } else {
      await createMutation.mutateAsync(payload);
    }
    onSuccess();
  }

  const mutationError =
    createMutation.isError || updateMutation.isError
      ? "No se pudo guardar el evento. Verifica los datos e intenta de nuevo."
      : null;

  return (
    <form
      onSubmit={(e) => {
        void handleSubmit(onSubmit)(e);
      }}
      noValidate
      className="space-y-6"
    >
      {/* Step 0: Event type selector */}
      <div className={sectionClass} style={sectionStyle}>
        <h2 className="text-base font-semibold text-charcoal">Tipo de evento</h2>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {ALL_EVENT_TYPES.map((type) => (
            <label
              key={type}
              className={`flex cursor-pointer items-center justify-center rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                selectedType === type
                  ? "bg-charcoal text-white"
                  : "bg-white text-charcoal hover:bg-light-gray"
              }`}
              style={inputStyle}
            >
              <input
                type="radio"
                value={type}
                {...register("event_type")}
                className="sr-only"
              />
              {labelForEventType(type)}
            </label>
          ))}
        </div>
        {errors.event_type && (
          <p className={errorClass}>{errors.event_type.message}</p>
        )}
      </div>

      {/* Tabs: Básico / Audiencia / Específico */}
      <TabsPrimitive.Root defaultValue="basic">
        <TabsPrimitive.List
          className="flex gap-1 rounded-xl bg-light-gray p-1"
          aria-label="Secciones del formulario"
        >
          {[
            { value: "basic", label: "Básico" },
            { value: "audience", label: "Audiencia" },
            { value: "specific", label: "Datos específicos" },
          ].map((tab) => (
            <TabsPrimitive.Trigger
              key={tab.value}
              value={tab.value}
              className="flex-1 rounded-lg px-3 py-2 text-sm font-medium text-mid-gray transition-colors data-[state=active]:bg-white data-[state=active]:text-charcoal data-[state=active]:shadow-sm"
            >
              {tab.label}
            </TabsPrimitive.Trigger>
          ))}
        </TabsPrimitive.List>

        {/* ── Tab 1: Básico ─────────────────────────────────────── */}
        <TabsPrimitive.Content value="basic" className="mt-4 space-y-4">
          <div className={sectionClass} style={sectionStyle}>
            {/* Title */}
            <div>
              <label htmlFor="event-title" className={labelClass}>
                Título
              </label>
              <input
                id="event-title"
                type="text"
                placeholder="Nombre del evento"
                {...register("title")}
                className={inputClass}
                style={inputStyle}
                aria-invalid={!!errors.title}
              />
              {errors.title && <p className={errorClass}>{errors.title.message}</p>}
            </div>

            {/* Description */}
            <div>
              <label htmlFor="event-description" className={labelClass}>
                Descripción{" "}
                <span className="font-normal text-mid-gray">(opcional)</span>
              </label>
              <textarea
                id="event-description"
                rows={3}
                placeholder="Detalles del evento..."
                {...register("description")}
                className={`${inputClass} resize-none`}
                style={inputStyle}
                aria-invalid={!!errors.description}
              />
              {errors.description && (
                <p className={errorClass}>{errors.description.message}</p>
              )}
            </div>

            {/* Location */}
            <div>
              <label htmlFor="event-location" className={labelClass}>
                Lugar{" "}
                <span className="font-normal text-mid-gray">(opcional)</span>
              </label>
              <input
                id="event-location"
                type="text"
                placeholder="Ej: Pista XCO La Buitrera"
                {...register("location")}
                className={inputClass}
                style={inputStyle}
                aria-invalid={!!errors.location}
              />
              {errors.location && (
                <p className={errorClass}>{errors.location.message}</p>
              )}
            </div>

            {/* Date, time, duration */}
            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <label htmlFor="event-start-date" className={labelClass}>
                  Fecha
                </label>
                <input
                  id="event-start-date"
                  type="date"
                  {...register("start_date")}
                  className={inputClass}
                  style={inputStyle}
                  aria-invalid={!!errors.start_date}
                />
                {errors.start_date && (
                  <p className={errorClass}>{errors.start_date.message}</p>
                )}
              </div>
              <div>
                <label htmlFor="event-start-time" className={labelClass}>
                  Hora inicio
                </label>
                <input
                  id="event-start-time"
                  type="time"
                  {...register("start_time")}
                  className={inputClass}
                  style={inputStyle}
                  aria-invalid={!!errors.start_time}
                />
                {errors.start_time && (
                  <p className={errorClass}>{errors.start_time.message}</p>
                )}
              </div>
              <div>
                <label htmlFor="event-duration" className={labelClass}>
                  Duración (min)
                </label>
                <input
                  id="event-duration"
                  type="number"
                  min={1}
                  max={1440}
                  {...register("duration_min", { valueAsNumber: true })}
                  className={inputClass}
                  style={inputStyle}
                  aria-invalid={!!errors.duration_min}
                />
                {errors.duration_min && (
                  <p className={errorClass}>{errors.duration_min.message}</p>
                )}
              </div>
            </div>

            {/* All day */}
            <label className="flex cursor-pointer items-center gap-2 text-sm text-charcoal">
              <input
                type="checkbox"
                {...register("all_day")}
                className="h-4 w-4 rounded border-mid-gray"
              />
              Todo el día
            </label>

            {/* Color */}
            <div>
              <label htmlFor="event-color" className={labelClass}>
                Color personalizado{" "}
                <span className="font-normal text-mid-gray">(opcional)</span>
              </label>
              <div className="flex items-center gap-2">
                <input
                  id="event-color"
                  type="color"
                  {...register("color_hex")}
                  className="h-9 w-16 cursor-pointer rounded-lg border-none bg-transparent p-1"
                  style={inputStyle}
                />
                <span className="text-xs text-mid-gray">
                  Deja vacío para usar el color por defecto del tipo
                </span>
              </div>
              {errors.color_hex && (
                <p className={errorClass}>{errors.color_hex.message}</p>
              )}
            </div>
          </div>
        </TabsPrimitive.Content>

        {/* ── Tab 2: Audiencia ──────────────────────────────────── */}
        <TabsPrimitive.Content value="audience" className="mt-4">
          <div className={sectionClass} style={sectionStyle}>
            <h2 className="text-base font-semibold text-charcoal">Audiencia</h2>
            <Controller
              name="audiences"
              control={control}
              render={({ field }) => (
                <AudienceSelector
                  value={field.value as import("@/types/calendar.types").Audience[]}
                  onChange={field.onChange}
                  error={
                    Array.isArray(errors.audiences)
                      ? undefined
                      : errors.audiences?.message
                  }
                />
              )}
            />
          </div>
        </TabsPrimitive.Content>

        {/* ── Tab 3: Específico ─────────────────────────────────── */}
        <TabsPrimitive.Content value="specific" className="mt-4">
          <div className={sectionClass} style={sectionStyle}>
            <h2 className="text-base font-semibold text-charcoal">
              Datos de {labelForEventType(selectedType as EventType)}
            </h2>

            {/* training_session — minimal, links to TrainingSession module */}
            {selectedType === "training_session" && (
              <p className="text-sm text-mid-gray">
                Los entrenamientos en el calendario están vinculados al módulo de
                sesiones. El ID de sesión se enlazará automáticamente.
              </p>
            )}

            {/* competition */}
            {selectedType === "competition" && (
              <div className="space-y-4">
                <div>
                  <label htmlFor="comp-city" className={labelClass}>
                    Ciudad
                  </label>
                  <input
                    id="comp-city"
                    type="text"
                    placeholder="Ej: Cali"
                    {...register("data_competition.city")}
                    className={inputClass}
                    style={inputStyle}
                  />
                  {errors.data_competition?.city && (
                    <p className={errorClass}>{errors.data_competition.city.message}</p>
                  )}
                </div>
                <div>
                  <label htmlFor="comp-race-category" className={labelClass}>
                    Categoría de carrera
                  </label>
                  <select
                    id="comp-race-category"
                    {...register("data_competition.race_category")}
                    className={inputClass}
                    style={inputStyle}
                  >
                    {COMPETITION_CATEGORIES.map((c) => (
                      <option key={c.value} value={c.value}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </div>
                <label className="flex cursor-pointer items-center gap-2 text-sm text-charcoal">
                  <input
                    type="checkbox"
                    {...register("data_competition.is_departmental")}
                    className="h-4 w-4 rounded border-mid-gray"
                  />
                  Campeonato Departamental
                </label>
              </div>
            )}

            {/* club_event */}
            {selectedType === "club_event" && (
              <div className="space-y-4">
                <div>
                  <label htmlFor="club-event-kind" className={labelClass}>
                    Tipo
                  </label>
                  <select
                    id="club-event-kind"
                    {...register("data_club_event.kind")}
                    className={inputClass}
                    style={inputStyle}
                  >
                    <option value="social">Social</option>
                    <option value="meeting">Reunión</option>
                    <option value="workshop">Taller</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="club-event-url" className={labelClass}>
                    URL de registro{" "}
                    <span className="font-normal text-mid-gray">(opcional)</span>
                  </label>
                  <input
                    id="club-event-url"
                    type="url"
                    placeholder="https://..."
                    {...register("data_club_event.registration_url")}
                    className={inputClass}
                    style={inputStyle}
                  />
                  {errors.data_club_event?.registration_url && (
                    <p className={errorClass}>
                      {errors.data_club_event.registration_url.message}
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* personal_training */}
            {selectedType === "personal_training" && (
              <div className="space-y-4">
                <div>
                  <label htmlFor="pt-intensity" className={labelClass}>
                    Intensidad
                  </label>
                  <select
                    id="pt-intensity"
                    {...register("data_personal_training.intensity")}
                    className={inputClass}
                    style={inputStyle}
                  >
                    {INTENSITY_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}

            {/* group_training */}
            {selectedType === "group_training" && (
              <div className="space-y-4">
                <div>
                  <label htmlFor="gt-intensity" className={labelClass}>
                    Intensidad
                  </label>
                  <select
                    id="gt-intensity"
                    {...register("data_group_training.intensity")}
                    className={inputClass}
                    style={inputStyle}
                  >
                    {INTENSITY_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="gt-group-size" className={labelClass}>
                    Máx. atletas{" "}
                    <span className="font-normal text-mid-gray">(opcional)</span>
                  </label>
                  <input
                    id="gt-group-size"
                    type="number"
                    min={1}
                    max={50}
                    {...register("data_group_training.group_size_max", {
                      valueAsNumber: true,
                    })}
                    className={inputClass}
                    style={inputStyle}
                  />
                  {errors.data_group_training?.group_size_max && (
                    <p className={errorClass}>
                      {errors.data_group_training.group_size_max.message}
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* rest_day */}
            {selectedType === "rest_day" && (
              <div className="space-y-4">
                <div>
                  <label htmlFor="rd-scope" className={labelClass}>
                    Alcance
                  </label>
                  <select
                    id="rd-scope"
                    {...register("data_rest_day.scope")}
                    className={inputClass}
                    style={inputStyle}
                  >
                    <option value="club">Todo el club</option>
                    <option value="category">Por categoría</option>
                    <option value="athlete">Atleta específico</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="rd-reason" className={labelClass}>
                    Motivo{" "}
                    <span className="font-normal text-mid-gray">(opcional)</span>
                  </label>
                  <input
                    id="rd-reason"
                    type="text"
                    placeholder="Ej: Semana de recuperación post-carrera"
                    {...register("data_rest_day.reason")}
                    className={inputClass}
                    style={inputStyle}
                  />
                  {errors.data_rest_day?.reason && (
                    <p className={errorClass}>{errors.data_rest_day.reason.message}</p>
                  )}
                </div>
              </div>
            )}
          </div>
        </TabsPrimitive.Content>
      </TabsPrimitive.Root>

      {mutationError && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {mutationError}
        </p>
      )}

      <div className="flex justify-end gap-3">
        <button
          type="button"
          onClick={onCancel}
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
            : mode === "edit"
              ? "Guardar cambios"
              : "Crear evento"}
        </button>
      </div>
    </form>
  );
}
