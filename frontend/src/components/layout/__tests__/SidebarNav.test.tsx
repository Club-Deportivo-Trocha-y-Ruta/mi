import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";

import { SidebarNav } from "@/components/layout/SidebarNav";
import type { NavRole } from "@/lib/navigation";

// T015 [US1] — role-filtered rendering, active-area auto-expand, the
// label-vs-chevron control split, and manual expand/collapse of a
// non-active group. Per data-model.md §3 and contracts/navigation-model.md.

function LocationDisplay() {
  const { pathname } = useLocation();
  return <div data-testid="location">{pathname}</div>;
}

function renderSidebar(role: NavRole, initialPath = "/dashboard") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <SidebarNav role={role} />
      <LocationDisplay />
    </MemoryRouter>,
  );
}

describe("SidebarNav — filtrado por rol (data-model.md §3)", () => {
  it("coach ve el área Atletas (Todos, Ansiedad competitiva)", () => {
    renderSidebar("coach");
    expect(screen.getByText("Atletas")).toBeInTheDocument();
  });

  it("admin NO ve el área Atletas en absoluto", () => {
    renderSidebar("admin");
    expect(screen.queryByText("Atletas")).not.toBeInTheDocument();
  });

  it("coach ve la etiqueta de área Familias resolviendo a Padres (/parents)", () => {
    renderSidebar("coach");
    const label = screen.getByRole("link", { name: /Familias/ });
    expect(label).toHaveAttribute("href", "/parents");
  });

  it("admin ve la etiqueta de área Familias resolviendo a Boletines (no /parents)", () => {
    renderSidebar("admin");
    const label = screen.getByRole("link", { name: /Familias/ });
    expect(label).toHaveAttribute("href", "/training/athlete-newsletters");
  });

  it("coach y admin ven Inicio, Entrenamiento, Competencias, Biblioteca", () => {
    for (const role of ["coach", "admin"] as NavRole[]) {
      const { unmount } = renderSidebar(role);
      expect(screen.getByText("Inicio")).toBeInTheDocument();
      expect(screen.getByText("Entrenamiento")).toBeInTheDocument();
      expect(screen.getByText("Competencias")).toBeInTheDocument();
      expect(screen.getByText("Biblioteca")).toBeInTheDocument();
      unmount();
    }
  });

  it("Inicio (área de un solo item) se renderiza como link plano, sin chevron de disclosure", () => {
    renderSidebar("coach");
    const inicioLink = screen.getByRole("link", { name: "Inicio" });
    expect(inicioLink).toHaveAttribute("href", "/dashboard");
    expect(
      screen.queryByRole("button", { name: /Inicio/ }),
    ).not.toBeInTheDocument();
  });
});

describe("SidebarNav — auto-expand del área activa en deep link", () => {
  it("un deep link a /anxiety expande Atletas y muestra sus items", () => {
    renderSidebar("coach", "/anxiety");

    const chevron = screen.getByRole("button", { name: /Atletas/ });
    expect(chevron).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "Todos" })).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Ansiedad competitiva" }),
    ).toBeInTheDocument();
  });

  it("un grupo no activo permanece colapsado (sus items no están en el DOM)", () => {
    renderSidebar("coach", "/anxiety");

    // Entrenamiento no es el área activa en /anxiety.
    const chevron = screen.getByRole("button", { name: /Entrenamiento/ });
    expect(chevron).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.queryByRole("link", { name: "Calendario" }),
    ).not.toBeInTheDocument();
  });
});

describe("SidebarNav — separación label (navega) vs. chevron (solo disclosure)", () => {
  it("hacer click en la etiqueta del área navega a su ruta por defecto resuelta", async () => {
    const user = userEvent.setup();
    renderSidebar("coach", "/dashboard");

    const label = screen.getByRole("link", { name: /Entrenamiento/ });
    expect(label).toHaveAttribute("href", "/calendar");

    await user.click(label);

    expect(screen.getByTestId("location")).toHaveTextContent("/calendar");
  });

  it("hacer click en el chevron NO navega — solo alterna aria-expanded", async () => {
    const user = userEvent.setup();
    renderSidebar("coach", "/dashboard");

    const chevron = screen.getByRole("button", { name: /Entrenamiento/ });
    expect(chevron).toHaveAttribute("aria-expanded", "false");

    await user.click(chevron);

    expect(chevron).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("location")).toHaveTextContent("/dashboard");
  });
});

describe("SidebarNav — expandir/colapsar manualmente un grupo no activo", () => {
  it("el chevron de un grupo inactivo lo expande, revelando sus items", async () => {
    const user = userEvent.setup();
    renderSidebar("coach", "/dashboard");

    expect(
      screen.queryByRole("link", { name: "Sesiones" }),
    ).not.toBeInTheDocument();

    const chevron = screen.getByRole("button", { name: /Entrenamiento/ });
    await user.click(chevron);

    expect(screen.getByRole("link", { name: "Calendario" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sesiones" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Actividades" })).toBeInTheDocument();
  });

  it("un segundo click en el mismo chevron vuelve a colapsar el grupo", async () => {
    const user = userEvent.setup();
    renderSidebar("coach", "/dashboard");

    const chevron = screen.getByRole("button", { name: /Entrenamiento/ });
    await user.click(chevron);
    expect(chevron).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "Sesiones" })).toBeInTheDocument();

    await user.click(chevron);
    expect(chevron).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.queryByRole("link", { name: "Sesiones" }),
    ).not.toBeInTheDocument();
  });

  it("expandir manualmente un grupo no altera el estado del área activa", async () => {
    const user = userEvent.setup();
    renderSidebar("coach", "/anxiety");

    const inactiveChevron = screen.getByRole("button", {
      name: /Entrenamiento/,
    });
    await user.click(inactiveChevron);
    expect(inactiveChevron).toHaveAttribute("aria-expanded", "true");

    // Atletas sigue expandido porque sigue siendo el área activa.
    const activeChevron = screen.getByRole("button", { name: /Atletas/ });
    expect(activeChevron).toHaveAttribute("aria-expanded", "true");
  });
});
