import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { UserMenu, type UserMenuVariant } from "@/components/layout/UserMenu";
import type { NavRole } from "@/lib/navigation";

// T039 [US4] — item visibility per role (Salud IA admin-only), logout()
// invoked on "Cerrar sesión", and the focus/roving-tabindex/Escape/
// focus-return behavior inherited from ui/dropdown-menu.tsx (Radix
// DropdownMenu). Per contracts/header-actions.md "User menu".
//
// Feature 035: el mismo menú se presenta en tres variantes de trigger
// (header / sidebar / sidebarRail) y ya NO monta useKeyboardShortcuts ni el
// diálogo de atajos — ambos subieron a AppShell, que se monta una sola vez.

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn(),
}));

import { useAuthStore } from "@/store/auth.store";

const logout = vi.fn();
const onOpenShortcutsHelp = vi.fn();
const user = {
  first_name: "Ana",
  last_name: "Ríos",
};

function mockAuthStore() {
  vi.mocked(useAuthStore).mockImplementation((selector: any) =>
    selector({ user, logout } as any),
  );
}

/**
 * La variante de barra lateral se queda con el testid canónico
 * `user-menu-trigger` (es el montaje visible en ≥md); el header, que sólo
 * existe bajo `md`, usa el sufijo `-header`. Ver UserMenu.tsx.
 */
const TRIGGER_TEST_ID: Record<UserMenuVariant, string> = {
  header: "user-menu-trigger-header",
  sidebar: "user-menu-trigger",
  sidebarRail: "user-menu-trigger",
};

function renderUserMenu(role: NavRole, variant: UserMenuVariant = "header") {
  return render(
    <MemoryRouter>
      <UserMenu
        role={role}
        variant={variant}
        onOpenShortcutsHelp={onOpenShortcutsHelp}
      />
    </MemoryRouter>,
  );
}

function getTrigger(variant: UserMenuVariant = "header") {
  return screen.getByTestId(TRIGGER_TEST_ID[variant]);
}

describe("UserMenu — trigger", () => {
  beforeEach(() => {
    mockAuthStore();
    logout.mockClear();
    onOpenShortcutsHelp.mockClear();
  });

  it("renderiza el nombre completo del usuario con aria-haspopup='menu'", () => {
    renderUserMenu("coach");

    const trigger = getTrigger();
    expect(trigger).toHaveTextContent("Ana Ríos");
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
  });
});

// Feature 035 — tarjeta de usuario del pie de la barra lateral
// (Main.dc.html) y su equivalente en el riel de 72px.
describe("UserMenu — variantes de trigger (feature 035)", () => {
  beforeEach(() => {
    mockAuthStore();
    logout.mockClear();
    onOpenShortcutsHelp.mockClear();
  });

  it("variant='sidebar': tarjeta con iniciales, nombre y etiqueta de rol ('Entrenador')", () => {
    renderUserMenu("coach", "sidebar");

    const trigger = getTrigger("sidebar");
    expect(trigger).toHaveTextContent("AR");
    expect(trigger).toHaveTextContent("Ana Ríos");
    expect(trigger).toHaveTextContent("Entrenador");
    // ≥48px de alto y ancho completo del pie de la barra.
    expect(trigger.className).toMatch(/min-h-12/);
    expect(trigger.className).toMatch(/w-full/);
  });

  it("variant='sidebar' con rol admin: la etiqueta de rol es 'Administrador'", () => {
    renderUserMenu("admin", "sidebar");

    expect(getTrigger("sidebar")).toHaveTextContent("Administrador");
  });

  it("variant='sidebarRail': sólo avatar, con aria-label 'Menú de usuario' y objetivo táctil de 44px", () => {
    renderUserMenu("coach", "sidebarRail");

    const trigger = getTrigger("sidebarRail");
    expect(trigger).toHaveAccessibleName("Menú de usuario");
    // El nombre no se dibuja en el riel (sólo las iniciales del avatar).
    expect(trigger).not.toHaveTextContent("Ana Ríos");
    expect(trigger).toHaveTextContent("AR");
    expect(trigger.className).toMatch(/h-11/);
    expect(trigger.className).toMatch(/w-11/);
  });

  it("las tres variantes abren el mismo menú (Mi perfil + Cerrar sesión)", async () => {
    for (const variant of [
      "header",
      "sidebar",
      "sidebarRail",
    ] as UserMenuVariant[]) {
      const testUser = userEvent.setup();
      const { unmount } = renderUserMenu("coach", variant);

      await testUser.click(getTrigger(variant));

      expect(screen.getByRole("menuitem", { name: /Mi perfil/i })).toHaveAttribute(
        "href",
        "/perfil",
      );
      expect(
        screen.getByRole("menuitem", { name: /Cerrar sesión/i }),
      ).toBeInTheDocument();

      unmount();
    }
  });
});

