import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe, toHaveNoViolations } from "jest-axe";
import { AppShell } from "../AppShell";
import { UserRole } from "@/types/enums";

expect.extend(toHaveNoViolations);

// Mock useMyAthletes para no disparar fetch real en tests del AppShell
// (Wave 4 introdujo AthleteSwitcher que consume useMyAthletes para parent).
vi.mock("@/hooks/parents/useMyAthletes", () => ({
  useMyAthletes: vi.fn(() => ({
    data: [],
    isLoading: false,
    isError: false,
  })),
}));

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn(),
}));

import { useAuthStore } from "@/store/auth.store";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockStoreWithRole(role: UserRole | "admin") {
  vi.mocked(useAuthStore).mockImplementation((selector: any) =>
    selector({
      user: {
        id: 1,
        email: "test@example.com",
        first_name: "Test",
        last_name: "User",
        role,
        is_active: true,
        can_login: true,
        created_at: "2026-01-01T00:00:00Z",
      },
      accessToken: "token",
      refreshToken: "refresh",
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      refreshSession: vi.fn(),
      fetchMe: vi.fn(),
    } as any),
  );
}

// feature 030 (T014): SidebarNav es config-driven (NAV_AREAS) para
// coach/admin — la mayoría de grupos de varios items empiezan colapsados,
// así que las pruebas que necesitan ver un item anidado o parten de un
// deep link dentro del área (auto-expand), o expanden manualmente el
// chevron correspondiente.
// T029 [US3]: with <BottomNav> now always mounted alongside <SidebarNav> for
// coach/admin (Tailwind's `md:hidden`/`md:flex` only toggle CSS `display` —
// both trees stay in the DOM per contracts/mobile-navigation.md), several
// area labels (e.g. "Atletas", "Competencias") exist twice in the
// accessibility tree: once in the sidebar, once as a bottom-bar slot. Tests
// that only care about the sidebar scope their queries to it via this
// helper (the `<aside aria-label="Menú de navegación">` landmark, unchanged
// by this feature — AppShell.tsx:123).
function getSidebar() {
  return screen.getByRole("complementary", { name: "Menú de navegación" });
}

