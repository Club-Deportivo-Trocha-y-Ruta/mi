import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import {
  SiblingViewTabs,
  type SiblingViewTabsItem,
} from "@/components/layout/SiblingViewTabs";

const ITEMS: SiblingViewTabsItem[] = [
  { label: "Calendario", to: "/calendar" },
  { label: "Sesiones", to: "/training/sessions" },
  { label: "Actividades", to: "/activities" },
];

function renderTabs(pathname: string) {
  return render(
    <MemoryRouter initialEntries={[pathname]}>
      <SiblingViewTabs items={ITEMS} />
    </MemoryRouter>,
  );
}

describe("SiblingViewTabs", () => {
  // ---------------------------------------------------------------------
  // Pastilla activa refleja la ruta actual
  // ---------------------------------------------------------------------
  describe("pastilla activa", () => {
    it("marca 'Calendario' como activa en /calendar", () => {
      renderTabs("/calendar");
      const active = screen.getByRole("tab", { name: "Calendario" });
      expect(active).toHaveAttribute("data-state", "active");
      expect(active).toHaveAttribute("aria-current", "page");

      expect(
        screen.getByRole("tab", { name: "Sesiones" }),
      ).toHaveAttribute("data-state", "inactive");
      expect(
        screen.getByRole("tab", { name: "Actividades" }),
      ).toHaveAttribute("data-state", "inactive");
    });

    it("marca 'Sesiones' como activa en /training/sessions", () => {
      renderTabs("/training/sessions");
      expect(
        screen.getByRole("tab", { name: "Sesiones" }),
      ).toHaveAttribute("data-state", "active");
      expect(
        screen.getByRole("tab", { name: "Calendario" }),
      ).toHaveAttribute("data-state", "inactive");
    });

    it("marca 'Actividades' como activa en una subruta de /activities", () => {
      renderTabs("/activities");
      expect(
        screen.getByRole("tab", { name: "Actividades" }),
      ).toHaveAttribute("data-state", "active");
    });

    it("ninguna pastilla queda activa cuando la ruta no pertenece al grupo", () => {
      renderTabs("/dashboard");
      for (const item of ITEMS) {
        expect(
          screen.getByRole("tab", { name: item.label }),
        ).toHaveAttribute("data-state", "inactive");
      }
    });
  });

  // ---------------------------------------------------------------------
  // Operabilidad por teclado heredada de @radix-ui/react-tabs
  // ---------------------------------------------------------------------
  describe("navegación por teclado", () => {
    it("mueve el foco con las flechas (roving tabindex de Radix)", async () => {
      const user = userEvent.setup();
      renderTabs("/calendar");

      const calendario = screen.getByRole("tab", { name: "Calendario" });
      const sesiones = screen.getByRole("tab", { name: "Sesiones" });
      const actividades = screen.getByRole("tab", { name: "Actividades" });

      calendario.focus();
      expect(calendario).toHaveFocus();

      await user.keyboard("{ArrowRight}");
      expect(sesiones).toHaveFocus();

      await user.keyboard("{ArrowRight}");
      expect(actividades).toHaveFocus();

      // Home vuelve a la primera pastilla, End a la última — mecánica
      // estándar de Radix Tabs (roving tabindex), no reimplementada aquí.
      await user.keyboard("{Home}");
      expect(calendario).toHaveFocus();

      await user.keyboard("{End}");
      expect(actividades).toHaveFocus();
    });

    it("Tab desde fuera del grupo enfoca la pastilla activa primero (roving tabindex)", async () => {
      const user = userEvent.setup();
      render(
        <MemoryRouter initialEntries={["/training/sessions"]}>
          <button type="button">Antes</button>
          <SiblingViewTabs items={ITEMS} />
        </MemoryRouter>,
      );

      const before = screen.getByRole("button", { name: "Antes" });
      const sesiones = screen.getByRole("tab", { name: "Sesiones" });
      const calendario = screen.getByRole("tab", { name: "Calendario" });

      before.focus();
      await user.tab();

      expect(sesiones).toHaveFocus();
      expect(sesiones).toHaveAttribute("tabIndex", "0");
      expect(calendario).toHaveAttribute("tabIndex", "-1");
    });
  });

  // ---------------------------------------------------------------------
  // Estructura: fila de ancho completo, no un slot de acciones
  // ---------------------------------------------------------------------
  describe("estructura de layout", () => {
    it("la raíz es una fila de ancho completo (w-full), no un botón/acción alineado a la derecha", () => {
      const { container } = renderTabs("/calendar");
      const root = container.firstElementChild as HTMLElement;
      expect(root.className).toMatch(/\bw-full\b/);
    });

    it("expone un único tablist accesible con las 3 vistas hermanas", () => {
      renderTabs("/calendar");
      const tablist = screen.getByRole("tablist", {
        name: "Vistas relacionadas",
      });
      expect(tablist).toBeInTheDocument();
      expect(screen.getAllByRole("tab")).toHaveLength(ITEMS.length);
    });

    it("acepta un aria-label personalizado sin perder el rol tablist", () => {
      render(
        <MemoryRouter initialEntries={["/calendar"]}>
          <SiblingViewTabs items={ITEMS} aria-label="Vistas de entrenamiento" />
        </MemoryRouter>,
      );
      expect(
        screen.getByRole("tablist", { name: "Vistas de entrenamiento" }),
      ).toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------
  // Navegación real vía NavLink
  // ---------------------------------------------------------------------
  it("cada pastilla apunta a su ruta real (href) para navegación de página completa", () => {
    renderTabs("/calendar");
    expect(screen.getByRole("tab", { name: "Calendario" })).toHaveAttribute(
      "href",
      "/calendar",
    );
    expect(screen.getByRole("tab", { name: "Sesiones" })).toHaveAttribute(
      "href",
      "/training/sessions",
    );
    expect(screen.getByRole("tab", { name: "Actividades" })).toHaveAttribute(
      "href",
      "/activities",
    );
  });
});
