/**
 * Tests para HistoryTable (feature 044, US6/US7 — T076; extendido T083).
 *
 * Cubre: agrupación temporada → categoría en `<tbody>` separados (ninguna
 * fila ni línea une dos grupos), "sin dato" en cada campo `null`, la nota
 * de cambio de categoría para la variante familia (T083: bifurcada por
 * `category_change_kind`), el explicador familiar de percentil/brecha
 * (T083 MAJOR) y la vista mobile de tarjetas (T083 BLOCKER).
 *
 * Desde T083 la tabla desktop y las tarjetas mobile se montan siempre
 * (toggle puramente CSS, igual que `AnthropometryHistory.tsx`) — los tests
 * que antes usaban `screen.getByText`/`getByTestId` sin escopear ahora
 * escopean explícitamente por `history-table` (desktop) o
 * `history-table-mobile`, porque el mismo texto existe en ambas vistas.
 *
 * El nombre de la válida es un `Link` de react-router (2026-09-23) — todo
 * `render` de este archivo pasa por `renderTable`, que envuelve en
 * `MemoryRouter` (un `Link` sin Router en el árbol lanza en jsdom).
 */
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { axe } from "jest-axe";

import { HistoryTable } from "@/components/race/history/HistoryTable";
import { makeRaceHistoryPoint } from "@/test/msw/raceHistoryHandlers";