function renderShell(role: UserRole | "admin", initialPath = "/dashboard") {
  mockStoreWithRole(role as UserRole);
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <AppShell>
          <div>Contenido</div>
        </AppShell>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AppShell", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Rol: coach
  // -------------------------------------------------------------------------
  describe("cuando el rol es coach", () => {
    it("debería mostrar 'Atletas' como grupo colapsable (con su propio control de disclosure), no como NavLink suelto", () => {
      renderShell(UserRole.coach);
      // La etiqueta del área sigue navegando a su ruta por defecto...
      // (scoped to the sidebar — "Atletas" is also a <BottomNav> slot, T029)
      const label = within(getSidebar()).getByRole("link", { name: "Atletas" });
      expect(label).toHaveAttribute("href", "/athletes");
      // ...pero ahora está acompañada de un control de expandir/colapsar
      // independiente — a diferencia del NavLink suelto del sidebar anterior.
      expect(
        screen.getByRole("button", { name: "Expandir Atletas" }),
      ).toBeInTheDocument();
    });

    it("'Padres' debería estar anidado dentro del grupo 'Familias' — no visible como enlace suelto hasta expandir", async () => {
      const user = userEvent.setup();
      renderShell(UserRole.coach);

      // Colapsado por defecto (ruta activa es /dashboard, ajena a Familias):
      // "Padres" no es un enlace de nivel superior accesible.
      expect(
        screen.queryByRole("link", { name: "Padres" }),
      ).not.toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Expandir Familias" }));

      const link = screen.getByRole("link", { name: "Padres" });
      expect(link).toHaveAttribute("href", "/parents");
    });

    it("debería mostrar el NavLink 'Boletines' (no 'Boletines Mensuales') apuntando a /training/athlete-newsletters", async () => {
      const user = userEvent.setup();
      renderShell(UserRole.coach);

      expect(
        screen.queryByRole("link", { name: "Boletines Mensuales" }),
      ).not.toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Expandir Familias" }));

      const link = screen.getByRole("link", { name: "Boletines" });
      expect(link).toHaveAttribute("href", "/training/athlete-newsletters");
    });

    it("debería mostrar el NavLink 'Informes del club' (no 'Reportes mensuales') apuntando a /training/reports", async () => {
      const user = userEvent.setup();
      renderShell(UserRole.coach);

      expect(
        screen.queryByRole("link", { name: "Reportes mensuales" }),
      ).not.toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Expandir Familias" }));

      const link = screen.getByRole("link", { name: "Informes del club" });
      expect(link).toHaveAttribute("href", "/training/reports");
    });

    it("NO debería mostrar el NavLink 'Mis Atletas'", () => {
      renderShell(UserRole.coach);
      expect(
        screen.queryByRole("link", { name: "Mis Atletas" }),
      ).not.toBeInTheDocument();
    });

    // Wave B unificación /competitions: la entrada separada "Análisis IA
    // carreras" se eliminó del sidebar. El análisis IA es accesible solo
    // desde dentro del módulo /competitions (tab insights en el detalle y
    // hub /competitions/insights). Un único enlace "Competencias" basta.
    it("NO debería mostrar el NavLink 'Análisis IA carreras' (Wave B — entrada fusionada)", () => {
      renderShell(UserRole.coach);
      expect(
        screen.queryByRole("link", { name: "Análisis IA carreras" }),
      ).not.toBeInTheDocument();
    });

    it("NO debería quedar ningún enlace a la ruta legacy /coach/race-analysis", () => {
      renderShell(UserRole.coach);
      const legacy = screen
        .queryAllByRole("link")
        .filter((el) => el.getAttribute("href") === "/coach/race-analysis");
      expect(legacy).toHaveLength(0);
    });

    it("NO debería existir un enlace a la URL exacta del hub eliminado /competitions/insights, aunque 'Panorama de temporada' viva en un path con ese prefijo", async () => {
      const user = userEvent.setup();
      renderShell(UserRole.coach);

      await user.click(
        screen.getByRole("button", { name: "Expandir Competencias" }),
      );

      // "Panorama de temporada" es una entrada legítima cuyo href empieza
      // con el mismo prefijo del hub K3 eliminado (029 FR-001) — no debe
      // confundirse con un enlace directo a la URL exacta del hub.
      const panorama = screen.getByRole("link", {
        name: "Panorama de temporada",
      });
      expect(panorama.getAttribute("href")).toMatch(
        /^\/competitions\/insights\//,
      );

      const exactHub = screen
        .queryAllByRole("link")
        .filter((el) => el.getAttribute("href") === "/competitions/insights");
      expect(exactHub).toHaveLength(0);
    });

    it("debería mostrar el NavLink 'Competencias' apuntando a /competitions", () => {
      renderShell(UserRole.coach);
      // Scoped to the sidebar — "Competencias" is also a <BottomNav> slot (T029).
      const link = within(getSidebar()).getByRole("link", { name: "Competencias" });
      expect(link).toHaveAttribute("href", "/competitions");
    });

    it("en un deep link a /anxiety, el grupo 'Atletas' que contiene la ruta activa está expandido y visualmente indicado", () => {
      renderShell(UserRole.coach, "/anxiety");

      // El chevron reporta expandido (aria-expanded) y su aria-label pasa
      // de "Expandir" a "Contraer".
      const chevron = screen.getByRole("button", { name: "Contraer Atletas" });
      expect(chevron).toHaveAttribute("aria-expanded", "true");

      // La etiqueta del área queda visualmente indicada como activa.
      // (scoped to the sidebar — "Atletas" is also a <BottomNav> slot, T029)
      const areaLabel = within(getSidebar()).getByRole("link", { name: "Atletas" });
      expect(areaLabel.className).toMatch(/bg-charcoal/);

      // Sus items quedan visibles y el item correspondiente a la ruta
      // actual está marcado como página actual.
      expect(
        within(getSidebar()).getByRole("link", { name: "Todos" }),
      ).toBeInTheDocument();
      const currentItem = within(getSidebar()).getByRole("link", {
        name: "Ansiedad competitiva",
      });
      expect(currentItem).toHaveAttribute("aria-current", "page");
      expect(currentItem.className).toMatch(/bg-charcoal/);
    });

    // Regression: "competitions" is the one area whose items nest path-wise
    // ("Válidas" → /competitions is a literal prefix of "Sin enlazar" →
    // /competitions/unlinked and "Panorama de temporada" →
    // /competitions/insights/season/:year). A naive NavLink prefix match
    // (no `end`) marks more than one sibling active simultaneously.
    it("en /competitions/insights/season/2026, solo 'Panorama de temporada' queda marcado activo (no también 'Válidas')", () => {
      renderShell(UserRole.coach, "/competitions/insights/season/2026");

      const sidebar = getSidebar();
      const seasonItem = within(sidebar).getByRole("link", {
        name: "Panorama de temporada",
      });
      const validasItem = within(sidebar).getByRole("link", { name: "Válidas" });

      expect(seasonItem).toHaveAttribute("aria-current", "page");
      expect(seasonItem.className).toMatch(/bg-charcoal/);
      expect(validasItem).not.toHaveAttribute("aria-current", "page");
      expect(validasItem.className).not.toMatch(/bg-charcoal/);
    });

    it("en /competitions/unlinked, solo 'Sin enlazar' queda marcado activo (no también 'Válidas')", () => {
      renderShell(UserRole.coach, "/competitions/unlinked");

      const sidebar = getSidebar();
      const unlinkedItem = within(sidebar).getByRole("link", {
        name: "Sin enlazar",
      });
      const validasItem = within(sidebar).getByRole("link", { name: "Válidas" });

      expect(unlinkedItem).toHaveAttribute("aria-current", "page");
      expect(unlinkedItem.className).toMatch(/bg-charcoal/);
      expect(validasItem).not.toHaveAttribute("aria-current", "page");
      expect(validasItem.className).not.toMatch(/bg-charcoal/);
    });
  });

  // -------------------------------------------------------------------------
  // Rol: parent
  // -------------------------------------------------------------------------
  describe("cuando el rol es parent", () => {
    it("debería mostrar el NavLink 'Mis Atletas'", () => {
      renderShell(UserRole.parent);
      expect(screen.getByRole("link", { name: "Mis Atletas" })).toBeInTheDocument();
    });

    it("NO debería mostrar el NavLink 'Atletas'", () => {
      renderShell(UserRole.parent);
      expect(
        screen.queryByRole("link", { name: "Atletas" }),
      ).not.toBeInTheDocument();
    });

    it("NO debería mostrar el NavLink 'Padres'", () => {
      renderShell(UserRole.parent);
      expect(
        screen.queryByRole("link", { name: "Padres" }),
      ).not.toBeInTheDocument();
    });

    it("NO debería mostrar el NavLink 'Boletines Mensuales'", () => {
      renderShell(UserRole.parent);
      expect(
        screen.queryByRole("link", { name: "Boletines Mensuales" }),
      ).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Rol: admin
  // -------------------------------------------------------------------------
  describe("cuando el rol es admin", () => {
    it("el grupo 'Atletas' completo está ausente (ni la etiqueta ni su control de disclosure existen)", () => {
      renderShell(UserRole.admin);
      expect(
        screen.queryByRole("link", { name: "Atletas" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /Atletas/ }),
      ).not.toBeInTheDocument();
    });

    it("NO debería mostrar el NavLink 'Padres'", () => {
      renderShell(UserRole.admin);
      expect(
        screen.queryByRole("link", { name: "Padres" }),
      ).not.toBeInTheDocument();
    });

    it("NO debería mostrar el NavLink 'Mis Atletas'", () => {
      renderShell(UserRole.admin);
      expect(
        screen.queryByRole("link", { name: "Mis Atletas" }),
      ).not.toBeInTheDocument();
    });

    it("debería mostrar el NavLink 'Boletines' (no 'Boletines Mensuales') apuntando a /training/athlete-newsletters", async () => {
      const user = userEvent.setup();
      renderShell(UserRole.admin);

      // Para admin, la etiqueta de "Familias" resuelve a Boletines
      // (Padres es coach-only) — expandir revela el item explícitamente.
      await user.click(screen.getByRole("button", { name: "Expandir Familias" }));

      const link = screen.getByRole("link", { name: "Boletines" });
      expect(link).toHaveAttribute("href", "/training/athlete-newsletters");
    });
  });

  // -------------------------------------------------------------------------
  // Navegación móvil: <BottomNav> + <MoreSheet> (feature 030, US3, T029)
  // -------------------------------------------------------------------------
  describe("navegación móvil — BottomNav + MoreSheet (< md)", () => {
    const originalInnerWidth = window.innerWidth;

    beforeEach(() => {
      // Simula un viewport móvil antes de montar. jsdom no aplica media
      // queries reales (Tailwind's `md:hidden`/`md:flex` sólo alternan
      // `display` vía CSS, que jsdom no calcula), así que <BottomNav> y
      // <MoreSheet> están siempre presentes en el árbol de accesibilidad
      // independientemente del ancho (contracts/mobile-navigation.md). Este
      // ancho documenta la intención y evita que `window.innerWidth`
      // quede en un valor de escritorio inconsistente si alguna lógica
      // futura llegara a leerlo. El comportamiento real de mostrar/ocultar
      // por ancho lo cubre el e2e de Playwright (T033).
      Object.defineProperty(window, "innerWidth", {
        writable: true,
        configurable: true,
        value: 375,
      });
      window.dispatchEvent(new Event("resize"));
    });

    afterEach(() => {
      Object.defineProperty(window, "innerWidth", {
        writable: true,
        configurable: true,
        value: originalInnerWidth,
      });
    });

    function getBottomBar() {
      return screen.getByRole("navigation", { name: "Navegación principal" });
    }

    it("coach: la barra inferior muestra Inicio, Entrenamiento, Competencias, Atletas y el botón Más (orden fijo)", () => {
      renderShell(UserRole.coach);

      const bar = getBottomBar();
      const labels = ["Inicio", "Entrenamiento", "Competencias", "Atletas"];
      for (const label of labels) {
        expect(
          within(bar).getByRole("link", { name: new RegExp(label) }),
        ).toBeInTheDocument();
      }
      expect(within(bar).getByRole("button", { name: /Más/ })).toBeInTheDocument();

      const linkNames = Array.from(bar.querySelectorAll("a")).map((a) =>
        a.textContent?.trim(),
      );
      expect(linkNames).toEqual(labels);
    });

    it("admin: el 4º slot de la barra inferior es Biblioteca, no Atletas (research.md R6)", () => {
      renderShell(UserRole.admin);

      const bar = getBottomBar();
      const labels = ["Inicio", "Entrenamiento", "Competencias", "Biblioteca"];
      for (const label of labels) {
        expect(
          within(bar).getByRole("link", { name: new RegExp(label) }),
        ).toBeInTheDocument();
      }
      expect(
        within(bar).queryByRole("link", { name: /Atletas/ }),
      ).not.toBeInTheDocument();
      expect(within(bar).getByRole("button", { name: /Más/ })).toBeInTheDocument();
    });

    it("coach: 'Más' lista las áreas restantes (Familias, Biblioteca) más Mi perfil y Cerrar sesión — sin Salud IA", async () => {
      const user = userEvent.setup();
      renderShell(UserRole.coach);

      await user.click(within(getBottomBar()).getByRole("button", { name: /Más/ }));

      const dialog = screen.getByRole("dialog");
      expect(within(dialog).getByRole("link", { name: "Familias" })).toBeInTheDocument();
      expect(
        within(dialog).getByRole("link", { name: "Biblioteca" }),
      ).toBeInTheDocument();
      expect(within(dialog).getByRole("link", { name: "Mi perfil" })).toHaveAttribute(
        "href",
        "/perfil",
      );
      expect(
        within(dialog).getByRole("button", { name: "Cerrar sesión" }),
      ).toBeInTheDocument();
      expect(
        within(dialog).queryByRole("link", { name: "Salud IA" }),
      ).not.toBeInTheDocument();
      // Las áreas ya promovidas a la barra no se repiten dentro del sheet.
      expect(within(dialog).queryByRole("link", { name: "Atletas" })).not.toBeInTheDocument();
    });

    it("admin: 'Más' lista Familias más Mi perfil, Salud IA y Cerrar sesión — Atletas ausente por completo (research.md R7) y Biblioteca no se repite (ya está en la barra)", async () => {
      const user = userEvent.setup();
      renderShell(UserRole.admin);

      await user.click(within(getBottomBar()).getByRole("button", { name: /Más/ }));

      const dialog = screen.getByRole("dialog");
      expect(within(dialog).getByRole("link", { name: "Familias" })).toBeInTheDocument();
      expect(within(dialog).getByRole("link", { name: "Mi perfil" })).toHaveAttribute(
        "href",
        "/perfil",
      );
      expect(within(dialog).getByRole("link", { name: "Salud IA" })).toHaveAttribute(
        "href",
        "/admin/ai",
      );
      expect(
        within(dialog).getByRole("button", { name: "Cerrar sesión" }),
      ).toBeInTheDocument();
      expect(within(dialog).queryByRole("link", { name: "Atletas" })).not.toBeInTheDocument();
      expect(
        within(dialog).queryByRole("link", { name: "Biblioteca" }),
      ).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Acciones de header — UserMenu + QuickCreate (feature 030, US4, T037)
  // -------------------------------------------------------------------------
  describe("acciones de header — UserMenu + QuickCreate (coach/admin)", () => {
    it("coach: el trigger del user menu muestra el nombre completo y al abrir revela 'Mi perfil' y 'Cerrar sesión' (sin 'Salud IA')", async () => {
      const user = userEvent.setup();
      renderShell(UserRole.coach);

      const trigger = screen.getByTestId("user-menu-trigger");
      expect(trigger).toHaveTextContent("Test User");

      await user.click(trigger);

      expect(
        screen.getByRole("menuitem", { name: /Mi perfil/i }),
      ).toHaveAttribute("href", "/perfil");
      expect(
        screen.getByRole("menuitem", { name: /Cerrar sesión/i }),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("menuitem", { name: /Salud IA/i }),
      ).not.toBeInTheDocument();
    });

    it("admin: el user menu revela 'Mi perfil', 'Salud IA' (/admin/ai) y 'Cerrar sesión'", async () => {
      const user = userEvent.setup();
      renderShell(UserRole.admin);

      await user.click(screen.getByTestId("user-menu-trigger"));

      expect(
        screen.getByRole("menuitem", { name: /Mi perfil/i }),
      ).toHaveAttribute("href", "/perfil");
      expect(
        screen.getByRole("menuitem", { name: /Salud IA/i }),
      ).toHaveAttribute("href", "/admin/ai");
      expect(
        screen.getByRole("menuitem", { name: /Cerrar sesión/i }),
      ).toBeInTheDocument();
    });

    it("coach: el trigger de quick-create abre y revela las 4 opciones filtradas por rol, incluyendo 'Nuevo atleta'", async () => {
      const user = userEvent.setup();
      renderShell(UserRole.coach);

      await user.click(screen.getByTestId("quick-create-trigger"));

      expect(screen.getByTestId("quick-create.session")).toBeInTheDocument();
      expect(
        screen.getByTestId("quick-create.competition"),
      ).toBeInTheDocument();
      expect(screen.getByTestId("quick-create.event")).toBeInTheDocument();
      expect(screen.getByTestId("quick-create.athlete")).toBeInTheDocument();
    });

    it("admin: el quick-create NO ofrece 'Nuevo atleta'", async () => {
      const user = userEvent.setup();
      renderShell(UserRole.admin);

      await user.click(screen.getByTestId("quick-create-trigger"));

      expect(screen.getByTestId("quick-create.session")).toBeInTheDocument();
      expect(
        screen.getByTestId("quick-create.competition"),
      ).toBeInTheDocument();
      expect(screen.getByTestId("quick-create.event")).toBeInTheDocument();
      expect(
        screen.queryByTestId("quick-create.athlete"),
      ).not.toBeInTheDocument();
    });

    it("admin: 'Salud IA' no es un enlace del sidebar ni de la barra inferior, pero sí está dentro del user menu abierto", async () => {
      const user = userEvent.setup();
      renderShell(UserRole.admin);

      expect(
        within(getSidebar()).queryByRole("link", { name: /Salud IA/i }),
      ).not.toBeInTheDocument();

      const bottomBar = screen.getByRole("navigation", {
        name: "Navegación principal",
      });
      expect(
        within(bottomBar).queryByRole("link", { name: /Salud IA/i }),
      ).not.toBeInTheDocument();

      await user.click(screen.getByTestId("user-menu-trigger"));

      expect(
        screen.getByRole("menuitem", { name: /Salud IA/i }),
      ).toHaveAttribute("href", "/admin/ai");
    });
  });

  // -------------------------------------------------------------------------
  // Accesibilidad (jest-axe) — quickstart.md "automated validation" checklist
  // -------------------------------------------------------------------------
  describe("accesibilidad (jest-axe)", () => {
    it("sin violaciones axe en el shell por defecto (coach, sidebar colapsado)", async () => {
      const { container } = renderShell(UserRole.coach);

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("sin violaciones axe con un grupo del sidebar expandido (coach, 'Familias' abierto)", async () => {
      const user = userEvent.setup();
      const { container } = renderShell(UserRole.coach);

      await user.click(screen.getByRole("button", { name: "Expandir Familias" }));
      // Confirma que el grupo realmente quedó expandido antes de auditar.
      expect(screen.getByRole("link", { name: "Padres" })).toBeInTheDocument();

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("sin violaciones axe con el sheet 'Más' abierto (coach)", async () => {
      const user = userEvent.setup();
      const { container } = renderShell(UserRole.coach);

      await user.click(
        within(
          screen.getByRole("navigation", { name: "Navegación principal" }),
        ).getByRole("button", { name: /Más/ }),
      );
      // Confirma que el sheet realmente quedó abierto antes de auditar.
      expect(screen.getByRole("dialog")).toBeInTheDocument();

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("sin violaciones axe con el user menu abierto (coach)", async () => {
      const user = userEvent.setup();
      const { container } = renderShell(UserRole.coach);

      await user.click(screen.getByTestId("user-menu-trigger"));
      // Confirma que el menú realmente quedó abierto antes de auditar.
      expect(
        screen.getByRole("menuitem", { name: /Mi perfil/i }),
      ).toBeInTheDocument();

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("sin violaciones axe con el quick-create menu abierto (coach)", async () => {
      const user = userEvent.setup();
      const { container } = renderShell(UserRole.coach);

      await user.click(screen.getByTestId("quick-create-trigger"));
      // Confirma que el menú realmente quedó abierto antes de auditar.
      expect(screen.getByTestId("quick-create.session")).toBeInTheDocument();

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });
});
