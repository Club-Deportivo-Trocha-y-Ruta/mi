import { useEffect, useMemo } from "react";
import { Link as RouterLink } from "react-router-dom";
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
import { useAvailableRaceEvents } from "@/hooks/calendar/useAvailableRaceEvents";
import type {
  CalendarEventRead,
  EventDataCompetition,
  EventDataClubEvent,
  EventDataPersonalTraining,
  EventDataGroupTraining,
  EventDataRestDay,
  EventDataTrainingSession,
  EventType,
} from "@/types/calendar.types";
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

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function buildSpecificFields(
  eventType: CalendarEventRead["event_type"],
  eventData: CalendarEventRead["event_data"],
): Record<string, any> {
  if (!eventData) return {};
  switch (eventType) {
    case "training_session": {
      const d = eventData as EventDataTrainingSession;
      return { data_training_session: { training_session_id: d.training_session_id } };
    }
    case "competition": {
      const d = eventData as EventDataCompetition;
      return {
        data_competition: {
          city: d.city ?? "",
          race_category: d.race_category ?? "A",
          is_departmental: d.is_departmental ?? false,
        },
      };
    }
    case "club_event": {
      const d = eventData as EventDataClubEvent;
      return {
        data_club_event: {
          kind: d.kind ?? "social",
          registration_url: d.registration_url ?? "",
        },
      };
    }
    case "personal_training": {
      const d = eventData as EventDataPersonalTraining;
      return {
        data_personal_training: {
          athlete_id: d.athlete_id,
          intensity: d.intensity ?? "medium",
        },
      };
    }
    case "group_training": {
      const d = eventData as EventDataGroupTraining;
      return {
        data_group_training: {
          intensity: d.intensity ?? "medium",
          group_size_max: d.group_size_max,
        },
      };
    }
    case "rest_day": {
      const d = eventData as EventDataRestDay;
      return {
        data_rest_day: {
          scope: d.scope ?? "club",
          reason: d.reason ?? "",
        },
      };
    }
    default:
      return {};
  }
}

