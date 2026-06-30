import { describe, it, expect } from "vitest";

import {
  gymkhanaLayoutSchema,
  circuitElementSchema,
  circuitElementKindSchema,
} from "./technique.schemas";

// ---------------------------------------------------------------------------
// Helpers — fixtures mínimos válidos
// ---------------------------------------------------------------------------

/** Canvas base: 100×80 unidades. */
function baseLayout(overrides: Record<string, unknown> = {}) {
  return {
    width: 100,
    height: 80,
    elements: [],
    ...overrides,
  };
}

/** Elemento cono válido en (10, 10). */
function baseCone(overrides: Record<string, unknown> = {}) {
  return { kind: "cone", x: 10, y: 10, ...overrides };
}

// ---------------------------------------------------------------------------
// circuitElementKindSchema — vocabulario controlado
// ---------------------------------------------------------------------------

describe("circuitElementKindSchema", () => {
  const validKinds = ["cone", "line", "gate", "mine", "arrow", "beam", "ring"] as const;

  it.each(validKinds)("acepta el kind '%s'", (kind) => {
    expect(circuitElementKindSchema.safeParse(kind).success).toBe(true);
  });

  it("rechaza un kind desconocido", () => {
    expect(circuitElementKindSchema.safeParse("hurdle").success).toBe(false);
    expect(circuitElementKindSchema.safeParse("").success).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// circuitElementSchema — elemento individual
// ---------------------------------------------------------------------------

describe("circuitElementSchema", () => {
  it("acepta un elemento mínimo válido (kind + x + y)", () => {
    const result = circuitElementSchema.safeParse(baseCone());
    expect(result.success).toBe(true);
  });

  it("acepta rotation opcional", () => {
    const result = circuitElementSchema.safeParse(baseCone({ rotation: 45 }));
    expect(result.success).toBe(true);
    if (result.success) expect(result.data.rotation).toBe(45);
  });

  it("acepta style 'dashed' en una línea", () => {
    const result = circuitElementSchema.safeParse({
      kind: "line",
      x: 5,
      y: 5,
      style: "dashed",
    });
    expect(result.success).toBe(true);
  });

  it("acepta style 'solid' en una línea", () => {
    const result = circuitElementSchema.safeParse({
      kind: "line",
      x: 5,
      y: 5,
      style: "solid",
    });
    expect(result.success).toBe(true);
  });

  it("acepta style en kind no-line (no es error duro — FR-007 nota)", () => {
    // style es semánticamente relevante solo en line pero se acepta en otros kinds
    const result = circuitElementSchema.safeParse(baseCone({ style: "dashed" }));
    expect(result.success).toBe(true);
  });

  it("elimina campos extra desconocidos (.strip)", () => {
    const result = circuitElementSchema.safeParse(
      baseCone({ label: "PII prohibida en Phase A", unknown_field: true }),
    );
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data).not.toHaveProperty("label");
      expect(result.data).not.toHaveProperty("unknown_field");
    }
  });

  it("rechaza kind desconocido", () => {
    const result = circuitElementSchema.safeParse({ kind: "wall", x: 0, y: 0 });
    expect(result.success).toBe(false);
  });

  it("rechaza si falta x", () => {
    const result = circuitElementSchema.safeParse({ kind: "cone", y: 10 });
    expect(result.success).toBe(false);
  });

  it("rechaza si falta y", () => {
    const result = circuitElementSchema.safeParse({ kind: "cone", x: 10 });
    expect(result.success).toBe(false);
  });

  it("rechaza style desconocido", () => {
    const result = circuitElementSchema.safeParse(
      baseCone({ style: "dotted" }),
    );
    expect(result.success).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// gymkhanaLayoutSchema — documento completo
// ---------------------------------------------------------------------------

describe("gymkhanaLayoutSchema — casos válidos", () => {
  it("acepta layout mínimo con elements vacío", () => {
    const result = gymkhanaLayoutSchema.safeParse(baseLayout());
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.elements).toHaveLength(0);
    }
  });

  it("acepta layout con varios elementos de kinds distintos", () => {
    const elements = [
      { kind: "cone", x: 10, y: 10 },
      { kind: "line", x: 20, y: 20, style: "dashed" },
      { kind: "gate", x: 30, y: 30, rotation: 90 },
      { kind: "mine", x: 40, y: 40 },
      { kind: "arrow", x: 50, y: 50, rotation: 180 },
      { kind: "beam", x: 60, y: 60 },
      { kind: "ring", x: 70, y: 70 },
    ];
    const result = gymkhanaLayoutSchema.safeParse(baseLayout({ elements }));
    expect(result.success).toBe(true);
    if (result.success) expect(result.data.elements).toHaveLength(7);
  });

  it("acepta elemento en el límite x=0, y=0", () => {
    const result = gymkhanaLayoutSchema.safeParse(
      baseLayout({ elements: [{ kind: "cone", x: 0, y: 0 }] }),
    );
    expect(result.success).toBe(true);
  });

  it("acepta elemento en el límite x=width, y=height", () => {
    const result = gymkhanaLayoutSchema.safeParse(
      baseLayout({ elements: [{ kind: "cone", x: 100, y: 80 }] }),
    );
    expect(result.success).toBe(true);
  });

  it("elimina campos extra desconocidos del layout (.strip)", () => {
    const result = gymkhanaLayoutSchema.safeParse(
      baseLayout({ extra_meta: "ignorar" }),
    );
    expect(result.success).toBe(true);
    if (result.success) expect(result.data).not.toHaveProperty("extra_meta");
  });
});

// ---------------------------------------------------------------------------
// gymkhanaLayoutSchema — width / height inválidos
// ---------------------------------------------------------------------------

describe("gymkhanaLayoutSchema — width / height inválidos", () => {
  it("rechaza width = 0 (no positivo)", () => {
    const result = gymkhanaLayoutSchema.safeParse(baseLayout({ width: 0 }));
    expect(result.success).toBe(false);
  });

  it("rechaza width negativo", () => {
    const result = gymkhanaLayoutSchema.safeParse(baseLayout({ width: -1 }));
    expect(result.success).toBe(false);
  });

  it("rechaza height = 0", () => {
    const result = gymkhanaLayoutSchema.safeParse(baseLayout({ height: 0 }));
    expect(result.success).toBe(false);
  });

  it("rechaza height negativo", () => {
    const result = gymkhanaLayoutSchema.safeParse(baseLayout({ height: -5 }));
    expect(result.success).toBe(false);
  });

  it("rechaza width = Infinity (no finito)", () => {
    const result = gymkhanaLayoutSchema.safeParse(
      baseLayout({ width: Infinity }),
    );
    expect(result.success).toBe(false);
  });

  it("rechaza height = Infinity", () => {
    const result = gymkhanaLayoutSchema.safeParse(
      baseLayout({ height: Infinity }),
    );
    expect(result.success).toBe(false);
  });

  it("rechaza width = NaN", () => {
    const result = gymkhanaLayoutSchema.safeParse(
      baseLayout({ width: NaN }),
    );
    expect(result.success).toBe(false);
  });

  it("rechaza height = NaN", () => {
    const result = gymkhanaLayoutSchema.safeParse(
      baseLayout({ height: NaN }),
    );
    expect(result.success).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// gymkhanaLayoutSchema — coordenadas de elementos fuera de rango
// ---------------------------------------------------------------------------

describe("gymkhanaLayoutSchema — coordenadas de elementos", () => {
  it("rechaza elemento con x negativo", () => {
    const result = gymkhanaLayoutSchema.safeParse(
      baseLayout({ elements: [{ kind: "cone", x: -1, y: 10 }] }),
    );
    expect(result.success).toBe(false);
    if (!result.success) {
      const paths = result.error.issues.map((i) => i.path.join("."));
      expect(paths.some((p) => p.includes("x"))).toBe(true);
    }
  });

  it("rechaza elemento con x > width", () => {
    const result = gymkhanaLayoutSchema.safeParse(
      baseLayout({ elements: [{ kind: "cone", x: 101, y: 10 }] }),
    );
    expect(result.success).toBe(false);
    if (!result.success) {
      const paths = result.error.issues.map((i) => i.path.join("."));
      expect(paths.some((p) => p.includes("x"))).toBe(true);
    }
  });

  it("rechaza elemento con y negativo", () => {
    const result = gymkhanaLayoutSchema.safeParse(
      baseLayout({ elements: [{ kind: "cone", x: 10, y: -1 }] }),
    );
    expect(result.success).toBe(false);
    if (!result.success) {
      const paths = result.error.issues.map((i) => i.path.join("."));
      expect(paths.some((p) => p.includes("y"))).toBe(true);
    }
  });

  it("rechaza elemento con y > height", () => {
    const result = gymkhanaLayoutSchema.safeParse(
      baseLayout({ elements: [{ kind: "cone", x: 10, y: 81 }] }),
    );
    expect(result.success).toBe(false);
    if (!result.success) {
      const paths = result.error.issues.map((i) => i.path.join("."));
      expect(paths.some((p) => p.includes("y"))).toBe(true);
    }
  });

  it("rechaza elemento con x = Infinity", () => {
    const result = gymkhanaLayoutSchema.safeParse(
      baseLayout({ elements: [{ kind: "cone", x: Infinity, y: 10 }] }),
    );
    expect(result.success).toBe(false);
  });

  it("rechaza elemento con y = -Infinity", () => {
    const result = gymkhanaLayoutSchema.safeParse(
      baseLayout({ elements: [{ kind: "cone", x: 10, y: -Infinity }] }),
    );
    expect(result.success).toBe(false);
  });

  it("rechaza elemento con rotation = Infinity", () => {
    const result = gymkhanaLayoutSchema.safeParse(
      baseLayout({
        elements: [{ kind: "gate", x: 10, y: 10, rotation: Infinity }],
      }),
    );
    expect(result.success).toBe(false);
    if (!result.success) {
      const paths = result.error.issues.map((i) => i.path.join("."));
      expect(paths.some((p) => p.includes("rotation"))).toBe(true);
    }
  });

  it("acumula errores de múltiples elementos inválidos en un solo parse", () => {
    const result = gymkhanaLayoutSchema.safeParse(
      baseLayout({
        elements: [
          { kind: "cone", x: -5, y: 10 },   // x fuera de rango
          { kind: "cone", x: 10, y: 999 },   // y fuera de rango
        ],
      }),
    );
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.length).toBeGreaterThanOrEqual(2);
    }
  });
});

// ---------------------------------------------------------------------------
// gymkhanaLayoutSchema — invariante: array elements puede estar vacío
// ---------------------------------------------------------------------------

describe("gymkhanaLayoutSchema — invariante de elements vacío", () => {
  it("un layout válido sin elementos (FR-007: empty elements is valid)", () => {
    const result = gymkhanaLayoutSchema.safeParse({
      width: 50,
      height: 50,
      elements: [],
    });
    expect(result.success).toBe(true);
  });

  it("rechaza si falta el campo elements", () => {
    const result = gymkhanaLayoutSchema.safeParse({ width: 100, height: 80 });
    expect(result.success).toBe(false);
  });
});
