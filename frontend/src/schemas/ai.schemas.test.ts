/**
 * Tests para la unión discriminada de `ai.schemas.ts` (feature 042, T064,
 * contracts/insight-schema.md §2, contracts/measurement-analysis-api.md §2):
 *   - Un payload SIN `schema_version` (fila legacy pre-042) se parsea como
 *     "v1" (default aplicado por `defaultRowSchemaVersion` antes de validar).
 *   - Un payload v2 se parsea con sus campos estructurados poblados.
 *   - Un payload v2 corrupto (estructura inválida en `structured`) falla el
 *     parseo de forma "capturable" (`safeParse`, sin excepción no atrapable)
 *     — de eso depende la degradación silenciosa de las tarjetas.
 *   - Los campos técnicos solo-coach (`prompt_version`, `trace_id`) son
 *     opcionales y están ausentes en un payload de familia.
 */
import { describe, expect, it } from "vitest";

import {
  anthropometricRecordExplanationResponseSchema,
  anthropometryInsightOutSchema,
  anthropometryInsightV1Schema,
  confidenceSchema,
  criticVerdictSchema,
  phvExplanationResponseSchema,
} from "@/schemas/ai.schemas";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const legacyV1Phv = {
  text: "En las últimas semanas se observó un crecimiento acorde a lo esperado para su edad.",
  model: "gemini-3.1-flash-lite",
  provider: "google",
  generated_at: "2026-06-02T14:03:00Z",
  age_group: "13-15",
  maturation_status: "Circa-PHV",
  // schema_version ausente a propósito: fila pre-042.
};

const structuredFixture = {
  summary_line: "Talla +1.0 cm en 14 semanas, dentro del rango esperado para su fase Circa-PHV.",
  changes: ["El cambio de talla supera el ruido instrumental y se mantiene en la fase Circa-PHV."],
  meaning: ["La velocidad estimada de 3.7 cm/año está por encima de lo típico para esta fase."],
  next_weeks: ["Esta fase es compatible con fuerza progresiva y mayor estructura de sesión."],
  warning_signs: [] as string[],
  confidence: { level: "high", reason: "Intervalo de 14 semanas consistente con la medición previa." },
  data_gaps: [] as string[],
};

const v2PhvCoach = {
  text: "En 14 semanas se registró un cambio de talla de +1.0 cm, dentro de lo esperable.",
  model: "gemini-3.8-flash",
  provider: "google",
  generated_at: "2026-09-10T11:56:00Z",
  age_group: "13-15",
  maturation_status: "Circa-PHV",
  schema_version: "v2",
  structured: structuredFixture,
  critic_verdict: "approved",
  is_fallback: false,
  prompt_version: "anthropometry_analyst_v1",
  trace_id: "a1b2c3d4e5f60718",
};

const v2PhvFamily = {
  text: v2PhvCoach.text,
  model: v2PhvCoach.model,
  provider: v2PhvCoach.provider,
  generated_at: v2PhvCoach.generated_at,
  age_group: v2PhvCoach.age_group,
  maturation_status: v2PhvCoach.maturation_status,
  schema_version: "v2",
  structured: structuredFixture,
  critic_verdict: "approved",
  is_fallback: false,
  // Un padre nunca recibe estos dos campos — la API los omite/null, nunca
  // los rellena — measurement-analysis-api.md §4.
};

const recordExtras = {
  record_id: 4900,
  num_previous_measurements: 3,
  delta_height_cm: 1.0,
  delta_weight_kg: 0.0,
};

// ---------------------------------------------------------------------------
// anthropometryInsightV1Schema / anthropometryInsightOutSchema (payload interno)
// ---------------------------------------------------------------------------

