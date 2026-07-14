import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { UserMenu } from "@/components/layout/UserMenu";
import type { NavRole } from "@/lib/navigation";

// T039 [US4] — item visibility per role (Salud IA admin-only), logout()
// invoked on "Cerrar sesión", and the focus/roving-tabindex/Escape/
// focus-return behavior inherited from ui/dropdown-menu.tsx (Radix
// DropdownMenu). Per contracts/header-actions.md "User menu".

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn(),
}));

import { useAuthStore } from "@/store/auth.store";

const logout = vi.fn();
const user = {
  first_name: "Ana",
  last_name: "Ríos",
};

function mockAuthStore() {
  vi.mocked(useAuthStore).mockImplementation((selector: any) =>
    selector({ user, logout } as any),
  );
}

function renderUserMenu(role: NavRole) {
  return render(
    <MemoryRouter>
      <UserMenu role={role} />
    </MemoryRouter>,
  );
}

describe("UserMenu — trigger", () => {
  beforeEach(() => {
    mockAuthStore();
    logout.mockClear();
  });

  it("renderiza el nombre completo del usuario con aria-haspopup='menu'", () => {
    renderUserMenu("coach");

    const trigger = screen.getByTestId("user-menu-trigger");
    expect(trigger).toHaveTextContent("Ana Ríos");
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
  });
});

describe("UserMenu — visibilidad de items por rol", () => {
  beforeEach(() => {
    mockAuthStore();
    logout.mockClear();
  });

  it("todos los roles ven 'Mi perfil' (/perfil) y 'Cerrar sesión'", async () => {
    for (const role of ["coach", "admin"] as NavRole[]) {
      const testUser = userEvent.setup();
      const { unmount } = renderUserMenu(role);

      await testUser.click(screen.getByTestId("user-menu-trigger"));

      const profile = screen.getByRole("menuitem", { name: /Mi perfil/i });
      expect(profile).toHaveAttribute("href", "/perfil");
      expect(
        screen.getByRole("menuitem", { name: /Cerrar sesión/i }),
      ).toBeInTheDocument();

      unmount();
    }
  });

  it("solo admin ve 'Salud IA' (/admin/ai)", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("admin");

    await testUser.click(screen.getByTestId("user-menu-trigger"));

    expect(
      screen.getByRole("menuitem", { name: /Salud IA/i }),
    ).toHaveAttribute("href", "/admin/ai");
  });

  it("coach NO ve 'Salud IA'", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    await testUser.click(screen.getByTestId("user-menu-trigger"));

    expect(
      screen.queryByRole("menuitem", { name: /Salud IA/i }),
    ).not.toBeInTheDocument();
  });
});

// T059 [US5] — toggle "Apariencia" (Sistema/Claro/Oscuro), feature 033.
describe("UserMenu — Apariencia (dark-mode toggle)", () => {
  beforeEach(() => {
    mockAuthStore();
    window.localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

  it("muestra las 3 opciones Sistema/Claro/Oscuro con 'Sistema' seleccionado por defecto", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    await testUser.click(screen.getByTestId("user-menu-trigger"));

    const system = screen.getByRole("menuitemradio", { name: /Sistema/i });
    expect(system).toHaveAttribute("aria-checked", "true");
    expect(
      screen.getByRole("menuitemradio", { name: /Claro/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("menuitemradio", { name: /Oscuro/i }),
    ).toBeInTheDocument();
  });

  it("elegir 'Oscuro' aplica data-theme='dark' en <html> y lo persiste en localStorage", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    await testUser.click(screen.getByTestId("user-menu-trigger"));
    await testUser.click(screen.getByRole("menuitemradio", { name: /Oscuro/i }));

    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem("tyr:theme-preference:v1")).toBe(
      "dark",
    );
  });

  it("elegir 'Claro' tras 'Oscuro' aplica data-theme='light'", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    await testUser.click(screen.getByTestId("user-menu-trigger"));
    await testUser.click(screen.getByRole("menuitemradio", { name: /Oscuro/i }));

    await testUser.click(screen.getByTestId("user-menu-trigger"));
    await testUser.click(screen.getByRole("menuitemradio", { name: /Claro/i }));

    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem("tyr:theme-preference:v1")).toBe(
      "light",
    );
  });

  it("volver a 'Sistema' quita el atributo data-theme (cae a prefers-color-scheme)", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    await testUser.click(screen.getByTestId("user-menu-trigger"));
    await testUser.click(screen.getByRole("menuitemradio", { name: /Oscuro/i }));

    await testUser.click(screen.getByTestId("user-menu-trigger"));
    await testUser.click(screen.getByRole("menuitemradio", { name: /Sistema/i }));

    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(window.localStorage.getItem("tyr:theme-preference:v1")).toBe(
      "system",
    );
  });
});

