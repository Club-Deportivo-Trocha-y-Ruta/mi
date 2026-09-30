import { describe, expect, it } from "vitest";

import { MaturationStatus } from "@/types/enums";
import { PLAUSIBILITY_COPY, PLAUSIBILITY_MEASURE_LABELS } from "../plausibilityCopy";
import { phvPlainLabel } from "../phvPlain";

describe("plausibilityCopy", () => {
  it("tiene los 5 mensajes y las 4 etiquetas", () => {
    expect(Object.keys(PLAUSIBILITY_COPY)).toHaveLength(5);
    expect(Object.keys(PLAUSIBILITY_MEASURE_LABELS)).toHaveLength(4);
    expect(PLAUSIBILITY_COPY.weight_change_large).toContain("10 %");
  });
});

describe("phvPlain", () => {
  it("traduce cada etapa", () => {
    expect(phvPlainLabel(MaturationStatus.PrePHV)).toBe("Aún no llega al estirón");
    expect(phvPlainLabel(MaturationStatus.CircaPHV)).toBe("Está en pleno estirón");
    expect(phvPlainLabel(MaturationStatus.PostPHV)).toBe("Ya pasó el estirón");
  });
});
