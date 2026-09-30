import { describe, expect, it } from "vitest";

import {
  anthropometryCaptureSchema,
  netSittingHeight,
  toAnthropometryPayload,
  todayISO,
} from "../anthropometryCapture.schema";

const valid = {
  evaluation_date: "2026-01-15",
  weight_kg: 41.2,
  standing_height_cm: 152.3,
  sitting_height_cm: 78.1,
  arm_span_cm: null,
  bench_height_cm: null,
  notes: null,
};

function messages(input: unknown, path?: string) {
  const r = anthropometryCaptureSchema.safeParse(input);
  if (r.success) return [];
  return r.error.issues
    .filter((i) => !path || i.path[0] === path)
    .map((i) => i.message);
}

describe("anthropometryCaptureSchema", () => {
  it("acepta valores válidos", () => {
    expect(anthropometryCaptureSchema.safeParse(valid).success).toBe(true);
  });

  it("rangos de peso", () => {
    expect(messages({ ...valid, weight_kg: 19 }, "weight_kg")).toContain("Mín. 20 kg");
    expect(messages({ ...valid, weight_kg: 151 }, "weight_kg")).toContain("Máx. 150 kg");
  });

  it("rangos de talla de pie y envergadura", () => {
    expect(messages({ ...valid, standing_height_cm: 99 }, "standing_height_cm")).toContain(
      "Mín. 100 cm",
    );
    expect(messages({ ...valid, standing_height_cm: 221 }, "standing_height_cm")).toContain(
      "Máx. 220 cm",
    );
    expect(messages({ ...valid, arm_span_cm: 99 }, "arm_span_cm")).toContain("Mín. 100 cm");
    expect(messages({ ...valid, arm_span_cm: 221 }, "arm_span_cm")).toContain("Máx. 220 cm");
    expect(anthropometryCaptureSchema.safeParse({ ...valid, arm_span_cm: 150 }).success).toBe(
      true,
    );
  });

  it("rango de talla sentado neta", () => {
    expect(messages({ ...valid, standing_height_cm: 100, sitting_height_cm: 49 }, "sitting_height_cm")).toContain(
      "Mín. 50 cm",
    );
    expect(messages({ ...valid, standing_height_cm: 200, sitting_height_cm: 121 }, "sitting_height_cm")).toContain(
      "Máx. 120 cm",
    );
  });

  it("razón sentado/de pie incoherente", () => {
    const msg = "La talla sentado no es coherente con la talla de pie";
    expect(messages({ ...valid, sitting_height_cm: 100 }, "sitting_height_cm")).toContain(msg);
    expect(messages({ ...valid, sitting_height_cm: 60 }, "sitting_height_cm")).toContain(msg);
  });

  it("descuenta el banco antes de validar", () => {
    const withBench = { ...valid, sitting_height_cm: 118.1, bench_height_cm: 40 };
    expect(anthropometryCaptureSchema.safeParse(withBench).success).toBe(true);
    // Sin descontar, 118.1 / 152.3 = 0.78: incoherente.
    expect(
      messages({ ...withBench, bench_height_cm: 0 }, "sitting_height_cm"),
    ).toContain("La talla sentado no es coherente con la talla de pie");
  });

  it("talla neta <= 0 es error", () => {
    const m = messages({ ...valid, sitting_height_cm: 40, bench_height_cm: 40 }, "sitting_height_cm");
    expect(m.length).toBeGreaterThan(0);
  });

  it("banco negativo es error", () => {
    expect(messages({ ...valid, bench_height_cm: -1 }, "bench_height_cm")).toContain(
      "No puede ser negativa",
    );
  });

  it("fecha futura es error, hoy es válido", () => {
    expect(messages({ ...valid, evaluation_date: "2999-01-01" }, "evaluation_date")).toContain(
      "No puede ser futura",
    );
    expect(
      anthropometryCaptureSchema.safeParse({ ...valid, evaluation_date: todayISO() }).success,
    ).toBe(true);
  });

  it("campos obligatorios faltantes", () => {
    const { weight_kg: _w, ...rest } = valid;
    expect(messages(rest, "weight_kg")).toContain("Obligatorio");
  });
});

describe("toAnthropometryPayload", () => {
  it("envía talla neta y nunca el banco", () => {
    const parsed = anthropometryCaptureSchema.parse({
      ...valid,
      sitting_height_cm: 118.1,
      bench_height_cm: 40,
    });
    const payload = toAnthropometryPayload(parsed);
    expect(payload.sitting_height_cm).toBe(78.1);
    expect(payload).not.toHaveProperty("bench_height_cm");
  });
});

describe("netSittingHeight", () => {
  it("redondea a 0.1", () => {
    expect(netSittingHeight(118.1, 40)).toBe(78.1);
    expect(netSittingHeight(80, null)).toBe(80);
  });
});
