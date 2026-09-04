import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import { NextMeasurementCard } from "@/components/athletes/growth/NextMeasurementCard";
import type { MeasurementDue } from "@/types/growth.types";

function makeMeasurement(overrides: Partial<MeasurementDue> = {}): MeasurementDue {
  return {
    status: "ok",
    interval_days: 120,
    next_due_date: "2026-12-12",
    days_overdue: null,
    ...overrides,
  };
}

describe("NextMeasurementCard", () => {
  it("expone data-testid=growth-next-measurement en la raíz", () => {
    render(<NextMeasurementCard measurement={makeMeasurement()} />);
    expect(screen.getByTestId("growth-next-measurement")).toBeInTheDocument();
  });

  it("muestra la fecha, el intervalo y la etapa cuando el estado es 'ok'", () => {
    render(<NextMeasurementCard measurement={makeMeasurement()} />);
    expect(
      screen.getByText("Próxima medición: 12 dic 2026 · cada 120 días en Post-PHV"),
    ).toBeInTheDocument();
    expect(screen.getByText("Al día")).toBeInTheDocument();
  });

  it("muestra la etapa Circa-PHV para el intervalo de 30 días", () => {
    render(
      <NextMeasurementCard
        measurement={makeMeasurement({ status: "due_soon", interval_days: 30, next_due_date: "2026-09-10" })}
      />,
    );
    expect(screen.getByText(/cada 30 días en Circa-PHV/)).toBeInTheDocument();
    expect(screen.getByText("Próxima")).toBeInTheDocument();
  });

  it("muestra la etapa Pre-PHV para el intervalo de 90 días", () => {
    render(
      <NextMeasurementCard
        measurement={makeMeasurement({
          status: "overdue",
          interval_days: 90,
          next_due_date: "2026-06-01",
          days_overdue: 15,
        })}
      />,
    );
    expect(screen.getByText(/cada 90 días en Pre-PHV/)).toBeInTheDocument();
    expect(screen.getByText("Vencida")).toBeInTheDocument();
    expect(screen.getByText(/15d de atraso/)).toBeInTheDocument();
  });

  it("muestra 'Sin medición registrada' y la insignia 'Sin medir' cuando el estado es 'never'", () => {
    render(
      <NextMeasurementCard
        measurement={makeMeasurement({ status: "never", next_due_date: null, days_overdue: null })}
      />,
    );
    expect(screen.getByText("Sin medición registrada")).toBeInTheDocument();
    expect(screen.getByText("Sin medir")).toBeInTheDocument();
    expect(screen.queryByText(/Próxima medición/)).not.toBeInTheDocument();
  });

  it("sin violaciones de accesibilidad (axe)", async () => {
    const { container } = render(<NextMeasurementCard measurement={makeMeasurement()} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