describe("UserMenu — visibilidad de items por rol", () => {
  beforeEach(() => {
    mockAuthStore();
    logout.mockClear();
    onOpenShortcutsHelp.mockClear();
  });

  it("todos los roles ven 'Mi perfil' (/perfil) y 'Cerrar sesión'", async () => {
    for (const role of ["coach", "admin"] as NavRole[]) {
      const testUser = userEvent.setup();
      const { unmount } = renderUserMenu(role);

      await testUser.click(getTrigger());

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

    await testUser.click(getTrigger());

    expect(
      screen.getByRole("menuitem", { name: /Salud IA/i }),
    ).toHaveAttribute("href", "/admin/ai");
  });

  it("coach NO ve 'Salud IA'", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    await testUser.click(getTrigger());

    expect(
      screen.queryByRole("menuitem", { name: /Salud IA/i }),
    ).not.toBeInTheDocument();
  });
});

// T059 [US5] — toggle "Apariencia" (Sistema/Claro/Oscuro), feature 033.
describe("UserMenu — Apariencia (dark-mode toggle)", () => {
  beforeEach(() => {
    mockAuthStore();
    onOpenShortcutsHelp.mockClear();
    window.localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

  it("muestra las 3 opciones Sistema/Claro/Oscuro con 'Sistema' seleccionado por defecto", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    await testUser.click(getTrigger());

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

    await testUser.click(getTrigger());
    await testUser.click(screen.getByRole("menuitemradio", { name: /Oscuro/i }));

    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem("tyr:theme-preference:v1")).toBe(
      "dark",
    );
  });

  it("elegir 'Claro' tras 'Oscuro' aplica data-theme='light'", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    await testUser.click(getTrigger());
    await testUser.click(screen.getByRole("menuitemradio", { name: /Oscuro/i }));

    await testUser.click(getTrigger());
    await testUser.click(screen.getByRole("menuitemradio", { name: /Claro/i }));

    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem("tyr:theme-preference:v1")).toBe(
      "light",
    );
  });

  it("volver a 'Sistema' quita el atributo data-theme (cae a prefers-color-scheme)", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    await testUser.click(getTrigger());
    await testUser.click(screen.getByRole("menuitemradio", { name: /Oscuro/i }));

    await testUser.click(getTrigger());
    await testUser.click(screen.getByRole("menuitemradio", { name: /Sistema/i }));

    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(window.localStorage.getItem("tyr:theme-preference:v1")).toBe(
      "system",
    );
  });
});

// T063 [US5] — "Atajos de teclado" entry point, feature 033. Desde la
// feature 035 el diálogo (y el hook de atajos) viven en AppShell: aquí sólo
// se verifica que el item avise al shell.
describe("UserMenu — Atajos de teclado (delegado a AppShell)", () => {
  beforeEach(() => {
    mockAuthStore();
    onOpenShortcutsHelp.mockClear();
  });

  it("muestra el item 'Atajos de teclado' junto al toggle de Apariencia", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    await testUser.click(getTrigger());

    expect(
      screen.getByRole("menuitem", { name: /Atajos de teclado/i }),
    ).toBeInTheDocument();
    // The Apariencia radio group from T059 is still present alongside it.
    expect(
      screen.getByRole("menuitemradio", { name: /Sistema/i }),
    ).toBeInTheDocument();
  });

  it("seleccionar 'Atajos de teclado' invoca onOpenShortcutsHelp", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    await testUser.click(getTrigger());
    await testUser.click(
      screen.getByRole("menuitem", { name: /Atajos de teclado/i }),
    );

    // El item deja cerrar el menú primero y avisa en el siguiente tick.
    await waitFor(() =>
      expect(onOpenShortcutsHelp).toHaveBeenCalledTimes(1),
    );
  });

  it("NO registra atajos globales: la tecla '?' no hace nada aquí (el hook vive en AppShell)", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    await testUser.keyboard("?");

    expect(onOpenShortcutsHelp).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("UserMenu — Cerrar sesión", () => {
  beforeEach(() => {
    mockAuthStore();
    logout.mockClear();
    onOpenShortcutsHelp.mockClear();
  });

  it("'Cerrar sesión' invoca logout() del auth store", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    await testUser.click(getTrigger());
    await testUser.click(screen.getByRole("menuitem", { name: /Cerrar sesión/i }));

    expect(logout).toHaveBeenCalledTimes(1);
  });
});

describe("UserMenu — foco/roving-tabindex/Escape heredados de Radix DropdownMenu", () => {
  beforeEach(() => {
    mockAuthStore();
    logout.mockClear();
    onOpenShortcutsHelp.mockClear();
  });

  it("al abrir, el foco queda atrapado dentro del contenido del menú", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    await testUser.click(getTrigger());

    const menu = screen.getByRole("menu");
    expect(menu).toContainElement(document.activeElement as HTMLElement);
  });

  it("ArrowDown navega entre items vía roving tabindex (tabindex=-1 en todos salvo el activo)", async () => {
    const testUser = userEvent.setup();
    renderUserMenu("coach");

    await testUser.click(getTrigger());

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

    const trigger = getTrigger();
    await testUser.click(trigger);
    expect(screen.getByRole("menu")).toBeInTheDocument();

    await testUser.keyboard("{Escape}");

    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});
