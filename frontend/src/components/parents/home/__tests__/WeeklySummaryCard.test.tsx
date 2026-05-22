import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { WeeklySummaryCard } from "@/components/parents/home/WeeklySummaryCard";
import type { ParentMonthlySummary } from "@/types/trainingSession.types";

function mkSummary(overrides?: Partial<ParentMonthlySummary>): ParentMonthlySummary {
  return {
    athlete_id: 7,
    athlete_name: "Santiago López",
    year: 2026,
    month: 5,
    count_present: 6,
    count_total: 8,
    percentage: 75,
    focos_técnicos: ["Frenada", "Pedaleo de pie"],
    ...overrides,
  };
}

describe("WeeklySummaryCard", () => {
  it("muestra skeleton accesible cuando isLoading", () => {
    render(
      <WeeklySummaryCard
        summary={undefined}
        isLoading={true}
        monthLabel="mayo de 2026"
      />,
    );
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-busy", "true");
  });

  it("muestra empty state cuando count_total = 0", () => {
    render(
      <WeeklySummaryCard
        summary={mkSummary({ count_total: 0, count_present: 0 })}
        isLoading={false}
        monthLabel="mayo de 2026"
      />,
    );
    expect(screen.getByTestId("weekly-empty")).toBeInTheDocument();
  });

  it("muestra X de Y entrenos con copy factual", () => {
    render(
      <WeeklySummaryCard
        summary={mkSummary({ count_present: 6, count_total: 8 })}
        isLoading={false}
        monthLabel="mayo de 2026"
        athleteName="Santiago"
      />,
    );
    expect(screen.getByText(/Santiago: 6 de 8 entrenos/i)).toBeInTheDocument();
  });

  it("NO muestra porcentaje grande (sólo conteo factual)", () => {
    render(
      <WeeklySummaryCard
        summary={mkSummary()}
        isLoading={false}
        monthLabel="mayo de 2026"
      />,
    );
    // No debería aparecer "75%" en la UI
    expect(screen.queryByText(/75%/)).not.toBeInTheDocument();
  });

  it("muestra disclaimer pedagógico con clase text-disclaimer", () => {
    const { container } = render(
      <WeeklySummaryCard
        summary={mkSummary()}
        isLoading={false}
        monthLabel="mayo de 2026"
      />,
    );
    const disclaimer = container.querySelector(".text-text-disclaimer");
    expect(disclaimer).not.toBeNull();
  });

  it("muestra mensaje de error cuando isError=true", () => {
    render(
      <WeeklySummaryCard
        summary={undefined}
        isLoading={false}
        isError={true}
        monthLabel="mayo de 2026"
      />,
    );
    expect(screen.getByText(/No fue posible cargar el resumen/i)).toBeInTheDocument();
  });
});