describe("anthropometryInsightV1Schema", () => {
  it("acepta un payload válido con schema_version explícito 'v1'", () => {
    const result = anthropometryInsightV1Schema.safeParse({
      schema_version: "v1",
      audience: "family",
      word_count: 42,
      ...structuredFixture,
    });
    expect(result.success).toBe(true);
  });

  it("rechaza un audience desconocido", () => {
    const result = anthropometryInsightV1Schema.safeParse({
      schema_version: "v1",
      audience: "vecino",
      word_count: 42,
      ...structuredFixture,
    });
    expect(result.success).toBe(false);
  });
});

describe("anthropometryInsightOutSchema", () => {
  it("acepta el subconjunto sin schema_version/audience/word_count", () => {
    const result = anthropometryInsightOutSchema.safeParse(structuredFixture);
    expect(result.success).toBe(true);
  });

  it("respeta la cardinalidad de 'changes' (mínimo 1, máximo 4)", () => {
    expect(
      anthropometryInsightOutSchema.safeParse({ ...structuredFixture, changes: [] })
        .success,
    ).toBe(false);
    expect(
      anthropometryInsightOutSchema.safeParse({
        ...structuredFixture,
        changes: ["a", "b", "c", "d", "e"],
      }).success,
    ).toBe(false);
  });
});

describe("confidenceSchema", () => {
  it("rechaza un nivel de confianza fuera de high|medium|low", () => {
    const result = confidenceSchema.safeParse({ level: "extreme", reason: "algo" });
    expect(result.success).toBe(false);
  });
});

