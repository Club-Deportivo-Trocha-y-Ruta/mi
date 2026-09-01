import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { MemoryRouter, useLocation } from "react-router-dom";

// Las insignias salen de queries reales (`useNavBadges` → race-events +
// resumen de boletines). Aquí se mockea el hook para controlar los conteos
// sin montar un QueryClientProvider ni tocar la red; su lógica de filtrado
// tiene pruebas propias en hooks/layout/__tests__/useNavBadges.test.tsx.
const badgeState = vi.hoisted(() => ({
  current: {} as { competitions?: number; families?: number },
}));

vi.mock("@/hooks/layout/useNavBadges", () => ({
  useNavBadges: () => badgeState.current,
}));

import { SidebarNav } from "@/components/layout/SidebarNav";
import type { NavRole } from "@/lib/navigation";

// T015 [US1] (feature 030) — filtrado por rol, auto-expand del área activa,
// separación etiqueta/chevron y expand/collapse manual de un grupo inactivo.
// Feature 035 — grupos con overline, estado activo con tinte + barra,
// insignias de pendientes y modo riel de 72px.

function LocationDisplay() {
  const { pathname } = useLocation();
  return <div data-testid="location">{pathname}</div>;
}

interface RenderOptions {
  initialPath?: string;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  footer?: React.ReactNode;
}

function renderSidebar(
  role: NavRole,
  {
    initialPath = "/dashboard",
    collapsed = false,
    onToggleCollapsed = () => {},
    footer,
  }: RenderOptions = {},
) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <SidebarNav
        role={role}
        collapsed={collapsed}
        onToggleCollapsed={onToggleCollapsed}
        footer={footer}
      />
      <LocationDisplay />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  badgeState.current = {};
});

