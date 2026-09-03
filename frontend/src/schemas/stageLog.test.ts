import { describe, expect, it } from "vitest";

import { stageLogSchema, parentStageLogSchema } from "@/schemas/stageLog";
import {
  buildStageLogFullMonth,
  buildStageLogTrainingOnlyMonth,
  buildStageLogZeroAttendanceMonth,
} from "@/test/fixtures/stageLog";
import { toParentStageLog } from "@/test/msw/stageLogHandlers";

describe("stageLogSchema", () => {
  it.each([
    ["mes completo (con analyst_reading, fotos, insignias)", buildStageLogFullMonth()],
    ["mes sin carrera (summit de entrenamiento, sin analyst_reading)", buildStageLogTrainingOnlyMonth()],
    ["mes con cero asistencia", buildStageLogZeroAttendanceMonth()],
  ])("valida el fixture: %s", (_label, fixture) => {
    const result = stageLogSchema.safeParse(fixture);
    expect(result.success).toBe(true);
  });

  it("rechaza schema_version distinto de 2", () => {
    const fixture = buildStageLogFullMonth({ schema_version: 2 });
    const result = stageLogSchema.safeParse({ ...fixture, schema_version: 1 });
    expect(result.success).toBe(false);
  });

  it("descarta campos no declarados (allowlist en cliente)", () => {
    const fixture = buildStageLogFullMonth();
    const result = stageLogSchema.parse({ ...fixture, unexpected_field: "x" });
    expect(result).not.toHaveProperty("unexpected_field");
  });
});

describe("parentStageLogSchema", () => {
  it("valida el DTO padre (sin block_states/grounding_violations)", () => {
    const parentView = toParentStageLog(buildStageLogFullMonth());
    const result = parentStageLogSchema.safeParse(parentView);
    expect(result.success).toBe(true);
  });

  it("valida el DTO padre de un mes sin analyst_reading", () => {
    const parentView = toParentStageLog(buildStageLogTrainingOnlyMonth());
    const result = parentStageLogSchema.safeParse(parentView);
    expect(result.success).toBe(true);
  });

  it("no expone source_insight_id ni block_states tras el parse", () => {
    const parentView = toParentStageLog(buildStageLogFullMonth());
    const parsed = parentStageLogSchema.parse(parentView);
    expect(parsed).not.toHaveProperty("block_states");
    expect(parsed).not.toHaveProperty("grounding_violations");
    if (parsed.analyst_reading) {
      expect(parsed.analyst_reading).not.toHaveProperty("source_insight_id");
    }
  });
});
