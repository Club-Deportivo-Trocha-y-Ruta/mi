import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { axe } from "jest-axe";

import { ParentBottomNav } from "@/components/parents/ParentBottomNav";

// Feature 035 — ParentBottomNav (mockup PadresInicio.dc.html). Cinco slots
// fijos (sin "Más"), resolución de activo exact-match/longest-prefix
// (mismo algoritmo que resolveActiveItemId, reimplementado localmente) y
// tamaño táctil >=48px.

function renderBottomNav(initialPath = "/my-athletes") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <ParentBottomNav />
    </MemoryRouter>,
  );
}

describe("ParentBottomNav — estructura", () => {
  it("renderiza los cinco slots en el orden del mockup con sus rutas", () => {
    renderBottomNav();

    const nav = screen.getByRole("navigation", { name: "Navegación principal" });
    const links = Array.from(nav.querySelectorAll("a"));

    expect(links.map((a) => a.textContent?.trim())).toEqual([
      "Inicio",
      "Calendario",
      "Entrenos",
      "Resumen",
      "Perfil",
    ]);
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "/my-athletes",
      "/parents/calendar",
      "/parents/training/sessions",
      "/parents/training/overview",
      "/perfil",
    ]);
  });

  it("no renderiza un disparador 'Más' (los 5 slots caben)", () => {
    renderBottomNav();
    expect(screen.queryByRole("button", { name: /Más/ })).not.toBeInTheDocument();
  });
});

describe("ParentBottomNav — resolución de activo", () => {
  it("/my-athletes marca 'Inicio' activo", () => {
    renderBottomNav("/my-athletes");
    expect(screen.getByRole("link", { name: "Inicio" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("una subruta de detalle (/my-athletes/42) mantiene 'Inicio' activo", () => {
    renderBottomNav("/my-athletes/42");
    expect(screen.getByRole("link", { name: "Inicio" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("/parents/calendar marca 'Calendario' activo", () => {
    renderBottomNav("/parents/calendar");
    expect(screen.getByRole("link", { name: "Calendario" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("/parents/training/sessions marca 'Entrenos' activo", () => {
    renderBottomNav("/parents/training/sessions");
    expect(screen.getByRole("link", { name: "Entrenos" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("/parents/training/overview marca 'Resumen' activo y NUNCA 'Entrenos' (caso de anidación)", () => {
    renderBottomNav("/parents/training/overview");

    expect(screen.getByRole("link", { name: "Resumen" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "Entrenos" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("/perfil marca 'Perfil' activo", () => {
    renderBottomNav("/perfil");
    expect(screen.getByRole("link", { name: "Perfil" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("los slots inactivos no tienen aria-current", () => {
    renderBottomNav("/parents/calendar");

    for (const label of ["Inicio", "Entrenos", "Resumen", "Perfil"]) {
      expect(screen.getByRole("link", { name: label })).not.toHaveAttribute(
        "aria-current",
      );
    }
  });
});

describe("ParentBottomNav — reparto de color del estado activo", () => {
  it("el acento va en el ícono; el label activo se queda en charcoal semibold", () => {
    renderBottomNav("/parents/calendar");

    const active = screen.getByRole("link", { name: "Calendario" });
    // El acento (#008492) sobre blanco da 4.45:1 y no llega al piso AA de
    // 4.5:1 para texto normal — el label no puede llevarlo (mismo reparto
    // que SidebarNav). El peso semibold sigue diferenciándolo.
    expect(active.className).toMatch(/font-semibold/);
    expect(active.className).toMatch(/text-charcoal/);
    expect(active.className).not.toMatch(/text-nav-accent/);
    expect(active.querySelector("svg")?.getAttribute("class")).toMatch(/text-nav-accent/);
  });

  it("el ícono de un slot inactivo no lleva el acento", () => {
    renderBottomNav("/parents/calendar");

    const inactive = screen.getByRole("link", { name: "Inicio" });
    expect(inactive.querySelector("svg")?.getAttribute("class")).not.toMatch(
      /text-nav-accent/,
    );
  });
});

describe("ParentBottomNav — tamaño de objetivo táctil (>=48px)", () => {
  it("cada slot tiene min-h-[48px]", () => {
    renderBottomNav();

    for (const label of ["Inicio", "Calendario", "Entrenos", "Resumen", "Perfil"]) {
      const link = screen.getByRole("link", { name: label });
      expect(link.className).toMatch(/min-h-\[48px\]/);
    }
  });
});

describe("ParentBottomNav — accesibilidad", () => {
  it("sin violaciones axe", async () => {
    const { container } = renderBottomNav();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