describe("SidebarNav — filtrado por rol (data-model.md §3)", () => {
  it("coach ve el área Atletas (Todos)", () => {
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

// ---------------------------------------------------------------------------
// Feature 035 — marca, grupos y estado activo
// ---------------------------------------------------------------------------

describe("SidebarNav — marca y grupos con overline (feature 035)", () => {
  it("muestra la marca del club en el encabezado de la barra", () => {
    renderSidebar("coach");
    expect(screen.getByText("Trocha y Ruta")).toBeInTheDocument();
    expect(screen.getByText("Club Ciclismo XCO")).toBeInTheDocument();
  });

  it("renderiza los dos overlines de grupo: Operación y Club", () => {
    renderSidebar("coach");
    expect(screen.getByText("Operación")).toBeInTheDocument();
    expect(screen.getByText("Club")).toBeInTheDocument();
  });

  it("cada grupo es un contenedor con nombre accesible que agrupa sus áreas", () => {
    renderSidebar("coach");

    const operacion = screen.getByRole("group", { name: "Operación" });
    expect(
      within(operacion).getByRole("link", { name: "Inicio" }),
    ).toBeInTheDocument();
    expect(
      within(operacion).getByRole("link", { name: "Atletas" }),
    ).toBeInTheDocument();

    const club = screen.getByRole("group", { name: "Club" });
    expect(
      within(club).getByRole("link", { name: /Familias/ }),
    ).toBeInTheDocument();
    expect(
      within(club).queryByRole("link", { name: "Inicio" }),
    ).not.toBeInTheDocument();
  });

  it("admin no ve Atletas dentro de Operación pero sí el resto del grupo", () => {
    renderSidebar("admin");
    const operacion = screen.getByRole("group", { name: "Operación" });
    expect(
      within(operacion).getByRole("link", { name: /Competencias/ }),
    ).toBeInTheDocument();
    expect(
      within(operacion).queryByRole("link", { name: "Atletas" }),
    ).not.toBeInTheDocument();
  });
});

describe("SidebarNav — estado activo (tinte + barra + semibold, nunca sólo color)", () => {
  it("el área activa marca aria-current='page' y suma tinte, barra y semibold", () => {
    renderSidebar("coach", { initialPath: "/dashboard" });

    const inicio = screen.getByRole("link", { name: "Inicio" });
    expect(inicio).toHaveAttribute("aria-current", "page");
    expect(inicio.className).toMatch(/bg-nav-active-bg/);
    // Canales no cromáticos: peso tipográfico + barra indicadora de 3px.
    expect(inicio.className).toMatch(/font-semibold/);
    expect(inicio.querySelector("span[aria-hidden='true']")).not.toBeNull();
  });

  it("un área inactiva no lleva aria-current ni el tinte activo", () => {
    renderSidebar("coach", { initialPath: "/dashboard" });

    const competencias = screen.getByRole("link", { name: /Competencias/ });
    expect(competencias).not.toHaveAttribute("aria-current");
    expect(competencias.className).not.toMatch(/bg-nav-active-bg/);
  });

  it("el sub-item de la ruta actual queda marcado como página actual y en semibold", () => {
    renderSidebar("coach", { initialPath: "/competitions/unlinked" });

    const current = screen.getByRole("link", { name: "Sin enlazar" });
    expect(current).toHaveAttribute("aria-current", "page");
    expect(current.className).toMatch(/bg-nav-active-bg/);
    expect(current.className).toMatch(/font-semibold/);

    const sibling = screen.getByRole("link", { name: "Válidas" });
    expect(sibling).not.toHaveAttribute("aria-current");
    expect(sibling.className).not.toMatch(/bg-nav-active-bg/);
  });

  it("en /competitions/insights/season/2026 sólo 'Panorama de temporada' queda activo", () => {
    renderSidebar("coach", {
      initialPath: "/competitions/insights/season/2026",
    });

    expect(
      screen.getByRole("link", { name: "Panorama de temporada" }),
    ).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Válidas" })).not.toHaveAttribute(
      "aria-current",
    );
  });
});

describe("SidebarNav — insignias de pendientes (useNavBadges)", () => {
  it("muestra el conteo como píldora y lo anuncia en el nombre accesible del área", () => {
    badgeState.current = { competitions: 2, families: 3 };
    renderSidebar("coach");

    const competencias = screen.getByRole("link", { name: /Competencias/ });
    expect(within(competencias).getByText("2")).toBeInTheDocument();
    expect(competencias).toHaveAccessibleName("Competencias · 2 pendientes");

    const familias = screen.getByRole("link", { name: /Familias/ });
    expect(within(familias).getByText("3")).toBeInTheDocument();
    expect(familias).toHaveAccessibleName("Familias · 3 pendientes");
  });

  it("sin conteos no renderiza ninguna píldora (ni un '0')", () => {
    badgeState.current = {};
    renderSidebar("coach");

    const competencias = screen.getByRole("link", { name: /Competencias/ });
    expect(competencias).toHaveAccessibleName("Competencias");
    expect(within(competencias).queryByText("0")).not.toBeInTheDocument();
  });

  it("un área sin fuente de pendientes nunca lleva insignia", () => {
    badgeState.current = { competitions: 2, families: 3 };
    renderSidebar("coach");

    expect(screen.getByRole("link", { name: "Inicio" })).toHaveAccessibleName(
      "Inicio",
    );
  });
});

// ---------------------------------------------------------------------------
// Feature 030 — contratos de disclosure preservados
// ---------------------------------------------------------------------------

describe("SidebarNav — auto-expand del área activa en deep link", () => {
  it("un deep link a /competitions/unlinked expande Competencias y muestra sus items", () => {
    renderSidebar("coach", { initialPath: "/competitions/unlinked" });

    const chevron = screen.getByRole("button", { name: /Competencias/ });
    expect(chevron).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "Válidas" })).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Sin enlazar" }),
    ).toBeInTheDocument();
  });

  it("un grupo no activo permanece colapsado (sus items no están en el DOM)", () => {
    renderSidebar("coach", { initialPath: "/competitions/unlinked" });

    // Entrenamiento no es el área activa en /competitions/unlinked.
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
    renderSidebar("coach", { initialPath: "/dashboard" });

    const label = screen.getByRole("link", { name: /Entrenamiento/ });
    expect(label).toHaveAttribute("href", "/calendar");

    await user.click(label);

    expect(screen.getByTestId("location")).toHaveTextContent("/calendar");
  });

  it("hacer click en el chevron NO navega — solo alterna aria-expanded", async () => {
    const user = userEvent.setup();
    renderSidebar("coach", { initialPath: "/dashboard" });

    const chevron = screen.getByRole("button", { name: /Entrenamiento/ });
    expect(chevron).toHaveAttribute("aria-expanded", "false");

    await user.click(chevron);

    expect(chevron).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("location")).toHaveTextContent("/dashboard");
  });

  it("los dos controles del área siguen siendo independientes y ≥44px", () => {
    renderSidebar("coach", { initialPath: "/dashboard" });

    const label = screen.getByRole("link", { name: /Entrenamiento/ });
    const chevron = screen.getByRole("button", { name: "Expandir Entrenamiento" });

    expect(label).not.toBe(chevron);
    expect(label.className).toMatch(/min-h-11/);
    expect(chevron.className).toMatch(/h-11/);
    expect(chevron.className).toMatch(/w-11/);
  });

  it("los sub-items también llegan a ≥44px — son destinos de navegación reales", () => {
    // Área activa → auto-expandida, así que sus sub-items están montados.
    renderSidebar("coach", { initialPath: "/training/sessions" });

    for (const name of ["Calendario", "Sesiones", "Actividades"]) {
      const subItem = screen.getByRole("link", { name });
      expect(subItem.className).toMatch(/min-h-11/);
    }
  });
});

