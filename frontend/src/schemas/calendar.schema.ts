import { z } from "zod";

// ─── Audience sub-schemas ────────────────────────────────────────────────────

const audienceAllClubSchema = z.object({
  audience_type: z.literal("all_club"),
  audience_value: z.object({}).optional().default({}),
});

const audienceCategorySchema = z.object({
  audience_type: z.literal("category"),
  audience_value: z.object({
    category: z.string().min(1, "Selecciona una categoría"),
  }),
});

const audienceAthleteListSchema = z.object({
  audience_type: z.literal("athlete_list"),
  audience_value: z.object({
    athlete_ids: z.array(z.number()).min(1, "Selecciona al menos un atleta"),
  }),
});

const audienceIndividualSchema = z.object({
  audience_type: z.literal("individual"),
  audience_value: z.object({
    athlete_id: z.number({ error: "Selecciona un atleta" }),
  }),
});

const audienceSchema = z.discriminatedUnion("audience_type", [
  audienceAllClubSchema,
  audienceCategorySchema,
  audienceAthleteListSchema,
  audienceIndividualSchema,
]);

// ─── EventData sub-schemas ───────────────────────────────────────────────────

const eventDataTrainingSessionSchema = z.object({
  training_session_id: z.number().optional(),
});

const eventDataCompetitionSchema = z.object({
  city: z.string().min(1, "La ciudad es requerida").max(100, "Máximo 100 caracteres"),
  race_category: z.enum(["A", "B", "C"]).optional().default("A"),
  is_departmental: z.boolean().default(false),
});

const eventDataClubEventSchema = z.object({
  kind: z.enum(["social", "meeting", "workshop"]).optional().default("social"),
  registration_url: z.string().url("URL no válida").optional().or(z.literal("")),
});

const eventDataPersonalTrainingSchema = z.object({
  athlete_id: z.number({ error: "Selecciona el atleta" }).optional(),
  intensity: z.enum(["low", "medium", "high"]).optional().default("medium"),
});

const eventDataGroupTrainingSchema = z.object({
  intensity: z.enum(["low", "medium", "high"]).optional().default("medium"),
  group_size_max: z
    .number()
    .int()
    .min(1, "Mínimo 1 atleta")
    .max(50, "Máximo 50 atletas")
    .optional(),
});

const eventDataRestDaySchema = z.object({
  scope: z.enum(["club", "category", "athlete"]).optional().default("club"),
  reason: z.string().max(200, "Máximo 200 caracteres").optional().or(z.literal("")),
});

// ─── Main form schema ─────────────────────────────────────────────────────────

