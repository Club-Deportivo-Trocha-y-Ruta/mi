/**
 * Tests para HistoryTable (feature 044, US6/US7 — T076).
 *
 * Cubre: agrupación temporada → categoría en `<tbody>` separados (ninguna
 * fila ni línea une dos grupos), "sin dato" en cada campo `null`, y la
 * nota de cambio de categoría para la variante familia.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import { HistoryTable } from "@/components/race/history/HistoryTable";
import { makeRaceHistoryPoint } from "@/test/msw/raceHistoryHandlers";

describe("HistoryTable", () => {
  it("agrupa por temporada → categoría en tbodies separados — ningún grupo comparte fila", () => {
    render(
      <HistoryTable
        points={[
          makeRaceHistoryPoint({
            event_id: 30,
            event_date: "2024-03-10",
            season: 2024,
            category_label: "INFANTIL B",
            category_changed: false,
          }),
          makeRaceHistoryPoint({
            event_id: 41,
            event_date: "2025-02-09",
            season: 2025,
            category_label: "PREJUVENIL A",
            category_changed: true,
            previous_category_label: "INFANTIL B",
          }),
        ]}
      />,
    );

    const table = screen.getByTestId("history-table");
    const bodies = table.querySelectorAll("tbody");
    expect(bodies).toHaveLength(2);
    expect(bodies[0]).toHaveTextContent("2024 · INFANTIL B");
    expect(bodies[1]).toHaveTextContent("2025 · PREJUVENIL A");
    // La fila de 2024 no aparece dentro del segundo grupo, ni viceversa.
    expect(bodies[0]).not.toHaveTextContent("PREJUVENIL A");
    expect(bodies[1]).not.toHaveTextContent("INFANTIL B 2024");
  });

  it("un mismo código de categoría en dos temporadas distintas sigue siendo dos grupos", () => {
    render(
      <HistoryTable
        points={[
          makeRaceHistoryPoint({
            event_id: 30,
            event_date: "2024-03-10",
            season: 2024,
            category_code: "PJUV_A",
            category_label: "PREJUVENIL A",
          }),
          makeRaceHistoryPoint({
            event_id: 41,
            event_date: "2025-02-09",
            season: 2025,
            category_code: "PJUV_A",
            category_label: "PREJUVENIL A",
          }),
        ]}
      />,
    );
    const table = screen.getByTestId("history-table");
    expect(table.querySelectorAll("tbody")).toHaveLength(2);
  });

  it('muestra "sin dato" en percentil/parrilla/brecha/velocidad cuando la API envía null', () => {
    render(
      <HistoryTable
        points={[
          makeRaceHistoryPoint({
            percentile: null,
            field_size: null,
            gap_to_median_pct: null,
            avg_speed_kmh: null,
          }),
        ]}
      />,
    );
    const row = screen.getByTestId("history-table").querySelector("tbody tr:last-child");
    expect(row).toHaveTextContent(/sin dato/i);
    // 4 columnas con "sin dato" en esta fila.
    expect(row?.textContent?.match(/sin dato/gi)).toHaveLength(4);
  });

  it("un no-finalista muestra su estado en la columna de puesto, no 'sin dato' genérico", () => {
    render(
      <HistoryTable
        points={[
          makeRaceHistoryPoint({
            status: "dnf",
            position: null,
            percentile: null,
            gap_to_median_pct: null,
          }),
        ]}
      />,
    );
    expect(screen.getByText("No terminó")).toBeInTheDocument();
  });

  it("audience=family: muestra el aviso de cambio de categoría sin afirmar un ascenso ni una expectativa de peor desempeño", () => {
    render(
      <HistoryTable
        audience="family"
        points={[
          makeRaceHistoryPoint({
            event_id: 30,
            event_date: "2024-03-10",
            season: 2024,
            category_label: "INFANTIL B",
            category_changed: false,
          }),
          makeRaceHistoryPoint({
            event_id: 41,
            event_date: "2025-02-09",
            season: 2025,
            category_label: "PREJUVENIL A",
            category_changed: true,
            previous_category_label: "INFANTIL B",
          }),
        ]}
      />,
    );
    const note = screen.getByText(/cambió de categoría/i);
    expect(note).toBeInTheDocument();
    expect(note.textContent).toContain("INFANTIL B");
    expect(note.textContent).toContain("PREJUVENIL A");
    // No afirma un ascenso ("subió") ni una expectativa de peor desempeño.
    expect(note.textContent).not.toMatch(/subió|bajó|empeoró|peor|mayores/i);
  });

  it("audience=coach (default): no muestra el aviso de familia", () => {
    render(
      <HistoryTable
        points={[
          makeRaceHistoryPoint({
            event_id: 41,
            season: 2025,
            category_changed: true,
            previous_category_label: "INFANTIL B",
          }),
        ]}
      />,
    );
    expect(screen.queryByText(/cambió de categoría/i)).not.toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = render(
      <HistoryTable points={[makeRaceHistoryPoint()]} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
