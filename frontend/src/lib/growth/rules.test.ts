import { describe, expect, it } from "vitest";

import {
  differsFromDefault,
  rulesFor,
  TRAINING_RULES,
  type TrainingRuleId,
} from "@/lib/growth/rules";

const ALL_IDS: TrainingRuleId[] = [
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

describe("TRAINING_RULES", () => {
  it("no contiene ningún estimado numérico de frecuencia cardíaca (D4 / T008)", () => {
    for (const rule of TRAINING_RULES) {
      expect(rule.text).not.toMatch(/\d+\s*(lpm|bpm)/i);
    }
  });

  it("cada id tiene al menos la fila default (stage: any) para los dos grupos de edad", () => {
    for (const id of ALL_IDS) {
      for (const ageGroup of ["10-12", "13-15"] as const) {
        const hasDefault = TRAINING_RULES.some(
          (r) => r.id === id && r.ageGroup === ageGroup && r.stage === "any",
        );
        expect(hasDefault).toBe(true);
      }
    }
  });
});

describe("rulesFor", () => {
  it("devuelve exactamente una regla por cada uno de los nueve criterios", () => {
    const rules = rulesFor("10-12", "any");
    expect(rules).toHaveLength(9);
    expect(new Set(rules.map((r) => r.id)).size).toBe(9);
  });

  it("mantiene el orden canónico de los nueve ids", () => {
    const rules = rulesFor("13-15", "any");
    expect(rules.map((r) => r.id)).toEqual(ALL_IDS);
  });

  describe("grupo 10-12 años, sin fase Circa-PHV", () => {
    const rules = rulesFor("10-12", "Pre-PHV");
    const byId = Object.fromEntries(rules.map((r) => [r.id, r]));

    it("prohíbe alta intensidad (solo juego libre)", () => {
      expect(byId.high_intensity.status).toBe("forbidden");
      expect(byId.high_intensity.text).toContain("solo juego libre");
    });

    it("permite fuerza peso corporal sin restricción", () => {
      expect(byId.bodyweight_strength.status).toBe("allowed");
    });

    it("prohíbe potenciómetro en menores de 13 años", () => {
      expect(byId.powermeter.status).toBe("forbidden");
      expect(byId.powermeter.text).toBe("Prohibido en menores de 13 años");
    });

    it("usa cadencia mínima de 70 rpm", () => {
      expect(byId.cadence.text).toBe("70 rpm — nunca < 60 rpm");
    });

    it("prohíbe el test de FC máxima sin importar la etapa", () => {
      expect(byId.max_hr_test.status).toBe("forbidden");
    });
  });

  describe("grupo 10-12 años, fase Circa-PHV", () => {
    const rules = rulesFor("10-12", "Circa-PHV");
    const byId = Object.fromEntries(rules.map((r) => [r.id, r]));

    it("prohíbe alta intensidad con el texto específico de Circa-PHV", () => {
      expect(byId.high_intensity.status).toBe("forbidden");
      expect(byId.high_intensity.text).toBe("Prohibido en Circa-PHV");
    });

    it("reduce el volumen de fuerza peso corporal (allowed → caution)", () => {
      expect(byId.bodyweight_strength.status).toBe("caution");
    });

    it("eleva la cadencia mínima a 75 rpm en Circa-PHV", () => {
      expect(byId.cadence.text).toBe("75 rpm — nunca < 60 rpm");
    });

    it("no cambia potenciómetro/max_hr_test/intensidad/ratio respecto al default de 10-12 (ya son los más restrictivos)", () => {
      const defaults = rulesFor("10-12", "any");
      const defaultById = Object.fromEntries(defaults.map((r) => [r.id, r]));
      expect(byId.powermeter.status).toBe(defaultById.powermeter.status);
      expect(byId.max_hr_test.text).toBe(defaultById.max_hr_test.text);
      expect(byId.intensity_distribution.text).toBe(
        defaultById.intensity_distribution.text,
      );
      expect(byId.train_race_ratio.text).toBe(defaultById.train_race_ratio.text);
    });
  });

  describe("grupo 13-15 años, sin fase Circa-PHV", () => {
    const rules = rulesFor("13-15", "Post-PHV");
    const byId = Object.fromEntries(rules.map((r) => [r.id, r]));

    it("permite alta intensidad con precaución (máximo 2 sesiones/semana)", () => {
      expect(byId.high_intensity.status).toBe("caution");
    });

    it("permite el test de FC máxima con supervisión", () => {
      expect(byId.max_hr_test.status).toBe("allowed");
      expect(byId.max_hr_test.text).toBe("Permitido con supervisión");
    });

    it("permite potenciómetro solo para mayores de 13 años", () => {
      expect(byId.powermeter.status).toBe("allowed");
    });

    it("usa distribución 80/20 y ratio 60:40 fuera de Circa-PHV", () => {
      expect(byId.intensity_distribution.text).toBe("80% / 20%");
      expect(byId.train_race_ratio.text).toBe("60 : 40");
    });
  });

  describe("grupo 13-15 años, fase Circa-PHV", () => {
    const rules = rulesFor("13-15", "Circa-PHV");
    const byId = Object.fromEntries(rules.map((r) => [r.id, r]));

    it("prohíbe alta intensidad, fuerza externa y potenciómetro en Circa-PHV", () => {
      expect(byId.high_intensity.status).toBe("forbidden");
      expect(byId.external_load.status).toBe("forbidden");
      expect(byId.powermeter.status).toBe("forbidden");
    });

    it("retira el test de FC máxima en Circa-PHV aunque el grupo sea 13-15", () => {
      expect(byId.max_hr_test.status).toBe("forbidden");
    });

    it("endurece la distribución de intensidad y el ratio a los valores conservadores", () => {
      expect(byId.intensity_distribution.text).toBe("90% / 10%");
      expect(byId.train_race_ratio.text).toBe("70 : 30");
    });

    it('cae al default 13-15/"any" para cadencia (sin cambio: ya era 75 rpm)', () => {
      const rule = byId.cadence;
      expect(rule.text).toBe("75 rpm — nunca < 60 rpm");
      expect(rule.stage).toBe("any");
    });
  });
});

describe("differsFromDefault", () => {
  it("la propia fila default nunca difiere de sí misma", () => {
    const [defaultRule] = rulesFor("10-12", "any");
    expect(differsFromDefault(defaultRule)).toBe(false);
  });

  it("una fila Circa-PHV con texto distinto al default sí difiere", () => {
    const rules = rulesFor("10-12", "Circa-PHV");
    const highIntensity = rules.find((r) => r.id === "high_intensity")!;
    expect(differsFromDefault(highIntensity)).toBe(true);
  });

  it("una fila que cae al default por fallback (sin fila propia) no difiere", () => {
    const rules = rulesFor("13-15", "Circa-PHV");
    const cadence = rules.find((r) => r.id === "cadence")!;
    expect(cadence.stage).toBe("any");
    expect(differsFromDefault(cadence)).toBe(false);
  });

  it("detecta diferencia de status manteniendo el mismo texto no aplica aquí, pero detecta status distinto (bodyweight_strength)", () => {
    const rules = rulesFor("13-15", "Circa-PHV");
    const bodyweight = rules.find((r) => r.id === "bodyweight_strength")!;
    expect(bodyweight.status).toBe("caution");
    expect(differsFromDefault(bodyweight)).toBe(true);
  });
});
