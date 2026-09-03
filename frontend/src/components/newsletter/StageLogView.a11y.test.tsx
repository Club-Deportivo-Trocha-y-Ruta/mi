/**
 * StageLogView.a11y.test.tsx — feature 038, T301.
 *
 * jest-axe cero violaciones para mode="parent" y mode="coach" sobre los
 * 3 fixtures (full month / training-only / zero attendance). recharts no
 * genera SVG real y fiable en jsdom (mismo patrón que
 * `PercentileCurves.a11y.test.tsx`) — se mockea `ResponsiveContainer` a
 * un `div` con dimensiones fijas para evitar falsos positivos de axe
 * sobre medidas de layout que jsdom no calcula.
 */
import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";

import {
  buildStageLogFullMonth,
  buildStageLogTrainingOnlyMonth,
  buildStageLogZeroAttendanceMonth,
} from "@/test/fixtures/stageLog";
import { StageLogView } from "./StageLogView";

expect.extend(toHaveNoViolations);

vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="responsive-container" style={{ width: 400, height: 224 }}>
        {children}
      </div>
    ),
  };
});

const FIXTURES = [
  ["mes completo", buildStageLogFullMonth] as const,
  ["mes sin carrera", buildStageLogTrainingOnlyMonth] as const,
  ["mes con cero asistencia", buildStageLogZeroAttendanceMonth] as const,
];

describe("StageLogView — accesibilidad", () => {
  describe.each(FIXTURES)("%s", (_label, buildFixture) => {
    it.each(["parent", "coach"] as const)("mode=%s sin violaciones jest-axe", async (mode) => {
      const { container } = render(
        <StageLogView stageLog={buildFixture()} mode={mode} />,
      );
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });
});
