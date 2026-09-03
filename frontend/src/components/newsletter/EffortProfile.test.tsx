/**
 * EffortProfile.test.tsx — feature 038, T301.
 *
 * recharts no genera SVG real de forma fiable en jsdom (mismo patrón que
 * `PercentileCurves.a11y.test.tsx`) — mockeamos los primitivos a `div`s
 * planos para probar la composición de datos (número de barras, tabla
 * sr-only) sin depender de medidas de layout que jsdom no calcula.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { buildStageLogFullMonth } from "@/test/fixtures/stageLog";
import { EffortProfile } from "./EffortProfile";

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

describe("EffortProfile", () => {
  const { effort_profile: weeks } = buildStageLogFullMonth();

  it("no renderiza nada con una lista vacía de semanas", () => {
    const { container } = render(<EffortProfile weeks={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("la tabla sr-only tiene una fila por semana con planificadas/asistidas/RPE", () => {
    render(<EffortProfile weeks={weeks} />);
    const table = screen.getByRole("table", {
      name: "Datos de perfil de esfuerzo semanal",
    });
    const rows = within(table).getAllByRole("row");
    // +1 por la fila de encabezado.
    expect(rows).toHaveLength(weeks.length + 1);

    weeks.forEach((w, idx) => {
      const row = rows[idx + 1];
      expect(row).toHaveTextContent(w.week_label);
      expect(row).toHaveTextContent(String(w.sessions_planned));
      expect(row).toHaveTextContent(String(w.sessions_attended));
      if (w.mean_rpe !== null) {
        expect(row).toHaveTextContent(w.mean_rpe.toFixed(1));
      }
    });
  });

  it("muestra 'Sin dato' en la tabla sr-only cuando mean_rpe es null", () => {
    const weeksWithNullRpe = [
      { week_label: "1–7 ago", sessions_planned: 2, sessions_attended: 0, mean_rpe: null },
    ];
    render(<EffortProfile weeks={weeksWithNullRpe} />);
    const table = screen.getByRole("table", {
      name: "Datos de perfil de esfuerzo semanal",
    });
    expect(within(table).getByText("Sin dato")).toBeInTheDocument();
  });

  it("renderiza el título del bloque", () => {
    render(<EffortProfile weeks={weeks} />);
    expect(screen.getByText("Perfil de esfuerzo")).toBeInTheDocument();
  });
});
