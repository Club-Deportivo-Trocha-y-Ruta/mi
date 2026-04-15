import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ParentsTable } from "../ParentsTable";
import type { UserOut } from "@/types/user.types";
import { UserRole } from "@/types/enums";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeParent(overrides?: Partial<UserOut>): UserOut {
  return {
    id: 1,
    email: "carlos.garcia@example.com",
    first_name: "Carlos",
    last_name: "García",
    phone: "+57 300 123 4567",
    role: UserRole.parent,
    is_active: true,
    can_login: true,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

const parentA = makeParent({ id: 1, first_name: "Carlos", last_name: "García" });
const parentB = makeParent({
  id: 2,
  first_name: "María",
  last_name: "Rodríguez",
  email: "maria.rodriguez@example.com",
});

function renderTable(items: UserOut[]) {
  return render(
    <MemoryRouter>
      <ParentsTable items={items} />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ParentsTable", () => {
  // -------------------------------------------------------------------------
  // Filas con datos
  // -------------------------------------------------------------------------
  describe("cuando hay padres en la lista", () => {
    it("debería renderizar el nombre y email de cada padre", () => {
      renderTable([parentA, parentB]);
      expect(screen.getByText("Carlos García")).toBeInTheDocument();
      expect(screen.getByText("carlos.garcia@example.com")).toBeInTheDocument();
      expect(screen.getByText("María Rodríguez")).toBeInTheDocument();
      expect(screen.getByText("maria.rodriguez@example.com")).toBeInTheDocument();
    });

    it("el link 'Ver' de cada fila debe apuntar a /parents/{id}", () => {
      renderTable([parentA, parentB]);
      const verLinks = screen.getAllByRole("link", { name: "Ver" });
      const hrefs = verLinks.map((l) => l.getAttribute("href"));
      expect(hrefs).toContain("/parents/1");
      expect(hrefs).toContain("/parents/2");
    });
  });

  // -------------------------------------------------------------------------
  // Lista vacía
  // -------------------------------------------------------------------------
  describe("cuando la lista está vacía", () => {
    it("debería renderizar la tabla sin filas de datos", () => {
      renderTable([]);
      // Los encabezados siguen presentes
      expect(screen.getByText("Nombre")).toBeInTheDocument();
      // No hay ningún enlace "Ver"
      expect(screen.queryByRole("link", { name: "Ver" })).not.toBeInTheDocument();
    });
  });
});
