/**
 * TrailRoute.test.tsx — feature 038, T301.
 *
 * Cubre: la lista de accesibilidad (`sr-only <ol>`) coincide con los
 * waypoints recibidos, el waypoint que coincide con la fecha de la cima
 * se dibuja como triángulo, y ambos trazados (horizontal + vertical)
 * están presentes en el DOM (el CSS decide cuál se ve por breakpoint).
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";

import {
  buildStageLogFullMonth,
  buildStageLogZeroAttendanceMonth,
} from "@/test/fixtures/stageLog";
import { TrailRoute } from "./TrailRoute";

describe("TrailRoute", () => {
  const fullMonth = buildStageLogFullMonth();

  it("no renderiza nada con una lista vacía de waypoints", () => {
    const { container } = render(<TrailRoute waypoints={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("la lista sr-only tiene exactamente un <li> por waypoint, en el mismo orden", () => {
    render(<TrailRoute waypoints={fullMonth.trail} summitDate={fullMonth.summit?.date} />);
    const list = screen.getByRole("list", { name: "Hitos de la ruta del mes" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(fullMonth.trail.length);
    fullMonth.trail.forEach((w, idx) => {
      expect(items[idx]).toHaveTextContent(w.label);
    });
  });

  it("incluye la etiqueta '(próximo)' solo para el waypoint futuro", () => {
    render(<TrailRoute waypoints={fullMonth.trail} />);
    const list = screen.getByRole("list", { name: "Hitos de la ruta del mes" });
    const items = within(list).getAllByRole("listitem");
    const futureCount = items.filter((li) => li.textContent?.includes("(próximo)")).length;
    const expectedFuture = fullMonth.trail.filter((w) => w.is_future).length;
    expect(futureCount).toBe(expectedFuture);
  });

  it("marca como triángulo (data-waypoint-summit) el waypoint cuya fecha coincide con la cima", () => {
    render(<TrailRoute waypoints={fullMonth.trail} summitDate={fullMonth.summit!.date} />);
    // El waypoint se renderiza dos veces (trazado horizontal + vertical) —
    // ambos deben coincidir con la misma marca de "cima".
    const horizontal = within(screen.getByTestId("trail-route-horizontal"));
    const summitMarkers = horizontal
      .getAllByTestId("trail-marker")
      .filter((m) => m.getAttribute("data-waypoint-summit") === "true");
    expect(summitMarkers).toHaveLength(1);
    expect(summitMarkers[0].getAttribute("data-waypoint-kind")).toBe("race");
  });

  it("sin summitDate, ningún waypoint se marca como triángulo", () => {
    render(<TrailRoute waypoints={fullMonth.trail} />);
    const markers = screen.getAllByTestId("trail-marker");
    expect(markers.every((m) => m.getAttribute("data-waypoint-summit") === null)).toBe(true);
  });

  it("renderiza ambos trazados (horizontal y vertical) en el DOM", () => {
    render(<TrailRoute waypoints={fullMonth.trail} />);
    expect(screen.getByTestId("trail-route-horizontal")).toBeInTheDocument();
    expect(screen.getByTestId("trail-route-vertical")).toBeInTheDocument();
  });

  it("con un solo waypoint (mes cero asistencia) igual renderiza el trail", () => {
    const zeroAttendance = buildStageLogZeroAttendanceMonth();
    render(<TrailRoute waypoints={zeroAttendance.trail} />);
    const list = screen.getByRole("list", { name: "Hitos de la ruta del mes" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
  });
});
