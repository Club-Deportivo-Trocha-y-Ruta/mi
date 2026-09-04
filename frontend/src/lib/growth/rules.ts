/**
 * Tabla única de reglas de entrenamiento por edad/etapa (feature 040, US2).
 *
 * Reemplaza la lógica de `buildRules()` que vivía embebida en
 * `components/athletes/TrainingReadiness.tsx` (T040 la refactoriza para
 * consumir este módulo) — mismos nueve criterios, mismos textos, sin el
 * estimado numérico de frecuencia cardíaca máxima (ya retirado en T008; D4
 * de `docs/18-growth-module-redesign/proposal.md`).
 *
 * Diseño (`data-model.md` §5): `TRAINING_RULES` es una tabla plana keyed por
 * `(id, ageGroup, stage)`. Cada `id` tiene siempre una fila `stage: "any"`
 * por grupo de edad (el default); solo se agrega una fila `stage: "Circa-PHV"`
 * cuando el comportamiento en esa etapa difiere del default — Pre-PHV y
 * Post-PHV se comportan igual que "any" en el modelo original, así que no
 * necesitan filas propias. `rulesFor` resuelve la fila aplicable con
 * fallback a "any"; `differsFromDefault` compara contra ese default.
 */

// ---------------------------------------------------------------------------
// Tipos públicos
// ---------------------------------------------------------------------------

export type AgeGroup = "10-12" | "13-15";
export type Stage = "Pre-PHV" | "Circa-PHV" | "Post-PHV" | "any";
export type RuleStatus = "allowed" | "caution" | "forbidden";

export type TrainingRuleId =
  | "high_intensity"
  | "bodyweight_strength"
  | "external_load"
  | "weekly_hours"
  | "cadence"
  | "max_hr_test"
  | "powermeter"
  | "intensity_distribution"
  | "train_race_ratio";

export interface TrainingRule {
  id: TrainingRuleId;
  /** Etiqueta corta mostrada como título del chip/fila. */
  topic: string;
  ageGroup: AgeGroup;
  stage: Stage;
  status: RuleStatus;
  /** Texto en español neutro, sin cifras estimadas de frecuencia cardíaca. */
  text: string;
}

/** Orden canónico de los nueve criterios — usado por `rulesFor` para una salida estable. */
const RULE_IDS: readonly TrainingRuleId[] = [
  "high_intensity",
  "bodyweight_strength",
  "external_load",
  "weekly_hours",
  "cadence",
  "max_hr_test",
  "powermeter",
  "intensity_distribution",
  "train_race_ratio",
];

const TOPICS: Record<TrainingRuleId, string> = {
  high_intensity: "Intervalos alta intensidad",
  bodyweight_strength: "Fuerza peso corporal",
  external_load: "Fuerza peso externo",
  weekly_hours: "Horas/semana",
  cadence: "Cadencia mínima",
  max_hr_test: "Test FC máxima",
  powermeter: "Potenciómetro",
  intensity_distribution: "Distribución Z1-Z2 / Z3-Z5",
  train_race_ratio: "Ratio entreno:competencia",
};

// ---------------------------------------------------------------------------
// TRAINING_RULES — portado de TrainingReadiness.tsx::buildRules
// ---------------------------------------------------------------------------