function renderTable(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("HistoryTable", () => {
  it("agrupa por temporada → categoría en tbodies separados — ningún grupo comparte fila", () => {
    renderTable(
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
            category_change_kind: "other",
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

  it("un renombre del catálogo a mitad de temporada (mismo category_code) sigue siendo UN solo grupo — encabezado 'A / B', fila anota su etiqueta propia", () => {
    renderTable(
      <HistoryTable
        points={[
          makeRaceHistoryPoint({
            event_id: 41,
            event_date: "2025-02-09",
            label: "Válida 1 — Ginebra",
            season: 2025,
            category_code: "PJUV_A",
            category_label: "PREJUVENIL A DAMAS",
            category_changed: false,
          }),
          makeRaceHistoryPoint({
            event_id: 42,
            event_date: "2025-03-09",
            label: "Válida 2 — Buga",
            season: 2025,
            category_code: "PJUV_A",
            category_label: "PREJUVENIL A FEMENINO",
            category_changed: false,
          }),
        ]}
      />,
    );
    const table = screen.getByTestId("history-table");
    // Un solo grupo — la renombrada frozen label NUNCA parte por category_id.
    expect(table.querySelectorAll("tbody")).toHaveLength(1);
    const heading = table.querySelector("tbody th");
    expect(heading).toHaveTextContent("2025 · PREJUVENIL A DAMAS / PREJUVENIL A FEMENINO");
    // Cada fila anota su propia etiqueta impresa, distinta del encabezado.
    expect(within(table).getByText("PREJUVENIL A DAMAS")).toBeInTheDocument();
    expect(within(table).getByText("PREJUVENIL A FEMENINO")).toBeInTheDocument();

    // Misma cobertura en la vista mobile.
    const mobile = screen.getByTestId("history-table-mobile");
    expect(
      within(mobile).getByText("2025 · PREJUVENIL A DAMAS / PREJUVENIL A FEMENINO"),
    ).toBeInTheDocument();
    expect(within(mobile).getByText("PREJUVENIL A DAMAS")).toBeInTheDocument();
    expect(within(mobile).getByText("PREJUVENIL A FEMENINO")).toBeInTheDocument();
  });

  it("un mismo código de categoría en dos temporadas distintas sigue siendo dos grupos", () => {
    renderTable(
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

  it('muestra "sin dato" en percentil/parrilla/brecha cuando la API envía null', () => {
    renderTable(
      <HistoryTable
        points={[
          makeRaceHistoryPoint({
            percentile: null,
            field_size: null,
            gap_to_median_pct: null,
          }),
        ]}
      />,
    );
    const row = screen.getByTestId("history-table").querySelector("tbody tr:last-child");
    expect(row).toHaveTextContent(/sin dato/i);
    // 3 columnas con "sin dato" en esta fila — velocidad ya no es una
    // columna (retirada 2026-09-22).
    expect(row?.textContent?.match(/sin dato/gi)).toHaveLength(3);
  });

  it("un no-finalista muestra su estado en la columna de puesto, no 'sin dato' genérico", () => {
    renderTable(
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
    // Escopeado a la tabla desktop: el mismo texto también vive en la
    // tarjeta mobile (T083) — ambas vistas están montadas a la vez.
    const table = screen.getByTestId("history-table");
    expect(within(table).getByText("No terminó")).toBeInTheDocument();
  });

  describe("audience=family — aviso de cambio de categoría (T083, FR-042)", () => {
    it("category_change_kind='other': aviso neutral, sin afirmar un ascenso ni una expectativa de peor desempeño", () => {
      renderTable(
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
              category_change_kind: "other",
            }),
          ]}
        />,
      );
      const table = screen.getByTestId("history-table");
      const note = within(table).getByText(/cambió de categoría/i);
      expect(note).toBeInTheDocument();
      expect(note.textContent).toContain("INFANTIL B");
      expect(note.textContent).toContain("PREJUVENIL A");
      // No afirma un ascenso ("subió") ni una expectativa de peor desempeño.
      expect(note.textContent).not.toMatch(/subió|bajó|empeoró|peor|mayores/i);
    });

    it("category_change_kind=null (sin distinción del backend): mismo aviso neutral que 'other'", () => {
      renderTable(
        <HistoryTable
          audience="family"
          points={[
            makeRaceHistoryPoint({
              event_id: 41,
              season: 2025,
              category_changed: true,
              previous_category_label: "INFANTIL B",
              category_change_kind: null,
            }),
          ]}
        />,
      );
      const table = screen.getByTestId("history-table");
      const note = within(table).getByText(/cambió de categoría/i);
      expect(note.textContent).not.toMatch(/subió|mayores/i);
    });

    it("category_change_kind='promotion': explica el ascenso — dato respaldado por el backend", () => {
      renderTable(
        <HistoryTable
          audience="family"
          points={[
            makeRaceHistoryPoint({
              event_id: 41,
              season: 2025,
              category_label: "PREJUVENIL A",
              category_changed: true,
              previous_category_label: "INFANTIL B",
              category_change_kind: "promotion",
            }),
          ]}
        />,
      );
      const table = screen.getByTestId("history-table");
      const note = within(table).getByText(/subió de categoría/i);
      expect(note.textContent).toBe(
        "Subió de categoría: ahora corre con deportistas mayores. Es normal que el puesto baje al comienzo.",
      );
    });
  });

  it("audience=coach (default): no muestra el aviso de familia", () => {
    renderTable(
      <HistoryTable
        points={[
          makeRaceHistoryPoint({
            event_id: 41,
            season: 2025,
            category_changed: true,
            previous_category_label: "INFANTIL B",
            category_change_kind: "promotion",
          }),
        ]}
      />,
    );
    expect(screen.queryByText(/cambió de categoría/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/subió de categoría/i)).not.toBeInTheDocument();
  });

  describe("audience=family — explicador de Percentil/Brecha (T083 MAJOR)", () => {
    it("presente en audience=family, ausente en audience=coach (default)", () => {
      const { rerender } = renderTable(
        <HistoryTable audience="family" points={[makeRaceHistoryPoint()]} />,
      );
      expect(
        screen.getByTestId("history-family-metrics-explainer"),
      ).toHaveTextContent(/percentil/i);
      expect(
        screen.getByTestId("history-family-metrics-explainer"),
      ).toHaveTextContent(/brecha a la mediana/i);
      // Nunca "el atleta" — la vista familiar dice "tu hijo o hija".
      expect(
        screen.getByTestId("history-family-metrics-explainer"),
      ).not.toHaveTextContent(/el atleta/i);

      rerender(
        <MemoryRouter>
          <HistoryTable points={[makeRaceHistoryPoint()]} />
        </MemoryRouter>,
      );
      expect(
        screen.queryByTestId("history-family-metrics-explainer"),
      ).not.toBeInTheDocument();
    });
  });

  describe("brecha a la mediana y a la 1.ª posición (2026-09-23)", () => {
    const point = () =>
      makeRaceHistoryPoint({
        event_id: 70,
        label: "Válida VII — Tuluá",
        gap_to_median_pct: 0,
        gap_to_winner_pct: 7.6,
      });

    it("coach: la tabla muestra ambas brechas con encabezados explícitos", () => {
      renderTable(<HistoryTable points={[point()]} />);
      const table = screen.getByTestId("history-table");
      expect(
        within(table).getByRole("columnheader", { name: "Brecha vs. mediana" }),
      ).toBeInTheDocument();
      expect(
        within(table).getByRole("columnheader", { name: "Brecha vs. 1.ª posición" }),
      ).toBeInTheDocument();
      expect(within(table).getByText("0.0 %")).toBeInTheDocument();
      expect(within(table).getByText("+7.6 %")).toBeInTheDocument();
      const mobile = screen.getByTestId("history-table-mobile");
      expect(within(mobile).getByText("+7.6 %")).toBeInTheDocument();
    });

    it("familia: solo la brecha a la mediana, nunca la de la ganadora", () => {
      renderTable(<HistoryTable points={[point()]} audience="family" />);
      expect(screen.queryByText(/Brecha vs\. 1\.ª posición/)).not.toBeInTheDocument();
      expect(screen.queryByText("+7.6 %")).not.toBeInTheDocument();
      const table = screen.getByTestId("history-table");
      expect(
        within(table).getByRole("columnheader", { name: "Brecha vs. mediana" }),
      ).toBeInTheDocument();
    });
  });

  describe("el nombre de la válida enlaza a la competencia (2026-09-23)", () => {
    it("coach (default): enlaza a /competitions/:event_id en desktop y mobile, con área táctil ≥48px en mobile", () => {
      renderTable(
        <HistoryTable
          points={[
            makeRaceHistoryPoint({ event_id: 55, label: "Válida V — Roldanillo" }),
          ]}
        />,
      );

      const table = screen.getByTestId("history-table");
      const desktopLink = within(table).getByRole("link", {
        name: "Válida V — Roldanillo",
      });
      expect(desktopLink).toHaveAttribute("href", "/competitions/55");

      const mobile = screen.getByTestId("history-table-mobile");
      const mobileLink = within(mobile).getByRole("link", {
        name: "Válida V — Roldanillo",
      });
      expect(mobileLink).toHaveAttribute("href", "/competitions/55");
      // min-h-12 = 48px, el piso táctil mínimo de la Constitution en mobile.
      expect(mobileLink.className).toMatch(/min-h-12/);
    });

    it("familia: enlaza a /parents/competitions/:event_id en desktop y mobile", () => {
      renderTable(
        <HistoryTable
          audience="family"
          points={[
            makeRaceHistoryPoint({ event_id: 55, label: "Válida V — Roldanillo" }),
          ]}
        />,
      );

      const table = screen.getByTestId("history-table");
      expect(
        within(table).getByRole("link", { name: "Válida V — Roldanillo" }),
      ).toHaveAttribute("href", "/parents/competitions/55");

      const mobile = screen.getByTestId("history-table-mobile");
      expect(
        within(mobile).getByRole("link", { name: "Válida V — Roldanillo" }),
      ).toHaveAttribute("href", "/parents/competitions/55");
    });

    it("cada fila enlaza a su propio event_id, incluso dentro del mismo grupo", () => {
      renderTable(
        <HistoryTable
          points={[
            makeRaceHistoryPoint({ event_id: 41, label: "Válida 1 — Ginebra" }),
            makeRaceHistoryPoint({ event_id: 42, label: "Válida 2 — Buga" }),
          ]}
        />,
      );
      const table = screen.getByTestId("history-table");
      expect(
        within(table).getByRole("link", { name: "Válida 1 — Ginebra" }),
      ).toHaveAttribute("href", "/competitions/41");
      expect(
        within(table).getByRole("link", { name: "Válida 2 — Buga" }),
      ).toHaveAttribute("href", "/competitions/42");
    });
  });

  describe("vista mobile (T083 BLOCKER) — tarjetas apiladas, mismos datos que la tabla desktop", () => {
    it("una tarjeta por resultado con Puesto/Percentil/Parrilla/Brecha", () => {
      renderTable(
        <HistoryTable
          points={[
            makeRaceHistoryPoint({
              event_id: 41,
              label: "Válida 1 — Ginebra",
              position: 9,
              field_size: 23,
              percentile: 63.6,
              gap_to_median_pct: -4.2,
            }),
          ]}
        />,
      );
      const mobile = screen.getByTestId("history-table-mobile");
      expect(within(mobile).getByText("Válida 1 — Ginebra")).toBeInTheDocument();
      expect(within(mobile).getByText("9°")).toBeInTheDocument();
      expect(within(mobile).getByText("P64")).toBeInTheDocument();
      expect(within(mobile).getByText("-4.2 %")).toBeInTheDocument();
      // Velocidad ya no es una métrica de esta vista (retirada 2026-09-22).
      expect(within(mobile).queryByText(/km\/h/)).not.toBeInTheDocument();
    });

    it("agrupa por temporada → categoría igual que la tabla, con el mismo encabezado de grupo", () => {
      renderTable(
        <HistoryTable
          points={[
            makeRaceHistoryPoint({
              event_id: 30,
              season: 2024,
              category_label: "INFANTIL B",
              category_changed: false,
            }),
            makeRaceHistoryPoint({
              event_id: 41,
              season: 2025,
              category_label: "PREJUVENIL A",
              category_changed: true,
              previous_category_label: "INFANTIL B",
            }),
          ]}
        />,
      );
      const mobile = screen.getByTestId("history-table-mobile");
      expect(within(mobile).getByText("2024 · INFANTIL B")).toBeInTheDocument();
      expect(within(mobile).getByText("2025 · PREJUVENIL A")).toBeInTheDocument();
    });

    it("audience=family: la nota de cambio de categoría también aparece en la vista mobile", () => {
      renderTable(
        <HistoryTable
          audience="family"
          points={[
            makeRaceHistoryPoint({
              event_id: 41,
              season: 2025,
              category_changed: true,
              previous_category_label: "INFANTIL B",
              category_change_kind: "promotion",
            }),
          ]}
        />,
      );
      const mobile = screen.getByTestId("history-table-mobile");
      expect(within(mobile).getByText(/subió de categoría/i)).toBeInTheDocument();
    });

    it("no tiene overflow horizontal propio — la lista de tarjetas no es una tabla ancha", () => {
      renderTable(<HistoryTable points={[makeRaceHistoryPoint()]} />);
      const mobile = screen.getByTestId("history-table-mobile");
      expect(mobile.tagName).toBe("UL");
      expect(mobile.querySelector("table")).toBeNull();
    });
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = renderTable(
      <HistoryTable points={[makeRaceHistoryPoint()]} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de accesibilidad en audience=family (explicador + aviso de categoría)", async () => {
    const { container } = renderTable(
      <HistoryTable
        audience="family"
        points={[
          makeRaceHistoryPoint({
            event_id: 41,
            category_changed: true,
            previous_category_label: "INFANTIL B",
            category_change_kind: "promotion",
          }),
        ]}
      />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