function buildDefaultValues(
  initialData?: CalendarEventRead,
  prefillDate?: string,
): CalendarEventFormValues {
  if (initialData) {
    const start = new Date(initialData.start_at);
    const end = new Date(initialData.end_at);
    const durationMin = Math.round((end.getTime() - start.getTime()) / 60_000);
    const startDate = start.toISOString().slice(0, 10);
    const startTime = start.toISOString().slice(11, 16);

    // Birthdays son virtuales y no se editan; el router bloquea PATCH, pero
    // como guarda defensiva caemos a "club_event" si llegara a invocarse.
    const editableType =
      initialData.event_type === "birthday"
        ? "club_event"
        : initialData.event_type;

    const specificFields = buildSpecificFields(
      editableType,
      initialData.event_data,
    );

    return {
      event_type: editableType,
      title: initialData.title,
      description: initialData.description ?? "",
      location: initialData.location ?? "",
      start_date: startDate,
      start_time: startTime,
      duration_min: durationMin,
      all_day: initialData.all_day,
      color_hex: initialData.color_hex ?? "",
      // FE-2: hidrata el race_event_id existente para que el dropdown
      // muestre la válida ya asociada cuando se edita una competition.
      race_event_id: initialData.race_event_id ?? null,
      audiences: (initialData.audiences ?? []) as CalendarEventFormValues["audiences"],
      ...specificFields,
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
    race_event_id: null,
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
    setValue,
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
  const isAllDay = useWatch({ control, name: "all_day" });
  const raceEventIdValue = useWatch({ control, name: "race_event_id" });

  useEffect(() => {
    if (initialData) {
      reset(buildDefaultValues(initialData));
    }
  }, [initialData, reset]);

  // FE-2: cuando el tipo deja de ser competition, descartamos la FK a
  // race_events para no enviar un id "huérfano" al backend (Pydantic lo
  // rechazaría con 422). En sentido inverso, el dropdown queda vacío
  // hasta que el coach elija.
  useEffect(() => {
    if (selectedType !== "competition" && raceEventIdValue != null) {
      setValue("race_event_id", null, { shouldDirty: true, shouldValidate: false });
    }
  }, [selectedType, raceEventIdValue, setValue]);

  // FE-2: temporada activa según la fecha de inicio del evento. El backend
  // exige `season` (year) y RaceSeries.season_year se alinea con el año
  // calendario. Cae al año actual si la fecha es inválida.
  const startDateValue = useWatch({ control, name: "start_date" });
  const seasonForRaceEvents = useMemo<number>(() => {
    if (typeof startDateValue === "string" && /^\d{4}-/.test(startDateValue)) {
      const y = Number(startDateValue.slice(0, 4));
      if (Number.isFinite(y)) return y;
    }
    return new Date().getFullYear();
  }, [startDateValue]);

  const isCompetition = selectedType === "competition";
  const raceEventsQuery = useAvailableRaceEvents(
    isCompetition ? seasonForRaceEvents : null,
  );

  // Si estamos editando un competition cuya válida YA está enlazada a este
  // mismo evento, la lista del endpoint (`available-for-calendar`) la
  // excluye. La añadimos manualmente para que el dropdown muestre el valor
  // actual y no aparezca como "vacío".
  const currentlyLinkedRaceEvent = useMemo(() => {
    if (!isCompetition) return null;
    const existingId = initialData?.race_event_id ?? null;
    if (existingId == null) return null;
    const inList = raceEventsQuery.data?.some((r) => r.id === existingId);
    if (inList) return null;
    return {
      id: existingId,
      name: `Válida #${existingId}`,
      event_date: initialData?.start_at?.slice(0, 10) ?? "",
      sequence_number: 0,
      location: null,
      series_id: 0,
    };
  }, [isCompetition, initialData, raceEventsQuery.data]);

  const raceEventOptions = useMemo(() => {
    const base = raceEventsQuery.data ?? [];
    if (currentlyLinkedRaceEvent) return [currentlyLinkedRaceEvent, ...base];
    return base;
  }, [raceEventsQuery.data, currentlyLinkedRaceEvent]);

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

  const hasSpecificErrors = !!(
    errors.data_competition ||
    errors.data_personal_training ||
    errors.data_group_training ||
    errors.data_training_session ||
    errors.data_club_event ||
    errors.data_rest_day ||
    // FE-2: el race_event_id vive a nivel raíz pero el coach lo edita en
    // la tab "Datos específicos" — su error debe marcar la pestaña.
    errors.race_event_id
  );

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
              className="relative flex-1 rounded-lg px-3 py-2 text-sm font-medium text-mid-gray transition-colors data-[state=active]:bg-white data-[state=active]:text-charcoal data-[state=active]:shadow-sm"
            >
              {tab.label}
              {tab.value === "specific" && hasSpecificErrors && (
                <span
                  aria-label="Esta sección tiene errores"
                  className="absolute right-2 top-2 h-2 w-2 rounded-full bg-red-500"
                />
              )}
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
              {!isAllDay && (
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
              )}
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
              <Controller
                name="color_hex"
                control={control}
                render={({ field }) => {
                  const hasColor =
                    typeof field.value === "string" &&
                    /^#[0-9a-fA-F]{6}$/.test(field.value) &&
                    field.value !== "#000000";
                  return (
                    <div className="space-y-2">
                      <label className="flex cursor-pointer items-center gap-2 text-sm text-charcoal">
                        <input
                          type="checkbox"
                          checked={hasColor}
                          onChange={(e) => {
                            field.onChange(e.target.checked ? "#3b82f6" : "");
                          }}
                          className="h-4 w-4 rounded border-mid-gray"
                        />
                        Color personalizado{" "}
                        <span className="font-normal text-mid-gray">(opcional)</span>
                      </label>
                      {hasColor && (
                        <div className="flex items-center gap-2">
                          <input
                            id="event-color"
                            type="color"
                            value={field.value as string}
                            onChange={(e) => field.onChange(e.target.value)}
                            className="h-9 w-16 cursor-pointer rounded-lg border-none bg-transparent p-1"
                            style={inputStyle}
                            aria-label="Seleccionar color del evento"
                          />
                          <span className="font-mono text-xs text-mid-gray">
                            {field.value as string}
                          </span>
                        </div>
                      )}
                    </div>
                  );
                }}
              />
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
        <TabsPrimitive.Content value="specific" className="mt-4" aria-label="Datos específicos">
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
                {/* FE-2: dropdown obligatorio que asocia este calendar_event
                    a una válida concreta de race_events. La lista viene del
                    endpoint /api/race-events/available-for-calendar y excluye
                    las válidas ya enlazadas a otro evento del calendario. */}
                <div>
                  <label htmlFor="comp-race-event" className={labelClass}>
                    Válida asociada
                  </label>
                  <Controller
                    name="race_event_id"
                    control={control}
                    render={({ field }) => (
                      <select
                        id="comp-race-event"
                        ref={field.ref}
                        name={field.name}
                        onBlur={field.onBlur}
                        value={
                          field.value == null
                            ? ""
                            : String(field.value)
                        }
                        onChange={(e) => {
                          const v = e.target.value;
                          field.onChange(v === "" ? null : Number(v));
                        }}
                        aria-invalid={!!errors.race_event_id}
                        aria-describedby={
                          errors.race_event_id
                            ? "comp-race-event-error"
                            : undefined
                        }
                        disabled={
                          raceEventsQuery.isLoading ||
                          (raceEventOptions.length === 0 &&
                            !raceEventsQuery.isError)
                        }
                        className={inputClass}
                        style={inputStyle}
                        data-testid="event-race-event-id"
                      >
                        <option value="">
                          {raceEventsQuery.isLoading
                            ? "Cargando válidas…"
                            : "Selecciona una válida…"}
                        </option>
                        {raceEventOptions.map((r) => (
                          <option key={r.id} value={String(r.id)}>
                            {r.sequence_number > 0
                              ? `Válida ${r.sequence_number} — ${r.name} (${r.event_date})`
                              : `${r.name}${r.event_date ? ` (${r.event_date})` : ""}`}
                          </option>
                        ))}
                      </select>
                    )}
                  />
                  {raceEventsQuery.isError && (
                    <p className={errorClass}>
                      No se pudo cargar la lista de válidas. Intenta de nuevo
                      en unos segundos.
                    </p>
                  )}
                  {!raceEventsQuery.isLoading &&
                    !raceEventsQuery.isError &&
                    raceEventOptions.length === 0 && (
                      <p
                        className="mt-1 text-xs text-mid-gray"
                        data-testid="event-race-event-empty"
                      >
                        No hay válidas disponibles para {seasonForRaceEvents}.
                        Crea una desde el{" "}
                        <RouterLink
                          to="/coach/race-analysis"
                          className="font-medium text-charcoal underline transition-opacity hover:opacity-70"
                        >
                          módulo de resultados
                        </RouterLink>
                        .
                      </p>
                    )}
                  {errors.race_event_id && (
                    <p id="comp-race-event-error" className={errorClass}>
                      {errors.race_event_id.message}
                    </p>
                  )}
                  {/* TODO(FE-3+): permitir crear una válida inline cuando el
                      coach está agendando una competencia sin PDF aún. */}
                </div>
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