describe("SidebarNav — expandir/colapsar manualmente un grupo no activo", () => {
  it("el chevron de un grupo inactivo lo expande, revelando sus items", async () => {
    const user = userEvent.setup();
    renderSidebar("coach", { initialPath: "/dashboard" });

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
    renderSidebar("coach", { initialPath: "/dashboard" });

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
    renderSidebar("coach", { initialPath: "/competitions/unlinked" });

    const inactiveChevron = screen.getByRole("button", {
      name: /Entrenamiento/,
    });
    await user.click(inactiveChevron);
    expect(inactiveChevron).toHaveAttribute("aria-expanded", "true");

    // Competencias sigue expandido porque sigue siendo el área activa.
    const activeChevron = screen.getByRole("button", { name: /Competencias/ });
    expect(activeChevron).toHaveAttribute("aria-expanded", "true");
  });
});

// ---------------------------------------------------------------------------
// Feature 035 — colapso manual y riel de 72px
// ---------------------------------------------------------------------------

describe("SidebarNav — control de colapso", () => {
  it("expandida: ofrece 'Contraer navegación' y avisa al padre al pulsarlo", async () => {
    const user = userEvent.setup();
    const onToggleCollapsed = vi.fn();
    renderSidebar("coach", { onToggleCollapsed });

    const toggle = screen.getByRole("button", { name: "Contraer navegación" });
    expect(
      screen.queryByRole("button", { name: "Expandir navegación" }),
    ).not.toBeInTheDocument();

    await user.click(toggle);

    expect(onToggleCollapsed).toHaveBeenCalledTimes(1);
  });

  it("el control de 28px mantiene un área táctil de 44px vía ::after", () => {
    renderSidebar("coach");
    const toggle = screen.getByRole("button", { name: "Contraer navegación" });
    expect(toggle.className).toMatch(/after:-inset-2/);
  });

  it("riel: ofrece 'Expandir navegación' y avisa al padre al pulsarlo", async () => {
    const user = userEvent.setup();
    const onToggleCollapsed = vi.fn();
    renderSidebar("coach", { collapsed: true, onToggleCollapsed });

    expect(
      screen.queryByRole("button", { name: "Contraer navegación" }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Expandir navegación" }));

    expect(onToggleCollapsed).toHaveBeenCalledTimes(1);
  });
});

describe("SidebarNav — modo riel (72px)", () => {
  it("cada área es un tile enlazado con nombre accesible, en el mismo orden", () => {
    renderSidebar("coach", { collapsed: true });

    const nav = screen.getByRole("navigation", { name: "Secciones" });
    const names = within(nav)
      .getAllByRole("link")
      .map((link) => link.getAttribute("aria-label"));
    expect(names).toEqual([
      "Inicio",
      "Entrenamiento",
      "Competencias",
      "Atletas",
      "Familias",
      "Biblioteca",
    ]);
  });

  it("el tile navega a la ruta por defecto del área (sin disclosure ni sub-items)", () => {
    renderSidebar("coach", { collapsed: true, initialPath: "/training/sessions" });

    expect(screen.getByRole("link", { name: "Entrenamiento" })).toHaveAttribute(
      "href",
      "/calendar",
    );
    expect(
      screen.queryByRole("button", { name: /Expandir Entrenamiento/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Sesiones" }),
    ).not.toBeInTheDocument();
  });

  it("el tile del área activa conserva aria-current y el tratamiento activo", () => {
    renderSidebar("coach", { collapsed: true, initialPath: "/training/sessions" });

    const tile = screen.getByRole("link", { name: "Entrenamiento" });
    expect(tile).toHaveAttribute("aria-current", "page");
    expect(tile.className).toMatch(/bg-nav-active-bg/);
    expect(tile.className).toMatch(/text-nav-accent/);
  });

  it("el conteo pasa al nombre accesible del tile: 'Competencias · 2 pendientes'", () => {
    badgeState.current = { competitions: 2 };
    renderSidebar("coach", { collapsed: true });

    expect(
      screen.getByRole("link", { name: "Competencias · 2 pendientes" }),
    ).toBeInTheDocument();
    // Sin pendientes, el nombre es sólo la etiqueta.
    expect(
      screen.getByRole("link", { name: "Biblioteca" }),
    ).toBeInTheDocument();
  });

  it("cada tile está envuelto en el primitivo Tooltip y lo abre al hover", async () => {
    const user = userEvent.setup();
    badgeState.current = { competitions: 2 };
    renderSidebar("coach", { collapsed: true });

    const tile = screen.getByRole("link", { name: "Competencias · 2 pendientes" });
    // Radix marca el trigger con data-state; confirma el cableado del tooltip.
    expect(tile).toHaveAttribute("data-state", "closed");

    await user.hover(tile);

    const tooltip = await screen.findByRole("tooltip");
    expect(tooltip).toHaveTextContent("Competencias · 2 pendientes");
  });

  it("el botón de expandir también lleva tooltip — ningún control de sólo ícono queda sin pista visible", async () => {
    const user = userEvent.setup();
    renderSidebar("coach", { collapsed: true });

    const toggle = screen.getByRole("button", { name: "Expandir navegación" });
    expect(toggle).toHaveAttribute("data-state", "closed");

    await user.hover(toggle);

    const tooltip = await screen.findByRole("tooltip");
    expect(tooltip).toHaveTextContent("Expandir navegación");
  });

  it("la barra oculta la marca textual y deja sólo el logotipo", () => {
    renderSidebar("coach", { collapsed: true });
    expect(screen.queryByText("Trocha y Ruta")).not.toBeInTheDocument();
    expect(screen.queryByText("Operación")).not.toBeInTheDocument();
  });
});

describe("SidebarNav — accesibilidad (jest-axe)", () => {
  it("sin violaciones en la barra expandida, con área activa e insignias", async () => {
    badgeState.current = { competitions: 2, families: 3 };
    const { container } = renderSidebar("coach", { initialPath: "/athletes/1" });

    expect(await axe(container)).toHaveNoViolations();
  });

  it("sin violaciones en el riel de 72px", async () => {
    badgeState.current = { competitions: 2 };
    const { container } = renderSidebar("coach", {
      collapsed: true,
      initialPath: "/training/sessions",
    });

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("SidebarNav — pie de barra", () => {
  it("renderiza el contenido del pie en modo expandido", () => {
    renderSidebar("coach", { footer: <div data-testid="footer">Usuario</div> });
    expect(screen.getByTestId("footer")).toBeInTheDocument();
  });

  it("renderiza el contenido del pie en modo riel", () => {
    renderSidebar("coach", {
      collapsed: true,
      footer: <div data-testid="footer">Usuario</div>,
    });
    expect(screen.getByTestId("footer")).toBeInTheDocument();
  });
});
