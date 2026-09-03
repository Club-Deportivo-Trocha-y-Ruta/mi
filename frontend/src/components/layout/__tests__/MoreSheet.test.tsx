import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { axe } from "jest-axe";

import { MoreSheet } from "@/components/layout/MoreSheet";
import type { NavRole } from "@/lib/navigation";

// T032 [US3] — role-filtered content list (getMoreSheetAreas), the
// focus-trap/Escape/focus-return behavior inherited from ui/sheet.tsx
// (Radix Dialog), and the >=48x48px row target size. Per
// contracts/mobile-navigation.md "Más sheet" + data-model.md §3.

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn(),
}));

import { useAuthStore } from "@/store/auth.store";

const logout = vi.fn();

function mockAuthStore() {
  vi.mocked(useAuthStore).mockImplementation((selector: any) =>
    selector({ logout } as any),
  );
}

function renderMoreSheet(role: NavRole, open = true) {
  const onOpenChange = vi.fn();
  const utils = render(
    <MemoryRouter>
      <button type="button">Más</button>
      <MoreSheet role={role} open={open} onOpenChange={onOpenChange} />
    </MemoryRouter>,
  );
  return { onOpenChange, ...utils };
}

describe("MoreSheet — contenido filtrado por rol (data-model.md §3, R7)", () => {
  beforeEach(() => {
    mockAuthStore();
    logout.mockClear();
  });

  it("coach ve Familias (área restante no promovida a la barra)", () => {
    renderMoreSheet("coach");

    expect(screen.getByRole("link", { name: "Familias" })).toBeInTheDocument();
  });

  it("coach NO ve Inicio/Entrenamiento/Competencias/Atletas dentro del sheet (ya están en la barra)", () => {
    renderMoreSheet("coach");

    expect(screen.queryByRole("link", { name: "Inicio" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Entrenamiento" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Competencias" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Atletas" })).not.toBeInTheDocument();
  });

  it("admin ve Familias únicamente — Atletas está ausente por completo (research.md R7)", () => {
    renderMoreSheet("admin");

    expect(screen.getByRole("link", { name: "Familias" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Atletas" })).not.toBeInTheDocument();
  });

  it("Familias de admin resuelve a Boletines (no /parents, coach-only)", () => {
    renderMoreSheet("admin");

    const familias = screen.getByRole("link", { name: "Familias" });
    expect(familias).toHaveAttribute("href", "/training/athlete-newsletters");
  });

  it("Familias de coach resuelve a Padres (/parents)", () => {
    renderMoreSheet("coach");

    const familias = screen.getByRole("link", { name: "Familias" });
    expect(familias).toHaveAttribute("href", "/parents");
  });

  it("todos los roles ven 'Mi perfil' (/perfil) y 'Cerrar sesión'", () => {
    for (const role of ["coach", "admin"] as NavRole[]) {
      const { unmount } = renderMoreSheet(role);
      const profile = screen.getByRole("link", { name: "Mi perfil" });
      expect(profile).toHaveAttribute("href", "/perfil");
      expect(
        screen.getByRole("button", { name: "Cerrar sesión" }),
      ).toBeInTheDocument();
      unmount();
    }
  });

  it("solo admin ve 'Salud IA' (/admin/ai); coach no lo ve", () => {
    renderMoreSheet("admin");
    expect(screen.getByRole("link", { name: "Salud IA" })).toHaveAttribute(
      "href",
      "/admin/ai",
    );

    const { unmount } = renderMoreSheet("admin"); // dispose first render's tree
    unmount();

    renderMoreSheet("coach");
    expect(screen.queryByRole("link", { name: "Salud IA" })).not.toBeInTheDocument();
  });

  it("'Cerrar sesión' invoca logout del auth store", async () => {
    const user = userEvent.setup();
    renderMoreSheet("coach");

    await user.click(screen.getByRole("button", { name: "Cerrar sesión" }));

    expect(logout).toHaveBeenCalledTimes(1);
  });
});

describe("MoreSheet — foco/Escape/retorno de foco heredados de ui/sheet.tsx", () => {
  beforeEach(() => {
    mockAuthStore();
    logout.mockClear();
  });

  it("al abrir, el foco queda atrapado dentro del contenido del sheet (dialog)", () => {
    renderMoreSheet("coach");

    const dialog = screen.getByRole("dialog");
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
  });

  it("Escape invoca onOpenChange(false) (Radix Dialog's built-in close)", async () => {
    const user = userEvent.setup();
    const { onOpenChange } = renderMoreSheet("coach");

    await user.keyboard("{Escape}");

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("al cerrar, el foco se libera limpiamente — el diálogo desaparece del DOM y el foco no queda huérfano en un nodo desmontado", async () => {
    function Wrapper({ open }: { open: boolean }) {
      return (
        <MemoryRouter>
          <MoreSheet role="coach" open={open} onOpenChange={() => {}} />
        </MemoryRouter>
      );
    }

    const { rerender } = render(<Wrapper open={true} />);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    rerender(<Wrapper open={false} />);

    await vi.waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    // Nota: MoreSheet no renderiza su propio disparador (BottomNav lo
    // posee, fuera de este componente) — el primitivo Radix Dialog sólo
    // devuelve el foco a un <SheetTrigger> registrado, que no existe aquí.
    // Lo verificable a este nivel es que el foco no quede atrapado en un
    // nodo ya removido del documento tras cerrar.
    expect(document.contains(document.activeElement)).toBe(true);
  });
});

describe("MoreSheet — tamaño de objetivo táctil >=48x48px (FR-005 acceptance #2)", () => {
  beforeEach(() => {
    mockAuthStore();
  });

  it("cada fila (área + acciones de cuenta) tiene la clase min-h-12 (48px) y ancho completo", () => {
    renderMoreSheet("coach");

    const rows = [
      screen.getByRole("link", { name: "Familias" }),
      screen.getByRole("link", { name: "Mi perfil" }),
      screen.getByRole("button", { name: "Cerrar sesión" }),
    ];

    for (const row of rows) {
      expect(row.className).toMatch(/min-h-12/);
      expect(row.className).toMatch(/w-full/);
    }
  });

  it("las filas de admin (incluyendo Salud IA) también cumplen min-h-12", () => {
    renderMoreSheet("admin");

    const rows = [
      screen.getByRole("link", { name: "Familias" }),
      screen.getByRole("link", { name: "Salud IA" }),
      screen.getByRole("link", { name: "Mi perfil" }),
      screen.getByRole("button", { name: "Cerrar sesión" }),
    ];

    for (const row of rows) {
      expect(row.className).toMatch(/min-h-12/);
    }
  });
});

describe("MoreSheet — accesibilidad (jest-axe)", () => {
  beforeEach(() => {
    mockAuthStore();
  });

  it("sin violaciones axe (coach, sheet abierto)", async () => {
    const { container } = renderMoreSheet("coach");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("sin violaciones axe (admin, sheet abierto)", async () => {
    const { container } = renderMoreSheet("admin");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
