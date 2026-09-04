import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import { GrowthAlerts } from "@/components/athletes/growth/GrowthAlerts";

describe("GrowthAlerts", () => {
  it("no renderiza nada cuando no hay alertas", () => {
    const { container } = render(<GrowthAlerts alerts={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("expone data-testid=growth-alerts en la raíz cuando hay alertas", () => {
    render(<GrowthAlerts alerts={["rapid_growth"]} />);
    expect(screen.getByTestId("growth-alerts")).toBeInTheDocument();
  });

  it("mapea rapid_growth al aviso de crecimiento acelerado (mismo título que el dashboard)", () => {
    render(<GrowthAlerts alerts={["rapid_growth"]} />);
    expect(screen.getByText(/Crecimiento acelerado detectado/i)).toBeInTheDocument();
  });

  it("mapea approaching_circa al aviso de acercamiento al estirón", () => {
    render(<GrowthAlerts alerts={["approaching_circa"]} />);
    expect(screen.getByText(/Se acerca al estirón/i)).toBeInTheDocument();
  });

  it("mapea phase_changed al aviso de cambio de etapa", () => {
    render(<GrowthAlerts alerts={["phase_changed"]} />);
    expect(screen.getByText(/Cambió de etapa de maduración/i)).toBeInTheDocument();
  });

  // circa_phv / height_p3 / bmi_p3 ya se muestran en el bloque propio de
  // `TrainingReadiness.tsx` (`buildAlertsFromSummary`) — GrowthAlerts los
  // ignora en silencio para no duplicar el mismo aviso dos veces en la
  // pestaña (ver docstring del componente).
  it("no renderiza nada para circa_phv/height_p3/bmi_p3 (ya cubiertos por TrainingReadiness)", () => {
    const { container } = render(<GrowthAlerts alerts={["circa_phv", "height_p3", "bmi_p3"]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("de una mezcla de códigos, sólo renderiza los tres compartidos con el dashboard", () => {
    render(<GrowthAlerts alerts={["circa_phv", "height_p3", "rapid_growth"]} />);
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.getByText(/Crecimiento acelerado detectado/i)).toBeInTheDocument();
  });

  it("renderiza una fila por cada alerta presente, en el orden fijo definido", () => {
    render(<GrowthAlerts alerts={["phase_changed", "approaching_circa", "rapid_growth"]} />);
    const rows = screen.getAllByRole("alert");
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent(/Crecimiento acelerado/i);
    expect(rows[1]).toHaveTextContent(/Se acerca al estirón/i);
    expect(rows[2]).toHaveTextContent(/Cambió de etapa/i);
  });

  it("cada fila lleva un ícono (nunca sólo color) acompañando el texto", () => {
    const { container } = render(<GrowthAlerts alerts={["rapid_growth"]} />);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("sin violaciones de accesibilidad (axe) con las tres alertas soportadas", async () => {
    const { container } = render(
      <GrowthAlerts alerts={["rapid_growth", "approaching_circa", "phase_changed"]} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