export const TRAINING_RULES: readonly TrainingRule[] = [
  // ── high_intensity ────────────────────────────────────────────────────
  {
    id: "high_intensity",
    topic: TOPICS.high_intensity,
    ageGroup: "10-12",
    stage: "any",
    status: "forbidden",
    text: "Prohibido en 10-12 años — solo juego libre",
  },
  {
    id: "high_intensity",
    topic: TOPICS.high_intensity,
    ageGroup: "13-15",
    stage: "any",
    status: "caution",
    text: "Max 2 sesiones/semana",
  },
  {
    id: "high_intensity",
    topic: TOPICS.high_intensity,
    ageGroup: "10-12",
    stage: "Circa-PHV",
    status: "forbidden",
    text: "Prohibido en Circa-PHV",
  },
  {
    id: "high_intensity",
    topic: TOPICS.high_intensity,
    ageGroup: "13-15",
    stage: "Circa-PHV",
    status: "forbidden",
    text: "Prohibido en Circa-PHV",
  },

  // ── bodyweight_strength ───────────────────────────────────────────────
  {
    id: "bodyweight_strength",
    topic: TOPICS.bodyweight_strength,
    ageGroup: "10-12",
    stage: "any",
    status: "allowed",
    text: "Permitido en todos los grupos",
  },
  {
    id: "bodyweight_strength",
    topic: TOPICS.bodyweight_strength,
    ageGroup: "13-15",
    stage: "any",
    status: "allowed",
    text: "Permitido en todos los grupos",
  },
  {
    id: "bodyweight_strength",
    topic: TOPICS.bodyweight_strength,
    ageGroup: "10-12",
    stage: "Circa-PHV",
    status: "caution",
    text: "Volumen reducido — Circa-PHV",
  },
  {
    id: "bodyweight_strength",
    topic: TOPICS.bodyweight_strength,
    ageGroup: "13-15",
    stage: "Circa-PHV",
    status: "caution",
    text: "Volumen reducido — Circa-PHV",
  },

  // ── external_load ─────────────────────────────────────────────────────
  {
    id: "external_load",
    topic: TOPICS.external_load,
    ageGroup: "10-12",
    stage: "any",
    status: "forbidden",
    text: "Prohibido en 10-12 años",
  },
  {
    id: "external_load",
    topic: TOPICS.external_load,
    ageGroup: "13-15",
    stage: "any",
    status: "caution",
    text: "Progresión: bandas → mancuernas",
  },
  {
    id: "external_load",
    topic: TOPICS.external_load,
    ageGroup: "10-12",
    stage: "Circa-PHV",
    status: "forbidden",
    text: "Prohibido en Circa-PHV",
  },
  {
    id: "external_load",
    topic: TOPICS.external_load,
    ageGroup: "13-15",
    stage: "Circa-PHV",
    status: "forbidden",
    text: "Prohibido en Circa-PHV",
  },

  // ── weekly_hours ──────────────────────────────────────────────────────
  {
    id: "weekly_hours",
    topic: TOPICS.weekly_hours,
    ageGroup: "10-12",
    stage: "any",
    status: "allowed",
    text: "3-5 h/semana (edad mínima regla)",
  },
  {
    id: "weekly_hours",
    topic: TOPICS.weekly_hours,
    ageGroup: "13-15",
    stage: "any",
    status: "allowed",
    text: "5-10 h/semana",
  },
  {
    id: "weekly_hours",
    topic: TOPICS.weekly_hours,
    ageGroup: "10-12",
    stage: "Circa-PHV",
    status: "caution",
    text: "Reducir 20-30% del plan habitual",
  },
  {
    id: "weekly_hours",
    topic: TOPICS.weekly_hours,
    ageGroup: "13-15",
    stage: "Circa-PHV",
    status: "caution",
    text: "Reducir 20-30% del plan habitual",
  },

  // ── cadence ───────────────────────────────────────────────────────────
  {
    id: "cadence",
    topic: TOPICS.cadence,
    ageGroup: "10-12",
    stage: "any",
    status: "allowed",
    text: "70 rpm — nunca < 60 rpm",
  },
  {
    id: "cadence",
    topic: TOPICS.cadence,
    ageGroup: "13-15",
    stage: "any",
    status: "allowed",
    text: "75 rpm — nunca < 60 rpm",
  },
  {
    id: "cadence",
    topic: TOPICS.cadence,
    ageGroup: "10-12",
    stage: "Circa-PHV",
    status: "allowed",
    text: "75 rpm — nunca < 60 rpm",
  },
  // 13-15/Circa-PHV: sin fila — igual al default 13-15/any (75 rpm).

  // ── max_hr_test ───────────────────────────────────────────────────────
  {
    id: "max_hr_test",
    topic: TOPICS.max_hr_test,
    ageGroup: "10-12",
    stage: "any",
    status: "forbidden",
    text: "Sin test de FC máxima — no se estima ni se usa para zonas",
  },
  {
    id: "max_hr_test",
    topic: TOPICS.max_hr_test,
    ageGroup: "13-15",
    stage: "any",
    status: "allowed",
    text: "Permitido con supervisión",
  },
  // 10-12/Circa-PHV: sin fila — ya es forbidden por edad, igual al default.
  {
    id: "max_hr_test",
    topic: TOPICS.max_hr_test,
    ageGroup: "13-15",
    stage: "Circa-PHV",
    status: "forbidden",
    text: "Sin test de FC máxima — no se estima ni se usa para zonas",
  },

  // ── powermeter ────────────────────────────────────────────────────────
  {
    id: "powermeter",
    topic: TOPICS.powermeter,
    ageGroup: "10-12",
    stage: "any",
    status: "forbidden",
    text: "Prohibido en menores de 13 años",
  },
  {
    id: "powermeter",
    topic: TOPICS.powermeter,
    ageGroup: "13-15",
    stage: "any",
    status: "allowed",
    text: "Permitido (solo > 13 años)",
  },
  {
    id: "powermeter",
    topic: TOPICS.powermeter,
    ageGroup: "10-12",
    stage: "Circa-PHV",
    status: "forbidden",
    text: "Prohibido en Circa-PHV",
  },
  {
    id: "powermeter",
    topic: TOPICS.powermeter,
    ageGroup: "13-15",
    stage: "Circa-PHV",
    status: "forbidden",
    text: "Prohibido en Circa-PHV",
  },

  // ── intensity_distribution ────────────────────────────────────────────
  {
    id: "intensity_distribution",
    topic: TOPICS.intensity_distribution,
    ageGroup: "10-12",
    stage: "any",
    status: "allowed",
    text: "90% / 10%",
  },
  {
    id: "intensity_distribution",
    topic: TOPICS.intensity_distribution,
    ageGroup: "13-15",
    stage: "any",
    status: "allowed",
    text: "80% / 20%",
  },
  // 10-12/Circa-PHV: sin fila — ya es 90/10 por edad, igual al default.
  {
    id: "intensity_distribution",
    topic: TOPICS.intensity_distribution,
    ageGroup: "13-15",
    stage: "Circa-PHV",
    status: "allowed",
    text: "90% / 10%",
  },

  // ── train_race_ratio ──────────────────────────────────────────────────
  {
    id: "train_race_ratio",
    topic: TOPICS.train_race_ratio,
    ageGroup: "10-12",
    stage: "any",
    status: "allowed",
    text: "70 : 30",
  },
  {
    id: "train_race_ratio",
    topic: TOPICS.train_race_ratio,
    ageGroup: "13-15",
    stage: "any",
    status: "allowed",
    text: "60 : 40",
  },
  // 10-12/Circa-PHV: sin fila — ya es 70:30 por edad, igual al default.
  {
    id: "train_race_ratio",
    topic: TOPICS.train_race_ratio,
    ageGroup: "13-15",
    stage: "Circa-PHV",
    status: "allowed",
    text: "70 : 30",
  },
];

