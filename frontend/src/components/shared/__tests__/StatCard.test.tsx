import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { axe, toHaveNoViolations } from "jest-axe";
import { StatCard } from "../StatCard";

expect.extend(toHaveNoViolations);

function renderStatCard(props: Parameters<typeof StatCard>[0]) {
  return render(
    <MemoryRouter>
      <StatCard {...props} />
    </MemoryRouter>,
  );
}

describe("StatCard", () => {
  // -------------------------------------------------------------------------
  // Contenido básico
  // -------------------------------------------------------------------------
  describe("contenido básico", () => {
    it("debería renderizar el label y el value", () => {
      renderStatCard({ label: "Atletas activos", value: 24 });
      expect(screen.getByText("Atletas activos")).toBeInTheDocument();
      expect(screen.getByText("24")).toBeInTheDocument();
    });

    it("debería renderizar el hint cuando se pasa", () => {
      renderStatCard({ label: "Atletas activos", value: 24, hint: "Últimos 30 días" });
      expect(screen.getByText("Últimos 30 días")).toBeInTheDocument();
    });

    it("no debería renderizar ningún hint cuando no se pasa", () => {
      const { container } = renderStatCard({ label: "Atletas activos", value: 24 });
      // Sin hint sólo deben existir dos <p>: label y value.
      expect(container.querySelectorAll("p")).toHaveLength(2);
    });
  });

  // -------------------------------------------------------------------------
  // isLoading
  // -------------------------------------------------------------------------
  describe("isLoading", () => {
    it("debería mostrar un skeleton en lugar del value cuando isLoading es true", () => {
      const { container } = renderStatCard({
        label: "Atletas activos",
        value: 24,
        isLoading: true,
      });
      expect(screen.queryByText("24")).not.toBeInTheDocument();
      expect(container.querySelector('[aria-hidden="true"]')).toBeInTheDocument();
    });

    it("debería seguir mostrando el label cuando isLoading es true", () => {
      renderStatCard({ label: "Atletas activos", value: 24, isLoading: true });
      expect(screen.getByText("Atletas activos")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // href
  // -------------------------------------------------------------------------
  describe("href", () => {
    it("debería renderizar como link con el href correcto cuando se pasa href", () => {
      renderStatCard({ label: "Atletas activos", value: 24, href: "/athletes" });
      const link = screen.getByRole("link");
      expect(link).toHaveAttribute("href", "/athletes");
    });

    it("debería incluir el label y el value dentro del link", () => {
      renderStatCard({ label: "Atletas activos", value: 24, href: "/athletes" });
      const link = screen.getByRole("link");
      expect(link).toHaveTextContent("Atletas activos");
      expect(link).toHaveTextContent("24");
    });

    it("no debería renderizar ningún link cuando href no se pasa", () => {
      renderStatCard({ label: "Atletas activos", value: 24 });
      expect(screen.queryByRole("link")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Accesibilidad
  // -------------------------------------------------------------------------
  describe("accesibilidad", () => {
    it("no debería tener violaciones jest-axe en el estado por defecto", async () => {
      const { container } = renderStatCard({
        label: "Atletas activos",
        value: 24,
        hint: "Últimos 30 días",
      });
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("no debería tener violaciones jest-axe cuando isLoading es true", async () => {
      const { container } = renderStatCard({
        label: "Atletas activos",
        value: 24,
        isLoading: true,
      });
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("no debería tener violaciones jest-axe cuando href está presente", async () => {
      const { container } = renderStatCard({
        label: "Atletas activos",
        value: 24,
        href: "/athletes",
      });
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });
});
