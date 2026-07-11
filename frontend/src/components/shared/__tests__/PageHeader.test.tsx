import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { axe, toHaveNoViolations } from "jest-axe";
import { PageHeader } from "../PageHeader";

expect.extend(toHaveNoViolations);

function renderHeader(props: Parameters<typeof PageHeader>[0]) {
  return render(
    <MemoryRouter>
      <PageHeader {...props} />
    </MemoryRouter>,
  );
}

describe("PageHeader", () => {
  // -------------------------------------------------------------------------
  // Título
  // -------------------------------------------------------------------------
  describe("título", () => {
    it("debería renderizar el título como encabezado h1", () => {
      renderHeader({ title: "Atletas" });
      const heading = screen.getByRole("heading", { level: 1, name: "Atletas" });
      expect(heading).toBeInTheDocument();
      expect(heading.tagName).toBe("H1");
    });

    it("debería incluir la clase font-display en el título", () => {
      renderHeader({ title: "Atletas" });
      const heading = screen.getByRole("heading", { level: 1, name: "Atletas" });
      expect(heading.className).toContain("font-display");
    });
  });

  // -------------------------------------------------------------------------
  // Subtítulo
  // -------------------------------------------------------------------------
  describe("subtítulo", () => {
    it("debería mostrar el subtítulo cuando se pasa", () => {
      renderHeader({ title: "Atletas", subtitle: "Gestiona el roster del club" });
      expect(screen.getByText("Gestiona el roster del club")).toBeInTheDocument();
    });

    it("no debería renderizar ningún subtítulo cuando no se pasa", () => {
      const { container } = renderHeader({ title: "Atletas" });
      // Sin subtitle no debe existir ningún párrafo en el encabezado.
      expect(container.querySelector("p")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Back link
  // -------------------------------------------------------------------------
  describe("backTo", () => {
    it("debería renderizar el back link con href y label correctos cuando se pasa", () => {
      renderHeader({
        title: "Detalle",
        backTo: { to: "/competitions", label: "Competencias" },
      });
      const link = screen.getByRole("link", { name: /Competencias/ });
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute("href", "/competitions");
      expect(link).toHaveTextContent("Competencias");
    });

    it("no debería renderizar ningún link cuando backTo no se pasa", () => {
      renderHeader({ title: "Detalle" });
      expect(screen.queryByRole("link")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Actions
  // -------------------------------------------------------------------------
  describe("actions", () => {
    it("debería renderizar el contenido de actions cuando se pasa", () => {
      renderHeader({
        title: "Sesiones",
        actions: <button type="button">+ Nueva sesión</button>,
      });
      expect(screen.getByRole("button", { name: "+ Nueva sesión" })).toBeInTheDocument();
    });

    it("no debería renderizar el contenedor de actions cuando no se pasa", () => {
      renderHeader({ title: "Sesiones" });
      expect(screen.queryByRole("button")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Accesibilidad
  // -------------------------------------------------------------------------
  describe("accesibilidad", () => {
    it("no debería tener violaciones jest-axe solo con título", async () => {
      const { container } = renderHeader({ title: "Atletas" });
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("no debería tener violaciones jest-axe con todos los props presentes", async () => {
      const { container } = renderHeader({
        title: "Detalle de competencia",
        subtitle: "Ginebra · 12 jun 2026",
        backTo: { to: "/competitions", label: "Competencias" },
        actions: (
          <button type="button" aria-label="Editar competencia">
            Editar
          </button>
        ),
      });
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });
});
