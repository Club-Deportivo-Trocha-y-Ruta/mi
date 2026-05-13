import { describe, it, expect } from "vitest";

import { rubricToLabel, showsRubricToParent } from "./parentMetrics";

describe("rubricToLabel", () => {
  it("mapea 1..5 a etiquetas cualitativas", () => {
    expect(rubricToLabel(1)).toBe("Iniciando");
    expect(rubricToLabel(2)).toBe("Desarrollando");
    expect(rubricToLabel(3)).toBe("Avanzando");
    expect(rubricToLabel(4)).toBe("Consolidando");
    expect(rubricToLabel(5)).toBe("Dominando");
  });

  it("redondea promedios decimales", () => {
    expect(rubricToLabel(3.4)).toBe("Avanzando");
    expect(rubricToLabel(3.6)).toBe("Consolidando");
  });

  it("retorna null para nulos y valores fuera de rango", () => {
    expect(rubricToLabel(null)).toBeNull();
    expect(rubricToLabel(undefined)).toBeNull();
    expect(rubricToLabel(0)).toBeNull();
    expect(rubricToLabel(6)).toBeNull();
  });
});

describe("showsRubricToParent — diferenciación LTAD", () => {
  it("oculta rúbrica para 10-12 (LTAD Aprender a Entrenar)", () => {
    expect(showsRubricToParent(10)).toBe(false);
    expect(showsRubricToParent(12.9)).toBe(false);
  });

  it("muestra rúbrica para ≥13 (LTAD Entrenar para Entrenar)", () => {
    expect(showsRubricToParent(13)).toBe(true);
    expect(showsRubricToParent(15)).toBe(true);
  });

  it("fallback conservador si age_decimal es null/undefined", () => {
    expect(showsRubricToParent(null)).toBe(false);
    expect(showsRubricToParent(undefined)).toBe(false);
  });
});