// ---------------------------------------------------------------------------
// rulesFor / differsFromDefault
// ---------------------------------------------------------------------------

/**
 * Resuelve exactamente una regla por cada uno de los nueve `id`, para el
 * grupo de edad y la etapa dados. Si no existe una fila específica de
 * `stage` (p. ej. Pre-PHV/Post-PHV, que no tienen excepciones), cae al
 * default `stage: "any"` del mismo grupo de edad.
 */
export function rulesFor(ageGroup: AgeGroup, stage: Stage): TrainingRule[] {
  return RULE_IDS.map((id) => {
    const rowsForId = TRAINING_RULES.filter(
      (rule) => rule.id === id && rule.ageGroup === ageGroup,
    );
    const exact = rowsForId.find((rule) => rule.stage === stage);
    if (exact) return exact;
    const fallback = rowsForId.find((rule) => rule.stage === "any");
    if (!fallback) {
      throw new Error(
        `TRAINING_RULES: falta la fila "any" para "${id}" en el grupo ${ageGroup}`,
      );
    }
    return fallback;
  });
}

/**
 * `true` cuando `rule` (status o texto) difiere de la fila default
 * `(rule.id, rule.ageGroup, "any")`. La propia fila default nunca difiere de
 * sí misma.
 */
export function differsFromDefault(rule: TrainingRule): boolean {
  if (rule.stage === "any") return false;
  const defaultRule = TRAINING_RULES.find(
    (candidate) =>
      candidate.id === rule.id &&
      candidate.ageGroup === rule.ageGroup &&
      candidate.stage === "any",
  );
  if (!defaultRule) return false;
  return rule.status !== defaultRule.status || rule.text !== defaultRule.text;
}
