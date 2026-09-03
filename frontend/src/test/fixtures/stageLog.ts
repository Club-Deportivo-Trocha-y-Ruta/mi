/**
 * Fixtures de StageLog (bitácora), feature 038, T204.
 *
 * Todos los datos son 100% ficticios (privacidad de menores, CLAUDE.md):
 * ningún nombre real, sin peso/IMC/fecha de nacimiento en ningún campo.
 * `athlete_first_name` es siempre "Atleta Demo".
 */
import type { StageLog } from "@/types/stageLog.types";

/**
 * Mes completo: carrera disputada, foto e insignia, `analyst_reading`
 * presente (InsightV3 disponible ese mes).
 */
export function buildStageLogFullMonth(overrides?: Partial<StageLog>): StageLog {
  return {
    schema_version: 2,
    stage_number: 4,
    period_label: "Junio 2026",
    is_current_month: false,
    athlete_first_name: "Atleta Demo",
    athlete_reference: "su hija",
    stage_title: "Un mes de frenadas más firmes y una válida sólida",
    trail: [
      {
        kind: "first_session",
        date: "2026-03-02",
        label: "Primera sesión",
        sublabel: null,
        icon: "flag",
        is_future: false,
      },
      {
        kind: "streak",
        date: "2026-06-08",
        label: "Racha de 10",
        sublabel: null,
        icon: "flame",
        is_future: false,
      },
      {
        kind: "race",
        date: "2026-06-14",
        label: "Válida 4 · P2",
        sublabel: "+4,1 % al P1",
        icon: "map-pin",
        is_future: false,
      },
      {
        kind: "badge",
        date: "2026-06-20",
        label: "Asistencia 90 %",
        sublabel: null,
        icon: "award",
        is_future: false,
      },
      {
        kind: "next_race",
        date: "2026-08-01",
        label: "Válida 5 · Palmira",
        sublabel: null,
        icon: "compass",
        is_future: true,
      },
    ],
    summit: {
      kind: "race",
      title: "P2 en la Válida 4",
      detail: "Copa Valle · Prejuvenil A Femenino · +4,1 % al P1",
      caption: "Su mejor resultado de la temporada, con una frenada mucho más limpia en curva.",
      date: "2026-06-14",
    },
    observations: [
      {
        claim: "La asistencia se mantuvo alta durante todo el mes.",
        evidence: "9 de 10 sesiones planificadas (90 %)",
        block_ref: "attendance",
      },
      {
        claim: "La técnica de frenada en curva cerrada mostró avance consistente.",
        evidence: "calificación media de técnica 4,1/5 (vs 3,5 el mes pasado)",
        block_ref: "technical",
      },
      {
        claim: "El resultado de la válida confirmó el trabajo técnico del mes.",
        evidence: "P2 de 11, a 4,1 % del primer lugar",
        block_ref: "race",
      },
    ],
    analyst_reading: {
      headline_family: "La frenada en curva fue la clave del podio de este mes.",
      action_family: "Sostener 2 sesiones técnicas semanales de frenada progresiva.",
      valida_label: "Válida 4 · Copa Valle",
      source_insight_id: 2001,
    },
    effort_profile: [
      { week_label: "1–7 jun", sessions_planned: 3, sessions_attended: 3, mean_rpe: 6.2 },
      { week_label: "8–14 jun", sessions_planned: 3, sessions_attended: 2, mean_rpe: 7.0 },
      { week_label: "15–21 jun", sessions_planned: 2, sessions_attended: 2, mean_rpe: 5.5 },
      { week_label: "22–30 jun", sessions_planned: 2, sessions_attended: 2, mean_rpe: 6.0 },
    ],
    next_segment: {
      focus_groups: ["Frenada", "Curvas cerradas", "Resistencia base"],
      next_race: {
        label: "Válida 5",
        date: "2026-08-01",
        venue: "Palmira, Valle del Cauca",
        priority_label: "Prioridad B",
      },
      text: "Julio se enfoca en consolidar la frenada y sumar resistencia de base antes de la Válida 5.",
    },
    family_compass: {
      conversation_question: "¿Qué fue lo que más disfrutó de la carrera del sábado?",
      monthly_challenge: "Acompañar una sesión técnica y preguntar qué practicó ese día.",
      what_to_watch: "Cómo se siente con el ritmo en los tramos técnicos de bajada.",
    },
    badges: [
      { code: "attendance_90", label: "Asistencia 90 %", icon: "award", earned_at: "2026-06-20" },
      { code: "streak_10", label: "Racha de 10", icon: "flame", earned_at: "2026-06-08" },
    ],
    photos: [
      { thumbnail_url: "https://example.org/media/thumb-1.jpg", caption: "Sesión técnica del 8 de junio" },
      { thumbnail_url: "https://example.org/media/thumb-2.jpg", caption: "Válida 4 en Cali" },
    ],
    coach_note: "Gran mes, sobre todo por la constancia en las sesiones técnicas de los martes.",
    block_states: {
      stage_title: "ai",
      summit_caption: "ai",
      observations: "ai",
      analyst_reading: "ai",
      next_segment_text: "ai",
      family_compass: "ai",
    },
    grounding_violations: [],
    ...overrides,
  };
}

/**
 * Mes sin carrera: `summit` de tipo entrenamiento, sin `analyst_reading`
 * (no hubo InsightV3 ese mes porque no hubo válida).
 */