// T063 [US5] — "Atajos de teclado" help dialog entry point, feature 033.
// Verifies the dark-mode toggle (T059) and the shortcuts entry point (T063)
// coexist in the same DropdownMenuContent without a merge/logic conflict.
describe("UserMenu — Atajos de teclado (help dialog)", () => {
  beforeEach(() => {
    mockAuthStore();
  });

  it("muestra el item 'Atajos de teclado' junto al toggle de Apariencia", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    await testUser.click(screen.getByTestId("user-menu-trigger"));

    expect(
      screen.getByRole("menuitem", { name: /Atajos de teclado/i }),
    ).toBeInTheDocument();
    // The Apariencia radio group from T059 is still present alongside it.
    expect(
      screen.getByRole("menuitemradio", { name: /Sistema/i }),
    ).toBeInTheDocument();
  });

  it("seleccionar 'Atajos de teclado' abre el diálogo de ayuda", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    await testUser.click(screen.getByTestId("user-menu-trigger"));
    await testUser.click(
      screen.getByRole("menuitem", { name: /Atajos de teclado/i }),
    );

    expect(
      await screen.findByRole("dialog", { name: /Atajos de teclado/i }),
    ).toBeInTheDocument();
  });

  it("la tecla '?' abre el diálogo de ayuda (wired a useKeyboardShortcuts)", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    await testUser.keyboard("?");

    expect(
      await screen.findByRole("dialog", { name: /Atajos de teclado/i }),
    ).toBeInTheDocument();
  });
});

describe("UserMenu — Cerrar sesión", () => {
  beforeEach(() => {
    mockAuthStore();
    logout.mockClear();
  });

  it("'Cerrar sesión' invoca logout() del auth store", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    await testUser.click(screen.getByTestId("user-menu-trigger"));
    await testUser.click(screen.getByRole("menuitem", { name: /Cerrar sesión/i }));

    expect(logout).toHaveBeenCalledTimes(1);
  });
});

describe("UserMenu — foco/roving-tabindex/Escape heredados de Radix DropdownMenu", () => {
  beforeEach(() => {
    mockAuthStore();
    logout.mockClear();
  });

  it("al abrir, el foco queda atrapado dentro del contenido del menú", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    await testUser.click(screen.getByTestId("user-menu-trigger"));

    const menu = screen.getByRole("menu");
    expect(menu).toContainElement(document.activeElement as HTMLElement);
  });

  it("ArrowDown navega entre items vía roving tabindex (tabindex=-1 en todos salvo el activo)", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    await testUser.click(screen.getByTestId("user-menu-trigger"));

    await testUser.keyboard("{ArrowDown}");
    const first = screen.getByRole("menuitem", { name: /Mi perfil/i });
    expect(first).toHaveFocus();

    // Feature 033, US5: el siguiente item tras "Mi perfil" ahora es el
    // primer radio item del toggle "Apariencia" (Sistema), insertado antes
    // de "Cerrar sesión".
    await testUser.keyboard("{ArrowDown}");
    expect(
      screen.getByRole("menuitemradio", { name: /Sistema/i }),
    ).toHaveFocus();
    expect(first).toHaveAttribute("tabindex", "-1");
  });

  it("Escape cierra el menú y retorna el foco al trigger", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    const trigger = screen.getByTestId("user-menu-trigger");
    await testUser.click(trigger);
    expect(screen.getByRole("menu")).toBeInTheDocument();

    await testUser.keyboard("{Escape}");

    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});