describe("criticVerdictSchema", () => {
  it("acepta los cinco valores persistidos", () => {
    for (const verdict of ["approved", "revised", "flagged", "fallback", "skipped"]) {
      expect(criticVerdictSchema.safeParse(verdict).success).toBe(true);
    }
  });

  it("rechaza el vocabulario crudo del crítico interno (approve/revise/reject)", () => {
    // El frontend nunca recibe este vocabulario de 3 valores — solo el
    // persistido de 5 (insight-schema.md §2).
    expect(criticVerdictSchema.safeParse("approve").success).toBe(false);
    expect(criticVerdictSchema.safeParse("reject").success).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// phvExplanationResponseSchema — unión discriminada v1 | v2
// ---------------------------------------------------------------------------

describe("phvExplanationResponseSchema — default a v1 cuando falta schema_version", () => {
  it("una fila legacy sin schema_version se parsea como v1", () => {
    const result = phvExplanationResponseSchema.safeParse(legacyV1Phv);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.schema_version).toBe("v1");
      expect(result.data.structured).toBeUndefined();
      expect(result.data.critic_verdict).toBeUndefined();
    }
  });

  it("una fila con schema_version: null también se normaliza a v1", () => {
    const result = phvExplanationResponseSchema.safeParse({
      ...legacyV1Phv,
      schema_version: null,
      structured: null,
      critic_verdict: null,
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.schema_version).toBe("v1");
    }
  });

  it("no toca un schema_version ya poblado explícitamente en 'v1'", () => {
    const result = phvExplanationResponseSchema.safeParse({
      ...legacyV1Phv,
      schema_version: "v1",
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.schema_version).toBe("v1");
    }
  });
});

describe("phvExplanationResponseSchema — rama v2", () => {
  it("parsea un payload v2 con sus campos estructurados poblados", () => {
    const result = phvExplanationResponseSchema.safeParse(v2PhvCoach);
    expect(result.success).toBe(true);
    if (result.success && result.data.schema_version === "v2") {
      expect(result.data.structured.summary_line).toBe(structuredFixture.summary_line);
      expect(result.data.structured.changes).toEqual(structuredFixture.changes);
      expect(result.data.critic_verdict).toBe("approved");
      expect(result.data.prompt_version).toBe("anthropometry_analyst_v1");
      expect(result.data.trace_id).toBe("a1b2c3d4e5f60718");
    } else {
      throw new Error("se esperaba una rama v2 exitosa");
    }
  });

  it("los campos técnicos solo-coach son opcionales y están ausentes en un payload de familia", () => {
    const result = phvExplanationResponseSchema.safeParse(v2PhvFamily);
    expect(result.success).toBe(true);
    if (result.success && result.data.schema_version === "v2") {
      expect(result.data.prompt_version).toBeUndefined();
      expect(result.data.trace_id).toBeUndefined();
      // Pero el contenido estructurado sí llega completo — la familia lee
      // el mismo análisis, solo sin la procedencia técnica.
      expect(result.data.structured.summary_line).toBe(structuredFixture.summary_line);
    } else {
      throw new Error("se esperaba una rama v2 exitosa");
    }
  });

  it("un payload v2 con `structured` corrupto (falta casi todo) falla el parseo de forma capturable", () => {
    const corrupt = {
      ...v2PhvCoach,
      structured: { summary_line: "x" },
    };
    const result = phvExplanationResponseSchema.safeParse(corrupt);
    expect(result.success).toBe(false);
    // safeParse nunca lanza — el caller (la tarjeta) puede degradar sin
    // reventar el error boundary.
    if (!result.success) {
      expect(result.error).toBeDefined();
    }
  });

  it("un payload v2 sin `structured` (null, forma de v1) falla el parseo — v2 exige structured poblado", () => {
    const result = phvExplanationResponseSchema.safeParse({
      ...v2PhvCoach,
      structured: null,
    });
    expect(result.success).toBe(false);
  });

  it("un critic_verdict fuera del vocabulario persistido falla el parseo", () => {
    const result = phvExplanationResponseSchema.safeParse({
      ...v2PhvCoach,
      critic_verdict: "approve", // vocabulario crudo del crítico, no el persistido
    });
    expect(result.success).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// anthropometricRecordExplanationResponseSchema — mismo contrato + deltas
// ---------------------------------------------------------------------------

describe("anthropometricRecordExplanationResponseSchema", () => {
  it("una fila legacy (sin schema_version) con los campos de delta se parsea como v1", () => {
    const result = anthropometricRecordExplanationResponseSchema.safeParse({
      ...legacyV1Phv,
      ...recordExtras,
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.schema_version).toBe("v1");
      expect(result.data.record_id).toBe(recordExtras.record_id);
    }
  });

  it("parsea una fila v2 con structured poblado y los campos de delta", () => {
    const result = anthropometricRecordExplanationResponseSchema.safeParse({
      ...v2PhvCoach,
      ...recordExtras,
    });
    expect(result.success).toBe(true);
    if (result.success && result.data.schema_version === "v2") {
      expect(result.data.structured.confidence.level).toBe("high");
      expect(result.data.delta_height_cm).toBe(1.0);
    } else {
      throw new Error("se esperaba una rama v2 exitosa");
    }
  });

  it("acepta delta_height_cm/delta_weight_kg en null (primera medición)", () => {
    const result = anthropometricRecordExplanationResponseSchema.safeParse({
      ...legacyV1Phv,
      record_id: 1,
      num_previous_measurements: 0,
      delta_height_cm: null,
      delta_weight_kg: null,
    });
    expect(result.success).toBe(true);
  });

  it("un `structured` corrupto en la rama v2 del endpoint de medición también falla el parseo de forma capturable", () => {
    const result = anthropometricRecordExplanationResponseSchema.safeParse({
      ...v2PhvCoach,
      ...recordExtras,
      structured: { summary_line: "x" },
    });
    expect(result.success).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Defensa en profundidad: campos no declarados (PII incluida) se descartan.
// ---------------------------------------------------------------------------

describe("descarte de campos no declarados (defensa en profundidad)", () => {
  it("un campo extra desconocido en el payload de nivel superior se descarta silenciosamente (.strip())", () => {
    const result = phvExplanationResponseSchema.safeParse({
      ...legacyV1Phv,
      first_name: "no-debería-viajar",
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data).not.toHaveProperty("first_name");
    }
  });
});