export function buildStageLogTrainingOnlyMonth(
  overrides?: Partial<StageLog>,
): StageLog {
  return {
    schema_version: 2,
    stage_number: 5,
    period_label: "Julio 2026",
    is_current_month: false,
    athlete_first_name: "Atleta Demo",
    athlete_reference: "su hijo",
    stage_title: "Un mes de base, sin carreras, construyendo resistencia",
    trail: [
      {
        kind: "first_session",
        date: "2026-03-02",
        label: "Primera sesión",
        sublabel: null,
        icon: "flag",
        is_future: false,
      },
      {
        kind: "streak",
        date: "2026-07-10",
        label: "Racha de 8",
        sublabel: null,
        icon: "flame",
        is_future: false,
      },
      {
        kind: "best_session",
        date: "2026-07-18",
        label: "Mejor sesión del mes",
        sublabel: "RPE 8/10 en fondo largo",
        icon: "star",
        is_future: false,
      },
      {
        kind: "next_race",
        date: "2026-08-01",
        label: "Válida 5 · Palmira",
        sublabel: null,
        icon: "compass",
        is_future: true,
      },
    ],
    summit: {
      kind: "training",
      title: "Mejor sesión de fondo del mes",
      detail: "Rodada larga de 2 h con RPE 8/10, sin quejas de fatiga",
      caption: "El mejor esfuerzo sostenido del mes, base sólida para la Válida 5.",
      date: "2026-07-18",
    },
    observations: [
      {
        claim: "La asistencia se sostuvo por encima del promedio del mes anterior.",
        evidence: "8 de 9 sesiones planificadas (89 %)",
        block_ref: "attendance",
      },
      {
        claim: "El volumen de rodadas largas aumentó respecto al mes anterior.",
        evidence: "3 sesiones de fondo ≥ 90 min (vs 1 en junio)",
        block_ref: "technical",
      },
      {
        claim: "La racha de asistencia se mantuvo activa durante todo el mes.",
        evidence: "racha de 8 sesiones consecutivas",
        block_ref: "streak",
      },
    ],
    analyst_reading: null,
    effort_profile: [
      { week_label: "1–7 jul", sessions_planned: 2, sessions_attended: 2, mean_rpe: 6.5 },
      { week_label: "8–14 jul", sessions_planned: 3, sessions_attended: 3, mean_rpe: 7.2 },
      { week_label: "15–21 jul", sessions_planned: 2, sessions_attended: 2, mean_rpe: 8.0 },
      { week_label: "22–31 jul", sessions_planned: 2, sessions_attended: 1, mean_rpe: 5.0 },
    ],
    next_segment: {
      focus_groups: ["Resistencia base", "Cadencia en subida"],
      next_race: {
        label: "Válida 5",
        date: "2026-08-01",
        venue: "Palmira, Valle del Cauca",
        priority_label: "Prioridad B",
      },
      text: "Agosto arranca con la Válida 5: la base construida en julio es el punto de partida.",
    },
    family_compass: {
      conversation_question: "¿Cómo se sintió en la rodada larga del sábado pasado?",
      monthly_challenge: "Preparar juntos la mochila de hidratación la noche antes de cada salida.",
      what_to_watch: "El nivel de energía en la semana previa a la Válida 5.",
    },
    badges: [
      { code: "streak_8", label: "Racha de 8", icon: "flame", earned_at: "2026-07-10" },
    ],
    photos: [],
    coach_note: null,
    block_states: {
      stage_title: "ai",
      summit_caption: "ai",
      observations: "ai",
      analyst_reading: "empty",
      next_segment_text: "ai",
      family_compass: "ai",
    },
    grounding_violations: [],
    ...overrides,
  };
}

/**
 * Mes con cero asistencia: sin `summit`, sin `analyst_reading`, sin
 * insignias ni fotos; observaciones estáticas (no narrativa AI, porque no
 * hay datos suficientes para generar una).
 */
export function buildStageLogZeroAttendanceMonth(
  overrides?: Partial<StageLog>,
): StageLog {
  return {
    schema_version: 2,
    stage_number: 6,
    period_label: "Agosto 2026",
    is_current_month: true,
    athlete_first_name: "Atleta Demo",
    athlete_reference: "su deportista",
    stage_title: "Un mes de pausa por lesión, sin sesiones registradas",
    trail: [
      {
        kind: "first_session",
        date: "2026-03-02",
        label: "Primera sesión",
        sublabel: null,
        icon: "flag",
        is_future: false,
      },
    ],
    summit: null,
    observations: [
      {
        claim: "No se registraron sesiones de entrenamiento durante el mes.",
        evidence: "0 de 8 sesiones planificadas (0 %)",
        block_ref: "attendance",
      },
    ],
    analyst_reading: null,
    effort_profile: [
      { week_label: "1–7 ago", sessions_planned: 2, sessions_attended: 0, mean_rpe: null },
      { week_label: "8–14 ago", sessions_planned: 2, sessions_attended: 0, mean_rpe: null },
      { week_label: "15–21 ago", sessions_planned: 2, sessions_attended: 0, mean_rpe: null },
      { week_label: "22–31 ago", sessions_planned: 2, sessions_attended: 0, mean_rpe: null },
    ],
    next_segment: null,
    family_compass: null,
    badges: [],
    photos: [],
    coach_note: "Sin novedades este mes; retomamos apenas el médico dé el visto bueno.",
    block_states: {
      stage_title: "static",
      summit_caption: "empty",
      observations: "static",
      analyst_reading: "empty",
      next_segment_text: "empty",
      family_compass: "empty",
    },
    grounding_violations: [],
    ...overrides,
  };
}
