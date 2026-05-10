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
      .regex(/^\d{2}:\d{2}$/, "Formato HH:MM requerido"),
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

    // Specific data — only one is used at a time depending on event_type
    data_training_session: eventDataTrainingSessionSchema.optional(),
    data_competition: eventDataCompetitionSchema.optional(),
    data_club_event: eventDataClubEventSchema.optional(),
    data_personal_training: eventDataPersonalTrainingSchema.optional(),
    data_group_training: eventDataGroupTrainingSchema.optional(),
    data_rest_day: eventDataRestDaySchema.optional(),
  })
  .superRefine((val, ctx) => {
    // Cross-field: end > start (derived from start_date + start_time + duration_min)
    if (val.start_date && val.start_time) {
      const start = new Date(`${val.start_date}T${val.start_time}:00`);
      if (isNaN(start.getTime())) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Fecha u hora de inicio inválida",
          path: ["start_date"],
        });
        return;
      }
      const end = new Date(start.getTime() + val.duration_min * 60_000);
      if (end <= start) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "La hora de fin debe ser posterior al inicio",
          path: ["duration_min"],
        });
      }
    }
  });

export type CalendarEventFormValues = z.output<typeof calendarEventSchema>;

// ─── Helpers to build API payload from form values ───────────────────────────

export function buildEventPayload(values: CalendarEventFormValues) {
  const start = new Date(`${values.start_date}T${values.start_time}:00`);
  const end = new Date(start.getTime() + values.duration_min * 60_000);

  const eventDataMap: Record<string, unknown> = {
    training_session: values.data_training_session ?? {},
    competition: values.data_competition,
    club_event: values.data_club_event,
    personal_training: values.data_personal_training,
    group_training: values.data_group_training,
    rest_day: values.data_rest_day,
  };

  return {
    event_type: values.event_type,
    title: values.title,
    description: values.description || undefined,
    location: values.location || undefined,
    start_at: start.toISOString(),
    end_at: end.toISOString(),
    all_day: values.all_day,
    color_hex: values.color_hex || undefined,
    event_data: eventDataMap[values.event_type] ?? {},
    audiences: values.audiences,
  };
}