export const calendarEventSchema = z
  .object({
    event_type: z.enum(
      [
        "training_session",
        "competition",
        "club_event",
        "personal_training",
        "group_training",
        "rest_day",
      ],
      { error: "Selecciona el tipo de evento" },
    ),
    title: z
      .string()
      .min(1, "El título es requerido")
      .max(200, "Máximo 200 caracteres"),
    description: z
      .string()
      .max(2000, "Máximo 2000 caracteres")
      .optional()
      .or(z.literal("")),
    location: z
      .string()
      .max(200, "Máximo 200 caracteres")
      .optional()
      .or(z.literal("")),
    start_date: z.string().min(1, "La fecha de inicio es requerida"),
    start_time: z
      .string()
      .regex(/^\d{2}:\d{2}$/, "Formato HH:MM requerido")
      .optional()
      .default("00:00"),
    duration_min: z
      .number()
      .int()
      .min(1, "Mínimo 1 minuto")
      .max(1440, "Máximo 1440 minutos (24 h)"),
    all_day: z.boolean().default(false),
    color_hex: z
      .string()
      .regex(/^#[0-9a-fA-F]{6}$/, "Color inválido")
      .optional()
      .or(z.literal("")),
    audiences: z
      .array(audienceSchema)
      .min(1, "Define al menos una audiencia"),

    // FE-2: FK a race_events.id — obligatorio sólo si event_type=competition.
    // El refine de abajo emite el error si se omite cuando aplica, y limpia
    // el valor para los demás tipos.
    race_event_id: z
      .number()
      .int()
      .positive()
      .nullable()
      .optional(),

    // Specific data — only one is used at a time depending on event_type
    data_training_session: eventDataTrainingSessionSchema.optional(),
    data_competition: eventDataCompetitionSchema.optional(),
    data_club_event: eventDataClubEventSchema.optional(),
    data_personal_training: eventDataPersonalTrainingSchema.optional(),
    data_group_training: eventDataGroupTrainingSchema.optional(),
    data_rest_day: eventDataRestDaySchema.optional(),
  })
  .superRefine((val, ctx) => {
    // start_time is required and must match HH:MM when all_day is false
    if (!val.all_day) {
      if (!val.start_time || !/^\d{2}:\d{2}$/.test(val.start_time)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Formato HH:MM requerido",
          path: ["start_time"],
        });
        return;
      }
    }

    // Cross-field: end > start (derived from start_date + start_time + duration_min)
    const timeToUse = val.all_day ? "00:00" : (val.start_time ?? "00:00");
    if (val.start_date && timeToUse) {
      const start = new Date(`${val.start_date}T${timeToUse}:00`);
      if (isNaN(start.getTime())) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Fecha u hora de inicio inválida",
          path: ["start_date"],
        });
        return;
      }
      const end = val.all_day
        ? new Date(`${val.start_date}T23:59:59`)
        : new Date(start.getTime() + val.duration_min * 60_000);
      if (end <= start) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "La hora de fin debe ser posterior al inicio",
          path: ["duration_min"],
        });
      }
    }

    // Cuando event_type es "competition", city es requerido
    if (val.event_type === "competition") {
      if (!val.data_competition?.city || val.data_competition.city.trim() === "") {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "La ciudad es requerida para una competencia",
          path: ["data_competition", "city"],
        });
      }
      // FE-2: para competition, race_event_id apunta a la válida (mirror
      // del validator Pydantic en `EventCreate._validate_competition_race_event`).
      if (val.race_event_id == null) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Selecciona la válida asociada a esta competencia",
          path: ["race_event_id"],
        });
      }
    }

    // Si hay personal_training type, athlete_id requerido
    if (val.event_type === "personal_training") {
      if (!val.data_personal_training?.athlete_id) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Selecciona el atleta para entrenamiento personal",
          path: ["data_personal_training", "athlete_id"],
        });
      }
    }
  });

export type CalendarEventFormValues = z.output<typeof calendarEventSchema>;

// ─── Helpers to build API payload from form values ───────────────────────────

export function buildEventPayload(values: CalendarEventFormValues) {
  // start_at / end_at se envían como strings ISO.
  let startAt: string;
  let endAt: string;
  if (values.all_day) {
    // all_day: límites de día como datetimes naive en hora local
    // (00:00:00 / 23:59:59 del start_date), SIN convertir a UTC. El backend
    // almacena timestamps naive interpretados como America/Bogota, y la ruta
    // "one-click" (create_linked_calendar_event) produce exactamente estos
    // mismos valores. Usar toISOString() aquí desplazaría la hora (y el día)
    // según la zona del navegador, divergiendo de esa ruta.
    startAt = `${values.start_date}T00:00:00`;
    endAt = `${values.start_date}T23:59:59`;
  } else {
    const timeToUse = values.start_time ?? "00:00";
    const start = new Date(`${values.start_date}T${timeToUse}:00`);
    const end = new Date(start.getTime() + values.duration_min * 60_000);
    startAt = start.toISOString();
    endAt = end.toISOString();
  }

  const eventDataMap: Record<string, unknown> = {
    training_session: values.data_training_session ?? {},
    competition: values.data_competition,
    club_event: values.data_club_event,
    personal_training: values.data_personal_training,
    group_training: values.data_group_training,
    rest_day: values.data_rest_day,
  };

  // FE-2: race_event_id sólo aplica a competition. Para los demás tipos
  // forzamos null (no `undefined`) para que un edit que cambie de
  // competition → otro tipo limpie la FK en el backend.
  const raceEventId =
    values.event_type === "competition"
      ? (values.race_event_id ?? null)
      : null;

  return {
    event_type: values.event_type,
    title: values.title,
    description: values.description || undefined,
    location: values.location || undefined,
    start_at: startAt,
    end_at: endAt,
    all_day: values.all_day,
    color_hex: values.color_hex || undefined,
    event_data: eventDataMap[values.event_type] ?? {},
    race_event_id: raceEventId,
    audiences: values.audiences,
  };
}
