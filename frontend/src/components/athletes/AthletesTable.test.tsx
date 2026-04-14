import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AthletesTable } from "./AthletesTable";
import type { AthleteRow } from "./AthletesTable";
import { MaturationStatus, Sex } from "@/types/enums";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeRow(overrides?: Partial<AthleteRow>): AthleteRow {
  return {
    id: 1,
    user_id: 10,
    first_name: "Sebastián",
    last_name: "García",
    birth_date: "2013-06-15",
    sex: Sex.M,
    club_join_date: "2024-01-01",
    years_in_club: 2.3,
    age_decimal: 12.8,
    category: "Pre-juvenil A",
    club_id: 1,
    created_at: "2026-01-01T00:00:00Z",
    latest_maturation_status: MaturationStatus.CircaPHV,
    ...overrides,
  };
}

const rowA = makeRow({ id: 1, first_name: "Sebastián", last_name: "García" });
const rowB = makeRow({
  id: 2,
  first_name: "Laura",
  last_name: "Martínez",
  sex: Sex.F,
  category: null,
  latest_maturation_status: null,
  age_decimal: null,
});

// Helper para renderizar con MemoryRouter (AthletesTable usa <Link>)
function renderTable(items: AthleteRow[]) {
  return render(
    <MemoryRouter>
      <AthletesTable items={items} />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AthletesTable", () => {
  // -------------------------------------------------------------------------
  // Encabezados de la tabla
  // -------------------------------------------------------------------------
  describe("encabezados de la tabla", () => {
    it("debería renderizar el encabezado 'Nombre'", () => {
      renderTable([rowA]);
      expect(screen.getByText("Nombre")).toBeInTheDocument();
    });

    it("debería renderizar el encabezado 'Edad'", () => {
      renderTable([rowA]);
      expect(screen.getByText("Edad")).toBeInTheDocument();
    });

    it("debería renderizar el encabezado 'Sexo'", () => {
      renderTable([rowA]);
      expect(screen.getByText("Sexo")).toBeInTheDocument();
    });

    it("debería renderizar el encabezado 'Categoria'", () => {
      renderTable([rowA]);
      expect(screen.getByText("Categoria")).toBeInTheDocument();
    });

    it("debería renderizar el encabezado 'Estado PHV'", () => {
      renderTable([rowA]);
      expect(screen.getByText("Estado PHV")).toBeInTheDocument();
    });

    it("debería renderizar el encabezado 'Acciones'", () => {
      renderTable([rowA]);
      expect(screen.getByText("Acciones")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Filas con datos
  // -------------------------------------------------------------------------
  describe("cuando hay atletas en la lista", () => {
    it("debería mostrar el nombre completo del atleta como enlace", () => {
      renderTable([rowA]);
      const link = screen.getByRole("link", { name: "Sebastián García" });
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute("href", "/athletes/1");
    });

    it("debería mostrar la edad decimal con 1 decimal", () => {
      renderTable([rowA]);
      expect(screen.getByText(/12\.8/)).toBeInTheDocument();
    });

    it("debería mostrar '-' cuando age_decimal es null", () => {
      renderTable([rowB]);
      // La celda renderiza "- anos"
      expect(screen.getByText(/- anos/)).toBeInTheDocument();
    });

    it("debería mostrar el sexo del atleta", () => {
      renderTable([rowA]);
      expect(screen.getByText("M")).toBeInTheDocument();
    });

    it("debería mostrar la categoría del atleta", () => {
      renderTable([rowA]);
      expect(screen.getByText("Pre-juvenil A")).toBeInTheDocument();
    });

    it("debería mostrar 'Sin categoria' cuando category es null", () => {
      renderTable([rowB]);
      expect(screen.getByText("Sin categoria")).toBeInTheDocument();
    });

    it("debería mostrar el badge del estado PHV", () => {
      renderTable([rowA]);
      expect(screen.getByText(MaturationStatus.CircaPHV)).toBeInTheDocument();
    });

    it("debería mostrar 'Sin evaluar' cuando latest_maturation_status es null", () => {
      renderTable([rowB]);
      expect(screen.getByText("Sin evaluar")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Acciones (links Ver / Editar)
  // -------------------------------------------------------------------------
  describe("acciones de cada fila", () => {
    it("debería mostrar el link 'Ver' apuntando al detalle del atleta", () => {
      renderTable([rowA]);
      const verLinks = screen.getAllByRole("link", { name: "Ver" });
      expect(verLinks[0]).toHaveAttribute("href", "/athletes/1");
    });

    it("debería mostrar el link 'Editar' apuntando a la edición del atleta", () => {
      renderTable([rowA]);
      const editLinks = screen.getAllByRole("link", { name: "Editar" });
      expect(editLinks[0]).toHaveAttribute("href", "/athletes/1/edit");
    });
  });

  // -------------------------------------------------------------------------
  // Lista vacía
  // -------------------------------------------------------------------------
  describe("cuando la lista está vacía", () => {
    it("debería renderizar la tabla sin filas de datos", () => {
      renderTable([]);
      // Encabezados siguen presentes
      expect(screen.getByText("Nombre")).toBeInTheDocument();
      // Sin filas de datos — no hay ningún link a atleta
      expect(screen.queryByRole("link", { name: /Sebastián/i })).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Múltiples atletas
  // -------------------------------------------------------------------------
  describe("cuando hay múltiples atletas", () => {
    it("debería renderizar una fila por cada atleta", () => {
      renderTable([rowA, rowB]);
      expect(screen.getByText("Sebastián García")).toBeInTheDocument();
      expect(screen.getByText("Laura Martínez")).toBeInTheDocument();
    });

    it("debería tener links únicos para cada atleta", () => {
      renderTable([rowA, rowB]);
      // rowA → /athletes/1, rowB → /athletes/2
      const nameLinks = screen.getAllByRole("link", { name: /García|Martínez/ });
      const hrefs = nameLinks.map((l) => l.getAttribute("href"));
      expect(hrefs).toContain("/athletes/1");
      expect(hrefs).toContain("/athletes/2");
    });
  });
});
