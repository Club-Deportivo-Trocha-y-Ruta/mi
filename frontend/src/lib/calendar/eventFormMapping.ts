/**
 * Helpers para mapear `CalendarEventRead` ↔ `CalendarEventFormValues`.
 *
 * Funciones puras extraídas de `EventForm.tsx` en B5:
 *   - `buildSpecificFields` — recoge el bloque `data_*` correcto según event_type.
 *   - `buildDefaultValues`   — produce los defaultValues completos para useForm.
 *
 * Mantener la lógica fuera del componente permite testearla sin montar
 * el árbol RHF y reduce el LOC del archivo de página.
 */
import type {
  CalendarEventRead,
  EventDataClubEvent,
  EventDataCompetition,
  EventDataGroupTraining,
  EventDataPersonalTraining,
  EventDataRestDay,
  EventDataTrainingSession,
} from "@/types/calendar.types";
import type { CalendarEventFormValues } from "@/schemas/calendar.schema";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function buildSpecificFields(
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

export function buildDefaultValues(
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
